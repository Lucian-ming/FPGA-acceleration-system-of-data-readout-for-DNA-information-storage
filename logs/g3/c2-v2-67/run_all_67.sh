#!/usr/bin/env bash
# C2 v2 @ **score_min=67（出厂门限）**：21 baseline + 21 challenge，共 42 例。
#
# 为什么有这个脚本（2026-10-16 新增）
# ----------------------------------
# §17/§18 把 v2 的 42 例全部跑完了，但用的是 `--score-min 65`
# —— 那是**数据集自带软件验证器**的门限，**不是出厂门限**。
# 客户端的 `default_score_min(150) == 67`，发布件 G3/长稳也都跑 67。
# ⇒ 现有"泛化 42/42 一致"这个结论**建立在一个比出厂更松的门限上**。
#
# 本脚本回答的问题（**没有软件基准可比，所以不是"一致性"验收**）：
#   1. 门限收到 67 后，**失败是否仍是"安全失败"** —— 即以 `LDPC 不收敛` 暴露，
#      而**不是**静默给出错误字节？出现后者就是真缺陷。
#   2. 与 65 档**逐例差异**（哪些从 PASS 变 FAIL、有没有反向翻转）。
#   3. 8 个 challenge 难例是否仍按同一机制失败。
#
# ⚠️ 纪律：**难例失败必须保留、不得降难度后宣布泛化通过**（数据集 HANDOFF 明确要求）。
#
# 与原脚本（logs/g3/c2-v2-challenge/run_all.sh）的差异
# ---------------------------------------------------
#   1. `--score-min 65` → **67**；
#   2. 判据 SHA 的取值措辞：原用 `唯一判据.*`，那是**三层判据实施之前**的格式，
#      现行 `run_g3.sh` 输出「系统判据 : PASS — SHA-256 <hex>」。只留旧正则会让
#      match 列恒为 NO —— 一个不会响的检查（与 g3_soak.py 当年同一坑）。
#      这里**先按新格式取，再回退旧格式**；
#   3. Windows 侧 xsdb/COM10/D:  → **WSL 侧** xsdb + `--hw-server` + `/dev/ttyUSB2` + /mnt/d；
#   4. 制品换成当前推广包（可用 ARTIFACT 覆盖）。
set -u
cd /home/lucian/projects/FPGA/FpgaAccelerationSystemOfDataReadout

D="/mnt/e/桌面/dna-multimedia-simulation-v2-20261013"
P="${ARTIFACT:-hw/build/bkb220-p16-k2-ldpc-release-stage3poll-20261016T000308Z-board-migrate}"
OUT="${OUTDIR:-logs/g3/c2-v2-67}"
SCORE_MIN="${SCORE_MIN:-67}"
mkdir -p "$OUT"
SUM="$OUT/SUMMARY.tsv"
printf 'case\tasset\tclass\tkind\text\tinput_bytes\texpect_sha16\tverdict\tjudge_sha16\tmatch\tfailmode\tnote\n' > "$SUM"

BOOTED=0   # 0 = 板上还不是本包，第一例必须真烧录

# 判据 SHA：先认新措辞（系统判据），再回退旧措辞（唯一判据）
judge_sha() {   # $1 = run_g3.sh 的输出文件
  local s
  s=$(grep -aoE '系统判据[^—]*—[[:space:]]*SHA-256[[:space:]]+[0-9a-f]{64}' "$1" | grep -aoE '[0-9a-f]{64}' | tail -1)
  [ -n "$s" ] || s=$(grep -aoE '唯一判据.*' "$1" | grep -aoE '[0-9a-f]{64}' | tail -1)
  printf '%s' "$s"
}

run_one() {   # $1=case_id $2=asset $3=class $4=kind $5=ext $6=ib $7=sha $8=fq $9=wm ${10}=skipboot
  local case="$1" asset="$2" cls="$3" kind="$4" ext="$5" ib="$6" sha="$7" fq="$8" wm="$9" sb="${10}"
  local tag="$OUT/${case}.out"
  local EXTRA=()
  case "$ext" in jpg|jpeg) : ;; *) EXTRA=(--input-bytes "$ib") ;; esac
  local SBARG=()
  [ "$sb" = "1" ] && SBARG=(--skip-boot)
  bash tools/run_g3.sh \
    --artifact-dir "$P" \
    --xsdb /tools/Xilinx/Vitis/2022.2/bin/xsdb --hw-server TCP:127.0.0.1:3132 \
    --device xc7z020 --strict-artifacts \
    --uart-port /dev/ttyUSB2 --ip 192.168.1.10 --port 7 \
    --win-root /mnt/d/bkb220_board_smoke \
    --reads "$fq" --watermark "$wm" --expect-sha "$sha" \
    --score-min "$SCORE_MIN" --full --skip-dump "${SBARG[@]}" "${EXTRA[@]}" \
    > "$tag" 2>&1
  local v j m note fm
  v=$(grep -aoE 'G3 (PASS|FAIL)' "$tag" | tail -1)
  j=$(judge_sha "$tag")
  m="NO"; [ -n "$j" ] && [ "$j" = "$sha" ] && m="YES"
  # 失败模式：LDPC 不收敛（安全失败） vs 其它（需要人看）
  fm=""
  if [ "$v" != "G3 PASS" ]; then
    if grep -aqE 'LDPC.{0,6}未收敛|不收敛' "$tag"; then fm="LDPC_NOCONV"; else fm="OTHER_SEE_LOG"; fi
  fi
  note=""
  if grep -aqE '^\s*FAIL\s+烧录' "$tag" || grep -aqE '^\s*FAIL\s+板端应用层就绪' "$tag"; then
    note="BOOT_FAIL"     # 交给上层重烧一次
  fi
  printf '%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\n' \
    "$case" "$asset" "$cls" "$kind" "$ext" "$ib" "${sha:0:16}" "${v:-?}" "${j:0:16}" "$m" "$fm" "$note" >> "$SUM"
  echo "  -> $case  $v  match=$m  failmode=$fm $note"
}

for ds in $(ls -d "$D"/datasets/*/ | sort); do
  base=$(basename "$ds"); asset=${base#*_}
  enc="$D/encoded/$asset/block000"
  wm="$enc/watermark.txt"
  read -r sha ib < <(python3 -I -c "import json;j=json.load(open('$enc/encoding.json'));print(j['input_sha256'], j['input_bytes'])")
  ext=$(ls "$D/payloads" | grep -iE "^${asset}\." | head -1 | sed 's/.*\.//')
  kind=$(python3 -I -c "
import json
for c in json.load(open('$D/suite_results.json')):
    if c['asset']=='$asset': print(c['kind']); break")
  for cls in baseline challenge; do
    fq="$ds/$cls/block000/se150.fastq"
    [ -f "$fq" ] || { echo "SKIP $asset/$cls (无 se150.fastq)"; continue; }
    case_id="$asset-$cls"
    echo "===== $case_id ====="
    if [ "$BOOTED" = "0" ]; then
      run_one "$case_id" "$asset" "$cls" "$kind" "$ext" "$ib" "$sha" "$fq" "$wm" 0
      BOOTED=1
    else
      run_one "$case_id" "$asset" "$cls" "$kind" "$ext" "$ib" "$sha" "$fq" "$wm" 1
      if tail -1 "$SUM" | grep -q 'BOOT_FAIL'; then
        echo "  !! 就绪失败，重烧重跑 $case_id"
        sed -i '$ d' "$SUM"
        run_one "$case_id" "$asset" "$cls" "$kind" "$ext" "$ib" "$sha" "$fq" "$wm" 0
      fi
    fi
  done
done
echo "=== C2 V2 score_min=$SCORE_MIN FULL SWEEP DONE ==="
