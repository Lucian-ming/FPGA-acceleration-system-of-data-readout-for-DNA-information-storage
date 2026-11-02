/******************************************************************************
 * bd_ring.h — PS 固件 AXI DMA 描述符环管理
 *
 * 封装 setup_bd_ring、submit_bd_transfer、reclaim_some_bd 等 BD 环核心操作。
 * 严格保持逐个 BD 64B flush 与沿 BdRingNext 遍历，正面回应 B21。
 ******************************************************************************/
#ifndef __BD_RING_H__
#define __BD_RING_H__

#include "xil_types.h"
#include "xaxidma.h"
#include "echo.h"

#ifdef __cplusplus
extern "C" {
#endif

#define MAX_BD_COUNT            512

/* 传输类型:决定每BD策略 */
typedef enum {
    XFER_TX_READS = 0,  /* MM2S:送 reads 数据 → 2560B/BD (TLAST) */
    XFER_TX_WM    = 1,  /* MM2S:送 watermark → 16KB/BD */
    XFER_RX_OUT   = 2   /* S2MM:收输出 → 【B21】48B/BD，DNA 核每条记录一个 TLAST packet */
} xfer_kind_e;

/* 小工具：对齐与最小值（单测被测项） */
static inline u32 align_down(u32 value, u32 alignment) {
    if (alignment == 0) return value;
    return (value / alignment) * alignment;
}

static inline u32 min_u32(u32 a, u32 b) {
    return (a < b) ? a : b;
}

/* BD 环及 DMA 全局上下文 */
typedef struct {
    XAxiDma dma;
    XAxiDma_BdRing *tx_ring;
    XAxiDma_BdRing *rx_ring;
    u32 tx_max_len;
    u32 rx_max_len;
} bdring_ctx_t;

extern bdring_ctx_t g_bdring_ctx;

#define AxiDma              (g_bdring_ctx.dma)
#define TxRingPtr           (g_bdring_ctx.tx_ring)
#define RxRingPtr           (g_bdring_ctx.rx_ring)
#define TxMaxTransferLen    (g_bdring_ctx.tx_max_len)
#define RxMaxTransferLen    (g_bdring_ctx.rx_max_len)

/* 设置单个 BD 环 */
int setup_bd_ring(XAxiDma_BdRing *RingPtr, u32 base, int cnt, const char *name);

/* 提交一组 BD（按 kind 选择每 BD 大小，逐个 BD 64B flush 回应 B21） */
int submit_bd_transfer(XAxiDma_BdRing *RingPtr,
                       u32 buffer_addr,
                       u32 total_length,
                       u32 max_per_bd,
                       const char *name,
                       xfer_kind_e kind);

/* 回收已完成的 BD（沿 BdRingNext 遍历回应 B21） */
int reclaim_some_bd(XAxiDma_BdRing *RingPtr, int max_to_reclaim);

#ifdef __cplusplus
}
#endif

#endif /* __BD_RING_H__ */
