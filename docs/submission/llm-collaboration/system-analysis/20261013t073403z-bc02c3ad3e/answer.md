> 脱敏副本，原件 `20261013T073403Z-bc02c3ad3e/{prompt.txt,answer.md}`。本机绝对路径、邮箱、凭据形模式及非白名单私网 IP 已替换；除脱敏与换行规范化外保留原文。

## 函数级流程

`PIPE_TX_STREAM` 的入口在 [`stage1_dna.c` 的 `pipeline_step_stage1`](<<仓库根目录>/sw/app/stage1_dna.c:274>)。每次进入后按这个顺序执行：

1. 调用 `reclaim_some_bd(RxRingPtr, 512)`，把已完成的 RX BD 回收到软件环；返回数量加到 `rx_done`。
2. 调用 `submit_rx_records()` → `dna_submit_rx_records()`。它按 `records_submitted - rx_done` 算未完成数，受 `RX_OUTSTANDING_MAX` 限制，再按 RX 环当前 free BD 数裁剪提交量；每条 48 B 记录一个 BD。
3. 读取 RX 环 free count。`free_rx < 100` 且还有 TX 帧未发出时，最多再试五次 RX 回收；每次未达到 `free_rx >= 150` 就 `usleep(50)`。未恢复时提前结束本次 `PIPE_TX_STREAM`，让主循环稍后再进。
4. 调用 `submit_reads_chunk()` → `dna_submit_reads_chunk()`。它先回收 TX BD；若 TX free BD `<=128`，本次不提交。否则按可用数、最多 100 帧和剩余帧数计算批量，flush 输入数据后提交。
5. 再回收一次 TX BD，更新 `tx_done`。若 TX/RX 完成计数持续 30 秒不变，则报停滞并失败；全部 TX/RX 完成后停止 DNA 核。

其中 RX “接近满环”的流控判断是 [`free_rx < 100 && tx_frames_sent < tx_frames_total`](<<仓库根目录>/sw/app/stage1_dna.c:286>)。RX 提交时的容量裁剪是 [`if (n > free_bd) n = free_bd`](<<仓库根目录>/sw/app/dma_dna.c:69>)，裁剪后 `n == 0` 会直接返回 0；通用提交函数另有硬错误检查 [`free_bd < bd_count`](<<仓库根目录>/sw/app/bd_ring.c:86>)。因此源码里没有一个单独的 RX “满环就报错”分支：当前实际行为是 free 少时缩小甚至跳过提交，并在 `free_rx < 100` 时尝试恢复。

[`submit_bd_transfer`](<<仓库根目录>/sw/app/bd_ring.c:50>) 逐 BD 写地址、长度和控制字段；逐 BD 做描述符 cache flush；每批调用一次 `XAxiDma_BdRingToHw`。[`reclaim_some_bd`](<<仓库根目录>/sw/app/bd_ring.c:145>) 每次调用 `FromHw`，逐 BD 检查状态后再归还 BD。

`echo.c` 的 `poll_callback` 对每次状态调用计时，并且进入 `PIPE_TX_STREAM` 后就让出；`main` 随后按 `PIPE_RUN_SLEEP_US` 休眠或立即再次轮询。参见 [`echo.c` 的 `poll_callback`](<<仓库根目录>/sw/app/echo.c:331>) 和 [`main.c` 的主循环](<<仓库根目录>/sw/app/main.c:304>)。以下行号只对应当前 checkout，可能随代码变动；函数名和条件标识符更稳定。

## A/B/C 证据

**当前吞吐瓶颈最可能是 C：Stage1 / DMA 消费速率。** 这是基于现有数据的判断，不是源码单独能证明的结论。

| 原因 | 已有支持 | 反证或缺口 |
|---|---|---|
| **A：PS 固定开销** | `submit_bd_transfer` 对每个 BD 设置字段并逐个 flush；`reclaim_some_bd` 对每个完成 BD 检查状态。每条记录一个 RX BD，故 103,616 条记录对应约 103,616 次 BD 处理。每个 `PIPE_TX_STREAM` 还会调用 RX 回收、`dna_submit_reads_chunk` 内的 TX 回收，以及之后另一次 TX 回收。 | 这些函数的累计耗时目前没有拆分。`PIPE_TX_STREAM` 的状态计时也包含空轮询和内部等待，不能把 5,892 ms 直接归因于 cache flush 或描述符工作。 |
| **B：容量／补充策略** | 按给定的 512 BD 环容量，103,616 个记录相当于约 203 次满容量周转。代码用 `RX_OUTSTANDING_MAX`、free count 裁剪提交，并在 `free_rx < 100` 时进入恢复路径。历史 640 对 512 的失败记录也说明过度预投会出问题。 | 当前 RX 提交先按 free count 裁剪，满环时会提交 0，而不是像历史批量路径那样直接提交超过容量的数量。现有 UART 摘要没有 `free_rx` 低水位命中、裁剪量或恢复次数，不能证明小环造成了当前延迟。环周转次数本身不等于容量瓶颈。 |
| **C：Stage1／DMA 消费速率** | 200/50/0 µs 的端到端耗时几乎不变；去掉休眠只是把 `[waiting]` 从 8,551 ms 降到 2,362 ms，同时 `[in-state]` 从 686 ms 升到 6,881 ms，`TX_STREAM` 计时升到 5,892 ms。这说明更快轮询没有提高吞吐，主要把等待变成了忙轮询。P4/P16 斜率比 3.09×，接近 Stage1 模块周期比 3.27×。 | Stage1 没有板端周期计数。现有状态计时不能区分硬件等待、重复查询 DMA 和 PS 描述符工作的时间；C 仍是强推断。 |

另外，RX 输出数据的 `Xil_DCacheInvalidateRange` 在 `PIPE_RX_PREP` 对整个输出区做一次；代码证据显示的逐 BD cache 操作是**描述符** flush，不能笼统说成每条输出记录都逐 BD invalidate。

源码中有容量注释写着 1024，而初始化把 `MAX_BD_COUNT_RX` 传给 `setup_bd_ring`；本判断按你给出的实测容量 512 作为事实，未用这些注释推断环大小。

## 最小计数集

计数只保存在 RAM，任务结束时汇总打印；不在 BD 循环里逐条打印。周期统计对高频回收调用每 256 次抽样一次并折算，避免给百万次空轮询增加定时器读取开销。

| 计数 | 加入位置 | 统计内容与量纲 |
|---|---|---|
| `submit_calls / submit_bds / submit_ticks` | `submit_bd_transfer` | 调用次数、提交 BD 总数、函数耗时总 XTime ticks。提交计数在每批加一次；周期每 256 次抽样，覆盖分配、BD 字段写入、逐 BD flush 和 ToHw。 |
| `reclaim_calls / reclaimed_bds / reclaim_ticks` | `reclaim_some_bd` | 调用次数、回收 BD 总数、函数耗时总 XTime ticks。BD 数每次调用按返回的 `n` 累加；周期每 256 次抽样。 |
| `rx_free_limited / rx_short_bds / rx_low_water / rx_recovery_exhausted` | `dna_submit_rx_records` 和 `PIPE_TX_STREAM` 的低水位分支 | free count 不足而裁剪的次数、被裁掉的 BD 数、进入 `free_rx < 100` 的次数、五轮后仍提前返回的次数。单位为事件次数和 BD 数。另记 `rx_min_free`（BD 数）。 |
| `stream_no_progress / sampled_no_progress_ticks` | `PIPE_TX_STREAM` | 有 DMA 在途且本次没有 TX/RX 完成或新提交的次数，以及该类调用每 256 次抽样的 XTime ticks。单位为调用次数和 ticks。已有 `echo.c` 的 `pipe_state_hits` 与 `pipe_state_cyc` 可作总调用数和总状态耗时基线。 |

## 判别预期

- **A 成立**：`submit_ticks + reclaim_ticks` 占 `TX_STREAM` 总耗时的大部分，且按 BD 数归一后每 BD 成本稳定；RX 低水位和 free 裁剪并不频繁。若 helper 耗时只占很小比例，A 就解释不了当前吞吐。
- **B 成立**：`rx_free_limited`、`rx_low_water` 和 `rx_recovery_exhausted` 相对约 203 次满容量周转反复出现，裁剪的 `rx_short_bds` 很多，且 `rx_min_free` 长期接近 0。若这些事件很少、RX 批量基本能按目标补足，B 就被削弱。
- **C 成立**：在途工作未完成时 `stream_no_progress` 很高，但 RX 容量压力少、A 的 helper 耗时占比低；完成速率与 P4/P16 的计算能力差异相符。若 no-progress 很少，或 A/B 的计数已覆盖大部分耗时，则当前 C 判断应推翻。

## 最便宜的旁证实验

只读 XSDB 采样现有 DNA DMA 的 S2MM 状态、当前描述符和尾描述符寄存器，例如每 10–100 ms 采样一次。若状态持续运行且当前描述符稳定向前推进、尾描述符也持续被 PS 推进，配合低容量压力计数，会加强 C 的判断；若当前描述符反复追到尾描述符并停住，或 S2MM 进入 Idle，则更支持 RX 补充/环容量路径存在瓶颈。寄存器采样本身不能单独区分 A 和 B，但比重编译或改镜像更便宜。

本轮未执行 XSDB，也未碰板卡。你给出的 `PIPE_RUN_SLEEP_US=200/50/0` 扫描已经是最低成本的无源码轮询旁证：它排除了主循环休眠是主要吞吐限制，但单靠它不能区分 A/B/C。

**产出路径：** 本次最终答复；没有写仓库文件。  
**验证结果：** 只读检查了指定的五个源码文件；未执行 Git 写操作或绑定脚本，未运行仿真、构建或硬件测试。  
**未完成项：** 缺少 A/B/C 最小计数集的板端数据，因此 C 是当前最可能原因，尚未达到实测定论。
