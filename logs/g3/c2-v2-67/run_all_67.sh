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
P="${ARTIFACT:-}"
OUT="${OUTDIR:-}"
SCORE_MIN="${SCORE_MIN:-67}"
ALLOW_OVERWRITE=0
while (($#)); do
  case "$1" in
    --i-know-overwrite-existing) ALLOW_OVERWRITE=1; shift ;;
    -h|--help)
      cat <<'HELP'
用法：ARTIFACT=<制品目录> OUTDIR=<全新输出目录> bash logs/g3/c2-v2-67/run_all_67.sh [--i-know-overwrite-existing]

ARTIFACT 必须含 manifest.json，且 manifest 中 bit/elf 指向存在的文件。
OUTDIR 必须显式设置；目录非空时拒绝运行，只有明确确认后才可加覆盖开关。
HELP
      exit 0
      ;;
    *) echo "FATAL: 未知参数 $1" >&2; exit 2 ;;
  esac
done

if [[ -z "$P" ]]; then
  echo "FATAL: 必须显式设置 ARTIFACT=<制品目录>；不再猜测默认制品包" >&2
  exit 2
fi
if [[ ! -d "$P" || ! -f "$P/manifest.json" ]]; then
  echo "FATAL: ARTIFACT 必须是含 manifest.json 的制品目录：$P" >&2
  exit 2
fi
if [[ -z "$OUT" ]]; then
  echo "FATAL: 必须显式设置 OUTDIR=<输出目录>；不再使用默认留证目录" >&2
  exit 2
fi
if [[ -e "$OUT" && ! -d "$OUT" ]]; then
  echo "FATAL: OUTDIR 已存在但不是目录：$OUT" >&2
  exit 2
fi
if [[ -d "$OUT" ]] && find "$OUT" -mindepth 1 -print -quit | grep -q . && (( ! ALLOW_OVERWRITE )); then
  echo "FATAL: OUTDIR 已存在且非空：$OUT；确认覆盖时显式传 --i-know-overwrite-existing" >&2
  exit 2
fi

# 身份信息从 manifest 指定的实际 bit/elf 取值，避免用目录名猜测产物。
IDENTITY=$(python3 - "$P" <<'PY'
import hashlib
import json
import sys
from pathlib import Path

root = Path(sys.argv[1]).resolve()
manifest = root / "manifest.json"
data = json.loads(manifest.read_text(encoding="utf-8"))
artifacts = data.get("artifacts", {})
rows = [("manifest", manifest)]
for key in ("bit", "elf"):
    rel = artifacts.get(key)
    if not isinstance(rel, str) or not rel:
        raise SystemExit(f"manifest.json 缺少 artifacts.{key}")
    path = (root / rel).resolve(strict=True)
    try:
        path.relative_to(root)
    except ValueError:
        raise SystemExit(f"artifacts.{key} 越出制品目录：{rel}")
    if not path.is_file():
        raise SystemExit(f"artifacts.{key} 不是文件：{rel}")
    rows.append((key, path))
for name, path in rows:
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    print(f"{name}\t{path.relative_to(root)}\t{digest}")
PY
) || { echo "FATAL: 无法从制品包读取 manifest/bit/elf 身份" >&2; exit 2; }

mkdir -p "$OUT"
SUM="$OUT/SUMMARY.tsv"
printf 'artifact\tpath\tsha256\n%s\n' "$IDENTITY" > "$OUT/artifact_identity.txt"
printf 'case\tasset\tclass\tkind\text\tinput_bytes\texpect_sha16\tverdict\tjudge_sha16\tmatch\tfailmode\tnote\tprocess_rc\n' > "$SUM"

BOOTED=0   # 0 = 板上还不是本包，第一例必须真烧录
CASE_COUNT=0
CASE_FAILURES=0
RUN_FAILURES=0
LAST_NOTE=""

# 判据 SHA：先认新措辞（系统判据），再回退旧措辞（唯一判据）
judge_sha() {   # $1 = run_g3.sh 的输出文件
  local s
  s=$(grep -aoE '系统判据[^—]*—[[:space:]]*SHA-256[[:space:]]+[0-9a-f]{64}' "$1" | grep -aoE '[0-9a-f]{64}' | tail -1)
  [ -n "$s" ] || s=$(grep -aoE '唯一判据.*' "$1" | grep -aoE '[0-9a-f]{64}' | tail -1)
  printf '%s' "$s"
}

run_one() {   # $1=case_id $2=asset $3=class $4=kind $5=ext $6=ib $7=sha $8=fq $9=wm ${10}=skipboot
  local case="$1" asset="$2" cls="$3" kind="$4" ext="$5" ib="$6" sha="$7" fq="$8" wm="$9" sb="${10}"
  local suffix="${11:-}"
  local tag="$OUT/${case}${suffix}.out"
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
  local rc=$?
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
  if (( rc == 0 )) && grep -aqE '^PASS[[:space:]]+烧录([[:space:]]|$)' "$tag"; then
    BOOTED=1
  fi
  if (( rc != 0 )); then
    note="${note:+$note,}RUN_G3_RC_$rc"
  fi
  printf '%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%d\n' \
    "$case" "$asset" "$cls" "${kind:-?}" "${ext:-?}" "${ib:-?}" "${sha:0:16}" "${v:-?}" "${j:0:16}" "$m" "${fm:-}" "${note:-}" "$rc" >> "$SUM"
  LAST_NOTE="$note"
  if (( rc != 0 )) || [[ "$v" != "G3 PASS" || "$m" != "YES" || "$fm" == "OTHER_SEE_LOG" || "${kind^^}" == "OTHER" || -n "$note" ]]; then
    ((CASE_FAILURES += 1))
    ((RUN_FAILURES += 1))
  fi
  echo "  -> $case  ${v:-?}  match=$m  failmode=$fm rc=$rc $note"
}

record_missing() {   # $1=case $2=asset $3=class $4=kind $5=why
  printf '%s\t%s\t%s\t%s\t?\t?\t?\tMISSING\t\tNO\tOTHER_SEE_LOG\t%s\tNA\n' \
    "$1" "$2" "$3" "${4:-?}" "$5" >> "$SUM"
  ((CASE_FAILURES += 1))
  echo "  !! $1 缺失：$5"
}

if [[ ! -d "$D/datasets" ]]; then
  echo "FATAL: 数据集目录不存在：$D/datasets" >&2
  exit 2
fi
shopt -s nullglob
DATASETS=("$D"/datasets/*/)
if ((${#DATASETS[@]} == 0)); then
  echo "FATAL: 数据集目录为空：$D/datasets" >&2
  exit 2
fi
for ds in "${DATASETS[@]}"; do
  base=$(basename "$ds"); asset=${base#*_}
  enc="$D/encoded/$asset/block000"
  wm="$enc/watermark.txt"
  meta=""
  if [[ -f "$enc/encoding.json" ]]; then
    meta=$(python3 -I - "$enc/encoding.json" <<'PY'
import json, sys
data = json.load(open(sys.argv[1], encoding="utf-8"))
print(data.get("input_sha256", ""), data.get("input_bytes", ""))
PY
) || meta=""
  fi
  read -r sha ib <<< "$meta"
  ext=""
  if [[ -d "$D/payloads" ]]; then
    for payload in "$D"/payloads/*; do
      [[ -f "$payload" ]] || continue
      if [[ "$(basename "$payload")" =~ ^${asset}\. ]]; then
        ext="${payload##*.}"
        break
      fi
    done
  fi
  kind=""
  if [[ -f "$D/suite_results.json" ]]; then
    kind=$(python3 -I - "$D/suite_results.json" "$asset" <<'PY'
import json, sys
for case in json.load(open(sys.argv[1], encoding="utf-8")):
    if case.get("asset") == sys.argv[2]:
        print(case.get("kind", "")); break
PY
) || kind=""
  fi
  for cls in baseline challenge; do
    fq="$ds/$cls/block000/se150.fastq"
    case_id="$asset-$cls"
    ((CASE_COUNT += 1))
    if [[ ! -f "$fq" ]]; then
      record_missing "$case_id" "$asset" "$cls" "$kind" "无 se150.fastq"
      continue
    fi
    if [[ -z "${sha:-}" || ! "${ib:-}" =~ ^[1-9][0-9]*$ || -z "$ext" || ! -f "$wm" || -z "$kind" ]]; then
      record_missing "$case_id" "$asset" "$cls" "$kind" "encoding/payload/watermark/kind 元数据缺失"
      continue
    fi
    echo "===== $case_id ====="
    if [ "$BOOTED" = "0" ]; then
      run_one "$case_id" "$asset" "$cls" "$kind" "$ext" "$ib" "$sha" "$fq" "$wm" 0
    else
      run_one "$case_id" "$asset" "$cls" "$kind" "$ext" "$ib" "$sha" "$fq" "$wm" 1
      if [[ "$LAST_NOTE" == *BOOT_FAIL* ]]; then
        echo "  !! 就绪失败，保留首轮记录并重烧重跑 $case_id"
        run_one "$case_id" "$asset" "$cls" "$kind" "$ext" "$ib" "$sha" "$fq" "$wm" 0 ".retry"
      fi
    fi
  done
done
if (( CASE_COUNT != 42 )); then
  echo "FATAL: 预期 42 例，实际枚举到 $CASE_COUNT 例"
  ((CASE_FAILURES += 1))
fi
echo "=== C2 V2 score_min=$SCORE_MIN FULL SWEEP DONE ==="
if (( CASE_FAILURES != 0 || RUN_FAILURES != 0 || CASE_COUNT != 42 )); then
  echo "AGGREGATE: FAIL cases=$CASE_COUNT case_failures=$CASE_FAILURES failed_runs=$RUN_FAILURES"
  exit 1
fi
echo "AGGREGATE: PASS cases=$CASE_COUNT failures=0"
