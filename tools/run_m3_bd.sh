#!/usr/bin/env bash
# M3：实际 Vivado Block Design 集成仿真的统一入口。
#
#   bash tools/run_m3_bd.sh [all|bd1|bd2|bd3|bd3ext|bd3b]
#
# BD-1  由 hw/scripts/bd.tcl 从干净目录重建实际 BD，validate/生成 simulation target，
#       编译并 elaborate top_bd_wrapper；核对地址图、未连接接口、IP 状态和黑盒。
# BD-2  控制面：PS7 VIP 经 GP0 → 实际 ic_lite → 四个从机，寄存器写/读回、
#       从机隔离、无效地址 DECERR。
# BD-3  数据面：Voter / Decoder 的实际 AXI4 主口经实际 ic_hp → PS7 S_AXI_HP0 → VIP DDR，
#       在真实地址上跑完整 81,000 bit / 64,800 bit，并与黄金向量逐位比较；
#       零延迟与最坏延迟（带背压）两档都必须通过。
#
# 判据纪律：编译通过、仿真跑完、有波形都不算 PASS。每一步都要显式 PASS/FAIL、
# 非零失败退出码、超时保护和逐位比较。
set -uo pipefail

REPO_ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
VIVADO_ROOT=${VIVADO_ROOT:-/tools/Xilinx/Vivado/2022.2}
VIVADO=${VIVADO:-$VIVADO_ROOT/bin/vivado}
XSIM=${XSIM:-$VIVADO_ROOT/bin/xsim}
PYTHON=${PYTHON:-python3}
KEEP=${KEEP:-3}
NO_PRUNE=0
WHICH="all"

while [[ $# -gt 0 ]]; do
    case "$1" in
        --keep)
            KEEP="$2"; shift 2 ;;
        --keep=*)
            KEEP="${1#*=}"; shift ;;
        --no-prune)
            NO_PRUNE=1; shift ;;
        -*)
            echo "Unknown option: $1" >&2; exit 2 ;;
        *)
            WHICH="$1"; shift ;;
    esac
done

# 日志判据检索器：优先 ripgrep，缺失时回退 POSIX grep -E（模式均为 ERE）。
RG=${RG:-}
if [[ -n "$RG" ]]; then
    LOG_GREP=("$RG")
elif command -v rg >/dev/null 2>&1; then
    LOG_GREP=(rg)
else
    LOG_GREP=(grep -E)
fi

# 除常规错误关键字外，还要抓 Xilinx VIP 的前向进展看门狗：xsim 在该看门狗触发后
# 仍以 0 退出，只靠退出码会漏判。
ERR_PAT='FATAL:|Fatal:|(^|[[:space:]])ERROR:|(^|[[:space:]])FAIL([:[:space:]]|$)|FAILED|\[FAIL\]|Forward progress timeout'

for tool in "$VIVADO" "$XSIM"; do
    [[ -x "$tool" ]] || { echo "FATAL: missing Vivado tool $tool" >&2; exit 2; }
done

RUN_ID=$(date -u +%Y%m%dT%H%M%SZ)
OUT_ROOT=${M3_OUT:-$REPO_ROOT/hw/build/xsim/m3/$RUN_ID}
WORK="$OUT_ROOT/work"
SUMMARY="$OUT_ROOT/summary.txt"
mkdir -p "$OUT_ROOT" "$WORK"

GOLDEN="$REPO_ROOT/tests/golden"
TB_DIR="$REPO_ROOT/hw/sim/m3"
GEN_TCL="$REPO_ROOT/hw/scripts/m3_bd_sim.tcl"

PASS=0
FAIL=0

{
    printf 'M3 BD run: %s\n' "$RUN_ID"
    printf 'repo: %s\n' "$REPO_ROOT"
    printf 'head: %s\n' "$(git -C "$REPO_ROOT" rev-parse HEAD 2>/dev/null || echo unknown)"
    printf 'git status: %s\n' "$(git -C "$REPO_ROOT" status --porcelain | wc -l) modified path(s)"
    printf 'vivado: %s\n' "$("$VIVADO" -version -nolog -nojournal 2>/dev/null | head -1)"
    printf 'python: %s\n' "$($PYTHON --version 2>&1)"
    printf '\n'
} > "$SUMMARY"

note()  { echo "$*" | tee -a "$SUMMARY"; }
fail()  { note "M3 FAIL: $*"; exit 1; }

# 记录判据输入的 SHA-256（黄金向量只读，用于最终比较）
{
    echo "---- golden manifest ----"
    for f in stage2_in.hex stage2_expect.hex stage3_expect.hex watermark_sym.hex; do
        [[ -f "$GOLDEN/$f" ]] && sha256sum "$GOLDEN/$f"
    done
    echo "---- testbench manifest ----"
    for f in "$TB_DIR"/*.v "$TB_DIR"/*.sv; do [[ -f "$f" ]] && sha256sum "$f"; done
    sha256sum "$REPO_ROOT/hw/scripts/bd.tcl" "$GEN_TCL" "$REPO_ROOT/tools/m3_mem.py"
    echo
} >> "$SUMMARY"

# ---------------------------------------------------------------------------
# 生成工程 + 编译 + elaborate。成功后 SIMDIR 里留下可复用的 snapshot。
#   gen_project <casedir> <tb_top|""> <tb_src|"">
# ---------------------------------------------------------------------------
gen_project() {
    local casedir="$1" tb_top="$2" tb_src="$3" bd_sel="${4:-prod}"
    local log="$casedir/vivado.log"
    mkdir -p "$casedir"
    local args=(outdir="$casedir" stage=bd1 bd_script_sel="$bd_sel")
    [[ -n "$tb_top" ]] && args+=(tb_top="$tb_top")
    [[ -n "$tb_src" ]] && args+=(tb_srcs="$tb_src")
    (
        cd "$casedir" || exit 1
        "$VIVADO" -mode batch -nojournal -log "$casedir/vivado_tool.log" \
                  -source "$GEN_TCL" -tclargs "${args[@]}"
    ) > "$log" 2>&1
    return $?
}

# xsim 复跑：<simdir> <snapshot> <logfile> [plusargs...]
run_snapshot() {
    local simdir="$1" snap="$2" log="$3"; shift 3
    local rc=0
    # 日志上限（MiB）。VIP 在 Stop-On-Error=0 下可能每个 delta 刷一条 Error：
    # 实测 BD-3ext 的 WORST_CASE 曾把日志刷到 16 GB，把 xsim 撑到被 OOM 杀掉，
    # 顺带差点填满磁盘。超过上限就截断并杀掉仿真，让它以失败收场而不是拖垮机器。
    local cap_mb="${M3_XSIM_LOG_CAP_MB:-512}"
    (
        cd "$simdir" || exit 1
        timeout --foreground "${M3_XSIM_TIMEOUT:-3600}" \
            "$XSIM" "$snap" -runall "$@" \
            | head -c "$((cap_mb * 1024 * 1024))"
        exit "${PIPESTATUS[0]}"
    ) > "$log" 2>&1 || rc=$?
    if [[ "$(stat -c %s "$log" 2>/dev/null || echo 0)" -ge "$((cap_mb * 1024 * 1024))" ]]; then
        printf '\n[run_m3_bd] FAIL 日志达到 %s MiB 上限被截断，仿真判为失败\n' "$cap_mb" >> "$log"
        rc=1
    fi
    return $rc
}

# 判据：退出码为 0、日志有 PASS、日志无错误关键字
judge_log() {
    local name="$1" rc="$2" log="$3"
    if [[ "$rc" -ne 0 ]]; then
        note "  FAIL $name (exit=$rc) -> $log"; FAIL=$((FAIL+1)); return 1
    fi
    if ! "${LOG_GREP[@]}" -q 'PASS' "$log"; then
        note "  FAIL $name (缺少 PASS 标记) -> $log"; FAIL=$((FAIL+1)); return 1
    fi
    if "${LOG_GREP[@]}" -q "$ERR_PAT" "$log"; then
        note "  FAIL $name (日志含错误关键字) -> $log"; FAIL=$((FAIL+1)); return 1
    fi
    note "  PASS $name"; PASS=$((PASS+1)); return 0
}

# ===========================================================================
# BD-1：静态与 elaboration
# ===========================================================================
do_bd1() {
    note "=== BD-1 实际 BD 生成 / 静态检查 / elaboration ==="
    local casedir="$OUT_ROOT/bd1"
    if ! gen_project "$casedir" "" ""; then
        note "  FAIL BD-1 (vivado 退出非 0) -> $casedir/vivado.log"
        FAIL=$((FAIL+1)); return 1
    fi

    local ok=1

    # 1. 地址图必须与 sw/app/xparameters.h 完全一致
    local amap="$casedir/bd_address.txt"
    if [[ ! -f "$amap" ]]; then
        note "  FAIL BD-1 未生成地址图"; ok=0
    else
        check_addr() {
            local seg="$1" want="$2"
            if "${LOG_GREP[@]}" -q "$seg.*offset=0x$want" "$amap"; then
                note "    ok  $seg @0x$want"
            else
                note "    FAIL $seg 期望 offset=0x$want，实际：$(grep -F "$seg" "$amap" || echo 缺失)"
                ok=0
            fi
        }
        check_addr "SEG_Dna_accelerator_core_0_S_AXI_LITE_CTRL_reg" "43C00000"
        check_addr "SEG_desparsification_dec_0_S00_AXI_reg"         "43C10000"
        check_addr "SEG_differential_voter_0_S00_AXI_reg"           "43C20000"
        check_addr "SEG_axi_dma_0_Reg"                              "40400000"
    fi

    # 2. 未连接接口：只允许 PS7 的可选 HP0 FIFO 边带
    local unconn="$casedir/bd_unconnected.txt"
    if [[ -f "$unconn" ]]; then
        local unexpected
        unexpected=$(grep -v 'S_AXI_HP0_FIFO_CTRL' "$unconn" | grep -v '^$' || true)
        if [[ -n "$unexpected" ]]; then
            note "    FAIL 存在未预期的未连接接口："; note "$unexpected"; ok=0
        else
            note "    ok  未连接接口仅 PS7 可选 HP0 FIFO 边带"
        fi
    fi

    # 3. 三个自研 IP 必须都在，且未被锁定
    local ipst="$casedir/bd_ip_status.txt"
    if [[ -f "$ipst" ]]; then
        for v in "user:Dna_accelerator_core" "user:differential_voter" "user:desparsification_decoder"; do
            if "${LOG_GREP[@]}" -q "$v" "$ipst"; then note "    ok  IP $v 已在 BD 中"
            else note "    FAIL BD 中缺少 IP $v"; ok=0; fi
        done
        if "${LOG_GREP[@]}" -q 'locked=1' "$ipst"; then
            note "    FAIL 存在被锁定的 IP（需要 upgrade）"; ok=0
        else
            note "    ok  无锁定/待升级 IP"
        fi
    fi

    # 4. 编译/elaborate 日志中不得出现黑盒或缺失模块
    local simdir="$casedir/proj/m3_bd.sim/sim_1/behav/xsim"
    for l in "$simdir/elaborate.log" "$simdir/xvlog.log" "$simdir/xvhdl.log"; do
        [[ -f "$l" ]] || continue
        if "${LOG_GREP[@]}" -qi 'black.?box|treated as a black box|module .* not found|unresolved' "$l"; then
            note "    FAIL $l 出现黑盒/缺失模块"; ok=0
        fi
    done
    [[ -f "$simdir/elaborate.log" ]] || { note "    FAIL 未生成 elaborate.log"; ok=0; }
    if [[ $ok -eq 1 ]]; then note "    ok  elaborate 无黑盒/缺失模块"; fi

    if [[ $ok -eq 1 ]]; then
        note "  PASS BD-1"; PASS=$((PASS+1)); return 0
    fi
    note "  FAIL BD-1"; FAIL=$((FAIL+1)); return 1
}

# ===========================================================================
# BD-2：控制面
# ===========================================================================
do_bd2() {
    note "=== BD-2 控制面事务（GP0 -> ic_lite -> 四个从机）==="
    local casedir="$OUT_ROOT/bd2"
    if ! gen_project "$casedir" "tb_m3_bd2_ctrl" "$TB_DIR/tb_m3_bd2_ctrl.v"; then
        note "  FAIL BD-2 (生成/elaborate 失败) -> $casedir/vivado.log"
        FAIL=$((FAIL+1)); return 1
    fi
    local simdir="$casedir/proj/m3_bd.sim/sim_1/behav/xsim"
    local log="$casedir/xsim_bd2.log"
    local rc=0
    run_snapshot "$simdir" "tb_m3_bd2_ctrl_behav" "$log" || rc=$?
    judge_log "BD-2 控制面" "$rc" "$log"
}

# ===========================================================================
# BD-3：数据面（两档内存延迟）
# ===========================================================================
# do_bd3_run <tag> <tb_top> <tb_src> <bd_sel> <标题>
#   tag    用于目录/文件名前缀，避免两条路径互相覆盖
#   bd_sel prod    = 生产 BD（内存端点是 PS7 的 HP0/AFI）
#          sim_mem = 仿真专用变体（内存端点换成 AXI VIP，见 hw/scripts/bd_sim_mem.tcl）
do_bd3_run() {
    local tag="$1" tb_top="$2" tb_src="$3" bd_sel="$4" title="$5"
    note "=== $title ==="
    local casedir="$OUT_ROOT/$tag"
    if ! gen_project "$casedir" "$tb_top" "$tb_src" "$bd_sel"; then
        note "  FAIL $tag (生成/elaborate 失败) -> $casedir/vivado.log"
        FAIL=$((FAIL+1)); return 1
    fi
    local simdir="$casedir/proj/m3_bd.sim/sim_1/behav/xsim"
    local snap="${tb_top}_behav"

    # Voter 的激励是受版本管理的 Stage1 输出向量（激励，不是期望值）
    local voter_in="$WORK/voter_in_vip.hex"
    $PYTHON "$REPO_ROOT/tools/m3_mem.py" to-vip \
        "$GOLDEN/stage2_in.hex" "$voter_in" >> "$SUMMARY" 2>&1 \
        || fail "生成 Voter 输入镜像失败"

    local lat name rc
    for lat in 0 2; do
        case $lat in
            0) name="零延迟(BEST_CASE)" ;;
            2) name="最坏延迟/带背压(WORST_CASE)" ;;
        esac
        note "--- 内存行为：$name ---"

        # ---- Stage2 / Voter ----
        local v_out_vip="$WORK/${tag}_stage2_out_vip_lat$lat.hex"
        local v_out="$WORK/${tag}_stage2_actual_lat$lat.hex"
        local v_log="$casedir/xsim_voter_lat$lat.log"
        rc=0
        run_snapshot "$simdir" "$snap" "$v_log" \
            -testplusarg "stage=voter" \
            -testplusarg "mem_in=$voter_in" \
            -testplusarg "mem_out=$v_out_vip" \
            -testplusarg "total_reads=4096" \
            -testplusarg "latency=$lat" || rc=$?
        judge_log "$tag Voter ($name)" "$rc" "$v_log" || continue

        $PYTHON "$REPO_ROOT/tools/m3_mem.py" from-vip "$v_out_vip" "$v_out" --beats 1266 \
            >> "$SUMMARY" 2>&1 || fail "Stage2 输出格式转换失败"

        if $PYTHON "$REPO_ROOT/tools/m3_mem.py" cmp "$v_out" "$GOLDEN/stage2_expect.hex" \
             --label "$tag Stage2 ($name)" | tee -a "$SUMMARY" | "${LOG_GREP[@]}" -q 'PASS'; then
            note "  PASS $tag Stage2 逐位比较 ($name)"; PASS=$((PASS+1))
        else
            note "  FAIL $tag Stage2 逐位比较 ($name)"; FAIL=$((FAIL+1)); continue
        fi

        # ---- PS 等价 XOR（在两次仿真之间，级间数据仍是实际输出）----
        local sparse="$WORK/${tag}_sparse_actual_lat$lat.hex"
        $PYTHON "$REPO_ROOT/tools/m2_chain.py" xor \
            --stage2 "$v_out" \
            --watermark "$GOLDEN/watermark_sym.hex" \
            --sparse "$sparse" >> "$SUMMARY" 2>&1 || fail "PS 等价 XOR 失败"

        local d_in_vip="$WORK/${tag}_dec_in_vip_lat$lat.hex"
        $PYTHON "$REPO_ROOT/tools/m3_mem.py" to-vip "$sparse" "$d_in_vip" \
            >> "$SUMMARY" 2>&1 || fail "生成 Decoder 输入镜像失败"

        # ---- Stage3 / Decoder ----
        local d_out_vip="$WORK/${tag}_stage3_out_vip_lat$lat.hex"
        local d_out="$WORK/${tag}_stage3_actual_lat$lat.hex"
        local d_log="$casedir/xsim_decoder_lat$lat.log"
        rc=0
        run_snapshot "$simdir" "$snap" "$d_log" \
            -testplusarg "stage=decoder" \
            -testplusarg "mem_in=$d_in_vip" \
            -testplusarg "mem_out=$d_out_vip" \
            -testplusarg "latency=$lat" || rc=$?
        judge_log "$tag Decoder ($name)" "$rc" "$d_log" || continue

        $PYTHON "$REPO_ROOT/tools/m3_mem.py" from-vip "$d_out_vip" "$d_out" --beats 1013 \
            >> "$SUMMARY" 2>&1 || fail "Stage3 输出格式转换失败"

        if $PYTHON "$REPO_ROOT/tools/m3_mem.py" cmp "$d_out" "$GOLDEN/stage3_expect.hex" \
             --label "$tag Stage3 ($name)" | tee -a "$SUMMARY" | "${LOG_GREP[@]}" -q 'PASS'; then
            note "  PASS $tag Stage3 逐位比较 ($name)"; PASS=$((PASS+1))
        else
            note "  FAIL $tag Stage3 逐位比较 ($name)"; FAIL=$((FAIL+1))
        fi
    done
}

# BD-3：生产 BD（内存端点是实际 PS7 HP0/AFI）
do_bd3() {
    do_bd3_run "bd3" "tb_m3_bd3_dpath" "$TB_DIR/tb_m3_bd3_dpath.v" "prod" \
        "BD-3 数据面事务（Voter/Decoder 主口 -> ic_hp -> 实际 PS7 HP0）"
}

# 故障注入自检的专用判据：这一档**期望**用例失败，所以不能用 judge_log
# （它的日志里本来就有 FAIL 行）。判据是：TB 自己打出「故障注入自检 PASS」，
# 且没有打出「判据没有鉴别力」。
judge_inject_log() {
    local name="$1" rc="$2" log="$3"
    if [[ "$rc" -ne 0 ]]; then
        note "  FAIL $name (exit=$rc) -> $log"; FAIL=$((FAIL+1)); return 1
    fi
    if "${LOG_GREP[@]}" -q '判据没有鉴别力' "$log"; then
        note "  FAIL $name (注入故障后判据仍然通过) -> $log"; FAIL=$((FAIL+1)); return 1
    fi
    if ! "${LOG_GREP[@]}" -q '故障注入自检 PASS' "$log"; then
        note "  FAIL $name (未看到故障注入自检结论) -> $log"; FAIL=$((FAIL+1)); return 1
    fi
    note "  PASS $name"; PASS=$((PASS+1)); return 0
}

# ===========================================================================
# BD-3b：AXI DMA <-> DNA 核（docs/05 §7.2 BD-3 第 1、2 项、docs/08 任务 A）
#
# 这是本项目至今唯一没有 BD 级覆盖的一段链路，也是缺陷 B26 的判据所在：
#   判据 = 「送入第 k 条读段 -> 引擎第 k 个槽位装的就是第 k 条读段
#            -> 第 k 条结果记录的码字就是第 k 条读段的码字」，
#   不是「跑完没报错」。
#
# 两档：
#   wm   50 个区域的水印预载（真实 SG DMA + 真实 preload 通路），逐符号比 wm BRAM
#   load 在 wm 之上再送 64 条读段，等引擎装完一个 batch（约 3 万拍）后校验 64 个槽位
#        —— B26 的快速判据
# ⚠️ 内存端点是 AXI VIP，不是实际 PS7 的 AFI 通路（docs/05 §5），引用结论时必须写明。
#
# 环境变量：
#   M3_BD3B_READS   送入的读段条数（64 的整数倍，默认 64）
#   M3_BD3B_PHASE   wm|load|full（默认 load；full 要等引擎扫完 50x808 个位置，极慢）
# ===========================================================================
do_bd3b() {
    local phase="${M3_BD3B_PHASE:-load}"
    local reads="${M3_BD3B_READS:-64}"
    note "=== BD-3b 数据面（AXI DMA MM2S -> DNA S_AXIS -> M_AXIS -> S2MM，phase=$phase）==="
    local casedir="$OUT_ROOT/bd3b"
    if ! gen_project "$casedir" "tb_m3_bd3b_dma" "$TB_DIR/tb_m3_bd3b_dma.sv" "sim_mem"; then
        note "  FAIL BD-3b (生成/elaborate 失败) -> $casedir/vivado.log"
        FAIL=$((FAIL+1)); return 1
    fi
    local simdir="$casedir/proj/m3_bd.sim/sim_1/behav/xsim"

    # 读段镜像：黄金 reads_cw.hex -> 每条 10 个 32 bit 字（与 MM2S 实际发的字节一致）
    local reads_vip="$WORK/bd3b_reads_vip.hex"
    $PYTHON "$REPO_ROOT/tools/m3_mem.py" reads-to-vip \
        "$GOLDEN/reads_cw.hex" "$reads_vip" --reads "$reads" >> "$SUMMARY" 2>&1 \
        || fail "生成读段镜像失败"

    local log="$casedir/xsim_bd3b_${phase}.log"
    local rc=0
    run_snapshot "$simdir" "tb_m3_bd3b_dma_behav" "$log" \
        -testplusarg "phase=$phase" \
        -testplusarg "require=all" \
        -testplusarg "rx_bd_mode=perrec" \
        -testplusarg "reads=$reads" \
        -testplusarg "wm_file=$GOLDEN/wm_regions.hex" \
        -testplusarg "reads_file=$reads_vip" \
        -testplusarg "mem_out=$WORK/bd3b_stage1_out_vip.hex" || rc=$?
    judge_log "BD-3b 入口逐条判据 (phase=$phase, reads=$reads)" "$rc" "$log"

    # 故障注入自检（docs/05 §十）：把 cw_data 强行接回 in_dout（= B26 修复前的接法），
    # 判据必须失败。跑一次只多花约 1 分钟，是「这条判据真的能抓住 B26」的唯一证明。
    if [[ "${M3_BD3B_SKIP_INJECT:-0}" != "1" ]]; then
        local ilog="$casedir/xsim_bd3b_inject.log"
        rc=0
        run_snapshot "$simdir" "tb_m3_bd3b_dma_behav" "$ilog" \
            -testplusarg "phase=load" \
            -testplusarg "require=all" \
            -testplusarg "rx_bd_mode=perrec" \
            -testplusarg "reads=$reads" \
            -testplusarg "inject_b26=1" \
            -testplusarg "wm_file=$GOLDEN/wm_regions.hex" \
            -testplusarg "reads_file=$reads_vip" || rc=$?
        judge_inject_log "BD-3b 故障注入自检（注入 B26 后判据必须失败）" "$rc" "$ilog"
    fi
}

# BD-3ext：仿真专用内存端点（绕开 PS7 VIP 的 HP0 读通路缺陷）
# ⚠️ 该路径的内存端点不是实际 PS7 的 AFI 通路，引用结论时必须写明。
do_bd3ext() {
    do_bd3_run "bd3ext" "tb_m3_bd3_extmem" "$TB_DIR/tb_m3_bd3_extmem.sv" "sim_mem" \
        "BD-3ext 数据面事务（Voter/Decoder 主口 -> ic_hp -> AXI VIP 内存模型，仿真专用端点）"
}

# ===========================================================================
case "$WHICH" in
    all)     do_bd1; do_bd2; do_bd3; do_bd3ext; do_bd3b ;;
    bd1)     do_bd1 ;;
    bd2)     do_bd2 ;;
    bd3)     do_bd3 ;;
    bd3ext)  do_bd3ext ;;
    bd3b)    do_bd3b ;;
    *)   echo "用法: bash tools/run_m3_bd.sh [all|bd1|bd2|bd3|bd3ext|bd3b]" >&2; exit 2 ;;
esac

note ""
note "=================================================="
note "通过 $PASS 项，失败 $FAIL 项"
note "证据目录：$OUT_ROOT"
note "=================================================="

if (( ! NO_PRUNE )) && [[ -x "$REPO_ROOT/tools/prune_xsim.sh" ]]; then
    "$REPO_ROOT/tools/prune_xsim.sh" --keep "$KEEP" >/dev/null 2>&1 || true
fi

if [[ "$FAIL" -ne 0 ]]; then
    echo "M3 FAIL" | tee -a "$SUMMARY"
    exit 1
fi
echo "M3 PASS" | tee -a "$SUMMARY"
exit 0
