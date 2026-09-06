#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Reusable TCP client core for the DNA accelerator workflow."""

from __future__ import annotations

import argparse
import socket
import struct
from dataclasses import dataclass
from pathlib import Path
from time import perf_counter
from typing import Callable, Iterable, Optional, Sequence

from protocol import (
    HDR_FMT,
    HDR_SZ,
    MAGIC,
    NetStats,
    PKT_BATCH,
    PKT_BATCH_OK,
    PKT_CAPS,
    PKT_CAPS_INFO,
    PKT_CONFIG,
    PKT_CONFIG_OK,
    PKT_ERROR,
    PKT_POST,
    PKT_RESULT,
    PKT_WM,
    PKT_WM_OK,
    expect_ack,
    make_header,
    make_packet,
    query_caps,
    recv_ack_byte,
    recv_exact,
    recv_packet,
    send_config,
    sendall_count,
)
from task_protocol import (
    FRAME_READS,
    MAX_TOTAL_READS,
    READ_BASES,
    SUPPORTED_READ_BASES,
    TASK_NUM_LC,
    TASK_PROTO_VERSION,
    TaskSpec,
    build_config_payload,
    default_score_min,
    read_size_bytes,
)
from fast_readout import (
    fast_iter_read_batches,
    fast_pack_watermark_bits,
    fast_unpack_result,
    seq_to_read_bytes as fast_seq_to_read_bytes,
)

# ============================================================================
# 基础常量
# ============================================================================
DEFAULT_IP = "192.168.1.10"
DEFAULT_PORT = 7

DEFAULT_WATERMARK_FILE = "watermark.txt"
DEFAULT_READS_FILE = "read.fastq"
# 默认将服务器返回的比特流保存为解码输入 dec_input.txt
DEFAULT_OUTPUT_FILE = "dec_input.txt"

DEFAULT_FORMAT = "auto"

# SE150 的线上字节数。编码路径本身已按 read_bps 参数化（见 seq_to_read_bytes），
# 这个模块级常量只是 SE150 的便捷别名；SE250 请用 read_size_bytes(250) = 64。
READ_SIZE_BYTES = read_size_bytes(READ_BASES)
DEFAULT_TOTAL_READS = 2_048  # 实测约 1,080 条即可完整还原，2,048 留足余量
DEFAULT_BATCH_SIZE = 1_000
RESULT_BYTES = 8_100
MAX_WATERMARK = 10_128
WM_ALIGN = 8

BASE2BITS = {
    "A": "00",
    "T": "01",
    "G": "10",
    "C": "11",
    "N": "00",
    "a": "00",
    "t": "01",
    "g": "10",
    "c": "11",
    "n": "00",
}

# 反向互补：A<->T, G<->C。测序数据里约一半读段是反向的（docs/03-status.md D1），
# 不处理的话即使用满全部读段也无法译码。
#
# 注意 N 映射到 T 而不是 N：整条流水线只认 2-bit 符号，而 BASE2BITS["N"] == "00"，
# 即 N 在编码阶段就已经被当成 A；既然如此，反向互补也必须按 A 处理（A→T）。
# 这样与黄金模型的「符号值异或 1 后整体反序」完全等价——否则含 N 的读段
# 会在两侧算出不同的编码（实测 64 条里差 1 条）。
REVCOMP = str.maketrans("ACGTNacgtn", "TGCATtgcat")


def reverse_complement(seq: str) -> str:
    return seq.translate(REVCOMP)[::-1]


class OperationCancelled(RuntimeError):
    """Raised when a stop event or user cancellation is detected."""


@dataclass()  # 注意: 原为 slots=True，仅为省内存但会把最低版本抬到 Py3.10，去掉以便更广泛地运行与测试
class ReadFileInfo:
    """Metadata extracted from a reads file."""

    path: Path
    format: str
    total_reads: int
    detected_read_bps: Optional[int] = None
    suggested_score_min: Optional[int] = None
    estimated_seconds: Optional[float] = None


@dataclass()  # 注意: 原为 slots=True，仅为省内存但会把最低版本抬到 Py3.10，去掉以便更广泛地运行与测试
class ClientConfig:
    """High-level configuration for a client session."""

    ip: str = DEFAULT_IP
    port: int = DEFAULT_PORT
    watermark: Path = Path(DEFAULT_WATERMARK_FILE)
    reads: Path = Path(DEFAULT_READS_FILE)
    out: Path = Path(DEFAULT_OUTPUT_FILE)
    batch: int = DEFAULT_BATCH_SIZE
    total: Optional[int] = None
    send_limit: Optional[int] = None
    skip_wm: bool = False
    orient: str = "both"        # both = 每条读段发正向+反向互补（必需，见 D1）
    post: bool = True
    format: str = DEFAULT_FORMAT
    read_bps: int = READ_BASES  # 150=SE150 / 250=SE250；决定线上字节数与默认阈值
    # 【P3】经 PKT_CONFIG 下发。None = 按 read_bps 取 int(0.45×read_bps)
    # （SE150 67 / SE250 112），与黄金向量的 --min-score 0.45 同源。
    score_min: Optional[int] = None
    dry_run: bool = False       # 【P3】只打印将下发的配置，不连接板端
    # 板端从收到 PKT_POST 到 send_result() 之间一个字节都不发（echo.c 的 poll_callback
    # 只在 PROC_DONE 才发结果），而 recv_exact 用的是 sock.settimeout()，
    # 所以这个值是**整条流水线处理时长的上限**，不是「两次进度打印的间隔」。
    # 4,096 条记录实测 32.4 s，其中约 97% 是随条数线性增长的 Stage1；
    # 换规模时必须一起调大，否则超时会把「还在算」误报成「挂了」。
    result_timeout: float = 180.0

    @property
    def resolved_score_min(self) -> int:
        """未显式指定时按 read_bps 推出阈值，避免拿 SE150 的 67 去跑 SE250。"""
        return default_score_min(self.read_bps) if self.score_min is None else self.score_min

    @property
    def read_size_bytes(self) -> int:
        return read_size_bytes(self.read_bps)

    def resolve_total(self, detected: int) -> int:
        """Return number of source reads to send.

        【P3 修正】原实现 `min(max(candidates))` 把 --total-reads 和 --limit
        都当成了「抬底」，--limit 2048 在 51,781 条的文件上会取 51,781——
        与帮助文本「最多发送多少条」相反。现在 PKT_CONFIG 会校验
        「声明条数 == 实发条数」，此处必须算对：
          --total-reads N → 恰好 N 条；--limit N → 至多 N 条。
        """
        if detected <= 0:
            raise ValueError("读段文件中没有完整记录")
        resolved = detected if self.total is None else self.total
        if self.total is not None and self.total <= 0:
            raise ValueError("--total-reads must be positive")
        if self.total is not None and self.total > detected:
            raise ValueError(
                f"--total-reads={self.total} 超过文件内实际读段数 {detected}"
            )
        if self.send_limit is not None and self.send_limit <= 0:
            raise ValueError("--limit must be positive")
        if self.send_limit is not None:
            resolved = min(resolved, self.send_limit)
        if resolved < 1:
            raise ValueError("Resolved read count must be >= 1")
        if resolved > MAX_TOTAL_READS:
            raise ValueError(
                f"源读段数量 {resolved} 超过客户端上限 {MAX_TOTAL_READS}，"
                "请显式使用 --limit"
            )
        return resolved


@dataclass()  # 注意: 原为 slots=True，仅为省内存但会把最低版本抬到 Py3.10，去掉以便更广泛地运行与测试
class ProgressCallbacks:
    """Optional GUI hooks for status and progress updates."""

    update_status: Optional[Callable[[str], None]] = None
    update_upload: Optional[Callable[[int, int], None]] = None
    update_stage_label: Optional[Callable[[str], None]] = None

    def set_status(self, message: str) -> None:
        if self.update_status:
            self.update_status(message)

    def update_upload_progress(self, sent: int, total: int) -> None:
        if self.update_upload:
            self.update_upload(sent, total)

    def set_stage(self, stage: str) -> None:
        if self.update_stage_label:
            self.update_stage_label(stage)


def log_info(logger: Optional[Callable[[str], None]], message: str) -> None:
    """Log helper that falls back to print when no logger provided."""
    if logger is not None:
        logger(message)
    else:
        print(message)


# ============================================================================
# 文件解析 / 编码工具
# ============================================================================
def detect_file_format(reads_file: Path) -> str:
    """检测读段文件格式: 'fastq' 或 'plain'."""
    with reads_file.open("r", encoding="utf-8", errors="ignore") as handle:
        first_line = handle.readline().strip()
    return "fastq" if first_line.startswith("@") else "plain"


def count_reads_in_file(reads_file: Path, format_type: str = "auto") -> int:
    """统计文件中的读段数量。"""
    count, _ = inspect_reads_file(reads_file, format_type)
    return count


def inspect_reads_file(reads_file: Path, format_type: str = "auto") -> tuple[int, Optional[int]]:
    """统计读段总数并采样探测典型读长 (bp)。"""
    if format_type == "auto":
        format_type = detect_file_format(reads_file)

    count = 0
    sample_lengths = []
    with reads_file.open("r", encoding="utf-8", errors="ignore") as handle:
        if format_type == "fastq":
            while True:
                header = handle.readline()
                if not header:
                    break
                seq = handle.readline()
                plus = handle.readline()
                qual = handle.readline()
                if seq and plus and qual:
                    count += 1
                    if len(sample_lengths) < 20:
                        sample_lengths.append(len(seq.strip()))
                else:
                    break
        else:
            for line in handle:
                s = line.strip()
                if s:
                    count += 1
                    if len(sample_lengths) < 20:
                        sample_lengths.append(len(s))

    detected_bps = None
    if sample_lengths:
        avg_len = sum(sample_lengths) // len(sample_lengths)
        if 130 <= avg_len <= 170:
            detected_bps = 150
        elif 220 <= avg_len <= 280:
            detected_bps = 250
        else:
            detected_bps = avg_len
    return count, detected_bps


def estimate_processing_time(total_reads: int, orient: str = "both") -> float:
    """基于板端实测模型 t = 4.93s + 0.9396ms * 记录数，预估处理耗时 (秒)。"""
    records = total_reads * 2 if orient == "both" else total_reads
    return 4.93 + 0.0009396 * records


def analyze_reads_file(path: Path, format_hint: str = "auto") -> ReadFileInfo:
    """Return format + total count + detected read length for the supplied reads file."""
    if not path.exists():
        raise FileNotFoundError(f"Reads file not found: {path}")
    fmt = format_hint
    if fmt == "auto":
        fmt = detect_file_format(path)
    count, detected_bps = inspect_reads_file(path, fmt)
    score_min = default_score_min(detected_bps) if detected_bps in SUPPORTED_READ_BASES else None
    est_sec = estimate_processing_time(count) if count > 0 else None
    return ReadFileInfo(
        path=path,
        format=fmt,
        total_reads=count,
        detected_read_bps=detected_bps,
        suggested_score_min=score_min,
        estimated_seconds=est_sec,
    )


def seq_to_read_bytes(seq: str, read_bps: int = READ_BASES) -> bytes:
    """把一条 read_bps bp 序列编码成 read_size_bytes(read_bps) 字节。

    SE150：150 bp → 40 B；SE250：250 bp → 64 B（63 B 有效 + 1 B 补零对齐）。

    格式见 docs/02-data-contract.md：
      * 位平面布局：码流前 read_bps 位是每个碱基的高位，后 read_bps 位是低位；
      * 字节内 **LSB-first** 打包：码流第 k 位 → 第 k/8 个字节的第 k%8 位。

    LSB-first 是刻意选的：这样 AXIS 上组装出来的 `in_buf[k]` 正好等于码流第 k 位，
    RTL 端不需要任何位反转。原实现用的是 MSB-first，与 RTL 对不上（缺陷 B4）。

    截断/补 N 一律按传入的 read_bps 做：这个参数写死成 150 的话，SE250 的
    250 bp 读段会被静默砍成 150 bp（docs/reference/dataset.md 记过这个风险）。
    """
    return fast_seq_to_read_bytes(seq, read_bps)


def iter_source_seqs(path: Path, limit: int, format_type: str = "auto") -> Iterable[str]:
    """按源文件顺序产出序列字符串，最多 limit 条。"""
    fmt = format_type
    if fmt == "auto":
        fmt = detect_file_format(path)
    produced = 0
    with path.open("r", encoding="utf-8", errors="ignore") as handle:
        if fmt == "fastq":
            while produced < limit:
                header = handle.readline()
                if not header:
                    break
                seq = handle.readline()
                handle.readline()
                qual = handle.readline()
                if not seq or not qual:
                    break
                yield seq.strip()
                produced += 1
        else:
            for line in handle:
                if produced >= limit:
                    break
                seq = line.strip()
                if seq:
                    yield seq
                    produced += 1


def iter_reads(
    path: Path,
    limit: int,
    format_type: str = "auto",
    orient: str = "both",
    read_bps: int = READ_BASES,
) -> Iterable[bytes]:
    """产出编码后的读段字节。

    `orient="both"` 时每条源读段发两份：正向 + 反向互补。
    板端 Stage1 会分别给两份打分，Voter 按分数丢掉方向错的那份
    （docs/06-implementation-plan.md P1）。这是必需的：测序数据里约一半读段
    是反向互补的，不发的话即使用满全部读段也无法译码。
    """
    if orient not in {"both", "forward"}:
        raise ValueError(f"未知 orient={orient!r}")
    for seq in iter_source_seqs(path, limit, format_type):
        yield seq_to_read_bytes(seq, read_bps)
        if orient == "both":
            yield seq_to_read_bytes(reverse_complement(seq), read_bps)


def round_up_frames(n: int) -> int:
    """向上取整到 FRAME_READS 的整数倍（srpe_batch 每批固定 64 条）。"""
    return ((n + FRAME_READS - 1) // FRAME_READS) * FRAME_READS


def iter_read_batches(
    reads_file: Path,
    source_reads: int,
    send_total: int,
    batch_size: int = DEFAULT_BATCH_SIZE,
    format_type: str = "auto",
    orient: str = "both",
    read_bps: int = READ_BASES,
) -> Iterable[bytes]:
    """产出 PKT_BATCH 的负载块；不足 send_total 的部分补零读段。"""
    return fast_iter_read_batches(
        reads_file=reads_file,
        source_reads=source_reads,
        send_total=send_total,
        batch_size=batch_size,
        format_type=format_type,
        orient=orient,
        read_bps=read_bps,
    )


# ============================================================================
# 业务流程
# ============================================================================
def parse_watermark_text(text: str) -> str:
    """只接受 0/1 与空白，返回去除空白后的逻辑位流。"""
    invalid = {char for char in text if char not in "01 \t\r\n"}
    if invalid:
        sample = "".join(sorted(invalid))[:16]
        raise ValueError(f"水印含非 0/1/空白字符: {sample!r}")
    bits = "".join(char for char in text if char in "01")
    if not bits:
        raise ValueError("水印不含任何 0/1 bit")
    return bits


def load_watermark_bits(path: Path) -> str:
    return parse_watermark_text(path.read_text(encoding="utf-8"))


def pack_watermark_bits(bits: str, task: TaskSpec) -> bytes:
    return fast_pack_watermark_bits(bits, task)


def send_watermark(
    sock: socket.socket,
    watermark_bits: str,
    stats: NetStats,
    task: TaskSpec,
) -> int:
    """编码并发送已读取的水印位流。"""
    payload = pack_watermark_bits(watermark_bits, task)

    sendall_count(stats, sock, make_packet(PKT_WM, payload))
    expect_ack(sock, stats, PKT_WM_OK, operation="水印上传", timeout=120.0)
    return len(payload)


def send_batches(
    sock: socket.socket,
    reads_file: Path,
    source_reads: int,
    send_total: int,
    stats: NetStats,
    *,
    batch_size: int = DEFAULT_BATCH_SIZE,
    format_type: str = "auto",
    orient: str = "both",
    read_bps: int = READ_BASES,
    stop_check: Optional[Callable[[], bool]] = None,
    progress: Optional[ProgressCallbacks] = None,
) -> int:
    """Send read batches while updating progress callbacks."""
    total_sent = 0
    batch_index = 0

    for payload in iter_read_batches(reads_file, source_reads, send_total,
                                     batch_size, format_type, orient, read_bps):
        if stop_check and stop_check():
            raise OperationCancelled("Operation cancelled")

        sendall_count(stats, sock, make_packet(PKT_BATCH, payload))
        stats.batches += 1

        expect_ack(sock, stats, PKT_BATCH_OK,
                   operation=f"读段批次 #{batch_index}")

        batch_reads = (len(payload) - 4) // read_size_bytes(read_bps)
        total_sent += batch_reads
        batch_index += 1

        if progress:
            progress.update_upload_progress(total_sent, send_total)

    if progress:
        progress.update_upload_progress(send_total, send_total)
    return batch_index


def send_post(sock: socket.socket, stats: NetStats) -> None:
    sendall_count(stats, sock, make_packet(PKT_POST, b""))


def recv_result(
    sock: socket.socket,
    stats: NetStats,
    out_file: Path,
    timeout: float = 120.0,
) -> int:
    pkt_type, payload = recv_packet(sock, stats, timeout=timeout)
    if pkt_type != PKT_RESULT:
        raise RuntimeError(f"Expected PKT_RESULT (0x04), got 0x{pkt_type:02X}")
    if len(payload) != RESULT_BYTES:
        raise RuntimeError(
            f"PKT_RESULT 长度应为 {RESULT_BYTES} B，实得 {len(payload)} B"
        )

    bit_string = fast_unpack_result(payload)
    out_file.parent.mkdir(parents=True, exist_ok=True)
    out_file.write_text(bit_string, encoding="utf-8")
    return len(payload)


def run_client(
    config: ClientConfig,
    *,
    log: Optional[Callable[[str], None]] = None,
    progress: Optional[ProgressCallbacks] = None,
    stop_event: Optional["threading.Event"] = None,
) -> NetStats:
    """Execute the full upload / download workflow."""
    import threading  # Local import to avoid runtime dependency for packaging.

    stats = NetStats()

    def stop_requested() -> bool:
        return stop_event.is_set() if isinstance(stop_event, threading.Event) else False

    reads_path = Path(config.reads).expanduser()
    watermark_path = Path(config.watermark).expanduser()
    output_path = Path(config.out).expanduser()

    if not reads_path.exists():
        raise FileNotFoundError(f"Reads file does not exist: {reads_path}")
    if not watermark_path.exists():
        raise FileNotFoundError(f"Watermark file does not exist: {watermark_path}")
    if config.skip_wm and config.post:
        raise ValueError("--skip-watermark 只能与 --no-post 一起用于协议调试")
    if config.read_bps not in SUPPORTED_READ_BASES:
        raise ValueError(
            f"--read-bps {config.read_bps} 不在支持列表 {SUPPORTED_READ_BASES}")

    info = analyze_reads_file(reads_path, config.format)
    source_reads = config.resolve_total(info.total_reads)
    if config.batch <= 0:
        raise ValueError("--batch must be positive")
    per_read = 2 if config.orient == "both" else 1
    send_total = round_up_frames(source_reads * per_read)
    if send_total > MAX_TOTAL_READS:
        raise ValueError(
            f"发送量 {send_total} 条超过板端上限 {MAX_TOTAL_READS}"
            f"（源读段 {source_reads} 条 × {per_read} 个方向，向上取整到 {FRAME_READS} 的倍数）")

    # 水印只读取一次；同一份 bit 字符串同时驱动 TaskSpec 与实际上传。
    watermark_bits = load_watermark_bits(watermark_path)
    task = TaskSpec.from_watermark_bits(
        len(watermark_bits),
        total_reads=send_total,
        score_min=config.resolved_score_min,
        read_bps=config.read_bps,
    )

    if config.dry_run:
        payload = task.config_payload()
        print("[dry-run] 将下发 PKT_CONFIG(0x05) 44B：")
        print(f"  每条读段线上 {task.read_size_bytes} B")
        print(f"  version={task.version} read_bps={task.read_bps} "
              f"num_lc={task.num_lc} stride={task.stride} symbols={task.symbols}")
        print(f"  total_reads={task.total_reads} score_min={task.score_min}")
        print(f"  payload hex = {payload.hex()}")
        return stats

    progress = progress or ProgressCallbacks()

    log_info(log, f"[INFO] Connecting to {config.ip}:{config.port}")
    log_info(
        log,
        f"[INFO] Reads file: {reads_path} ({info.total_reads} reads detected, format {info.format.upper()})",
    )
    log_info(log, f"[INFO] 几何 read_bps={task.read_bps} num_lc={task.num_lc} "
                  f"stride={task.stride} 每条读段 {task.read_size_bytes} B "
                  f"score_min={task.score_min}")
    log_info(log, f"[INFO] 取用源读段 {source_reads} 条，方向 {config.orient}（每条 {per_read} 份）")
    padding = send_total - source_reads * per_read
    log_info(log, f"[INFO] 实际发送 {send_total} 条（{FRAME_READS} 的整数倍"
                  + (f"，其中补零 {padding} 条" if padding else "") + "）")
    log_info(log, f"[INFO] Output file: {output_path}")

    with socket.create_connection((config.ip, config.port)) as sock:
        t_start = perf_counter()

        # 【P3】先查能力再下发配置（严格拒绝模式：不匹配直接失败）
        caps = query_caps(sock, stats)
        log_info(log, f"[CAPS] v{caps.version} read_bps={caps.read_bps} "
                      f"num_lc={caps.num_lc} stride={caps.stride} "
                      f"max_reads={caps.max_reads} features=0x{caps.features:X}")
        task.validate_caps(caps)
        send_config(sock, stats, task, log=log)

        if config.skip_wm:
            log_info(log, "[1/4] Skipping watermark upload (user request)")
        else:
            if stop_requested():
                raise OperationCancelled("Operation cancelled")
            progress.set_status("上传水印...")
            t0 = perf_counter()
            wm_size = send_watermark(sock, watermark_bits, stats, task)
            stats.t_wm = perf_counter() - t0
            log_info(
                log,
                f"      Watermark: {wm_size} bytes, {stats.t_wm:.2f}s, {stats.mbps(wm_size, stats.t_wm):.2f} Mbps",
            )

        if stop_requested():
            raise OperationCancelled("Operation cancelled")

        progress.set_status("发送读段...")
        progress.set_stage("UPLOAD")
        t0 = perf_counter()
        batch_count = send_batches(
            sock,
            reads_path,
            source_reads,
            send_total,
            stats,
            batch_size=config.batch,
            format_type=info.format,
            orient=config.orient,
            read_bps=config.read_bps,
            stop_check=stop_requested,
            progress=progress,
        )
        stats.t_batches = perf_counter() - t0
        reads_bytes = send_total * task.read_size_bytes
        log_info(
            log,
            (
                f"      Reads: {batch_count} batches, {reads_bytes} bytes, "
                f"{stats.t_batches:.2f}s, {stats.mbps(reads_bytes, stats.t_batches):.2f} Mbps"
            ),
        )

        if stop_requested():
            raise OperationCancelled("Operation cancelled")

        if config.post:
            progress.set_status("发送POST命令...")
            progress.set_stage("POST")
            send_post(sock, stats)
        else:
            stats.t_total = perf_counter() - t_start
            progress.set_status("上传完成（未触发 POST）")
            return stats

        if stop_requested():
            raise OperationCancelled("Operation cancelled")

        progress.set_status("接收结果...")
        progress.set_stage("RESULT")
        t0 = perf_counter()
        result_size = recv_result(sock, stats, output_path, timeout=config.result_timeout)
        stats.t_result = perf_counter() - t0
        log_info(
            log,
            f"      Result: {result_size} bytes, {stats.t_result:.2f}s, "
            f"{stats.mbps(result_size, stats.t_result):.2f} Mbps",
        )

        stats.t_total = perf_counter() - t_start
        progress.set_status("任务完成")

    return stats


def format_metric_report(stats: NetStats) -> str:
    """Return a human-readable metrics report."""
    return (
        "\n"
        + "=" * 60
        + "\n传输统计:\n"
        + f"  上行:    {stats.upload:,} bytes\n"
        + f"  下行:    {stats.download:,} bytes\n"
        + f"  总计:    {stats.total_bytes:,} bytes\n"
        + f"  总时长:  {stats.t_total:.2f}s\n"
        + f"  平均速率: {stats.mbps(stats.total_bytes, stats.t_total):.2f} Mbps\n"
        + "\n各阶段耗时:\n"
        + f"  水印:    {stats.t_wm:.2f}s\n"
        + f"  读段:    {stats.t_batches:.2f}s\n"
        + f"  结果:    {stats.t_result:.2f}s\n"
        + f"  其他:    {stats.t_total - stats.t_wm - stats.t_batches - stats.t_result:.2f}s\n"
        + "=" * 60
    )


# ============================================================================
# CLI entry for backwards compatibility
# ============================================================================
def _parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="DNA Accelerator Client - GUI/CLI shared core",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "示例:\n"
            "  python first.py --watermark wm.txt --reads data.fastq\n"
            "\n"
            "默认会自动检测读段数量, 也可以通过 --total-reads 指定。\n"
        ),
    )

    parser.add_argument("--ip", default=DEFAULT_IP)
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument("--watermark", type=Path, default=Path(DEFAULT_WATERMARK_FILE))
    parser.add_argument("--reads", type=Path, default=Path(DEFAULT_READS_FILE))
    parser.add_argument("--output", type=Path, default=Path(DEFAULT_OUTPUT_FILE))
    parser.add_argument("--total-reads", type=int, default=None, help="指定读段数量(默认自动检测)")
    parser.add_argument("--limit", type=int, default=None, help="最多发送多少条读段(默认全部)")
    parser.add_argument("--batch", type=int, default=DEFAULT_BATCH_SIZE, help="每批包含的读段数")
    parser.add_argument("--format", choices=["auto", "fastq", "plain"], default=DEFAULT_FORMAT)
    parser.add_argument("--orient", choices=["both", "forward"], default="both",
                        help="both=每条读段发正向+反向互补（默认，必需）；forward=只发正向（仅作对照实验）")
    parser.add_argument("--skip-watermark", action="store_true", help="跳过水印发送")
    parser.add_argument("--read-bps", type=int, default=READ_BASES,
                        choices=list(SUPPORTED_READ_BASES),
                        help="读段长度：150=SE150（默认）/ 250=SE250。"
                             "决定线上字节数（40/64 B）与默认阈值（67/112）；"
                             "板端只支持它综合时的那一种，混用会被 PKT_CONFIG 拒绝码 2 拒掉")
    parser.add_argument("--score-min", type=int, default=None,
                        help="PKT_CONFIG 下发的比对分阈值"
                             "（默认 int(0.45×read_bps)：SE150 67 / SE250 112，与黄金向量一致）")
    parser.add_argument("--dry-run", action="store_true",
                        help="只打印将下发的 PKT_CONFIG 内容，不连接板端")
    parser.add_argument("--no-post", action="store_true", help="不发送POST触发命令")
    parser.add_argument("--result-timeout", type=float, default=180.0,
                        help="等待板端结果的超时（秒）。板端处理期间静默，"
                             "所以这是整条流水线的时长上限；条数越多必须调得越大（默认 180）")
    return parser.parse_args(argv)


def main(argv: Optional[Sequence[str]] = None) -> None:
    args = _parse_args(argv)

    config = ClientConfig(
        ip=args.ip,
        port=args.port,
        watermark=args.watermark,
        reads=args.reads,
        out=args.output,
        batch=args.batch,
        total=args.total_reads,
        send_limit=args.limit,
        skip_wm=args.skip_watermark,
        orient=args.orient,
        post=not args.no_post,
        format=args.format,
        read_bps=args.read_bps,
        score_min=args.score_min,
        dry_run=args.dry_run,
        result_timeout=args.result_timeout,
    )

    stats = run_client(config, log=lambda msg: print(msg))
    print(format_metric_report(stats))
    if not config.dry_run:
        print(f"\n结果已保存到: {Path(config.out).resolve()}")


if __name__ == "__main__":
    main()
