#!/usr/bin/env bash
# Git Bash 入口：等价于 run_build.bat。
set -euo pipefail
cd "$(dirname "$0")"
: "${VIVADO_BAT:?请先设置 VIVADO_BAT 指向 Vivado 2026.1 的 vivado.bat}"
[ -f "$VIVADO_BAT" ] || { echo "找不到 Vivado：$VIVADO_BAT" >&2; exit 1; }
mkdir -p logs
exec "$VIVADO_BAT" -mode batch -log "logs/vivado.log" -journal "logs/vivado.jou" -source "build_driver.tcl"
