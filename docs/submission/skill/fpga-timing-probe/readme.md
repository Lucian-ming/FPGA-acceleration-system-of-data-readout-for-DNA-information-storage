# 技能包：单模块 OOC 摸底——「装得下吗、跑得到目标频率吗」

> 参赛提交物，不是本仓库的开发规范（见上级 README）。

## 适用场景

在把一个改动做进整机之前，先花十几分钟回答三个问题：

- 这版 RTL **能不能综合**（仿真通过不等于能综合）；
- 它在目标器件上**占多少资源**、还剩多少余量；
- 它在目标频率下**时序收不收敛**，不收敛差多少。

典型用途：加并行度前先摸底、**换器件前评估能放几路**、比较两版微架构、给报告里的
「优化前后资源与性能对比表」取数。

配套脚本：[`ooc_probe.tcl`](ooc_probe.tcl)（Vivado 2022.2 使用；原 OOC 流程有历史验证记录。本轮改了时序失败退出条件，尚未重新运行 Vivado）。

## 使用方法

```bash
RUN_ID="$(date -u +%Y%m%dT%H%M%SZ)-$$"
OOC_TCL=docs/submission/skill/fpga-timing-probe/ooc_probe.tcl
VIVADO=/tools/Xilinx/Vivado/2022.2/bin/vivado
"$VIVADO" -version  # 确认输出是 Vivado v2022.2；其他项目须替换并记录实际版本
mkdir -p "logs/vivado/$RUN_ID"
# 1) BKB220 / XC7Z020：显式指定当前实测器件与 100 MHz，并跑到布线
SYNTH_PART=xc7z020clg400-2 SYNTH_IMPL=1 SYNTH_TAG="$RUN_ID" \
  SYNTH_OUT_ROOT="logs/vivado/$RUN_ID/reports" \
  "$VIVADO" -mode batch -log "logs/vivado/$RUN_ID/vivado.log" \
    -journal "logs/vivado/$RUN_ID/vivado.jou" \
    -source "$OOC_TCL" -tclargs my_top 100 rtl/my_top.v rtl/sub.v

# 2) 换器件 + 覆盖顶层参数 + 跑到布线（推荐，见下「最重要的一条」）
RUN_ID="${RUN_ID}-w16"
mkdir -p "logs/vivado/$RUN_ID"
SYNTH_PART=xc7z020clg400-2 \
SYNTH_GENERICS="WIDTH=16 DEPTH=1024" \
SYNTH_TAG="$RUN_ID" \
SYNTH_OUT_ROOT="logs/vivado/$RUN_ID/reports" \
SYNTH_IMPL=1 \
  "$VIVADO" -mode batch -log "logs/vivado/$RUN_ID/vivado.log" \
    -journal "logs/vivado/$RUN_ID/vivado.jou" \
    -source "$OOC_TCL" -tclargs my_top 100 rtl/my_top.v
```

上述命令从仓库根目录运行；独立复制本技能包时，将 `OOC_TCL` 改为 `./ooc_probe.tcl`，并把 HDL 文件参数改成相对当前目录可访问的路径。

脚本会打印 LUT / FF / BRAM / DSP 占用与 setup/hold slack，并把完整报告写进 `${SYNTH_OUT_ROOT:-build}/synth_<top>_<tag>/`；Vivado `.log` / `.jou` 放进每次独立的 `logs/vivado/<run-id>/`。
`SYNTH_TAG` 不同的多次摸底不会互相覆盖，适合一次跑多个参数点做对比表。

**最重要的一条：只综合的 WNS 不能用来下结论，必须跑到布线（`SYNTH_IMPL=1`）。**
综合阶段的时序是基于估算布线延迟的，通常乐观得多；
布线后的数字才和整机接近。做决策（买不买板、做几路）时只看布线后的。

判读建议：

| 看什么 | 怎么判 |
| --- | --- |
| 资源占用 | 留出整机其它模块的余量再判断。单模块 50% 不代表整机装得下 |
| WNS ≥ 0 且 WHS ≥ 0 | 在这个频率下 setup/hold 收敛。余量很小（< 0.2 ns）时整机仍可能更紧 |
| WNS < 0 | 脚本会按 `1000/(周期 − WNS)` 给出估算的最高频率 |
| 关键路径 | 打开 `timing.rpt` 看 `Logic Levels` 与 `Source/Destination`：逻辑级数多 = 该切流水；扇出大 = 该寄存或复制 |

**会红的判据**：使用 `SYNTH_IMPL=1` 时必须找得到受约束时钟路径，且布线后 WNS/WHS 都不小于 0；否则脚本以非零状态退出。综合-only 的时序只是探索结果，不用于接受目标频率。只有 `SYNTH_IMPL=1` 下 exit 0 才表示该模块在给定 OOC 约束下过了时序判据，不表示整机、I/O 或板端通过；综合-only exit 0 只表示脚本跑完。

资源数字目前只报告，不设跨项目通用的 LUT/FF 上限。若要用它做“装得下”的接受判据，必须先给当前整机留出其它模块所需余量并写下预算，再将 `util.rpt` 与预算比较；不能把“Vivado 能综合”或 OOC 资源未超器件总量当成整机可装下。

## 失效条件

- **OOC 没有 IO 约束、没有整机互连**，所以它的 WNS 仍然比整机乐观一点，只是差距小得多。
  整机是否收敛必须由整机实现回答。
- 模块端口数很多时，不加 `SYNTH_IMPL=1`（即不走 out_of_context 模式）会因 IO 数超限而无法布局。
- 资源数字会随综合策略、`-flatten_hierarchy` 设置变化；**跨配置比较时必须固定同一套设置**。
- BRAM / DSP 的推断结果依赖编码风格，改了 `ram_style` 之类属性要重新摸底。

## 已验证效果

本项目 2026-09-22 用它做旧板 XC7Z010 → XC7Z020 的迁移决策，一次拿到全部数据（历史 OOC 数据，不等同于当前 BKB220 整机实现）：

| 器件 | 配置 | LUT | 布线后 WNS @100 MHz |
| --- | --- | ---: | ---: |
| XC7Z010 | 4 路（校准用，整机已实测 +0.167 ns） | 8,067（45.8%） | **+0.145 ns** |
| XC7Z020 | 8 路（组合选优树） | 15,666 | −3.058 ns |
| XC7Z020 | 16 路（组合选优树） | 30,747 | −10.220 ns |
| XC7Z020 | 32 路 | 63,040 | **放不下**，布局前被 DRC 拒绝 |
| XC7Z020 | 8 路 + 选优树逐级打拍 | 14,432 | **+0.640 ns** |
| XC7Z020 | 16 路 + 选优树逐级打拍 | 26,867 | **+0.705 ns** |

三点收获：

1. **校准可信**：同一模块在原器件上 OOC 布线后 +0.145 ns，整机实测 +0.167 ns，两者接近；
   而同一模块**只综合**的历史数字是 +2.197 ns——差了一个数量级，说明只综合的数不能用；
2. `timing.rpt` 指出关键路径是「一个比较结果扇出 168 → 3 级比较树」，据此把树逐级打拍，
   **时序从 −3.058 ns 变成 +0.640 ns，LUT 反而从 15,666 降到 14,432**；
3. 32 路在布局前就被资源 DRC 拒绝，**十几分钟就排除了一个方向**，不必等整机实现。

### BKB220 当前整机结果

2026-10-12 使用 WSL Vivado 2022.2，在真实 `xc7z020clg400-2` 完成完整 route：

| 配置 | LUT | WNS / WHS @100 MHz | 失败端点 |
| --- | ---: | ---: | ---: |
| P4（4/0） | 15,447（29.04%） | +0.680 / +0.036 ns | 0 |
| P16（16/1） | 33,987（63.89%） | +0.617 / +0.017 ns | 0 |

这里的 **P16 整机 LUT 与时序**和上面旧 OOC 表的模块数字不是同一阶段、同一器件 profile 或同一测量边界；不得互换。详细约束、DRC 与警告见 `docs/benchmarks/bkb220-p4-p16-100mhz-build.md`。该构建结果只证明静态实现，不证明板端功能或速度。

## 来源

来自一次差点做错的决策：文档里长期引用某模块「WNS +2.197 ns，时序很宽裕」，
而那是**单模块只综合**的结果；同一设计整机布线后是 −0.252 ns，根本不收敛。
后来定下规矩：**跨阶段的时序数字不可混用，做决策只认布线后**，并把这条写进脚本注释里，
免得下一个人再拿综合数去拍板。
