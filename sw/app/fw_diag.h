#ifndef FW_DIAG_H
#define FW_DIAG_H

#include "xil_printf.h"

/*
 * 出厂默认保留现有串口诊断。正式制品流程没有给 app build 注入 -D 的入口，
 * 因此默认必须维持当前行为；A/B 变体显式传入 -DFW_DIAG_VERBOSE=0。
 */
#ifndef FW_DIAG_VERBOSE
#define FW_DIAG_VERBOSE 1
#endif

/* 显式保留端到端测量行；其它 xil_printf 调用由下方宏统一裁剪。 */
#define FW_RESULT_PRINTF(...) (xil_printf)(__VA_ARGS__)

#if FW_DIAG_VERBOSE
#define FW_DIAG_EMIT(...) (xil_printf)(__VA_ARGS__)
#else
/* 仍在不可达语句中做格式与参数类型检查，但安静模式运行时不求值参数。 */
#define FW_DIAG_EMIT(...) do { if (0) (xil_printf)(__VA_ARGS__); } while (0)
#endif

#define xil_printf(...) FW_DIAG_EMIT(__VA_ARGS__)

#endif /* FW_DIAG_H */
