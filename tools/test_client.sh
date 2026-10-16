#!/usr/bin/env bash
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO"

CLIENT_DIR="$REPO/clients/python"
TEST_DIR="$CLIENT_DIR/tests"
MIN_TESTS=28
# unittest discovery 的最低实际执行数（跳过项不计入）；新增用例后须同步提高下限。

TMP_DIR="$(mktemp -d)"
trap 'rm -rf "$TMP_DIR"' EXIT

shopt -s nullglob
PY_FILES=("$CLIENT_DIR"/*.py)
if ((${#PY_FILES[@]} == 0)); then
    echo "FAIL: 未找到 clients/python/*.py"
    exit 1
fi

echo "=== 客户端 Python 语法检查 ==="
PYTHONPYCACHEPREFIX="$TMP_DIR/pycache" python3 -m py_compile "${PY_FILES[@]}"
printf 'PASS: clients/python/*.py 语法检查（%d 个文件）\n' "${#PY_FILES[@]}"

echo "=== 客户端 unittest discovery ==="
TEST_LOG="$TMP_DIR/unittest.log"
set +e
python3 -m unittest discover -s "$TEST_DIR" -p 'test_*.py' >"$TEST_LOG" 2>&1
UNITTEST_RC=$?
set -e
cat "$TEST_LOG"

TEST_STATS="$(python3 - "$TEST_LOG" <<'PY'
import re
import sys
from pathlib import Path

output = Path(sys.argv[1]).read_text(encoding="utf-8", errors="replace")
ran = re.findall(r"^Ran (\d+) tests? in .+$", output, flags=re.MULTILINE)
summaries = re.findall(r"^(?:OK|FAILED)(?: \(([^)]*)\))?$", output, flags=re.MULTILINE)
total = int(ran[-1]) if ran else 0
summary = summaries[-1] if summaries else ""
counts = {
    name: int(value)
    for name, value in re.findall(r"(failures|errors|skipped)=(\d+)", summary)
}
skipped = counts.get("skipped", 0)
failures = counts.get("failures", 0)
errors = counts.get("errors", 0)
failed = failures + errors
executed = max(0, total - skipped)
passed = max(0, executed - failed)
print("|".join(map(str, (total, executed, skipped, passed, failed, failures, errors, int(bool(ran and summaries))))))
PY
)"
IFS='|' read -r COLLECTED_TESTS EXECUTED_TESTS SKIPPED_TESTS PASSED_TESTS FAILED_TESTS FAILURES ERRORS SUMMARY_PARSED <<< "$TEST_STATS"
printf '测试计数：收集=%s，实际执行=%s，跳过=%s（实际执行下限：%d）\n' \
    "$COLLECTED_TESTS" "$EXECUTED_TESTS" "$SKIPPED_TESTS" "$MIN_TESTS"
printf '测试统计：通过=%s，失败=%s（failures=%s, errors=%s），跳过=%s\n' \
    "$PASSED_TESTS" "$FAILED_TESTS" "$FAILURES" "$ERRORS" "$SKIPPED_TESTS"

if ((SUMMARY_PARSED != 1)); then
    echo "FAIL: 无法解析 unittest 的 Ran 行或 OK/FAILED 摘要"
    exit 1
fi

if ((EXECUTED_TESTS < MIN_TESTS)); then
    echo "FAIL: 实际执行的客户端测试少于登记下限 $MIN_TESTS（跳过项不计入）"
    exit 1
fi

if ((UNITTEST_RC != 0)); then
    printf 'FAIL: unittest discovery 退出码为 %d\n' "$UNITTEST_RC"
    exit "$UNITTEST_RC"
fi

echo "PASS: 客户端测试全部通过"
