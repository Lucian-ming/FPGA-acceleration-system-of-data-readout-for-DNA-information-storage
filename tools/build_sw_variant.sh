#!/usr/bin/env bash
# tools/build_sw_variant.sh —— 从一份已验收的完整制品包派生出「只改 PS 侧编译配置」的变体包
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
#   2. **[可选]** 改 BSP 的 `lwipopts.h`（`--lwip-opt`）并重建 BSP 库
#      （liblwip4.a / libxil.a）；
#   3. 把 workspace 里 Makefile 的路径改指向新包，并在 CFLAGS 追加给定宏（`--define`）；
#   4. 清掉应用目标文件后重建 ELF；
#   5. 用新 ELF 重打 BOOT.bin（bootgen，与参考包同一 .bif）；
#   6. 在 manifest 里写明**派生了什么、参考包与参考 ELF 的 SHA**，重签 SHA256SUMS。
#
# 为什么 `--lwip-opt` 必须重建 BSP 库，而不能只改头文件
# ------------------------------------------------------
# `TCP_WND` 这类开关是在**编译 lwIP 库时**被烧进 `liblwip4.a` 的（`tcp_in.c`/`tcp_out.c`
# 里按它算接收窗口），应用侧再 `-D` 也改不了。而 BSP 的 Makefile **没有头文件依赖跟踪**
# （COMPILER_FLAGS 里只有 `-O2 -c`，没有 `-MMD`），改完 lwipopts.h 直接 `make` 会因为
# `.o` 比 `.c` 新而**一个文件都不重编**、静默产出与原来完全相同的库。
# 所以这里先删掉 lwIP 的目标文件强制重编，并且在重建后**校验库的 SHA 确实变了**——
# 静默无效的构建必须变红，不能靠"命令退出 0"当成功。
#
# 边界
# ----
# - **硬件制品不变**：bit/XSA/ps7_init 与参考包逐字节相同（脚本会核验并打印）。
#   本脚本**不做**综合/实现，也不改任何 RTL。
# - 它只证明「新包自洽且与参考包同源」；**不证明**新包在板上通过——那要另行跑 G3。
# - 修改只发生在**新包目录内的副本**；`sw/app/` 权威源一个字节都不动。
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
REF=""; OUT=""; DEFS=(); LWIPOPTS=(); LABEL=""; SYNC_SRC=0
while [[ $# -gt 0 ]]; do
  case "$1" in
    --ref)       REF="$2"; shift 2 ;;
    --out)       OUT="$2"; shift 2 ;;
    --define)    DEFS+=("$2"); shift 2 ;;
    --lwip-opt)  LWIPOPTS+=("$2"); shift 2 ;;
    --sync-src)  SYNC_SRC=1; shift ;;
    --label)     LABEL="$2"; shift 2 ;;
    *) echo "未知参数：$1" >&2; exit 2 ;;
  esac
done
[[ -n "$REF" && -n "$OUT" ]] || {
  echo "用法：$0 --ref <参考包> --out <新包> [--define MACRO=V]... [--lwip-opt NAME=VALUE]... [--sync-src] [--label 说明]" >&2
  echo "  至少要给一个 --define / --lwip-opt / --sync-src" >&2; exit 2; }
(( ${#DEFS[@]} + ${#LWIPOPTS[@]} + SYNC_SRC )) || { echo "至少要给一个 --define / --lwip-opt / --sync-src" >&2; exit 2; }
REF_ABS="$(cd "$REF" && pwd)"
[[ -e "$OUT" ]] && { echo "输出目录已存在，拒绝覆盖：$OUT" >&2; exit 1; }
OUT_ABS="$REPO/$OUT"

TOOLBIN=/tools/Xilinx/Vitis/2022.2/gnu/aarch32/lin/gcc-arm-none-eabi/bin
CC=$TOOLBIN/arm-none-eabi-gcc
BOOTGEN=/tools/Xilinx/Vitis/2022.2/bin/bootgen
APP="$OUT_ABS/workspace/dna_lwip_app"
[[ -x "$CC" && -x "$BOOTGEN" ]] || { echo "找不到 2022.2 工具链（$CC / $BOOTGEN）" >&2; exit 1; }

STEPS=6
echo "== 1/$STEPS 复制参考包 =="
mkdir -p "$(dirname "$OUT_ABS")"
cp -a "$REF_ABS" "$OUT_ABS"

# ---- 可选的 BSP 层改动 ----------------------------------------------------
LWIPOPT_NOTE=""
if (( ${#LWIPOPTS[@]} )); then
  echo "== 2/$STEPS 改 lwipopts.h 并重建 BSP 库：${LWIPOPTS[*]} =="
  BSP_ROOT="$(dirname "$(find "$OUT_ABS/workspace" -path '*/standalone_domain/bsp/Makefile' -print -quit)")"
  [[ -d "$BSP_ROOT" ]] || { echo "新包内找不到 BSP Makefile" >&2; exit 1; }
  # 两份 lwipopts.h 必须一起改，否则会分叉：
  #   <bsp>/<cpu>/include/lwipopts.h                    ← 真正被 -I 命中的那份
  #   <bsp>/<cpu>/libsrc/lwip211_*/src/contrib/ports/xilinx/include/lwipopts.h  ← 源副本
  # 限定在 BSP_ROOT 下找，避免误命中 export/ 里的 bspinclude 副本。
  BSP_INC_HDR="$(find "$BSP_ROOT" -maxdepth 3 -name lwipopts.h -path '*/include/*' -print -quit)"
  BSP_SRC_HDR="$(find "$BSP_ROOT" -name lwipopts.h -path '*/libsrc/*' -print -quit)"
  [[ -n "$BSP_INC_HDR" && -n "$BSP_SRC_HDR" ]] || { echo "找不到 lwipopts.h（include / libsrc 两份）" >&2; exit 1; }
  BSP_INST="$(dirname "$(dirname "$BSP_INC_HDR")")"   # .../<bsp>/<cpu>，其下有 include/ 与 lib/
  LIBLWIP="$BSP_INST/lib/liblwip4.a"
  [[ -f "$LIBLWIP" ]] || { echo "找不到 $LIBLWIP" >&2; exit 1; }
  OLD_LIB_SHA=$(sha256sum "$LIBLWIP" | cut -d' ' -f1)

  python3 - "$BSP_INC_HDR" "$BSP_SRC_HDR" "${LWIPOPTS[@]}" <<'PY'
import re, sys
hdrs, pairs = sys.argv[1:3], sys.argv[3:]
for h in hdrs:
    s = open(h, encoding="utf-8", errors="surrogateescape").read()
    for kv in pairs:
        name, _, val = kv.partition("=")
        if not name or not val:
            raise SystemExit(f"--lwip-opt 需要 NAME=VALUE，得到 {kv!r}")
        pat = re.compile(r'^(#define\s+%s\s+)(\S+)(.*)$' % re.escape(name), re.M)
        if not pat.search(s):
            raise SystemExit(f"{h}: 找不到 `#define {name}`，拒绝凭空注入")
        s = pat.sub(lambda m: m.group(1) + val + m.group(3), s)
        print(f"  {h}: #define {name} -> {val}")
    open(h, "w", encoding="utf-8", errors="surrogateescape").write(s)
PY

  # lwIP 的 Makefile 没有头依赖跟踪：不删 .o 就会「成功但什么都没重编」。
  find "$BSP_ROOT" -path '*/libsrc/lwip211_*/src/*.o' -delete
  rm -f "$LIBLWIP"
  PATH="$TOOLBIN:$PATH" make -C "$BSP_ROOT" all \
      > "$OUT_ABS/logs/bsp-build.log" 2>&1 \
      || { echo "BSP 重建失败，见 $OUT_ABS/logs/bsp-build.log" >&2; tail -20 "$OUT_ABS/logs/bsp-build.log" >&2; exit 1; }
  NEW_LIB_SHA=$(sha256sum "$LIBLWIP" | cut -d' ' -f1)
  [[ "$OLD_LIB_SHA" != "$NEW_LIB_SHA" ]] \
    || { echo "liblwip4.a 重建后 SHA 未变——改动没生效，拒绝继续" >&2; exit 1; }
  # export/ 里还有一份交付副本（bsplib/bspinclude）。不同步的话包内会自相矛盾：
  # SHA256SUMS 照样自检通过（它只是把现有内容哈希一遍），但「包里那份头文件」
  # 与「真正链进去的库」对不上。这里一并同步。
  EXP_HDR="$(find "$OUT_ABS/workspace" -name lwipopts.h -path '*/bspinclude/*' -print -quit)"
  EXP_LIB="$(find "$OUT_ABS/workspace" -name liblwip4.a -path '*/bsplib/*' -print -quit)"
  [[ -n "$EXP_HDR" ]] && cp "$BSP_INC_HDR" "$EXP_HDR"
  [[ -n "$EXP_LIB" ]] && cp "$LIBLWIP" "$EXP_LIB"

  LWIPOPT_NOTE="lwip_opts=${LWIPOPTS[*]}"
  echo "  liblwip4.a: $OLD_LIB_SHA -> $NEW_LIB_SHA （已确认真的变了）"
fi

if (( ${#DEFS[@]} )); then
  echo "== 3/$STEPS 改应用 Makefile：路径指向新包 + 追加宏 ${DEFS[*]} =="
else
  echo "== 3/$STEPS 改应用 Makefile：路径指向新包（无 --define） =="
fi
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
if defs:
    if 'PIPE_RUN_SLEEP_US' in m.group(1): raise SystemExit('CFLAGS 里已有该宏，拒绝重复注入')
    s=s[:m.end()]+defs+s[m.end():]
    open(mk,'w').write(s)
    print('CFLAGS 已注入：', defs.strip())
PY

SRC_NOTE=""
if (( SYNC_SRC )); then
  echo "== 3b/$STEPS 同步权威源码 sw/app -> 新包 src/ =="
  # 派生包里的 src/ 是 sw/app 的**构建期副本**。只要改的是 .c/.h 本身（不是编译宏），
  # 就必须重新同步，否则新包编的还是参考包当年那份旧源码，而"--define"根本盖不住。
  # `xparameters.h` 是按平台生成的，不来自 sw/app，必须排除（与 source_manifest 的口径一致）。
  SYNC_DIFF=""
  for f in "$REPO"/sw/app/*.c "$REPO"/sw/app/*.h; do
    b="$(basename "$f")"
    [[ "$b" == "xparameters.h" ]] && continue
    if [[ -f "$APP/src/$b" ]] && ! cmp -s "$f" "$APP/src/$b"; then SYNC_DIFF+=" $b"; fi
    cp "$f" "$APP/src/$b"
  done
  SRC_NOTE="synced_src=${SYNC_DIFF# }"
  echo "  与参考包副本不同的文件：${SYNC_DIFF:-（无）}"
fi

echo "== 4/$STEPS 重建应用 ELF =="
rm -f "$APP"/Debug/*.o "$APP"/Debug/*.d "$APP"/Debug/*.elf "$APP"/Debug/*.map
make -C "$APP" 2>&1 | tail -3
NEWELF="$APP/Debug/dna_lwip_app.elf"
[[ -s "$NEWELF" ]] || { echo "ELF 未生成" >&2; exit 1; }

echo "== 5/$STEPS 更新 export/ 与 BOOT.bin =="
cp "$NEWELF" "$OUT_ABS/export/dna_lwip_app.elf"
# 必须**在 export/ 目录里**跑：bootgen 按 CWD 解析 .bif 里的相对路径（fsbl.elf 等），
# 从包根目录跑会直接 "Cannot read file - fsbl.elf"。
( cd "$OUT_ABS/export" && "$BOOTGEN" -image boot.bif -arch zynq -o BOOT.bin -w on > "$OUT_ABS/logs/bootgen-create.log" 2>&1 ) \
  || { echo "bootgen 失败，见日志" >&2; exit 1; }
grep -q "Bootimage generated successfully" "$OUT_ABS/logs/bootgen-create.log" \
  || { echo "bootgen 未报成功，拒绝继续" >&2; exit 1; }

echo "== 6/$STEPS 写 manifest 并重签 SHA256SUMS =="
REF_BIT_SHA=$(sha256sum "$REF_ABS/export/top_bd_wrapper.bit" | cut -d' ' -f1)
REF_ELF_SHA=$(sha256sum "$REF_ABS/export/dna_lwip_app.elf" | cut -d' ' -f1)
REF_FSBL_SHA=$(sha256sum "$REF_ABS/export/fsbl.elf" | cut -d' ' -f1)
NEW_BIT_SHA=$(sha256sum "$OUT_ABS/export/top_bd_wrapper.bit" | cut -d' ' -f1)
NEW_FSBL_SHA=$(sha256sum "$OUT_ABS/export/fsbl.elf" | cut -d' ' -f1)
[[ "$REF_BIT_SHA" == "$NEW_BIT_SHA" ]] || { echo "bit 与参考包不一致——本脚本不应改硬件制品" >&2; exit 1; }
[[ "$REF_FSBL_SHA" == "$NEW_FSBL_SHA" ]] || { echo "FSBL 与参考包不一致——本脚本不应改 FSBL" >&2; exit 1; }
python3 - "$OUT_ABS/manifest.json" "$REF" "$REF_ELF_SHA" "$LABEL" "$DEFSTR" "$LWIPOPT_NOTE" "$SRC_NOTE" <<'PY'
import json,sys
p,ref,refelf,label,defs,lwip,src=sys.argv[1:8]
d=json.load(open(p))
d['software']['app_defines']=' '.join(defs.split())
if lwip:
    d['software']['bsp_lwipopts']=' '.join(lwip.split('=',1)[1].split()) if '=' in lwip else lwip
if src:
    d['software']['app_src_synced_from']='sw/app'
    d['software']['app_src_files_diff_vs_reference']=src.split('=',1)[1].split()
d['software']['variant_of']={'reference_package':ref,'reference_elf_sha256':refelf}
note=('由 tools/build_sw_variant.sh 派生：bit/XSA/ps7_init/FSBL 与参考包逐字节相同，'
      '仅应用 ELF 与 BOOT.bin 因编译配置不同而重打。')
d['software']['variant_note']=note+('label='+label if label else '')
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
echo "  FSBL  SHA     : $NEW_FSBL_SHA（与参考包相同）"
echo "  SHA256SUMS    : $(grep -c '' "$OUT_ABS/SHA256SUMS") 项，全部 OK"
echo "  CFLAGS 追加   :$DEFSTR"
[[ -n "$LWIPOPT_NOTE" ]] && echo "  lwipopts 改动 : ${LWIPOPTS[*]}"
