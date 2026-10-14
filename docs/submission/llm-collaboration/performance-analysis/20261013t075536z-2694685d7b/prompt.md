> 脱敏副本，原件 `20261013T075536Z-2694685d7b/{prompt.txt,answer.md}`。本机绝对路径、邮箱、凭据形模式及非白名单私网 IP 已替换；除脱敏与换行规范化外保留原文。

任务（workspace-write，看板名 **prof-instr**）：给 PS 裸机固件加**函数级耗时埋点**，用于产出「每一步耗时」的精细预算。**只加测量，不改任何功能语义。**

【背景】
- 项目 <仓库根目录>，PS 裸机 lwIP 固件在 `sw/app/`。
- 已有埋点只到**状态级**：`sw/app/echo.c` 里 `pipe_state_hits[PIPE_STATE_COUNT]` / `pipe_state_cyc[]`，18 个状态（IDLE/WM_PREP/WM_TX/RX_PREP/TX_PREFILL/START_IP/TX_STREAM/PROGRESS/DONE_STAGE1/VOTER_PREP/VOTER_START/VOTER_WAIT/DONE_STAGE2/SEND_RESULT/DECODER_PREP/DECODER_START/DECODER_WAIT/DONE_STAGE3），结束时打印 `[PIPE-BREAKDOWN]`。
- 但 `PIPE_TX_STREAM` 内部被裹在一起，实测它在「运行期不休眠」时占总时间 64%（5892 ms / 9244 ms），却看不出里面各占多少。

【要加什么】（全部只累加计数，任务结束时**一次性**打印一个 `[PROF]` 块；**禁止在热路径里逐条 printf**）
| 计数器 | 加在哪 | 统计 |
|---|---|---|
| `sub_calls` / `sub_bds` / `sub_ticks` | `sw/app/bd_ring.c` 的 `submit_bd_transfer` | 调用次数、提交 BD 总数、函数耗时 ticks |
| `rec_calls` / `rec_bds` / `rec_ticks` | `sw/app/bd_ring.c` 的 `reclaim_some_bd` | 调用次数、回收 BD 总数、函数耗时 ticks |
| `flush_calls` / `flush_bytes` / `flush_ticks` | 所有 `Xil_DCacheFlushRange` 调用点（`bd_ring.c:129`、`dma_dna.c:113`、`stage3_decoder.c:122`、`stage1_dna.c:257`、`stage1_dna.c:416` 等，请自行 grep 全） | 调用数、字节数、ticks |
| `inv_calls` / `inv_bytes` / `inv_ticks` | 所有 `Xil_DCacheInvalidateRange` 调用点（同上自行 grep 全） | 同上 |
| `tstream_enter` / `tstream_lowwater_enter` / `tstream_lowwater_usleeps` / `tstream_lowwater_ticks` | `sw/app/stage1_dna.c` 的 `PIPE_TX_STREAM` 分支与其 `free_rx < 100` 恢复路径 | 进入次数、进入低水位恢复的次数、内部 `usleep(50)` 执行次数、该恢复路径总 ticks |
| `tstream_helper_ticks` | 同上，包裹 `reclaim_some_bd` + `submit_rx_records` + `submit_reads_chunk` 三段调用 | 三段合计 ticks |
| `netin_calls` / `netin_ticks` | `sw/app/main.c` 调 `xemacif_input` 处 | 调用数、总 ticks |
| `sendres_ticks` / `sendres_bytes` | `sw/app/echo.c` 的 `send_result` | ticks、发出字节 |
| `wmx_ticks` / `wmpre_ticks` | WM 展开与预载处（`stage1_dna.c` 的 `WM_PREP` 分支） | ticks |
| `serialize_ticks` | 结果打包/展开处 | ticks |

【硬性要求】
1. **不改功能语义**：不得改动任何状态机转移、提交策略、缓存操作的范围与顺序、协议字节、几何参数。唯一允许的行为变化是**多打印一个 `[PROF]` 块**。
2. **热路径开销要可忽略**：`submit_bd_transfer` / `reclaim_some_bd` 会被调用十万次量级，**必须每 256 次调用才读一次 `XTime_GetTime`**，并把结果乘 256 折算；纯计数（`calls`/`bds`/`bytes`）可以每次都加。在注释里写明哪些是抽样折算、折算比是多少。
3. 用 `XTime_GetTime` / `COUNTS_PER_SECOND`（与既有代码一致，见 `dna_time.h`），**不要引入新的计时设施**。
4. 埋点代码集中放一个新增的 `sw/app/prof.h` + `sw/app/prof.c`（宏/内联函数形式，未启用时零开销），**不要散落一堆全局变量在各文件**。提供 `PROF_BEGIN/PROF_END` 之类的宏。
5. 结束时打印格式示例（单位 ms，保留 3 位小数），便于机器解析：
```
[PROF] submit: calls=%u bds=%u ms=%u.%03u (sampled 1/256)
[PROF] reclaim: ...
[PROF] cache_flush: calls=%u bytes=%u ms=...
[PROF] cache_inval: ...
[PROF] tstream: enter=%u lowwater=%u usleeps=%u helper_ms=... lowwater_ms=...
[PROF] netif_input: calls=%u ms=...
[PROF] send_result: bytes=%u ms=...
[PROF] wm_expand_ms=... wm_preload_ms=... serialize_ms=...
```
6. **构建**：用 `tools/build_sw_variant.sh` 之外的路径也行，但你必须**实际编译通过**再交付。参考包是 `hw/build/bkb220-p16-enet0-software-20261012T144141Z-board-migrate`；应用 Makefile 在它的 `workspace/dna_lwip_app/`（`make -C <dir>`，工具链 `<本机路径>`）。为了不带人工等待，编译时请在这份**参考包派生出的新包副本**里构建（不要改参考包本身），并把 `-DPIPE_RUN_SLEEP_US=0` 一并注入（细粒度测量要在无睡眠下做，否则时间被空等淹没）。构建方法可参考 `tools/build_sw_variant.sh`，但你要把 `sw/app/*.c` 的改动同步进新包的 `workspace/dna_lwip_app/src/`。
7. **不要**在 `hw/build/` 下已有的参考包（`bkb220-p16-enet0-software-*`、`bkb220-p4-*`）里就地修改；新包另起名字，例如 `hw/build/bkb220-p16-prof-<UTC时间戳>-board-migrate`。

【硬约束】
- **不要执行任何 Git 写操作**（不 add/commit/push）。**不要运行 `tools/verify_repo_binding.sh`**（沙箱内 git 目录只读，必然失败，白跑）。
- 不要碰板卡，不要跑 Vivado/XSim。
- 改完 `sw/app/` 后，`tools/check_repo_hygiene.sh` 有一条「sw/app/ 与 sw/workspace/dna_lwip_app_b27/src 同名文件必须逐字节相同」——**这条留给 main 处理，你不要动 `sw/workspace/`**，但要在答复里明确列出你改了 `sw/app/` 的哪些文件。
- 看板：用 `tools/agent_view.sh start/update/done --agent prof-instr --doing ... --why ... --next ...` 自行登记（workspace-write 由你登记）。

【交付】
1. 改动的文件清单与每个文件改了什么（一句话）。
2. **实际编译命令与 `APP_BUILD_PASS` 输出**，以及新包路径。
3. 抽样折算比与开销估算（为什么热路径开销可忽略）。
4. 你能确认的边界：哪些计数器是精确值、哪些是抽样折算。
答复用中文。