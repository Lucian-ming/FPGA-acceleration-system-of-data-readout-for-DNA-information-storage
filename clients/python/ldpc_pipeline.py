#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""LDPC 译码流水线：默认原生 Python，外部 EXE 仅显式启用。"""

from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional

from native_ldpc import bits_to_jpeg_bytes, decode_file, read_bit_text

DECODER_EXE = "R5_6_LDPC_hard_decoder.exe"
DECODER_PCHK = "dvb_s2_r5_6.pchk"
DECODER_PERM = "permutation64800"
DECODER_DLLS = ("libstdc++-6.dll", "libgcc_s_seh-1.dll", "libwinpthread-1.dll")
DEC_INPUT_NAME = "dec_input.txt"
DECODER_OUTPUT_BITS = "TestBitStream.txt"
DECODER_OUTPUT_IMAGE = "image.jpg"
SUPPORTED_BACKENDS = ("auto", "native", "external")


@dataclass
class LDPCResult:
    """译码输出及实际使用的后端。"""

    result_path: Path
    dec_input_path: Path
    decoded_bits_path: Path
    image_path: Path
    backend: str


def _bundle_root() -> Path:
    if hasattr(sys, "_MEIPASS"):
        return Path(sys._MEIPASS)  # type: ignore[attr-defined]
    return Path(__file__).resolve().parent


def resource_path(name: str) -> Path:
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
    source = resource_path(filename)
    target = target_dir / filename
    if source.resolve() != target.resolve():
        shutil.copy2(source, target)
    return target


def _write_dec_input(result_bits_path: Path, output_dir: Path) -> tuple[str, Path]:
    bits = read_bit_text(result_bits_path)
    if result_bits_path.name == DEC_INPUT_NAME and result_bits_path.parent.resolve() == output_dir.resolve():
        dec_input_path = result_bits_path
    else:
        dec_input_path = output_dir / DEC_INPUT_NAME
        dec_input_path.write_text(bits, encoding="utf-8")
    return bits, dec_input_path


def _run_native(
    result_bits_path: Path,
    output_dir: Path,
    dec_input_path: Path,
    log: Callable[[str], None],
) -> LDPCResult:
    pchk = resource_path(DECODER_PCHK)
    permutation = resource_path(DECODER_PERM)
    info, _codeword, failed, iterations = decode_file(
        dec_input_path, pchk, permutation
    )

    decoded_bits_path = output_dir / "decoded_bits.txt"
    image_path = output_dir / "decoded_image.jpg"
    decoded_bits_path.write_text("".join("01"[int(bit)] for bit in info), encoding="utf-8")
    image_path.write_bytes(bits_to_jpeg_bytes(info))
    log(f"[LDPC] native 收敛：起始失败校验 {failed}，迭代 {iterations} 轮")
    log(f"[LDPC] 已保存解码比特 {decoded_bits_path}")
    log(f"[LDPC] 已保存图像 {image_path}")
    return LDPCResult(
        result_path=result_bits_path,
        dec_input_path=dec_input_path,
        decoded_bits_path=decoded_bits_path,
        image_path=image_path,
        backend="native",
    )


def _run_external(
    result_bits_path: Path,
    output_dir: Path,
    dec_input_path: Path,
    bits: str,
    log: Callable[[str], None],
) -> LDPCResult:
    workspace = Path(tempfile.mkdtemp(prefix="ldpc_", dir=output_dir))
    log(f"[LDPC] external 工作目录: {workspace}")
    try:
        decoder_exe = _copy_resource(workspace, DECODER_EXE)
        _copy_resource(workspace, DECODER_PCHK)
        _copy_resource(workspace, DECODER_PERM)
        missing_dlls = []
        for name in DECODER_DLLS:
            try:
                resource_path(name)
            except FileNotFoundError:
                missing_dlls.append(name)
        if missing_dlls:
            raise FileNotFoundError(
                "external LDPC 缺少 MinGW 运行时: " + ", ".join(missing_dlls)
            )
        for dll in DECODER_DLLS:
            _copy_resource(workspace, dll)

        (workspace / DEC_INPUT_NAME).write_text(bits, encoding="utf-8")
        command = [
            str(decoder_exe),
            DEC_INPUT_NAME,
            DECODER_OUTPUT_BITS,
            DECODER_OUTPUT_IMAGE,
            "H",
        ]
        log(f"[LDPC] 运行 external 后端: {' '.join(command)}")
        try:
            process = subprocess.run(
                command,
                cwd=workspace,
                capture_output=True,
                text=True,
                check=False,
            )
        except OSError as exc:
            raise RuntimeError(f"external LDPC 无法启动: {exc}") from exc
        if process.returncode != 0:
            detail = process.stderr.strip() or process.stdout.strip()
            raise RuntimeError(f"external LDPC 失败 (exit={process.returncode}): {detail}")

        decoded_source = workspace / DECODER_OUTPUT_BITS
        image_source = workspace / DECODER_OUTPUT_IMAGE
        if not decoded_source.is_file() or not image_source.is_file():
            raise RuntimeError("external LDPC 已退出但未生成解码比特或图像")

        decoded_bits_path = output_dir / "decoded_bits.txt"
        image_path = output_dir / "decoded_image.jpg"
        shutil.copy2(decoded_source, decoded_bits_path)
        shutil.copy2(image_source, image_path)
        return LDPCResult(
            result_path=result_bits_path,
            dec_input_path=dec_input_path,
            decoded_bits_path=decoded_bits_path,
            image_path=image_path,
            backend="external",
        )
    finally:
        shutil.rmtree(workspace, ignore_errors=True)


def run_ldpc_decoder(
    result_bits_path: Path,
    *,
    output_dir: Path,
    backend: str = "auto",
    log: Optional[Callable[[str], None]] = None,
) -> LDPCResult:
    """译码板端回传。

    auto 与 native 都使用仓库内的可审计 Python 实现；只有显式指定
    external 才会运行 Windows EXE，绝不静默回退。
    """
    if backend not in SUPPORTED_BACKENDS:
        raise ValueError(f"未知 LDPC backend={backend!r}，可选 {SUPPORTED_BACKENDS}")
    if not result_bits_path.is_file():
        raise FileNotFoundError(f"结果文件不存在: {result_bits_path}")

    output_dir.mkdir(parents=True, exist_ok=True)
    emit = log or (lambda _message: None)
    bits, dec_input_path = _write_dec_input(result_bits_path, output_dir)
    selected = "native" if backend == "auto" else backend
    emit(f"[LDPC] 后端: {selected}")
    emit(f"[LDPC] 输入: {result_bits_path} ({len(bits)} bit)")

    if selected == "native":
        return _run_native(result_bits_path, output_dir, dec_input_path, emit)
    return _run_external(result_bits_path, output_dir, dec_input_path, bits, emit)
