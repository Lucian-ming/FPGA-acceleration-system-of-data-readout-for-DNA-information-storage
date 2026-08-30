#!/usr/bin/env bash
# M2 quick direct checkpoint chain:
#   actual Stage1 -> Stage2 input; actual Stage2 -> PS-equivalent XOR -> Stage3.
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
TIMEOUT_SEC=${XSIM_TIMEOUT_SEC:-1800}

for tool in "$XVLOG" "$XELAB" "$XSIM"; do
    [[ -x "$tool" ]] || { echo "FATAL: missing Vivado tool $tool" >&2; exit 2; }
done

RUN_ID=$(date -u +%Y%m%dT%H%M%SZ)
OUT_ROOT=${M2_OUT:-$REPO_ROOT/hw/build/xsim/m2_quick/$RUN_ID}
CHECKPOINT="$OUT_ROOT/checkpoint"
mkdir -p "$OUT_ROOT" "$CHECKPOINT"

STAGE1_RAW="$CHECKPOINT/stage1_actual_64.hex"
STAGE1_PAD="$CHECKPOINT/stage1_actual_padded_4096.hex"
STAGE2_EXPECT="$CHECKPOINT/stage2_expected_64.hex"
SPARSE_EXPECT="$CHECKPOINT/sparse_expected_64.hex"
STAGE3_EXPECT="$CHECKPOINT/stage3_expected_64.hex"
STAGE2_RAW="$CHECKPOINT/stage2_actual_64.hex"
SPARSE_RAW="$CHECKPOINT/sparse_actual_64.hex"

printf 'M2 quick XSim run: %s\nrepo: %s\nhead: %s\n' "$RUN_ID" "$REPO_ROOT" \
    "$(git -C "$REPO_ROOT" rev-parse HEAD 2>/dev/null || echo unknown)" > "$OUT_ROOT/summary.txt"

run_case() {
    local name="$1" top="$2"
    shift 2
    local sources=() sim_args=()
    while [[ "$#" -gt 0 && "$1" != "--" ]]; do sources+=("$1"); shift; done
    [[ "$#" -gt 0 ]] && shift
    sim_args=("$@")
    local case_dir="$OUT_ROOT/$name"
    local compile_rc=0 elab_rc=0 sim_rc=0 log_error=0
    mkdir -p "$case_dir"
    ln -s "$REPO_ROOT/tests" "$case_dir/tests" 2>/dev/null || true
    printf '\n=== %s ===\n' "$name" | tee -a "$OUT_ROOT/summary.txt"
    (
        cd "$case_dir" || exit 1
        "$XVLOG" -work work "${sources[@]}" > xvlog.log 2>&1
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
            timeout --foreground "$TIMEOUT_SEC" "$XSIM" "${name}_sim" -runall "${sim_args[@]}"
        ) > "$case_dir/xsim.log" 2>&1 || sim_rc=$?
    fi
    if "${LOG_GREP[@]}" -n 'FATAL:|ERROR:|(^|[[:space:]])FAIL([:[:space:]]|$)|FAILED|\[FAIL\]' \
        "$case_dir/xvlog.log" "$case_dir/xelab.log" "$case_dir/xsim.log" >/dev/null 2>&1; then
        log_error=1
    fi
    if [[ "$compile_rc" -eq 0 && "$elab_rc" -eq 0 && "$sim_rc" -eq 0 \
          && "$log_error" -eq 0 ]] && "${LOG_GREP[@]}" -n 'PASS' "$case_dir/xsim.log" >/dev/null 2>&1; then
        printf '%s\tPASS\tcompile=0\telaborate=0\tsimulate=0\n' "$name" >> "$OUT_ROOT/summary.txt"
        echo "  PASS ($case_dir)"
        return 0
    fi
    printf '%s\tFAIL\tcompile=%s\telaborate=%s\tsimulate=%s\n' \
        "$name" "$compile_rc" "$elab_rc" "$sim_rc" >> "$OUT_ROOT/summary.txt"
    echo "  FAIL compile=$compile_rc elaborate=$elab_rc simulate=$sim_rc"
    return 1
}

DNA="$REPO_ROOT/hw/ip/Dna_accelerator_core_1_0/hdl"
VOTER="$REPO_ROOT/hw/ip/differential_voter_1_0/hdl"
DEC="$REPO_ROOT/hw/ip/desparsification_decoder_1_0/hdl"

run_case stage1_core tb_srpe_batch \
    "$DNA/srpe_batch.v" "$DNA/tb_srpe_batch.v" -- \
    -testplusarg "dump_stage1=$STAGE1_RAW" || exit 1

python3 "$REPO_ROOT/tools/m2_chain.py" pad \
    --input "$STAGE1_RAW" --output "$STAGE1_PAD" --records 4096 || exit 1
python3 "$REPO_ROOT/tools/m2_chain.py" stage2 \
    --stage1 "$STAGE1_RAW" --watermark "$REPO_ROOT/tests/golden/watermark_sym.hex" \
    --stage2-expect "$STAGE2_EXPECT" --sparse-expect "$SPARSE_EXPECT" \
    --stage3-expect "$STAGE3_EXPECT" --score-min 67 || exit 1

run_case stage2_voter tb_differential_voter \
    "$VOTER/differential_voter_v1_0.v" "$VOTER/tb_differential_voter.v" -- \
    -testplusarg "input=$STAGE1_PAD" \
    -testplusarg "expect=$STAGE2_EXPECT" \
    -testplusarg "expect_thr=$STAGE2_EXPECT" \
    -testplusarg "runs=1" \
    -testplusarg "dump_stage2=$STAGE2_RAW" || exit 1

python3 "$REPO_ROOT/tools/m2_chain.py" xor \
    --stage2 "$STAGE2_RAW" --watermark "$REPO_ROOT/tests/golden/watermark_sym.hex" \
    --sparse "$SPARSE_RAW" || exit 1

run_case stage3_decoder tb_desparsifier \
    "$DEC/desparsification_decoder_v1_0.v" "$DEC/desparsify_datapath.v" \
    "$DEC/tb_desparsifier.v" -- \
    -testplusarg "input=$SPARSE_RAW" \
    -testplusarg "expect=$STAGE3_EXPECT" || exit 1

{
    echo
    echo "M2 quick PASS: actual Stage1 -> Stage2 -> PS XOR -> Stage3"
    sha256sum "$STAGE1_RAW" "$STAGE2_RAW" "$SPARSE_RAW" "$STAGE3_EXPECT"
    echo "logs=$OUT_ROOT"
} | tee -a "$OUT_ROOT/summary.txt"
echo "日志目录：$OUT_ROOT"
