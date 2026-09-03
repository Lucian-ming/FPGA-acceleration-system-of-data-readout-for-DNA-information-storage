# 03 · 现状与缺陷清单

初始审计：2026-08-06；代码与回归复核：2026-08-10；Stage2 黄金 Testbench：2026-08-16；
离线任务全量完成（D1/D2、C1~C4、A2/A3/A8/A9、P5）：2026-08-16。证据全部标注了 `文件:行号`，可直接跳转复核。

---

## 一句话现状

> **2026-08-30 更新：G3 已闭环。** 第五次上板（B26+B27 修复后重建的 bitstream/ELF）回传数据
> 经 `tools/ldpc_decode.py` 译码，图片 SHA-256 = `fcd0cf90bd680e7bbdc203e3398119504da0897acac9e2117008b4efb6b1f2c3`，
> 与判据逐位相同。详见下面「第五次上板」一节。以下段落是闭环前的历史现状描述，保留备查。

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
- 2026-08-29 · **板级 DDR 配置修正（G3 硬阻塞）**：导入并核验目标板资料
  `docs/board/zynq-eco-7010/`（15 个文件 SHA-256 全通过），确认实物为 **ZYNQ ECO R6**。
  硬件规格说明书明确要求「配置 DDR3 必须是 16 位，默认配置 32 位，如果不更改不能运行」，
  而 `bd.tcl` 固化的是 32 bit 双颗 `MT41J128M16`。**直接解包 `design_2_wrapper.xsa` 核实：
  历史 XSA 自身就是 32 bit 双颗，属于另一块板**，`bd.tcl` 只是忠实复制了它。
  已改为 `16 Bit` + `MT41J256M16 RE-125` + `4096 MBits`（`T_RC` 同步为 48.91），
  BD 重新生成 0 错误、地址图与修改前逐行一致。影响面很窄：DDR 总容量仍 512 MiB，
  `echo.h` 地址布局不动，PL 侧（RTL/IP/XDC/时序）完全不受影响；代价是 DDR 带宽减半，
  对本流水线无实质影响。**后果：`hw/build/export/` 全套制品作废，必须重建后才能上板。**
  详见 `docs/16-board-zynq-eco-7010.md`。

同时，**算法本身已经被证明是正确可行的**：`tools/golden_model.py verify-code` 用 R0.83
黄金数据证明了「编码序列 ⊕ 水印 → 5b4b → 码字」逐位成立。所以要做的是把 RTL 对齐到
已验证的模型，而不是重新发明算法。

---

## 第五次上板（2026-08-30）：G3 端到端闭环 ✅

烧录的是 B26（DNA 核入口采样错位）+ B27（Decoder 被固件的第二次 START 写重启）
两处修复后**重新综合实现**的制品；PS 配置未动（`ps7_init.tcl` 与上一版逐字节相同）。

| 项 | 值 |
| --- | --- |
| 实现收敛 | WNS **+0.088 ns** / WHS **+0.016 ns**，0 failing endpoint，0 error / 0 critical warning |
| bitstream | `hw/build/export/top_bd_wrapper.bit` |
| 固件 | `hw/build/export/dna_lwip_app_b27.elf`（`sw/boot/dna_board_b27.bif` → `BOOT.bin`） |
| 上板方式 | JTAG（`D:\dna_board_smoke\boot_b27.tcl`：rst -system → fpga → ps7_init → dow → con） |
| 上位机命令 | `first.py --limit 2048 --orient both --score-min 67`（4,096 条正反记录） |
| 回传 | `Result: 8100 bytes, 32.56s` |
| LDPC | **起始失败校验 332，5 轮收敛**，输出 54,000 bit（第四次是 50 轮后仍有 5,215 个失败校验） |

### 唯一判据 ✅

```
sha256(重建 JPEG) = fcd0cf90bd680e7bbdc203e3398119504da0897acac9e2117008b4efb6b1f2c3
判据要求          = fcd0cf90bd680e7bbdc203e3398119504da0897acac9e2117008b4efb6b1f2c3
```

**逐位相同。G3 闭环。**

### 逐级留证（XSDB 只读 DDR，不复位不重烧；备份在 `D:\dna_board_smoke\run5_dumps\`，含 SHA256SUMS）

| 级 | 板上 DDR | 与黄金比对 | 第四次 | 第五次 |
| --- | --- | --- | --- | --- |
| 展开水印 | `0x10040000` | vs `tests/golden/wm_regions.hex` | 47,850/47,850 ✅ | **47,850/47,850** ✅ |
| Stage1 输出 | `0x10600000` | vs `tests/golden/stage2_in.hex`，整条 48 B 相同 | 4,009/4,096 | **4,011/4,096** |
| Stage1 码字 | 同上 | 与黄金**同序号**相同 | 4,094/4,095（错位一条） | **4,096/4,096** ✅ |
| Stage2 ⊕ 水印 | `0x11000000` | vs `tests/golden/sparse_expect.hex` | 比特误码 0/81,000 ✅ | **0/81,000** ✅ |
| Stage3 输出 | `0x11100000` | vs `tests/golden/stage3_expect.hex` | **0/1,013 字，误码 49.47%** ❌ | **1,013/1,013 字，误码 0/64,800** ✅ |

缺陷特征全部消失：

```
B23 特征（每条记录 word4 == word5）        : 0 / 4,096
B26 特征（board 记录 i 的码字 == 黄金 i+1）: 0 / 4,095
```

Stage1 剩下 85 条与黄金不同的记录，经拆解是 **score 相同、码字相同、只有 position 不同** ——
同分并列时 RTL 与 Python 黄金模型选了不同的位置，不是缺陷；LDPC 起始失败校验 332
（远低于纠错能力）也印证了这一点。

UART 实录也印证 B27 修好了：`[STAGE3] ✓ DONE flag set after 1 polls`
（第四次要靠「输出区哨兵被覆盖」的旁证收尾）。

### 闭环那一版 RTL 的完整回归（2026-08-30 复跑）

| 回归 | 结果 |
| --- | --- |
| `tools/run_xsim.sh all` | **9/9 PASS**（含 B26 的 `ingress_result`、B27 的 `dec_restart`） |
| `tools/run_m2_full.sh` | 全链 PASS：Stage1 64/64 批、Stage2 81,000 bit、Stage3 64,800 bit；LDPC 图片哈希 `fcd0cf90…f2c3`；单 bit 故障注入被 Stage3 scoreboard 检出 |
| `tools/run_m3_bd.sh bd2` | PASS |
| `tools/run_m3_bd.sh bd3ext` | **8/8 PASS**：BEST_CASE 与 WORST_CASE 两档下 Voter / Stage2 逐位 / Decoder / Stage3 逐位全通过 |
| `tools/run_m3_bd.sh bd3b` | PASS（AXI DMA → DNA 入口逐条判据 + 故障注入，见 `b866c49`） |

复跑过程中另外揪出并修掉一个**与 B26/B27 无关的既有 TB 缺陷**（提交 `aec5ce7`）：
`tb_m3_bd3_extmem.sv` 的背压用 `XIL_AXI_READY_GEN_RANDOM` + `forever send_*ready(g)`，
而该策略的 ready 对象是一次性的（`event_count` 默认 1）、`send_*ready()` 又非阻塞，
于是无限排队撞上 VIP 的 500 上限，配合 `Stop-On-Error=0` 把日志刷到 16 GB、
xsim 被 OOM 杀掉 —— 此时 DUT 一拍数据都还没传。改用自持的
`XIL_AXI_READY_GEN_OSC` 只 send 一次即可。详见 `docs/15` §9.1。

### 闭环的适用范围

第五次上板当时只成立于**这一次运行、这一组参数**（4,096 条记录、单次任务）。
**2026-08-30 当日又跑了 6 轮，把范围扩到了全量与二次任务** ——
见下面「第六~十次上板」一节。

### 这一轮之后的状态

- G3（板端端到端验收）**关闭**。
- 剩余：A7（LICENSE 需要用户确认权属与许可证类型）、P7（Stage1 架构改造，追求更高吞吐时再做）、
  以及 SE250 几何参数化（现有比特流只支持 SE150 150 bp）。

---

## 第六~十次上板（2026-08-30）：规模与状态复位边界 ✅

这 6 轮全部由 `tools/run_g3.sh` 驱动（P0 交付物，提交 `2f189a2`），
烧的是同一份制品（bitstream `7d125520…b21f9d1`、ELF `9006d0ca…fead0bd`，
每轮开跑前先按 `hw/build/export/SHA256SUMS` 校验，不符即停）。
**RTL 与固件一行未改** —— 这几轮验的是既有实现的适用边界，不是新修复。

### 结果总表（唯一判据：图片 SHA-256 = `fcd0cf90…f2c3`）

| 轮次 | 参数 | 记录数 | result 耗时 | 唯一判据 | 四级取证 |
| --- | --- | --- | --- | --- | --- |
| 6 | 默认（P0 自检） | 4,096 | 33.08 s | ✅ 逐位相同 | 4/4 ✅ |
| 7 | `--limit 4096` | 8,192 | 37.06 s | ✅ | 4/4 ✅ |
| 8 | `--limit 8192` | 16,384 | 45.36 s | ✅ | 4/4 ✅ |
| 9 | `--limit 16384` | 32,768 | 61.59 s | ✅ | 4/4 ✅ |
| **10** | **`--full`（全量）** | **103,616** | **132.67 s** | **✅** | **4/4 ✅** |
| **11** | **`--runs 2`（二次任务）** | 4,096 ×2 | 33.15 / 33.31 s | **✅ 两轮均相同** | 4/4 ✅ |

留证：`docs/board/run-logs/run9-uart-full-dataset-2026-08-30.log`、
`run10-uart-2runs-reset-2026-08-30.log`，以及各轮 `*-summary.txt`。

### 全量数据集 ✅

**103,616 条记录**（51,781 × 2 = 103,562，`first.py:322` 向上取整到 64 的倍数；
`docs/18`/`docs/19` 先前写的 103,552 是向下取整，差 64 条）。
容量结论不变：103,616 ≤ `TASK_MAX_READS` 107,968，Stage1 输出 4.74 MB ≤ 预算 4.94 MB。

规模效应三项均未出问题：RX BD 环回绕 202 次、TX 1,619 帧、
`srpe_batch` 的 partial batch idle timeout 在最后一批无异常。
LDPC 起始失败校验 **33**（4,096 条那档是 332）—— 读段越多投票证据越足，符合预期。

⚠️ **口径说明**：全量下 Stage1/Stage2/Stage3 的黄金向量仍是按 2,048 条源读段生成的，
所以四级取证里 Stage2 比特误码 0.16%、Stage3 0.12%，**不再是逐位相同**。
这不是缺陷（更多读段参与投票，结果本就会略有不同），
但也意味着**全量下四级取证只是容差内的旁证，真正的判据仍然只有图片 SHA-256**。

### 二次任务 / 状态复位 ✅ 已全部覆盖（累加器那条于 2026-08-31 补齐）

`docs/12` §11 挂了很久的「二次任务是否真正清零 Voter 累加器」**已在板上回答：是**。
但**第一版判据（两轮同参数）回答不了它**，原因见下面的盲区说明；
补齐它靠的是「第一轮换个 `score_min` 把累加器弄脏」，见本节末尾。

**先厘清**：「同一次**连接**内跑两次任务」现有协议**不支持**，且是设计如此不是缺陷 ——
`conn->configured` 对重复 `PKT_CONFIG` 直接拒绝（拒绝码 8，`echo.c:1691`），
而 WM/BATCH/POST 都要求 `configured`（`echo.c:1905`、`:2013`、`:2059`）。
真正有风险、也确实该验的是「**同一次上电内、两条连接**」：
`accept_callback` 只 memset 软件侧的 `g_conn`（`echo.c:1866`），
硬件状态（Voter 累加器、BD 环指针、DNA 核、Decoder）并不随新连接复位。

| 判据 | 结果 |
| --- | --- |
| 两轮图片 SHA-256 都等于 `fcd0cf90…f2c3` | ✅ |
| **两轮回传比特流逐位相同（64,800 bit，`cmp` 无差异）** | ✅ |
| **两轮 LDPC 起始失败校验相同（均 332，均 5 轮收敛）** | ✅ |

**后两行的价值**：只比最终图片哈希，无法排除「第二轮中间结果略有不同、
但被 LDPC 纠了回去」。回传比特流逐位相同、起始失败校验也一模一样，排除了这种可能，
说明第二次任务的板端中间结果与第一次完全一致。据此覆盖到的是
**B21 的 BD 环指针、B27 的 START 语义、Stage3 的 `done` 清除时机**这三个雷区。

#### ⚠️ 盲区：这条判据**证明不了 Voter 累加器被清零**

两轮用的是**同一份输入**，而在同输入下「累加器没清零」在输出上**结构性不可观测**——
这不是「这组数据碰巧测不出」，而是可以证明的：

每位累加器的更新是 `x ← clip(x ± 1)`（`differential_voter_v1_0.v` 的 `S_VOTE_UPDATE`：
`bram_din <= safe_vote_value(bram_dout ± 10'sd1)`），±1 的方向只取决于读到的符号、
**不取决于累加器当前值**，所以同输入同 `score_min` 下两轮的增量序列逐条相同。
`x ↦ x+d` 单调不减、`clip` 单调不减，复合仍单调不减 ⇒ 整条轨迹对**起始值**单调不减。
设第一轮终值 `v`、残留时第二轮终值 `w`，输出位是符号判决
（源码注释原话：「按补码语义：非负且非零才是 1」）：

- `v > 0` ⇒ 起点更高 ⇒ `w ≥ v > 0`，判决同为 1
- `v < 0` ⇒ 起点更低 ⇒ `w ≤ v < 0`，判决同为 0
- `v = 0` ⇒ 起点相同 ⇒ 轨迹逐拍相同 ⇒ `w = 0`，判决同为 0

**饱和不需要单独讨论**——它就在 `clip` 里，不破坏单调性。
（直觉上「撞了 +511 丢信息、之后可能跨过零点」是不会发生的：轨迹一旦撞顶就把起始偏移
「忘掉」了，两轮反而更容易收敛到同一个值，而不是发散。）

**推论：加大规模、多跑几轮都是白跑**——只要第二轮用同一份输入和同一个阈值，
无论多少条读段都测不出累加器没清零。

所以「比得更细」在这一条上没有任何鉴别力——**逐位相同正是该缺陷的必然输出**，
不是它不存在的证据。这一点由 `run_xsim.sh vot_ddr` 的 `inject=c4` + `+second_score_min=67`
实测坐实：清零被完全压制，两轮输出仍然逐位相同，TB 自己打出「判据没有鉴别力」（见本文 §vot_ddr）。

仿真侧由 `vot_ddr` 的 `fw-second-task` 场景覆盖（第二轮换 `SCORE_MIN=0`，逐位通过；
`inject=c4` 在该场景下报 4.49% 误码，判据有鉴别力）。

#### ✅ 板级补齐（2026-08-31，第十二次上板）

思路和仿真侧一样：**让第一轮用不同的 `score_min` 把累加器弄脏**，
残差与判据轮的增量不同向，没清零就会翻符号、露馅。

    tools/run_g3.sh --runs 2 --first-run-score-min 0

| 步骤 | 结果 |
| --- | --- |
| 第 1 轮（弄脏轮，`score_min=0`） | 32.33 s；板端输出与判据轮差别大到 LDPC 译不出来（预期之内，不作判据） |
| 第 2 轮（判据轮，`score_min=67`） | 32.84 s，图片 SHA-256 = `fcd0cf90…f2c3` **逐位相同** ✅ |
| **弄脏轮鉴别力自证** | 两轮板端**原始回传**（pre-LDPC）相差 **6,277/64,800 bit** ✅ |
| 四级 DDR 取证 | 4/4 ✅（Stage2 误码 0.02%、Stage3 0.00%） |

**第三行是这条判据成立的前提**，不是附赠信息：如果弄脏轮没能让板端输出变样，
就说明它压根没在累加器里留下不同向的票，那第二轮通过也证明不了任何事。
`run_g3.sh` 把它做成了硬判据——两轮原始回传若相同，**报 FAIL 而不是 PASS**。
（这正是第一版判据的教训：一条不会失败的判据，通过了也没有信息量。）

结论：**Voter 累加器在两次任务之间确实被清零了**，而且是在 `echo.c:861` 的
`clear_voter_out_region()` 仍被注释掉的前提下 —— 说明清零不依赖那段固件代码。

**「为什么不需要」已查清（2026-08-31）：是 RTL 在每次 START 时自清。**

- `differential_voter_v1_0.v` 的修订 **C4**：原实现靠 `bram_initialized` 只在**首次**
  START 清零，第二次任务会在上一轮旧票上叠加；改为 `S_IDLE --start_latched_pulse-->
  S_INIT_BRAM`，**每次 START 都走清零路径**，把 `bram[0..TOTAL_BITS-1]` 全写 `10'sd0`
  （81,000 拍 ≈ 0.81 ms @100 MHz）。
- 清零范围受 `FAST_INIT` 控制：为 1 时只清前 64 格。**实测本设计恒为 0**——
  RTL 默认 `parameter integer FAST_INIT = 0`、`component.xml` 的
  `MODELPARAM_VALUE`/`PARAM_VALUE` 均为 0、BD 实例化
  （`top_bd_differential_voter_0_0.xml`）也是 0。三处一致，全 81,000 格都清。
- 另外 `clear_voter_out_region()` 清的是 **DDR 输出区**，与累加器 BRAM 不是一回事；
  而且该函数**在 `sw/` 下已无任何定义**，`echo.c:875` 只剩一行注释掉的调用。
  也就是说它不是「被停用的保险」，而是一段死文本——**没有可恢复的东西**。
  建议连同注释一起删掉，免得下一个人再花时间判断它是不是被误关的安全网。
- 六个配置寄存器（`IN_ADDR`/`IN_BEATS`/`OUT_ADDR`/`OUT_BEATS`/`TOTAL_READS`/`SCORE_MIN`）
  每次任务都按本次实际条数重写并逐个回读校验（`echo.c:829-834`），
  所以第二次任务的读写长度不会沿用上一次的。

留证：`docs/board/run-logs/run12-uart-reset-dirty-2026-08-31.log`、
`20260831T022122Z-reset-dirty-v2-summary.txt`。

⚠️ 仍未验证：三轮以上、跨不同**规模**的连续任务（如先全量再 2,048 条）、长时间连续运行。

### 板端处理时长（顺带量化，`tools/g3_timing_fit.py` 可复跑）

**`t = 28.90 s + 1.0012 ms/条 × 条数`，五档实测 4,096~103,616 条，R² = 1.00000。**

> ⏳ **这个式子正在被改掉，但还没有新的实测**（2026-09-04）。
> 水印预载批量化已提交（`a2a8067`，`sw/app/echo.c`），把预载从 ≈100 个 poll 步
> 压到 5 步；`run_xsim.sh all` 13/13、`run_sim.sh` 11/11 都过了，
> **但上板 `run_g3.sh` 一次都没跑过**，改前/改后的拟合对照也还没有。
> 在实测数字出来之前，**上面这个式子仍然是当前唯一有效的时长模型** ——
> 不要拿「应该会降到 X」去替换一个实测值，那正是 `docs/18` P1 第 3 项
> 「扣除法推断被当成实测引用」的翻版。改法与判据清单见 `docs/18` P2 第 6 项。

**28.90 s 的固定开销是水印预载的约 100 个 poll 步**：
`run_processing_pipeline()` 每次 `poll_callback` 只走一个状态（`echo.c:1557-1574`），
而预载是 `PIPE_WM_TX` ↔ `PIPE_WM_WAIT` 按 50 个区域循环（`echo.c:554-586`），
与读段条数无关。4,096 条那档 **87% 的时间花在这里**。

这同时推翻了 `docs/18` 先前「全量必然超时 ≈800 s」的结论（作废理由见 `docs/18` P1 第 3 项）：
那条推断依据「水印预载走同步 DMA，UART 里 `WM_PREP` → `WM preload done` 之间没有轮询等待」，
而那两个状态**每区域一行都不打印**——**看不到打印不等于没有轮询**。
实测直接分开了两种可能：若真是 97% 随条数线性，条数翻倍应到 ~65 s，实测只到 37.06 s。

**poll 间隔的机理（已核实，非推测）**：不是注释里写的 500 ms，而是**落在 250~500 ms**，
实测反推 ~280 ms。`tcp_slowtmr()` 有两个各自独立、互不清零的驱动源同时在跑：

1. **ISR**：SCU timer 250 ms（`platform_zynq.c:174` 载入 `CPU_CLK/8`，而 SCU 时钟是 `CPU_CLK/2`），
   `timer_callback` 用 `odd` 隔一次才置 `TcpSlowTmrFlag`（`platform_zynq.c:104-113`）→ 500 ms，
   由 `main.c:282` 消费；
2. **软件兜底**：`main.c:290` 的 `slow_acc >= 500` 直接调 `tcp_slowtmr()`，
   **既不看 ISR 的脸色、也不被它清零** → 另一个 ≥500 ms 源。

`pollinterval=1` 时每次 `tcp_slowtmr` 都回调一次 poll，两个不同步的源叠加即得 250~500 ms。

这条还给了一个**不依赖拟合的独立佐证**：间隔 ≥250 ms ⇒ 水印预载那 100 步 ≥25 s；
而 4,096 档总共才 33.08 s ⇒ Stage1 ≤ 8 s。拟合出的 0.9959 ms/条 × 4,096 = 4.1 s 在此上界内，
两条独立路径互相印证。

**连带修正了 `echo.c` 三处错误注释**（`:439`、`:674`、`:1431` 原本都写「约 500 ms」），
以及据它们算出来的两个常数说明 —— 两个都**比宣称的更早触发**：

| 位置 | 原注释宣称 | 按 ~280 ms 实际 |
| --- | --- | --- |
| `S1_NO_PROGRESS_LIMIT 60` | 60 × 500 ms ≈ 30 s | **≈ 17 s** |
| Stage3 超时 240 次（`echo.c:1479`） | 240 × 500 ms ≈ 120 s | **≈ 67 s** |

⚠️ **只改了注释，没动数值**：改数值会让编译产物与 `hw/build/export/` 里已验证的 ELF 不同源，
就得整套重建 + 重新上板复验。两者当前都不构成故障（全量那轮 Stage1 一次都没误触发，
Stage3 实测 < 500 ms 就 DONE，离 67 s 差两个数量级）。
记下来是因为：**下一个照「500 ms/步」去调这两个常数的人一定会算错**，
而「拿注释当实现」正是 B22 当年翻车的同一类错误。


---

## B 类新增 · B21（2026-08-29，首次上板 G3 发现）

### ~~B21 Stage1 在板上产出约 13 条结果后硬卡死~~ ✅ 已修复并在板上验证（2026-08-29）

**现象**：首次 G3 上板，协议握手、CONFIG、水印下发、读段下发全部成功，
板端打印到 `[STAGE1] IP core START` 后再无任何输出，客户端等结果 180 s 超时。

**证据**（XSDB 只读 DDR 中的 DMA 描述符环，未复位、未重烧）：

| 观测项 | 值 |
| --- | --- |
| RX BD 环 Cmplt | **13 / 1024**，首个未完成 = 13 |
| TX BD 环 Cmplt | **69 / 2048**，首个未完成 = 69 |
| 任一 BD 的错误位（DecErr/SlvErr/IntErr） | **0** |
| RX BD 状态样本 | `0x8c000030` = Cmplt + RXSOF + RXEOF + 48 B（一条完整记录） |
| TX BD 状态样本 | `0x80000ef4` = Cmplt + 3828 B（= 957×4，水印预载） |
| 间隔一段时间复测 | RX 仍 13、TX 仍 69，**完全静止** |

**推断**：TX 的 69 个 BD 中，前 50 个是水印预载（每区域 3828 B），
其余 19 个是读段帧（每帧 64 条 × 40 B = 2560 B），即约 1,216 条读段已被 DMA 送入 DNA 核；
而 DNA 核只吐出 13 条结果就停止。无任何 AXI 错误响应，属于**功能性挂死**而非总线错误。

**为什么仿真没抓到**：M3 的 BD-3ext 只覆盖了 Voter 与 Decoder 的 AXI 主口通路；
**`AXI DMA MM2S → DNA S_AXIS` 与 `DNA M_AXIS → AXI DMA S2MM` 这条链从未在 BD 级仿真过**
（即 `docs/13` §7.2 的 BD-3 第 1、2 项，本轮未实施）。IP 级的 `tb_dna_ingress` 只验证了
FIFO 背压，没有真实 DMA、没有 50 次水印预载的区域切换时序。

**优先怀疑方向**（与 `docs/12` §11 早已列出的板端观察点一致）：
1. 水印预载 50 次区域切换时 `wm_waddr` 是否每次从 0 开始、`preload` 位与 DMA 的时序配合；
2. DNA ingress FIFO 满背压后的恢复；
3. `start` 与 `preload` 位的先后与清除时机。

### 根因（2026-08-29 已坐实，三方独立印证）

| 环节 | 事实 |
| --- | --- |
| DNA 核 | `s2mm_pack64.v` 的 `S_PACK5` 状态 `m_last <= 1'b1`：每条 48 B 结果（6 拍 × 64 bit）结尾都拉 `M_AXIS_RESULT_TLAST`，即**每条记录是一个独立 AXIS packet** |
| AXI DMA S2MM | SG 模式遇 `TLAST` 即关闭当前 BD，**一个 BD 只能收下一条记录** |
| 固件 `echo.c` | RX BD 却按「总字节 / 每 BD 最大长度」切：`ceil(196608 / 16376) = 13` 个 BD |
| 板上实测 | RX Cmplt = **13**，与上式**精确吻合**；BD 状态 `0x8c000030` = Cmplt+RXSOF+RXEOF+48 B，正是「一条记录一个 packet」 |
| 自相矛盾佐证 | 同一份固件里 `rx_expected = total_reads = 4096`，说明它本就预期每条读段回一次，与投递逻辑不一致 |

收满 13 条后 `S2MM_CURDESC == S2MM_TAILDESC`，S2MM 进入 Idle，
AXIS 反压回灌把 DNA 核连同整条链锁死——这解释了「无任何 AXI 错误位却完全静止」。

**正确做法**：RX 每个 BD 按 **48 B**（`DNA_ACC_RESULT_PACKED_BYTES`）投递，
4,096 条记录需要 4,096 个 BD，而 RX 环只有 `MAX_BD_COUNT_RX = 1024`，
**因此必须边回收边滚动补投**。

### 状态：已修复，**板上实测通过**（2026-08-29 第二次上板）

固件改动（`sw/app/echo.c`）：

1. `XFER_RX_OUT` 的 `per_bd` 改为 `DNA_ACC_RESULT_PACKED_BYTES` = 48 B；
2. 新增 `submit_rx_records()`：按 `RX_OUTSTANDING_MAX = 512` 在 1,024 个 BD 的环上
   滚动补投，`PIPE_RX_PREP` / `PIPE_TX_STREAM` / `PIPE_PROGRESS` 三处都会补；
3. `reclaim_some_bd()` 原来用 `&BdPtr[i]` **线性索引**遍历刚回收的一批 BD。
   `XAxiDma_BdRingFromHw()` 返回的是环上一段逻辑连续的 BD，**可能跨过环尾回绕**；
   RX 改成 48 B/BD 后一次任务要用掉 4,096 个 BD 而环只有 1,024 个，
   必然回绕 4 次，线性索引会读到 BD 环之外的内存——既可能把垃圾值误判成 BD 错误
   而让整条流水线 FAIL，也可能漏掉真正回绕那几个 BD 的错误位。已改为沿
   `XAxiDma_BdRingNext()` 遍历；`submit_bd_transfer()` 里那次
   `Xil_DCacheFlushRange(BdPtr, bd_count*64)` 同样是「假设一批 BD 内存连续」，
   一并改为逐个刷。
4. `dump_dma_regs()` 补上实际打印（原实现读完寄存器一行都不打印，等于哑巴看门狗），
   新增 `dump_dna_regs()`；`PIPE_TX_STREAM` 的无进展看门狗从
   `stuck_count > 10000`（按 500 ms 一次的 poll 折算约 83 分钟，等于永远打不出证据）
   改为 60 次 poll ≈ 30 s。

**板上判据（第二次上板，UART 实录）**：

```
[STAGE1] RX_PREP
  Reads: 4096
  Output: 196608 bytes (4096 x 48 B/read)
  RX BD: 1 BD/记录(48 B)，预投 512/4096 条
[STAGE1] IP core START
[STAGE1] COMPLETE!
  TX: sent=64 done=64/64
  RX: done=4096/4096
```

`RX: done=4096/4096`（原为 13）即 B21 关闭判据：滚动补投在真实硬件上成立，
含 4 次环回绕，无一条 BD 报错。Stage1 之后 Stage2 正常 DONE，流水线继续向下走。

> **注意**：B21 关闭**只**代表「4,096 条记录都被 DMA 搬回了 DDR」，
> **不代表记录内容正确**。内容错误另见 B23。

---

## B 类新增 · B22（2026-08-29，第二次上板发现）

### ~~B22 Stage3 等待循环从不读 STATUS，DONE 永远等不到、超时也永远触发不了~~ ✅ 已修复并验证

**现象**：B21 修好后再次上板，Stage1、Stage2 都正常完成，日志停在
`[STAGE3] ✓ Started, monitoring progress...` 之后再无输出，客户端 180 s 超时。

**根因**（`sw/app/echo.c` 的 `PIPE_DECODER_WAIT`，三处叠加）：

| # | 缺陷 | 后果 |
| --- | --- | --- |
| 1 | 注释声称「用状态寄存器的 DONE 标志(可靠)」，但循环里**从来没有读过 `DECODER_REG_STATUS`** | 完成信号根本没人看 |
| 2 | 唯一的判定是每 1,000 次轮询做一次的内存启发式；本状态由 lwIP `tcp_poll` 驱动，间隔 500 ms，**最早也要 1000 × 500 ms = 500 s 才做第一次判断** | 上位机 `recv_result` 的静默上限是 180 s，必然先超时 |
| 3 | 那个启发式把 `0` 和 `0xAAAA…` 当「未写」，可 `PIPE_DECODER_PREP` 填的哨兵是 `DECODER_SENTINEL_U64 = 0x0A55AA55AA55AA55`，**根本不在比较之列**；超时阈值 `poll_count > 500000` ≈ 69 小时 | 既分不出写没写，也等于没有超时 |

**修复**：与 Stage2 的 `PIPE_VOTER_WAIT` 对齐——每次轮询都读 `STATUS` 判 `DONE`；
内存进度只作旁证且按真正的哨兵比较、每 20 次轮询（约 10 s）打一次；
超时改为 240 次轮询 ≈ 120 s，仍在上位机 180 s 静默上限之内，超时时打印
`STATUS / IN_ADDR / IN_BEATS / OUT_ADDR / OUT_BEATS`。

**判据**：修复后同一条命令拿到 `Result: 8100 bytes, 32.23s`，
Stage3 正常完成，8,100 B 回传成立。

---

## B 类新增 · B23 / B24（2026-08-29，第二次上板发现；RTL 已修，**待重建 bitstream 上板验证**）

### B23 DNA 核 `M_AXIS_RESULT` 的 TDATA 比 TVALID 早一拍，每条记录丢首拍、末拍重复

**现象**：B21 + B22 修好后，G3 全程走通并回传 8,100 B，但
`tools/ldpc_decode.py` **译码不收敛**（50 轮后仍有 5,265 个失败校验）。
把回传比特与 `archive/submission_2025-11-07/演示文件/dec_input.txt` 逐位比，
**误码率 49.70%**（32,206/64,800），即与正确结果完全不相关。

**取证方式**：板子跑完后**不复位、不重烧**，用 XSDB 只读 DDR
（`mrd -bin -file`，脚本 `D:\dna_board_smoke\dump_ddr.tcl`）导出四级中间结果，
与仓库内黄金向量逐拍比对。

| 观测项 | 结果 |
| --- | --- |
| DDR 里展开后的 50 个水印区域（`0x10040000`，191,400 B）vs `tests/golden/wm_regions.hex` | **47,850/47,850 字逐位相同** ✅ |
| Stage1 输出（`0x10600000`，4,096 × 48 B）vs `tests/golden/stage2_in.hex` | **内容错位** ❌ |
| 每条记录的第 5、6 个 64-bit 字 | **4,096/4,096 条完全相同**，且都 ≤ 6 bit |
| 解析出的 score / position | score 均匀铺满 0..1023、position 最大 64,306（**> L=40,500，不可能**）→ 是随机比特 |

**错位规律（决定性证据）**：设 golden 记录 *i* 的第 *k* 拍为 `G[i][k]`，
板上记录 *i* 的第 *k* 拍为 `B[i][k]`，则

```
B[i][k] == G[i+1][k+1]   k = 0..4     实测 20,470 / 20,475 拍吻合（99.98%）
B[i][5] == B[i][4]                    实测 4,095 / 4,095 条成立
```

即 **每个 48 B 包实际收到的是 `[b1,b2,b3,b4,b5,b5]`**：首拍被丢掉、末拍被重复采样，
整条流水还额外整体偏移了一条记录。首拍正是 `score[9:0]` + `position[15:0]` +
码字低 38 bit 所在的那 64 bit，**所以 Voter 拿到的分数和位置全是码字碎片**，
投票结果自然与正确答案不相关。

**根因**（`hw/ip/Dna_accelerator_core_1_0/hdl/Dna_accelerator_core_v1_0.v:404-424`）：

```verilog
end else if (M_AXIS_RESULT_TREADY || ~M_AXIS_RESULT_TVALID) begin
    M_AXIS_RESULT_TVALID <= pack_vld;      // 寄存，晚一拍
    M_AXIS_RESULT_TLAST  <= pack_last;     // 寄存，晚一拍
end
...
assign M_AXIS_RESULT_TDATA = pack_dat;     // 组合直连，立刻跟随
```

`TDATA` 组合直连 `s2mm_pack64` 的寄存输出，而 `TVALID`/`TLAST` 又寄存了一拍，
**数据比 valid 早一整拍**。于是每次握手采到的都是「下一拍」的数据：
包首那一拍在 TVALID 还没抬起来时就过去了（丢），包尾那一拍在 TVALID 多拉一拍时被采两次（重）。

**为什么所有仿真都没抓到**：`tools/run_m2_full.sh` 的 Stage1 环节
（`run_m2_full.sh:99`）只编译 `srpe_batch.v` + `tb_srpe_batch.v`，
**直接抓引擎的 `res_din` 记录，完全绕开了 `Dna_accelerator_core_v1_0.v` 的 AXIS 输出级和
`s2mm_pack64`**；`tb_dna_ingress` 只测入口 FIFO 背压。
`DNA M_AXIS → AXI DMA S2MM` 这条链至今没有任何仿真覆盖——
正是 `docs/13` §7.2 BD-3 第 2 项、`docs/17` §1「根因缺口」点名的那一条。

### 修复（RTL，已在仿真中逐拍验证；**尚未上板**）

补判据的过程中发现同一个输出级还有第二个缺陷，一并修掉，记为 **B24**：

| 编号 | 缺陷 | 位置 |
| --- | --- | --- |
| B23 | `TDATA` 组合直连、`TVALID`/`TLAST` 寄存，数据比 valid 早一拍 | `Dna_accelerator_core_v1_0.v` AXIS 输出级 |
| B24 | `s2mm_pack64` 的 `m_vld` 依赖 `m_rdy`（VALID 依赖 READY），且状态机按 `m_rdy` 而不是按握手 `m_vld && m_rdy` 推进；下游在包中间撤 TREADY 就丢拍 | `s2mm_pack64.v` |
| B24 | `res_rd <= ~res_empty & TREADY & pack_vld` 在一条记录的 6 拍打包过程中**反复 pop** 结果 FIFO，FIFO 积压时整条整条丢记录 | `Dna_accelerator_core_v1_0.v` |

改法：把 `s2mm_pack64` 重写成合规的 AXI-Stream master——有数据就拉 VALID（与 READY 无关）、
只在 `m_vld && m_rdy` 时推进、未握手时 `m_dat`/`m_last` 保持不变；新增 `din_rd` 单拍脉冲
给 FIFO 当 `rd_en`，保证一条记录只 pop 一次。输出级因此天然同拍，`M_AXIS_RESULT_*` 直接
从 packer 连出去，不再需要额外寄存级，B23 的偏斜从结构上消失。
另外补上 FIFO 两级同步读的两道保护：`res_empty_q`（刚写进空 FIFO 时 dout 要下一拍才出来）
与 `res_settle`（刚 pop 完 `rptr→raddr_q→dout` 共 3 拍才稳定）。

### 新增回归：`tools/run_xsim.sh result_axis`

新 TB `hw/sim/dna/tb_dna_result_axis.v` 用**真实 DUT**（不复制被测逻辑）：
引擎不启动，改为 `force` 内部的 `eng_res_wr`/`eng_res_din`，把
`tests/golden/stage2_in.hex` 的已知记录压进结果 FIFO，再在 `M_AXIS_RESULT` 上逐拍核对。
判据：每包恰好 6 拍、TLAST 只在第 6 拍、每拍逐位等于黄金字、总拍数不多不少，
且全程在随机 TREADY 背压下成立。

| RTL 版本 | 结果 |
| --- | --- |
| 修复前（`git show 363c7f1:`） | **FAIL**：应收 384 拍实收 376 拍，逐拍不符 422 处 |
| 修复后 | **PASS**：384/384 拍逐位正确，TLAST 位置正确，随机背压下成立 |

### 仍未完成（G3 未闭环）

**RTL 改动必须重新综合/实现、重建 bitstream 与整套 `hw/build/export/` 制品，
然后再上板复跑 G3。在图片 SHA-256 等于
`fcd0cf90bd680e7bbdc203e3398119504da0897acac9e2117008b4efb6b1f2c3` 之前，
不得声称端到端正确。**

新 TB 覆盖的是 DNA 核到 AXIS 端口这一段；`AXI DMA MM2S → DNA S_AXIS` 与
`DNA M_AXIS → AXI DMA S2MM` 的 **BD 级**串联（`docs/13` §7.2 BD-3 第 1、2 项、
`docs/17` 任务 A）仍未实施，在途文件 `hw/sim/m3/tb_m3_bd3b_dma.sv`。

---

## B 类新增 · B25 / B26（2026-08-29，第三次上板发现）

第三次上板（RTL 修完 B23/B24、bitstream 重建后）用 XSDB 只读导出 Stage1 输出，
与 `tests/golden/stage2_in.hex` 逐拍比对，**B23/B24 已确认修复**：

| 指标 | 第二次上板（修复前） | 第三次上板（修复后） |
| --- | --- | --- |
| 每条记录 `word4 == word5`（B23 特征） | **4,096 / 4,096** | **1 / 4,096** |
| 每包拍序 | `[b1,b2,b3,b4,b5,b5]`，丢首拍重末拍 | 6 拍完整、顺序正确 |
| 码字（记录 bit 26 以上）与黄金一致 | 0 | **4,094 / 4,095** |
| score 与黄金一致 | 0 | **4,094 / 4,095** |

但回传经 LDPC 仍不收敛（50 轮后 5,215 个失败校验），因为还剩两处**互相独立**的错位。

### ~~B25 水印预载写偏一个符号，导致每条记录的 position 恒 +1~~ ✅ 已修复并在板上验证（第四次上板）

**证据**：board 记录与黄金对齐后，`position` 差值分布高度集中：

```
position 差值 = +1 : 4,009 / 4,095 条
其余 86 条为较大差值（并列被 +1 打破后选了另一个位置）
score 差值 = 0     : 4,094 / 4,095 条
码字完全相同        : 4,094 / 4,095 条
```

即**只有 position 偏了，而且恒偏 +1**。

**根因**（`Dna_accelerator_core_v1_0.v` 的 preload always 块）：

```verilog
end else if (preload_mode_s && S_AXIS_DATA_TVALID && S_AXIS_DATA_TREADY) begin
    wm_we    <= 1'b1;                       // 寄存，下一拍才有效
    wm_wdata <= S_AXIS_DATA_TDATA[1:0];     // 寄存，下一拍才有效
    wm_waddr <= (wm_waddr == 10'd956) ? 10'd0 : (wm_waddr + 10'd1);   // 同拍就自增了
end
```

`wm_we` / `wm_wdata` 是寄存输出，下一拍才拉高；而 `wm_waddr` 在同一拍已经自增。
于是第 *k* 个符号在 `wm_we` 有效那一拍看到的地址是 *k+1*——**整条水印在 BRAM 里
被写偏一个符号**，所有匹配位置因此恒 +1。

**为什么仿真没抓到**：`tb_srpe_batch` 是直接把水印灌进 `srpe_batch` 的 BRAM 的，
根本不走 `preload_mode + S_AXIS` 这条 DMA 预载通路。这正是 `docs/17` §1
列的「1 号怀疑方向：水印预载 50 次区域切换时 `wm_waddr` 是否每次从 0 开始」——
方向对了，但真正的错不在区域切换，而在**地址与数据不同拍**。

**修复**：新增与 `wm_wdata` 同拍的 `wm_waddr_q` 作为真正的写地址，
`srpe_batch` 的 `.bram_write_addr` 改接 `wm_waddr_q`。

**第四次上板判据**（重建 bitstream 后，XSDB 只读 DDR 比对）：

| 指标 | 第三次（B25 未修） | 第四次（B25 已修） |
| --- | --- | --- |
| `position` 差值 = 0 | 0 / 4,095 | **4,009 / 4,095** |
| `position` 差值 = +1 | 4,009 / 4,095 | 0 |
| 整条 48 B 记录与黄金逐位相同 | 0 | **4,009 / 4,096** |

即 position 偏移已彻底消失，Stage1 除了 B26 的整体错位之外已经逐位正确。

### ~~B26 入口 FIFO 两级同步读 + 引擎晚采样 → Stage1 结果整体错位一条读段~~ ✅ **已修复，第五次上板验证通过**

**板上证据**（第四次上板，XSDB 只读 DDR）：board 记录 *i* 的码字 == 黄金记录 *i+1* 的码字
（4,094/4,095 条），且**黄金记录 0 的码字在整份板上 dump 里根本不存在**；
board 最后一条（slot 4095）是多出来的一条。
即：送入 4,096 条读段，核吐出的结果对应读段 **1..4095**，读段 0 的结果丢失，末尾多一条。

#### 根因（已在仿真里逐条坐实，不再是推测）

`fifo_sync_sdpram_b64` 是**两级**同步读：

```verilog
raddr_q <= rptr;
dout    <= mem[raddr_q];
```

设 `in_rd` 有效（pop `mem[rptr(m)]`）的那一拍为 *m*，则

| 周期 | `dout` 的内容 |
| --- | --- |
| m+1 | `mem[rptr(m-1)]` —— 上一条（FIFO 空闲时恰好等于本条） |
| **m+2** | **`mem[rptr(m)]` —— 这一拍才是刚被 pop 的那一条** |
| m+3 起 | `mem[rptr(m)+1]` —— **已经跳到下一条**，并一直保持 |

而原来的握手写着 `eng_cw_vld <= in_rd`（注释：「Sync FIFO read delay is 1 cycle」），
即在 *m+1* 就拉 `cw_valid`；`srpe_batch` 收到 `cw_valid` 后要到 `S_LOAD_R` 的
`phase==2`（*m+4*）才**第一次**采样 `cw_data`，并在随后 450 拍里持续采样
（一条读段 150 行 × 3 相）。**那时 `dout` 早已跳到下一条**。

于是每一次装载拿到的都是**下一条读段**：结果 *k* 是读段 *k+1*，读段 0 的结果凭空消失；
最后一次 pop 时「下一条」还没写进来，装出来的是从未写入的 FIFO 槽位 —— 就是末尾那条多余记录。
pop 次数仍然等于读段条数，所以条数不多不少，板上看不出任何异常，只有内容整体错位。

这与 B24 给**结果** FIFO 补的 `res_empty_q` / `res_settle` 是同一类缺陷：
两处都把 `fifo_sync_sdpram_b64` 当成一级同步读用了。

#### 为什么之前所有仿真都是绿的

| 既有 TB | 为什么抓不到 |
| --- | --- |
| `tb_srpe_batch.v` | 直接把 `cw_data` 摆在**引擎端口**上，完全不经过 `in_fifo`、也不经过 `in_rd`/`eng_cw_vld` 握手 |
| `tb_dna_ingress.v` | 只看 `S_AXIS_DATA_TREADY` 的背压行为，从不检查「送进去的第 k 条读段是不是成了第 k 条结果」 |
| `tb_dna_result_axis.v` | 只覆盖**出口**（force `eng_res_wr`/`eng_res_din` 注入），引擎根本不启动 |
| `run_m2_full.sh` Stage1 | 只编译 `srpe_batch.v`，抓引擎的 `res_din` |

**入口这一侧至今没有任何逐条判据** —— 与 B23/B24/B25 同一个模式：
出问题的永远是仿真没覆盖到的那条真实接口。

#### 修复

`Dna_accelerator_core_v1_0.v`：pop 之后等两拍，把 `dout` 锁进新增的 `cw_hold`，
再拉 `cw_valid`；引擎全程读 `cw_hold`（下一次 pop 之前恒定不变），不再直接读 FIFO 的 `dout`。

```verilog
in_rd_d1 <= in_rd;
in_rd_d2 <= in_rd_d1;
if (in_rd_d2) cw_hold <= in_dout;   // 此拍 dout 正好是刚被 pop 的那一条
eng_cw_vld <= in_rd_d2;             // valid 与 cw_hold 同拍
...
.cw_data (cw_hold),                 // 原来接的是 in_dout
```

代价是每条读段多 2 拍（一条读段本来就要 450+ 拍装载），可忽略。

#### 新增回归：`tools/run_xsim.sh ingress_result`

新 TB `hw/sim/dna/tb_dna_ingress_result.v`，**真实 DUT**（`Dna_accelerator_core_v1_0`），
真实 AXI-Lite 写 `reg0`/`reg1`、真实 `S_AXIS` 送水印与读段、真实 `M_AXIS` 收结果，
全程随机上游空档 + 随机 `TREADY` 背压。
`READ_BPS`/`CODEBITS`/`REF_LEN`/两个 FIFO 与生产完全一致；只把**扫描几何**改小
（`NUM_LC=1`、`STRIDE=8`、`BATCH=8`）好让一个 batch 在秒级跑完 ——
入口装载通路逐比特与生产相同，`NUM_LC`/`STRIDE` 只决定比对要跑多少拍，不参与装载。

判据：送入 N 条 → 收到恰好 N 条 48 B 记录；**第 k 条记录的码字（bit 325:26）逐位等于
送入的第 k 条读段**；每条 6 拍、`TLAST` 只在第 6 拍、末拍高 58 bit 为 0；码字不含 X/Z。

| RTL 版本 | 结果 |
| --- | --- |
| 修复前（`git show 65a4ade:`） | **FAIL**：32/32 条「记录 k 的码字 == 读段 k+1 的码字」，错位恒 +1，与板上特征逐条吻合 |
| 修复后 | **PASS**：32 条记录的码字逐位等于送入的第 k 条读段 |

故障注入自检（docs/13 §十）：把送出的第 3 条读段翻 1 bit（只动激励、不动期望）→ 用例 FAIL；
把判据的配对改成 k+1（即「接受错位一条」）→ 修好的 RTL 下 FAIL。判据确实有鉴别力。

> **XSim 2022.2 的坑**：`$fatal` 在这里既不终止仿真也不让 `xsim` 非零退出（实测会继续往下跑）。
> 因此 TB 里 `$fatal` 之后一律显式 `$finish`，并用 `if/else` 保证失败路径**绝不打印 PASS**；
> 真正的判定由 `tools/run_xsim.sh` 做（日志里出现 FAIL 关键字即判失败，且必须有 PASS 标记）。

#### BD 级判据：`tools/run_m3_bd.sh bd3b`（2026-08-30 补齐）

上面的 `ingress_result` 是 IP 级的。`AXI DMA MM2S → DNA S_AXIS` 这条链的 **BD 级**判据
（`docs/13` §7.2 BD-3 第 1 项、`docs/17` 任务 A）也已补上：
`hw/sim/m3/tb_m3_bd3b_dma.sv` 用**实际 BD**（真实 PS7 GP0、真实 `ic_lite`/`ic_hp`、
真实 AXI DMA SG 模式、真实 DNA 核；只把 HP0 内存端点换成 AXI VIP，理由见 `docs/15` §5），
完全按 `echo.c` 的顺序搭 BD 环、预载水印、下发读段。

| 判据 | 结果 |
| --- | --- |
| 水印预载 50 区域 × 957 符号（真实 SG DMA + 真实 preload 通路） | PASS，47,850 个符号逐个相同 |
| **DMA 送入的第 k 条读段必须原样进入引擎的第 k 个槽位** | PASS，64/64 槽位逐位相同 |
| **故障注入自检**：`force` 把 `cw_data` 接回 `in_dout`（= 修复前的接法） | 判据**如期失败**：64 个槽位 63 个不符，其中 62 个整体错位 +1、1 个含 X（装到从未写入的 FIFO 槽位）、1 个因黄金第 53/54 条读段内容相同而不可分辨 |

**同一条判据、同一个工程，FAIL ↔ PASS 只取决于 `cw_data` 接哪根线** ——
这既复现了 B26，也证明这条判据确实有鉴别力。细节见 `docs/15` §8。

#### 交付边界（**重要**）

~~**RTL 已改，但 bitstream 未重建、板子未验证。**~~

**已于第五次上板（2026-08-30）验证通过**：与 B27 的修复一起重新综合实现后烧录，
XSDB 只读比对 `0x10600000` 与 `tests/golden/stage2_in.hex`，
**码字与黄金同序号相同 4,096/4,096**（第四次是错位一条的 4,094/4,095），
B26 的错位特征「board 记录 *i* 的码字 == 黄金记录 *i+1*」降到 **0/4,095**。
详见上面「第五次上板」一节。

### ~~B27 Stage3（Decoder）输入全对、输出却与黄金完全不相关~~ ✅ **已修复，第五次上板验证通过**

第四次上板后逐级比对（XSDB 只读 DDR，与仓库黄金向量比；dump 备份在 `D:\dna_board_smoke\run4_dumps\`）：

| 级 | 板上 DDR | 与黄金比对 | 判定 |
| --- | --- | --- | --- |
| 展开水印 | `0x10040000` | 47,850 / 47,850 字逐位相同 | ✅ |
| Stage1 输出 | `0x10600000` | 4,009 / 4,096 条整条逐位相同；码字 4,094/4,095（其余是 B26 的整体错位一条） | ✅（除 B26） |
| Stage2 输出 ⊕ 水印 | `0x11000000` | 与 `tests/golden/sparse_expect.hex` **81,000 / 81,000 bit 逐位相同**（唯一不同的第 1,266 字只差末拍无效的高位） | ✅ |
| Stage3 输出 | `0x11100000` | 与 `tests/golden/stage3_expect.hex` **0 / 1,013 字相同，比特误码 49.47%** | ❌ |

即 **Decoder 拿到的输入 100% 正确，吐出来的却与正确答案完全不相关。**

#### 第 1 步：把范围一刀切成两半（不用板子）

把 `run4_dumps/dump_stage2.bin`（板上真实 DDR 内容，小端 64 bit 转 hex）直接喂 `tb_desparsifier`：

| 被测对象 | 激励 | 结果 |
| --- | --- | --- |
| RTL（`desparsification_decoder_v1_0.v` + `desparsify_datapath.v`） | 板上 `dump_stage2` | **PASS**：1,013 拍 / 64,800 bit 与 `stage3_expect.hex` 逐位相同 |
| 综合后网表（`top_bd_desparsification_dec_0_0_sim_netlist.v`，即比特流里那一份） | 板上 `dump_stage2` | **PASS**，同上 |

**结论：RTL 和综合结果都没问题。** 也不是 cache：固件在启动 Decoder 之前已经
`Xil_DCacheInvalidateRange(0x11000000, 10128)` 并把整块重读了一遍（`echo.c` 的
`[STAGE3] Input Validation`），所以 XSDB 后来 dump 到的就是 DDR 里的内容，输入在 DDR 里是对的。

#### 第 2 步：从板上输出反推 Decoder 实际读进了什么

反稀疏化是每 5 bit 一组、组内第一个 bit 是取反标志：`out[3:0] = grp[4:1] ^ {4{grp[0]}}`。
因此 `out[j] ^ out[j']` **与标志位无关**，可以拿它当每组 3 bit 的指纹，去输入流里搜对齐位置
（一次性取证脚本，不进仓库；可复现的判据以下面的 TB 为准）。把板上 Stage3 的 16,200 组
与板上 Stage2 的输入流逐段匹配，得到一个干净得不像话的结构：

```
board 输出组     0.. 1599   ← 输入 bit 偏移 +72960 = +1140.00 拍
board 输出组  1613..15488   ← 输入 bit 偏移  -8064 =  -126.00 拍
board 输出组 15504..16191   ← 输入 bit 偏移  -8080 =  -126.25 拍
```

即 **Decoder 先读了输入缓冲区最后的 126 拍（第 1140..1265 拍），然后才从第 0 拍读起** ——
整条输入被旋转了 126 拍。126 个输入拍 = 8,064 bit ⇒ 输出旋转 8064/5×4 = 6,451.2 bit ≈ 101 拍，
这正好解释了板上 dump 里唯一两段能对上的数据：

```
board[   0..  99] == golden[912..1011]      （delta +912）
board[ 969..1012] == golden[868.. 911]      （delta -101 = +912 - 1013）
board[100] 的低 4 字节 == golden[1012] 的低 4 字节，高 4 字节仍是哨兵 0x0A55AA55
   —— 整个任务末拍 WSTRB=0x0F 的特征，证明这确实是 Decoder 自己写下的
```

#### 根因（两个缺陷叠加，缺一不可）

**① RTL：写 START 寄存器时不看数据位。**
`hw/ip/desparsification_decoder_1_0/hdl/desparsification_decoder_v1_0.v` 的 `axi_slave_decoder`：

```verilog
case (waddr)
    ...
    4'd4: start_pulse <= 1'b1;      // ← 写 0x10 就产生脉冲，压根不看 write_data[0]
endcase
```

同项目的 `differential_voter_v1_0.v:943` 写的是 `start_pulse <= write_data[0];`，
DNA 核用的是电平寄存器 —— **只有 Decoder 是错的**。

**② 固件：启动之后又写了一次 START。**
`sw/app/echo.c` 的 `PIPE_DECODER_START`：

```c
write_reg32(..., DECODER_REG_START, 0x00);
usleep(10);
write_reg32(..., DECODER_REG_START, 0x01);
usleep(100);                                    /* 100 us */
write_reg32(..., DECODER_REG_START, 0x00);      /* 注释写「脉冲结束」← 致命 */
```

于是那句「脉冲结束」在任务跑到一半（读到第 1,140 拍）时**把核重启了**。

**③ 为什么一重启就必错：** 重启只复位了本模块的 FSM 和 `desparsify_datapath`，
**已经发出去的 AXI 读突发不会被取消**。真实 DDR / 真实互连会把那段突发剩下的 R 拍
继续送回来（当时正在第 5 段突发，还剩 1266 − 1140 = **126 拍**），它们落进刚被清空的
`in_pool`，被当成新任务输入流的开头 —— 输入旋转 126 拍，输出与黄金完全不相关。

**为什么所有仿真都没抓到**：`desparsifier_axi` / `desparsify_datapath` / M3 的 BD-3ext
都只写一次 `START=1`（`tb_desparsifier.v` 的 `axil_write(6'h10, 32'd1)`），从机模型也不模拟
「主机复位后已接受的突发仍要发完」。与 B23/B24/B25 同一个模式：
出问题的永远是仿真没覆盖到的那条真实接口。

#### 修复

| 编号 | 缺陷 | 位置 | 改法 |
| --- | --- | --- | --- |
| B27-① | 写 START 寄存器时 `start_pulse <= 1'b1`，写 0 也启动 | `desparsification_decoder_v1_0.v` 的 `axi_slave_decoder` | 改成 `start_pulse <= write_data[0]` |
| B27-② | 核忙时也接受 START，而重启不清飞行中的读突发 | 同文件的 M00_AXI 时钟域 | 新增 `core_active_m = busy \| (rd_state==RD_ADDR) \| (rd_state==RD_DATA)` 与 `start_eff_m = start_pulse_m & ~core_active_m`；读引擎、写引擎、数据通路复位、`done_m` 全部改用 `start_eff_m`。`RD_DONE` 时所有读突发已收完、`busy=0` 时最后一个 B 也已回来，此时重启才安全 |
| B27-③ | 启动后 100 us 又写一次 START=0 | `sw/app/echo.c` 的 `PIPE_DECODER_START` | 只写一次 `START=0x01`，前后都不再碰这个寄存器 |

RTL 与固件两边都改，互不依赖。

#### 新增判据：`tools/run_xsim.sh dec_restart`

新 TB `hw/sim/dec/tb_dec_ddr_restart.v`，做到「真实 DDR / 真实 AXI 主口」级别，
不再用温柔的 VIP 内存喂黄金数据：

- 真实 DUT（`desparsification_decoder_v1_0` + `desparsify_datapath`），不复制被测逻辑；
- 板上真实地址（IN `0x1100_0000` / OUT `0x1110_0000`）与板上真实数据
  （`tests/golden/sparse_expect.hex` 就是第四次上板 DDR 里逐位相同的那一份）；
- 从机模型像真 DDR：AR→首拍 12~32 拍延迟、突发中间随机空档、AW/W/B 随机背压，
  **已接受的读突发一定把 `ARLEN+1` 拍发完，不因主机重启而取消**；
- 输出区先按固件填 `DECODER_SENTINEL_U64`，逐拍逐位比对，末拍按 `WSTRB=0x0F` 只比低 32 bit；
- 一次仿真跑两个场景，并额外判 AXI 流量必须刚好（读 1,266 拍、写 1,013 拍，不多不少）：

| 场景 | 寄存器时序 | 修复前 | 修复后 |
| --- | --- | --- | --- |
| `clean-single-start` | 只写一次 `START=1` | **PASS** | **PASS** |
| `firmware-sequence` | 原样回放 `echo.c`：写 0 → 10 us → 写 1 → 100 us → 写 0 | **FAIL**：读 839/1266 拍、写 665/1013 拍，759 处不符 | **PASS**：1,013 拍 / 64,800 bit 逐位相同 |

修复前的失败输出用同一套指纹分析，同样呈现「输入被拼成若干段旋转」的结构
（`+643.5 / −124.5 / 0 / −252` 拍），与板上同型，机理一致。

`tools/run_xsim.sh all` 全量回归 **9/9 通过**（含 `dec_restart`）。

#### 上板验证（第五次上板，2026-08-30）✅

连同 B26 的入口修复一起重新综合实现、重建整套 `hw/build/export/` 制品后烧录：

| 指标 | 第四次（B27 未修） | 第五次（B27 已修） |
| --- | --- | --- |
| Stage3 `0x11100000` vs `stage3_expect.hex` | 0/1,013 字相同，比特误码 **49.47%** | **1,013/1,013 字相同，比特误码 0/64,800** |
| UART 完成方式 | 靠「输出区哨兵被覆盖」的旁证收尾 | `[STAGE3] ✓ DONE flag set after 1 polls` |
| LDPC | 50 轮后仍有 5,215 个失败校验，不收敛 | 起始失败校验 332，**5 轮收敛** |
| 重建图片 SHA-256 | 与判据不同 | **`fcd0cf90…f2c3`，与判据逐位相同** |

详见上面「第五次上板」一节。
---

## B 类新增 · B20（2026-08-29，M3 BD-3ext 发现）

### ~~B20 Voter 的 AXI 读突发跨越 4 KB 边界，违反 AXI 规范 A3.4.1~~ ✅ 已修复并逐位验证（2026-08-29）

`hw/ip/differential_voter_1_0/hdl/differential_voter_v1_0.v:675` 固定
`M00_AXI_ARLEN = 8'd5`（6 拍 × 8 B = 48 B），`:512` 每条记录 `read_addr += 48`，
**无 4 KB 边界处理**。因 4096 不是 48 的整数倍，突发会周期性跨页。

判据证据（实际 BD + AXI 协议检查器）：

```
Warning: ARADDR=0x10600ff0, ARID=0x2, ARLEN=0x05, ARSIZE=0b011
Fatal: AXI4_ERRM_ARADDR_BOUNDARY: A burst must not cross a 4kbyte boundary.
```

- 4096 条记录中 **32 次**跨界；首次在记录 **85**（`0x10600ff0`），
  周期为每 256 条 2 次（`i ≡ 85, 170 mod 256`）。
- Decoder 读、Voter 写、Decoder 写均为 128 B 突发且基址 4 KB 对齐，**不受影响**。
- 既有 Stage2 黄金 TB 用的简易内存模型不检查 4 KB 规则，因此长期未被发现。

**后果**：跨 4 KB 突发在 AXI 下行为未定义，实际 Interconnect/AFI 可能返回错数据或挂死。

**修复（方案 A：拆分突发）**：新增 `rd_ptr` / `rd_burst_beats` / `rd_burst_done`；
发 AR 前取「页内剩余拍数」与「本记录剩余拍数」的较小者作为本笔突发长度，
`ARLEN` 由固定 `8'd5` 改为 `本笔拍数-1`；跨页时自动拆成两笔（先到页边界，再读余下），
`read_beat_count` 作为记录内拍索引跨两笔连续，因此不再在 `S_READ_SETUP` 清零。

**同时修正黄金 Testbench 的根本缺陷**：`tb_differential_voter.v` 的内存模型原先
`r_left <= 6` 写死、无视 `ARLEN`——这正是 B20 长期未被发现的原因。现改为按 `ARLEN`
返回拍数，并把原「ARLEN 必须为 5」的检查替换为真正应当成立的
**AXI A3.4.1 跨 4 KB 检查**，今后同类缺陷会被 IP 级黄金 TB 直接拦截。

**验证判据（全部通过）**：

| 判据 | 结果 |
| --- | --- |
| Stage2 黄金 TB（3 轮，含 SCORE_MIN=67/0） | 1,266 拍 / 81,000 bit 逐位相同；跨 4 KB 违规 0 次 |
| `bash tools/run_sim.sh` | **11/11 PASS** |
| `bash tools/run_xsim.sh all` | **6/6 PASS** |
| `bash tools/run_m2_full.sh` | 全链 PASS，LDPC 图片哈希仍为 `fcd0cf90...b6b1f2c3`，单 bit 故障注入仍被检出 |
| BD-3ext Voter（实际 BD + 实际 Interconnect） | PASS，**协议违规 0**，错误标志 0，末次 RRESP=OKAY；输出 1,266 拍 / 81,024 bit 逐位相同 |
| BD-3ext Decoder（级联自**实际** Stage2 输出经 PS 等价 XOR） | PASS，输出 1,013 拍 / 64,832 bit 逐位相同 |

修改前同一用例在 1.32 ms 处被 AXI 协议检查器 Fatal 终止（记录 85 / `0x10600ff0`），
修复后同一位置安全通过并跑完全部 4,096 条记录，这是修复生效的直接证据。

---

## 接口判据补齐 · Voter 的 AXI 读通路走真实 DDR（2026-08-30，`voter-ddr` 会话）

`docs/18` §5「仍未覆盖」的第一条已补齐：**`tools/run_xsim.sh vot_ddr`**，
新 TB `hw/sim/vot/tb_vot_ddr_bitexact.v`。

### 为什么必须补这一条

Voter 的 AXI 主口此前**从来没有走过带时序的从机**：

| 既有判据 | 从机是什么 | 缺口 |
| --- | --- | --- |
| `tb_differential_voter.v`（`run_xsim.sh stage2`） | 自写的温柔内存：`ARREADY` 恒 1、AR→首拍零延迟、突发无空档、`WREADY` 恒 1、B 固定 1 拍 | 没有任何真实 DDR 时序；只写一次 `START=1`，不回放固件写序列 |
| `run_m3_bd.sh bd3ext` | **AXI VIP 内存模型**（`docs/15` §5 已注明不是实际 PS7 AFI 通路） | 不是「PS 用 CPU 写 DDR → Voter 用 AXI 主口读 DDR」 |

B27 的教训正是：Decoder 喂 VIP 内存连**综合后网表**都 PASS，板上照样 49.47% 误码。

### 这条 TB 做了什么

- **真实 DUT**（`differential_voter_v1_0`，含 `axi_slave_voter`），不复制被测逻辑；
- **一片共享 DDR**：输入区 `0x1060_0000`（`DDR_DNA_ACC_OUT_BASE`）与输出区
  `0x1100_0000`（`DDR_VOTER_OUT_BASE`）用板上真实地址落在同一个数组里，
  PS 侧先把 `tests/golden/stage2_in.hex` 写进输入区、把输出区填成
  `DECODER_SENTINEL_U64`，然后 Voter 用自己的 AXI 主口去读同一片内存。
  Voter 若把结果写回输入区、或读写越界，会被直接抓住，而不是像分离数组那样被下标掩盖；
  两区之间的 10 MB 空洞保持 X，读到那里会把 X 带进码字（不屏蔽 X）；
- **类 DDR 从机**：AR 队列深 8、`ARREADY`/`AWREADY`/`WREADY` 随机撤下，
  AR→首拍 12~31 拍延迟并有 1/32 概率叠加 200 拍长停顿（模拟刷新），
  突发中间随机空档，B 响应 3~14 拍时延，
  **已接受的读突发一定把 `ARLEN+1` 拍发完**，不因主机被写 `START` 而取消；
- **逐字节 `WSTRB`**（不是 32 bit 粒度近似——末拍 `WSTRB=0x1F` 只写低 5 字节，
  32 bit 粒度的模型会漏掉字节 4）；
- **原样回放 `sw/app/echo.c` 的寄存器时序**：DONE 清除通路、6 个配置寄存器写 +
  `usleep(10)` + 逐个回读校验、`写 0 → usleep(100) → 写 1 → usleep(100) → 写 0`，
  以及 `PIPE_VOTER_WAIT` 那样用 AXI-Lite 轮询 `STATUS`；
- **AXI 协议判据**：4 KB 页边界（A3.4.1）、地址区间与 8 B 对齐、`ARSIZE/ARBURST`、
  `AWSIZE/AWBURST`、`WLAST` 位置、无 AW 就来 W、
  `AxVALID` 期间地址/长度必须保持不变，以及
  **R 拍只能在 `S_READ_DATA` 被握手**（DUT 的 `RREADY` 在 `S_READ_SETUP` 也是 1，
  但只有 `S_READ_DATA` 才把数据存进 `read_words`，真实 DDR 有延迟时落在别的状态
  就是静默丢数据）；
- 读写拍数必须刚好（读 24,576 拍、写 1,266 拍，不多不少），
  `DBG_WRITE` / `DBG_FIRST_AWADDR` / `ERR_FLAGS` / `LAST_RRESP` 全部核对；
- 逐拍逐位比对 DDR 输出区，末拍只比低 40 bit（81,000 = 1,265×64 + 40）。

### 结果：5 个场景全部逐位通过

`bash tools/run_xsim.sh vot_ddr`（实测约 3 min，含 3 档故障注入）：

| 场景 | 内容 | 期望向量 | 结果 |
| --- | --- | --- | --- |
| `fw-board-cfg` | 固件时序 + `SCORE_MIN=67`（= 第五次上板那组参数） | `stage2_expect.hex` | **PASS** 1,266 拍 / 81,000 bit 逐位相同 |
| `fw-second-task` | 不复位，紧接第二次任务，走固件 DONE 清除通路，换 `SCORE_MIN=0` | `stage2_rtl_expect.hex` | **PASS** |
| `fw-raw-score0` | 复位后单独跑 `SCORE_MIN=0`（给上一档做对照） | `stage2_rtl_expect.hex` | **PASS** |
| `late-start0` | `START=1` 之后 **5 ms**（投票途中）才写 `START=0` | `stage2_expect.hex` | **PASS** |
| `spurious-start` | 投票途中再写一次 `START=1` | `stage2_expect.hex` | **PASS** |

后两档是针对 B27 的定向探测：`axi_slave_voter` 是 `start_pulse <= wdata[0]`
（写 0 不启动），且 FSM 只在 `S_IDLE` 响应 `start_latched_pulse`，
所以固件那笔「脉冲结束」的 `START=0` 和途中多余的 `START=1` 都是无害的——
**这件事此前只是读代码的推断，现在在真实 DDR 时序下被逐位证明**。

背压随机种子换过三组（默认 / `rseed=12345 wseed=98765` / `rseed=777 wseed=31337`），
5 个场景均逐位通过，结论不依赖某一组种子。

### 故障注入自检（`docs/13` §十，判据必须能失败）

三档注入都必须让判据变红，否则它没有鉴别力。判据用 `sim_case ... inject`
（注入档不能用通用判据，因为日志里本来就有 `FAIL` 行）：

| 注入 | 复现的缺陷 | 手段 | 结果 |
| --- | --- | --- | --- |
| `inject=b20` | B20：读突发跨 4 KB | `force dut.rd_burst_beats = 6`，退回「每条记录固定 6 拍、从不按页拆分」 | **判据报错**：`page(4KB)=32` —— 与 B20 记录的「4096 条中 32 次」完全吻合 |
| `inject=rot` | B27 那类「输入流被旋转」的读通路损坏 | 从机把读回的数据流整体旋转一个 64 bit 字 | **判据报错**：1,266 拍全错，误码 **50.06%** |
| `inject=c4` | C4：二次任务复用旧累加器 | 第二次任务的 `S_INIT_BRAM` 期间 `force dut.bram_we = 0`，清零被完全压制 | **判据报错**：第二轮 720 拍不符，误码 **4.49%** |

### ⚠️ 由此测出来的一件事：二次任务用同一组参数**测不出**累加器没清零

`inject=c4` 加上 `+second_score_min=67`（即第二次任务与第一次用**同一份输入、
同一个阈值**）时，累加器清零被完全压制，两轮输出**仍然逐位相同**，
判据打出「判据没有鉴别力」。

机理：输出位是 `票数 > 0` 的符号判决，而第二轮在旧票上再加一遍同样的增量。

⚠️ 这里**不要**用「票数整体翻倍所以符号不变」来解释：一旦撞上
`safe_vote_value` 的 `[-512, +511]` 饱和，「翻倍」这个描述本身就不成立了，
用它去论证饱和区也没事是循环论证。正确的论证在下面，它把饱和吸收进证明里。

**这不只是「这份数据碰巧测不出来」，而是结构性的——任何输入都测不出来。**
证明（单调性，一行）：每位累加器的更新是 `x ← clip(x ± 1)`，`clip` 到
`[-512, +511]`（`safe_vote_value`）。`x ↦ x + d` 与 `clip` 都是单调不减的，
复合仍单调，所以整条轨迹对**起始值**单调不减。设第一轮终值为 `v`、
残留时第二轮终值为 `w`（同一份输入、同一 `score_min` ⇒ 增量序列逐条相同）：

- `v > 0`：第二轮起点 `v > 0 =` 第一轮起点 ⇒ `w >= v > 0`，判决同为 1；
- `v < 0`：起点更低 ⇒ `w <= v < 0`，判决同为 0；
- `v = 0`：两轮起点相同 ⇒ 轨迹逐拍相同 ⇒ `w = 0`，判决同为 0。

三种情况判决全部一致，**且饱和已经含在 `clip` 里**（撞饱和不破坏单调性），
所以不存在任何一条能让残留露馅的路径。上面 `+second_score_min=67`
那次实测只是这条结论的一个实例，不是全部依据；另用 20 万组随机增量序列
（偏置到高饱和率，覆盖 `v`/`w` 的各种饱和组合）穷举复核，判决零不一致。

顺带回答「为什么直觉会觉得饱和有风险」：轨迹一旦撞顶就把起始偏移**忘掉**了，
两轮因此更容易收敛到同一个值，而不是发散。
（机理由 `voter-ddr` 与另一会话独立复核；RTL 出处：`S_VOTE_UPDATE` 的
`bram_din <= safe_vote_value(bram_dout ± 10'sd1)` 与 `S_OUTPUT_PACK` 的
`~bram_dout[9] && (bram_dout != 10'd0)`。）

**对 `docs/18` P1 第 4 项（二次任务 / 状态复位）的直接影响**：
「同一次连接内连续跑两次任务、判据是两次都拿到同一张图片哈希」这条判据
**抓不到 Voter 累加器没清零**。要覆盖它，第二次任务必须换参数
（换 `score_min`、或换读段子集），让两轮的票集不同。
上面的 `fw-second-task` 场景就是这么设计的（第二轮换成 `SCORE_MIN=0`）。

### 顺带钉住的两件事实

1. **两份 Stage2 黄金向量的语义**（此前只在 TB 注释里，现已由本轮实测确认）：
   `stage2_expect.hex` = `SCORE_MIN=67`，`stage2_rtl_expect.hex` = `SCORE_MIN=0`，
   两者相差 **4,894 bit**。
   进入 G3 链路的是前者：`sparse_expect.hex = stage2_expect.hex ⊕ watermark_packed.bin`
   **逐位相等（0 bit 差）**，而 `stage2_rtl_expect.hex ⊕ watermark` 与它差 4,894 bit。
   所以**只比 `stage2_rtl_expect.hex` 等于在验一组板上不跑的参数**；
   板上那组必须比 `stage2_expect.hex`。本 TB 两者都比。
2. 修好了 `run_xsim.sh` 的一个结构性限制：原 `run_case` 把编译/elaborate/复跑
   绑成一次，无法「一次 build、多次带不同 plusarg 复跑」。已拆成
   `build_case` / `sim_case`（判据可选 `default` 或 `inject`），
   既有用例行为不变——`bash tools/run_xsim.sh all` **13/13 通过**。

### 证据

- TB：`hw/sim/vot/tb_vot_ddr_bitexact.v`
  SHA-256 `695156d6edebb094e409f729838f3cf271dab002bfd4b57a399a37511d5a838d`
- 输入 `tests/golden/stage2_in.hex` SHA-256 `9e5cd0adebc1a2806a739b8d87a44d3cbefe5275b11fb97ddc234dd12e92175d`
- 期望 `tests/golden/stage2_expect.hex` SHA-256 `74182edfcaf55fef7b414ed4f77e6205c8b1b29ca1710ca366e79d7cd977f9fc`
- 期望 `tests/golden/stage2_rtl_expect.hex` SHA-256 `6ffd7560bfcf95b7b9719c015a111b2afc30e3e89e1aa474317e4bdc3350df44`
- 复跑：`bash tools/run_xsim.sh vot_ddr`（4/4）、`bash tools/run_xsim.sh all`（13/13）

### 结论边界

**可以确认**：Voter 的 AXI 读/写通路在带延迟、带背压、带长停顿的类 DDR 从机上，
以板上真实地址、按固件原样的寄存器时序，对 4,096 条记录输出 81,000 bit 逐位正确；
固件那笔 `START=0`、途中多余的 `START=1` 都无害；换阈值的二次任务累加器确实清零。

**仍不能确认**：这仍然是**仿真**，从机是行为模型而不是实际 PS7 的 AFI/DDR 控制器；
`docs/16` 那颗 16 bit `MT41J256M16HA-125` 的实际时序、刷新与 AFI 深度都没有建模。
唯一判据仍然是板端实际回传经 LDPC 后的图片 SHA-256。

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
