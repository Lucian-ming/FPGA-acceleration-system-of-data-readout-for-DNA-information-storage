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
case "$#" in
    0) ;;
    1)
        if [[ "$1" == "--write-manifest" ]]; then
            WRITE_MANIFEST=1
        else
            echo "未知参数: $1" >&2
            echo "用法: $0 [--write-manifest]" >&2
            exit 2
        fi
        ;;
    *)
        echo "参数过多: $*" >&2
        echo "用法: $0 [--write-manifest]" >&2
        exit 2
        ;;
esac

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
        done | LC_ALL=C sort
    } > hw/ip/packaged_variants.txt
    echo "已写出 hw/ip/packaged_variants.txt"
    exit 0
fi

FAIL=0
bad()  { printf '\033[31m  ✗ %s\033[0m\n' "$*"; FAIL=1; }
ok()   { printf '\033[32m  ✓ %s\033[0m\n' "$*"; }
info() { printf '    %s\n' "$*"; }

# component.xml 的文件集通过 spirit:file/spirit:name 列出相对路径。
# 从 XML 文件节点取路径，包含 foo.v 这样的无目录前缀文件名。
component_file_references() {
    python3 - "$1" <<'PY'
import sys
import xml.etree.ElementTree as ET

ns = {"s": "http://www.spiritconsortium.org/XMLSchema/SPIRIT/1685-2009"}
root = ET.parse(sys.argv[1]).getroot()
paths = set()
for node in root.findall(".//s:fileSets/s:fileSet/s:file", ns):
    path = node.findtext("s:name", namespaces=ns)
    if not path:
        raise SystemExit(f"component.xml 的 spirit:file 缺少 spirit:name: {sys.argv[1]}")
    paths.add(path)
if not paths:
    raise SystemExit(f"component.xml 没有 spirit:file 节点: {sys.argv[1]}")
for path in sorted(paths):
    print(path)
PY
}

echo "=== IP 打包卫生检查 ==="

# --- 1. IP 的 hdl/ 里不得出现 testbench -------------------------------------
STRAY_TB="$(ls hw/ip/*/hdl/tb_*.v 2>/dev/null || true)"
if [[ -n "$STRAY_TB" ]]; then
    bad "IP 的 hdl/ 目录里发现 testbench（应放在 ../sim/rtl/ 或 ../sim/rtl/ip_tb/）："
    echo "$STRAY_TB" | sed 's/^/      /'
else
    ok "IP hdl/ 目录内无 testbench"
fi

# --- 1b. IP 的 hdl/ 里不得出现非 .v 文件 -------------------------------------
# 2026-10-12 新增。原检查只扫 tb_*.v 与同名模块，于是 hdl/ 里的 .tcl/.sv/.md
# 之类**完全漏检**——vivado_quick_sim.tcl 就在一个「只放会被综合的文件」的目录里
# 躺了很久而门禁全绿（AGENTS.md 代码卫生 §1：卫生问题必须是会红的判据）。
STRAY_NONV="$(find hw/ip/*/hdl -maxdepth 1 -type f ! -name '*.v' 2>/dev/null || true)"
if [[ -n "$STRAY_NONV" ]]; then
    bad "IP 的 hdl/ 目录里发现非 HDL 文件（hdl/ 只放会被综合的 .v）："
    echo "$STRAY_NONV" | sed 's/^/      /'
else
    ok "IP hdl/ 目录内无非 HDL 文件"
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
        cx="$(dirname "$d")/component.xml"
        packed_references=""
        if ! packed_references="$(component_file_references "$cx")"; then
            bad "$ip: 无法解析 component.xml 的 spirit:file 引用"
        fi
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
                if grep -Fxq "hdl/$bn" <<< "$packed_references"; then
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
    if ! file_references="$(component_file_references "$cx")"; then
        bad "$ip: 无法解析 component.xml 的 spirit:file 引用"
        continue
    fi
    while read -r rel; do
        [[ -z "$rel" ]] && continue
        [[ -f "$(dirname "$cx")/$rel" ]] || missing+=" $rel"
    done <<< "$file_references"
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
        refs="$(grep -rl "\b$b\b" hw/ip/*/hdl/*.v ../sim/rtl/*.v ../sim/rtl/ip_tb/*.v 2>/dev/null \
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
MANIFEST="hw/ip/packaged_variants.txt"
CUR="$(for cx in hw/ip/*/component.xml; do
         ip="$(basename "$(dirname "$cx")")"
         grep -oE '<spirit:name>hdl/[^<]*\.v</spirit:name>' "$cx" \
           | sed -E 's|</?spirit:name>||g' | sort -u | sed "s|^|$ip |"
       done | LC_ALL=C sort)"
if [[ ! -f "$MANIFEST" ]]; then
    bad "缺少 $MANIFEST —— 无法验证当前打包的是哪个实现变体"
    info "首次生成： tools/check_ip_packaging.sh --write-manifest"
elif ! diff -q <(printf '%s\n' "$CUR") <(grep -vE '^\s*#|^\s*$' "$MANIFEST" | LC_ALL=C sort) >/dev/null; then
    bad "打包内容与 $MANIFEST 不符 —— 有人换了实现变体却没更新清单"
    diff <(grep -vE '^\s*#|^\s*$' "$MANIFEST" | LC_ALL=C sort) \
         <(printf '%s\n' "$CUR") | sed 's/^/      /' | head -12
    info "确认这是有意变更后，用 --write-manifest 更新清单并在提交说明里写明原因"
else
    ok "打包内容与 $MANIFEST 一致"
fi

# --- 6. 被打包的实现必须被回归覆盖 -----------------------------------------
# 2026-09-11 发现：component.xml 打包的是 srpe_batch_4way.v，而 run_sim.sh 一直
# 只跑 srpe_batch.v(2-way)——**回归验证的实现与综合出来的实现不是同一个**，
# 而两个 4-way 的 TB 当时还留在仿真目录里，从没接进回归。
# 这类缺陷不产生任何错误答案，所以整套验证金字塔对它失明，必须单独设门禁。
SIM_ENTRY="tools/run_sim.sh"
SIM_COMPILED_SOURCES=""
if ! SIM_COMPILED_SOURCES="$(bash "$SIM_ENTRY" --list-compiled-sources all)"; then
    bad "$SIM_ENTRY 无法枚举实际编译源文件，拒绝判定回归覆盖"
    SIM_COMPILED_SOURCES=""
else
    SIM_COMPILED_SOURCES="$(printf '%s\n' "$SIM_COMPILED_SOURCES" | LC_ALL=C sort -u)"
fi
for cx in hw/ip/*/component.xml; do
    ip="$(basename "$(dirname "$cx")")"
    uncovered=""
    if ! file_references="$(component_file_references "$cx")"; then
        bad "$ip: 无法解析 component.xml 的 spirit:file 引用，拒绝判定回归覆盖"
        continue
    fi
    while IFS= read -r rel; do
        [[ -z "$rel" ]] && continue
        [[ "$rel" == *.v || "$rel" == *.sv ]] || continue
        if ! grep -Fxq "hw/ip/$ip/$rel" <<< "$SIM_COMPILED_SOURCES"; then
            uncovered+=" ${rel#hdl/}"
        fi
    done <<< "$file_references"
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
import hashlib
import xml.etree.ElementTree as ET

base = Path("hw/ip/dna_accelerator_core_1_0")
ns = {"s": "http://www.spiritconsortium.org/XMLSchema/SPIRIT/1685-2009"}
root = ET.parse(base / "component.xml").getroot()
for file_node in root.findall("s:fileSets/s:fileSet/s:file", ns):
    path = file_node.findtext("s:name", namespaces=ns)
    assert path and (base / path).is_file(), f"Stage1 XML引用文件不存在: {path}"
top = (base / "hdl/dna_accelerator_core.v").read_text()
gui = (base / "xgui/dna_accelerator_core.tcl").read_text()
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

expected = {"hdl/dna_accelerator_core.v", "hdl/dna_accelerator_core_s_axi_lite_ctrl.v",
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

# ---------------------------------------------------------------- 迁移契约：已按约定撤销
# 原契约断言「生产 P-way 算法体（去注释去空白后）逐字节等于 hw/experimental/srpe_batch_pway.v」，
# 用途是证明 2026-09-22 那次从 P14 候选到正式 IP 的搬运**没有夹带算法改动**。该搬运早已完成。
# 原注释本身写明：「未来修改算法时需同时更新本门禁的迁移约定」——现在是那个时候。
#
# 2026-10-14：每拍碱基数 K 被**有意**写死为 2（原为可配置 parameter）。
# 这是算法变更不是迁移误差：同一模组整机 LUT 由 33,987（K=1）变为 35,702（K=2），
# K=4 更是 63,246 > 器件容量 53,200 而 place 失败。继续保留逐字节断言，
# 只会逼出一个与生产文件逐字节相同的实验副本，那是个没有信息量的复制品。
#
# 取代它的是**两道更强的门禁**，故这是替换而非放宽：
#   1) 源码 SHA 冻结 —— 下面 pin 住生产 RTL 的 SHA256。任何源码改动都必须显式更新本行，
#      使「出片源码变了」在 Git diff 里必然可见（本仓库对微架构变更的一贯要求）。
#   2) 行为判据 —— tb_dna_stage1_p16_equivalence.v 用「生产 P4 + 独立符号滑窗 oracle」
#      对 P16 做 score/pos/cw **三重逐位**比对，LC6 与 LC50 两档都跑。
#      与独立 oracle 的行为等价，强于与一个旧文件的字节等价。
# 本值是**本包内实测**的那一份（= build/artifact/reports/source_manifest.json 记录的值，
# 也是出片用的那一份）。它与开发仓库的 54104a96… 不同：两棵树只差第 6 行注释里的顶层模块名
# （本包按指南 §3.3.5.4 已改为小写），去注释去空白后 SHA 相同（c5f1ccf5…）。
# 故两棵树**各钉自己的值**，不互相迁就。依据见 build/reports/pway-source-pin.md。
PRODUCTION_PWAY_SHA256 = "03a78b21846061dfbc8736b656d8af9cacd6fd636f52ea5b0927a2e44f10feb6"
_sha = hashlib.sha256((base / "hdl/srpe_batch_pway.v").read_bytes()).hexdigest()
assert _sha == PRODUCTION_PWAY_SHA256, (
    "生产 P-way 源码 SHA 与冻结值不符：\n"
    "  实测 %s\n  冻结 %s\n"
    "这是**有意的源码变更**。确认：(a) 已跑过 tb_dna_stage1_p16_equivalence.v（LC6 与 LC50）；"
    "(b) 改动理由已写进 build/reports/pway-source-pin.md；"
    "然后才同步更新本门禁的 PRODUCTION_PWAY_SHA256。" % (_sha, PRODUCTION_PWAY_SHA256))
production = (base / "hdl/srpe_batch_pway.v").read_text()
for name, default in {"READ_BPS": 150, "REF_LEN": 957, "STRIDE": 807, "NUM_LC": 50, "BATCH": 64}.items():
    assert re.search(r"parameter\s+integer\s+" + name + r"\s*=\s*" + str(default) + r"\s*,", production), f"Pway生产默认{name}错误"
# K 必须是写死的 localparam 2，且不得再作为 parameter 出现在参数表里
assert re.search(r"localparam\s+integer\s+BASES_PER_CYCLE\s*=\s*2\s*;", production), \
    "每拍碱基数应写死为 localparam BASES_PER_CYCLE = 2（K=4 整机 LUT 超容量）"
assert not re.search(r"parameter\s+integer\s+BASES_PER_CYCLE", production), \
    "BASES_PER_CYCLE 不得再是可配置 parameter——构建期传参通道应已全部撤销"
print("    Stage1: P4=4/0, P16=16/1；六文件源集与参数对齐；生产源码 SHA 已冻结；K 写死为 2")
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
