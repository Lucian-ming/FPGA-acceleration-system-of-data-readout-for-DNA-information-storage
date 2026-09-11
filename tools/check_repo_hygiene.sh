#!/usr/bin/env bash
# =============================================================================
# tools/check_repo_hygiene.sh —— 仓库卫生门禁（AGENTS.md「代码卫生」一节的执行体）
#
# 为什么要有它
# ------------
# 本项目的验证金字塔只对**错误答案**响应：黄金向量、四级 DDR 取证、图片哈希，
# 答案错了就会红。但下面这些缺陷**不产生任何错误答案**，所以整套体系对它们失明：
#
#   - 零引用的脚本（bench_align.py 存着「种子法为何失效」的实证却无人可见，
#     导致 docs/17 把被它推翻的方向列为第一优先级长期方向）；
#   - 同一份数据存多份副本（6 份 watermark.txt 逐字节相同，各自校验和都自洽，
#     发现不了彼此不一致）；
#   - 根目录残留、新日志目录没进 .gitignore、散落的不带号文档。
#
# AGENTS.md 的其余规则保护的是**结论**，没有一条保护**仓库状态**。
# 本脚本就是那一条。IP 打包相关的检查在 tools/check_ip_packaging.sh。
#
# 用法
# ----
#   tools/check_repo_hygiene.sh          # 全通过退出码 0
#   已接入 tools/run_sim.sh
# =============================================================================
set -uo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO"

FAIL=0
bad()  { printf '\033[31m  ✗ %s\033[0m\n' "$*"; FAIL=1; }
ok()   { printf '\033[32m  ✓ %s\033[0m\n' "$*"; }
info() { printf '    %s\n' "$*"; }

echo "=== 仓库卫生检查 ==="

# --- 1. 根目录不得有工具生成的残留 ------------------------------------------
STRAY="$(find . -maxdepth 1 -type f \( -name '*.log' -o -name '*.jou' -o -name '*.str' \
         -o -name '*.pb' -o -name '*.wdb' -o -name 'ref.bin' -o -name 'reads.bin' \) 2>/dev/null)"
if [[ -n "$STRAY" ]]; then
    bad "仓库根目录有工具残留："
    echo "$STRAY" | sed 's/^/      /'
    info "先归档到带时间戳目录再清理，不得静默删除证据（AGENTS.md）"
else
    ok "仓库根目录无残留"
fi

# --- 2. tools/ 下每个脚本都必须可被发现 --------------------------------------
# 「一个无人可见的脚本，等于它得出的结论不存在」——不是比喻，已付过一次代价。
UNDOC=""
for f in tools/*.py tools/*.sh tools/board/*.py tools/board/*.tcl; do
    [[ -f "$f" ]] || continue
    bn="$(basename "$f")"
    grep -q "$bn" tools/README.md 2>/dev/null || UNDOC+=" $bn"
done
if [[ -n "$UNDOC" ]]; then
    bad "未登记进 tools/README.md 的脚本：$UNDOC"
    info "新增工具必须登记；无人可见的脚本等于它的结论不存在（AGENTS.md 代码卫生 §6）"
else
    ok "tools/ 下所有脚本均已登记进 README"
fi

# --- 3. docs/ 现用文档必须带序号 ---------------------------------------------
STRAY_DOC="$(ls docs/*.md 2>/dev/null | sed 's|docs/||' \
             | grep -vE '^[0-9]{2}-|^README\.md$' || true)"
if [[ -n "$STRAY_DOC" ]]; then
    bad "docs/ 下有不带序号的现用文档（归档才不带号）：$STRAY_DOC"
else
    ok "docs/ 现用文档均带序号"
fi

# --- 4. 归档文档必须不带序号 -------------------------------------------------
NUMBERED_ARCHIVE="$(ls docs/archive/history/*/[0-9][0-9]-*.md 2>/dev/null || true)"
if [[ -n "$NUMBERED_ARCHIVE" ]]; then
    bad "归档目录里有带序号的文档（应去号，便于一眼区分是否现行）："
    echo "$NUMBERED_ARCHIVE" | sed 's/^/      /'
else
    ok "归档文档均已去号"
fi

# --- 5. 共享数据不得存多份副本 -----------------------------------------------
# 多份副本各自的 SHA256SUMS 都自洽，发现不了彼此不一致——这正是危险之处。
DUP_WM="$(ls tests/datasets/*/watermark.txt 2>/dev/null | grep -v '/common/' || true)"
if [[ -n "$DUP_WM" ]]; then
    bad "数据集目录下又出现了本地 watermark.txt 副本（应共享 common/ 一份）："
    echo "$DUP_WM" | sed 's/^/      /'
    info "见 tests/datasets/common/README.md 与 AGENTS.md 代码卫生 §8"
else
    ok "水印未出现重复副本"
fi

# --- 6. 新增的 logs/ 子目录必须已被 .gitignore 覆盖 ---------------------------
UNIGNORED=""
for d in logs/*/; do
    [[ -d "$d" ]] || continue
    # 目录里有已跟踪文件说明是刻意入库的证据，跳过
    if [[ -n "$(git ls-files "$d" 2>/dev/null)" ]]; then continue; fi
    git check-ignore -q "$d" 2>/dev/null || UNIGNORED+=" ${d%/}"
done
if [[ -n "$UNIGNORED" ]]; then
    bad "logs/ 下未被 .gitignore 覆盖的目录：$UNIGNORED"
    info "运行产物动辄几百 MB，漏网一次就可能被误提交进仓库"
else
    ok "logs/ 子目录均已被 .gitignore 覆盖（或已刻意入库）"
fi

echo
if (( FAIL )); then
    printf '\033[31m######## 仓库卫生检查 FAIL ########\033[0m\n'
    exit 1
fi
printf '\033[32m######## 仓库卫生检查 PASS ########\033[0m\n'
