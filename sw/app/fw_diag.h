#ifndef FW_DIAG_H
#define FW_DIAG_H

#include "xil_printf.h"

/*
 * FW_DIAG_LEVEL: 2=啰嗦，1=分级静默（只留错误/告警与流水线完成标记），
 *                0=全静默（兼容原 FW_DIAG_VERBOSE=0 行为）。
 * 旧构建参数 FW_DIAG_VERBOSE 仍被识别：为 0 时映射到 0；否则按 FW_DIAG_LEVEL 走。
 *
 * **默认取 1（分级静默），这是一次有意的默认变更**，理由三条：
 *   1) 2026-10-15 板端**交替 A/B**（V G V G V G 六次实跑，PL bit 与 FSBL 逐字节相同、
 *      只差一个宏）实测：啰嗦 **5,515 ms**、分级 **5,148 ms**，三轮配对差值全为
 *      **−367 ms（−6.66%）**，且两种配置各自三次跑**逐毫秒相同**。
 *      机制：全量档串口共 9,262 字节、线速约 804 ms，而 `xil_printf` 在单线程主循环里
 *      **忙等 TX FIFO**，主循环一次只推进一步流水线 —— 打印直接吃掉流水线时间
 *      （实测掉的是"节流之外"那段：687 → 301 ms，节流底几乎没动）。
 *   2) **保留错误与告警是免费的**：同一 A/B 里分级档的串口输出只有 **275 字节**，
 *      与全静默档**完全相同** —— 成功路径上根本不打印 `[ERROR]`/`[WARNING]`。
 *      ⇒ 分级档拿到那 367 ms 的 100%，而**排障能力零损失**。
 *      （这也说明"全静默"没有意义：它和分级档一样快，却把错误信息白白扔掉。）
 *   3) **默认值 = 出厂值**：正式构建路径 `sw/scripts/create_vitis.tcl` 走 `app build`，
 *      **没有注入 `-D` 的口子**（同 `main.c` 里 `PIPE_IDLE_FETCH_N` 那段论证）。
 *      若默认取 2，正式流程编出来的包会**悄悄退回慢配置**，本次优化的转正就落空。
 * 取 `-DFW_DIAG_LEVEL=2` 可退回旧的全量日志，排障复现时用。
 */
#ifndef FW_DIAG_LEVEL
# if defined(FW_DIAG_VERBOSE) && !(FW_DIAG_VERBOSE)
#  define FW_DIAG_LEVEL 0
# else
#  define FW_DIAG_LEVEL 1
# endif
#endif

#ifndef FW_DIAG_VERBOSE
# define FW_DIAG_VERBOSE (FW_DIAG_LEVEL >= 2)
#endif

#if FW_DIAG_LEVEL < 0 || FW_DIAG_LEVEL > 2
# error "FW_DIAG_LEVEL must be 0 (quiet), 1 (graded), or 2 (verbose)"
#endif

/* 流水线完成测量行在三档都保留，作为成功路径完成标记。 */
#define FW_RESULT_PRINTF(...) (xil_printf)(__VA_ARGS__)

/* 错误/告警在分级静默与啰嗦档保留；全静默档兼容旧行为并抑制它们。 */
#if FW_DIAG_LEVEL >= 1
# define FW_ERR_PRINTF(...) (xil_printf)(__VA_ARGS__)
#else
# define FW_ERR_PRINTF(...) do { if (0) (xil_printf)(__VA_ARGS__); } while (0)
#endif

#if FW_DIAG_LEVEL >= 2
#define FW_DIAG_EMIT(...) (xil_printf)(__VA_ARGS__)
#else
/* 仍在不可达语句中做格式与参数类型检查，但静默档运行时不求值参数。 */
#define FW_DIAG_EMIT(...) do { if (0) (xil_printf)(__VA_ARGS__); } while (0)
#endif

#define xil_printf(...) FW_DIAG_EMIT(__VA_ARGS__)

#endif /* FW_DIAG_H */
