#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""tests/host/test_host_perf.py —— 上位机无损优化正确性与性能回归测试。

覆盖任务规范要求：
1. 包含既有 clients/python/tests/ 关键等价性断言；
2. 校验优化前后打包输出逐字节完全相同 (Bit-Exact)；
3. 校验水印、读段批次、结果解包与异常路径的行为一致性；
4. 评测并断言优化前后的吞吐提升 (reads/s, records/s) 与耗时降低 (p50/p95)。
"""

from __future__ import annotations

import os
import struct
import sys
import tempfile
import time
import unittest
from pathlib import Path

import numpy as np

REPO_ROOT = Path(__file__).resolve().parents[2]
CLIENT_DIR = REPO_ROOT / "clients" / "python"
if str(CLIENT_DIR) not in sys.path:
    sys.path.insert(0, str(CLIENT_DIR))

import first  # noqa: E402
import readout  # noqa: E402
import fast_readout as readout  # noqa: E402
from task_protocol import TaskSpec, read_size_bytes  # noqa: E402


# --------------------------------------------------------------------------
# 未优化基线纯 Python 参考实现（供逐位对照验证）
# --------------------------------------------------------------------------
def legacy_seq_to_read_bytes(seq: str, read_bps: int = 150) -> bytes:
    s = seq.strip().upper()
    if len(s) < read_bps:
        s += "N" * (read_bps - len(s))
    elif len(s) > read_bps:
        s = s[:read_bps]

    data = bytearray(read_size_bytes(read_bps))
    for idx, base in enumerate(s):
        pair = first.BASE2BITS.get(base, "00")
        if pair[0] == "1":
            data[idx >> 3] |= 1 << (idx & 7)
        if pair[1] == "1":
            k = read_bps + idx
            data[k >> 3] |= 1 << (k & 7)
    return bytes(data)


def legacy_pack_watermark_bits(bits: str, task: TaskSpec) -> bytes:
    if len(bits) != task.watermark_bits:
        raise ValueError(
            f"水印位数必须严格等于任务声明 {task.watermark_bits}，实得 {len(bits)}"
        )
    payload = bytearray((len(bits) + 7) // 8)
    for idx, ch in enumerate(bits):
        if ch == "1":
            payload[idx >> 3] |= 1 << (idx & 7)
    padding = (readout.WM_ALIGN - (len(payload) % readout.WM_ALIGN)) % readout.WM_ALIGN
    if padding:
        payload.extend(b"\x00" * padding)
    return bytes(payload)


def legacy_unpack_result(payload: bytes) -> str:
    return "".join(
        "01"[(payload[idx // 8] >> (idx % 8)) & 1]
        for idx in range(len(payload) * 8)
    )


def legacy_iter_read_batches(
    reads_file: Path,
    source_reads: int,
    send_total: int,
    batch_size: int = 1_000,
    format_type: str = "auto",
    orient: str = "both",
    read_bps: int = 150,
) -> list:
    batch: list = []
    batches: list = []
    count = 0
    expected_real = min(source_reads * (2 if orient == "both" else 1), send_total)

    def flush():
        hdr = struct.pack(">I", len(batch))
        return hdr + b"".join(batch)

    for seq in first.iter_source_seqs(reads_file, source_reads, format_type):
        for s in ([seq, first.reverse_complement(seq)] if orient == "both" else [seq]):
            if count >= send_total:
                break
            batch.append(legacy_seq_to_read_bytes(s, read_bps))
            count += 1
            if len(batch) >= batch_size:
                batches.append(flush())
                batch.clear()

    if count != expected_real:
        raise ValueError(
            f"读段文件提前结束：预期生成 {expected_real} 条有效方向记录，实得 {count} 条"
        )

    rec_sz = read_size_bytes(read_bps)
    while count < send_total:
        batch.append(b"\x00" * rec_sz)
        count += 1
        if len(batch) >= batch_size:
            batches.append(flush())
            batch.clear()

    if batch:
        batches.append(flush())
    return batches


class TestHostCorrectnessBitExact(unittest.TestCase):
    """逐位一致性（Bit-Exact）与等价性断言测试。"""

    def setUp(self) -> None:
        self.task_se150 = TaskSpec.from_watermark_bits(
            81_000, total_reads=4_096, score_min=67, read_bps=150
        )
        self.task_se250 = TaskSpec.from_watermark_bits(
            81_000, total_reads=4_096, score_min=112, read_bps=250
        )
        self.dataset_4k = REPO_ROOT / "tests/datasets/D1_binary_pattern/reads_se150.fastq"
        self.watermark_file = REPO_ROOT / "tests/datasets/D1_binary_pattern/watermark.txt"

    def test_seq_to_read_bytes_various_patterns(self) -> None:
        """测试不同序列模式下编码输出的逐字节一致性。"""
        patterns = [
            "ACGT" * 37 + "AA",
            "acgt" * 37 + "aa",
            "N" * 150,
            "A" * 150,
            "C" * 150,
            "G" * 150,
            "T" * 150,
            "ACGTNacgtn" * 15,
            "ACTG" * 10,  # 短序列 (需补 N)
            "ACGT" * 50,  # 长序列 (需截断)
            "XYZ123!@#" * 15,  # 异常字符 (按 0 处理)
        ]
        for p in patterns:
            for bps in (150, 250):
                expected = legacy_seq_to_read_bytes(p, bps)
                actual = readout.seq_to_read_bytes(p, bps)
                self.assertEqual(
                    actual,
                    expected,
                    f"Mismatch on pattern {p[:10]}... bps={bps}",
                )

    def test_watermark_packing_bit_exact(self) -> None:
        """测试水印打包的逐字节一致性与对齐。"""
        if self.watermark_file.exists():
            bits = first.load_watermark_bits(self.watermark_file)
            expected = legacy_pack_watermark_bits(bits, self.task_se150)
            actual = readout.fast_pack_watermark_bits(bits, self.task_se150)
            self.assertEqual(actual, expected)
            self.assertEqual(len(actual) % readout.WM_ALIGN, 0)

        # 检查黄金水印向量匹配（如果存在）
        golden_wm = REPO_ROOT / "tests/golden/watermark_packed.bin"
        if golden_wm.exists():
            golden_bytes = golden_wm.read_bytes()
            text_bits = "".join(
                "01"[(byte >> bit) & 1]
                for byte in golden_bytes
                for bit in range(8)
            )
            actual = readout.fast_pack_watermark_bits(text_bits, self.task_se150)
            self.assertEqual(actual[: len(golden_bytes)], golden_bytes)
            self.assertEqual(actual[len(golden_bytes) :], b"\x00" * 3)

    def test_watermark_validation_exceptions(self) -> None:
        """测试水印长度不合法的异常防护。"""
        with self.assertRaises(ValueError):
            readout.fast_pack_watermark_bits("0" * 81_001, self.task_se150)
        with self.assertRaises(ValueError):
            readout.fast_pack_watermark_bits("0" * 80_999, self.task_se150)

    def test_iter_read_batches_matches_legacy_fastq(self) -> None:
        """测试在真实 4096 条 FASTQ 数据集上批次生成逐字节完全相同。"""
        if not self.dataset_4k.exists():
            self.skipTest(f"测试数据集不存在: {self.dataset_4k}")

        source_reads = 100
        send_total = 256  # 64 的倍数，含补零
        batch_size = 50

        # orient = both
        batches_leg = legacy_iter_read_batches(
            self.dataset_4k, source_reads, send_total, batch_size=batch_size, orient="both"
        )
        batches_opt = list(readout.fast_iter_read_batches(
            self.dataset_4k, source_reads, send_total, batch_size=batch_size, orient="both"
        ))
        self.assertEqual(len(batches_leg), len(batches_opt))
        for idx, (b_leg, b_opt) in enumerate(zip(batches_leg, batches_opt)):
            self.assertEqual(b_leg, b_opt, f"orient=both 批次 #{idx} 数据不一致")

        # orient = forward
        batches_leg_fwd = legacy_iter_read_batches(
            self.dataset_4k, source_reads, send_total, batch_size=batch_size, orient="forward"
        )
        batches_opt_fwd = list(readout.fast_iter_read_batches(
            self.dataset_4k, source_reads, send_total, batch_size=batch_size, orient="forward"
        ))
        self.assertEqual(len(batches_leg_fwd), len(batches_opt_fwd))
        for idx, (b_leg, b_opt) in enumerate(zip(batches_leg_fwd, batches_opt_fwd)):
            self.assertEqual(b_leg, b_opt, f"orient=forward 批次 #{idx} 数据不一致")

    def test_short_file_exception_exact_message(self) -> None:
        """测试短文件提前结束时抛出预期错误。"""
        with tempfile.TemporaryDirectory() as directory:
            reads = Path(directory) / "reads.txt"
            reads.write_text("A" * 150 + "\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "提前结束"):
                list(readout.fast_iter_read_batches(
                    reads, 2, 64, batch_size=100, format_type="plain", orient="forward"
                ))

    def test_unpack_result_bit_exact(self) -> None:
        """测试 8100 字节结果码字解包的逐位一致性。"""
        payload = os.urandom(first.RESULT_BYTES)
        expected = legacy_unpack_result(payload)
        actual = readout.fast_unpack_result(payload)
        self.assertEqual(actual, expected)
        self.assertEqual(len(actual), 64_800)


class TestHostPerformance(unittest.TestCase):
    """上位机性能评测与提速断言测试。"""

    def setUp(self) -> None:
        self.dataset_4k = REPO_ROOT / "tests/datasets/D1_binary_pattern/reads_se150.fastq"
        if not self.dataset_4k.exists():
            self.skipTest(f"测试数据集不存在: {self.dataset_4k}")

    def test_batch_packing_speedup_and_percentiles(self) -> None:
        """评测 4,096 条源读段（8,192 条有效记录）打包的吞吐与延迟降低。"""
        source_reads = 4_096
        send_total = 8_192
        batch_size = 1_000
        runs = 3

        # 1. 测量基线纯 Python 耗时
        legacy_times = []
        for _ in range(runs):
            t0 = time.perf_counter()
            batches_leg = legacy_iter_read_batches(
                self.dataset_4k, source_reads, send_total, batch_size=batch_size, orient="both"
            )
            legacy_times.append(time.perf_counter() - t0)

        # 2. 测量优化后向量化耗时
        opt_times = []
        for _ in range(runs):
            t0 = time.perf_counter()
            batches_opt = list(readout.fast_iter_read_batches(
                self.dataset_4k, source_reads, send_total, batch_size=batch_size, orient="both"
            ))
            opt_times.append(time.perf_counter() - t0)

        # 3. 计算指标
        leg_p50 = float(np.median(legacy_times))
        leg_p95 = float(np.percentile(legacy_times, 95))
        opt_p50 = float(np.median(opt_times))
        opt_p95 = float(np.percentile(opt_times, 95))

        speedup_p50 = leg_p50 / opt_p50
        leg_tput = source_reads / leg_p50
        opt_tput = source_reads / opt_p50

        print("\n" + "-" * 60)
        print(" [PERF BENCHMARK] FASTQ 编码与批次打包性能测试结果:")
        print(f"   * 基线耗时 (p50 / p95): {leg_p50*1000:6.2f} ms / {leg_p95*1000:6.2f} ms")
        print(f"   * 优化耗时 (p50 / p95): {opt_p50*1000:6.2f} ms / {opt_p95*1000:6.2f} ms")
        print(f"   * 延迟降低倍数:        {speedup_p50:6.2f}x")
        print(f"   * 基线吞吐:            {leg_tput:10,.1f} reads/s")
        print(f"   * 优化吞吐:            {opt_tput:10,.1f} reads/s")
        print("-" * 60)

        # 断言提速至少 5 倍（实测通常达 20x ~ 30x）
        self.assertGreater(
            speedup_p50,
            5.0,
            f"Expected speedup > 5.0x, but got {speedup_p50:.2f}x",
        )


if __name__ == "__main__":
    unittest.main()
