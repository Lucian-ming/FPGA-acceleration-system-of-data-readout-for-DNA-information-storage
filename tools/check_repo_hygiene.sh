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
#     导致 docs/08 把被它推翻的方向列为第一优先级长期方向）；
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
SKIPPED=0
bad()  { printf '\033[31m  ✗ %s\033[0m\n' "$*"; FAIL=1; }
ok()   { printf '\033[32m  ✓ %s\033[0m\n' "$*"; }
info() { printf '    %s\n' "$*"; }
# 缺前置条件时必须**显式跳过**，不能落到 else 分支被当成 ✓ 打印。
# 提交包（D:\dna-accel-bkb220）是仓库的裁剪快照：没有 docs/、没有 .git、
# 没有 hw/experimental/ 与 sw/workspace/，这几节在那里根本没有输入可查。
# 若静默算通过，就等于把「没检查」伪装成「检查过了」，判据比仓库里这版更弱——
# 本项目明令禁止任何一层判据被悄悄放宽。所以统一走 skip()：
# 用不同的符号（⊘）打印、计入末尾汇总，且可被 HYGIENE_REQUIRE_FULL=1 变成失败。
skip() { printf '\033[33m  ⊘ 跳过 %s\033[0m\n' "$*"; SKIPPED=$((SKIPPED+1)); }

echo "=== 仓库卫生检查 ==="

# 只把 README 表格首列中的反引号条目当作登记。board 目录的 basename
# 只在明确的 tools/board/ 小节内有效；也接受表格首列直接写完整路径。
readme_registers_tool() {
    local path="$1"
    local basename="${path##*/}"
    local is_board=0
    [[ "$path" == tools/board/* ]] && is_board=1
    awk -v basename="$basename" -v path="$path" -v is_board="$is_board" '
        /^##[[:space:]]/ { heading=$0 }
        /^\|/ {
            cell=$0
            sub(/^\|[[:space:]]*/, "", cell)
            sub(/[[:space:]]*\|.*/, "", cell)
            count=split(cell, token, "`")
            for (i=2; i<=count; i+=2) {
                if (token[i] == path ||
                    (token[i] == basename && (!is_board || heading ~ /tools\/board\//))) {
                    found=1
                }
            }
        }
        END { exit !found }
    ' tools/README.md
}

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
for f in tools/*.py tools/*.sh tools/*.ps1 tools/*.tcl tools/board/*.py tools/board/*.tcl tools/board/*.ps1 tools/board/*.sh; do
    [[ -f "$f" ]] || continue
    readme_registers_tool "$f" || UNDOC+=" $f"
done
if [[ -n "$UNDOC" ]]; then
    bad "未登记进 tools/README.md 的脚本：$UNDOC"
    info "新增工具必须登记；无人可见的脚本等于它的结论不存在（AGENTS.md 代码卫生 §6）"
else
    ok "tools/ 下所有脚本均已登记进 README"
fi

# --- 3. docs/ 现用文档必须带序号 ---------------------------------------------
if [[ ! -d docs ]]; then
    skip "docs/ 现用文档序号：无 docs/ 目录，本项无输入可查"
else
    STRAY_DOC="$(ls docs/*.md 2>/dev/null | sed 's|docs/||' \
                 | grep -vE '^[0-9]{2}-|^README\.md$' || true)"
    if [[ -n "$STRAY_DOC" ]]; then
        bad "docs/ 下有不带序号的现用文档（归档才不带号）：$STRAY_DOC"
    else
        ok "docs/ 现用文档均带序号"
    fi
fi

# --- 4. 归档文档必须不带序号 -------------------------------------------------
if [[ ! -d docs/archive ]]; then
    skip "归档文档去号：无 docs/archive/ 目录，本项无输入可查"
else
    NUMBERED_ARCHIVE="$(ls docs/archive/history/*/[0-9][0-9]-*.md 2>/dev/null || true)"
    if [[ -n "$NUMBERED_ARCHIVE" ]]; then
        bad "归档目录里有带序号的文档（应去号，便于一眼区分是否现行）："
        echo "$NUMBERED_ARCHIVE" | sed 's/^/      /'
    else
        ok "归档文档均已去号"
    fi
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
[[ -d logs ]] || skip "logs/ 忽略覆盖：无 logs/ 目录，本项无输入可查"
for d in logs/*/; do
    [[ -d "$d" ]] || continue
    # 目录里有已跟踪文件说明是刻意入库的证据，跳过
    if [[ -n "$(git ls-files "$d" 2>/dev/null)" ]]; then continue; fi
    git check-ignore -q "$d" 2>/dev/null || UNIGNORED+=" ${d%/}"
done
if [[ ! -d logs ]]; then
    :
elif [[ -n "$UNIGNORED" ]]; then
    bad "logs/ 下未被 .gitignore 覆盖的目录：$UNIGNORED"
    info "运行产物动辄几百 MB，漏网一次就可能被误提交进仓库"
else
    ok "logs/ 子目录均已被 .gitignore 覆盖（或已刻意入库）"
fi


# --- 7. 现行文档与源码里的「文件:行号」引用不得悬空或越界 --------------------
# 2026-09-11 新增。起因：sw/app/echo.c 的注释里写着 `stage1_dna.c:178`，而那一行
# 在 WM 批量化补进注释后早已不是被引用的内容（真正的位置是 PIPE_WM_TX 分支里的
# 第 205 行）。这条错误引用从源码注释扩散进了 5 份文档，**全程没有任何判据变红**。
#
# 同一次扫描还发现 docs/04-interfaces.md 指着 `echo.c:465-495`（那段代码早就拆到
# stage1_dna.c，echo.c 现在只有 740 行），以及 4 处指向已被删除的 srpe_batch_2way.v。
#
# 能查与不能查，必须说清楚：
#   能查——文件不存在（悬空）、行号超出文件总行数（越界）；
#   **不能查——文件还在、行号也在范围内，但内容已经挪走**（上面那个 :178 就是这种）。
# 后者只能靠纪律：**现行文档与新写的注释一律按标识符引用（函数名/状态名/模块名），
# 不要写行号**。行号引用会静默过期，而过期的引用比没有引用更糟。
#
# docs/archive/ 整个排除：归档文档引用的是它写作当时的行号，那是正确的历史记录。
STALE_REF=""
LINE_REF_PATTERN='[A-Za-z0-9_/.-]+\.(c|h|v|sv|py|sh|tcl|xml):[0-9]+'
scan_line_references() {
    local -a includes=() roots=()
    local status=0
    while (($#)); do
        if [[ "$1" == --include=* ]]; then
            includes+=("$1")
        else
            roots+=("$1")
        fi
        shift
    done
    grep -rn "${includes[@]}" -oE "$LINE_REF_PATTERN" "${roots[@]}"
    status=$?
    # grep=1 means no matches; codes above 1 mean the scan could not read its inputs.
    (( status == 0 || status == 1 ))
}

SCAN_FAILED=0
DOCS_SCAN_ABSENT=0
# 必须在命令替换**外面**判定：子 shell 里赋的变量传不回父 shell。
[[ -d docs ]] || DOCS_SCAN_ABSENT=1
LINE_REF_HITS="$(
    # 不吞掉读取错误；任一分组失败都令整次扫描失败，不能把空输出当作通过。
    if (( ! DOCS_SCAN_ABSENT )); then
        scan_line_references --include='*.md' docs/ || SCAN_FAILED=1
    fi
    scan_line_references --include='*.c' --include='*.h' --include='*.v' --include='*.sv' \
        --include='*.py' --include='*.sh' \
        sw/app/ hw/ip/ hw/sim/ tools/ clients/python/ hw/scripts/ sw/scripts/ || SCAN_FAILED=1
    # Tcl/PowerShell 入口还存在于 hw/sim/ 与 tools/；递归扫描这四个目录。
    scan_line_references --include='*.tcl' --include='*.ps1' \
        hw/scripts/ sw/scripts/ hw/sim/ tools/ || SCAN_FAILED=1
    (( SCAN_FAILED == 0 ))
)"
if (( $? != 0 )); then
    bad "扫描文件行号引用失败；拒绝按空结果通过"
else
    while IFS= read -r hit; do
        [[ -n "$hit" ]] || continue
        hit="$(sed -E 's#^([^:]+):[0-9]+:#\1:::#' <<< "$hit")"
        src="${hit%%:*}"                       # 出处文件
        # 豁免两类**历史记录**：这里的行号是当时真实写下的，改写等于伪造留证。
        [[ "$src" == docs/archive/* ]] && continue
        [[ "$src" == docs/submission/llm-collaboration/* ]] && continue
        ref="${hit##*:::}"                     # 被引用的 path:line
        f="${ref%%:*}"; ln="${ref##*:}"
        resolved=""
        for pre in "" sw/app/ tools/ tools/board/ clients/python/ hw/scripts/ hw/sim/ hw/sim/ip_tb/ \
                   hw/experimental/ hw/experimental/unused_axi_wrappers/ sw/scripts/ \
                   hw/ip/Dna_accelerator_core_1_0/hdl/ hw/ip/differential_voter_1_0/hdl/ \
                   hw/ip/desparsification_decoder_1_0/hdl/; do
            [[ -f "$pre$f" ]] && { resolved="$pre$f"; break; }
        done
        if [[ -z "$resolved" ]]; then
            STALE_REF+=$'\n'"      悬空  $ref        （出自 $src）"
        else
            tot="$(wc -l < "$resolved")"
            (( ln > tot )) && STALE_REF+=$'\n'"      越界  $ref  实际 $tot 行  （出自 $src）"
        fi
    done < <(printf '%s\n' "$LINE_REF_HITS")
fi
if [[ -n "$STALE_REF" ]]; then
    bad "现行文档/源码里有悬空或越界的「文件:行号」引用：$STALE_REF"
    info "修法：改按标识符引用（函数名/状态名/模块名）。行号引用会静默过期，"
    info "而**内容挪走但行号仍在范围内**的那种过期本检查查不出来——只能靠不写行号。"
elif (( DOCS_SCAN_ABSENT )); then
    ok "源码侧「文件:行号」引用均可解析且在范围内"
    skip "文档侧「文件:行号」引用：无 docs/ 目录，本项无输入可查"
else
    ok "现行文档/源码的「文件:行号」引用均可解析且在范围内"
fi

# --- 8. sw/app 与 sw/workspace 同名文件必须逐字节相同 -------------------------
# 2026-09-11 新增（docs/05 的清理分类与门禁）。sw/app 是唯一权威源，sw/workspace 是其生成副本。
WS_APP="sw/workspace/dna_lwip_app_b27/src"
if [[ -d "$WS_APP" ]]; then
    WS_DIFF=""
    for app_f in sw/app/*; do
        [[ -f "$app_f" ]] || continue
        bn="$(basename "$app_f")"
        ws_f="$WS_APP/$bn"
        if [[ -f "$ws_f" ]]; then
            if ! cmp -s "$app_f" "$ws_f"; then
                WS_DIFF+=" $bn"
            fi
        fi
    done
    if [[ -n "$WS_DIFF" ]]; then
        bad "sw/app/ 与 $WS_APP/ 存在不一致的文件：$WS_DIFF"
        info "sw/app 是权威源，禁止直接编辑 workspace；重新同步或由 create_vitis.tcl 生成"
    else
        ok "sw/app/ 与 workspace 同名文件逐字节相同"
    fi
else
    skip "sw/app 与 workspace 一致性：无 sw/workspace/ 目录，本项无输入可查"
fi

# --- 9. tools/attic/ 下脚本必须登记进 tools/README.md -------------------------
# 2026-09-11 新增（docs/05 的清理分类与门禁）。退役脚本也须在 README 单列一节说明原用途与归档原因。
UNDOC_ATTIC=""
if [[ -d "tools/attic" ]]; then
    for f in tools/attic/*.py tools/attic/*.sh; do
        [[ -f "$f" ]] || continue
        if ! readme_registers_tool "$f"; then
            # Attic 表登记为指向归档源码的 Markdown 链接；检查链接所在表格行。
            if ! awk -v basename="${f##*/}" '
                /^\|/ {
                    cell=$0
                    sub(/^\|[[:space:]]*/, "", cell)
                    sub(/[[:space:]]*\|.*/, "", cell)
                    label="[" basename "]("; start=index(cell, label)
                    if (start) {
                        target=substr(cell, start + length(label))
                        end_pos=index(target, ")")
                        if (end_pos > 1) {
                            target=substr(target, 1, end_pos - 1)
                            n=split(target, part, "/")
                            if (part[n] == basename) found=1
                        }
                    }
                }
                END { exit !found }
            ' tools/README.md; then
                UNDOC_ATTIC+=" ${f##*/}"
            fi
        fi
    done
fi
if [[ ! -d tools/attic ]]; then
    skip "attic 脚本登记：无 tools/attic/ 目录，本项无输入可查"
elif [[ -n "$UNDOC_ATTIC" ]]; then
    bad "未登记进 tools/README.md 的 attic 脚本：$UNDOC_ATTIC"
    info "退役工具也须在 tools/README.md 单列一节说明原用途与为何归档"
else
    ok "tools/attic/ 下脚本均已登记进 README"
fi

# --- 10. hw/experimental/README.md 当前内容表必须与目录实际文件一一对应 ------
# 2026-09-11 新增（docs/05 的清理分类与门禁）。表与目录不一致本身就是一个新的卫生缺陷。
EXP_TABLE_FILES=()
EXP_ACTUAL_FILES=()
EXP_MISMATCH=""

if [[ -f "hw/experimental/README.md" ]]; then
    while IFS= read -r f; do
        [[ -n "$f" ]] && EXP_TABLE_FILES+=("$f")
    done < <(awk '/^## 当前内容/{flag=1; next} /^## /{flag=0} flag' hw/experimental/README.md | grep -oE '`[^`]+`' | tr -d '`')
fi

for p in hw/experimental/*; do
    [[ -e "$p" ]] || continue
    bn="$(basename "$p")"
    [[ "$bn" == "README.md" ]] && continue
    EXP_ACTUAL_FILES+=("$bn")
done

for af in "${EXP_ACTUAL_FILES[@]}"; do
    found=0
    for tf in "${EXP_TABLE_FILES[@]}"; do
        if [[ "$af" == "$tf" ]]; then found=1; break; fi
    done
    if (( ! found )); then
        EXP_MISMATCH+=$'\n'"      目录有但表未记录：$af"
    fi
done

for tf in "${EXP_TABLE_FILES[@]}"; do
    found=0
    for af in "${EXP_ACTUAL_FILES[@]}"; do
        if [[ "$tf" == "$af" ]]; then found=1; break; fi
    done
    if (( ! found )); then
        EXP_MISMATCH+=$'\n'"      表有但目录不存在：$tf"
    fi
done

if [[ ! -d hw/experimental ]]; then
    skip "hw/experimental 表与目录一致性：无 hw/experimental/ 目录，本项无输入可查"
elif [[ -n "$EXP_MISMATCH" ]]; then
    bad "hw/experimental/ 实际文件与 README.md「当前内容」表不一致：$EXP_MISMATCH"
    info "表与目录不一致本身就是卫生缺陷；增删实验文件须同步维护 README.md 表"
else
    ok "hw/experimental/README.md「当前内容」表与目录实际文件一致"
fi

# --- 11. 仓库内不得存在两份 SHA-256 相同的已跟踪文件 --------------------------
# 2026-09-11 新增（docs/05 的清理分类与门禁，A1 那类重复文件的通用判据）。
# 注意：测试数据集（tests/datasets/）、测试黄金向量（tests/golden/）、
# 压测留证（tests/stress_results/）与图像验证留证（docs/images/）包含独立基准包
# 或跨几何黄金断言，各自有独立 SHA256SUMS 清单或运行日志，予以排除。
# 另排除 docs/submission/llm-collaboration/ —— 竞赛要求的 LLM 交互**逐字**记录：
# 两次不同调用产出相同文字是**事实**，删掉一份就等于篡改留证。A1 抓的是
# 「同一份源码被误复制成多份」，与"历史记录里恰好有重复"是两回事。
if ! git rev-parse --git-dir >/dev/null 2>&1; then
    DUP_TRACKED=""
    RC=99
else
DUP_TRACKED="$(python3 -c "
import subprocess, hashlib, os, sys
files = subprocess.check_output(['git', 'ls-files']).decode().splitlines()
hashes = {}
for f in files:
    if f.startswith(('tests/datasets/', 'tests/golden/', 'tests/stress_results/', 'docs/images/',
                        'docs/submission/llm-collaboration/')):
        continue
    if os.path.isfile(f):
        h = hashlib.sha256(open(f, 'rb').read()).hexdigest()
        hashes.setdefault(h, []).append(f)
dups = {h: flist for h, flist in hashes.items() if len(flist) > 1}
if dups:
    for h, flist in dups.items():
        print(f'      SHA-256 {h}:')
        for f in flist:
            print(f'        {f}')
    sys.exit(1)
" 2>&1)"
RC=$?
fi
if (( RC == 99 )); then
    skip "重复 SHA-256 扫描：无 Git 元数据，\"已跟踪文件\"集合不存在，本项无输入可查"
elif (( RC != 0 )); then
    bad "仓库内存在相同 SHA-256 的已跟踪重复文件："$'\n'"$DUP_TRACKED"
    info "见 docs/05 的清理分类与门禁 与 AGENTS.md 代码卫生 §5 第 2 条；消除冗余副本，保留单一权威源"
else
    ok "仓库内无重复 SHA-256 已跟踪文件（A1 通用判据）"
fi

echo
if (( SKIPPED > 0 )); then
    info "本次有 ${SKIPPED} 项因缺少前置条件被显式跳过（⊘）。**跳过不等于通过**："
    info "这些判据在缺少相应目录/元数据的环境里没有输入可查；只有完整仓库里跑才是全量。"
    if [[ "${HYGIENE_REQUIRE_FULL:-0}" == "1" ]]; then
        bad "HYGIENE_REQUIRE_FULL=1 要求全量执行，但缺 ${SKIPPED} 项前置条件"
    fi
fi
if (( FAIL )); then
    printf '\033[31m######## 仓库卫生检查 FAIL ########\033[0m\n'
    exit 1
fi
if (( SKIPPED > 0 )); then
    printf '\033[32m######## 仓库卫生检查 PASS（%s 项显式跳过，非全量） ########\033[0m\n' "$SKIPPED"
else
    printf '\033[32m######## 仓库卫生检查 PASS ########\033[0m\n'
fi
