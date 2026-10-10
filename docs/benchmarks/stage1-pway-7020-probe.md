# Stage1 参数化 P 路引擎与 XC7Z020 迁移摸底（2026-09-22）

> **结论**：16 路 Stage1 在 XC7Z020 上 OOC 布线后 **26,867 LUT（50.5%）、WNS +0.705 ns @100 MHz**，
> 生产几何仿真与生产 4-way **逐位一致**、与黄金模型吻合，比对周期 **3.30x**。
> 32 路放不下（63,040 LUT > 53,200）。**未上板，整机与端到端数字均为估算。**
>
> 前提来自 [docs/03](../archive/history/2026/pre-bkb220-handoff-2026-10-10/status.md) P13：P12 之后板端每记录成本（0.2451 ms）
> 与 4-way Stage1 理论周期（0.2436 ms）相差 0.6%，Stage1 是唯一的主要瓶颈。

## 1. 被测对象

- RTL：`hw/experimental/srpe_batch_pway.v`（未打包，不进任何 `component.xml`），
  由生产 `srpe_batch_4way.v` 机械推广：`P_WAYS` 参数化；选优树改为 generate 生成的二叉树
  （「左 >= 右取左」，并列取低序号，语义与 4-way 相同）；`pos_valid` 改在 `S_LAUNCH` 寄存；
  `PIPE_TREE=1` 时选优树逐级打拍，`S_UPD1` 多等 log2(P) 拍。
- TB：`hw/sim/tb_srpe_batch_pway.v`，与生产 4-way 同时例化、同输入，逐位比对 score/pos/cw，
  P=4 且 `PIPE_TREE=0` 时额外要求周期数相同；NUM_LC=50 时再比 `tests/golden/stage1_fwd_expect.txt`。
- 回归入口：`bash tools/run_sim.sh stage1_pway`（NUM_LC=6，P=4 逐周期 + P=16 流水逐位）。

## 2. 功能与周期（iverilog，生产几何 NUM_LC=50，一批 64 条读段）

| 配置 | 周期 | 相对生产 4-way | 与 4-way 逐位 | 黄金模型 |
|---|---:|---:|---|---|
| 生产 4-way | 1,674,009 | 1.00x | — | PASS（并列 2/64） |
| P=4，组合树 | 1,674,009 | 1.00x（逐周期相同） | 一致 | PASS |
| P=8，组合树 | 886,209 | 1.89x | 一致 | PASS |
| P=16，组合树 | 496,609 | 3.37x | 一致 | PASS |
| **P=8，流水树** | **901,359** | **1.86x** | 一致 | PASS |
| **P=16，流水树** | **506,809** | **3.30x** | 一致 | PASS |

流水树的代价：每组位置多 log2(P) 拍，P=16 比组合树多 2.1% 周期。

## 3. 资源与时序（Vivado 2022.2，OOC 综合 + place/phys_opt/route，100 MHz）

复现（以 16 路为例；日志在 `logs/vivado/pway_probe_20260922/`，报告在 `hw/build/synth_srpe_batch_pway_<tag>/`）：

```bash
SYNTH_PART=xc7z020clg400-1 SYNTH_IMPL=1 SYNTH_TAG=z020_p16_pipe \
SYNTH_GENERICS="P_WAYS=16 PIPE_TREE=1 READ_BPS=150 REF_LEN=957 STRIDE=807 NUM_LC=50" \
  vivado -mode batch -source hw/scripts/synth_check.tcl -tclargs \
    srpe_batch_pway 100 hw/experimental/srpe_batch_pway.v
```

| 器件 | 配置 | Slice LUT | FF | RAMB36 | 布线后 WNS |
|---|---|---:|---:|---:|---:|
| XC7Z010 | P=4 组合树（校准） | 8,067（45.8%） | 6,592 | 8 | **+0.145 ns** |
| XC7Z020 | P=8 组合树 | 15,666（29.5%） | 9,293 | 8 | −3.058 ns |
| XC7Z020 | P=16 组合树 | 30,747（57.8%） | 15,307 | 8 | −10.220 ns |
| XC7Z020 | P=32 组合树 | 63,040（118%） | — | — | **放不下**（place 前 DRC 拒绝） |
| XC7Z020 | **P=8 流水树** | **14,432（27.1%）** | 15,256 | 8 | **+0.640 ns** |
| XC7Z020 | **P=16 流水树** | **26,867（50.5%）** | 25,829 | 8 | **+0.705 ns** |

- **校准**：P=4 在 7010 上 OOC 布线后 +0.145 ns，整机实测为 +0.167 ns，二者接近；
  只综合不布线的 WNS（历史 +2.197 ns）不能用于判断。
- 组合树的关键路径为 `pos_base → pos_valid 比较（扇出 168）→ 3 级比较树 → stage1_pos`，15 级逻辑、13 ns；
  改为寄存 `pos_valid` 与逐级流水后，关键路径只剩 1 级 LUT（控制扇出布线主导）。
- BRAM 恒为 8 块，与路数无关。

## 4. 估算（未上板，不得写成实测）

- **整机 LUT**：当前整机 15,709 LUT 中 4-way Stage1 约 8.7k，其余约 7.0k；
  换 16 路后约 33.9k / 53,200 ≈ **64%**。整机时序须重新实现确认。
- **端到端**：按 P13 板端斜率 0.2451 ms/记录（含 Voter 约 0.006），Stage1 部分按周期比 1/3.30 缩放：
  `0.239/3.30 + 0.006 ≈ 0.079 ms/记录`，SE150 全量 ≈ `0.48 + 103,616 × 0.079 ms ≈ 8.6 s`，
  约 **6,000 reads/s**：单核 CPU 1,364.9 的约 4.4x；16 线程 14,003.1 仍快约 2.3x。
- 到那时 Voter 与固定开销的占比会升高，是下一轮要复测的对象。

## 5. 迁移还缺什么

1. 选定 7020 板卡（优先与 ECO 同厂同 PCB 的 7020 版，PS7/DDR/MIO/PHY 差异最小）；
2. 按新板重建 BD、XDC、PS7 配置，重新生成 XSA/FSBL/ELF/BOOT.bin；
3. 把 `srpe_batch_pway`（P=16，流水树）接进 `Dna_accelerator_core` 并更新 `component.xml`
   与 `hw/ip/PACKAGED_VARIANTS.txt`，整机实现确认 100 MHz；
4. 上板 G3 全量，复测斜率。
