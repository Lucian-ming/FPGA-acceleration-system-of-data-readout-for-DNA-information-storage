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

- **它不烧录**：`--skip-boot`。启动时先用 XSDB 将板上 `fw_build_id` 与所选包
  `manifest.json` 核对一次；成功读回留证会传给各轮 G3，避免每轮重复连接 JTAG。
- **不采集硬件周期与功耗**：TSV 里 `hardware_cycles`/`power_w` 恒为 `null`。
  板端结果耗时是**客户端打印值**，不是硬件计数器，**不得反推周期或功耗**。
- **墙钟达标 ≠ 全部轮次通过**：`--hours` 只保证跑够时长；只要有一轮 FAIL，
  脚本仍会继续（长稳要观察"坏了之后还能不能回来"），但**最终 verdict 会红**。
- 单板资源：跑之前确认没有别的任务在用这块板。
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

# Windows 上 PATH 里可能同时有 Git Bash 与 System32 的 WSL bash；后者不带
# Windows 盘符语义，会让 run_g3.sh 走进 WSL 分支。允许用 G3_BASH 显式指定。
BASH = os.environ.get("G3_BASH") or "bash"

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
    # 【2026-10-15 补】旧措辞「唯一判据 … SHA」是三层判据实施前的格式；改成三层后
    # run_g3.sh 输出的是「系统判据 : PASS — SHA-256 <hex>；期望 <hex>」。
    # 只留旧正则会让 judge_sha 恒空、match 恒 NO —— 一个不会响的检查。
    # 先按新格式取"板端码字载荷"那一行，取不到再退回旧格式。
    m = re.findall(r"系统判据\s*:\s*(?:PASS|FAIL)\s*—\s*SHA-256\s*([0-9a-f]{64})", text)
    if m:
        sha = m[-1]
    else:
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
    ap.add_argument("--xsdb", default=os.environ.get("G3_XSDB", ""),
                    help="必填（或设 G3_XSDB）：Vitis xsdb 可执行文件路径")
    ap.add_argument("--uart-port", default=os.environ.get("G3_UART_PORT", "COM10"))
    ap.add_argument("--win-root", default=os.environ.get("G3_WIN_ROOT", ""),
                    help="必填（或设 G3_WIN_ROOT）：板测留证根目录")
    ap.add_argument("--hw-server", default="",
                    help="必填，如 TCP:127.0.0.1:3132；固件身份核对必须显式指定")
    ap.add_argument("--fw-id-nm", default="",
                    help="可选：覆盖 arm-none-eabi-nm 路径；仅在默认工具路径不适用时使用")
    ap.add_argument("--hours", type=float, required=True, help="目标墙钟时长（小时）")
    ap.add_argument("--score-min", type=int, default=67)
    ap.add_argument("--expect-sha", default=EXPECT_SHA_DEFAULT)
    ap.add_argument("--recovery-every", type=int, default=10,
                    help="每多少轮插一次畸变包恢复探针；0 = 不插")
    ap.add_argument("--round-timeout", type=float, default=900.0)
    ap.add_argument("--out-dir", required=True)
    ap.add_argument("--i-know-overwrite-existing", action="store_true",
                    help="明确允许复用非空输出目录；本轮会重置 TSV、日志、身份读回与恢复探针留证")
    ap.add_argument("--stop-after-consecutive-failures", type=int, default=3,
                    help="连续失败达到此轮数时提前停止（默认 3；单轮失败仍会继续）")
    ap.add_argument("--tag", required=True, help="本轮长稳的标识（含制品包 SHA/来源）")
    args = ap.parse_args(argv)

    if not args.xsdb.strip() or not args.win_root.strip():
        ap.error("必须显式传 --xsdb 与 --win-root（或设 G3_XSDB / G3_WIN_ROOT）；脚本不提供本机默认路径")
    if not args.hw_server.strip():
        ap.error("必须显式传 --hw-server TCP:<主机>:<端口>；固件身份核对不使用隐式 server")
    if args.stop_after_consecutive_failures < 1:
        ap.error("--stop-after-consecutive-failures 必须 >= 1")
    if args.hours <= 0:
        ap.error("--hours 必须大于 0")

    out = Path(args.out_dir)
    if out.exists() and not out.is_dir():
        ap.error(f"--out-dir 已存在但不是目录：{out}")
    if out.is_dir() and any(out.iterdir()) and not args.i_know_overwrite_existing:
        ap.error(f"--out-dir 已存在且非空：{out}；确认覆盖时传 --i-know-overwrite-existing")
    out.mkdir(parents=True, exist_ok=True)
    tsv = out / "soak.tsv"
    log = out / "soak.log"
    # 通过非空目录检查后，启动新一轮数据；显式覆盖时也不能把旧 TSV 混入新结论。
    tsv.write_text("round\twall_s\tverdict\trecords\tresult_s\tjudge_sha\tmatch\trun_dir\tnote\tprocess_rc\n")
    log.write_text("")
    (out / "recovery.jsonl").write_text("")

    identity_log = out / "fw_build_id_startup.out"
    identity_evidence = out.resolve() / "fw_build_id_startup.json"
    identity_log.write_text("")
    identity_evidence.write_text("")
    identity_cmd = [BASH, "tools/run_g3.sh",
                    "--artifact-dir", args.artifact_dir,
                    "--xsdb", args.xsdb, "--device", args.device, "--strict-artifacts",
                    "--ip", args.ip, "--port", str(args.port), "--win-root", args.win_root,
                    "--hw-server", args.hw_server, "--skip-boot", "--fw-id-only",
                    "--fw-id-evidence-out", str(identity_evidence)]
    if args.fw_id_nm:
        identity_cmd += ["--fw-id-nm", args.fw_id_nm]
    with log.open("a") as fh:
        fh.write("\n[启动固件身份核对] $ " + " ".join(identity_cmd) + "\n")
    identity_rc = sh(identity_cmd, identity_log, timeout=min(args.round_timeout, 180.0))
    identity_doc = None
    if identity_evidence.is_file():
        try:
            identity_doc = json.loads(identity_evidence.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            identity_doc = None
    identity_ok = (
        identity_rc == 0 and isinstance(identity_doc, dict) and
        identity_doc.get("verdict") == "PASS" and
        identity_doc.get("check_source") == "live_readback" and
        isinstance(identity_doc.get("expected_fw_build_id"), str) and
        re.fullmatch(r"[0-9a-f]{16}", identity_doc["expected_fw_build_id"]) and
        identity_doc.get("expected_fw_build_id") == identity_doc.get("actual_fw_build_id") and
        identity_doc.get("expected_fw_build_id") != "0000000000000000" and
        identity_doc.get("actual_fw_build_id") != "0000000000000000"
    )
    if not identity_ok:
        with log.open("a") as fh:
            fh.write(f"\n[启动固件身份核对] FAIL rc={identity_rc}; 详见 {identity_log}\n")
        summary = {
            "tag": args.tag, "artifact_dir": args.artifact_dir, "ip": args.ip,
            "target_hours": args.hours, "wall_s": 0.0,
            "rounds": 0, "rounds_pass_with_expected_sha": 0,
            "rounds_failed": 0, "rounds_unverified": 0,
            "verdict": "FAIL", "stop_reason": "fw_build_id_startup_check_failed",
            "fw_build_id_check": {
                "verdict": "FAIL", "exit_code": identity_rc,
                "expected_fw_build_id": (identity_doc or {}).get("expected_fw_build_id", "<unknown>"),
                "actual_fw_build_id": (identity_doc or {}).get("actual_fw_build_id", "<unknown>"),
                "reason": (identity_doc or {}).get("reason", "startup readback failed"),
                "evidence": str(identity_evidence), "log": str(identity_log),
            },
            "hardware_cycles": None, "power_w": None,
            "note": "启动身份核对未通过；没有开始长稳循环。",
        }
        (out / "soak_summary.json").write_text(
            json.dumps(summary, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
        print(f"启动失败：板上运行的固件与所选包不符，未启动长稳；见 {identity_log}")
        return 1

    expected_fw_id = identity_doc["expected_fw_build_id"]
    actual_fw_id = identity_doc["actual_fw_build_id"]
    with log.open("a") as fh:
        fh.write(f"[启动固件身份核对] PASS expected={expected_fw_id} actual={actual_fw_id} "
                 f"checked_utc={identity_doc.get('checked_utc', '')}\n")
    print(f"板上固件身份核对通过：期望={expected_fw_id}；实读={actual_fw_id}")

    t0 = time.time()
    deadline = t0 + args.hours * 3600.0
    print(f"=== G3 长稳 run={time.strftime('%Y%m%dT%H%M%S')}  目标 {args.hours}h  墙钟 {time.ctime(t0)} ===")
    print(f"    制品包 {args.artifact_dir}")
    print(f"    tag   {args.tag}")

    rnd = 0
    recovery_probe_rcs: list[int] = []
    consecutive_failures = 0
    stop_reason = ""
    while time.time() < deadline:
        rnd += 1
        rlog = out / f"round{rnd:04d}.out"
        rlog.write_text("")
        cmd = [BASH, "tools/run_g3.sh",
               "--artifact-dir", args.artifact_dir,
               "--xsdb", args.xsdb, "--device", args.device, "--strict-artifacts",
               "--uart-port", args.uart_port, "--ip", args.ip, "--port", str(args.port),
               "--win-root", args.win_root,
               "--score-min", str(args.score_min), "--full", "--skip-dump", "--skip-boot",
               "--expect-sha", args.expect_sha,
               "--hw-server", args.hw_server,
               "--fw-id-evidence", str(identity_evidence)]
        if args.fw_id_nm:
            cmd += ["--fw-id-nm", args.fw_id_nm]
        with log.open("a") as fh:                 # 主日志只记一行索引，完整输出在 roundNNNN.out
            fh.write(f"\n[轮 {rnd}] $ {' '.join(cmd)}\n")
        rc = sh(cmd, rlog, timeout=args.round_timeout)
        info = parse_round(rlog)
        match = "YES" if info["judge_sha"] == args.expect_sha else "NO"
        note = "" if rc == 0 else f"rc={rc}"
        with tsv.open("a") as fh:
            fh.write("\t".join([str(rnd), f"{time.time()-t0:.1f}", info["verdict"],
                                info["records"], info["result_s"], info["judge_sha"],
                                match, info["run_dir"], note, str(rc)]) + "\n")
        print(f"[{time.time()-t0:7.0f}s] 轮 {rnd:4d}  {info['verdict']:4s}  "
              f"{info['records']:>7s} 条  {info['result_s']:>6s}s  match={match} rc={rc}")

        if rc == 0 and info["verdict"] == "PASS" and match == "YES":
            consecutive_failures = 0
        else:
            consecutive_failures += 1
        if consecutive_failures >= args.stop_after_consecutive_failures:
            stop_reason = f"stopped_early_after_{consecutive_failures}_consecutive_failures"
            print(f"提前止损：连续 {consecutive_failures} 轮失败；已写入 summary，停止长稳循环")
            break

        if args.recovery_every and rnd % args.recovery_every == 0:
            jl = out / "recovery.jsonl"
            prc = sh([sys.executable, "tools/board/g3_recovery_probe.py",
                      "--ip", args.ip, "--port", str(args.port),
                      "--jsonl", str(jl), "--cycles", "1",
                      "--tag", f"{args.tag}-soak-r{rnd}"], log, timeout=600)
            recovery_probe_rcs.append(prc)
            print(f"          ↳ 畸变包探针 rc={prc}")
            if prc != 0:
                stop_reason = f"stopped_early_after_recovery_probe_failure_at_round_{rnd}"
                print("提前止损：首次恢复探针失败；已写入 summary，停止长稳循环")
                break

    if not stop_reason:
        stop_reason = "wall_clock_target_reached"

    # 收尾：必须同时有展示判据 PASS、期望 SHA 命中和 G3 子进程 rc=0。
    # 兼容旧 TSV 仅用于读取事实：旧表没有 process_rc 的轮次按“退出码未知”处理，
    # 不能因展示文本 PASS 就补推它们曾以 rc=0 退出。
    lines = [line for line in tsv.read_text().splitlines() if line.strip()]
    header = lines[0].split("\t") if lines else []
    header_idx = {name: i for i, name in enumerate(header)}
    rows = [line.split("\t") for line in lines[1:]]

    def field(row: list[str], name: str) -> str:
        idx = header_idx.get(name)
        return row[idx] if idx is not None and idx < len(row) else ""

    def process_rc(row: list[str]) -> str:
        # 既有 9 列 TSV 会在运行时追加第 10 列 process_rc；即使旧表头不能改写，
        # 新行仍可从额外列读取退出码。
        if len(row) > len(header):
            return row[-1]
        idx = header_idx.get("process_rc")
        if idx is not None and idx < len(row):
            return row[idx]
        # 旧格式把非零码留在 note，但成功码从未被记录，故空 note 是未知而非 0。
        note = field(row, "note")
        m = re.fullmatch(r"rc=(-?\d+)", note)
        return m.group(1) if m else ""

    wall = time.time() - t0
    target_wall = args.hours * 3600.0
    round_statuses = []
    for row in rows:
        rc_value = process_rc(row)
        verdict_value = field(row, "verdict")
        match_value = field(row, "match")
        if not re.fullmatch(r"-?\d+", rc_value):
            round_statuses.append("unverified")
        elif rc_value != "0":
            round_statuses.append("fail")
        elif verdict_value == "PASS" and match_value == "YES":
            round_statuses.append("pass")
        elif verdict_value == "FAIL" or match_value == "NO":
            round_statuses.append("fail")
        else:
            round_statuses.append("unverified")
    ok = [status for status in round_statuses if status == "pass"]
    rounds_failed = sum(status == "fail" for status in round_statuses)
    rounds_unverified = sum(status == "unverified" for status in round_statuses)
    probe_failures = sum(rc != 0 for rc in recovery_probe_rcs)
    enough_wall = wall >= target_wall * 0.98
    verdict = "PASS" if (rows and len(ok) == len(rows) and not probe_failures and enough_wall) else "FAIL"
    stopped_early = stop_reason.startswith("stopped_early_")
    if stopped_early:
        verdict = "FAIL"
    summary = {
        "tag": args.tag, "artifact_dir": args.artifact_dir, "ip": args.ip,
        "fw_build_id_check": {
            "verdict": "PASS", "expected_fw_build_id": expected_fw_id,
            "actual_fw_build_id": actual_fw_id,
            "checked_utc": identity_doc.get("checked_utc"),
            "evidence": str(identity_evidence),
        },
        "target_hours": args.hours, "wall_s": round(wall, 1),
        "wall_target_delta_s": round(wall - target_wall, 1),
        "wall_target_delta_hours": round((wall - target_wall) / 3600.0, 4),
        "wall_time_minimum_s": round(target_wall * 0.98, 1),
        "rounds": len(rows), "rounds_pass_with_expected_sha": len(ok),
        "rounds_failed": rounds_failed, "rounds_unverified": rounds_unverified,
        "verdict": verdict,
        "recovery_probes": len(recovery_probe_rcs),
        "recovery_probes_pass": len(recovery_probe_rcs) - probe_failures,
        "recovery_probes_failed": probe_failures,
        "recovery_probe_rcs": recovery_probe_rcs,
        "wall_time_sufficient": enough_wall,
        "consecutive_failure_limit": args.stop_after_consecutive_failures,
        "stop_reason": stop_reason,
        "stopped_early": stopped_early,
        "hardware_cycles": None, "power_w": None,
        "note": ("UNMEASURED: 无外部 UART 周期采集、无功率计；result_s 是客户端打印值，"
                 "不得反推周期或功耗"),
    }
    (out / "soak_summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=1))
    print(f"\n实际墙钟 {wall/3600:.3f} h（目标 {args.hours} h，实际-目标 {wall-target_wall:+.1f}s；"
          f"保留 98% 阈值 {target_wall*0.98:.1f}s），{len(rows)} 轮，"
          f"通过 {len(ok)} 轮，失败 {rounds_failed} 轮，未验证 {rounds_unverified} 轮")
    print(f"停止原因：{stop_reason}")
    print(f"长稳结论：{verdict}  → {out/'soak_summary.json'}")
    return 0 if verdict == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
