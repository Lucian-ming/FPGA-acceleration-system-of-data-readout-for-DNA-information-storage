> 脱敏副本，原件 `20261013T075536Z-2694685d7b/{prompt.txt,answer.md}`。本机绝对路径、邮箱、凭据形模式及非白名单私网 IP 已替换；除脱敏与换行规范化外保留原文。

已完成函数级计时埋点；只在任务结束时输出一个 `[PROF]` 块，没有在热路径逐条打印。**未修改状态转移、BD 提交策略、缓存范围与顺序或协议字节。**

### `sw/app` 改动

- [prof.h](<仓库根目录>/sw/app/prof.h)：新增集中式计数器和计时宏；未定义 `PROF_ENABLE` 时埋点宏无运行时开销。
- [prof.c](<仓库根目录>/sw/app/prof.c)：新增任务计数器重置、一次性打印和毫秒格式化。
- [bd_ring.c](<仓库根目录>/sw/app/bd_ring.c)：累计提交/回收次数与 BD 数，函数 ticks 按 1/256 抽样。
- [stage1_dna.c](<仓库根目录>/sw/app/stage1_dna.c)：覆盖 WM 展开与预载、TX_STREAM 进入次数、低水位恢复、usleep 和 helper 调用。
- [main.c](<仓库根目录>/sw/app/main.c)：统计 `xemacif_input` 调用数和抽样耗时。
- [dma_dna.c](<仓库根目录>/sw/app/dma_dna.c)：统计读段 DMA 缓存 flush。
- [fw_log.c](<仓库根目录>/sw/app/fw_log.c)：统计调试读取用的缓存 invalidate。
- [stage2_voter.c](<仓库根目录>/sw/app/stage2_voter.c)：统计缓存操作，并计时 Voter 输出到 Stage3 输入的逐字节差分循环。
- [stage3_decoder.c](<仓库根目录>/sw/app/stage3_decoder.c)：统计全部缓存操作；轮询中的高频 invalidate 按 1/256 抽样。
- [echo.c](<仓库根目录>/sw/app/echo.c)：在任务开始重置计数器、成功或失败结束时打印一次，并累计 `send_result` 耗时和成功入队的 payload 字节数。

缓存函数的所有实际调用点都已接入统计宏。`serialize_ticks` 计量当前 PS 路径中将 Voter 结果转换为 Stage3 打包输入的 XOR 循环；当前实现没有独立的结果序列化函数。

### 构建

新包路径：[bkb220-p16-prof-20261013T080142Z-board-migrate](<仓库根目录>/hw/build/bkb220-p16-prof-20261013T080142Z-board-migrate)。

实际执行：

```bash
make -C hw/build/bkb220-p16-prof-20261013T080142Z-board-migrate/workspace/dna_lwip_app -B
```

副本 Makefile 注入了 `-DPIPE_RUN_SLEEP_US=0 -DPROF_ENABLE=1`。构建退出码为 0，输出：

```text
APP_BUILD_PASS source=sw/app BSP=generated-from-P16-XSA lwip=lwip211_v1_8
```

新 ELF 位于 [dna_lwip_app.elf](<仓库根目录>/hw/build/bkb220-p16-prof-20261013T080142Z-board-migrate/workspace/dna_lwip_app/Debug/dna_lwip_app.elf)；`prof.o` 已生成。副本内 `.c` 与 `prof.h` 已核对和 `sw/app` 同步，`SHA256SUMS` 已重签并通过校验。构建有若干未修改代码的 `-Wall/-Wextra` 警告，但没有编译错误。

### 计数精度与抽样开销

- `submit` / `reclaim` 的调用数和成功提交、回收的 BD 数精确；函数 ticks 每 256 次调用抽一个样本，并乘 256 估算。
- Cache 调用数和字节数精确；BD 描述符 flush ticks、Stage3 轮询 invalidate ticks 抽样 1/256，其余缓存操作 ticks 精确。
- TX_STREAM 的 enter、lowwater、usleep 次数精确；helper ticks 按各 helper 类别分别抽样 1/256。`netif_input` 调用数精确、ticks 抽样 1/256。
- lowwater 路径、`send_result`、WM 展开、WM 区域预载和 XOR 转换循环的 ticks 精确。`send_result` 耗时包含 ARP、重试和等待确认；bytes 只统计成功入队的结果 payload，不含 8 字节头。
- 按 1/256 抽样时，每 256 次调用只有一个样本调用入口和出口的 `XTime_GetTime`，即平均约 0.78% 的计时器读取数相对于调用数；其余调用只更新计数器。该比例是静态开销估算，未做板上测量。

计数区间从 `PROC_REQUESTED` 开始，到发送结果或处理失败结束；此前的启动和收包缓存操作会在任务开始时清零。

### 未完成项

未上板、未运行 Vivado/XSim，因此没有运行时 `[PROF]` 数据。新包是编译暂存副本，`export/dna_lwip_app.elf` 和 `BOOT.bin` 仍是参考包内容，没有重打完整发布制品。`sw/workspace/dna_lwip_app_b27/src` 同步及对应卫生检查留给 main 处理；本任务未执行 Git 写操作。
