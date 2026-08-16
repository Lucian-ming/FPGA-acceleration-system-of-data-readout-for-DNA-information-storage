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
CLIENT_DIR = REPO / "clients" / "python"
if str(CLIENT_DIR) not in sys.path:
    sys.path.insert(0, str(CLIENT_DIR))

from native_ldpc import (  # noqa: E402
    PARITY_COLS,
    bits_to_jpeg_bytes,
    decode_file as decode_native_file,
    deinterleave,
    hard_decode,
    load_pchk,
    load_permutation,
)


def decode_file(rx_path: Path, pchk: Path = None, perm_path: Path = None):
    return decode_native_file(
        rx_path,
        pchk or (RES / "dvb_s2_r5_6.pchk"),
        perm_path or (RES / "permutation64800"),
    )


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
