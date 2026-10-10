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

# --- 6. 被打包的实现必须被回归覆盖 -----------------------------------------
# 2026-09-11 发现：component.xml 打包的是 srpe_batch_4way.v，而 run_sim.sh 一直
# 只跑 srpe_batch.v(2-way)——**回归验证的实现与综合出来的实现不是同一个**，
# 而两个 4-way 的 TB 就躺在 hw/sim/ 里从没接进回归。
# 这类缺陷不产生任何错误答案，所以整套验证金字塔对它失明，必须单独设门禁。
SIM_ENTRY="tools/run_sim.sh"
for cx in hw/ip/*/component.xml; do
    ip="$(basename "$(dirname "$cx")")"
    uncovered=""
    while read -r rel; do
        [[ -z "$rel" ]] && continue
        bn="$(basename "$rel")"
        grep -q "$bn" "$SIM_ENTRY" 2>/dev/null || uncovered+=" $bn"
    done < <(grep -oE '<spirit:name>hdl/[^<]*\.v</spirit:name>' "$cx" \
             | sed -E 's|</?spirit:name>||g' | sort -u)
    if [[ -n "$uncovered" ]]; then
        bad "$ip: 打包进比特流但**回归没覆盖**的文件：$uncovered"
        info "测了不会进比特流的那份实现，等于没测。请在 $SIM_ENTRY 里加用例。"
    else
        ok "$ip: 打包的实现均被 $SIM_ENTRY 覆盖"
    fi
done


# --- 7. Stage1的可选生产架构必须贯通XML/HDL/GUI/回归 -----------------------
# 两份源是不同模块名，静态generate只展开一个。仅检查文件名无法抓到
# XML默认16、wrapper默认4或漏传REF_LEN等静默漂移，故检查参数与源集。
if python3 - <<'PY'
from pathlib import Path
import re
import xml.etree.ElementTree as ET

base = Path("hw/ip/Dna_accelerator_core_1_0")
ns = {"s": "http://www.spiritconsortium.org/XMLSchema/SPIRIT/1685-2009"}
root = ET.parse(base / "component.xml").getroot()
for file_node in root.findall("s:fileSets/s:fileSet/s:file", ns):
    path = file_node.findtext("s:name", namespaces=ns)
    assert path and (base / path).is_file(), f"Stage1 XML引用文件不存在: {path}"
top = (base / "hdl/Dna_accelerator_core_v1_0.v").read_text()
gui = (base / "xgui/Dna_accelerator_core_v1_0.tcl").read_text()
runner = Path("tools/run_sim.sh").read_text()

def params(path):
    nodes = root.findall(path, ns)
    names = [n.findtext("s:name", namespaces=ns) for n in nodes]
    assert len(names) == len(set(names)), "参数重名"
    return {n.findtext("s:name", namespaces=ns): n.findtext("s:value", namespaces=ns) for n in nodes}

user = params("s:parameters/s:parameter")
model = params("s:model/s:modelParameters/s:modelParameter")
for name, default in {"C_STAGE1_P_WAYS": 4, "C_STAGE1_PIPE_TREE": 0}.items():
    assert user.get(name) == str(default), f"{name}用户默认错误"
    assert model.get(name) == str(default), f"{name}HDL默认错误"
    assert re.search(r"parameter\s+integer\s+" + name + r"\s*=\s*" + str(default) + r"\s*,", top), f"{name}顶层未对齐"
    for prefix in ["update_PARAM_VALUE.", "validate_PARAM_VALUE.", "update_MODELPARAM_VALUE."]:
        assert "proc " + prefix + name in gui, f"GUI未贯通{prefix}{name}"
    assert "ipgui::add_param $IPINST -name \"" + name + "\"" in gui, f"GUI不可选择{name}"

expected = {"hdl/Dna_accelerator_core_v1_0.v", "hdl/Dna_accelerator_core_v1_0_S_AXI_LITE_CTRL.v",
            "hdl/fifo_sync_sdpram_b64.v", "hdl/s2mm_pack64.v", "hdl/srpe_batch_4way.v", "hdl/srpe_batch_pway.v"}
sets = []
for fileset in root.findall("s:fileSets/s:fileSet", ns):
    files = [f.findtext("s:name", namespaces=ns) for f in fileset.findall("s:file", ns)
             if f.findtext("s:fileType", namespaces=ns) == "verilogSource"]
    if files:
        assert len(files) == len(set(files)), "同一fileset有重复HDL"
        sets.append(set(files))
assert len(sets) == 2 and all(f == expected for f in sets), "生产综合/仿真源集必须恰为P4/P16正式六文件"
for gname, module in [("g_stage1_p4", "srpe_batch"), ("g_stage1_pway", "srpe_batch_pway")]:
    start = top.index("begin: " + gname)
    branch = top[start:top.index("end", start)]
    assert module + " #(" in branch, f"{gname}选错模块"
    for name in ["BATCH", "NUM_LC", "STRIDE", "REF_LEN", "READ_BPS", "SCORE_W", "POS_W"]:
        assert re.search(r"\." + name + r"\s*\(\s*" + name + r"\s*\)", branch), f"{gname}漏传{name}"
assert "STAGE1_CONFIGURATION_MUST_BE_P4_OR_P16_PIPELINED" in top, "非法配置缺少展开失败判据"
assert "stage1_production_full" in runner and "tb_dna_stage1_p16_equivalence.v" in runner and "tb_dna_stage1_p16_interface.v" in runner, "真实生产回归入口缺失"

# 本轮迁移只允许改变说明/SE150默认，算法体应与已验证P14候选相同。
# 历史实验文件不参与生产回归；未来修改算法时需同时更新本门禁的迁移约定。
production = (base / "hdl/srpe_batch_pway.v").read_text()
historical = Path("hw/experimental/srpe_batch_pway.v").read_text()
def algorithm(text):
    text = re.sub(r"/\*.*?\*/|//[^\n]*", "", text, flags=re.S)
    for name in ["STRIDE", "REF_LEN", "READ_BPS"]:
        text = re.sub(r"(parameter\s+integer\s+" + name + r"\s*=)\s*\d+", r"\1 MIGRATION_DEFAULT", text)
    return re.sub(r"\s+", "", text)
assert algorithm(production) == algorithm(historical), "生产Pway算法与本轮P14机械迁移契约不符"
for name, default in {"READ_BPS": 150, "REF_LEN": 957, "STRIDE": 807, "NUM_LC": 50, "BATCH": 64}.items():
    assert re.search(r"parameter\s+integer\s+" + name + r"\s*=\s*" + str(default) + r"\s*,", production), f"Pway生产默认{name}错误"
print("    Stage1: P4=4/0, P16=16/1；六文件源集与参数对齐；P14算法体等价")
PY
then
    ok "Stage1生产参数、静态选择、源集与迁移算法契约一致"
else
    bad "Stage1生产参数/源集/迁移算法契约检查失败"
fi

echo
if (( FAIL )); then
    printf '\033[31m######## IP 打包卫生检查 FAIL ########\033[0m\n'
    exit 1
fi
printf '\033[32m######## IP 打包卫生检查 PASS ########\033[0m\n'
