#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Stage1 比对的 CPU 侧性能基准，以及「种子法为何失效」的实证。

产出 docs/08-performance-and-strategy.md 里的全部 CPU 数字。同时导出 ref.bin / reads.bin
供 tools/align.c 的 C 版本使用：

    python3 tools/bench_align.py --reads 2048
    gcc -O3 -march=native -o align tools/align.c && ./align ref.bin reads.bin 2048
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

import numpy as np
from numpy.lib.stride_tricks import sliding_window_view as swv

sys.path.insert(0, str(Path(__file__).resolve().parent))
import golden_model as g  # noqa: E402


def load(n_reads):
    wm = g.read_bits(Path(str(g.DEF_WATERMARK)))
    ref = g.planes_to_symbols(wm)
    reads = [s.upper() for s in g.iter_fastq(Path(str(g.DEF_READS)), n_reads)]
    R = np.array([[g.BASE2VAL.get(c, 0) for c in s] for s in reads], dtype=np.uint8)
    return wm, ref, R


def bench(ref, R, n_probe):
    L, RB = ref.size, R.shape[1]
    RC = (R ^ 1)[:, ::-1]
    out = {}

    W = swv(ref, RB)
    t = time.perf_counter()
    for i in range(n_probe):
        s1 = (W == R[i]).sum(axis=1)
        s2 = (W == RC[i]).sum(axis=1)
        int(np.argmax(s1) if s1.max() >= s2.max() else np.argmax(s2))
    out["numpy 暴力滑窗（与 FPGA 同算法）"] = (time.perf_counter() - t) / n_probe

    size, spec = g.make_ref_spectrum(ref, RB)
    t = time.perf_counter()
    for i in range(n_probe):
        g.align_read(R[i], size, spec, L - RB)
        g.align_read(RC[i], size, spec, L - RB)
    out["numpy FFT 相关（黄金模型）"] = (time.perf_counter() - t) / n_probe
    return out


def seed_feasibility(ref, truth, R, n_probe=40):
    """证明精确 k-mer 种子在本任务中失效：读段与水印只有约 50% 碱基相同。"""
    def longest_run(read, reference):
        W = swv(reference, read.size)
        eq = W == read
        row = eq[int(np.argmax(eq.sum(axis=1)))]
        best = run = 0
        for x in row:
            run = run + 1 if x else 0
            best = max(best, run)
        return best

    vs_wm = [longest_run(R[i], ref) for i in range(n_probe)]
    vs_truth = [longest_run(R[i], truth) for i in range(n_probe)]
    return int(np.median(vs_wm)), max(vs_wm), int(np.median(vs_truth)), max(vs_truth)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--reads", type=int, default=2048, help="导出并计时的读段数")
    ap.add_argument("--probe", type=int, default=30, help="慢速实现的采样条数")
    ap.add_argument("--outdir", default=".", help="ref.bin / reads.bin 的输出目录")
    args = ap.parse_args(argv)

    wm, ref, R = load(args.reads)
    truth = g.read_sequence(Path(str(g.DEF_SEQUENCE)))
    print(f"参考 {ref.size} nt，读段 {R.shape[0]} 条 × {R.shape[1]} bp\n")

    m_wm, x_wm, m_tr, x_tr = seed_feasibility(ref, truth, R)
    print("【种子法可行性】最佳位置处的最长连续精确匹配")
    print(f"  读段 vs 水印（接收端拥有的）  中位 {m_wm} nt，最大 {x_wm} nt")
    print(f"  读段 vs 真实序列（拿不到）    中位 {m_tr} nt，最大 {x_tr} nt")
    print(f"  → 16-mer 精确命中概率 ≈ {0.5**16:.2e}，精确种子法不可用，必须暴力相关\n")

    print("【CPU 耗时，双向】")
    for name, per in bench(ref, R, args.probe).items():
        print(f"  {name:34s}{per*1000:8.2f} ms/条  → {args.reads} 条 {per*args.reads:7.2f} s")

    out = Path(args.outdir)
    out.mkdir(parents=True, exist_ok=True)
    (out / "ref.bin").write_bytes(ref.tobytes())
    (out / "reads.bin").write_bytes(R.tobytes())
    print(f"\n已导出 {out/'ref.bin'} 与 {out/'reads.bin'}，可用 tools/align.c 的 C 版本继续测。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
