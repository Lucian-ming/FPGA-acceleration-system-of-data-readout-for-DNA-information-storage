#!/usr/bin/env bash
# =============================================================================
# tools/run_g3.sh —— G3 板级验收的一键复现入口
#
# 为什么要有它
# ------------
# G3 在 2026-08-30 第五次上板闭环，但当时的验收是跨 Windows/WSL 的一串手工步骤：
# 开串口抓取 → xsdb 烧录 → first.py 跑任务 → 板端 syndrome 判据 + 系统 SHA + 主机诊断 →
# xsdb 只读导出四级 DDR → board_stage_check.py。**判据要能被一条命令复现，才算真的钉住。**
# 这轮的教训正是「摸索过程本身就会引入错误」（B23~B27 五个缺陷在所有仿真里都是绿的，
# 只有上板才暴露），所以复现路径本身不能再靠人记步骤。
#
# 判据纪律（AGENTS.md「事实边界」）
# --------------------------------
# 界面成功、TCP 返回结果、四级取证全绿，**都不算 G3 通过**。
#
# 三层判据（2026-10-14 更正：**架构与系统都须过**才判 G3 通过）
#   · 架构判据：板端回传码字的 syndrome 是否全零 —— 回答「板端到底纠对了没有」。
#     它挡住的是**主机译码兜底**：板端没纠对，靠 PC 补出来也算过。
#   · 系统判据：从板端合法码字直接载荷出的字节 SHA 是否等于期望 ——
#     回答「载荷出来的就是期望的那一份吗」。它挡住的是**合法但错误的码字**：
#     syndrome 全零、架构 PASS，可是载荷不是期望的。
#   · 诊断层：主机译码 + SHA 的旧口径，**只记录**，任何情况下都不参与裁决。
#   · 四级检查器退出码 3 表示 UNVERIFIED（没有可用黄金基准）：它表示未取证，
#     不能据此判硬件 FAIL，也不抵消架构与系统判据；退出码 1 或其他非零仍判步骤 FAIL。
# ⚠️ 早先的写法只让架构判据决定裁决。那比旧口径（「只对译码后的板端回传作判定」）
#    **更宽**——上面第二类错误会被判 PASS，所以已经改掉。反过来，系统判据也**不能**
#    在架构 FAIL 时独自救场，那正是要杜绝的 PC 兜底。
#
# 制品选择与证据边界
# ------------------
# 默认兼容旧 hw/build/export；xc7z020 或 --strict-artifacts 验收必须显式指定完整包。
# bit/XSA/ELF/FSBL/BOOT/manifest/source_manifest 均校验SHA，且核对XSA实际part、
# 内置bit和HWH生产参数。ps7_init只从选中XSA提取，禁止新bit+旧PS7混搭。
# 校验只证明包内一致；源码到制品的因果关系仍须审查源manifest和构建日志。
#
# 用法
# ----
#   tools/run_g3.sh                                   # 复现 G3 闭环那组参数（2048 条源读段）
#   tools/run_g3.sh --limit 4096                      # 分档测量：源读段数翻倍
#   tools/run_g3.sh --limit 2048 --skip-boot          # 板子已在跑，只重跑任务
#   tools/run_g3.sh --artifact-dir <export> --xsdb /tools/Xilinx/Vitis/2022.2/bin/xsdb --hw-server TCP:127.0.0.1:3132 --device xc7z020 --uart-port /dev/ttyUSB2 --win-root /tmp/bkb220-g3
#   tools/run_g3.sh --win-root D:/dna_board_smoke
#   tools/run_g3.sh --bit <path>                      # 仅兼容指定所选包内同一bit，禁止独立覆盖
#   tools/run_g3.sh --elf <path>                      # 仅允许选中包内同一ELF；独立实验也要完整制品包
#   tools/run_g3.sh --full --result-timeout 1800      # 全量数据集
#   tools/run_g3.sh --input-bytes 3862 --expect-sha <SHA256> --reads <reads.fastq> --watermark <watermark.txt>
#                                                     # 任意载荷按外部元数据字节数截断并比较 SHA
#   tools/run_g3.sh --runs 2                          # 同一次上电内连续跑两次任务（状态复位判据）
#   tools/run_g3.sh --runs 2 --first-run-score-min 0  # 第一轮弄脏 Voter 累加器，第二轮才是判据
#   tools/run_g3.sh --runs 2 --first-run-limit full --first-run-score-min 0
#                                                     # 跨规模：先全量（弄脏），再回到默认小规模判据
#   tools/run_g3.sh --runs 6 --run-score-mins 0,67,60,67,0,67
#                                                     # 多轮：奇数轮弄脏、偶数轮判据（每轮换 score_min）
#   tools/run_g3.sh --runs 3 --run-limits full,2048,full --run-score-mins 0,67,67
#                                                     # 逐轮指定条数与阈值（'-' = 用全局默认，'full' = 全量）
#   tools/run_g3.sh --runs 6 --run-score-mins 0,67,60,67,0,67 --plan-only
#                                                     # 只打印逐轮计划，不碰板子（自查参数）
#   tools/run_g3.sh --offline-recheck <已有 G3 留证目录>
#                                                     # 只读复算三层判据，不访问硬件
#   tools/run_g3.sh --ready-deadline 150              # 板端就绪探针（CAPS 握手）多等一会儿
#
# 旧ECO默认环境（新板按docs/07-board-build-and-acceptance.md和实际目标核对）
# --------------------------------------
#   Windows 侧 D:\dev_tools\Vivado_Lab\2022.2\bin\xsdb.bat，从 WSL 用 cmd.exe /c 调用；
#   工作目录 D:\dna_board_smoke\；JTAG Digilent 210251A08870，器件 xc7z010_1；
#   串口 CH340 = COM6@115200（一次只能一个进程占用）；
#   主机 192.168.1.100/24，板子 192.168.1.10，WSL 可直连 TCP:7。
# =============================================================================
set -uo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO"

# 原样存下本次调用参数：下面的解析循环会 shift 掉 "$@"，
# 而 summary.txt 是留证，必须记准「这一轮是怎么跑的」。
INVOCATION="$*"

# --elf/--bit 仅允许指向完整选中制品包内同一文件，禁止独立覆盖混搭
ELF_OVERRIDE=""
BIT_OVERRIDE=""
ARTIFACT_DIR="hw/build/export"
ARTIFACT_EXPLICIT=0
STRICT_ARTIFACTS=0
ALLOW_UART_SKIP=0

# ---------------------------------------------------------------------------
# 默认值：G3 闭环那一组参数。改默认值等于改判据口径，改之前先读 docs/07-board-build-and-acceptance.md和docs/04-interfaces.md。
# ---------------------------------------------------------------------------
EXPECT_SHA="fcd0cf90bd680e7bbdc203e3398119504da0897acac9e2117008b4efb6b1f2c3"
INPUT_BYTES=""
INPUT_BYTES_SET=0
LIMIT=2048
SCORE_MIN=67
READ_BPS=150
ORIENT="both"
BOARD_IP="${G3_BOARD_IP:-192.168.1.10}"
IP_EXPLICIT=0
[[ -n "${G3_BOARD_IP:-}" ]] && IP_EXPLICIT=1
BOARD_PORT=7
RESULT_TIMEOUT=""            # 空 = 按条数自动估
READY_DEADLINE=90            # 板端「应用层就绪」探针最多等多少秒（见第 5 步）
RUNS=1
TAG=""
DO_BOOT=1
DO_DUMP=1
DO_UART=1
UART_PORT="${UART_PORT:-}"
STAGE1_DUMP_RECORDS=""       # 空 = min(本次记录数, 4096)，黄金向量只覆盖 4096 条
# 【二次任务判据的关键】第一轮用一个**不同的** score_min 把 Voter 累加器「弄脏」。
# 为什么必须不同：Voter 的票是有符号累加（±1，饱和到 [-512,+511]），
# 输出按符号判决（differential_voter_v1_0.v:569 `~bram_dout[9] && (bram_dout != 0)`）。
# 两轮用**同一组参数**时，票的更新 x <- clip(x ± 1) 对起始值单调不减，于是第一轮
# 终值 v>0 => w>=v>0、v<0 => w<=v<0、v=0 => w=0，符号判决三种情况全不变 ——
# 输出逐位相同，**无论累加器有没有清零，且与输入规模无关**。
# （别用「票数翻倍所以保号」解释：撞上饱和后「翻倍」这个描述本身就不成立，
#   拿它去论证饱和区没问题是循环论证。完整推导见 docs/03-status.md 的盲区小节。）
# 也就是说「两轮同哈希」根本证明不了累加器被复位，这条判据没有鉴别力。
# 换个 score_min，两轮票集不同，残留就会在**一部分位**上翻符号而露馅。
# 注意这是统计上足够、而非逐位必然：vot_ddr 的 inject=c4 实测 4.49% 误码
# （720/1266 拍不符），足以让逐位判据变红，但别指望「差一位也必然被抓到」。
# 正因如此，本脚本把「弄脏轮鉴别力自证」做成硬判据：两轮原始回传若相同即 FAIL。
SCORE_MIN_RUN1=""            # 空 = 各轮都用 --score-min
# 逐轮参数（比 --first-run-* 更一般，供三轮以上与跨规模连续任务使用）。
# 逗号分隔，第 r 项对应第 r 轮；'-' 或空 = 沿用全局默认；'full' = 全量数据集。
RUN_LIMITS=""
RUN_SCORE_MINS=""
LIMIT_RUN1=""
# 「弄脏强度」硬校验：弄脏轮的 score_min 必须**低于**判据轮的，理由见下面的 dirty_strength 检查。
ALLOW_WEAK_DIRTY=0
PLAN_ONLY=0                  # 只打印逐轮计划就退出，不碰板子（用来自查参数表）
OFFLINE_RECHECK_DIR=""      # 只读复算既有留证；绝不执行烧录/串口/TCP/XSDB 流程
READS_FILE="data/R0.83_data/Sequencing data/DNA-40.5Kb-MC-SE150.fastq"
WM_FILE="data/R0.83_data/Source data/Watermark sequences/r0.83_watermark.txt"

WIN_ROOT_VALUE="${G3_WIN_ROOT:-D:/dna_board_smoke}"
WIN_ROOT_EXPLICIT=0
XSDB_VALUE="${G3_XSDB:-D:/dev_tools/Vivado_Lab/2022.2/bin/xsdb.bat}"
HW_SERVER_URL="${G3_HW_SERVER_URL:-}"
JTAG_DEVICE="${G3_DEVICE:-}"
XSDB_MODE="windows"

# 使用同一转换函数，支持 Windows 盘符、反斜杠和 /mnt/<盘符>/，拒绝相对/UNC猜测。
path_pair() {
    python3 - "$1" <<'PY'
import sys
from tools.board.g3_artifacts import normalize_windows_path
try:
    print("\n".join(normalize_windows_path(sys.argv[1])))
except ValueError as error:
    print(error, file=sys.stderr); raise SystemExit(2)
PY
}

usage() {
    # 头部注释块就是帮助正文。结束位置用 `set -uo pipefail` 那行现找，不再写死行号——
    # 旧写法固定到第 53 行，头部改过之后已经把 4 行代码当帮助打了出来。
    sed -n '2,/^set -uo pipefail$/p' "${BASH_SOURCE[0]}" | sed '$d' | sed 's/^# \{0,1\}//'
    exit "${1:-0}"
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        --artifact-dir)     ARTIFACT_DIR="$2"; ARTIFACT_EXPLICIT=1; shift 2 ;;
        --strict-artifacts) STRICT_ARTIFACTS=1; shift ;;
        --xsdb)             XSDB_VALUE="$2"; shift 2 ;;
        --hw-server)        HW_SERVER_URL="$2"; shift 2 ;;
        --device)           JTAG_DEVICE="$2"; shift 2 ;;
        --win-root)         WIN_ROOT_VALUE="$2"; WIN_ROOT_EXPLICIT=1; shift 2 ;;
        --limit)            LIMIT="$2"; shift 2 ;;
        --full)             LIMIT=""; shift ;;          # 不传 --limit 给 first.py = 全量
        --score-min)        SCORE_MIN="$2"; shift 2 ;;
        --read-bps)         READ_BPS="$2"; shift 2 ;;
        --first-run-score-min) SCORE_MIN_RUN1="$2"; shift 2 ;;
        --first-run-limit)  LIMIT_RUN1="$2"; shift 2 ;;
        --run-limits)       RUN_LIMITS="$2"; shift 2 ;;
        --run-score-mins)   RUN_SCORE_MINS="$2"; shift 2 ;;
        --allow-weak-dirty) ALLOW_WEAK_DIRTY=1; shift ;;
        --plan-only)        PLAN_ONLY=1; shift ;;
        --offline-recheck)  OFFLINE_RECHECK_DIR="$2"; shift 2 ;;
        --orient)           ORIENT="$2"; shift 2 ;;
        --result-timeout)   RESULT_TIMEOUT="$2"; shift 2 ;;
        --ready-deadline)   READY_DEADLINE="$2"; shift 2 ;;
        --runs)             RUNS="$2"; shift 2 ;;
        --tag)              TAG="$2"; shift 2 ;;
        --ip)               BOARD_IP="$2"; IP_EXPLICIT=1; shift 2 ;;
        --port)             BOARD_PORT="$2"; shift 2 ;;
        --reads)            READS_FILE="$2"; shift 2 ;;
        --watermark)        WM_FILE="$2"; shift 2 ;;
        --expect-sha)       EXPECT_SHA="$2"; shift 2 ;;
        --input-bytes)
            if [[ $# -lt 2 ]]; then echo "--input-bytes 需要一个字节数 N" >&2; exit 2; fi
            INPUT_BYTES="$2"; INPUT_BYTES_SET=1; shift 2 ;;
        --stage1-records)   STAGE1_DUMP_RECORDS="$2"; shift 2 ;;
        --skip-boot)        DO_BOOT=0; shift ;;
        --elf)              ELF_OVERRIDE="$2"; shift 2 ;;
        --bit)              BIT_OVERRIDE="$2"; shift 2 ;;
        --skip-dump)        DO_DUMP=0; shift ;;
        --no-uart)          DO_UART=0; shift ;;
        --allow-uart-skip)  ALLOW_UART_SKIP=1; shift ;;
        --uart-port)        UART_PORT="$2"; shift 2 ;;
        -h|--help)          usage 0 ;;
        *) echo "未知参数：$1" >&2; usage 2 ;;
    esac
done

# 离线复算入口必须在任何路径转换、工具/串口检查和 run 目录创建之前分流。
# g3_judge.py 的中间产物只落在临时目录；历史留证目录保持只读。
if [[ -n "$OFFLINE_RECHECK_DIR" ]]; then
    RECHECK_ARGS=(--offline-recheck "$OFFLINE_RECHECK_DIR" --expect-sha "$EXPECT_SHA")
    [[ -n "$INPUT_BYTES" ]] && RECHECK_ARGS+=(--input-bytes "$INPUT_BYTES")
    exec python3 tools/board/g3_judge.py "${RECHECK_ARGS[@]}"
fi

# ---------------------------------------------------------------------------
# 记账：每一步的 PASS/FAIL 都登记，最后统一裁决。
# ---------------------------------------------------------------------------
declare -a STEP_NAMES=() STEP_STATES=() STEP_NOTES=()
FAILED=0

step_ok()   { STEP_NAMES+=("$1"); STEP_STATES+=("PASS"); STEP_NOTES+=("${2:-}"); }
step_bad()  { STEP_NAMES+=("$1"); STEP_STATES+=("FAIL"); STEP_NOTES+=("${2:-}"); FAILED=1; }
step_skip() { STEP_NAMES+=("$1"); STEP_STATES+=("SKIP"); STEP_NOTES+=("${2:-}"); }
record_stage_check_result() {
    local status="$1"
    case "$status" in
        0) step_ok "四级逐级取证（board_stage_check.py）" ;;
        3) step_skip "四级逐级取证（board_stage_check.py）" \
            "本轮四级未取证（退出码 3；UNVERIFIED 不判硬件 FAIL），见 $RUN_DIR/stage_check.log" ;;
        *) step_bad "四级逐级取证（board_stage_check.py）" \
            "board_stage_check.py 退出码 $status；见 $RUN_DIR/stage_check.log" ;;
    esac
}

say()  { printf '\n\033[1m=== %s ===\033[0m\n' "$*"; }
info() { printf '    %s\n' "$*"; }
die()  { printf '\n\033[31mFATAL: %s\033[0m\n' "$*" >&2; exit 2; }
warn() { printf '\033[33m    %s\033[0m\n' "$*" >&2; }

# ---------------------------------------------------------------------------
# 0. 参数推导
# ---------------------------------------------------------------------------
[[ "$RUNS" =~ ^[1-9][0-9]*$ ]] || die "--runs 必须为正整数"
if (( INPUT_BYTES_SET )); then
    [[ "$INPUT_BYTES" =~ ^[1-9][0-9]*$ ]] || die "--input-bytes 必须为 1..6750 的正整数"
    (( ${#INPUT_BYTES} <= 4 )) || die "--input-bytes 必须为 1..6750，实得 $INPUT_BYTES"
    (( INPUT_BYTES <= 6750 )) || die "--input-bytes 必须为 1..6750，实得 $INPUT_BYTES"
fi
[[ "$TAG" =~ ^[A-Za-z0-9_.-]*$ ]] || die "--tag 只允许字母/数字/点/横线/下划线"
[[ "$ORIENT" == "both" || "$ORIENT" == "fwd" || "$ORIENT" == "rev" ]] || die "未知 orient"
# xc7z020 是新板严格验收的明确标记；调用者也可在不传 --device 时显式收紧。
[[ "${JTAG_DEVICE,,}" == "xc7z020" || "${JTAG_DEVICE,,}" == xc7z020* ]] && STRICT_ARTIFACTS=1
if [[ "$XSDB_VALUE" == /* ]]; then
    XSDB_MODE="wsl"
    STRICT_ARTIFACTS=1
    XSDB_UNIX="$XSDB_VALUE"
    XSDB_BAT="(WSL 本机) $XSDB_VALUE"
    [[ -x "$XSDB_UNIX" ]] || die "WSL XSDB 不存在或不可执行：$XSDB_UNIX"
    [[ -n "$HW_SERVER_URL" ]] || die "WSL XSDB 必须显式传 --hw-server TCP:127.0.0.1:3132"
    [[ "$HW_SERVER_URL" =~ ^TCP:[A-Za-z0-9.-]+:[0-9]{1,5}$ ]] || die "--hw-server 格式必须为 TCP:<主机>:<端口>"
    (( WIN_ROOT_EXPLICIT )) || die "WSL XSDB 必须显式传 --win-root <WSL 绝对留证目录>"
    [[ "$WIN_ROOT_VALUE" == /* ]] || die "WSL XSDB 的 --win-root 必须是 Linux 绝对路径"
    WIN_ROOT_UNIX="$(realpath -m "$WIN_ROOT_VALUE")"
    WIN_ROOT_WIN="$WIN_ROOT_UNIX"
else
    PAIR="$(path_pair "$WIN_ROOT_VALUE")" || die "--win-root 路径转换失败"
    WIN_ROOT_WIN="$(printf '%s\n' "$PAIR" | head -1)"
    WIN_ROOT_UNIX="$(printf '%s\n' "$PAIR" | tail -1)"
    PAIR="$(path_pair "$XSDB_VALUE")" || die "--xsdb 路径转换失败"
    XSDB_BAT="$(printf '%s\n' "$PAIR" | head -1)"
    XSDB_UNIX="$(printf '%s\n' "$PAIR" | tail -1)"
fi
if (( STRICT_ARTIFACTS && ! ARTIFACT_EXPLICIT )); then
    die "新板严格验收模式必须显式传 --artifact-dir；拒绝默认 hw/build/export legacy 回退"
fi
if (( STRICT_ARTIFACTS && ! IP_EXPLICIT )); then
    die "新板严格验收模式必须显式传 --ip <实测板端IP>"
fi
if [[ -n "$HW_SERVER_URL" ]]; then
    [[ "$HW_SERVER_URL" =~ ^TCP:[A-Za-z0-9.-]+:[0-9]{1,5}$ ]] || die "--hw-server 格式必须为 TCP:<主机>:<端口>"
    CONNECT_CMD="connect -url {$HW_SERVER_URL}"
else
    CONNECT_CMD="connect"
fi
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
RUN_NAME="$STAMP${TAG:+-$TAG}"
RUN_DIR="$WIN_ROOT_UNIX/g3_runs/$RUN_NAME"
RUN_DIR_WIN="$WIN_ROOT_WIN/g3_runs/$RUN_NAME"

FULL_READS=""
detect_reads() {
    # FASTQ 每条记录 4 行；只在需要推导记录数时才数，全量文件数一次约 1 s（数完就缓存）。
    [[ -n "$FULL_READS" ]] || FULL_READS="$(awk 'END{print int(NR/4)}' "$READS_FILE")"
    printf '%s' "$FULL_READS"
}

records_of() {
    # 源读段数 → 板端记录数：--orient both 每条读段发正/反两条记录，再按 64 对齐
    # （first.py 补零到整批），dump 与判据都按对齐后的条数算。
    local mult=1 rec
    [[ "$ORIENT" == "both" ]] && mult=2
    rec=$(( $1 * mult ))
    printf '%s' $(( (rec + 63) / 64 * 64 ))
}

timeout_of() {
    # 显式给了 --result-timeout 就一律用它；否则按本轮条数估。
    # 第五次上板实测：4,096 条记录的 result 阶段 32.4 s；按 (常数 20 s + 每条 10 ms)
    # 再乘 2 倍余量取整，宁可等也不要被超时掩盖真故障。
    local t
    if [[ -n "$RESULT_TIMEOUT" ]]; then printf '%s' "$RESULT_TIMEOUT"; return; fi
    t=$(( (20 + $1 / 100) * 2 ))
    (( t < 180 )) && t=180
    printf '%s' "$t"
}

# ---------------------------------------------------------------------------
# 逐轮参数表：连续任务的每一轮可以有**不同的条数和不同的 score_min**。
# 为什么要逐轮：
#   - 换条数 → 覆盖「跨不同规模的连续任务」（DDR 里还留着上一轮更长的中间结果）；
#   - 换 score_min → 让「Voter 累加器没清零」这条缺陷可观测（同参数下它结构性不可观测，
#     推导见 docs/03-status.md 盲区小节）。
# 优先级：--first-run-* > --run-limits/--run-score-mins 的第 r 项 > 全局默认。
# ---------------------------------------------------------------------------
IFS=',' read -r -a LIM_SEQ  <<< "$RUN_LIMITS"
IFS=',' read -r -a SM_SEQ   <<< "$RUN_SCORE_MINS"
declare -a RUN_LIMIT=() RUN_SM=() RUN_SR=() RUN_REC=() RUN_TO=()

for (( r = 1; r <= RUNS; r++ )); do
    lim="$LIMIT"
    if (( ${#LIM_SEQ[@]} >= r )) && [[ -n "${LIM_SEQ[r-1]}" && "${LIM_SEQ[r-1]}" != "-" ]]; then
        lim="${LIM_SEQ[r-1]}"
    fi
    [[ $r -eq 1 && -n "$LIMIT_RUN1" ]] && lim="$LIMIT_RUN1"
    [[ "$lim" == "full" || "$lim" == "all" ]] && lim=""      # 空 = 不传 --limit = 全量

    sm="$SCORE_MIN"
    if (( ${#SM_SEQ[@]} >= r )) && [[ -n "${SM_SEQ[r-1]}" && "${SM_SEQ[r-1]}" != "-" ]]; then
        sm="${SM_SEQ[r-1]}"
    fi
    [[ $r -eq 1 && -n "$SCORE_MIN_RUN1" && $RUNS -gt 1 ]] && sm="$SCORE_MIN_RUN1"

    [[ -z "$lim" || "$lim" =~ ^[1-9][0-9]*$ ]] || die "第 $r 轮 limit 必须为正整数或 full"
    [[ "$sm" =~ ^[0-9]+$ ]] && (( sm <= 511 )) || die "第 $r 轮 score_min 必须为0..511"
    if [[ -z "$lim" ]]; then
        [[ -f "$READS_FILE" ]] || die "全量计划缺少reads文件"
        sr="$(detect_reads)"
    else sr="$lim"; fi
    rec="$(records_of "$sr")"
    RUN_LIMIT+=("$lim"); RUN_SM+=("$sm"); RUN_SR+=("$sr")
    RUN_REC+=("$rec");  RUN_TO+=("$(timeout_of "$rec")")
done

# 全局展示量与四级取证都按**最后一轮**算 —— DDR 里留下的就是最后一轮的结果。
SOURCE_READS="${RUN_SR[RUNS-1]}"
RECORDS="${RUN_REC[RUNS-1]}"
RESULT_TIMEOUT_LAST="${RUN_TO[RUNS-1]}"

if [[ -z "$STAGE1_DUMP_RECORDS" ]]; then
    STAGE1_DUMP_RECORDS=$(( RECORDS < 4096 ? RECORDS : 4096 ))
fi

# UART 抓取窗口：烧录 + 各轮超时之和 + 余量。有 StopFile 收尾，这里只是兜底上限。
UART_SECONDS=90
for (( r = 0; r < RUNS; r++ )); do
    UART_SECONDS=$(( UART_SECONDS + RUN_TO[r] + 60 ))
done

say "G3 一键复现  run=$RUN_NAME"
info "任务次数  : $RUNS（同一次上电内连续下发，中间不复位、不重烧）"
for (( r = 1; r <= RUNS; r++ )); do
    tag=""
    [[ "${RUN_SM[r-1]}" != "$SCORE_MIN" ]] && tag="  ← 弄脏轮（输出不作判据）"
    info "  第 $r 轮 : 源读段 $(printf '%8s' "${RUN_SR[r-1]}") 条 → $(printf '%7s' "${RUN_REC[r-1]}") 条记录，score_min=${RUN_SM[r-1]}，超时 ${RUN_TO[r-1]}s$tag"
done
info "判据 score_min : $SCORE_MIN（只有这个阈值的轮次作为判据轮）"
info "载荷输出模式 : $( [[ -n "$INPUT_BYTES" ]] && echo "原始字节截断（$INPUT_BYTES B）" || echo 'JPEG EOI 截断' )"
info "系统 SHA  : $EXPECT_SHA（架构判据与系统判据都须过才是 G3 通过）"
info "留证目录  : $RUN_DIR"
info "XSDB 模式 : $XSDB_MODE${HW_SERVER_URL:+，hw_server=$HW_SERVER_URL}"

# ---------------------------------------------------------------------------
# 0.5 弄脏强度：结构性校验，跑之前就挡住「不会失败的判据」
#
# 「弄脏轮 → 判据轮」这套判据要成立，弄脏轮必须在累加器里留下**与判据轮反向**的票。
# 只有**降低**阈值才做得到：score_min 越低放进来的错配读段越多，它们的票方向是错的。
# 提高阈值只是把判据轮那批高分记录取了个子集，残差与判据轮同向 —— 缺陷若存在，
# 单调性保证符号判决不变（推导见 docs/03-status.md 盲区小节），判据照样全绿。
#
# 离线量化（tools/readout.py 语义，2,048 条读段，模拟「未清零」缺陷后判据轮的码字差异）：
#     弄脏 score_min :    0      40      60      75      90
#     码字差异 bit   : 1654    1654    1240       3       0
# 75 那一档特别值得看：它自身输出与判据轮差 5,415 bit（现有的「两轮回传不同」自证
# 会通过），但缺陷真的存在时只差 3 bit —— LDPC 顺手就纠回去了，判据仍然全绿。
# 也就是说「两轮回传不同」是**必要非充分**条件，必须再加这条结构性校验。
# ---------------------------------------------------------------------------
for (( r = 2; r <= RUNS; r++ )); do
    [[ "${RUN_SM[r-1]}" == "$SCORE_MIN" && "${RUN_SM[r-2]}" != "$SCORE_MIN" ]] || continue
    # 规模稀释：弄脏轮条数少于判据轮时，残差会被判据轮自己的票淹没 —— 这一对
    # 对「累加器没清零」同样没有鉴别力，但它对**跨规模**（DDR 里的长度/缓冲复用）
    # 仍然有效，所以只提示、不拦。离线实测：2,048 条 score_min=0 弄脏后跑全量判据轮，
    # 缺陷若存在码字差异 0/64,800 bit（票数 ~190/位，把 ±15 的残差整个盖掉）；
    # 反过来（全量弄脏 → 2,048 条判据）是 1,155/64,800 bit，红得很清楚。
    if (( RUN_REC[r-2] < RUN_REC[r-1] )); then
        info "⚠️ 第 $(( r - 1 )) 轮只有 ${RUN_REC[r-2]} 条记录，少于第 $r 轮的 ${RUN_REC[r-1]} 条："
        info "   残差会被判据轮自己的票淹没，这一对只覆盖跨规模，不覆盖累加器复位"
    fi
    if (( RUN_SM[r-2] >= SCORE_MIN )); then
        if (( ALLOW_WEAK_DIRTY )); then
            info "⚠️ 第 $(( r - 1 )) 轮 score_min=${RUN_SM[r-2]} ≥ 判据轮 $SCORE_MIN：残差与判据轮同向，"
            info "   这一对「弄脏→判据」对累加器复位没有鉴别力（--allow-weak-dirty 已放行）"
        else
            die "第 $(( r - 1 )) 轮 score_min=${RUN_SM[r-2]} ≥ 判据轮的 $SCORE_MIN：提高阈值只会留下同向的票，
     第 $r 轮即使不清零也照样全绿 —— 这条判据不会失败，跑了也没有信息量。
     要弄脏就用**更低**的 score_min（如 0 或 60）。确要跑请显式加 --allow-weak-dirty。"
        fi
    fi
done

# 计划模式也运行只读制品/工具门禁，避免批准后才发现 XSA/PS7 混搭。
ARTIFACT_ARGS=(--artifact-dir "$ARTIFACT_DIR" --read-bps "$READ_BPS")
if (( ! ARTIFACT_EXPLICIT && ! STRICT_ARTIFACTS )); then ARTIFACT_ARGS+=(--allow-legacy); fi
[[ -n "$JTAG_DEVICE" ]] && ARTIFACT_ARGS+=(--device "$JTAG_DEVICE")
[[ -n "$BIT_OVERRIDE" ]] && ARTIFACT_ARGS+=(--bit "$BIT_OVERRIDE")
[[ -n "$ELF_OVERRIDE" ]] && ARTIFACT_ARGS+=(--elf "$ELF_OVERRIDE")
SELECTION="$(python3 tools/board/g3_artifacts.py "${ARTIFACT_ARGS[@]}")" || die "完整制品选择门禁失败"
JTAG_DEVICE="$(python3 -c 'import json,sys; print(json.load(sys.stdin)["device"])' <<< "$SELECTION")"
info "制品包     : $ARTIFACT_DIR，目标 $JTAG_DEVICE"
info "制品证据   : $SELECTION"
if (( DO_BOOT || DO_DUMP )); then
    if [[ "$XSDB_MODE" == "wsl" ]]; then
        [[ -x "$XSDB_UNIX" ]] || die "找不到可执行 WSL XSDB：$XSDB_UNIX"
    else
        [[ -f "$XSDB_UNIX" ]] || die "找不到 XSDB：$XSDB_BAT（WSL: $XSDB_UNIX）；请 --xsdb 指定本机安装"
        command -v powershell.exe >/dev/null || die "调不到powershell.exe，无法驱动Windows工具"
    fi
fi
info "留证根       : $WIN_ROOT_WIN（本机路径: $WIN_ROOT_UNIX）"
info "XSDB          : $XSDB_BAT"
if (( PLAN_ONLY )); then
    info "--plan-only：只读制品/工具核验完成，不打开串口、不连接JTAG、不下发TCP、不创建run"
    if [[ -n "$UART_PORT" ]]; then
        info "串口选择      : $UART_PORT"
    elif [[ "$XSDB_MODE" == "wsl" ]]; then
        info "串口选择      : 运行时必须显式传 --uart-port。BKB220 2026-10-12 实测：PS UART=UART0/MIO14-15 → FT4232H 通道 C = /dev/ttyUSB2（见 docs/board/bkb220/migration-source-table.md §9）"
    else
        info "串口选择      : Windows 运行时按唯一 USB 串口选择；多口必须显式 --uart-port"
    fi
    info "串口裁决      : $([[ "$ALLOW_UART_SKIP" -eq 1 ]] && echo '排错放宽(--allow-uart-skip)' || echo '验收严格(必须打开且收到数据)')"
    [[ "$XSDB_MODE" == "wsl" ]] && info "WSL hw_server : $HW_SERVER_URL"
    exit 0
fi

# ---------------------------------------------------------------------------
# 1. 前置检查：环境、数据、制品同源性
# ---------------------------------------------------------------------------
say "1/7 前置检查"

for f in "$READS_FILE" "$WM_FILE" tools/ldpc_decode.py tools/board/g3_judge.py \
         clients/python/ldpc_pipeline.py tools/board_stage_check.py \
         clients/python/first.py tools/board/g3_wait_ready.py tools/board/g3_xsdb.ps1 \
         "$ARTIFACT_DIR/SHA256SUMS"; do
    [[ -e "$f" ]] || die "缺少 $f"
done
info "仓库内数据与脚本齐备"

if [[ "$XSDB_MODE" == "wsl" ]]; then
    mkdir -p "$WIN_ROOT_UNIX" || die "不能创建 WSL 留证根目录：$WIN_ROOT_UNIX"
else
    [[ -d "$WIN_ROOT_UNIX" ]] || die "看不到 $WIN_ROOT_UNIX（Windows 侧工作目录未挂载？）"
fi
[[ ! -e "$RUN_DIR" ]] || die "本轮留证目录已存在，禁止覆盖：$RUN_DIR（换 --tag 或稍后重试）"
mkdir -p "$RUN_DIR" || die "建不了留证目录 $RUN_DIR"
python3 tools/board/g3_artifacts.py "${ARTIFACT_ARGS[@]}" --stage "$RUN_DIR" \
    > "$RUN_DIR/artifact_selection.out" || die "制品复制前复核失败"
step_ok "完整制品包一致性（所选SHA/XSA内bit/part/参数）" "$ARTIFACT_DIR"
info "bit / elf / ps7_init 均来自所选同一XSA制品包；摘要见 artifact_selection.json"

# ---------------------------------------------------------------------------
# 2. 渲染板级脚本
# ---------------------------------------------------------------------------
say "2/7 渲染板级脚本"

if [[ "$READ_BPS" -eq 250 ]]; then
    WM_WORDS=52750
    STAGE1_REC_WORDS=18
    STAGE1_ADDR="0x10900000"
    STAGE2_ADDR="0x11200000"
    STAGE3_ADDR="0x11300000"
else
    WM_WORDS=47850
    STAGE1_REC_WORDS=12
    STAGE1_ADDR="0x10600000"
    STAGE2_ADDR="0x11000000"
    STAGE3_ADDR="0x11100000"
fi

render() {
    [[ "$RUN_DIR_WIN" != *'&'* && "$RUN_DIR_WIN" != *'#'* && "$RUN_DIR_WIN" != *'{'* && "$RUN_DIR_WIN" != *'}'* ]] || die "留证路径含Tcl/sed保留字符"
    sed -e "s#@@CONNECT_CMD@@#$CONNECT_CMD#g" \
        -e "s#@@DEVICE@@#$JTAG_DEVICE#g" \
        -e "s#@@BITFILE@@#$RUN_DIR_WIN/top_bd_wrapper.bit#g" \
        -e "s#@@ELFFILE@@#$RUN_DIR_WIN/dna_lwip_app.elf#g" \
        -e "s#@@PS7INIT@@#$RUN_DIR_WIN/ps7_init.tcl#g" \
        -e "s#@@OUTDIR@@#$RUN_DIR_WIN#g" \
        -e "s#@@WM_WORDS@@#$WM_WORDS#g" \
        -e "s#@@STAGE1_RECORDS@@#$STAGE1_DUMP_RECORDS#g" \
        -e "s#@@STAGE1_WORDS@@#$(( STAGE1_DUMP_RECORDS * STAGE1_REC_WORDS ))#g" \
        -e "s#@@STAGE1_ADDR@@#$STAGE1_ADDR#g" \
        -e "s#@@STAGE2_ADDR@@#$STAGE2_ADDR#g" \
        -e "s#@@STAGE3_ADDR@@#$STAGE3_ADDR#g" \
        -e "s#@@STAGE2_WORDS@@#2532#g" \
        -e "s#@@STAGE3_WORDS@@#2026#g" \
        "$1" > "$2"
}
render tools/board/g3_boot.tcl.in "$RUN_DIR/boot.tcl"
render tools/board/g3_dump.tcl.in "$RUN_DIR/dump.tcl"
cp -f tools/board/g3_uart_cap.ps1 "$RUN_DIR/uart_cap.ps1"
cp -f tools/board/g3_xsdb.ps1 "$RUN_DIR/xsdb_run.ps1"
info "boot.tcl / dump.tcl / uart_cap.ps1 已渲染到 run 目录（原样留证）"

# ---------------------------------------------------------------------------
# 3. 串口实录（后台）
# ---------------------------------------------------------------------------
UART_LOG="$RUN_DIR/uart.log"
STOP_FILE="$RUN_DIR/uart.stop"
UART_PID=""
UART_CAPTURE_STARTED=0

uart_unavailable() {
    local detail="$1"
    if (( ALLOW_UART_SKIP )); then
        step_skip "串口实录" "$detail（--allow-uart-skip 排错放宽）"
    else
        step_bad "串口实录" "$detail；验收模式要求串口可打开且本轮收到输出"
    fi
}

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
    if [[ "$XSDB_MODE" == "wsl" ]]; then
        if [[ -z "$UART_PORT" || "$UART_PORT" != /dev/ttyUSB[0-9]* ]]; then
            uart_unavailable "WSL 串口必须显式指定为 /dev/ttyUSBn；BKB220 实测 PS UART 在通道 C = /dev/ttyUSB2（2026-10-12，见来源表 §9）"
            DO_UART=0
        elif [[ ! -e "$UART_PORT" ]]; then
            uart_unavailable "串口设备不存在：$UART_PORT"
            DO_UART=0
        else
            python3 tools/board/g3_uart_cap.py --device "$UART_PORT" --log "$UART_LOG" \
                --seconds "$UART_SECONDS" --stop-file "$STOP_FILE" \
                > "$RUN_DIR/uart_cap.out" 2>&1 &
            UART_PID=$!
            sleep 1
            if grep -q '^CAPTURING ' "$RUN_DIR/uart_cap.out" 2>/dev/null; then
                UART_CAPTURE_STARTED=1
                info "$UART_PORT@115200 抓取中，上限 ${UART_SECONDS}s（WSL 本地串口；收工时用 stop 文件收尾）"
            else
                uart_unavailable "WSL 串口采集未能启动，见 uart_cap.out"
                sed -n '1,8p' "$RUN_DIR/uart_cap.out" 2>/dev/null | sed 's/^/      /'
                wait "$UART_PID" 2>/dev/null || true
                UART_PID=""
                DO_UART=0
            fi
        fi
    else
        # 只读枚举 USB/FTDI 串口。蓝牙COM和历史COM不作为兜底。
        UART_DEVICES="$(powershell.exe -NoProfile -Command 'ConvertTo-Json -Compress -InputObject @(Get-PnpDevice -PresentOnly -Class Ports | Select-Object FriendlyName,InstanceId)' < /dev/null | tr -d '\r')"
        if [[ $? -ne 0 ]]; then
            uart_unavailable "枚举 USB 串口失败"
            DO_UART=0
        else
            SELECTED_UART="$(python3 - "$UART_DEVICES" "$UART_PORT" <<'PY'
import json,sys
from tools.board.g3_artifacts import choose_uart
try:
    print(choose_uart(json.loads(sys.argv[1]), sys.argv[2] or None))
except (ValueError,TypeError) as error:
    print(error, file=sys.stderr); raise SystemExit(2)
PY
            )"
            if [[ $? -ne 0 ]]; then
                uart_unavailable "不能明确确定 USB/PS 串口；请传 --uart-port COMx，不要选蓝牙 COM"
                DO_UART=0
            else
                UART_PORT="$SELECTED_UART"
                powershell.exe -NoProfile -ExecutionPolicy Bypass \
                    -File "$(echo "$RUN_DIR_WIN/uart_cap.ps1" | tr '/' '\\')" \
                    -LogPath "$(echo "$RUN_DIR_WIN/uart.log" | tr '/' '\\')" \
                    -Seconds "$UART_SECONDS" \
                    -StopFile "$(echo "$RUN_DIR_WIN/uart.stop" | tr '/' '\\')" \
                    -PortName "$UART_PORT" \
                    < /dev/null \
                    > "$RUN_DIR/uart_cap.out" 2>&1 &
                UART_PID=$!
                sleep 3
                # 必须看见 CAPTURING；沉默失败不能伪装成一次有效采集。
                if grep -q "^CAPTURING" "$RUN_DIR/uart_cap.out" 2>/dev/null; then
                    UART_CAPTURE_STARTED=1
                    info "${UART_PORT}@115200 抓取中，上限 ${UART_SECONDS}s（收工时用 stop 文件收尾）"
                else
                    uart_unavailable "串口实录未启动，见 uart_cap.out"
                    sed -n '1,8p' "$RUN_DIR/uart_cap.out" 2>/dev/null | sed 's/^/      /'
                    wait "$UART_PID" 2>/dev/null || true
                    UART_PID=""
                    DO_UART=0
                fi
            fi
        fi
    fi
else
    uart_unavailable "--no-uart 已关闭串口采集"
fi

# ---------------------------------------------------------------------------
# 4. 烧录
# ---------------------------------------------------------------------------
say "4/7 烧录（rst -system → fpga → ps7_init → dow → con）"
if (( DO_BOOT )); then
    if [[ "$XSDB_MODE" == "wsl" ]]; then
        "$XSDB_UNIX" "$RUN_DIR/boot.tcl" > "$RUN_DIR/boot.out" 2>&1
    else
        powershell.exe -NoProfile -ExecutionPolicy Bypass \
            -File "$RUN_DIR_WIN/xsdb_run.ps1" -XsdbPath "$XSDB_BAT" \
            -TclPath "$RUN_DIR_WIN/boot.tcl" < /dev/null \
            > "$RUN_DIR/boot.out" 2>&1
    fi
    if [[ $? -eq 0 ]]; then
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

# ---------------------------------------------------------------------------
# 5. 等板端**应用层**就绪（B28）
# ---------------------------------------------------------------------------
# 这一步以前只探裸 TCP 连通性（`echo > /dev/tcp/IP/PORT`），那是 B28 的直接成因：
# 烧录完成后裸连通性立刻就「成功」，此时下发任务却必然失败（2026-09-03 实测 2/2），
# 固定死在 clients/python/protocol.py:76 recv_exact ← query_caps ——
# connect() 通、请求发得出去，读应答时对端已经把连接关掉，first.py 非零退出，
# 于是**每个实验的第一轮都被打红**，而红的是一个不存在的缺陷。
# 传输层有人应答 ≠ 应用层能回包，所以判据抬到应用层：必须收到合法的
# PKT_CAPS_INFO(0x16) 才算就绪。探针实测烧录后约 7 s 才通过，那 7 s 就是假失败的产地。
# 探针自己也做了 --settle 让位（板端 g_conn 是单例，关连接要占一个 tcp 回调周期）。
say "5/7 等待板端应用层就绪（CAPS 握手，探针 tools/board/g3_wait_ready.py）"
if (( FAILED )); then
    # 烧录已经红了还去等 90 s，等出来的失败信息会指向 CAPS，把真因（烧录）盖掉。
    step_skip "板端应用层就绪（CAPS）" "前置步骤已失败，不再探测"
else
    READY_LOG="$RUN_DIR/wait_ready.out"
    if python3 tools/board/g3_wait_ready.py --ip "$BOARD_IP" --port "$BOARD_PORT" \
            --deadline "$READY_DEADLINE" > "$READY_LOG" 2>&1; then
        READY_LINE="$(grep '^READY ' "$READY_LOG" | tail -1)"
        step_ok "板端应用层就绪（CAPS）" "$READY_LINE"
        info "$BOARD_IP:$BOARD_PORT $READY_LINE（READY <秒数> <尝试次数>；留证 $READY_LOG）"
    else
        step_bad "板端应用层就绪（CAPS）" \
                 "$READY_DEADLINE s 内 $BOARD_IP:$BOARD_PORT 没有正常应答 CAPS，见 $READY_LOG"
        # 逐次尝试的异常类型都在日志里：ConnectionRefusedError 之类是板子/网络没起来，
        # 连接期正常但 recv 失败则是应用层还没起来 —— 两者的处置完全不同，别只看结论行。
        tail -5 "$READY_LOG"
    fi
fi

# 网络都不通就没必要往下跑了，后面每一步都会以另一种面目失败，反而掩盖真因。
if (( FAILED )); then
    say "前置步骤已失败，终止（不再下发任务，避免用假故障掩盖真因）"
    stop_uart
fi

# ---------------------------------------------------------------------------
# 6. 逐轮任务：first.py → syndrome 架构判据 + 系统 SHA + 主机译码诊断
# ---------------------------------------------------------------------------
declare -a RUN_SHAS=()      # 判据轮的系统载荷 SHA（并行记录）
declare -a RUN_ELAPSED=()   # 逐轮 first.py 墙钟耗时，用来看长时间连续运行有没有退化
declare -a RUN_KIND=()      # judge / dirty
declare -a RUN_LAYER_REPORTS=()
RUNS_COMPLETED=0
json_field() {
    python3 - "$1" "$2" <<'PYJSON'
import json
import sys
with open(sys.argv[1], encoding="utf-8") as stream:
    value = json.load(stream).get(sys.argv[2])
if isinstance(value, bool):
    print("true" if value else "false")
elif value is None:
    print("")
else:
    print(value)
PYJSON
}
if (( ! FAILED )); then
say "6/7 下发任务并记录三层判据（共 $RUNS 轮）"
for (( r = 1; r <= RUNS; r++ )); do
    BITS_OUT="$RUN_DIR/dec_input_run$r.txt"
    if [[ -n "$INPUT_BYTES" ]]; then
        PAYLOAD_OUT="$RUN_DIR/decoded_run$r.payload"
    else
        PAYLOAD_OUT="$RUN_DIR/decoded_run$r.jpg"
    fi
    CLI_LOG="$RUN_DIR/first_run$r.log"

    RUN_SCORE_MIN="${RUN_SM[r-1]}"
    RUN_THIS_LIMIT="${RUN_LIMIT[r-1]}"
    # 「弄脏轮」= score_min 与判据轮不同的轮次：它只为在 Voter 累加器里留下
    # 与判据轮不同向的残差，其自身输出不作旧多轮系统 SHA 一致性比较。
    DIRTY_RUN=0
    [[ "$RUN_SCORE_MIN" != "$SCORE_MIN" ]] && DIRTY_RUN=1
    RUN_KIND+=("$( (( DIRTY_RUN )) && echo dirty || echo judge )")

    info "--- 第 $r/$RUNS 轮：first.py（源读段 ${RUN_SR[r-1]} → ${RUN_REC[r-1]} 条记录，score_min=$RUN_SCORE_MIN）---"
    (( DIRTY_RUN )) && info "本轮是「弄脏轮」：score_min=$RUN_SCORE_MIN（与判据轮的 $SCORE_MIN 不同），其系统 SHA 仅记录"
    FIRST_ARGS=(--ip "$BOARD_IP" --port "$BOARD_PORT"
                --reads "$READS_FILE" --watermark "$WM_FILE"
                --output "$BITS_OUT" --orient "$ORIENT"
                --result-timeout "${RUN_TO[r-1]}"
                --read-bps "$READ_BPS")
    [[ -n "$RUN_THIS_LIMIT" ]] && FIRST_ARGS+=(--limit "$RUN_THIS_LIMIT")
    FIRST_ARGS+=(--score-min "$RUN_SCORE_MIN")

    T0=$SECONDS
    if python3 clients/python/first.py "${FIRST_ARGS[@]}" > "$CLI_LOG" 2>&1; then
        FIRST_RC=0
    else
        FIRST_RC=$?
    fi
    T_RUN=$(( SECONDS - T0 ))
    RUN_ELAPSED+=("$T_RUN")
    RESULT_LINE="$(grep -E '^\s+Result:' "$CLI_LOG" | tail -1)"
    if (( FIRST_RC == 0 )); then
        step_ok "第 $r 轮 first.py 原始回传" "${RUN_REC[r-1]} 条记录 / score_min=$RUN_SCORE_MIN / ${T_RUN}s；$RESULT_LINE"
    elif [[ -s "$BITS_OUT" ]] && grep -Eq '板端未纠对|校验行非零' "$CLI_LOG"; then
        # first.py 在保存原始码字后会因 BoardCodeRejected 退出 1。
        # 这是架构判据失败，不是传输失败；仍跑主机诊断以保留旧口径可比性。
        step_ok "第 $r 轮 first.py 原始回传" "TCP 结果已留存；客户端发现 syndrome 非零并退出 1，见 $CLI_LOG"
    else
        step_bad "第 $r 轮 first.py" "非零退出码 $FIRST_RC，未发现可复算的板端 syndrome 拒绝；见 $CLI_LOG"
        tail -20 "$CLI_LOG"
        break
    fi
    info "耗时 ${T_RUN}s；${RESULT_LINE:-客户端未报告 Result 行}"

    LAYER_DIR="$RUN_DIR/g3_layers_run$r"
    LAYER_JSON="$RUN_DIR/g3_layers_run$r.json"
    LAYER_REPORT="$RUN_DIR/g3_layers_run$r.txt"
    JUDGE_ARGS=(--bits "$BITS_OUT" --output-dir "$LAYER_DIR" --json-out "$LAYER_JSON"
                --expect-sha "$EXPECT_SHA"
                --host-bits-out "$RUN_DIR/decoded_bits_run$r.txt"
                --host-payload-out "$PAYLOAD_OUT"
                --host-log-out "$RUN_DIR/ldpc_run$r.log")
    [[ -n "$INPUT_BYTES" ]] && JUDGE_ARGS+=(--input-bytes "$INPUT_BYTES")
    if python3 tools/board/g3_judge.py "${JUDGE_ARGS[@]}" > "$LAYER_REPORT" 2>"$RUN_DIR/g3_judge_run$r.err"; then
        JUDGE_RC=0
    else
        JUDGE_RC=$?
    fi
    if [[ ! -s "$LAYER_JSON" ]]; then
        step_bad "第 $r 轮三层判据计算" "工具退出码 $JUDGE_RC，见 $RUN_DIR/g3_judge_run$r.err"
        cat "$RUN_DIR/g3_judge_run$r.err" >&2
        break
    fi

    ARCH_STATUS="$(json_field "$LAYER_JSON" architecture_status)"
    ARCH_FAILED_ROWS="$(json_field "$LAYER_JSON" syndrome_failed_rows)"
    ARCH_TOTAL_ROWS="$(json_field "$LAYER_JSON" syndrome_total_rows)"
    SYSTEM_STATUS="$(json_field "$LAYER_JSON" system_status)"
    SYSTEM_SHA="$(json_field "$LAYER_JSON" system_sha256)"
    SYSTEM_SOURCE="$(json_field "$LAYER_JSON" system_source)"
    DIAGNOSTIC_NOTE="$(json_field "$LAYER_JSON" diagnostic_decoder)"
    DIAGNOSTIC_SHA="$(json_field "$LAYER_JSON" diagnostic_sha256)"
    LEGACY_STATUS="$(json_field "$LAYER_JSON" legacy_status)"
    PC_FALLBACK="$(json_field "$LAYER_JSON" pc_fallback_recovered_expected_sha)"
    RUN_LAYER_REPORTS+=("$LAYER_REPORT")

    if [[ "$ARCH_STATUS" == "PASS" ]]; then
        step_ok "第 $r 轮架构判据（板端 syndrome 全零）" "$ARCH_FAILED_ROWS/$ARCH_TOTAL_ROWS 条非零校验行"
    else
        step_bad "第 $r 轮架构判据（板端 syndrome 全零）" \
            "架构判据未过：板端未纠对，$ARCH_FAILED_ROWS/$ARCH_TOTAL_ROWS 条非零校验行"
    fi
    # 系统判据：架构过、但板端码字载荷出的字节不是期望的那一份 ⇒ 结果是错的，判 FAIL。
    # 架构没过时系统判据取的是 PC 诊断译码，那种情形下它只作比较，由上面那条架构判据定成败。
    if [[ "$ARCH_STATUS" == "PASS" ]]; then
        if [[ "$SYSTEM_STATUS" == "PASS" ]]; then
            step_ok "第 $r 轮系统判据（板端码字载荷 SHA）" "来源=$SYSTEM_SOURCE"
        else
            step_bad "第 $r 轮系统判据（板端码字载荷 SHA）" \
                "系统判据未过：板端码字合法但载荷不是期望的那一份（SHA=${SYSTEM_SHA:-无载荷}，期望 $EXPECT_SHA）"
        fi
    else
        info "系统判据（架构未过，取主机诊断译码，仅供比较）: $SYSTEM_STATUS；SHA=${SYSTEM_SHA:-无载荷}；来源=$SYSTEM_SOURCE"
    fi
    info "诊断层（不参与判定）: $DIAGNOSTIC_NOTE；主机译码 SHA=${DIAGNOSTIC_SHA:-不可用}；旧口径=$LEGACY_STATUS"
    [[ "$PC_FALLBACK" == "true" ]] && info "PC兜底告警：系统 SHA 通过但架构判据未过，旧口径依赖主机译码"
    [[ "$(json_field "$LAYER_JSON" verdict)" == "PASS" ]] || info "本轮三层裁决：FAIL"
    sed 's/^/    /' "$LAYER_REPORT"
    if [[ "${RUN_KIND[r-1]}" == "judge" && -n "$SYSTEM_SHA" ]]; then
        RUN_SHAS+=("$SYSTEM_SHA")
    fi
    RUNS_COMPLETED=$(( RUNS_COMPLETED + 1 ))
done
fi

# 「弄脏轮鉴别力自证」（每一对「弄脏轮 → 判据轮」都要各自过一遍）：
# 两轮的**板端原始回传比特流**必须不同。若相同，说明这一轮压根没在 Voter 累加器里
# 留下不同向的残差，那么下一轮通过也证明不了累加器被复位 —— 判据没有鉴别力，
# 必须报失败而不是报通过。用 pre-LDPC 的原始回传来比，不依赖弄脏轮能不能译出图片。
# 注意这是**必要非充分**条件，充分性由上面「弄脏强度」那条结构性校验补上。
for (( r = 2; r <= RUNS_COMPLETED; r++ )); do
    [[ "${RUN_KIND[r-1]:-}" == "judge" && "${RUN_KIND[r-2]:-}" == "dirty" ]] || continue
    A="$RUN_DIR/dec_input_run$(( r - 1 )).txt"
    B="$RUN_DIR/dec_input_run$r.txt"
    if [[ -f "$A" && -f "$B" ]]; then
        if cmp -s "$A" "$B"; then
            step_bad "第 $(( r - 1 ))→$r 轮 弄脏轮鉴别力自证" \
                "两轮回传比特流逐位相同 → 弄脏轮没起作用，本判据对累加器复位没有鉴别力"
        else
            DIFF_BITS="$(cmp -l "$A" "$B" | wc -l)"
            step_ok "第 $(( r - 1 ))→$r 轮 弄脏轮鉴别力自证" \
                "两轮回传相差 $DIFF_BITS/64800 bit，累加器确实被写入了不同向的票"
        fi
    else
        step_bad "第 $(( r - 1 ))→$r 轮 弄脏轮鉴别力自证" "缺少两轮的 dec_input，无法自证"
    fi
done

# 多轮一致性：记录所有判据轮的系统载荷 SHA，作为并行诊断信息。
if (( ${#RUN_SHAS[@]} > 1 )); then
    if [[ "$(printf '%s\n' "${RUN_SHAS[@]}" | sort -u | wc -l)" == "1" ]]; then
        step_ok "多轮系统 SHA 一致性（仅记录）" "${#RUN_SHAS[@]} 个判据轮哈希相同"
    else
        step_skip "多轮系统 SHA 一致性（仅记录）" "各轮哈希不同：$(printf '%s ' "${RUN_SHAS[@]}")；不参与三层裁决"
    fi
fi

# 长时间连续运行的退化判据：同参数（同条数、同 score_min）的轮次之间，
# 板端耗时不应随轮次增长。lwIP 的连接资源泄漏、BD 环退化、DDR 状态污染
# 最先表现出来的就是「越跑越慢」或「干脆连不上」（连不上会在 first.py 那步先红）。
# 阈值 1.5x：板端时长是确定性的（t = 28.90 s + 1.0012 ms/条，R² = 1.00000），
# 同参数轮次之间的正常抖动远小于 50%，所以这条**会**因真退化而变红。
if (( RUNS_COMPLETED > 2 )); then
    DEGRADED=0; DEG_NOTE=""; SEEN_KEYS=" "
    for (( i = 0; i < RUNS_COMPLETED; i++ )); do
        [[ -n "${RUN_ELAPSED[i]:-}" ]] || continue
        KEY="${RUN_REC[i]}/${RUN_SM[i]}"
        # 每个「条数/阈值」组合只在它首次出现时比一次，避免同一组被重复登记。
        [[ "$SEEN_KEYS" == *" $KEY "* ]] && continue
        SEEN_KEYS="$SEEN_KEYS$KEY "
        FIRST_T=""; LAST_T=""; CNT=0
        for (( j = i; j < RUNS_COMPLETED; j++ )); do
            [[ "${RUN_REC[j]}/${RUN_SM[j]}" == "$KEY" ]] || continue
            [[ -n "${RUN_ELAPSED[j]:-}" ]] || continue
            [[ -z "$FIRST_T" ]] && FIRST_T="${RUN_ELAPSED[j]}"
            LAST_T="${RUN_ELAPSED[j]}"; CNT=$(( CNT + 1 ))
        done
        (( CNT >= 2 && FIRST_T > 0 )) || continue
        if (( LAST_T * 100 > FIRST_T * 150 )); then
            DEGRADED=1
            DEG_NOTE="$DEG_NOTE ${KEY}: 首轮 ${FIRST_T}s → 末轮 ${LAST_T}s;"
        fi
    done
    ALL_T="$(printf '%s ' "${RUN_ELAPSED[@]}")"
    if (( DEGRADED )); then
        step_bad "连续运行无退化（同参数轮次耗时 < 1.5x）" "$DEG_NOTE 逐轮耗时：$ALL_T"
    else
        step_ok "连续运行无退化（同参数轮次耗时 < 1.5x）" "逐轮耗时：$ALL_T"
    fi
fi

# ---------------------------------------------------------------------------
# 7. 逐级取证：只读导出四级 DDR 快照（不复位、不重烧）
# ---------------------------------------------------------------------------
READS_SHA="$(sha256sum "$READS_FILE" | awk '{print $1}')"
say "7/7 逐级取证（XSDB 只读 DDR，不复位不重烧）"
if (( DO_DUMP )) && (( RUNS_COMPLETED > 0 )); then
    if [[ "$XSDB_MODE" == "wsl" ]]; then
        "$XSDB_UNIX" "$RUN_DIR/dump.tcl" > "$RUN_DIR/dump.out" 2>&1
    else
        powershell.exe -NoProfile -ExecutionPolicy Bypass \
            -File "$RUN_DIR_WIN/xsdb_run.ps1" -XsdbPath "$XSDB_BAT" \
            -TclPath "$RUN_DIR_WIN/dump.tcl" < /dev/null \
            > "$RUN_DIR/dump.out" 2>&1
    fi
    if [[ $? -eq 0 ]] && grep -q "DUMP> stage3 done" "$RUN_DIR/dump.out"; then
        info "四级快照已导出到 $RUN_DIR"
        if python3 tools/board_stage_check.py --dump-dir "$RUN_DIR" --reads "$STAGE1_DUMP_RECORDS" --read-bps "$READ_BPS" \
                --reads-sha256 "$READS_SHA" \
                > "$RUN_DIR/stage_check.log" 2>&1; then
            record_stage_check_result 0
        else
            record_stage_check_result "$?"
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

if (( UART_CAPTURE_STARTED )); then
    # uart_cap.out 由 Windows 侧采集脚本写，**行尾是 CRLF**；带 $ 锚点的正则会被 \r 顶掉，
    # 于是"明明收到了 7781 个字符"会被判成"没有可确认的输出"（2026-10-12 实测踩到）。
    # 所有对该文件的读取一律先 tr -d '\r' 归一化行尾。
    UART_CAP_TXT="$(tr -d '\r' < "$RUN_DIR/uart_cap.out" 2>/dev/null)"
    UART_COUNT="$(printf '%s\n' "$UART_CAP_TXT" | sed -nE 's/^CAPTURE_DONE (bytes|chars)=([0-9]+)$/\2/p' | tail -1)"
    if printf '%s\n' "$UART_CAP_TXT" | grep -Eq '^CAPTURE_DONE (bytes|chars)=[1-9][0-9]*$'; then
        step_ok "串口收到板端输出" "$UART_COUNT 个字符/字节；原始日志 uart.log"
    else
        uart_unavailable "串口打开后没有可确认的输出（count=${UART_COUNT:-未报告}），见 uart.log/uart_cap.out"
    fi
fi

WM_SHA="$(sha256sum "$WM_FILE" | awk '{print $1}')"

# ---------------------------------------------------------------------------
# 8. 裁决
# ---------------------------------------------------------------------------
SUMMARY="$RUN_DIR/summary.txt"
{
    echo "G3 一键复现  run=$RUN_NAME"
    echo "时间(UTC)   : $STAMP"
    echo "命令        : tools/run_g3.sh $INVOCATION"
    echo "任务次数    : $RUNS（同一次上电内连续下发，中间不复位、不重烧）"
    echo "判据阈值    : score_min=$SCORE_MIN（该阈值标识常规判据轮；每轮架构 syndrome 均判定）"
    echo "载荷字节数  : ${INPUT_BYTES:-JPEG EOI 截断}"
    echo "orient      : $ORIENT（both = 每条读段发正/反两条记录），记录数按 64 对齐"
    echo
    printf '%-4s %-10s %-9s %-9s %-7s %-8s %s\n' \
        "轮次" "类型" "源读段" "记录数" "阈值" "超时(s)" "实测耗时(s)"
    for (( r = 1; r <= RUNS; r++ )); do
        printf '%-4s %-10s %-9s %-9s %-7s %-8s %s\n' \
            "$r" "$( [[ "${RUN_SM[r-1]}" == "$SCORE_MIN" ]] && echo "判据轮" || echo "弄脏轮" )" \
            "${RUN_SR[r-1]}" "${RUN_REC[r-1]}" "${RUN_SM[r-1]}" "${RUN_TO[r-1]}" \
            "${RUN_ELAPSED[r-1]:-未跑}"
    done
    echo
    echo "四级取证按最后一轮算：Stage1 dump $STAGE1_DUMP_RECORDS 条记录"
    echo "bitstream   : $(sha256sum "$RUN_DIR/top_bd_wrapper.bit" | awk '{print $1}')"
    echo "ELF         : $(sha256sum "$RUN_DIR/dna_lwip_app.elf" | awk '{print $1}')"
    echo "制品目录    : $ARTIFACT_DIR"
    echo "制品严格模式: $([[ "$STRICT_ARTIFACTS" -eq 1 ]] && echo '是（legacy 禁止）' || echo '否（兼容旧板入口）')"
    echo "目标器件    : $JTAG_DEVICE"
    echo "XSDB        : $XSDB_BAT"
    echo "XSDB 模式   : $XSDB_MODE"
    echo "hw_server   : ${HW_SERVER_URL:-XSDB 默认连接}"
    echo "板端地址    : $BOARD_IP:$BOARD_PORT"
    echo "FASTQ SHA256: $READS_SHA"
    echo "水印 SHA256 : $WM_SHA"
    echo "串口裁决    : $([[ "$ALLOW_UART_SKIP" -eq 1 ]] && echo '排错放宽 --allow-uart-skip（可能带 SKIP）' || echo '验收严格（必须打开且收到输出）')"
    echo "串口接收量  : $(tr -d '\r' < "$RUN_DIR/uart_cap.out" 2>/dev/null | sed -nE 's/^CAPTURE_DONE (bytes|chars)=([0-9]+)$/\2/p' | tail -1)"
    echo "串口        : ${UART_PORT:-未抓取}"
    echo "制品细节    : artifact_selection.json（XSA/PS7/manifest/完整参数）"
    echo "期望系统 SHA: $EXPECT_SHA（系统判据；架构判据与它都须过才是 G3 通过）"
    echo
    echo "三层判据（架构与系统都须过；主机译码仅作诊断，不参与裁决）"
    for layer_report in "${RUN_LAYER_REPORTS[@]}"; do
        [[ -f "$layer_report" ]] || continue
        cat "$layer_report"
        echo
    done
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
    printf '本次架构判据或既有流程步骤失败；系统 SHA 与主机译码诊断不会覆盖 syndrome 失败。\n'
    exit 1
fi
# 没跑完所有轮次就谈不上 PASS —— 别让「一步都没做」被当成通过。
# 注意用 RUNS_COMPLETED 而不是 ${#RUN_SHAS[@]}：弄脏轮跑完了也不计入判据轮 SHA 汇总。
if (( RUNS_COMPLETED < RUNS )); then
    printf '\n\033[31m######## G3 FAIL ########\033[0m\n'
    printf '预期 %d 轮，实际只完成 %d 轮。\n' "$RUNS" "$RUNS_COMPLETED"
    exit 1
fi
# 判据轮一个都没有也不能算通过。
if (( ${#RUN_SHAS[@]} == 0 )); then
    printf '\n\033[31m######## G3 FAIL ########\033[0m\n'
    printf '没有任何一轮产出判据轮的系统 SHA。\n'
    exit 1
fi
printf '\n\033[32m######## G3 PASS ########\033[0m\n'
printf '板端回传 syndrome 全零；系统 SHA 与旧口径诊断结果见 summary.txt（不改变架构判据裁决）。\n'
exit 0
