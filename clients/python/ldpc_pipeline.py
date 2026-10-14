#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""板端片上 LDPC 结果的**校验与载荷提取** —— PC 端不做译码。

架构决定（用户 2026-10-14，覆盖此前"多后端"的一切设计）
--------------------------------------------------------
**LDPC 译码全部由 FPGA 片上完成。PC 端若还需要"再译一次"，就说明板端没纠对，
那是失败，不是让 PC 兜底。**

因此本模块只做三件事，**没有任何迭代译码、没有任何后端可选**：

  1. 把板端回传的结果解包（每字节 LSB 先）并**解交织**到自然序；
  2. **校验 syndrome**：全部校验行 XOR 为 0 ⇒ 板端已把码字纠对，通过；
     只要有一条非零 ⇒ 抛 BoardCodeRejected（板端未纠对，本用例失败）；
  3. 从合法码字里取出信息位（natural[PARITY_COLS:]，54,000 bit），
     按调用方给的字节数打包成载荷。

为什么「校验不过就失败」是对的
------------------------------
片上译码器**只在 syndrome 全零时才收敛**（`ldpc_decoder_p1.v` 的
`iteration_q >= MAX_ITER` 分支就是失败出口）；不收敛时固件**原样保留 Stage3 的输出**
（`sw/app/ldpc_onchip.c`）。所以：

    syndrome == 0   ⟺   板端确实把码字纠对了

反过来，PC 拿到一个 syndrome 非零的缓冲还想"救一救"，那正是被明令禁止的兜底。

为什么去掉 `hard_decode` 不改变任何结果
---------------------------------------
板端收敛时，`hard_decode` 本来就返回输入本身（0 轮迭代）——实测留证
`g3_runs/20261014T113108Z/ldpc_run1.log` 记「起始失败校验 0，0 轮收敛」。
逐位核对过：`natural[PARITY_COLS:]` ≡ `hard_decode` 输出的信息位 ≡ 当时落盘的
`decoded_bits`。⇒ 本模块把"再译一遍"换成"校验一遍"，**载荷逐位不变，只是不再兜底**。

`native_ldpc.hard_decode` 仍然存在——**离线工具**（数据集生成、黄金向量、
`tools/ldpc_decode.py`）在用，但**不在客户端运行路径上**。
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional

import numpy as np
from native_ldpc import (
    K_INFO,
    N_BITS,
    PARITY_COLS,
    bits_to_payload_bytes,
    deinterleave,
    load_pchk,
    load_permutation,
    read_bit_text,
    validate_input_bytes,
)

DECODER_PCHK = "dvb_s2_r5_6.pchk"
DECODER_PERM = "permutation64800"
DEC_INPUT_NAME = "dec_input.txt"
DECODED_BITS_NAME = "decoded_bits.txt"
# 载荷不再叫 .jpg —— 它可能是图像、音频、视频、文本或任意二进制（见 docs 的 kind 分布）。
PAYLOAD_NAME = "decoded_payload.bin"


class BoardCodeRejected(RuntimeError):
    """板端回传的不是合法码字 ⇒ 片上 LDPC 没纠对。**这是失败，不是让 PC 兜底。**"""

    def __init__(self, failed_rows: int, total_rows: int) -> None:
        self.failed_rows = failed_rows
        self.total_rows = total_rows
        super().__init__(
            f"板端回传的码字校验不过：{failed_rows}/{total_rows} 条校验行非零。"
            "片上 LDPC 没有收敛（固件此时原样保留 Stage3 的输出）。"
            "按既定架构，PC 端不做译码兜底 —— 本用例判为失败。"
        )


@dataclass
class BoardVerifyResult:
    """一次板端结果的校验与提取结果。"""

    result_path: Path
    dec_input_path: Path
    decoded_bits_path: Path
    payload_path: Path
    payload_bytes: int
    failed_rows: int
    total_rows: int

    @property
    def verified(self) -> bool:
        return self.failed_rows == 0


def _bundle_root() -> Path:
    if hasattr(sys, "_MEIPASS"):
        return Path(sys._MEIPASS)  # type: ignore[attr-defined]
    return Path(__file__).resolve().parent


def resource_path(name: str) -> Path:
    base = _bundle_root()
    candidates = [
        base / name,
        base / "resources" / name,
        Path(__file__).resolve().parent / name,
        Path(__file__).resolve().parent / "resources" / name,
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    raise FileNotFoundError(f"无法找到资源文件: {name}")


def row_index(rows) -> tuple[np.ndarray, np.ndarray]:
    """把稀疏校验矩阵压平成 (列号, 各段起点)，供一次 reduceat 算完全部校验行。"""
    lengths = np.fromiter((len(r) for r in rows), dtype=np.int64, count=len(rows))
    flat = np.concatenate([np.asarray(r, dtype=np.int64) for r in rows])
    starts = np.zeros(len(rows), dtype=np.int64)
    np.cumsum(lengths[:-1], out=starts[1:])
    return flat, starts


def syndrome_failures(natural: np.ndarray, flat: np.ndarray, starts: np.ndarray) -> int:
    """返回非零校验行的条数。0 表示这是一个合法码字（板端已纠对）。"""
    parity = np.bitwise_xor.reduceat(natural[flat], starts)
    return int(np.count_nonzero(parity))


def verify_board_result(
    result_bits_path: Path,
    output_dir: Path,
    input_bytes: Optional[int] = None,
    log: Optional[Callable[[str], None]] = None,
) -> BoardVerifyResult:
    """校验板端回传的码字并提取载荷。

    :param result_bits_path: 板端回传解包后的 64,800 个 0/1 位（即 dec_input.txt）
    :param input_bytes: 载荷字节数。给了按此截断；不给按 JPEG EOI 截断（沿用 R0.83 判据）。
    :raises BoardCodeRejected: syndrome 非零 —— 板端没纠对，本用例失败。
    """
    emit = log or (lambda _msg: None)
    output_dir.mkdir(parents=True, exist_ok=True)

    bits = read_bit_text(result_bits_path, expected_bits=N_BITS)
    rx = np.frombuffer(bits.encode("ascii"), dtype=np.uint8) - ord("0")

    if result_bits_path.name == DEC_INPUT_NAME and result_bits_path.parent.resolve() == output_dir.resolve():
        dec_input_path = result_bits_path
    else:
        dec_input_path = output_dir / DEC_INPUT_NAME
        dec_input_path.write_text(bits, encoding="utf-8")

    permutation = load_permutation(resource_path(DECODER_PERM))
    rows = load_pchk(resource_path(DECODER_PCHK))
    flat, starts = row_index(rows)

    natural = deinterleave(rx, permutation)

    failed = syndrome_failures(natural, flat, starts)
    if failed:
        emit(f"[板端校验] ✗ 校验行非零 {failed}/{len(rows)} —— 片上 LDPC 未纠对")
        raise BoardCodeRejected(failed, len(rows))
    emit(f"[板端校验] ✓ {len(rows)} 条校验行全为零 —— 板端已纠对；PC 端不做任何译码")

    info = natural[PARITY_COLS:]
    if input_bytes is not None:
        validate_input_bytes(input_bytes, int(info.size))

    decoded_bits_path = output_dir / DECODED_BITS_NAME
    decoded_bits_path.write_text("".join("01"[int(b)] for b in info), encoding="utf-8")

    payload = bits_to_payload_bytes(info, input_bytes)
    payload_path = output_dir / PAYLOAD_NAME
    payload_path.write_bytes(payload)
    emit(f"[板端校验] 已保存信息位 {decoded_bits_path}（{K_INFO} bit）")
    emit(f"[板端校验] 已保存载荷 {payload_path}（{len(payload)} 字节）")

    return BoardVerifyResult(
        result_path=result_bits_path,
        dec_input_path=dec_input_path,
        decoded_bits_path=decoded_bits_path,
        payload_path=payload_path,
        payload_bytes=len(payload),
        failed_rows=0,
        total_rows=len(rows),
    )


if __name__ == "__main__":  # pragma: no cover - 便于手工排查
    if len(sys.argv) < 2:
        print("用法: ldpc_pipeline.py <dec_input.txt> [输出目录] [载荷字节数]", file=sys.stderr)
        raise SystemExit(2)
    _src = Path(sys.argv[1])
    _out = Path(sys.argv[2]) if len(sys.argv) > 2 else _src.parent
    _n = int(sys.argv[3]) if len(sys.argv) > 3 else None
    try:
        _res = verify_board_result(_src, _out, _n, log=lambda m: print(m))
    except BoardCodeRejected as _exc:
        print(f"FAIL: {_exc}", file=sys.stderr)
        raise SystemExit(1)
    print(f"OK: 载荷 {_res.payload_bytes} 字节 -> {_res.payload_path}")
