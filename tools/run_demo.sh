#!/usr/bin/env bash
# =============================================================================
# tools/run_demo.sh —— 答辩现场演示：换 payload + 故障红灯
#
# 为什么要有它
# ------------
# docs/05-implementation-plan.md的G4/G8门禁 列了两个最能形成技术记忆点的演示：
#   C4 现场换 payload —— 证明系统不是「只会跑那一张图」的通道；
#   C5 故障注入红灯 —— 证明判据有鉴别力，不是只会报 PASS。
# 这两件事必须**现场实时产生哈希**，不能展示预生成结果
# （docs/06-verification-plan.md的真实输出判据：「演示只能依靠预生成正确结果」即为不合格）。
#
# 本脚本把两者串成一条命令，每一步的哈希都是当场从板端回传算出来的。
#
# 演示设计
# --------
#   第 1 幕 (C4)  D0 真实图像      -> 现场出哈希，与该 payload 自己的参考比对
#   第 2 幕 (C4)  D1 纯文本        -> 换成完全不同的 payload，现场出哈希
#                 两幕用**同一个比特流、同一份固件**，只换输入。
#   第 3 幕 (C5)  D1 高熵 @门限60  -> **预期红灯**，如实报 FAIL
#   第 4 幕 (C5)  D1 高熵 @门限65  -> 同一份数据，调整门限后恢复
#                 第 3/4 幕合起来说明：失败是**确定性的算法边界**，
#                 不是随机故障，而且我们知道它在哪、怎么跨过去。
#
# 判据边界（讲解时必须说清楚）
# ----------------------------
#   - 板端回传是真实的，但 LDPC 译码与哈希比对在主机侧完成；
#   - 第 3 幕的失败是**已知边界**，2026-09-10 实测 0/3 稳定复现，不是现场翻车；
#   - 单次演示不构成成功率，成功率见
#     docs/benchmarks/measured_board_multi_payload.md §6（21 次运行 18/21）。
#
# 用法
# ----
#   tools/run_demo.sh              # 板子已在跑（推荐：先跑一次 run_g3.sh 确认环境）
#   tools/run_demo.sh --ip 192.168.1.10
#   tools/run_demo.sh --quick      # 只演 C4 两幕，不演故障红灯
#
# 前提：板子已烧录并在运行，且没有其他进程占用板卡
#       （板端 lwIP 是单例 g_conn，并发连接会破坏正在进行的任务）。
# =============================================================================
set -uo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO"

BOARD_IP="192.168.1.10"
BOARD_PORT=7
QUICK=0

while [[ $# -gt 0 ]]; do
    case "$1" in
        --ip)    BOARD_IP="$2"; shift 2 ;;
        --port)  BOARD_PORT="$2"; shift 2 ;;
        --quick) QUICK=1; shift ;;
        -h|--help) sed -n '2,40p' "$0"; exit 0 ;;
        *) echo "未知参数：$1" >&2; exit 2 ;;
    esac
done

RUN_ID="demo_$(date +%Y%m%dT%H%M%SZ)"
OUT_DIR="$REPO/logs/demo/$RUN_ID"
mkdir -p "$OUT_DIR"

banner() {
    printf '\n\033[1;36m'
    printf '═%.0s' {1..72}; printf '\n  %s\n' "$*"
    printf '═%.0s' {1..72}; printf '\033[0m\n'
}
note() { printf '  \033[2m%s\033[0m\n' "$*"; }

# 每一幕：跑一个数据集，现场打印哈希与判定
# $1=数据集 test_id  $2=幕标题  $3=预期结果(PASS/FAIL)
declare -a SCENE_NAME SCENE_EXPECT SCENE_ACTUAL
scene() {
    local ds="$1" title="$2" expect="$3"
    banner "$title"
    local log="$OUT_DIR/${ds}.log"
    if timeout 600 python3 tools/run_multi_payload_regression.py \
            --mode board --extended --dataset "$ds" \
            --ip "$BOARD_IP" --port "$BOARD_PORT" \
            --out-dir "$OUT_DIR/$ds" > "$log" 2>&1; then :; fi

    # 现场把哈希与误码打出来（全部来自本次板端回传）
    grep -E "结果: 误码|恢复 SHA|预期 SHA" "$log" | sed 's/^/  /' || true
    local got
    got="$(grep -oE '匹配=(True|False)' "$log" | tail -1 | cut -d= -f2)"
    local actual="FAIL"; [[ "$got" == "True" ]] && actual="PASS"

    SCENE_NAME+=("$title"); SCENE_EXPECT+=("$expect"); SCENE_ACTUAL+=("$actual")
    if [[ "$actual" == "$expect" ]]; then
        printf '  \033[32m▶ 本幕结果：%s（与预期一致）\033[0m\n' "$actual"
    else
        printf '  \033[31m▶ 本幕结果：%s，但预期是 %s —— 与留证不符，需当场说明\033[0m\n' \
               "$actual" "$expect"
    fi
    note "原始日志：$log"
    sleep 2   # 让板端单例 g_conn 回收
}

banner "DNA 信息存储读出系统 · 现场演示   run=$RUN_ID"
note "板卡 $BOARD_IP:$BOARD_PORT   全部哈希均为本次板端回传现场算出，无预生成结果"
note "同一比特流、同一固件，全程只换输入"

scene D0_image_mandrill      "第 1 幕 · 真实测序数据恢复原始图像 (D0)"        PASS
scene D1_text_manifesto      "第 2 幕 · 现场换成完全不同的 payload：纯文本 (D1)" PASS

if (( ! QUICK )); then
    scene D1_random_entropy      "第 3 幕 · 故障红灯：高熵数据 @ 出厂门限 60（预期失败）" FAIL
    scene D1_random_entropy_thr65 "第 4 幕 · 同一数据 @ 自适应门限 65（恢复）"        PASS
fi

banner "演示汇总"
printf '  %-52s %-8s %s\n' "幕次" "预期" "实测"
for i in "${!SCENE_NAME[@]}"; do
    color=$'\033[32m'
    [[ "${SCENE_EXPECT[$i]}" != "${SCENE_ACTUAL[$i]}" ]] && color=$'\033[31m'
    printf "  %-52s %-8s ${color}%s\033[0m\n" \
        "${SCENE_NAME[$i]}" "${SCENE_EXPECT[$i]}" "${SCENE_ACTUAL[$i]}"
done
cat <<EOF

  要点：
    · 第 1/2 幕用同一比特流、同一固件跑两个**完全不同**的 payload —— 不是通道；
    · 第 3 幕如实报 FAIL —— 判据有鉴别力，系统不是只会报 PASS；
    · 第 4 幕说明那个失败是**确定性的算法边界**（实测 0/3 稳定复现），
      我们知道它在哪、也知道怎么跨过去。
    · 成功率见 docs/benchmarks/measured_board_multi_payload.md §6（21 次 18/21）。

  留证目录：$OUT_DIR
EOF
