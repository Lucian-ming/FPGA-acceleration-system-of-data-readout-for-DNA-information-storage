#!/usr/bin/env bash
# =============================================================================
# tools/prune_iverilog.sh —— Icarus Verilog 历史生成物常态化修剪工具
#
# 为什么有这个工具
# ----------------
# XSim 那条路有 `tools/prune_xsim.sh`（保留最近 N 轮、日志自动归档），**iverilog 这条路一直是空的**。
# 项目改用 iverilog 做仿真之后没有对应机制，`logs/iverilog/` 一路涨到 **444 MB / 83 个仿真器二进制 / 432 MB**。
# 2026-10-16 一次性删掉了那 432 MB，但**手删不是机制**——不补工具，下个月还会涨回来。
#
# 它做什么
# --------
# **默认行为：只剥「编译出来的仿真器二进制」，保留全部留证。**
#   · 删：run_sim.sh 生成的 run 目录内，无扩展名、>1 MB、可执行且带 Icarus VVP 签名的产物
#   · 留：`.log` `.txt` `.hex` `.sha256` `.json` `.command.txt` —— 判据与留证靠这些
#   iverilog 每次都会重新编译（`run_sim.sh` 里就是先 `iverilog -o <二进制>` 再 `vvp`），
#   所以删掉二进制**不损失任何可复现性**，只省体积。
#
# `--keep N`（可选、非默认）：按**目录修改时间**保留最新 N 个 run 目录，更旧的整目录修剪；
#   修剪前把 `.log`/`.txt`/`.hex`/`.sha256`/`.json` 归集到 `logs/iverilog/archive/<原名>/`。
#   ⚠️ 整目录修剪有风险：**有些 run 目录被文档当作留证引用**。默认不做，要用请先用 `--dry-run` 看清单。
#
# 用法：
#   tools/prune_iverilog.sh [--keep N] [--dry-run] [--no-archive]
# =============================================================================
set -uo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
IV_BASE="$REPO_ROOT/logs/iverilog"
ARCHIVE_BASE="$IV_BASE/archive"

KEEP=""
DRY_RUN=0
NO_ARCHIVE=0
PRUNE_FAILED=0

while [[ $# -gt 0 ]]; do
    case "$1" in
        --keep)       KEEP="$2"; shift 2 ;;
        --keep=*)     KEEP="${1#*=}"; shift ;;
        --dry-run)    DRY_RUN=1; shift ;;
        --no-archive) NO_ARCHIVE=1; shift ;;
        -h|--help)
            echo "Usage: $0 [--keep N] [--dry-run] [--no-archive]"
            echo "  默认：只剥编译出来的仿真器二进制，保留全部留证"
            echo "  --keep N：按目录时间保留最新 N 个 run 目录，更旧目录先归档留证并校验后再修剪"
            exit 0 ;;
        *) echo "Unknown option: $1" >&2; exit 2 ;;
    esac
done

if [[ ! -d "$IV_BASE" ]]; then
    echo "iverilog 目录不存在：$IV_BASE"
    exit 0
fi

# 归档所选留证，保留源目录相对路径，并逐文件比较复制结果。
archive_tree() {
    local source_dir="$1"
    local archive_dir="$2"
    local manifest
    manifest="$(mktemp "${TMPDIR:-/tmp}/prune-iverilog.XXXXXX")" || return 1
    if ! find "$source_dir" -type f \( -name '*.log' -o -name '*.txt' -o -name '*.hex' -o -name '*.sha256' -o -name '*.json' \) -print0 >"$manifest"; then
        rm -f -- "$manifest"
        return 1
    fi

    local f rel dest_file failed=0
    while IFS= read -r -d '' f; do
        rel="${f#$source_dir/}"
        dest_file="$archive_dir/$rel"
        if ! mkdir -p "$(dirname "$dest_file")" || ! cp -p -- "$f" "$dest_file" || ! cmp -s -- "$f" "$dest_file"; then
            echo "  [归档失败] $f -> $dest_file" >&2
            failed=1
            break
        fi
    done <"$manifest"
    rm -f -- "$manifest"
    return "$failed"
}

is_iverilog_output() {
    local candidate="$1" run_dir base command_file sources_file first second compile_line
    [[ -x "$candidate" ]] || return 1
    run_dir="$(dirname -- "$candidate")"
    base="$(basename -- "$candidate")"
    command_file="$run_dir/$base.command.txt"
    sources_file="$run_dir/$base.sources.sha256"

    # 目录标记、逐目标命令和源码清单必须齐全；ELF 魔数本身不能证明产物来自 Icarus。
    [[ -f "$run_dir/run-config.txt" && -f "$sources_file" && -s "$command_file" ]] || return 1
    grep -Eq '^entry=[^[:space:]]+$' "$run_dir/run-config.txt" || return 1
    compile_line="$(head -n 1 -- "$command_file")"
    [[ "$compile_line" == iverilog\ -g2005\ -o\ * ]] || return 1
    [[ "$compile_line" == *"$base"* ]] || return 1

    # iverilog -o 默认生成由 vvp 执行的文本程序，不是 ELF；识别其稳定头部签名。
    { IFS= read -r first && IFS= read -r second; } <"$candidate" || return 1
    [[ "$first" == '#!'*'vvp' && "$second" == ':ivl_version '* ]]
}

echo "=== Icarus Verilog 目录修剪 ==="
INITIAL="$(du -sh "$IV_BASE" 2>/dev/null | awk '{print $1}')"
echo "修剪前体积: $INITIAL"

# --- 1) 剥编译产物（默认动作，安全：这些由 run_sim.sh 每次重新编译）----------------
bin_count=0
bin_bytes=0
while IFS= read -r -d '' f; do
    [[ -f "$f" ]] || continue
    # 仅接受 run_sim.sh 留证齐全且带标准 Icarus VVP 头部的文件。
    is_iverilog_output "$f" || continue
    sz="$(stat -c %s "$f" 2>/dev/null || echo 0)"
    bin_count=$((bin_count + 1))
    bin_bytes=$((bin_bytes + sz))
    if (( DRY_RUN )); then
        echo "  [DRY-RUN] 将删编译产物: $f ($(( sz / 1048576 )) MB)"
    else
        rm -f "$f"
    fi
done < <(find "$IV_BASE" -mindepth 2 -maxdepth 2 -type f -size +1M ! -name '*.*' -executable \
             -not -path "$ARCHIVE_BASE/*" -print0 2>/dev/null)

if (( DRY_RUN )); then
    echo "编译产物: 命中 $bin_count 个，共 $(( bin_bytes / 1048576 )) MB（未删）"
else
    echo "已剥编译产物: $bin_count 个，释放 $(( bin_bytes / 1048576 )) MB"
fi

# --- 2) 可选：整目录修剪（--keep N，默认关闭）------------------------------------
if [[ -n "$KEEP" ]]; then
    echo
    echo "--- 整目录修剪（keep=$KEEP）---"
    runs=()
    while IFS= read -r d; do
        [[ -d "$d" ]] && runs+=("$d")
    done < <(find "$IV_BASE" -mindepth 1 -maxdepth 1 -type d -not -name archive -printf '%T@ %p\n' 2>/dev/null \
             | sort -n | cut -d' ' -f2-)

    total=${#runs[@]}
    if (( total <= KEEP )); then
        echo "共 $total 个 run 目录，未超过保留上限 ($KEEP)，跳过"
    else
        num=$((total - KEEP))
        echo "共 $total 个，保留最新 $KEEP 个，修剪 $num 个"
        for ((i = 0; i < num; i++)); do
            dir="${runs[i]}"; bn="$(basename "$dir")"
            if (( DRY_RUN )); then
                echo "  [DRY-RUN] 将修剪整目录: $dir"
                continue
            fi
            if (( ! NO_ARCHIVE )); then
                dest="$ARCHIVE_BASE/$bn"
                if ! mkdir -p "$dest" || ! archive_tree "$dir" "$dest"; then
                    echo "  [跳过删除] 留证归档未能完整校验：$dir" >&2
                    PRUNE_FAILED=1
                    continue
                fi
            fi
            rm -rf "$dir"
            echo "  [修剪完成] $dir（留证已归档至 $ARCHIVE_BASE/$bn）"
        done
    fi
fi

FINAL="$(du -sh "$IV_BASE" 2>/dev/null | awk '{print $1}')"
echo
echo "修剪后体积: $FINAL"
exit "$PRUNE_FAILED"
