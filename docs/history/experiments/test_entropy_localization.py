#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""D1_random_entropy 数据生成契约与退役历史诊断测试。

当前有效测试覆盖数据生成、确定性和定长适配。六项高熵历史诊断保留为
独立的显式跳过项：历史诊断，已退役，无现行目标。
"""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

import numpy as np

REPO_ROOT = Path(__file__).resolve().parent.parent
TOOLS_DIR = REPO_ROOT / "tools"

if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))

from generate_payload_dataset import (
    generate_dataset,
    mutate_read_sequence,
    simulate_sequencing_reads,
    sha256_file,
)


class TestRetiredHistoricalEntropyDiagnostics(unittest.TestCase):
    """历史诊断测试保留独立条目，但不再声称覆盖现行目标。"""

    def test_retired_historical_diagnostic_level1_encoder_self_test(self):
        self.skipTest("历史诊断，已退役，无现行目标；原实现依赖已退役的 debug_high_entropy。")

    def test_retired_historical_diagnostic_level2_alignment_and_cross_correlation(self):
        self.skipTest("历史诊断，已退役，无现行目标；原实现依赖已退役的 debug_high_entropy。")

    def test_retired_historical_diagnostic_level3_threshold_sensitivity(self):
        self.skipTest("历史诊断，已退役，无现行目标；原实现依赖已退役的 debug_high_entropy。")

    def test_retired_historical_diagnostic_level4_voter_saturation_and_paired_selection(self):
        self.skipTest("历史诊断，已退役，无现行目标；原实现依赖已退役的 debug_high_entropy。")

    def test_retired_historical_diagnostic_level5_spatial_error_distribution(self):
        self.skipTest("历史诊断，已退役，无现行目标；原实现依赖已退役的 debug_high_entropy。")

    def test_retired_historical_diagnostic_root_cause_conclusions(self):
        self.skipTest("历史诊断，已退役，无现行目标；原实现依赖已退役的 debug_high_entropy。")


class TestEntropyDatasetGeneration(unittest.TestCase):
    """仍有效的 D1/D2 数据生成与输入定长契约。"""

    def test_generator_mutation_and_fixed_len(self):
        """测试生成器变异与定长适配 (fixed_len_adaptation)"""
        rng = np.random.default_rng(12345)
        orig_seq = "A" * 75 + "C" * 75
        orig_qual = "I" * 150

        # 1. 纯替换
        seq_sub, qual_sub, n_sub, n_del, n_ins = mutate_read_sequence(
            orig_seq, orig_qual, sub_rate=0.05, ins_rate=0.0, del_rate=0.0, rng=rng, fixed_len=True
        )
        self.assertEqual(len(seq_sub), 150)
        self.assertEqual(len(qual_sub), 150)
        self.assertGreater(n_sub, 0)
        self.assertEqual(n_del, 0)
        self.assertEqual(n_ins, 0)

        # 2. 纯插入 + 定长截断
        seq_ins, qual_ins, n_sub, n_del, n_ins = mutate_read_sequence(
            orig_seq, orig_qual, sub_rate=0.0, ins_rate=0.05, del_rate=0.0, rng=rng, fixed_len=True
        )
        self.assertEqual(len(seq_ins), 150, "插入后定长适配应维持 150 bp")
        self.assertGreater(n_ins, 0)

        # 3. 纯缺失 + 定长填补
        seq_del, qual_del, n_sub, n_del, n_ins = mutate_read_sequence(
            orig_seq, orig_qual, sub_rate=0.0, ins_rate=0.0, del_rate=0.05, rng=rng, fixed_len=True
        )
        self.assertEqual(len(seq_del), 150, "缺失后定长适配应维持 150 bp")
        self.assertGreater(n_del, 0)

    def test_generator_seed_reproducibility(self):
        """测试模拟测序读段生成多 seed 确定性与可复现性"""
        ref_seq = "ACGT" * 1000
        reads1 = simulate_sequencing_reads(ref_seq, read_len=150, reads_count=50, seed=999)
        reads2 = simulate_sequencing_reads(ref_seq, read_len=150, reads_count=50, seed=999)
        reads3 = simulate_sequencing_reads(ref_seq, read_len=150, reads_count=50, seed=888)

        # 同 seed 必须 100% 逐字符一致
        self.assertEqual(reads1, reads2)
        # 异 seed 必须产生不同读段
        self.assertNotEqual(reads1, reads3)

    def test_d2_dataset_generation_and_manifest(self):
        """测试 D2 受控噪声数据集端到端生成与 manifest 契约规范"""
        with tempfile.TemporaryDirectory() as tmpdir:
            out_path = Path(tmpdir) / "test_d2_entropy"
            test_payload = np.random.default_rng(42).bytes(6750)
            manifest = generate_dataset(
                dataset_id="test_d2_entropy",
                payload_data=test_payload,
                payload_type="random",
                output_dir=out_path,
                tier="D2",
                reads_count=100,
                read_len=150,
                seed=42,
                sub_rate=0.01,
                ins_rate=0.005,
                del_rate=0.005,
                base_dataset="D1_random_entropy",
                verify_readout=False,
            )

            # 检查关键产物存在。
            # 注意 watermark.txt **不在**此列：2026-09-10 起水印收敛到
            # <datasets>/common/watermark.txt 一份共享副本，不再每个数据集各存一份
            # （详见 tests/datasets/common/README.md）。下面单独校验共享副本。
            for fname in [
                "source_payload.bin",
                "codeword.txt",
                "reference_sequence.txt",
                "reads_se150.fastq",
                "manifest.json",
                "SHA256SUMS",
            ]:
                self.assertTrue((out_path / fname).exists(), f"产物缺失: {fname}")

            # 水印共享副本：必须存在，且 manifest 记录的哈希必须与它逐字节相符。
            # 这比原来「数据集目录下有个 watermark.txt」更强——原断言只证明文件在，
            # 证明不了它与 manifest 自洽；收敛之后如果哪次生成用了不同水印，
            # 生成器会直接报错，而这条断言是第二道防线。
            shared_wm = out_path.parent / "common" / "watermark.txt"
            self.assertTrue(shared_wm.exists(), f"共享水印缺失: {shared_wm}")
            import hashlib as _h
            self.assertEqual(
                _h.sha256(shared_wm.read_bytes()).hexdigest(),
                manifest["watermark"]["sha256"],
                "共享水印与 manifest 记录的哈希不符——水印被换过但数据集没重生成",
            )
            self.assertNotIn(
                "watermark.txt",
                [ln.split()[-1] for ln in
                 (out_path / "SHA256SUMS").read_text(encoding="utf-8").split("\n") if ln.strip()],
                "SHA256SUMS 不应再列数据集本地的 watermark.txt（已收敛到 common/）",
            )

            # 检查 manifest 规范
            self.assertEqual(manifest["dataset_id"], "test_d2_entropy")
            self.assertEqual(manifest["provenance"]["tier"], "D2")
            self.assertEqual(manifest["provenance"]["base_dataset"], "D1_random_entropy")
            noise_model = manifest["provenance"]["noise_model"]
            self.assertEqual(noise_model["target_sub_rate"], 0.01)
            self.assertEqual(noise_model["target_ins_rate"], 0.005)
            self.assertEqual(noise_model["target_del_rate"], 0.005)
            self.assertIn("插删加定长适配", noise_model["length_adaptation"])
            self.assertGreater(noise_model["actual_substitutions"], 0)

            # 校验 SHA256SUMS 准确性
            sums_file = out_path / "SHA256SUMS"
            lines = sums_file.read_text(encoding="utf-8").strip().splitlines()
            for line in lines:
                sha, rel_name = line.strip().split()
                target_file = out_path / rel_name
                self.assertEqual(sha256_file(target_file), sha, f"SHA256 不符: {rel_name}")


if __name__ == "__main__":
    unittest.main()
