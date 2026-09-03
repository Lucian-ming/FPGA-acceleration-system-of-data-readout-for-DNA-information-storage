#ifndef __XIL_TYPES_H__
#define __XIL_TYPES_H__
/* 主机侧壳层：只提供 sw/app/echo.c 真正用到的 Xilinx 基础类型。
 * 目的是让**未经修改的** sw/app/echo.c 能在 x86 主机上编译运行。 */
#include <stdint.h>
#include <stddef.h>

typedef uint8_t  u8;
typedef uint16_t u16;
typedef uint32_t u32;
typedef uint64_t u64;
typedef int8_t   s8;
typedef int16_t  s16;
typedef int32_t  s32;
typedef int64_t  s64;
typedef uintptr_t UINTPTR;
typedef uint32_t  INTPTR32;

#ifndef TRUE
#define TRUE  1
#endif
#ifndef FALSE
#define FALSE 0
#endif
#ifndef NULL
#define NULL ((void *)0)
#endif

#define XST_SUCCESS   0L
#define XST_FAILURE   1L

#endif /* __XIL_TYPES_H__ */
