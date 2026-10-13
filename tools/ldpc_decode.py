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
  python3 tools/ldpc_decode.py decode <输入0/1文本> --payload 输出文件 --input-bytes N
  python3 tools/ldpc_decode.py verify          # 用仓库内 R0.83 黄金向量自检
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
    K_INFO,
    PARITY_COLS,
    bits_to_jpeg_bytes,
    bits_to_payload_bytes,
    decode_file as decode_native_file,
    deinterleave,
    hard_decode,
    load_pchk,
    load_permutation,
    validate_input_bytes,
)


def decode_file(rx_path: Path, pchk: Path = None, perm_path: Path = None):
    return decode_native_file(
        rx_path,
        pchk or (RES / "dvb_s2_r5_6.pchk"),
        perm_path or (RES / "permutation64800"),
    )


# ---------------------------------------------------------------- 自检
def cmd_verify(args) -> int:
    # data/R0.83_data 是不入 Git 的只读原始数据，不能作为干净 clone
    # 的回归前置条件。目标 JPEG 已作为验证证据纳入版本管理；其
    # MSB-first 字节位流直接提供 52,992 bit 有效载荷判据。
    target_path = REPO / "docs/images/verification/recovered_1080reads.jpg"
    jpg = target_path.read_bytes()
    jpg_bits = np.unpackbits(np.frombuffer(jpg, dtype=np.uint8))
    if jpg_bits.size > K_INFO:
        raise ValueError(f"目标 JPEG 为 {jpg_bits.size} bit，超过 LDPC 信息位 {K_INFO}")
    dec_input = np.frombuffer(
        "".join(c for c in (REPO / "tests/golden/dec_input.txt").read_text() if c in "01").encode(),
        dtype=np.uint8) - ord("0")

    rows = load_pchk(RES / "dvb_s2_r5_6.pchk")
    perm = load_permutation(RES / "permutation64800")

    # 对版本化的 dec_input 译码。纠正后的自然码字可用于记录译码器
    # 实际改写量；业务正确性由 JPEG 有效载荷逐 bit、逐字节与哈希共同判定。
    received = deinterleave(dec_input, perm)
    codeword, synd0, iters = hard_decode(received, rows)
    info = codeword[PARITY_COLS:]
    corrected_bits = int((received != codeword).sum())
    payload_before = int((received[PARITY_COLS:PARITY_COLS + jpg_bits.size] != jpg_bits).sum())
    payload_after = int((info[:jpg_bits.size] != jpg_bits).sum())
    tail_ones = int(info[jpg_bits.size:].sum())
    print(f"[verify] dec_input 起始失败校验 {synd0}，{iters} 轮收敛，译码器改写 {corrected_bits} bit；"
          f"JPEG 有效载荷错误 {payload_before} → {payload_after}，尾部 1 为 {tail_ones}")

    img = bits_to_jpeg_bytes(info)
    img_ok = img == jpg
    print(f"[verify] 重建 JPEG 与 Milk coronet.jpg 逐字节{'相同' if img_ok else '不同'} "
          f"({len(img)} vs {len(jpg)} B)")
    import hashlib
    print(f"[verify] SHA-256 {hashlib.sha256(img).hexdigest()[:16]}...")

    if corrected_bits == 91 and iters == 5 and payload_after == 0 and img_ok:
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
    if args.payload:
        payload = bits_to_payload_bytes(info, args.input_bytes)
        Path(args.payload).write_bytes(payload)
        print(f"[decode] 原始载荷已写入 {args.payload} ({len(payload)} B)")
    elif args.image:
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
    outputs = p.add_mutually_exclusive_group()
    outputs.add_argument("--image", help="同时重建 JPEG（沿用 EOI 截断）")
    outputs.add_argument("--payload", help="同时写出任意原始载荷；必须同时指定 --input-bytes")
    p.add_argument("--input-bytes", type=int, help="原始载荷的有效字节数（1..6750，不查找 JPEG 标记）")
    p.set_defaults(func=cmd_decode)

    p = sub.add_parser("verify", help="用 R0.83 黄金数据自检")
    p.set_defaults(func=cmd_verify)

    args = ap.parse_args(argv)
    if args.cmd == "decode":
        if args.payload and args.input_bytes is None:
            ap.error("--payload 必须同时指定 --input-bytes N")
        if args.input_bytes is not None and not args.payload:
            ap.error("--input-bytes 只用于 --payload；JPEG 请使用 --image")
        if args.input_bytes is not None:
            try:
                validate_input_bytes(args.input_bytes, K_INFO)
            except ValueError as error:
                ap.error(str(error))
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
