# Stage1 每拍多碱基 OOC 探针

日期：2026-10-13（Asia/Shanghai）  
目标：`srpe_batch_pway`，XC7Z020 `xc7z020clg400-2`，100 MHz，Vivado 2022.2，`SYNTH_IMPL=1`（OOC 综合、布局、物理优化与布线）。K=1 运行目录：`logs/vivado/20261013T1834CST_stage1_multibase/`；最终扁平水印 bank 地址 RTL 的 K=2/K=4 运行目录：`logs/vivado/20261013T1900CST_stage1_multibase_flataddr/`。

## 结论

K=1 对照通过：布线后 27,522 LUT、25,872 FF、8 RAMB36；相对已知 26,867 LUT / 25,829 FF / 8 RAMB36 基线，LUT 增加 655（+2.44%）、FF 增加 43（+0.17%），远低于 20% 停止线，因此继续完成 K=2/K=4。

**K=4 的 OOC 单模块资源可装入 XC7Z020：** 41,342/53,200 LUT（77.71%）、26,499/106,400 FF（24.91%）、20/140 RAMB36、0 RAMB18、7/220 DSP。**该 OOC 单模块在 100 MHz 收敛：** route 后 WNS +0.185 ns、WHS +0.084 ns、TNS/THS 均为 0，setup/hold 失败端点均为 0。LUT 余量约 11,858（22.29%）；setup 余量只有 0.185 ns。OOC 结果不能证明替换进整机后仍装得下或收敛，整机集成与布线尚未测试。

本报告中的资源和时序均为 **OOC 单模块数据，不是整机、不是板测**。本探针不验证功能正确性，未运行仿真、未触板。K=1 的结构保持单 lane、单 bank 与原读写/窗口推进节拍一致，但本任务没有做功能等价仿真证明。

`ooc_probe.tcl` 只给 `clk` 建 100 MHz 时钟，未给顶层输入/输出端口设置 delay；因此表中的 WNS/WHS 是该 OOC 约束下的模块内部时序结果，不能代替整机接口约束、时钟树与布线后的 signoff。

## 配置结果

每块拍数来自静态推导 `1 + 18 + ceil(150/K) + 5 + 1 + 1`；18 拍预充填未优化。除拍数以外，表中资源、时序与端点数字均来自对应 Vivado `util.rpt` / `timing.rpt`。

| K | 每块拍数 | LUT | FF | RAMB36 | RAMB18 | DSP | WNS ns | WHS ns | TNS ns | THS ns | setup/hold 失败端点 | OOC 100 MHz |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|
| 1 | 176 | 27,522 | 25,872 | 8 | 0 | 3 | +0.735 | +0.069 | 0.000 | 0.000 | 0 / 0 | 收敛 |
| 2 | 101 | 28,708 | 26,509 | 12 | 0 | 4 | +0.300 | +0.078 | 0.000 | 0.000 | 0 / 0 | 收敛 |
| 4 | 64 | 41,342 | 26,499 | 20 | 0 | 7 | +0.185 | +0.084 | 0.000 | 0.000 | 0 / 0 | 收敛 |

K=1 已知对照：约 26,867 LUT、25,829 FF、8 RAMB36，来源为 [`stage1-pway-7020-probe.md`](stage1-pway-7020-probe.md) §3 及本任务指定门槛。新测 K=1 报告：[`util.rpt`](../../logs/vivado/20261013T1834CST_stage1_multibase/reports/K1/synth_srpe_batch_pway_K1/util.rpt)、[`timing.rpt`](../../logs/vivado/20261013T1834CST_stage1_multibase/reports/K1/synth_srpe_batch_pway_K1/timing.rpt)。

K=1 跑在水印 bank 地址改为扁平余数之前；最终 K=1 仍只有 bank 0，扁平写地址、读地址和单 bank 深度与该次 elaboration 完全相同。K=2/K=4 已在最终扁平 bank 地址 RTL 上重跑，且下列链接指向这两次报告。

K=2 原始报告（最终扁平 bank 地址 RTL）：[`util.rpt`](../../logs/vivado/20261013T1900CST_stage1_multibase_flataddr/reports/K2/synth_srpe_batch_pway_K2/util.rpt)、[`timing.rpt`](../../logs/vivado/20261013T1900CST_stage1_multibase_flataddr/reports/K2/synth_srpe_batch_pway_K2/timing.rpt)。  
K=4 原始报告（最终扁平 bank 地址 RTL）：[`util.rpt`](../../logs/vivado/20261013T1900CST_stage1_multibase_flataddr/reports/K4/synth_srpe_batch_pway_K4/util.rpt)、[`timing.rpt`](../../logs/vivado/20261013T1900CST_stage1_multibase_flataddr/reports/K4/synth_srpe_batch_pway_K4/timing.rpt)。

## 复现入口

三档均使用 `docs/submission/skill/fpga-timing-probe/ooc_probe.tcl`，part=`xc7z020clg400-2`、100 MHz、`SYNTH_IMPL=1`。每档 tag 分别为 `K1` / `K2` / `K4`。K1 报告根目录为 `logs/vivado/20261013T1834CST_stage1_multibase/reports/K1/`；最终 RTL 的 K2/K4 报告根目录分别为 `logs/vivado/20261013T1900CST_stage1_multibase_flataddr/reports/K2/` 与 `.../reports/K4/`；Vivado log/journal 在各自同名档位子目录。

通用命令模板（将 `K` 替换为 1、2、4；`SYNTH_GENERICS` 其余参数保持不变）。复跑时把 `RUN_ROOT` 改成新的唯一目录，避免覆盖已留存的报告：

```bash
K=4
RUN_ROOT=logs/vivado/20261013T1900CST_stage1_multibase_flataddr
mkdir -p ${RUN_ROOT}/reports/K${K} ${RUN_ROOT}/K${K}
SYNTH_PART=xc7z020clg400-2 SYNTH_IMPL=1 \
SYNTH_GENERICS="P_WAYS=16 PIPE_TREE=1 BASES_PER_CYCLE=${K} READ_BPS=150 REF_LEN=957 STRIDE=807 NUM_LC=50 BATCH=64" \
SYNTH_TAG=K${K} SYNTH_OUT_ROOT=${RUN_ROOT}/reports/K${K} \
/tools/Xilinx/Vivado/2022.2/bin/vivado -mode batch \
  -log ${RUN_ROOT}/K${K}/vivado.log \
  -journal ${RUN_ROOT}/K${K}/vivado.jou \
  -source docs/submission/skill/fpga-timing-probe/ooc_probe.tcl \
  -tclargs srpe_batch_pway 100 hw/ip/Dna_accelerator_core_1_0/hdl/srpe_batch_pway.v
```

## RTL 结构与简化

- 读段位平面按 `READ_BPS` 局部地址的 `addr mod K` 分 bank，bank 内地址为 `addr / K`；每 bank 有自己的同步读口，Port B 仍对写地址对应 bank 做读改写，没有复制整块位平面。
- 水印按原扁平地址 `lc_idx*REF_LEN+offset` 的余数分 bank，每 bank 一个读口；写口用 `bram_sel*REF_LEN+bram_write_addr` 的余数选 bank，bank 内地址为扁平地址除以 K。K=1 时与单 bank 原布局一致。越过 LC 末端的 lane 钳到该 LC 最后一个有效符号。
- 匹配窗口宽度为 `P_WAYS+K-1`；每个候选位置计算 K 路 64-bit 比较，每拍右移 K 位并追加 K 个水印符号。`score_inc` 对 `READ_BPS=150` 最后一组不足 K 个碱基的 lane 屏蔽，K=4 时尾组只计 2 lane。
- `S_RUN` 运行组数为 `ceil(READ_BPS/K)`；`S_PREFILL` 仍为 18 拍，未作为本探针变量优化。
- 本次只探测 RTL 单模块，不更新 IP 打包、整机封装、约束、固件或板端制品；无功能仿真，因此 K 路读数/水印对齐和得分功能仍需后续独立回归确认。

---

## 复现与见证（2026-10-13 追加）

**被测 RTL 的 SHA-256**：`f2400a5533bd424afde98627634554fdd0190d5c9a733097c1d8b6b60f3fdbfb`（`hw/ip/Dna_accelerator_core_1_0/hdl/srpe_batch_pway.v`）。

**为什么补这一段**：子 Agent 在跑完 K=2/K=4 之后又动过一次该文件（19:12:47），
而那次改动**晚于**所有报告的时间戳（K=2 于 19:04、K=4 于 19:09）。报告里没有钉住 RTL 的哈希，
所以「报告对应的就是现在这份文件」这件事**当时无法证明**。

**见证复跑**：对**冻结后的当前文件**重跑 K=2（同一 `ooc_probe.tcl`、`SYNTH_IMPL=1`、100 MHz、
同一组 `SYNTH_GENERICS`），结果与报告的 flataddr 一档**逐项相同**：

| | LUT | FF | RAMB36 | DSP | WNS | WHS | 失败端点 |
|---|---:|---:|---:|---:|---:|---:|---:|
| flataddr 记录 | 28,708 | 26,509 | 12 | 4 | +0.300 | +0.078 | 0 / 0 |
| 见证复跑 | 28,708 | 26,509 | 12 | 4 | +0.300 | +0.078 | 0 / 0 |

→ 19:12 那次改动**没有实质影响**（综合/实现结果等价），本文第三节的表**成立**。
见证留证：`logs/vivado/verifyk2-*/reports/`（`logs/` 不入库，文件保留）。

---

## ⚠️ 整机对照：**两次构建都作废**（2026-10-13 深夜，K=2/K=4 决策时发现）

本节记录一个**必须先修掉才能谈 K 选型的工具链缺陷**，以及它作废了哪些结论。

### 现象

为回答「K 取 2 还是 4」，用 `tools/run_vivado_build.sh` 对同一份 RTL
（`srpe_batch_pway.v` SHA `f2400a55…`）跑了**两次整机 route**，只差
`stage1_bases_per_cycle=2 / =4`：

| 构建 | `hardware_build_config.txt` | 整机 LUT | Stage1 实例 LUT | WNS | 失败端点 | DRC |
|---|---|---:|---:|---:|---:|---:|
| K=2 | `C_STAGE1_BASES_PER_CYCLE=4`… 见下 | 35,285 | **28,103** | +0.978 | 0 | 0 |
| K=4 | `C_STAGE1_BASES_PER_CYCLE=4` | 35,285 | **28,103** | +0.978 | 0 | 0 |

**两次逐字节相同**（LUT/FF/BRAM/DSP/WNS 全部一致到小数第三位），而且用的是**同一个 IP HDL**
（`f2400a5533bd`）。**两个不同的 K 不可能综合出一模一样的网表。**

### 判定：**参数根本没进到被综合的 HDL，两次整机实际都是 K=1**

证据链：

1. 原始 P16 整机（main，尚无 K 参数）的 Stage1 实例是 **26,809 LUT**；
   两次新构建都是 **28,103**，增量 **+1,294**，与整机增量 +1,298 基本相等。
2. 该增量与 **K=1 OOC 相对基线的高出量（+655）方向一致**——都是**参数化本身的银行化机制开销**，
   不是 K>1 的收益。
3. RTL 里 `BASES_PER_CYCLE` 的默认值是 **1**。参数没传进去 ⇒ 用默认值 ⇒ 两次都是 K=1。

**`bd.tcl` 里"设完 CONFIG 再 `get_property` 读回比对"那道校验通过了（读回 4）——
它只证明了「IP 对象上存的值是 4」，没有证明「这个值被传进了 RTL」。** 这两件事必须分开看，
是本轮的一条方法教训。

### 因此作废的结论

- ~~「K=2 整机 route 通过：35,285 LUT / +3.8% / WNS +0.978」~~ ——**那是一次 K=1 构建**，
  不能当作 K=2 的整机结果。**K=2 与 K=4 的整机资源/时序目前都是未知。**
- 仍然**有效**的是 **OOC 数字**：那个探针用 `SYNTH_GENERICS` 直接给模块传参、**绕过了 IP**，
  所以参数确实生效：

| K | 每块拍数 | OOC LUT | OOC WNS |
|---:|---:|---:|---:|
| 1 | 176 | 27,522 | +0.735 |
| 2 | 101 | 28,708 | +0.300 |
| 4 | 64 | 41,342 | +0.185 |

### 整机推算（**外推，不是实测**）

非 Stage1 部分 ≈ 33,987 − 26,809 = **7,178 LUT**：

| | Stage1(OOC) | 整机推算 | 利用率 |
|---|---:|---:|---:|
| K=2 | 28,708 | ≈ **35,886** | ≈ 67.5% |
| K=4 | 41,342 | ≈ **48,520** | ≈ **91.2%** |

### 明天要做的（按顺序）

1. **修传参**：查清 `CONFIG.C_STAGE1_BASES_PER_CYCLE` 为何没进 RTL。怀疑方向：
   IP 打包/缓存（`hw/ip/Dna_accelerator_core_1_0/` 下只有 `component.xml`，无 `.xci`，
   但 Vivado 可能用了工程内缓存的 IP 产物）、或 `component.xml` 的 modelParameter
   需要与 RTL 参数逐项对上（含 `spice:` 侧声明）。
   **验收判据**：K=2 与 K=4 两次整机的 **Stage1 实例 LUT 必须不同**（对照 OOC 差 12,634）；
   若仍相同，就是没修好。
2. 修好后**重跑 K=2 / K=4 两次整机**，拿到真数字。
3. 再定 K（判据见下），然后**一次性写死**：删参数、删未选中路径、显式更新打包门禁的迁移契约。

### K 选型的建议（**基于 OOC 与外推，不是基于有效的整机实测**）

- K=4 的 OOC 余量只有 **+0.185 ns**，而本项目自己的记录写着 **OOC 偏乐观**
  （同一模块 OOC +2.197 → 整机布线后约 +0.2）；整机推算 **91.2%**。
- 因此**倾向 K=2**：外推 67.5%，余量大得多，且留出约 17.9k LUT 可容纳别的功能
  （例如用户提过的片上 LDPC，其 4-lane 档约 4k–10k LUT）。
- **但这只是倾向，不是结论**——K=4 的整机到底收不收敛，必须等传参修好、实测出来才知道。
  **在拿到有效的整机数字前，不要对外宣称任何 K 的整机结果。**
