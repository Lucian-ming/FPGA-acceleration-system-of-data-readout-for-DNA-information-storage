#!/usr/bin/env bash
# =============================================================================
# tools/run_g5_matrix.sh —— G5「阈值 → 误接受率」曲线的误差矩阵驱动
#
# 做什么
# ------
# 按 docs/05 §4 G5 要求的受控矩阵，用 tools/mutate_reads.py 生成加噪读段，
# 再用 tools/g5_false_accept.py 逐点测「误接受率 / 误拒绝率 vs score_min」。
#
#   替换率扫描   sub = 0 / 0.5% / 1% / 2% / 4%      (indel = 0)
#   插删扫描     ins=del = 0.1% / 0.5%              (sub = 1%)
#   每点 3 个随机种子
#
# 为什么覆盖度不在矩阵里
# ----------------------
# 误接受率是**逐记录**的判定（见 g5_false_accept.py 的定义一节），
# 而覆盖度只改变记录条数，不改变单条记录的得分分布。
# 覆盖度影响的是「恢复成功率」曲线，那条曲线已由
# tools/run_robustness_scan.py 覆盖，不在本脚本职责内。
#
# 产物
# ----
#   $OUT/mut_<tag>/            加噪 FASTQ（可由 seed 复现，故不入库）
#   $OUT/g5_<tag>.json         该点的 τ 扫描结果
#   $OUT/summary.tsv           汇总表
#
# 用法
#   tools/run_g5_matrix.sh [输出目录] [每点读段数]
# =============================================================================
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO"

OUT="${1:-logs/g5_matrix/$(date -u +%Y%m%dT%H%M%SZ)}"
LIMIT="${2:-512}"
BASE_DS="tests/datasets/D1_text_manifesto"
BASE_FQ="$BASE_DS/reads_se150.fastq"

mkdir -p "$OUT"
echo "输出目录 : $OUT"
echo "每点读段 : $LIMIT 条源读段（= $((LIMIT*2)) 条记录）"
echo

# tag  sub      ins      del
POINTS=(
  "sub0.000  0      0      0"
  "sub0.005  0.005  0      0"
  "sub0.010  0.01   0      0"
  "sub0.020  0.02   0      0"
  "sub0.040  0.04   0      0"
  "indel0.001 0.01  0.001  0.001"
  "indel0.005 0.01  0.005  0.005"
)
SEEDS=(101 202 303)

printf 'tag\tseed\tsub\tins\tdel\ttau\taccepted\tfalse_accept\tfa_decoy\tfa_tie\tfa_mis\tfar\tfrr\n' \
    > "$OUT/summary.tsv"

for p in "${POINTS[@]}"; do
    read -r tag sub ins del <<<"$p"
    for seed in "${SEEDS[@]}"; do
        key="${tag}_s${seed}"
        mdir="$OUT/mut_$key"
        if [[ "$sub" == "0" && "$ins" == "0" && "$del" == "0" ]]; then
            # 零噪声点直接用原数据集，不走加噪（避免引入无谓的随机重排）
            dsdir="$BASE_DS"
        else
            python3 tools/mutate_reads.py --input-fastq "$BASE_FQ" --output-dir "$mdir" \
                --manifest "$BASE_DS/manifest.json" \
                --sub-rate "$sub" --ins-rate "$ins" --del-rate "$del" --seed "$seed" \
                >"$OUT/mutate_$key.log" 2>&1
            dsdir="$mdir"
        fi
        python3 tools/g5_false_accept.py --dataset "$dsdir" --limit "$LIMIT" \
            --out-dir "$OUT/res_$key" >"$OUT/g5_$key.log" 2>&1
        python3 - "$OUT/res_$key/g5_false_accept.json" "$tag" "$seed" "$sub" "$ins" "$del" \
            >> "$OUT/summary.tsv" <<'PY'
import json, sys
j = json.load(open(sys.argv[1]))
tag, seed, sub, ins, dele = sys.argv[2:7]
for name, d in j["datasets"].items():
    for r in d["sweep"]:
        print("\t".join(str(x) for x in (
            tag, seed, sub, ins, dele, r["tau"], r["accepted"], r["false_accept"],
            r["fa_decoy"], r["fa_tie"], r["fa_true_mislocate"],
            f'{r["far"]:.6f}', f'{r["frr"]:.6f}')))
PY
        printf '  %-14s seed=%-4s ok\n' "$tag" "$seed"
    done
done

echo
echo "汇总: $OUT/summary.tsv"
