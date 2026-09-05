#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""tools/stress_test_suite.py —— 全流程高强度、高质量、多变化自动化长时压测套件

功能：
1. 双规格（SE150 / SE250）自动化切换、烧录与就绪验证；
2. 边界探索：二分搜索/阶梯步进精确定位 SE150 与 SE250 各自的最低可恢复源读段数 N_min；
3. 多尺度长时高压测试：跨越小规模（N_min）、标准规模（2K~4K）、中规模（8K~16K）、
   大规模（32K）与全量极限规模（51.7K / 64.8K），覆盖多阈值与弄脏轮穿插；
4. 实时持久化留证：每轮更新 summary.md、results.jsonl 与 view.md 看板；
5. 支持长达数小时无人值守运行，具备超时防护、错误自愈与详尽统计。
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import time
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

# 路径配置
REPO_ROOT = Path(__file__).resolve().parent.parent
CLIENTS_PY = REPO_ROOT / "clients" / "python"
TOOLS_DIR = REPO_ROOT / "tools"
RES_DIR = CLIENTS_PY / "resources"

if str(CLIENTS_PY) not in sys.path:
    sys.path.insert(0, str(CLIENTS_PY))

import c_ldpc
from first import ClientConfig, run_client
from native_ldpc import bits_to_jpeg_bytes

GOLDEN_IMAGE_SHA256 = "fcd0cf90bd680e7bbdc203e3398119504da0897acac9e2117008b4efb6b1f2c3"

# 数据集路径
SE150_READS = REPO_ROOT / "data/R0.83_data/Sequencing data/DNA-40.5Kb-MC-SE150.fastq"
SE250_READS = REPO_ROOT / "data/R0.83_data/Sequencing data/DNA-40.5Kb-MC-SE250.fastq"
WATERMARK_FILE = REPO_ROOT / "data/R0.83_data/Source data/Watermark sequences/r0.83_watermark.txt"
GOLDEN_CODEWORD = REPO_ROOT / "data/R0.83_data/Source data/Encoded_codeword/codeword_R083.txt"

PCHK_PATH = RES_DIR / "dvb_s2_r5_6.pchk"
PERM_PATH = RES_DIR / "permutation64800"


@dataclass
class TestRecord:
    run_id: int
    timestamp: str
    mode: str                  # 'se250' or 'se150'
    read_count: int            # 源读段数
    record_count: int          # 发送记录数 (orient both)
    score_min: int
    tag: str                   # 'explore', 'stress', 'dirty', etc.
    total_time: float          # 秒
    board_result_time: float   # 硬件计算回传耗时
    raw_bit_errors: int        # 回传 64800 比特与 golden codeword 差异
    initial_syndromes: int     # 初始校验子不符数
    ldpc_iters: int            # 迭代轮数
    ldpc_time_ms: float        # LDPC 耗时
    image_sha256: str          # 还原图像 SHA-256
    recovered: bool            # 是否成功恢复目标图像
    notes: str = ""


class StressTestSuite:
    def __init__(
        self,
        board_ip: str = "192.168.1.10",
        board_port: int = 7,
        out_dir: Optional[Path] = None,
        duration_hours: float = 4.5,
    ):
        self.ip = board_ip
        self.port = board_port
        self.start_time = time.time()
        self.deadline = self.start_time + duration_hours * 3600.0
        self.duration_hours = duration_hours

        stamp = datetime.now().strftime("%Y%m%dT%H%M%S")
        self.out_dir = out_dir or (REPO_ROOT / "tests" / "stress_results" / f"stress_{stamp}")
        self.out_dir.mkdir(parents=True, exist_ok=True)

        self.jsonl_path = self.out_dir / "results.jsonl"
        self.summary_md_path = self.out_dir / "summary.md"
        self.current_run_id = 0
        self.records: List[TestRecord] = []

        # 加载黄金码字供误码比对
        self.golden_codeword_str = ""
        if GOLDEN_CODEWORD.exists():
            with open(GOLDEN_CODEWORD, "r") as f:
                self.golden_codeword_str = f.read().strip()

        print(f"[INIT] 压力测试套件已启动")
        print(f"  目标开发板: {self.ip}:{self.port}")
        print(f"  留证根目录: {self.out_dir}")
        print(f"  计划持续时间: {self.duration_hours:.1f} 小时 (截止: {datetime.fromtimestamp(self.deadline).strftime('%H:%M:%S')})")

    def update_view(self, doing: str, next_action: str = ""):
        """更新 view.md 看板"""
        try:
            cmd = [
                str(TOOLS_DIR / "agent_view.sh"),
                "update",
                "--agent", "stress-runner",
                "--doing", doing,
                "--why", "全流程高强度长时间多变化压测 (SE150/SE250 边界探索与长稳)",
                "--next", next_action or "继续执行下一项测试矩阵",
            ]
            subprocess.run(cmd, cwd=str(REPO_ROOT), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except Exception:
            pass

    def wait_board_ready(self, max_seconds: int = 60) -> bool:
        """探针检测板端是否响应 CAPS"""
        probe_script = TOOLS_DIR / "board" / "g3_wait_ready.py"
        cmd = [
            sys.executable,
            str(probe_script),
            "--ip", self.ip,
            "--port", str(self.port),
            "--deadline", str(max_seconds),
        ]
        rc = subprocess.run(cmd, cwd=str(REPO_ROOT), stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        return rc.returncode == 0

    def flash_mode(self, mode: str) -> bool:
        """一键切换并烧录指定模式 (se150 / se250)"""
        print(f"\n[FLASH] 开始切换并重新烧录板卡 -> {mode.upper()} ...")
        self.update_view(f"切换并烧录板卡 -> {mode.upper()}", "等待烧录完成并握手 CAPS")

        # 1. 切换导出制品与头文件
        sw_cmd = ["bash", str(TOOLS_DIR / "switch_export.sh"), mode]
        r1 = subprocess.run(sw_cmd, cwd=str(REPO_ROOT), stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        if r1.returncode != 0:
            print(f"[ERROR] switch_export.sh 失败:\n{r1.stderr}")
            return False

        # 2. 调用 run_g3.sh 执行烧录与初验
        read_bps = 150 if mode == "se150" else 250
        score_min = 67 if mode == "se150" else 112
        reads_file = SE150_READS if mode == "se150" else SE250_READS

        flash_cmd = [
            "bash", str(TOOLS_DIR / "run_g3.sh"),
            "--tag", f"stress-flash-{mode}",
            "--read-bps", str(read_bps),
            "--score-min", str(score_min),
            "--limit", "2048",
            "--reads", str(reads_file),
            "--skip-dump",
        ]
        # WSL 下调用 Windows xsdb 需重定向 stdin
        p = subprocess.Popen(
            flash_cmd,
            cwd=str(REPO_ROOT),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )
        out, _ = p.communicate()
        if p.returncode != 0:
            print(f"[ERROR] 烧录 {mode} 失败 (exit {p.returncode}):\n{out[-800:]}")
            return False

        print(f"[FLASH] ✓ 烧录与初验 {mode.upper()} 成功！板卡已就绪")
        return True

    def run_single(
        self,
        mode: str,
        reads_limit: int,
        score_min: int,
        tag: str = "stress",
        timeout: float = 300.0,
    ) -> TestRecord:
        """执行单次完整的 端到端测试 (上位机 -> FPGA -> 回传 -> C LDPC 译码 -> 比对)"""
        self.current_run_id += 1
        t_start = time.time()
        ts_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        reads_file = SE150_READS if mode == "se150" else SE250_READS
        read_bps = 150 if mode == "se150" else 250
        out_dec_path = self.out_dir / f"dec_run_{self.current_run_id:03d}_{mode}_{reads_limit}.txt"

        config = ClientConfig(
            ip=self.ip,
            port=self.port,
            watermark=WATERMARK_FILE,
            reads=reads_file,
            out=out_dec_path,
            send_limit=reads_limit,
            read_bps=read_bps,
            score_min=score_min,
            orient="both",
            result_timeout=timeout,
        )

        # 1. 运行网络客户端与 FPGA 交互
        board_time = 0.0
        try:
            stats = run_client(config, log=lambda m: None)
            board_time = getattr(stats, "t_result", 0.0)
        except Exception as e:
            total_t = time.time() - t_start
            rec = TestRecord(
                run_id=self.current_run_id,
                timestamp=ts_str,
                mode=mode,
                read_count=reads_limit,
                record_count=reads_limit * 2,
                score_min=score_min,
                tag=tag,
                total_time=total_t,
                board_result_time=board_time,
                raw_bit_errors=-1,
                initial_syndromes=-1,
                ldpc_iters=-1,
                ldpc_time_ms=0.0,
                image_sha256="N/A",
                recovered=False,
                notes=f"Client communication failed: {e}",
            )
            self._save_record(rec)
            return rec

        # 2. 读取回传比特串
        if not out_dec_path.exists():
            total_t = time.time() - t_start
            rec = TestRecord(
                run_id=self.current_run_id,
                timestamp=ts_str,
                mode=mode,
                read_count=reads_limit,
                record_count=reads_limit * 2,
                score_min=score_min,
                tag=tag,
                total_time=total_t,
                board_result_time=board_time,
                raw_bit_errors=-1,
                initial_syndromes=-1,
                ldpc_iters=-1,
                ldpc_time_ms=0.0,
                image_sha256="N/A",
                recovered=False,
                notes="Result file not generated",
            )
            self._save_record(rec)
            return rec

        with open(out_dec_path, "r") as f:
            raw_text = f.read().strip()

        # 计算与黄金码字的原始比特误码
        bit_errors = -1
        if self.golden_codeword_str and len(raw_text) == len(self.golden_codeword_str):
            bit_errors = sum(c1 != c2 for c1, c2 in zip(raw_text, self.golden_codeword_str))

        # 3. 极速 C LDPC 译码
        t_ldpc_start = time.time()
        rx_arr = np.frombuffer(raw_text.encode("ascii"), dtype=np.uint8) - ord("0")
        ldpc_recovered = False
        init_failed = -1
        iters = -1
        img_sha = "N/A"

        try:
            info_bits, init_failed, iters = c_ldpc.decode_bits_c(
                rx_arr, PCHK_PATH, PERM_PATH, max_iter=50, raise_on_error=False
            )
            ldpc_recovered = (info_bits is not None)
            if ldpc_recovered:
                jpg_bytes = bits_to_jpeg_bytes(info_bits)
                img_sha = hashlib.sha256(jpg_bytes).hexdigest()
        except Exception as e:
            ldpc_recovered = False

        ldpc_ms = (time.time() - t_ldpc_start) * 1000.0
        total_t = time.time() - t_start

        success = (ldpc_recovered and img_sha == GOLDEN_IMAGE_SHA256)
        notes = "OK" if success else ("LDPC decode unconverged" if not ldpc_recovered else "Hash mismatch")

        rec = TestRecord(
            run_id=self.current_run_id,
            timestamp=ts_str,
            mode=mode,
            read_count=reads_limit,
            record_count=reads_limit * 2,
            score_min=score_min,
            tag=tag,
            total_time=total_t,
            board_result_time=board_time,
            raw_bit_errors=bit_errors,
            initial_syndromes=init_failed,
            ldpc_iters=iters,
            ldpc_time_ms=ldpc_ms,
            image_sha256=img_sha,
            recovered=success,
            notes=notes,
        )
        self._save_record(rec)
        return rec

    def _save_record(self, rec: TestRecord):
        """记录并输出结果"""
        self.records.append(rec)
        with open(self.jsonl_path, "a") as f:
            f.write(json.dumps(asdict(rec)) + "\n")

        status_sym = "✅ PASS" if rec.recovered else "❌ FAIL"
        sha_short = rec.image_sha256[:8] if rec.image_sha256 != "N/A" else "------"
        print(
            f"[{rec.run_id:03d}][{rec.mode.upper()}][{rec.tag:7s}] 读段:{rec.read_count:5d}条({rec.record_count:6d}记) "
            f"分阈:{rec.score_min:3d} | 板耗:{rec.board_result_time:5.2f}s | "
            f"误码:{rec.raw_bit_errors:4d} 初始子:{rec.initial_syndromes:3d} 迭代:{rec.ldpc_iters:2d}轮({rec.ldpc_time_ms:4.1f}ms) | "
            f"{status_sym} SHA:{sha_short} ({rec.notes})"
        )

        self._render_markdown_summary()

    def _render_markdown_summary(self):
        """实时渲染 Markdown 汇总表"""
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        passed = sum(1 for r in self.records if r.recovered)
        total = len(self.records)

        # 统计 SE150 和 SE250 的成功记录
        succ_se150 = [r.read_count for r in self.records if r.mode == "se150" and r.recovered]
        succ_se250 = [r.read_count for r in self.records if r.mode == "se250" and r.recovered]

        min_se150 = min(succ_se150) if succ_se150 else "探索中"
        min_se250 = min(succ_se250) if succ_se250 else "探索中"

        lines = [
            f"# 自动化长时高压测试实时报告",
            f"",
            f"- **更新时间**：{now_str}",
            f"- **已完成轮次**：{total} 轮（成功 {passed} 轮，通过率 {passed/total*100:.1f}%）",
            f"- **SE150 最低可恢复源读段数 ($N_{{min}}$)**：**{min_se150}** 条",
            f"- **SE250 最低可恢复源读段数 ($N_{{min}}$)**：**{min_se250}** 条",
            f"- **计划运行时间**：{self.duration_hours:.1f} 小时",
            f"",
            f"## 最近 20 轮执行记录",
            f"",
            f"| 轮次 | 规格 | 标签 | 读段数 | 记录数 | 阈值 | 硬件耗时 | 初始校验子 | 迭代轮数 | 状态 | 图像 SHA-256 |",
            f"| :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |",
        ]

        for r in self.records[-20:]:
            st = "✅ PASS" if r.recovered else "❌ FAIL"
            sha = f"`{r.image_sha256[:8]}...`" if r.image_sha256 != "N/A" else "-"
            lines.append(
                f"| {r.run_id} | {r.mode.upper()} | {r.tag} | {r.read_count} | {r.record_count} | "
                f"{r.score_min} | {r.board_result_time:.2f}s | {r.initial_syndromes} | {r.ldpc_iters} | "
                f"{st} | {sha} |"
            )

        with open(self.summary_md_path, "w") as f:
            f.write("\n".join(lines) + "\n")

    def explore_boundary(self, mode: str, candidates: List[int], score_min: int) -> int:
        """阶梯式边界探索，寻找能够完整恢复的最少读段数"""
        print(f"\n========================================================")
        print(f"[{mode.upper()}] 开始探索最低恢复读段数 N_min (候选列表: {candidates})")
        print(f"========================================================")

        lowest_success = -1
        highest_fail = -1

        for n in candidates:
            if time.time() > self.deadline:
                break
            self.update_view(
                f"[{mode.upper()}] 边界探索: 测试源读段数 {n} 条",
                f"当前已知最高失败={highest_fail}, 最低成功={lowest_success}",
            )
            rec = self.run_single(mode, n, score_min, tag="explore")
            if rec.recovered:
                lowest_success = n
                break
            else:
                highest_fail = n

        # 二分细化
        if highest_fail > 0 and lowest_success > highest_fail:
            low = highest_fail
            high = lowest_success
            while high - low > 32 and time.time() < self.deadline:
                # 按 32 条对齐 (对应 64 条记录)
                mid = ((low + high) // 2 // 32) * 32
                if mid <= low or mid >= high:
                    break
                self.update_view(
                    f"[{mode.upper()}] 边界二分细化: 测试 {mid} 条",
                    f"区间 [{low}, {high}]",
                )
                rec = self.run_single(mode, mid, score_min, tag="binary")
                if rec.recovered:
                    high = mid
                    lowest_success = mid
                else:
                    low = mid
                    highest_fail = mid

        print(f"[{mode.upper()}] 边界探索完成！最低可恢复源读段数 N_min = {lowest_success} 条")
        return lowest_success

    def run_endurance_loop(self, mode: str, n_min: int, standard_score: int, max_runs: int = 15):
        """执行多尺度、长时间多变化连续压测"""
        print(f"\n========================================================")
        print(f"[{mode.upper()}] 开始多尺度长时间连续高压测试 (计划 {max_runs} 轮)")
        print(f"========================================================")

        full_reads = 51781 if mode == "se150" else 64800
        test_scales = [
            (n_min, standard_score, "n_min_stress"),
            (2048, standard_score, "std_2k"),
            (4096, standard_score, "med_4k"),
            (2048, standard_score - 10, "dirty_proof"),  # 弄脏轮自证
            (2048, standard_score, "clean_check"),
            (8192, standard_score, "large_8k"),
            (16384, standard_score, "xl_16k"),
            (4096, standard_score + 3, "tight_thresh"),
            (32768, standard_score, "huge_32k"),
            (full_reads, standard_score, "full_scale"),
        ]

        run_idx = 0
        scale_idx = 0
        while run_idx < max_runs and time.time() < self.deadline:
            n, sm, tag = test_scales[scale_idx % len(test_scales)]
            scale_idx += 1
            run_idx += 1
            self.update_view(
                f"[{mode.upper()}] 高压长跑 第 {run_idx}/{max_runs} 轮: {n} 条 (阈值 {sm})",
                f"剩余运行预算: {(self.deadline - time.time())/3600:.2f} 小时",
            )
            self.run_single(mode, n, sm, tag=tag)

    def run_full_suite(self):
        """执行完整四五个小时的全面测试流程"""
        print(f"\n>>> 启动全流程无人值守压力测试矩阵 <<<")

        # -------------------------------------------------------------
        # Phase 1: SE250 (板卡当前已运行 SE250，无需重复烧录)
        # -------------------------------------------------------------
        if not self.wait_board_ready(10):
            print("[WARN] 板端未响应，先执行一次初始烧录...")
            self.flash_mode("se250")

        # SE250 边界探索
        candidates_se250 = [768, 896, 1024, 1152, 1216, 1280, 1536, 2048]
        n_min_250 = self.explore_boundary("se250", candidates_se250, score_min=112)
        if n_min_250 <= 0:
            n_min_250 = 1216  # 保底默认

        # SE250 多尺度长跑压测
        self.run_endurance_loop("se250", n_min_250, standard_score=112, max_runs=15)

        # -------------------------------------------------------------
        # Phase 2: 切换到 SE150 并执行烧录与边界探索
        # -------------------------------------------------------------
        if time.time() < self.deadline:
            print(f"\n========================================================")
            print(f">>> 切换到 SE150 制品并重新烧录板卡 <<<")
            print(f"========================================================")
            if self.flash_mode("se150"):
                candidates_se150 = [384, 512, 640, 768, 896, 960, 1024, 1088, 1152, 1280, 1536, 2048]
                n_min_150 = self.explore_boundary("se150", candidates_se150, score_min=67)
                if n_min_150 <= 0:
                    n_min_150 = 1088  # 保底默认

                # SE150 多尺度长跑压测
                self.run_endurance_loop("se150", n_min_150, standard_score=67, max_runs=15)

        # -------------------------------------------------------------
        # Phase 3: 持续交替循环直至时间预算耗尽
        # -------------------------------------------------------------
        cycle = 0
        while time.time() < self.deadline:
            cycle += 1
            print(f"\n>>> 持续加压循环 Cycle {cycle} (剩余: {(self.deadline - time.time())/3600:.2f}h) <<<")
            # 运行一批随机尺度任务
            for n in [2048, 4096, 8192, 16384]:
                if time.time() > self.deadline:
                    break
                self.run_single("se150", n, 67, tag=f"cycle_{cycle}")

        print(f"\n========================================================")
        print(f"全部测试矩阵圆满完成！报告已生成: {self.summary_md_path}")
        print(f"========================================================")
        self.update_view("全流程长稳高压测试圆满完成", "导出最终测试分析图谱并归档")


def main():
    parser = argparse.ArgumentParser(description="DNA 读出系统高强度长时间自动化压测")
    parser.add_argument("--ip", default="192.168.1.10", help="开发板 IP")
    parser.add_argument("--port", type=int, default=7, help="开发板端口")
    parser.add_argument("--hours", type=float, default=4.5, help="总运行时长 (小时)")
    parser.add_argument("--out-dir", type=Path, default=None, help="输出目录")
    args = parser.parse_args()

    suite = StressTestSuite(
        board_ip=args.ip,
        board_port=args.port,
        out_dir=args.out_dir,
        duration_hours=args.hours,
    )
    suite.run_full_suite()


if __name__ == "__main__":
    main()
