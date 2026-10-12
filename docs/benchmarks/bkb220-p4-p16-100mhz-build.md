# BKB220 新板 P4 / P16 整机 100 MHz 构建与时序（2026-10-12）

本轮回答本次迁移最大的技术未知：**P4 与 P16 能否在真实 `xc7z020clg400-2` 上完成完整 route 并收敛 100 MHz。**

结论：**两者都完成完整 route，setup/hold 均满足，失败端点 0。** 但这是**构建与静态时序**结论 —— **不含**板端下载、功能、G3 或性能验证。

## 1. 实际命令与产物

两次都用 WSL Vivado 2022.2，各自独立的 build/export/report 目录，退出码均 **0**。

```bash
VIVADO_ROOT=/tools/Xilinx/Vivado/2022.2 bash tools/run_vivado_build.sh \
  board=bkb220 part_name=xc7z020clg400-2 clk_mhz=100 \
  stage1_p_ways=<4|16> stage1_pipe_tree=<0|1> \
  build_dir=<独立> export_dir=<独立> report_dir=<独立>
```

| | P4（4/0） | P16（16/1） |
|---|---|---|
| build/export/report | `hw/build/bkb220-p4-100mhz-20261012T123158Z-board-migrate-p4/` | `hw/build/bkb220-p16-100mhz-20261012T123936Z-board-migrate-p16/` |
| Vivado 日志 | `logs/vivado/20261012T123158Z-342/vivado.log` | `logs/vivado/20261012T123936Z-342/vivado.log` |
| 产物 | `top_bd_wrapper.bit`、`dna_accel.xsa`（`PART="xc7z020clg400-2"`）、`hardware_build_config.txt` | 同左 |
| 归档摘要 | `<...>/reports/run_summary.md` | `<...>/reports/run_summary.md` |

> 上面这些目录在 `.gitignore` 里（`hw/build/bkb220-p4-*/`、`bkb220-p16-*/`）：它们是可重建的大生成物，
> **只把本文件的判据与结论入库**，工程目录本身不入库也不自动删除。

## 2. 时序判据（main 从原始报告独立复核，非转述子 Agent 摘要）

来源：`<P4|P16>/reports/timing.rpt`，`Design State : Physopt postRoute`，`Device : xc7z020clg400-2`，`Speed File : -2`。

| 判据 | P4 | P16 |
|---|---:|---:|
| **WNS / TNS** | **+0.680 ns / 0.000** | **+0.617 ns / 0.000** |
| **WHS / THS** | **+0.036 ns / 0.000** | **+0.017 ns / 0.000** |
| **Setup 失败端点** | **0 / 51,506** | **0 / 86,415** |
| **Hold 失败端点** | **0 / 51,506** | **0 / 86,415** |
| WPWS / TPWS 失败端点 | 3.000 ns / 0 | 3.000 ns / 0 |
| 时钟 | `clk_fpga_0` 10.000 ns = **100.000 MHz** | 同左 |
| `check_timing` | no_clock / unconstrained / 缺 I-O delay 均 0 | 同左 |
| 结论行 | `All user specified timing constraints are met.` | 同左 |

**最差 setup 路径（均为正 slack、非失败端点）**：
- P4：`desparsification_dec` → `differential_voter`，`Slack (MET) 0.680 ns`。
- P16：Stage1 `g_stage1_pway.u_srpe/pos_valid_reg[8]` → 选优树 `gen_tree[30].gen_node[13].gen_q.s_q_reg[3]`，`Slack (MET) 0.617 ns`。
  → **与 rtl-16way 事先点名的"末组 `pos_valid` 扇出到选优树"路径类型一致**；先验判断被实测印证。

## 3. 资源

| 资源 | P4 | P16 | P16−P4 |
|---|---:|---:|---:|
| LUT | 15,447 / 53,200（**29.04 %**） | 33,987 / 53,200（**63.89 %**） | +18,540 |
| FF | 16,910 / 106,400（15.89 %） | 36,067 / 106,400（33.90 %） | +19,157 |
| BRAM tile | 45 / 140（32.14 %） | 45 / 140（32.14 %） | 0 |
| DSP | 3 / 220（1.36 %） | 3 / 220（1.36 %） | 0 |

- **P16 = 33,987 LUT（63.89 %）**，与 rtl-16way 的整机先验「约 33.9k LUT / 64 %」相差 87 LUT。旧板 XC7Z010 只有 17,600 LUT，这也是 P16 在旧板不可能、在 7Z020 可行的直接原因。
- P4 整机 15,447 LUT 也接近该先验（15,709）。

## 4. 路由与 DRC

| | P4 | P16 |
|---|---|---|
| 可布线 net | 26,731 / 26,731 完成 | 49,404 / 49,404 完成 |
| Routing errors | **0** | **0** |
| DRC（`drc_routed.rpt`） | **0 errors**，58 warnings，3 advisories | **0 errors**，75 warnings，3 advisories |

**未清理的 warnings（如实记录，属待 RTL 复核项，不是时序失败）**：
- **各 20 项 `REQP-1839` / `REQP-1840`**（两个设计都有）：BRAM 的异步复位控制。报告提示复位期间可能影响存储内容，**且默认 STA 不分析该风险**。
- P16 另有 **16 项 `DPOR-1`**：异步复位限制了 DSP 输出寄存器的映射。
- P16 有 `RTSTAT-10` no-routable-load 警告；但 route status 的 routing errors 为 0。

> 这些是**警告与建议**，不改变上面的时序判据；但按项目纪律不能只因为"时序过了"就忽略。
> 尤其是 `REQP-1839/1840` 指向**复位期间 BRAM 内容**，而本项目的关键判据之一正是「脏轮→干净轮」的状态复位 ——
> 应在 F6 的状态复位板测里**专门盯这一点**，必要时由 rtl-16way 复审。

## 5. 结论边界（不得外推）

- **可以说**：P4/P16 在 `xc7z020clg400-2` 上完成整机综合、实现、完整 route、bitstream 与 XSA 导出，100 MHz 下 setup/hold 全通过、失败端点 0、DRC 0 errors；P16 资源 33,987 LUT。
- **不能说**：板端下载/启动通过、功能正确、G3 通过、性能提升"N 倍"。模块周期 3.27 倍与这里的 LUT 数字都**不是整机加速比**。
- **仍未证**：ENET0 之外 —— 工业级精确料号、DDR 板级延迟与 DQS-to-CLK（用 Vivado `Custom` 默认值）；QSPI/SD 冷启动。
- 本轮**未触板**；仅构建与静态时序。同 XSA 的软件包（BSP/应用/FSBL/BOOT/readback/manifest）尚未生成。
