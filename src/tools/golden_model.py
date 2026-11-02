#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""DNA 读出流水线的黄金参考模型（纯软件实现）。

本脚本用可运行代码固化 `docs/02-data-contract.md` 中的数据契约：

    编码序列(40,500 nt) --2bit/位平面--> 81,000 bit
        XOR 水印(81,000 bit)          --> 81,000 bit 稀疏流
        5b->4b 反稀疏化                --> 64,800 bit LDPC 码字

`verify-code` 子命令用 R0.83 黄金数据证明上述链路逐位成立；
`simulate` 子命令用同样的规则从 FASTQ 复现 Stage1(比对)+Stage2(投票)+Stage3(反稀疏化)，
产出可直接喂给 LDPC 解码器的 dec_input.txt，并给出每一级与黄金数据的逐位符合率。

它是 RTL / PS 固件的验收基准（oracle），不是生产路径的替代品。

用法示例：
    python3 tools/golden_model.py verify-code
    python3 tools/golden_model.py desparsify voter_out.bin dec_input.txt
    python3 tools/golden_model.py simulate --limit 5000
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parent.parent
DATA = REPO / ".." / "data" / "r083-data"

DEF_WATERMARK = DATA / "source-data" / "watermark-sequences" / "r0.83_watermark.txt"
DEF_SEQUENCE = DATA / "source-data" / "encoded_sequences" / "dna-40_5kb-mc-r0_83.txt"
DEF_CODEWORD = DATA / "source-data" / "encoded_codeword" / "codeword_r083.txt"
DEF_READS = DATA / "sequencing-data" / "dna-40_5kb-mc-se150.fastq"

# 碱基 -> 2 bit，与 clients/python/first.py 的 BASE2BITS 一致。
# 高位（pair[0]）进入第 0 位平面，低位（pair[1]）进入第 1 位平面。
BASE2VAL = {"A": 0, "T": 1, "G": 2, "C": 3, "N": 0}

# 5b -> 4b 反稀疏化：由 R0.83 黄金数据反解得到，与 RTL conv40_32() 的
# “最高位为取反标志、低 4 位为数据”规则完全一致。
# 输入按码流顺序读取 5 bit，b0 为组内第一个 bit（即表中的 bit4）。
DESPARSIFY_TABLE = {
    0b00000: 0b0000, 0b00001: 0b0001, 0b00010: 0b0010, 0b00011: 0b0011,
    0b00100: 0b0100, 0b00101: 0b0101, 0b00110: 0b0110, 0b01000: 0b1000,
    0b01001: 0b1001, 0b01010: 0b1010, 0b01100: 0b1100, 0b10000: 0b1111,
    0b10001: 0b1110, 0b10010: 0b1101, 0b10100: 0b1011, 0b11000: 0b0111,
}


# ---------------------------------------------------------------------------
# 基础读写
# ---------------------------------------------------------------------------
def read_bits(path: Path) -> np.ndarray:
    """读取纯 0/1 文本，返回 uint8 位数组。"""
    text = path.read_text(encoding="utf-8", errors="ignore")
    return np.frombuffer(
        "".join(ch for ch in text if ch in "01").encode("ascii"), dtype=np.uint8
    ) - ord("0")


def read_sequence(path: Path) -> np.ndarray:
    """读取纯 ACGT 文本，返回 0..3 的符号数组。"""
    text = "".join(ch for ch in path.read_text(encoding="utf-8", errors="ignore") if ch in "ACGTNacgtn")
    return np.array([BASE2VAL[ch.upper()] for ch in text], dtype=np.uint8)


def symbols_to_planes(sym: np.ndarray) -> np.ndarray:
    """符号数组 -> 位平面码流：前 L bit 为高位平面，后 L bit 为低位平面。"""
    return np.concatenate([(sym >> 1) & 1, sym & 1]).astype(np.uint8)


def planes_to_symbols(bits: np.ndarray) -> np.ndarray:
    """位平面码流 -> 符号数组（与 symbols_to_planes 互逆）。"""
    half = bits.size // 2
    return ((bits[:half] << 1) | bits[half:]).astype(np.uint8)


def desparsify(bits: np.ndarray) -> np.ndarray:
    """81,000 bit 稀疏流 -> 64,800 bit 码字（5b -> 4b）。

    规则：每组 5 bit 按码流顺序 b0..b4，输出 b1^b0, b2^b0, b3^b0, b4^b0。
    对码本内的 16 个输入，它与 DESPARSIFY_TABLE 完全一致；对码本外的输入
    （信道出错时会出现）也有定义，行为与硬件一致，因此可用于统计误码率。
    """
    if bits.size % 5:
        raise ValueError(f"稀疏流长度 {bits.size} 不是 5 的倍数")
    groups = bits.reshape(-1, 5)
    return (groups[:, 1:] ^ groups[:, :1]).reshape(-1)


def count_illegal_groups(bits: np.ndarray) -> int:
    """统计不在稀疏码本（汉明重量<=2）内的 5-bit 组数量。"""
    groups = bits.reshape(-1, 5)
    return int((groups.sum(axis=1) > 2).sum())


def bits_to_text(bits: np.ndarray) -> str:
    return "".join("01"[b] for b in bits)


# ---------------------------------------------------------------------------
# Stage1 / Stage2 软件模型
# ---------------------------------------------------------------------------
def iter_fastq(path: Path, limit: int):
    """按 FASTQ 逐条产出序列字符串。"""
    produced = 0
    with path.open("r", encoding="utf-8", errors="ignore") as fh:
        while produced < limit:
            if not fh.readline():
                break
            seq = fh.readline().strip()
            fh.readline()
            fh.readline()
            if not seq:
                break
            yield seq
            produced += 1


def make_ref_spectrum(ref_sym: np.ndarray, read_len: int):
    """预计算参考序列 4 个指示向量的 FFT，用于快速滑窗相关。"""
    n = ref_sym.size + read_len
    size = 1 << (n - 1).bit_length()
    return size, [np.fft.rfft((ref_sym == s).astype(np.float64), size) for s in range(4)]


def align_read(read_sym: np.ndarray, size: int, spectra, max_pos: int):
    """返回 (最佳起点, 最佳匹配分数)。等价于 srpe_batch 的滑窗相关+取峰。"""
    score = np.zeros(size)
    for s in range(4):
        kernel = (read_sym == s).astype(np.float64)[::-1]
        score += np.fft.irfft(spectra[s] * np.fft.rfft(kernel, size), size)
    valid = score[read_sym.size - 1: read_sym.size - 1 + max_pos + 1]
    pos = int(np.argmax(valid))
    return pos, int(round(valid[pos]))


def cmd_verify_code(args) -> int:
    wm = read_bits(Path(args.watermark))
    seq = read_sequence(Path(args.sequence))
    codeword = read_bits(Path(args.codeword))

    print(f"水印      : {wm.size} bit")
    print(f"编码序列  : {seq.size} nt -> {seq.size * 2} bit")
    print(f"参考码字  : {codeword.size} bit")
    if wm.size != seq.size * 2:
        print("[FAIL] 水印位数必须等于编码序列的 2 倍")
        return 1

    # XOR 规则与查找表必须在码本内完全等价
    for value, expect in DESPARSIFY_TABLE.items():
        b = np.array([(value >> k) & 1 for k in (4, 3, 2, 1, 0)], dtype=np.uint8)
        got = desparsify(b)
        got_val = int(got[0] << 3 | got[1] << 2 | got[2] << 1 | got[3])
        if got_val != expect:
            print(f"[FAIL] XOR 规则与查找表不符: {value:05b} -> {got_val:04b} != {expect:04b}")
            return 1
    print("规则自检  : XOR 规则与 16 项查找表等价  PASS")

    sparse = symbols_to_planes(seq) ^ wm
    ones = int(sparse.sum())
    print(f"稀疏流    : {sparse.size} bit, 1 的比例 {ones / sparse.size:.4f}, "
          f"码本外的组 {count_illegal_groups(sparse)}")
    produced = desparsify(sparse)
    ok = produced.size == codeword.size and bool((produced == codeword).all())
    print(f"5b->4b 输出: {produced.size} bit")
    print(f"[{'PASS' if ok else 'FAIL'}] 反稀疏化结果与 codeword_r083.txt 逐位一致: {ok}")
    return 0 if ok else 1


def cmd_desparsify(args) -> int:
    src = Path(args.infile)
    raw = src.read_bytes()
    if args.input_format == "text":
        bits = read_bits(src)
    else:
        # 板端 Stage2 输出：按 64-bit 字 LSB-first 打包
        bits = np.unpackbits(np.frombuffer(raw, dtype=np.uint8), bitorder="little")
    bits = bits[: args.bits]
    if bits.size != args.bits:
        print(f"[FAIL] 输入只有 {bits.size} bit，需要 {args.bits} bit")
        return 1
    out = desparsify(bits)
    Path(args.outfile).write_text(bits_to_text(out), encoding="utf-8")
    print(f"已写出 {out.size} bit 到 {args.outfile}")
    return 0


def reverse_complement(sym: np.ndarray) -> np.ndarray:
    """A<->T, G<->C 并反序。BASE2VAL 下互补即 值^1。"""
    return (sym ^ 1)[::-1]


def cmd_simulate(args) -> int:
    wm = read_bits(Path(args.watermark))
    ref_sym = planes_to_symbols(wm)          # 水印本身就是比对参考
    truth_sym = read_sequence(Path(args.sequence))
    codeword = read_bits(Path(args.codeword))
    layer = ref_sym.size

    reads = list(iter_fastq(Path(args.reads), args.limit))
    if not reads:
        print("[FAIL] 未读到任何 read")
        return 1
    read_len = len(reads[0])
    max_pos = layer - read_len
    print(f"参考长度  : {layer} nt   水印 {wm.size} bit")
    print(f"读段      : {len(reads)} 条 x {read_len} bp   有效起点 0..{max_pos}")

    size, spectra = make_ref_spectrum(ref_sym, read_len)
    votes = np.zeros(2 * layer, dtype=np.int32)
    score_sum = 0
    used = 0
    rc_used = 0
    for i, seq in enumerate(reads):
        if len(seq) != read_len:
            continue
        rs = np.array([BASE2VAL.get(c, 0) for c in seq.upper()], dtype=np.uint8)
        pos, score = align_read(rs, size, spectra, max_pos)
        if args.rc:
            rc = reverse_complement(rs)
            pos_r, score_r = align_read(rc, size, spectra, max_pos)
            if score_r > score:
                rs, pos, score = rc, pos_r, score_r
                rc_used += 1
        score_sum += score
        if score < args.min_score:
            continue
        used += 1
        idx = np.arange(pos, pos + read_len)
        hi = ((rs >> 1) & 1).astype(np.int32) * 2 - 1
        lo = (rs & 1).astype(np.int32) * 2 - 1
        np.add.at(votes, idx, hi)
        np.add.at(votes, idx + layer, lo)
        if args.progress and (i + 1) % args.progress == 0:
            print(f"  ... {i + 1}/{len(reads)} 条已比对", flush=True)

    print(f"平均比对分: {score_sum / len(reads):.1f} / {read_len}   参与投票 {used} 条"
          f"   反向互补 {rc_used} 条")
    consensus = (votes > 0).astype(np.uint8)
    covered = votes != 0
    truth_bits = symbols_to_planes(truth_sym)
    agree = int((consensus == truth_bits).sum())
    print(f"共识覆盖  : {int(covered.sum())}/{covered.size} bit")
    print(f"共识误码率: {(consensus.size - agree) / consensus.size:.6f} "
          f"({consensus.size - agree} bit 错)")

    sparse = consensus ^ wm
    illegal = count_illegal_groups(sparse)
    print(f"码本外的组: {illegal}/{sparse.size // 5} = {illegal / (sparse.size // 5):.6f}"
          "   （理想为 0，可作为共识质量的自检指标）")

    produced = desparsify(sparse)
    err = int((produced != codeword).sum())
    print(f"码字误码率: {err}/{codeword.size} = {err / codeword.size:.6f}")
    print("            DVB-S2 R=5/6 硬判决的纠错门限约 1e-2 量级，超过即无法译码")
    out = Path(args.out)
    out.write_text(bits_to_text(produced), encoding="utf-8")
    print(f"已写出 dec_input 到 {out}")
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("verify-code", help="证明 编码序列^水印 -> 5b4b == 参考码字")
    p.add_argument("--watermark", default=str(DEF_WATERMARK))
    p.add_argument("--sequence", default=str(DEF_SEQUENCE))
    p.add_argument("--codeword", default=str(DEF_CODEWORD))
    p.set_defaults(func=cmd_verify_code)

    p = sub.add_parser("desparsify", help="把 81,000 bit 稀疏流转成 64,800 bit 码字")
    p.add_argument("infile")
    p.add_argument("outfile")
    p.add_argument("--input-format", choices=["text", "packed"], default="text",
                   help="text=0/1 文本; packed=板端 64bit LSB-first 打包的二进制")
    p.add_argument("--bits", type=int, default=81000)
    p.set_defaults(func=cmd_desparsify)

    p = sub.add_parser("simulate", help="从 FASTQ 软件复现 Stage1+2+3")
    p.add_argument("--reads", default=str(DEF_READS))
    p.add_argument("--watermark", default=str(DEF_WATERMARK))
    p.add_argument("--sequence", default=str(DEF_SEQUENCE))
    p.add_argument("--codeword", default=str(DEF_CODEWORD))
    p.add_argument("--limit", type=int, default=2000)
    p.add_argument("--rc", action="store_true",
                   help="同时尝试反向互补方向并取比对分更高者（真实测序数据必需）")
    p.add_argument("--min-score", type=int, default=0,
                   help="只让比对分不低于该值的读段参与投票（0=全部）")
    p.add_argument("--out", default="dec_input.txt")
    p.add_argument("--progress", type=int, default=0, help="每 N 条打印一次进度")
    p.set_defaults(func=cmd_simulate)

    args = ap.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
