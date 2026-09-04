#!/usr/bin/env bash
# Refuse development in a copy, nested repository, wrong branch, or wrong remote.
set -euo pipefail

# 绑定到当前脚本所属 checkout，而不是某台机器的绝对路径。这样用户明确
# 授权的新 WSL clone 可以复用同一门禁，同时仍拒绝从别的/嵌套仓库误调用。
SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)
EXPECTED_ROOT=$(cd "$SCRIPT_DIR/.." && pwd -P)
EXPECTED_HTTPS="https://github.com/Lucian-ming/FPGA-acceleration-system-of-data-readout-for-DNA-information-storage.git"
EXPECTED_SSH="git@github.com:Lucian-ming/FPGA-acceleration-system-of-data-readout-for-DNA-information-storage.git"

REMOTE_CHECK=0
REQUIRE_SYNCED=0
for arg in "$@"; do
    case "$arg" in
        --remote) REMOTE_CHECK=1 ;;
        --require-synced) REMOTE_CHECK=1; REQUIRE_SYNCED=1 ;;
        *) echo "Usage: $0 [--remote] [--require-synced]" >&2; exit 2 ;;
    esac
done

fail() {
    echo "[REPO BINDING] FAIL: $*" >&2
    echo "Git binding must be fixed before any simulation or development." >&2
    exit 1
}

# ── git index 健康自检（多 Agent 并发写竞争 + git 2.25.1 已知 bug 可能截断 index）─
# 必须在第一次调用 git 之前检查，否则 git 本身就会 fatal 退出
_idx_candidates=(
    "${GIT_DIR:-}/index"
    "${EXPECTED_ROOT}/.git-data/index"
    "${EXPECTED_ROOT}/.git/index"
)
for _idx in "${_idx_candidates[@]}"; do
    [ -f "$_idx" ] || continue
    _idx_size=$(stat -c%s "$_idx" 2>/dev/null || echo 0)
    if [ "$_idx_size" -lt 12 ]; then
        echo "⚠️  git index 已损坏（${_idx_size} 字节），自动修复中..." >&2
        rm -f "$_idx"
        git -C "$EXPECTED_ROOT" reset --quiet 2>/dev/null && \
            echo "✅ git index 已重建" >&2 || \
            echo "⚠️  index 重建失败，请手动运行: rm -f $(dirname $_idx)/index && git reset" >&2
    fi
    break
done
unset _idx_candidates _idx _idx_size

command -v git >/dev/null 2>&1 || fail "git is not installed"

actual_root=$(git rev-parse --show-toplevel 2>/dev/null) || fail "not inside a Git worktree"
actual_root=$(cd "$actual_root" && pwd -P)
[ "$actual_root" = "$EXPECTED_ROOT" ] || fail "unexpected Git root: $actual_root"

cd "$EXPECTED_ROOT"
branch=$(git branch --show-current)
[ "$branch" = "main" ] || fail "current branch is '$branch', expected 'main'"

origin_url=$(git remote get-url origin 2>/dev/null) || fail "origin is missing"
case "$origin_url" in
    "$EXPECTED_HTTPS"|"$EXPECTED_SSH") ;;
    *) fail "origin points to an unauthorized repository: $origin_url" ;;
esac

upstream=$(git rev-parse --abbrev-ref --symbolic-full-name '@{upstream}' 2>/dev/null) \
    || fail "main has no upstream"
[ "$upstream" = "origin/main" ] || fail "main tracks '$upstream', expected 'origin/main'"

if [ "$REMOTE_CHECK" -eq 1 ]; then
    git fetch --prune origin || fail "cannot fetch the private GitHub repository"
    git show-ref --verify --quiet refs/remotes/origin/main \
        || fail "origin/main does not exist"
    git push --dry-run origin HEAD:main \
        || fail "current GitHub identity cannot push main"
fi

read -r ahead behind < <(git rev-list --left-right --count main...origin/main)
if [ "$behind" -ne 0 ]; then
    fail "local main is behind origin/main by $behind commit(s); synchronize before development"
fi
if [ "$REQUIRE_SYNCED" -eq 1 ] && [ "$ahead" -ne 0 ]; then
    fail "local main has $ahead unpushed commit(s)"
fi

printf '[REPO BINDING] PASS\n'
printf '  root: %s\n' "$actual_root"
printf '  branch/upstream: %s -> %s\n' "$branch" "$upstream"
printf '  origin: %s\n' "$origin_url"
printf '  main...origin/main: %s ahead, %s behind\n' "$ahead" "$behind"
