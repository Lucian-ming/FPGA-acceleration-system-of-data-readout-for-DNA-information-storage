#!/usr/bin/env bash
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO"

CLIENT_DIR="$REPO/clients/python"
TEST_DIR="$CLIENT_DIR/tests"
MIN_TESTS=28
# unittest discovery 当前实测收集 28 项（含本轮 3 个板端校验/载荷判据）；
# 此数来自最终输出的 “Ran 28 tests”，新增用例后须同步提高下限。

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

python3 - "$TEST_LOG" <<'PY'
import re
import sys
from pathlib import Path

output = Path(sys.argv[1]).read_text(encoding="utf-8", errors="replace")
summary = re.findall(r"^(?:OK|FAILED)(?: \(([^)]*)\))?$", output, flags=re.MULTILINE)
if not summary:
    print("测试统计：通过=未知，失败=未知，跳过=未知（无法解析 unittest 摘要）")
    raise SystemExit(0)

ran = re.findall(r"^Ran (\d+) tests? in .+$", output, flags=re.MULTILINE)
total = int(ran[-1]) if ran else 0
counts = {
    name: int(value)
    for name, value in re.findall(r"(failures|errors|skipped)=(\d+)", summary[-1])
}
failures = counts.get("failures", 0)
errors = counts.get("errors", 0)
skipped = counts.get("skipped", 0)
failed = failures + errors
passed = max(0, total - failed - skipped)
print(
    f"测试统计：通过={passed}，失败={failed}（failures={failures}, errors={errors}），"
    f"跳过={skipped}"
)
PY

if ((ACTUAL_TESTS < MIN_TESTS)); then
    echo "FAIL: 收集到的客户端测试少于登记下限 $MIN_TESTS"
    exit 1
fi

if ((UNITTEST_RC != 0)); then
    printf 'FAIL: unittest discovery 退出码为 %d\n' "$UNITTEST_RC"
    exit "$UNITTEST_RC"
fi

echo "PASS: 客户端测试全部通过"
