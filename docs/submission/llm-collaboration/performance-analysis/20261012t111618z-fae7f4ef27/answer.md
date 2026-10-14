> 脱敏副本，原件 `20261012T111618Z-fae7f4ef27/{prompt.txt,answer.md}`。本机绝对路径、邮箱、凭据形模式及非白名单私网 IP 已替换；除脱敏与换行规范化外保留原文。

## 产出与范围

只读复核结果交付于本答复；**未写入或生成任何项目文件**，未运行综合或 XSim。根目录残留扫描为空。

## A. 源集、参数与覆盖

`component.xml` 的综合与仿真 fileSets 都包含相同的 6 个 Stage1 HDL 文件：`Dna_accelerator_core_v1_0.v`、`Dna_accelerator_core_v1_0_S_AXI_LITE_CTRL.v`、`fifo_sync_sdpram_b64.v`、`s2mm_pack64.v`、`srpe_batch_4way.v`、`srpe_batch_pway.v`。对三个 IP 共 9 个打包 HDL 做集合比较后，`PACKAGED_VARIANTS.txt` **条目集合完全一致**，无缺项或过期项。

按 `hw/scripts/bd.tcl` 中的七项 `CONFIG.*` 核对，XML 用户参数和模型参数默认值一致：`C_STAGE1_P_WAYS=4`、`C_STAGE1_PIPE_TREE=0`、`READ_BPS=150`、`NUM_LC=50`、`STRIDE=807`、`REF_LEN=957`、`BATCH=64`。BD 默认 P4=4/0，显式参数可传入 P16=16/1；生产几何值由 BD 固定设置。`SCORE_W=10` 和 `POS_W=16` 不在这七项 BD 配置中，但顶层在 P4、P16 两个分支都将它们连同 `BATCH`、`NUM_LC`、`STRIDE`、`REF_LEN`、`READ_BPS` 一并传给 batch 核。P4 源文件的旧默认几何不会漏入生产路径。

XGUI 显示 `C_STAGE1_P_WAYS` 和 `C_STAGE1_PIPE_TREE`，校验只接受 4/0 与 16/1。顶层 `Dna_accelerator_core_v1_0` 的 `g_stage1_invalid` 分支以未定义模块 `STAGE1_CONFIGURATION_MUST_BE_P4_OR_P16_PIPELINED` 拒绝非法组合，例如 16/0；这不是静默回退。只读静态参数核对退出码 **0**。此前 Vivado 2022.2 catalog 通过记录见 [Stage1 集成摘要](<<仓库根目录>/docs/benchmarks/stage1-16way-ip-integration.md>)。

`tools/run_sim.sh` 覆盖全部 9 个打包 HDL，**未覆盖文件：无**。Stage1 的 6 个文件都出现在生产接口/语法检查等用例源集中；集合与覆盖静态核对退出码 **0**。两份正式源码名按 `component.xml` 是 `srpe_batch_4way.v` 和 `srpe_batch_pway.v`；前者默认宏展开为模块 `srpe_batch`，后者为 `srpe_batch_pway`。历史 `srpe_batch.v` 同样定义 `srpe_batch`，但未被打包，并由仿真作为 2-way 参考实现使用；因此没有同名模块同时进入综合源集。`Dna_accelerator_core_4way.v` 也未打包，仍由独立仿真用例引用。

### 门禁实际结果

| 命令 | 退出码 | 输出要点 |
|---|---:|---|
| `bash tools/check_ip_packaging.sh` | **1** | 报告无 testbench、打包文件存在、`.v` 无孤儿、各 IP 打包文件均被 `run_sim.sh` 覆盖；但该只读环境不能为 shell here-string 和 Python heredoc 创建临时输入，导致同名模块检查及脚本内 Stage1 Python 检查未完整执行。它还报告 manifest 不一致。 |
| `bash tools/check_repo_hygiene.sh` | **0** | 11 项全部 PASS，包括根目录无残留、工具登记、文档编号、日志忽略、引用检查和重复文件检查。 |
| 独立 `component.xml` / manifest / `run_sim.sh` 集合解析 | **0** | 9 条打包项集合相同；missing、stale、uncovered 均为空。 |
| P4/P16 参数与非法组合静态核对 | **0** | XML 默认、BD 七项配置、XGUI 组合校验、两分支七个 batch 泛型透传和顶层非法组合拒绝均通过。 |
| P16 算法体对比 | **0** | 生产 `srpe_batch_pway.v` 与 P14 实验版本在文档约定的注释及几何默认值归一化后相同。 |
| 根目录残留检查：`find . -maxdepth 1 -type f \( -name '*.log' -o -name '*.jou' -o -name '*.str' -o -name '*.pb' \)` | **0** | 无输出。 |
| 活动代码搜索：`rg -n 'vivado_quick_sim\.tcl' tools hw/scripts hw/boards hw/ip --glob '!hw/ip/Dna_accelerator_core_1_0/hdl/vivado_quick_sim.tcl'` | **1** | 无匹配，表示没有活动调用点。 |

`check_ip_packaging.sh` 的 manifest 报错是**文本顺序差异**，不是条目集合差异：脚本按当前 shell 的组件目录遍历顺序生成比较文本，清单采用另一顺序。当前门禁仍然是 FAIL；建议 main 将生成与比较都规范为全局排序后，再在可正常创建 shell 临时输入的环境运行该门禁。

另有一个卫生缺陷：[vivado_quick_sim.tcl](<<仓库根目录>/hw/ip/Dna_accelerator_core_1_0/hdl/vivado_quick_sim.tcl>) 位于 `hdl/`，不是综合 HDL，且没有活动调用点，只在历史说明中被提及。当前孤儿检查只扫描 `*.v`，因此漏掉了它。建议将它移到 `hw/experimental/` 或归档目录，并同步相关索引；同时扩展打包门禁，检查 `hdl/` 中非 HDL 文件。它不在 `component.xml` 源集中，**不影响当前打包结果或已通过的 Stage1 仿真**。

还有一处文档名称不准：[05 执行计划](<<仓库根目录>/docs/05-implementation-plan.md>) 将 P4 模块写作 `srpe_batch4`；实际打包文件为 `srpe_batch_4way.v`，其默认模块名是 `srpe_batch`。这属于文档标注问题，不是 RTL 源集冲突。

## B. P16 整机资源与时序先验

XC7Z020 资源为 LUT 53,200、FF 106,400、DSP 220、BRAM 4.9 Mb。P14 的 XC7Z020 OOC 结果为 26,867 LUT（50.5%）、25,829 FF（24.3%）、8 个 RAMB36（约 0.29 Mb，约占 4.9 Mb 的 5.9%），WNS +0.705 ns @100 MHz。该 OOC 报告未给出 DSP 计数，不能据此宣称 DSP 为零。

[摸底摘要](<<仓库根目录>/docs/benchmarks/stage1-pway-7020-probe.md>) 用 P4 整机约 15,709 LUT、其中 Stage1 约 8.7k、其余约 7.0k，外推 P16 整机约 **33.9k LUT / 64%**。这可作为当前中心估算。为早期筛选，可用 **33.9k–42.6k LUT（64%–80%）** 做规划预算，42.6k 是保留 20% LUT 余量的工程上限，不是测量值或置信区间；器件硬上限仍是 53.2k。现有证据不足以给出更窄的实测区间。

P14 OOC 使用 `xc7z020clg400-1`，而任务卡中的新板料号是 `XC7Z020-2CLG400I`。资源规模可用于该系列的粗略估算，但速度等级、实际板级约束和整机布线不同，OOC 的 WNS 不能转作新板时序结论。阶段卡中的器件枚举与 IDCODE 也不等于 PS7、DDR、MIO、GEM/PHY 配置已经完成。

P16 最需要优先检查的路径类型：

- `pos_cnt/pos_base` 到 16 路 `pos_valid`，再到每路 64 条记录的匹配和累加使能；`wm_win` 的匹配信号也会扇出到这些记录通道。
- `score[p][t]`、`pos_valid` 到 16 路选优树各级寄存器，再到 `stage1_score`、`stage1_pos` 及跨窗口的全局最优比较。P16 的 `PIPE_TREE=1` 将比较树分为 4 级；P14 OOC 表明流水化后控制扇出和布线仍是重点。
- 末组有效 lane 屏蔽：`pos_valid[p] = pos_cnt + p <= STRIDE`，SE150 的 STRIDE=807 时最终组只有部分 lane 有效；要查看掩码扇出及其进入比较树后的路径。
- 输出侧 `res_full`、结果 FIFO、pack64 和 AXIS `TVALID/TREADY/TLAST` 握手路径，以及位置/区域结果合成路径。

以上全部是 OOC 外推或 RTL 结构分析。**在新板 P4/P16 整机 route 前都属于未测先验，不能当作 100 MHz 时序通过。**

## C. F4/F5 行动清单

**已有 PASS 可沿用，不要重跑长测：**

- Vivado 2022.2 catalog 对默认 P4、显式 P16 和 SE150 参数的记录：`logs/vivado/stage1_ip_catalog_20261010_2110`。
- LC50 独立 oracle 模块及真实 AXI 包装接口：Windows 2026.1 XSim 两个 case 各两轮 PASS；Icarus LC50 模块周期一致。Icarus 接口长测曾在正式 XSim 通过后停止，不能称为 Icarus 接口 PASS。具体边界和 14 文件 source manifest 见 [集成摘要](<<仓库根目录>/docs/benchmarks/stage1-16way-ip-integration.md>)。
- P14 OOC 的 LUT、FF、BRAM、WNS 数据只作为先验；不代替新板完整 route。
- 黄金输入和几何判据已有 `wm_regions.hex` 哨兵，见 `tools/make_golden.py`；不得用最终图像哈希代替几何核验。

**F4/F5 仍须等待新板 profile 和整机实现：**

1. 确认 BKB220 实际 part、PS7/DDR、时钟、UART MIO、PHY/MIO、XDC 和来源表；板卡 JTAG 可枚举不代表 profile 已 ready。
2. F4 先用 WSL Vivado 2022.2 按同一 SE150/100 MHz profile 构建并 route P4，完成约束、DRC、资源及整机 STA 检查，建立新板 P4 制品和 G3 基线。
3. 再以独立目录构建 P16=16/1，核对 XSA/HWH 的实际参数与完整 manifest，并要求 WNS/WHS≥0、TNS/THS=0、失败端点为 0、DRC 和路由合法。必要时按实际端点修复后复验。
4. 同板 P16 全量正确性、连续/恢复、性能以及后续 Windows 2026.1 独立重建仍未测；不得把 3.27 倍模块周期改善外推为整机提速。

## 未完成项

当前 `check_ip_packaging.sh` 的直接调用未能 PASS：除只读临时输入限制外，manifest 比较存在顺序敏感问题。需要 main 在合适环境下修正/规范门禁并复核。`hdl/vivado_quick_sim.tcl` 的退役也未处理。本任务没有新板 profile、完整 route 或真板 G3 证据；这些仍属后续 F4/F5/F6 工作。
