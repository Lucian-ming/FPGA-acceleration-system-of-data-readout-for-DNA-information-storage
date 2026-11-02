#ifndef __XIL_PRINTF_H__
#define __XIL_PRINTF_H__
/* 主机侧壳层：固件日志。默认吞掉（HOSTENV_VERBOSE=1 时打到 stderr）。
 * 日志文本**刻意不进轨迹判据**：拆分时允许调整日志措辞，不允许改行为。 */
void xil_printf(const char *fmt, ...);
#define print(s) xil_printf("%s", (s))
#endif
