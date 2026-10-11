#ifndef __XIL_CACHE_H__
#define __XIL_CACHE_H__
/* 主机侧壳层：缓存维护。
 * invalidate / flush 的**位置与范围是正确性的一部分**（tests/host/README.md的cache行为轨迹），
 * 不是样板代码，所以每一次调用（地址 + 长度）都进轨迹。 */
#include "xil_types.h"

void Xil_DCacheFlushRange(UINTPTR adr, u32 len);
void Xil_DCacheInvalidateRange(UINTPTR adr, u32 len);
void Xil_DCacheFlush(void);
void Xil_DCacheInvalidate(void);

#endif
