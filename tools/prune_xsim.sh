#!/usr/bin/env bash
# =============================================================================
# tools/prune_xsim.sh —— XSim 历史生成物保留窗口与常态化修剪工具（docs/05 §A3）
#
# 用法：
#   tools/prune_xsim.sh [--keep N] [--dry-run] [--no-archive]
#
# 默认保留各仿真目录（hw/build/xsim、m3、m2_full）最近 3 个时间戳运行，
# 修剪删除前自动将 summary.txt 与 *.log 归集到 logs/xsim/ 留存备查。
# =============================================================================
set -uo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
XSIM_BASE="$REPO_ROOT/hw/build/xsim"
LOGS_XSIM="$REPO_ROOT/logs/xsim"

KEEP=3
DRY_RUN=0
NO_ARCHIVE=0

while [[ $# -gt 0 ]]; do
    case "$1" in
        --keep)
            KEEP="$2"; shift 2 ;;
        --keep=*)
            KEEP="${1#*=}"; shift ;;
        --dry-run)
            DRY_RUN=1; shift ;;
        --no-archive)
            NO_ARCHIVE=1; shift ;;
        -h|--help)
            echo "Usage: $0 [--keep N] [--dry-run] [--no-archive]"
            exit 0 ;;
        *)
            echo "Unknown option: $1" >&2; exit 2 ;;
    esac
done

if [[ ! -d "$XSIM_BASE" ]]; then
    echo "xsim base directory not found: $XSIM_BASE"
    exit 0
fi

prune_dir() {
    local target_dir="$1"
    local scope="$2"
    [[ -d "$target_dir" ]] || return 0

    local runs=()
    while IFS= read -r d; do
        [[ -d "$d" ]] && runs+=("$d")
    done < <(find "$target_dir" -mindepth 1 -maxdepth 1 -type d -name '[0-9][0-9][0-9][0-9][0-9][0-9][0-9][0-9]T*' | sort)

    local total=${#runs[@]}
    if (( total <= KEEP )); then
        echo "[$scope] 共 $total 个时间戳目录，未超过保留上限 ($KEEP)，跳过修剪"
        return 0
    fi

    local num_to_prune=$((total - KEEP))
    echo "[$scope] 共 $total 个运行，保留最新 $KEEP 个，修剪超期 $num_to_prune 个目录..."

    for ((i = 0; i < num_to_prune; i++)); do
        local dir="${runs[i]}"
        local bn="$(basename "$dir")"
        local archive_dest="$LOGS_XSIM/$scope/$bn"

        if (( DRY_RUN )); then
            echo "  [DRY-RUN] 将修剪: $dir -> 归档至 $archive_dest"
            continue
        fi

        if (( ! NO_ARCHIVE )); then
            mkdir -p "$archive_dest"
            find "$dir" -type f \( -name 'summary*.txt' -o -name '*.log' \) | while IFS= read -r f; do
                local rel="${f#$dir/}"
                local dest_file="$archive_dest/$rel"
                mkdir -p "$(dirname "$dest_file")"
                cp "$f" "$dest_file" 2>/dev/null || true
            done
            find "$archive_dest" -type f -name '*.log' -size +1M -exec gzip -9 {} + 2>/dev/null || true
        fi

        rm -rf "$dir"
        echo "  [修剪完成] $dir (已归档关键日志)"
    done
}

echo "=== 执行 XSim 目录生命周期修剪 (keep=$KEEP) ==="
INITIAL_SIZE="$(du -sh "$XSIM_BASE" 2>/dev/null | awk '{print $1}')"
echo "修剪前体积: $INITIAL_SIZE"

prune_dir "$XSIM_BASE" "root"
prune_dir "$XSIM_BASE/m3" "m3"
prune_dir "$XSIM_BASE/m2_full" "m2_full"

for legacy in "$XSIM_BASE/m3/trial01" "$XSIM_BASE/test_4way" "$XSIM_BASE/test_8way"; do
    if [[ -d "$legacy" ]]; then
        bn="$(basename "$legacy")"
        if (( DRY_RUN )); then
            echo "  [DRY-RUN] 将清理遗留测试目录: $legacy"
        else
            if (( ! NO_ARCHIVE )); then
                dest="$LOGS_XSIM/legacy/$bn"
                mkdir -p "$dest"
                find "$legacy" -type f \( -name 'summary*.txt' -o -name '*.log' \) -exec cp {} "$dest/" \; 2>/dev/null || true
            fi
            rm -rf "$legacy"
            echo "  [清理遗留] $legacy"
        fi
    fi
done

FINAL_SIZE="$(du -sh "$XSIM_BASE" 2>/dev/null | awk '{print $1}')"
echo "修剪后体积: $FINAL_SIZE"
