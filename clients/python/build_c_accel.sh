#!/usr/bin/env bash
# 编译 C 语言 LDPC 极速译码核心共享库
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "${SCRIPT_DIR}"

SRC="c_ldpc_accel.c"
OUT_DIR="resources"
OUT_SO="${OUT_DIR}/libc_ldpc.so"
SOURCES_JSON="${OUT_DIR}/SOURCES.json"

if ! command -v python3 >/dev/null 2>&1; then
    echo "[ERROR] 未检测到 python3，无法刷新 ${SOURCES_JSON}。" >&2
    exit 1
fi

if [[ ! -f "${SOURCES_JSON}" ]]; then
    echo "[ERROR] 缺少资源同源清单: ${SOURCES_JSON}" >&2
    exit 1
fi

mkdir -p "${OUT_DIR}"

if command -v gcc >/dev/null 2>&1; then
    echo "[BUILD] 正在使用 gcc 编译 ${SRC} -> ${OUT_SO} ..."
    gcc -O3 -fPIC -shared -Wall -Wextra "${SRC}" -o "${OUT_SO}"
    python3 - "${OUT_SO}" "${SOURCES_JSON}" <<'PY'
import hashlib
import json
import platform
import sys
from pathlib import Path

library_path = Path(sys.argv[1])
manifest_path = Path(sys.argv[2])
manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
entry = next(
    (item for item in manifest.get("resources", []) if item.get("file") == library_path.name),
    None,
)
if entry is None:
    raise SystemExit(f"[ERROR] 清单未登记 {library_path.name}，拒绝写入新哈希")

digest = hashlib.sha256(library_path.read_bytes()).hexdigest()
entry["sha256"] = digest
entry["build_command"] = (
    "gcc -O3 -fPIC -shared -Wall -Wextra c_ldpc_accel.c "
    "-o resources/libc_ldpc.so"
)
entry["platform"] = f"Linux {platform.machine()} ELF shared library"
manifest_path.write_text(
    json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
    encoding="utf-8",
)
print(f"[BUILD] 已刷新 {manifest_path} 中 {library_path.name} 的 SHA-256: {digest}")
PY
    echo "[BUILD] 编译成功: ${OUT_SO} ($(ls -lh "${OUT_SO}" | awk '{print $5}'))"
else
    echo "[ERROR] 未检测到 gcc 编译器，无法构建共享库。" >&2
    exit 1
fi
