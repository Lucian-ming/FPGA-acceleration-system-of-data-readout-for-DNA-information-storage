#ifndef DNA_PROF_H
#define DNA_PROF_H

/*
 * 裸机固件性能累计器。
 * 以 -DPROF_ENABLE=1 启用；未启用时宏直接展开为空或原始缓存调用。
 * 高频路径每 256 次调用抽一个函数样本，样本入口/出口各读一次 XTime_GetTime，
 * 再把样本 ticks 乘 256 估算总 ticks；纯 calls/BDs/bytes 计数仍逐次精确累计。
 */
#include "xil_types.h"
#include "dna_time.h"

#ifdef PROF_ENABLE
#include "xil_cache.h"

typedef struct {
    u32 sub_calls;
    u32 sub_bds;
    u64 sub_ticks;
    u32 rec_calls;
    u32 rec_bds;
    u64 rec_ticks;
    u32 flush_calls;
    u32 flush_bytes;
    u64 flush_ticks;
    u32 inv_calls;
    u32 inv_bytes;
    u64 inv_ticks;
    u32 tstream_enter;
    u32 tstream_lowwater_enter;
    u32 tstream_lowwater_usleeps;
    u32 helper_rx_reclaim_calls;
    u32 helper_rx_submit_calls;
    u32 helper_low_reclaim_calls;
    u32 helper_read_submit_calls;
    u32 helper_tx_reclaim_calls;
    u64 tstream_lowwater_ticks;
    u64 tstream_helper_ticks;
    u32 netin_calls;
    u64 netin_ticks;
    u32 sendres_bytes;
    u64 sendres_ticks;
    u64 wmx_ticks;
    u64 wmpre_ticks;
    u64 serialize_ticks;
    u32 dumped;
} prof_stats_t;

extern prof_stats_t g_prof;
void prof_reset(void);
void prof_dump_once(void);

/* 单次调用计时：适用于每个任务只调用少数几次的阶段函数。 */
#define PROF_TIME_BEGIN(tag) \
    XTime prof_time_start_##tag; \
    XTime_GetTime(&prof_time_start_##tag)
#define PROF_TIME_END(tag, field) do { \
    XTime _prof_time_end; \
    XTime_GetTime(&_prof_time_end); \
    g_prof.field += (u64)(_prof_time_end - prof_time_start_##tag); \
} while (0)
#define PROF_ADD_TICKS(field, ticks) do { g_prof.field += (u64)(ticks); } while (0)

/* submit/reclaim：精确累计调用数与 BD 数，ticks 每 256 次调用抽样一次。 */
#define PROF_SUBMIT_BEGIN(tag) \
    XTime prof_submit_start_##tag = 0; \
    u32 prof_submit_sampled_##tag = 0; \
    g_prof.sub_calls++; \
    if ((g_prof.sub_calls & 255U) == 0U) { \
        prof_submit_sampled_##tag = 1U; \
        XTime_GetTime(&prof_submit_start_##tag); \
    }
#define PROF_SUBMIT_END(tag, bds) do { \
    g_prof.sub_bds += (u32)(bds); \
    if (prof_submit_sampled_##tag) { \
        XTime _prof_submit_end; \
        XTime_GetTime(&_prof_submit_end); \
        g_prof.sub_ticks += (u64)(_prof_submit_end - prof_submit_start_##tag) * 256U; \
    } \
} while (0)

#define PROF_RECLAIM_BEGIN(tag) \
    XTime prof_reclaim_start_##tag = 0; \
    u32 prof_reclaim_sampled_##tag = 0; \
    g_prof.rec_calls++; \
    if ((g_prof.rec_calls & 255U) == 0U) { \
        prof_reclaim_sampled_##tag = 1U; \
        XTime_GetTime(&prof_reclaim_start_##tag); \
    }
#define PROF_RECLAIM_END(tag, bds) do { \
    g_prof.rec_bds += (u32)(bds); \
    if (prof_reclaim_sampled_##tag) { \
        XTime _prof_reclaim_end; \
        XTime_GetTime(&_prof_reclaim_end); \
        g_prof.rec_ticks += (u64)(_prof_reclaim_end - prof_reclaim_start_##tag) * 256U; \
    } \
} while (0)

/* BD 描述符 flush 高频：计数/字节精确，ticks 每 256 次抽样并折算。 */
#define PROF_CACHE_FLUSH_SAMPLED(addr, len) do { \
    const UINTPTR _prof_addr = (UINTPTR)(addr); \
    const u32 _prof_len = (u32)(len); \
    XTime _prof_start = 0; \
    u32 _prof_sampled; \
    g_prof.flush_calls++; \
    g_prof.flush_bytes += _prof_len; \
    _prof_sampled = ((g_prof.flush_calls & 255U) == 0U); \
    if (_prof_sampled) XTime_GetTime(&_prof_start); \
    Xil_DCacheFlushRange(_prof_addr, _prof_len); \
    if (_prof_sampled) { \
        XTime _prof_end; \
        XTime_GetTime(&_prof_end); \
        g_prof.flush_ticks += (u64)(_prof_end - _prof_start) * 256U; \
    } \
} while (0)

/* 低频缓存范围操作精确计时；调用数和字节数也逐次精确累计。 */
#define PROF_CACHE_FLUSH(addr, len) do { \
    const UINTPTR _prof_addr = (UINTPTR)(addr); \
    const u32 _prof_len = (u32)(len); \
    XTime _prof_start, _prof_end; \
    XTime_GetTime(&_prof_start); \
    Xil_DCacheFlushRange(_prof_addr, _prof_len); \
    XTime_GetTime(&_prof_end); \
    g_prof.flush_calls++; \
    g_prof.flush_bytes += _prof_len; \
    g_prof.flush_ticks += (u64)(_prof_end - _prof_start); \
} while (0)

#define PROF_CACHE_INVALIDATE_SAMPLED(addr, len) do { \
    const UINTPTR _prof_addr = (UINTPTR)(addr); \
    const u32 _prof_len = (u32)(len); \
    XTime _prof_start = 0; \
    u32 _prof_sampled; \
    g_prof.inv_calls++; \
    g_prof.inv_bytes += _prof_len; \
    _prof_sampled = ((g_prof.inv_calls & 255U) == 0U); \
    if (_prof_sampled) XTime_GetTime(&_prof_start); \
    Xil_DCacheInvalidateRange(_prof_addr, _prof_len); \
    if (_prof_sampled) { \
        XTime _prof_end; \
        XTime_GetTime(&_prof_end); \
        g_prof.inv_ticks += (u64)(_prof_end - _prof_start) * 256U; \
    } \
} while (0)

#define PROF_CACHE_INVALIDATE(addr, len) do { \
    const UINTPTR _prof_addr = (UINTPTR)(addr); \
    const u32 _prof_len = (u32)(len); \
    XTime _prof_start, _prof_end; \
    XTime_GetTime(&_prof_start); \
    Xil_DCacheInvalidateRange(_prof_addr, _prof_len); \
    XTime_GetTime(&_prof_end); \
    g_prof.inv_calls++; \
    g_prof.inv_bytes += _prof_len; \
    g_prof.inv_ticks += (u64)(_prof_end - _prof_start); \
} while (0)

/* STREAM 各类子函数分别计数后各按 1/256 抽样，避免固定调用序列造成偏采样；
 * 高频 xemacif_input 也按 1/256 ticks 抽样。 */
#define PROF_HELPER_BEGIN(tag, call_field) \
    XTime prof_helper_start_##tag = 0; \
    u32 prof_helper_sampled_##tag = 0; \
    g_prof.call_field++; \
    if ((g_prof.call_field & 255U) == 0U) { \
        prof_helper_sampled_##tag = 1U; \
        XTime_GetTime(&prof_helper_start_##tag); \
    }
#define PROF_HELPER_END(tag) do { \
    if (prof_helper_sampled_##tag) { \
        XTime _prof_helper_end; \
        XTime_GetTime(&_prof_helper_end); \
        g_prof.tstream_helper_ticks += \
            (u64)(_prof_helper_end - prof_helper_start_##tag) * 256U; \
    } \
} while (0)

#define PROF_NETIN_BEGIN(tag) \
    XTime prof_netin_start_##tag = 0; \
    u32 prof_netin_sampled_##tag = 0; \
    g_prof.netin_calls++; \
    if ((g_prof.netin_calls & 255U) == 0U) { \
        prof_netin_sampled_##tag = 1U; \
        XTime_GetTime(&prof_netin_start_##tag); \
    }
#define PROF_NETIN_END(tag) do { \
    if (prof_netin_sampled_##tag) { \
        XTime _prof_netin_end; \
        XTime_GetTime(&_prof_netin_end); \
        g_prof.netin_ticks += (u64)(_prof_netin_end - prof_netin_start_##tag) * 256U; \
    } \
} while (0)

#define PROF_TSTREAM_ENTER() do { g_prof.tstream_enter++; } while (0)
#define PROF_TSTREAM_LOW_BEGIN(tag) \
    g_prof.tstream_lowwater_enter++; \
    PROF_TIME_BEGIN(tag)
#define PROF_TSTREAM_USLEEP() do { g_prof.tstream_lowwater_usleeps++; } while (0)

#define PROF_SEND_RESULT_END(tag, bytes) do { \
    XTime _prof_sendres_end; \
    XTime_GetTime(&_prof_sendres_end); \
    g_prof.sendres_ticks += (u64)(_prof_sendres_end - prof_time_start_##tag); \
    g_prof.sendres_bytes += (u32)(bytes); \
} while (0)

#else /* PROF_ENABLE */

static inline void prof_reset(void) { }
static inline void prof_dump_once(void) { }

#define PROF_TIME_BEGIN(tag) do { } while (0)
#define PROF_TIME_END(tag, field) do { } while (0)
#define PROF_ADD_TICKS(field, ticks) do { } while (0)
#define PROF_SUBMIT_BEGIN(tag) do { } while (0)
#define PROF_SUBMIT_END(tag, bds) do { } while (0)
#define PROF_RECLAIM_BEGIN(tag) do { } while (0)
#define PROF_RECLAIM_END(tag, bds) do { } while (0)
#define PROF_CACHE_FLUSH_SAMPLED(addr, len) Xil_DCacheFlushRange((addr), (len))
#define PROF_CACHE_FLUSH(addr, len) Xil_DCacheFlushRange((addr), (len))
#define PROF_CACHE_INVALIDATE_SAMPLED(addr, len) Xil_DCacheInvalidateRange((addr), (len))
#define PROF_CACHE_INVALIDATE(addr, len) Xil_DCacheInvalidateRange((addr), (len))
#define PROF_HELPER_BEGIN(tag, call_field) do { } while (0)
#define PROF_HELPER_END(tag) do { } while (0)
#define PROF_NETIN_BEGIN(tag) do { } while (0)
#define PROF_NETIN_END(tag) do { } while (0)
#define PROF_TSTREAM_ENTER() do { } while (0)
#define PROF_TSTREAM_LOW_BEGIN(tag) do { } while (0)
#define PROF_TSTREAM_USLEEP() do { } while (0)
#define PROF_SEND_RESULT_END(tag, bytes) do { } while (0)

#endif /* PROF_ENABLE */

#endif /* DNA_PROF_H */
