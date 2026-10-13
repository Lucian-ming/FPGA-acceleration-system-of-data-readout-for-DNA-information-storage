#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""DVB-S2 R=5/6 纯 Python/Numpy 硬判决 LDPC 译码核心。"""

from __future__ import annotations

from pathlib import Path

import numpy as np

M_ROWS = 10_800
N_BITS = 64_800
K_INFO = 54_000
PARITY_COLS = 10_800
MAX_PAYLOAD_BYTES = K_INFO // 8


def load_pchk(path: Path):
    raw = np.fromfile(path, dtype="<i4")
    if raw.size < 3 or int(raw[0]) != 0x5080:
        raise ValueError(f"pchk 魔数不符: {hex(int(raw[0])) if raw.size else 'empty'}")
    m, n = int(raw[1]), int(raw[2])
    if (m, n) != (M_ROWS, N_BITS):
        raise ValueError(f"pchk 尺寸不符: {m}x{n}")

    rows, current = [], []
    for value in raw[3:]:
        if value < 0:
            rows.append(current)
            current = []
        else:
            current.append(int(value))
    rows.append(current)

    out = []
    for segment in rows[1:]:
        columns = [value - 1 for value in segment if value > 0]
        if any(column < 0 or column >= N_BITS for column in columns):
            raise ValueError("pchk 列地址越界")
        out.append(np.array(columns, dtype=np.int64))
    if len(out) != M_ROWS:
        raise ValueError(f"pchk 行数 {len(out)} != {M_ROWS}")
    return out


def load_permutation(path: Path) -> np.ndarray:
    permutation = np.fromfile(path, dtype="<u4").astype(np.int64)
    if permutation.size != N_BITS or len(np.unique(permutation)) != N_BITS:
        raise ValueError("permutation 表不是 64800 的排列")
    return permutation


def deinterleave(rx: np.ndarray, permutation: np.ndarray) -> np.ndarray:
    natural = np.empty_like(rx)
    natural[permutation] = rx
    return natural


def hard_decode(
    natural: np.ndarray,
    rows,
    max_iter: int = 50,
    verbose: bool = False,
) -> tuple[np.ndarray, int, int]:
    width = max(len(row) for row in rows)
    matrix = np.zeros((len(rows), width), dtype=np.int64)
    valid = np.zeros((len(rows), width), dtype=bool)
    for index, row in enumerate(rows):
        matrix[index, :len(row)] = row
        valid[index, :len(row)] = True

    llr0 = np.where(natural == 1, 3.0, -3.0)
    llr = llr0.copy()

    def syndrome(bits):
        values = bits[matrix]
        values[~valid] = 0
        return values.sum(axis=1) & 1

    decoded = natural.copy()
    initial_failed = int(syndrome(decoded).sum())
    if initial_failed == 0:
        return decoded.astype(np.uint8), 0, 0

    big = 1e9
    for iteration in range(1, max_iter + 1):
        magnitudes = np.abs(llr)[matrix]
        magnitudes[~valid] = big
        signs = np.sign(llr)[matrix]
        signs[~valid] = 1.0
        row_signs = np.prod(signs, axis=1)

        sorted_magnitudes = np.sort(magnitudes, axis=1)
        minimum1, minimum2 = sorted_magnitudes[:, 0], sorted_magnitudes[:, 1]
        equal_minimum = magnitudes == minimum1[:, None]
        previous = np.zeros_like(equal_minimum)
        previous[:, 1:] = np.cumsum(equal_minimum.astype(np.int8), axis=1)[:, :-1]
        first = equal_minimum & (previous == 0)

        messages = row_signs[:, None] * signs * np.where(
            first, minimum2[:, None], minimum1[:, None]
        )
        messages[~valid] = 0.0
        llr = llr0 + np.bincount(
            matrix.ravel(), weights=messages.ravel(), minlength=N_BITS
        )

        decoded = (llr > 0).astype(np.int64)
        failed = int(syndrome(decoded).sum())
        if verbose:
            print(f"  iter {iteration}: 剩余失败校验 {failed}")
        if failed == 0:
            return decoded.astype(np.uint8), initial_failed, iteration

    raise RuntimeError(
        f"LDPC 译码未收敛（{max_iter} 轮后仍有 {failed} 个失败校验）"
    )


def validate_input_bytes(input_bytes: int, available_bits: int | None = None) -> int:
    if isinstance(input_bytes, bool) or not isinstance(input_bytes, (int, np.integer)):
        raise ValueError("input_bytes 必须为 1..6750 的整数")
    count = int(input_bytes)
    if not 1 <= count <= MAX_PAYLOAD_BYTES:
        raise ValueError(f"input_bytes 必须为 1..{MAX_PAYLOAD_BYTES}，实得 {count}")
    if available_bits is not None and count * 8 > available_bits:
        raise ValueError(
            f"input_bytes={count} 需要 {count * 8} bit，当前只有 {available_bits} bit"
        )
    return count


def bits_to_bytes(bits: np.ndarray, input_bytes: int) -> bytes:
    """按 MSB-first 打包并截到指定字节数，不解释载荷格式。"""
    input_bytes = validate_input_bytes(input_bytes, int(bits.size))
    padding = (-bits.size) % 8
    padded = np.concatenate([bits, np.zeros(padding, dtype=np.uint8)])
    weights = np.array([128, 64, 32, 16, 8, 4, 2, 1], dtype=np.uint16)
    data = (padded.reshape(-1, 8) @ weights).astype(np.uint8).tobytes()
    return data[:input_bytes]


def bits_to_jpeg_bytes(bits: np.ndarray) -> bytes:
    """保留既有 JPEG EOI 截断语义，供 v1/R0.83 判据继续使用。"""
    padding = (-bits.size) % 8
    padded = np.concatenate([bits, np.zeros(padding, dtype=np.uint8)])
    weights = np.array([128, 64, 32, 16, 8, 4, 2, 1], dtype=np.uint16)
    data = (padded.reshape(-1, 8) @ weights).astype(np.uint8).tobytes()
    end = data.rfind(b"\xff\xd9")
    return data if end < 0 else data[:end + 2]


def bits_to_payload_bytes(bits: np.ndarray, input_bytes: int | None = None) -> bytes:
    """写任意载荷；未给长度时沿用原 JPEG EOI 截断，给长度时按字节截断。"""
    return bits_to_jpeg_bytes(bits) if input_bytes is None else bits_to_bytes(bits, input_bytes)


def read_bit_text(path: Path, expected_bits: int = N_BITS) -> str:
    text = path.read_text(encoding="utf-8")
    invalid = {char for char in text if char not in "01 \t\r\n"}
    if invalid:
        sample = "".join(sorted(invalid))[:16]
        raise ValueError(f"LDPC 输入含非 0/1/空白字符: {sample!r}")
    bits = "".join(char for char in text if char in "01")
    if len(bits) != expected_bits:
        raise ValueError(f"LDPC 输入应为 {expected_bits} bit，实得 {len(bits)}")
    return bits


def decode_file(rx_path: Path, pchk: Path, permutation_path: Path):
    bits = read_bit_text(rx_path)
    rx = np.frombuffer(bits.encode("ascii"), dtype=np.uint8) - ord("0")
    rows = load_pchk(pchk)
    permutation = load_permutation(permutation_path)
    natural = deinterleave(rx, permutation)
    codeword, initial_failed, iterations = hard_decode(natural, rows)
    return codeword[PARITY_COLS:], codeword, initial_failed, iterations
