#!/usr/bin/env bash
# tools/board/g3_upload_sweep.sh —— 读段上传段的多档 x 多次扫描（**只测上传，不触发流水线**）
#
# 为什么要有它
# ------------
# `first.py` 的 `stats.t_batches` 是整轮里最容易被误判的一段：2026-10-13 之前它被当成
# 「逐批 ACK 停等」，实测否掉（批次数降到 1/4 只降 6%）。要判断上传段到底被什么限速，
# 必须能在**不触发流水线**的前提下、按规模重复取数。
# `--no-post` 让板子只把读段收进 DDR 就停，所以本脚本**不判正确性**，只出耗时与吞吐；
# 正确性判据仍必须由 `tools/run_g3.sh --full --strict-artifacts` 给。
#
# 用法：
#   bash tools/board/g3_upload_sweep.sh <tag> [IP:PORT]
#   → 写 logs/g3/<tag>/upload-sweep.tsv（logs/ 不入库，文件保留）
#
# 边界：板端耗时是**客户端打印值**（墙钟），不是硬件周期计数；`hardware_cycles`/`power_w` 仍为 null。
# **烧的是哪个包由调用者负责**——本脚本不烧录、也不核验板上跑的是哪份固件，
# 所以做 A/B 时必须在两次扫描之间自己换包，并把包 SHA 记进 <tag>。
set -euo pipefail
cd "$(dirname "$0")/../.."   # tools/board -> 工程根（src/）
TAG="$1"
IPPORT="${2:-192.168.1.10:7}"
IP="${IPPORT%%:*}"; PORT="${IPPORT##*:}"
OUT="logs/g3/${TAG}/upload-sweep.tsv"
mkdir -p "$(dirname "$OUT")"
R083_DATA_PARENT="../data"
READS="$R083_DATA_PARENT/r083-data/sequencing-data/dna-40_5kb-mc-se150.fastq"
WM="$R083_DATA_PARENT/r083-data/source-data/watermark-sequences/r0.83_watermark.txt"
printf 'tag\tsource_reads\trep\tbatches\tbytes\tt_batches_s\tmbps\n' > "$OUT"
for LIM in 2048 8192 32768 full; do
  for REP in 1 2 3; do
    ARGS=(--ip "$IP" --port "$PORT" --reads "$READS" --watermark "$WM"
          --output "/tmp/${TAG}-${LIM}-${REP}.bits.txt" --no-post --batch 1000)
    [[ "$LIM" == "full" ]] || ARGS+=(--limit "$LIM")
    if ! LINE="$(timeout 300 python3 clients/python/first.py "${ARGS[@]}" 2>&1 \
            | /bin/grep -E '^\s+Reads:' | tail -1)"; then
      echo "ERROR: upload measurement failed (command, timeout, or missing Reads line): limit=$LIM rep=$REP" >&2
      exit 1
    fi
    # Reads: 104 batches, 4144640 bytes, 0.27s, 123.36 Mbps
    if [[ ! "$LINE" =~ ^[[:space:]]+Reads:[[:space:]]+([0-9]+)[[:space:]]+batches,[[:space:]]+([0-9,]+)[[:space:]]+bytes,[[:space:]]+([0-9]+([.][0-9]+)?)s,[[:space:]]+([0-9]+([.][0-9]+)?)[[:space:]]+Mbps[[:space:]]*$ ]]; then
      echo "ERROR: malformed Reads measurement: ${LINE:-<empty>}" >&2
      exit 1
    fi
    B="${BASH_REMATCH[1]}"
    BY_RAW="${BASH_REMATCH[2]}"
    T="${BASH_REMATCH[3]}"
    M="${BASH_REMATCH[5]}"
    if [[ ! "$BY_RAW" =~ ^[0-9]+$ && ! "$BY_RAW" =~ ^[0-9]{1,3}(,[0-9]{3})+$ ]]; then
      echo "ERROR: invalid byte-count grouping: $BY_RAW" >&2
      exit 1
    fi
    BY="${BY_RAW//,/}"
    if ! awk -v b="$B" -v by="$BY" -v t="$T" -v m="$M" \
            'BEGIN { exit !(b > 0 && by > 0 && t > 0 && m > 0) }'; then
      echo "ERROR: non-positive/invalid measurement fields: batches=$B bytes=$BY seconds=$T Mbps=$M" >&2
      exit 1
    fi
    printf '%s\t%s\t%s\t%s\t%s\t%s\t%s\n' "$TAG" "$LIM" "$REP" "$B" "$BY" "$T" "$M" >> "$OUT"
    echo "  $TAG limit=$LIM rep=$REP -> ${T}s (${M} Mbps)"
  done
done
echo "written: $OUT"
