#!/usr/bin/env bash
# 编译 C 语言 LDPC 极速译码核心共享库
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "${SCRIPT_DIR}"

SRC="c_ldpc_accel.c"
OUT_DIR="resources"
OUT_SO="${OUT_DIR}/libc_ldpc.so"

mkdir -p "${OUT_DIR}"

if command -v gcc >/dev/null 2>&1; then
    echo "[BUILD] 正在使用 gcc 编译 ${SRC} -> ${OUT_SO} ..."
    gcc -O3 -fPIC -shared -Wall -Wextra "${SRC}" -o "${OUT_SO}"
    echo "[BUILD] 编译成功: ${OUT_SO} ($(ls -lh "${OUT_SO}" | awk '{print $5}'))"
else
    echo "[ERROR] 未检测到 gcc 编译器，无法构建共享库。" >&2
    exit 1
fi
