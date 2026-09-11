#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""tools/board/g3_config_guard_probe.py —— 板端配置/容量守卫的故障注入探针

## 为什么需要它

固件里有三道**防越界守卫**，但它们**从未在板上被触发过**：

    C3  容量防溢出   echo.c: total_reads_received + num_reads > TOTAL_READS
    P3  超出声明条数 echo.c: ... > conn->cfg.total_reads
    C2  非整帧尾批   ddr_layout_validate(): records % FRAME_READS != 0

`clients/python/task_protocol.py` 还定义了 9 种 CONFIG 拒绝理由
（版本/read_bps/几何/symbols/total_reads/score_min/CRC/重复/顺序），
同样没有任何板级留证证明它们会触发。

**没被触发过的守卫等于没有守卫。** 这一点在 2026-09-11 尤其要紧：
`TOTAL_READS` 刚由 108000 改为 129600，**直接改了 C3 的阈值**——
守卫的行为变了，却没有任何实验验证过它还拦得住。

`AGENTS.md` 的教训已经说过同类事：B27 的缺陷在所有仿真里都是绿的，
因为「真实固件那串寄存器写时序从未被回放过」。守卫也一样：
不去真的越界一次，就不知道它拦不拦得住。

## 判据（每个用例两条，缺一不可）

1. **拒绝**：板端必须明确拒绝（`PKT_ERROR` 或连接被拒），
   **不得**接受后静默溢出 DDR；
2. **可恢复**：注入之后板子必须仍能跑通一个正常任务——
   守卫把自己卡死和没有守卫一样糟。

## 用法

    tools/board/g3_config_guard_probe.py
    tools/board/g3_config_guard_probe.py --ip 192.168.1.10 --out-dir <dir>

**前提**：板子已烧录并在运行，且没有其他进程占用板卡
（板端 lwIP 是单例 `g_conn`，并发连接会破坏正在进行的任务）。
"""

from __future__ import annotations

import argparse
import json
import socket
import struct
import zlib
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent.parent
CLIENTS_PY = REPO / "clients" / "python"
if str(CLIENTS_PY) not in sys.path:
    sys.path.insert(0, str(CLIENTS_PY))

import protocol as pr  # noqa: E402
from task_protocol import TaskCaps  # noqa: E402

class _Stats:
    """protocol.recv_packet 会往 stats 上累加字节数，传 None 会 AttributeError。
    本探针不关心流量统计，给个最小桩即可。"""
    def __init__(self):
        self.download = 0
        self.upload = 0


WM_BITS = 81000
READ_BPS = 150
NUM_LC = 50
STRIDE = 807


def _raw_config_payload(*, read_bps: int, total_reads: int, score_min: int,
                        num_lc: int = NUM_LC, stride: int = STRIDE,
                        symbols: int = WM_BITS // 2, version: int = 1) -> bytes:
    """按线格式手工拼 CONFIG payload，不做任何校验。

    布局与 task_protocol.TaskSpec.config_payload() 一致：
        >BBHIIIII  version, read_bps, 保留(0), num_lc, stride, symbols,
                   total_reads, score_min
        + 16 B 保留 + 大端 CRC32(body)
    改协议时这里必须跟着改——本函数刻意不复用 TaskSpec，就是为了绕开它的 validate()。
    """
    body = struct.pack(">BBHIIIII", version, read_bps, 0, num_lc, stride,
                       symbols, total_reads, score_min) + b"\x00" * 16
    return body + struct.pack(">I", zlib.crc32(body) & 0xFFFFFFFF)


def _connect(ip: str, port: int, timeout: float = 8.0) -> socket.socket:
    s = socket.socket()
    s.settimeout(timeout)
    s.connect((ip, port))
    return s


def _caps(sock) -> dict:
    """取板端能力，用来推导「刚好越界」的参数——不要写死数字，
    否则改了 TOTAL_READS 之后这个探针又会去测一个过时的阈值。"""
    sock.sendall(pr.make_packet(pr.PKT_CAPS, b""))
    t, payload = pr.recv_packet(sock, _Stats(), timeout=8.0)
    if t != pr.PKT_CAPS_INFO:
        raise RuntimeError(f"CAPS 应答类型异常: 0x{t:02X}")
    caps = TaskCaps.from_payload(payload)
    return {"read_bps": caps.read_bps, "max_reads": caps.max_reads,
            "num_lc": caps.num_lc, "stride": caps.stride}


def _try_config(ip: str, port: int, total_reads: int, read_bps: int = READ_BPS,
                score_min: int | None = None) -> tuple[bool, str]:
    """下发一个 CONFIG，返回 (是否被接受, 说明)。"""
    try:
        sock = _connect(ip, port)
    except Exception as e:
        return False, f"连接失败: {e}"
    try:
        # 【关键】手工拼 CONFIG 字节，**完全绕开客户端所有校验**。
        # 演进史（两次都是自己骗自己，留着当反例）：
        #   v1 用 TaskSpec.from_watermark_bits() —— 6 个用例里 4 个被上位机拒了；
        #   v2 改用 TaskSpec(...) 直接构造 —— 它的 validate() 照样拦，5 个没到板。
        # 两版都报「通过」，但**板端守卫一次都没被触发**。
        # 一个从没碰到被测对象却报绿的探针，比没有探针更糟：它制造虚假信心。
        # 判据必须有鉴别力（AGENTS.md），所以这里直接按线格式拼字节。
        payload = _raw_config_payload(read_bps=read_bps, total_reads=total_reads,
                                      score_min=score_min if score_min is not None else 67)
        sock.sendall(pr.make_packet(pr.PKT_CONFIG, payload))
        t, _ = pr.recv_packet(sock, _Stats(), timeout=8.0)
        if t == pr.PKT_CONFIG_OK:
            return True, "板端接受 CONFIG"
        if t == pr.PKT_ERROR:
            return False, "板端拒绝 (PKT_ERROR) ← 固件守卫生效"
        return False, f"板端应答异常类型 0x{t:02X}"
    except socket.timeout:
        return False, "板端无应答(超时)"
    except Exception as e:
        return False, f"异常: {e}"
    finally:
        try:
            sock.close()
        except Exception:
            pass


def _board_alive(ip: str, port: int) -> bool:
    """注入后板子是否仍可用：能完成一次 CAPS 握手即算存活。"""
    for _ in range(6):
        try:
            s = _connect(ip, port, timeout=6.0)
            try:
                _caps(s)
                return True
            finally:
                s.close()
        except Exception:
            time.sleep(2.0)
    return False


def _probe_late_guard(ip: str, port: int, max_reads: int) -> dict:
    """CONFIG 被接受之后，后置守卫（BATCH 的 C3 / POST 的 ddr_layout_validate）
    是否仍拦得住？这一条决定严重性：

    ⚠️ **已知局限（2026-09-11，尚未跑通）**：本函数在 PKT_WM 之后收不到应答而超时，
    试过 10125 / 10128 两种水印长度均如此，因此**后置守卫至今没有板级实测**。
    目前只能由代码审查界定严重性：
        echo.c process_batch(): total_reads_received + num_reads > TOTAL_READS -> 返回 -1
    该判断位于任何 DDR 写之前，故 DDR 越界风险已被代码层拦住。
    但「代码里有」不等于「板上会触发」——这正是本探针要证的东西，
    所以在跑通之前，**不得据此宣称后置守卫已验证**。

      - 若后置守卫拦得住 -> DDR 安全，缺陷是「拒绝得太晚 + 协议契约未执行」；
      - 若也拦不住       -> 真实的越界写风险，等级完全不同。

    做法：先用超容量 total_reads 让 CONFIG 通过，再真的送一批读段上去。
    """
    out = {"case": "late_guard_batch_over_capacity"}
    try:
        sock = _connect(ip, port, timeout=10.0)
    except Exception as e:
        out["error"] = f"连接失败: {e}"
        return out
    try:
        # 1) 声明一个超容量任务，上一节已证明 CONFIG 会被接受
        over = max_reads + 6400
        sock.sendall(pr.make_packet(pr.PKT_CONFIG,
                     _raw_config_payload(read_bps=READ_BPS, total_reads=over,
                                         score_min=67)))
        t, _ = pr.recv_packet(sock, _Stats(), timeout=8.0)
        out["config_accepted"] = (t == pr.PKT_CONFIG_OK)

        # 2) 先送水印——固件的包序要求 CONFIG -> WM -> BATCH，
        #    跳过 WM 直接发 BATCH 会让板端不应答（首版探针在这里超时）。
        wm = b"\x00" * 10128   # 板端实录: [WM] Stored 10128 bytes (81000 bits)
        # 10125 = 81000/8 向上对齐到 16 的倍数；发 10125 会让板端不应答
        sock.sendall(pr.make_packet(pr.PKT_WM, wm))
        tw, _ = pr.recv_packet(sock, _Stats(), timeout=10.0)
        out["wm_accepted"] = (tw == pr.PKT_WM_OK)

        # 3) 送一批读段（64 条，40 B/条），看 BATCH 是否被接受
        batch = struct.pack(">I", 64) + b"\x00" * (64 * 40)
        sock.sendall(pr.make_packet(pr.PKT_BATCH, batch))
        t2, _ = pr.recv_packet(sock, _Stats(), timeout=8.0)
        out["first_batch_accepted"] = (t2 == pr.PKT_BATCH_OK)
        out["first_batch_type"] = f"0x{t2:02X}"
    except socket.timeout:
        out["error"] = "超时"
    except Exception as e:
        out["error"] = f"异常: {e}"
    finally:
        try:
            sock.close()
        except Exception:
            pass
    out["board_alive_after"] = _board_alive(ip, port)
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--ip", default="192.168.1.10")
    ap.add_argument("--port", type=int, default=7)
    ap.add_argument("--out-dir", default=None)
    args = ap.parse_args(argv)

    run_id = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
    out_dir = Path(args.out_dir) if args.out_dir else \
        REPO / "tests" / "stress_results" / f"g6_config_guard_{run_id}"
    out_dir.mkdir(parents=True, exist_ok=True)

    print(f"=== 板端配置/容量守卫探针 run={run_id} ===")
    print(f"    目标 {args.ip}:{args.port}   留证 {out_dir}")

    # 先取 CAPS，据此推导越界参数——不写死阈值
    s = _connect(args.ip, args.port)
    try:
        caps = _caps(s)
    finally:
        s.close()
    max_reads = int(caps["max_reads"])
    print(f"    板端 CAPS: read_bps={caps['read_bps']} num_lc={caps['num_lc']} "
          f"stride={caps['stride']} max_reads={max_reads}\n")

    FRAME = 64
    cases = [
        # (名称, total_reads, read_bps, 期望被接受?, 说明)
        ("capacity_ok_boundary", max_reads, READ_BPS, True,
         "恰好等于容量上限，应当接受（守卫不能把合法值也拦掉）"),
        ("capacity_exceed_by_one_frame", max_reads + FRAME, READ_BPS, False,
         "超容量一帧，C3 应当拒绝"),
        ("capacity_exceed_large", max_reads * 2, READ_BPS, False,
         "远超容量，C3 应当拒绝"),
        ("not_frame_aligned", max_reads - 1, READ_BPS, False,
         "非 64 整数倍，C2 应当拒绝"),
        ("zero_reads", 0, READ_BPS, False,
         "空任务，应当拒绝"),
        ("wrong_read_bps", 4096, 250, False,
         "read_bps=250 与 150bp 比特流不符，几何校验应当拒绝"),
    ]

    rows = []
    for name, tr, rbps, expect_ok, why in cases:
        accepted, detail = _try_config(args.ip, args.port, tr, rbps)
        alive = _board_alive(args.ip, args.port)
        ok = (accepted == expect_ok) and alive
        rows.append({
            "case": name, "total_reads": tr, "read_bps": rbps,
            "expect_accepted": expect_ok, "accepted": accepted,
            "detail": detail, "board_alive_after": alive, "verdict": ok,
            "why": why,
        })
        mark = "✓" if ok else "✗"
        print(f"  {mark} {name:<30} 期望{'接受' if expect_ok else '拒绝'} / "
              f"实测{'接受' if accepted else '拒绝'} / 存活={alive}")
        print(f"      {detail}   （{why}）")
        time.sleep(1.5)   # 让板端单例 g_conn 回收

    late = _probe_late_guard(args.ip, args.port, max_reads)
    print(f"\n  [后置守卫] CONFIG 接受={late.get('config_accepted')} "
          f"首批 BATCH 接受={late.get('first_batch_accepted')} "
          f"({late.get('first_batch_type','-')}) 存活={late.get('board_alive_after')}")
    print("      判断严重性用：后置守卫拦得住 = DDR 安全、缺陷是拒绝太晚；"
          "拦不住 = 真实越界写风险")
    rows.append(late)

    (out_dir / "config_guard.jsonl").write_text(
        "\n".join(json.dumps(r, ensure_ascii=False) for r in rows) + "\n",
        encoding="utf-8")

    passed = sum(1 for r in rows if r.get("verdict"))
    print(f"\n结果: {passed}/{len(rows)} 通过   留证 {out_dir}/config_guard.jsonl")
    if passed != len(rows):
        print("⚠️  守卫行为与预期不符——要么拦不住越界，要么把合法值也拦掉，"
              "两者都必须定位后再上板跑正式任务。")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
