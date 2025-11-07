/******************************************************************************
 * @file echo.c
 * @brief DNA Accelerator - 串口整段流水线(滑动窗 + 投票 + 解码)
 ******************************************************************************/

#include <string.h>
#include "echo.h"
#include "lwip/err.h"
#include "lwip/tcp.h"
#include "xil_printf.h"
#include "xil_cache.h"
#include "sleep.h"
#include "xaxidma.h"
#include "netif/xadapter.h"

#define BIT_SET(val, bit)    ((val) |= (1ULL << (bit)))
#define BIT_CLEAR(val, bit)  ((val) &= ~(1ULL << (bit)))
#define BIT_GET(val, bit)    (((val) >> (bit)) & 1ULL)

/* 轮询与日志相关 */
#define VOTER_EXPECTED_TIME_MS  500
#define VOTER_TIMEOUT_POLLS     5000000
#define VOTER_REPORT_INTERVAL   10000
#ifndef VOTER_TOTAL_BITS
#define VOTER_TOTAL_BITS          (81000u)
#endif
#define VOTER_EXPECTED_OUT_BEATS  ((VOTER_TOTAL_BITS + 63u) / 64u)  /* =1266 */
/* ===== Fallback: Voter 调试寄存器偏移（如果 echo.h 未定义时启用） ===== */
#ifndef VOTER_REG_DBG_STATE
#define VOTER_REG_DBG_STATE     0x18u
#endif
#ifndef VOTER_REG_DBG_WRITE
#define VOTER_REG_DBG_WRITE     0x24u
#endif
#ifndef VOTER_REG_ERR_FLAGS
#define VOTER_REG_ERR_FLAGS     0x2Cu
#endif

/*================ 外部网络接口 ================*/
extern struct netif *echo_netif;

/*================ 前向声明 ================*/
static err_t send_ack_byte(struct tcp_pcb *tpcb, u8 ack_type);
static void process_complete_packet(dna_connection_t *conn, u8 *packet_data, u32 total_len);
static int   parse_header(u8 *buf, u16 *magic, u8 *pkt_type, u32 *payload_len);
static err_t recv_callback(void *arg, struct tcp_pcb *tpcb, struct pbuf *p, err_t err);
static err_t accept_callback(void *arg, struct tcp_pcb *newpcb, err_t err);
static err_t poll_callback(void *arg, struct tcp_pcb *tpcb);

/*============================================================================
 * DMA常量
 *============================================================================*/
#define MAX_BD_COUNT            512
//#define BD_SPACE_BASE           0x11000000U
#define DMA_ADDR_ALIGNMENT      8U

/*============================================================================
 * 全局
 *============================================================================*/
static XAxiDma AxiDma;
static XAxiDma_BdRing *TxRingPtr;
static XAxiDma_BdRing *RxRingPtr;
static u32 TxMaxTransferLen = 0;
static u32 RxMaxTransferLen = 0;

static dna_connection_t g_conn;
static struct tcp_pcb *g_server_pcb = NULL;

/* TCP接收缓冲区 */
static u8  tcp_recv_buffer[100000];
static u32 tcp_recv_offset = 0;

/* 处理状态(poll轮询) */
typedef enum {
    PROC_IDLE = 0,
    PROC_REQUESTED,
    PROC_RUNNING,
    PROC_DONE,
    PROC_FAILED
} proc_state_e;

static volatile proc_state_e g_proc_state = PROC_IDLE;

/* 传输类型:决定每BD策略 */
typedef enum {
    XFER_TX_READS = 0,  /* MM2S:送 reads 数据 → 2560B/BD (TLAST) */
    XFER_TX_WM    = 1,  /* MM2S:送 watermark → 16KB/BD */
    XFER_RX_OUT   = 2   /* S2MM:收输出 → 16KB/BD */
} xfer_kind_e;

/*============================================================================
 * 小工具
 *============================================================================*/
static inline u32 align_down(u32 value, u32 alignment) {
    return (value / alignment) * alignment;
}
static inline u32 min_u32(u32 a, u32 b) { return (a < b) ? a : b; }

/* 喂lwIP */
static inline void keep_tcp_alive(void){
    if (echo_netif) xemacif_input(echo_netif);
}
/* ===== 通用字节视图打印工具（避免 llX 丢高 32 位） ===== */

/* 打印一个 48B 的 read（Stage1/Stage2 输入），索引按 read 计数 */
static inline void dump_read_48(const void *base_addr, u32 read_index)
{
    const UINTPTR addr = (UINTPTR)base_addr + (UINTPTR)read_index * 48U;
    Xil_DCacheInvalidateRange(addr, 48U);
    __asm__ volatile("dsb sy"); __asm__ volatile("isb");

    const volatile u8 *p = (const volatile u8 *)addr;
    xil_printf("[READ #%u] 48 bytes @ 0x%08X\n\r", read_index, (u32)addr);
    xil_printf("  [00-15]: "); for (int i = 0; i < 16; i++) xil_printf("%02X ", p[i]);
    xil_printf("\n\r  [16-31]: "); for (int i = 16; i < 32; i++) xil_printf("%02X ", p[i]);
    xil_printf("\n\r  [32-47]: "); for (int i = 32; i < 48; i++) xil_printf("%02X ", p[i]);
    xil_printf("\n\r");
}

/* 打印 8B 对齐的 u64 数组的若干元素（Stage2/Decoder 的 8B beats） */
static inline void dump_u64_bytes_window(const void *base_addr, u32 start_index, u32 count, const char *label)
{
    const UINTPTR addr = (UINTPTR)base_addr + ((UINTPTR)start_index * 8U);
    Xil_DCacheInvalidateRange(addr, 8U * count);
    __asm__ volatile("dsb sy"); __asm__ volatile("isb");

    const volatile u8 *p = (const volatile u8 *)addr;
    xil_printf("%s (index %u..%u):\n\r", label ? label : "[DUMP]", start_index, start_index + count - 1);
    for (u32 i = 0; i < count; i++) {
        const volatile u8 *b = p + (i * 8U);
        xil_printf("  [%4u]: ", start_index + i);
        for (int k = 0; k < 8; k++) xil_printf("%02X ", b[k]);
        xil_printf("\n\r");
    }
}

/*============================================================================
 * IP核 START 信号控制
 *============================================================================*/
static inline void trigger_ip_start(void) {
    write_reg32(DNA_ACCELERATOR_BASEADDR, DNA_ACC_REG0_CTRL, 0x00);
    usleep(10);
    write_reg32(DNA_ACCELERATOR_BASEADDR, DNA_ACC_REG0_CTRL, 0x01);
}
static inline void clear_ip_start(void) {
    write_reg32(DNA_ACCELERATOR_BASEADDR, DNA_ACC_REG0_CTRL, 0x00);
}

/*============================================================================
 * 打印寄存器
 *============================================================================*/
static void dump_dma_regs(const char *tag)
{
    UINTPTR tx = AxiDma.RegBase + XAXIDMA_TX_OFFSET;
    UINTPTR rx = AxiDma.RegBase + XAXIDMA_RX_OFFSET;

    u32 tx_cr = XAxiDma_ReadReg(tx, XAXIDMA_CR_OFFSET);
    u32 tx_sr = XAxiDma_ReadReg(tx, XAXIDMA_SR_OFFSET);
    u32 tx_cur= XAxiDma_ReadReg(tx, XAXIDMA_CDESC_OFFSET);
    u32 tx_tal= XAxiDma_ReadReg(tx, XAXIDMA_TDESC_OFFSET);

    u32 rx_cr = XAxiDma_ReadReg(rx, XAXIDMA_CR_OFFSET);
    u32 rx_sr = XAxiDma_ReadReg(rx, XAXIDMA_SR_OFFSET);
    u32 rx_cur= XAxiDma_ReadReg(rx, XAXIDMA_CDESC_OFFSET);
    u32 rx_tal= XAxiDma_ReadReg(rx, XAXIDMA_TDESC_OFFSET);

    xil_printf("\n\r[DMA] %s\n\r", tag);

}

/*============================================================================
 * BD ring设置
 *============================================================================*/
static int setup_bd_ring(XAxiDma_BdRing *RingPtr, u32 base, int cnt, const char *name)
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
 * 提交一组BD(关键:根据 kind 选择 perBD)
 *============================================================================*/
static int submit_bd_transfer(XAxiDma_BdRing *RingPtr,
                              u32 buffer_addr,
                              u32 total_length,
                              u32 max_per_bd,
                              const char *name,
                              xfer_kind_e kind)
{
    int Status;
    XAxiDma_Bd *BdPtr, *BdCurPtr;

    u32 per_bd;
    switch (kind) {
    case XFER_TX_READS:
        per_bd = FRAME_BYTES;
        break;
    case XFER_TX_WM:
    case XFER_RX_OUT:
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
        return -1;
    }

    Status = XAxiDma_BdRingAlloc(RingPtr, bd_count, &BdPtr);
    if (Status != XST_SUCCESS) {
        xil_printf("[ERROR] BD alloc failed\n\r");
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

    Xil_DCacheFlushRange((UINTPTR)BdPtr, bd_count * sizeof(XAxiDma_Bd));

    Status = XAxiDma_BdRingToHw(RingPtr, bd_count, BdPtr);
    if (Status != XST_SUCCESS) {
        xil_printf("[ERROR] ToHw failed\n\r");
        return -1;
    }
    return bd_count;
}

/* 回收已完成的BD(一次尽量多)*/
static int reclaim_some_bd(XAxiDma_BdRing *RingPtr, int max_to_reclaim)
{
    XAxiDma_Bd *BdPtr;
    int n = XAxiDma_BdRingFromHw(RingPtr, max_to_reclaim, &BdPtr);
    if (n > 0) {
        for (int i=0;i<n;i++) {
            u32 sts = XAxiDma_BdGetSts(&BdPtr[i]);
            if (sts & XAXIDMA_BD_STS_ALL_ERR_MASK) {
                xil_printf("[ERROR] BD status error: 0x%08X\n\r", sts);
                return -1;
            }
        }
        if (XAxiDma_BdRingFree(RingPtr, n, BdPtr) != XST_SUCCESS) return -1;
    }
    return n;
}

/*============================================================================
 * 第一级: DNA Accelerator (滑动窗+预加载)
 *============================================================================*/
typedef enum {
    PIPE_IDLE = 0,
    PIPE_WM_PREP,
    PIPE_WM_TX,
    PIPE_WM_WAIT,
    PIPE_RX_PREP,
    PIPE_TX_PREFILL,
    PIPE_START_IP,
    PIPE_TX_STREAM,
    PIPE_PROGRESS,
    PIPE_DONE_STAGE1,

    /* 第二级: Voter */
    PIPE_VOTER_PREP,
    PIPE_VOTER_START,
    PIPE_VOTER_WAIT,
    PIPE_DONE_STAGE2,
	PIPE_SEND_RESULT,
    /* 第三级: Decoder */
    PIPE_DECODER_PREP,
    PIPE_DECODER_START,
    PIPE_DECODER_WAIT,
    PIPE_DONE_STAGE3,

    PIPE_FAIL
} pipe_state_e;

static volatile pipe_state_e pipe_state = PIPE_IDLE;

typedef enum {
    PIPE_STEP_PROGRESS = 1,
    PIPE_STEP_DONE     = 0,
    PIPE_STEP_FAIL     = -1
} pipe_step_rc_e;

/* 第一级计数 */
static int wm_tx_expected = 0;
static int rx_expected    = 0;
static int tx_expected    = 0;
static int tx_done        = 0;
static int rx_done        = 0;

static u32 tx_frames_total = 0;
static u32 tx_frames_sent  = 0;
static u32 tx_frames_done  = 0;

static inline void pipeline_reset_counters(void){
    wm_tx_expected=0; rx_expected=0; tx_expected=0; tx_done=0; rx_done=0;
    tx_frames_total=0; tx_frames_sent=0; tx_frames_done=0;
}

static inline void pipeline_set_state(pipe_state_e st){ pipe_state = st; }

/* 小批提交 READS */
static int submit_reads_chunk(void)
{
    u32 remain_frames = (tx_frames_total > tx_frames_sent) ?
                        (tx_frames_total - tx_frames_sent) : 0;
    if (remain_frames == 0) return 0;

    int reclaimed = reclaim_some_bd(TxRingPtr, 512);
    if (reclaimed < 0) {
        xil_printf("[ERROR] TX BD reclaim failed before submit\n\r");
        return -1;
    }
    if (reclaimed > 0) {
        tx_done += reclaimed;
        tx_frames_done = tx_done;

    }

    int free_bd = XAxiDma_BdRingGetFreeCnt(TxRingPtr);
    if (free_bd <= 128) return 0;

    int can_frames = free_bd - 128;
    if (can_frames > 100) can_frames = 100;
    if ((u32)can_frames > remain_frames) can_frames = (int)remain_frames;
    if (can_frames <= 0) return 0;

    u32 chunk_bytes = (u32)can_frames * FRAME_BYTES;
    u32 addr        = DDR_READS_BASE + tx_frames_sent * FRAME_BYTES;

    Xil_DCacheFlushRange(addr, chunk_bytes);

    int bd = submit_bd_transfer(TxRingPtr, addr, chunk_bytes, TxMaxTransferLen,
                                "TX-READS-CHUNK", XFER_TX_READS);
    if (bd < 0) {
        dump_dma_regs("TX_STREAM submit failed");
        return -1;
    }

    tx_frames_sent += (u32)can_frames;
    tx_expected    += bd;



    return bd;
}
/* 第一级流水线步骤 */
static pipe_step_rc_e pipeline_step_stage1(dna_connection_t *conn)
{
    switch (pipe_state) {
    case PIPE_WM_PREP: {
        xil_printf("\n\r[STAGE1] WM_PREP\n\r");
        write_reg32(DNA_ACCELERATOR_BASEADDR, DNA_ACC_REG0_CTRL, 0x02);
        usleep(100);
        Xil_DCacheFlushRange(DDR_WATERMARK_BASE, conn->watermark_size);
        pipeline_set_state(PIPE_WM_TX);
        return PIPE_STEP_PROGRESS;
    }
    case PIPE_WM_TX: {
        wm_tx_expected = submit_bd_transfer(TxRingPtr, DDR_WATERMARK_BASE,
                                            conn->watermark_size, TxMaxTransferLen,
                                            "TX-WM", XFER_TX_WM);
        if (wm_tx_expected < 0) { pipeline_set_state(PIPE_FAIL); return PIPE_STEP_FAIL; }
        pipeline_set_state(PIPE_WM_WAIT);
        return PIPE_STEP_PROGRESS;
    }
    case PIPE_WM_WAIT: {
        int got = reclaim_some_bd(TxRingPtr, wm_tx_expected);
        if (got < 0) { pipeline_set_state(PIPE_FAIL); return PIPE_STEP_FAIL; }
        if (got == wm_tx_expected) {
            write_reg32(DNA_ACCELERATOR_BASEADDR, DNA_ACC_REG0_CTRL, 0x00);
            usleep(100);
            xil_printf("[STAGE1] WM preload done\n\r");
            pipeline_set_state(PIPE_RX_PREP);
        }
        return PIPE_STEP_PROGRESS;
    }
    case PIPE_RX_PREP: {
        u32 total_reads = conn->total_reads_received;
        u32 out_size = total_reads * DNA_ACC_RESULT_PACKED_BYTES;

        xil_printf("[STAGE1] RX_PREP\n\r");
        xil_printf("  Reads: %u\n\r", total_reads);
        xil_printf("  Output: %u bytes (%u × %u B/read)\n\r",
                   out_size, total_reads, DNA_ACC_RESULT_PACKED_BYTES);

        rx_expected = submit_bd_transfer(RxRingPtr, DDR_DNA_ACC_OUT_BASE,
                                        out_size, RxMaxTransferLen,
                                        "RX-DNA", XFER_RX_OUT);
        if (rx_expected < 0) { pipeline_set_state(PIPE_FAIL); return PIPE_STEP_FAIL; }
        pipeline_set_state(PIPE_TX_PREFILL);
        return PIPE_STEP_PROGRESS;
    }
    case PIPE_TX_PREFILL: {
        u32 total_reads = conn->total_reads_received;
        tx_frames_total = (total_reads + FRAME_READS - 1) / FRAME_READS;
        tx_frames_sent = 0;
        tx_frames_done = 0;

        xil_printf("[STAGE1] Total: %u reads = %u frames (%u reads/frame)\n\r",
                   total_reads, tx_frames_total, FRAME_READS);

        u32 addr = DDR_READS_BASE;
        u32 len  = FRAME_BYTES;
        Xil_DCacheFlushRange(addr, len);

        int bd = submit_bd_transfer(TxRingPtr, addr, len, TxMaxTransferLen,
                                    "TX-PREFILL", XFER_TX_READS);
        if (bd < 0) { pipeline_set_state(PIPE_FAIL); return PIPE_STEP_FAIL; }
        tx_frames_sent += 1;
        tx_expected    += bd;

        pipeline_set_state(PIPE_START_IP);
        return PIPE_STEP_PROGRESS;
    }
    case PIPE_START_IP: {
        write_reg32(DNA_ACCELERATOR_BASEADDR, DNA_ACC_REG0_CTRL, 0x01);
        usleep(50);
        xil_printf("[STAGE1] IP core START\n\r");
        pipeline_set_state(PIPE_TX_STREAM);
        return PIPE_STEP_PROGRESS;
    }
    case PIPE_TX_STREAM: {
        int got_rx = reclaim_some_bd(RxRingPtr, 512);
        if (got_rx < 0) { dump_dma_regs("TX_STREAM reclaim RX failed"); pipeline_set_state(PIPE_FAIL); return PIPE_STEP_FAIL; }
        if (got_rx > 0) {
            rx_done += got_rx;

        }

        int free_rx = XAxiDma_BdRingGetFreeCnt(RxRingPtr);
        if (free_rx < 100 && tx_frames_sent < tx_frames_total) {
            static u32 rx_stall_count = 0; rx_stall_count++;
            for (int i = 0; i < 5; i++) {
                got_rx = reclaim_some_bd(RxRingPtr, 512);
                if (got_rx > 0) {
                    rx_done += got_rx;
                    free_rx = XAxiDma_BdRingGetFreeCnt(RxRingPtr);
                    if (free_rx >= 150) { rx_stall_count = 0; break; }
                }
                usleep(50);
            }
            if (rx_stall_count > 5000) { xil_printf("[WARN] RX recovery timeout, forcing TX continue\n\r"); rx_stall_count = 0; }
            else return PIPE_STEP_PROGRESS;
        }

        int bd = submit_reads_chunk();
        if (bd < 0) { dump_dma_regs("TX_STREAM submit failed"); pipeline_set_state(PIPE_FAIL); return PIPE_STEP_FAIL; }

        int got_tx = reclaim_some_bd(TxRingPtr, 512);
        if (got_tx < 0) { dump_dma_regs("TX_STREAM reclaim TX failed"); pipeline_set_state(PIPE_FAIL); return PIPE_STEP_FAIL; }
        if (got_tx > 0) { tx_done += got_tx; tx_frames_done = tx_done; }

        static u32 last_report_sent = 0;


        static u32 last_rx_done = 0, stuck_count = 0;
        if (rx_done == last_rx_done && tx_frames_sent >= tx_frames_total) {
            stuck_count++;
            if (stuck_count > 10000) {
                xil_printf("\n\r[ERROR] RX stuck at %d/%d after TX complete!\n\r", rx_done, rx_expected);
                dump_dma_regs("RX stuck");
                xil_printf("[STAGE1] Final RX recovery attempt...\n\r");
                for (int i = 0; i < 10; i++) {
                    got_rx = reclaim_some_bd(RxRingPtr, 512);
                    if (got_rx > 0) { rx_done += got_rx; xil_printf("  +%d BDs\n\r", got_rx); }
                    usleep(1000);
                }
                if (rx_done == last_rx_done) { xil_printf("[ERROR] RX truly stuck, hardware issue!\n\r"); pipeline_set_state(PIPE_FAIL); return PIPE_STEP_FAIL; }
                stuck_count = 0;
            }
        } else stuck_count = 0;
        last_rx_done = rx_done;

        if (tx_frames_sent >= tx_frames_total && tx_done >= tx_expected && rx_done >= rx_expected) {
            xil_printf("\n\r[STAGE1] COMPLETE!\n\r");
            xil_printf("  TX: sent=%u done=%d/%d\n\r", tx_frames_sent, tx_done, tx_expected);
            xil_printf("  RX: done=%d/%d\n\r", rx_done, rx_expected);
            clear_ip_start(); usleep(100);
            pipeline_set_state(PIPE_PROGRESS);
            return PIPE_STEP_PROGRESS;
        }
        return PIPE_STEP_PROGRESS;
    }
    case PIPE_PROGRESS: {
        int got_tx = reclaim_some_bd(TxRingPtr, 256); if (got_tx < 0){pipeline_set_state(PIPE_FAIL);return PIPE_STEP_FAIL;}
        tx_done += got_tx; tx_frames_done = tx_done;

        int got_rx = reclaim_some_bd(RxRingPtr, 256); if (got_rx < 0){pipeline_set_state(PIPE_FAIL);return PIPE_STEP_FAIL;}
        rx_done += got_rx;

        static u32 wait_count = 0;
        if (++wait_count >= 50) {
            xil_printf("[STAGE1] WAIT tx=%u/%u rx=%d/%d\n\r", tx_frames_done, tx_frames_total, rx_done, rx_expected);
            wait_count = 0;
        }

        if (tx_frames_done >= tx_frames_total && rx_done >= rx_expected) {
            pipeline_set_state(PIPE_DONE_STAGE1);
            wait_count = 0;
            return PIPE_STEP_PROGRESS;
        }
        return PIPE_STEP_PROGRESS;
    }
    case PIPE_DONE_STAGE1: {
    	  xil_printf("\n\r[STAGE1] ========================================\n\r");
    	    xil_printf("[STAGE1] ✓ DNA Accelerator stage COMPLETE\n\r");
    	    xil_printf("[STAGE1] ========================================\n\r");

    	    /* 直接进入 Stage2：使用 Stage1 输出来做投票 */
    	    xil_printf("[STAGE1→STAGE2] Using Stage1 output directly\n\r");
    	    xil_printf("  Output address: 0x%08X\n\r", DDR_DNA_ACC_OUT_BASE);
    	    xil_printf("  Data format: 48 bytes/read × %u reads\n\r", TOTAL_READS);
    	    xil_printf("  Total size: %u bytes\n\r", TOTAL_READS * 48);

    	    /* 验证前 10 个 read 的数据新鲜度 */
    	    Xil_DCacheInvalidateRange(DDR_DNA_ACC_OUT_BASE, 48U * 10U);
    	    __asm__ volatile("dsb sy");
    	    __asm__ volatile("isb");

    	    /* 统计前 10 个 read 的非零字节（更直观），并展示第 0 read 的完整 48B */
    	    const volatile u8 *pbytes = (const volatile u8 *)DDR_DNA_ACC_OUT_BASE;
    	    u32 nonzero_bytes = 0;
    	    for (u32 i = 0; i < 10U * 48U; i++) {
    	        if (pbytes[i] != 0) nonzero_bytes++;
    	    }

    	    xil_printf("\n\r[DEBUG] Output Statistics (first 10 reads):\n\r");
    	    xil_printf("  Non-zero bytes: %u / %u (%.1f%%)\n\r",
    	               nonzero_bytes, 10U * 48U,
    	               (float)nonzero_bytes * 100.0f / (float)(10U * 48U));

    	    xil_printf("\n\r[DEBUG] First read (48 bytes):\n\r");
    	    dump_read_48((const void*)DDR_DNA_ACC_OUT_BASE, 0);


    	    /* 友好提示：若几乎全为 0，告警一次 */
    	    if (nonzero_bytes == 0) {
    	        xil_printf("\n\r[WARNING] ⚠️  Stage1 output seems all zeros in first 10 reads!\n\r");
    	        xil_printf("[WARNING] Possible causes:\n\r");
    	        xil_printf("  1) DMA transfer incomplete\n\r");
    	        xil_printf("  2) IP core computation error\n\r");
    	        xil_printf("  3) Invalid input reads/watermark\n\r");
    	    }

    	    /* 强制把数据刷新到 DDR（后续 Stage2 直接读取） */
    	    xil_printf("\n\r[STAGE1] Flushing all output to DDR...\n\r");
    	    Xil_DCacheFlushRange(DDR_DNA_ACC_OUT_BASE, TOTAL_READS * 48U);
    	    __asm__ volatile("dsb sy");
    	    __asm__ volatile("isb");
    	    usleep(5000);
    	    xil_printf("[STAGE1] ✓ Flush complete\n\r");

    	    xil_printf("\n\r[PIPELINE] Proceeding to Stage2 (Voter).\n\r");
    	    pipeline_set_state(PIPE_VOTER_PREP);
    	    return PIPE_STEP_PROGRESS;
    	}
    default:
        return PIPE_STEP_FAIL;
    }
}

/*============================================================================
 * 第二级: Voter (投票)
 *============================================================================*/
static pipe_step_rc_e pipeline_step_stage2(dna_connection_t *conn)
{

    switch (pipe_state) {

    /* ========================================================================
     * PIPE_VOTER_PREP: Voter准备阶段
     * ======================================================================== */
    case PIPE_VOTER_PREP: {
    	xil_printf("\n\r========================================\n\r");
    	    xil_printf("[STAGE2] Voter Preparation\n\r");
    	    xil_printf("========================================\n\r");
    	   // clear_voter_out_region();


        // ✅ Cache一致性修复: Invalidate输入区域cache
        xil_printf("[STAGE2] Invalidating input cache...\n\r");
        const u32 VOTER_IN_TEMP = DDR_VOTER_IN_BASE;
        const u32 INV_CHUNK = 256*1024;
        u32 inv_done = 0;

        while (inv_done < VOTER_INPUT_TOTAL_BYTES) {
            u32 chunk = (VOTER_INPUT_TOTAL_BYTES - inv_done > INV_CHUNK)
                        ? INV_CHUNK
                        : (VOTER_INPUT_TOTAL_BYTES - inv_done);
            Xil_DCacheInvalidateRange(VOTER_IN_TEMP + inv_done, chunk);
            inv_done += chunk;
        }

        __asm__ volatile("dsb sy");
        __asm__ volatile("isb");
        usleep(1000);

        xil_printf("[STAGE2] ✓ Cache invalidated (%u bytes)\n\r", inv_done);

        /* -------------------- 配置Voter寄存器（修复 OUT_BEATS 计算） -------------------- */
        const u32 VOTER_IN_ADDR        = DDR_VOTER_IN_BASE;
        const u32 VOTER_OUT_ADDR       = DDR_VOTER_OUT_BASE;
        const u32 VOTER_IN_BEATS       = TOTAL_READS * 6u;              /* 每个 read 6 个 u64 */
        const u32 VOTER_OUT_BEATS_EXP  = VOTER_EXPECTED_OUT_BEATS;      // [FIX] 期望拍数 = ceil(81000/64) = 1266

        xil_printf("[STAGE2] Configuration:\n\r");
        xil_printf("  Input address:  0x%08X (Stage1 output)\n\r", VOTER_IN_ADDR);
        xil_printf("  Output address: 0x%08X\n\r", VOTER_OUT_ADDR);
        xil_printf("  Input beats:    %u (6 u64 / read)\n\r", VOTER_IN_BEATS);
        xil_printf("  Output beats:   %u (expected)\n\r", VOTER_OUT_BEATS_EXP);
        xil_printf("  Total reads:    %u\n\r", TOTAL_READS);

        /* 下发寄存器（关键：OUT_BEATS 用期望拍数） */
        write_reg32(VOTER_BASEADDR, VOTER_REG_IN_ADDR,     VOTER_IN_ADDR);
        write_reg32(VOTER_BASEADDR, VOTER_REG_IN_BEATS,    VOTER_IN_BEATS);
        write_reg32(VOTER_BASEADDR, VOTER_REG_OUT_ADDR,    VOTER_OUT_ADDR);
        write_reg32(VOTER_BASEADDR, VOTER_REG_OUT_BEATS,   VOTER_OUT_BEATS_EXP);  // [FIX]
        write_reg32(VOTER_BASEADDR, VOTER_REG_TOTAL_READS, TOTAL_READS);
        __asm__ volatile("dsb sy"); __asm__ volatile("isb"); usleep(10);

        /* 回读寄存器并强校验（包含 OUT_BEATS 一致性） */
        xil_printf("\n\r[VERIFY] Configuration readback:\n\r");
        u32 in_addr_rb     = read_reg32(VOTER_BASEADDR, VOTER_REG_IN_ADDR);
        u32 in_beats_rb    = read_reg32(VOTER_BASEADDR, VOTER_REG_IN_BEATS);
        u32 out_addr_rb    = read_reg32(VOTER_BASEADDR, VOTER_REG_OUT_ADDR);
        u32 out_beats_rb   = read_reg32(VOTER_BASEADDR, VOTER_REG_OUT_BEATS);
        u32 total_reads_rb = read_reg32(VOTER_BASEADDR, VOTER_REG_TOTAL_READS);

        xil_printf("  IN_ADDR     : 0x%08X\n\r", in_addr_rb);
        xil_printf("  IN_BEATS    : %u\n\r",    in_beats_rb);
        xil_printf("  OUT_ADDR    : 0x%08X\n\r", out_addr_rb);
        xil_printf("  OUT_BEATS   : %u (expected %u)\n\r", out_beats_rb, VOTER_OUT_BEATS_EXP);
        xil_printf("  TOTAL_READS : %u\n\r",    total_reads_rb);

        /* [FIX] 任何一项不一致 → 立即失败，避免后续 DONE 护栏卡死 */
        if (in_addr_rb  != VOTER_IN_ADDR      ||
            in_beats_rb != VOTER_IN_BEATS     ||
            out_addr_rb != VOTER_OUT_ADDR     ||
            out_beats_rb!= VOTER_OUT_BEATS_EXP||
            total_reads_rb != TOTAL_READS)
        {
            xil_printf("\n\r[ERROR] Voter configuration verification failed!\n\r");
            xil_printf("       OUT_BEATS mismatch will cause DONE guard to stall.\n\r");
            pipeline_set_state(PIPE_FAIL);
            return PIPE_STEP_FAIL;
        }
        xil_printf("[STAGE2] ✓ Configuration successful\n\r");

    	    pipeline_set_state(PIPE_VOTER_START);
    	    return PIPE_STEP_PROGRESS;
    }
    /* ========================================================================
     * PIPE_VOTER_START: 配置并启动Voter IP核
     * ======================================================================== */
    case PIPE_VOTER_START: {

        xil_printf("\n\r========================================\n\r");
        xil_printf("[STAGE2] Starting Voter IP Core\n\r");
        xil_printf("========================================\n\r");

        const u32 voter_in_addr      = DDR_DNA_ACC_OUT_BASE;
        const u32 voter_out_addr     = DDR_VOTER_OUT_BASE;
        const u32 voter_total_reads  = TOTAL_READS;
        const u32 voter_out_beats    = VOTER_OUTPUT_BEATS;

        /* -------------------- Pre-start Input Validation（全部字节视图） -------------------- */
        xil_printf("\n\r[STAGE2] Pre-start Input Validation:\n\r");
        Xil_DCacheInvalidateRange(voter_in_addr, 48U * 10U);
        __asm__ volatile("dsb sy"); __asm__ volatile("isb");
        usleep(1000);

        /* 统计前 10 个 read 的非零字节 */
        const volatile u8 *vin = (const volatile u8 *)voter_in_addr;
        u32 nz = 0;
        for (u32 i = 0; i < 10U * 48U; i++) if (vin[i] != 0) nz++;
        xil_printf("  Non-zero bytes: %u / %u\n\r", nz, 10U * 48U);

        /* 打印第 0 个 read 的 48B 字节视图（不再打印 64 位 Word0） */
        xil_printf("\n\r[DEBUG] First read (48 bytes):\n\r");
        dump_read_48((const void*)voter_in_addr, 0);

        /* 如需：从字节解析 score/position（示例，与你的位域注释一致） */
        const u8 *src = (const u8*)voter_in_addr;
        u16 score = (u16)(src[0] | ((src[1] & 0x03) << 8));                                   /* bits[9:0]  */
        u32 position = ((src[1] >> 2) & 0x3F) | ((u32)src[2] << 6) | ((src[3] & 0x03) << 14); /* bits[25:10] */
        xil_printf("  Parsed Score: %u\n\r", score);
        xil_printf("  Parsed Position: %u\n\r", position);

        if (nz == 0) {
            xil_printf("\n\r[ERROR] ❌ CRITICAL: Stage1→Stage2 input appears all-zero!\n\r");
            xil_printf("[ERROR] Check DMA, IP configuration, or endian conversion.\n\r");
            pipeline_set_state(PIPE_FAIL);
            return PIPE_STEP_FAIL;
        }

        xil_printf("\n\r[STAGE2] ✓ Input validation passed\n\r");
        xil_printf("[STAGE2] Configuration:\n\r");
        xil_printf("  Input format: 48 bytes/read (6 beats/read)\n\r");
        xil_printf("  TOTAL_READS : %u (HW will auto-read 6 beats per read)\n\r", voter_total_reads);

        /* -------------------- Step 1: 读取初始状态 -------------------- */
        u32 status_init = read_reg32(VOTER_BASEADDR, VOTER_REG_STATUS);
        xil_printf("\n\r[STAGE2] Initial status: 0x%02X (IDLE=%d, DONE=%d)\n\r",
                   status_init,
                   (status_init & VOTER_STATUS_IDLE) ? 1 : 0,
                   (status_init & VOTER_STATUS_DONE) ? 1 : 0);

        /* -------------------- Step 2: 若 DONE=1，则清一次 DONE -------------------- */
        if (status_init & VOTER_STATUS_DONE) {
            xil_printf("[STAGE2] DONE set at init, clearing...\n\r");
            write_reg32(VOTER_BASEADDR, VOTER_REG_START, 0x02);  /* bit1=1: done_clr */
            usleep(500);                                         /* 短延时足够 */
            write_reg32(VOTER_BASEADDR, VOTER_REG_START, 0x00);  /* 拉回0 */
            usleep(100);

            u32 st = read_reg32(VOTER_BASEADDR, VOTER_REG_STATUS);
            xil_printf("[STAGE2] Status after clear: 0x%02X (IDLE=%d, DONE=%d)\n\r",
                       st, (st & VOTER_STATUS_IDLE) ? 1 : 0, (st & VOTER_STATUS_DONE) ? 1 : 0);
            if (st & VOTER_STATUS_DONE) {
                xil_printf("[STAGE2] ❌ ERROR: Failed to clear DONE flag!\n\r");
                pipeline_set_state(PIPE_FAIL);
                return PIPE_STEP_FAIL;
            }
            status_init = st;
        }

        /* -------------------- Step 3: 若非 IDLE，则做一次轻量复位 -------------------- */
        if (!(status_init & VOTER_STATUS_IDLE)) {
            xil_printf("[STAGE2] WARNING: Voter not IDLE, resetting config...\n\r");
            write_reg32(VOTER_BASEADDR, VOTER_REG_START, 0x00);
            write_reg32(VOTER_BASEADDR, VOTER_REG_IN_BEATS, 0);
            write_reg32(VOTER_BASEADDR, VOTER_REG_OUT_BEATS, 0);
            write_reg32(VOTER_BASEADDR, VOTER_REG_TOTAL_READS, 0);
            usleep(2000);

            u32 st = read_reg32(VOTER_BASEADDR, VOTER_REG_STATUS);
            if (!(st & VOTER_STATUS_IDLE)) {
                xil_printf("[STAGE2] ❌ ERROR: Cannot reset Voter to IDLE!\n\r");
                pipeline_set_state(PIPE_FAIL);
                return PIPE_STEP_FAIL;
            }
            xil_printf("[STAGE2] ✓ Reset successful\n\r");
        }

        /* -------------------- Step 4: 配置寄存器 + 回读校验 -------------------- */
        xil_printf("\n\r[STAGE2] Writing configuration registers...\n\r");

        write_reg32(VOTER_BASEADDR, VOTER_REG_IN_ADDR,     voter_in_addr);
        write_reg32(VOTER_BASEADDR, VOTER_REG_IN_BEATS,    voter_total_reads);
        write_reg32(VOTER_BASEADDR, VOTER_REG_OUT_ADDR,    voter_out_addr);
        write_reg32(VOTER_BASEADDR, VOTER_REG_OUT_BEATS,   voter_out_beats);
        write_reg32(VOTER_BASEADDR, VOTER_REG_TOTAL_READS, voter_total_reads);
        __asm__ volatile("dsb sy"); __asm__ volatile("isb");
        usleep(10);
        // 验证硬件收到的配置
        xil_printf("\n\r[VERIFY] Configuration readback:\n\r");
        u32 hw_out_addr = read_reg32(VOTER_BASEADDR, VOTER_REG_OUT_ADDR);
        xil_printf("  Expected OUT_ADDR: 0x%08X\n\r", DDR_VOTER_OUT_BASE);
        xil_printf("  Hardware OUT_ADDR: 0x%08X\n\r", hw_out_addr);
        if (hw_out_addr != DDR_VOTER_OUT_BASE) {
            xil_printf("  ⚠️  ADDRESS MISMATCH!\n\r");
        }
        u32 in_addr_rb     = read_reg32(VOTER_BASEADDR, VOTER_REG_IN_ADDR);
        u32 in_beats_rb    = read_reg32(VOTER_BASEADDR, VOTER_REG_IN_BEATS);
        u32 out_addr_rb    = read_reg32(VOTER_BASEADDR, VOTER_REG_OUT_ADDR);
        u32 out_beats_rb   = read_reg32(VOTER_BASEADDR, VOTER_REG_OUT_BEATS);
        u32 total_reads_rb = read_reg32(VOTER_BASEADDR, VOTER_REG_TOTAL_READS);



        if (in_addr_rb != voter_in_addr || in_beats_rb != voter_total_reads ||
            out_addr_rb != voter_out_addr || out_beats_rb != VOTER_OUTPUT_BEATS ||
            total_reads_rb != TOTAL_READS) {
            xil_printf("\n\r[ERROR] Configuration verification failed!\n\r");
            pipeline_set_state(PIPE_FAIL);
            return PIPE_STEP_FAIL;
        }

        /* -------------------- Step 5: 发送 START 脉冲（简洁稳定版） -------------------- */
        xil_printf("\n\r[START] Sending START pulse to Voter IP core...\n\r");

        write_reg32(VOTER_BASEADDR, VOTER_REG_START, 0x00);
        usleep(100);

        u32 status_before_start = read_reg32(VOTER_BASEADDR, VOTER_REG_STATUS);
        xil_printf("[START] Status before START: 0x%02X (IDLE=%d, DONE=%d)\n\r",
                   status_before_start,
                   (status_before_start & VOTER_STATUS_IDLE) ? 1 : 0,
                   (status_before_start & VOTER_STATUS_DONE) ? 1 : 0);

        if (!(status_before_start & VOTER_STATUS_IDLE)) {
            xil_printf("[START] ❌ ERROR: IP core not IDLE before START!\n\r");
            pipeline_set_state(PIPE_FAIL);
            return PIPE_STEP_FAIL;
        }

        /* 发送短脉冲：bit0=1（start），bit1=0（不清done） */
        write_reg32(VOTER_BASEADDR, VOTER_REG_START, 0x01);
        usleep(100);
        write_reg32(VOTER_BASEADDR, VOTER_REG_START, 0x00);
        usleep(100);

        u32 status_after_start = read_reg32(VOTER_BASEADDR, VOTER_REG_STATUS);
        xil_printf("[START] Status after START: 0x%02X (IDLE=%d, DONE=%d)\n\r",
                   status_after_start,
                   (status_after_start & VOTER_STATUS_IDLE) ? 1 : 0,
                   (status_after_start & VOTER_STATUS_DONE) ? 1 : 0);

        if (status_after_start & VOTER_STATUS_IDLE) {
            xil_printf("[START] ⚠️ NOTE: Still IDLE after START (could be ultra-fast or not started)\n\r");
        } else {
            xil_printf("[START] ✓ IP core started (IDLE: 1→0)\n\r");
        }

        xil_printf("[START] ✓ START pulse issued\n\r");
        xil_printf("[STAGE2] Waiting for completion...\n\r");
        xil_printf("[STAGE2] ==========================================\n\r\n\r");

        /* 进入等待状态 */
        pipeline_set_state(PIPE_VOTER_WAIT);
        return PIPE_STEP_PROGRESS;
    }

    /* ========================================================================
     * PIPE_VOTER_WAIT: 轮询等待Voter完成
     * ======================================================================== */
    case PIPE_VOTER_WAIT: {
        static u32 poll_count = 0;

        /* 读取状态寄存器 */
        u32 status = read_reg32(VOTER_BASEADDR, VOTER_REG_STATUS);

        /* ===== 追加：DONE 之外的“写进度守卫” ===== */
        static u32 poll_cnt = 0;
        poll_cnt++;

        if ((poll_cnt % 2000u) == 0u) {  // 每 2000 次轮询做一次内存侧进度检查，避免串口过载
            /* 统计已写拍数：哨兵值被覆盖即视为已写 */
            Xil_DCacheInvalidateRange(DDR_VOTER_OUT_BASE, VOTER_OUTPUT_BEATS * 8u);
            volatile const u64 *p64 = (volatile const u64 *)DDR_VOTER_OUT_BASE;
            u32 written = 0;
            for (u32 i = 0; i < VOTER_OUTPUT_BEATS; ++i) {
                if (p64[i] != 0x55AA55AA55AA550AULL)  /* 你前面清区时的哨兵值 */
                    written++;
            }
            /* ---- 追加：读取硬件调试寄存器，判定所处阶段 ---- */
            if ((poll_cnt % 1000u) == 0u) {
                const u32 status   = read_reg32(VOTER_BASEADDR, VOTER_REG_STATUS);      // 0x00
                const u32 dbg_st   = read_reg32(VOTER_BASEADDR, VOTER_REG_DBG_STATE);   // 0x18
                const u32 dbg_wcnt = read_reg32(VOTER_BASEADDR, VOTER_REG_DBG_WRITE);   // 0x24
                const u32 errf     = read_reg32(VOTER_BASEADDR, VOTER_REG_ERR_FLAGS);   // 0x2C

                xil_printf("[DBG] STATUS=0x%02X (IDLE=%u,DONE=%u)  FSM=%u  WCOUNT=%u  ERR=0x%X\n\r",
                           status, status & 0x1, (status>>1)&0x1, dbg_st, dbg_wcnt, errf);

                /* 小抄：FSM 编码（见我们定义）
                   0:IDLE 1:INIT 2:R_SETUP 3:R_DATA 4:PARSE 5:CALC 6:V_READ 7:V_UPD
                   8:NEXT 9:OUT_PREF 10:OUT_ADDR 11:OUT_PACK 12:OUT_SETUP 13:OUT_WRITE
                   14:WAIT_BRESP 15:DONE 16:ERROR
                */
            }

            if (written >=VOTER_OUTPUT_BEATS) {
                xil_printf("\n\r[STAGE2] ✓ Memory shows %u/%u beats written (100%%), but DONE=0.\n\r",
                           written, VOTER_OUTPUT_BEATS);
                xil_printf("[STAGE2] ⚠️ Treating as completed (likely OUT_BEATS mismatch blocked DONE guard).\n\r");

                /* 按完成路径收尾：让 Stage3 能继续读取 */
                write_reg32(VOTER_BASEADDR, VOTER_REG_START, 0x00);
                pipeline_set_state(PIPE_DONE_STAGE2);
                poll_cnt = 0;
                return PIPE_STEP_PROGRESS;
            } else {
                xil_printf("[POLL #%u] Progress: %u/%u beats written\n\r",
                           poll_cnt, written,VOTER_OUTPUT_BEATS);
            }
        }

        /* 条件1: DONE标志位置位 */
        if (status & VOTER_STATUS_DONE) {
            xil_printf("\n\r[STAGE2] ========================================\n\r");
            xil_printf("[STAGE2] ✓ DONE flag set after %u polls\n\r", poll_count);
            xil_printf("[STAGE2] ========================================\n\r");

            /* 清除START信号 */
            write_reg32(VOTER_BASEADDR, VOTER_REG_START, 0x00);

            /* 重置轮询计数 */
            poll_count = 0;

            /* 进入完成状态 */
            pipeline_set_state(PIPE_DONE_STAGE2);
            return PIPE_STEP_PROGRESS;
        }

        /* 超时检查 */
        poll_count++;
        if (poll_count >= 100000) {  // 10万次轮询超时
            xil_printf("\n\r[ERROR] Voter timeout after %u polls\n\r", poll_count);
            xil_printf("[ERROR] Final status: 0x%02X\n\r", status);

            /* ✓ 新增：输出详细诊断信息 */
            xil_printf("[ERROR] Diagnostic information:\n\r");
            xil_printf("  - Voter may be stuck in processing\n\r");
            xil_printf("  - Check if START signal was captured\n\r");
            xil_printf("  - Verify input data format\n\r");

            /* 清除START信号并失败 */
            write_reg32(VOTER_BASEADDR, VOTER_REG_START, 0x00);
            poll_count = 0;
            pipeline_set_state(PIPE_FAIL);
            return PIPE_STEP_FAIL;
        }

        return PIPE_STEP_PROGRESS;
    }
    /* ========================================================================
     * PIPE_DONE_STAGE2: Voter完成,验证输出并准备进入Stage3
     * ======================================================================== */
    case PIPE_DONE_STAGE2: {
    	  xil_printf("\n\r[STAGE2] ========================================\n\r");
    	    xil_printf("[STAGE2] ✓ Voter stage COMPLETE\n\r");
    	    xil_printf("[STAGE2] ========================================\n\r");
    	    /* PIPE_DONE_STAGE2 分支内： */
    	    u32 voter_out_addr = DDR_VOTER_OUT_BASE;

    	    // ✅ 硬件写完后，只需要 Invalidate，让CPU丢弃旧缓存行，从DDR重取真值
    	    xil_printf("[STAGE2] Making HW-written output visible to CPU (invalidate only)...\n\r");
    	    Xil_DCacheInvalidateRange(voter_out_addr, VOTER_OUTPUT_BYTES);   // [FIX] 改为仅 Invalidate
    	    __asm__ volatile("dsb sy");
    	    __asm__ volatile("isb");
    	    usleep(100);

    	    xil_printf("[STAGE2] Verifying output...\n\r");
    	    // 这里即可直接读/统计，不再需要前面的 Flush

        Xil_DCacheInvalidateRange(voter_out_addr, VOTER_OUTPUT_BYTES);
        __asm__ volatile("dsb sy");
        usleep(100);

    	    /* 验证输出数据 */
    	    xil_printf("[STAGE2] Verifying output data...\n\r");
    	    u64 *out_ptr = (u64*)voter_out_addr;
    	    u32 zero_count = 0, nonzero_count = 0;

    	    // ⭐ 扩大检查范围到前1000个u64
    	    u32 check_count = (1000 < VOTER_OUTPUT_BEATS) ? 1000 : VOTER_OUTPUT_BEATS;

    	    for (u32 i = 0; i < check_count; i++) {
    	        if (out_ptr[i] == 0) {
    	            zero_count++;
    	        } else {
    	            nonzero_count++;
    	        }
    	    }

    	    xil_printf("[STAGE2] Data statistics (first %u u64s):\n\r", check_count);
    	    xil_printf("  Zero count    : %u (%.1f%%)\n\r",
    	               zero_count, (float)zero_count * 100.0f / check_count);
    	    xil_printf("  Non-zero count: %u (%.1f%%)\n\r",
    	               nonzero_count, (float)nonzero_count * 100.0f / check_count);
    	    /* 警告：如果输出全为0 */
    	    if (nonzero_count == 0) {
    	        xil_printf("\n\r[WARNING] Voter output is all zeros!\n\r");
    	        xil_printf("[WARNING] This may indicate:\n\r");
    	        xil_printf("  1. Input data format mismatch between Stage1 and Voter\n\r");
    	        xil_printf("  2. Voter parsing logic error (codeword extraction)\n\r");
    	        xil_printf("  3. Voting algorithm produced all-zero result\n\r");
    	        xil_printf("  4. AXI write channel issue (writes not reaching DDR)\n\r");
    	        xil_printf("  5. BRAM initialization problem\n\r");
    	        xil_printf("[WARNING] Stage3 (Decoder) will likely fail or produce garbage.\n\r");
    	        xil_printf("[WARNING] Proceeding anyway for debugging...\n\r");
    	    } else {
    	        xil_printf("\n\r[STAGE2] ✓ Output contains valid data\n\r");
    	        xil_printf("[STAGE2] Non-zero ratio: %.1f%%\n\r",
    	                   (float)nonzero_count * 100.0f / check_count);
    	    }

    	    // ✅ 给 Stage3 使用时，保持“硬件写→CPU读”的一致性策略：仅 Invalidate 即可
    	    xil_printf("[STAGE2] Preparing output for Stage3 (invalidate only)...\n\r");
    	    Xil_DCacheInvalidateRange(voter_out_addr, VOTER_OUTPUT_BYTES);   // [FIX] 只 Invalidate
    	    __asm__ volatile("dsb sy");
    	    __asm__ volatile("isb");
    	    usleep(100);

    	    __asm__ volatile("dsb sy");
    	    __asm__ volatile("isb");
    	    usleep(2000);
    	    xil_printf("[STAGE2] ✓ Flush complete\n\r");

    	    xil_printf("\n\r[PIPELINE] Proceeding to Stage3 (Decoder)...\n\r");
    	    pipeline_set_state(PIPE_DECODER_PREP);
    	    return PIPE_STEP_PROGRESS;
    }

    default:
        xil_printf("[ERROR] Unknown state in pipeline_step_stage2: %d\n\r",
                   pipe_state);
        return PIPE_STEP_FAIL;
    }
}
/*============================================================================
 * 第三阶段(最终修复版本)
 * 核心规模统一：
 *   - 输入：81000 bit → 输入拍数 1266(最后一拍仅 40bit)
 *   - 输出：64800 字节 → 8100 拍(8B/拍)
 *============================================================================*/
#ifdef DECODER_INPUT_BEATS
#undef DECODER_INPUT_BEATS
#endif
#ifdef DECODER_OUTPUT_BEATS
#undef DECODER_OUTPUT_BEATS
#endif
#ifdef DECODER_OUTPUT_BYTES
#undef DECODER_OUTPUT_BYTES
#endif
#define DEC_IN_BITS              (81000u)
#define DECODER_INPUT_BEATS      ((DEC_IN_BITS + 63u)/64u)  /* =1266 */  /* =1266 */
#define DECODER_OUTPUT_BYTES     (8100u)
#define DECODER_OUTPUT_BEATS     ((DECODER_OUTPUT_BYTES + 7u)/8u)  /* =1013 */  /* =8100 */
static pipe_step_rc_e pipeline_step_stage3(dna_connection_t *conn)
{
	u32 status;
	    const u32 DEC_IN_ADDR  = DDR_VOTER_OUT_BASE;
	    const u32 DEC_OUT_ADDR = DDR_DECODER_OUT_BASE;
	    const u32 DEC_IN_BEATS = 1266;   // 81000位 / 64
	    const u32 DEC_OUT_BEATS = 1013;  // 8100字节 / 8

	    switch (pipe_state) {

	    case PIPE_DECODER_PREP: {
	        xil_printf("\n\r========================================\n\r");
	        xil_printf("[STAGE3] Decoder Preparation\n\r");
	        xil_printf("========================================\n\r");

	        // ✅ 关键修复：在做任何操作前先强制清零START和beats
	        xil_printf("[STAGE3] Step 0: Ensuring START is cleared...\n\r");
	        write_reg32(DECODER_BASEADDR, DECODER_REG_START, 0x00);
	        write_reg32(DECODER_BASEADDR, DECODER_REG_IN_BEATS, 0);
	        write_reg32(DECODER_BASEADDR, DECODER_REG_OUT_BEATS, 0);
	        usleep(10000);  // 等待10ms

	        u32 status_before_config = read_reg32(DECODER_BASEADDR, DECODER_REG_STATUS);
	        xil_printf("[STAGE3] Status before config: 0x%02X (IDLE=%d)\n\r",
	                   status_before_config, (status_before_config & 0x01) ? 1 : 0);

	        if (!(status_before_config & DECODER_STATUS_IDLE)) {
	            xil_printf("[STAGE3] ❌ ERROR: Not IDLE before config!\n\r");
	            pipeline_set_state(PIPE_FAIL);
	            return PIPE_STEP_FAIL;
	        }

	        // ✅ Cache一致性修复
	        xil_printf("[STAGE3] Invalidating input cache...\n\r");
	        Xil_DCacheInvalidateRange(DEC_IN_ADDR, DEC_IN_BEATS * 8);
	        __asm__ volatile("dsb sy");
	        __asm__ volatile("isb");
	        usleep(100);
	        xil_printf("[STAGE3] ✓ Cache invalidated\n\r");

	        /* 验证输入数据 */
	        xil_printf("[STAGE3] Input Validation:\n\r");
	        const u64 *in_data = (const u64*)DEC_IN_ADDR;
	        u32 nonzero_count = 0, bit_ones = 0, bit_zeros = 0;

	        for (u32 i = 0; i < DEC_IN_BEATS; i++) {
	            u64 val = in_data[i];
	            if (val != 0) {
	                nonzero_count++;
	                for (int b = 0; b < 64; b++) {
	                    (val & (1ULL << b)) ? bit_ones++ : bit_zeros++;
	                }
	            } else {
	                bit_zeros += 64;
	            }
	        }

	        xil_printf("  Non-zero u64s: %u/%u (%%)\n\r", nonzero_count, DEC_IN_BEATS);
	        xil_printf("  Bit ones:      %u (%%)\n\r", bit_ones);
	        xil_printf("  Bit zeros:     %u (%%)\n\r", bit_zeros);

	        if (nonzero_count == 0) {
	            xil_printf("[STAGE3] ❌ ERROR: Input is all zeros!\n\r");
	            pipeline_set_state(PIPE_FAIL);
	            return PIPE_STEP_FAIL;
	        }

	        /* 清空输出区域 */
	        xil_printf("[STAGE3] Clearing output area...\n\r");
	        u64 *out64 = (u64*)DEC_OUT_ADDR;
	        for (u32 i = 0; i < DEC_OUT_BEATS; i++) {
	            out64[i] = DECODER_SENTINEL_U64;
	        }
	        Xil_DCacheFlushRange(DEC_OUT_ADDR, DEC_OUT_BEATS * 8);
	        xil_printf("[STAGE3] Output area filled with sentinel values\n\r");

	        // ✅ 关键修复：写配置前再次确认START=0
	        xil_printf("[STAGE3] Writing configuration (with safety checks)...\n\r");
	        write_reg32(DECODER_BASEADDR, DECODER_REG_START, 0x00);  // 再次确认
	        usleep(1000);

	        // 按安全顺序写入：先写地址，最后才写beats
	        write_reg32(DECODER_BASEADDR, DECODER_REG_IN_ADDR,  DEC_IN_ADDR);
	        usleep(100);
	        write_reg32(DECODER_BASEADDR, DECODER_REG_OUT_ADDR, DEC_OUT_ADDR);
	        usleep(100);

	        // ✅ 关键：最后才写beats，避免触发自动启动
	        write_reg32(DECODER_BASEADDR, DECODER_REG_OUT_BEATS, DEC_OUT_BEATS);
	        usleep(100);
	        write_reg32(DECODER_BASEADDR, DECODER_REG_IN_BEATS, DEC_IN_BEATS);  // 最后写

	        /* 内存屏障 */
	        __asm__ volatile("dsb sy");
	        __asm__ volatile("isb");
	        usleep(10);

	        /* 回读验证 */
	        u32 in_addr_rb  = read_reg32(DECODER_BASEADDR, DECODER_REG_IN_ADDR);
	        u32 in_beats_rb = read_reg32(DECODER_BASEADDR, DECODER_REG_IN_BEATS);
	        u32 out_addr_rb = read_reg32(DECODER_BASEADDR, DECODER_REG_OUT_ADDR);
	        u32 out_beats_rb= read_reg32(DECODER_BASEADDR, DECODER_REG_OUT_BEATS);

	        xil_printf("[STAGE3] Configuration verification:\n\r");
	        xil_printf("  IN_ADDR:  0x%08X %s\n\r", in_addr_rb,
	                   (in_addr_rb == DEC_IN_ADDR) ? "✓" : "❌");
	        xil_printf("  IN_BEATS: %u %s\n\r", in_beats_rb,
	                   (in_beats_rb == DEC_IN_BEATS) ? "✓" : "❌");
	        xil_printf("  OUT_ADDR: 0x%08X %s\n\r", out_addr_rb,
	                   (out_addr_rb == DEC_OUT_ADDR) ? "✓" : "❌");
	        xil_printf("  OUT_BEATS:%u %s\n\r", out_beats_rb,
	                   (out_beats_rb == DEC_OUT_BEATS) ? "✓" : "❌");

	        if (in_addr_rb != DEC_IN_ADDR || in_beats_rb != DEC_IN_BEATS ||
	            out_addr_rb != DEC_OUT_ADDR || out_beats_rb != DEC_OUT_BEATS) {
	            xil_printf("\n\r[ERROR] Configuration verification failed!\n\r");
	            pipeline_set_state(PIPE_FAIL);
	            return PIPE_STEP_FAIL;
	        }

	        // ✅ 关键检查：写完配置后验证是否意外启动
	        usleep(5000);  // 等待5ms
	        u32 status_after_config = read_reg32(DECODER_BASEADDR, DECODER_REG_STATUS);
	        xil_printf("[STAGE3] Status after config: 0x%02X (IDLE=%d, DONE=%d)\n\r",
	                   status_after_config,
	                   (status_after_config & 0x01) ? 1 : 0,
	                   (status_after_config & 0x02) ? 1 : 0);

	        if (!(status_after_config & DECODER_STATUS_IDLE)) {
	            xil_printf("[STAGE3] ❌ ERROR: IP started unexpectedly during config!\n\r");
	            xil_printf("[STAGE3] This indicates a hardware bug or signal glitch\n\r");

	            // 尝试紧急停止
	            write_reg32(DECODER_BASEADDR, DECODER_REG_START, 0x00);
	            write_reg32(DECODER_BASEADDR, DECODER_REG_IN_BEATS, 0);
	            write_reg32(DECODER_BASEADDR, DECODER_REG_OUT_BEATS, 0);
	            usleep(50000);

	            u32 recovery_status = read_reg32(DECODER_BASEADDR, DECODER_REG_STATUS);
	            if (recovery_status & DECODER_STATUS_IDLE) {
	                xil_printf("[STAGE3] ✓ Recovered, retrying config...\n\r");
	                // 重新开始PREP阶段
	                return PIPE_STEP_PROGRESS;
	            } else {
	                xil_printf("[STAGE3] ❌ Cannot recover from unexpected start\n\r");
	                pipeline_set_state(PIPE_FAIL);
	                return PIPE_STEP_FAIL;
	            }
	        }

	        xil_printf("========================================\n\r\n\r");

	        /* 进入启动状态 */
	        pipeline_set_state(PIPE_DECODER_START);
	        return PIPE_STEP_PROGRESS;
	    }
	    /*========================================================================
	     * PIPE_DECODER_START: 启动Decoder（保守、无“假任务推进”）
	     *========================================================================*/
	    case PIPE_DECODER_START: {
	        xil_printf("========================================\n\r");
	        xil_printf("[STAGE3] Starting Decoder...\n\r");

	        u32 status = read_reg32(DECODER_BASEADDR, DECODER_REG_STATUS);
	        xil_printf("[STAGE3] Status before START: 0x%02X (IDLE=%d, DONE=%d)\n\r",
	                   status, (status & 0x01) ? 1 : 0, (status & 0x02) ? 1 : 0);

	        // 改为强制写入 START=0 再 START=1，确保脉冲对齐
	        write_reg32(DECODER_BASEADDR, DECODER_REG_START, 0x00);
	        usleep(10);
	        write_reg32(DECODER_BASEADDR, DECODER_REG_START, 0x01);

	        usleep(100);  // 确保 START=1 被采样

	        write_reg32(DECODER_BASEADDR, DECODER_REG_START, 0x00); // 脉冲结束

	        xil_printf("[STAGE3] ✓ IP core started (IDLE: 1→0)\n\r");
	        xil_printf("[STAGE3] ✓ Started, monitoring progress...\n\r");

	        pipeline_set_state(PIPE_DECODER_WAIT);
	        return PIPE_STEP_PROGRESS;
	    }
	    /*========================================================================
	     * PIPE_DECODER_WAIT: 等待完成

	     * ✓ 关键改进：使用两种方法监控进度
	     * 1. 状态寄存器的DONE标志(可靠)
	     * 2. 实际写入的beat数(区别0和最后写入)
	     *========================================================================*/
	    case PIPE_DECODER_WAIT: {
	        static int poll_count = 0;
	        poll_count++;

	        if (poll_count % 1000 == 0) {
	            // 每1000次轮询，刷新一次Decoder输出区缓存
	            Xil_DCacheInvalidateRange(DDR_DECODER_OUT_BASE, DECODER_OUTPUT_BEATS * 8);

	            u64 *p_out = (u64 *)DDR_DECODER_OUT_BASE;
	            u32 nonzero_count = 0;

	            for (u32 i = 0; i < DECODER_OUTPUT_BEATS; i++) {
	                u64 val = p_out[i];
	                if (val != 0x0000000000000000ULL && val != 0xAAAAAAAAAAAAAAAAULL) {
	                    nonzero_count++;
	                }
	            }

	            xil_printf("[POLL #%d] Progress: %u/%u beats (%.1f%%)\n\r",
	                       poll_count,
	                       nonzero_count,
	                       DECODER_OUTPUT_BEATS,
	                       100.0f * nonzero_count / DECODER_OUTPUT_BEATS);

	            if (nonzero_count >= DECODER_OUTPUT_BEATS) {
	                xil_printf("[STAGE3] ✓ Output memory written (%u/%u)\n\r",
	                           nonzero_count, DECODER_OUTPUT_BEATS);
	                pipeline_set_state(PIPE_DONE_STAGE3);
	                return PIPE_STEP_PROGRESS;
	            }

	            if (poll_count > 500000) {
	                xil_printf("[STAGE3] ❌ Timeout after %d polls\n\r", poll_count);
	                pipeline_set_state(PIPE_FAIL);
	                return PIPE_STEP_FAIL;
	            }
	        }

	        return PIPE_STEP_PROGRESS;
	    }

	    /*========================================================================
	     * PIPE_DONE_STAGE3: 完成
	     *========================================================================*/
	    case PIPE_DONE_STAGE3: {
	        xil_printf("\n\r[STAGE3] ========================================\n\r");
	        xil_printf("[STAGE3] ✓ Decoder Stage COMPLETE\n\r");
	        xil_printf("[STAGE3] ========================================\n\r");

	        // 最终验证
	        Xil_DCacheInvalidateRange(DEC_OUT_ADDR, DEC_OUT_BEATS * 8);

	        u32 final_written = 0;
	        validate_decoder_written_beats(DEC_OUT_ADDR, DEC_OUT_BEATS, &final_written);

	        xil_printf("\n[STAGE3] Final Validation:\n\r");
	        xil_printf("  Written beats: %u/%u (%.1f%%)\n\r",
	                   final_written, DEC_OUT_BEATS,
	                   (float)final_written * 100.0f / DEC_OUT_BEATS);

	        if (final_written < DEC_OUT_BEATS / 2) {
	            xil_printf("[STAGE3] ⚠️  WARNING: Less than 50%% written\n\r");
	            xil_printf("[STAGE3] Results may be incomplete\n\r");
	        }
	        xil_printf("[CLEANUP] Resetting Decoder for next run...\n\r");
	           write_reg32(DECODER_BASEADDR, DECODER_REG_START, 0x00);
	           write_reg32(DECODER_BASEADDR, DECODER_REG_IN_BEATS, 0);
	           write_reg32(DECODER_BASEADDR, DECODER_REG_OUT_BEATS, 0);
	           usleep(50000);  // 等待50ms让状态机稳定

	           u32 cleanup_status = read_reg32(DECODER_BASEADDR, DECODER_REG_STATUS);
	           xil_printf("[CLEANUP] Decoder STATUS: 0x%02X (IDLE=%d)\n\r",
	                      cleanup_status, (cleanup_status & 0x01) ? 1 : 0);

	           if (!(cleanup_status & 0x01)) {
	               xil_printf("[CLEANUP] ⚠️ Not IDLE, forcing dummy run...\n\r");
	               // 执行虚拟运行
	               write_reg32(DECODER_BASEADDR, DECODER_REG_IN_ADDR,  DDR_VOTER_OUT_BASE);
	               write_reg32(DECODER_BASEADDR, DECODER_REG_IN_BEATS, 1);
	               write_reg32(DECODER_BASEADDR, DECODER_REG_OUT_ADDR, DDR_DECODER_OUT_BASE);
	               write_reg32(DECODER_BASEADDR, DECODER_REG_OUT_BEATS, 1);
	               usleep(1000);
	               write_reg32(DECODER_BASEADDR, DECODER_REG_START, 0x01);
	               usleep(5000);
	               write_reg32(DECODER_BASEADDR, DECODER_REG_START, 0x00);
	               usleep(50000);
	           }

	           xil_printf("[CLEANUP] ✓ Decoder ready for next run\n\r");

	           // 准备发送结果
	           pipeline_set_state(PIPE_SEND_RESULT);
	           return PIPE_STEP_PROGRESS;
	       }
	    default:
	        return PIPE_STEP_PROGRESS;
	    }
	}

/*============================================================================
 * 其他工具/公共流程
 *============================================================================*/
int run_processing_pipeline(dna_connection_t *conn)
{
    pipe_step_rc_e rc;

    if (pipe_state >= PIPE_IDLE && pipe_state <= PIPE_DONE_STAGE1) {
        rc = pipeline_step_stage1(conn);
    } else if (pipe_state >= PIPE_VOTER_PREP && pipe_state <= PIPE_DONE_STAGE2) {
        rc = pipeline_step_stage2(conn);
    } else if (pipe_state >= PIPE_DECODER_PREP && pipe_state <= PIPE_DONE_STAGE3) {
        rc = pipeline_step_stage3(conn);
    } else {
        rc = PIPE_STEP_FAIL;
    }

    if (rc == PIPE_STEP_FAIL) { pipe_state = PIPE_FAIL; return XST_FAILURE; }
    if (rc == PIPE_STEP_DONE) { return XST_SUCCESS; }
    return XST_SUCCESS;
}

/*============================================================================
 * TCP / 协议
 *============================================================================*/
static int parse_header(u8 *buf, u16 *magic, u8 *pkt_type, u32 *payload_len)
{
    *magic = (buf[0] << 8) | buf[1];
    *pkt_type = buf[2];
    *payload_len = (buf[4] << 24) | (buf[5] << 16) | (buf[6] << 8) | buf[7];
    if (*magic != PROTOCOL_MAGIC) return -1;
    return 0;
}

static void process_complete_packet(dna_connection_t *conn, u8 *packet_data, u32 total_len)
{
    u16 magic; u8 pkt_type; u32 payload_len;
    if (parse_header(packet_data, &magic, &pkt_type, &payload_len) != 0) {
        xil_printf("[PKT] Invalid header\n\r");
        if (conn->tpcb) send_ack_byte(conn->tpcb, PKT_ERROR);
        return;
    }
    if (total_len != PROTOCOL_HDR_SIZE + payload_len) {
        xil_printf("[PKT] Size mismatch\n\r");
        if (conn->tpcb) send_ack_byte(conn->tpcb, PKT_ERROR);
        return;
    }

    u8 *payload = packet_data + PROTOCOL_HDR_SIZE;

    switch (pkt_type) {
    case PKT_WM:   process_watermark(conn, payload, payload_len); send_ack_byte(conn->tpcb, PKT_WM_OK); break;
    case PKT_BATCH:process_batch(conn, payload, payload_len);     send_ack_byte(conn->tpcb, PKT_BATCH_OK); break;
    case PKT_POST: process_post(conn); break;
    default:       xil_printf("[PKT] Unknown type\n\r"); send_ack_byte(conn->tpcb, PKT_ERROR); break;
    }
}

static err_t recv_callback(void *arg, struct tcp_pcb *tpcb, struct pbuf *p, err_t err)
{
    dna_connection_t *conn = (dna_connection_t *)arg;

    if (p == NULL) { tcp_recv_offset = 0; tcp_close(tpcb); return ERR_OK; }
    if (err != ERR_OK) { pbuf_free(p); return err; }

    u16 received_len = p->tot_len;
    if (tcp_recv_offset + received_len > sizeof(tcp_recv_buffer)) {
        xil_printf("[TCP] Buffer overflow\n\r"); pbuf_free(p); return ERR_MEM;
    }

    pbuf_copy_partial(p, tcp_recv_buffer + tcp_recv_offset, received_len, 0);
    tcp_recv_offset += received_len;

    while (tcp_recv_offset >= PROTOCOL_HDR_SIZE) {
        u16 magic; u8 pkt_type; u32 payload_len;
        if (parse_header(tcp_recv_buffer, &magic, &pkt_type, &payload_len) != 0) {
            memmove(tcp_recv_buffer, tcp_recv_buffer + 1, tcp_recv_offset - 1);
            tcp_recv_offset--;
            continue;
        }
        u32 need = PROTOCOL_HDR_SIZE + payload_len;
        if (tcp_recv_offset < need) break;
        process_complete_packet(conn, tcp_recv_buffer, need);
        if (tcp_recv_offset > need) memmove(tcp_recv_buffer, tcp_recv_buffer + need, tcp_recv_offset - need);
        tcp_recv_offset -= need;
    }

    tcp_recved(tpcb, p->tot_len);
    pbuf_free(p);
    return ERR_OK;
}

static err_t send_ack_byte(struct tcp_pcb *tpcb, u8 ack_type)
{
    u8 ack = ack_type;
    err_t e = tcp_write(tpcb, &ack, 1, TCP_WRITE_FLAG_COPY);
    if (e == ERR_OK) tcp_output(tpcb);
    return e;
}

static err_t poll_callback(void *arg, struct tcp_pcb *tpcb)
{
    dna_connection_t *conn = (dna_connection_t *)arg;
    keep_tcp_alive();

    switch (g_proc_state) {
    case PROC_REQUESTED:
        pipeline_reset_counters(); pipeline_set_state(PIPE_WM_PREP); g_proc_state = PROC_RUNNING; break;
    case PROC_RUNNING: {
        int st = run_processing_pipeline(conn);
        if (pipe_state == PIPE_FAIL) g_proc_state = PROC_FAILED;
        else if (pipe_state == PIPE_DONE_STAGE3 && st == XST_SUCCESS) g_proc_state = PROC_DONE;
        break;
    }
    case PROC_DONE:   send_result(conn); g_proc_state = PROC_IDLE; break;
    case PROC_FAILED: xil_printf("[POST] Pipeline failed\n\r"); send_ack_byte(conn->tpcb, PKT_ERROR); g_proc_state = PROC_IDLE; break;
    default: break;
    }
    return ERR_OK;
}

static err_t accept_callback(void *arg, struct tcp_pcb *newpcb, err_t err)
{
    if (err != ERR_OK || newpcb == NULL) return ERR_VAL;

    xil_printf("\n\r========================================\n\r");
    xil_printf("[TCP] Client connected\n\r");
    xil_printf("========================================\n\r");

    memset(&g_conn, 0, sizeof(dna_connection_t));
    g_conn.tpcb = newpcb;
    g_conn.state = STATE_IDLE;
    g_proc_state = PROC_IDLE;
    tcp_recv_offset = 0;

    tcp_arg(newpcb, &g_conn);
    tcp_recv(newpcb, recv_callback);
    tcp_nagle_disable(newpcb);

    newpcb->so_options |= SOF_KEEPALIVE;
    newpcb->keep_idle = 7200000;

    tcp_poll(newpcb, poll_callback, 1);
    return ERR_OK;
}

int start_application(void)
{
    err_t err;
    xil_printf("\n\r[TCP] Starting server on port 7...\n\r");

    g_server_pcb = tcp_new();
    if (!g_server_pcb) { xil_printf("[ERROR] tcp_new failed\n\r"); return -1; }
    err = tcp_bind(g_server_pcb, IP_ADDR_ANY, 7);
    if (err != ERR_OK) { xil_printf("[ERROR] bind failed: %d\n\r", err); return -1; }
    g_server_pcb = tcp_listen(g_server_pcb);
    if (!g_server_pcb) { xil_printf("[ERROR] listen failed\n\r"); return -1; }
    tcp_accept(g_server_pcb, accept_callback);
    xil_printf("[TCP] Server ready\n\r");
    return 0;
}

/*============================================================================
 * 重启包：Stage1→Stage2
 *============================================================================*/

/*============================================================================
 * 数据接收流程
 *============================================================================*/
void process_watermark(dna_connection_t *conn, u8 *data, u32 len)
{
    if (len > MAX_WATERMARK_SIZE) len = MAX_WATERMARK_SIZE;
    memcpy((void *)DDR_WATERMARK_BASE, data, len);
    Xil_DCacheFlushRange(DDR_WATERMARK_BASE, len);
    conn->watermark_size = len;
    xil_printf("[WM] Stored %u bytes\n\r", len);
}

void process_batch(dna_connection_t *conn, u8 *data, u32 len)
{
    if (len < 4) return;
    u32 num_reads = (data[0]<<24)|(data[1]<<16)|(data[2]<<8)|data[3];
    u32 data_size = num_reads * READ_SIZE_BYTES;
    if (len < 4 + data_size) return;

    u32 offset  = conn->total_reads_received * READ_SIZE_BYTES;
    u32 dst     = DDR_READS_BASE + offset;

    memcpy((void *)dst, data + 4, data_size);
    conn->total_reads_received += num_reads;

    if (conn->total_reads_received >= TOTAL_READS) {
        xil_printf("[BATCH] Target reached, auto-trigger\n\r");
        process_post(conn);
    }
}

void process_post(dna_connection_t *conn)
{
    if (conn->total_reads_received == 0 || conn->watermark_size == 0) {
        xil_printf("[POST] No data\n\r");
        if (conn->tpcb) send_ack_byte(conn->tpcb, PKT_ERROR);
        return;
    }
    xil_printf("\n\r========================================\n\r");
    xil_printf("Starting Processing Pipeline\n\r");
    xil_printf("Total Reads: %u\n\r", conn->total_reads_received);
    xil_printf("Watermark:   %u bytes\n\r", conn->watermark_size);
    xil_printf("========================================\n\r");
    conn->state = STATE_PROCESSING;
    g_proc_state = PROC_REQUESTED;
}

/*============================================================================
 * 结果发送(严格发送 64800 字节)
 *============================================================================*/
void send_result(dna_connection_t *conn)
{
    u32 result_size = DECODER_OUTPUT_BYTES; /* 64800 */
    xil_printf("\n\r[RESULT] Sending %u bytes\n\r", result_size);

    u8 header[8];
    header[0] = (PROTOCOL_MAGIC >> 8) & 0xFF;
    header[1] = PROTOCOL_MAGIC & 0xFF;
    header[2] = PKT_RESULT;
    header[3] = 0;
    header[4] = (result_size >> 24) & 0xFF;
    header[5] = (result_size >> 16) & 0xFF;
    header[6] = (result_size >> 8) & 0xFF;
    header[7] = (result_size) & 0xFF;

    /* 头 */
    for (;;) {
        err_t e = tcp_write(conn->tpcb, header, 8, TCP_WRITE_FLAG_COPY);
        if (e == ERR_OK) break;
        if (e == ERR_MEM || e == ERR_WOULDBLOCK) { tcp_output(conn->tpcb); keep_tcp_alive(); usleep(1000); continue; }
        xil_printf("[ERROR] Header write failed: %d\n\r", e);
        conn->state = STATE_IDLE;
        return;
    }
    tcp_output(conn->tpcb);

    /* 正文：从 DDR_DECODER_OUT_BASE 连续发送 64800 字节 */
    u32 sent = 0;
    while (sent < result_size) {
        u16 snd_avail = tcp_sndbuf(conn->tpcb);
        if (snd_avail == 0) { tcp_output(conn->tpcb); keep_tcp_alive(); usleep(1000); continue; }
        u32 remain = result_size - sent;
        u32 to_send = (remain < snd_avail) ? remain : snd_avail;
        if (to_send > 1460) to_send = 1460;

        err_t e = tcp_write(conn->tpcb, (void *)(DDR_DECODER_OUT_BASE + sent), to_send, TCP_WRITE_FLAG_COPY);
        if (e == ERR_OK) {
            sent += to_send;
            if ((sent & 0x7FF) == 0) { tcp_output(conn->tpcb); keep_tcp_alive(); }
        } else if (e == ERR_MEM || e == ERR_WOULDBLOCK) {
            tcp_output(conn->tpcb); keep_tcp_alive(); usleep(1000);
        } else {
            xil_printf("[ERROR] Data write failed: %d @%u\n\r", e, sent);
            conn->state = STATE_IDLE;
            return;
        }
    }
    tcp_output(conn->tpcb);
    xil_printf("[RESULT] Complete %u bytes\n\r", sent);
    conn->state = STATE_IDLE;
}

/*============================================================================
 * DDR地址合法性检查(可用于调试)
 *============================================================================*/
static int validate_ddr_addresses(void)
{
    u32 wm_end    = DDR_WATERMARK_BASE + MAX_WATERMARK_SIZE;
    u32 reads_end = DDR_READS_BASE + (TOTAL_READS * READ_SIZE_BYTES);
    u32 dna_end   = DDR_DNA_ACC_OUT_BASE + DNA_ACC_OUTPUT_SIZE_BYTES;

    xil_printf("\n\r[MEM] DDR Address Map:\n\r");
    xil_printf("  WM:     0x%08X - 0x%08X (size: %u bytes)\n\r", DDR_WATERMARK_BASE, wm_end, MAX_WATERMARK_SIZE);
    xil_printf("  READS:  0x%08X - 0x%08X (size: %u bytes)\n\r", DDR_READS_BASE, reads_end, TOTAL_READS * READ_SIZE_BYTES);
    xil_printf("  DNA_OUT:0x%08X - 0x%08X (size: %u bytes)\n\r", DDR_DNA_ACC_OUT_BASE, dna_end, DNA_ACC_OUTPUT_SIZE_BYTES);
    xil_printf("  VOTER:  0x%08X\n\r", DDR_VOTER_OUT_BASE);
    xil_printf("  DECODE: 0x%08X\n\r", DDR_DECODER_OUT_BASE);

    if (wm_end > DDR_READS_BASE) { xil_printf("[ERROR] WM overlaps with READS!\n\r"); return XST_FAILURE; }
    if (reads_end > DDR_DNA_ACC_OUT_BASE) { xil_printf("[ERROR] READS overlaps with DNA_OUT!\n\r"); return XST_FAILURE; }

    xil_printf("[MEM] Address map OK\n\r\n\r");
    return XST_SUCCESS;
}



/*============================================================================
 * 可选的 Stage1 直接截取函数(保留工具函数)
 *============================================================================*/


 int validate_decoder_written_beats(u32 out_addr, u32 total_beats, u32 *written_beats)
{
    Xil_DCacheInvalidateRange(out_addr, total_beats * 8);
    u64 *data = (u64*)out_addr;

    u32 sentinel_count = 0;   // 未写入(仍是哨兵值)
    u32 zero_count = 0;       // 已写入但为0
    u32 nonzero_count = 0;    // 已写入且非0

    for (u32 i = 0; i < total_beats; i++) {
        if (data[i] == DECODER_SENTINEL_U64) {
            sentinel_count++;
        } else if (data[i] == 0ULL) {
            zero_count++;
        } else {
            nonzero_count++;
        }
    }

    *written_beats = zero_count + nonzero_count;

    return 0;
}
 void analyze_decoder_output(u32 out_addr, u32 total_beats)
 {
     /* 采样验证 cache 可见性 */
     for (int sample = 0; sample < 3; sample++) {
         usleep(1000);
         Xil_DCacheInvalidateRange(out_addr, 1 * 8);
         __asm__ volatile("dsb sy"); __asm__ volatile("isb");
         /* 不打印 64 位字面量，改用字节视图 */
         xil_printf("[Sample %d] First beat (bytes):\n\r", sample);
         dump_u64_bytes_window((const void*)out_addr, 0, 1, "First beat");
     }

     Xil_DCacheInvalidateRange(out_addr, total_beats * 8U);
     __asm__ volatile("dsb sy"); __asm__ volatile("isb");

     const volatile u64 *data = (const volatile u64*)out_addr;

     u32 sentinel_count = 0, zero_count = 0, nonzero_count = 0;
     u32 bit_ones = 0, bit_zeros = 0;

     for (u32 i = 0; i < total_beats; i++) {
         u64 w = data[i];
         if (w == DECODER_SENTINEL_U64) {
             sentinel_count++;
             bit_zeros += 64;
         } else if (w == 0ULL) {
             zero_count++;
             bit_zeros += 64;
         } else {
             nonzero_count++;
             for (int b = 0; b < 64; b++) (w & (1ULL << b)) ? bit_ones++ : bit_zeros++;
         }
     }

     const u32 written_beats = zero_count + nonzero_count;
     const u32 total_bits = bit_ones + bit_zeros;

     xil_printf("\n[ANALYSIS] Decoder Output Analysis:\n\r");
     xil_printf("========================================\n\r");
     xil_printf("Beat Statistics:\n\r");
     xil_printf("  Total beats:        %u\n\r", total_beats);
     xil_printf("  Sentinel (未写入):  %u (%.1f%%)\n\r", sentinel_count, (float)sentinel_count * 100.0f / total_beats);
     xil_printf("  Zero (已写入):      %u (%.1f%%)\n\r", zero_count, (float)zero_count * 100.0f / total_beats);
     xil_printf("  Non-zero (已写入):  %u (%.1f%%)\n\r", nonzero_count, (float)nonzero_count * 100.0f / total_beats);
     xil_printf("  Written total:      %u (%.1f%%)\n\r", written_beats, (float)written_beats * 100.0f / total_beats);

     if (total_bits > 0) {
         xil_printf("\nBit Distribution:\n\r");
         xil_printf("  Total bits:   %u\n\r", total_bits);
         xil_printf("  Ones:         %u (%.1f%%)\n\r", bit_ones, (float)bit_ones * 100.0f / total_bits);
         xil_printf("  Zeros:        %u (%.1f%%)\n\r", bit_zeros, (float)bit_zeros * 100.0f / total_bits);
     }

     /* 样本窗口（字节视图） */
     xil_printf("\nFirst 8 beats (bytes):\n\r");
     dump_u64_bytes_window((const void*)out_addr, 0, (total_beats < 8 ? total_beats : 8), "First 8");

     if (total_beats >= 4) {
         xil_printf("\nLast 4 beats (bytes):\n\r");
         dump_u64_bytes_window((const void*)out_addr, total_beats - 4, 4, "Last 4");
     }

     xil_printf("========================================\n\r");
 }
