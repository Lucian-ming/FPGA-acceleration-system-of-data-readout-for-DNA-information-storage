#ifndef __ECHO_UNDER_TEST_H__
#define __ECHO_UNDER_TEST_H__
/******************************************************************************
 * echo_under_test.h — 把**未经修改的** sw/app/echo.c 整个拉进测试单元
 *
 * 为什么是 #include "echo.c" 而不是链接：echo.c 里绝大多数被测逻辑是 static
 * （pipeline_step_stage1/2/3、submit_bd_transfer、reclaim_some_bd、parse_header、
 * poll_callback …）。整份包含进来，测试才能直接调用它们、直接读 pipe_state
 * 这类文件级静态量。判据因此建立在**真实固件源码**上，而不是它的一份抄写 ——
 * 抄一份来测，测的是抄件，对 echo.c 的回归零鉴别力。
 *
 * 两个宏是让 ARM 内存屏障在 x86 上编过去的**唯一**手段，且不需要动 echo.c：
 *   - `#define __asm__`            —— 对象宏，把 `__asm__` 抹掉；
 *   - `#define volatile(x)`        —— **函数式**宏，只在 `volatile(` 时展开，
 *     所以 `__asm__ volatile("dsb sy");` 整条变成 `;`，
 *     而 `volatile u8 *p` / `(const volatile u64 *)` 这些限定符原样保留。
 *
 * ⚠️ 顺序要求：必须**先**包含所有系统头，再定义这两个宏。glibc 头文件自己会用
 *    `__asm__("...")` 做符号重命名，先定义宏会把它们一起抹掉，症状是一堆莫名
 *    其妙的链接错误。下面已经按这个顺序排好，往里加系统头请加在宏之前。
 ******************************************************************************/

/* ---- 1) 系统头先来 ---- */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <stdint.h>
#include <stdarg.h>
#include <unistd.h>
#include <errno.h>

/* ---- 2) 主机侧环境 ---- */
#include "hostenv.h"

/* ---- 3) 抹掉 ARM 内存屏障（见上文） ---- */
#define __asm__
#define volatile(x)

/* ---- 4) 真实固件 ---- */
#if __has_include("fw_log.c")
#include "fw_log.c"
#endif
#if __has_include("reg_timing.c")
#include "reg_timing.c"
#endif
#if __has_include("bd_ring.c")
#include "bd_ring.c"
#endif
#if __has_include("dma_dna.c")
#include "dma_dna.c"
#endif
#if __has_include("proto.c")
#include "proto.c"
#endif
#if __has_include("pipeline.c")
#include "pipeline.c"
#endif
#if __has_include("stage2_voter.c")
#include "stage2_voter.c"
#endif
#if __has_include("stage3_decoder.c")
#include "stage3_decoder.c"
#endif
#include "echo.c"

#endif /* __ECHO_UNDER_TEST_H__ */
