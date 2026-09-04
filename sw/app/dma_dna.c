/******************************************************************************
 * dma_dna.c — PS 固件 DNA 加速器 DMA 接口实现
 *
 * 实现 dna_accelerator_init、dna_submit_rx_records、dna_submit_reads_chunk、
 * 以及 dna_wait_wm_region_bd。
 ******************************************************************************/

#include "dma_dna.h"
#include "fw_log.h"
#include "xil_printf.h"
#include "xil_cache.h"
#include "xparameters.h"
#include "sleep.h"
#include <unistd.h>

/*============================================================================
 * DNA/DMA初始化
 *============================================================================*/
int dna_accelerator_init(void)
{
    XAxiDma_Config *CfgPtr = XAxiDma_LookupConfig(XPAR_AXIDMA_0_DEVICE_ID);
    if (!CfgPtr) {
        xil_printf("[ERROR] DMA config lookup failed\n\r");
        return XST_FAILURE;
    }
    int Status = XAxiDma_CfgInitialize(&AxiDma, CfgPtr);
    if (Status != XST_SUCCESS) {
        xil_printf("[ERROR] DMA CfgInitialize failed\n\r");
        return XST_FAILURE;
    }
    if (!XAxiDma_HasSg(&AxiDma)) {
        xil_printf("[ERROR] DMA not in SG mode\n\r");
        return XST_FAILURE;
    }

    TxRingPtr = XAxiDma_GetTxRing(&AxiDma);
    RxRingPtr = XAxiDma_GetRxRing(&AxiDma);

    if (setup_bd_ring(TxRingPtr, BD_SPACE_BASE_TX, MAX_BD_COUNT_TX, "TX") != XST_SUCCESS)
        return XST_FAILURE;
    if (setup_bd_ring(RxRingPtr, BD_SPACE_BASE_RX, MAX_BD_COUNT_RX, "RX") != XST_SUCCESS)
        return XST_FAILURE;

    if (XAxiDma_BdRingStart(TxRingPtr) != XST_SUCCESS) return XST_FAILURE;
    if (XAxiDma_BdRingStart(RxRingPtr) != XST_SUCCESS) return XST_FAILURE;

    dump_dma_regs("After init");
    xil_printf("[INIT] DNA Accelerator ready\n\r");
    xil_printf("[INFO] TX BD Ring: %u BDs, RX BD Ring: %u BDs\n\r",
               MAX_BD_COUNT_TX, MAX_BD_COUNT_RX);
    return XST_SUCCESS;
}

/*============================================================================
 * 【B21】按「一条记录一个 BD」滚动补投 RX 描述符。
 * 返回本次投出的 BD 数（0 表示暂时不需要补），-1 表示失败。
 *============================================================================*/
int dna_submit_rx_records(dna_rx_state_t *st)
{
    if (st->records_submitted >= st->records_total) return 0;
    u32 remain = st->records_total - st->records_submitted;

    u32 done = (st->rx_done > 0) ? (u32)st->rx_done : 0U;
    u32 outstanding = (st->records_submitted > done) ? (st->records_submitted - done) : 0U;
    if (outstanding >= RX_OUTSTANDING_MAX) return 0;

    u32 n = RX_OUTSTANDING_MAX - outstanding;
    if (n > remain) n = remain;

    u32 free_bd = XAxiDma_BdRingGetFreeCnt(RxRingPtr);
    if (n > free_bd) n = free_bd;
    if (n == 0) return 0;

    u32 addr  = DDR_DNA_ACC_OUT_BASE + st->records_submitted * DNA_ACC_RESULT_PACKED_BYTES;
    u32 bytes = n * DNA_ACC_RESULT_PACKED_BYTES;

    int bd = submit_bd_transfer(RxRingPtr, addr, bytes, RxMaxTransferLen,
                                "RX-DNA-RECORDS", XFER_RX_OUT);
    if (bd < 0) return -1;
    st->records_submitted += n;
    return bd;
}

/*============================================================================
 * 小批提交 READS
 *============================================================================*/
int dna_submit_reads_chunk(dna_tx_state_t *st)
{
    u32 remain_frames = (st->frames_total > st->frames_sent) ?
                        (st->frames_total - st->frames_sent) : 0;
    if (remain_frames == 0) return 0;

    int reclaimed = reclaim_some_bd(TxRingPtr, 512);
    if (reclaimed < 0) {
        xil_printf("[ERROR] TX BD reclaim failed before submit\n\r");
        return -1;
    }
    if (reclaimed > 0) {
        st->tx_done += reclaimed;
        st->frames_done = st->tx_done;
    }

    int free_bd = XAxiDma_BdRingGetFreeCnt(TxRingPtr);
    if (free_bd <= 128) return 0;

    int can_frames = free_bd - 128;
    if (can_frames > 100) can_frames = 100;
    if ((u32)can_frames > remain_frames) can_frames = (int)remain_frames;
    if (can_frames <= 0) return 0;

    u32 chunk_bytes = (u32)can_frames * FRAME_BYTES;
    u32 addr        = DDR_READS_BASE + st->frames_sent * FRAME_BYTES;

    Xil_DCacheFlushRange(addr, chunk_bytes);

    int bd = submit_bd_transfer(TxRingPtr, addr, chunk_bytes, TxMaxTransferLen,
                                "TX-READS-CHUNK", XFER_TX_READS);
    if (bd < 0) {
        dump_dma_regs("TX_STREAM submit failed");
        return -1;
    }

    st->frames_sent += (u32)can_frames;
    st->tx_expected += bd;

    return bd;
}

/*============================================================================
 * 【WM 批量化】单个水印区域的 BD 有界忙等。
 * 返回 0 成功，-1 失败（BD 报错或超时）。
 *============================================================================*/
int dna_wait_wm_region_bd(u32 region, int expected)
{
    int got = 0;
    u32 waited_us = 0;

    while (got < expected) {
        int n = reclaim_some_bd(TxRingPtr, expected - got);
        if (n < 0) {
            xil_printf("[ERROR] WM region %u: TX BD error\n\r", region);
            return -1;
        }
        got += n;
        if (got >= expected) break;

        if (waited_us >= WM_BD_WAIT_US) {
            xil_printf("[ERROR] WM region %u: TX BD timeout (%d/%d after %u us)\n\r",
                       region, got, expected, waited_us);
            dump_dma_regs("WM region BD timeout");
            return -1;
        }
        usleep(WM_BD_WAIT_STEP_US);
        waited_us += WM_BD_WAIT_STEP_US;
    }
    return 0;
}
