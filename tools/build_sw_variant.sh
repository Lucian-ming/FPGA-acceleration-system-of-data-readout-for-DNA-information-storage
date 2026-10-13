#!/usr/bin/env bash
# tools/build_sw_variant.sh —— 从一份已验收的完整制品包派生出「只改 PS 编译宏」的变体包
#
# 为什么需要它
# ------------
# `run_g3.sh` 明确**禁止** `--elf` 指向所选包之外的文件（2026 年加的守卫，正是为了
# 堵住「拿一份临时 ELF 去验收」的做法）。所以任何 PS 侧编译期改动的 A/B，都必须
# 产出**自己的一份完整包**：bit / XSA / FSBL 与参考包逐字节相同，只有应用 ELF
# （以及随之重打的 BOOT.bin）不同，并且新包要有自己的清单与 SHA256SUMS。
#
# 它做什么
# --------
#   1. 复制参考包（含 workspace、export、reports、logs）；
#   2. 把 workspace 里 Makefile 的路径改指向新包，并在 CFLAGS 追加给定宏；
#   3. 清掉应用目标文件后重建 ELF；
#   4. 用新 ELF 重打 BOOT.bin（bootgen，与参考包同一 .bif）；
#   5. 在 manifest 里写明**派生了什么、参考包与参考 ELF 的 SHA**，重签 SHA256SUMS。
#
# 边界
# ----
# - **硬件制品不变**：bit/XSA/ps7_init 与参考包逐字节相同（脚本会核验并打印）。
#   本脚本**不做**综合/实现，也不改任何 RTL。
# - 它只证明「新包自洽且与参考包同源」；**不证明**新包在板上通过——那要另行跑 G3。
# - 修改只发生在**新包目录内的副本**；`sw/app/` 权威源一个字节都不动。
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
REF=""; OUT=""; DEFS=(); LABEL=""
while [[ $# -gt 0 ]]; do
  case "$1" in
    --ref)    REF="$2"; shift 2 ;;
    --out)    OUT="$2"; shift 2 ;;
    --define) DEFS+=("$2"); shift 2 ;;
    --label)  LABEL="$2"; shift 2 ;;
    *) echo "未知参数：$1" >&2; exit 2 ;;
  esac
done
[[ -n "$REF" && -n "$OUT" ]] || { echo "用法：$0 --ref <参考包> --out <新包> --define MACRO=V [--define M2=V2] [--label 说明]" >&2; exit 2; }
(( ${#DEFS[@]} )) || { echo "至少要给一个 --define" >&2; exit 2; }
REF_ABS="$(cd "$REF" && pwd)"
[[ -e "$OUT" ]] && { echo "输出目录已存在，拒绝覆盖：$OUT" >&2; exit 1; }
OUT_ABS="$REPO/$OUT"

CC=/tools/Xilinx/Vitis/2022.2/gnu/aarch32/lin/gcc-arm-none-eabi/bin/arm-none-eabi-gcc
BOOTGEN=/tools/Xilinx/Vitis/2022.2/bin/bootgen
APP="$OUT_ABS/workspace/dna_lwip_app"
[[ -x "$CC" && -x "$BOOTGEN" ]] || { echo "找不到 2022.2 工具链（$CC / $BOOTGEN）" >&2; exit 1; }

echo "== 1/5 复制参考包 =="
mkdir -p "$(dirname "$OUT_ABS")"
cp -a "$REF_ABS" "$OUT_ABS"

echo "== 2/5 改 Makefile：路径指向新包 + 追加宏 ${DEFS[*]} =="
MK="$APP/Makefile"
[[ -f "$MK" ]] || { echo "新包内没有 $MK" >&2; exit 1; }
sed -i "s|$REF_ABS|$OUT_ABS|g" "$MK"
DEFSTR=""
for d in "${DEFS[@]}"; do DEFSTR+=" -D$d"; done
python3 - "$MK" "$DEFSTR" <<'PY'
import sys,re
mk,defs=sys.argv[1],sys.argv[2]
s=open(mk).read()
m=re.search(r'^CFLAGS :=(.*)$', s, re.M)
if not m: raise SystemExit('Makefile 里没有 CFLAGS := 行')
if 'PIPE_RUN_SLEEP_US' in m.group(1): raise SystemExit('CFLAGS 里已有该宏，拒绝重复注入')
s=s[:m.end()]+defs+s[m.end():]
open(mk,'w').write(s)
print('CFLAGS 已注入：', defs.strip())
PY

echo "== 3/5 重建应用 ELF =="
rm -f "$APP"/Debug/*.o "$APP"/Debug/*.d "$APP"/Debug/*.elf "$APP"/Debug/*.map
make -C "$APP" 2>&1 | tail -3
NEWELF="$APP/Debug/dna_lwip_app.elf"
[[ -s "$NEWELF" ]] || { echo "ELF 未生成" >&2; exit 1; }

echo "== 4/5 更新 export/ 与 BOOT.bin =="
cp "$NEWELF" "$OUT_ABS/export/dna_lwip_app.elf"
# 必须**在 export/ 目录里**跑：bootgen 按 CWD 解析 .bif 里的相对路径（fsbl.elf 等），
# 从包根目录跑会直接 "Cannot read file - fsbl.elf"。
( cd "$OUT_ABS/export" && "$BOOTGEN" -image boot.bif -arch zynq -o BOOT.bin -w on > "$OUT_ABS/logs/bootgen-create.log" 2>&1 ) \
  || { echo "bootgen 失败，见日志" >&2; exit 1; }
grep -q "Bootimage generated successfully" "$OUT_ABS/logs/bootgen-create.log" \
  || { echo "bootgen 未报成功，拒绝继续" >&2; exit 1; }

echo "== 5/5 写 manifest 并重签 SHA256SUMS =="
REF_BIT_SHA=$(sha256sum "$REF_ABS/export/top_bd_wrapper.bit" | cut -d' ' -f1)
REF_ELF_SHA=$(sha256sum "$REF_ABS/export/dna_lwip_app.elf" | cut -d' ' -f1)
NEW_BIT_SHA=$(sha256sum "$OUT_ABS/export/top_bd_wrapper.bit" | cut -d' ' -f1)
[[ "$REF_BIT_SHA" == "$NEW_BIT_SHA" ]] || { echo "bit 与参考包不一致——本脚本不应改硬件制品" >&2; exit 1; }
python3 - "$OUT_ABS/manifest.json" "$REF" "$REF_ELF_SHA" "$LABEL" "$DEFSTR" <<'PY'
import json,sys
p,ref,refelf,label,defs=sys.argv[1:6]
d=json.load(open(p))
d['software']['app_defines']=' '.join(defs.split())
d['software']['variant_of']={'reference_package':ref,'reference_elf_sha256':refelf}
d['software']['variant_note']=('由 tools/build_sw_variant.sh 派生：bit/XSA/ps7_init/FSBL 与参考包逐字节相同，'
                               '仅应用 ELF 与 BOOT.bin 因编译宏不同而重打。'+('label='+label if label else ''))
for t in ('manifest.json','artifact_manifest.json'):
    json.dump(d, open(p.rsplit('/',1)[0]+'/'+t,'w'), ensure_ascii=False, indent=1)
print('manifest 已更新')
PY

( cd "$OUT_ABS" && find . -type f ! -name SHA256SUMS -printf '%P\n' | LC_ALL=C sort \
    | xargs -d '\n' sha256sum > SHA256SUMS )
( cd "$OUT_ABS" && sha256sum -c SHA256SUMS >/dev/null ) || { echo "SHA256SUMS 自检失败" >&2; exit 1; }

echo
echo "新包：$OUT_ABS"
echo "  参考 ELF SHA : $REF_ELF_SHA"
echo "  新   ELF SHA : $(sha256sum "$OUT_ABS/export/dna_lwip_app.elf" | cut -d' ' -f1)"
echo "  bit   SHA     : $NEW_BIT_SHA（与参考包相同）"
echo "  SHA256SUMS    : $(grep -c '' "$OUT_ABS/SHA256SUMS") 项，全部 OK"
echo "  CFLAGS 追加   :$DEFSTR"
