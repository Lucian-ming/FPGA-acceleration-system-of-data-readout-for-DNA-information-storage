#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Reusable TCP client core for the DNA accelerator workflow."""

from __future__ import annotations

import argparse
import socket
import struct
from dataclasses import dataclass, field
from pathlib import Path
from time import perf_counter
from typing import Callable, Iterable, Optional, Sequence

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

MAGIC = 0xBEEF
HDR_FMT = ">HBBI"
HDR_SZ = struct.calcsize(HDR_FMT)

PKT_WM = 0x01
PKT_BATCH = 0x02
PKT_POST = 0x03
PKT_RESULT = 0x04
PKT_WM_OK = 0x11
PKT_BATCH_OK = 0x12
PKT_ERROR = 0xEE

READ_SIZE_BYTES = 40
DEFAULT_TOTAL_READS = 64_800
MAX_TOTAL_READS = 108_000
DEFAULT_BATCH_SIZE = 1_000
RESULT_BYTES = 8 * 1024
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


class OperationCancelled(RuntimeError):
    """Raised when a stop event or user cancellation is detected."""


class NetStats:
    """Keep track of upload/download metrics for reporting."""

    def __init__(self) -> None:
        self.upload = 0
        self.download = 0
        self.t_wm = 0.0
        self.t_batches = 0.0
        self.t_result = 0.0
        self.t_total = 0.0
        self.batches = 0

    @property
    def total_bytes(self) -> int:
        return self.upload + self.download

    def mbps(self, bytes_: int, seconds: float) -> float:
        if seconds <= 0:
            return 0.0
        return (bytes_ * 8) / seconds / 1e6


@dataclass(slots=True)
class ReadFileInfo:
    """Metadata extracted from a reads file."""

    path: Path
    format: str
    total_reads: int


@dataclass(slots=True)
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
    post: bool = True
    format: str = DEFAULT_FORMAT

    def resolve_total(self, detected: int) -> int:
        """Return number of reads to send after applying limits."""
        candidates = [detected]
        if self.total and self.total > 0:
            candidates.append(self.total)
        if self.send_limit and self.send_limit > 0:
            candidates.append(self.send_limit)
        resolved = min(max(candidates), MAX_TOTAL_READS)
        if resolved < 1:
            raise ValueError("Resolved read count must be >= 1")
        return resolved


@dataclass(slots=True)
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
    if format_type == "auto":
        format_type = detect_file_format(reads_file)

    count = 0
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
                else:
                    break
        else:
            for line in handle:
                if line.strip():
                    count += 1
    return count


def analyze_reads_file(path: Path, format_hint: str = "auto") -> ReadFileInfo:
    """Return format + total count for the supplied reads file."""
    if not path.exists():
        raise FileNotFoundError(f"Reads file not found: {path}")
    fmt = format_hint
    if fmt == "auto":
        fmt = detect_file_format(path)
    count = count_reads_in_file(path, fmt)
    return ReadFileInfo(path=path, format=fmt, total_reads=count)


def seq_to_40B(seq: str) -> bytes:
    """Encode a 150bp sequence into 40 bytes (packed 2-bit bases)."""
    s = seq.strip().upper()
    if len(s) < 150:
        s += "N" * (150 - len(s))
    elif len(s) > 150:
        s = s[:150]

    out_bits = ["0"] * (150 * 2)
    for idx, base in enumerate(s):
        pair = BASE2BITS.get(base, "00")
        out_bits[idx] = pair[0]
        out_bits[150 + idx] = pair[1]

    bit_string = "".join(out_bits)
    data = bytes(int(bit_string[i : i + 8].ljust(8, "0"), 2) for i in range(0, len(bit_string), 8))

    if len(data) < READ_SIZE_BYTES:
        data += b"\x00" * (READ_SIZE_BYTES - len(data))
    elif len(data) > READ_SIZE_BYTES:
        data = data[:READ_SIZE_BYTES]
    return data


def iter_reads_fastq(path: Path, limit: int) -> Iterable[bytes]:
    """Yield encoded reads from a FASTQ file."""
    produced = 0
    with path.open("r", encoding="utf-8", errors="ignore") as handle:
        while produced < limit:
            header = handle.readline()
            if not header:
                break
            seq = handle.readline()
            plus = handle.readline()
            qual = handle.readline()
            if not seq or not qual:
                break
            yield seq_to_40B(seq)
            produced += 1

    while produced < limit:
        yield b"\x00" * READ_SIZE_BYTES
        produced += 1


def iter_reads_plain(path: Path, limit: int) -> Iterable[bytes]:
    """Yield encoded reads when each line contains one sequence."""
    produced = 0
    with path.open("r", encoding="utf-8", errors="ignore") as handle:
        for line in handle:
            if produced >= limit:
                break
            seq = line.strip()
            if not seq:
                continue
            yield seq_to_40B(seq)
            produced += 1

    while produced < limit:
        yield b"\x00" * READ_SIZE_BYTES
        produced += 1


def iter_reads(path: Path, limit: int, format_type: str = "auto") -> Iterable[bytes]:
    """Dispatch to the appropriate reader iterator."""
    fmt = format_type
    if fmt == "auto":
        fmt = detect_file_format(path)
    if fmt == "fastq":
        return iter_reads_fastq(path, limit)
    return iter_reads_plain(path, limit)


def iter_read_batches(
    reads_file: Path,
    total_reads: int,
    batch_size: int = DEFAULT_BATCH_SIZE,
    format_type: str = "auto",
) -> Iterable[bytes]:
    """Generate payload blocks for sending read batches."""
    batch: list[bytes] = []
    count = 0

    for read in iter_reads(reads_file, total_reads, format_type):
        batch.append(read)
        count += 1
        if len(batch) >= batch_size:
            header = struct.pack(">I", len(batch))
            yield header + b"".join(batch)
            batch.clear()

    if batch:
        header = struct.pack(">I", len(batch))
        yield header + b"".join(batch)

    if count != total_reads:
        # 调试信息: 实际发送数量与预期不一致
        print(f"[WARN] 预期 {total_reads} 条读段, 实际生成 {count} 条")


# ============================================================================
# 网络传输
# ============================================================================
def sendall_count(stats: NetStats, sock: socket.socket, data: bytes) -> None:
    sock.sendall(data)
    stats.upload += len(data)


def make_header(pkt_type: int, payload_len: int) -> bytes:
    return struct.pack(HDR_FMT, MAGIC, pkt_type, 0, payload_len)


def make_packet(pkt_type: int, payload: bytes = b"") -> bytes:
    return make_header(pkt_type, len(payload)) + (payload or b"")


def recv_exact(sock: socket.socket, n: int, stats: NetStats, timeout: float = 60.0) -> bytes:
    sock.settimeout(timeout)
    buf = bytearray()
    while len(buf) < n:
        chunk = sock.recv(n - len(buf))
        if not chunk:
            raise ConnectionError("Connection closed while receiving")
        buf.extend(chunk)
        stats.download += len(chunk)
    return bytes(buf)


def recv_packet(sock: socket.socket, stats: NetStats, timeout: float = 60.0) -> tuple[int, bytes]:
    header = recv_exact(sock, HDR_SZ, stats, timeout=timeout)
    magic, pkt_type, _rsv, length = struct.unpack(HDR_FMT, header)
    if magic != MAGIC:
        raise ValueError(f"Unexpected magic value: 0x{magic:04X}")
    payload = b""
    if length > 0:
        payload = recv_exact(sock, length, stats, timeout=timeout)
    return pkt_type, payload


def recv_ack_byte(sock: socket.socket, stats: NetStats, expected: int, timeout: float = 10.0) -> bool:
    ack = recv_exact(sock, 1, stats, timeout=timeout)
    return ack[0] == expected


# ============================================================================
# 业务流程
# ============================================================================
def send_watermark(sock: socket.socket, wm_file: Path, stats: NetStats) -> int:
    """Encode watermark file and push to the board."""
    text = wm_file.read_text(encoding="utf-8")
    filtered = "".join(ch for ch in text if ch in "01")
    if len(filtered) > 81_000:
        filtered = filtered[:81_000]

    payload = bytearray()
    for idx in range(0, len(filtered), 8):
        byte_str = filtered[idx : idx + 8].ljust(8, "0")
        payload.append(int(byte_str, 2))

    padding = (WM_ALIGN - (len(payload) % WM_ALIGN)) % WM_ALIGN
    if padding:
        payload.extend(b"\x00" * padding)

    if len(payload) > MAX_WATERMARK:
        raise ValueError(f"Watermark payload too large: {len(payload)} bytes > {MAX_WATERMARK} bytes")

    sendall_count(stats, sock, make_packet(PKT_WM, bytes(payload)))
    if not recv_ack_byte(sock, stats, PKT_WM_OK, timeout=120.0):
        raise RuntimeError("Watermark ACK failed")
    return len(payload)


def send_batches(
    sock: socket.socket,
    reads_file: Path,
    total_reads: int,
    stats: NetStats,
    *,
    batch_size: int = DEFAULT_BATCH_SIZE,
    format_type: str = "auto",
    stop_check: Optional[Callable[[], bool]] = None,
    progress: Optional[ProgressCallbacks] = None,
) -> int:
    """Send read batches while updating progress callbacks."""
    total_sent = 0
    batch_index = 0

    for payload in iter_read_batches(reads_file, total_reads, batch_size, format_type):
        if stop_check and stop_check():
            raise OperationCancelled("Operation cancelled")

        sendall_count(stats, sock, make_packet(PKT_BATCH, payload))
        stats.batches += 1

        if not recv_ack_byte(sock, stats, PKT_BATCH_OK):
            raise RuntimeError(f"Batch #{batch_index} ACK failed")

        batch_reads = (len(payload) - 4) // READ_SIZE_BYTES
        total_sent += batch_reads
        batch_index += 1

        if progress:
            progress.update_upload_progress(total_sent, total_reads)

    if progress:
        progress.update_upload_progress(total_reads, total_reads)
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

    bit_string = "".join("01"[(payload[idx // 8] >> (idx % 8)) & 1] for idx in range(len(payload) * 8))
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
    if not config.skip_wm and not watermark_path.exists():
        raise FileNotFoundError(f"Watermark file does not exist: {watermark_path}")

    info = analyze_reads_file(reads_path, config.format)
    total_reads = config.resolve_total(info.total_reads if info.total_reads else DEFAULT_TOTAL_READS)
    if total_reads > MAX_TOTAL_READS:
        raise ValueError(f"Read count {total_reads} exceeds hardware limit {MAX_TOTAL_READS}")

    progress = progress or ProgressCallbacks()

    log_info(log, f"[INFO] Connecting to {config.ip}:{config.port}")
    log_info(
        log,
        f"[INFO] Reads file: {reads_path} ({info.total_reads} reads detected, format {info.format.upper()})",
    )
    if config.send_limit and config.send_limit < info.total_reads:
        log_info(log, f"[INFO] Will only send first {total_reads} reads (user limited)")
    else:
        log_info(log, f"[INFO] Sending {total_reads} reads")
    log_info(log, f"[INFO] Output file: {output_path}")

    with socket.create_connection((config.ip, config.port)) as sock:
        t_start = perf_counter()

        if config.skip_wm:
            log_info(log, "[1/4] Skipping watermark upload (user request)")
        else:
            if stop_requested():
                raise OperationCancelled("Operation cancelled")
            progress.set_status("上传水印...")
            t0 = perf_counter()
            wm_size = send_watermark(sock, watermark_path, stats)
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
            total_reads,
            stats,
            batch_size=config.batch,
            format_type=info.format,
            stop_check=stop_requested,
            progress=progress,
        )
        stats.t_batches = perf_counter() - t0
        reads_bytes = total_reads * READ_SIZE_BYTES
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

        if stop_requested():
            raise OperationCancelled("Operation cancelled")

        progress.set_status("接收结果...")
        progress.set_stage("RESULT")
        t0 = perf_counter()
        result_size = recv_result(sock, stats, output_path, timeout=180.0)
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
    parser.add_argument("--skip-watermark", action="store_true", help="跳过水印发送")
    parser.add_argument("--no-post", action="store_true", help="不发送POST触发命令")
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
        post=not args.no_post,
        format=args.format,
    )

    stats = run_client(config, log=lambda msg: print(msg))
    print(format_metric_report(stats))
    print(f"\n结果已保存到: {Path(config.out).resolve()}")


if __name__ == "__main__":
    main()
