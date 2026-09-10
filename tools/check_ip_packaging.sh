#!/usr/bin/env bash
# =============================================================================
# tools/check_ip_packaging.sh —— IP 打包卫生门禁
#
# 为什么要有它
# ------------
# 2026-09-10 清理时发现两类**不会报错、只会静默出错**的隐患：
#
# 1. **多个文件定义同一个模块名。** 当时 hdl/ 下有五个文件都定义 `srpe_batch`：
#    srpe_batch.v(2way) / srpe_batch_2way.v(与前者逐字节相同) /
#    srpe_batch_4way.v(宏默认名也是 srpe_batch) /
#    srpe_batch_8way_wip.v(半成品) / srpe_batch_1way_baseline.v。
#    **比特流里跑哪个微架构，取决于 component.xml 恰好列了哪一个文件**——
#    改错一行不会报错，只会静默换掉整个微架构，包括换成那个 WIP 半成品。
#
# 2. **testbench 躺在 IP 的 hdl/ 目录里。** IP 打包目录的内容决定综合工具看到什么，
#    把 tb_*.v 混在里面纯属给自己埋雷。
#
# 这个项目已经为「component.xml 手工维护」付过一次代价：10 处重复的
# <spirit:value> 让整个 IP 被 IP Catalog 拒绝，整机根本无法从零重建。
# 所以这类检查必须是**脚本门禁**，不能是「记得注意」。
#
# 用法
# ----
#   tools/check_ip_packaging.sh          # 全部通过则退出码 0
#   在 tools/run_sim.sh / CI 里调用
# =============================================================================
set -uo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO"

WRITE_MANIFEST=0
[[ "${1:-}" == "--write-manifest" ]] && WRITE_MANIFEST=1

if (( WRITE_MANIFEST )); then
    {
        echo "# 各 IP 的 component.xml 当前打包了哪些 HDL 文件。"
        echo "# 由 tools/check_ip_packaging.sh --write-manifest 生成，请勿手工编辑。"
        echo "# 换实现变体（如 2-way <-> 4-way）会让本文件产生 diff——这正是目的："
        echo "# 让微架构变更在 Git 里可见，而不是藏在 component.xml 的一行文件名里。"
        for cx in hw/ip/*/component.xml; do
            ip="$(basename "$(dirname "$cx")")"
            grep -oE '<spirit:name>hdl/[^<]*\.v</spirit:name>' "$cx" \
              | sed -E 's|</?spirit:name>||g' | sort -u | sed "s|^|$ip |"
        done
    } > hw/ip/PACKAGED_VARIANTS.txt
    echo "已写出 hw/ip/PACKAGED_VARIANTS.txt"
    exit 0
fi

FAIL=0
bad()  { printf '\033[31m  ✗ %s\033[0m\n' "$*"; FAIL=1; }
ok()   { printf '\033[32m  ✓ %s\033[0m\n' "$*"; }
info() { printf '    %s\n' "$*"; }

echo "=== IP 打包卫生检查 ==="

# --- 1. IP 的 hdl/ 里不得出现 testbench -------------------------------------
STRAY_TB="$(ls hw/ip/*/hdl/tb_*.v 2>/dev/null || true)"
if [[ -n "$STRAY_TB" ]]; then
    bad "IP 的 hdl/ 目录里发现 testbench（应放在 hw/sim/ 或 hw/sim/ip_tb/）："
    echo "$STRAY_TB" | sed 's/^/      /'
else
    ok "IP hdl/ 目录内无 testbench"
fi

# --- 2. 同一 IP 内不得有多个文件定义同一模块名 ------------------------------
for d in hw/ip/*/hdl; do
    ip="$(basename "$(dirname "$d")")"
    dup="$(for f in "$d"/*.v; do
             [[ -f "$f" ]] || continue
             # 取模块名；宏定义的模块名解析出其 `define 默认值
             m="$(sed -nE 's/^[[:space:]]*module[[:space:]]+`?([A-Za-z0-9_]+).*/\1/p' "$f" | head -1)"
             if [[ "$m" == *MODNAME* ]] || grep -qE "^\s*module\s+\`" "$f"; then
                 m="$(sed -nE "s/^[[:space:]]*\`define[[:space:]]+[A-Za-z0-9_]*MODNAME[[:space:]]+([A-Za-z0-9_]+).*/\1/p" "$f" | head -1)"
             fi
             [[ -n "$m" ]] && echo "$m $(basename "$f")"
           done | sort | awk '{c[$1]=c[$1]" "$2; n[$1]++} END{for(k in n) if(n[k]>1) print k":"c[k]}')"
    if [[ -n "$dup" ]]; then
        # 同名变体共存本身是允许的（2-way / 4-way 需要并排存在做 A/B 仿真），
        # **有歧义才是错**：只要 component.xml 恰好打包其中一个，综合结果就是确定的。
        # 所以这里只在「同一组同名文件里被打包了不止一个」时判失败。
        # 必须按行读：每行形如 "模块名: 文件1 文件2"，含空格，
        # 用 for grp in $dup 会被按空格分词，把一行拆成三个假条目。
        while IFS= read -r grp; do
            [[ -z "$grp" ]] && continue
            mod="${grp%%:*}"; files="${grp#*:}"
            packed=0; packed_name=""
            for bn in $files; do
                if grep -q "hdl/$bn" "$(dirname "$d")/component.xml" 2>/dev/null; then
                    packed=$((packed+1)); packed_name="$bn"
                fi
            done
            if (( packed > 1 )); then
                bad "$ip: 模块 $mod 有 $packed 个实现被同时打包，综合结果不确定：$files"
            elif (( packed == 0 )); then
                bad "$ip: 模块 $mod 有多个实现($files)，但 component.xml 一个都没打包"
            else
                ok "$ip: 模块 $mod 有多个实现($files)，已明确打包 $packed_name"
            fi
        done <<< "$dup"
    else
        ok "$ip: 模块名无冲突"
    fi
done

# --- 3. component.xml 列的文件必须真实存在 ----------------------------------
for cx in hw/ip/*/component.xml; do
    ip="$(basename "$(dirname "$cx")")"
    missing=""
    while read -r rel; do
        [[ -z "$rel" ]] && continue
        [[ -f "$(dirname "$cx")/$rel" ]] || missing+=" $rel"
    done < <(grep -oE '<spirit:name>[^<]*\.v</spirit:name>' "$cx" \
             | sed -E 's|</?spirit:name>||g' | sort -u)
    if [[ -n "$missing" ]]; then
        bad "$ip: component.xml 引用了不存在的文件：$missing"
    else
        ok "$ip: component.xml 引用的文件均存在"
    fi
done

# --- 4. hdl/ 里不得有零引用的孤儿文件 ---------------------------------------
for d in hw/ip/*/hdl; do
    ip="$(basename "$(dirname "$d")")"
    cx="$(dirname "$d")/component.xml"
    orphan=""
    for f in "$d"/*.v; do
        [[ -f "$f" ]] || continue
        b="$(basename "$f" .v)"
        # 被 component.xml 列出、或被同目录/仿真目录里其它文件引用，即算有主
        grep -q "hdl/$(basename "$f")" "$cx" 2>/dev/null && continue
        refs="$(grep -rl "\b$b\b" hw/ip/*/hdl/*.v hw/sim/*.v hw/sim/ip_tb/*.v 2>/dev/null \
                | grep -v "/$(basename "$f")$" | wc -l)"
        [[ "$refs" -eq 0 ]] && orphan+=" $(basename "$f")"
    done
    if [[ -n "$orphan" ]]; then
        bad "$ip: hdl/ 下存在零引用孤儿文件：$orphan"
        info "处理方式：移到 hw/experimental/ 或删除；留在打包目录里迟早被误打包"
    else
        ok "$ip: hdl/ 无孤儿文件"
    fi
done

# --- 5. 打包变体必须与受版本管理的清单一致 ----------------------------------
# 换微架构是重大变更，必须在 Git 里留下一处可见的 diff，而不是只改 component.xml
# 里的一行文件名（那种改动在 review 时极易被当成无关紧要的路径调整放过）。
MANIFEST="hw/ip/PACKAGED_VARIANTS.txt"
CUR="$(for cx in hw/ip/*/component.xml; do
         ip="$(basename "$(dirname "$cx")")"
         grep -oE '<spirit:name>hdl/[^<]*\.v</spirit:name>' "$cx" \
           | sed -E 's|</?spirit:name>||g' | sort -u | sed "s|^|$ip |"
       done)"
if [[ ! -f "$MANIFEST" ]]; then
    bad "缺少 $MANIFEST —— 无法验证当前打包的是哪个实现变体"
    info "首次生成： tools/check_ip_packaging.sh --write-manifest"
elif ! diff -q <(echo "$CUR") <(grep -vE '^\s*#|^\s*$' "$MANIFEST") >/dev/null; then
    bad "打包内容与 $MANIFEST 不符 —— 有人换了实现变体却没更新清单"
    diff <(grep -vE '^\s*#|^\s*$' "$MANIFEST") <(echo "$CUR") | sed 's/^/      /' | head -12
    info "确认这是有意变更后，用 --write-manifest 更新清单并在提交说明里写明原因"
else
    ok "打包内容与 $MANIFEST 一致"
fi

echo
if (( FAIL )); then
    printf '\033[31m######## IP 打包卫生检查 FAIL ########\033[0m\n'
    exit 1
fi
printf '\033[32m######## IP 打包卫生检查 PASS ########\033[0m\n'
