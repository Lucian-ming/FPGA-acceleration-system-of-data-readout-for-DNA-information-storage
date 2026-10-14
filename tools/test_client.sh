#!/usr/bin/env bash
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO"

CLIENT_DIR="$REPO/clients/python"
TEST_DIR="$CLIENT_DIR/tests"
MIN_TESTS=25
# 下限 25 对应当前完整 discovery 的实测用例数；新增测试没被收集到正是要防的事。

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

ACTUAL_TESTS="$(python3 - "$TEST_LOG" <<'PY'
import re
import sys
from pathlib import Path

output = Path(sys.argv[1]).read_text(encoding="utf-8", errors="replace")
matches = re.findall(r"^Ran (\d+) tests? in .+$", output, flags=re.MULTILINE)
print(matches[-1] if matches else 0)
PY
)"
printf '实际收集用例数：%s（下限：%d）\n' "$ACTUAL_TESTS" "$MIN_TESTS"

if ((ACTUAL_TESTS < MIN_TESTS)); then
    echo "FAIL: 收集到的客户端测试少于登记下限 $MIN_TESTS"
    exit 1
fi

if ((UNITTEST_RC != 0)); then
    printf 'FAIL: unittest discovery 退出码为 %d\n' "$UNITTEST_RC"
    exit "$UNITTEST_RC"
fi

echo "PASS: 客户端测试全部通过"
