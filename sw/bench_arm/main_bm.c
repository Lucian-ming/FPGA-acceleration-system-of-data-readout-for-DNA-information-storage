/******************************************************************************
 * main_bm.c — 同片 ARM 基线的裸机入口（Cortex-A9 #0，standalone BSP）
 *
 * 数据由 XSDB 在 con 之前写进 DDR（tools/board/arm_baseline.py 渲染的脚本）：
 *   AB_HDR_ADDR   : ab_hdr_t（magic、条数）
 *   AB_REF_ADDR   : AA_L 字节水印符号
 *   AB_READS_ADDR : n × AA_RB 字节读段符号
 * 结果写到 AB_RES_ADDR（每条 aa_result_t），摘要写到 AB_SUM_ADDR；
 * 写完 D-cache flush，再置 done 标志——XSDB 经 DAP 读的是 DDR，不是 cache。
 * 生产固件（sw/app）不含本文件，互不影响。
 ******************************************************************************/
#include <stdint.h>
#include "xil_printf.h"
#include "xil_cache.h"
#include "xtime_l.h"
#include "arm_align.h"

#define AB_HDR_ADDR    0x08000000u
#define AB_REF_ADDR    0x08001000u
#define AB_READS_ADDR  0x08010000u
#define AB_RES_ADDR    0x09000000u
#define AB_SUM_ADDR    0x09F00000u
#define AB_MAGIC_IN    0xAB5E0001u
#define AB_MAGIC_DONE  0xAB5E00D0u
#define AB_MAGIC_BAD   0xAB5E0BADu

typedef struct { uint32_t magic, n_reads, reserved[2]; } ab_hdr_t;
typedef struct {
    uint32_t magic, n_reads;
    uint32_t ticks_lo, ticks_hi;          /* 比对总耗时（XTime 计数） */
    uint32_t counts_per_second;
    uint32_t prep_ticks;                  /* 水印位平面准备耗时 */
    uint32_t rb, reserved;
} ab_sum_t;

int main(void)
{
    volatile ab_hdr_t *hdr = (volatile ab_hdr_t *)AB_HDR_ADDR;
    volatile ab_sum_t *sum = (volatile ab_sum_t *)AB_SUM_ADDR;
    const uint8_t *ref   = (const uint8_t *)AB_REF_ADDR;
    const uint8_t *reads = (const uint8_t *)AB_READS_ADDR;
    aa_result_t *res     = (aa_result_t *)AB_RES_ADDR;

    sum->magic = 0;
    if (hdr->magic != AB_MAGIC_IN || hdr->n_reads == 0u || hdr->n_reads > 60000u) {
        xil_printf("[ARMBL] bad header magic=0x%08X n=%u\r\n", hdr->magic, hdr->n_reads);
        sum->magic = AB_MAGIC_BAD;
        Xil_DCacheFlush();
        return 1;
    }
    const uint32_t n = hdr->n_reads;
    xil_printf("[ARMBL] start: %u reads, RB=%u, L=%u\r\n", n, (unsigned)AA_RB, (unsigned)AA_L);

    XTime t0, t1, t2;
    XTime_GetTime(&t0);
    aa_prepare_ref(ref);
    XTime_GetTime(&t1);
    for (uint32_t i = 0; i < n; i++) {
        aa_align_read(reads + (uint32_t)i * AA_RB, &res[i]);
    }
    XTime_GetTime(&t2);

    const uint64_t dt = (uint64_t)(t2 - t1);
    sum->n_reads = n;
    sum->ticks_lo = (uint32_t)dt;
    sum->ticks_hi = (uint32_t)(dt >> 32);
    sum->counts_per_second = (uint32_t)COUNTS_PER_SECOND;
    sum->prep_ticks = (uint32_t)(t1 - t0);
    sum->rb = AA_RB;
    Xil_DCacheFlush();
    sum->magic = AB_MAGIC_DONE;
    Xil_DCacheFlush();

    const uint32_t ms = (uint32_t)(dt * 1000u / COUNTS_PER_SECOND);
    xil_printf("[ARMBL] done: %u reads in %u ms (%u us/read, both orientations)\r\n",
               n, ms, (uint32_t)(dt * 1000000u / COUNTS_PER_SECOND / n));
    for (;;) { }
}
