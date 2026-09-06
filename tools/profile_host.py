#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""tools/profile_host.py —— 上位机性能瓶颈深度剖析与端到端拆解工具。

本工具用于深入剖析 DNA 数据读出上位机在真实数据集（如 SE150 4,096 条与全量）下的
端到端链路耗时拆解，明确各环节瓶颈与占比：
1. FASTQ 磁盘加载与碱基解析；
2. 碱基转 2-bit 位平面与 40B/64B 打包（基线纯 Python vs 向量化加速）；
3. 水印展开与载入；
4. 纯硬件加速器计算耗时（板端实测模型分离）；
5. 网络传输开销（基于千兆/百兆网口带宽模型）；
6. C LDPC 接口与格式转换。

输出控制台详尽表格与结构化 JSON，支持计算 p50/p95/min/mean 统计指标与加速比。
"""

from __future__ import annotations

import argparse
import json
import os
import platform
import struct
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

# 导入上位机模块
REPO_ROOT = Path(__file__).resolve().parent.parent
CLIENT_DIR = REPO_ROOT / "clients" / "python"
if str(CLIENT_DIR) not in sys.path:
    sys.path.insert(0, str(CLIENT_DIR))

import c_ldpc  # noqa: E402
import first  # noqa: E402
import ldpc_pipeline  # noqa: E402
import fast_readout as readout  # noqa: E402
from task_protocol import (  # noqa: E402
    FRAME_READS,
    MAX_TOTAL_READS,
    READ_BASES,
    TaskSpec,
    read_size_bytes,
)

# ==============================================================================
# 基线（未优化前）纯 Python 逻辑（用于严格对照评测与收益测量）
# ==============================================================================
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
) -> List[bytes]:
    batch: list = []
    batches: List[bytes] = []
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


# ==============================================================================
# 性能剖析核心函数
# ==============================================================================
def profile_watermark_stage(
    watermark_path: Path,
    task: TaskSpec,
    runs: int = 5,
) -> Dict[str, Any]:
    """剖析水印文件解析与打包耗时。"""
    # 1. 文本读取
    t_read_list = []
    for _ in range(runs):
        t0 = time.perf_counter()
        raw_text = watermark_path.read_text(encoding="utf-8")
        bits = first.parse_watermark_text(raw_text)
        t_read_list.append(time.perf_counter() - t0)

    # 2. 基线打包
    t_pack_legacy = []
    for _ in range(runs):
        t0 = time.perf_counter()
        legacy_pack_watermark_bits(bits, task)
        t_pack_legacy.append(time.perf_counter() - t0)

    # 3. 向量化打包
    t_pack_opt = []
    for _ in range(runs):
        t0 = time.perf_counter()
        readout.fast_pack_watermark_bits(bits, task)
        t_pack_opt.append(time.perf_counter() - t0)

    return {
        "watermark_bits": len(bits),
        "io_parse_sec": float(np.median(t_read_list)),
        "pack_legacy_sec": float(np.median(t_pack_legacy)),
        "pack_opt_sec": float(np.median(t_pack_opt)),
        "pack_speedup": float(np.median(t_pack_legacy) / max(1e-9, np.median(t_pack_opt))),
    }


def profile_reads_parsing_stage(
    reads_path: Path,
    source_reads: int,
    format_type: str = "auto",
    runs: int = 3,
) -> Dict[str, Any]:
    """剖析读段磁盘读取与文本解析耗时。"""
    # 1. 文件分析（统计总条数与读长探测）
    t_inspect_list = []
    for _ in range(runs):
        t0 = time.perf_counter()
        info = first.analyze_reads_file(reads_path, format_type)
        t_inspect_list.append(time.perf_counter() - t0)

    # 2. 传统行级读取 seqs
    t_seqs_legacy = []
    for _ in range(runs):
        t0 = time.perf_counter()
        seqs_leg = list(first.iter_source_seqs(reads_path, source_reads, format_type))
        t_seqs_legacy.append(time.perf_counter() - t0)

    # 3. 快速流式批量读取 seqs
    t_seqs_opt = []
    for _ in range(runs):
        t0 = time.perf_counter()
        seqs_opt = readout.fast_iter_source_seqs(reads_path, source_reads, format_type)
        t_seqs_opt.append(time.perf_counter() - t0)

    return {
        "file_bytes": reads_path.stat().st_size,
        "total_in_file": info.total_reads,
        "sampled_bps": info.detected_read_bps,
        "inspect_sec": float(np.median(t_inspect_list)),
        "read_seqs_legacy_sec": float(np.median(t_seqs_legacy)),
        "read_seqs_opt_sec": float(np.median(t_seqs_opt)),
        "seqs_speedup": float(np.median(t_seqs_legacy) / max(1e-9, np.median(t_seqs_opt))),
    }


def profile_batch_packing_stage(
    reads_path: Path,
    source_reads: int,
    send_total: int,
    batch_size: int,
    orient: str,
    read_bps: int,
    runs: int = 3,
) -> Dict[str, Any]:
    """剖析位平面转换、打包与批次序列化耗时（基线 vs 优化）。"""
    # 1. 基线（未优化）打包耗时
    t_legacy_list = []
    for _ in range(runs):
        t0 = time.perf_counter()
        batches_leg = legacy_iter_read_batches(
            reads_path, source_reads, send_total, batch_size, "auto", orient, read_bps
        )
        t_legacy_list.append(time.perf_counter() - t0)

    # 2. 优化（向量化）打包耗时
    t_opt_list = []
    for _ in range(runs):
        t0 = time.perf_counter()
        batches_opt = list(readout.fast_iter_read_batches(
            reads_path, source_reads, send_total, batch_size, "auto", orient, read_bps
        ))
        t_opt_list.append(time.perf_counter() - t0)

    # 3. 逐字节验证两者的输出完全一致
    assert len(batches_leg) == len(batches_opt), f"批次数不一致: {len(batches_leg)} vs {len(batches_opt)}"
    for idx, (b_leg, b_opt) in enumerate(zip(batches_leg, batches_opt)):
        assert b_leg == b_opt, f"批次 #{idx} 数据不一致"

    total_data_bytes = sum(len(b) for b in batches_opt)
    t_leg_med = float(np.median(t_legacy_list))
    t_opt_med = float(np.median(t_opt_list))

    records_count = source_reads * (2 if orient == "both" else 1)
    legacy_reads_per_sec = source_reads / max(1e-9, t_leg_med)
    opt_reads_per_sec = source_reads / max(1e-9, t_opt_med)

    return {
        "source_reads": source_reads,
        "records_count": records_count,
        "send_total": send_total,
        "batches_count": len(batches_opt),
        "total_data_bytes": total_data_bytes,
        "legacy_sec_p50": t_leg_med,
        "legacy_sec_p95": float(np.percentile(t_legacy_list, 95)),
        "opt_sec_p50": t_opt_med,
        "opt_sec_p95": float(np.percentile(t_opt_list, 95)),
        "speedup": t_leg_med / max(1e-9, t_opt_med),
        "legacy_reads_per_sec": legacy_reads_per_sec,
        "opt_reads_per_sec": opt_reads_per_sec,
        "legacy_records_per_sec": records_count / max(1e-9, t_leg_med),
        "opt_records_per_sec": records_count / max(1e-9, t_opt_med),
    }


def profile_ldpc_stage(
    golden_dec_path: Optional[Path] = None,
    runs: int = 10,
) -> Dict[str, Any]:
    """剖析结果展开、C LDPC 极速译码与图像保存耗时。"""
    c_avail = c_ldpc.is_c_accel_available()
    result: Dict[str, Any] = {
        "c_accel_available": c_avail,
        "unpack_legacy_sec": 0.0,
        "unpack_opt_sec": 0.0,
        "unpack_speedup": 0.0,
        "c_ldpc_decode_sec": 0.0,
        "iterations": 0,
        "initial_failed": 0,
    }

    # 1. 解包 8,100 字节为 64,800 比特
    dummy_payload = os.urandom(first.RESULT_BYTES)
    t_unp_leg = []
    for _ in range(runs):
        t0 = time.perf_counter()
        s_leg = legacy_unpack_result(dummy_payload)
        t_unp_leg.append(time.perf_counter() - t0)

    t_unp_opt = []
    for _ in range(runs):
        t0 = time.perf_counter()
        s_opt = readout.fast_unpack_result(dummy_payload)
        t_unp_opt.append(time.perf_counter() - t0)

    assert s_leg == s_opt, "结果解包不一致"
    result["unpack_legacy_sec"] = float(np.median(t_unp_leg))
    result["unpack_opt_sec"] = float(np.median(t_unp_opt))
    result["unpack_speedup"] = float(np.median(t_unp_leg) / max(1e-9, np.median(t_unp_opt)))

    # 2. C LDPC 译码
    if c_avail:
        pchk = ldpc_pipeline.resource_path(ldpc_pipeline.DECODER_PCHK)
        perm = ldpc_pipeline.resource_path(ldpc_pipeline.DECODER_PERM)

        if golden_dec_path and golden_dec_path.exists():
            raw_bits = golden_dec_path.read_text(encoding="utf-8").strip()
            rx = np.frombuffer(raw_bits.encode("ascii"), dtype=np.uint8) - ord("0")
        else:
            # 使用全 0 码字作为标准输入
            rx = np.zeros(64_800, dtype=np.uint8)

        t_ldpc_list = []
        last_failed = 0
        last_iters = 0
        for _ in range(runs):
            t0 = time.perf_counter()
            info, failed, iters = c_ldpc.decode_bits_c(rx, pchk, perm, max_iter=50)
            t_ldpc_list.append(time.perf_counter() - t0)
            last_failed = failed
            last_iters = iters

        result["c_ldpc_decode_sec"] = float(np.median(t_ldpc_list))
        result["c_ldpc_decode_p95"] = float(np.percentile(t_ldpc_list, 95))
        result["iterations"] = last_iters
        result["initial_failed"] = last_failed

    return result


def estimate_hw_and_network(
    send_total: int,
    total_bytes_sent: int,
    network_mbps: float = 100.0,
) -> Dict[str, Any]:
    """估算板端硬件计算耗时与网络传输耗时。

    硬件模型依据 docs/07-performance.md 与 first.py 实际板测事实：
      t_hw = 4.93s + 0.0009396s * records (SE150)
    网络带宽按 100 Mbps (约 11.5 MB/s 真实净荷吞吐) 测算。
    """
    t_hw_calc = first.estimate_processing_time(send_total // 2, orient="both")
    # 实际上传字节数 + 结果 8,100 字节下行
    net_bytes = total_bytes_sent + first.RESULT_BYTES
    net_speed_bytes_sec = (network_mbps * 1_000_000) / 8.0 * 0.85  # 考虑 TCP 开销与窗口
    t_net_transfer = net_bytes / net_speed_bytes_sec

    return {
        "network_bandwidth_nominal_mbps": network_mbps,
        "t_hw_compute_sec": t_hw_calc,
        "t_network_transfer_sec": t_net_transfer,
    }


def run_full_profiling(
    reads_path: Path,
    watermark_path: Path,
    limit: Optional[int] = None,
    read_bps: int = 150,
    batch_size: int = 1_000,
    orient: str = "both",
    runs: int = 3,
    golden_dec_path: Optional[Path] = None,
) -> Dict[str, Any]:
    """运行全流程端到端链路耗时拆解与对比剖析。"""
    t_start_global = time.perf_counter()

    # 1. 读段基本信息
    info = first.analyze_reads_file(reads_path)
    source_reads = limit if limit is not None else info.total_reads
    per_read = 2 if orient == "both" else 1
    send_total = first.round_up_frames(source_reads * per_read)

    # 2. 水印剖析
    task = TaskSpec.from_watermark_bits(
        81_000, total_reads=send_total, score_min=first.default_score_min(read_bps), read_bps=read_bps
    )
    wm_profile = profile_watermark_stage(watermark_path, task, runs=runs)

    # 3. 读段解析剖析
    parse_profile = profile_reads_parsing_stage(reads_path, source_reads, runs=runs)

    # 4. 位平面与打包剖析
    batch_profile = profile_batch_packing_stage(
        reads_path, source_reads, send_total, batch_size, orient, read_bps, runs=runs
    )

    # 5. LDPC 译码剖析
    ldpc_profile = profile_ldpc_stage(golden_dec_path, runs=runs)

    # 6. 硬件与网络模型
    hw_net = estimate_hw_and_network(
        send_total, batch_profile["total_data_bytes"], network_mbps=100.0
    )

    # 7. 端到端拆解与汇总
    t_host_legacy = (
        wm_profile["io_parse_sec"]
        + wm_profile["pack_legacy_sec"]
        + batch_profile["legacy_sec_p50"]
        + ldpc_profile["unpack_legacy_sec"]
        + ldpc_profile["c_ldpc_decode_sec"]
    )
    t_host_opt = (
        wm_profile["io_parse_sec"]
        + wm_profile["pack_opt_sec"]
        + batch_profile["opt_sec_p50"]
        + ldpc_profile["unpack_opt_sec"]
        + ldpc_profile["c_ldpc_decode_sec"]
    )

    t_e2e_legacy = t_host_legacy + hw_net["t_network_transfer_sec"] + hw_net["t_hw_compute_sec"]
    t_e2e_opt = t_host_opt + hw_net["t_network_transfer_sec"] + hw_net["t_hw_compute_sec"]

    report: Dict[str, Any] = {
        "metadata": {
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
            "host": platform.node(),
            "python_version": platform.python_version(),
            "reads_file": str(reads_path),
            "watermark_file": str(watermark_path),
            "source_reads": source_reads,
            "send_total": send_total,
            "read_bps": read_bps,
            "orient": orient,
            "batch_size": batch_size,
        },
        "watermark_stage": wm_profile,
        "fastq_parsing_stage": parse_profile,
        "batch_packing_stage": batch_profile,
        "ldpc_stage": ldpc_profile,
        "hw_and_network_estimates": hw_net,
        "summary": {
            "t_host_legacy_sec": t_host_legacy,
            "t_host_opt_sec": t_host_opt,
            "host_speedup": t_host_legacy / max(1e-9, t_host_opt),
            "t_e2e_legacy_sec": t_e2e_legacy,
            "t_e2e_opt_sec": t_e2e_opt,
            "e2e_speedup": t_e2e_legacy / max(1e-9, t_e2e_opt),
            "host_pct_in_legacy_e2e": (t_host_legacy / t_e2e_legacy) * 100.0,
            "host_pct_in_opt_e2e": (t_host_opt / t_e2e_opt) * 100.0,
            "hw_compute_pct_in_e2e": (hw_net["t_hw_compute_sec"] / t_e2e_opt) * 100.0,
            "network_pct_in_e2e": (hw_net["t_network_transfer_sec"] / t_e2e_opt) * 100.0,
        },
    }
    return report


def print_formatted_report(report: Dict[str, Any]) -> None:
    """打印清晰的控制台格式化表格。"""
    meta = report["metadata"]
    wm = report["watermark_stage"]
    bp = report["batch_packing_stage"]
    ldpc = report["ldpc_stage"]
    hn = report["hw_and_network_estimates"]
    sm = report["summary"]

    print("=" * 80)
    print("           上位机端到端链路性能剖析与瓶颈拆解报告 (HOST PROFILING)")
    print("=" * 80)
    print(f"数据源:    {meta['reads_file']}")
    print(f"读段规模:  源读段 {meta['source_reads']:,} 条 | 方向 {meta['orient']} | 发送 {meta['send_total']:,} 记录")
    print(f"数据几何:  {meta['read_bps']} bp | 批次大小: {meta['batch_size']}")
    print("-" * 80)

    print(f"{'环节名称':<28} | {'基线耗时 (Legacy)':<18} | {'优化耗时 (Opt)':<16} | {'加速比':<8}")
    print("-" * 80)
    print(
        f"{'1. 水印读取与校验':<28} | {wm['io_parse_sec']*1000:14.2f} ms | {wm['io_parse_sec']*1000:12.2f} ms | {'1.00x':<8}"
    )
    print(
        f"{'2. 水印位平面打包':<28} | {wm['pack_legacy_sec']*1000:14.2f} ms | {wm['pack_opt_sec']*1000:12.2f} ms | {wm['pack_speedup']:6.1f}x"
    )
    print(
        f"{'3. FASTQ 编码与批次序列化':<28} | {bp['legacy_sec_p50']*1000:14.2f} ms | {bp['opt_sec_p50']*1000:12.2f} ms | {bp['speedup']:6.1f}x"
    )
    print(
        f"{'4. 结果码字解包 (8.1KB)':<28} | {ldpc['unpack_legacy_sec']*1000:14.2f} ms | {ldpc['unpack_opt_sec']*1000:12.2f} ms | {ldpc['unpack_speedup']:6.1f}x"
    )
    print(
        f"{'5. C LDPC 极速译码核心':<28} | {ldpc['c_ldpc_decode_sec']*1000:14.2f} ms | {ldpc['c_ldpc_decode_sec']*1000:12.2f} ms | {'1.00x':<8}"
    )
    print("-" * 80)
    print(
        f"{'上位机纯处理总耗时 (Host Total)':<24} | {sm['t_host_legacy_sec']:14.4f}  s | {sm['t_host_opt_sec']:12.4f}  s | {sm['host_speedup']:6.1f}x"
    )
    print("-" * 80)

    print("\n【端到端各环节耗时占比 (优化后流水线)】:")
    t_opt_e2e = sm["t_e2e_opt_sec"]
    pct_host = (sm["t_host_opt_sec"] / t_opt_e2e) * 100.0
    pct_net = (hn["t_network_transfer_sec"] / t_opt_e2e) * 100.0
    pct_hw = (hn["t_hw_compute_sec"] / t_opt_e2e) * 100.0

    print(f"  * 上位机预处理与后处理: {sm['t_host_opt_sec']:8.4f} s ({pct_host:5.2f}%)")
    print(f"  * 网络传输 (100 Mbps):   {hn['t_network_transfer_sec']:8.4f} s ({pct_net:5.2f}%)")
    print(f"  * FPGA 硬件流水线计算:  {hn['t_hw_compute_sec']:8.4f} s ({pct_hw:5.2f}%) [主导耗时]")
    print(f"  * 端到端总计预估:        {t_opt_e2e:8.4f} s (100.00%)")

    print("\n【吞吐率对比】:")
    print(f"  * 基线编码吞吐: {bp['legacy_reads_per_sec']:,.1f} reads/s ({bp['legacy_records_per_sec']:,.1f} records/s)")
    print(f"  * 优化编码吞吐: {bp['opt_reads_per_sec']:,.1f} reads/s ({bp['opt_records_per_sec']:,.1f} records/s)")
    print(f"  * 吞吐提升幅度: {bp['speedup']:.2f} 倍")
    print("=" * 80)


def main() -> None:
    parser = argparse.ArgumentParser(description="Host Readout Performance Profiler")
    parser.add_argument(
        "--reads",
        type=Path,
        default=REPO_ROOT / "tests/datasets/D1_binary_pattern/reads_se150.fastq",
        help="读段文件路径 (FASTQ 或 plain)",
    )
    parser.add_argument(
        "--watermark",
        type=Path,
        default=REPO_ROOT / "tests/datasets/D1_binary_pattern/watermark.txt",
        help="水印文件路径",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="测试源读段条数 (默认全部，如 4096)",
    )
    parser.add_argument(
        "--read-bps",
        type=int,
        default=150,
        choices=[150, 250],
        help="读段长度 (150 或 250)",
    )
    parser.add_argument(
        "--batch",
        type=int,
        default=1_000,
        help="每批次记录数 (默认 1000)",
    )
    parser.add_argument(
        "--orient",
        type=str,
        default="both",
        choices=["both", "forward"],
        help="读段方向 (both 或 forward)",
    )
    parser.add_argument(
        "--runs",
        type=int,
        default=3,
        help="重复测试轮数 (用于取中位数)",
    )
    parser.add_argument(
        "--json-out",
        type=Path,
        default=None,
        help="输出 JSON 报告文件路径",
    )
    parser.add_argument(
        "--golden-dec",
        type=Path,
        default=REPO_ROOT / "tests/golden/dec_input.txt",
        help="用于测试 LDPC 译码的黄金码字文件",
    )

    args = parser.parse_args()

    if not args.reads.exists():
        print(f"[ERROR] 读段文件不存在: {args.reads}")
        sys.exit(1)
    if not args.watermark.exists():
        print(f"[ERROR] 水印文件不存在: {args.watermark}")
        sys.exit(1)

    print(f"[INFO] 开始性能剖析: reads={args.reads}, limit={args.limit}, runs={args.runs}...")
    report = run_full_profiling(
        reads_path=args.reads,
        watermark_path=args.watermark,
        limit=args.limit,
        read_bps=args.read_bps,
        batch_size=args.batch,
        orient=args.orient,
        runs=args.runs,
        golden_dec_path=args.golden_dec if args.golden_dec.exists() else None,
    )

    print_formatted_report(report)

    if args.json_out:
        args.json_out.parent.mkdir(parents=True, exist_ok=True)
        with args.json_out.open("w", encoding="utf-8") as fh:
            json.dump(report, fh, indent=2, ensure_ascii=False)
        print(f"[INFO] 剖析指标 JSON 已保存至: {args.json_out}")


if __name__ == "__main__":
    main()
