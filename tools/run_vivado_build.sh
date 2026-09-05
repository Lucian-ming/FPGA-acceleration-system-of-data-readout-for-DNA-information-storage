#!/usr/bin/env bash
# 在固定归档目录运行 Vivado，避免 vivado.log/vivado.jou 出现在仓库根目录。
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)"
LOG_ROOT="${VIVADO_LOG_ROOT:-$ROOT/logs/vivado}"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)-$$"
RUN_DIR="$LOG_ROOT/$STAMP"
mkdir -p "$RUN_DIR"

if [[ -n "${VIVADO:-}" ]]; then
    VIVADO_BIN="$VIVADO"
elif command -v vivado >/dev/null 2>&1; then
    VIVADO_BIN="$(command -v vivado)"
elif [[ -n "${VIVADO_ROOT:-}" && -x "$VIVADO_ROOT/bin/vivado" ]]; then
    VIVADO_BIN="$VIVADO_ROOT/bin/vivado"
else
    echo "找不到 Vivado；请设置 VIVADO 或 VIVADO_ROOT" >&2
    exit 127
fi

if (($# != 0)); then
    echo "用法：$0（如需额外 Tcl 参数，请直接维护 hw/scripts/build.tcl）" >&2
    exit 2
fi

printf 'Vivado: %s\n日志目录: %s\n' "$VIVADO_BIN" "$RUN_DIR"
exec "$VIVADO_BIN" \
    -mode batch \
    -journal "$RUN_DIR/vivado.jou" \
    -log "$RUN_DIR/vivado.log" \
    -source "$ROOT/hw/scripts/build.tcl"
