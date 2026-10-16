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
#   · 删：run 目录里编译产物（无扩展名且 >1 MB 的可执行文件，如 `srpe_batch_pway_p16`）
#   · 留：`.log` `.txt` `.hex` `.sha256` `.json` `.command.txt` —— 判据与留证靠这些
#   iverilog 每次都会重新编译（`run_sim.sh` 里就是先 `iverilog -o <二进制>` 再 `vvp`），
#   所以删掉二进制**不损失任何可复现性**，只省体积。
#
# `--keep N`（可选、非默认）：按**目录修改时间**保留最新 N 个 run 目录，更旧的整目录修剪；
#   修剪前把 `.log`/`.txt`/`.hex`/`.sha256` 归集到 `logs/iverilog/archive/<原名>/`。
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

while [[ $# -gt 0 ]]; do
    case "$1" in
        --keep)       KEEP="$2"; shift 2 ;;
        --keep=*)     KEEP="${1#*=}"; shift ;;
        --dry-run)    DRY_RUN=1; shift ;;
        --no-archive) NO_ARCHIVE=1; shift ;;
        -h|--help)
            echo "Usage: $0 [--keep N] [--dry-run] [--no-archive]"
            echo "  默认：只剥编译出来的仿真器二进制，保留全部留证"
            echo "  --keep N：另按目录时间保留最新 N 个 run 目录，更旧的整目录修剪（修剪前归档日志）"
            exit 0 ;;
        *) echo "Unknown option: $1" >&2; exit 2 ;;
    esac
done

if [[ ! -d "$IV_BASE" ]]; then
    echo "iverilog 目录不存在：$IV_BASE"
    exit 0
fi

echo "=== Icarus Verilog 目录修剪 ==="
INITIAL="$(du -sh "$IV_BASE" 2>/dev/null | awk '{print $1}')"
echo "修剪前体积: $INITIAL"

# --- 1) 剥编译产物（默认动作，安全：这些由 run_sim.sh 每次重新编译）----------------
bin_count=0
bin_bytes=0
while IFS= read -r f; do
    [[ -f "$f" ]] || continue
    sz="$(stat -c %s "$f" 2>/dev/null || echo 0)"
    bin_count=$((bin_count + 1))
    bin_bytes=$((bin_bytes + sz))
    if (( DRY_RUN )); then
        echo "  [DRY-RUN] 将删编译产物: $f ($(( sz / 1048576 )) MB)"
    else
        rm -f "$f"
    fi
done < <(find "$IV_BASE" -type f -size +1M ! -name '*.*' -not -path "$ARCHIVE_BASE/*" 2>/dev/null)

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
                mkdir -p "$dest"
                find "$dir" -type f \( -name '*.log' -o -name '*.txt' -o -name '*.hex' -o -name '*.sha256' \) \
                    -exec cp {} "$dest/" \; 2>/dev/null || true
            fi
            rm -rf "$dir"
            echo "  [修剪完成] $dir（留证已归档至 $ARCHIVE_BASE/$bn）"
        done
    fi
fi

FINAL="$(du -sh "$IV_BASE" 2>/dev/null | awk '{print $1}')"
echo
echo "修剪后体积: $FINAL"
