#!/usr/bin/env bash
# RTL 仿真回归：用 tests/golden/ 里的黄金向量逐位判定，不匹配即失败。
#
#   bash tools/run_sim.sh              # 跑全部
#   bash tools/run_sim.sh datapath     # 只跑某一项
#
# 依赖 Icarus Verilog（iverilog / vvp）。黄金向量由 tools/make_golden.py 生成。
set -u

cd "$(dirname "$0")/.." || exit 1
BUILD=$(mktemp -d)
trap 'rm -rf "$BUILD"' EXIT

PASS=0
FAIL=0
A1=hw/ip/Dna_accelerator_core_1_0/hdl

run_case() {
    local name="$1"; shift
    printf '\n=== %s ===\n' "$name"
    if ! iverilog -g2005 -o "$BUILD/$name" "$@" 2>&1; then
        echo "  ✗ 编译失败"
        FAIL=$((FAIL+1)); return
    fi
    if timeout 600 vvp "$BUILD/$name" 2>&1 | sed 's/^/  /'; then
        PASS=$((PASS+1))
    else
        FAIL=$((FAIL+1))
    fi
}

if [ ! -f tests/golden/sparse_ideal.hex ]; then
    echo "缺少黄金向量，请先运行： python3 tools/make_golden.py"
    exit 1
fi

WHICH="${1:-all}"
D=hw/ip/desparsification_decoder_1_0/hdl

if [ "$WHICH" = "all" ] || [ "$WHICH" = "datapath" ]; then
    # Stage3 数据通路：81,000 bit 稀疏流 -> 64,800 bit 码字（含随机背压）
    run_case desparsify_datapath "$D/desparsify_datapath.v" "$D/tb_desparsify_datapath.v"
fi

if [ "$WHICH" = "all" ] || [ "$WHICH" = "axi" ]; then
    # Stage3 整核（AXI-Lite 配置 + AXI4 读写 DDR），从机取最严格设置：
    # B 零延迟、只允许 1 个未完成地址
    run_case desparsifier_axi "$D/desparsification_decoder_v1_0.v" \
                              "$D/desparsify_datapath.v" "$D/tb_desparsifier.v"
fi

if [ "$WHICH" = "all" ] || [ "$WHICH" = "stage1" ]; then
    # Stage1 比对引擎：一批 64 条读段，pos/score 与黄金模型比对
    # （约 620 万周期，Icarus 上 1~3 分钟）
    run_case srpe_batch "$A1/srpe_batch.v" "$A1/tb_srpe_batch.v"
fi

if [ "$WHICH" = "all" ] || [ "$WHICH" = "stage2" ]; then
    # Stage2 投票核：4,096 条 Stage1 输出记录（正反两方向，与上位机一致）
    # → 81,000 bit 共识。连跑两轮，第二轮验证累加器重新清零。
    V=hw/ip/differential_voter_1_0/hdl
    run_case differential_voter "$V/differential_voter_v1_0.v" "$V/tb_differential_voter.v"
fi

if [ "$WHICH" = "all" ] || [ "$WHICH" = "host" ]; then
    # PS 侧水印展开的主机单元测试（与固件共用 sw/app/wm_expand.h）
    printf '\n=== wm_expand（PS 侧水印展开，主机单元测试）===\n'
    if gcc -O2 -I sw/app -o "$BUILD/test_wm" tools/test_wm_expand.c 2>&1 \
       && "$BUILD/test_wm" tests/golden/watermark_packed.bin tests/golden/wm_regions.hex \
          | sed 's/^/  /'; then
        PASS=$((PASS+1))
    else
        FAIL=$((FAIL+1))
    fi
fi

if [ "$WHICH" = "all" ] || [ "$WHICH" = "syntax" ]; then
    # 语法体检：三个当前综合顶层（不是功能验证）
    printf '\n=== 语法检查（三个综合顶层）===\n'
    check() {  # 名称 + 该顶层的完整文件集
        local label="$1"; shift
        if iverilog -g2005 -t null "$@" 2>/dev/null; then
            echo "  ✓ $label"
        else
            echo "  ✗ $label"; FAIL=$((FAIL+1))
        fi
    }
    check Dna_accelerator_core \
        "$A1/Dna_accelerator_core_v1_0.v" "$A1/srpe_batch.v" \
        "$A1/Dna_accelerator_core_v1_0_S_AXI_LITE_CTRL.v" \
        "$A1/fifo_sync_sdpram_b64.v" "$A1/s2mm_pack64.v"
    check differential_voter        hw/ip/differential_voter_1_0/hdl/differential_voter_v1_0.v
    check desparsification_decoder  "$D/desparsification_decoder_v1_0.v" "$D/desparsify_datapath.v"
    check five_to_four_decoder      "$D/five_to_four_decoder.v"
fi

printf '\n==================================================\n'
printf '通过 %d 项，失败 %d 项\n' "$PASS" "$FAIL"
printf '==================================================\n'
[ "$FAIL" -eq 0 ]
