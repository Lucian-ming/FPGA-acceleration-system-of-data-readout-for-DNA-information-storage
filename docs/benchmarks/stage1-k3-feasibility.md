# Stage1 K=3 可行性探针

日期：2026-10-14（Asia/Shanghai）

## 结论

**K=3 当前实现不适合继续进入整机集成。** OOC 单模块在 XC7Z020 资源容量内完成布局布线，但 100 MHz setup 严重不收敛：WNS −15.244 ns、TNS −45,753.648 ns、16,115 个 setup 失败端点。否决项是**时序**；资源容量不是本次 OOC 的否决项，6-bit 跨字节也没有破坏当前位平面契约。

K=3 的每块拍数由既有公式计算为 `1 + 18 + ceil(150/3) + 5 + 1 + 1 = 76`，比 K=2 的 101 拍少 25 拍（静态减少约 24.8%）。但当前实现的时序余量不是略低于门槛，而是大幅为负；这次探针不支持把 K=3 当作可用提速方案。若后续重写水印 bank 地址路径，应重新做 OOC 探针后再决定是否投入整机。

## OOC 布线后对照

| K | 每块拍数 | LUT | FF | RAMB36 | RAMB18 | DSP | WNS (ns) | WHS (ns) | TNS / THS (ns) | setup / hold 失败端点 | 100 MHz |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|
| 2 | 101 | 28,708 | 26,509 | 12 | 0 | 4 | +0.300 | +0.078 | 0 / 0 | 0 / 0 | 收敛 |
| **3** | **76** | **28,429** | **26,559** | **15** | **0** | **9** | **−15.244** | **+0.078** | **−45,753.648 / 0** | **16,115 / 0** | **不收敛** |
| 4 | 64 | 41,342 | 26,499 | 20 | 0 | 7 | +0.185 | +0.084 | 0 / 0 | 0 / 0 | 收敛 |

K=3 资源占比为 LUT 53.44%、FF 24.96%、RAMB36 10.71%、DSP 4.09%。布局和布线均完成，未布通网络为 0。K=2 / K=4 的数字来自 [Stage1 多碱基 OOC 探针记录](stage1-multibase-ooc-probe.md) §「配置结果」；K=3 原始数据见[利用率报告](../../logs/vivado/k3-probe/reports/synth_srpe_batch_pway_K3/util.rpt)和[时序报告](../../logs/vivado/k3-probe/reports/synth_srpe_batch_pway_K3/timing.rpt)。

最差 setup 路径从 `lc_idx_reg[1]_replica_1` 到 `gen_wm_bank[2].wm_rd_addr_q_reg[2][8]`，总数据延迟 25.245 ns，其中逻辑 13.409 ns、布线 11.836 ns；路径含 19 个 CARRY4 和 2 个 DSP48E1，经过 `wm_rd_addr_lin` 与水印 bank 读地址组合逻辑。它与 K=3 的除/余数地址生成相符，但本次没有单独替换该逻辑来隔离因果。详见原始 [timing.rpt](../../logs/vivado/k3-probe/reports/synth_srpe_batch_pway_K3/timing.rpt)。

**⚠️ main 补记（同日，推理不是实验）**：上面那句「与除/余数地址生成相符」可以再具体一步——
`srpe_batch_pway.v` 的地址路径是**运行期除法**：

```verilog
wire [31:0] wm_wr_addr_wide = wm_wr_addr_lin / BASES_PER_CYCLE;   // 写地址
a_lo_bank_q <= lo_mem[a_addr / BASES_PER_CYCLE];                  // 读地址
```

K=2 / K=4 时 `BASES_PER_CYCLE` 是 2 的幂，综合器把它变成**移位**（免费）；
**K=3 时它变成一次真正的除以 3**——19 个 CARRY4 + 2 个 DSP48E1 正是它的形状。
⇒ **这解释了为什么 K=3 的 WNS 不是从 K=2 的 +0.300 与 K=4 的 +0.185 之间插值出
一个温和的数（按插值应在 +0.24 附近），而是一个结构性断崖：K=3 打破了 bank 地址
对「2 的幂」的隐含依赖。**

**这条是推理，没有做隔离实验**（没有单独把那一处除法换成流水化实现再综合）。
若将来要救 K=3，第一步就是先把 bank 地址生成改成不依赖 K 为 2 的幂
（例如把除法拆到独立流水级，或换成不按 K 分 bank 的方案），**重做 OOC 探针再议**。

## 位对齐与 bank 深度

`docs/02-data-contract.md` 的传输格式是两平面布局：高位平面 150 bit、低位平面 150 bit，PC→板每字节 LSB-first。`srpe_batch_pway` 的 `S_LOAD` 将 `cw_data[149:0]` 和 `cw_data[299:150]` 分别移入两个平面存储，再按碱基序号写入。K 是内部每拍比较多少个碱基，不是传输总线按 6-bit 分组。

几何也整除：

- `PLANE_BANK_DEPTH=ceil(150/3)=50`，3 个 bank 正好覆盖 150 个碱基。
- `WM_DEPTH=NUM_LC×REF_LEN=50×957=47,850`，`WM_BANK_DEPTH=ceil(47,850/3)=15,950`，同样整除。
- `REF_LEN=957` 是 3 的倍数，每个 LC 的水印起点都落在 bank 0；`READ_BPS=150`、`STRIDE=807` 也为 3 的倍数。`RUN_GROUPS=50`，没有末尾不足 3 碱基的残组。候选地址按绝对地址取模选 bank，不要求候选起点都落在同一 bank。

因此，“K=3 是 6 bit、跨字节”不会单独破坏现行数据契约，也没有发现需要额外搬运/重打包的理由。这是**静态结构分析**，不是功能证明。

## 证据边界

本结果是 `srpe_batch_pway` **OOC 单模块**综合、布局与布线，**不是整机结果，也不是板测**。OOC 正 slack 不等于整机余量；本项目有同模块 OOC +0.444 ns、整机约 +0.31～+0.33 ns 的实测案例，见[固定开销探针计划](stage1-block-overhead-plan.md)及其引用的整机记录。

探针只给 `clk` 设置 100 MHz 时钟，没有设置输入/输出 delay；但最差路径是模块内部寄存器到寄存器。**未运行功能仿真、未做整机综合/实现、未触板**，因此没有证明 K=3 的逐位功能等价，也没有证明它能被整机容纳或在板上正确工作。

详细运行配置、资源/端点数字、完整 Vivado 日志和复现命令见 [运行报告](../../logs/vivado/k3-probe/report.md)。完整原始日志在 `logs/vivado/k3-probe/K3/vivado.log` 与 `vivado.jou`。

