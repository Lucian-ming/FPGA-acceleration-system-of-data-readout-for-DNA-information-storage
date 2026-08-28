#!/usr/bin/env bash
# M2 full direct chain (2,048 original reads / 4,096 forward+RC records):
#   actual Stage1 -> actual Stage2 -> PS-equivalent XOR -> actual Stage3 -> LDPC/JPEG.
# The tracked stage2/stage3 vectors are scoreboards only and never replace a DUT checkpoint.
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
STAGE1_JOBS=${STAGE1_JOBS:-3}
ORIGINAL_READS=2048
STAGE1_RECORDS=$((ORIGINAL_READS * 2))
BATCH_RECORDS=64
BATCHES=$((STAGE1_RECORDS / BATCH_RECORDS))
TARGET_IMAGE_SHA256=fcd0cf90bd680e7bbdc203e3398119504da0897acac9e2117008b4efb6b1f2c3

for tool in "$XVLOG" "$XELAB" "$XSIM"; do
    [[ -x "$tool" ]] || { echo "FATAL: missing Vivado tool $tool" >&2; exit 2; }
done
[[ "$STAGE1_JOBS" =~ ^[1-9][0-9]*$ ]] || {
    echo "FATAL: STAGE1_JOBS must be a positive integer" >&2; exit 2;
}

RUN_ID=$(date -u +%Y%m%dT%H%M%SZ)
OUT_ROOT=${M2_FULL_OUT:-$REPO_ROOT/hw/build/xsim/m2_full/$RUN_ID}
CHECKPOINT="$OUT_ROOT/checkpoint"
BATCH_DIR="$CHECKPOINT/stage1_batches"
SUMMARY="$OUT_ROOT/summary.txt"
mkdir -p "$OUT_ROOT" "$CHECKPOINT" "$BATCH_DIR"

fail() {
    echo "M2 FULL FAIL: $*" | tee -a "$SUMMARY" >&2
    echo "logs=$OUT_ROOT" | tee -a "$SUMMARY" >&2
    exit 1
}

{
    echo "M2 full XSim run: $RUN_ID"
    echo "repo: $REPO_ROOT"
    echo "head: $(git -C "$REPO_ROOT" rev-parse HEAD 2>/dev/null || echo unknown)"
    echo "input: $ORIGINAL_READS original reads / $STAGE1_RECORDS forward+RC records"
    echo "stage1_jobs: $STAGE1_JOBS"
    "$XVLOG" -version 2>&1 | sed -n '1p'
} > "$SUMMARY"

for required in \
    tests/golden/SHA256SUMS \
    tests/golden/reads_cw.hex \
    tests/golden/stage2_in.hex \
    tests/golden/watermark_sym.hex \
    clients/python/resources/dvb_s2_r5_6.pchk \
    clients/python/resources/permutation64800; do
    [[ -f "$REPO_ROOT/$required" ]] || fail "missing required vector $required"
done
(cd "$REPO_ROOT/tests/golden" && sha256sum -c SHA256SUMS) \
    > "$OUT_ROOT/golden_sha256.log" 2>&1 || fail "golden SHA-256 verification failed"

python3 "$REPO_ROOT/tools/m2_chain.py" prepare-stage1 \
    --reads-cw "$REPO_ROOT/tests/golden/reads_cw.hex" \
    --stage2-golden "$REPO_ROOT/tests/golden/stage2_in.hex" \
    --reads-out "$CHECKPOINT/stage1_reads_4096.hex" \
    --expect-out "$CHECKPOINT/stage1_expect_4096.txt" \
    --batch-dir "$BATCH_DIR" \
    --original-records "$ORIGINAL_READS" \
    > "$OUT_ROOT/prepare_stage1.log" 2>&1 || fail "could not prepare Stage1 inputs"

DNA="$REPO_ROOT/hw/ip/Dna_accelerator_core_1_0/hdl"
VOTER="$REPO_ROOT/hw/ip/differential_voter_1_0/hdl"
DEC="$REPO_ROOT/hw/ip/desparsification_decoder_1_0/hdl"

compile_snapshot() {
    local name="$1" top="$2" snapshot="$3"
    shift 3
    local build_dir="$OUT_ROOT/$name"
    mkdir -p "$build_dir"
    (
        cd "$build_dir" || exit 1
        "$XVLOG" -work work "$@" > xvlog.log 2>&1
        "$XELAB" -debug typical "$top" -s "$snapshot" > xelab.log 2>&1
    ) || return 1
    if "${LOG_GREP[@]}" -n 'FATAL:|ERROR:|(^|[[:space:]])FAIL([:[:space:]]|$)|FAILED|\[FAIL\]' \
        "$build_dir/xvlog.log" "$build_dir/xelab.log" >/dev/null 2>&1; then
        return 1
    fi
}

compile_snapshot stage1_compile tb_srpe_batch stage1_full_sim \
    "$DNA/srpe_batch.v" "$DNA/tb_srpe_batch.v" \
    || fail "Stage1 compile/elaborate failed"

run_stage1_batch() {
    local batch="$1" batch_id run_dir log sim_rc=0
    printf -v batch_id '%03d' "$batch"
    run_dir="$OUT_ROOT/stage1_run_$batch_id"
    log="$run_dir/xsim.log"
    mkdir -p "$run_dir"
    # XSim rewrites xsim_script.tcl with the current plusargs at launch, so a
    # shared xsim.dir is not concurrency-safe.  The snapshot is only ~260 KiB;
    # give every worker a private copy to keep batch inputs isolated.
    cp -a "$OUT_ROOT/stage1_compile/xsim.dir" "$run_dir/xsim.dir"
    ln -s "$REPO_ROOT/tests" "$run_dir/tests" 2>/dev/null || true
    (
        cd "$run_dir" || exit 1
        timeout --foreground "$TIMEOUT_SEC" "$XSIM" stage1_full_sim -runall \
            -testplusarg "reads=$BATCH_DIR/reads_$batch_id.hex" \
            -testplusarg "expect=$BATCH_DIR/expect_$batch_id.txt" \
            -testplusarg "max_ties=$BATCH_RECORDS" \
            -testplusarg "dump_stage1=$BATCH_DIR/actual_$batch_id.hex"
    ) > "$log" 2>&1 || sim_rc=$?
    if [[ "$sim_rc" -ne 0 ]] \
       || ! "${LOG_GREP[@]}" -q 'PASS' "$log" \
       || "${LOG_GREP[@]}" -q 'FATAL:|ERROR:|(^|[[:space:]])FAIL([:[:space:]]|$)|FAILED|\[FAIL\]' "$log"; then
        echo "Stage1 batch $batch_id FAIL (rc=$sim_rc)"
        return 1
    fi
    echo "Stage1 batch $batch_id PASS"
}

stage1_failed=0
for ((group=0; group<BATCHES; group+=STAGE1_JOBS)); do
    pids=()
    for ((slot=0; slot<STAGE1_JOBS && group+slot<BATCHES; slot++)); do
        batch=$((group + slot))
        run_stage1_batch "$batch" &
        pids+=("$!")
    done
    for index in "${!pids[@]}"; do
        if ! wait "${pids[$index]}"; then
            stage1_failed=1
        fi
    done
done
[[ "$stage1_failed" -eq 0 ]] || fail "one or more Stage1 batches failed"
python3 "$REPO_ROOT/tools/m2_chain.py" summarize-stage1 \
    --input-dir "$OUT_ROOT" --batches "$BATCHES" --records "$STAGE1_RECORDS" \
    --max-percent 5 > "$OUT_ROOT/stage1_aggregate.log" 2>&1 \
    || fail "Stage1 aggregate scoreboard failed"

python3 "$REPO_ROOT/tools/m2_chain.py" combine-stage1 \
    --input-dir "$BATCH_DIR" --output "$CHECKPOINT/stage1_actual_4096.hex" \
    --batches "$BATCHES" > "$OUT_ROOT/combine_stage1.log" 2>&1 \
    || fail "could not combine Stage1 checkpoints"
python3 "$REPO_ROOT/tools/m2_chain.py" stage2 \
    --stage1 "$CHECKPOINT/stage1_actual_4096.hex" \
    --watermark "$REPO_ROOT/tests/golden/watermark_sym.hex" \
    --stage2-expect "$CHECKPOINT/stage2_expected_from_actual.hex" \
    --sparse-expect "$CHECKPOINT/sparse_expected_from_actual.hex" \
    --stage3-expect "$CHECKPOINT/stage3_expected_from_actual.hex" \
    --score-min 67 > "$OUT_ROOT/model_from_stage1.log" 2>&1 \
    || fail "could not derive downstream scoreboard from actual Stage1"

compile_snapshot stage2_voter tb_differential_voter stage2_full_sim \
    "$VOTER/differential_voter_v1_0.v" "$VOTER/tb_differential_voter.v" \
    || fail "Stage2 compile/elaborate failed"
(
    cd "$OUT_ROOT/stage2_voter" || exit 1
    timeout --foreground "$TIMEOUT_SEC" "$XSIM" stage2_full_sim -runall \
        -testplusarg "input=$CHECKPOINT/stage1_actual_4096.hex" \
        -testplusarg "expect=$CHECKPOINT/stage2_expected_from_actual.hex" \
        -testplusarg "expect_thr=$CHECKPOINT/stage2_expected_from_actual.hex" \
        -testplusarg "runs=1" \
        -testplusarg "dump_stage2=$CHECKPOINT/stage2_actual.hex"
) > "$OUT_ROOT/stage2_voter/xsim.log" 2>&1 || fail "Stage2 simulation failed"
"${LOG_GREP[@]}" -q 'PASS' "$OUT_ROOT/stage2_voter/xsim.log" || fail "Stage2 PASS marker missing"
! "${LOG_GREP[@]}" -q 'FATAL:|ERROR:|(^|[[:space:]])FAIL([:[:space:]]|$)|FAILED|\[FAIL\]' \
    "$OUT_ROOT/stage2_voter/xsim.log" || fail "Stage2 log contains failure"

python3 "$REPO_ROOT/tools/m2_chain.py" xor \
    --stage2 "$CHECKPOINT/stage2_actual.hex" \
    --watermark "$REPO_ROOT/tests/golden/watermark_sym.hex" \
    --sparse "$CHECKPOINT/sparse_actual.hex" > "$OUT_ROOT/ps_xor.log" 2>&1 \
    || fail "PS-equivalent XOR failed"

compile_snapshot stage3_decoder tb_desparsifier stage3_full_sim \
    "$DEC/desparsification_decoder_v1_0.v" "$DEC/desparsify_datapath.v" \
    "$DEC/tb_desparsifier.v" || fail "Stage3 compile/elaborate failed"
(
    cd "$OUT_ROOT/stage3_decoder" || exit 1
    timeout --foreground "$TIMEOUT_SEC" "$XSIM" stage3_full_sim -runall \
        -testplusarg "input=$CHECKPOINT/sparse_actual.hex" \
        -testplusarg "expect=$CHECKPOINT/stage3_expected_from_actual.hex" \
        -testplusarg "dump_stage3=$CHECKPOINT/stage3_actual.hex"
) > "$OUT_ROOT/stage3_decoder/xsim.log" 2>&1 || fail "Stage3 simulation failed"
"${LOG_GREP[@]}" -q 'PASS' "$OUT_ROOT/stage3_decoder/xsim.log" || fail "Stage3 PASS marker missing"
! "${LOG_GREP[@]}" -q 'FATAL:|ERROR:|(^|[[:space:]])FAIL([:[:space:]]|$)|FAILED|\[FAIL\]' \
    "$OUT_ROOT/stage3_decoder/xsim.log" || fail "Stage3 log contains failure"

python3 "$REPO_ROOT/tools/m2_chain.py" to-bittext \
    --input "$CHECKPOINT/stage3_actual.hex" \
    --output "$CHECKPOINT/dec_input_actual.txt" --bits 64800 \
    > "$OUT_ROOT/stage3_to_bits.log" 2>&1 || fail "could not serialize Stage3 output"
python3 "$REPO_ROOT/tools/ldpc_decode.py" decode "$CHECKPOINT/dec_input_actual.txt" \
    --output "$CHECKPOINT/decoded_bits.txt" --image "$CHECKPOINT/decoded_image.jpg" \
    > "$OUT_ROOT/ldpc.log" 2>&1 || fail "LDPC decode failed"
image_sha=$(sha256sum "$CHECKPOINT/decoded_image.jpg" | awk '{print $1}')
[[ "$image_sha" == "$TARGET_IMAGE_SHA256" ]] \
    || fail "decoded image SHA-256 $image_sha != $TARGET_IMAGE_SHA256"

# Mutation proof: flip one Stage2 checkpoint bit, propagate it through the
# PS-equivalent XOR, and require the real Stage3 scoreboard to reject it.
python3 "$REPO_ROOT/tools/m2_chain.py" flip \
    --input "$CHECKPOINT/stage2_actual.hex" \
    --output "$CHECKPOINT/stage2_fault_bit123.hex" --bit 123 \
    > "$OUT_ROOT/fault_injection.log" 2>&1 || fail "fault injection setup failed"
python3 "$REPO_ROOT/tools/m2_chain.py" xor \
    --stage2 "$CHECKPOINT/stage2_fault_bit123.hex" \
    --watermark "$REPO_ROOT/tests/golden/watermark_sym.hex" \
    --sparse "$CHECKPOINT/sparse_fault_bit123.hex" \
    >> "$OUT_ROOT/fault_injection.log" 2>&1 || fail "fault propagation failed"
fault_rc=0
(
    cd "$OUT_ROOT/stage3_decoder" || exit 1
    timeout --foreground "$TIMEOUT_SEC" "$XSIM" stage3_full_sim -runall \
        -testplusarg "input=$CHECKPOINT/sparse_fault_bit123.hex" \
        -testplusarg "expect=$CHECKPOINT/stage3_expected_from_actual.hex"
) > "$OUT_ROOT/stage3_decoder/fault_xsim.log" 2>&1 || fault_rc=$?
if "${LOG_GREP[@]}" -q 'PASS' "$OUT_ROOT/stage3_decoder/fault_xsim.log" \
   || ! "${LOG_GREP[@]}" -q 'FATAL:|FAIL|不符' "$OUT_ROOT/stage3_decoder/fault_xsim.log"; then
    fail "fault-injected Stage3 run was not rejected (rc=$fault_rc)"
fi

sha256sum \
    "$CHECKPOINT/stage1_actual_4096.hex" \
    "$CHECKPOINT/stage2_actual.hex" \
    "$CHECKPOINT/sparse_actual.hex" \
    "$CHECKPOINT/stage3_actual.hex" \
    "$CHECKPOINT/decoded_bits.txt" \
    "$CHECKPOINT/decoded_image.jpg" > "$CHECKPOINT/SHA256SUMS"

{
    echo
    echo "Stage1: $BATCHES/$BATCHES batches PASS ($STAGE1_RECORDS records)"
    echo "Stage2: 81000 bit PASS"
    echo "PS XOR: 81000 bit generated from actual Stage2"
    echo "Stage3: 64800 bit / 8100 byte PASS"
    echo "LDPC image SHA-256: $image_sha PASS"
    echo "fault injection: Stage2 bit 123 detected by Stage3 scoreboard PASS"
    echo "M2 full PASS: actual Stage1 -> Stage2 -> PS XOR -> Stage3 -> LDPC/JPEG"
    echo "logs=$OUT_ROOT"
} | tee -a "$SUMMARY"
echo "日志目录：$OUT_ROOT"
