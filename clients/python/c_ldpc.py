#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""C 语言极速 LDPC 译码核心的 ctypes 绑定与运行时加速器。"""

from __future__ import annotations

import ctypes
import os
import sys
from pathlib import Path
from typing import Optional, Tuple

import numpy as np

M_ROWS = 10_800
N_BITS = 64_800
K_INFO = 54_000
PARITY_COLS = 10_800

# 全局单例解码器句柄缓存，避免重复解析 1MB+ 的 pchk 校验矩阵
_CACHED_DECODER: Optional["CLDPCDecoder"] = None


class CLDPCDecoder:
    """C 原生 LDPC 译码器生命周期与调用封装。"""

    def __init__(self, lib_path: Path, pchk_path: Path, perm_path: Path):
        self._lib = ctypes.CDLL(str(lib_path))

        # 声明 C 函数原型
        self._lib.ldpc_create.argtypes = [ctypes.c_char_p, ctypes.c_char_p]
        self._lib.ldpc_create.restype = ctypes.c_void_p

        self._lib.ldpc_destroy.argtypes = [ctypes.c_void_p]
        self._lib.ldpc_destroy.restype = None

        self._lib.ldpc_decode.argtypes = [
            ctypes.c_void_p,
            ctypes.POINTER(ctypes.c_uint8),
            ctypes.POINTER(ctypes.c_uint8),
            ctypes.c_int,
            ctypes.POINTER(ctypes.c_int),
            ctypes.POINTER(ctypes.c_int),
        ]
        self._lib.ldpc_decode.restype = ctypes.c_int

        self._handle = self._lib.ldpc_create(
            str(pchk_path).encode("utf-8"),
            str(perm_path).encode("utf-8"),
        )
        if not self._handle:
            raise RuntimeError(
                f"初始化 C LDPC 译码器失败: pchk={pchk_path}, perm={perm_path}"
            )
        self.pchk_path = pchk_path
        self.perm_path = perm_path

    def __del__(self):
        if hasattr(self, "_handle") and self._handle and hasattr(self, "_lib"):
            self._lib.ldpc_destroy(self._handle)
            self._handle = None

    def decode(
        self,
        rx_bits: np.ndarray,
        max_iter: int = 50,
        raise_on_error: bool = True,
    ) -> Tuple[Optional[np.ndarray], int, int]:
        """对接收比特流进行解交织与硬判决翻转译码。

        :param rx_bits: 64800 个 uint8 (0 或 1)
        :param max_iter: 最大迭代轮数
        :param raise_on_error: 译码失败时是否抛出异常；False 时返回 (None, init_failed, iters)
        :return: (info_bits [54000] 或 None, initial_failed, iterations)
        """
        if rx_bits.size != N_BITS:
            raise ValueError(f"输入比特数应为 {N_BITS}，实得 {rx_bits.size}")

        rx_c = np.ascontiguousarray(rx_bits, dtype=np.uint8)
        out_info = np.zeros(K_INFO, dtype=np.uint8)

        initial_failed = ctypes.c_int(0)
        iterations = ctypes.c_int(0)

        rx_ptr = rx_c.ctypes.data_as(ctypes.POINTER(ctypes.c_uint8))
        out_ptr = out_info.ctypes.data_as(ctypes.POINTER(ctypes.c_uint8))

        rc = self._lib.ldpc_decode(
            self._handle,
            rx_ptr,
            out_ptr,
            max_iter,
            ctypes.byref(initial_failed),
            ctypes.byref(iterations),
        )

        if rc != 0:
            if raise_on_error:
                raise RuntimeError(
                    f"C LDPC 译码未收敛（{max_iter} 轮后仍未通过所有校验方程）"
                )
            return None, initial_failed.value, iterations.value

        return out_info, initial_failed.value, iterations.value


def find_c_library() -> Optional[Path]:
    """在资源路径中查找编译好的 C 动态库。"""
    candidates = []
    base_dirs = [
        Path(__file__).resolve().parent / "resources",
        Path(__file__).resolve().parent,
    ]
    if hasattr(sys, "_MEIPASS"):
        base_dirs.insert(0, Path(sys._MEIPASS) / "resources")  # type: ignore
        base_dirs.insert(0, Path(sys._MEIPASS))  # type: ignore

    names = ["libc_ldpc.so", "c_ldpc.dll", "libc_ldpc.dll"]
    for b in base_dirs:
        for name in names:
            candidates.append(b / name)

    for cand in candidates:
        if cand.is_file():
            return cand
    return None


def is_c_accel_available() -> bool:
    """检查 C 加速动态库是否可用。"""
    lib_path = find_c_library()
    return lib_path is not None


def get_cached_decoder(pchk_path: Path, perm_path: Path) -> CLDPCDecoder:
    """获取或初始化全局缓存的 C 译码器实例。"""
    global _CACHED_DECODER
    if (
        _CACHED_DECODER is not None
        and _CACHED_DECODER.pchk_path.resolve() == pchk_path.resolve()
        and _CACHED_DECODER.perm_path.resolve() == perm_path.resolve()
    ):
        return _CACHED_DECODER

    lib_path = find_c_library()
    if not lib_path:
        raise FileNotFoundError("未找到 LDPC C 动态库 (libc_ldpc.so / c_ldpc.dll)")

    _CACHED_DECODER = CLDPCDecoder(lib_path, pchk_path, perm_path)
    return _CACHED_DECODER


def decode_bits_c(
    rx_bits: np.ndarray,
    pchk_path: Path,
    perm_path: Path,
    max_iter: int = 50,
    raise_on_error: bool = True,
) -> Tuple[Optional[np.ndarray], int, int]:
    """使用 C 核心直接对接收的 64,800 比特数组进行解交织与译码。"""
    decoder = get_cached_decoder(pchk_path, perm_path)
    return decoder.decode(rx_bits, max_iter=max_iter, raise_on_error=raise_on_error)
