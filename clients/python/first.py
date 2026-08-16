#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Reusable TCP client core for the DNA accelerator workflow."""

from __future__ import annotations

import argparse
import socket
import struct
import zlib
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

PKT_CONFIG = 0x05           # 【P3】任务配置，必须在 WM/BATCH/POST 之前
PKT_CAPS = 0x06             # 【P3】查询板端能力
PKT_WM = 0x01
PKT_BATCH = 0x02
PKT_POST = 0x03
PKT_RESULT = 0x04
PKT_WM_OK = 0x11
PKT_BATCH_OK = 0x12
PKT_CONFIG_OK = 0x15        # 【P3】带包头，4B 状态码
PKT_CAPS_INFO = 0x16        # 【P3】带包头，24B 能力描述
PKT_ERROR = 0xEE

# 【P3】任务配置（docs/05-interfaces.md 1.1~1.3）
TASK_PROTO_VERSION = 1
TASK_NUM_LC = 50            # 与比特流综合参数一致（换档位需重新综合）
CONFIG_REJECT_REASONS = {
    1: "协议版本不支持", 2: "read_bps 不被支持", 3: "几何与比特流不符",
    4: "symbols 契约不满足", 5: "total_reads 非法", 6: "score_min 超范围",
    7: "CRC32 不符", 8: "重复 CONFIG", 9: "顺序非法",
}

READ_SIZE_BYTES = 40
READ_BASES = 150            # 当前比特流只支持 150 bp；换档位需重新综合
DEFAULT_TOTAL_READS = 2_048  # 实测约 1,080 条即可完整还原，2,048 留足余量
MAX_TOTAL_READS = 107_968   # 板端容量内最大的 64 对齐条数（108000 不是 64 的倍数）
DEFAULT_BATCH_SIZE = 1_000
RESULT_BYTES = 8 * 1024
MAX_WATERMARK = 10_128
WM_ALIGN = 8

# srpe_batch 固定每批 64 条，发送总量必须是它的整数倍，否则尾批会饿死（C2）
FRAME_READS = 64

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


@dataclass()  # 注意: 原为 slots=True，仅为省内存但会把最低版本抬到 Py3.10，去掉以便更广泛地运行与测试
class ReadFileInfo:
    """Metadata extracted from a reads file."""

    path: Path
    format: str
    total_reads: int


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
    score_min: int = 67         # 【P3】经 PKT_CONFIG 下发；67=int(0.45×150)，与黄金向量一致
    dry_run: bool = False       # 【P3】只打印将下发的配置，不连接板端

    def resolve_total(self, detected: int) -> int:
        """Return number of source reads to send.

        【P3 修正】原实现 `min(max(candidates))` 把 --total-reads 和 --limit
        都当成了「抬底」，--limit 2048 在 51,781 条的文件上会取 51,781——
        与帮助文本「最多发送多少条」相反。现在 PKT_CONFIG 会校验
        「声明条数 == 实发条数」，此处必须算对：
          --total-reads N → 恰好 N 条；--limit N → 至多 N 条。
        """
        resolved = detected if self.total is None else self.total
        if self.total is not None and self.total <= 0:
            raise ValueError("--total-reads must be positive")
        if self.send_limit and self.send_limit > 0:
            resolved = min(resolved, self.send_limit)
        resolved = min(resolved, MAX_TOTAL_READS)
        if resolved < 1:
            raise ValueError("Resolved read count must be >= 1")
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
    """把一条 150 bp 序列编码成 40 字节。

    格式见 docs/02-data-contract.md：
      * 位平面布局：码流前 150 位是每个碱基的高位，后 150 位是低位；
      * 字节内 **LSB-first** 打包：码流第 k 位 → 第 k/8 个字节的第 k%8 位。

    LSB-first 是刻意选的：这样 AXIS 上组装出来的 `in_buf[k]` 正好等于码流第 k 位，
    RTL 端不需要任何位反转。原实现用的是 MSB-first，与 RTL 对不上（缺陷 B4）。
    """
    s = seq.strip().upper()
    if len(s) < READ_BASES:
        s += "N" * (READ_BASES - len(s))
    elif len(s) > READ_BASES:
        s = s[:READ_BASES]

    data = bytearray(READ_SIZE_BYTES)
    for idx, base in enumerate(s):
        pair = BASE2BITS.get(base, "00")
        if pair[0] == "1":                       # 高位平面
            data[idx >> 3] |= 1 << (idx & 7)
        if pair[1] == "1":                       # 低位平面
            k = READ_BASES + idx
            data[k >> 3] |= 1 << (k & 7)
    return bytes(data)


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
) -> Iterable[bytes]:
    """产出编码后的读段字节。

    `orient="both"` 时每条源读段发两份：正向 + 反向互补。
    板端 Stage1 会分别给两份打分，Voter 按分数丢掉方向错的那份
    （docs/06-implementation-plan.md P1）。这是必需的：测序数据里约一半读段
    是反向互补的，不发的话即使用满全部读段也无法译码。
    """
    for seq in iter_source_seqs(path, limit, format_type):
        yield seq_to_40B(seq)
        if orient == "both":
            yield seq_to_40B(reverse_complement(seq))


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
) -> Iterable[bytes]:
    """产出 PKT_BATCH 的负载块；不足 send_total 的部分补零读段。"""
    batch: list = []
    count = 0

    def flush():
        header = struct.pack(">I", len(batch))
        return header + b"".join(batch)

    for read in iter_reads(reads_file, source_reads, format_type, orient):
        if count >= send_total:
            break
        batch.append(read)
        count += 1
        if len(batch) >= batch_size:
            yield flush()
            batch.clear()

    # 补零到 64 的整数倍（这些补零读段的比对分接近 0，会被板端阈值丢掉）
    while count < send_total:
        batch.append(b"\x00" * READ_SIZE_BYTES)
        count += 1
        if len(batch) >= batch_size:
            yield flush()
            batch.clear()

    if batch:
        yield flush()

    if count != send_total:
        print(f"[WARN] 预期发送 {send_total} 条读段, 实际生成 {count} 条")


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
# 【P3】任务配置：CAPS 查询 + CONFIG 下发（docs/05-interfaces.md 1.1~1.3）
# ============================================================================
def query_caps(sock: socket.socket, stats: NetStats) -> dict:
    """查询板端能力；板端不实现该协议时给出明确报错。"""
    sendall_count(stats, sock, make_packet(PKT_CAPS, b""))
    pkt_type, payload = recv_packet(sock, stats, timeout=30.0)
    if pkt_type != PKT_CAPS_INFO or len(payload) != 24:
        raise RuntimeError(
            f"板端未按 P3 协议应答 PKT_CAPS（得到 0x{pkt_type:02X}/{len(payload)}B）。"
            "请确认固件是 2026-08-16 之后构建的 ELF")
    version, read_bps, _rsv, num_lc, stride, max_symbols, max_reads, features = \
        struct.unpack(">BBHIIIII", payload)
    return {"version": version, "read_bps": read_bps, "num_lc": num_lc,
            "stride": stride, "max_symbols": max_symbols,
            "max_reads": max_reads, "features": features}


def build_config_payload(*, read_bps: int, num_lc: int, stride: int,
                         symbols: int, total_reads: int, score_min: int) -> bytes:
    """44B PKT_CONFIG 负载：40B 描述 + CRC-32/IEEE（与 zlib.crc32 一致）。"""
    body = struct.pack(">BBHIIIII", TASK_PROTO_VERSION, read_bps, 0,
                       num_lc, stride, symbols, total_reads, score_min) + b"\x00" * 16
    return body + struct.pack(">I", zlib.crc32(body) & 0xFFFFFFFF)


def send_config(sock: socket.socket, stats: NetStats,
                *, read_bps: int, num_lc: int, stride: int, symbols: int,
                total_reads: int, score_min: int,
                log: Optional[Callable[[str], None]] = None) -> None:
    """下发任务配置；板端严格拒绝（非 0 状态码）时抛错。"""
    payload = build_config_payload(read_bps=read_bps, num_lc=num_lc, stride=stride,
                                   symbols=symbols, total_reads=total_reads,
                                   score_min=score_min)
    sendall_count(stats, sock, make_packet(PKT_CONFIG, payload))
    pkt_type, resp = recv_packet(sock, stats, timeout=30.0)
    if pkt_type != PKT_CONFIG_OK or len(resp) != 4:
        raise RuntimeError(f"板端未按 P3 协议应答 PKT_CONFIG（得到 0x{pkt_type:02X}）")
    code = struct.unpack(">I", resp)[0]
    if code != 0:
        raise RuntimeError(f"PKT_CONFIG 被拒绝（码 {code}）："
                           f"{CONFIG_REJECT_REASONS.get(code, '未知')}")
    log_info(log, f"[INFO] CONFIG 接受：L={symbols} ({num_lc}×{stride}+{read_bps}), "
                  f"reads={total_reads}, score_min={score_min}")


# ============================================================================
# 业务流程
# ============================================================================
def send_watermark(sock: socket.socket, wm_file: Path, stats: NetStats) -> int:
    """Encode watermark file and push to the board."""
    text = wm_file.read_text(encoding="utf-8")
    filtered = "".join(ch for ch in text if ch in "01")
    if len(filtered) > 81_000:
        filtered = filtered[:81_000]

    # 与读段一致：码流顺序 + 字节内 LSB-first（docs/02-data-contract.md）。
    # 原实现是 MSB-first，与 RTL / PS 的取位方式对不上。
    payload = bytearray((len(filtered) + 7) // 8)
    for idx, ch in enumerate(filtered):
        if ch == "1":
            payload[idx >> 3] |= 1 << (idx & 7)

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
    source_reads: int,
    send_total: int,
    stats: NetStats,
    *,
    batch_size: int = DEFAULT_BATCH_SIZE,
    format_type: str = "auto",
    orient: str = "both",
    stop_check: Optional[Callable[[], bool]] = None,
    progress: Optional[ProgressCallbacks] = None,
) -> int:
    """Send read batches while updating progress callbacks."""
    total_sent = 0
    batch_index = 0

    for payload in iter_read_batches(reads_file, source_reads, send_total,
                                     batch_size, format_type, orient):
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
    source_reads = config.resolve_total(info.total_reads if info.total_reads else DEFAULT_TOTAL_READS)
    per_read = 2 if config.orient == "both" else 1
    send_total = round_up_frames(source_reads * per_read)
    if send_total > MAX_TOTAL_READS:
        raise ValueError(
            f"发送量 {send_total} 条超过板端上限 {MAX_TOTAL_READS}"
            f"（源读段 {source_reads} 条 × {per_read} 个方向，向上取整到 {FRAME_READS} 的倍数）")

    # 【P3】从水印文件推导任务几何（数据契约：L = NUM_LC×STRIDE + READ_BPS）
    wm_bits = sum(1 for ch in watermark_path.read_text(encoding="utf-8") if ch in "01")
    if wm_bits == 0 or wm_bits % 2:
        raise ValueError(f"水印文件 {watermark_path} 的 0/1 位数异常：{wm_bits}")
    symbols = wm_bits // 2
    read_bps = READ_BASES
    if symbols <= read_bps:
        raise ValueError(f"水印符号数 {symbols} ≤ 读段长度 {read_bps}，无法推导几何")
    stride = (symbols - read_bps) // TASK_NUM_LC
    if TASK_NUM_LC * stride + read_bps != symbols:
        raise ValueError(
            f"水印符号数 {symbols} 不满足契约 L={TASK_NUM_LC}×STRIDE+{read_bps}"
            f"（STRIDE={stride} 有余数）——换档位需重新综合比特流")
    if config.score_min > 1023:
        raise ValueError(f"score_min={config.score_min} 超过比对分 10 bit 上限 1023")

    if config.dry_run:
        payload = build_config_payload(read_bps=read_bps, num_lc=TASK_NUM_LC,
                                       stride=stride, symbols=symbols,
                                       total_reads=send_total,
                                       score_min=config.score_min)
        print("[dry-run] 将下发 PKT_CONFIG(0x05) 44B：")
        print(f"  version={TASK_PROTO_VERSION} read_bps={read_bps} "
              f"num_lc={TASK_NUM_LC} stride={stride} symbols={symbols}")
        print(f"  total_reads={send_total} score_min={config.score_min}")
        print(f"  payload hex = {payload.hex()}")
        return stats

    progress = progress or ProgressCallbacks()

    log_info(log, f"[INFO] Connecting to {config.ip}:{config.port}")
    log_info(
        log,
        f"[INFO] Reads file: {reads_path} ({info.total_reads} reads detected, format {info.format.upper()})",
    )
    log_info(log, f"[INFO] 取用源读段 {source_reads} 条，方向 {config.orient}（每条 {per_read} 份）")
    padding = send_total - source_reads * per_read
    log_info(log, f"[INFO] 实际发送 {send_total} 条（{FRAME_READS} 的整数倍"
                  + (f"，其中补零 {padding} 条" if padding else "") + "）")
    log_info(log, f"[INFO] Output file: {output_path}")

    with socket.create_connection((config.ip, config.port)) as sock:
        t_start = perf_counter()

        # 【P3】先查能力再下发配置（严格拒绝模式：不匹配直接失败）
        caps = query_caps(sock, stats)
        log_info(log, f"[CAPS] v{caps['version']} read_bps={caps['read_bps']} "
                      f"num_lc={caps['num_lc']} stride={caps['stride']} "
                      f"max_reads={caps['max_reads']} features=0x{caps['features']:X}")
        if caps["read_bps"] != read_bps:
            raise ValueError(f"板端只支持 {caps['read_bps']}bp，本任务需要 {read_bps}bp")
        if caps["num_lc"] != TASK_NUM_LC or caps["stride"] != stride:
            raise ValueError(f"板端几何 {caps['num_lc']}×{caps['stride']} 与任务 "
                             f"{TASK_NUM_LC}×{stride} 不符")
        if send_total > caps["max_reads"]:
            raise ValueError(f"发送量 {send_total} 超过板端容量 {caps['max_reads']}")
        send_config(sock, stats, read_bps=read_bps, num_lc=TASK_NUM_LC,
                    stride=stride, symbols=symbols, total_reads=send_total,
                    score_min=config.score_min, log=log)

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
            source_reads,
            send_total,
            stats,
            batch_size=config.batch,
            format_type=info.format,
            orient=config.orient,
            stop_check=stop_requested,
            progress=progress,
        )
        stats.t_batches = perf_counter() - t0
        reads_bytes = send_total * READ_SIZE_BYTES
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
    parser.add_argument("--orient", choices=["both", "forward"], default="both",
                        help="both=每条读段发正向+反向互补（默认，必需）；forward=只发正向（仅作对照实验）")
    parser.add_argument("--skip-watermark", action="store_true", help="跳过水印发送")
    parser.add_argument("--score-min", type=int, default=67,
                        help="PKT_CONFIG 下发的比对分阈值（默认 67=int(0.45×150)，与黄金向量一致）")
    parser.add_argument("--dry-run", action="store_true",
                        help="只打印将下发的 PKT_CONFIG 内容，不连接板端")
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
        orient=args.orient,
        post=not args.no_post,
        format=args.format,
        score_min=args.score_min,
        dry_run=args.dry_run,
    )

    stats = run_client(config, log=lambda msg: print(msg))
    print(format_metric_report(stats))
    print(f"\n结果已保存到: {Path(config.out).resolve()}")


if __name__ == "__main__":
    main()
