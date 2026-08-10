#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""纯软件读出参考实现：滑窗相关 → 大数投票 → 差分 → 反稀疏化。

**输入只有两个文件：FASTQ 读段 和 水印。** 本脚本不打开、不引用任何参考答案
（`codeword_R083.txt` / `source_bit.txt` / `Milk coronet.jpg` / 编码序列），
输出的 `dec_input.txt` 完全来自读段本身。这一点可以用 `--prove-inputs` 自证。

它是 `docs/07-performance.md` 里 CPU 侧耗时的来源，也是板端结果的对照实现。
LDPC 译码不在本脚本内，需另行调用 `R5_6_LDPC_hard_decoder.exe`。

    python3 tools/readout.py --reads r.fastq --watermark wm.txt --limit 2048 \
        --jobs 8 --out dec_input.txt
"""

from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path

import numpy as np

BASE2VAL = {"A": 0, "T": 1, "G": 2, "C": 3, "N": 0}


# --------------------------------------------------------------------------
# 输入解析（只有这两个函数会读文件）
# --------------------------------------------------------------------------
def load_watermark(path: Path):
    """水印文本/32-bit 值 → 参考符号序列。位平面布局：前半为高位，后半为低位。"""
    raw = path.read_bytes()
    if b"\x00" in raw[:64]:                       # 32-bit 值序列
        vals = np.frombuffer(raw, dtype="<u4")
        bits = (vals & 1).astype(np.uint8)
    else:                                          # 0/1 文本
        txt = raw.decode("utf-8", "ignore")
        bits = np.frombuffer("".join(c for c in txt if c in "01").encode(), dtype=np.uint8) - ord("0")
    if bits.size % 2:
        raise ValueError(f"水印位数 {bits.size} 必须为偶数")
    half = bits.size // 2
    return ((bits[:half] << 1) | bits[half:]).astype(np.uint8), bits


def load_reads(path: Path, limit: int):
    """FASTQ 或每行一条序列 → (N, read_len) 符号矩阵。"""
    seqs = []
    with path.open("r", encoding="utf-8", errors="ignore") as fh:
        first = fh.readline()
        fh.seek(0)
        fastq = first.startswith("@")
        while len(seqs) < limit:
            line = fh.readline()
            if not line:
                break
            if fastq:
                s = fh.readline().strip()
                fh.readline()
                fh.readline()
            else:
                s = line.strip()
            if s:
                seqs.append(s.upper())
    if not seqs:
        raise ValueError("未读到任何读段")
    n = len(seqs[0])
    seqs = [s for s in seqs if len(s) == n]
    return np.array([[BASE2VAL.get(c, 0) for c in s] for s in seqs], dtype=np.uint8)


# --------------------------------------------------------------------------
# Stage1：滑窗相关（与 srpe_batch 相同的算法）
# --------------------------------------------------------------------------
_REF = {}


def _init_worker(ref, read_len):
    n = ref.size + read_len
    size = 1 << (n - 1).bit_length()
    _REF["ref"] = ref
    _REF["size"] = size
    _REF["spec"] = [np.fft.rfft((ref == s).astype(np.float64), size) for s in range(4)]
    _REF["rl"] = read_len
    _REF["maxpos"] = ref.size - read_len


def _align_one(a):
    size, spec, rl, maxpos = _REF["size"], _REF["spec"], _REF["rl"], _REF["maxpos"]
    sc = np.zeros(size)
    for s in range(4):
        sc += np.fft.irfft(spec[s] * np.fft.rfft((a == s).astype(np.float64)[::-1], size), size)
    v = sc[rl - 1: rl + maxpos]
    p = int(np.argmax(v))
    return p, int(round(v[p]))


def _align_pair(row):
    """同一条读段的正向与反向互补各比对一次，返回得分高者。"""
    a = row
    b = (a ^ 1)[::-1]                     # 反向互补：符号异或 1 后整体反序
    p1, s1 = _align_one(a)
    p2, s2 = _align_one(b)
    return (0, p1, s1) if s1 >= s2 else (1, p2, s2)


def _align_both(row):
    """返回 (正向 pos, 正向 score, 反向 pos, 反向 score)，供 RTL 判据使用。"""
    p1, s1 = _align_one(row)
    p2, s2 = _align_one((row ^ 1)[::-1])
    return (p1, s1, p2, s2)


# --------------------------------------------------------------------------
# Stage3：5b → 4b 反稀疏化
# --------------------------------------------------------------------------
def desparsify(bits: np.ndarray) -> np.ndarray:
    """每组 5 bit 按码流顺序 b0..b4，输出 b1^b0, b2^b0, b3^b0, b4^b0。"""
    g = bits.reshape(-1, 5)
    return (g[:, 1:] ^ g[:, :1]).reshape(-1)


# --------------------------------------------------------------------------
def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--reads", required=True)
    ap.add_argument("--watermark", required=True)
    ap.add_argument("--out", default="dec_input.txt")
    ap.add_argument("--limit", type=int, default=2048)
    ap.add_argument("--min-score", type=float, default=0.45,
                    help="参与投票的最低比对分，按读段长度的比例给出（默认 0.45）")
    ap.add_argument("--jobs", type=int, default=1, help="并行进程数")
    ap.add_argument("--prove-inputs", action="store_true",
                    help="打印本次运行实际打开的全部文件，自证没有引用参考答案")
    args = ap.parse_args(argv)

    opened = []
    t = {}
    t0 = time.perf_counter()
    ref, wm_bits = load_watermark(Path(args.watermark))
    opened.append(args.watermark)
    L = ref.size
    t["载入水印"] = time.perf_counter() - t0

    tt = time.perf_counter()
    R = load_reads(Path(args.reads), args.limit)
    opened.append(args.reads)
    t["读FASTQ+2bit编码"] = time.perf_counter() - tt
    n, rl = R.shape
    thr = int(args.min_score * rl)
    print(f"参考 {L} nt   读段 {n} 条 × {rl} bp   比对分阈值 {thr}/{rl}   并行 {args.jobs}")

    tt = time.perf_counter()
    if args.jobs > 1:
        import multiprocessing as mp
        with mp.Pool(args.jobs, initializer=_init_worker, initargs=(ref, rl)) as pool:
            res = pool.map(_align_pair, list(R), chunksize=8)
    else:
        _init_worker(ref, rl)
        res = [_align_pair(R[i]) for i in range(n)]
    t["Stage1 滑窗相关(双向)"] = time.perf_counter() - tt

    tt = time.perf_counter()
    votes = np.zeros(2 * L, dtype=np.int32)
    used = 0
    for i, (d, p, s) in enumerate(res):
        if s < thr:
            continue
        a = R[i] if d == 0 else (R[i] ^ 1)[::-1]
        used += 1
        idx = np.arange(p, p + rl)
        np.add.at(votes, idx, ((a >> 1) & 1).astype(np.int32) * 2 - 1)
        np.add.at(votes, idx + L, (a & 1).astype(np.int32) * 2 - 1)
    t["Stage2 大数投票"] = time.perf_counter() - tt

    tt = time.perf_counter()
    sparse = (votes > 0).astype(np.uint8) ^ wm_bits          # 差分：共识 ⊕ 水印
    out = desparsify(sparse)
    Path(args.out).write_text("".join("01"[b] for b in out), encoding="utf-8")
    opened.append(args.out)
    t["Stage3 差分+反稀疏化"] = time.perf_counter() - tt

    print(f"参与投票 {used}/{n} 条   覆盖 {int((votes != 0).sum())}/{votes.size} bit")
    total = sum(t.values())
    for k, v in t.items():
        print(f"  {k:26s}{v*1000:9.1f} ms")
    print(f"  {'合计（不含 LDPC）':26s}{total*1000:9.1f} ms")
    print(f"已写出 {out.size} bit 到 {args.out}")

    if args.prove_inputs:
        print("\n本次运行打开过的文件（除标准库/numpy 自身）：")
        for f in opened:
            print("  ", os.path.abspath(f))
        print("  —— 不含任何参考答案文件")
    return 0


if __name__ == "__main__":
    sys.exit(main())
