#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把 run_g3.sh 的留证目录收敛成结构化 JSONL（docs/06 的统计口径）。

为什么要单独一个提取器
----------------------
`run_g3.sh` 的产物是给人看的 `summary.txt` + 一堆逐轮日志，压测统计要的是**逐轮一行**
的机器可读记录。手工誊抄必然出错，而且会把「没测到的字段」抄成看起来像测过的数字。

诚实边界（重要）
----------------
docs/06 列了 `dma_in_s / stage1_s / stage2_s / stage3_s / download_s`。这些在**上位机
侧根本不可分辨**：first.py 只能看到一个合并的 `Result` 墙钟（下发 POST → 收全结果），
板内四级流水与回传全在这一个数里。因此本脚本把它们输出为 `null`，并在
`unobservable_note` 里写明原因，**绝不拆一个假的比例出来**。
功耗同理：没接功率计，`power_w` 恒为 null + `UNMEASURED`。

用法：
    python3 tools/board/g3_runs_to_jsonl.py \
        --run-dir /mnt/d/dna_board_smoke/g3_runs/<run> [...] \
        --jsonl tests/stress_results/<x>/continuous.jsonl
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent.parent

EXPECT_SHA = "fcd0cf90bd680e7bbdc203e3398119504da0897acac9e2117008b4efb6b1f2c3"


def sha256_of(path: Path) -> str | None:
    if not path.is_file():
        return None
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def parse_summary(run_dir: Path) -> dict:
    """从 summary.txt 取本次 run 的全局参数与逐轮表。"""
    txt = (run_dir / "summary.txt").read_text(encoding="utf-8", errors="replace")
    meta = {"run_name": run_dir.name}
    for key, pat in (
        ("invocation", r"命令\s*:\s*(.+)"),
        ("judge_score_min", r"判据阈值\s*:\s*score_min=(\d+)"),   # 下面转 int
        ("bitstream_sha256", r"bitstream\s*:\s*([0-9a-f]{64})"),
        ("elf_sha256", r"ELF\s*:\s*([0-9a-f]{64})"),
        ("timestamp_utc", r"时间\(UTC\)\s*:\s*(\S+)"),
    ):
        m = re.search(pat, txt)
        meta[key] = m.group(1).strip() if m else None
    # 阈值是数，别让它以字符串混进 JSONL —— 下游做区间筛选时会静默失配。
    if meta.get("judge_score_min") is not None:
        meta["judge_score_min"] = int(meta["judge_score_min"])

    rows = {}
    # 轮次 类型 源读段 记录数 阈值 超时(s) 实测耗时(s)
    for m in re.finditer(r"^(\d+)\s+(判据轮|弄脏轮)\s+(\d+)\s+(\d+)\s+(\d+)\s+(\d+)\s+(\S+)\s*$",
                         txt, re.M):
        r = int(m.group(1))
        rows[r] = {
            "kind": "judge" if m.group(2) == "判据轮" else "dirty",
            "source_reads": int(m.group(3)),
            "record_count": int(m.group(4)),
            "score_min": int(m.group(5)),
            "timeout_s": int(m.group(6)),
            "wall_s": None if m.group(7) == "未跑" else int(m.group(7)),
        }
    meta["rows"] = rows

    # 步骤裁决行：用来给每轮定 failure_class，而不是靠猜。
    meta["steps"] = re.findall(r"^(PASS|FAIL|SKIP)\s+(.+)$", txt, re.M)
    meta["overall_fail"] = any(s == "FAIL" for s, _ in meta["steps"])
    return meta


def parse_first_log(path: Path) -> dict:
    """从 first_runN.log 取真正被打印出来的阶段耗时。没打印的一律留 None。"""
    out = {
        "wm_upload_s": None, "wm_bytes": None,
        "reads_upload_s": None, "reads_bytes": None, "reads_batches": None,
        "board_result_s": None, "result_bytes": None,
        "total_s": None, "other_s": None,
        "upload_bytes": None, "download_bytes": None,
        "caps_read_bps": None, "caps_max_reads": None,
    }
    if not path.is_file():
        return out
    txt = path.read_text(encoding="utf-8", errors="replace")

    m = re.search(r"Watermark:\s*(\d+)\s*bytes,\s*([\d.]+)s", txt)
    if m:
        out["wm_bytes"], out["wm_upload_s"] = int(m.group(1)), float(m.group(2))
    m = re.search(r"Reads:\s*(\d+)\s*batches,\s*(\d+)\s*bytes,\s*([\d.]+)s", txt)
    if m:
        out["reads_batches"] = int(m.group(1))
        out["reads_bytes"] = int(m.group(2))
        out["reads_upload_s"] = float(m.group(3))
    m = re.search(r"Result:\s*(\d+)\s*bytes,\s*([\d.]+)s", txt)
    if m:
        out["result_bytes"], out["board_result_s"] = int(m.group(1)), float(m.group(2))
    m = re.search(r"总时长:\s*([\d.]+)s", txt)
    if m:
        out["total_s"] = float(m.group(1))
    m = re.search(r"其他:\s*([\d.]+)s", txt)
    if m:
        out["other_s"] = float(m.group(1))
    m = re.search(r"上行:\s*([\d,]+)\s*bytes", txt)
    if m:
        out["upload_bytes"] = int(m.group(1).replace(",", ""))
    m = re.search(r"下行:\s*([\d,]+)\s*bytes", txt)
    if m:
        out["download_bytes"] = int(m.group(1).replace(",", ""))
    m = re.search(r"\[CAPS\]\s*v\d+\s*read_bps=(\d+).*?max_reads=(\d+)", txt)
    if m:
        out["caps_read_bps"], out["caps_max_reads"] = int(m.group(1)), int(m.group(2))
    return out


def parse_ldpc_log(path: Path) -> dict:
    out = {"ldpc_initial_fail_checks": None, "ldpc_iters": None,
           "ldpc_converged": None, "ldpc_output_bits": None}
    if not path.is_file():
        return out
    txt = path.read_text(encoding="utf-8", errors="replace")
    m = re.search(r"起始失败校验\s*(\d+)，(\d+)\s*轮收敛，输出\s*(\d+)\s*bit", txt)
    if m:
        out["ldpc_initial_fail_checks"] = int(m.group(1))
        out["ldpc_iters"] = int(m.group(2))
        out["ldpc_converged"] = True
        out["ldpc_output_bits"] = int(m.group(3))
    elif txt.strip():
        out["ldpc_converged"] = False
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--run-dir", action="append", required=True,
                    help="run_g3.sh 的留证目录，可重复")
    ap.add_argument("--jsonl", required=True)
    ap.add_argument("--campaign", default="", help="本批压测的短名，写进每条记录")
    ap.add_argument("--reads-file",
                    default="data/R0.83_data/Sequencing data/DNA-40.5Kb-MC-SE150.fastq")
    ap.add_argument("--wm-file",
                    default="data/R0.83_data/Source data/Watermark sequences/r0.83_watermark.txt")
    args = ap.parse_args(argv)

    # 数据集指纹只算一次：它对整批压测是常量，但必须真的算出来写进去，
    # 否则「用的是哪份数据」这件事在报告里就只剩一句人话，没法复核。
    payload_sha = sha256_of(REPO / args.reads_file)
    wm_sha = sha256_of(REPO / args.wm_file)

    out = Path(args.jsonl)
    out.parent.mkdir(parents=True, exist_ok=True)
    n = 0
    with out.open("w", encoding="utf-8") as fh:
        for rd in args.run_dir:
            run_dir = Path(rd)
            if not (run_dir / "summary.txt").is_file():
                print(f"跳过（无 summary.txt）：{run_dir}", file=sys.stderr)
                continue
            meta = parse_summary(run_dir)
            for r in sorted(meta["rows"]):
                row = meta["rows"][r]
                first = parse_first_log(run_dir / f"first_run{r}.log")
                ldpc = parse_ldpc_log(run_dir / f"ldpc_run{r}.log")
                img = run_dir / f"decoded_run{r}.jpg"
                img_sha = sha256_of(img)

                if row["wall_s"] is None:
                    failure_class = "tooling"      # 这一轮压根没跑起来
                    hash_match = None
                elif row["kind"] == "dirty":
                    # 弄脏轮的输出本来就是噪声，不进产品成功率，单独归一类。
                    failure_class = "dirty_proof"
                    hash_match = None
                else:
                    hash_match = (img_sha == EXPECT_SHA)
                    failure_class = "pass" if hash_match else "functional"

                upload_s = None
                if first["wm_upload_s"] is not None and first["reads_upload_s"] is not None:
                    upload_s = round(first["wm_upload_s"] + first["reads_upload_s"], 3)

                rec = {
                    "campaign": args.campaign,
                    "run_name": meta["run_name"],
                    "timestamp_utc": meta["timestamp_utc"],
                    "invocation": meta["invocation"],
                    "round": r,
                    "round_kind": row["kind"],
                    "score_min": row["score_min"],
                    "judge_score_min": meta["judge_score_min"],
                    "source_reads": row["source_reads"],
                    "record_count": row["record_count"],
                    "timeout_s": row["timeout_s"],

                    "dataset_id": "R0.83_SE150_DNA-40.5Kb-MC",
                    "payload_sha256": payload_sha,
                    "watermark_sha256": wm_sha,
                    "bitstream_sha256": meta["bitstream_sha256"],
                    "elf_sha256": meta["elf_sha256"],

                    # —— 真实测到的耗时 ——
                    "wall_s": row["wall_s"],
                    "upload_s": upload_s,
                    "wm_upload_s": first["wm_upload_s"],
                    "reads_upload_s": first["reads_upload_s"],
                    "board_result_s": first["board_result_s"],
                    "client_total_s": first["total_s"],
                    "client_other_s": first["other_s"],

                    # —— 上位机侧不可分辨，禁止编造 ——
                    "fastq_read_s": None,
                    "dma_in_s": None,
                    "stage1_s": None,
                    "stage2_s": None,
                    "stage3_s": None,
                    "download_s": None,
                    "ldpc_s": None,
                    "unobservable_note": (
                        "dma_in/stage1/stage2/stage3/download 合并在 board_result_s 这一个"
                        "墙钟里，上位机无法拆分；fastq_read_s 与 ldpc_s 当前脚本未计时。"
                        "均记 null，不做比例估算。"
                    ),

                    "upload_bytes": first["upload_bytes"],
                    "download_bytes": first["download_bytes"],
                    "result_bytes": first["result_bytes"],
                    "reads_batches": first["reads_batches"],
                    "caps_read_bps": first["caps_read_bps"],
                    "caps_max_reads": first["caps_max_reads"],

                    "ldpc_initial_fail_checks": ldpc["ldpc_initial_fail_checks"],
                    "ldpc_iters": ldpc["ldpc_iters"],
                    "ldpc_converged": ldpc["ldpc_converged"],
                    "image_sha256": img_sha,
                    "expect_sha256": EXPECT_SHA,
                    "hash_match": hash_match,
                    "failure_class": failure_class,

                    "power_w": None,
                    "energy_j": None,
                    "power_note": "UNMEASURED (no power meter attached) — N/A",
                }
                fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
                n += 1
    print(f"写出 {n} 条记录 → {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
