#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""纯 Python 的 DVB-S2 R=5/6 硬判决 LDPC 译码器（P5：替代 Windows EXE 的参考实现）。

与 `clients/python/resources/R5_6_LDPC_hard_decoder.exe` 等价的三个阶段：
  1) 读入 64,800 bit 的接收流（0/1 文本，交织后的顺序）；
  2) 用 `permutation64800` 解交织到自然码字顺序【校验位在前】：
         natural[perm[i]] = rx[i]
     （方向已用黄金数据钉死：codeword_R083 经此映射后仅 2 bit 与真码字不符，
      对应恰好 8 个失败校验，见 verify 子命令）；
  3) 在 pchk 稀疏校验矩阵上做多轮硬判决比特翻转（Gallager-B），
     收敛后取自然顺序的第 10800..64799 列（信息位，54,000 bit）。

pchk 二进制格式（逆向自黄金数据，全部判据见 verify）：
  头 3 个小端 uint32：[0x5080, M=10800, N=64800]；
  之后按 -(行号+1) 的负数标记分行，行内是【1-based】列地址，
  数值 0 是行尾对齐填充（丢弃），偶见 64800 表示 1-based 的最大列 64799。

用法：
  python3 tools/ldpc_decode.py decode <输入0/1文本> [-o 输出bits] [--image 输出jpg]
  python3 tools/ldpc_decode.py verify          # 用 R0.83 黄金数据自检
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parent.parent
RES = REPO / "clients" / "python" / "resources"

M_ROWS = 10800
N_BITS = 64800
K_INFO = 54000
PARITY_COLS = 10800          # 自然顺序：列 0..10799 是校验位，10800..64799 是信息位


def load_pchk(path: Path):
    """返回 (行→列地址 数组列表)。"""
    raw = np.fromfile(path, dtype="<i4")
    if int(raw[0]) != 0x5080:
        raise ValueError(f"pchk 魔数不符: {hex(int(raw[0]))}")
    m, n = int(raw[1]), int(raw[2])
    if (m, n) != (M_ROWS, N_BITS):
        raise ValueError(f"pchk 尺寸不符: {m}×{n}")

    rows, cur = [], []
    for v in raw[3:]:
        if v < 0:
            rows.append(cur)
            cur = []
        else:
            cur.append(int(v))
    rows.append(cur)
    rows = rows[1:]                       # 首个标记前的空段

    out = []
    for seg in rows:
        cols = [v - 1 for v in seg if v > 0]   # 1-based → 0-based，丢弃填充 0
        if any(c < 0 or c >= N_BITS for c in cols):
            raise ValueError("pchk 列地址越界")
        out.append(np.array(cols, dtype=np.int64))
    if len(out) != M_ROWS:
        raise ValueError(f"行数 {len(out)} != {M_ROWS}")
    return out


def load_permutation(path: Path) -> np.ndarray:
    perm = np.fromfile(path, dtype="<u4").astype(np.int64)
    if perm.size != N_BITS or len(np.unique(perm)) != N_BITS:
        raise ValueError("permutation 表不是 64800 的排列")
    return perm


def deinterleave(rx: np.ndarray, perm: np.ndarray) -> np.ndarray:
    """接收流 → 自然码字顺序（校验位在前）。"""
    natural = np.empty_like(rx)
    natural[perm] = rx
    return natural


def hard_decode(natural: np.ndarray, rows, max_iter: int = 50,
                verbose: bool = False) -> tuple[np.ndarray, int, int]:
    """对硬判决比特做 min-sum 置信传播（LLR 域，2-min 近似），全 numpy 向量化。

    简单多数翻转在 DVB-S2 的度 2 校验列上会振荡（实测 60 轮不收敛）；
    min-sum 是硬判决 LDPC 的标准做法，几十个错误一两轮即收敛。
    返回 (码字, 起始失败校验数, 迭代轮数)。
    """
    W = max(len(r) for r in rows)              # 行重上限（本矩阵 23）
    M = len(rows)
    # 行主序矩阵（不足补 dummy，列号 0 但消息权重恒 0）
    C = np.zeros((M, W), dtype=np.int64)
    valid = np.zeros((M, W), dtype=bool)
    for j, r in enumerate(rows):
        C[j, : len(r)] = r
        valid[j, : len(r)] = True

    llr0 = np.where(natural == 1, 3.0, -3.0)   # BSC 硬判决初始置信
    llr = llr0.copy()

    def synd(yv):
        ym = yv[C]
        ym[~valid] = 0
        return ym.sum(axis=1) & 1

    y = natural.copy()
    s0 = int(synd(y).sum())
    if s0 == 0:
        return y, 0, 0

    BIG = 1e9
    for it in range(1, max_iter + 1):
        A = np.abs(llr)[C]                     # |LLR| 矩阵
        A[~valid] = BIG
        sgn = np.sign(llr)[C]
        sgn[~valid] = 1.0
        row_sgn = np.prod(sgn, axis=1)

        srt = np.sort(A, axis=1)
        min1, min2 = srt[:, 0], srt[:, 1]
        eq = (A == min1[:, None])              # 等于行最小（并列取首个）
        prev = np.zeros_like(eq)
        prev[:, 1:] = np.cumsum(eq.astype(np.int8), axis=1)[:, :-1]
        first = eq & (prev == 0)

        msg = row_sgn[:, None] * sgn * np.where(first, min2[:, None], min1[:, None])
        msg[~valid] = 0.0
        llr = llr0 + np.bincount(C.ravel(), weights=msg.ravel(),
                                 minlength=N_BITS)

        y = (llr > 0).astype(np.int64)
        s = int(synd(y).sum())
        if verbose:
            print(f"  iter {it}: 剩余失败校验 {s}")
        if s == 0:
            return y.astype(np.uint8), s0, it

    raise RuntimeError(f"LDPC 译码未收敛（{max_iter} 轮后仍有 {s} 个失败校验）")


def bits_to_jpeg_bytes(bits: np.ndarray) -> bytes:
    """54,000 bit → 字节（MSB-first），再按 JPEG 的 FFD9 结束标记截断。"""
    pad = (-bits.size) % 8
    b = np.concatenate([bits, np.zeros(pad, dtype=np.uint8)])
    vals = b.reshape(-1, 8) @ np.array([128, 64, 32, 16, 8, 4, 2, 1], dtype=np.uint16)
    data = vals.astype(np.uint8).tobytes()
    eoi = data.rfind(b"\xff\xd9")
    return data if eoi < 0 else data[: eoi + 2]


def decode_file(rx_path: Path, pchk: Path = None, perm_path: Path = None):
    pchk = pchk or (RES / "dvb_s2_r5_6.pchk")
    perm_path = perm_path or (RES / "permutation64800")

    text = "".join(c for c in rx_path.read_text(encoding="utf-8") if c in "01")
    if len(text) != N_BITS:
        raise ValueError(f"输入应为 {N_BITS} bit，实得 {len(text)}")
    rx = np.frombuffer(text.encode(), dtype=np.uint8) - ord("0")

    rows = load_pchk(pchk)
    perm = load_permutation(perm_path)
    natural = deinterleave(rx, perm)
    codeword, synd0, iters = hard_decode(natural, rows)
    info = codeword[PARITY_COLS:]
    return info, codeword, synd0, iters


# ---------------------------------------------------------------- 自检
def cmd_verify(args) -> int:
    data = REPO / "data" / "R0.83_data"
    cw = np.frombuffer(
        "".join(c for c in (data / "Source data/Encoded_codeword/codeword_R083.txt").read_text() if c in "01").encode(),
        dtype=np.uint8) - ord("0")
    src = np.frombuffer(
        "".join(c for c in (data / "Source data/Original data files/source_bit.txt").read_text() if c in "01").encode(),
        dtype=np.uint8) - ord("0")
    jpg = (data / "Source data/Original data files/Milk coronet.jpg").read_bytes()
    dec_input = np.frombuffer(
        "".join(c for c in (REPO / "tests/golden/dec_input.txt").read_text() if c in "01").encode(),
        dtype=np.uint8) - ord("0")

    rows = load_pchk(RES / "dvb_s2_r5_6.pchk")
    perm = load_permutation(RES / "permutation64800")

    # 判据 1：参考码字解交织后，失败校验恰好由 2 个固有偏差位解释
    natural = deinterleave(cw, perm)
    s = np.array([int(natural[r].sum()) & 1 for r in rows])
    diff = np.nonzero(natural[PARITY_COLS:] != src)[0]
    print(f"[verify] 参考码字失败校验 {int(s.sum())} 个；info 与 source_bit 差 {len(diff)} 位 "
          f"(H列 {diff + PARITY_COLS})")
    ok1 = len(diff) == 2 and int(s.sum()) <= 8

    # 判据 2：对含 88 bit 错误的 dec_input 译码，恢复出 source_bit 与原图
    codeword, synd0, iters = hard_decode(deinterleave(dec_input, perm), rows)
    info = codeword[PARITY_COLS:]
    err_before = int((deinterleave(dec_input, perm)[PARITY_COLS:] != src).sum())
    err_after = int((info != src).sum())
    print(f"[verify] dec_input 起始失败校验 {synd0}，{iters} 轮收敛；"
          f"info 错误 {err_before} → {err_after}")

    img = bits_to_jpeg_bytes(info)
    img_ok = img == jpg
    print(f"[verify] 重建 JPEG 与 Milk coronet.jpg 逐字节{'相同' if img_ok else '不同'} "
          f"({len(img)} vs {len(jpg)} B)")
    import hashlib
    print(f"[verify] SHA-256 {hashlib.sha256(img).hexdigest()[:16]}...")

    if ok1 and err_after == 0 and img_ok:
        print("[verify] ✓ PASS")
        return 0
    print("[verify] ✗ FAIL")
    return 1


def cmd_decode(args) -> int:
    info, _, synd0, iters = decode_file(Path(args.input))
    print(f"[decode] 起始失败校验 {synd0}，{iters} 轮收敛，输出 {len(info)} bit")
    out = Path(args.output) if args.output else Path("TestBitStream.txt")
    out.write_text("".join("01"[b] for b in info), encoding="utf-8")
    print(f"[decode] 比特已写入 {out}")
    if args.image:
        img = bits_to_jpeg_bytes(info)
        Path(args.image).write_bytes(img)
        print(f"[decode] 图像已写入 {args.image} ({len(img)} B)")
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("decode", help="译码 0/1 文本")
    p.add_argument("input")
    p.add_argument("-o", "--output", help="输出比特文件（默认 TestBitStream.txt）")
    p.add_argument("--image", help="同时重建 JPEG")
    p.set_defaults(func=cmd_decode)

    p = sub.add_parser("verify", help="用 R0.83 黄金数据自检")
    p.set_defaults(func=cmd_verify)

    args = ap.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
