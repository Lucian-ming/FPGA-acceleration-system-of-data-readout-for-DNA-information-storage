#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""调试脚本：重算板端语义的逐位置票值，与 TB 转储的 dut.bram 做 diff。

用法： python3 tools/debug_vote_diff.py /tmp/voter_bram_dump.hex
"""
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import readout as rd

REPO = Path(__file__).resolve().parent.parent
DATA = REPO / "data" / "R0.83_data"
READS = DATA / "Sequencing data" / "DNA-40.5Kb-MC-SE150.fastq"
WM = DATA / "Source data" / "Watermark sequences" / "r0.83_watermark.txt"

NUM_LC, STRIDE, REF_LEN = 50, 807, 957


def main(argv):
    ref, _ = rd.load_watermark(WM)
    L = ref.size
    R = rd.load_reads(READS, 2048)
    n, rb = R.shape
    rd._init_worker(ref, rb)

    votes = np.zeros(2 * L, dtype=np.int64)
    for i in range(n):
        for a in (R[i], (R[i] ^ 1)[::-1]):
            p, _ = rd._align_one(a)
            idx = np.arange(p, p + rb)
            np.add.at(votes, idx, ((a >> 1) & 1).astype(np.int64) * 2 - 1)
            np.add.at(votes, idx + L, (a & 1).astype(np.int64) * 2 - 1)
    votes = np.clip(votes, -512, 511)

    vals = []
    for line in Path(argv[1]).read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("//"):
            continue
        if "x" in line:              # 部分未定义值，保留占位维持位置对齐
            vals.append(None)
        else:
            vals.append(int(line, 16))
    x_cnt = sum(v is None for v in vals)
    if x_cnt:
        first_x = next(i for i, v in enumerate(vals) if v is None)
        print(f"⚠ 转储含 {x_cnt} 个未定义值，首个在位置 {first_x}")
    dump = np.array([v if v is not None else 0 for v in vals], dtype=np.int64)
    # 10-bit 补码 → 有符号
    dump_s = np.where(dump >= 512, dump - 1024, dump)

    print(f"DUT 累加器 {dump_s.size} 项，期望 {votes.size} 项")
    m = min(dump_s.size, votes.size)
    diff = np.nonzero(dump_s[:m] != votes[:m])[0]
    print(f"不一致位置数：{len(diff)}/{m}")
    if len(diff):
        print(f"首个分歧位置：{diff[0]}")
        lo = max(0, diff[0] - 5)
        for k in range(lo, min(diff[0] + 20, m)):
            mark = "  ✗" if dump_s[k] != votes[k] else "  ✓"
            print(f"  [{k:6d}] DUT={dump_s[k]:+5d}  期望={votes[k]:+5d}{mark}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
