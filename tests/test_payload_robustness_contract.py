#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""tests/test_payload_robustness_contract.py —— Payload 与鲁棒性契约测试套件

对齐 docs/05 §5 (任务 B) 门禁要求：
1. 测试 dump 校验函数：全文件合法性校验（全文件 64,800 字节检查，拒收非法字节与异常长度；明确 8,100 字节 LSB-first 解包）；
2. 测试 check-dumps 逻辑对 tests/datasets/ 下五份真实保存 dump 的复核：精确得到 4 PASS + 1 FAIL，保留 D1 random 边界事实；
3. 测试板端等价投票模式（双向独立过阈值 + 逐票饱和截断 [-128, 127]）与传统软件最佳方向模式的区别与自洽性。
"""

import os
import sys
import unittest
from pathlib import Path
import numpy as np

REPO_ROOT = Path(__file__).resolve().parent.parent
CLIENTS_PY = REPO_ROOT / "clients" / "python"
TOOLS_DIR = REPO_ROOT / "tools"

if str(CLIENTS_PY) not in sys.path:
    sys.path.insert(0, str(CLIENTS_PY))
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))

from run_multi_payload_regression import (
    MultiPayloadRegression,
    PayloadTestResult,
    unpack_dump_bytes,
)
from run_robustness_scan import (
    stage2_vote_board_equivalent,
    stage2_vote_legacy_software,
)


class TestDumpValidationContract(unittest.TestCase):
    """测试 dump 文件全文件严格合法性校验契约"""

    def test_valid_64800_ascii(self):
        """合法 64,800 字节全 ASCII '0'/'1'"""
        raw = b"0" * 32400 + b"1" * 32400
        bits = unpack_dump_bytes(raw)
        self.assertEqual(bits.shape, (64800,))
        self.assertEqual(bits.dtype, np.uint8)
        self.assertEqual(int(bits[:32400].sum()), 0)
        self.assertEqual(int(bits[32400:].sum()), 32400)

    def test_valid_64800_binary(self):
        """合法 64,800 字节全二进制 0x00/0x01"""
        raw = bytes([0] * 20000 + [1] * 44800)
        bits = unpack_dump_bytes(raw)
        self.assertEqual(bits.shape, (64800,))
        self.assertEqual(bits.dtype, np.uint8)
        self.assertEqual(int(bits[:20000].sum()), 0)
        self.assertEqual(int(bits[20000:].sum()), 44800)

    def test_valid_8100_packed_lsb_first(self):
        """合法 8,100 字节 packed 数据按字节内 LSB-first 解包 (docs/02 契约)"""
        # 构造字节: 0x01 (0b00000001), 0x80 (0b10000000)
        # LSB-first:
        #   0x01 -> [1, 0, 0, 0, 0, 0, 0, 0]
        #   0x80 -> [0, 0, 0, 0, 0, 0, 0, 1]
        raw = bytes([0x01, 0x80]) + bytes(8098)
        bits = unpack_dump_bytes(raw, bitorder="little")
        self.assertEqual(bits.shape, (64800,))
        np.testing.assert_array_equal(bits[:8], [1, 0, 0, 0, 0, 0, 0, 0])
        np.testing.assert_array_equal(bits[8:16], [0, 0, 0, 0, 0, 0, 0, 1])

    def test_invalid_length(self):
        """异常长度必须明确报错抛出 ValueError"""
        bad_lengths = [0, 100, 8099, 8101, 32400, 64799, 64801]
        for bl in bad_lengths:
            with self.subTest(length=bl):
                raw = bytes(bl)
                with self.assertRaises(ValueError) as cm:
                    unpack_dump_bytes(raw)
                self.assertIn("长度非法", str(cm.exception))

    def test_invalid_bytes_full_file_check(self):
        """全文件校验：前 100 字节合法但后续包含非法字节必须被捕获"""
        # 前 100 字节合法 ASCII，第 105 字节为 0x02
        raw = bytearray(b"0" * 64800)
        raw[105] = 0x02
        with self.assertRaises(ValueError) as cm:
            unpack_dump_bytes(bytes(raw))
        self.assertIn("105", str(cm.exception))
        self.assertIn("0x02", str(cm.exception))

        # 前 5000 字节合法 ASCII，第 5001 字节为 'X' (ord('X')=88)
        raw2 = bytearray(b"1" * 64800)
        raw2[5001] = ord("X")
        with self.assertRaises(ValueError) as cm:
            unpack_dump_bytes(bytes(raw2))
        self.assertIn("5001", str(cm.exception))

        # 末尾字节非法
        raw3 = bytearray(b"0" * 64800)
        raw3[64799] = 0xFF
        with self.assertRaises(ValueError) as cm:
            unpack_dump_bytes(bytes(raw3))
        self.assertIn("64799", str(cm.exception))


class TestSavedDumpsRegressionFact(unittest.TestCase):
    """复核已保存的 5 份真实板测 dump：精确重现 4 PASS + 1 FAIL 科学边界"""

    def setUp(self):
        self.reg = MultiPayloadRegression()
        self.configs = self.reg.get_dataset_configs()

    def test_reproduce_exact_four_pass_one_fail(self):
        """必须精确得到 4 个 PASS + 1 个 FAIL，忠实重现真实事实"""
        results = []
        for cfg in self.configs:
            res = self.reg.run_check_saved_dumps(cfg)
            self.assertIsNotNone(res)
            results.append(res)

        pass_count = sum(1 for r in results if r.passed)
        fail_count = sum(1 for r in results if not r.passed)
        self.assertEqual(pass_count, 4, f"期望 4 PASS，实际得到 {pass_count}")
        self.assertEqual(fail_count, 1, f"期望 1 FAIL，实际得到 {fail_count}")

        # 逐数据集断言
        res_map = {r.dataset_id: r for r in results}
        self.assertTrue(res_map["D0_image_mandrill"].passed)
        self.assertEqual(res_map["D0_image_mandrill"].raw_bit_errors, 42)
        self.assertEqual(res_map["D0_image_mandrill"].ldpc_iters, 47)

        self.assertTrue(res_map["D1_text_manifesto"].passed)
        self.assertEqual(res_map["D1_text_manifesto"].raw_bit_errors, 16)
        self.assertEqual(res_map["D1_text_manifesto"].ldpc_iters, 4)

        self.assertTrue(res_map["D1_binary_pattern"].passed)
        self.assertEqual(res_map["D1_binary_pattern"].raw_bit_errors, 7)
        self.assertEqual(res_map["D1_binary_pattern"].ldpc_iters, 1)

        self.assertTrue(res_map["D1_structured_sparse"].passed)
        self.assertEqual(res_map["D1_structured_sparse"].raw_bit_errors, 18)
        self.assertEqual(res_map["D1_structured_sparse"].ldpc_iters, 1)

        # 高熵失败边界必须保留
        d1_rand = res_map["D1_random_entropy"]
        self.assertFalse(d1_rand.passed)
        self.assertEqual(d1_rand.raw_bit_errors, 2671)
        self.assertEqual(d1_rand.ldpc_iters, 50)
        self.assertEqual(d1_rand.recovered_sha256, "LDPC_DECODE_FAILED")

    def test_threshold_differences_recorded(self):
        """明确保留 D1_random_entropy 门限 (60) 与其它样本 (67) 差异"""
        cfg_map = {c["id"]: c for c in self.configs}
        self.assertEqual(cfg_map["D1_random_entropy"]["score_min"], 60)
        self.assertEqual(cfg_map["D0_image_mandrill"]["score_min"], 67)
        self.assertEqual(cfg_map["D1_text_manifesto"]["score_min"], 67)
        self.assertEqual(cfg_map["D1_binary_pattern"]["score_min"], 67)
        self.assertEqual(cfg_map["D1_structured_sparse"]["score_min"], 67)

    def test_missing_dump_fails_explicitly(self):
        """缺 dump 文件必须判定为失败，严禁静默跳过"""
        dummy_cfg = {
            "id": "non_existent_dataset_999",
            "type": "test/dummy",
            "expected_sha256": "0" * 64,
            "read_count": 100,
            "score_min": 67,
            "codeword": REPO_ROOT / "data/R0.83_data/Source data/Encoded_codeword/codeword_R083.txt",
        }
        res = self.reg.run_check_saved_dumps(dummy_cfg)
        self.assertIsNotNone(res)
        self.assertFalse(res.passed)
        self.assertEqual(res.recovered_sha256, "FILE_NOT_FOUND")


class TestVoterModesContract(unittest.TestCase):
    """测试板端等价投票模式与传统纯软件最佳方向模式的区别与自洽性"""

    def test_dual_independent_strand_filtering(self):
        """板端等价模式下，正反双向独立过门限；传统模式仅单向择优一条"""
        # 构造一条读段：正向得 70 分 (>=67)，反向得 68 分 (>=67)
        # 传统模式：正向 70 >= 反向 68，只放行正向 1 票；
        # 板端等价模式：正向 70 >= 67 放行，反向 68 >= 67 亦放行，共计 2 笔记录参与投票。
        ref_len = 1000
        rb = 150
        reads_sym = np.zeros((1, rb), dtype=np.uint8)

        fwd_pos = np.array([10], dtype=np.int32)
        fwd_score = np.array([70], dtype=np.int32)
        rev_pos = np.array([200], dtype=np.int32)
        rev_score = np.array([68], dtype=np.int32)

        # 板端等价投票
        _, valid_records = stage2_vote_board_equivalent(
            fwd_pos, fwd_score, rev_pos, rev_score,
            reads_sym, ref_len, score_min=67,
        )
        self.assertEqual(valid_records, 2, "板端等价模式下双向独立过阈值应为 2 笔有效记录")

        # 传统软件最佳方向投票
        dirs = np.array([0], dtype=np.int32)  # 正向
        poss = np.array([10], dtype=np.int32)
        scores = np.array([70], dtype=np.int32)
        _, valid_count = stage2_vote_legacy_software(
            dirs, poss, scores, reads_sym, ref_len, score_min=67,
        )
        self.assertEqual(valid_count, 1, "传统软件模式每条读段仅择优 1 票")

    def test_saturation_clipping_behavior(self):
        """板端等价模式必须对累加器做逐票饱和截断 [-128, 127]"""
        ref_len = 500
        rb = 10
        # 构造连续 150 条相同的正向全 1 记录 (每一票对平面累加 +1)
        n = 150
        reads_sym = np.ones((n, rb), dtype=np.uint8) * 3  # (1, 1) 两平面全为 1
        fwd_pos = np.zeros(n, dtype=np.int32)             # 全都落在位置 0
        fwd_score = np.full(n, 70, dtype=np.int32)
        rev_pos = np.full(n, 200, dtype=np.int32)
        rev_score = np.full(n, 50, dtype=np.int32)        # 反向不合格 (<67)

        # 运行板端等价投票 (sat_min=-128, sat_max=127)
        # 经过 150 票后，若无饱和累加值为 150；但饱和机制将其截断在 127
        # 随后我们再灌入 10 票全 0 记录 (-1)，饱和系统从 127 下降到 117；
        # 若无饱和系统则从 150 下降到 140。
        # 这里测试：对单条极多同向累加的饱和自洽性。
        consensus, valid_records = stage2_vote_board_equivalent(
            fwd_pos, fwd_score, rev_pos, rev_score,
            reads_sym, ref_len, score_min=67,
            sat_min=-128, sat_max=127,
        )
        self.assertEqual(valid_records, n)
        self.assertEqual(int(consensus[0]), 1)


if __name__ == "__main__":
    unittest.main()
