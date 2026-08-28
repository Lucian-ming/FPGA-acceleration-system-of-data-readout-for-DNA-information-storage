# 03 · 现状与缺陷清单

初始审计：2026-08-06；代码与回归复核：2026-08-10；Stage2 黄金 Testbench：2026-08-16；
离线任务全量完成（D1/D2、C1~C4、A2/A3/A8/A9、P5）：2026-08-16。证据全部标注了 `文件:行号`，可直接跳转复核。

---

## 一句话现状

**当前 RTL 的 bitstream/XSA 与相匹配 ELF 已重建；剩余主路径是上板端到端验收。**
硬件侧：Stage1/2/3 三级 RTL 全部有黄金向量逐位背书（含 D1 方案B 的 SCORE_MIN 阈值过滤），
完整 `top_bd_wrapper` 已生成 bitstream，在 100 MHz 收敛（WNS +0.145 ns、WHS +0.018 ns）；
2026-08-28 又完成 2,048 条原始读段（4,096 条正反记录）的 M2 完整 XSim 串联，
Stage1 实际输出真实进入 Stage2，Stage2 实际输出经 PS 等价 XOR 后真实进入 Stage3，
最终 LDPC 重建图片哈希为 `fcd0cf90...b6b1f2c3`，并通过单 bit 故障注入反证；
PS 侧：按实际条数运行（C1~C3）、SCORE_MIN=67 已写入并回读校验，ELF 已基于同一份新 XSA 用 xsct 重建；
主机侧：纯 Python LDPC 译码器（P5）在 Linux 上完成黄金数据全链自检（重建 JPEG 与原图逐字节相同）。

**唯一剩余主路径：烧录新 bitstream/ELF → 真实回传 → LDPC → 图片哈希 = `fcd0cf90...b6b1f2c3`（G3）。**
次要遗留：A7（LICENSE 需要用户选择许可证类型与权属确认）、P7 Stage1 架构改造。
P3 任务配置化（PKT_CONFIG/PKT_CAPS）已于 2026-08-16 傍晚完成离线部分，见 changelog。

**已完成（时间线）**：
- 2026-08-07 · Stage3：B5、B6 修复；B7/B8/B9 通过重写控制层解决，最苛刻从机条件下逐位通过。
- 2026-08-08 · Stage1：B2、B4 修复；又发现并修复 B10/B11/B12 三个流水线错位。
- 2026-08-08 · 上位机：`first.py` 反向互补（D1 软件半边）与 LSB-first 打包。
- 2026-08-10 · 复跑全部通过（见 `docs/08-handoff-2026-08-10.md`）。
- 2026-08-13 · A10：`ldpc_pipeline.py` 把 3 个 MinGW DLL 与 EXE 一起拷贝，判据验证。
- 2026-08-16 上午 · **Stage2 黄金 Testbench**：暴露并修复 B13/B14/B15/B16/C4，
  两轮 4,096 条记录投票逐位相同（`run_sim.sh stage2`）。
- 2026-08-16 下午 · **D1/D2 板端取舍**：Voter 新增 SCORE_MIN(0x30)，阈值 67 三轮 TB
  逐位通过（`stage2_expect.hex` 改为方案B语义重新生成）；**C1~C3**：PS 按实际条数配置、
  `ddr_layout.h` 主机单测、协议层 64 倍数校验；**C4** 二次任务清零；
  **A2/A8/A9**：build.tcl 修路径/IP 仓库/XDC，top.xdc 与 collect_info.tcl 落盘，
  tb_dna_quick 真正驱动 AXI-Lite；**P5**：纯 Python min-sum LDPC 译码器黄金自检通过。
  Voter（D1 版）重新综合收敛；ELF 用 xsct 重建（920,472 B）。
- 2026-08-16 傍晚 · **P3 任务配置化（离线部分）**：协议 PKT_CONFIG(0x05,44B+CRC32)/
  PKT_CAPS(0x06→0x16,24B) 落地（严格拒绝、强制 CONFIG、v1 只支持 SE150 三项决策）；
  `sw/app/task_config.h` 解析/校验/CRC 主机单测全过（黄金 CRC 与 zlib 交叉验证）；
  `first.py` 自动推导几何并下发（`--dry-run` 可预览，顺带修正 `resolve_total` 把
  `--limit` 当抬底的既有 bug）；ELF 重建（943,120 B）。板端握手联调待上板。
- 2026-08-16 晚 · **A3 与可上板构建链关闭**：从只读历史 XSA 的 `design_1.hwh`
  固化 DDR、GEM0/MDIO、UART1、FCLK0 和 MIO Bank 电压；完整 Vivado/Vitis 2022.2
  重建 bitstream、XSA、lwIP BSP 与匹配 ELF。全量回归 11/11；产物和哈希见下文。
- 2026-08-28 · **M2 完整 XSim 串联关闭**：64/64 个 Stage1 batch（4,096 条记录）
  score/codeword 0 错误，并列峰 85/4,096（2.08%）；Stage2 81,000 bit、PS XOR、
  Stage3 64,800 bit 与受控黄金向量逐字节一致；LDPC 5 轮收敛并得到目标图片哈希。
  翻转 Stage2 bit 123 后 Stage3 精确报告 1 bit mismatch。统一入口为
  `STAGE1_JOBS=3 bash tools/run_m2_full.sh`，实现提交 `e7b4e44`。
- 2026-08-29 · **异机复跑与运行器可移植性修复**（提交 `b388d2e`）：四个仿真入口原先硬依赖
  ripgrep，在未装 rg 的 checkout 上 `run_sim.sh` 会把 11 个实际 PASS 的用例统计成
  「通过 5 项，失败 6 项」（假红），`run_xsim.sh`/`run_m2_quick.sh`/`run_m2_full.sh`
  则直接 `FATAL: ripgrep is required` 退出。已回退到 POSIX `grep -E`（判据强度不变）。
  本 checkout 复跑：`run_sim.sh` 11/11 PASS、`run_xsim.sh all` 6/6 PASS、
  `STAGE1_JOBS=6 bash tools/run_m2_full.sh` 全链 PASS（Stage1 64/64 batch、Stage2 81,000 bit、
  Stage3 64,800 bit / 8,100 B、LDPC 图片哈希命中目标值，Stage2 bit 123 故障注入被检出）。
  注意 `hw/build/xsim/` 不入 Git，各条记录里的证据目录只存在于当初运行的那台机器；
  换 checkout 后必须本机重跑生成自己的证据，不得直接引用他机运行 ID。
- 2026-08-29 · **M3 实际 Block Design 集成仿真**（提交 `1bd236d`，详见
  `docs/15-m3-bd-simulation-2026-08-29.md`）：新增 `tools/run_m3_bd.sh` 与
  `hw/scripts/m3_bd_sim.tcl`，DUT 是 `bd.tcl` 生成的实际 `top_bd_wrapper`。
  **BD-1 PASS**：地址图与 `sw/app/xparameters.h` 逐项一致，无黑盒，三个自研 IP 均在且未锁定；
  **BD-2 PASS**：71 项检查 0 失败（寄存器写/读回、从机隔离、未映射地址 DECERR）；
  **BD-3 未通过**：Voter/Decoder 的合法 INCR 读突发经实际 ic_hp 到达 S_AXI_HP0、AR 握手完成后，
  Vivado 2022.2 的 `processing_system7_vip` 一拍 RDATA 都不返回；已逐条排除跨 4KB 边界、
  地址范围、未完成事务上限、三档从机延迟、单 IP 因素与时钟/复位。定位为仿真模型限制，
  **不为此修改生产 BD**。M3 因此仍未完成，不得据此关闭 G3。

同时，**算法本身已经被证明是正确可行的**：`tools/golden_model.py verify-code` 用 R0.83
黄金数据证明了「编码序列 ⊕ 水印 → 5b4b → 码字」逐位成立。所以要做的是把 RTL 对齐到
已验证的模型，而不是重新发明算法。

---

## D 类 · 算法缺口（比所有实现 bug 更靠前）

### ~~D1 反向互补读段的板端判别与取舍~~ ✅ 已完成离线实现，待 G3 上板验收

当前实现采用方案 B：`first.py` 默认发送正向与反向互补两份记录，Voter 使用
`SCORE_MIN=67` 丢弃噪声方向；Stage2 三轮黄金回归和下游 LDPC 判据均通过。以下内容保留
为修复前的问题量化和方案依据，其中“当前实现”均指 2026-08-16 修复前的旧路径。

实测（`tools/golden_model.py`，SE150 前 400 条）：

| 比对方式 | 与真实编码序列一致度 ≥140/150 的比例 |
| --- | --- |
| 仅正向 | 50.7% |
| 仅反向互补 | 48.0% |
| 两方向取更优 | **98.8%**（平均 148.9/150） |

**这批数据里约一半读段是反向互补的**。`clients/python/first.py` 已能把每条原始读段的
正向和反向互补版本都编码并发送（默认 `--orient both`），这是 D1 的主机侧准备；但
`srpe_batch` 仍只对单条输入做正向比对，`differential_voter_v1_0.v` 也没有使用 `score`
把同源的两份结果择优或加权。因此错误方向会参与投票；该问题后来由上述方案 B 关闭。

后果与修复效果都已用全量 51,781 条读段量化：

| 软件模型（全部 51,781 条，191× 覆盖） | 共识误码率 | 码字误码率 | LDPC 实测结果 |
| --- | ---: | ---: | --- |
| 不处理反向互补（旧实现） | 1.33%（1,078 bit） | **2.33%**（1,507 bit） | ❌ `Decoding failed!`，图片错 |
| 处理反向互补（`--rc`，实测 25,615 条为反向） | **0.0037%**（3 bit） | **0.014%**（9 bit） | ✅ `Decoding successful!`，**图片 SHA-256 与 `Milk coronet.jpg` 完全相同** |

这不是推断——已用 `R5_6_LDPC_hard_decoder.exe` 实跑验证（见下方 A10 关于运行该 EXE 的前置条件）。
即：**补上反向互补这一件事，就把误码率降低了 167 倍，整条算法链路随即闭合到原始图片。**
读段本身质量很好（两方向取优后平均 148.9/150 ≈ 99.3%），问题不在数据。

**所需读段数也已实测**（按 FASTQ 原始顺序取前 N 条，含反向互补）：

| 读段数 | 覆盖 | 码字误码率 | 能否还原图片 |
| ---: | ---: | ---: | --- |
| 500 | 80.0% | 10.36% | ❌ |
| 1,000 | 96.8% | 1.80% | ❌ |
| 1,060 | 97.0% | 1.63% | ❌ |
| **1,080** | **97.1%** | **1.56%** | ✅ **完全还原** |
| 2,000 | 99.7% | 0.31% | ✅ |
| 51,781 | 100% | 0.014% | ✅ |

**约 1,080 条读段（≈4× 覆盖）即可完整还原原图**，门槛非常陡（LDPC 的瀑布效应）。
反过来说：不处理反向互补时，即使把全部 51,781 条都用上也无法译码——**多给数据不解决问题**。

**即使其余 B 类修复都在，若没有方向取舍也不会得到正确图片。** 当前方案和判据见本节开头。

### ~~D2 比对分被算出来却从未使用~~ ✅ 已随 D1 修复（SCORE_MIN 使用 parse_score 过滤）

`current_score` 寄存器本身仍在（未删），过滤在解析拍用组合的 `parse_score` 完成。
注意：实测简单阈值过滤会因丢失覆盖而更差（阈值 75 时误码率反升到 3.3%）——
该结论针对「择优一条再过滤」的旧语义；方案B 语义下 67/68 都在分离带（噪声底 59~62）内，
且 67 与黄金向量严格一致，已按 67 固化到 `VOTER_SCORE_MIN`。

<details><summary>原始记录</summary>

### D2（原始）比对分被算出来却从未使用

`srpe_batch` 输出 `score`，Voter 曾把它存进 `current_score` 后再未使用。

---

## B 类 · 正确性缺陷（必须全部修完才可能出正确结果）

### ~~B1 水印预载通路失效~~ ✅ 已修复（2026-08-08），主机单元测试通过

**修复**（`sw/app/echo.c` + `echo.h` + 新增 `sw/app/wm_expand.h`）：

1. PS 先把打包水印展开成 **50 个区域 × 957 个符号**（每符号一个 32-bit 字，
   因为 DNA 核预载时每拍只取 `TDATA[1:0]`），写入新增的 DDR 区
   `DDR_WM_REGIONS_BASE = 0x1004_0000`（191,400 B）；
2. 预载状态机改为**逐区域**：`写 reg1=区域号 → 置 preload → DMA 957 拍 → 等完成`，
   循环 50 次。原来从未写过 `reg1`，导致区域 1..49 恒为全 0；
3. `MAX_WATERMARK_SIZE` 10,120 → 10,240，并**去掉静默截断**，超限/不足都返回错误；
4. `first.py` 的水印打包由 MSB-first 改为 **LSB-first**，与读段和 PS 取位方式统一。

**判据结果**：展开逻辑抽进 `sw/app/wm_expand.h`（不依赖 Xilinx 头），
固件与主机测试**共用同一份代码**；`bash tools/run_sim.sh host` 用黄金向量验证：

```
✓ PASS  47850 个符号全部与黄金向量一致（50 区域 × 957 行）
```

上位机打包的 10,125 字节与 `tests/golden/watermark_packed.bin` **逐字节相同**。

> ⚠️ 仍未验证的部分：区域切换时 `wm_waddr` 是否正好回到 0、DMA 与 `preload`
> 位的时序配合——这些只能上板或做 DNA 顶层的 AXIS 级仿真确认。

<details><summary>原始记录</summary>

### B1 水印预载通路失效 —— 最高优先级

- `hw/ip/Dna_accelerator_core_1_0/hdl/Dna_accelerator_core_v1_0.v:242-248`
  预载时每个 32-bit AXIS 拍只取 `TDATA[1:0]`，即 **1 拍 1 个符号**。
  PS 一次 DMA 送 10,120 B = 2,530 拍，只能写入 2,530 个符号。
- 水印 BRAM 需要 `NUM_LC * REF_LEN = 50 × 957 = 47,850` 个符号
  （50 个重叠区域各存一份 957 符号的窗口），当前只有约 5% 被写入。
- `wm_waddr` 到 956 就归零，写入永远落在 `bram_sel` 指定的**单个区域**；
  而 `bram_sel` 来自 `reg1[5:0]`，`sw/app/echo.c` 从头到尾只写 `reg0`
  → 区域 1..49 恒为全 0。
- `sw/app/echo.h:42` `MAX_WATERMARK_SIZE = 10120`，小于 81,000 bit 所需的 10,125 B；
  `sw/app/echo.c:1570` 还会静默截断，客户端发的 10,128 B 被砍掉 8 B。

**后果**：Stage1 的比对参考几乎是空的，所有 `position` 都无意义。

</details>

### ~~B2 / B4 码字位平面布局与位序~~ ✅ 已修复并仿真验证（2026-08-08）

**修复**：
- `srpe_batch.v` 的装载与输出都改为**位平面**布局，并与 `match_mask` 的
  `{a_hi, a_lo}` 符号约定对齐（第一位平面进 hi）；
- `first.py` 的 `seq_to_40B()` 改为**字节内 LSB-first** 打包，这样 AXIS 上
  `in_buf[k]` 正好等于码流第 k 位，RTL 端零转换。

**判据结果**：`bash tools/run_sim.sh stage1` —— 一批 64 条读段，
**分数 64/64 完全一致，回传码字 64/64 完全一致**，仅 2 条并列峰（两条的分数都是
59 分的噪声底，本来就是反向互补读段，正向比对无意义）。
上位机侧：2,048 条读段的正向与反向互补编码**逐字节**与黄金模型相同。

> 修这一项时又挖出 3 个**先前就存在**的流水线缺陷，见下方 B10/B11/B12。

<details><summary>原始记录</summary>

### B2 Stage1 输出与 Stage2 输入的码字布局冲突

- `srpe_batch.v:377-378` 输出的 300 bit 是**交织**布局（`cw[2i]`/`cw[2i+1]` 是第 i 个碱基的两位）。
- `differential_voter_v1_0.v:262-270` `calc_layer_position()` 按**位平面**布局解释
  （前 150 bit 属上层、后 150 bit 属下层）。

**后果**：即使位置正确，每一位也会被投到错误的地址上。二者必须统一到
`docs/02-data-contract.md` 第 2 节的位平面布局。

### ~~B3 缺少「与水印做差分」这一整级功能~~ ✅ 已实现（2026-08-08）

**修复**：新增 `apply_watermark_differential()`（`sw/app/echo.c`），在 Stage2 完成、
Stage3 启动之前，对 DDR 上的 10,125 B 做逐字节 `共识 ⊕ 水印`。
两侧都是「码流顺序 + 字节内 LSB-first」打包，因此逐字节异或即可，无需任何位重排。
已接入流水线状态机：`PIPE_DONE_STAGE2` → 差分 → `PIPE_DECODER_PREP`。

按计划先用 PS 软件实现打通链路（10,125 B，几十微秒）；是否下沉进 Voter
等端到端验证通过后再决定。

**判据状态**：已编译并链接进 ELF；**逐位正确性依赖 Stage2 的输出**，
需等 Stage2 验证后一并确认。

<details><summary>原始记录</summary>

### B3 缺少「与水印做差分」这一整级功能

在三个 IP 的 RTL 里搜索不到任何异或/差分运算。Stage2 输出的是**共识 DNA 序列**，
而 Stage3 把它当作**稀疏流**来反稀疏化——中间少了 `XOR 水印`。

**后果**：即使前两级完全正确，Stage3 的输入依然是错的。
可选修法（按改动量从小到大）：
1. 过渡方案：PS 在 Stage2 完成后对 DDR 上的 10,125 B 做一次软件 XOR（几十行代码，可立即验证整链）；
2. 在 Voter 判决输出处 XOR 水印（需要给 Voter 加水印缓存和一路 AXI 读）；
3. 在 Desparsifier 入口 XOR（同样需要水印通路）。

建议先做 1 打通端到端，再决定是否下沉到 PL。

</details>

### B4 读段编码位序未对齐

- `clients/python/first.py:202-223` 产出「位平面 + 每字节 MSB-first」。
- Stage1 从 AXIS 组装 `in_buf` 时 word0 落在 `in_buf[31:0]`，字节内低位在前，
  相当于把 MSB-first 的字节又翻了一次；且 `srpe_batch` 期望交织布局（见 B2）。

**后果**：碱基顺序被打乱，相关运算失效。必须用黄金向量在 Testbench 里钉死，不能靠读代码推断。

</details>

### ~~B10 / B11 / B12 srpe_batch 的三个流水线错位~~ ✅ 仿真新发现并已修复（2026-08-08）

写 Stage1 的 Testbench 时暴露出来的，三个都由 **BRAM 同步读延迟**引起，
且都**先于本次改动就存在**——只改 B2 的布局根本不可能让结果正确。

| 编号 | 问题 | 修法 |
| --- | --- | --- |
| **B11** | 装载位平面时的读改写只有两相（给地址→立刻读改写），读到的是**上一行**内容再写回本行，等于把别的读段的位覆盖掉，装载出来的位平面全错 | 插入一拍等待相，`phase` 由 1 bit 扩成 2 bit |
| **B10** | 输出时 `S_EMIT` 给地址、`S_EMIT2` 立刻取数，同样早了一拍，`cw_acc[k]` 拿到的是 `plane[k-1]` | 加一个 `S_EMIT_W` 等待态 |
| **B12** | 比对流水线有 3 拍延迟，却用 `(st==S_RUN)` 延迟 1 拍当累加使能：每个位置的**前 2 个碱基用的是上一个位置的残留**，自己**最后 2 个碱基没被计入** | 用有效性移位链把使能与数据严格对齐，`S_RUN` 多跑 3 拍排空流水线 |

**症状对照**（同一个 TB，同一批 64 条读段）：

| 版本 | 分数不符 | 回传码字不符 |
| --- | ---: | ---: |
| 只修 B2/B4 | 55/64 | **64/64** | 
| 再修 B10/B11 | 1/64 | 1/64 |
| 再修 B12 | **0/64** | **0/64** |

「回传码字 64/64 全不符」是最有价值的线索：它与比对算法无关，直接指向装载/输出通路。

### ~~B13 / B14 / B15 / B16 Voter 的四个数据通路/协议缺陷~~ ✅ 黄金 Testbench 新发现并已修复（2026-08-16）

写 Stage2 的 Testbench（`hw/ip/differential_voter_1_0/hdl/tb_differential_voter.v`）时暴露，
全部**先于本次改动就存在**——此前 Voter 从未被任何黄金向量验证过，这些缺陷说明
「界面跑通」与「运算正确」完全无关。

| 编号 | 问题 | 修法 |
| --- | --- | --- |
| **B13** | 投票读流水线错位：`bram_addr → bram_raddr_q → bram_dout → bram_dout_r` 共 3 拍，而每位投票循环只有 3 拍（CALC/READ/UPDATE），`S_VOTE_UPDATE` 读到的是**上一位**的累加器，还把 ±1 写进当前位地址——整个投票被系统性摧毁。输出级同样错位（ADDR 只等 1 拍） | 删除多余的 `bram_dout_r` 一级；投票循环改 4 拍（插入 `S_VOTE_WAIT`）；输出级 ADDR 改 3 拍（`output_addr_wait` 扩为 2 位计数器），统一改用 2 拍对齐的 `bram_dout` |
| **B14** | 输出判决 `(bram_dout > 10'sd0)` 是**无符号**比较，负票（如 −1 = `10'h3FF`）被判成 1 | 改为按补码语义：`~bram_dout[9] && (bram_dout != 10'd0)` |
| **B15** | 每 64 bit 字丢 1 bit：字装满后 FSM 先绕回 ADDR/PACK 多打包一拍，`S_WAIT_BRESP` 清 `output_word` 时把它静默抹掉（81000/65 ≈ 1247，与实测只写出 1,247/1,266 拍吻合） | 新增组合 `word_done`，装满当拍直接转 `S_OUTPUT_SETUP` |
| **B16** | `S_READ_DATA` 完成条件 `(beat_count>=6 && RVALID)` 依赖第 6 拍握手后 RVALID 仍保持——合规从机在 RLAST 握手后即撤下 RVALID，**真实互连上会死锁**（原 TB 从机残留 RVALID 电平才让它勉强走完，代价是污染下一条记录的字序列） | 完成条件只看握手计数 `beat_count >= 6` |

**症状对照**（同一个 TB，同样 4,096 条记录）：

| 版本 | 输出拍数 | 逐位比对 |
| --- | ---: | --- |
| 修复前 | 1,247/1,266 | 全部 1,266 拍不符（满屏 `ffff`/全零两种模式） |
| 修 B13~B16 后 | 1,266/1,266 | **0 拍不符，81,000 bit 逐位相同** |

**判据结果**（`bash tools/run_sim.sh stage2`，约 1,100 万周期）：

```
[TB] 第 1 轮：1,266 拍 / 81,000 bit 与黄金向量逐位相同
[TB] 第 2 轮：1,266 拍 / 81,000 bit 与黄金向量逐位相同
[TB] ✓ PASS  两轮结果均与黄金向量逐位相同（累加器确已清零）
```

判据要点：
- 激励 `tests/golden/stage2_in.hex` = 2,048 读段 ×（正向 + 反向互补）共 4,096 条
  Stage1 格式记录（与 `first.py orient="both"` 的板端数据流一致）；
- 期望 `tests/golden/stage2_rtl_expect.hex` = **板端现行语义**（D2 未修，分数不过滤，
  全部记录投票）的共识码流——将来实现 SCORE_MIN 后改用已有的
  `stage2_expect.hex`（阈值过滤版）即可直接复用同一 TB；
- 附带判据：每次读突发恰 6 拍（ARLEN=5）、每笔写单拍（WLAST=1）、
  末拍 WSTRB=0x1F、DBG_WRITE=1266、首写地址=OUT_ADDR、ERR_FLAGS=0；
- **连跑两轮**：第二轮验证每次 START 都重新清零累加器（C4）；
- 调试手段：`vvp ... +dump_bram` 转储 81,000 个累加器，
  配 `tools/debug_vote_diff.py` 与 Python 重算票值逐位置 diff。

### ~~B17 DNA 输入 FIFO 满时仍接收数据~~ ✅ 已修复并仿真验证（2026-08-16，R3）

**原问题**：`Dna_accelerator_core_v1_0.v` 在 `eng_busy=1` 时无条件令
`S_AXIS_DATA_TREADY=1`。输入 FIFO 深度只有 1,024，满后 `fifo_sync_sdpram_b64.v`
会静默忽略写入，但顶层 `in_count` 仍增加；DMA 认为数据已握手，实际读段已经丢失。

**修复**：预载模式仍直接接收；正常读段的 `TREADY` 改为 `~in_full`，`in_count`
只按 `in_wr && ~in_full` 的真实 FIFO 写入计数。新增 `tb_dna_ingress.v`：先验证
10×32 bit 组装成 300 bit，再模拟引擎长时间 busy 连续提供 1,100 条读段。
修复前 11,000 拍全部被接受且无背压；修复后 FIFO 与镜像计数都稳定在 1,024，测试通过。

### ~~B18 三个生产 IP 的 AXI-Lite 写通道要求 AW/W 同周期~~ ✅ 已修复（2026-08-16，R3）

**原问题**：DNA、Voter、Desparsifier 的生产 AXI-Lite 从机都隐含要求地址通道 AW
与数据通道 W 同周期有效；合法的“先 AW 后 W”事务无法产生 B 响应。Voter/Decoder 目录中
同名 `_S00_AXI.v` 是未进入 `component.xml` 的死文件，不能修它们代替生产顶层。

**修复**：三个生产从机各自缓存一个 AW 和一个 W，独立握手，凑齐后仅提交一次写入并
返回一次 B 响应。新增 `tb_dna_axil.v` 覆盖 AW→W、W→AW 与 `WSTRB`；Stage2/Stage3
既有 BFM 改为先 AW 后 W。修复前两级都在首笔事务报“B 响应超时”，修复后
Stage2 三轮 81,000 bit 与 Stage3 64,800 bit 黄金向量仍逐位相同。

### ~~B19 DNA 尾批超时阈值超出计数器位宽~~ ✅ 已修复（2026-08-16，R3）

`idle_counter` 原为 16 bit，却比较 `100000`，因此 partial-batch 超时永远不可达。
当前 CONFIG 强制读段数为 64 的倍数，生产协议不依赖该分支，但 RTL 行为与注释不符。
计数器扩为 17 bit，饱和值和比较常量同步修正；`tb_dna_ingress.v` 直接钉死阈值可表示且可触发。

### ~~B5 反稀疏化的取反标志取错了位置~~ ✅ 已修复并仿真验证（2026-08-07）

**修复**：`conv40_32()` 改为 `r[k] = grp[4:1] ^ {4{grp[0]}}`，取反标志改用组内**第一个** bit。
`five_to_four_decoder.v` 的查找表也已按契约校正（3 处错误）。

**判据结果**：`bash tools/run_sim.sh` → 喂 81,000 bit 黄金稀疏流，
输出 64,800 bit 与 `codeword_R083.txt` **逐位相同**（含随机背压）。
反向对照：恢复旧规则后测试立即失败，证明该判据有效。

<details><summary>原始记录</summary>

### B5 反稀疏化的取反标志取错了位置

- `desparsification_decoder_v1_0.v:220-233` `conv40_32()` 用 `grp[4]`
  （码流里每组的**最后一个** bit）作取反标志，数据取前 4 bit；
  契约要求用**第一个** bit 作标志、数据取后 4 bit（`docs/02-data-contract.md` 第 4 节，已由黄金数据证明）。
- `five_to_four_decoder.v` 是**未被综合引用的死文件**，其查找表另有 3 处错误
  （缺 `00100`/`10100`，多出汉明重量为 3 的 `01011`，`01000` 映射错），会误导后续开发。

</details>

### ~~B6 Stage3 输入缓冲的拍序与同周期冲突~~ ✅ 已修复并仿真验证（2026-08-07）

**修复**：插入改为 `in_pool | (RDATA << in_bits)`；接收/消费/写出三步合并成一条
组合链后统一寄存，消除同周期非阻塞赋值互相覆盖。同样的问题在 `out_pool` 上也存在
（产出的 32 bit 会被 `>>64` 覆盖），一并修掉。

**判据结果**：同 B5，随机背压下 1,013 拍逐位正确。反向对照失败。

<details><summary>原始记录</summary>

### B6 Stage3 输入缓冲的拍序与同周期冲突

`desparsification_decoder_v1_0.v:279` 与 `:288-289` 在**同一个 always 块**里都对
`in_pool`/`in_bits` 做非阻塞赋值：

- 插入用 `in_pool <= {in_pool[63:0], RDATA}`，把新拍放到低位、把上一拍的残留推到高位，
  而消费又从低位 `in_pool[39:0]` 取——只要 `in_bits != 0`（64 不是 40 的倍数，必然发生）顺序就乱了；
- 同一周期若 RVALID 与消费同时成立，后写的消费分支胜出，新到的一拍被直接丢弃，
  `in_bits` 记账也随之出错。

</details>

### ~~B7 / B8 / B9 控制状态机的三个死锁~~ ✅ 已重写并在严格条件下验证（2026-08-07）

**做法**：把「读、转换、写共用一个状态机」拆成**读引擎 / 数据通路 / 写引擎**三块，
读写两个状态机完全独立，只通过数据通路的 valid/ready 耦合。
一旦发出 AR/AW 就必定走完该段突发；B 用状态而非电平等待。
控制层从约 300 行降到约 170 行，去掉了全部 `STREAM_TIMEOUT`/`FLUSH_TIMEOUT`/recovery 分支。

**判据结果**（`bash tools/run_sim.sh`）：AXI 级 Testbench 在**最苛刻**的从机设置下通过 ——

| 从机设置 | 用意 | 结果 |
| --- | --- | --- |
| `B_LATENCY = 0`（WLAST 同拍给 B） | 直击 B7 的电平竞争 | ✅ |
| `Q_DEPTH = 1`（只允许 1 个未完成地址） | 直击 B8 的死锁环 | ✅ |
| 1,013 拍全部交付、无中途放弃 | 直击 B9 | ✅ |

同一个 TB 下，重写前的版本（数据通路修复已在内）停在 **1/1013 拍**。

**另外还修掉一个被掩盖的溢出**：`beats_to_4k()` 原本返回 9 bit，
而地址 4K 对齐时结果是 **512**，装不下被截成 0；原版靠「等于 0 就当没有 4K 限制」
的补丁绕过去。现改为 10 bit 返回。

<details><summary>原始记录（三个缺陷的定位过程）</summary>

### B7 S_WAITB 电平等待 BVALID，可能等一个已经消费掉的响应 —— 仿真新发现

`desparsification_decoder_v1_0.v` 的 `S_WAITB` 用 `if (M00_AXI_BVALID)` 做**电平**判断。
但 DUT 写完一段突发后要过约 2 拍才进入 `S_WAITB`；若从机在 WLAST 后立刻给 B，
DUT 会在进入该状态之前就把它消费掉（`if (BVALID && BREADY)` 分支），
随后死等一个不会再来的 BVALID。

**证据**：`tb_desparsifier.v` 在零延迟 B 响应下必然死锁；把 B 时延加到 4 拍才能继续。
真实互连的 B 时延较大，掩盖了这个竞争，但它是确定存在的。

**修法**：用一个"本段突发的 B 已收到"的标志位替代电平判断。

### B8 无限制发起读突发，同时又阻塞等 AR 握手 → 死锁 —— 仿真新发现

每次回到 `S_ADDR` 就再发一个 AR，不限制未完成读突发数；而 `S_ADDR` 的退出条件
又依赖该 AR 被接受。一旦输入池满（`RREADY` 含 `in_bits<=64`，会拉低）
且互连的地址队列也满，就形成死锁环：
**AR 要等队列腾空 → 队列要等数据流动 → 数据要等池腾空 → 池要等写出 → 写出只在 S_STREAM。**

**证据**：`tb_desparsifier.v` 的地址队列深度为 4 时必然死锁（实测停在 5 拍）；
加深到 16 才能继续。Zynq HP 端口的未完成事务数是有限的，因此板上同样会踩到。

### B9 在写突发中途放弃 AXI burst —— 仿真新发现，违反 AXI 协议

实测到 DUT 在 `AWLEN=243`（244 拍）的突发只写出 1 拍后就跳到 `S_WAITB`，
不再驱动 `WVALID`，然后等 B。AXI 要求主机发完 AW 后必须交付恰好 `AWLEN+1` 个 W 拍，
否则从机永远不会给 B —— 死锁。

**证据**：`tb_desparsifier.v` 停在 264 拍，`w_active=1, w_left=255, state=S_WAITB`。

> **B7/B8/B9 的共同根因**：读和写共用一个状态机，任何一方阻塞都会卡死另一方。

</details>

---

## C 类 · 配置与健壮性

### ~~C1 读段条数由固定宏决定，而非实际收到的条数~~ ✅ 已修复（2026-08-16）

**实现**：`echo.c` 的 `PIPE_VOTER_PREP` / `PIPE_VOTER_START` 两处 Voter 配置全部改用
`conn->total_reads_received`（含 IN_BEATS、TOTAL_READS、cache invalidate/flush 范围、
回读校验）；`PIPE_DONE_STAGE1` 的 flush 同样按实际条数。**判据**：xsct 重建 ELF 成功
（920,472 B，`sw/workspace/dna_lwip_app/Debug/`，含全部改动）；
`ddr_layout` 主机单测（`bash tools/run_sim.sh host` → PASS）。

<details><summary>原始记录</summary>

### C1（原始）读段条数由固定宏决定

- `sw/app/echo.c:634-669,708-740,785,870-895` 用 `TOTAL_READS`（108,000）配置 Voter 的
  cache 范围、`IN_BEATS`/`TOTAL_READS`，而 SE150 实际只有 51,781 条
  → Voter 会把约 5.6 万条 DDR 残留数据当成读段投进去。
- `clients/python/first.py:499-518` 已能检测输入条数、允许指定数量并补齐到 64 的倍数；
  但这只保证官方客户端的发送量，PS 并未把 `conn->total_reads_received` 传给 Voter。
- `dna_connection_t.total_reads_received` 已经存在且在 Stage1 里被正确使用
  （`echo.c:499-518`），Stage2 只是没用它。**这是一处低成本高收益的修复。**

### ~~C2 非 64 整数倍的尾批可能卡死~~ ✅ 已修复（2026-08-16）

**实现**：`process_post()` 入口用 `ddr_layout_validate()` 强校验条数为
`FRAME_READS(64)` 的整数倍，否则回 `PKT_ERROR` 不启动流水线；`process_batch()`
增加容量防溢出（`total > TOTAL_READS` 即拒绝）。补零记录由 SCORE_MIN（0 分 < 67）
在 Voter 内过滤。**判据**：`tools/test_ddr_layout.c` 主机单测钉死边界
（4096/103616/107968 合法，0/100/103562/108000 非法，`run_sim.sh host` → PASS）。

<details><summary>原始记录</summary>

### C2（原始）非 64 整数倍的尾批可能卡死

`srpe_batch` 每批固定处理 `BATCH=64` 条；51,781 = 64×809 + 5。官方 `first.py` 已将发送量
向上补零到 64 的倍数，这避免了该客户端触发空 FIFO；但 PS 协议没有声明或校验此条件，
任意第三方客户端或非 64 倍数任务仍会让 `PIPE_TX_PREFILL` 发送一整帧并读取 DDR 残留。
要彻底支持任意条数，仍需引入“本批有效条数”或由 PS 在协议层显式填充并传递实际条数。

### ~~C3 DDR 布局按 108,000 条预留~~ ✅ 已修复（2026-08-16）

**实现**：新增 `sw/app/ddr_layout.h`（纯计算、参数化、不依赖 Xilinx 头，
固件与 `tools/test_ddr_layout.c` 共用），按实际条数计算区间大小并校验不越界；
顺带发现并记录：`TOTAL_READS=108000` 本身不是 64 的倍数（=64×1687+32），
容量内最大合法条数为 107,968。**判据**：同 C2 的主机单测。

<details><summary>原始记录</summary>

### C3（原始）DDR 布局按 108,000 条预留

`echo.h:41-79` 的地址表按 108,000 条计算（Stage1 输出 5.184 MB）。
实际条数变化时，各缓冲区上界、cache flush/invalidate 范围都要跟着算，
目前是硬编码常量。

### ~~C4 Voter 第二次任务复用旧累加器~~ ✅ 已修复（2026-08-16，Stage2 黄金 Testbench 发现）

原实现靠 `bram_initialized` 只在**首次** START 后清零 81,000 个累加器；
板卡不断电、第二条 TCP 任务到来时，投票会在上一轮的旧票上叠加，结果必然错误。
 Voter 也没有软复位寄存器，PS 无法单独清零。
**修复**：每次 START 都走 `S_INIT_BRAM`（81,000 拍 ≈ 0.81 ms @100 MHz，相对
约 50 ms 的任务时长可忽略），START 时同步复位 `init_addr`。
**判据**：`tb_differential_voter.v` 连跑两轮，输出逐位相同（见 B13~B16 判据）。

### ~~C5 PS 失败 ACK 与成功 ACK 叠加~~ ✅ 已修复（2026-08-16，R1）

`process_complete_packet()` 现在依据 `process_watermark()` / `process_batch()` 的返回值只发
一次 `WM_OK`、`BATCH_OK` 或 `PKT_ERROR`；两个处理函数不再自行发送错误 ACK。BATCH 达到声明条数
也不再隐式调用 `process_post()`，流水线只由显式 `PKT_POST` 触发，避免客户端收到第二个裸字节。

**判据**：`bash tools/run_sim.sh` 通过 8 项、失败 0 项；xsct 重建 ELF 成功
（941,888 B，text 144,519 / data 3,148 / bss 3,266,624）。

### ~~C6 分帧响应非原子重试~~ ✅ 已修复（2026-08-16，R1）

`send_framed_pkt()` 将 8 字节包头与小型负载合并为一次 `tcp_write(TCP_WRITE_FLAG_COPY)`，
只有整包入队成功才返回 `ERR_OK`；`ERR_MEM`/`ERR_WOULDBLOCK` 重试不会重复排队包头，调用方记录
发送失败。

### ~~C7 超大 TCP payload 令接收状态永久等待~~ ✅ 已修复（2026-08-16，R1）

`recv_callback()` 解析包头后立即检查声明长度是否超过接收缓冲容量；缓冲溢出或超限时发送
`PKT_ERROR`、清理回调与偏移并关闭连接，不再等待一个永远无法收满的包。BATCH 还严格校验条数、
精确负载长度和 32 位乘法边界。

### ~~C8 Voter 两处配置语义漂移~~ ✅ 已修复（2026-08-16，R1）

`voter_configure_and_verify()` 成为唯一寄存器配置/回读入口，`IN_BEATS` 固定按
`records × 6` 下发；`PIPE_VOTER_PREP` 只做 cache 准备，`PIPE_VOTER_START` 统一调用 helper。
经 `rg` 确认 `validate_ddr_addresses()` 与 `analyze_decoder_output()` 无调用后删除，保留实际使用的
`validate_decoder_written_beats()`。

### ~~C9 上位机静默截断/补齐协议输入~~ ✅ 已修复（2026-08-16，R2）

`first.py` 原来把超过 81,000 bit 的水印静默截到 81,000 bit，读段生成数不符也只打印 WARN；
`ClientConfig.resolve_total()` 还会把超上限数量静默压到 `MAX_TOTAL_READS`。现在水印只读一次并由
`TaskSpec.watermark_bits` 严格校验，非 0/1 字符、位数不符、读段文件提前结束、非法 batch/limit
和超容量全部抛出可诊断异常。

### ~~C10 上位机协议/任务配置散落在 first.py~~ ✅ 已重构（2026-08-16，R2）

新增 `clients/python/task_protocol.py`（`TaskSpec`/`TaskCaps`、几何、CONFIG CRC）与
`clients/python/protocol.py`（包编解码、ACK、CAPS/CONFIG）；`first.py` 只保留文件编码与会话编排，
GUI 继续只调用其公共入口。`PKT_RESULT` 同时新增 8,100 B 精确长度校验，`--no-post` 不再继续等待结果。

### ~~C11 GUI LDPC 路径仍强制 Windows EXE~~ ✅ 已修复（2026-08-16，R2）

新增 `clients/python/native_ldpc.py` 承接 P5 的可审计核心；`ldpc_pipeline.py` 的 `auto`/`native`
均使用原生实现，只有显式 `external` 才启动 EXE，且 DLL 缺失会在启动前报错。`tools/ldpc_decode.py`
与 GUI 共用同一核心，避免两份算法漂移。

**判据**：12 项 Python 单测通过；`bash tools/run_sim.sh` 通过 9 项、失败 0 项；
真实 `ldpc_pipeline(auto)` 对 `tests/golden/dec_input.txt` 5 轮收敛，输出 54,000 bit，JPEG SHA-256
为 `fcd0cf90bd680e7bbdc203e3398119504da0897acac9e2117008b4efb6b1f2c3`。

---

## 已验证的构建结果（2026-08-08，Vivado/Vitis 2022.2，WSL `/tools/Xilinx`）

### 综合（xc7z010clg400-1 @ 100 MHz）

| 模块 | LUT | FF | BRAM36 | DSP | WNS | 结论 |
| --- | ---: | ---: | ---: | ---: | ---: | --- |
| `srpe_batch`（含 B2/B10/B11/B12 修复） | 3,304（18.8%） | 3,665（10.4%） | 8（13.3%） | 0 | **+0.777 ns** | ✓ 可综合、时序收敛 |
| `desparsification_decoder_v1_0`（控制层重写版） | 939 | 770 | 0 | 0 | **+1.856 ns** | ✓ 可综合、时序收敛 |
| `differential_voter_v1_0`（B13~B16/C4 + SCORE_MIN 版，2026-08-16） | 1,045 | 1,871 | 30 | 0 | **+2.480 ns** | ✓ 可综合、时序收敛（≈133 MHz 上限）；`hw/build/synth_differential_voter_v1_0/` |

本轮所有 RTL 改动都已确认**可综合且在 100 MHz 收敛**，不只是仿真通过。

### PS 侧

`xsct sw/scripts/create_vitis.tcl` 现在可以从 XSA 一路跑到 ELF：

```
platform: dna_platform（从 hw/build/export/hardware.xsa）
ELF     : sw/workspace/dna_lwip_app/Debug/dna_lwip_app.elf  (917,780 B)
段大小  : text 138,087  data 3,116  bss 3,266,624
关键符号: tcp_new / tcp_bind / xemacif_input / XAxiDma_CfgInitialize
          / start_application / run_processing_pipeline  均已链接
```

**这意味着 B1、B3 等 PS 侧改动从此可以编译验证，不再只能靠代码审查。**

2026-08-16 下午复跑：C1~C3/D1 的全部 PS 改动（实际条数、SCORE_MIN、ddr_layout、
协议校验）重建 ELF 成功——`dna_lwip_app.elf` 920,472 B，
text 140,603 / data 3,116 / bss 3,266,624。
2026-08-16 傍晚（P3 后）：`dna_lwip_app.elf` 943,120 B。

2026-08-16 晚（A3 后，当前可上板构建对）：

```
bitstream: hw/build/dna_accel.runs/impl_1/top_bd_wrapper.bit
           2,083,850 B  SHA-256 c3a365a02b76daff29e52acd694c2457f25cd3a44f553f169baf45f9a3f7d25f
XSA      : hw/build/export/dna_accel.xsa
           680,134 B    SHA-256 aed6f74ab5f2ef5fcd5998ddd575834e9dd68d8d4f3fbdb76065da0f87df92cf
ELF      : sw/workspace/dna_lwip_app_board_20260816/Debug/dna_lwip_app_board_20260816.elf
           943,824 B    SHA-256 fd88dce5909f522a7255ca6ae1fe114539dcefa0a2e5bef0b6ca94a00a4cfef4
段大小  : text 144,519 / data 3,148 / bss 3,266,624
BOOT.bin : hw/build/export/BOOT.bin
           2,319,112 B  SHA-256 5b7f9840cff67fc36a1c5cdcefb56a8c7581956460c4d97cab724dff8d92b711
```

XSA 内嵌 `dna_accel.bit` 与独立 bitstream SHA-256 相同；Vitis 平台目录内两份
`dna_accel.xsa` 与导出 XSA 也逐字节相同。完整实现 0 路由错误，WNS +0.145 ns、
WHS +0.018 ns；`clk_fpga_0` 与 `clk_wiz_0/clk_out1` 均为 100 MHz。`BOOT.bin` 由
同源 FSBL（SHA-256 `6575e43f...8cb78cb0`）、上述 bitstream、上述 ELF 依次组装；
Bootgen 读回确认 3 个 image/partition header，独立重生成逐字节相同。

---

## A 类 · 工程可复现性（不影响算法，但影响能否交付）

| 编号 | 问题 | 证据 |
| --- | --- | --- |
| A1 | 旧 README 的一键命令、`requirements.txt`、`client.py`、`LICENSE` 全都不存在 | 已在本次整理中重写 |
| ~~A2~~ ✅ | ~~build.tcl 路径/IP 仓库/XDC 三缺失~~（2026-08-16 修复并完整复跑）：路径按脚本位置推导；注册 `hw/ip`；XDC 进入构建；综合/实现失败立即终止；实现后正确打开 run 并输出报告到 `hw/build/reports/`。 | `hw/scripts/build.tcl`、`hw/build/reports/summary.log` |
| ~~A3~~ ✅ | ~~`bd.tcl` 未保存 PS7 DDR/MIO/PHY 配置~~（2026-08-16 修复）：从只读历史 XSA 的 `design_1.hwh` 固化 MT41J128M16、GEM0 MIO16..27、MDIO MIO52..53、UART1 MIO48..49、Bank1 1.8V、FCLK0 100 MHz、GP0/HP0；四个 AXI-Lite 地址与历史 XSA/PS 常量固定一致。新 XSA 已成功生成 lwIP BSP 和 ELF。 | `hw/scripts/bd.tcl`、`hw/build/.../top_bd.hwh`、当前构建哈希 |
| ~~A4~~ ✅ | `clients/python/requirements.txt` 已补 `numpy` / `Pillow`；`first.py` 已移除 `dataclass(slots=True)`，当前最低 Python 为 3.8。 | `clients/python/requirements.txt`、`clients/python/first.py:114` |
| ~~A5~~ ✅ | 已删除（2026-08-07） | 原：`gui_app.spec` 仍把 `dec_input.txt` 打进 EXE |
| ~~A11~~ ✅ | **`sw/scripts/create_vitis.tcl` 有 4 处错误，脚本从未跑通过**（2026-08-08 全部修复）：① 第 90 行 Tcl 括号不配对，整个脚本解析即失败；② `platform reset` 在 Vitis 2022.2 里不是合法子命令；③ `domain create -runtime c` 非法（只接受 cpp/ocl）；④ workspace 为空时 `app list` 抛错而非返回空。另把相对路径改成按脚本自身位置推导。 | 实测 xsct 输出 |
| ~~A12~~ ✅ | **`sw/app/main.c` 编译不过**（2026-08-08 修复）：① 自带的 `void sleep(unsigned int)` 弱符号与 BSP 的 `void sleep(u32)` 原型冲突，直接 `error: conflicting types`；② 未包含 `lwip/priv/tcp_priv.h`，`tcp_fasttmr/tcp_slowtmr` 是隐式声明。**说明仓库里交付的 PS 源码不是产出历史 ELF 的那一份。** | 实测 arm-none-eabi-gcc |
| A5-orig | `gui_app.spec` 仍把 `dec_input.txt` 打进 EXE —— 这正是历史「用正确结果直接出图」的残留通道，必须删除 | `clients/python/gui_app.spec:10` |
| ~~A6~~ ✅ | ~~LDPC 只有 Windows EXE~~（2026-08-16，P5）：新增 `tools/ldpc_decode.py` 纯 Python min-sum 硬判决译码器（逆向了 pchk 二进制格式与 permutation 方向），黄金自检通过：88 bit 错误 5 轮收敛、info 0 错误、重建 JPEG 与 `Milk coronet.jpg` 逐字节相同。Windows EXE 仍保留给 GUI 用 | `tools/ldpc_decode.py`、`clients/python/resources/` |
| A7 | 缺 LICENSE、第三方声明（Xilinx/lwIP）、`.gitignore` | 仓库根 |
| ~~A8~~ ✅ | ~~top.xdc 与 collect_info.tcl 均为 0 字节~~（2026-08-16 补齐并实跑）：PS7 生成的 IP XDC 是 FCLK 唯一时钟源，`top.xdc` 记录无 PL 外部引脚的约束边界（删除 XDC 不支持的 `if`）；collect_info 产出 util/timing/summary。实现报告确认两个相关时钟均为 100 MHz。 | `hw/constr/top.xdc`、`hw/scripts/collect_info.tcl`、`hw/build/reports/` |
| ~~A9~~ ✅ | ~~tb_dna_quick 把 AWVALID/WVALID 固定为 0；quick_sim part 写错~~（2026-08-16 修复）：TB 改为标准 axil_write 任务真正写入 preload/start；fork/join_none（SystemVerilog）重构为独立 initial+使能标志；quick_sim part 改为 xc7z010clg400-1。Icarus -g2005 语法通过（该 TB 仍是冒烟级，非黄金判据） | `hw/ip/Dna_accelerator_core_1_0/hdl/tb_dna_quick.v`、`vivado_quick_sim.tcl` |
| ~~A10~~ ✅ | **LDPC EXE 缺 3 个 MinGW 运行时 DLL，在干净机器上会静默失败**（2026-08-13 已修复并验证）。缺 `libstdc++-6.dll`/`libgcc_s_seh-1.dll`/`libwinpthread-1.dll` 时 EXE 无输出、无报错、退出码 0。DLL 已提取进 `clients/python/resources/`，且 `run_ldpc_decoder()` 会把它们与 EXE/`.pchk`/`permutation64800` 一起拷进临时工作目录，缺失时打警告并提示 `tools/extract_ldpc_dlls.py`，运行后还有输出缺失检查兜底报错（不再静默）。**判据**：① 拷贝逻辑单元验证（2026-08-13 实测通过，可复跑）——3 个 DLL 经 `resource_path`/`_copy_resource` 拷入临时工作目录后 SHA-256 与源一致：
```bash
python3 -c "import sys,tempfile,hashlib,pathlib,shutil;sys.path.insert(0,'clients/python');import ldpc_pipeline as lp;t=pathlib.Path(tempfile.mkdtemp(dir='.'));ok=all(hashlib.sha256(lp._copy_resource(t,d).read_bytes()).digest()==hashlib.sha256(lp.resource_path(d).read_bytes()).digest() for d in lp.DECODER_DLLS);shutil.rmtree(t,ignore_errors=True);sys.exit(0 if ok else 1)"
```
② 同源性：`tools/extract_ldpc_dlls.py` 从历史 `gui_app.exe` 重新提取的 3 个 DLL 与仓库内逐字节相同（SHA-256 一致）；③ 端到端真跑 EXE 需 Windows 可见可写路径（本环境 `/mnt/c` 只读），留待 Windows/可写 WSL 环境执行。 | `clients/python/ldpc_pipeline.py:20,88-96,135-140` |

---

## 已确认可信的部分

- 算法链路（`docs/02-data-contract.md`）已被黄金数据逐位证明。
- Stage1 的滑窗几何 `NUM_LC=50, STRIDE=807, REF_LEN=957` 与 40,500 nt / 150 bp 完全自洽，
  覆盖 0..40,350 全部合法起点，设计意图正确。
- Stage2 的投票机制（±1 饱和累加、`vote>0` 判决）与位平面地址计算逻辑正确，
  且已用黄金向量逐位证明（2026-08-16）。
- Stage3 的 `conv40_32` **函数形式**正确（标志位取反 + 4 bit 数据），只是标志位取在了组的另一端。
- 两份历史 XSA 字节相同（SHA-256 `79c64736...`），只作为板级配置反推来源；当前 Tcl
  已可复现生成新 XSA（SHA-256 `aed6f74a...92cf`）及匹配 ELF，但最终正确性仍须 G3 上板验收。
  历史 XSA 内的旧 bitstream 仍是 B13~B16 修复前版本，禁止与当前构建对混用。
- 三个当前综合顶层通过 Icarus Verilog 语法检查（非功能验证）。
