#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""上位机高性能读出与向量化批处理核心模块 (clients/python/readout.py)。

本模块提供无损、逐位严格一致 (Bit-Exact) 的高性能读段解析与位平面打包实现：
1. 利用 numpy 向量化与查表 (LUT) 消除 Python 解释器层面的逐字节与逐位循环；
2. 消除反向互补链的冗余字符串创建与重复编码（通过位平面逆序与翻转 `hi_rc = hi[::-1]`, `lo_rc = lo[::-1] ^ 1`）；
3. 预分配整批 DMA / 网络传输缓冲区，避免大量小对象的内存重分配与复制；
4. 严格遵守 docs/02-data-contract.md 与 docs/05-interfaces.md 的数据契约与位序 (LSB-first)；
5. 提供与 first.py 逐位等价的高性能实现与流式生成器。
"""

from __future__ import annotations

import struct
from pathlib import Path
from typing import Iterable, List, Optional, Sequence, Tuple, Union

import numpy as np
from task_protocol import (
    FRAME_READS,
    MAX_TOTAL_READS,
    READ_BASES,
    TaskSpec,
    read_size_bytes,
)

# ============================================================================
# 预计算常数与查表 (Lookup Tables)
# ============================================================================
# 水印对齐常数
WM_ALIGN = 8
MAX_WATERMARK = 10_128
RESULT_BYTES = 8_100

# 256 元素 ASCII 查表：
# 高位平面 (hi): G/g/C/c -> 1, 其余 -> 0
# 低位平面 (lo): T/t/C/c -> 1, 其余 -> 0
# A/a/N/n 及任何其它非法/未知字符均映射为 0 (与 BASE2BITS.get(base, '00') 严格等价)
LUT_HI = np.zeros(256, dtype=np.uint8)
LUT_LO = np.zeros(256, dtype=np.uint8)
for _c in b"GCgc":
    LUT_HI[_c] = 1
for _c in b"TCtc":
    LUT_LO[_c] = 1


def seq_to_read_bytes(seq: str, read_bps: int = READ_BASES) -> bytes:
    """把一条 read_bps bp 序列编码成 read_size_bytes(read_bps) 字节（单条快速编码）。

    SE150: 150 bp -> 40 B; SE250: 250 bp -> 64 B。
    码流前 read_bps 位为高位平面，后 read_bps 位为低位平面，字节内 LSB-first 打包。
    """
    s = seq.strip()
    seq_len = len(s)
    if seq_len < read_bps:
        s = s + ("N" * (read_bps - seq_len))
    elif seq_len > read_bps:
        s = s[:read_bps]

    raw = s.encode("latin1", errors="replace")
    buf = np.frombuffer(raw, dtype=np.uint8)
    full_bits = np.concatenate([LUT_HI[buf], LUT_LO[buf]])
    packed = np.packbits(full_bits, bitorder="little")

    target_sz = read_size_bytes(read_bps)
    out = np.zeros(target_sz, dtype=np.uint8)
    out[: len(packed)] = packed
    return out.tobytes()


def batch_seqs_to_records(
    seqs: Sequence[str],
    read_bps: int = READ_BASES,
    orient: str = "both",
) -> np.ndarray:
    """将一批序列字符串批量向量化转换为打包记录矩阵。

    :param seqs: 读段序列字符串序列
    :param read_bps: 读段长度 (150 或 250)
    :param orient: "both" (每条产生正向 + 反向互补) 或 "forward" (仅正向)
    :return: 形状为 (N_records, read_size_bytes) 的 uint8 数组
    """
    k_seqs = len(seqs)
    if k_seqs == 0:
        return np.zeros((0, read_size_bytes(read_bps)), dtype=np.uint8)

    # 规范化长度为 read_bps
    standard_len = all(len(s) == read_bps for s in seqs)
    if standard_len:
        raw_ascii = "".join(seqs).encode("latin1", errors="replace")
        arr = np.frombuffer(raw_ascii, dtype=np.uint8).reshape(k_seqs, read_bps)
    else:
        padded = []
        for s in seqs:
            s = s.strip()
            slen = len(s)
            if slen < read_bps:
                s = s + ("N" * (read_bps - slen))
            elif slen > read_bps:
                s = s[:read_bps]
            padded.append(s)
        raw_ascii = "".join(padded).encode("latin1", errors="replace")
        arr = np.frombuffer(raw_ascii, dtype=np.uint8).reshape(k_seqs, read_bps)

    hi = LUT_HI[arr]
    lo = LUT_LO[arr]

    if orient == "both":
        # 反向互补无需重新解码字符串：
        # 序列反序后，hi_rc 恰为 hi[:, ::-1]，lo_rc 恰为 lo[:, ::-1] ^ 1
        hi_rc = hi[:, ::-1]
        lo_rc = lo[:, ::-1] ^ 1
        bits_fwd = np.concatenate([hi, lo], axis=1)
        bits_rc = np.concatenate([hi_rc, lo_rc], axis=1)

        # 交织排列: [fwd0, rc0, fwd1, rc1, ...]
        records_bits = np.empty((2 * k_seqs, 2 * read_bps), dtype=np.uint8)
        records_bits[0::2] = bits_fwd
        records_bits[1::2] = bits_rc
        total_records = 2 * k_seqs
    elif orient == "forward":
        records_bits = np.concatenate([hi, lo], axis=1)
        total_records = k_seqs
    else:
        raise ValueError(f"未知 orient={orient!r}")

    packed = np.packbits(records_bits, axis=1, bitorder="little")
    rec_sz = read_size_bytes(read_bps)
    out_buf = np.zeros((total_records, rec_sz), dtype=np.uint8)
    out_buf[:, : packed.shape[1]] = packed
    return out_buf


def fast_pack_watermark_bits(bits: str, task: TaskSpec) -> bytes:
    """向量化打包水印比特流至网络传输负载 (LSB-first, 8 字节对齐)。"""
    if len(bits) != task.watermark_bits:
        raise ValueError(
            f"水印位数必须严格等于任务声明 {task.watermark_bits}，实得 {len(bits)}"
        )

    arr = np.frombuffer(bits.encode("ascii"), dtype=np.uint8) - ord("0")
    packed = np.packbits(arr, bitorder="little")

    padding = (WM_ALIGN - (len(packed) % WM_ALIGN)) % WM_ALIGN
    if padding:
        packed = np.pad(packed, (0, padding), constant_values=0)

    payload = packed.tobytes()
    if len(payload) > MAX_WATERMARK:
        raise ValueError(
            f"Watermark payload too large: {len(payload)} bytes > {MAX_WATERMARK} bytes"
        )
    return payload


def fast_unpack_result(payload: bytes) -> str:
    """极速展开板端回传的 8,100 字节码字为 64,800 比特 0/1 字符串 (LSB-first)。"""
    if len(payload) != RESULT_BYTES:
        raise RuntimeError(
            f"PKT_RESULT 长度应为 {RESULT_BYTES} B，实得 {len(payload)} B"
        )
    raw = np.frombuffer(payload, dtype=np.uint8)
    bits = np.unpackbits(raw, bitorder="little")
    return (bits + ord("0")).tobytes().decode("ascii")


def fast_iter_source_seqs(
    path: Path,
    limit: int,
    format_type: str = "auto",
) -> List[str]:
    """批量读取最多 limit 条读段序列。"""
    if format_type == "auto":
        with path.open("r", encoding="utf-8", errors="ignore") as handle:
            first_line = handle.readline().strip()
        format_type = "fastq" if first_line.startswith("@") else "plain"

    seqs: List[str] = []
    with path.open("r", encoding="utf-8", errors="ignore") as handle:
        if format_type == "fastq":
            for _ in handle:
                try:
                    s = next(handle)
                    next(handle)
                    next(handle)
                except StopIteration:
                    break
                seqs.append(s.strip())
                if len(seqs) >= limit:
                    break
        else:
            for line in handle:
                s = line.strip()
                if s:
                    seqs.append(s)
                    if len(seqs) >= limit:
                        break
    return seqs


def fast_iter_read_batches(
    reads_file: Path,
    source_reads: int,
    send_total: int,
    batch_size: int = 1_000,
    format_type: str = "auto",
    orient: str = "both",
    read_bps: int = READ_BASES,
) -> Iterable[bytes]:
    """产出 PKT_BATCH 负载块的高性能向量化生成器。

    与 legacy iter_read_batches 保持逐字节完全一致：
    - 批次划分与尾批补零规则完全一致；
    - 预分配整批 DMA 缓冲区，减少数千次小对象分配与拼接；
    - 向上取整到 FRAME_READS (64) 倍数；
    - 文件提前结束时抛出相同 ValueError。
    """
    if source_reads <= 0 or send_total <= 0:
        raise ValueError("source_reads 与 send_total 必须为正数")
    if batch_size <= 0:
        raise ValueError("batch_size 必须为正数")
    if send_total % FRAME_READS:
        raise ValueError(f"send_total 必须为 {FRAME_READS} 的整数倍")

    per_read = 2 if orient == "both" else 1
    expected_real = min(source_reads * per_read, send_total)
    rec_sz = read_size_bytes(read_bps)

    # 1. 批量加载序列
    seqs = fast_iter_source_seqs(reads_file, source_reads, format_type)
    real_seq_count = len(seqs)
    actual_real_records = real_seq_count * per_read

    if real_seq_count < source_reads:
        raise ValueError(
            f"读段文件提前结束：预期生成 {expected_real} 条有效方向记录，实得 {actual_real_records} 条"
        )

    # 2. 向量化转换为记录矩阵
    records_matrix = batch_seqs_to_records(seqs, read_bps=read_bps, orient=orient)
    if records_matrix.shape[0] > send_total:
        records_matrix = records_matrix[:send_total]
        actual_real_records = send_total

    # 3. 预分配 send_total 总缓冲区（已自动补零）
    total_buf = np.zeros((send_total, rec_sz), dtype=np.uint8)
    total_buf[:actual_real_records] = records_matrix

    # 4. 按 batch_size 切片产出 PKT_BATCH 负载: struct.pack(">I", batch_count) + data
    raw_mem = total_buf.tobytes()
    offset = 0
    records_left = send_total
    while records_left > 0:
        cur_count = min(batch_size, records_left)
        chunk_len = cur_count * rec_sz
        hdr = struct.pack(">I", cur_count)
        yield hdr + raw_mem[offset : offset + chunk_len]
        offset += chunk_len
        records_left -= cur_count
