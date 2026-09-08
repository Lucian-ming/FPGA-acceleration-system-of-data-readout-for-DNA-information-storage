#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""tools/make_stage1_tie_golden.py —— 生成 Stage1 正向比对的「同分并列位置集」黄金向量

## 为什么需要这个文件

`tests/golden/stage1_fwd_expect.txt` 每条读段只记录**一个**最佳位置，但该位置在
同分并列时是**不可复现的浮点噪声产物**，不能当作 RTL 的位置判据：

`tools/readout.py::_align_one` 用 FFT 做互相关，得到 float64 数组后 `np.argmax`。
当多个位置的整数匹配分完全相同时，FFT 的浮点结果并不严格相等，argmax 取的是
「浮点值最大」而非「位置最小」的那个。2026-09-09 在 SE150 前 64 条读段上实测：

    read  4  整数并列位置 [17193, 17954, 32993]，整数分数均为 59
             FFT 浮点值    59.0 / 59.000000000000014 / 59.0  -> argmax 选中 17954（中间）
    read 30  整数并列位置 [2621, 32735, 37642]，整数分数均为 59
             FFT 浮点值    59.0 / 59.0 / 59.00000000000001   -> argmax 选中 37642（末位）

也就是说黄金文件里这两条的位置是 1e-14 量级的舍入误差决定的。RTL（2-way 与
4-way 都一样）确定性地选最小位置，于是与黄金文件差异恰好 2 条 —— 这**不是 RTL 缺陷**，
是判据本身写错了。

## 正确判据

对每条读段：
  1. RTL 的 score 必须与整数精确最大分**严格相等**；
  2. RTL 的 pos 必须**属于并列最大集**（不要求等于黄金文件里那一个）。

本工具用整数精确滑窗（不走 FFT，无浮点）算出并列集，供 Testbench 使用。

## 为什么不写进 tests/golden/

`tools/make_golden.py` 结尾会把 `tests/golden/` 下**所有**文件重算进 `SHA256SUMS`，
往该目录新增文件会破坏「不带参数调用即逐字节复现已冻结 SE150」这条判据
（见 make_golden.py 的 --manifest 帮助文本）。故本文件输出到 `hw/sim/golden/`。

## 输出格式

    # idx max_score n_ties pos...
    0 61 1 326
    4 59 3 17193 17954 32993

## 用法

    python3 tools/make_stage1_tie_golden.py                 # 默认前 64 条（顶层 TB 批次）
    python3 tools/make_stage1_tie_golden.py --limit 2048    # 全量
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "tools"))

import readout as rd  # noqa: E402
from make_golden import DEF_READS, DEF_WM, derive_geometry  # noqa: E402


def compute_ties(ref: np.ndarray, read: np.ndarray, max_pos: int):
    """整数精确滑窗，返回 (最大分, 并列位置列表)。

    只在 RTL 真正搜索得到的位置范围内比较：RTL 的搜索空间是
    NUM_LC 个区域 × STRIDE 个位置 = 全局位置 0..NUM_LC*STRIDE-1，
    而黄金模型在整条 ref 上滑窗（0..L-READ_BPS）。两者差一个位置，
    必须按 RTL 的范围截断，否则会把 RTL 根本够不到的位置算成并列。
    """
    rb = read.size
    sc = np.array([int(np.sum(ref[p:p + rb] == read)) for p in range(max_pos + 1)])
    m = int(sc.max())
    return m, np.flatnonzero(sc == m).tolist()


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--reads", default=str(DEF_READS))
    ap.add_argument("--watermark", default=str(DEF_WM))
    ap.add_argument("--limit", type=int, default=64,
                    help="生成前 N 条（默认 64，即顶层 TB 的一个硬件批次）")
    ap.add_argument("--num-lc", type=int, default=50,
                    help="水印区域数，决定 RTL 的搜索空间上界（默认 50 = 生产几何）")
    ap.add_argument("--out", default=str(REPO / "hw" / "sim" / "golden" / "stage1_fwd_ties.txt"))
    args = ap.parse_args(argv)

    ref, _ = rd.load_watermark(Path(args.watermark))
    R = rd.load_reads(Path(args.reads), max(args.limit, 1))
    n, rb = R.shape
    n = min(n, args.limit)
    L = ref.size
    stride, ref_len = derive_geometry(L, rb, args.num_lc)
    rtl_max_pos = args.num_lc * stride - 1

    print(f"参考 {L} nt   读段 {n} 条 × {rb} bp")
    print(f"几何 NUM_LC={args.num_lc} STRIDE={stride} REF_LEN={ref_len}")
    print(f"RTL 搜索空间: 全局位置 0..{rtl_max_pos}（黄金模型是 0..{L - rb}，差 1 个位置）")

    lines = ["# idx max_score n_ties pos...   （整数精确滑窗，RTL 搜索空间内的同分并列集）"]
    tied = 0
    for i in range(n):
        m, positions = compute_ties(ref, R[i], rtl_max_pos)
        if len(positions) > 1:
            tied += 1
        lines.append(f"{i} {m} {len(positions)} " + " ".join(str(p) for p in positions))

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"\n已写出 {n} 条到 {out}")
    print(f"其中 {tied} 条存在同分并列（占 {100.0 * tied / n:.1f}%）—— "
          f"这些读段的位置判据必须按集合成员判定，不能按单值相等判定")
    return 0


if __name__ == "__main__":
    sys.exit(main())
