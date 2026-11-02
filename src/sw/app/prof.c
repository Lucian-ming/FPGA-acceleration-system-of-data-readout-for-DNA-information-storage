#include "prof.h"

#ifdef PROF_ENABLE
#include <string.h>
#include "xil_printf.h"
#include "fw_diag.h"

prof_stats_t g_prof;

void prof_reset(void)
{
    memset(&g_prof, 0, sizeof g_prof);
}

static void prof_print_ms(u64 ticks)
{
    const u64 ticks_per_ms = (u64)(COUNTS_PER_SECOND / 1000U);
    const u64 whole_ms = ticks / ticks_per_ms;
    const u32 fraction = (u32)(((ticks % ticks_per_ms) * 1000U) / ticks_per_ms);
    xil_printf("%u.%03u", (u32)whole_ms, fraction);
}

void prof_dump_once(void)
{
    if (g_prof.dumped) return;
    g_prof.dumped = 1U;

    xil_printf("[PROF] submit: calls=%u bds=%u ms=", g_prof.sub_calls, g_prof.sub_bds);
    prof_print_ms(g_prof.sub_ticks);
    xil_printf(" (sampled 1/256)\n\r");

    xil_printf("[PROF] reclaim: calls=%u bds=%u ms=", g_prof.rec_calls, g_prof.rec_bds);
    prof_print_ms(g_prof.rec_ticks);
    xil_printf(" (sampled 1/256)\n\r");

    xil_printf("[PROF] cache_flush: calls=%u bytes=%u ms=",
               g_prof.flush_calls, g_prof.flush_bytes);
    prof_print_ms(g_prof.flush_ticks);
    xil_printf(" (BD flush sampled 1/256; other calls exact)\n\r");

    xil_printf("[PROF] cache_inval: calls=%u bytes=%u ms=",
               g_prof.inv_calls, g_prof.inv_bytes);
    prof_print_ms(g_prof.inv_ticks);
    xil_printf(" (Stage3 poll sampled 1/256; other calls exact)\n\r");

    xil_printf("[PROF] tstream: enter=%u lowwater=%u usleeps=%u helper_ms=",
               g_prof.tstream_enter, g_prof.tstream_lowwater_enter,
               g_prof.tstream_lowwater_usleeps);
    prof_print_ms(g_prof.tstream_helper_ticks);
    xil_printf(" lowwater_ms=");
    prof_print_ms(g_prof.tstream_lowwater_ticks);
    xil_printf(" (helper sampled 1/256)\n\r");

    xil_printf("[PROF] netif_input: calls=%u ms=", g_prof.netin_calls);
    prof_print_ms(g_prof.netin_ticks);
    xil_printf(" (sampled 1/256)\n\r");

    xil_printf("[PROF] send_result: bytes=%u ms=", g_prof.sendres_bytes);
    prof_print_ms(g_prof.sendres_ticks);
    xil_printf("\n\r");

    xil_printf("[PROF] wm_expand_ms=");
    prof_print_ms(g_prof.wmx_ticks);
    xil_printf(" wm_preload_ms=");
    prof_print_ms(g_prof.wmpre_ticks);
    xil_printf(" serialize_ms=");
    prof_print_ms(g_prof.serialize_ticks);
    xil_printf("\n\r");
}
#endif
