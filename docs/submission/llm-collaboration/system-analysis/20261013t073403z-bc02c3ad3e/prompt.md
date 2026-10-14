> 脱敏副本，原件 `20261013T073403Z-bc02c3ad3e/{prompt.txt,answer.md}`。本机绝对路径、邮箱、凭据形模式及非白名单私网 IP 已替换；除脱敏与换行规范化外保留原文。

任务：只读定位「PS 侧 RX BD 环为什么卡住」。不改任何文件，不做 git 写操作。

【已实测的事实，不要重复测量、不要质疑】
- 板 BKB220 / XC7Z020，PL 100 MHz，SE150，P16 包（C_STAGE1_P_WAYS=16 / PIPE_TREE=1）。
- 全量 103616 条板端记录。客户端先上传全部读段（t_reads），再发 POST，之后计时 t_result≈8.95 s。
- 固件自报分解（同一轮的 UART 留证）：
  - 参考包（PIPE_RUN_SLEEP_US=200）：`[PIPE] total 199151 steps in 42648 callbacks, 9238 ms`，`[in-state] 686 ms`，`[waiting] 8551 ms`；其中 TX_STREAM 40162 次命中 165 ms、VOTER_WAIT 158973 次命中 134 ms。
  - 去掉节流（PIPE_RUN_SLEEP_US=0）：`[PIPE] total 5741156 steps in 5160359 callbacks, 9244 ms`，`[in-state] 6881 ms`，`[waiting] 2362 ms`；其中 **TX_STREAM 5151139 次命中 5892 ms**、VOTER_WAIT 590001 次命中 602 ms。
  - 两轮端到端都是约 9.24 s，**去掉节流没有变快**（三档 200/50/0 的斜率 0.079086/0.078348/0.079057 ms/记录，差异 <1%）。
- `[HW-CYCLES]`：Stage2 Voter 644.953 ms、Stage3 Decoder 0.022 ms。Stage1 无板端周期计数。
- 历史：2026-09-10 有过 `RX submitted=640 超过 ring free=512`、Stage1 停顿约 30 s 直接 FAIL 的实录；`MAX_BD_COUNT` 是 512；`bd_ring.c` 有按每条 BD 单独 `Xil_DCacheFlushRange` 的路径。
- 对照：P4 斜率 0.251851 ms/记录、P16 0.081426 ms/记录，比值 3.09×，接近 P4/P16 Stage1 模块周期比 3.27×。

【要回答的核心问题】
`PIPE_TX_STREAM` 的空转**只是症状**。请只读阅读 `sw/app/stage1_dna.c`（PIPE_TX_STREAM 分支）、`sw/app/bd_ring.c`、`sw/app/dma_dna.c`、`sw/app/main.c`、`sw/app/echo.c`，判定**这三类原因中哪一类最可能**，并给出判别依据：
  A. **逐 BD 或逐批的 PS 固定开销**（cache 维护、描述符写、doorbell、BD 回收循环）在 512 条一换环的节奏下累积；
  B. **环容量不足/补充策略**（512 太小、一次提交太少、导致频繁进入"环满"分支）；
  C. **Stage1 / DMA 的消费速率**才是真限制（PS 只是在等硬件）。

【必须交付】
1. `PIPE_TX_STREAM` 每一步**具体做了什么**（函数级），以及"环满"的判定语句在**哪个文件哪一行**（给标识符，行号可给但注明会过期）。
2. 上述 A/B/C 各自**已有的代码证据**（支持或反对），以及**还缺什么测量才能定论**。
3. **最小计数集**：为区分 A/B/C，最少要加哪几个计数器？每个计数器：加在哪个函数、统计什么、量纲。要求**计数本身的开销可忽略**（不要每 BD 一次 printf）。
4. **判别预期**：每种原因成立时，这些计数器会呈现什么数值特征（例如"环满次数 ≈ 环周转次数 → 指向 B"），以及**哪个结果会推翻**你的判断。
5. 若要做**不改源码**的旁证实验，给出最便宜的一个（例如用现成的 XSDB 读寄存器/计数器、或改变批次大小参数的编译宏）及其预期。

【硬约束】
- **只读**：不写/改/删文件，不 `git add/commit/push`，**不要运行 `tools/verify_repo_binding.sh`**（沙箱内 git 目录只读，必然失败）。
- 不碰板卡，不跑 Vivado/Vitis/XSim。
- 引用代码必须给真实存在的标识符；不确定就写「不确定」，不要编。
- 结论写在**最终答复**里（中文），按「函数级流程 → A/B/C 证据 → 最小计数集 → 判别预期 → 最便宜的旁证实验」组织。