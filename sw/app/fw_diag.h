#ifndef FW_DIAG_H
#define FW_DIAG_H

#include "xil_printf.h"

/*
 * 正式制品流程的 app build 没有注入 -D 的入口，因此默认保持原有完整诊断。
 * FW_DIAG_LEVEL: 2=啰嗦，1=分级静默（只留错误/告警与流水线完成标记），
 *                0=全静默（兼容原 FW_DIAG_VERBOSE=0 行为）。
 * 旧构建参数 FW_DIAG_VERBOSE=0 映射到全静默；未定义或为 1 时仍是默认啰嗦。
 */
#ifndef FW_DIAG_LEVEL
# if defined(FW_DIAG_VERBOSE) && !(FW_DIAG_VERBOSE)
#  define FW_DIAG_LEVEL 0
# else
#  define FW_DIAG_LEVEL 2
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
