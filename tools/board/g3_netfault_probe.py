#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""板端「任务中途断网 / 上位机崩溃」恢复探针（G6）。

与 g3_recovery_probe.py 的分工
------------------------------
`g3_recovery_probe.py` 注入的是**畸变包**：连接是好的，内容是坏的。本探针注入的是
**连接本身消失**，而且是最难的那一种——**板端连 FIN 都收不到**：

    上位机任务跑到一半 → iptables 把双向流量黑洞掉 → SIGKILL 掉 first.py

内核发出的 FIN 会被黑洞规则丢掉，于是板端的 `g_conn`（lwIP 单例）停在
"ESTABLISHED、对端再也不说话"的状态。这正是现场拔网线/交换机抽风的样子，
也是**正常回归一次都测不到**的路径：run_g3.sh 的每一轮都善始善终。

判据分两层，缺一不可：
  1. **连接层**：解除黑洞后，板端要能重新完成 CAPS 握手（`recovered`）；
  2. **数据层**：恢复之后再跑一轮**判据轮**，图片 SHA-256 必须仍与判据逐位相同。
     只测第 1 层是不够的——板子"能连上"不等于中途夭折的那次任务没在 DDR / Voter
     累加器里留下残渣。第 2 层由调用方（run_g3.sh 判据轮）完成，本脚本只负责
     把板子弄成那个状态并记录恢复过程。

安全性：iptables 规则在 finally 里删除，异常/中断都会还原；只针对板卡 IP，
不动其它网段。

用法：
    sudo -n true && python3 tools/board/g3_netfault_probe.py \
        --jsonl tests/stress_results/<run>/netfault.jsonl
退出码 0 = 每个用例解除故障后板端都恢复了 CAPS 握手。
"""

from __future__ import annotations

import argparse
import json
import os
import signal
import socket
import subprocess
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO / "clients" / "python"))
import protocol as pr  # noqa: E402


def sh(cmd: list[str]) -> tuple[int, str]:
    p = subprocess.run(cmd, capture_output=True, text=True)
    return p.returncode, (p.stdout + p.stderr).strip()


class Blackhole:
    """把与板卡之间的双向流量丢掉。进出都要挡，否则 FIN/RST 仍会漏过去。"""

    def __init__(self, ip: str):
        self.ip = ip
        self.applied = False

    def __enter__(self):
        for chain, key in (("OUTPUT", "-d"), ("INPUT", "-s")):
            rc, out = sh(["sudo", "-n", "iptables", "-I", chain, "1", key, self.ip, "-j", "DROP"])
            if rc != 0:
                self.__exit__(None, None, None)
                raise RuntimeError(f"插入 iptables 规则失败（{chain}）：{out}")
        self.applied = True
        return self

    def __exit__(self, *exc):
        # 删规则必须尽力而为并且幂等：漏删会把板子从本机彻底隔离，比测试失败严重得多。
        for chain, key in (("OUTPUT", "-d"), ("INPUT", "-s")):
            for _ in range(5):
                rc, _out = sh(["sudo", "-n", "iptables", "-D", chain, key, self.ip, "-j", "DROP"])
                if rc != 0:
                    break
        self.applied = False
        return False


def try_caps(ip: str, port: int, timeout: float = 5.0):
    sock = socket.create_connection((ip, port), timeout=timeout)
    try:
        sock.settimeout(8)
        return pr.query_caps(sock, pr.NetStats())
    finally:
        try:
            sock.close()
        except OSError:
            pass


def wait_recovered(ip, port, deadline, interval=2.0, settle=2.0):
    t0 = time.time()
    attempt = 0
    last_err = ""
    while time.time() - t0 < deadline:
        attempt += 1
        try:
            try_caps(ip, port)
            time.sleep(settle)
            return True, time.time() - t0, attempt, ""
        except Exception as exc:  # noqa: BLE001
            last_err = f"{type(exc).__name__}: {exc}"
        time.sleep(interval)
    return False, time.time() - t0, attempt, last_err


def start_task(args, log_path: Path) -> subprocess.Popen:
    """起一个真实任务；用 setsid 独立进程组，方便整组 kill 掉。"""
    cmd = [
        sys.executable, "clients/python/first.py",
        "--ip", args.ip, "--port", str(args.port),
        "--reads", args.reads, "--watermark", args.watermark,
        "--output", str(log_path.with_suffix(".dec.txt")),
        "--orient", "both", "--limit", str(args.limit),
        "--score-min", str(args.score_min),
        "--read-bps", "150", "--result-timeout", "300",
    ]
    fh = log_path.open("w", encoding="utf-8")
    return subprocess.Popen(cmd, cwd=str(REPO), stdout=fh, stderr=subprocess.STDOUT,
                            start_new_session=True)


def kill_group(proc: subprocess.Popen) -> None:
    try:
        os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
    except (ProcessLookupError, PermissionError):
        pass
    try:
        proc.wait(timeout=10)
    except subprocess.TimeoutExpired:
        pass


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--ip", default="192.168.1.10")
    ap.add_argument("--port", type=int, default=7)
    ap.add_argument("--jsonl", required=True)
    ap.add_argument("--deadline", type=float, default=180.0, help="解除故障后最多等多少秒")
    ap.add_argument("--outage", type=float, default=25.0, help="黑洞持续多少秒")
    ap.add_argument("--limit", type=int, default=16384, help="被中断任务的源读段数（要够长）")
    ap.add_argument("--score-min", type=int, default=67)
    ap.add_argument("--reads",
                    default="data/R0.83_data/Sequencing data/DNA-40.5Kb-MC-SE150.fastq")
    ap.add_argument("--watermark",
                    default="data/R0.83_data/Source data/Watermark sequences/r0.83_watermark.txt")
    ap.add_argument("--tag", default="")
    args = ap.parse_args(argv)

    out = Path(args.jsonl)
    out.parent.mkdir(parents=True, exist_ok=True)
    scratch = out.parent / "netfault_logs"
    scratch.mkdir(exist_ok=True)

    records = []
    n_fail = 0

    def record(case, detail, ok, t_rec, attempts, last_err, extra=None):
        nonlocal n_fail
        if not ok:
            n_fail += 1
        rec = {
            "timestamp_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "tag": args.tag,
            "case": case,
            "injection": detail,
            "outage_s": args.outage,
            "recovered": ok,
            "recovery_s": round(t_rec, 2),
            "recovery_attempts": attempts,
            "last_error": last_err,
            "failure_class": "pass" if ok else "functional",
            "power_w": None,
            "power_note": "UNMEASURED (no power meter attached) — N/A",
        }
        if extra:
            rec.update(extra)
        records.append(rec)
        print(f"[{'OK ' if ok else 'FAIL'}] {case:<24} 恢复 {t_rec:6.1f}s / {attempts} 次尝试"
              + ("" if ok else f"  ← {last_err}"))

    # ---- 用例 1：纯断网（无任务在跑）----------------------------------------
    # 先测最简单的一档：连接层本来就是空闲的，恢复应当是即时的。
    # 它同时也是用例 2 的对照——若这一档就恢复不了，那问题与"任务中途"无关。
    with Blackhole(args.ip):
        time.sleep(args.outage)
        try:
            try_caps(args.ip, args.port, timeout=3)
            blocked = False
        except Exception:  # noqa: BLE001
            blocked = True
    ok, t, a, err = wait_recovered(args.ip, args.port, args.deadline)
    record("idle_outage", f"空闲状态下双向黑洞 {args.outage:.0f}s", ok, t, a, err,
           {"outage_confirmed_blocked": blocked})

    # ---- 用例 2：任务中途断网 + 上位机被 kill -9 ----------------------------
    # 关键点：先插黑洞、再 kill。顺序反了的话内核的 FIN 会先跑出去，
    # 板端就是一次"正常关闭"，测的就不是断网了。
    log_path = scratch / "task_aborted.log"
    proc = start_task(args, log_path)
    # 等它真的进入传输阶段再动手，否则可能还卡在读 FASTQ，压根没连上板子。
    t_wait0 = time.time()
    entered = False
    while time.time() - t_wait0 < 120:
        if log_path.is_file() and "Watermark:" in log_path.read_text(errors="replace"):
            entered = True
            break
        if proc.poll() is not None:
            break
        time.sleep(0.5)
    time.sleep(1.0)   # 让它再往前跑一点，确保是"中途"而不是刚开头

    with Blackhole(args.ip):
        kill_group(proc)
        time.sleep(args.outage)
    ok2, t2, a2, err2 = wait_recovered(args.ip, args.port, args.deadline)
    record("mid_task_outage_kill", 
           f"任务（{args.limit} 源读段）传输中途双向黑洞 {args.outage:.0f}s 并 SIGKILL 上位机",
           ok2, t2, a2, err2,
           {"task_entered_transfer": entered,
            "task_log": str(log_path.relative_to(REPO)) if log_path.is_absolute() else str(log_path)})

    # ---- 用例 3：紧接着再来一次，看恢复是否可重复 ---------------------------
    # 一次恢复可能是运气（比如刚好撞上 lwIP 的某个超时）。重复一次才谈得上"机制"。
    log_path2 = scratch / "task_aborted_2.log"
    proc2 = start_task(args, log_path2)
    t_wait0 = time.time()
    entered2 = False
    while time.time() - t_wait0 < 120:
        if log_path2.is_file() and "Watermark:" in log_path2.read_text(errors="replace"):
            entered2 = True
            break
        if proc2.poll() is not None:
            break
        time.sleep(0.5)
    time.sleep(1.0)
    with Blackhole(args.ip):
        kill_group(proc2)
        time.sleep(args.outage)
    ok3, t3, a3, err3 = wait_recovered(args.ip, args.port, args.deadline)
    record("mid_task_outage_kill_repeat",
           f"重复一次：任务传输中途双向黑洞 {args.outage:.0f}s 并 SIGKILL 上位机",
           ok3, t3, a3, err3, {"task_entered_transfer": entered2})

    with out.open("a", encoding="utf-8") as fh:
        for r in records:
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")

    # 收尾自检：规则必须一条不剩，否则后续所有测试都会以"板子挂了"的面目失败。
    rc, listing = sh(["sudo", "-n", "iptables", "-S"])
    leftover = [ln for ln in listing.splitlines() if args.ip in ln and "DROP" in ln]
    if leftover:
        print(f"\n⚠️ iptables 仍残留规则，请手工清理：\n" + "\n".join(leftover), file=sys.stderr)
        return 2
    print(f"\niptables 规则已清理干净。共 {len(records)} 个用例，未恢复 {n_fail} 个 → {out}")
    return 1 if n_fail else 0


if __name__ == "__main__":
    sys.exit(main())
