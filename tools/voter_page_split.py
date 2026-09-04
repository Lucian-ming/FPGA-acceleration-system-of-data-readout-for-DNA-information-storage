#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Voter 读突发的 4 KB 跨页拆分参考表（B20 那套逻辑在新记录尺寸下的落点）。

`differential_voter_v1_0.v` 每条 Stage1 记录用一次读突发取回。AXI 规范 A3.4.1
禁止突发跨越 4 KB 边界，所以 B20 把跨页的读拆成两笔：先读到页边界，再读完剩余
拍数（RTL 里是 `rd_beats_to_page_end` / `rd_next_burst_beats`，:337-344）。

记录尺寸一变，落点全变：
    SE150  48 B / 6 拍   gcd(48,4096)=16 → 周期 256 条，4096 条里跨页 32 次
    SE250  72 B / 9 拍   gcd(72,4096)=8  → 周期 512 条，4096 条里跨页 64 次
docs/20 §3.2 V8 要求「必须重新验证，不能只改数字」——本脚本给出那份落点表，
供 S4 的 TB 当判据用。

**顺带查一个只在 SE250 才出现的位宽截断**：`rd_next_burst_beats` 取的是
`rd_beats_to_page_end[2:0]`（3 bit）。它只在 `beats_to_page_end < beats_remaining`
时被选中，所以 SE150 下取值恒为 0..5，3 bit 装得下；SE250 下 `beats_remaining`
最大是 9，取值可达 8，而 8 & 0b111 == 0 —— **零拍突发**。

用法：
    python3 tools/voter_page_split.py                 # SE150 自校验 + SE250 报告
    python3 tools/voter_page_split.py --record-bytes 72 --beats 9 --records 4096
"""

from __future__ import annotations

import argparse
import math
import sys

PAGE = 4096
BEAT_BYTES = 8          # 64 bit 数据通道


def analyse(record_bytes: int, beats: int, n_records: int, burst_field_bits: int = 3):
    """返回跨页记录清单与位宽截断风险清单。"""
    crossings, truncated = [], []
    for i in range(n_records):
        offset = (record_bytes * i) % PAGE
        beats_to_page_end = (PAGE - offset) // BEAT_BYTES
        if beats_to_page_end < beats:                    # 需要拆成两笔
            crossings.append((i, record_bytes * i, beats_to_page_end,
                              beats - beats_to_page_end))
            if beats_to_page_end != (beats_to_page_end & ((1 << burst_field_bits) - 1)):
                truncated.append((i, beats_to_page_end,
                                  beats_to_page_end & ((1 << burst_field_bits) - 1)))
    period = record_bytes * PAGE // math.gcd(record_bytes, PAGE) // record_bytes
    return crossings, truncated, period


def report(record_bytes, beats, n_records, burst_field_bits, label):
    crossings, truncated, period = analyse(record_bytes, beats, n_records,
                                           burst_field_bits)
    print(f"=== {label}：每条 {record_bytes} B / {beats} 拍，共 {n_records} 条，"
          f"突发拍数字段 {burst_field_bits} bit ===")
    print(f"  拆分周期            {period} 条（lcm({record_bytes},{PAGE})/{record_bytes}）")
    print(f"  跨页记录数          {len(crossings)}")
    if crossings:
        i, off, a, b = crossings[0]
        print(f"  首次跨页            记录 {i}（偏移 0x{off:X}），拆成 {a} + {b} 拍")
        print(f"  前 8 个跨页记录号   {[c[0] for c in crossings[:8]]}")
    if truncated:
        print(f"  ⚠️ 位宽截断出错     {len(truncated)} 次 —— "
              f"beats_to_page_end 取值 {truncated[0][1]} 被截成 {truncated[0][2]}（零拍突发）")
        print(f"     出错记录号        {[t[0] for t in truncated[:6]]}"
              f"{' …' if len(truncated) > 6 else ''}")
        print(f"     记录号 mod {period}    {sorted({t[0] % period for t in truncated})}")
    else:
        print(f"  位宽截断            无风险（取值恒 ≤ {(1 << burst_field_bits) - 1}）")
    return crossings, truncated


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--record-bytes", type=int)
    ap.add_argument("--beats", type=int)
    ap.add_argument("--records", type=int, default=4096)
    ap.add_argument("--burst-field-bits", type=int, default=3,
                    help="rd_burst_beats / rd_beats_to_page_end 的位宽（RTL 现状 3）")
    ap.add_argument("--list", action="store_true", help="打印全部跨页记录")
    args = ap.parse_args(argv)

    if args.record_bytes:
        crossings, _ = report(args.record_bytes, args.beats, args.records,
                              args.burst_field_bits, "自定义")
        if args.list:
            print("\n  记录号  字节偏移   第一笔拍数  第二笔拍数")
            for i, off, a, b in crossings:
                print(f"  {i:6d}  0x{off:08X}  {a:9d}  {b:9d}")
        return 0

    # 默认：先用 SE150 自校验，再报 SE250。
    # 自校验的判据来自 RTL 自己的注释（differential_voter_v1_0.v:278-281：
    # 「4096 条记录中 32 次，首次在记录 85」），是独立于本脚本的第三方数字。
    # 对不上就说明本脚本的模型错了，后面 SE250 那张表也不能信。
    crossings, truncated = report(48, 6, 4096, 3, "SE150（自校验）")
    ok = len(crossings) == 32 and crossings[0][0] == 85 and not truncated
    print(f"  自校验（RTL 注释：32 次 / 首次记录 85 / 无截断）"
          f"{'  ✅ 相符' if ok else '  ❌ 不符，模型有问题'}")
    print()
    report(72, 9, 4096, 3, "SE250（RTL 现状位宽）")
    print()
    report(72, 9, 4096, 4, "SE250（把这些字段加宽到 4 bit 之后）")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
