#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Utility helpers to run the bundled LDPC decoder pipeline."""

from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional

DECODER_EXE = "R5_6_LDPC_hard_decoder.exe"
DECODER_PCHK = "dvb_s2_r5_6.pchk"
DECODER_PERM = "permutation64800"
# 解码器是 MinGW 构建，运行时依赖这三个 DLL。缺失时它不报错、不输出、退出码仍为 0，
# 极易被误判成输入数据有问题。来源见 tools/extract_ldpc_dlls.py。
DECODER_DLLS = ("libstdc++-6.dll", "libgcc_s_seh-1.dll", "libwinpthread-1.dll")
DEC_INPUT_NAME = "dec_input.txt"
DECODER_OUTPUT_BITS = "TestBitStream.txt"
DECODER_OUTPUT_IMAGE = "image.jpg"


@dataclass()  # 注意: 原为 slots=True，仅为省内存但会把最低版本抬到 Py3.10，去掉以便更广泛地运行与测试
class LDPCResult:
    """Summary of decoder outputs."""

    result_path: Path
    dec_input_path: Path
    decoded_bits_path: Path
    image_path: Path


def _bundle_root() -> Path:
    """Return base directory that hosts bundled resources."""
    if hasattr(sys, "_MEIPASS"):
        return Path(sys._MEIPASS)  # type: ignore[attr-defined]
    return Path(__file__).resolve().parent


def resource_path(name: str) -> Path:
    """Locate a bundled resource by trying common layouts."""
    base = _bundle_root()
    candidates = [
        base / name,
        base / "resources" / name,
        Path(__file__).resolve().parent / name,
        Path(__file__).resolve().parent / "resources" / name,
    ]

    for candidate in candidates:
        if candidate.exists():
            return candidate
    raise FileNotFoundError(f"无法找到资源文件: {name}")


def _copy_resource(target_dir: Path, filename: str) -> Path:
    src = resource_path(filename)
    dst = target_dir / filename
    if src.resolve() != dst.resolve():
        shutil.copy2(src, dst)
    return dst


def run_ldpc_decoder(
    result_bits_path: Path,
    *,
    output_dir: Path,
    log: Optional[Callable[[str], None]] = None,
) -> LDPCResult:
    """Run the external LDPC decoder and collect outputs."""

    def log_info(message: str) -> None:
        if log:
            log(message)

    if not result_bits_path.exists():
        raise FileNotFoundError(f"结果文件不存在: {result_bits_path}")

    output_dir.mkdir(parents=True, exist_ok=True)

    workspace = Path(tempfile.mkdtemp(prefix="ldpc_", dir=output_dir))

    log_info(f"[LDPC] 工作目录: {workspace}")

    decoder_exe = _copy_resource(workspace, DECODER_EXE)
    _copy_resource(workspace, DECODER_PCHK)
    _copy_resource(workspace, DECODER_PERM)
    for dll in DECODER_DLLS:
        try:
            _copy_resource(workspace, dll)
        except FileNotFoundError:
            log_info(f"[LDPC] 警告: 缺少运行时 {dll}，解码器可能静默失败；"
                     f"可用 tools/extract_ldpc_dlls.py 从历史 gui_app.exe 提取")

    # 1. 把板端回传的比特流写入解码器工作目录
    result_bits = result_bits_path.read_text(encoding="utf-8")
    log_info(f"[LDPC] 读取板端结果: {result_bits_path} ({len(result_bits)} 字符)")

    dec_input_workspace = workspace / DEC_INPUT_NAME
    dec_input_workspace.write_text(result_bits, encoding="utf-8")
    log_info(f"[LDPC] 已写入 {dec_input_workspace.name} ({len(result_bits)} 字符)")

    if result_bits_path.name == DEC_INPUT_NAME:
        dec_input_output = result_bits_path
    else:
        dec_input_output = output_dir / DEC_INPUT_NAME
        dec_input_output.write_text(result_bits, encoding="utf-8")
        log_info(f"[LDPC] 已另存 {dec_input_output.name}")

    # 2. 调用外部 LDPC 解码器
    cmd = [
        str(decoder_exe),
        DEC_INPUT_NAME,
        DECODER_OUTPUT_BITS,
        DECODER_OUTPUT_IMAGE,
        "H",
    ]
    log_info(f"[LDPC] 运行命令: {' '.join(cmd)}")

    proc = subprocess.run(cmd, cwd=workspace, capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError(
            f"LDPC 解码失败 (exit={proc.returncode}): {proc.stderr.strip() or proc.stdout.strip()}"
        )

    log_info("[LDPC] 解码完成")

    # 3. 复制输出
    decoded_bits_src = workspace / DECODER_OUTPUT_BITS
    image_src = workspace / DECODER_OUTPUT_IMAGE

    if not decoded_bits_src.exists() or not image_src.exists():
        raise FileNotFoundError(
            "解码输出缺失。解码器已退出但没有产出文件——最常见的原因是缺少 MinGW 运行时 "
            f"({', '.join(DECODER_DLLS)})，此时它不报错、退出码仍为 0。"
            "请确认 clients/python/resources/ 下这三个 DLL 存在。"
        )

    decoded_bits_dst = output_dir / "decoded_bits.txt"
    image_dst = output_dir / "decoded_image.jpg"

    shutil.copy2(decoded_bits_src, decoded_bits_dst)
    shutil.copy2(image_src, image_dst)

    log_info(f"[LDPC] 已保存解码比特 {decoded_bits_dst}")
    log_info(f"[LDPC] 已保存图像 {image_dst}")

    shutil.rmtree(workspace, ignore_errors=True)

    return LDPCResult(
        result_path=result_bits_path,
        dec_input_path=dec_input_output,
        decoded_bits_path=decoded_bits_dst,
        image_path=image_dst,
    )
