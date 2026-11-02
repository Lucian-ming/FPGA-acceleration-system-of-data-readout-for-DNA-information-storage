#ifndef DNA_TIME_H
#define DNA_TIME_H

/* Preserve the monotonic 64-bit Zynq global timer and seconds-to-ticks
 * conversion across legacy standalone and the SDT xiltimer BSP. */
#ifdef SDT
#include "xiltimer.h"
#if !defined(XTIMER_IS_DEFAULT_TIMER) || defined(XSLEEPTIMER_IS_SCUTIMER) || defined(XSLEEPTIMER_IS_TTCPS) || defined(XSLEEPTIMER_IS_AXITIMER)
#error "DNA firmware requires the Zynq global timer, not a wrapping peripheral sleep counter"
#endif
#else
#include "xtime_l.h"
#endif

#define DNA_TIMEOUT_TICKS(seconds) ((XTime)(COUNTS_PER_SECOND) * (XTime)(seconds))

#endif
