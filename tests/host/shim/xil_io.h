#ifndef __XIL_IO_H__
#define __XIL_IO_H__
/* 主机侧壳层：AXI-Lite 寄存器读写。
 * 所有写/读都交给 hostenv 的设备模型，并逐条记进轨迹 ——
 * 「寄存器写序列本身就是被测对象」(AGENTS.md 常见陷阱 / B27)。 */
#include "xil_types.h"

void Xil_Out32(UINTPTR addr, u32 value);
u32  Xil_In32(UINTPTR addr);
void Xil_Out8(UINTPTR addr, u8 value);
u8   Xil_In8(UINTPTR addr);

#endif
