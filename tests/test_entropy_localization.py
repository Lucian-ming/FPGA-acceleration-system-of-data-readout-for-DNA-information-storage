#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""tests/test_entropy_localization.py —— 高熵样本 (D1_random_entropy) 失败分级定位与数据扩展测试套件

依据 docs/05 §6(D) 与项目数据契约要求：
1. 测试级 1（编码器自检）：验证原始随机 Payload 经全流程编码后与标准码字逐位吻合，C LDPC 0 迭代 0 错误还原；
2. 测试级 2（对齐准确率与伪互相关）：验证高熵下真实对齐得分均值降至 ~70.9 分，与伪互相关极值 (62~65 分) 严重重叠；
3. 测试级 3（门限敏感性）：验证 score_min=60 下产生 >2000 误码（复现板端 2671 误码），score_min=65 时误码降至 <300 且 LDPC 成功收敛；
4. 测试级 4（投票器与饱和）：验证累加器在 4096 条读段下未发生任何截断饱和，而双向配对择优完全消除伪读段、误码降至 0；
5. 测试级 5（反稀疏化空间分布）：验证板端 2671 误码全码字均匀分布（信息位与校验位均 ~4.1%），彻底排除 5b4b 错误扩散；
6. 测试根因综合判定：严格定论为 (B) 伪互相关与门限不适配为首要根因，(C) 浅覆盖为加剧因素，排除 (A) 和 (D)；
7. 测试数据生成扩展：测试多 seed 随机生成、D2 受控噪声注入（替换/插入/缺失）及定长适配契约。
"""

from __future__ import annotations

import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

import numpy as np

REPO_ROOT = Path(__file__).resolve().parent.parent
CLIENTS_PY = REPO_ROOT / "clients" / "python"
TOOLS_DIR = REPO_ROOT / "tools"
TOOLS_ATTIC = REPO_ROOT / "tools" / "attic"

if str(CLIENTS_PY) not in sys.path:
    sys.path.insert(0, str(CLIENTS_PY))
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))
if str(TOOLS_ATTIC) not in sys.path:
    sys.path.insert(0, str(TOOLS_ATTIC))

from debug_high_entropy import HighEntropyDiagnostics, unpack_dump_bytes
from generate_payload_dataset import (
    generate_dataset,
    mutate_read_sequence,
    simulate_sequencing_reads,
    sha256_file,
)


class TestEntropyLocalization(unittest.TestCase):
    """高熵随机样本 D1 失败分级定位与数据生成扩展测试"""

    @classmethod
    def setUpClass(cls):
        cls.dataset_dir = REPO_ROOT / "tests" / "datasets" / "D1_random_entropy"
        if not cls.dataset_dir.exists():
            raise unittest.SkipTest(f"数据集目录不存在: {cls.dataset_dir}")
        cls.diag = HighEntropyDiagnostics(cls.dataset_dir)

    def test_level1_encoder_self_test(self):
        """测试级 1: 编码器与纯生成逻辑自检 (证明生成器与 LDPC 编码无缺陷)"""
        res = self.diag.run_level1_encoder_self_test()
        self.assertTrue(res["passed"], "级 1 编码器自检必须 PASS")
        self.assertTrue(res["codeword_match"], "生成码字必须与原始标准码字完全一致")
        self.assertTrue(res["sparsify_reversible"], "4b->5b 稀疏化必须可逆还原")
        self.assertTrue(res["ref_seq_match"], "双位平面合成 DNA 序列必须与参考完全一致")
        self.assertTrue(res["direct_ldpc_pass"], "C LDPC 硬判决译码必须 100% 成功")
        self.assertEqual(res["direct_ldpc_iters"], 0, "无噪码字必须 0 轮迭代直接收敛")
        self.assertEqual(res["direct_ldpc_syndromes"], 0, "无噪码字综合征失败数必须为 0")
        self.assertTrue(res["payload_identical"], "译码解出 Payload 必须与原始输入逐字节一致")

    def test_level2_alignment_and_cross_correlation(self):
        """测试级 2: 模拟读段真实比对得分与极值伪互相关重叠特征"""
        res = self.diag.run_level2_alignment_accuracy(num_threads=4)
        self.assertEqual(res["total_reads"], 4096)
        corr_mean = res["correct_scores"]["mean"]
        self.assertAlmostEqual(corr_mean, 70.9, delta=2.5, msg="真实读段对齐得分均值应在 70.9 左右")

        wrong_max = res["wrong_scores"]["max"]
        self.assertGreaterEqual(wrong_max, 62, "40,350 位置滑窗极大伪相关得分应达到 62~65 分")

        corr_min = res["correct_scores"]["min"]
        self.assertLess(corr_min, wrong_max, "真读段得分下限应低于伪相关上限，证实存在得分重叠区间")

    def test_level3_threshold_sensitivity(self):
        """测试级 3: 门限敏感性扫描 (复现板端 60 门限失败并验证 65 门限成功)"""
        res = self.diag.run_level3_threshold_sensitivity(thresholds=(60, 65, 67), num_threads=4)
        scan = {item["threshold"]: item for item in res["threshold_scan"]}

        # thr=60: 板端默认环境，伪读段大量误入，复现高误码与 LDPC 失败
        r60 = scan[60]
        self.assertGreater(r60["false_reads_passed"], 3000, "thr=60 时错误方向读段误入应超过 3000 条")
        self.assertLess(r60["snr"], 1.5, "thr=60 时信噪比应小于 1.5")
        self.assertGreater(r60["raw_bit_errors"], 2000, "thr=60 时原始误码应超过 2000 bit (复现板端 2671 误码)")
        self.assertFalse(r60["ldpc_pass"], "thr=60 时 LDPC 必须失败")

        # thr=65: 最佳平衡点，伪读段被过滤大部分，误码大幅下降且 LDPC 收敛
        r65 = scan[65]
        self.assertLess(r65["false_reads_passed"], 200, "thr=65 时伪读段应降至 200 条以下")
        self.assertLess(r65["raw_bit_errors"], 300, "thr=65 时误码应降至 300 bit 以下")
        self.assertTrue(r65["ldpc_pass"], "thr=65 时 LDPC 必须成功收敛")

        # thr=67: 门限过高误杀真读段，15x 浅覆盖下产生空洞
        r67 = scan[67]
        self.assertLess(r67["true_retention_pct"], 85.0, "thr=67 时真读段保留率应低于 85%")
        self.assertGreater(r67["raw_bit_errors"], 400, "thr=67 时覆盖空洞应导致误码反弹至 400 bit 以上")
        self.assertFalse(r67["ldpc_pass"], "thr=67 时由于浅覆盖空洞 LDPC 失败")

    def test_level4_voter_saturation_and_paired_selection(self):
        """测试级 4: 累加器饱和事件与配对择优对比实验"""
        res = self.diag.run_level4_voter_saturation_analysis(num_threads=4)
        # 饱和检查：4096 条读段下未达到 ±127 或 ±511 上限
        self.assertEqual(res["saturation_events"]["safe_vote_value_511"], 0, "RTL 511 饱和截断事件必须为 0")
        self.assertEqual(res["saturation_events"]["int8_clip_127"], 0, "8-bit 127 饱和截断事件必须为 0")
        self.assertLess(res["vote_range"]["max_positive"], 100)
        self.assertGreater(res["vote_range"]["max_negative"], -100)

        # 双向配对择优对照组：彻底消除单方向伪相关后，误码降至 0
        paired = res["paired_selection_comparison"]
        self.assertEqual(paired["paired_errors"], 0, "双向配对择优应完全消除误码达到 0 错误")
        self.assertTrue(paired["paired_ldpc_converged"], "双向配对择优下 LDPC 必须收敛")

    def test_level5_spatial_error_distribution(self):
        """测试级 5: 板端真实 2671 误码空间均匀分布 (排除 5b4b 错误扩散)"""
        res = self.diag.run_level5_error_spatial_distribution()
        self.assertEqual(res["total_errors"], 2671, "实测 dump 误码数必须为 2671")
        self.assertFalse(res["error_propagation_check"]["is_cascading"])

        # 信息位与校验位误码率平稳（~4.1% 对 ~4.25%）
        p_rate = res["parity_bits_errors"]["error_rate_pct"]
        i_rate = res["info_bits_errors"]["error_rate_pct"]
        self.assertAlmostEqual(p_rate, i_rate, delta=0.5, msg="校验位与信息位误码率应高度一致 (无结构性偏向)")

        # 10 个 block 的分布均在合理区间 (2% ~ 8%)
        for b in res["blocks_10"]:
            self.assertGreaterEqual(b["error_rate_pct"], 2.0, f"Block {b['block']} 误码率偏低异常")
            self.assertLessEqual(b["error_rate_pct"], 8.0, f"Block {b['block']} 误码率偏高异常")

    def test_root_cause_conclusions(self):
        """测试根因综合研判结论的完备性与准确性"""
        l1 = self.diag.run_level1_encoder_self_test()
        l2 = self.diag.run_level2_alignment_accuracy(num_threads=2)
        l3 = self.diag.run_level3_threshold_sensitivity(thresholds=(60, 65), num_threads=2)
        l4 = self.diag.run_level4_voter_saturation_analysis(num_threads=2)
        l5 = self.diag.run_level5_error_spatial_distribution()

        verdict = self.diag.conclude_root_cause(l1, l2, l3, l4, l5)
        self.assertEqual(verdict["primary_cause"], "B")
        self.assertEqual(verdict["contributing_factor"], "C")

        hypos = verdict["hypotheses"]
        self.assertIn("REJECTED", hypos["A_generator_encoder_flaw"]["status"])
        self.assertIn("CONFIRMED_PRIMARY_ROOT_CAUSE", hypos["B_spurious_correlation_and_threshold_mismatch"]["status"])
        self.assertIn("CONFIRMED_CONTRIBUTING_FACTOR", hypos["C_insufficient_voting_depth"]["status"])
        self.assertIn("REJECTED", hypos["D_desparsifier_error_propagation"]["status"])

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
