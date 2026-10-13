/******************************************************************************
 * bd_ring.c — PS 固件 AXI DMA 描述符环管理实现
 *
 * 封装 setup_bd_ring、submit_bd_transfer、reclaim_some_bd 等 BD 环核心操作。
 * 严格保持逐个 BD 64B flush 与沿 BdRingNext 遍历，正面回应 B21。
 ******************************************************************************/

#include "bd_ring.h"
#include "fw_log.h"
#include "xil_printf.h"
#include "xil_cache.h"
#include "prof.h"

bdring_ctx_t g_bdring_ctx;

/*============================================================================
 * BD ring设置
 *============================================================================*/
int setup_bd_ring(XAxiDma_BdRing *RingPtr, u32 base, int cnt, const char *name)
{
    int Status;
    XAxiDma_Bd BdTemplate;
    Status = XAxiDma_BdRingCreate(RingPtr, base, base, BD_ALIGNMENT, cnt);
    if (Status != XST_SUCCESS) {
        xil_printf("[ERROR] BdRingCreate failed\n\r");
        return XST_FAILURE;
    }

    XAxiDma_BdClear(&BdTemplate);
    Status = XAxiDma_BdRingClone(RingPtr, &BdTemplate);
    if (Status != XST_SUCCESS) {
        xil_printf("[ERROR] BdRingClone failed\n\r");
        return XST_FAILURE;
    }

    XAxiDma_BdRingIntDisable(RingPtr, XAXIDMA_IRQ_ALL_MASK);

    u32 max_len = RingPtr->MaxTransferLen;
    u32 aligned_max = align_down(max_len, DMA_ADDR_ALIGNMENT);
    if (RingPtr == XAxiDma_GetTxRing(&AxiDma)) {
        TxMaxTransferLen = aligned_max;
    } else {
        RxMaxTransferLen = aligned_max;
    }
    return XST_SUCCESS;
}

/*============================================================================
 * 提交一组BD(关键:根据 kind 选择 perBD)
 *============================================================================*/
int submit_bd_transfer(XAxiDma_BdRing *RingPtr,
                       u32 buffer_addr,
                       u32 total_length,
                       u32 max_per_bd,
                       const char *name,
                       xfer_kind_e kind)
{
    PROF_SUBMIT_BEGIN(submit);
    int Status;
    XAxiDma_Bd *BdPtr, *BdCurPtr;

    u32 per_bd;
    switch (kind) {
    case XFER_TX_READS:
        per_bd = FRAME_BYTES;
        break;
    case XFER_RX_OUT:
        /* 【B21 根因】DNA 核的 s2mm_pack64 在每条 48 B 结果的第 6 拍就拉 M_AXIS_RESULT_TLAST，
         * 即每条记录都是一个独立的 AXIS packet。AXI DMA S2MM 在 SG 模式下遇到 TLAST 就
         * 关闭当前 BD，所以一个 BD 只能收下一条记录（板上取证：BD 状态 0x8c000030 =
         * Cmplt|RXSOF|RXEOF|len=48）。原实现按 16,376 B/BD 只投了 13 个 BD，
         * 收满 13 条后 S2MM_CURDESC==S2MM_TAILDESC 进入 Idle，反压把整条链锁死。
         * 正确做法：一条记录一个 BD，并在 ring 上滚动补投。 */
        per_bd = DNA_ACC_RESULT_PACKED_BYTES;
        break;
    case XFER_TX_WM:
    default: {
        u32 target = min_u32(max_per_bd, 16U*1024U);
        per_bd = align_down(target, DMA_ADDR_ALIGNMENT);
        if (per_bd == 0) per_bd = align_down(max_per_bd, DMA_ADDR_ALIGNMENT);
        break;
    }
    }
    if (per_bd == 0) per_bd = FRAME_BYTES;

    u32 bd_count = (total_length + per_bd - 1U) / per_bd;

    u32 free_bd = XAxiDma_BdRingGetFreeCnt(RingPtr);
    if (free_bd < bd_count) {
        xil_printf("[ERROR] Not enough BDs (need %u, have %u)\n\r", bd_count, free_bd);
        PROF_SUBMIT_END(submit, 0U);
        return -1;
    }

    Status = XAxiDma_BdRingAlloc(RingPtr, bd_count, &BdPtr);
    if (Status != XST_SUCCESS) {
        xil_printf("[ERROR] BD alloc failed\n\r");
        PROF_SUBMIT_END(submit, 0U);
        return -1;
    }

    BdCurPtr = BdPtr;
    u32 remaining = total_length;
    u32 offset    = 0;

    for (u32 i = 0; i < bd_count; i++) {
        u32 this_len = (remaining > per_bd) ? per_bd : remaining;
        u32 addr     = buffer_addr + offset;

        XAxiDma_BdSetBufAddr(BdCurPtr, addr);
        XAxiDma_BdSetLength(BdCurPtr, this_len, RingPtr->MaxTransferLen);

        u32 ctrl = 0;
        if (RingPtr == TxRingPtr) {
            ctrl |= XAXIDMA_BD_CTRL_TXSOF_MASK;
            ctrl |= XAXIDMA_BD_CTRL_TXEOF_MASK;
        }
        XAxiDma_BdSetCtrl(BdCurPtr, ctrl);

        remaining -= this_len;
        offset    += this_len;
        BdCurPtr   = (XAxiDma_Bd *)XAxiDma_BdRingNext(RingPtr, BdCurPtr);
    }

    /* 【B21】BD ring 是环形的：一批 BD 可能跨过环尾回绕到环首。
     * 原来的 Xil_DCacheFlushRange(BdPtr, bd_count*64) 假设这批 BD 在内存里连续，
     * 回绕时会刷到环外地址、而漏掉真正回绕到环首的那几个 BD。
     * RX 现在按 48 B/BD 投递，一次任务要用掉 4,096 个 BD 而环只有 1,024 个，
     * 必然回绕 4 次，所以必须逐个沿 BdRingNext 刷。 */
    {
        XAxiDma_Bd *FlushPtr = BdPtr;
        for (u32 i = 0; i < bd_count; i++) {
            PROF_CACHE_FLUSH_SAMPLED((UINTPTR)FlushPtr, sizeof(XAxiDma_Bd));
            FlushPtr = (XAxiDma_Bd *)XAxiDma_BdRingNext(RingPtr, FlushPtr);
        }
    }

    Status = XAxiDma_BdRingToHw(RingPtr, bd_count, BdPtr);
    if (Status != XST_SUCCESS) {
        xil_printf("[ERROR] ToHw failed\n\r");
        PROF_SUBMIT_END(submit, 0U);
        return -1;
    }
    PROF_SUBMIT_END(submit, bd_count);
    return bd_count;
}

/*============================================================================
 * 回收已完成的BD(一次尽量多)
 *============================================================================*/
int reclaim_some_bd(XAxiDma_BdRing *RingPtr, int max_to_reclaim)
{
    PROF_RECLAIM_BEGIN(reclaim);
    XAxiDma_Bd *BdPtr;
    int n = XAxiDma_BdRingFromHw(RingPtr, max_to_reclaim, &BdPtr);
    if (n > 0) {
        /* 【B21】BdRingFromHw 返回的是环上一段「逻辑连续」的 BD，它可能跨过环尾回绕。
         * 原实现用 &BdPtr[i] 线性索引，一旦回绕就会读到 BD 环之外的内存：
         * 既可能把垃圾值误判成 BD 错误而让整条流水线 FAIL，
         * 也可能漏掉真正回绕那几个 BD 的错误位。
         * RX 改成 48 B/BD 后每次任务必然回绕（4,096 条记录 / 1,024 个 BD），
         * 必须沿 BdRingNext 走。 */
        XAxiDma_Bd *CurPtr = BdPtr;
        for (int i = 0; i < n; i++) {
            u32 sts = XAxiDma_BdGetSts(CurPtr);
            if (sts & XAXIDMA_BD_STS_ALL_ERR_MASK) {
                xil_printf("[ERROR] BD status error: 0x%08X (BD %d/%d)\n\r", sts, i, n);
                PROF_RECLAIM_END(reclaim, 0U);
                return -1;
            }
            CurPtr = (XAxiDma_Bd *)XAxiDma_BdRingNext(RingPtr, CurPtr);
        }
        if (XAxiDma_BdRingFree(RingPtr, n, BdPtr) != XST_SUCCESS) {
            PROF_RECLAIM_END(reclaim, 0U);
            return -1;
        }
    }
    PROF_RECLAIM_END(reclaim, (n > 0) ? (u32)n : 0U);
    return n;
}
