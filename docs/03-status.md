# 03 · 现状与缺陷清单

初始审计：2026-08-06；代码与回归复核：2026-08-10。证据全部标注了 `文件:行号`，可直接跳转复核。

---

## 一句话现状

**代码已修复多处关键数据通路，但没有板端端到端正确性证据。** 未闭合的主路径是：

- **D1 反向互补的板端取舍未完成**：上位机已能发送两个方向，但 Stage1/Voter 尚未按 `score`
  配对择优或加权，不能把“双份发送”等同于正确处理；
- **Stage2 Voter 尚未有黄金 RTL Testbench**，其 PS 配置仍固定使用 `TOTAL_READS=108000`；
- **C1～C3、A 类工程问题**仍在，尤其是读段数、尾批、DDR 布局和可复现构建；
- 所有 RTL/PS 回归均为离线仿真或构建，尚无“真实 FPGA 回传 → LDPC → 图片哈希”的验收。

**已完成**：
- 2026-08-07 · Stage3：B5、B6 修复；B7/B8/B9 通过重写控制层解决，最苛刻从机条件下逐位通过。
- 2026-08-08 · Stage1：B2、B4 修复；又发现并修复 B10/B11/B12 三个流水线错位，
  一批 64 条读段的 pos/score 与黄金模型完全一致。
- 2026-08-08 · 上位机：`first.py` 补上反向互补（D1 的软件半边）与 LSB-first 打包，
  编码逐字节与黄金模型相同。
- 2026-08-10 · 复跑：黄金模型、Stage1、Stage3（数据通路与 AXI）、PS 水印展开主机单测
  和综合顶层语法检查全部通过，详见 `docs/08-handoff-2026-08-10.md`。

**Stage1 与 Stage3 的核心运算已经用黄金 RTL 仿真证明；B1 已用主机单测证明 PS 展开几何。**
**B3 已接入 PS 状态机，但其输入仍依赖未经验证的 Stage2。**
剩余：D1 板端取舍、D2、C1～C3、A 类，以及 Stage2/整链/上板验证。

同时，**算法本身已经被证明是正确可行的**：`tools/golden_model.py verify-code` 用 R0.83
黄金数据证明了「编码序列 ⊕ 水印 → 5b4b → 码字」逐位成立。所以要做的是把 RTL 对齐到
已验证的模型，而不是重新发明算法。

---

## D 类 · 算法缺口（比所有实现 bug 更靠前）

### D1 反向互补读段的板端判别与取舍尚未完成 —— 全项目最高优先级

实测（`tools/golden_model.py`，SE150 前 400 条）：

| 比对方式 | 与真实编码序列一致度 ≥140/150 的比例 |
| --- | --- |
| 仅正向 | 50.7% |
| 仅反向互补 | 48.0% |
| 两方向取更优 | **98.8%**（平均 148.9/150） |

**这批数据里约一半读段是反向互补的**。`clients/python/first.py` 已能把每条原始读段的
正向和反向互补版本都编码并发送（默认 `--orient both`），这是 D1 的主机侧准备；但
`srpe_batch` 仍只对单条输入做正向比对，`differential_voter_v1_0.v` 也没有使用 `score`
把同源的两份结果择优或加权。因此错误方向仍会参与投票，**当前板端路径没有完成 D1**。

后果与修复效果都已用全量 51,781 条读段量化：

| 软件模型（全部 51,781 条，191× 覆盖） | 共识误码率 | 码字误码率 | LDPC 实测结果 |
| --- | ---: | ---: | --- |
| 不处理反向互补（= 当前实现） | 1.33%（1,078 bit） | **2.33%**（1,507 bit） | ❌ `Decoding failed!`，图片错 |
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

**即使其余 B 类修复都在，若不完成方向取舍也不会得到正确图片。** 方案见 `docs/04-roadmap.md`。

### D2 比对分被算出来却从未使用

`srpe_batch` 输出 `score`，Voter 在 `differential_voter_v1_0.v:440` 把它存进
`current_score`，然后**再也没有用过**。所有读段（包括比对失败的）等权投票。
注意：实测简单阈值过滤会因丢失覆盖而更差（阈值 75 时误码率反升到 3.3%），
应当用加权投票而不是直接砍掉。

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

### C1 读段条数由固定宏决定，而非实际收到的条数

- `sw/app/echo.c:634-669,708-740,785,870-895` 用 `TOTAL_READS`（108,000）配置 Voter 的
  cache 范围、`IN_BEATS`/`TOTAL_READS`，而 SE150 实际只有 51,781 条
  → Voter 会把约 5.6 万条 DDR 残留数据当成读段投进去。
- `clients/python/first.py:499-518` 已能检测输入条数、允许指定数量并补齐到 64 的倍数；
  但这只保证官方客户端的发送量，PS 并未把 `conn->total_reads_received` 传给 Voter。
- `dna_connection_t.total_reads_received` 已经存在且在 Stage1 里被正确使用
  （`echo.c:499-518`），Stage2 只是没用它。**这是一处低成本高收益的修复。**

### C2 非 64 整数倍的尾批可能卡死

`srpe_batch` 每批固定处理 `BATCH=64` 条；51,781 = 64×809 + 5。官方 `first.py` 已将发送量
向上补零到 64 的倍数，这避免了该客户端触发空 FIFO；但 PS 协议没有声明或校验此条件，
任意第三方客户端或非 64 倍数任务仍会让 `PIPE_TX_PREFILL` 发送一整帧并读取 DDR 残留。
要彻底支持任意条数，仍需引入“本批有效条数”或由 PS 在协议层显式填充并传递实际条数。

### C3 DDR 布局按 108,000 条预留

`echo.h:41-79` 的地址表按 108,000 条计算（Stage1 输出 5.184 MB）。
实际条数变化时，各缓冲区上界、cache flush/invalidate 范围都要跟着算，
目前是硬编码常量。

---

## 已验证的构建结果（2026-08-08，Vivado/Vitis 2022.2，WSL `/tools/Xilinx`）

### 综合（xc7z010clg400-1 @ 100 MHz）

| 模块 | LUT | FF | BRAM36 | DSP | WNS | 结论 |
| --- | ---: | ---: | ---: | ---: | ---: | --- |
| `srpe_batch`（含 B2/B10/B11/B12 修复） | 3,304（18.8%） | 3,665（10.4%） | 8（13.3%） | 0 | **+0.777 ns** | ✓ 可综合、时序收敛 |
| `desparsification_decoder_v1_0`（控制层重写版） | 939 | 770 | 0 | 0 | **+1.856 ns** | ✓ 可综合、时序收敛 |

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

---

## A 类 · 工程可复现性（不影响算法，但影响能否交付）

| 编号 | 问题 | 证据 |
| --- | --- | --- |
| A1 | 旧 README 的一键命令、`requirements.txt`、`client.py`、`LICENSE` 全都不存在 | 已在本次整理中重写 |
| A2 | `hw/scripts/build.tcl` 用 `[pwd]/../..` 推导仓库根；没有 `ip_repo_paths`/`update_ip_catalog`；不读 XDC | `hw/scripts/build.tcl` |
| A3 | `bd.tcl` 只调 `apply_bd_automation`，PS7 的 DDR 型号/MIO/PHY 全没保存；生成的是 `top_bd`，而 XSA 内是 `design_1`，两者不同源 | `hw/scripts/bd.tcl`，XSA 内 `design_1.hwh` |
| ~~A4~~ ✅ | `clients/python/requirements.txt` 已补 `numpy` / `Pillow`；`first.py` 已移除 `dataclass(slots=True)`，当前最低 Python 为 3.8。 | `clients/python/requirements.txt`、`clients/python/first.py:114` |
| ~~A5~~ ✅ | 已删除（2026-08-07） | 原：`gui_app.spec` 仍把 `dec_input.txt` 打进 EXE |
| ~~A11~~ ✅ | **`sw/scripts/create_vitis.tcl` 有 4 处错误，脚本从未跑通过**（2026-08-08 全部修复）：① 第 90 行 Tcl 括号不配对，整个脚本解析即失败；② `platform reset` 在 Vitis 2022.2 里不是合法子命令；③ `domain create -runtime c` 非法（只接受 cpp/ocl）；④ workspace 为空时 `app list` 抛错而非返回空。另把相对路径改成按脚本自身位置推导。 | 实测 xsct 输出 |
| ~~A12~~ ✅ | **`sw/app/main.c` 编译不过**（2026-08-08 修复）：① 自带的 `void sleep(unsigned int)` 弱符号与 BSP 的 `void sleep(u32)` 原型冲突，直接 `error: conflicting types`；② 未包含 `lwip/priv/tcp_priv.h`，`tcp_fasttmr/tcp_slowtmr` 是隐式声明。**说明仓库里交付的 PS 源码不是产出历史 ELF 的那一份。** | 实测 arm-none-eabi-gcc |
| A5-orig | `gui_app.spec` 仍把 `dec_input.txt` 打进 EXE —— 这正是历史「用正确结果直接出图」的残留通道，必须删除 | `clients/python/gui_app.spec:10` |
| A6 | LDPC 只有 Windows EXE，无源码/无 Linux 路径 | `clients/python/resources/` |
| A7 | 缺 LICENSE、第三方声明（Xilinx/lwIP）、`.gitignore` | 仓库根 |
| A8 | `hw/constr/top.xdc` 与 `hw/scripts/collect_info.tcl` 均为 0 字节 | — |
| A9 | `tb_dna_quick.v` 把 AXI-Lite `AWVALID`/`WVALID` 固定为 0，控制寄存器从未真正写入；`vivado_quick_sim.tcl` 的 part 写成 `xc7z020clg484-1`（实际是 `xc7z010clg400-1`） | `hw/ip/Dna_accelerator_core_1_0/hdl/` |
| A10 | **LDPC EXE 缺 3 个 MinGW 运行时 DLL，在干净机器上会静默失败**（无输出、无报错、退出码 0，极易被误判成数据问题）。缺的是 `libstdc++-6.dll`、`libgcc_s_seh-1.dll`、`libwinpthread-1.dll`；它们只存在于历史 `gui_app.exe` 内部。已用 `tools/extract_ldpc_dlls.py` 提取并补进 `clients/python/resources/`；**`ldpc_pipeline.py` 还需要把它们一起拷进临时工作目录**（目前只拷 3 个数据文件）。 | `clients/python/ldpc_pipeline.py:85-87` |

---

## 已确认可信的部分

- 算法链路（`docs/02-data-contract.md`）已被黄金数据逐位证明。
- Stage1 的滑窗几何 `NUM_LC=50, STRIDE=807, REF_LEN=957` 与 40,500 nt / 150 bp 完全自洽，
  覆盖 0..40,350 全部合法起点，设计意图正确。
- Stage2 的投票机制（±1 饱和累加、`vote>0` 判决）与位平面地址计算逻辑正确。
- Stage3 的 `conv40_32` **函数形式**正确（标志位取反 + 4 bit 数据），只是标志位取在了组的另一端。
- 两份 XSA 字节相同（SHA-256 `79c64736...`），内含可用的 bitstream 与 `ps7_init.tcl`，
  可作为「历史硬件快照」用于板级回归，但不是当前 Tcl 的可复现产物。
- 三个当前综合顶层通过 Icarus Verilog 语法检查（非功能验证）。
