/******************************************************************************
 * dma_dna.h — PS 固件 DNA 加速器 DMA 接口封装
 *
 * 封装 dna_accelerator_init、dna_submit_rx_records、dna_submit_reads_chunk、
 * 以及 dna_wait_wm_region_bd。
 ******************************************************************************/
#ifndef __DMA_DNA_H__
#define __DMA_DNA_H__

#include "xil_types.h"
#include "bd_ring.h"
#include "fw_log.h"

#ifdef __cplusplus
extern "C" {
#endif

#define RX_OUTSTANDING_MAX     512U    /* ring 有 1024 个 BD，最多留一半在飞 */
#define WM_BD_WAIT_US          5000U   /* 单区域 BD 回收忙等上限（正常 ~10 us） */
#define WM_BD_WAIT_STEP_US     5U      /* 忙等的轮询步长 */

/* DNA DMA RX 记录滚动补投状态 */
typedef struct {
    u32 records_total;
    u32 records_submitted;
    int rx_done;
} dna_rx_state_t;

/* DNA DMA TX 读段小批提交状态 */
typedef struct {
    u32 frames_total;
    u32 frames_sent;
    u32 frames_done;
    int tx_done;
    int tx_expected;
} dna_tx_state_t;

/* 初始化 DNA 相关的 AXI DMA */
int dna_accelerator_init(void);

/* 【B21】按「一条记录一个 BD」滚动补投 RX 描述符。
 * 返回本次投出的 BD 数（0 表示暂时不需要补），-1 表示失败。 */
int dna_submit_rx_records(dna_rx_state_t *st);

/* 小批提交 READS */
int dna_submit_reads_chunk(dna_tx_state_t *st);

/* 【WM 批量化】单个水印区域的 BD 有界忙等 */
int dna_wait_wm_region_bd(u32 region, int expected);

/* 便捷函数：打印 DMA 寄存器 */
static inline void dump_dma_regs(const char *tag)
{
    fw_dump_dma(&AxiDma, tag);
}

#ifdef __cplusplus
}
#endif

#endif /* __DMA_DNA_H__ */
