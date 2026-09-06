#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""tests/host/test_benchmark_contract.py —— 基准测试与计时契约单元测试

落实 docs/15 §5 (任务 A) 要求：
1. 验证 CPU 优化 C 实现与 Python 参考模型在小型固定输入下返回完全相同的 best_pos, best_score 与 tie-break 规则；
2. 验证分型契约：无物理板卡/无功率计接入时，杜绝伪造 FPGA 实测与 reads/(s·W) 能效比；
3. 验证源读段 (N) 与板端记录数 (2N, orientation=both) 契约及延迟/吞吐换算；
4. 验证历史板测证据隔离与理论流水线估算隔离；
5. 验证 JSON 结构化落盘格式与计时重叠边界规范。
"""

import json
import shutil
import tempfile
import unittest
from pathlib import Path
from typing import Tuple

import numpy as np

import run_cpu_benchmark as rcb

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
DATA_DIR = REPO_ROOT / "data" / "R0.83_data"
SAMPLE_BOARD_LOG = REPO_ROOT / "docs" / "board" / "run-logs" / "20260904T104011Z-crossscale-runs3-summary.txt"


class TestCAlignVsPythonReference(unittest.TestCase):
    """验证 C 语言优化实现与 Python 纯算参考模型在位置、得分与并列仲裁上逐位一致"""

    def setUp(self):
        np.random.seed(20260906)

    def test_c_and_python_exact_matches_and_mutations(self):
        """小型合成序列：包含正向精准匹配、反向互补精准匹配、带突变模糊匹配与随机读段"""
        L = 600
        rb = 40
        ref = np.random.randint(0, 4, size=L, dtype=np.uint8)

        reads_list = []
        # 0. 正向精确匹配 (位置 120)
        reads_list.append(ref[120 : 120 + rb].copy())
        # 1. 反向互补精确匹配 (位置 250)
        rc_exact = (ref[250 : 250 + rb] ^ 1)[::-1].copy()
        reads_list.append(rc_exact)
        # 2. 正向 1 个突变 (位置 80)
        r_mut1 = ref[80 : 80 + rb].copy()
        r_mut1[10] = (r_mut1[10] + 1) % 4
        reads_list.append(r_mut1)
        # 3. 反向 3 个突变 (位置 340)
        rc_mut3 = (ref[340 : 340 + rb] ^ 1)[::-1].copy()
        rc_mut3[5] = (rc_mut3[5] + 1) % 4
        rc_mut3[15] = (rc_mut3[15] + 2) % 4
        rc_mut3[25] = (rc_mut3[25] + 3) % 4
        reads_list.append(rc_mut3)
        # 4-9. 随机噪声读段
        for _ in range(6):
            reads_list.append(np.random.randint(0, 4, size=rb, dtype=np.uint8))

        reads = np.array(reads_list, dtype=np.uint8)
        n = len(reads)

        # C 优化实现调用
        c_dir, c_pos, c_score = rcb.c_align_all(ref, reads, num_threads=1)

        # Python 参考模型逐条计算
        for i in range(n):
            py_dir, py_pos, py_score = rcb.py_align_brute_pair(ref, reads[i])
            self.assertEqual(
                int(c_dir[i]),
                py_dir,
                f"Read {i} 方向不一致: C={c_dir[i]} vs Py={py_dir}",
            )
            self.assertEqual(
                int(c_pos[i]),
                py_pos,
                f"Read {i} 位置不一致: C={c_pos[i]} vs Py={py_pos}",
            )
            self.assertEqual(
                int(c_score[i]),
                py_score,
                f"Read {i} 得分不一致: C={c_score[i]} vs Py={py_score}",
            )

        # 针对已知样本检查期望值
        self.assertEqual(int(c_pos[0]), 120)
        self.assertEqual(int(c_score[0]), rb)
        self.assertEqual(int(c_dir[0]), 0)

        self.assertEqual(int(c_pos[1]), 250)
        self.assertEqual(int(c_score[1]), rb)
        self.assertEqual(int(c_dir[1]), 1)

    def test_position_tie_break_smallest_index(self):
        """位置并列仲裁：多处最高得分相同时，C 与 Python 必须一致选择最小位置索引"""
        # 周期序列：[0, 1, 2, 3] 重复 20 次，长度 80
        ref = np.tile(np.array([0, 1, 2, 3], dtype=np.uint8), 20)
        # 读段：[0, 1, 2, 3]，在位置 0, 4, 8, 12, ... 均得满分 4
        read = np.array([[0, 1, 2, 3]], dtype=np.uint8)

        c_dir, c_pos, c_score = rcb.c_align_all(ref, read, num_threads=1)
        py_dir, py_pos, py_score = rcb.py_align_brute_pair(ref, read[0])

        self.assertEqual(int(c_pos[0]), 0, "C 实现未在并列时选择最小位置 0")
        self.assertEqual(py_pos, 0, "Python 模型未在并列时选择最小位置 0")
        self.assertEqual(int(c_score[0]), 4)
        self.assertEqual(py_score, 4)

    def test_orientation_tie_break_forward_preference(self):
        """方向并列仲裁：正反向最高得分完全相同时，C 与 Python 必须一致优先选择正向 (dir=0)"""
        # 构造一个使正向与反向互补在参考序列上最大得分严格相同的读段
        # 全同序列参考 ref = [1, 1, 1, 1, ...]，此时任何读段其正反向各位置匹配数可能不同；
        # 为确保并列，构造对称参考与读段：
        ref = np.array([0, 1, 2, 3, 3, 2, 1, 0, 0, 1, 2, 3], dtype=np.uint8)
        # 构造回文/反向互补对称读段或使得 s1 == s2
        # 若 read = [0, 1]，则 read^1 = [1, 0]，反序为 [0, 1]！
        # 即 read == (read^1)[::-1]，正向与反向互补完全同序同分！
        read = np.array([[0, 1]], dtype=np.uint8)
        self.assertTrue(np.array_equal(read[0], (read[0] ^ 1)[::-1]))

        c_dir, c_pos, c_score = rcb.c_align_all(ref, read, num_threads=1)
        py_dir, py_pos, py_score = rcb.py_align_brute_pair(ref, read[0])

        self.assertEqual(int(c_dir[0]), 0, "C 实现在正反同分时未优先选择正向 0")
        self.assertEqual(py_dir, 0, "Python 实现在正反同分时未优先选择正向 0")
        self.assertEqual(int(c_pos[0]), py_pos)
        self.assertEqual(int(c_score[0]), py_score)

    def test_c_multithread_consistency(self):
        """多线程一致性：1 线程、2 线程、4 线程计算结果必须 100% 逐条相同"""
        L = 800
        rb = 50
        n = 64
        ref = np.random.randint(0, 4, size=L, dtype=np.uint8)
        reads = np.random.randint(0, 4, size=(n, rb), dtype=np.uint8)

        dir_1t, pos_1t, score_1t = rcb.c_align_all(ref, reads, num_threads=1)
        dir_2t, pos_2t, score_2t = rcb.c_align_all(ref, reads, num_threads=2)
        dir_4t, pos_4t, score_4t = rcb.c_align_all(ref, reads, num_threads=4)

        np.testing.assert_array_equal(dir_1t, dir_2t)
        np.testing.assert_array_equal(dir_1t, dir_4t)
        np.testing.assert_array_equal(pos_1t, pos_2t)
        np.testing.assert_array_equal(pos_1t, pos_4t)
        np.testing.assert_array_equal(score_1t, score_2t)
        np.testing.assert_array_equal(score_1t, score_4t)


class TestBenchmarkContractAndTaxonomy(unittest.TestCase):
    """验证基准测试分型契约、无伪造实测、源读段与记录数定义及 JSON 格式"""

    def setUp(self):
        self.temp_dir = Path(tempfile.mkdtemp(prefix="test_bench_contract_"))

    def tearDown(self):
        if self.temp_dir.exists():
            shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_benchmark_clean_measured_only_contract(self):
        """在无历史板测输入、无估算开关时：仅生成 MEASURED 数据，绝不包含虚假 FPGA 实测与虚假能效"""
        # 使用小样本快速运行
        res = rcb.run_benchmark_suite(
            reads=64,
            probe=5,
            threads=[1, 2],
            modes=["SE150"],
            board_log_path=None,
            include_estimates=False,
            run_id="test_clean_run",
            outdir=self.temp_dir,
            repeats=1,
        )

        # 1. 顶层契约检查
        self.assertEqual(res["contract_version"], "1.0.0")
        self.assertIn("host_info", res)
        self.assertIn("model_name", res["host_info"])
        self.assertNotEqual(res["host_info"]["model_name"], "")

        # 2. 功耗契约检查：未接入外置功率计，严禁标称 2.5W 或真实能效比
        power_contract = res["power_contract"]
        self.assertFalse(power_contract["power_meter_connected"])
        self.assertEqual(power_contract["power_status"], "UNMEASURED")
        self.assertEqual(power_contract["power_w"], "N/A")
        self.assertEqual(power_contract["energy_efficiency"], "N/A")

        # 3. 数据集与记录数契约检查
        ds_contract = res["dataset_contract"]
        self.assertEqual(ds_contract["source_reads"], 64)
        self.assertEqual(ds_contract["orientation"], "both")
        self.assertEqual(ds_contract["evaluated_records"], 128)
        self.assertEqual(ds_contract["record_multiplier"], 2)

        # 4. 计时重叠边界检查
        overlap_info = res["timing_overlap_boundaries"]
        stages = [s["name"] for s in overlap_info["stages"]]
        self.assertIn("MM2S Upload", stages)
        self.assertIn("FPGA Accelerator Compute", stages)
        self.assertIn("S2MM Download", stages)
        self.assertIn("LDPC Software Decode", stages)
        self.assertIn("overlap_characteristics", overlap_info)

        # 5. 结果项检查：全部为 MEASURED，无伪造 FPGA 实测
        results = res["results"]
        self.assertGreater(len(results), 0)
        for r in results:
            self.assertEqual(r["category"], "MEASURED", "默认运行中混入了非 MEASURED 结果")
            self.assertEqual(r["source_reads"], 64)
            self.assertEqual(r["evaluated_records"], 128)
            # 功耗与能效比必须为未测量
            self.assertIn("UNMEASURED", str(r["power_w"]))
            self.assertIn("UNMEASURED", str(r["energy_efficiency"]))
            # 绝不得出现虚假硬编码 FPGA 耗时
            impl = r["implementation"]
            self.assertNotIn("FPGA 1-way 基线", impl)
            self.assertNotIn("FPGA 2-way 实测", impl)
            self.assertNotIn("FPGA 8-way 演进预期", impl)
            # 检查延迟与吞吐严格满足 2 倍关系 (records = 2 * source_reads)
            self.assertAlmostEqual(r["ms_per_source_read"], 2.0 * r["ms_per_record"], places=4)
            self.assertAlmostEqual(r["records_per_s"], 2.0 * r["source_reads_per_s"], places=4)

    def test_historical_board_data_segregation(self):
        """传入真实历史板测日志时：严格归入 [HISTORICAL] 分型，关联完整证据链，不参与跨分型能效虚标"""
        if not SAMPLE_BOARD_LOG.exists():
            self.skipTest(f"样例板测日志不存在: {SAMPLE_BOARD_LOG}")

        res = rcb.run_benchmark_suite(
            reads=64,
            probe=5,
            threads=[1],
            modes=["SE150"],
            board_log_path=SAMPLE_BOARD_LOG,
            include_estimates=False,
            run_id="test_hist_run",
            outdir=self.temp_dir,
            repeats=1,
        )

        results = res["results"]
        hist_rows = [r for r in results if r["category"] == "HISTORICAL"]
        self.assertEqual(len(hist_rows), 1, "未成功解析合入历史板测条目")

        h = hist_rows[0]
        self.assertEqual(h["category"], "HISTORICAL")
        self.assertEqual(h["platform"], "ZYNQ XC7Z010 (100MHz, Board Test)")
        # 证据检查
        evidence = h["evidence"]
        self.assertIn("run_id", evidence)
        self.assertIn("crossscale-runs3", evidence["run_id"])
        self.assertEqual(evidence["bitstream_sha256"], "7d12552a0df87bdeee75ebe6c4d58fa0ebadfa87001a5639db8b3d138b21f9d1")
        self.assertEqual(evidence["criterion_hash"], "fcd0cf90bd680e7bbdc203e3398119504da0897acac9e2117008b4efb6b1f2c3")
        # 功耗与加速比防混淆
        self.assertIn("UNMEASURED", str(h["power_w"]))
        self.assertEqual(h["speedup_vs_c1"], "N/A (跨分型不比)")

    def test_estimates_segregation_and_opt_in(self):
        """开启 --include-estimates 时：严格归入 [ESTIMATED] 分型，附带清晰模型说明，未开启时绝不呈现"""
        # 开启估算
        res_with_est = rcb.run_benchmark_suite(
            reads=64,
            probe=5,
            threads=[1],
            modes=["SE150"],
            board_log_path=None,
            include_estimates=True,
            run_id="test_est_run",
            outdir=self.temp_dir,
            repeats=1,
        )
        est_rows = [r for r in res_with_est["results"] if r["category"] == "ESTIMATED"]
        self.assertGreater(len(est_rows), 0, "开启估算后应包含 ESTIMATED 条目")
        for e in est_rows:
            self.assertIn("estimation_model", e)
            self.assertIn("理论推导", e["implementation"])
            self.assertEqual(e["speedup_vs_c1"], "N/A (跨分型不比)")
            self.assertIn("ESTIMATED", e["energy_efficiency"])

    def test_json_and_summary_files_created_in_target_dir(self):
        """验证结果文件精准落盘在指定目录，且符合预期 JSON Schema"""
        outdir = self.temp_dir / "custom_run"
        res = rcb.run_benchmark_suite(
            reads=32,
            probe=5,
            threads=[1],
            modes=["SE150"],
            board_log_path=None,
            include_estimates=False,
            run_id="custom_run",
            outdir=outdir,
            repeats=1,
        )

        json_file = outdir / "benchmark_result.json"
        md_file = outdir / "benchmark_summary.md"

        self.assertTrue(json_file.exists(), f"JSON 文件未落盘: {json_file}")
        self.assertTrue(md_file.exists(), f"Markdown 摘要未落盘: {md_file}")

        # 验证 JSON 可被正常反序列化
        loaded = json.loads(json_file.read_text(encoding="utf-8"))
        self.assertEqual(loaded["run_id"], "custom_run")
        self.assertEqual(len(loaded["results"]), len(res["results"]))


if __name__ == "__main__":
    unittest.main()
