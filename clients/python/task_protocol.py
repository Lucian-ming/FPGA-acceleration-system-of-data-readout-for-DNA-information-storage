#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""任务配置与板端能力的纯数据模型。"""

from __future__ import annotations

import struct
import zlib
from dataclasses import dataclass

TASK_PROTO_VERSION = 1
TASK_NUM_LC = 50
READ_BASES = 150            # SE150 默认；SE250 显式传 read_bps=250
SE250_READ_BASES = 250
# 一套比特流只服务一种几何（几何是综合期常量），客户端这层先挡一道，
# 与板端 PKT_CONFIG 拒绝码 2 同义（task_config.h:113-114）。
SUPPORTED_READ_BASES = (150, 250)
FRAME_READS = 64
MAX_TOTAL_READS = 107_968   # = (TOTAL_READS/64)*64，echo.h:27,52；SE250 全量需 129_600
CONFIG_PAYLOAD_LEN = 44
CAPS_PAYLOAD_LEN = 24


def read_size_bytes(read_bps: int = READ_BASES) -> int:
    """一条读段在线上占多少字节。

    位平面编码是 2 bit/碱基 = 2*read_bps bit，但 DNA 核的 AXIS 是 32 bit
    （`Dna_accelerator_core_v1_0.v:16`），所以必须向上对齐到 4 B：
        SE150  ceil(300/8) = 38 → **40**
        SE250  ceil(500/8) = 63 → **64**
    对齐这一步不能省成 63 —— 入口是按整拍收的，少一拍整条记录就错位
    （docs/20 §1.4 与 §3.5 的 S2）。
    """
    return ((2 * read_bps + 31) // 32) * 4


def default_score_min(read_bps: int = READ_BASES) -> int:
    """比对分阈值 int(0.45*read_bps)：SE150 → 67，SE250 → 112。

    这个 0.45 必须和黄金向量同源（`make_golden.py --min-score 0.45`）。
    docs/20 §2.2 的阈值扫描表明 0.45 对两个数据集都落在
    「真方向过阈 ~98 %、假方向 0 %」的平台区里。
    """
    return int(0.45 * read_bps)

CONFIG_REJECT_REASONS = {
    1: "协议版本不支持",
    2: "read_bps 不被支持",
    3: "几何与比特流不符",
    4: "symbols 契约不满足",
    5: "total_reads 非法",
    6: "score_min 超范围",
    7: "CRC32 不符",
    8: "重复 CONFIG",
    9: "顺序非法",
}


@dataclass(frozen=True)
class TaskCaps:
    """PKT_CAPS_INFO 返回的板端能力。"""

    version: int
    read_bps: int
    num_lc: int
    stride: int
    max_symbols: int
    max_reads: int
    features: int

    @classmethod
    def from_payload(cls, payload: bytes) -> "TaskCaps":
        if len(payload) != CAPS_PAYLOAD_LEN:
            raise ValueError(
                f"CAPS_INFO 长度应为 {CAPS_PAYLOAD_LEN} B，实得 {len(payload)} B"
            )
        version, read_bps, reserved, num_lc, stride, max_symbols, max_reads, features = \
            struct.unpack(">BBHIIIII", payload)
        if reserved != 0:
            raise ValueError(f"CAPS_INFO reserved 非零: 0x{reserved:04X}")
        return cls(version, read_bps, num_lc, stride, max_symbols, max_reads, features)


@dataclass(frozen=True)
class TaskSpec:
    """一次任务的完整几何与协议参数。"""

    read_bps: int
    num_lc: int
    stride: int
    symbols: int
    total_reads: int
    score_min: int
    version: int = TASK_PROTO_VERSION

    @property
    def watermark_bits(self) -> int:
        return self.symbols * 2

    @classmethod
    def from_watermark_bits(
        cls,
        watermark_bits: int,
        *,
        total_reads: int,
        score_min: int,
        read_bps: int = READ_BASES,
        num_lc: int = TASK_NUM_LC,
    ) -> "TaskSpec":
        if watermark_bits <= 0 or watermark_bits % 2:
            raise ValueError(f"水印位数必须为正偶数，实得 {watermark_bits}")
        symbols = watermark_bits // 2
        if symbols <= read_bps:
            raise ValueError(f"水印符号数 {symbols} <= 读段长度 {read_bps}")
        span = symbols - read_bps
        if span % num_lc:
            raise ValueError(
                f"水印符号数 {symbols} 不满足 L={num_lc}*STRIDE+{read_bps}"
            )
        spec = cls(
            read_bps=read_bps,
            num_lc=num_lc,
            stride=span // num_lc,
            symbols=symbols,
            total_reads=total_reads,
            score_min=score_min,
        )
        spec.validate()
        return spec

    @property
    def read_size_bytes(self) -> int:
        """本任务每条读段的线上字节数（SE150 40 B / SE250 64 B）。"""
        return read_size_bytes(self.read_bps)

    def validate(self) -> None:
        if self.version != TASK_PROTO_VERSION:
            raise ValueError(f"任务协议版本必须为 {TASK_PROTO_VERSION}")
        if self.read_bps not in SUPPORTED_READ_BASES:
            raise ValueError(
                f"read_bps={self.read_bps} 不在客户端支持的 {SUPPORTED_READ_BASES}；"
                "一套比特流只服务一种几何，混用会被板端 PKT_CONFIG 拒绝码 2 拒掉"
            )
        if self.symbols != self.num_lc * self.stride + self.read_bps:
            raise ValueError("任务几何不满足 symbols=num_lc*stride+read_bps")
        if self.total_reads <= 0 or self.total_reads % FRAME_READS:
            raise ValueError(f"total_reads 必须为 {FRAME_READS} 的正整数倍")
        if self.total_reads > MAX_TOTAL_READS:
            raise ValueError(
                f"total_reads={self.total_reads} 超过客户端上限 {MAX_TOTAL_READS}"
            )
        if not 0 <= self.score_min <= 1023:
            raise ValueError("score_min 必须在 0..1023")

    def validate_caps(self, caps: TaskCaps) -> None:
        if caps.version != self.version:
            raise ValueError(f"板端协议 v{caps.version} 与任务 v{self.version} 不匹配")
        if caps.read_bps != self.read_bps:
            raise ValueError(f"板端只支持 {caps.read_bps}bp，本任务需要 {self.read_bps}bp")
        if caps.num_lc != self.num_lc or caps.stride != self.stride:
            raise ValueError(
                f"板端几何 {caps.num_lc}x{caps.stride} 与任务 "
                f"{self.num_lc}x{self.stride} 不匹配"
            )
        if caps.max_symbols != self.symbols:
            raise ValueError(
                f"板端综合水印长度 {caps.max_symbols} symbols，任务为 {self.symbols}"
            )
        if self.total_reads > caps.max_reads:
            raise ValueError(
                f"发送量 {self.total_reads} 超过板端容量 {caps.max_reads}"
            )
        if not (caps.features & 0x1) and self.score_min != 0:
            raise ValueError("板端不支持 SCORE_MIN，但任务请求了非零阈值")

    def config_payload(self) -> bytes:
        self.validate()
        body = struct.pack(
            ">BBHIIIII",
            self.version,
            self.read_bps,
            0,
            self.num_lc,
            self.stride,
            self.symbols,
            self.total_reads,
            self.score_min,
        ) + b"\x00" * 16
        payload = body + struct.pack(">I", zlib.crc32(body) & 0xFFFFFFFF)
        if len(payload) != CONFIG_PAYLOAD_LEN:
            raise AssertionError(f"CONFIG payload 长度异常: {len(payload)}")
        return payload


def build_config_payload(
    *,
    read_bps: int,
    num_lc: int,
    stride: int,
    symbols: int,
    total_reads: int,
    score_min: int,
) -> bytes:
    """兼容旧调用方的 CONFIG 纯函数入口。"""
    return TaskSpec(
        read_bps=read_bps,
        num_lc=num_lc,
        stride=stride,
        symbols=symbols,
        total_reads=total_reads,
        score_min=score_min,
    ).config_payload()
