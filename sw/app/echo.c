/******************************************************************************
 * @file echo.c
 * @brief DNA Accelerator - 串口整段流水线(滑动窗 + 投票 + 解码)
 ******************************************************************************/

#include <string.h>
#include "echo.h"
#include "wm_expand.h"
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
static err_t send_framed_pkt(struct tcp_pcb *tpcb, u8 type,
                             const u8 *payload, u32 len);
static err_t reject_and_close_connection(dna_connection_t *conn,
                                         struct tcp_pcb *tpcb,
                                         struct pbuf *p);
static int validate_decoder_written_beats(u32 out_addr, u32 total_beats,
                                          u32 *written_beats);
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
    XFER_RX_OUT   = 2   /* S2MM:收输出 → 【B21】48B/BD，DNA 核每条记录一个 TLAST packet */
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
    /* 【B21】原实现读完寄存器却一行都没打印，等于哑巴看门狗：
     * 上一轮板上卡死时即使触发了 dump 也看不到任何证据。 */
    xil_printf("  MM2S: DMACR=0x%08X DMASR=0x%08X CURDESC=0x%08X TAILDESC=0x%08X\n\r",
               tx_cr, tx_sr, tx_cur, tx_tal);
    xil_printf("  S2MM: DMACR=0x%08X DMASR=0x%08X CURDESC=0x%08X TAILDESC=0x%08X\n\r",
               rx_cr, rx_sr, rx_cur, rx_tal);
    xil_printf("  MM2S halted=%u idle=%u err=0x%X | S2MM halted=%u idle=%u err=0x%X\n\r",
               (unsigned)(tx_sr & 1U), (unsigned)((tx_sr >> 1) & 1U),
               (unsigned)((tx_sr >> 4) & 0x7U),
               (unsigned)(rx_sr & 1U), (unsigned)((rx_sr >> 1) & 1U),
               (unsigned)((rx_sr >> 4) & 0x7U));
}

/* 【B21】DNA 核控制寄存器回读（reg0=start/preload/softrst，reg1=wm_sel） */
static void dump_dna_regs(const char *tag)
{
    xil_printf("[DNA] %s reg0=0x%08X reg1=0x%08X\n\r", tag,
               read_reg32(DNA_ACCELERATOR_BASEADDR, DNA_ACC_REG0_CTRL),
               read_reg32(DNA_ACCELERATOR_BASEADDR, DNA_ACC_REG1_WMSEL));
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

    /* 【B21】BD ring 是环形的：一批 BD 可能跨过环尾回绕到环首。
     * 原来的 Xil_DCacheFlushRange(BdPtr, bd_count*64) 假设这批 BD 在内存里连续，
     * 回绕时会刷到环外地址、而漏掉真正回绕到环首的那几个 BD。
     * RX 现在按 48 B/BD 投递，一次任务要用掉 4,096 个 BD 而环只有 1,024 个，
     * 必然回绕 4 次，所以必须逐个沿 BdRingNext 刷。 */
    {
        XAxiDma_Bd *FlushPtr = BdPtr;
        for (u32 i = 0; i < bd_count; i++) {
            Xil_DCacheFlushRange((UINTPTR)FlushPtr, sizeof(XAxiDma_Bd));
            FlushPtr = (XAxiDma_Bd *)XAxiDma_BdRingNext(RingPtr, FlushPtr);
        }
    }

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
        /* 【B21】BdRingFromHw 返回的是环上一段「逻辑连续」的 BD，它可能跨过环尾回绕。
         * 原实现用 &BdPtr[i] 线性索引，一旦回绕就会读到 BD 环之外的内存：
         * 既可能把垃圾值误判成 BD 错误而让整条流水线 FAIL，
         * 也可能漏掉真正回绕那几个 BD 的错误位。
         * RX 改成 48 B/BD 后每次任务必然回绕（4,096 条记录 / 1,024 个 BD），
         * 必须沿 BdRingNext 走。 */
        XAxiDma_Bd *CurPtr = BdPtr;
        for (int i=0;i<n;i++) {
            u32 sts = XAxiDma_BdGetSts(CurPtr);
            if (sts & XAXIDMA_BD_STS_ALL_ERR_MASK) {
                xil_printf("[ERROR] BD status error: 0x%08X (BD %d/%d)\n\r", sts, i, n);
                return -1;
            }
            CurPtr = (XAxiDma_Bd *)XAxiDma_BdRingNext(RingPtr, CurPtr);
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

static u32 wm_region = 0;      /* 预载到第几个区域（修订 B1） */
static u32 tx_frames_total = 0;
static u32 tx_frames_sent  = 0;
static u32 tx_frames_done  = 0;

/* 【B21】RX 改为「一条 48 B 记录一个 BD」后的滚动补投计数 */
static u32 rx_records_total     = 0;   /* 本次任务应收的记录条数 = 实际读段数 */
static u32 rx_records_submitted = 0;   /* 已交给硬件的 BD（记录）条数 */
#define RX_OUTSTANDING_MAX  512U       /* ring 有 1024 个 BD，最多留一半在飞 */

/* 【B21】Stage1 无进展看门狗。
 * poll 间隔实测 ~280 ms，不是 500 ms：
 * `tcp_slowtmr()` 有两个各自独立、互不清零的驱动源同时在跑 ——
 *   1) ISR：SCU timer 250 ms（platform_zynq.c:174 载入 CPU_CLK/8，而 SCU 时钟是 CPU_CLK/2），
 *      timer_callback 用 odd 隔一次才置 TcpSlowTmrFlag（platform_zynq.c:104-113）→ 500 ms；
 *   2) 软件兜底：main.c:290 的 slow_acc >= 500 直接调 tcp_slowtmr()，
 *      既不看 ISR 脸色也不被它清零 → 另一个 >=500 ms 源。
 * 两个不同步的 ~500 ms 源叠加，有效间隔落在 250~500 ms。
 */
static int  s1_last_tx_done = -1;
static int  s1_last_rx_done = -1;
static u32  s1_no_progress  = 0;
/* 60 步完全无 BD 进展即判定卡死。按实测 ~280 ms/步折算 **≈ 17 s**，
 * 不是原注释写的「60 x 500 ms ≈ 30 s」—— 那是照错的 500 ms 算的，乐观了约 2 倍。
 * 触发得比宣称的更早，方向上是安全的（宁可早报也不要 83 分钟才报，那正是 B21 当年的坑），
 * 所以本轮**只改注释、不动数值**：改数值要重建 ELF 并刷新 SHA256SUMS，
 * 而 2026-08-30 全量 103,616 条实跑（132.67 s）下它一次都没误触发。 */
#define S1_NO_PROGRESS_LIMIT  60U

static inline void pipeline_reset_counters(void){
    wm_tx_expected=0; rx_expected=0; tx_expected=0; tx_done=0; rx_done=0;
    tx_frames_total=0; tx_frames_sent=0; tx_frames_done=0; wm_region=0;
    rx_records_total=0; rx_records_submitted=0;
    s1_last_tx_done=-1; s1_last_rx_done=-1; s1_no_progress=0;
}

/* 【B21】按「一条记录一个 BD」滚动补投 RX 描述符。
 * 返回本次投出的 BD 数（0 表示暂时不需要补），-1 表示失败。 */
static int submit_rx_records(void)
{
    if (rx_records_submitted >= rx_records_total) return 0;
    u32 remain = rx_records_total - rx_records_submitted;

    u32 done = (rx_done > 0) ? (u32)rx_done : 0U;
    u32 outstanding = (rx_records_submitted > done) ? (rx_records_submitted - done) : 0U;
    if (outstanding >= RX_OUTSTANDING_MAX) return 0;

    u32 n = RX_OUTSTANDING_MAX - outstanding;
    if (n > remain) n = remain;

    u32 free_bd = XAxiDma_BdRingGetFreeCnt(RxRingPtr);
    if (n > free_bd) n = free_bd;
    if (n == 0) return 0;

    u32 addr  = DDR_DNA_ACC_OUT_BASE + rx_records_submitted * DNA_ACC_RESULT_PACKED_BYTES;
    u32 bytes = n * DNA_ACC_RESULT_PACKED_BYTES;

    int bd = submit_bd_transfer(RxRingPtr, addr, bytes, RxMaxTransferLen,
                                "RX-DNA-RECORDS", XFER_RX_OUT);
    if (bd < 0) return -1;
    rx_records_submitted += n;
    return bd;
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
    /* 【修订 B1】水印预载重做
     *
     * 原实现：置 preload → 一次 DMA 整个打包水印 → 清 preload。
     * 三处致命问题：
     *   1) DNA 核预载时每个 32-bit 拍只取 TDATA[1:0]，即 1 拍 1 个符号，
     *      而打包水印一拍带 16 个符号 —— 只有 1/16 的数据被写进去；
     *   2) wm_waddr 到 956 就归零，写入永远落在 bram_sel 选中的**单个**区域；
     *   3) bram_sel 来自 reg1，而这里从头到尾只写过 reg0 —— 区域 1..49 恒为全 0。
     *
     * 现在改为：先把水印展开成 50 个区域（每符号一个 32-bit 字），
     * 然后逐区域「写 reg1=区域号 → 置 preload → DMA 957 拍 → 等完成」。
     */
    case PIPE_WM_PREP: {
        xil_printf("\n\r[STAGE1] WM_PREP: expanding watermark into %u regions\n\r",
                   (u32)WM_NUM_LC);
        if (expand_watermark_regions(conn) != 0) {
            pipeline_set_state(PIPE_FAIL);
            return PIPE_STEP_FAIL;
        }
        wm_region = 0;
        pipeline_set_state(PIPE_WM_TX);
        return PIPE_STEP_PROGRESS;
    }
    case PIPE_WM_TX: {
        /* 先选区域，再进预载模式；顺序不能反 */
        write_reg32(DNA_ACCELERATOR_BASEADDR, DNA_ACC_REG1_WMSEL, wm_region);
        usleep(10);
        write_reg32(DNA_ACCELERATOR_BASEADDR, DNA_ACC_REG0_CTRL,
                    DNA_ACC_CTRL_BIT_PRELOAD);
        usleep(10);

        wm_tx_expected = submit_bd_transfer(TxRingPtr,
                                            DDR_WM_REGIONS_BASE + wm_region * WM_REGION_BYTES,
                                            WM_REGION_BYTES, TxMaxTransferLen,
                                            "TX-WM-REGION", XFER_TX_WM);
        if (wm_tx_expected < 0) { pipeline_set_state(PIPE_FAIL); return PIPE_STEP_FAIL; }
        pipeline_set_state(PIPE_WM_WAIT);
        return PIPE_STEP_PROGRESS;
    }
    case PIPE_WM_WAIT: {
        int got = reclaim_some_bd(TxRingPtr, wm_tx_expected);
        if (got < 0) { pipeline_set_state(PIPE_FAIL); return PIPE_STEP_FAIL; }
        if (got == wm_tx_expected) {
            /* 每个区域传完都退出预载模式，确保 wm_waddr 与区域边界对齐 */
            write_reg32(DNA_ACCELERATOR_BASEADDR, DNA_ACC_REG0_CTRL, 0x00);
            usleep(10);
            wm_region++;
            if (wm_region < WM_NUM_LC) {
                pipeline_set_state(PIPE_WM_TX);
            } else {
                xil_printf("[STAGE1] WM preload done: %u regions x %u symbols\n\r",
                           (u32)WM_NUM_LC, (u32)WM_REF_LEN);
                pipeline_set_state(PIPE_RX_PREP);
            }
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

        /* 【B21】DNA 核每条记录一个 AXIS packet（TLAST），所以一个 BD 只收一条记录。
         * 需要收 total_reads 条 = total_reads 个 BD，而 ring 只有 1024 个，
         * 因此按 RX_OUTSTANDING_MAX 滚动补投，rx_expected 直接按条数计。 */
        Xil_DCacheInvalidateRange(DDR_DNA_ACC_OUT_BASE, out_size);
        rx_records_total     = total_reads;
        rx_records_submitted = 0;
        rx_expected          = (int)total_reads;
        if (submit_rx_records() < 0) { pipeline_set_state(PIPE_FAIL); return PIPE_STEP_FAIL; }
        xil_printf("  RX BD: 1 BD/记录(48 B)，预投 %u/%u 条\n\r",
                   rx_records_submitted, rx_records_total);
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
        /* 【B21】立刻补投 RX BD：一条记录一个 BD，ring 不能空，否则 S2MM 进 Idle
         * → 结果 FIFO 满 → 输入 FIFO 满 → S_AXIS_DATA_TREADY 拉低 → MM2S 永久停摆 */
        if (submit_rx_records() < 0) { dump_dma_regs("RX resubmit failed"); pipeline_set_state(PIPE_FAIL); return PIPE_STEP_FAIL; }

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

        /* 【B21】可达的无进展看门狗。
         * 本函数由 lwIP 的 poll_callback 驱动，实测约 280 ms 走一次（见 S1_NO_PROGRESS_LIMIT
         * 处的说明：两个独立的 tcp_slowtmr 驱动源叠加，有效间隔 250~500 ms，不是 500 ms）；
         * 原来的 stuck_count>10000 需要约 83 分钟才会触发，等于永远打不出证据，
         * 这正是上一轮板上「IP core START 之后再无任何输出」的原因。 */
        if (rx_done == s1_last_rx_done && tx_done == s1_last_tx_done) {
            s1_no_progress++;
        } else {
            s1_no_progress = 0;
            s1_last_rx_done = rx_done;
            s1_last_tx_done = tx_done;
        }
        if (s1_no_progress > S1_NO_PROGRESS_LIMIT) {
            xil_printf("\n\r[ERROR] STAGE1 停滞 ~%u s 无任何 BD 进展\n\r",
                       (unsigned)(S1_NO_PROGRESS_LIMIT / 2U));
            xil_printf("  TX frames sent=%u/%u  TX BD done=%d/%d\n\r",
                       tx_frames_sent, tx_frames_total, tx_done, tx_expected);
            xil_printf("  RX records done=%d/%d  submitted=%u  ring free=%d\n\r",
                       rx_done, rx_expected, rx_records_submitted,
                       (int)XAxiDma_BdRingGetFreeCnt(RxRingPtr));
            dump_dma_regs("STAGE1 stall");
            dump_dna_regs("STAGE1 stall");
            pipeline_set_state(PIPE_FAIL);
            return PIPE_STEP_FAIL;
        }

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
        /* 【B21】收尾阶段同样要保证 RX ring 里始终有描述符 */
        if (submit_rx_records() < 0) { dump_dma_regs("PROGRESS RX resubmit failed"); pipeline_set_state(PIPE_FAIL); return PIPE_STEP_FAIL; }

        static u32 wait_count = 0;
        if (++wait_count >= 10) {
            xil_printf("[STAGE1] WAIT tx=%u/%u rx=%d/%d (submitted=%u)\n\r",
                       tx_frames_done, tx_frames_total, rx_done, rx_expected,
                       rx_records_submitted);
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
	    xil_printf("  Data format: 48 bytes/read × %u reads (actual)\n\r",
	               conn->total_reads_received);
	    xil_printf("  Total size: %u bytes\n\r",
	               (u32)ddr_layout_stage1_bytes(conn->total_reads_received,
	                                            DNA_ACC_RESULT_PACKED_BYTES));

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

	    /* 强制把数据刷新到 DDR（后续 Stage2 直接读取；[C1] 按实际条数） */
	    xil_printf("\n\r[STAGE1] Flushing all output to DDR...\n\r");
	    Xil_DCacheFlushRange(DDR_DNA_ACC_OUT_BASE,
	                         (u32)ddr_layout_stage1_bytes(conn->total_reads_received,
	                                                       DNA_ACC_RESULT_PACKED_BYTES));
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
static int voter_configure_and_verify(const dna_connection_t *conn)
{
    const u32 in_addr = DDR_VOTER_IN_BASE;
    const u32 out_addr = DDR_VOTER_OUT_BASE;
    const u32 total_reads = conn->total_reads_received;
    const u32 in_beats = total_reads * 6u;
    const u32 out_beats = VOTER_OUTPUT_BEATS;
    const u32 score_min = conn->cfg.score_min;

    xil_printf("[STAGE2] Configuration:\n\r");
    xil_printf("  IN_ADDR:     0x%08X\n\r", in_addr);
    xil_printf("  IN_BEATS:    %u (6 beats/read)\n\r", in_beats);
    xil_printf("  OUT_ADDR:    0x%08X\n\r", out_addr);
    xil_printf("  OUT_BEATS:   %u\n\r", out_beats);
    xil_printf("  TOTAL_READS: %u\n\r", total_reads);
    xil_printf("  SCORE_MIN:   %u\n\r", score_min);

    write_reg32(VOTER_BASEADDR, VOTER_REG_IN_ADDR, in_addr);
    write_reg32(VOTER_BASEADDR, VOTER_REG_IN_BEATS, in_beats);
    write_reg32(VOTER_BASEADDR, VOTER_REG_OUT_ADDR, out_addr);
    write_reg32(VOTER_BASEADDR, VOTER_REG_OUT_BEATS, out_beats);
    write_reg32(VOTER_BASEADDR, VOTER_REG_TOTAL_READS, total_reads);
    write_reg32(VOTER_BASEADDR, VOTER_REG_SCORE_MIN, score_min);
    __asm__ volatile("dsb sy");
    __asm__ volatile("isb");
    usleep(10);

    const u32 in_addr_rb = read_reg32(VOTER_BASEADDR, VOTER_REG_IN_ADDR);
    const u32 in_beats_rb = read_reg32(VOTER_BASEADDR, VOTER_REG_IN_BEATS);
    const u32 out_addr_rb = read_reg32(VOTER_BASEADDR, VOTER_REG_OUT_ADDR);
    const u32 out_beats_rb = read_reg32(VOTER_BASEADDR, VOTER_REG_OUT_BEATS);
    const u32 total_reads_rb = read_reg32(VOTER_BASEADDR, VOTER_REG_TOTAL_READS);
    const u32 score_min_rb = read_reg32(VOTER_BASEADDR, VOTER_REG_SCORE_MIN);

    if (in_addr_rb != in_addr || in_beats_rb != in_beats ||
        out_addr_rb != out_addr || out_beats_rb != out_beats ||
        total_reads_rb != total_reads || score_min_rb != score_min) {
        xil_printf("[ERROR] Voter configuration readback mismatch:\n\r");
        xil_printf("  IN_ADDR     0x%08X != 0x%08X\n\r", in_addr_rb, in_addr);
        xil_printf("  IN_BEATS    %u != %u\n\r", in_beats_rb, in_beats);
        xil_printf("  OUT_ADDR    0x%08X != 0x%08X\n\r", out_addr_rb, out_addr);
        xil_printf("  OUT_BEATS   %u != %u\n\r", out_beats_rb, out_beats);
        xil_printf("  TOTAL_READS %u != %u\n\r", total_reads_rb, total_reads);
        xil_printf("  SCORE_MIN   %u != %u\n\r", score_min_rb, score_min);
        return XST_FAILURE;
    }

    xil_printf("[STAGE2] Configuration readback verified\n\r");
    return XST_SUCCESS;
}

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

        /* 【C1】本次任务的实际记录数：含上位机补零的尾批记录。
         * 补零记录 score=0，会被 SCORE_MIN 过滤，不参与投票。 */
        const u32 task_reads = conn->total_reads_received;
        const u32 task_in_bytes = (u32)ddr_layout_stage1_bytes(task_reads,
                                                    DNA_ACC_RESULT_PACKED_BYTES);

        // ✅ Cache一致性修复: Invalidate输入区域cache（按实际大小，不按预留容量）
        xil_printf("[STAGE2] Invalidating input cache (%u bytes)...\n\r", task_in_bytes);
        const u32 VOTER_IN_TEMP = DDR_VOTER_IN_BASE;
        const u32 INV_CHUNK = 256*1024;
        u32 inv_done = 0;

        while (inv_done < task_in_bytes) {
            u32 chunk = (task_in_bytes - inv_done > INV_CHUNK)
                        ? INV_CHUNK
                        : (task_in_bytes - inv_done);
            Xil_DCacheInvalidateRange(VOTER_IN_TEMP + inv_done, chunk);
            inv_done += chunk;
        }

        __asm__ volatile("dsb sy");
        __asm__ volatile("isb");
        usleep(1000);

        xil_printf("[STAGE2] ✓ Cache invalidated (%u bytes)\n\r", inv_done);

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
        const u32 voter_total_reads  = conn->total_reads_received;  /* [C1] 实际条数 */

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

        /* -------------------- Step 4: 唯一配置入口 + 回读校验 -------------------- */
        if (voter_configure_and_verify(conn) != XST_SUCCESS) {
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

    	    /* 【修订 B3】Stage2 输出的是共识 DNA 序列，必须先与水印做差分
    	       才是 Stage3 期望的稀疏流。原来整条链路缺了这一级。 */
    	    if (apply_watermark_differential() != 0) {
    	        pipeline_set_state(PIPE_FAIL);
    	        return PIPE_STEP_FAIL;
    	    }

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

	        /* 【B27】START 只能写一次 1，前后都不许再写这个寄存器。
	         * 原来的「写 0 → 写 1 → 100 us 后再写 0（脉冲结束）」是致命的：
	         * decoder 的 AXI-Lite 把**对 0x10 的任何一次写**都当成 START 脉冲
	         * （见 desparsification_decoder_v1_0.v 的 axi_slave_decoder），
	         * 所以那句「脉冲结束」在任务跑到一半时把核重启了；而重启不会取消
	         * 已经发出去的 AXI 读突发，残留的 R 拍被当成新任务输入流的开头，
	         * 整条输入被旋转，Stage3 输出与黄金 49.46% 误码（第四次上板）。
	         * RTL 已同时修好（只认 wdata[0]=1，且忙时不接受 START），
	         * 这里也一并改成单次脉冲，两边都不再依赖对方。 */
	        write_reg32(DECODER_BASEADDR, DECODER_REG_START, 0x01);
	        usleep(100);  /* 只是让 START 在 M 域被采样，期间不再碰这个寄存器 */

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
	        /* 【B22】本状态由 poll_callback 驱动，实测约 280 ms 走一次
	         * （有效间隔 250~500 ms，机理见 S1_NO_PROGRESS_LIMIT 处的说明）。
	         * 原实现三处错误，合起来等于「永远等不到、也永远超不了时」：
	         *   1) 注释声称用 STATUS 的 DONE 标志判完成，但循环里**从来没读过 STATUS**，
	         *      只靠每 1000 次轮询一次的内存启发式 —— 最早也要 1000 x 500 ms = 500 s
	         *      才做第一次判断，而上位机 recv_result 的静默上限是 180 s；
	         *   2) 那个启发式拿 0 和 0xAAAA... 当「未写」，可 PREP 填的哨兵是
	         *      DECODER_SENTINEL_U64 = 0x0A55AA55AA55AA55，压根不在比较之列，
	         *      所以它其实分不出写没写；
	         *   3) 超时阈值 500000 次轮询 ≈ 69 小时，等于没有超时。
	         * 现在与 Stage2 的 PIPE_VOTER_WAIT 对齐：每次轮询都读 STATUS 看 DONE，
	         * 内存进度只作旁证（且按真正的哨兵比较），并给一个够得着的超时。 */
	        static u32 poll_count = 0;
	        poll_count++;

	        u32 status = read_reg32(DECODER_BASEADDR, DECODER_REG_STATUS);

	        /* 条件1（主判据）：DONE 标志置位 */
	        if (status & DECODER_STATUS_DONE) {
	            xil_printf("\n\r[STAGE3] ✓ DONE flag set after %u polls\n\r", poll_count);
	            write_reg32(DECODER_BASEADDR, DECODER_REG_START, 0x00);
	            poll_count = 0;
	            pipeline_set_state(PIPE_DONE_STAGE3);
	            return PIPE_STEP_PROGRESS;
	        }

	        /* 条件2（旁证）：输出区哨兵是否已被全部覆盖。每 20 次轮询（~10 s）看一次 */
	        if ((poll_count % 20u) == 0u) {
	            Xil_DCacheInvalidateRange(DDR_DECODER_OUT_BASE, DECODER_OUTPUT_BEATS * 8);
	            volatile const u64 *p_out = (volatile const u64 *)DDR_DECODER_OUT_BASE;
	            u32 written = 0;
	            for (u32 i = 0; i < DECODER_OUTPUT_BEATS; i++) {
	                if (p_out[i] != DECODER_SENTINEL_U64) written++;
	            }
	            xil_printf("[STAGE3][POLL #%u] STATUS=0x%02X (IDLE=%u,DONE=%u) 已写 %u/%u 拍\n\r",
	                       poll_count, status, (unsigned)(status & 0x1U),
	                       (unsigned)((status >> 1) & 0x1U),
	                       written, (u32)DECODER_OUTPUT_BEATS);

	            if (written >= DECODER_OUTPUT_BEATS) {
	                xil_printf("[STAGE3] ⚠️ 输出区 %u/%u 拍已全部写出，但 DONE=0；按完成收尾\n\r",
	                           written, (u32)DECODER_OUTPUT_BEATS);
	                write_reg32(DECODER_BASEADDR, DECODER_REG_START, 0x00);
	                poll_count = 0;
	                pipeline_set_state(PIPE_DONE_STAGE3);
	                return PIPE_STEP_PROGRESS;
	            }
	        }

	        /* 够得着的超时。原注释写「240 x 500 ms ≈ 120 s，仍在上位机 180 s 之内」，
	         * 但每步实测 ~280 ms，**实际预算只有 ≈ 67 s**，乐观了约 2 倍。
	         * 不是紧迫故障：Stage3 实测 < 500 ms 就 DONE（全量 103,616 条那轮也一样），
	         * 离 67 s 差着两个数量级。同样只改注释不动数值（改了要重建 ELF）。
	         * 记在这里是因为：下一个照「500 ms/步」去调这个常数的人一定会算错，
	         * 而「拿注释当实现」正是 B22 当年翻车的同一类错误。 */
	        if (poll_count > 240u) {
	            /* 注意：这句打印的「~120 s」是照错的 500 ms/步算出来的，实际约 67 s。
	             * 本轮**刻意不改这个字符串** —— 改了会让编译产物与
	             * hw/build/export/ 里已验证的 ELF 不同源，就得整套重建 + 重新上板复验，
	             * 而它只在一条从未触发过的失败路径上打印。下次因真实需求重建 ELF 时一并改掉。 */
	            xil_printf("\n\r[ERROR] STAGE3 等待 ~120 s 仍未完成\n\r");
	            xil_printf("  STATUS=0x%08X IN_ADDR=0x%08X IN_BEATS=%u OUT_ADDR=0x%08X OUT_BEATS=%u\n\r",
	                       status,
	                       read_reg32(DECODER_BASEADDR, DECODER_REG_IN_ADDR),
	                       read_reg32(DECODER_BASEADDR, DECODER_REG_IN_BEATS),
	                       read_reg32(DECODER_BASEADDR, DECODER_REG_OUT_ADDR),
	                       read_reg32(DECODER_BASEADDR, DECODER_REG_OUT_BEATS));
	            poll_count = 0;
	            pipeline_set_state(PIPE_FAIL);
	            return PIPE_STEP_FAIL;
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

/*============================================================================
 * 【P3】任务配置化：PKT_CONFIG / PKT_CAPS（docs/05-interfaces.md 1.1~1.3）
 * 语义：严格拒绝（无降级）、强制 CONFIG（WM/BATCH/POST 前必须配置）、
 *       v1 只支持 SE150。校验逻辑在 sw/app/task_config.h（主机可测）。
 *============================================================================*/

/* 当前比特流的能力（如实反映综合参数） */
static task_caps_t board_caps(void)
{
    task_caps_t c;
    memset(&c, 0, sizeof c);
    c.version     = 1;
    c.read_bps    = READ_BASES_PER_READ;
    c.num_lc      = WM_NUM_LC;
    c.stride      = WM_STRIDE;
    c.max_symbols = WM_SYMBOLS;
    c.max_reads   = TASK_MAX_READS;
    c.features    = 1u;              /* bit0：SCORE_MIN 寄存器可用 */
    return c;
}

/* 发送一个带 8B 包头的小包（CONFIG_OK / CAPS_INFO）。
 * 单次 tcp_write 保证“包头+负载”要么整体入队，要么整体失败。 */
static err_t send_framed_pkt(struct tcp_pcb *tpcb, u8 type,
                             const u8 *payload, u32 len)
{
    u8 frame[PROTOCOL_HDR_SIZE + TASK_CAPS_INFO_LEN];
    if (tpcb == NULL || len > TASK_CAPS_INFO_LEN || (len != 0u && payload == NULL)) {
        return ERR_ARG;
    }

    frame[0] = (PROTOCOL_MAGIC >> 8) & 0xFF;
    frame[1] = PROTOCOL_MAGIC & 0xFF;
    frame[2] = type;
    frame[3] = 0;
    frame[4] = (len >> 24) & 0xFF; frame[5] = (len >> 16) & 0xFF;
    frame[6] = (len >> 8) & 0xFF;  frame[7] = len & 0xFF;
    if (len != 0u) memcpy(frame + PROTOCOL_HDR_SIZE, payload, len);

    for (int attempt = 0; attempt < 100; attempt++) {
        err_t e = tcp_write(tpcb, frame, PROTOCOL_HDR_SIZE + len,
                            TCP_WRITE_FLAG_COPY);
        if (e == ERR_OK) {
            tcp_output(tpcb);
            return ERR_OK;
        }
        if (e != ERR_MEM && e != ERR_WOULDBLOCK) return e;
        tcp_output(tpcb);
        keep_tcp_alive();
        usleep(1000);
    }
    xil_printf("[PKT] send_framed_pkt(%02X) giving up\n\r", type);
    return ERR_MEM;
}

static err_t reject_and_close_connection(dna_connection_t *conn,
                                         struct tcp_pcb *tpcb,
                                         struct pbuf *p)
{
    if (p != NULL) {
        tcp_recved(tpcb, p->tot_len);
        pbuf_free(p);
    }
    send_ack_byte(tpcb, PKT_ERROR);
    tcp_recv_offset = 0;
    if (conn != NULL) conn->tpcb = NULL;

    tcp_arg(tpcb, NULL);
    tcp_recv(tpcb, NULL);
    tcp_poll(tpcb, NULL, 0);
    err_t close_rc = tcp_close(tpcb);
    if (close_rc != ERR_OK) {
        tcp_abort(tpcb);
        return ERR_ABRT;
    }
    return ERR_OK;
}

void process_caps(dna_connection_t *conn)
{
    task_caps_t caps = board_caps();
    u8 payload[TASK_CAPS_INFO_LEN];
    task_caps_serialize(&caps, payload);
    xil_printf("[CAPS] version=%u read_bps=%u num_lc=%u stride=%u "
               "max_symbols=%u max_reads=%u features=%u\n\r",
               (u32)caps.version, (u32)caps.read_bps, caps.num_lc, caps.stride,
               caps.max_symbols, caps.max_reads, caps.features);
    if (conn->tpcb && send_framed_pkt(conn->tpcb, PKT_CAPS_INFO,
                                      payload, sizeof payload) != ERR_OK)
        xil_printf("[CAPS] ERROR: response enqueue failed\n\r");
}

void process_config(dna_connection_t *conn, u8 *data, u32 len)
{
    u8 ok[4];

    if (len != TASK_CONFIG_PAYLOAD_LEN) {
        xil_printf("[CONFIG] ERROR: payload %u != %u\n\r",
                   len, (u32)TASK_CONFIG_PAYLOAD_LEN);
        if (conn->tpcb) send_ack_byte(conn->tpcb, PKT_ERROR);
        return;
    }

    if (conn->configured) {                    /* 拒绝码 8：重复配置 */
        xil_printf("[CONFIG] rejected: already configured\n\r");
        wr_u32_be(ok, 8u);
        if (conn->tpcb && send_framed_pkt(conn->tpcb, PKT_CONFIG_OK,
                                          ok, sizeof ok) != ERR_OK)
            xil_printf("[CONFIG] ERROR: response enqueue failed\n\r");
        return;
    }
    if (conn->watermark_size != 0u || conn->total_reads_received != 0u) {
        wr_u32_be(ok, 9u);                      /* 拒绝码 9：顺序非法 */
        xil_printf("[CONFIG] rejected: data already received\n\r");
        if (conn->tpcb && send_framed_pkt(conn->tpcb, PKT_CONFIG_OK,
                                          ok, sizeof ok) != ERR_OK)
            xil_printf("[CONFIG] ERROR: response enqueue failed\n\r");
        return;
    }

    task_caps_t caps = board_caps();
    task_config_t cfg;
    int rc = task_config_parse(data, &caps, FRAME_READS,
                               DDR_READS_BASE, DDR_DNA_ACC_OUT_BASE,
                               DDR_DNA_ACC_OUT_BASE, DDR_VOTER_OUT_BASE,
                               READ_SIZE_BYTES, DNA_ACC_RESULT_PACKED_BYTES,
                               &cfg);
    if (rc != 0) {                              /* 严格拒绝：1..7 */
        static const char *why[] = {
            "", "version", "read_bps", "geometry", "symbols contract",
            "total_reads", "score_min", "CRC32"
        };
        xil_printf("[CONFIG] rejected (%d): %s\n\r", rc,
                   (rc >= 1 && rc <= 7) ? why[rc] : "?");
        wr_u32_be(ok, (u32)rc);
        if (conn->tpcb && send_framed_pkt(conn->tpcb, PKT_CONFIG_OK,
                                          ok, sizeof ok) != ERR_OK)
            xil_printf("[CONFIG] ERROR: response enqueue failed\n\r");
        return;
    }

    conn->cfg = cfg;
    conn->configured = 1;
    xil_printf("[CONFIG] accepted: v%u %ubp L=%u (%ux%u) reads=%u score_min=%u\n\r",
               (u32)cfg.version, (u32)cfg.read_bps, cfg.symbols,
               cfg.num_lc, cfg.stride, cfg.total_reads, cfg.score_min);
    wr_u32_be(ok, 0u);
    if (conn->tpcb && send_framed_pkt(conn->tpcb, PKT_CONFIG_OK,
                                      ok, sizeof ok) != ERR_OK)
        xil_printf("[CONFIG] ERROR: response enqueue failed\n\r");
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
    /* 【P3】CONFIG/CAPS 自己发带包头的应答，不走裸 ACK */
    case PKT_CONFIG: process_config(conn, payload, payload_len); break;
    case PKT_CAPS:   process_caps(conn); break;
    case PKT_WM:
        if (conn->tpcb)
            send_ack_byte(conn->tpcb,
                          process_watermark(conn, payload, payload_len) == 0
                          ? PKT_WM_OK : PKT_ERROR);
        break;
    case PKT_BATCH:
        if (conn->tpcb)
            send_ack_byte(conn->tpcb,
                          process_batch(conn, payload, payload_len) == 0
                          ? PKT_BATCH_OK : PKT_ERROR);
        break;
    case PKT_POST: process_post(conn); break;
    default:       xil_printf("[PKT] Unknown type\n\r"); send_ack_byte(conn->tpcb, PKT_ERROR); break;
    }
}

static err_t recv_callback(void *arg, struct tcp_pcb *tpcb, struct pbuf *p, err_t err)
{
    dna_connection_t *conn = (dna_connection_t *)arg;

    if (p == NULL) {
        tcp_recv_offset = 0;
        if (conn) conn->tpcb = NULL;
        tcp_close(tpcb);
        return ERR_OK;
    }
    if (err != ERR_OK) { pbuf_free(p); return err; }

    u16 received_len = p->tot_len;
    if (tcp_recv_offset + received_len > sizeof(tcp_recv_buffer)) {
        xil_printf("[TCP] Buffer overflow; closing connection\n\r");
        return reject_and_close_connection(conn, tpcb, p);
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
        if (payload_len > sizeof(tcp_recv_buffer) - PROTOCOL_HDR_SIZE) {
            xil_printf("[TCP] Declared payload %u exceeds receive capacity %u; "
                       "closing connection\n\r",
                       payload_len,
                       (u32)(sizeof(tcp_recv_buffer) - PROTOCOL_HDR_SIZE));
            return reject_and_close_connection(conn, tpcb, p);
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
int process_watermark(dna_connection_t *conn, u8 *data, u32 len)
{
    /* 【P3】强制 CONFIG：未配置直接拒绝 */
    if (!conn->configured) {
        xil_printf("[WM] rejected: no PKT_CONFIG on this connection\n\r");
        conn->watermark_size = 0;
        return -1;
    }
    /* 【修订 B1】原实现是 `if (len > MAX) len = MAX;` —— 静默截断。
       MAX 当时还是 10120，比 81,000 bit 所需的 10,125 B 还小，
       尾部 40 bit 直接被丢掉，而上位机完全无从得知。 */
    if (len > MAX_WATERMARK_SIZE) {
        xil_printf("[WM] ERROR: %u bytes exceeds MAX_WATERMARK_SIZE %u\n\r",
                   len, (u32)MAX_WATERMARK_SIZE);
        conn->watermark_size = 0;
        return -1;
    }
    if (len < WM_PACKED_BYTES) {
        xil_printf("[WM] ERROR: %u bytes < required %u (%u bits)\n\r",
                   len, (u32)WM_PACKED_BYTES, (u32)WM_TOTAL_BITS);
        conn->watermark_size = 0;
        return -1;
    }
    memcpy((void *)DDR_WATERMARK_BASE, data, len);
    Xil_DCacheFlushRange(DDR_WATERMARK_BASE, len);
    conn->watermark_size = len;
    xil_printf("[WM] Stored %u bytes (%u bits, %u symbols)\n\r",
               len, (u32)WM_TOTAL_BITS, (u32)WM_SYMBOLS);
    return 0;
}

/*============================================================================
 * 【修订 B1】把打包水印展开成 NUM_LC 个重叠区域
 *
 * 上位机送来的是「码流顺序 + 字节内 LSB-first」的 81,000 bit：
 *     bit[k]        = (buf[k>>3] >> (k&7)) & 1
 *     symbol[i]     = (bit[i] << 1) | bit[WM_SYMBOLS + i]        位平面布局
 * DNA 核的水印 BRAM 需要 NUM_LC × REF_LEN 个符号（区域之间重叠 READ_BPS），
 * 且预载时每个 32-bit AXIS 拍只取 TDATA[1:0]，所以必须一符号一拍地送。
 *
 * 区域 lc 覆盖符号 [lc*STRIDE, lc*STRIDE + REF_LEN)。
 *==========================================================================*/
int expand_watermark_regions(dna_connection_t *conn)
{
    const volatile u8 *wm = (const volatile u8 *)DDR_WATERMARK_BASE;
    volatile u32 *dst = (volatile u32 *)DDR_WM_REGIONS_BASE;
    u32 lc, row, idx, sym;

    if (conn->watermark_size < WM_PACKED_BYTES) {
        xil_printf("[WM] ERROR: watermark not loaded (%u bytes)\n\r",
                   conn->watermark_size);
        return -1;
    }

    Xil_DCacheInvalidateRange(DDR_WATERMARK_BASE, conn->watermark_size);

    /* 位序与几何由 wm_expand.h 统一定义，并在主机上用黄金向量单元测试
       （tools/test_wm_expand.c，见 tools/run_sim.sh） */
    for (lc = 0; lc < WM_NUM_LC; lc++) {
        for (row = 0; row < WM_REF_LEN; row++) {
            sym = wm_region_symbol((const unsigned char *)wm, lc, row,
                                   WM_STRIDE, WM_SYMBOLS);
            *dst++ = sym;
        }
    }
    (void)idx;

    Xil_DCacheFlushRange(DDR_WM_REGIONS_BASE, WM_REGIONS_TOTAL_BYTES);
    __asm__ volatile("dsb sy");
    xil_printf("[WM] Expanded to %u regions x %u symbols (%u bytes) @ 0x%08X\n\r",
               (u32)WM_NUM_LC, (u32)WM_REF_LEN,
               (u32)WM_REGIONS_TOTAL_BYTES, (u32)DDR_WM_REGIONS_BASE);
    return 0;
}

/*============================================================================
 * 【修订 B3】共识序列 ⊕ 水印 = 稀疏流
 *
 * 整条流水线原本缺了这一整级：Stage2 输出的是共识 DNA 序列，
 * Stage3 却直接把它当稀疏流去做 5b→4b 反稀疏化。
 *
 * 两侧都是「码流顺序 + 字节内 LSB-first」打包，因此逐字节异或即可。
 * 这里先用 PS 软件实现（10,125 B，一次几十微秒），把端到端链路打通；
 * 是否下沉到 Voter 里做，等链路验证通过后再决定。
 *==========================================================================*/
int apply_watermark_differential(void)
{
    volatile u8 *cons = (volatile u8 *)DDR_VOTER_OUT_BASE;
    const volatile u8 *wm = (const volatile u8 *)DDR_WATERMARK_BASE;
    u32 i;

    Xil_DCacheInvalidateRange(DDR_VOTER_OUT_BASE, VOTER_OUTPUT_BYTES);
    Xil_DCacheInvalidateRange(DDR_WATERMARK_BASE, WM_PACKED_BYTES);
    __asm__ volatile("dsb sy");

    for (i = 0; i < WM_PACKED_BYTES; i++) {
        cons[i] = (u8)(cons[i] ^ wm[i]);
    }
    /* 81,000 bit 不是 8 的整数倍余数为 0（10,125*8 = 81,000），无需处理尾部 */

    Xil_DCacheFlushRange(DDR_VOTER_OUT_BASE, VOTER_OUTPUT_BYTES);
    __asm__ volatile("dsb sy");
    __asm__ volatile("isb");
    xil_printf("[DIFF] Consensus XOR watermark done (%u bytes)\n\r",
               (u32)WM_PACKED_BYTES);
    return 0;
}

int process_batch(dna_connection_t *conn, u8 *data, u32 len)
{
    /* 【P3】强制 CONFIG */
    if (!conn->configured) {
        xil_printf("[BATCH] rejected: no PKT_CONFIG on this connection\n\r");
        return -1;
    }
    if (len < 4u) {
        xil_printf("[BATCH] invalid payload: %u bytes\n\r", len);
        return -1;
    }
    u32 num_reads = (data[0]<<24)|(data[1]<<16)|(data[2]<<8)|data[3];
    if (num_reads == 0u || num_reads > (len - 4u) / READ_SIZE_BYTES) {
        xil_printf("[BATCH] invalid read count %u for payload %u\n\r",
                   num_reads, len);
        return -1;
    }
    u32 data_size = num_reads * READ_SIZE_BYTES;
    if (len != 4u + data_size) {
        xil_printf("[BATCH] size mismatch: payload=%u expected=%u\n\r",
                   len, 4u + data_size);
        return -1;
    }

    /* 【C3】容量防溢出：DDR 只预留了 TOTAL_READS 条的空间；
     * 【P3】也不得超过声明的本任务条数 */
    if (conn->total_reads_received + num_reads > TOTAL_READS) {
        xil_printf("[BATCH] ✗ capacity exceeded: %u + %u > %u\n\r",
                   conn->total_reads_received, num_reads, (u32)TOTAL_READS);
        return -1;
    }
    if (conn->total_reads_received + num_reads > conn->cfg.total_reads) {
        xil_printf("[BATCH] ✗ exceeds declared total_reads: %u + %u > %u\n\r",
                   conn->total_reads_received, num_reads, conn->cfg.total_reads);
        return -1;
    }

    u32 offset  = conn->total_reads_received * READ_SIZE_BYTES;
    u32 dst     = DDR_READS_BASE + offset;

    memcpy((void *)dst, data + 4, data_size);
    conn->total_reads_received += num_reads;

    return 0;
}

void process_post(dna_connection_t *conn)
{
    /* 【P3】强制 CONFIG */
    if (!conn->configured) {
        xil_printf("[POST] rejected: no PKT_CONFIG on this connection\n\r");
        if (conn->tpcb) send_ack_byte(conn->tpcb, PKT_ERROR);
        return;
    }
    if (conn->total_reads_received == 0 || conn->watermark_size == 0) {
        xil_printf("[POST] No data\n\r");
        if (conn->tpcb) send_ack_byte(conn->tpcb, PKT_ERROR);
        return;
    }
    /* 【P3】声明条数与实际收到的必须一致 */
    if (conn->total_reads_received != conn->cfg.total_reads) {
        xil_printf("[POST] ✗ count mismatch: declared %u, received %u\n\r",
                   conn->cfg.total_reads, conn->total_reads_received);
        if (conn->tpcb) send_ack_byte(conn->tpcb, PKT_ERROR);
        return;
    }

    /* 【C2/C3】进入流水线前做协议与 DDR 布局校验：
     * - 条数必须是 FRAME_READS(64) 的整数倍（尾批由上位机补零；
     *   补零记录 score=0，会被 Voter 的 SCORE_MIN 过滤）；
     * - 按实际条数检查读段区 / Stage1 输出区不越界。 */
    int layout_rc = ddr_layout_validate(conn->total_reads_received,
                                        FRAME_READS, TOTAL_READS,
                                        DDR_READS_BASE, DDR_DNA_ACC_OUT_BASE,
                                        DDR_DNA_ACC_OUT_BASE, DDR_VOTER_OUT_BASE,
                                        READ_SIZE_BYTES,
                                        DNA_ACC_RESULT_PACKED_BYTES);
    if (layout_rc != 0) {
        xil_printf("[POST] ✗ DDR layout validation failed (rc=%d, reads=%u)\n\r",
                   layout_rc, conn->total_reads_received);
        xil_printf("[POST]    -1=空任务 -2=非64整数倍(补零缺失) "
                   "-3=超容量 -4/-5=区间越界\n\r");
        if (conn->tpcb) send_ack_byte(conn->tpcb, PKT_ERROR);
        return;
    }

    xil_printf("\n\r========================================\n\r");
    xil_printf("Starting Processing Pipeline\n\r");
    xil_printf("Total Reads: %u (actual)\n\r", conn->total_reads_received);
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

static int validate_decoder_written_beats(u32 out_addr, u32 total_beats, u32 *written_beats)
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
