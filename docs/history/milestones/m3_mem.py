#!/usr/bin/env python3
"""M3 / BD-3 的 DDR 镜像转换与逐位比较。

Xilinx PS7 VIP 的 DDR 模型是 **32 bit 字寻址**：
`pre_load_mem_from_file` / `peek_mem_to_file` 读写的文件都是「每行一个 32 bit 十六进制字」，
字 N 覆盖字节地址 4N..4N+3，且字内是小端（字节 4N 是该字的最低字节）。

而本项目的黄金向量（stage2_in / stage2_expect / stage3_expect）是「每行一个 64 bit 字」，
对应 Voter / Decoder 的 64 bit AXI 主口一拍。因此一个 64 bit 拍 = VIP 文件里连续两行：
先低 32 bit，后高 32 bit。

本脚本只做格式搬运和比较，不生成、不修改任何黄金数据；黄金文件始终只读。
"""

import argparse
import sys


def read_words(path, width_bits):
    """读取「每行一个十六进制字」的文件，返回整数列表。"""
    words = []
    nibbles = width_bits // 4
    with open(path, "r", encoding="ascii") as fh:
        for lineno, raw in enumerate(fh, 1):
            tok = raw.strip()
            if not tok or tok.startswith("//"):
                continue
            try:
                val = int(tok, 16)
            except ValueError:
                raise SystemExit(f"{path}:{lineno}: 不是合法的十六进制字: {tok!r}")
            if val >> width_bits:
                raise SystemExit(
                    f"{path}:{lineno}: 值 {tok} 超过 {width_bits} bit"
                )
            words.append(val)
    _ = nibbles
    return words


def cmd_to_vip(args):
    """64 bit 黄金格式 -> VIP 32 bit 字文件（低字在前）。"""
    src = read_words(args.src, 64)
    with open(args.dst, "w", encoding="ascii") as fh:
        for w in src:
            fh.write("%08x\n" % (w & 0xFFFFFFFF))
            fh.write("%08x\n" % ((w >> 32) & 0xFFFFFFFF))
    print(f"[m3_mem] to-vip: {args.src} ({len(src)} × 64bit) -> "
          f"{args.dst} ({2 * len(src)} × 32bit, {8 * len(src)} B)")


def cmd_from_vip(args):
    """VIP 32 bit 字文件 -> 64 bit 格式（两行合一拍）。"""
    src = read_words(args.src, 32)
    if args.beats is not None:
        need = 2 * args.beats
        if len(src) < need:
            raise SystemExit(
                f"[m3_mem] FAIL: {args.src} 只有 {len(src)} 个 32bit 字，"
                f"不足 {args.beats} 拍所需的 {need} 个"
            )
        src = src[:need]
    if len(src) % 2:
        raise SystemExit(f"[m3_mem] FAIL: {args.src} 的 32bit 字数为奇数，无法组成 64bit 拍")
    with open(args.dst, "w", encoding="ascii") as fh:
        for i in range(0, len(src), 2):
            fh.write("%016x\n" % (src[i] | (src[i + 1] << 32)))
    print(f"[m3_mem] from-vip: {args.src} -> {args.dst} ({len(src) // 2} × 64bit)")


def cmd_reads_to_vip(args):
    """reads_cw.hex（每行一条读段的 300 bit 码字）-> VIP 32 bit 字镜像。

    板端 MM2S 每条读段发 40 B = 10 个 32 bit 字，与 DNA 核 AXIS 入口的装配顺序
    （in_cnt 0..9，第 9 个字只用低 12 bit）完全一致：
        word w = cw[32w .. 32w+31]，w = 0..8；word 9 = {20'b0, cw[299:288]}
    这是 BD-3b 入口判据的**激励**，同时也是它的**期望值**（引擎把装载进来的码字
    原样搬进结果记录的 bit 325:26）。黄金文件只读，本函数不修改它。
    """
    words = []
    n = 0
    with open(args.src, "r", encoding="ascii") as fh:
        for raw in fh:
            tok = raw.strip()
            if not tok or tok.startswith("//"):
                continue
            cw = int(tok, 16)
            if cw >> 300:
                raise SystemExit(f"{args.src}: 码字超过 300 bit: {tok!r}")
            for w in range(10):
                words.append((cw >> (32 * w)) & 0xFFFFFFFF)
            n += 1
            if args.reads is not None and n >= args.reads:
                break
    if args.reads is not None and n < args.reads:
        raise SystemExit(f"[m3_mem] FAIL: {args.src} 只有 {n} 条读段，不足 {args.reads} 条")
    with open(args.dst, "w", encoding="ascii") as fh:
        for w in words:
            fh.write("%08x\n" % w)
    print(f"[m3_mem] reads-to-vip: {args.src} ({n} 条读段) -> "
          f"{args.dst} ({len(words)} × 32bit, {4 * len(words)} B)")


def cmd_cmp(args):
    """逐拍/逐位比较两个 64 bit 文件，报告第一处不一致。"""
    act = read_words(args.actual, 64)
    exp = read_words(args.expect, 64)
    if args.beats is not None:
        exp = exp[:args.beats]
        act = act[:args.beats]
    if len(act) != len(exp):
        print(f"[m3_mem] FAIL: 拍数不一致，实际 {len(act)}，期望 {len(exp)}")
        return 1

    bad_beats = 0
    bad_bits = 0
    first = None
    for i, (a, e) in enumerate(zip(act, exp)):
        if a != e:
            bad_beats += 1
            bad_bits += bin(a ^ e).count("1")
            if first is None:
                first = (i, a, e)

    if bad_beats:
        i, a, e = first
        print(f"[m3_mem] FAIL: {args.label}：{len(act)} 拍中 {bad_beats} 拍不符，"
              f"共 {bad_bits} bit；首个不符在第 {i} 拍 "
              f"实际 {a:016x} 期望 {e:016x}")
        return 1

    total_bits = 64 * len(act)
    print(f"[m3_mem] PASS: {args.label}：{len(act)} 拍 / {total_bits} bit 与黄金向量逐位相同")
    return 0


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("to-vip", help="64bit 黄金格式 -> VIP 32bit 字文件")
    p.add_argument("src")
    p.add_argument("dst")
    p.set_defaults(func=cmd_to_vip)

    p = sub.add_parser("from-vip", help="VIP 32bit 字文件 -> 64bit 格式")
    p.add_argument("src")
    p.add_argument("dst")
    p.add_argument("--beats", type=int, default=None, help="只取前 N 拍")
    p.set_defaults(func=cmd_from_vip)

    p = sub.add_parser("reads-to-vip",
                       help="reads_cw.hex（300bit/行）-> VIP 32bit 字镜像（10 字/读段）")
    p.add_argument("src")
    p.add_argument("dst")
    p.add_argument("--reads", type=int, default=None, help="只取前 N 条读段")
    p.set_defaults(func=cmd_reads_to_vip)

    p = sub.add_parser("cmp", help="逐位比较两个 64bit 文件")
    p.add_argument("actual")
    p.add_argument("expect")
    p.add_argument("--beats", type=int, default=None)
    p.add_argument("--label", default="比较")
    p.set_defaults(func=cmd_cmp)

    args = ap.parse_args()
    rc = args.func(args)
    sys.exit(rc if isinstance(rc, int) else 0)


if __name__ == "__main__":
    main()
