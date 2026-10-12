#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""板端「断连 / 畸变包」恢复能力探针（G6 长稳鲁棒性）。

为什么需要它
------------
`tools/run_g3.sh` 只覆盖**正常**会话：连上去、按 P3 协议走完、断开。但长时间连续
运行里真正会把板子打死的是**异常连接**——上位机崩了留下半截包、网线被拔、
误发了一个 magic 不对的包。板端 lwIP 的 `g_conn` 是**单例**，一旦异常连接没被
正确回收，后面所有任务都连不上，而这在正常回归里一次也测不到。

本探针逐个注入异常，每注入一次就用一次完整的 CAPS 握手验证板子是否还活着，
并记录**恢复耗时与重试次数**。判据是「每个用例注入后板端都能重新握手」，
而不是「板子没崩」——后者用裸 TCP 连通性就能假装通过（见 g3_wait_ready.py 的教训）。

注意边界
--------
本探针只证明**协议层/连接层**的恢复，不证明数据通路正确。数据通路的唯一判据仍是
run_g3.sh 的图片 SHA-256；因此调用方应当在本探针跑完之后**再跑一轮判据轮**，
用「弄完还能出正确的图」把两件事接起来。

用法：
    python3 tools/board/g3_recovery_probe.py --ip 192.168.1.10 --port 7 \
        --jsonl tests/stress_results/<run>/recovery.jsonl
退出码 0 = 所有用例注入后板端都恢复；1 = 有用例未恢复。
"""

from __future__ import annotations

import argparse
import json
import socket
import struct
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO / "clients" / "python"))
import protocol as pr  # noqa: E402
from g3_caps import validate_caps  # noqa: E402


# ---------------------------------------------------------------------------
# 恢复判据：一次完整的 CAPS 握手（应用层），不是裸 TCP 连通性。
# ---------------------------------------------------------------------------
def try_caps(ip: str, port: int, timeout: float = 5.0):
    """成功返回 TaskCaps，失败抛异常。调用方负责重试。"""
    sock = socket.create_connection((ip, port), timeout=timeout)
    try:
        sock.settimeout(8)
        caps = pr.query_caps(sock, pr.NetStats())
        validate_caps(caps)
        return caps
    finally:
        try:
            sock.close()
        except OSError:
            pass


def wait_recovered(ip: str, port: int, deadline: float, interval: float, settle: float):
    """反复握手直到成功或超时。返回 (ok, 秒数, 尝试次数, 最后一次错误)。"""
    t0 = time.time()
    attempt = 0
    last_err = ""
    while time.time() - t0 < deadline:
        attempt += 1
        try:
            caps = try_caps(ip, port)
            # 板端 g_conn 单例：关连接要占一个 tcp 回调周期，让一会儿再交还控制权。
            time.sleep(settle)
            return True, time.time() - t0, attempt, "", caps
        except Exception as exc:  # noqa: BLE001 —— 探针要吞掉连接期异常继续重试
            last_err = f"{type(exc).__name__}: {exc}"
        time.sleep(interval)
    return False, time.time() - t0, attempt, last_err, None


# ---------------------------------------------------------------------------
# 异常注入用例。每个 injector 返回一段「板端观察到了什么」的描述字符串。
# 约定：injector 自己负责把 socket 关掉（含 RST 这种要特殊处理的）。
# ---------------------------------------------------------------------------
def _peek(sock: socket.socket, n: int = 64, timeout: float = 3.0) -> str:
    """读一下对端还回了什么：ERROR 包 / 直接关闭 / 静默超时，三者处置完全不同。"""
    sock.settimeout(timeout)
    try:
        data = sock.recv(n)
    except socket.timeout:
        return "no_reply_timeout"
    except OSError as exc:
        return f"recv_error:{type(exc).__name__}"
    if not data:
        return "peer_closed"
    return "reply:" + data[:16].hex()


def inj_half_header(ip, port):
    """半截包头就断开：模拟上位机在发包中途崩掉。"""
    s = socket.create_connection((ip, port), timeout=5)
    s.sendall(struct.pack(">HB", pr.MAGIC, pr.PKT_CAPS))  # 4 字节头只发了 3 字节
    obs = _peek(s)
    s.close()
    return obs, "发送 3/8 字节包头后正常关闭"


def inj_bad_magic(ip, port):
    """magic 不是 0xBEEF：板端必须能识别并拒绝，而不是把它当长度解析。"""
    s = socket.create_connection((ip, port), timeout=5)
    s.sendall(struct.pack(">HBBI", 0xDEAD, pr.PKT_CAPS, 0, 0))
    obs = _peek(s)
    s.close()
    return obs, "magic=0xDEAD 的完整包头"


def inj_unknown_type(ip, port):
    """magic 正确但包类型未定义：走的是板端的 default 分支。"""
    s = socket.create_connection((ip, port), timeout=5)
    s.sendall(pr.make_packet(0x7F))
    obs = _peek(s)
    s.close()
    return obs, "合法 magic + 未定义包类型 0x7F"


def inj_oversized_len(ip, port):
    """声明 4 GiB payload 却不发：板端若拿它去 malloc 或死等就会挂。"""
    s = socket.create_connection((ip, port), timeout=5)
    s.sendall(struct.pack(">HBBI", pr.MAGIC, pr.PKT_WM, 0, 0xFFFFFFF0))
    obs = _peek(s)
    s.close()
    return obs, "PKT_WM 声明 0xFFFFFFF0 字节 payload，实发 0 字节"


def inj_truncated_payload(ip, port):
    """声明 4096 字节只发 16 字节就断：半截 payload 的缓冲区必须被回收。"""
    s = socket.create_connection((ip, port), timeout=5)
    s.sendall(struct.pack(">HBBI", pr.MAGIC, pr.PKT_WM, 0, 4096) + b"\xA5" * 16)
    obs = _peek(s)
    s.close()
    return obs, "PKT_WM 声明 4096 字节，实发 16 字节后关闭"


def inj_reset_mid_caps(ip, port):
    """发完 CAPS 立刻 RST：模拟拔网线/上位机被 kill -9，对端收不到 FIN。"""
    s = socket.create_connection((ip, port), timeout=5)
    s.sendall(pr.make_packet(pr.PKT_CAPS))
    # SO_LINGER l_onoff=1 / l_linger=0 → close() 发 RST 而不是 FIN
    s.setsockopt(socket.SOL_SOCKET, socket.SO_LINGER, struct.pack("ii", 1, 0))
    s.close()
    return "rst_sent", "发送 PKT_CAPS 后以 TCP RST 断开（不发 FIN）"


def inj_idle_then_close(ip, port, idle=10.0):
    """占着连接什么都不发：单例 g_conn 被一个哑连接霸占的情形。"""
    s = socket.create_connection((ip, port), timeout=5)
    time.sleep(idle)
    obs = _peek(s, timeout=1.0)
    s.close()
    return obs, f"连上后静默占用 {idle:.0f}s 再关闭"


def inj_second_connection(ip, port):
    """第一条连接还开着就再连一条：g_conn 是单例，第二条的处置必须明确。"""
    s1 = socket.create_connection((ip, port), timeout=5)
    s1.sendall(pr.make_packet(pr.PKT_CAPS))
    try:
        s2 = socket.create_connection((ip, port), timeout=5)
    except Exception as exc:  # noqa: BLE001
        s1.close()
        return f"second_connect_refused:{type(exc).__name__}", "第一条连接未关时再发起第二条"
    obs2 = _peek(s2, timeout=3.0)
    s2.close()
    s1.close()
    return f"second={obs2}", "第一条连接未关时再发起第二条"


def inj_flood_bad_headers(ip, port, n=32):
    """连续灌 n 个垃圾包头：看有没有逐包泄漏（pbuf / 连接资源）。"""
    s = socket.create_connection((ip, port), timeout=5)
    try:
        for i in range(n):
            s.sendall(struct.pack(">HBBI", 0x1234 + i, 0xAA, 0xBB, i))
    except OSError as exc:
        s.close()
        return f"send_broken_at_{i}:{type(exc).__name__}", f"连灌 {n} 个垃圾包头"
    obs = _peek(s)
    s.close()
    return obs, f"连灌 {n} 个垃圾包头"


CASES = [
    ("baseline_caps", None, "对照组：一次正常 CAPS 握手"),
    ("half_header", inj_half_header, ""),
    ("bad_magic", inj_bad_magic, ""),
    ("unknown_pkt_type", inj_unknown_type, ""),
    ("oversized_length", inj_oversized_len, ""),
    ("truncated_payload", inj_truncated_payload, ""),
    ("reset_mid_caps", inj_reset_mid_caps, ""),
    ("idle_then_close", inj_idle_then_close, ""),
    ("second_connection", inj_second_connection, ""),
    ("flood_bad_headers", inj_flood_bad_headers, ""),
]


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--ip", required=True, help="必须显式指定本轮实测板端 IP")
    ap.add_argument("--port", type=int, default=7)
    ap.add_argument("--jsonl", required=True, help="结构化结果输出路径（JSONL，追加）")
    ap.add_argument("--deadline", type=float, default=60.0, help="每个用例的恢复超时")
    ap.add_argument("--interval", type=float, default=2.0)
    ap.add_argument("--settle", type=float, default=2.0)
    ap.add_argument("--cycles", type=int, default=1, help="整个用例表重复几遍")
    ap.add_argument("--tag", default="")
    args = ap.parse_args(argv)

    out = Path(args.jsonl)
    out.parent.mkdir(parents=True, exist_ok=True)

    n_fail = 0
    seq = 0
    with out.open("a", encoding="utf-8") as fh:
        for cycle in range(1, args.cycles + 1):
            for name, injector, desc in CASES:
                seq += 1
                ts = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
                t_inj0 = time.time()
                observed, detail = "", desc
                inj_err = ""
                if injector is not None:
                    try:
                        observed, detail = injector(args.ip, args.port)
                    except Exception as exc:  # noqa: BLE001
                        # 注入本身失败也是事实（例如板子已经连不上了），照记不漏。
                        inj_err = f"{type(exc).__name__}: {exc}"
                        observed = "inject_failed"
                t_inject = time.time() - t_inj0

                ok, t_rec, attempts, last_err, caps = wait_recovered(
                    args.ip, args.port, args.deadline, args.interval, args.settle)

                if ok:
                    failure_class = "pass"
                else:
                    # 恢复不了 = 板端连接层没回收 → 功能缺陷，不是工具问题。
                    failure_class = "functional"
                    n_fail += 1

                rec = {
                    "seq": seq,
                    "cycle": cycle,
                    "timestamp_utc": ts,
                    "tag": args.tag,
                    "case": name,
                    "injection": detail,
                    "board_response": observed,
                    "inject_error": inj_err,
                    "inject_s": round(t_inject, 3),
                    "recovered": ok,
                    "recovery_s": round(t_rec, 2),
                    "recovery_attempts": attempts,
                    "last_error": last_err,
                    "caps_read_bps": caps.read_bps if caps else None,
                    "caps_max_reads": caps.max_reads if caps else None,
                    "failure_class": failure_class,
                    "power_w": None,          # 未接功率计
                    "power_note": "UNMEASURED (no power meter attached)",
                }
                fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
                fh.flush()

                flag = "OK " if ok else "FAIL"
                print(f"[{flag}] c{cycle} {name:<20} 注入={observed:<28} "
                      f"恢复 {t_rec:5.1f}s / {attempts} 次尝试"
                      + ("" if ok else f"  ← {last_err}"))

    print(f"\n共 {seq} 个用例，未恢复 {n_fail} 个。结构化结果：{out}")
    return 1 if n_fail else 0


if __name__ == "__main__":
    sys.exit(main())
