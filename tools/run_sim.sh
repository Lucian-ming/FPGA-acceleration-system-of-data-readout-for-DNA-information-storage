#!/usr/bin/env bash
# RTL 仿真回归：用 tests/golden/ 里的黄金向量逐位判定，不匹配即失败。
#
#   bash tools/run_sim.sh              # 跑全部
#   bash tools/run_sim.sh datapath     # 只跑某一项
#   bash tools/run_sim.sh stage1_production       # 正式P4/P16，LC6快速回归
#   SIM_CASE_TIMEOUT=3600 bash tools/run_sim.sh stage1_production_full # LC50生产长测
#   SIM_LOG_DIR=logs/iverilog/<run-id> 可指定证据目录；退出不删除日志/fixture。
#
# 依赖 Icarus Verilog（iverilog / vvp）。黄金向量由 tools/make_golden.py 生成。
set -uo pipefail

cd "$(dirname "$0")/.." || exit 1
WHICH="${1:-all}"
case "$WHICH" in
    all|packaging|hygiene|datapath|axi|stage1|stage1_4way|stage1_pway|stage1_production|stage1_production_full|core_4way|ingress|dna_axil|stage2|host|syntax) ;;
    *) echo "未知仿真项: $WHICH" >&2; exit 2 ;;
esac
[[ "$#" -le 1 ]] || { echo "只接受一个仿真项参数" >&2; exit 2; }
VVP_ARGS=()
# 每次运行保留编译、配置、源码hash和失败输出，不在退出时删除证据。
BUILD="${SIM_LOG_DIR:-logs/iverilog/run_$(date +%Y%m%d_%H%M%S)_${BASHPID}_${WHICH}}"
mkdir -p "$BUILD" || exit 1
CASE_TIMEOUT="${SIM_CASE_TIMEOUT:-600}"
echo "仿真入口: $WHICH；证据目录: $BUILD；每项超时: ${CASE_TIMEOUT}s"
printf 'entry=%s\ntimeout_seconds=%s\n' "$WHICH" "$CASE_TIMEOUT" > "$BUILD/run-config.txt"

PASS=0
FAIL=0
A1=hw/ip/Dna_accelerator_core_1_0/hdl
# 2026-09-10 起 testbench 不再放在 IP 的 hdl/ 里（那是打包目录，决定综合工具
# 看到什么），统一收到 hw/sim/ip_tb/。见 tools/check_ip_packaging.sh 第 1 项。
IPTB=hw/sim/ip_tb

run_case() {
    local name="$1"; shift
    local log="$BUILD/$name.log"
    local status
    printf '\n=== %s ===\n' "$name"
    printf '%q ' iverilog -g2005 -o "$BUILD/$name" "$@" > "$BUILD/$name.command.txt"
    printf '\n' >> "$BUILD/$name.command.txt"
    for source in "$@"; do
        [[ "$source" == *.v && -f "$source" ]] && sha256sum "$source"
    done > "$BUILD/$name.sources.sha256"
    if ! iverilog -g2005 -o "$BUILD/$name" "$@" > "$BUILD/$name.compile.log" 2>&1; then
        sed 's/^/  /' "$BUILD/$name.compile.log"
        echo "  ✗ 编译失败"
        FAIL=$((FAIL+1)); return
    fi
    printf '%q ' timeout "$CASE_TIMEOUT" vvp "$BUILD/$name" "${VVP_ARGS[@]}" >> "$BUILD/$name.command.txt"
    printf '\n' >> "$BUILD/$name.command.txt"
    timeout "$CASE_TIMEOUT" vvp "$BUILD/$name" "${VVP_ARGS[@]}" >"$log" 2>&1
    status=$?
    sed 's/^/  /' "$log"
    if [ "$status" -eq 0 ] && ! grep -q 'FATAL:' "$log" && grep -q 'PASS' "$log"; then
        PASS=$((PASS+1))
    else
        FAIL=$((FAIL+1))
    fi
}

if [[ "$WHICH" != packaging && "$WHICH" != hygiene && "$WHICH" != syntax ]] \
   && [ ! -f tests/golden/sparse_ideal.hex ]; then
    echo "缺少黄金向量，请先运行： python3 tools/make_golden.py"
    exit 1
fi

# IP 打包卫生门禁：hdl/ 里不许有 testbench、同名模块不许被同时打包、
# component.xml 引用的文件必须存在、不许有孤儿文件、打包变体须与清单一致。
# 放在最前面：这些问题会让综合工具「看到的设计」与你以为的不是同一个，
# 后面所有仿真判据都建立在错误前提上。
if [ "$WHICH" = "all" ] || [ "$WHICH" = "packaging" ] \
   || [ "$WHICH" = "stage1_production" ] || [ "$WHICH" = "stage1_production_full" ]; then
    if bash tools/check_ip_packaging.sh > "$BUILD/packaging.log" 2>&1; then
        cat "$BUILD/packaging.log"
        PASS=$((PASS+1))
    else
        cat "$BUILD/packaging.log"
        FAIL=$((FAIL+1))
    fi
fi

# 仓库卫生门禁：根目录残留、工具登记、文档编号、共享数据副本、logs 忽略覆盖。
# 与打包门禁分开：那个管「综合工具看到什么」，这个管「仓库状态是否自洽」。
if [ "$WHICH" = "all" ] || [ "$WHICH" = "hygiene" ]; then
    if bash tools/check_repo_hygiene.sh; then
        PASS=$((PASS+1))
    else
        FAIL=$((FAIL+1))
    fi
fi
D=hw/ip/desparsification_decoder_1_0/hdl

if [ "$WHICH" = "all" ] || [ "$WHICH" = "datapath" ]; then
    # Stage3 数据通路：81,000 bit 稀疏流 -> 64,800 bit 码字（含随机背压）
    run_case desparsify_datapath "$D/desparsify_datapath.v" "$IPTB/tb_desparsify_datapath.v"
fi

if [ "$WHICH" = "all" ] || [ "$WHICH" = "axi" ]; then
    # Stage3 整核（AXI-Lite 配置 + AXI4 读写 DDR），从机取最严格设置：
    # B 零延迟、只允许 1 个未完成地址
    run_case desparsifier_axi "$D/desparsification_decoder_v1_0.v" \
                              "$D/desparsify_datapath.v" "$IPTB/tb_desparsifier.v"
fi

if [ "$WHICH" = "all" ] || [ "$WHICH" = "stage1" ]; then
    # Stage1 比对引擎：一批 64 条读段，pos/score 与黄金模型比对
    # （约 620 万周期，Icarus 上 1~3 分钟）
    run_case srpe_batch "$A1/srpe_batch.v" "$IPTB/tb_srpe_batch.v"
fi

if [ "$WHICH" = "all" ] || [ "$WHICH" = "stage1_4way" ]; then
    # Stage1 4-way 比对引擎：**这才是 component.xml 当前打包、会进比特流的实现**
    # （见 hw/ip/PACKAGED_VARIANTS.txt）。上面的 srpe_batch 用例测的是 2-way 参考实现。
    # 2026-09-11 之前这两个 4-way TB 存在于 hw/sim/ 却没接进回归，
    # 等于**回归验证的实现与综合出来的实现不是同一个**——这是本轮发现的最严重卫生问题。
    run_case srpe_batch_4way \
        -DSRPE_BATCH_4WAY_MODNAME=srpe_batch_4way \
        "$A1/srpe_batch.v" "$A1/srpe_batch_4way.v" hw/sim/tb_srpe_batch_4way.v
fi

if [ "$WHICH" = "all" ] || [ "$WHICH" = "stage1_pway" ]; then
    # 正式打包的参数化 P 路 Stage1 对照生产 4-way；历史实验源不参与生产回归：
    # P=4 须逐周期相同；P=16 + 选优树流水须逐位相同。NUM_LC=6 玩具配置，约 1 分钟。
    # 生产几何 NUM_LC=50 的结果见 docs/benchmarks/stage1-pway-7020-probe.md。
    run_case srpe_batch_pway_p4 \
        -DSRPE_BATCH_4WAY_MODNAME=srpe_batch_4way -DCFG_P_WAYS=4 -DCFG_PIPE_TREE=0 \
        "$A1/srpe_batch_4way.v" "$A1/srpe_batch_pway.v" hw/sim/tb_srpe_batch_pway.v
    run_case srpe_batch_pway_p16 \
        -DSRPE_BATCH_4WAY_MODNAME=srpe_batch_4way -DCFG_P_WAYS=16 -DCFG_PIPE_TREE=1 \
        "$A1/srpe_batch_4way.v" "$A1/srpe_batch_pway.v" hw/sim/tb_srpe_batch_pway.v
fi

# 真实生产P4/P16源集。stage1_production_full 显式启用LC50长测并建议
# SIM_CASE_TIMEOUT=3600；默认 all 只跑 LC6 快速模块/接口测试。
if [ "$WHICH" = "all" ] || [ "$WHICH" = "stage1_production" ] \
   || [ "$WHICH" = "stage1_production_full" ]; then
    # 2026-10-14 起 Stage1 P16 每拍推进的碱基数已写死为 2（见 RTL 内 localparam
    # BASES_PER_CYCLE），不再是构建期参数，故本入口就是 K=2 的判据，无需额外档位。
    PROD_LC=6
    [[ "$WHICH" == stage1_production_full ]] && PROD_LC=50
    echo "生产配置: READ_BPS=150 NUM_LC=$PROD_LC STRIDE=807 REF_LEN=957 BATCH=64 P4=4/0 P16=16/1 (K=2 写死)"
    printf 'read_bps=150\nnum_lc=%s\nstride=807\nref_len=957\nbatch=64\np4=4/0\np16=16/1\nbases_per_cycle=2\n' \
        "$PROD_LC" >> "$BUILD/run-config.txt"
    FIXTURE_DIR="$(cd "$BUILD" && pwd)/fixtures"
    printf '%q ' python3 tools/board/generate_stage1_fixture.py --num-lc "$PROD_LC" \
        --out-dir "$FIXTURE_DIR" > "$BUILD/fixture-generation.command.txt"
    printf '\n' >> "$BUILD/fixture-generation.command.txt"
    if python3 tools/board/generate_stage1_fixture.py --num-lc "$PROD_LC" \
        --out-dir "$FIXTURE_DIR" > "$BUILD/fixture-generation.log" 2>&1; then
        cat "$BUILD/fixture-generation.log"
        sha256sum tools/board/generate_stage1_fixture.py > "$BUILD/fixture-generator.sha256"
        find "$FIXTURE_DIR" -maxdepth 1 -type f -print0 | sort -z | xargs -0 sha256sum > "$BUILD/fixtures.sha256"
        VVP_ARGS=("+fixture_dir=$FIXTURE_DIR")
        run_case dna_stage1_p16_equivalence -DCFG_NUM_LC="$PROD_LC" \
            "$A1/srpe_batch_4way.v" "$A1/srpe_batch_pway.v" \
            "$IPTB/tb_dna_stage1_p16_equivalence.v"
        run_case dna_stage1_p16_interface -DCFG_NUM_LC="$PROD_LC" \
            "$A1/fifo_sync_sdpram_b64.v" "$A1/s2mm_pack64.v" \
            "$A1/srpe_batch_4way.v" "$A1/srpe_batch_pway.v" \
            "$A1/Dna_accelerator_core_v1_0_S_AXI_LITE_CTRL.v" \
            "$A1/Dna_accelerator_core_v1_0.v" "$IPTB/tb_dna_stage1_p16_interface.v"
        VVP_ARGS=()
    else
        cat "$BUILD/fixture-generation.log"
        echo "  ✗ Stage1独立fixture生成失败"; FAIL=$((FAIL+1))
    fi
fi

if [ "$WHICH" = "all" ] || [ "$WHICH" = "core_4way" ]; then
    # 4-way 顶层整核：AXI-Lite + S_AXIS 输入 FIFO + M_AXIS 背压 + 与 2-way 同构对照。
    # NUM_LC 默认 6（玩具配置，跑得快）；生产几何 NUM_LC=50 的黄金比对耗时约 20 分钟，
    # 由 docs/benchmarks/stage1_4way_ip_integration.md §6.3 的命令按需单独跑。
    run_case accelerator_core_4way \
        -DSRPE_BATCH_4WAY_MODNAME=srpe_batch_4way \
        -I "$A1" \
        "$A1/fifo_sync_sdpram_b64.v" "$A1/s2mm_pack64.v" \
        "$A1/srpe_batch.v" "$A1/srpe_batch_4way.v" "$A1/srpe_batch_pway.v" \
        "$A1/Dna_accelerator_core_v1_0_S_AXI_LITE_CTRL.v" \
        "$A1/Dna_accelerator_core_v1_0.v" "$A1/Dna_accelerator_core_4way.v" \
        hw/sim/tb_accelerator_core_4way.v
fi

if [ "$WHICH" = "all" ] || [ "$WHICH" = "ingress" ]; then
    # DNA 顶层 AXIS 入口：10 拍组装 + FIFO 满背压，防止 DMA 数据静默丢失。
    run_case dna_ingress \
        "$A1/Dna_accelerator_core_v1_0.v" \
        "$A1/Dna_accelerator_core_v1_0_S_AXI_LITE_CTRL.v" \
        "$A1/fifo_sync_sdpram_b64.v" "$A1/s2mm_pack64.v" \
        "$A1/srpe_batch_4way.v" "$A1/srpe_batch_pway.v" "$IPTB/tb_dna_ingress.v"
fi

if [ "$WHICH" = "all" ] || [ "$WHICH" = "dna_axil" ]; then
    # DNA AXI-Lite 控制口：AW/W 独立握手与字节写使能。
    run_case dna_axil "$A1/Dna_accelerator_core_v1_0_S_AXI_LITE_CTRL.v" \
                      "$IPTB/tb_dna_axil.v"
fi

if [ "$WHICH" = "all" ] || [ "$WHICH" = "stage2" ]; then
    # Stage2 投票核：4,096 条 Stage1 输出记录（正反两方向，与上位机一致）
    # → 81,000 bit 共识。连跑两轮，第二轮验证累加器重新清零。
    V=hw/ip/differential_voter_1_0/hdl
    run_case differential_voter "$V/differential_voter_v1_0.v" "$IPTB/tb_differential_voter.v"
fi

if [ "$WHICH" = "all" ] || [ "$WHICH" = "host" ]; then
    # PS 侧纯计算逻辑的主机单元测试（与固件共用头文件）
    printf '\n=== wm_expand（PS 侧水印展开，主机单元测试）===\n'
    if gcc -O2 -I sw/app -o "$BUILD/test_wm" tools/test_wm_expand.c 2>&1 \
       && "$BUILD/test_wm" tests/golden/watermark_packed.bin tests/golden/wm_regions.hex \
          | sed 's/^/  /'; then
        PASS=$((PASS+1))
    else
        FAIL=$((FAIL+1))
    fi

    printf '\n=== ddr_layout（C2/C3 按实际条数校验，主机单元测试）===\n'
    if gcc -O2 -Wall -I sw/app -o "$BUILD/test_ddr" tools/test_ddr_layout.c 2>&1 \
       && "$BUILD/test_ddr" | sed 's/^/  /'; then
        PASS=$((PASS+1))
    else
        FAIL=$((FAIL+1))
    fi

    printf '\n=== task_config（P3 协议解析/校验/CRC，主机单元测试）===\n'
    if gcc -O2 -Wall -I sw/app -o "$BUILD/test_tcfg" tools/test_task_config.c 2>&1 \
       && "$BUILD/test_tcfg" | sed 's/^/  /'; then
        PASS=$((PASS+1))
    else
        FAIL=$((FAIL+1))
    fi

    printf '\n=== echo.c（PS 固件：主机侧编译真实源码 + 行为轨迹判据）===\n'
    # 默认编译 **HEAD 里的** sw/app/echo.c，不受其它会话工作树改动影响；
    # 做拆分时用 `bash tests/host/run_host_tests.sh --worktree`。
    if bash tests/host/run_host_tests.sh | sed 's/^/  /'; then
        PASS=$((PASS+1))
    else
        FAIL=$((FAIL+1))
    fi

    printf '\n=== client_core（上位机任务模型/协议/批处理单元测试）===\n'
    if python3 -m unittest discover -s clients/python/tests -p 'test_*.py' \
       | sed 's/^/  /'; then
        PASS=$((PASS+1))
    else
        FAIL=$((FAIL+1))
    fi

    printf '\n=== ldpc_decode（P5 纯 Python 硬判决译码，黄金数据自检）===\n'
    if python3 tools/ldpc_decode.py verify | sed 's/^/  /'; then
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
            echo "  ✓ $label"; PASS=$((PASS+1))
        else
            echo "  ✗ $label"; FAIL=$((FAIL+1))
        fi
    }
    check Dna_accelerator_core \
        "$A1/Dna_accelerator_core_v1_0.v" "$A1/srpe_batch_4way.v" "$A1/srpe_batch_pway.v" \
        "$A1/Dna_accelerator_core_v1_0_S_AXI_LITE_CTRL.v" \
        "$A1/fifo_sync_sdpram_b64.v" "$A1/s2mm_pack64.v"
    check Dna_accelerator_core_P16 -s Dna_accelerator_core_v1_0 \
        -P Dna_accelerator_core_v1_0.C_STAGE1_P_WAYS=16 \
        -P Dna_accelerator_core_v1_0.C_STAGE1_PIPE_TREE=1 \
        "$A1/Dna_accelerator_core_v1_0.v" "$A1/srpe_batch_4way.v" "$A1/srpe_batch_pway.v" \
        "$A1/Dna_accelerator_core_v1_0_S_AXI_LITE_CTRL.v" \
        "$A1/fifo_sync_sdpram_b64.v" "$A1/s2mm_pack64.v"
    if iverilog -g2005 -t null -s Dna_accelerator_core_v1_0 \
        -P Dna_accelerator_core_v1_0.C_STAGE1_P_WAYS=16 \
        -P Dna_accelerator_core_v1_0.C_STAGE1_PIPE_TREE=0 \
        "$A1/Dna_accelerator_core_v1_0.v" "$A1/srpe_batch_4way.v" "$A1/srpe_batch_pway.v" \
        "$A1/Dna_accelerator_core_v1_0_S_AXI_LITE_CTRL.v" \
        "$A1/fifo_sync_sdpram_b64.v" "$A1/s2mm_pack64.v" \
        > "$BUILD/invalid-stage1.compile.log" 2>&1; then
        echo "  ✗ 非法16/0组合未被拒绝"; FAIL=$((FAIL+1))
    else
        echo "  ✓ 非法16/0组合在展开时被拒绝"; PASS=$((PASS+1))
    fi
    check differential_voter        hw/ip/differential_voter_1_0/hdl/differential_voter_v1_0.v
    check desparsification_decoder  "$D/desparsification_decoder_v1_0.v" "$D/desparsify_datapath.v"
fi

printf '\n==================================================\n'
printf '通过 %d 项，失败 %d 项\n' "$PASS" "$FAIL"
printf '==================================================\n'
[ "$FAIL" -eq 0 ]
