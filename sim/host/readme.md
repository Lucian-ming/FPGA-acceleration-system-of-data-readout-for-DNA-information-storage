# `sim/host/` —— PS 固件（`sw/app/echo.c`）的主机侧判据

一条命令：

```bash
bash sim/host/run_host_tests.sh              # 用 HEAD 里的 echo.c（默认）
bash sim/host/run_host_tests.sh --worktree   # 用当前工作树的 echo.c（做拆分时用这个）
bash sim/host/run_host_tests.sh --selftest   # 故障注入，证明判据能失败
bash sim/host/run_host_tests.sh --record     # 重录行为轨迹黄金文件
```

也已挂进 `bash src/tools/run_sim.sh host`。单一 PASS/FAIL、非零退出码。

## 它凭什么算判据

**被测对象是 `sw/app/echo.c` 本身，不是它的一份抄写。**
`sim/host/shim/echo_under_test.h` 把整份 `echo.c` `#include` 进测试单元，
因此 `pipeline_step_stage1/2/3`、`submit_bd_transfer`、`reclaim_some_bd`、
`parse_header`、`poll_callback` 这些 `static` 函数可以被直接调用、
`pipe_state` 这类文件级静态量可以被直接读。
抄一份逻辑到测试里再测，测的是抄件，对 `echo.c` 的回归零鉴别力。

固件源码一个字节都没有改。三件事让它能在 x86 上跑起来：

| 障碍 | 办法 |
| --- | --- |
| `memcpy((void *)0x10000000, …)` 这类**绝对地址** | `mmap(MAP_FIXED_NOREPLACE)` 把 `0x10000000..0x12000000` 映进进程，地址原样可用 |
| `__asm__ volatile("dsb sy")` 在 x86 汇编不过 | `#define __asm__`（对象宏）+ `#define volatile(x)`（**函数式**宏，只在 `volatile(` 时展开，限定符 `volatile u8 *` 原样保留）。⚠️ 必须**先**包含所有系统头再定义，否则会把 glibc 自己的 `__asm__("…")` 符号重命名一起抹掉 |
| Xilinx / lwIP 头文件 | `sim/host/shim/` 下的壳层，只提供 `echo.c` 真正用到的接口 |

基地址来自仓库里那份**真实的** `sw/app/xparameters.h`（壳层只补了空的 `xparameters_ps.h`）。

## 两类判据

**1. 纯逻辑单元测试**（`test_echo_pure.c`，约 50 条）
`parse_header` 的大端长度与 magic 边界、`align_down`、`board_caps` 对
`report/design-report-2026.pdf` 的接口说明、`process_batch` 的四类边界、`process_config`
的连接层拒绝码 8/9、`process_post` 的布局校验、
`expand_watermark_regions` 对 `sim/golden/wm_regions.hex` 的 **47,850 个符号逐个比对**、
`apply_watermark_differential` 的范围与幂等、`validate_decoder_written_beats` 的哨兵计数、
以及 `run_processing_pipeline` 的状态分派。

**2. 行为轨迹判据**（`test_echo_trace.c`）——**这是拆分的「行为等价」判据**
驱动真实固件走完 `accept → CONFIG → WM → BATCH×2 → POST → 100+ 次 poll → 回传 8,100 B`，
把每一个**对外可见的效应**按发生顺序记成一行：

```
REGW dna+0x04 = 0x00000000     AXI-Lite 写（含值）
SLEEP 10us                     usleep —— 「写 0 → 写 1 → usleep → 写 0」里的那一段
REGW dna+0x00 = 0x00000002     置 preload
CACHE FLUSH 0x11800000 +64     缓存维护的地址与长度
DMA TOHW tx n=1                BD 投递 / 回收
TCP WRITE 1460                 回传字节数与顺序
NETIF INPUT                    keep_tcp_alive 的位置
```

黄金文件 `golden/echo_trace_se150_128reads.txt`（812 行），出处记在同名 `.meta`。
**拆分前后这份轨迹必须逐行相同。** 固件日志文本**刻意不在轨迹里**：
拆分时措辞可以改，行为不可以。

## 判据的鉴别力（`--selftest`）

一条不会失败的判据，通过了也没有信息量（`readme.md` §5）。
`sim/host/inject.py` 对 `echo.c` 的**临时副本**做四种「拆分时顺手整理掉」的改动，
每一种都必须让轨迹判据变红（注入点找不到会直接报错，不会悄悄变成空操作）：

| 注入 | 复刻的错误 | 实测 |
| --- | --- | --- |
| `b27-start-clear` | Decoder START=1 之后再写一次 0 —— **B27 本尊** | 第 798 行变红 |
| `dec-beats-order` | `OUT_BEATS`/`IN_BEATS` 写入顺序对调 | 第 784 行变红 |
| `voter-prestart-zero` | 删掉 Voter START 脉冲前那次「先写 0」 | 第 745 行变红 |
| `drop-stage2-invalidate` | 删掉 Stage2 输入区的分块 invalidate | 第 725 行变红 |

轨迹测试内部还带一段自证：把 Decoder 的 RTL 语义换回 B27 之前那版
（对 START 写任何值都启动），固件 `PIPE_DECODER_PREP` 里那句
`write START=0x00` **本身**就会把核启动，`Status before config` 读回非 IDLE，
流水线当场失败 —— B27 在主机上被复现，用时不到一秒。

## 建模边界（别当成真硬件）

- 三个 IP 核和 AXI DMA 都是**行为模型**，不是 RTL，更不是板子。
  **端到端唯一判据仍然是 `src/tools/run_g3.sh` 的图片 SHA-256。**
  本套判据能证明的只有一件事：**拆分前后 PS 侧的对外行为逐条相同。**
- `sizeof(XAxiDma_Bd)` 取 64 B（与 `echo.h` 的 `BD_SPACE_SIZE_*` / `BD_ALIGNMENT`
  一致），真实 Xilinx 驱动是 20 words = 80 B。
- BD 环按 Xilinx 的指针纪律建模（free → pre → hw → post → free），
  **如实回绕** —— B21 第 3 条「线性索引 `&BdPtr[i]` 读到环外」在这里是可判定的。
- DNA 核结果 FIFO 满会停 MM2S（B21 的锁死机理）；`usleep` 会推进数据通路，
  因为板上 usleep 期间 DMA 真的在跑（固件在一个 poll 里忙等 BD 完成时要靠这条）。
- 三个 IP 核的忙碌时长按 poll 计（`host_hw_cfg`），不是真实时序。

## 目录

| 文件 | 作用 |
| --- | --- |
| `run_host_tests.sh` | 唯一入口 |
| `test_echo_pure.c` | 纯逻辑单元测试 |
| `test_echo_trace.c` | 行为轨迹判据 + B27 语义自证 |
| `inject.py` | 故障注入（改临时副本，不碰仓库里的 `echo.c`） |
| `shim/echo_under_test.h` | 把真实 `echo.c` 拉进测试单元的那层（含两个宏的顺序要求） |
| `shim/hostenv.{h,c}` | 假 DDR + 设备模型 + 轨迹录制 + lwIP 模型 |
| `shim/*.h` | Xilinx / lwIP 头文件壳层 |
| `golden/` | 行为轨迹黄金文件与出处 |
