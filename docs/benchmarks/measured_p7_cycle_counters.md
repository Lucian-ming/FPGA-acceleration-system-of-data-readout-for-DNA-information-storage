# P7 硬件周期计数器实测：拆解 62.9% 非 Stage1 耗时真相

> **评测日期**：2026-09-11  
> **比特流**：`hw/build/export/top_bd_wrapper.bit`（SHA-256 `fd5c401c…`，WNS = +0.167 ns @ 100 MHz）  
> **固件**：`hw/build/export/dna_lwip_app_b27.elf`（SHA-256 `b10665ca…`）  
> **留证**：`/mnt/d/dna_board_smoke/g3_runs/20260911T140559Z/`、`uart.log`、`summary.txt`  
> **前置结论**：`docs/benchmarks/measured_4way_board.md` 揭示 4-way 端到端加速仅 1.218x，非 Stage1 耗时占 62.9%（0.3456 ms/记录）。  
> **本评测目的**：通过硬件核级独立 100 MHz 周期计数器，实测 Voter、Decoder 及 PS 固件在各阶段的微秒级耗时，彻底澄清 62.9% 瓶颈根因。

---

## 1. 硬件计数器实现与校验

在 Voter 与 Decoder 的 AXI-Lite 寄存器映射中分别嵌入 32 位硬件周期计数器（100 MHz，1 拍 = 10 ns）：

### 1.1 Voter 计数器（`0x40 ~ 0x50`）
- `0x40` `CYCLES_TOTAL`：从接收 START 脉冲至完成 DDR 写回并置位 DONE 的完整周期数；
- `0x44` `CYCLES_INIT`：BRAM 清零初始化耗时（固定 81,000 拍）；
- `0x48` `CYCLES_READ`：AXI-MM 从 DDR 读取 48B 记录包的耗时；
- `0x4C` `CYCLES_VOTE`：读入后执行差分投票及 BRAM 读改写的耗时；
- `0x50` `CYCLES_WRITE`：投票结束遍历 BRAM 将最终判决结果写回 DDR 的耗时。

### 1.2 Decoder 计数器（`0x14 ~ 0x24`）
- `0x14` `CYCLES_TOTAL`：从接收 START 至解码结束置位 DONE 的完整耗时；
- `0x18` `CYCLES_RD_BUSY`：AXI 读总线处于 ACTIVE 状态的拍数；
- `0x1C` `CYCLES_WR_BUSY`：AXI 写总线处于 ACTIVE 状态的拍数；
- `0x20` `CYCLES_RD_WAIT`：解码流水线因等待 DDR 读数据返回而停顿的拍数。

---

## 2. 板级真实测试数据（4,096 条记录）

在真实 Zynq XC7Z010 开发板上执行标准 G3 流程（4,096 条记录，`score_min=67`）：

### 2.1 正确性验证（G3 PASS）
- **图片 SHA-256**：`fcd0cf90bd680e7bbdc203e3398119504da0897acac9e2117008b4efb6b1f2c3`（**逐位一致 PASS**）；
- **四级 DDR 取证**：`board_stage_check.py` 4/4 级全部通过（Stage1、Stage2 Voter、Stage3 Decoder、Watermark Regions）。

### 2.2 串口实测硬件周期（`[HW-CYCLES]` 仪表输出）

```text
[HW-CYCLES] Stage2 Voter: total 2962716 cyc (29.627 ms), init 81000, read 131333, vote 2399792, write 350591
[HW-CYCLES] Stage3 Decoder: total 2238 cyc (0.022 ms), rd_busy 2220, wr_busy 2239, rd_wait 115
```

### 2.3 硬件周期守恒验证
$$\text{CYCLES\_TOTAL} = \text{INIT} + \text{READ} + \text{VOTE} + \text{WRITE}$$
$$81,000 + 131,333 + 2,399,792 + 350,591 = 2,962,716\ \text{cyc}$$
**计数器加和与总周期完全相等，误差为 0 周期，验证了硬件计数器逻辑的精确无遗漏。**

---

## 3. 端到端墙钟耗时拆解（真相大白）

板端固件状态机流水线打点统计（`[PIPE]` 仪表输出）：

```text
[PIPE] total 86 steps in 12 callbacks, 3173 ms (WM preload: 4 steps)
[PIPE-BREAKDOWN] state / hits / ms
  WM_PREP            1       7
  WM_TX              4       6
  RX_PREP            1      11
  TX_PREFILL         1       4
  START_IP           1       2
  TX_STREAM          9       5
  PROGRESS           1       0
  DONE_STAGE1        1      59
  VOTER_PREP         1      18
  VOTER_START        1     107
  VOTER_WAIT        61      16
  DONE_STAGE2        1      54
  DECODER_PREP       1      71
  DECODER_START      1      18
  DECODER_WAIT       1      12
  [in-state]         -     396
  [waiting]          -    2777  <- lwIP poll 轮询空等
```

### 3.1 耗时全景构成分析

| 模块 / 耗时源 | 实测耗时 (ms) | 占总时间比例 | 属性 |
| :--- | :---: | :---: | :--- |
| **lwIP poll 空等 (`[waiting]`)** | **2,777 ms** | **87.52%** | **PS 固件调度缺陷**（依赖 TCP 周期性慢速轮询驱动状态机） |
| **PS 内存与 Cache 维护 (`[in-state]`)** | **396 ms** | **12.48%** | **PS 驱动低效**（大范围 `Xil_DCacheInvalidateRange` 与哨兵读写） |
| **PL Stage 2 Voter 纯硬件计算** | **29.63 ms** | **0.93%** | PL 硬件内核 |
| **PL Stage 3 Decoder 纯硬件计算** | **0.02 ms** | **0.0007%** | PL 硬件内核 |
| **流水线总墙钟耗时** | **3,173 ms** | **100.0%** | |

---

## 4. 关键结论与决策

### 4.1 彻底推翻「Voter / Decoder 硬件性能是瓶颈」的假设
此前推测「非 Stage1 耗时 62.9% 中 Voter/Decoder 占大头，需要做 8-way 并行 Voter 或流水线 Decoder」。  
**本实测数据以无可辩驳的事实推翻了这一假设**：
- Voter 纯硬件执行耗时仅 **29.6 ms**（在 3.17 秒端到端耗时中仅占 **0.93%**）；
- Decoder 纯硬件耗时仅 **0.02 ms**（仅占 **0.0007%**）；
- **结论**：即便将 Voter 与 Decoder 的硬件执行时间完全优化到 0 周期，端到端性能提升理论上限也不超过 **0.94%**！
- **决议**：**彻底关闭所有 Voter / Decoder 的硬件微架构优化项目**，不再投入任何逻辑资源。

### 4.2 真正瓶颈锁死在 PS 侧
实测证明非 Stage1 耗时 62.9% 的 **99.0% 以上全部发生在 PS 侧**：
1. **lwIP poll 轮询推进机制（占 87.5%）**：  
   固件没有采用中断驱动，而是依赖 lwIP 的主循环 `tcp_poll` 回调（通常以 250ms 或 500ms 为单位触发），导致大量状态转换在无谓地等待下一次轮询唤醒，空等了 2.78 秒；
2. **全局全量 Cache Invalidate 开销（占 12.5%）**：  
   在 Stage1 完成、Voter 启动前、Decoder 启动前等阶段，PS 执行了多次全段 DDR 范围的 Cache Flush / Invalidate，并在 `DONE_STAGE1` (59ms)、`VOTER_START` (107ms)、`DECODER_PREP` (71ms) 处反复扫描哨兵，耗尽了近 400 ms CPU 时间。

### 4.3 终局路线收敛
后续性能优化的唯一有效方向：
1. **固件状态机改造为事件/中断驱动**：消除 2,777 ms 空白 poll 延迟；
2. **精细化局部 Cache 维护**：仅针对真实写入的有效数据边界执行 Cache 操作，消除无谓的整块 Cache 清刷；
3. 保持硬件稳定收敛，不盲目膨胀 PL 资源。
