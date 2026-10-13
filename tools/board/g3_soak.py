#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""tools/board/g3_soak.py —— 新板长稳（soak）编排：按**实际墙钟时长**跑完整 G3 轮。

## 为什么需要它

`docs/06` 的长稳验收口径是「以**实际墙钟时长**验收 2h/8h，保存逐轮证据」，
执行方式规定为「用 `run_g3.sh --artifact-dir` 完整包 + 显式 XSDB/device/PS 串口
编排」（旧的 `stress_test_suite.py` 已原样归档，不得再当入口）。

归档之后没有任何现成入口在做这件事，于是每次长稳都靠临时敲循环 —— 而临时循环
最容易出三种错：**跑不满 2h 就说跑完了**、**只统计成功轮不记录失败轮**、
**用 `--skip-boot` 时没先确认板上就是本包**。本脚本把这三条钉死。

## 它做什么

循环调 `run_g3.sh` 跑完整判据轮（全量输入、唯一判据 SHA），直到**墙钟**达到
`--hours`；每轮把 verdict/SHA/结果耗时逐轮写进 TSV。每隔 `--recovery-every` 轮
插一次 `g3_recovery_probe.py`（畸变包恢复），让长稳同时覆盖「连续正确」与
「被异常连接打扰后仍正确」两件事。

## 边界（读结论前必须看）

- **它不烧录**：`--skip-boot`。调用方必须先用本包跑过一轮真烧录并在 `--tag` 里
  记录制品包 SHA；否则「板上是哪份固件」无从证明。
- **不采集硬件周期与功耗**：TSV 里 `hardware_cycles`/`power_w` 恒为 `null`。
  板端结果耗时是**客户端打印值**，不是硬件计数器，**不得反推周期或功耗**。
- **墙钟达标 ≠ 全部轮次通过**：`--hours` 只保证跑够时长；只要有一轮 FAIL，
  脚本仍会继续（长稳要观察"坏了之后还能不能回来"），但**最终 verdict 会红**。
- 单板资源：跑之前确认没有别的任务在用这块板。
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
EXPECT_SHA_DEFAULT = "fcd0cf90bd680e7bbdc203e3398119504da0897acac9e2117008b4efb6b1f2c3"


def sh(cmd: list[str], log: Path, timeout: float | None = None) -> int:
    """跑一条命令，stdout+stderr 追加进 log。返回退出码（超时返回 124）。"""
    with log.open("a") as fh:
        fh.write("\n$ " + " ".join(cmd) + "\n")
        fh.flush()
        try:
            p = subprocess.run(cmd, cwd=str(REPO), stdout=fh, stderr=subprocess.STDOUT,
                               timeout=timeout)
            return p.returncode
        except subprocess.TimeoutExpired:
            fh.write(f"\n!! 超时（{timeout}s）\n")
            return 124


def parse_round(out_path: Path) -> dict:
    """从一轮 run_g3.sh 的输出里取 verdict / 判据 SHA / 板端结果耗时 / 轮目录。"""
    text = out_path.read_text(errors="replace")
    verdict = "?"
    m = re.findall(r"G3 (PASS|FAIL)", text)
    if m:
        verdict = m[-1]
    sha = ""
    m = re.findall(r"唯一判据.*?([0-9a-f]{64})", text, re.S)
    if m:
        sha = m[-1]
    t = ""
    m = re.findall(r"Result: 8100 bytes, ([0-9.]+)s", text)
    if m:
        t = m[-1]
    recs = ""
    m = re.findall(r"—\s*(\d+) 条记录", text)
    if m:
        recs = m[-1]
    run_dir = ""
    m = re.findall(r"(/mnt/[dD]/[^\s]*g3_runs/[0-9TZ]+)", text)
    if m:
        run_dir = m[-1]
    return {"verdict": verdict, "judge_sha": sha, "result_s": t,
            "records": recs, "run_dir": run_dir}


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--artifact-dir", required=True)
    ap.add_argument("--ip", required=True, help="必须显式指定本轮实测板端 IP")
    ap.add_argument("--port", type=int, default=7)
    ap.add_argument("--device", default="xc7z020")
    ap.add_argument("--xsdb", default=r"D:/xilinx/2026.1/Vitis/bin/xsdb.bat")
    ap.add_argument("--uart-port", default="COM10")
    ap.add_argument("--win-root", default=r"D:/bkb220_board_smoke")
    ap.add_argument("--hours", type=float, required=True, help="目标墙钟时长（小时）")
    ap.add_argument("--score-min", type=int, default=67)
    ap.add_argument("--expect-sha", default=EXPECT_SHA_DEFAULT)
    ap.add_argument("--recovery-every", type=int, default=10,
                    help="每多少轮插一次畸变包恢复探针；0 = 不插")
    ap.add_argument("--round-timeout", type=float, default=900.0)
    ap.add_argument("--out-dir", required=True)
    ap.add_argument("--tag", required=True, help="本轮长稳的标识（含制品包 SHA/来源）")
    args = ap.parse_args(argv)

    out = Path(args.out_dir)
    out.mkdir(parents=True, exist_ok=True)
    tsv = out / "soak.tsv"
    log = out / "soak.log"
    if not tsv.exists():
        tsv.write_text("round\twall_s\tverdict\trecords\tresult_s\tjudge_sha\tmatch\trun_dir\tnote\n")

    t0 = time.time()
    deadline = t0 + args.hours * 3600.0
    print(f"=== G3 长稳 run={time.strftime('%Y%m%dT%H%M%S')}  目标 {args.hours}h  墙钟 {time.ctime(t0)} ===")
    print(f"    制品包 {args.artifact_dir}")
    print(f"    tag   {args.tag}")

    rnd = 0
    n_fail = 0
    while time.time() < deadline:
        rnd += 1
        rlog = out / f"round{rnd:04d}.out"
        cmd = ["bash", "tools/run_g3.sh",
               "--artifact-dir", args.artifact_dir,
               "--xsdb", args.xsdb, "--device", args.device, "--strict-artifacts",
               "--uart-port", args.uart_port, "--ip", args.ip, "--port", str(args.port),
               "--win-root", args.win_root,
               "--score-min", str(args.score_min), "--full", "--skip-dump", "--skip-boot",
               "--expect-sha", args.expect_sha]
        with log.open("a") as fh:                 # 主日志只记一行索引，完整输出在 roundNNNN.out
            fh.write(f"\n[轮 {rnd}] $ {' '.join(cmd)}\n")
        rc = sh(cmd, rlog, timeout=args.round_timeout)
        info = parse_round(rlog)
        match = "YES" if info["judge_sha"] == args.expect_sha else "NO"
        note = "" if rc == 0 else f"rc={rc}"
        if info["verdict"] != "PASS":
            n_fail += 1
        with tsv.open("a") as fh:
            fh.write("\t".join([str(rnd), f"{time.time()-t0:.1f}", info["verdict"],
                                info["records"], info["result_s"], info["judge_sha"],
                                match, info["run_dir"], note]) + "\n")
        print(f"[{time.time()-t0:7.0f}s] 轮 {rnd:4d}  {info['verdict']:4s}  "
              f"{info['records']:>7s} 条  {info['result_s']:>6s}s  match={match} {note}")

        if args.recovery_every and rnd % args.recovery_every == 0:
            jl = out / "recovery.jsonl"
            prc = sh(["python3", "tools/board/g3_recovery_probe.py",
                      "--ip", args.ip, "--port", str(args.port),
                      "--jsonl", str(jl), "--cycles", "1",
                      "--tag", f"{args.tag}-soak-r{rnd}"], log, timeout=600)
            print(f"          ↳ 畸变包探针 rc={prc}")

    # 收尾：把 TSV 汇成一条可判读的结论（墙钟 + 轮次 + 失败轮 + 退出码）
    rows = [l.split("\t") for l in tsv.read_text().splitlines()[1:] if l.strip()]
    wall = time.time() - t0
    ok = [r for r in rows if r[2] == "PASS" and r[6] == "YES"]
    verdict = "PASS" if (rows and len(ok) == len(rows) and wall >= args.hours * 3600 * 0.98) else "FAIL"
    summary = {
        "tag": args.tag, "artifact_dir": args.artifact_dir, "ip": args.ip,
        "target_hours": args.hours, "wall_s": round(wall, 1),
        "rounds": len(rows), "rounds_pass_with_expected_sha": len(ok),
        "rounds_failed": len(rows) - len(ok), "verdict": verdict,
        "hardware_cycles": None, "power_w": None,
        "note": ("UNMEASURED: 无外部 UART 周期采集、无功率计；result_s 是客户端打印值，"
                 "不得反推周期或功耗"),
    }
    (out / "soak_summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=1))
    print(f"\n墙钟 {wall/3600:.3f} h（目标 {args.hours} h），{len(rows)} 轮，"
          f"通过 {len(ok)} 轮，失败 {len(rows)-len(ok)} 轮")
    print(f"长稳结论：{verdict}  → {out/'soak_summary.json'}")
    return 0 if verdict == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
