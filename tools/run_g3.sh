#!/usr/bin/env bash
# =============================================================================
# tools/run_g3.sh —— G3 板级验收的一键复现入口
#
# 为什么要有它
# ------------
# G3 在 2026-08-30 第五次上板闭环，但当时的验收是跨 Windows/WSL 的一串手工步骤：
# 开串口抓取 → xsdb 烧录 → first.py 跑任务 → ldpc_decode.py 译码 → 比图片哈希 →
# xsdb 只读导出四级 DDR → board_stage_check.py。**判据要能被一条命令复现，才算真的钉住。**
# 这轮的教训正是「摸索过程本身就会引入错误」（B23~B27 五个缺陷在所有仿真里都是绿的，
# 只有上板才暴露），所以复现路径本身不能再靠人记步骤。
#
# 判据纪律（AGENTS.md「事实边界」）
# --------------------------------
# 界面成功、TCP 返回结果、四级取证全绿，**都不算 G3 通过**。
# 唯一判据是板端真实回传经 tools/ldpc_decode.py 译码后重建的 JPEG 的 SHA-256。
# 本脚本据此给出单一 PASS/FAIL 与非零退出码。
#
# 制品同源性
# ----------
# 烧进板子的 bitstream / ELF / ps7_init.tcl 全部取自 hw/build/export/，
# 并先与该目录的 SHA256SUMS 逐一校验（ps7_init.tcl 从受版本管理的 dna_accel.xsa 里解出来）。
# 校验不过直接停，绝不允许「源码是新的、板上跑的是旧制品」这种不同源的情况混过去。
#
# 用法
# ----
#   tools/run_g3.sh                                   # 复现 G3 闭环那组参数（2048 条源读段）
#   tools/run_g3.sh --limit 4096                      # 分档测量：源读段数翻倍
#   tools/run_g3.sh --limit 2048 --skip-boot          # 板子已在跑，只重跑任务
#   tools/run_g3.sh --full --result-timeout 1800      # 全量数据集
#   tools/run_g3.sh --runs 2                          # 同一次上电内连续跑两次任务（状态复位判据）
#
# 环境（docs/16、docs/19 已验证，勿重摸）
# --------------------------------------
#   Windows 侧 D:\dev_tools\Vivado_Lab\2022.2\bin\xsdb.bat，从 WSL 用 cmd.exe /c 调用；
#   工作目录 D:\dna_board_smoke\；JTAG Digilent 210251A08870，器件 xc7z010_1；
#   串口 CH340 = COM6@115200（一次只能一个进程占用）；
#   主机 192.168.1.100/24，板子 192.168.1.10，WSL 可直连 TCP:7。
# =============================================================================
set -uo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO"

# ---------------------------------------------------------------------------
# 默认值：G3 闭环那一组参数。改默认值等于改判据口径，改之前先读 docs/18 §2。
# ---------------------------------------------------------------------------
EXPECT_SHA="fcd0cf90bd680e7bbdc203e3398119504da0897acac9e2117008b4efb6b1f2c3"
LIMIT=2048
SCORE_MIN=67
ORIENT="both"
BOARD_IP="192.168.1.10"
BOARD_PORT=7
RESULT_TIMEOUT=""            # 空 = 按条数自动估
RUNS=1
TAG=""
DO_BOOT=1
DO_DUMP=1
DO_UART=1
STAGE1_DUMP_RECORDS=""       # 空 = min(本次记录数, 4096)，黄金向量只覆盖 4096 条
READS_FILE="data/R0.83_data/Sequencing data/DNA-40.5Kb-MC-SE150.fastq"
WM_FILE="data/R0.83_data/Source data/Watermark sequences/r0.83_watermark.txt"

WIN_ROOT_UNIX="/mnt/d/dna_board_smoke"
WIN_ROOT_WIN="D:/dna_board_smoke"
XSDB_BAT="D:/dev_tools/Vivado_Lab/2022.2/bin/xsdb.bat"
JTAG_DEVICE="xc7z010"

usage() {
    sed -n '2,45p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'
    exit "${1:-0}"
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        --limit)            LIMIT="$2"; shift 2 ;;
        --full)             LIMIT=""; shift ;;          # 不传 --limit 给 first.py = 全量
        --score-min)        SCORE_MIN="$2"; shift 2 ;;
        --orient)           ORIENT="$2"; shift 2 ;;
        --result-timeout)   RESULT_TIMEOUT="$2"; shift 2 ;;
        --runs)             RUNS="$2"; shift 2 ;;
        --tag)              TAG="$2"; shift 2 ;;
        --ip)               BOARD_IP="$2"; shift 2 ;;
        --port)             BOARD_PORT="$2"; shift 2 ;;
        --reads)            READS_FILE="$2"; shift 2 ;;
        --watermark)        WM_FILE="$2"; shift 2 ;;
        --expect-sha)       EXPECT_SHA="$2"; shift 2 ;;
        --stage1-records)   STAGE1_DUMP_RECORDS="$2"; shift 2 ;;
        --skip-boot)        DO_BOOT=0; shift ;;
        --skip-dump)        DO_DUMP=0; shift ;;
        --no-uart)          DO_UART=0; shift ;;
        -h|--help)          usage 0 ;;
        *) echo "未知参数：$1" >&2; usage 2 ;;
    esac
done

# ---------------------------------------------------------------------------
# 记账：每一步的 PASS/FAIL 都登记，最后统一裁决。
# ---------------------------------------------------------------------------
declare -a STEP_NAMES=() STEP_STATES=() STEP_NOTES=()
FAILED=0

step_ok()   { STEP_NAMES+=("$1"); STEP_STATES+=("PASS"); STEP_NOTES+=("${2:-}"); }
step_bad()  { STEP_NAMES+=("$1"); STEP_STATES+=("FAIL"); STEP_NOTES+=("${2:-}"); FAILED=1; }
step_skip() { STEP_NAMES+=("$1"); STEP_STATES+=("SKIP"); STEP_NOTES+=("${2:-}"); }

say()  { printf '\n\033[1m=== %s ===\033[0m\n' "$*"; }
info() { printf '    %s\n' "$*"; }
die()  { printf '\n\033[31mFATAL: %s\033[0m\n' "$*" >&2; exit 2; }

# ---------------------------------------------------------------------------
# 0. 参数推导
# ---------------------------------------------------------------------------
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
RUN_NAME="$STAMP${TAG:+-$TAG}"
RUN_DIR="$WIN_ROOT_UNIX/g3_runs/$RUN_NAME"
RUN_DIR_WIN="$WIN_ROOT_WIN/g3_runs/$RUN_NAME"

detect_reads() {
    # FASTQ 每条记录 4 行；只在需要推导记录数时才数，全量文件数一次约 1 s。
    awk 'END{print int(NR/4)}' "$READS_FILE"
}

if [[ -z "$LIMIT" ]]; then
    SOURCE_READS="$(detect_reads)"
else
    SOURCE_READS="$LIMIT"
fi
MULT=1; [[ "$ORIENT" == "both" ]] && MULT=2
RECORDS=$(( SOURCE_READS * MULT ))
# 板端按 64 的倍数对齐（first.py 补零到整批），dump 与判据都按对齐后的条数算。
RECORDS=$(( (RECORDS + 63) / 64 * 64 ))

if [[ -z "$RESULT_TIMEOUT" ]]; then
    # 第五次上板实测：4,096 条记录的 result 阶段 32.4 s，其中约 97% 是 Stage1（随条数线性）。
    # 这里按 (常数 20 s + 每条 10 ms) 再乘 2 倍余量取整，宁可等也不要被超时掩盖真故障。
    RESULT_TIMEOUT=$(( (20 + RECORDS / 100) * 2 ))
    (( RESULT_TIMEOUT < 180 )) && RESULT_TIMEOUT=180
fi

if [[ -z "$STAGE1_DUMP_RECORDS" ]]; then
    STAGE1_DUMP_RECORDS=$(( RECORDS < 4096 ? RECORDS : 4096 ))
fi

# UART 抓取窗口：烧录 + RUNS 轮任务 + 余量。有 StopFile 收尾，这里只是兜底上限。
UART_SECONDS=$(( 90 + RUNS * (RESULT_TIMEOUT + 60) ))

say "G3 一键复现  run=$RUN_NAME"
info "源读段    : $SOURCE_READS 条（--orient $ORIENT）→ 对齐后 $RECORDS 条记录"
info "score_min : $SCORE_MIN"
info "任务次数  : $RUNS（同一次上电内连续下发）"
info "结果超时  : ${RESULT_TIMEOUT}s（板端处理期间一个字节都不发，这是整条流水线的时长上限）"
info "判据哈希  : $EXPECT_SHA"
info "留证目录  : $RUN_DIR"

# ---------------------------------------------------------------------------
# 1. 前置检查：环境、数据、制品同源性
# ---------------------------------------------------------------------------
say "1/7 前置检查"

for f in "$READS_FILE" "$WM_FILE" tools/ldpc_decode.py tools/board_stage_check.py \
         clients/python/first.py hw/build/export/SHA256SUMS; do
    [[ -e "$f" ]] || die "缺少 $f"
done
info "仓库内数据与脚本齐备"

[[ -d "$WIN_ROOT_UNIX" ]] || die "看不到 $WIN_ROOT_UNIX（Windows 侧工作目录未挂载？）"
XSDB_UNIX="/mnt/$(echo "${XSDB_BAT:0:1}" | tr 'A-Z' 'a-z')${XSDB_BAT:2}"
[[ -f "$XSDB_UNIX" ]] || die "找不到 xsdb.bat：$XSDB_BAT（WSL 视角 $XSDB_UNIX）"
command -v cmd.exe >/dev/null || die "调不到 cmd.exe，无法驱动 Windows 侧工具"
info "Windows 侧工具可达（xsdb.bat / cmd.exe）"

mkdir -p "$RUN_DIR" || die "建不了留证目录 $RUN_DIR"

# 制品同源性：先按 SHA256SUMS 校验 export/，再把校验过的副本放进本轮 run 目录。
# 这样「板上跑的是哪一版」有据可查，也不会被 D:\dna_board_smoke\ 里的历史同名文件顶掉。
if ! ( cd hw/build/export && sha256sum -c --quiet --ignore-missing SHA256SUMS ) 2>"$RUN_DIR/sha256sums.err"; then
    cat "$RUN_DIR/sha256sums.err" >&2
    die "hw/build/export/ 与 SHA256SUMS 不符 —— 制品与源码不同源，禁止上板"
fi
step_ok "制品同源性（hw/build/export/ vs SHA256SUMS）"
info "export/ 全部制品与 SHA256SUMS 相符"

BIT_SRC="hw/build/export/top_bd_wrapper.bit"
ELF_SRC="hw/build/export/dna_lwip_app_b27.elf"
[[ -f "$BIT_SRC" ]] || die "缺少 $BIT_SRC"
[[ -f "$ELF_SRC" ]] || die "缺少 $ELF_SRC"

cp -f "$BIT_SRC" "$RUN_DIR/top_bd_wrapper.bit"
cp -f "$ELF_SRC" "$RUN_DIR/dna_lwip_app.elf"
# ps7_init.tcl 只存在于 gitignore 掉的 sw/workspace/ 里，不可作为复现来源；
# 改从受版本管理、且刚校验过哈希的 dna_accel.xsa（就是个 zip）里解出来。
if ! unzip -o -q -j hw/build/export/dna_accel.xsa ps7_init.tcl -d "$RUN_DIR" 2>/dev/null; then
    die "从 hw/build/export/dna_accel.xsa 里解不出 ps7_init.tcl"
fi
info "bit / elf / ps7_init.tcl 已从受版本管理的制品复制到 run 目录"

# ---------------------------------------------------------------------------
# 2. 渲染板级脚本
# ---------------------------------------------------------------------------
say "2/7 渲染板级脚本"

render() {
    sed -e "s#@@DEVICE@@#$JTAG_DEVICE#g" \
        -e "s#@@BITFILE@@#$RUN_DIR_WIN/top_bd_wrapper.bit#g" \
        -e "s#@@ELFFILE@@#$RUN_DIR_WIN/dna_lwip_app.elf#g" \
        -e "s#@@PS7INIT@@#$RUN_DIR_WIN/ps7_init.tcl#g" \
        -e "s#@@OUTDIR@@#$RUN_DIR_WIN#g" \
        -e "s#@@WM_WORDS@@#47850#g" \
        -e "s#@@STAGE1_RECORDS@@#$STAGE1_DUMP_RECORDS#g" \
        -e "s#@@STAGE1_WORDS@@#$(( STAGE1_DUMP_RECORDS * 12 ))#g" \
        -e "s#@@STAGE2_WORDS@@#2532#g" \
        -e "s#@@STAGE3_WORDS@@#2026#g" \
        "$1" > "$2"
}
render tools/board/g3_boot.tcl.in "$RUN_DIR/boot.tcl"
render tools/board/g3_dump.tcl.in "$RUN_DIR/dump.tcl"
cp -f tools/board/g3_uart_cap.ps1 "$RUN_DIR/uart_cap.ps1"
info "boot.tcl / dump.tcl / uart_cap.ps1 已渲染到 run 目录（原样留证）"

# ---------------------------------------------------------------------------
# 3. 串口实录（后台）
# ---------------------------------------------------------------------------
UART_LOG="$RUN_DIR/uart.log"
STOP_FILE="$RUN_DIR/uart.stop"
UART_PID=""

stop_uart() {
    [[ -n "$UART_PID" ]] || return 0
    : > "$STOP_FILE"
    # 给它一个 500 ms 读超时周期把尾巴写完，再等进程自己收尾。
    for _ in $(seq 1 20); do
        kill -0 "$UART_PID" 2>/dev/null || break
        sleep 0.5
    done
    kill -0 "$UART_PID" 2>/dev/null && kill "$UART_PID" 2>/dev/null
    UART_PID=""
}
trap stop_uart EXIT INT TERM

say "3/7 串口实录"
if (( DO_UART )); then
    powershell.exe -NoProfile -ExecutionPolicy Bypass \
        -File "$(echo "$RUN_DIR_WIN/uart_cap.ps1" | tr '/' '\\')" \
        -LogPath "$(echo "$RUN_DIR_WIN/uart.log" | tr '/' '\\')" \
        -Seconds "$UART_SECONDS" \
        -StopFile "$(echo "$RUN_DIR_WIN/uart.stop" | tr '/' '\\')" \
        > "$RUN_DIR/uart_cap.out" 2>&1 &
    UART_PID=$!
    sleep 3
    # 判据要正着写：必须看到 CAPTURING 才算抓起来了。
    # 只查 OPEN_FAIL 不够 —— 第一次实跑就栽在这：ps1 被 PowerShell 5.1 当 GBK 解析、
    # param() 块直接语法错误，进程压根没跑到打开串口那一步，
    # 于是「没有 OPEN_FAIL」被误判成成功，整轮跑完才发现根本没有串口实录。
    if grep -q "^CAPTURING" "$RUN_DIR/uart_cap.out" 2>/dev/null; then
        info "COM6@115200 抓取中，上限 ${UART_SECONDS}s（收工时用 stop 文件收尾）"
    else
        info "串口实录没起来（COM6 被占用？或 ps1 解析失败），详见 $RUN_DIR/uart_cap.out"
        sed -n '1,6p' "$RUN_DIR/uart_cap.out" 2>/dev/null | sed 's/^/      /'
        step_skip "串口实录" "未能启动，见 uart_cap.out"
        UART_PID=""
        DO_UART=0
    fi
else
    step_skip "串口实录" "--no-uart"
fi

# ---------------------------------------------------------------------------
# 4. 烧录
# ---------------------------------------------------------------------------
say "4/7 烧录（rst -system → fpga → ps7_init → dow → con）"
wait_board() {
    local deadline=$(( SECONDS + ${1:-60} ))
    while (( SECONDS < deadline )); do
        if timeout 2 bash -c "echo > /dev/tcp/$BOARD_IP/$BOARD_PORT" 2>/dev/null; then
            return 0
        fi
        sleep 2
    done
    return 1
}

if (( DO_BOOT )); then
    if ( cd "$WIN_ROOT_UNIX" && cmd.exe /c "$(echo "$XSDB_BAT" | tr '/' '\\') $(echo "$RUN_DIR_WIN/boot.tcl" | tr '/' '\\')" ) \
            > "$RUN_DIR/boot.out" 2>&1; then
        if grep -q "BOOT> running" "$RUN_DIR/boot.out"; then
            step_ok "烧录"
            info "$(grep '^BOOT>' "$RUN_DIR/boot.out" | tr '\n' ' ')"
        else
            step_bad "烧录" "xsdb 退出码为 0 但没打印 BOOT> running"
            sed -n '1,40p' "$RUN_DIR/boot.out"
        fi
    else
        step_bad "烧录" "xsdb 非零退出，见 $RUN_DIR/boot.out"
        sed -n '1,40p' "$RUN_DIR/boot.out"
    fi
else
    step_skip "烧录" "--skip-boot"
fi

say "5/7 等待板端网络就绪"
if wait_board 90; then
    step_ok "板端 TCP:$BOARD_PORT 可达"
    info "$BOARD_IP:$BOARD_PORT 已就绪"
else
    step_bad "板端 TCP:$BOARD_PORT 可达" "90 s 内连不上 $BOARD_IP:$BOARD_PORT"
fi

# 网络都不通就没必要往下跑了，后面每一步都会以另一种面目失败，反而掩盖真因。
if (( FAILED )); then
    say "前置步骤已失败，终止（不再下发任务，避免用假故障掩盖真因）"
    stop_uart
fi

# ---------------------------------------------------------------------------
# 5. 逐轮任务：first.py → ldpc_decode.py → 比哈希
# ---------------------------------------------------------------------------
declare -a RUN_SHAS=()
if (( ! FAILED )); then
say "6/7 下发任务并比对判据哈希（共 $RUNS 轮）"
for (( r = 1; r <= RUNS; r++ )); do
    BITS_OUT="$RUN_DIR/dec_input_run$r.txt"
    IMG_OUT="$RUN_DIR/decoded_run$r.jpg"
    CLI_LOG="$RUN_DIR/first_run$r.log"

    info "--- 第 $r/$RUNS 轮：first.py ---"
    FIRST_ARGS=(--ip "$BOARD_IP" --port "$BOARD_PORT"
                --reads "$READS_FILE" --watermark "$WM_FILE"
                --output "$BITS_OUT" --orient "$ORIENT"
                --score-min "$SCORE_MIN" --result-timeout "$RESULT_TIMEOUT")
    [[ -n "$LIMIT" ]] && FIRST_ARGS+=(--limit "$LIMIT")

    T0=$SECONDS
    if ! python3 clients/python/first.py "${FIRST_ARGS[@]}" > "$CLI_LOG" 2>&1; then
        step_bad "第 $r 轮 first.py" "非零退出，见 $CLI_LOG"
        tail -20 "$CLI_LOG"
        break
    fi
    T_RUN=$(( SECONDS - T0 ))
    RESULT_LINE="$(grep -E '^\s+Result:' "$CLI_LOG" | tail -1)"
    step_ok "第 $r 轮 first.py" "$RESULT_LINE"
    info "耗时 ${T_RUN}s；$RESULT_LINE"

    info "--- 第 $r/$RUNS 轮：ldpc_decode.py ---"
    if ! python3 tools/ldpc_decode.py decode "$BITS_OUT" \
            -o "$RUN_DIR/decoded_bits_run$r.txt" --image "$IMG_OUT" \
            > "$RUN_DIR/ldpc_run$r.log" 2>&1; then
        step_bad "第 $r 轮 LDPC 译码" "非零退出，见 $RUN_DIR/ldpc_run$r.log"
        tail -20 "$RUN_DIR/ldpc_run$r.log"
        break
    fi
    grep -E "失败校验|收敛|iter" "$RUN_DIR/ldpc_run$r.log" | head -4 | sed 's/^/    /'

    GOT_SHA="$(sha256sum "$IMG_OUT" | awk '{print $1}')"
    RUN_SHAS+=("$GOT_SHA")
    if [[ "$GOT_SHA" == "$EXPECT_SHA" ]]; then
        step_ok "第 $r 轮 唯一判据（图片 SHA-256）" "$GOT_SHA"
        info "图片 SHA-256 = $GOT_SHA  ← 与判据逐位相同"
    else
        step_bad "第 $r 轮 唯一判据（图片 SHA-256）" "实得 $GOT_SHA"
        info "实得 : $GOT_SHA"
        info "判据 : $EXPECT_SHA"
    fi
done
fi

# 二次任务的附加判据：两轮必须拿到同一张图片。哈希都对时这条自然成立，
# 但若判据哈希本身换过（--expect-sha），这条仍然能独立抓出「第二轮状态没复位」。
if (( RUNS > 1 && ${#RUN_SHAS[@]} == RUNS )); then
    if [[ "$(printf '%s\n' "${RUN_SHAS[@]}" | sort -u | wc -l)" == "1" ]]; then
        step_ok "多轮一致性（$RUNS 轮同一张图片）"
    else
        step_bad "多轮一致性（$RUNS 轮同一张图片）" "$(printf '%s ' "${RUN_SHAS[@]}")"
    fi
fi

# ---------------------------------------------------------------------------
# 6. 逐级取证：只读导出四级 DDR 快照（不复位、不重烧）
# ---------------------------------------------------------------------------
say "7/7 逐级取证（XSDB 只读 DDR，不复位不重烧）"
if (( DO_DUMP )) && (( ${#RUN_SHAS[@]} > 0 )); then
    if ( cd "$WIN_ROOT_UNIX" && cmd.exe /c "$(echo "$XSDB_BAT" | tr '/' '\\') $(echo "$RUN_DIR_WIN/dump.tcl" | tr '/' '\\')" ) \
            > "$RUN_DIR/dump.out" 2>&1 && grep -q "DUMP> stage3 done" "$RUN_DIR/dump.out"; then
        info "四级快照已导出到 $RUN_DIR"
        if python3 tools/board_stage_check.py --dump-dir "$RUN_DIR" --reads "$STAGE1_DUMP_RECORDS" \
                > "$RUN_DIR/stage_check.log" 2>&1; then
            step_ok "四级逐级取证（board_stage_check.py）"
        else
            step_bad "四级逐级取证（board_stage_check.py）" "见 $RUN_DIR/stage_check.log"
        fi
        sed -n '/^===/,$p' "$RUN_DIR/stage_check.log" | sed 's/^/    /'
    else
        step_bad "四级快照导出" "见 $RUN_DIR/dump.out"
        tail -20 "$RUN_DIR/dump.out"
    fi
else
    step_skip "四级逐级取证" "$( (( DO_DUMP )) && echo '任务未跑到出结果' || echo '--skip-dump')"
fi

stop_uart

# ---------------------------------------------------------------------------
# 7. 裁决
# ---------------------------------------------------------------------------
SUMMARY="$RUN_DIR/summary.txt"
{
    echo "G3 一键复现  run=$RUN_NAME"
    echo "时间(UTC)   : $STAMP"
    echo "命令        : tools/run_g3.sh $*"
    echo "源读段/记录 : $SOURCE_READS / $RECORDS （--orient $ORIENT，对齐 64）"
    echo "score_min   : $SCORE_MIN"
    echo "任务次数    : $RUNS"
    echo "结果超时    : ${RESULT_TIMEOUT}s"
    echo "bitstream   : $(sha256sum "$RUN_DIR/top_bd_wrapper.bit" | awk '{print $1}')"
    echo "ELF         : $(sha256sum "$RUN_DIR/dna_lwip_app.elf" | awk '{print $1}')"
    echo "判据哈希    : $EXPECT_SHA"
    echo
    printf '%-6s  %s\n' "结果" "步骤"
    for i in "${!STEP_NAMES[@]}"; do
        printf '%-6s  %s%s\n' "${STEP_STATES[$i]}" "${STEP_NAMES[$i]}" \
            "$( [[ -n "${STEP_NOTES[$i]}" ]] && echo "  — ${STEP_NOTES[$i]}" )"
    done
} > "$SUMMARY"

say "结果汇总"
cat "$SUMMARY"
echo
info "全部留证：$RUN_DIR"

if (( FAILED )); then
    printf '\n\033[31m######## G3 FAIL ########\033[0m\n'
    printf '唯一判据是图片 SHA-256；上面第一个 FAIL 就是要定位的那一级。\n'
    exit 1
fi
# 没跑出任何一轮结果就谈不上 PASS —— 别让「一步都没做」被当成通过。
if (( ${#RUN_SHAS[@]} < RUNS )); then
    printf '\n\033[31m######## G3 FAIL ########\033[0m\n'
    printf '预期 %d 轮，实际只完成 %d 轮。\n' "$RUNS" "${#RUN_SHAS[@]}"
    exit 1
fi
printf '\n\033[32m######## G3 PASS ########\033[0m\n'
printf '板端回传经 LDPC 译码后的图片 SHA-256 与判据逐位相同：%s\n' "$EXPECT_SHA"
exit 0
