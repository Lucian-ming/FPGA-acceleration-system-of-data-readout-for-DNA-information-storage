#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""tools/run_cpu_benchmark.py —— CPU vs FPGA 严格公平基准测试与计时契约评测

落实 docs/08-performance-and-strategy.md的公平基线与docs/05-implementation-plan.md的G1/G2:
1. 建立明确分型体系：
   - [MEASURED]  : 当前宿主机现场运行实测数据（CPU 单核/多核 OpenMP 实测，Python 抽样外推）；
   - [HISTORICAL]: 真实历史板测数据（严格关联 board log / run-id / bitstream 证据，无证据不呈现）；
   - [ESTIMATED] : 纯理论或流水线周期推导估算（显式标注 ESTIMATED，默认不混入实测）。
2. 杜绝虚假实测与伪造能效：
   - 彻底清除硬编码的 FPGA 耗时与功耗常量 (2.5W) 冒充实测行为；
   - 未连接物理板卡时不生成“FPGA 实测”；未接入硬件功率测试仪时功耗标为 "N/A (UNMEASURED)"，
     严禁虚构 reads/(s·W)。
3. 契约化数据集与记录数：
   - 显式区分 source_reads = N 与 orientation = both -> records = 2N；
   - 吞吐率与延迟同时明确标出每源读段 (per source read) 与每记录 (per record)。
4. 明确计时单位与重叠边界：
   - 区分秒 (s) 与毫秒 (ms)；分列展示 Python 抽样外推、CPU wall time、板端周期与端到端耗时；
   - 显式说明 MM2S 上传、硬件计算、S2MM 接收、LDPC 软件译码在流式/双缓冲下的重叠边界，说明不可简单相加。
5. 结构化 JSON 落盘：
   - 写入 logs/benchmarks/<run-id>/benchmark_result.json 与 benchmark_summary.md。
"""

from __future__ import annotations

import argparse
import ctypes
import datetime
import json
import math
import os
import platform
import re
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
from numpy.lib.stride_tricks import sliding_window_view as swv

REPO_ROOT = Path(__file__).resolve().parent.parent
TOOLS_DIR = REPO_ROOT / "tools"
DATA_DIR = REPO_ROOT / "data" / "R0.83_data"
LOGS_BASE_DIR = REPO_ROOT / "logs" / "benchmarks"

if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))

try:
    import golden_model as g
except ImportError:
    g = None

# ==============================================================================
# 契约常量与说明字典
# ==============================================================================
CONTRACT_VERSION = "1.0.0"

TAXONOMY_DEFINITIONS = {
    "MEASURED": (
        "Empirical measurements obtained on the current host machine during this benchmark run "
        "(e.g. CPU wall clock time, throughput)."
    ),
    "HISTORICAL": (
        "Verified board measurements from historical runs associated with concrete board log, "
        "run-id, bitstream SHA, and ELF SHA evidence."
    ),
    "ESTIMATED": (
        "Theoretical or derived performance estimates based on hardware clock frequency and "
        "pipeline stages, strictly excluding I/O, DMA, and protocol overhead."
    ),
}

TIMING_OVERLAP_BOUNDARIES = {
    "stages": [
        {
            "name": "MM2S Upload",
            "description": "Host memory to FPGA AXI DMA transfer of packed read data",
        },
        {
            "name": "FPGA Accelerator Compute",
            "description": (
                "Hardware pipeline: Stage1 Window Search -> Stage2 Differential Voter -> Stage3 Desparsify"
            ),
        },
        {
            "name": "S2MM Download",
            "description": "FPGA DDR/BRAM to Host memory AXI DMA transfer of voted/desparsified output",
        },
        {
            "name": "LDPC Software Decode",
            "description": "Host/PS CPU software LDPC belief propagation / bit-flipping decoder",
        },
    ],
    "overlap_characteristics": (
        "In a pipelined or double-buffered architecture, upload of batch k+1, FPGA computation of batch k, "
        "download of batch k-1, and LDPC decoding of batch k-2 can overlap in time. In a single-batch "
        "stop-and-wait execution, latencies occur sequentially (T_e2e = T_upload + T_hw + T_download + T_ldpc). "
        "Under streaming pipeline mode, overall throughput is bounded by the slowest bottleneck stage: "
        "max(T_upload, T_hw, T_download, T_ldpc). Individual stage durations cannot be directly summed "
        "to determine throughput without specifying the pipelining depth."
    ),
}

POWER_CONTRACT = {
    "power_meter_connected": False,
    "power_status": "UNMEASURED",
    "power_w": "N/A",
    "energy_efficiency": "N/A",
    "warning": (
        "No physical power meter attached. Fabricating power constants (e.g. ~2.5W or TDP formulas) "
        "or energy efficiency figures (reads/(s·W)) is strictly prohibited."
    ),
}


# ==============================================================================
# 系统信息采集
# ==============================================================================
def get_host_info() -> Dict[str, Any]:
    """采集当前宿主机 CPU 型号、架构与核数信息"""
    info = {
        "model_name": "Unknown CPU",
        "architecture": platform.machine(),
        "logical_cores": os.cpu_count() or 1,
        "physical_cores": None,
        "os": platform.system(),
        "platform_release": platform.release(),
    }
    cpuinfo_path = Path("/proc/cpuinfo")
    if cpuinfo_path.exists():
        try:
            core_ids = set()
            for line in cpuinfo_path.read_text(encoding="utf-8", errors="ignore").splitlines():
                if "model name" in line and info["model_name"] == "Unknown CPU":
                    info["model_name"] = line.split(":", 1)[1].strip()
                if "core id" in line:
                    core_ids.add(line.split(":", 1)[1].strip())
            if core_ids:
                info["physical_cores"] = len(core_ids)
        except Exception:
            pass
    if info["model_name"] == "Unknown CPU":
        info["model_name"] = platform.processor() or "Unknown CPU"
    return info


# ==============================================================================
# C 语言高性能滑窗比对动态库加载与调用
# ==============================================================================
_C_ALIGN_LIB = None


def get_c_aligner(lib_path: Optional[Path] = None):
    """加载 C 语言动态库，若不存在则现场编译"""
    global _C_ALIGN_LIB
    if _C_ALIGN_LIB is not None:
        return _C_ALIGN_LIB

    target_lib = lib_path or (TOOLS_DIR / "libalign_fast.so")
    if not target_lib.exists():
        src = TOOLS_DIR / "align_fast.c"
        if not src.exists():
            raise FileNotFoundError(f"C source file not found: {src}")
        cmd = [
            "gcc",
            "-O3",
            "-march=native",
            "-fopenmp",
            "-fPIC",
            "-shared",
            str(src),
            "-o",
            str(target_lib),
        ]
        res = subprocess.run(cmd, capture_output=True, text=True)
        if res.returncode != 0:
            raise RuntimeError(f"编译 {src} 失败:\n{res.stderr}")

    lib = ctypes.CDLL(str(target_lib))
    lib.align_reads_fast.argtypes = [
        ctypes.POINTER(ctypes.c_uint8),  # ref_sym
        ctypes.c_int,                    # L
        ctypes.POINTER(ctypes.c_uint8),  # reads_sym
        ctypes.c_int,                    # n
        ctypes.c_int,                    # rb
        ctypes.c_int,                    # num_threads
        ctypes.POINTER(ctypes.c_int),    # out_dir
        ctypes.POINTER(ctypes.c_int),    # out_pos
        ctypes.POINTER(ctypes.c_int),    # out_score
    ]
    lib.align_reads_fast.restype = None
    _C_ALIGN_LIB = lib
    return _C_ALIGN_LIB


def c_align_all(
    ref_sym: np.ndarray,
    reads_sym: np.ndarray,
    num_threads: int = 1,
    lib_path: Optional[Path] = None,
) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    """调用 C 动态库进行全量读段双向滑窗比对，返回 (out_dir, out_pos, out_score)"""
    lib = get_c_aligner(lib_path)
    n, rb = reads_sym.shape
    L = len(ref_sym)

    ref_ptr = np.ascontiguousarray(ref_sym, dtype=np.uint8).ctypes.data_as(ctypes.POINTER(ctypes.c_uint8))
    reads_ptr = np.ascontiguousarray(reads_sym, dtype=np.uint8).ctypes.data_as(ctypes.POINTER(ctypes.c_uint8))

    out_dir = np.empty(n, dtype=np.int32)
    out_pos = np.empty(n, dtype=np.int32)
    out_score = np.empty(n, dtype=np.int32)

    dir_ptr = out_dir.ctypes.data_as(ctypes.POINTER(ctypes.c_int))
    pos_ptr = out_pos.ctypes.data_as(ctypes.POINTER(ctypes.c_int))
    score_ptr = out_score.ctypes.data_as(ctypes.POINTER(ctypes.c_int))

    lib.align_reads_fast(ref_ptr, L, reads_ptr, n, rb, num_threads, dir_ptr, pos_ptr, score_ptr)
    return out_dir, out_pos, out_score


def run_c_benchmark_timing(
    ref_sym: np.ndarray,
    reads_sym: np.ndarray,
    threads: int,
    repeats: int = 3,
    warmup: int = 1,
    lib_path: Optional[Path] = None,
) -> Tuple[float, float, float, np.ndarray, np.ndarray, np.ndarray]:
    """运行 C 优化版本评测，包含预热与多次重复取中位数。
    返回: (median_wall_time_s, min_s, max_s, out_dir, out_pos, out_score)
    """
    for _ in range(warmup):
        c_align_all(ref_sym, reads_sym, num_threads=threads, lib_path=lib_path)

    durations: List[float] = []
    last_res = None
    for _ in range(repeats):
        t0 = time.perf_counter()
        last_res = c_align_all(ref_sym, reads_sym, num_threads=threads, lib_path=lib_path)
        dt = time.perf_counter() - t0
        durations.append(dt)

    med_dt = float(np.median(durations))
    min_dt = float(np.min(durations))
    max_dt = float(np.max(durations))
    out_dir, out_pos, out_score = last_res
    return med_dt, min_dt, max_dt, out_dir, out_pos, out_score


# 保持向后兼容辅助函数
def compile_align_omp(rb: int, out_bin: Path) -> bool:
    """编译高度优化的独立 C OpenMP 可执行程序（兼容旧版测试）"""
    src = TOOLS_DIR / "align_omp.c"
    cmd = [
        "gcc",
        "-O3",
        "-march=native",
        "-fopenmp",
        f"-DRB={rb}",
        str(src),
        "-o",
        str(out_bin),
    ]
    res = subprocess.run(cmd, capture_output=True, text=True)
    if res.returncode != 0:
        print(f"[ERROR] 编译 {src} (RB={rb}) 失败:\n{res.stderr}")
        return False
    return True


def run_c_bench_binary(bin_path: Path, ref_bin: Path, reads_bin: Path, n_reads: int, threads: int) -> Tuple[float, float]:
    """运行独立的 C 可执行程序，返回 (耗时_s, 吞吐_条每秒)"""
    cmd = [str(bin_path), str(ref_bin), str(reads_bin), str(n_reads), str(threads)]
    t0 = time.perf_counter()
    res = subprocess.run(cmd, capture_output=True, text=True)
    dt = time.perf_counter() - t0
    if res.returncode != 0:
        raise RuntimeError(f"运行 C benchmark 失败:\n{res.stderr}")

    throughput = n_reads / dt
    for line in res.stdout.splitlines():
        if "吞吐:" in line:
            parts = line.split("|")
            for p in parts:
                if "吞吐:" in p:
                    tp_str = p.split("吞吐:")[1].strip().split("条/s")[0].strip()
                    throughput = float(tp_str)
                if "耗时:" in p:
                    dt_str = p.split("耗时:")[1].strip().split("s")[0].strip()
                    dt = float(dt_str)
    return dt, throughput


# ==============================================================================
# Python 参考模型（精确滑动比对与抽样评测）
# ==============================================================================
def py_align_brute_one(ref: np.ndarray, r: np.ndarray) -> Tuple[int, int]:
    """Python 逐位置完全匹配比对（单条单向），并列时选最小位置索引"""
    rb = len(r)
    max_p = len(ref) - rb
    best_score = -1
    best_pos = 0
    for p in range(max_p + 1):
        score = int(np.sum(ref[p : p + rb] == r))
        if score > best_score:
            best_score = score
            best_pos = p
    return best_pos, best_score


def py_align_brute_pair(ref: np.ndarray, read: np.ndarray) -> Tuple[int, int, int]:
    """Python 读段正反双向比对，并列时优先选择正向 (0)"""
    rc = (read ^ 1)[::-1]
    p1, s1 = py_align_brute_one(ref, read)
    p2, s2 = py_align_brute_one(ref, rc)
    if s1 >= s2:
        return 0, p1, s1
    else:
        return 1, p2, s2


def run_python_bench(
    ref_sym: np.ndarray,
    reads_sym: np.ndarray,
    n_probe: int,
    rb: int,
) -> Tuple[float, float]:
    """运行 Python Numpy 暴力滑窗与 FFT 相关测试（抽样 n_probe 条估算每条耗时）
    返回: (t_brute_per_source_read, t_fft_per_source_read)
    """
    R = reads_sym[:n_probe]
    RC = (R ^ 1)[:, ::-1]

    # 1. 暴力滑窗
    W = swv(ref_sym, rb)
    t0 = time.perf_counter()
    for i in range(n_probe):
        s1 = (W == R[i]).sum(axis=1)
        s2 = (W == RC[i]).sum(axis=1)
        _ = int(np.argmax(s1) if s1.max() >= s2.max() else np.argmax(s2))
    t_brute = (time.perf_counter() - t0) / n_probe

    # 2. FFT 相关
    if g is not None:
        size, spec = g.make_ref_spectrum(ref_sym, rb)
        t0 = time.perf_counter()
        for i in range(n_probe):
            g.align_read(R[i], size, spec, ref_sym.size - rb)
            g.align_read(RC[i], size, spec, ref_sym.size - rb)
        t_fft = (time.perf_counter() - t0) / n_probe
    else:
        t_fft = t_brute

    return t_brute, t_fft


# ==============================================================================
# 数据集读取与准备
# ==============================================================================
def prepare_dataset(reads_path: Path, n_reads: int, rb: int) -> Tuple[np.ndarray, np.ndarray]:
    """从 FASTQ 和水印序列读取并转换为 uint8 符号矩阵"""
    if g is None:
        raise RuntimeError("golden_model module not available")
    wm_path = DATA_DIR / "Source data" / "Watermark sequences" / "r0.83_watermark.txt"
    if not wm_path.exists():
        raise FileNotFoundError(f"Watermark file not found: {wm_path}")
    wm = g.read_bits(wm_path)
    ref = g.planes_to_symbols(wm)

    if not reads_path.exists():
        raise FileNotFoundError(f"Reads file not found: {reads_path}")
    reads = [s.upper() for s in g.iter_fastq(reads_path, n_reads)]
    if len(reads) != n_reads:
        raise ValueError(f"FASTQ 记录不足：要求 {n_reads} 条，实际读取 {len(reads)} 条 ({reads_path})")
    invalid = [i for i, read in enumerate(reads) if len(read) != rb]
    if invalid:
        raise ValueError(f"FASTQ 读长与 {rb} bp 模式不符，首个错误记录索引 {invalid[0]} ({reads_path})")
    R = np.array([[g.BASE2VAL.get(c, 0) for c in s] for s in reads], dtype=np.uint8)
    return ref, R


# ==============================================================================
# 历史板测数据解析器 (HISTORICAL)
# ==============================================================================
def parse_board_log(log_path: Path) -> Optional[Dict[str, Any]]:
    """解析真实板测 summary 或 log 文件，提取历史板测证据与耗时数据。
    若无有效证据则返回 None。
    """
    if not log_path.exists():
        return None

    content = log_path.read_text(encoding="utf-8", errors="ignore")
    run_id = None
    bitstream = None
    elf = None
    criterion_hash = None
    source_reads = None
    records = None
    elapsed_s = None

    for line in content.splitlines():
        line_str = line.strip()
        if "run=" in line_str and not run_id:
            run_id = line_str.split("run=")[1].split()[0].strip()
        if "bitstream" in line_str and ":" in line_str and not bitstream:
            bitstream = line_str.split(":", 1)[1].strip()
        if "ELF" in line_str and ":" in line_str and not elf:
            elf = line_str.split(":", 1)[1].strip()
        if "判据哈希" in line_str and ":" in line_str and not criterion_hash:
            criterion_hash = line_str.split(":", 1)[1].strip()
        # Result 行含有 "bytes"，不能通过找任意字母 s 来猜耗时字段。
        result_match = re.search(
            r"Result:\s*[0-9,]+\s+bytes,\s*([0-9]+(?:\.[0-9]+)?)s(?=,|\s|$)",
            line_str,
        )
        if result_match:
            elapsed_s = float(result_match.group(1))

        # orientation=both 的板测记录数必须是源读段数的两倍；接受数字与“条记录”间的空格。
        records_match = re.search(r"([0-9][0-9,]*)\s*条记录", line_str)
        if records_match:
            parsed_records = int(records_match.group(1).replace(",", ""))
            records = parsed_records
            source_reads = parsed_records // 2 if parsed_records % 2 == 0 else None

    if not run_id:
        run_id = log_path.stem
    # 缺失或无效的测量字段不能用“典型值”补齐后冒充历史实测。
    if (
        source_reads is None
        or records is None
        or elapsed_s is None
        or source_reads <= 0
        or records <= 0
        or elapsed_s <= 0
        or not math.isfinite(elapsed_s)
    ):
        return None

    throughput_source = source_reads / elapsed_s if elapsed_s > 0 else 0.0
    throughput_records = records / elapsed_s if elapsed_s > 0 else 0.0

    return {
        "mode": "SE150",
        "category": "HISTORICAL",
        "platform": "ZYNQ XC7Z010 (100MHz, Board Test)",
        "implementation": "FPGA 2-way + PS lwIP TCP 端到端板测",
        "measurement_method": "真实物理板端以太网端到端回传耗时",
        "threads": 1,
        "source_reads": source_reads,
        "evaluated_records": records,
        "wall_time_s": elapsed_s,
        "ms_per_source_read": (elapsed_s * 1000.0) / source_reads,
        "ms_per_record": (elapsed_s * 1000.0) / records,
        "source_reads_per_s": throughput_source,
        "records_per_s": throughput_records,
        "power_w": "N/A (UNMEASURED)",
        "energy_efficiency": "N/A (UNMEASURED)",
        "evidence": {
            "log_file": str(log_path),
            "run_id": run_id,
            "bitstream_sha256": bitstream or "UNSPECIFIED",
            "elf_sha256": elf or "UNSPECIFIED",
            "criterion_hash": criterion_hash or "UNSPECIFIED",
        },
        "note": (
            "真实板测日志记录包含 PS lwIP TCP 上传、硬件计算、DDR 回写与回传整体验证耗时；"
            "未接入外置功率测试仪，功耗记录为 UNMEASURED。"
        ),
    }


# ==============================================================================
# 理论流水线周期估算生成器 (ESTIMATED)
# ==============================================================================
def get_theoretical_estimates(mode_name: str, rb: int, n_reads: int) -> List[Dict[str, Any]]:
    """生成硬件流水线理论周期推导条目。仅在显式请求 --include-estimates 时呈现。"""
    n_records = n_reads * 2
    # 纯硬件流水线推导参数：
    # 100MHz 频率，时钟周期 10ns
    # 1-way: ~94,000 cycles/record -> 0.940 ms/record -> 1.880 ms/source_read
    # 2-way: ~47,000 cycles/record -> 0.470 ms/record -> 0.940 ms/source_read
    # 8-way: ~11,750 cycles/record -> 0.118 ms/record -> 0.235 ms/source_read
    if rb == 250:
        base_ms_per_record = 1.580
    else:
        base_ms_per_record = 0.940

    estimates = []
    configs = [
        ("FPGA 1-way (纯硬件流水线周期理论推导)", 1.0, "ZYNQ XC7Z010 (100MHz)"),
        ("FPGA 2-way (纯硬件流水线周期理论推导)", 2.0, "ZYNQ XC7Z010 (100MHz)"),
        ("FPGA 8-way (面向高规格器件展开理论推导)", 8.0, "ZYNQ XC7Z020 (100MHz)"),
    ]

    for impl_name, ways, plat_name in configs:
        ms_record = base_ms_per_record / ways
        ms_source = ms_record * 2.0
        sec_total = (ms_source * n_reads) / 1000.0
        tp_source = 1000.0 / ms_source
        tp_record = 1000.0 / ms_record

        estimates.append({
            "mode": mode_name,
            "category": "ESTIMATED",
            "platform": plat_name,
            "implementation": impl_name,
            "measurement_method": "理论时钟周期推导 (100MHz 纯硬件流水线)",
            "threads": 1,
            "source_reads": n_reads,
            "evaluated_records": n_records,
            "wall_time_s": sec_total,
            "ms_per_source_read": ms_source,
            "ms_per_record": ms_record,
            "source_reads_per_s": tp_source,
            "records_per_s": tp_record,
            "power_w": "N/A (UNMEASURED)",
            "energy_efficiency": "N/A (ESTIMATED)",
            "estimation_model": (
                f"基于 100MHz 硬件时钟与 {ways:.0f}-way 滑窗展开流水线拍数纯理论推导；"
                "严格未计入 DMA 传输、以太网通信与 LDPC 译码耗时，不代表端到端实测性能。"
            ),
        })
    return estimates


# ==============================================================================
# 基准测试主执行逻辑
# ==============================================================================
def run_benchmark_suite(
    reads: int = 4096,
    probe: int = 20,
    threads: Optional[List[int]] = None,
    modes: Optional[List[str]] = None,
    board_log_path: Optional[Path] = None,
    include_estimates: bool = False,
    run_id: Optional[str] = None,
    outdir: Optional[Path] = None,
    fastq_overrides: Optional[Dict[str, Path]] = None,
    repeats: int = 3,
) -> Dict[str, Any]:
    """执行基准测试套件，返回完整结构化结果字典"""
    if threads is None:
        threads = [1, 2, 4, 8, 16]
    if modes is None:
        modes = ["SE150", "SE250"]

    if reads <= 0 or probe <= 0 or repeats <= 0:
        raise ValueError("reads、probe、repeats 都必须是正整数")
    if not threads or any(thread <= 0 for thread in threads):
        raise ValueError("threads 必须包含至少一个正整数")

    test_configs = {
        "SE150": (150, DATA_DIR / "Sequencing data" / "DNA-40.5Kb-MC-SE150.fastq"),
        "SE250": (250, DATA_DIR / "Sequencing data" / "DNA-40.5Kb-MC-SE250.fastq"),
    }
    if fastq_overrides:
        for k, v in fastq_overrides.items():
            if k in test_configs:
                test_configs[k] = (test_configs[k][0], v)
    unknown_modes = [mode for mode in modes if mode not in test_configs]
    if unknown_modes:
        raise ValueError(f"未知 mode: {', '.join(unknown_modes)}；支持 SE150、SE250")

    if not run_id:
        timestamp_str = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        run_id = f"bench_{timestamp_str}"

    output_dir = outdir or (LOGS_BASE_DIR / run_id)
    output_dir.mkdir(parents=True, exist_ok=True)

    host_info = get_host_info()

    all_results: List[Dict[str, Any]] = []
    errors: List[str] = []

    for mode_name in modes:
        rb, fastq_path = test_configs[mode_name]
        if not fastq_path.exists():
            message = f"数据集文件未找到: {fastq_path}，无法测量 {mode_name}"
            errors.append(message)
            print(f"[FAIL] {message}")
            continue

        print(f"\n>>> 正在加载数据集 {mode_name} (读长: {rb} bp, 源读段数: {reads} 条) ...")
        ref_sym, reads_sym = prepare_dataset(fastq_path, reads, rb)
        n_records = reads * 2

        # ----------------------------------------------------------------------
        # 1. Python 性能测试 [MEASURED] (抽样外推)
        # ----------------------------------------------------------------------
        print(f"  正在执行 Python Numpy 抽样外推测试 (probe={probe} 条) ...")
        t_brute_per_read, t_fft_per_read = run_python_bench(ref_sym, reads_sym, probe, rb)

        all_results.append({
            "mode": mode_name,
            "category": "MEASURED",
            "platform": f"Host CPU ({host_info['model_name']})",
            "implementation": "Python (Numpy 暴力滑窗)",
            "measurement_method": f"Python 抽样外推 (Sampling Extrapolation, N_probe={probe})",
            "threads": 1,
            "source_reads": reads,
            "evaluated_records": n_records,
            "wall_time_s": t_brute_per_read * reads,
            "ms_per_source_read": t_brute_per_read * 1000.0,
            "ms_per_record": (t_brute_per_read * 1000.0) / 2.0,
            "source_reads_per_s": 1.0 / t_brute_per_read,
            "records_per_s": 2.0 / t_brute_per_read,
            "power_w": "N/A (UNMEASURED)",
            "energy_efficiency": "N/A (UNMEASURED)",
        })

        all_results.append({
            "mode": mode_name,
            "category": "MEASURED",
            "platform": f"Host CPU ({host_info['model_name']})",
            "implementation": "Python (FFT 频域相关)",
            "measurement_method": f"Python 抽样外推 (Sampling Extrapolation, N_probe={probe})",
            "threads": 1,
            "source_reads": reads,
            "evaluated_records": n_records,
            "wall_time_s": t_fft_per_read * reads,
            "ms_per_source_read": t_fft_per_read * 1000.0,
            "ms_per_record": (t_fft_per_read * 1000.0) / 2.0,
            "source_reads_per_s": 1.0 / t_fft_per_read,
            "records_per_s": 2.0 / t_fft_per_read,
            "power_w": "N/A (UNMEASURED)",
            "energy_efficiency": "N/A (UNMEASURED)",
        })

        # ----------------------------------------------------------------------
        # 2. CPU C 优化实现 [MEASURED] (多线程实测)
        # ----------------------------------------------------------------------
        for th in threads:
            print(f"  正在执行 C 语言优化版本实测 (OpenMP {th:2d} 线程, 重复 {repeats} 次) ...")
            med_dt, min_dt, max_dt, _, _, _ = run_c_benchmark_timing(
                ref_sym, reads_sym, threads=th, repeats=repeats, warmup=1
            )
            tp_source = reads / med_dt
            tp_record = n_records / med_dt
            ms_source = (med_dt * 1000.0) / reads
            ms_record = (med_dt * 1000.0) / n_records

            all_results.append({
                "mode": mode_name,
                "category": "MEASURED",
                "platform": f"Host CPU ({host_info['model_name']})",
                "implementation": f"C (-O3 Bitwise + Popcount, OpenMP {th}T)",
                "measurement_method": f"C Wall Time 全量实测 (Repeats={repeats}, N={reads})",
                "threads": th,
                "source_reads": reads,
                "evaluated_records": n_records,
                "wall_time_s": med_dt,
                "wall_time_min_s": min_dt,
                "wall_time_max_s": max_dt,
                "ms_per_source_read": ms_source,
                "ms_per_record": ms_record,
                "source_reads_per_s": tp_source,
                "records_per_s": tp_record,
                "power_w": "N/A (UNMEASURED)",
                "energy_efficiency": "N/A (UNMEASURED)",
            })

        # ----------------------------------------------------------------------
        # 3. 历史板测数据 (HISTORICAL)
        # ----------------------------------------------------------------------
        if board_log_path and board_log_path.exists():
            hist_item = parse_board_log(board_log_path)
            if hist_item:
                # 仅将适配该模式的历史条目合入
                if hist_item["mode"] == mode_name:
                    all_results.append(hist_item)

        # ----------------------------------------------------------------------
        # 4. 纯理论流水线估算 (ESTIMATED，仅在 --include-estimates 时加入)
        # ----------------------------------------------------------------------
        if include_estimates:
            est_items = get_theoretical_estimates(mode_name, rb, reads)
            all_results.extend(est_items)

    # 计算相对加速比（严格限定：仅在 MEASURED 行中相对于 C 1线程实测计算）
    for mode_name in modes:
        mode_measured = [r for r in all_results if r["mode"] == mode_name and r["category"] == "MEASURED"]
        c1_entry = next((r for r in mode_measured if r["threads"] == 1 and "C (" in r["implementation"]), None)
        c1_tp = c1_entry["source_reads_per_s"] if c1_entry else 1.0

        for r in all_results:
            if r["mode"] == mode_name:
                if r["category"] == "MEASURED":
                    r["speedup_vs_c1"] = round(r["source_reads_per_s"] / c1_tp, 2)
                else:
                    r["speedup_vs_c1"] = "N/A (跨分型不比)"

    # 构造最终结构化 JSON
    status = "PASS" if all_results and not errors else "FAIL"
    output_json = {
        "contract_version": CONTRACT_VERSION,
        "status": status,
        "errors": errors,
        "run_id": run_id,
        "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "host_info": host_info,
        "dataset_contract": {
            "source_reads": reads,
            "orientation": "both",
            "evaluated_records": reads * 2,
            "record_multiplier": 2,
            "description": (
                "Each source read is evaluated in both forward and reverse-complement "
                "orientations against the reference (evaluated_records = 2 * source_reads)."
            ),
        },
        "taxonomy_definitions": TAXONOMY_DEFINITIONS,
        "timing_overlap_boundaries": TIMING_OVERLAP_BOUNDARIES,
        "power_contract": POWER_CONTRACT,
        "results": all_results,
    }

    # 落盘 JSON
    json_path = output_dir / "benchmark_result.json"
    json_path.write_text(json.dumps(output_json, indent=2, ensure_ascii=False), encoding="utf-8")

    # 生成人类可读 Markdown 摘要
    md_lines = [
        f"# CPU vs FPGA 公平基准与计时契约评测报告 ({run_id})",
        "",
        f"- **运行状态**: **{status}**",
        *([f"- **失败原因**: {message}" for message in errors] if errors else []),
        *(["- **失败原因**: 没有生成任何测量结果。"] if not all_results and not errors else []),
        "",
        "> 依据 `docs/08-performance-and-strategy.md的公平基线` 规范生成。严格杜绝稻草人对比与虚假加速比。",
        "",
        "## 1. 评测环境与契约说明",
        f"- **测试时间**: {output_json['timestamp']}",
        f"- **宿主 CPU**: {host_info['model_name']} ({host_info['logical_cores']} 逻辑核 / {host_info['physical_cores'] or 'N/A'} 物理核, {host_info['architecture']})",
        f"- **源读段契约**: source_reads = {reads} 条, orientation = both -> evaluated_records = {reads*2} 条",
        "- **功耗测量状态**: **UNMEASURED (N/A)** —— 未接入外置功率测试仪，严禁伪造能效比",
        "- **分型体系说明**:",
        "  * `[MEASURED]`: 当前主机现场运行实测数据（CPU 单核/多核 OpenMP 实测，Python 抽样外推）",
        "  * `[HISTORICAL]`: 真实历史板测数据（严格关联 board log / run-id / bitstream 证据，无证据不呈现）",
        "  * `[ESTIMATED]`: 纯理论流水线周期估算（显式标注 ESTIMATED，不含 I/O 与传输开销）",
        "",
        "## 2. 计时重叠边界与流水线特性说明 (Timing Overlap Boundaries)",
        "端到端数据读出链路包含以下四个关键阶段：",
        "1. **MM2S 上传**: 主机内存 -> FPGA DDR/BRAM DMA 传输",
        "2. **FPGA 硬件计算**: Stage1 滑窗比对 -> Stage2 差分投票 -> Stage3 反稀疏化",
        "3. **S2MM 接收**: FPGA DDR -> 主机内存 DMA 传输",
        "4. **LDPC 软件译码**: 主机/PS CPU 执行 LDPC 译码",
        "",
        "**不可简单相加的边界原理**：",
        "- 在同步停等（Stop-and-Wait）单批次测量下，总耗时为各阶段顺序累加：`T_e2e = T_upload + T_hw + T_download + T_ldpc`；",
        "- 在双缓冲 / 流式流水线（Streaming Pipeline）架构下，第 k+1 批上传、第 k 批硬件计算、第 k-1 批接收与第 k-2 批 LDPC 译码可时间重叠，系统吞吐受限于最慢瓶颈阶段 `max(T_upload, T_hw, T_download, T_ldpc)`；",
        "- 因此，严禁将未考虑流水线重叠的独立阶段耗时简单折叠或相加，必须明确标注测量边界是「纯硬件流水线周期」、「板端单批端到端」还是「上位机完整回传」。",
        "",
        "## 3. 详细性能数据对照表",
        "",
        "| 分型 | 规格 | 计算平台 | 实现方案 / 测量方法 | 线程 | 延迟 (ms/源读段) | 延迟 (ms/记录) | 吞吐 (源读段/s) | 吞吐 (记录/s) | 相对 C单核加速比 | 功耗 (W) | 能效比 (reads/(s·W)) |",
        "| :---: | :---: | :--- | :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |",
    ]

    for r in all_results:
        spd_str = f"{r['speedup_vs_c1']}x" if isinstance(r["speedup_vs_c1"], (int, float)) else str(r["speedup_vs_c1"])
        md_lines.append(
            f"| **{r['category']}** | {r['mode']} | {r['platform']} | {r['implementation']} | "
            f"{r['threads']}T | {r['ms_per_source_read']:.3f} | {r['ms_per_record']:.3f} | "
            f"{r['source_reads_per_s']:8.1f} | {r['records_per_s']:8.1f} | {spd_str} | "
            f"{r['power_w']} | {r['energy_efficiency']} |"
        )

    md_lines.extend([
        "",
        "## 4. 科学结论与边界",
        "",
        "1. **彻底拒绝「稻草人对比」（No Strawman）**：",
        "   - 若以未优化单核 Python 暴力滑窗为代表，FPGA 会产生虚高数十倍的伪加速比；",
        "   - 但与高度优化的多核 C 语言（-O3 -march=native 位平面位运算 + __builtin_popcountll）相比，现代多核 CPU 具有极高吞吐；",
        "   - 在无板卡物理实测或外置功率仪输入时，严禁宣称已在综合性能或能效比上击败优化 CPU。",
        "",
        "2. **严守功耗未测事实**：",
        "   - 本评测未接入外置硬件功率测试仪，所有功耗与能效比字段标记为 `UNMEASURED / N/A`，杜绝使用 2.5W 或 TDP 估算冒充真实能效比。",
    ])

    summary_md_path = output_dir / "benchmark_summary.md"
    summary_md_path.write_text("\n".join(md_lines) + "\n", encoding="utf-8")

    print("\n" + "\n".join(md_lines))
    marker = "PASS" if status == "PASS" else "FAIL"
    print(f"\n[{marker}] 结构化评测结果已保存至: {json_path}")
    print(f"[{marker}] 摘要报告已保存至: {summary_md_path}")

    return output_json


# ==============================================================================
# 命令行入口
# ==============================================================================
def main():
    parser = argparse.ArgumentParser(description="CPU vs FPGA 严格公平基准测试与计时契约评测工具")
    parser.add_argument("--reads", type=int, default=4096, help="评测源读段数 (默认 4096)")
    parser.add_argument("--probe", type=int, default=20, help="Python 慢速实现抽样读段数 (默认 20)")
    parser.add_argument("--threads", nargs="+", type=int, default=[1, 2, 4, 8, 16], help="OpenMP 测试线程数")
    parser.add_argument("--modes", nargs="+", default=["SE150", "SE250"], help="测试模式 (SE150, SE250)")
    parser.add_argument("--board-log", type=str, default=None, help="历史真实板测日志/摘要路径 (可选)")
    parser.add_argument("--include-estimates", action="store_true", help="包含理论流水线估算条目 [ESTIMATED]")
    parser.add_argument("--run-id", type=str, default=None, help="本次评测 run-id")
    parser.add_argument("--outdir", type=str, default=None, help="评测结果输出目录 (默认 logs/benchmarks/<run-id>)")
    parser.add_argument("--repeats", type=int, default=3, help="C benchmark 重复测量次数 (默认 3)")
    args = parser.parse_args()

    board_log = Path(args.board_log) if args.board_log else None
    outdir = Path(args.outdir) if args.outdir else None

    try:
        result = run_benchmark_suite(
            reads=args.reads,
            probe=args.probe,
            threads=args.threads,
            modes=args.modes,
            board_log_path=board_log,
            include_estimates=args.include_estimates,
            run_id=args.run_id,
            outdir=outdir,
            repeats=args.repeats,
        )
    except (ValueError, FileNotFoundError, RuntimeError) as exc:
        parser.error(str(exc))
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
