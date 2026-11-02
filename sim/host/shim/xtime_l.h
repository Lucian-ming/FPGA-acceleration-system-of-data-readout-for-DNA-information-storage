#ifndef __XTIME_L_H__
#define __XTIME_L_H__
/* 主机侧壳层：Zynq 的全局定时器。
 * 固件用它做**直接测量**（比如水印预载耗时），主机上给一个由「硬件 tick 次数」
 * 推出来的确定值 —— 必须确定，否则行为轨迹不可复现。
 * 注意：轨迹里不记录时间值，时间只影响固件自己打的日志。 */
#include "xil_types.h"

typedef u64 XTime;
#define COUNTS_PER_SECOND  (333333343U / 2U)   /* PS7 全局定时器 = CPU_CLK/2/... */

void XTime_GetTime(XTime *t);

#endif
