#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""tools/run_multi_payload_regression.py —— 多 Payload 独立泛化自动化回归测试套件

对齐 docs/13-final-delivery-roadmap.md G4 门禁：
  证明系统支持多种独立数据特征（文本、二值几何、稀疏跳变、高熵随机），
  彻底打破“数据单一性、重复测同一张图”的质疑。

支持模式：
  1. --mode golden (默认): 纯软件黄金模型流水线（秒级端到端自测，无需板卡）；
  2. --mode board --ip 192.168.1.10: 真实物理板卡交互测试；
  3. --mode check-dumps: 校验已保存在 tests/datasets/ 下的 board_output.bin 真实板测回传。
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

REPO_ROOT = Path(__file__).resolve().parent.parent
CLIENTS_PY = REPO_ROOT / "clients" / "python"
TOOLS_DIR = REPO_ROOT / "tools"
RES_DIR = CLIENTS_PY / "resources"
DATASETS_DIR = REPO_ROOT / "tests" / "datasets"

if str(CLIENTS_PY) not in sys.path:
    sys.path.insert(0, str(CLIENTS_PY))
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))

import c_ldpc
import protocol as pr
from first import ClientConfig, run_client
import readout as rd


def read_file_text(path: Path) -> str:
    return Path(path).read_text(encoding="utf-8").strip()

PCHK_PATH = RES_DIR / "dvb_s2_r5_6.pchk"
PERM_PATH = RES_DIR / "permutation64800"


@dataclass
class PayloadTestResult:
    dataset_id: str
    data_type: str
    original_size_bytes: int
    read_count: int
    raw_bit_errors: int
    initial_syndromes: int
    ldpc_iters: int
    recovered_sha256: str
    expected_sha256: str
    passed: bool
    elapsed_seconds: float
    notes: str = ""


class MultiPayloadRegression:
    def __init__(self, board_ip: str = "192.168.1.10", board_port: int = 7):
        self.ip = board_ip
        self.port = board_port
        self.results: List[PayloadTestResult] = []

    def get_dataset_configs(self) -> List[Dict[str, Any]]:
        """获取支持的全部 5 大独立 Payload 配置"""
        configs = [
            # D0 经典基准
            {
                "id": "D0_image_mandrill",
                "type": "image/jpeg",
                "tier": "D0",
                "manifest": None,
                "fastq": REPO_ROOT / "data/R0.83_data/Sequencing data/DNA-40.5Kb-MC-SE150.fastq",
                "watermark": REPO_ROOT / "data/R0.83_data/Source data/Watermark sequences/r0.83_watermark.txt",
                "codeword": REPO_ROOT / "data/R0.83_data/Source data/Encoded_codeword/codeword_R083.txt",
                "source_payload": None,
                "expected_sha256": "fcd0cf90bd680e7bbdc203e3398119504da0897acac9e2117008b4efb6b1f2c3",
                "read_count": 4096,
                "score_min": 67,
            },
            # D1 四大独立合成 Payload
            {
                "id": "D1_text_manifesto",
                "type": "text/ascii",
                "tier": "D1",
                "manifest": DATASETS_DIR / "D1_text_manifesto/manifest.json",
                "fastq": DATASETS_DIR / "D1_text_manifesto/reads_se150.fastq",
                "watermark": DATASETS_DIR / "D1_text_manifesto/watermark.txt",
                "codeword": DATASETS_DIR / "D1_text_manifesto/codeword.txt",
                "source_payload": DATASETS_DIR / "D1_text_manifesto/source_payload.bin",
                "expected_sha256": "101d89599e84011f30816dea901c43d96bd2a1654a5252dbf47e9c0cc8601ccf",
                "read_count": 4096,
                "score_min": 67,
            },
            {
                "id": "D1_binary_pattern",
                "type": "binary/geometric",
                "tier": "D1",
                "manifest": DATASETS_DIR / "D1_binary_pattern/manifest.json",
                "fastq": DATASETS_DIR / "D1_binary_pattern/reads_se150.fastq",
                "watermark": DATASETS_DIR / "D1_binary_pattern/watermark.txt",
                "codeword": DATASETS_DIR / "D1_binary_pattern/codeword.txt",
                "source_payload": DATASETS_DIR / "D1_binary_pattern/source_payload.bin",
                "expected_sha256": "034adb3c5096819e35dde255bcad95377f31f3fdcc7e27083ffe1ef0cdbe0525",
                "read_count": 4096,
                "score_min": 67,
            },
            {
                "id": "D1_structured_sparse",
                "type": "binary/sparse",
                "tier": "D1",
                "manifest": DATASETS_DIR / "D1_structured_sparse/manifest.json",
                "fastq": DATASETS_DIR / "D1_structured_sparse/reads_se150.fastq",
                "watermark": DATASETS_DIR / "D1_structured_sparse/watermark.txt",
                "codeword": DATASETS_DIR / "D1_structured_sparse/codeword.txt",
                "source_payload": DATASETS_DIR / "D1_structured_sparse/source_payload.bin",
                "expected_sha256": "831b499c0bf4dfd1ca70e89edd3412669ade6e213fe60b2f55d034c2b246486c",
                "read_count": 4096,
                "score_min": 67,
            },
            {
                "id": "D1_random_entropy",
                "type": "random/high_entropy",
                "tier": "D1",
                "manifest": DATASETS_DIR / "D1_random_entropy/manifest.json",
                "fastq": DATASETS_DIR / "D1_random_entropy/reads_se150.fastq",
                "watermark": DATASETS_DIR / "D1_random_entropy/watermark.txt",
                "codeword": DATASETS_DIR / "D1_random_entropy/codeword.txt",
                "source_payload": DATASETS_DIR / "D1_random_entropy/source_payload.bin",
                "expected_sha256": "d7cbdc06d173b6ec01b7fce8646249589e5f1611ca4fe0fedd25187af0cc7b5f",
                "read_count": 4096,
                "score_min": 60,
            },
        ]
        for c in configs:
            if c.get("manifest") and Path(c["manifest"]).exists():
                try:
                    mf_data = json.loads(Path(c["manifest"]).read_text(encoding="utf-8"))
                    c["expected_sha256"] = mf_data["payload"]["sha256"]
                except Exception:
                    pass
        return configs

    def decode_and_verify(
        self,
        rx_bits: np.ndarray,
        golden_codeword_str: str,
        expected_sha256: str,
        data_type: str,
        source_len: Optional[int] = None,
    ) -> Tuple[bool, int, int, int, str]:
        """对 64,800 位回传序列执行 LDPC 译码并验证哈希"""
        # 1. 码字误码比对
        golden_bits = np.array([int(c) for c in golden_codeword_str.strip()], dtype=np.uint8)
        raw_bit_errors = int(np.sum(rx_bits != golden_bits))

        # 2. LDPC 译码
        info_bits, init_failed, iters = c_ldpc.decode_bits_c(
            rx_bits, PCHK_PATH, PERM_PATH, max_iter=50, raise_on_error=False
        )

        if info_bits is None:
            return False, raw_bit_errors, init_failed, iters, "LDPC_DECODE_FAILED"

        # 3. 还原 Payload 字节流
        info_bytes = np.packbits(info_bits[:54000]).tobytes()
        if source_len is not None and source_len > 0:
            rec_bytes = info_bytes[:source_len]
        elif data_type == "image/jpeg":
            eoi = info_bytes.rfind(b"\xff\xd9")
            if eoi != -1:
                rec_bytes = info_bytes[: eoi + 2]
            else:
                rec_bytes = info_bytes
        else:
            rec_bytes = info_bytes

        rec_sha256 = hashlib.sha256(rec_bytes).hexdigest()
        passed = (rec_sha256.lower() == expected_sha256.lower())
        return passed, raw_bit_errors, init_failed, iters, rec_sha256

    def run_golden_mock(self, cfg: Dict[str, Any]) -> PayloadTestResult:
        """执行纯软件黄金模型流水线"""
        t0 = time.time()
        print(f"\n--- [GOLDEN] 运行数据集: {cfg['id']} ({cfg['type']}) ---")

        ref, wm_bits = rd.load_watermark(Path(cfg["watermark"]))
        golden_cw_text = read_file_text(cfg["codeword"])
        R = rd.load_reads(Path(cfg["fastq"]), limit=cfg["read_count"])
        n, rl = R.shape
        L = ref.size
        thr = cfg.get("score_min", 67)

        # Stage 1: 双向比对
        rd._init_worker(ref, rl)
        res = [rd._align_pair(R[i]) for i in range(n)]

        # Stage 2: 大数投票
        votes = np.zeros(2 * L, dtype=np.int32)
        for i, (d, p, s) in enumerate(res):
            if s < thr:
                continue
            a = R[i] if d == 0 else (R[i] ^ 1)[::-1]
            idx = np.arange(p, p + rl)
            np.add.at(votes, idx, ((a >> 1) & 1).astype(np.int32) * 2 - 1)
            np.add.at(votes, idx + L, (a & 1).astype(np.int32) * 2 - 1)

        # Stage 3: 差分 ⊕ 反稀疏化
        sparse = (votes > 0).astype(np.uint8) ^ wm_bits
        rx_bits = rd.desparsify(sparse)

        # LDPC 译码与核验
        source_len = cfg["source_payload"].stat().st_size if (cfg.get("source_payload") and cfg["source_payload"].exists()) else None
        passed, raw_errs, init_failed, iters, rec_sha = self.decode_and_verify(
            rx_bits, golden_cw_text, cfg["expected_sha256"], cfg["type"], source_len=source_len
        )
        elapsed = time.time() - t0

        print(f"  结果: 误码={raw_errs} bit, LDPC轮数={iters}, 匹配={passed}, 耗时={elapsed:.2f}s")
        return PayloadTestResult(
            dataset_id=cfg["id"],
            data_type=cfg["type"],
            original_size_bytes=len(rx_bits) // 8,
            read_count=len(R),
            raw_bit_errors=raw_errs,
            initial_syndromes=init_failed,
            ldpc_iters=iters,
            recovered_sha256=rec_sha,
            expected_sha256=cfg["expected_sha256"],
            passed=passed,
            elapsed_seconds=elapsed,
            notes="Golden pure software model",
        )

    def run_check_saved_dumps(self, cfg: Dict[str, Any]) -> Optional[PayloadTestResult]:
        """复查磁盘上保存的物理板测 DUMP 文件"""
        dump_path = DATASETS_DIR / cfg["id"] / "board_output.bin"
        if not dump_path.exists():
            return None

        t0 = time.time()
        print(f"\n--- [SAVED DUMP] 校验板测留证: {cfg['id']} ---")
        raw_bytes = dump_path.read_bytes()
        if len(raw_bytes) == 64800:
            if set(raw_bytes[:100]).issubset({ord('0'), ord('1')}):
                rx_bits = np.frombuffer(raw_bytes, dtype=np.uint8) - ord('0')
            else:
                rx_bits = np.frombuffer(raw_bytes, dtype=np.uint8)
        elif len(raw_bytes) == 8100:
            rx_bits = np.unpackbits(np.frombuffer(raw_bytes, dtype=np.uint8))
        else:
            print(f"  [ERROR] {dump_path} 长度为 {len(raw_bytes)} (期望 64800 或 8100 字节)")
            return None

        golden_cw_text = read_file_text(cfg["codeword"])
        source_len = cfg["source_payload"].stat().st_size if (cfg.get("source_payload") and cfg["source_payload"].exists()) else None

        passed, raw_errs, init_failed, iters, rec_sha = self.decode_and_verify(
            rx_bits, golden_cw_text, cfg["expected_sha256"], cfg["type"], source_len=source_len
        )
        elapsed = time.time() - t0

        print(f"  结果: 误码={raw_errs} bit, LDPC轮数={iters}, 匹配={passed}, 耗时={elapsed:.2f}s")
        return PayloadTestResult(
            dataset_id=cfg["id"],
            data_type=cfg["type"],
            original_size_bytes=8100,
            read_count=cfg["read_count"],
            raw_bit_errors=raw_errs,
            initial_syndromes=init_failed,
            ldpc_iters=iters,
            recovered_sha256=rec_sha,
            expected_sha256=cfg["expected_sha256"],
            passed=passed,
            elapsed_seconds=elapsed,
            notes="Physical board output verification",
        )

    def run_board_test(self, cfg: Dict[str, Any]) -> PayloadTestResult:
        """执行物理板端交互读出"""
        t0 = time.time()
        print(f"\n--- [BOARD] 板级上板实测: {cfg['id']} ({cfg['type']}) -> {self.ip}:{self.port} ---")

        client_cfg = ClientConfig(
            ip=self.ip,
            port=self.port,
            reads_file=str(cfg["fastq"]),
            limit_reads=cfg["read_count"],
            read_bps=150,
            score_min=cfg["score_min"],
            orient="both",
            preload_watermark=True,
            watermark_file=str(cfg["watermark"]),
            write_out=False,
            golden_check=False,
            output_file=None,
        )

        try:
            rx_arr, report = run_client(client_cfg)
        except Exception as e:
            print(f"  [ERROR] 板端通信异常: {e}")
            return PayloadTestResult(
                dataset_id=cfg["id"],
                data_type=cfg["type"],
                original_size_bytes=0,
                read_count=cfg["read_count"],
                raw_bit_errors=-1,
                initial_syndromes=-1,
                ldpc_iters=-1,
                recovered_sha256="COMM_ERROR",
                expected_sha256=cfg["expected_sha256"],
                passed=False,
                elapsed_seconds=time.time() - t0,
                notes=f"Communication error: {e}",
            )

        golden_cw_text = read_file_text(cfg["codeword"])
        passed, raw_errs, init_failed, iters, rec_sha = self.decode_and_verify(
            rx_arr, golden_cw_text, cfg["expected_sha256"], cfg["type"]
        )
        elapsed = time.time() - t0

        out_dump = DATASETS_DIR / cfg["id"] / "board_output.bin"
        if not out_dump.parent.exists():
            out_dump.parent.mkdir(parents=True, exist_ok=True)
        out_dump.write_bytes(np.packbits(rx_arr).tobytes())

        print(f"  结果: 误码={raw_errs} bit, LDPC轮数={iters}, 匹配={passed}, 耗时={elapsed:.2f}s")
        return PayloadTestResult(
            dataset_id=cfg["id"],
            data_type=cfg["type"],
            original_size_bytes=len(rx_arr) // 8,
            read_count=cfg["read_count"],
            raw_bit_errors=raw_errs,
            initial_syndromes=init_failed,
            ldpc_iters=iters,
            recovered_sha256=rec_sha,
            expected_sha256=cfg["expected_sha256"],
            passed=passed,
            elapsed_seconds=elapsed,
            notes="Live board execution",
        )

    def generate_report(self, report_path: Path):
        """生成 Markdown 格式的完整泛化验证报告"""
        lines = [
            "# 多 Payload 独立泛化回归测试报告",
            "",
            f"> 生成时间: {time.strftime('%Y-%m-%d %H:%M:%S')} CST",
            f"> 判定标准: LDPC 5/6 收敛且 SHA-256 与独立源文件逐位 100% 匹配",
            "",
            "## 1. 测试结果汇总",
            "",
            "| 数据集 ID | 数据类型 | 规模 | 误码 (bit) | 初始校验子 | LDPC 轮数 | 耗时 (s) | 最终哈希匹配 | 结论 |",
            "|---|---|---:|---:|---:|---:|---:|:---:|:---:|",
        ]

        total_pass = 0
        for r in self.results:
            status_icon = "✅ PASS" if r.passed else "❌ FAIL"
            if r.passed:
                total_pass += 1
            hash_match = "100% 吻合" if r.passed else "不匹配"
            lines.append(
                f"| `{r.dataset_id}` | {r.data_type} | {r.read_count} 条 | {r.raw_bit_errors} | "
                f"{r.initial_syndromes} | {r.ldpc_iters} | {r.elapsed_seconds:.2f}s | {hash_match} | {status_icon} |"
            )

        lines.extend([
            "",
            f"**总计通过率**: {total_pass} / {len(self.results)} ({total_pass/max(1, len(self.results))*100:.1f}%)",
            "",
            "## 2. 独立 Payload 详细哈希对照表",
            "",
            "| 数据集 ID | 期望 Payload SHA-256 | 还原结果 SHA-256 | 说明 |",
            "|---|---|---|---|",
        ])

        for r in self.results:
            lines.append(f"| `{r.dataset_id}` | `{r.expected_sha256}` | `{r.recovered_sha256}` | {r.notes} |")

        lines.append("")
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text("\n".join(lines), encoding="utf-8")
        print(f"\n[REPORT] 完整报告已生成至: {report_path}")


def main():
    parser = argparse.ArgumentParser(description="多 Payload 自动化泛化回归工具")
    parser.add_argument("--mode", choices=["golden", "board", "check-dumps"], default="golden", help="测试模式")
    parser.add_argument("--ip", default="192.168.1.10", help="开发板 IP")
    parser.add_argument("--port", type=int, default=7, help="开发板端口")
    parser.add_argument("--report", default=str(REPO_ROOT / "docs" / "multi_payload_regression_report.md"), help="报告输出路径")
    args = parser.parse_args()

    reg = MultiPayloadRegression(board_ip=args.ip, board_port=args.port)
    configs = reg.get_dataset_configs()

    print(f"=== 多 Payload 独立泛化回归测试启动 (模式: {args.mode.upper()}) ===")

    for cfg in configs:
        if args.mode == "golden":
            res = reg.run_golden_mock(cfg)
            reg.results.append(res)
        elif args.mode == "check-dumps":
            res = reg.run_check_saved_dumps(cfg)
            if res:
                reg.results.append(res)
        elif args.mode == "board":
            res = reg.run_board_test(cfg)
            reg.results.append(res)

    reg.generate_report(Path(args.report))

    all_passed = all(r.passed for r in reg.results)
    if all_passed:
        print("\n🎉 [ALL PASSED] 所有 Payload 均已成功通过全流程验证！")
        return 0
    else:
        print("\n⚠️ [FAILURE] 部分 Payload 验证未通过，请检查日志！")
        return 1


if __name__ == "__main__":
    sys.exit(main())
