#!/usr/bin/env bash
# =============================================================================
# tests/host/run_host_tests.sh — PS 固件（sw/app/echo.c）的主机侧判据入口
#
#   bash tests/host/run_host_tests.sh              # 用 HEAD 里的 echo.c（默认）
#   bash tests/host/run_host_tests.sh --worktree   # 用当前工作树的 echo.c
#   bash tests/host/run_host_tests.sh --rev <rev>  # 用任意 git 版本的 echo.c
#   bash tests/host/run_host_tests.sh --record     # 重录行为轨迹黄金文件
#   bash tests/host/run_host_tests.sh --selftest   # 故障注入：证明判据能失败
#
# **为什么默认不是工作树**：这棵工作树是多个会话共用的，别的会话的半成品就在
# 旁边（docs/21 §5）。默认编译 HEAD 里的 echo.c，判据才不会被别人的中间状态
# 搞成假红。真正做拆分时用 --worktree —— 那时「轨迹逐行相同」就是行为等价判据。
#
# 单一 PASS/FAIL + 非零退出码。
# =============================================================================
set -uo pipefail

cd "$(dirname "$0")/../.." || exit 1
ROOT=$(pwd)
BUILD=$(mktemp -d)
trap 'rm -rf "$BUILD"' EXIT

GOLDEN_DIR=tests/golden
TRACE_GOLDEN=tests/host/golden/echo_trace_se150_128reads.txt
TRACE_META=tests/host/golden/echo_trace_se150_128reads.meta
SHIM=tests/host/shim
CFLAGS="-O1 -std=gnu11 -Wall -Wextra -Wno-unused-parameter -Wno-int-to-pointer-cast -Wno-sign-compare -Wno-unused-variable -Wno-unused-function"

REV=HEAD
USE_WORKTREE=0
RECORD=0
SELFTEST=0
while [ $# -gt 0 ]; do
    case "$1" in
        --worktree) USE_WORKTREE=1 ;;
        --rev)      REV="$2"; shift ;;
        --record)   RECORD=1 ;;
        --selftest) SELFTEST=1 ;;
        -h|--help)  sed -n '2,20p' "$0"; exit 0 ;;
        *) echo "未知参数：$1"; exit 2 ;;
    esac
    shift
done

PASS=0
FAIL=0
note() { printf '\n=== %s ===\n' "$1"; }

# ---- 1) 取出被测的 sw/app（默认 HEAD，见上文） ------------------------------
SRC="$BUILD/src/sw/app"
mkdir -p "$BUILD/src"
if [ "$USE_WORKTREE" = 1 ]; then
    mkdir -p "$SRC"
    cp sw/app/*.h sw/app/*.c "$SRC/" || { echo "✗ 复制工作树 sw/app 失败"; exit 2; }
    ORIGIN="工作树"
else
    git archive "$REV" sw/app 2>/dev/null | tar -x -C "$BUILD/src" \
        || { echo "✗ 取不出版本 $REV 的 sw/app"; exit 2; }
    ORIGIN="git $REV ($(git rev-parse --short "$REV"))"
fi
ECHO_SHA=$(sha256sum "$SRC/echo.c" | cut -c1-16)
ECHO_LINES=$(wc -l < "$SRC/echo.c")
echo "被测固件：$ORIGIN    sw/app/echo.c  ${ECHO_LINES} 行  sha256:${ECHO_SHA}…"

build_one() {   # build_one <可执行名> <测试源文件> [echo.c 所在目录]
    local out="$1" src="$2" dir="${3:-$SRC}"
    gcc $CFLAGS -I "$dir" -I "$SHIM" -o "$BUILD/$out" "$src" "$SHIM/hostenv.c" \
        2>"$BUILD/$out.cc.log"
    local rc=$?
    if [ $rc -ne 0 ]; then
        echo "  ✗ 编译失败："; sed 's/^/    /' "$BUILD/$out.cc.log" | head -30
    fi
    return $rc
}

# ---- 2) 纯逻辑单元测试 ------------------------------------------------------
note "echo.c 纯逻辑单元测试"
if build_one t_pure tests/host/test_echo_pure.c \
   && "$BUILD/t_pure" "$GOLDEN_DIR" | sed 's/^/  /'; then
    PASS=$((PASS+1))
else
    FAIL=$((FAIL+1))
fi

# ---- 3) 行为轨迹判据 --------------------------------------------------------
note "echo.c 行为轨迹判据（拆分的「行为等价」判据）"
if [ "$RECORD" = 1 ]; then
    mkdir -p "$(dirname "$TRACE_GOLDEN")"
    if build_one t_trace tests/host/test_echo_trace.c \
       && "$BUILD/t_trace" "$GOLDEN_DIR" "$TRACE_GOLDEN" --record | sed 's/^/  /'; then
        { echo "# 行为轨迹黄金文件的出处（本文件不参与比对，只记来源）"
          echo "source     = $ORIGIN"
          echo "echo.c     = ${ECHO_LINES} 行, sha256 前 16 位 ${ECHO_SHA}"
          echo "recorded   = $(date -Iseconds)"
          echo "scenario   = SE150 / 128 条 / score_min=67 / 50 个水印区域"
          echo "lines      = $(wc -l < "$TRACE_GOLDEN")"
        } > "$TRACE_META"
        echo "  ● 出处已写入 $TRACE_META"
        PASS=$((PASS+1))
    else
        FAIL=$((FAIL+1))
    fi
else
    if [ ! -f "$TRACE_GOLDEN" ]; then
        echo "  ✗ 缺黄金轨迹 $TRACE_GOLDEN，先跑一次 --record"
        FAIL=$((FAIL+1))
    elif build_one t_trace tests/host/test_echo_trace.c \
         && "$BUILD/t_trace" "$GOLDEN_DIR" "$TRACE_GOLDEN" | sed 's/^/  /'; then
        PASS=$((PASS+1))
    else
        FAIL=$((FAIL+1))
        [ -f "$TRACE_META" ] && { echo "  黄金轨迹出处："; sed 's/^/    /' "$TRACE_META"; }
    fi
fi

# ---- 4) 鉴别力自证：故障注入 ------------------------------------------------
if [ "$SELFTEST" = 1 ]; then
    note "鉴别力自证：把「拆分时顺手整理掉」的四种改动注进去，轨迹判据必须变红"
    for what in b27-start-clear dec-beats-order voter-prestart-zero drop-stage2-invalidate; do
        target_file="echo.c"
        if [ -f "$SRC/reg_timing.c" ]; then
            case "$what" in
                b27-start-clear|dec-beats-order|voter-prestart-zero)
                    target_file="reg_timing.c" ;;
            esac
        fi
        if [ -f "$SRC/stage2_voter.c" ]; then
            case "$what" in
                drop-stage2-invalidate)
                    target_file="stage2_voter.c" ;;
            esac
        fi
        desc=$(python3 tests/host/inject.py --src "$SRC/$target_file" --out /dev/null \
                        --what "$what" --describe)
        idir="$BUILD/inj_$what"
        mkdir -p "$idir"
        cp "$SRC"/*.h "$SRC"/*.c "$idir/"
        if ! python3 tests/host/inject.py --src "$SRC/$target_file" \
                --out "$idir/$target_file" --what "$what"; then
            echo "  ✗ [$what] 注入点已失效（见上）"
            FAIL=$((FAIL+1)); continue
        fi
        if ! build_one "t_inj_$what" tests/host/test_echo_trace.c "$idir"; then
            echo "  ✗ [$what] 注入版编译不过"
            FAIL=$((FAIL+1)); continue
        fi
        "$BUILD/t_inj_$what" "$GOLDEN_DIR" "$TRACE_GOLDEN" >"$BUILD/$what.out" 2>&1
        if [ $? -ne 0 ]; then
            echo "  ✓ [$what] 判据变红 —— $desc"
            grep -m1 '第 .* 行不同' "$BUILD/$what.out" | sed 's/^/      /'
            PASS=$((PASS+1))
        else
            echo "  ✗ [$what] 注入后判据仍是绿的！这条判据没有鉴别力 —— $desc"
            FAIL=$((FAIL+1))
        fi
    done
fi

printf '\n--------------------------------------------------\n'
printf '通过 %d 项，失败 %d 项\n' "$PASS" "$FAIL"
if [ "$FAIL" -eq 0 ]; then
    echo "✓ PASS  主机侧固件判据全部通过（被测：$ORIGIN）"
    exit 0
else
    echo "✗ FAIL  主机侧固件判据有 $FAIL 项不通过"
    exit 1
fi
