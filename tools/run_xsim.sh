#!/usr/bin/env bash
# Vivado/XSim 黄金回归入口。
# 用法：bash tools/run_xsim.sh [all|datapath|axi|stage1|stage2|ingress|dna_axil]
set -uo pipefail

REPO_ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
VIVADO_ROOT=${VIVADO_ROOT:-/tools/Xilinx/Vivado/2022.2}
XVLOG=${XVLOG:-$VIVADO_ROOT/bin/xvlog}
XELAB=${XELAB:-$VIVADO_ROOT/bin/xelab}
XSIM=${XSIM:-$VIVADO_ROOT/bin/xsim}
# 日志判据检索器：优先用 ripgrep，缺失时回退到 POSIX grep -E（模式均为 ERE）。
RG=${RG:-}
if [[ -n "$RG" ]]; then
    LOG_GREP=("$RG")
elif command -v rg >/dev/null 2>&1; then
    LOG_GREP=(rg)
else
    LOG_GREP=(grep -E)
fi
TIMEOUT_SEC=${XSIM_TIMEOUT_SEC:-900}
WHICH=${1:-all}

if [[ ! -x "$XVLOG" || ! -x "$XELAB" || ! -x "$XSIM" ]]; then
    echo "FATAL: Vivado/XSim not found under $VIVADO_ROOT" >&2
    exit 2
fi

RUN_ID=$(date -u +%Y%m%dT%H%M%SZ)
OUT_ROOT=${XSIM_OUT:-$REPO_ROOT/hw/build/xsim/$RUN_ID}
mkdir -p "$OUT_ROOT"

PASS=0
FAIL=0
printf 'XSim run: %s\n' "$RUN_ID" > "$OUT_ROOT/summary.txt"
printf 'repo: %s\n' "$REPO_ROOT" >> "$OUT_ROOT/summary.txt"
printf 'head: %s\n' "$(git -C "$REPO_ROOT" rev-parse HEAD 2>/dev/null || echo unknown)" >> "$OUT_ROOT/summary.txt"
printf 'vivado: ' >> "$OUT_ROOT/summary.txt"
"$XVLOG" -version 2>&1 | sed -n '1p' >> "$OUT_ROOT/summary.txt"

run_case() {
    local name="$1" top="$2"
    shift 2
    local case_dir="$OUT_ROOT/$name"
    local compile_rc=0 elab_rc=0 sim_rc=0 golden_rc=0
    mkdir -p "$case_dir"
    ln -s "$REPO_ROOT/tests" "$case_dir/tests" 2>/dev/null || true
    printf '\n=== %s ===\n' "$name"
    (
        cd "$case_dir" || exit 1
        # xvlog 2022.2 treats .v files as Verilog by default; it has no -2005 switch.
        "$XVLOG" -work work "$@" > xvlog.log 2>&1
    ) || compile_rc=$?
    if [[ "$compile_rc" -eq 0 ]]; then
        (
            cd "$case_dir" || exit 1
            "$XELAB" -debug typical "$top" -s "${name}_sim"
        ) > "$case_dir/xelab.log" 2>&1 || elab_rc=$?
    fi
    if [[ "$compile_rc" -eq 0 && "$elab_rc" -eq 0 ]]; then
        (
            cd "$case_dir" || exit 1
            timeout --foreground "$TIMEOUT_SEC" "$XSIM" "${name}_sim" -runall
        ) > "$case_dir/xsim.log" 2>&1 || sim_rc=$?
    fi
    local log_error=0
    if "${LOG_GREP[@]}" -n 'FATAL:|ERROR:|(^|[[:space:]])FAIL([:[:space:]]|$)|FAILED|\[FAIL\]' \
        "$case_dir/xvlog.log" "$case_dir/xelab.log" "$case_dir/xsim.log" >/dev/null 2>&1; then
        log_error=1
    fi
    if [[ "$compile_rc" -eq 0 && "$elab_rc" -eq 0 && "$sim_rc" -eq 0 \
          && -s "$case_dir/xsim.log" && "$log_error" -eq 0 ]] \
          && "${LOG_GREP[@]}" -n 'PASS' "$case_dir/xsim.log" >/dev/null 2>&1; then
        golden_rc=0
        PASS=$((PASS + 1))
        echo "  PASS ($case_dir)"
    else
        golden_rc=1
        FAIL=$((FAIL + 1))
        echo "  FAIL compile=$compile_rc elaborate=$elab_rc simulate=$sim_rc"
    fi
    {
        printf '%s\tcompile=%s\telaborate=%s\tsimulate=%s\tgolden=%s\n' \
            "$name" "$compile_rc" "$elab_rc" "$sim_rc" "$golden_rc"
        printf '  logs=%s\n' "$case_dir"
    } >> "$OUT_ROOT/summary.txt"
}

DNA=hw/ip/Dna_accelerator_core_1_0/hdl
VOTER=hw/ip/differential_voter_1_0/hdl
DEC=hw/ip/desparsification_decoder_1_0/hdl

if [[ "$WHICH" == all || "$WHICH" == datapath ]]; then
    run_case desparsify_datapath tb_desparsify_datapath \
        "$REPO_ROOT/$DEC/desparsify_datapath.v" \
        "$REPO_ROOT/$DEC/tb_desparsify_datapath.v"
fi
if [[ "$WHICH" == all || "$WHICH" == axi ]]; then
    run_case desparsifier_axi tb_desparsifier \
        "$REPO_ROOT/$DEC/desparsification_decoder_v1_0.v" \
        "$REPO_ROOT/$DEC/desparsify_datapath.v" \
        "$REPO_ROOT/$DEC/tb_desparsifier.v"
fi
if [[ "$WHICH" == all || "$WHICH" == ingress ]]; then
    run_case dna_ingress tb_dna_ingress \
        "$REPO_ROOT/$DNA/Dna_accelerator_core_v1_0.v" \
        "$REPO_ROOT/$DNA/Dna_accelerator_core_v1_0_S_AXI_LITE_CTRL.v" \
        "$REPO_ROOT/$DNA/fifo_sync_sdpram_b64.v" \
        "$REPO_ROOT/$DNA/s2mm_pack64.v" \
        "$REPO_ROOT/$DNA/srpe_batch.v" \
        "$REPO_ROOT/$DNA/tb_dna_ingress.v"
fi
if [[ "$WHICH" == all || "$WHICH" == dna_axil ]]; then
    run_case dna_axil tb_dna_axil \
        "$REPO_ROOT/$DNA/Dna_accelerator_core_v1_0_S_AXI_LITE_CTRL.v" \
        "$REPO_ROOT/$DNA/tb_dna_axil.v"
fi
if [[ "$WHICH" == all || "$WHICH" == stage1 ]]; then
    run_case srpe_batch tb_srpe_batch \
        "$REPO_ROOT/$DNA/srpe_batch.v" \
        "$REPO_ROOT/$DNA/tb_srpe_batch.v"
fi
if [[ "$WHICH" == all || "$WHICH" == stage2 ]]; then
    run_case differential_voter tb_differential_voter \
        "$REPO_ROOT/$VOTER/differential_voter_v1_0.v" \
        "$REPO_ROOT/$VOTER/tb_differential_voter.v"
fi

printf '\n通过 %d 项，失败 %d 项\n' "$PASS" "$FAIL"
printf '通过 %d 项，失败 %d 项\n' "$PASS" "$FAIL" >> "$OUT_ROOT/summary.txt"
printf '日志目录：%s\n' "$OUT_ROOT"
[[ "$FAIL" -eq 0 ]]
