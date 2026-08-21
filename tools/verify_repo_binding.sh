#!/usr/bin/env bash
# Refuse development in a copy, nested repository, wrong branch, or wrong remote.
set -euo pipefail

EXPECTED_ROOT="/home/lucian/projects/FPGA/FpgaAccelerationSystemOfDataReadout"
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

command -v git >/dev/null 2>&1 || fail "git is not installed"

actual_root=$(git rev-parse --show-toplevel 2>/dev/null) || fail "not inside a Git worktree"
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

