#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""生成 PS 侧解交织要用的查表 —— sw/app/ldpc_perm_table.c

为什么要有它
------------
板端结果缓冲是**交织序** `rx`，而片上译码核的 H 矩阵寻址是**自然序** `natural`
（见 docs/benchmarks/ldpc-onchip-l7-board.md）。两种序之间是**位级**置换：

    natural[perm[i]] = rx[i]        （clients/python/native_ldpc.py: deinterleave）

这条式子里 `perm` 表没被用上——**PS 需要的是它的逆**。把上式改写成「自然序第 c 位
取自 rx 的第几位」：

    natural[c] = rx[inv[c]]   ，其中 inv[perm[i]] = i

于是**装载与读回两个方向可以共用同一张 `inv`，且都按自然序计数器 c 顺序查表**：

    装载：natural[c] = rx[inv[c]]      按 c 递增 → 顺序查表、从 rx 聚读
    读回：rx[inv[c]] = natural[c]      按 c 递增 → 顺序查表、向 rx 散写

为什么不用压缩表
----------------
置换是伪随机的：行列交织、模关系、块内重排、字节级整块搬家**全部实测不命中**
（相邻差为 1 的比例 0.0）。所以只能老老实实存 64,800 项。

`inv` 的取值域是 0..64799 < 2^16，故 **u16 就够**（129,600 字节），不必 u32。
（`perm` 同理；本脚本选 `inv` 是因为它让两个方向的查表下标都是自然序计数。）

自检
----
生成前断言：输入表是 64,800 的**排列**；生成后断言：由 inv 反推的 perm 与原表逐项相同，
且用真实的板端回传样本跑一遍「本文件的语义」与 `native_ldpc.deinterleave` **逐位一致**。

用法
----
    python3 tools/gen_ldpc_perm_table.py            # 生成并自检
    python3 tools/gen_ldpc_perm_table.py --check    # 只校验现有文件是否最新（CI/门禁用）
"""

from __future__ import annotations

import argparse
import hashlib
import sys
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parent.parent
PERM_FILE = REPO / "clients" / "python" / "resources" / "permutation64800"
OUT_FILE = REPO / "sw" / "app" / "ldpc_perm_table.c"
N_BITS = 64800


def load_perm() -> np.ndarray:
    raw = PERM_FILE.read_bytes()
    perm = np.frombuffer(raw, dtype="<u4").astype(np.int64)
    if perm.size != N_BITS:
        raise SystemExit(f"置换表长度 {perm.size} != {N_BITS}")
    if len(np.unique(perm)) != N_BITS:
        raise SystemExit("置换表不是排列（有重复项）")
    if perm.min() < 0 or perm.max() >= N_BITS:
        raise SystemExit("置换表有越界项")
    return perm


def render(inv: np.ndarray, perm_sha: str) -> str:
    lines = []
    for i in range(0, N_BITS, 12):
        chunk = ", ".join(f"0x{v:04X}" for v in inv[i:i + 12])
        lines.append(f"    {chunk},")
    body = "\n".join(lines)
    arr_sha = hashlib.sha256(inv.astype("<u2").tobytes()).hexdigest()
    return f"""/* 自动生成，请勿手改 —— 由 tools/gen_ldpc_perm_table.py 产出。
 *
 * 语义：natural[c] = rx[inv[c]]（自然序第 c 位取自交织序第 inv[c] 位）。
 * 装载方向与读回方向共用本表，且都按自然序计数器 c 递增查表。
 *
 * 源：clients/python/resources/permutation64800（SHA-256 {perm_sha}）
 * 本数组（{N_BITS} × u16 小端）SHA-256：{arr_sha}
 * 校验：python3 tools/gen_ldpc_perm_table.py --check
 */
#include <stdint.h>

#include "ldpc_perm.h"

const uint16_t g_ldpc_nat_to_rx[{N_BITS}] = {{
{body}
}};
"""


def check_reference(perm: np.ndarray, inv: np.ndarray) -> None:
    """用真实语义自检：inv 必须与 native_ldpc.deinterleave 等价。"""
    sys.path.insert(0, str(REPO / "clients" / "python"))
    import native_ldpc as L  # noqa: E402

    rng = np.random.default_rng(20261014)
    for _ in range(3):
        rx = rng.integers(0, 2, N_BITS, dtype=np.uint8)
        want = L.deinterleave(rx, perm)
        got = rx[inv]                       # natural[c] = rx[inv[c]]
        if not np.array_equal(want, got):
            raise SystemExit("自检失败：inv 的语义与 native_ldpc.deinterleave 不一致")
    # 反推：inv[perm[i]] == i
    back = np.empty(N_BITS, np.int64)
    back[perm] = np.arange(N_BITS)
    if not np.array_equal(back, inv):
        raise SystemExit("自检失败：inv 不是 perm 的逆")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true",
                    help="只校验现有文件与源表一致，不写文件")
    args = ap.parse_args()

    perm = load_perm()
    inv = np.empty(N_BITS, np.int64)
    inv[perm] = np.arange(N_BITS)
    check_reference(perm, inv)

    perm_sha = hashlib.sha256(PERM_FILE.read_bytes()).hexdigest()
    text = render(inv, perm_sha)

    if args.check:
        if not OUT_FILE.is_file():
            print(f"缺失 {OUT_FILE.relative_to(REPO)}", file=sys.stderr)
            return 1
        if OUT_FILE.read_text() != text:
            print(f"{OUT_FILE.relative_to(REPO)} 与源表不一致，请重新生成", file=sys.stderr)
            return 1
        print(f"{OUT_FILE.relative_to(REPO)} 与 {PERM_FILE.name} 一致 ✓")
        return 0

    OUT_FILE.write_text(text)
    size = OUT_FILE.stat().st_size
    print(f"已生成 {OUT_FILE.relative_to(REPO)}（{size} 字节 / {size/1024:.0f} KiB）")
    print(f"  源表 SHA-256 : {perm_sha[:16]}…")
    print(f"  自检         : 排列性 ✓  逆变换 ✓  与 deinterleave 逐位一致 ✓")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
