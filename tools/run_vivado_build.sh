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

if [[ "${1:-}" == "--help" || "${1:-}" == "-h" ]]; then
    cat <<'HELP'
用法：tools/run_vivado_build.sh [key=value ...]
参数：board=zynq_eco_7010|bkb220 part_name=... proj_name=... clk_mhz=100
      build_dir=... export_dir=... report_dir=... jobs=8
      stage1_p_ways=4|16 stage1_pipe_tree=0|1 dry_run=0|1
新板资料未验证时必须失败；P4默认保持旧板；P16必须16/1并使用独立目录。
配置预检可直接运行：tclsh hw/scripts/build.tcl board=... dry_run=1
Windows2026.1请对只读源码快照调用vivado.bat，并使用Windows本地生成目录。
HELP
    exit 0
fi
for arg in "$@"; do
    if [[ ! "$arg" =~ ^[a-z0-9_]+= ]]; then
        printf '非法参数：%s（需要 key=value）\n' "$arg" >&2
        exit 2
    fi
done

cd "$RUN_DIR"

printf 'Vivado: %s\n日志目录: %s\n' "$VIVADO_BIN" "$RUN_DIR"
exec "$VIVADO_BIN" \
    -mode batch \
    -journal "$RUN_DIR/vivado.jou" \
    -log "$RUN_DIR/vivado.log" \
    -source "$ROOT/hw/scripts/build.tcl" \
    -tclargs "$@"
