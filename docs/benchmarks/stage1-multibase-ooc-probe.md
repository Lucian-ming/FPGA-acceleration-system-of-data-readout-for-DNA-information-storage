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

> ⚠️ **本节命令只对「冻结前的参数化 RTL」有效**（2026-10-14 之前，`BASES_PER_CYCLE` 是
> `parameter`）。2026-10-14 写死 K=2 后它变成 RTL 内的 `localparam`，`SYNTH_GENERICS`
> 里的 `BASES_PER_CYCLE=` 覆盖**不再起作用**；要复现下面的历史数字，须先
> `git checkout <冻结前提交> -- hw/ip/Dna_accelerator_core_1_0/hdl/srpe_batch_pway.v`。
> 保留本节是为了让历史报告可追溯，**不是当前可跑的入口**。

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

---

## ✅ 根因已定位并修复 + **K=2 整机实测**（2026-10-13 深夜）

### 根因：Vivado IP 的参数链少了一环

IP 的参数传递是三段，**我只补了头尾、漏了中间**：

```
CONFIG.<X>            ← bd.tcl 的 set_property 改的是这一层（组件参数 PARAM_VALUE.X）
   ↓  【xgui/<ip>.tcl 里的 update_MODELPARAM_VALUE.<X> proc】   ← 漏的就是这一条
MODELPARAM_VALUE.X    ← **这一层才是传给 HDL 的**
```

缺了那条 proc，`set_property` 改的永远只是组件参数，**模型参数恒为 component.xml 里写死的 1**。

**方法教训（比 bug 本身值钱）**：`bd.tcl` 那道「设完 CONFIG 再 `get_property` 读回比对」
**通过了**——因为它读的是 `PARAM_VALUE`，**不是** `MODELPARAM_VALUE`。
**凡是"设了参数要确认生效"，读回自己设的那个值都不算数**，必须查到**最终被消费的那一层**
（这里就是生成的 IP 包装 HDL），或者用**"两个不同取值必须产生不同结果"**来反证。

**修复**：`hw/ip/Dna_accelerator_core_1_0/xgui/Dna_accelerator_core_v1_0.tcl` 补上
① `ipgui::add_param` ② `validate`（只允许 1/2/4，且 K>1 只对 `P_WAYS=16` 有效）
③ **`update_MODELPARAM_VALUE.C_STAGE1_BASES_PER_CYCLE`**（缺的就是它）。
**确证**：生成的 `top_bd_Dna_accelerator_core_0_0.v` 里出现 `.C_STAGE1_BASES_PER_CYCLE(2)`。

### K=2 整机实测（有效）

| | K=2 整机（**有效**） | 对照：原始 P16（K 参数不存在） |
|---|---:|---:|
| 整机 LUT | **35,702（67.1%）** | 33,987（63.9%） |
| Stage1 实例 LUT | **28,524** | 26,809 |
| FF | 36,816 | 36,067 |
| RAMB36 | **48** | 44 |
| DSP | 5 | 3 |
| **WNS / WHS** | **+0.313 / +0.036** | +0.617 / +0.017 |
| TNS/THS、失败端点 | 0 / 0 | 0 / 0 |

**判据（事先写下、确实变红过）**：K=2 与 K=4 的 Stage1 实例 LUT **必须不同**。
修复前两次都是 28,103（相同 → 参数没生效）；修复后 K=2 = **28,524**，判据通过。

**外推核对**：先前推算整机 35,886（67.5%），实测 **35,702（67.1%）**，差 0.5%。

### K=4 整机：**未完成**（断电中断）

K=4 的整机 route 在 22:51 启动，**因断电未跑完**。所以
**「K 取 2 还是 4」今晚没有定论**，明天要补跑 K=4 整机（命令与 K=2 相同，只把
`stage1_bases_per_cycle` 改成 4）。

**选型倾向仍是 K=2**（依据：K=4 的 OOC 余量仅 +0.185 ns vs K=2 的 +0.300，
整机推算 K=4 ≈91% vs K=2 实测 67.1%），但**这是倾向、不是结论**。

### ★ 决定：K = 2（被器件容量定死，不是价值判断）

**K=4 整机在布局阶段硬失败**——不是"时序勉强"，是**装不下**：

```
ERROR: [Place 30-487] Luts: 54164 (combined) 63246 (total)，器件容量 53200
                      可用 slice 10335，未布局实例需要 10591
ERROR: [Place 30-99]  Placer failed
FATAL: run impl_1 failed: status='place_design ERROR', progress=33.3%
```

| | K=2（**实测，有效**） | K=4（**实测**） |
|---|---:|---:|
| 整机 LUT | **35,702（67.1%）** | **54,164 / 63,246 → 超容量** |
| 布局布线 | ✅ 通过 | ❌ `place_design` 失败 |
| WNS / 失败端点 | +0.313 / 0 | 未到时序阶段 |

**因此 K=2 是唯一可选项**，先前"K 取 2 还是 4"的开放问题就此关闭。

### ⚠️ 一条外推法失效的记录（本轮第二个方法教训）

先前用「非 Stage1（7,178）+ Stage1 OOC（K=4 = 41,342）≈ 48,520（91.2%）」外推整机，
**实测 54,164–63,246，低估约 14,700 LUT**。反推 K=4 的 Stage1 在整机上下文里约 47,000，
而其 OOC 只有 41,342。
→ **「OOC 模块 + 其余部分之和」这个外推法，在模块足够大时不成立**；
大模块的整机上下文会有额外的复制/retiming 开销。**资源结论必须以整机 route 为准。**
（K=2 那次外推 35,886 vs 实测 35,702 只差 0.5%，所以这个偏差不是线性的——**规模越大越失真**。）

### 由此打开的选项：片上 LDPC —— **容量问题没有解决，只是没有被证伪**

K=2 整机实测占 67.1%，**余量 17,498 LUT、92 块 RAMB36**。

> **勘误（2026-10-14）**：上一版此处写「`ldpc-pl-v2` 核过的 4-lane 译码器约需
> 4k–10k LUT + 69 BRAM → 容量够」。**这句话两头都错，属误引**：
> `ldpc-pl-v2` 的答复里 LUT 一栏是「**未综合**——仓库没有译码 RTL，不能给出可信消耗数」，
> 而 69 块 BRAM 是**单路 8-bit** 的容量下界，**不是 4 路**。原始答复见
> `~/.local/state/codex-subagent/runs/20261013T104123Z-de415b4607/answer.md` §3。

按该答复的实测/估算（`clients/python/resources/dvb_s2_r5_6.pchk` 已确认是**标准
DVB-S2 R=5/6**，150 组、600 个基地址与 ETSI EN 302 307-1 Table B.9 零差异，
H 有紧凑生成表示，紧凑表仅约 1 KB，**不必存展开边表**）：

| 项 | 数值 | 性质 |
|---|---|---|
| 紧凑 H 单路、8-bit LLR | 69 / 95 块 BRAM | 静态容量下界 |
| 4 路朴素复制 | 165 块 BRAM | **超余量** |
| LUT / DSP | **无数据** | RTL 不存在，未综合 |
| 单路时延 | ≈0.381 s（45 轮外推） | 外推，不含 DMA，**慢于 PC 的 C 实现 0.182 s** |
| 4 / 22 路时延 | ≈0.095 / 0.017 s | 外推，**假定无端口冲突** |

**因此「装得下」目前是未决问题**：单路有容量空间，4 路要不要复制、能不能找到无冲突
banking 都未证；`column mod bank_count` 的实测统计是 4 bank 时每行最多 14 条边同 bank，
**不能假定 4 路可无停顿**。最可能失败的正是 **LLR 的多读多写端口冲突**。
且当前 K=2 的 WNS 只剩 **+0.313 ns**，再塞逻辑进同一 PL 的时序风险不小。

工程量级（`ldpc-pl-v2` 估计，未验证）：RTL 原型 + 定点对照 + 存储调度约**数个人周**，
到时序收敛与板端验收可能**数周级**。**真要做必须先跑 OOC 探针**，不能直接上板。

**性能上它是展示项不是提速项**：主机侧 LDPC（0.653 s）一旦与下一轮重叠，稳态省 ≈0；
且题面「比 CPU 快」的口径只算比对内核、不含 LDPC，搬上去也不改善该指标。

---

## ✅ K=2 已写死（2026-10-14）

### 改了什么

| 位置 | 改动 |
|---|---|
| `hdl/srpe_batch_pway.v` | `parameter BASES_PER_CYCLE` → **`localparam BASES_PER_CYCLE = 2`** |
| `hdl/Dna_accelerator_core_v1_0.v` | 删 `parameter C_STAGE1_BASES_PER_CYCLE` 与 `.BASES_PER_CYCLE(...)` 连接 |
| `component.xml` / `xgui/*.tcl` | 删对应 modelParameter、parameter、add_param、validate、update 过程 |
| `hw/scripts/bd.tcl` / `build.tcl` | 删默认值、全局覆盖、`CONFIG.C_STAGE1_BASES_PER_CYCLE`、取值校验与回读项 |
| `tools/run_vivado_build.sh` | usage 去掉该选项 |

**冻结版源码 SHA256**：`cefe308735eb1e51b579024c60a0c415ebeb93bd9441ecbc78d0af2934d46366`
（已 pin 进 `tools/check_ip_packaging.sh`）。
负向验证：`tclsh hw/scripts/build.tcl board=bkb220 stage1_bases_per_cycle=2 dry_run=1`
现在**报错拒绝**该参数——传参通道确实已不存在。

### 行为不变性：**已证，不是推断**

用 `tb_dna_stage1_p16_equivalence.v`（生产 P4 + 独立符号滑窗 oracle，score/pos/cw 三重逐位）
跑冻结版，与写死前那一版对照。**下表为 LC6（快速档）**；周期数随 NUM_LC 变化，LC50 的数字不同，
不可混用：

| 版本（均 LC6） | P4 周期 | P16 周期 | 判定 |
|---|---:|---:|---|
| 写死前（`parameter`，K=2） | 258,875 | 95,873 | PASS |
| **冻结版（`localparam` = 2）** | **258,875** | **95,873** | PASS |

**周期数逐位相同** ⇒ 把可配置参数改成常量没有改变任何行为。

**LC50 生产几何（`bash tools/run_sim.sh stage1_production_full`）也已通过**：

```
[PRODUCTION EQ] round=0 LC=50 P4=1680956 P16=322507 PASS
[PRODUCTION EQ] round=1 LC=50 P4=1680956 P16=322507 PASS
[PRODUCTION EQ] PASS 独立oracle、末组/807/补零/反向/并列零分/复位再任务
```

同一条判据（生产 P4 + 独立 oracle、score/pos/cw 三重逐位）在两档几何上都成立。
**LC50 的周期比是 5.21×**（1,680,956 → 322,507），高于 LC6 的 2.70×——
因为 P4 的周期数随 NUM_LC 扩张得更快（8.33 倍区域数下 P4 ×6.49、P16 ×3.36）。
**两个倍数不是同一口径，不可混用。**

同一入口的第二个用例 `dna_stage1_p16_interface`（AXI-Lite 控制 + S_AXIS 入口 +
M_AXIS 背压）在 LC50 也通过：

```
[PRODUCTION AXIS] P16 round=0 LC=50 PASS records=64
[PRODUCTION AXIS] P16 round=1 LC=50 PASS records=64
[PRODUCTION AXIS] P4  round=0 LC=50 PASS records=64
[PRODUCTION AXIS] P4  round=1 LC=50 PASS records=64
[PRODUCTION AXIS] PASS LC=50 P4cycles=1674229 P16cycles=315778
```

**`stage1_production_full` 整轮 3 项通过 / 0 项失败。**

### 整机：与写死前逐项相同

`hw/build/bkb220-p16-k2freeze-20261014T000848Z-board-migrate`（`stage1_p_ways=16 stage1_pipe_tree=1`）：

| | 写死前 K=2 | **冻结版** |
|---|---:|---:|
| LUT | 35,702 | **35,702** |
| RAMB36 | 48 | **48** |
| DSP | 5 | **5** |
| WNS / 失败端点 | +0.313 / 0 | **+0.313 / 0**（共 88,748） |
| WHS / 失败端点 | +0.036 / 0 | **+0.036 / 0** |
| DRC | 0 Error | **0 Error**（79 Warning，全为既有 BD/axi_dma 类） |

制品：`dna_accel.xsa`、`top_bd_wrapper.bit`。**出片源码与提交内容现已一致。**

### 打包门禁：迁移契约**按它自己的约定**撤销并替换

原契约断言「生产 P-way 算法体 == `hw/experimental/srpe_batch_pway.v`」，用途是证明 2026-09-22
那次 P14→正式 IP 的搬运没夹带算法改动；其注释原文即写明「**未来修改算法时需同时更新本门禁的迁移约定**」。
K=2 是**有意的算法变更**（同模组整机 LUT 33,987 → 35,702；K=4 更是 63,246 > 容量 53,200），
继续保留逐字节断言只会逼出一个没有信息量的副本。故替换为：

1. **源码 SHA 冻结** —— 出片源码一变，Git diff 里必然可见；
2. **行为判据** —— 独立 oracle 三重逐位比对（强于与旧文件的字节等价）；
3. 新增：断言 `BASES_PER_CYCLE` 必须是 `localparam = 2`，且**不得**再作为 `parameter` 存在。

**这是替换不是放宽**：`tools/check_ip_packaging.sh` 现已 PASS。

### 顺带拆掉的一个雷

`hw/sim/tb_srpe_batch_pway.v` 原有断言「P_WAYS=4 时周期数与生产 4-way **完全相同**」，
前提是「机械推广无副作用」——K=2 后该前提作废，沿用会**无意义变红**。改为断言
**P 路必须严格快于同 P_WAYS 的生产 4-way**：这样「K 被悄悄改回 1」会立刻变红。已 PASS（2/2）。

### ✅ 板端验收：G3 PASS（2026-10-14，生产几何全量）

制品包 `hw/build/bkb220-p16-k2freeze-20261014T000848Z-board-migrate`，
`g3_artifacts.py --device xc7z020` 严格预检先通过。命令：

```bash
bash tools/run_g3.sh --artifact-dir <该包> \
  --xsdb /tools/Xilinx/Vitis/2022.2/bin/xsdb --hw-server TCP:127.0.0.1:3132 \
  --device xc7z020 --uart-port /dev/ttyUSB2 --win-root /tmp/bkb220-g3-k2freeze \
  --ip 192.168.1.10 --port 7 --strict-artifacts --full --skip-dump
```

| 级 | 结果 |
|---|---|
| 完整制品包一致性 | PASS |
| 烧录（rst→fpga→ps7_init→dow→con） | PASS |
| 板端应用层就绪（CAPS） | PASS `READY 7.1 2` |
| 第 1 轮 first.py | 103,616 条记录 / `score_min=67` |
| **唯一判据（译码载荷 SHA-256）** | **PASS** `fcd0cf90bd680e7bbdc203e3398119504da0897acac9e2117008b4efb6b1f2c3`（逐位相同） |
| 串口收到板端输出 | PASS 9,734 字节 |

**实测耗时**：载荷回传段 **6.06 s**（8100 B）。LDPC 起始失败校验 33，47 轮收敛，输出 54,000 bit。

#### ✅ 同小时 A/B：K=2 相对 K=1 快 **1.50×**

按本项目纪律（`t_result` 一天内漂 ±7.5%，**任何 A/B 必须同小时重测参考包**），
不拿异时段的 9.33 s 做比较，而是**紧接着重烧 K=1 参照包**
（`hw/build/bkb220-p16-upload-promoted-20261013T113400Z-board-migrate`，即 K 参数化之前的 P16）
重测一次：

| | run id（UTC） | 载荷回传段 | 记录数 | 判据 | G3 |
|---|---|---:|---:|---|---|
| K=1（参照包） | `20261014T010542Z` | **9.08 s** | 103,616 | `fcd0cf90…b1f2c3` | PASS |
| K=2（冻结版） | `20261014T010224Z` | **6.06 s** | 103,616 | `fcd0cf90…b1f2c3` | PASS |

两次相隔 **3 分 20 秒**，同一次会话、同一批输入、同一判据阈值 `score_min=67`。

**⇒ 载荷回传段 9.08 → 6.06 s，快 1.50×，省 3.02 s。**

⚠️ 口径说明（不得省略）：
- 这是**板端「下发任务→收齐载荷」那一段**，**不含**读段上传与上位机 LDPC；
- 单个样本各一次，**非 ≥3 次的统计**；要写进对外性能表须补重复测量；
- 与仿真周期比 2.70×（LC6 258,875→95,873）**不是同一口径**——后者只含 PL 的 Stage1，
  而这一段还含上传与回传，故倍数更低。

**软件侧制品的复用依据**（本轮**只改 PL**，不重建应用）：`sw/app` 全部 40 个源文件与冻结包
`workspace/dna_lwip_app/src/` **逐字节相同**（仅生成物 `xparameters.h` 除外）；新旧 XSA 的
`top_bd.hwh` **归一化 `TIMESTAMP` 后零差异**；`ps7_init.tcl` 在两份 XSA 内逐字节相同。
BOOT.bin 已用新 bit 重打。两条依据都写进了包的 `manifest.json` → `software.variant_note`。

**本轮板测前踩到的两个坑**（都不在本轮改动范围内，值得记）：

1. `sw/scripts/create_vitis.tcl` 的 `TCP_WND` 替换用 `\S+`，**只吃掉值的第一个 token**；
   Vitis 2022.2 原始模板是 `#define TCP_WND                 6 * 1024`，会被改成
   `32768 * 1024`（= 33,554,432）。冻结包里的正确值 `32768` **不是这条路径产出的**——
   即「TCP_WND 改动可复现」当时并未真正闭合。已改为整行替换并**加回读断言**。
2. 触板前 `usbipd attach` 的 busid **会随重启变**（当天是 `5-2`，不是记忆里的 `4-2`）。
   症状是 WSL 里一个 `/dev/ttyUSB*` 都没有，**极易误判成板子没通电**。且 `run_g3.sh`
   的串口实录要求能打开设备，而 `/dev/ttyUSB*` 属 `root:plugdev`——**不在该组会 FAIL**。

### 仍未关闭的边界

- **`lane_valid` 末组掩码路径在本器件上是死代码**：`wire lane_valid = (run_cnt*K + gsl < READ_BPS)`
  只在 K 不整除 150 时触发。150 的可行 K 为 1/2/3/5/6…，**K=2 时恒为真**；能触发它的 K=4 装不下。
  即：**这条路径在本芯片上无法被任何可综合配置覆盖**，属已知覆盖缺口，不是遗漏。
- 打包门禁的 SHA pin 是**有意**的钝器：任何对该 RTL 的改动都必须显式更新它。

---

## 片上 LDPC：两个去风险子任务的结论（2026-10-14）

派了两个只读子 Agent 去打「最可能杀死项目、且**不需要板子/Vivado**」的两个风险。
原始产物：`~/.local/state/codex-subagent/runs/20261013T235255Z-f14dd13b6e/answer.md`（定点）、
`.../20261013T235328Z-0b9417a003/answer.md`（bank）。

### 风险二（定点正确性）：**风险基本拆掉**

在 2026-09-05 实测活动留下的 14 个回传文件（12 个唯一输入，**未自造向量**）上对照：

| 模式 | 成功 | 与 double 的完整码字差异 |
|---|---:|---|
| double | 8/14 | — |
| **8 bit 饱和** | **8/14** | **0 bit** |
| **6 bit 饱和** | **8/14** | **0 bit** |
| 8 bit 回绕 | **0/14** | 均不收敛 |
| 6 bit 回绕 | **0/14** | 均不收敛 |

**饱和是必需的，不是优化**（回绕版连 double 能成的样本都不收敛）。
**但必须连量化尺度一起限定**：Q1（Δ=0.5、±3→±6）通过；Q2（Δ=0.25）下 6 bit 变成 7/14，
有样本由成功变失败、也有由失败变成功。5 bit 及以下**未测**。
算法：`native_ldpc.hard_decode` / `c_ldpc_accel.c` 均为 **flooding Min-Sum**，无归一化/偏移因子，
≤50 轮，syndrome 早停。

### 风险一（LLR 端口冲突）：**第一轮结论被第二轮推翻**

| 并行度 L | 每拍去重地址数 W | 无冲突 bank **下界** | 着色**上界** |
|---:|---:|---:|---:|
| 1 | 22 | 22 | 29 |
| 2 | 43 | 43 | 53 |
| 4 | 85 | **85** | 97 |
| 22 | 463 | 463 | 476 |

**下界是已证的**（每拍地址须落在互不相同的 bank）。第一轮按「**1 个逻辑 bank = 1 块
BRAM36**」折算，得 L=4 需 118~130 块 > 余量 92 ⇒ 判「放不下」。

> **该折算已被推翻**（原始产物 `~/.local/state/codex-subagent/runs/20261014T000641Z-b6e116553d/answer.md`）。
> 正确的器件事实：**RAMB36E1 真双端口可在两个端口上独立寻址**，故 85 个独立读只需
> `ceil(85/2)=43` 块；而 `512×72` 宽度打包是简单双端口（**一个**读地址），
> **不能满足**多 bank 独立访问——这一点两个方向都值得记住。

按真双端口配对 + 颜色类深度和 ≤4096 行重算：

| 并行度 L | bank 下界 / 着色数 | LLR 状态 BRAM36 | +H 表 + 片上 permutation | +H 表（permutation 留 DDR） |
|---:|---:|---:|---:|---:|
| 1 | 22 / 29 | 25 | 58 / 92 | 26 / 92 |
| 2 | 43 / 53 | 27 | **60 / 92** | 28 / 92 |
| 4 | 85 / 97 | 49 | **82 / 92** | 50 / 92 |

**⇒ L=2 与 L=4 在存储与读端口口径下都能落进余量。** 另有更低 BRAM、更低吞吐的四 bank
分拍方案（L=4 时状态仅 16 块）。

**但这仍不是「装得下」的证明**，边界必须一起写：

- 以上是**存储与读端口的静态估算，不是 Vivado 综合/布线结果**；**LUT 与时序仍无数据**。
- **bank 地址转换未实现**：仅 L=4 的 7-bit bank 标签原始存储就约 453,600 bit（≈14 块 BRAM36），
  尚未含 bank 内地址，也未解决每拍大量并行查询的端口。
- **写回/读改写调度未建模**；逐边消息存储未含。
- LUTRAM 路线：LLR 全放单读口分布式 RAM 的存储下界 **8,100 LUT**（估算 8.1k~8.9k + 控制逻辑），
  在 17,498 余量内；**但每存储位要第二个独立读地址时约需 16,200 LUT，已顶到余量**，
  且 SLICEM 余量与时序未验证。
- 精确最小染色数未定论；64 组线性映射穷举只证明在该映射族内最优。

### 立项与分阶段计划（2026-10-14，用户确认）

**用户 2026-10-14 确认：把 LDPC 集成到 FPGA 上。** 定位是**集成度/展示**，不是提速
（理由见本节末「性能上它是展示项不是提速项」）。**因此验收口径不是"省多少时间"，
而是：功能正确 + 资源与时序可行 + 板端判据 SHA 不变。**

| 阶段 | 内容 | 状态 |
|---|---|---|
| L0 | 矩阵身份与紧凑表示（150 组 / 600 基地址与 ETSI Table B.9 **零差异**） | ✅ 已证 |
| L1 | 定点正确性（**8/6 位饱和逐位复现 double**；回绕 0/14 不可用） | ✅ 已证 |
| L2 | 存储与读端口可行性（L=2 60/92、L=4 82/92，真双端口口径） | ⚠️ 静态估算 |
| **L3** | **bank 地址转换 + 写回/读改写调度的 RTL 与资源** | ❌ **未开始——当前最大未知** |
| L4 | 译码器 RTL 原型，对软件黄金逐位验证 | ❌ |
| L5 | OOC 综合 + 100 MHz 时序 | ❌ |
| L6 | 并入 AXI 地址图 + 主机协议（LLR 下发 / 译码位回传） | ❌ |
| L7 | 整机 route + **板端判据 SHA 必须不变** | ❌ |

**门槛（任一不过就停，不得为推进而放宽）：**
L3 的地址转换若吞掉大量 LUT/BRAM（L=4 仅 bank 标签原始存储就约 14 块 BRAM，且未含 bank 内地址）；
L5 时序不收敛（**K=2 整机只剩 +0.313 ns 余量，这是最可能失败的一关**）；
L7 板端判据 SHA 变化。
**L1 的定点可用是前置条件，不是充分条件**——它只证明"数值上不必用 double"。

**并行度选型尚未定，建议先做 L=2：**

| | L=2 | L=4 |
|---|---|---|
| 含片上 permutation | **60 / 92** | 82 / 92 |
| permutation 留 DDR | 28 / 92 | 50 / 92 |
| 时延外推（45 轮，不含 DMA） | ≈0.19 s（**与 PC 的 C 实现 0.182 s 持平**） | ≈0.095 s |
| bank 地址转换代价 | 较小 | 更大 |

L=4 余量更紧、地址转换更贵、且要一次做对更多东西；**L=2 的时延已与现有 C 实现持平**，
用它先把"能跑通、能上板、判据不变"这条链走完，再决定是否加宽。
**注意**：以上时延都是**外推**，不含 DMA 与端口冲突，不得当交付性能引用。
