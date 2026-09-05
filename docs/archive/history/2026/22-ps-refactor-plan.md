# 22 · PS 固件拆分解耦方案（2026-09-03）

`sw/app/echo.c` 已经 2,206 行、41 个函数定义、25 个文件级 `static` 变量，把 TCP 协议、流水线状态机、DMA/BD 管理、
寄存器时序、缓存维护全塞在一起。`docs/18` 技术债第 1 条要求按流水级拆分。

本文是**拆分的任务书**：模块边界、对外接口、拆分顺序，以及**每一步用什么证明
「行为没变」**。第一波（`ps-refactor-net`）只交付判据，不动 `echo.c`；
第二波（`ps-refactor`）按本文动刀。

> **本文的前提**：`docs/21` §2 的冲突表、`docs/03-status.md` 的 B21/B22/B27 三条编年、
> `AGENTS.md` 的判据纪律。**端到端唯一判据仍然是 `tools/run_g3.sh` 的图片 SHA-256
> `fcd0cf90…f2c3`**；本文加的一切只是让「拆到一半出问题」能在主机上当场发现，
> 而不是攒到上板才暴露 —— 那正是 B22/B27 的产生方式。

---

## 0. 一页结论

**先有判据，再动刀。** 判据已经就位（第一波交付，见 §1）：

```bash
bash tests/host/run_host_tests.sh --worktree     # 拆分时的行为等价判据
bash tests/host/run_host_tests.sh --selftest     # 判据自身的鉴别力自证
bash tools/run_sim.sh host                       # 已挂进回归，6/6
```

**拆成 9 个文件，分 6 步走，风险从低到高**（§3）：

```
S1 fw_log       诊断打印（250 行 xil_printf ≈ 全文 11%）
S2 reg_timing   48 处寄存器读写 → 少数几个有名字的写序列    ← B27 的正面回应
S3 bd_ring      DMA/BD 环（5 个函数 + 5 个文件级 static）    ← B21 的正面回应
S4 proto/net    协议分帧与 lwIP 回调
S5 stage1/2/3   三个 step 函数（989 行，全文 45%）           ← 风险最高，放最后
S6 上板复验     run_g3.sh 仍得 fcd0cf90…f2c3
```

**每一步一笔提交，判据是「主机侧轨迹逐行相同」。拆分是纯重构，不允许顺手改行为**
（想改行为就单独开一笔提交，否则一旦上板出问题，分不清是拆错了还是改错了）。

---

## 1. 第一波已交付的判据（`tests/host/`）

详细说明见 `tests/host/README.md`，这里只说它凭什么算判据。

**被测对象是 `sw/app/echo.c` 本身**：`tests/host/shim/echo_under_test.h` 把整份
`echo.c` `#include` 进测试单元，所以那些 `static` 函数和文件级静态量可以直接被调用、
被读。抄一份逻辑到测试里再测，测的是抄件，对 `echo.c` 的回归零鉴别力。
固件源码**一个字节都没有改**（绝对地址靠 `mmap(MAP_FIXED_NOREPLACE)` 落到
`0x10000000`，ARM 内存屏障靠两个宏抹掉，Xilinx/lwIP 用壳层）。

两类判据：

1. **纯逻辑单元测试**（约 50 条）：协议头解析、`board_caps` 对 `docs/05` 1.3 节、
   `process_batch`/`process_config`/`process_post` 的拒绝边界、
   `expand_watermark_regions` 对 `tests/golden/wm_regions.hex` 的 **47,850 个符号逐个比对**、
   差分的范围与幂等、哨兵计数、状态分派。
2. **行为轨迹判据**：驱动真实固件走完
   `accept → CONFIG → WM → BATCH×2 → POST → 118 次 poll → 回传 8,100 B`，
   把寄存器读写（含值）、`usleep`、缓存维护（地址+长度）、BD 投递/回收、
   TCP 发送、`keep_tcp_alive` 的位置按发生顺序记成 **812 行文本**，与黄金文件逐行比对。
   **固件日志文本刻意不在轨迹里**：拆分时措辞可以改，行为不可以。

**鉴别力是实测出来的，不是声称的**（`--selftest`）：四种「拆分时顺手整理掉」的改动
注进 `echo.c` 的临时副本，每一种都让判据在指定行变红 ——
`b27-start-clear`(798) / `dec-beats-order`(784) / `voter-prestart-zero`(745) /
`drop-stage2-invalidate`(725)。另外轨迹测试内部把 Decoder 的 RTL 语义换回 B27 之前那版，
固件 `PIPE_DECODER_PREP` 里那句 `write START=0x00` **本身**就把核启动了，
流水线当场失败 —— **B27 在主机上被复现，用时不到一秒**。

### 建模边界（写清楚，不许越界引用）

三个 IP 核和 AXI DMA 都是**行为模型**，不是 RTL，更不是板子。
本套判据能证明的只有一件事：**拆分前后 PS 侧的对外行为逐条相同**。
它证明不了硬件正确、证明不了时序、更证明不了端到端结果。
`AGENTS.md` 那条纪律不因为多了一套主机判据而放松：
2026-08-29~30 修掉的 7 个缺陷里有 5 个（B23~B27）在**所有仿真里都是绿的**。

---

## 2. 现状体检（数字，不是印象）

对 `HEAD:sw/app/echo.c`（2,206 行）逐行统计：

| 维度 | 数字 | 说明 |
| --- | --- | --- |
| 三个 `pipeline_step_stageN` | **989 行 = 全文 45%** | 271 / 389 / 329 |
| `xil_printf` | **250 行 = 全文 11%** | 但**不是纯日志**，见下 |
| `write_reg32` / `read_reg32` | 48 处 | 其中 `DECODER_REG_START` 9 处、`VOTER_REG_START` 9 处 |
| `Xil_DCache*` | 26 处 | 位置与范围是正确性的一部分 |
| **文件级 `static` 变量** | **25 个** | 三个流水级共享的隐式状态 —— **真正的耦合在这里** |

三条从体检里读出来、必须写进设计的结论：

1. **日志不是纯日志。** `dump_read_48()` / `dump_u64_bytes_window()` 里带着
   `Xil_DCacheInvalidateRange`；`PIPE_DONE_STAGE1` 里那段「统计前 10 个 read 的非零字节」
   读的是 DDR。所以 S1 只能**整函数搬走**，不能顺手删调用点。
2. **耦合的本体是那 25 个文件级 static**，不是函数长度。
   `tx_done` / `rx_done` / `tx_frames_*` / `rx_records_*` / `s1_no_progress` 被
   `pipeline_step_stage1`、`submit_reads_chunk`、`submit_rx_records`、
   `pipeline_reset_counters` 四处共享。拆文件而不收敛状态，等于把耦合从文件内挪到文件间。
3. **`DECODER_REG_START` 那 9 处写里，只有 4 处在实际执行路径上**（见 §5 的死状态）。
   剩下 5 处在两条从未触发的恢复路径和一段**死代码**里。拆分时不要因为
   「看起来是重复代码」就合并它们 —— 先确认哪些是活的。

---

## 3. 目标模块划分

原则：**按「对外效应的种类」切，不按「代码看起来像一类」切。**
一个模块要么只碰寄存器、要么只碰 BD 环、要么只碰 TCP —— 这样轨迹判据里每一类事件
都能对上唯一一个模块，出问题时定位是常数时间。

| # | 文件 | 内容 | 对外接口（建议） |
| --- | --- | --- | --- |
| 1 | `fw_log.{c,h}` | `dump_read_48`、`dump_u64_bytes_window`、`dump_dma_regs`、`dump_dna_regs` | `fw_dump_read48(base, idx)`、`fw_dump_u64(base, start, n, label)`、`fw_dump_dma(&dma, tag)`、`fw_dump_dna(tag)` |
| 2 | `reg_timing.{c,h}` | **所有**寄存器读写，按「有名字的写序列」封装 | `dna_select_wm_region(lc)`、`dna_enter_preload()`、`dna_leave_preload()`、`dna_start()`、`dna_stop()`；`voter_configure(&cfg)`（含回读校验）、`voter_clear_done()`、`voter_start_pulse()`、`voter_status()`；`decoder_configure(&cfg)`（含回读校验）、`decoder_start_once()`、`decoder_status()`、`decoder_ack_done()` |
| 3 | `bd_ring.{c,h}` | `setup_bd_ring`、`submit_bd_transfer`、`reclaim_some_bd`、BD 环指针与 `*MaxTransferLen` | `bdring_init(&ctx)`、`bdring_submit(ring, addr, len, kind)`、`bdring_reclaim(ring, max)`、`bdring_free_cnt(ring)` |
| 4 | `dma_dna.{c,h}` | `dna_accelerator_init`、`submit_rx_records`、`submit_reads_chunk` | `dna_dma_init()`、`dna_rx_topup(&st)`、`dna_tx_chunk(&st)` |
| 5 | `pipeline.{c,h}` | 状态枚举、`run_processing_pipeline`、`pipeline_reset_counters`、**流水线上下文结构体** | `pipeline_reset(&ctx)`、`pipeline_step(&ctx, conn)`、`pipeline_state(&ctx)` |
| 6 | `stage1_dna.c` | `pipeline_step_stage1` 的 9 个状态 | `stage1_step(&ctx, conn)` |
| 7 | `stage2_voter.c` | `voter_configure_and_verify` + `pipeline_step_stage2` 的 4 个状态 | `stage2_step(&ctx, conn)` |
| 8 | `stage3_decoder.c` | `pipeline_step_stage3` 的 4 个状态 + `validate_decoder_written_beats` | `stage3_step(&ctx, conn)` |
| 9 | `proto.{c,h}` | `parse_header`、`send_framed_pkt`、`send_ack_byte`、`board_caps`、`process_complete_packet` 的分发 | `proto_parse_header()`、`proto_send_framed()`、`proto_dispatch(conn, buf, len)` |
| 10 | `echo.c`（保留） | lwIP 回调（`accept`/`recv`/`poll`）、`start_application`、`send_result`、`process_*` 数据接收 | 现有对外接口不变（`echo.h` 不动） |

### 3.1 那 25 个文件级 static 怎么办

新增一个 `pipeline_ctx_t`，把 Stage1 的计数器全部收进去，**显式传参**：

```c
typedef struct {
    pipe_state_e state;
    int  wm_tx_expected, rx_expected, tx_expected, tx_done, rx_done;
    u32  wm_region, tx_frames_total, tx_frames_sent, tx_frames_done;
    u32  rx_records_total, rx_records_submitted;
    int  s1_last_tx_done, s1_last_rx_done;
    u32  s1_no_progress;
} pipeline_ctx_t;
```

**注意 `volatile`**：`pipe_state` 与 `g_proc_state` 现在是 `volatile`。
本工程没有中断修改它们（`XAxiDma_BdRingIntDisable` 关了 DMA 中断，
流水线全在 `tcp_poll` 回调里推进），所以 `volatile` 是历史保守写法而非必需。
**但拆分阶段照抄，不要顺手去掉** —— 去掉 `volatile` 会改变编译器的优化空间，
属于「顺手改行为」，要改单开一笔提交并说明理由。

`AxiDma` / `TxRingPtr` / `RxRingPtr` / `Tx|RxMaxTransferLen` 收进 `bd_ring.c` 的
一个 `bdring_ctx_t`；`g_conn` / `g_server_pcb` / `tcp_recv_buffer` / `tcp_recv_offset`
留在 `echo.c`（它们本来就是连接层的）。

---

## 4. 拆分顺序与每一步的判据

**每一步的判据都一样，只是覆盖面递增**：

```bash
bash tests/host/run_host_tests.sh --worktree   # 纯逻辑全过 + 812 行轨迹逐行相同
bash tools/run_sim.sh host                     # 6/6（含上位机与 LDPC）
```

**轨迹一行都不许变。** 变了就是行为变了，回退或说明理由 ——
「说明理由」意味着你要拿出「为什么这个改动是必要的、它改的是什么」，
然后单开一笔提交、`--record` 重录黄金，并在本文追加一行记录。

| 步 | 内容 | 为什么这个顺序 | 额外判据 |
| --- | --- | --- | --- |
| **S0** | **重录基线** ✅ **已于 2026-09-04 完成（`bbe4012`）** | `wm-preload` 落地后 `echo.c` 变了，黄金轨迹必须在**新的 HEAD** 上重录 | 开工前核对 `.meta` 里的 sha256 与当前 `HEAD:sw/app/echo.c` 是否一致：一致就直接进 S1，不一致说明 `echo.c` 又变了，重做一次 S0。**重录前必须先确认「只有轨迹变了、不变量没红」**——不变量也红就是缺陷，该报给改动方，不是刷新基线 |
| **S1** | `fw_log` | 风险最低：搬的是叶子函数，没有被谁依赖 | 注意 §2 结论 1：**整函数搬走**，`dump_read_48` 里的 `Xil_DCacheInvalidateRange` 必须跟着走，轨迹里那几行 `CACHE INVAL` 一行都不能少 |
| **S2** | `reg_timing` | 把 48 处散落的寄存器读写收敛成有名字的序列 —— **这是 B27 的正面回应**：序列从此是可审计、可回放的对象，而不是散在 989 行里的孤立语句 | 轨迹里 `REGW`/`REGR`/`SLEEP` 的**顺序与值**逐行相同；`--selftest` 四条注入仍全部变红 |
| **S3** | `bd_ring` + `dma_dna` | BD 环是 B21 的现场，但它的接口面很窄（5 个函数），且已被轨迹里的 `DMA TOHW/FROMHW` + 每个 BD 一行 `CACHE FLUSH` 钉死 | 轨迹里 BD 的 flush **必须仍是逐个 64 B**（B21 第 3 条：不能退回 `bd_count*64` 那种「假设连续」的批量刷） |
| **S4** | `proto` + 连接层 | 协议侧纯逻辑多、已有 50 条单测护着 | `TCP WRITE`/`TCP OUTPUT` 的字节数与顺序逐行相同 |
| **S5** | `stage1/2/3` | 989 行、共享 25 个 static，风险最高。前四步已经把它依赖的东西都变成了显式接口，此时拆才是「搬运」而不是「重写」 | 建议**一级一笔提交**（stage3 → stage2 → stage1，从下游往上游，因为下游依赖最少） |
| **S6** | 上板复验 | 主机判据再全也证明不了硬件 | `bash tools/run_g3.sh` 退出码 0 且图片 SHA-256 = `fcd0cf90…f2c3`；重建 ELF 后**必须**刷新 `hw/build/export/SHA256SUMS`，否则 `run_g3.sh` 的制品同源性校验会挡住你（那是故意的，不要绕过） |

### 4.1 判据覆盖不到的地方（先知道，别自欺）

轨迹判据跑的是**一条**场景：SE150 / 128 条 / `score_min=67` / 50 个水印区域 / 全部顺利。
它**没有**覆盖：

- 失败路径（BD 报错、配置回读不符、看门狗触发、Voter/Decoder 超时）；
- 规模相关的分支：128 条时 `submit_rx_records` **一次投完**，
  `RX_OUTSTANDING_MAX=512` 的节流和 1,024 个 BD 的**环回绕**都没走到
  —— 而那正是 B21 的现场；
- 三级 IP 的真实时序、AXI 错误响应、DDR 控制器。

**S5 之前建议先把场景补到 2,048 条**（`TASK_READS`，`test_echo_trace.c` 顶部一个宏），
让 RX 环真的回绕两次；那时轨迹会长很多（BD 每条一行 `CACHE FLUSH`），
可以考虑给轨迹加一个「BD 批量」的压缩形式 —— 但压缩必须保留「逐个 flush」这个事实，
否则就把 B21 第 3 条的鉴别力压没了。这件事本身要单独做一笔提交并跑一次 `--selftest`。

---

## 5. 设计时必须尊重的既有约束

**这一节不是背景介绍，是禁止事项。** 每一条都有出处。

### 5.1 poll 的节奏是 lwIP 定的，不是随意写的

`run_processing_pipeline()` **每次只推进一个状态**，由 `tcp_poll` 驱动，
实测有效间隔 **250~500 ms**（两个互不清零的 `tcp_slowtmr` 驱动源叠加，
机理见 `echo.c` 的 `S1_NO_PROGRESS_LIMIT` 注释与 `docs/18`）。

- **不许**把状态机改成「一个 poll 里跑到底」：`poll_callback` 长时间不返回会饿死 TCP。
- **不许**照注释里的「500 ms/步」去折算超时常数 —— 三处注释都是错的，
  实际约 280 ms，据此算的超时差一倍（`docs/03-status.md` 已记录，
  当时**只改注释不改数值**，因为改数值要重建 ELF 并重新上板复验）。
  拆分**同样不许改这些数值**：`S1_NO_PROGRESS_LIMIT=60`、Stage3 的 `poll_count > 240`、
  Voter 的 `poll_count >= 100000` 原样搬过去。

### 5.2 寄存器写序列本身就是被测对象

「写 0 → 写 1 → `usleep` → 写 0」这类顺序**不能在重构中被「整理」掉**。
仿真判据 `run_xsim.sh dec_restart`（`hw/sim/dec/tb_dec_ddr_restart.v`）和
`run_xsim.sh vot_ddr` 正是在**回放固件原样的寄存器时序**；
主机侧 `--selftest` 的 `b27-start-clear` / `dec-beats-order` / `voter-prestart-zero`
三条注入是同一件事的主机版。

具体地：

- Stage1 预载：`写 reg1=区域号 → usleep(10) → 写 reg0=PRELOAD → usleep(10) → DMA →
  等完成 → 写 reg0=0 → usleep(10)`。**顺序不能反**（先选区域再进预载模式）。
- Stage2：`START` 脉冲是 `写 0 → usleep(100) → 读 STATUS 确认 IDLE → 写 1 →
  usleep(100) → 写 0 → usleep(100)`。
- Stage3 配置：**先写地址、最后才写 beats**，且 `OUT_BEATS` 在 `IN_BEATS` 之前
  （注释写着「最后才写 beats，避免触发自动启动」）。
- Stage3 启动：**只写一次 `START=0x01`，之后到 DONE 之前不许再碰这个寄存器**（B27-③）。

### 5.3 缓存维护是正确性的一部分

26 处 `Xil_DCache*` 的**位置与范围**都不是样板代码：

- Stage2 输入区按 **256 KB 分块** invalidate，且按**本次任务的实际字节数**
  （`ddr_layout_stage1_bytes()`），不是按 `TOTAL_READS` 的预留容量（C1）。
- 硬件写完之后给 CPU 读，**只 invalidate 不 flush**（`PIPE_DONE_STAGE2` 里
  标着 `[FIX]` 的那两处）。反过来会把 CPU 的旧缓存行写回 DDR，覆盖掉硬件刚写的结果。
- BD 是**逐个** flush 的（沿 `BdRingNext` 走），不是 `bd_count*64` 批量刷 ——
  BD 环会回绕，批量刷会刷到环外、漏掉回绕的那几个（B21 第 3 条）。

### 5.4 别把死代码当活代码合并

**实测事实**（由 `tests/host/test_echo_pure.c` 的 J 节和轨迹里
`dec_start_writes == 4` 两处钉死）：

- `PIPE_SEND_RESULT` **落在 `run_processing_pipeline()` 三个区间判断之外**
  （`[IDLE,DONE_STAGE1]` / `[VOTER_PREP,DONE_STAGE2]` / `[DECODER_PREP,DONE_STAGE3]`），
  一旦真的走到这个状态会**直接判 FAIL**。
- 现在走不到，是因为 `PIPE_DECODER_WAIT` 在 DONE 时把 `pipe_state` 置成
  `PIPE_DONE_STAGE3` 并返回，`poll_callback` 当场把 `g_proc_state` 推成 `PROC_DONE`，
  下一次 poll 直接 `send_result()`。
- **后果**：`case PIPE_DONE_STAGE3` 的整段函数体（最终校验 + `[CLEANUP]` 复位 +
  「forcing dummy run」里那次 `写 START=0x01`）**从来没有执行过**。

**所以**：拆分时若改动 `poll_callback` 与 `PIPE_DONE_STAGE3` 的先后，
就会让这段死代码活过来，而它会**再启动一次 Decoder** —— 正是 B27 那一类。
建议在 S5 单独开一笔提交处理这两个状态（删除死代码 or 让它真正执行），
**不要混在搬运提交里**，并且那笔提交必须重录轨迹 + 上板复验。

### 5.4a 已经有一个「序列封装」，但它没被用 —— 别顺手接上去

`trigger_ip_start()`（`echo.c:144`）和 `dump_u64_bytes_window()`（`echo.c:125`）
**定义了但全文一次都没被调用**（`clear_ip_start()` 只在 `echo.c:716` 用了一次）。

这不是「删掉就行」的死代码，而是 S2 的一个陷阱：`trigger_ip_start()` 的序列是

```c
写 reg0=0x00 → usleep(10) → 写 reg0=0x01
```

而 `PIPE_START_IP` 实际做的是

```c
写 reg0=0x01 → usleep(50)
```

**两者不等价**（少一次预置 0、延时也不同）。看到「这里有个现成的函数，
顺手接上去就统一了」——**接上去就是改行为**，轨迹判据会立刻变红（这是好事）。
S2 的正确做法：先按 `PIPE_START_IP` 的**实际**序列定义 `dna_start()`，
把 `trigger_ip_start()` 连同它那个从未被验证过的序列一起删掉，并在提交信息里写明
「删的是死函数，采用的是实际执行过的序列」。

### 5.5 `echo.h` 的对外接口本波不动

`echo.h` 里的宏（DDR 地址、寄存器偏移、尺寸）与 `dna_connection_t` 是三方共享的契约
（`docs/05-interfaces.md`）。拆分只动 `.c` 的组织方式；要改 `echo.h` 就是改契约，
按 `AGENTS.md` 得同步改文档并三方成对修改。

---

## 6. 第二波开工检查表

1. `bash tools/verify_repo_binding.sh --remote` PASS，且 `wm-preload` 已落地
   （`echo.c` 写权已释放，见 `docs/21` §6）。
2. **S0 先做**：`bash tests/host/run_host_tests.sh --record`，
   确认 `--worktree` 立刻全绿，`.meta` 里的出处指向新的 HEAD。
   （`tests/host/inject.py` 的四个注入点若因 `wm-preload` 的改动而失效，
   脚本会**报错退出**而不是悄悄变成空操作 —— 报错就更新注入点。）
3. 按 §4 的 S1→S5 一步一笔提交，每笔提交前跑 `--worktree` + `run_sim.sh host`。
4. 轨迹变了就停下来，先回答「变的是哪一行、为什么」，再决定回退还是重录。
5. S6 上板：申请板子令牌（`docs/21` §3），`bash tools/run_g3.sh`，
   重建 ELF 后刷新 `hw/build/export/SHA256SUMS`。
6. 结论写回本文 §7 与 `docs/18` 技术债第 1 条。

---

## 7. 记录

| 日期 | 事项 |
| --- | --- |
| 2026-09-03 | 第一波（`ps-refactor-net`）：`tests/host/` 判据落地并挂进 `tools/run_sim.sh host`（6/6）。基线 `echo.c` = 2,206 行、sha256 前 16 位 `f5a036486673fba7`（当时的 `HEAD:e25dab1`），轨迹 812 行，四种故障注入全部变红。**未动 `sw/app/echo.c`。** |
| | ⚠️ **提交归属对不上（两次）**：`tests/host/*` + `tools/run_sim.sh` 被 `430c1c6`（标题是 AGENTS.md 的事）带走，本文 + `docs/README.md` 被 `7747e9e`（标题是 SE250 阶段 S1 的 RTL）带走 —— 都是暂存后被并行会话的提交扫走的，正是 `AGENTS.md` 里「禁止 `git add -A`」那条要防的情况。**内容完好、已在 `origin/main`**，只是按提交标题找不到出处，所以记在这里。 |
| 2026-09-04 | **S0 已完成**（`bbe4012`）：`wm-preload` 的 `a2a8067`（水印预载批量化）落地后重录基线 —— `echo.c` 2,335 行、sha256 前 16 位 `32cb28ea87229f74`（`HEAD:2a67a07`），轨迹 812 → **816 行**。重录前先确认「只有轨迹变了、行为没坏」：13 条与轨迹无关的不变量在新 `echo.c` 上全过。重录后四条注入各自在 802/788/749/729 行变红（重录前四条都停在第 26 行 —— 那是基线漂移，不是注入生效，判据当时已经失去鉴别力）。**第二波不必再做 S0，除非 `echo.c` 又被改过**（`.meta` 里的 sha256 与当前 `HEAD:sw/app/echo.c` 对不上就要重做）。 |
| 2026-09-04 | **S1~S6 全面闭环（`ps-refactor` 会话）**：<br>1. **S1**（`1548b4f`）：拆分 `fw_log.{c,h}`，整函数迁移 dump 工具并保留 ARM 内存屏障；<br>2. **S2**（`582c871`）：拆分 `reg_timing.{c,h}`，收敛 48 处硬件寄存器读写时序；<br>3. **S3**（`fe00169`）：拆分 `bd_ring.{c,h}` + `dma_dna.{c,h}`，封装描述符环与 DMA 提交/回收；<br>4. **S4**（`961f181`）：拆分 `proto.{c,h}`，封装协议解析与发包；<br>5. **S5a/b/c**（`b75534b`, `108c4ae`, `2cb7177`）：按流水级拆分为 `stage3_decoder.{c,h}`、`stage2_voter.{c,h}`、`stage1_dna.{c,h}`，创建状态机核心 `pipeline.{c,h}`；在 `send_result` 中嵌入 B29 诊断探针（统计 `sndbuf_zero`、重试计数及发送余量）；`sw/app/echo.c` 由 2,335 行瘦身至 578 行；<br>6. **环境适配**（`4c8f65d`）：移除多余 `<unistd.h>` 解决与 Xilinx Standalone `sleep.h` 符号冲突，收敛流水线计时全局符号；<br>7. **S6 编译与上板**：Vitis workspace 适配 20 个 C 源码多目标编译，ARM gcc 编译链接生成 `dna_lwip_app_b27.elf`，bootgen 重建 `BOOT.bin`，刷新 `export/SHA256SUMS`；<br>8. **板级实测**：<br> - 单轮（`run 20260904T115419Z-ps-refactor-s6`）：2048 源读段（4096 记录），图片 SHA-256 = `fcd0cf90bd680e7bbdc203e3398119504da0897acac9e2117008b4efb6b1f2c3` 逐位一致，四级 DDR 取证 4/4 级全绿！UART 证实 B29 探针工作正常（`Enqueued 8100 bytes (retries: hdr=0, data=0, sndbuf_zero=0, sndbuf_avail=84)`）；<br> - 连续两轮（`run 20260904T115512Z-ps-refactor-s6-runs2`）：第 1 轮 `score_min=0` 弄脏轮（耗时 9s）+ 第 2 轮 `score_min=67` 判据轮（耗时 11s），弄脏轮鉴别力自证通过（两轮相差 6277/64800 bit），判据轮图片哈希与四级 DDR 取证全绿！ |

### 一个顺带量到的数（**是模型侧数字，不是板级实测**）

同一场景（128 条）从 **118 次 poll 降到 22 次**（`a2a8067` 前后，均为主机模型），各项不变量（50 个区域 × 957 符号、128 条记录、
Decoder 只启动 1 次、回传 8,100 B 逐字节相同）全过。

**这只能说明「poll 步数确实收敛了」，不能当性能结论引用**：主机模型里没有真实的
250~500 ms poll 间隔，也没有真实 DMA 时序。性能结论以 `wm-preload` 自己的
`tools/g3_timing_fit.py` 板级对照拟合为准（`docs/21` ② 的判据）。
把它记在这里，是因为 `docs/19` §3 复盘过的那个坑值得再防一次：
**扣除法/模型侧的推断进了表格之后，会被下一个人当实测引用。**
