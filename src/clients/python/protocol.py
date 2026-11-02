#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""DNA 加速器 TCP 协议编解码与网络交互。"""

from __future__ import annotations

import socket
import struct
from typing import Callable, Optional

from task_protocol import CONFIG_REJECT_REASONS, TaskCaps, TaskSpec

MAGIC = 0xBEEF
HDR_FMT = ">HBBI"
HDR_SZ = struct.calcsize(HDR_FMT)

PKT_CONFIG = 0x05
PKT_CAPS = 0x06
PKT_WM = 0x01
PKT_BATCH = 0x02
PKT_POST = 0x03
PKT_RESULT = 0x04
PKT_WM_OK = 0x11
PKT_BATCH_OK = 0x12
PKT_CONFIG_OK = 0x15
PKT_CAPS_INFO = 0x16
PKT_ERROR = 0xEE


class NetStats:
    """记录一次会话的网络量与各阶段耗时。"""

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

    @staticmethod
    def mbps(bytes_: int, seconds: float) -> float:
        return 0.0 if seconds <= 0 else (bytes_ * 8) / seconds / 1e6


def sendall_count(stats: NetStats, sock: socket.socket, data: bytes) -> None:
    sock.sendall(data)
    stats.upload += len(data)


def make_header(pkt_type: int, payload_len: int) -> bytes:
    if not 0 <= pkt_type <= 0xFF:
        raise ValueError(f"包类型越界: {pkt_type}")
    if not 0 <= payload_len <= 0xFFFFFFFF:
        raise ValueError(f"payload_len 越界: {payload_len}")
    return struct.pack(HDR_FMT, MAGIC, pkt_type, 0, payload_len)


def make_packet(pkt_type: int, payload: bytes = b"") -> bytes:
    return make_header(pkt_type, len(payload)) + payload


def recv_exact(sock: socket.socket, n: int, stats: NetStats, timeout: float = 60.0) -> bytes:
    if n < 0:
        raise ValueError("接收长度不能为负数")
    sock.settimeout(timeout)
    buf = bytearray()
    while len(buf) < n:
        chunk = sock.recv(n - len(buf))
        if not chunk:
            raise ConnectionError("连接在接收完整数据前关闭")
        buf.extend(chunk)
        stats.download += len(chunk)
    return bytes(buf)


def recv_packet(sock: socket.socket, stats: NetStats, timeout: float = 60.0) -> tuple[int, bytes]:
    header = recv_exact(sock, HDR_SZ, stats, timeout=timeout)
    magic, pkt_type, reserved, length = struct.unpack(HDR_FMT, header)
    if magic != MAGIC:
        raise ValueError(f"包头 magic 异常: 0x{magic:04X}")
    if reserved != 0:
        raise ValueError(f"包头 reserved 非零: 0x{reserved:02X}")
    payload = recv_exact(sock, length, stats, timeout=timeout) if length else b""
    return pkt_type, payload


def recv_ack_byte(
    sock: socket.socket,
    stats: NetStats,
    expected: int,
    timeout: float = 10.0,
) -> bool:
    """兼容旧调用方；新代码优先使用 expect_ack() 获得诊断信息。"""
    return recv_exact(sock, 1, stats, timeout=timeout)[0] == expected


def expect_ack(
    sock: socket.socket,
    stats: NetStats,
    expected: int,
    *,
    operation: str,
    timeout: float = 10.0,
) -> None:
    actual = recv_exact(sock, 1, stats, timeout=timeout)[0]
    if actual == PKT_ERROR:
        raise RuntimeError(f"板端拒绝 {operation}（PKT_ERROR=0x{PKT_ERROR:02X}）")
    if actual != expected:
        raise RuntimeError(
            f"{operation} ACK 异常：期望 0x{expected:02X}，实得 0x{actual:02X}"
        )


def query_caps(sock: socket.socket, stats: NetStats) -> TaskCaps:
    sendall_count(stats, sock, make_packet(PKT_CAPS))
    pkt_type, payload = recv_packet(sock, stats, timeout=30.0)
    if pkt_type != PKT_CAPS_INFO:
        raise RuntimeError(
            f"板端未按 P3 协议应答 PKT_CAPS（得到 0x{pkt_type:02X}）。"
            "请确认固件是 2026-08-16 之后构建的 ELF"
        )
    return TaskCaps.from_payload(payload)


def send_config(
    sock: socket.socket,
    stats: NetStats,
    task: TaskSpec,
    *,
    log: Optional[Callable[[str], None]] = None,
) -> None:
    sendall_count(stats, sock, make_packet(PKT_CONFIG, task.config_payload()))
    pkt_type, payload = recv_packet(sock, stats, timeout=30.0)
    if pkt_type != PKT_CONFIG_OK or len(payload) != 4:
        raise RuntimeError(
            f"板端未按 P3 协议应答 PKT_CONFIG（得到 0x{pkt_type:02X}/{len(payload)}B）"
        )
    code = struct.unpack(">I", payload)[0]
    if code:
        raise RuntimeError(
            f"PKT_CONFIG 被拒绝（码 {code}）：{CONFIG_REJECT_REASONS.get(code, '未知')}"
        )
    if log:
        log(
            f"[INFO] CONFIG 接受：L={task.symbols} "
            f"({task.num_lc}x{task.stride}+{task.read_bps}), "
            f"reads={task.total_reads}, score_min={task.score_min}"
        )
