#!/usr/bin/env bash
# Vivado/XSim 黄金回归入口。
# 用法：bash tools/run_xsim.sh [all|result_axis|ingress_result|dec_restart|vot_ddr|datapath|axi|stage1|stage2|ingress|dna_axil]
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

# ---------------------------------------------------------------------------
# 编译 + elaborate。成功后 $OUT_ROOT/<name> 里留下可复跑的 snapshot <name>_sim。
#   build_case <name> <top> <src...>
# ---------------------------------------------------------------------------
build_case() {
    local name="$1" top="$2"
    shift 2
    local case_dir="$OUT_ROOT/$name"
    mkdir -p "$case_dir"
    ln -s "$REPO_ROOT/tests" "$case_dir/tests" 2>/dev/null || true
    (
        cd "$case_dir" || exit 1
        # xvlog 2022.2 treats .v files as Verilog by default; it has no -2005 switch.
        "$XVLOG" -work work "$@" > xvlog.log 2>&1
    ) || return 1
    (
        cd "$case_dir" || exit 1
        "$XELAB" -debug typical "$top" -s "${name}_sim"
    ) > "$case_dir/xelab.log" 2>&1 || return 2
    return 0
}

# 编译/elaborate 日志里不得出现错误关键字（两种判据都要查）
build_log_clean() {
    local case_dir="$1"
    ! "${LOG_GREP[@]}" -n 'FATAL:|ERROR:|(^|[[:space:]])FAIL([:[:space:]]|$)|FAILED|\[FAIL\]' \
        "$case_dir/xvlog.log" "$case_dir/xelab.log" >/dev/null 2>&1
}

# ---------------------------------------------------------------------------
# 复跑一次 snapshot：sim_case <name> <sublabel> <judge:default|inject> [plusargs...]
#   default 判据：xsim 退出 0、日志有 PASS、三份日志都没有错误关键字
#   inject  判据：这一档**期望用例失败**，所以不能用 default（日志里本来就有 FAIL 行）。
#           判据是 TB 自己打出「故障注入自检 PASS」且没有打出「判据没有鉴别力」。
# ---------------------------------------------------------------------------
sim_case() {
    local name="$1" sub="$2" judge="$3"
    shift 3
    local case_dir="$OUT_ROOT/$name"
    local log="$case_dir/xsim_${sub}.log"
    local sim_rc=0
    (
        cd "$case_dir" || exit 1
        timeout --foreground "${CASE_TIMEOUT:-$TIMEOUT_SEC}" "$XSIM" "${name}_sim" -runall "$@"
    ) > "$log" 2>&1 || sim_rc=$?

    local ok=1
    [[ "$sim_rc" -eq 0 && -s "$log" ]] || ok=0
    if [[ "$judge" == inject ]]; then
        # XSim 2022.2 即使 TB 判失败也以 0 退出，判据只能看日志内容
        "${LOG_GREP[@]}" -n '判据没有鉴别力' "$log" >/dev/null 2>&1 && ok=0
        "${LOG_GREP[@]}" -n '故障注入自检 PASS' "$log" >/dev/null 2>&1 || ok=0
    else
        "${LOG_GREP[@]}" -n 'FATAL:|ERROR:|(^|[[:space:]])FAIL([:[:space:]]|$)|FAILED|\[FAIL\]' \
            "$log" >/dev/null 2>&1 && ok=0
        "${LOG_GREP[@]}" -n 'PASS' "$log" >/dev/null 2>&1 || ok=0
    fi

    if [[ "$ok" -eq 1 ]]; then
        PASS=$((PASS + 1)); echo "  PASS $name/$sub"
        printf '%s/%s\tsimulate=%s\tgolden=0\n' "$name" "$sub" "$sim_rc" >> "$OUT_ROOT/summary.txt"
        return 0
    fi
    FAIL=$((FAIL + 1)); echo "  FAIL $name/$sub simulate=$sim_rc -> $log"
    printf '%s/%s\tsimulate=%s\tgolden=1\n' "$name" "$sub" "$sim_rc" >> "$OUT_ROOT/summary.txt"
    return 1
}

# 单次用例（编译 + elaborate + 一次复跑），保持原有行为
run_case() {
    local name="$1" top="$2"
    shift 2
    local case_dir="$OUT_ROOT/$name"
    local build_rc=0
    printf '\n=== %s ===\n' "$name"
    build_case "$name" "$top" "$@" || build_rc=$?
    if [[ "$build_rc" -ne 0 ]] || ! build_log_clean "$case_dir"; then
        FAIL=$((FAIL + 1))
        echo "  FAIL $name (compile/elaborate) -> $case_dir"
        {
            printf '%s\tcompile/elaborate=%s\tgolden=1\n' "$name" "$build_rc"
            printf '  logs=%s\n' "$case_dir"
        } >> "$OUT_ROOT/summary.txt"
        return 1
    fi
    sim_case "$name" "run" default
    printf '  logs=%s\n' "$case_dir" >> "$OUT_ROOT/summary.txt"
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
if [[ "$WHICH" == all || "$WHICH" == dec_restart ]]; then
    # [B27] Stage3 Decoder 的「真实 DDR / 真实 AXI 主口 + 固件寄存器时序」判据。
    # desparsifier_axi / desparsify_datapath / M3 BD-3ext 都 PASS，板上却 49.46% 误码：
    # 它们只写一次 START=1、从机也很温柔，抓不到「跑到一半被 START 重启、
    # 飞行中的读突发残留拍污染输入流」这条真实路径。
    run_case dec_ddr_restart tb_dec_ddr_restart \
        "$REPO_ROOT/$DEC/desparsification_decoder_v1_0.v" \
        "$REPO_ROOT/$DEC/desparsify_datapath.v" \
        "$REPO_ROOT/hw/sim/dec/tb_dec_ddr_restart.v"
fi
if [[ "$WHICH" == all || "$WHICH" == vot_ddr ]]; then
    # Stage2 Voter 的「真实 DDR / 真实 AXI 主口 + 固件原样寄存器时序」判据。
    # docs/18 §5「仍未覆盖」的第一条：Voter 的 AXI 读通路此前只走过温柔从机
    # （tb_differential_voter：ARREADY 恒 1、零延迟、无背压、只写一次 START=1）
    # 和 M3 BD-3ext 的 AXI VIP 内存模型，从来没走过「PS 写 DDR -> Voter 读 DDR」。
    # 一次 build，四次复跑：正常档 + 三档故障注入自检（docs/13 §十）。
    printf '\n=== %s ===\n' vot_ddr
    if build_case vot_ddr tb_vot_ddr_bitexact \
        "$REPO_ROOT/$VOTER/differential_voter_v1_0.v" \
        "$REPO_ROOT/hw/sim/vot/tb_vot_ddr_bitexact.v" \
       && build_log_clean "$OUT_ROOT/vot_ddr"; then
        # 正常档：5 个场景逐位比黄金向量
        sim_case vot_ddr main default
        # 故障注入自检：注入已知缺陷后判据**必须**报错，否则它没有鉴别力
        #   b20 读突发退回「固定 6 拍、不按 4KB 页拆分」 -> 必须触发页边界判据
        #   rot 从机把读回的数据流旋转一个字        -> 必须触发逐位比较
        #   c4  第二次任务的 BRAM 清零被压制         -> 必须触发第二轮逐位比较
        sim_case vot_ddr inject_b20 inject -testplusarg "inject=b20"
        sim_case vot_ddr inject_rot inject -testplusarg "inject=rot"
        sim_case vot_ddr inject_c4  inject -testplusarg "inject=c4"
    else
        FAIL=$((FAIL + 1))
        echo "  FAIL vot_ddr (compile/elaborate) -> $OUT_ROOT/vot_ddr"
        printf 'vot_ddr\tcompile/elaborate=failed\tgolden=1\n' >> "$OUT_ROOT/summary.txt"
    fi
    printf '  logs=%s\n' "$OUT_ROOT/vot_ddr" >> "$OUT_ROOT/summary.txt"
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
if [[ "$WHICH" == all || "$WHICH" == result_axis ]]; then
    # [B23/B24] DNA 核 M_AXIS_RESULT 输出级的逐拍判据。
    # 这条链（DNA M_AXIS -> AXI DMA S2MM）此前没有任何仿真覆盖：
    # run_m2_full.sh 的 Stage1 只编译 srpe_batch.v，直接抓引擎的 res_din，
    # 完全绕开 AXIS 输出级和 s2mm_pack64，所以 B23 只有上板才暴露。
    run_case dna_result_axis tb_dna_result_axis \
        "$REPO_ROOT/$DNA/Dna_accelerator_core_v1_0.v" \
        "$REPO_ROOT/$DNA/Dna_accelerator_core_v1_0_S_AXI_LITE_CTRL.v" \
        "$REPO_ROOT/$DNA/fifo_sync_sdpram_b64.v" \
        "$REPO_ROOT/$DNA/s2mm_pack64.v" \
        "$REPO_ROOT/$DNA/srpe_batch.v" \
        "$REPO_ROOT/hw/sim/dna/tb_dna_result_axis.v"
fi
if [[ "$WHICH" == all || "$WHICH" == ingress_result ]]; then
    # [B26] DNA 核入口的「逐条」判据：送入第 k 条读段 -> 第 k 条结果的码字必须等于它。
    # tb_srpe_batch 直接把 cw_data 摆在引擎端口上（不经过 in_fifo 与 in_rd/eng_cw_vld
    # 握手），tb_dna_ingress 只测 TREADY 背压，所以入口错位一条在仿真里从来是绿的。
    run_case dna_ingress_result tb_dna_ingress_result \
        "$REPO_ROOT/$DNA/Dna_accelerator_core_v1_0.v" \
        "$REPO_ROOT/$DNA/Dna_accelerator_core_v1_0_S_AXI_LITE_CTRL.v" \
        "$REPO_ROOT/$DNA/fifo_sync_sdpram_b64.v" \
        "$REPO_ROOT/$DNA/s2mm_pack64.v" \
        "$REPO_ROOT/$DNA/srpe_batch.v" \
        "$REPO_ROOT/hw/sim/dna/tb_dna_ingress_result.v"
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
