/******************************************************************************
 * @file echo.c
 * @brief DNA Accelerator - 串口整段流水线(滑动窗 + 投票 + 解码)
 ******************************************************************************/

#include <string.h>
#include "echo.h"
#include "wm_expand.h"
#include "fw_log.h"
#include "reg_timing.h"
#include "bd_ring.h"
#include "dma_dna.h"
#include "proto.h"
#include "pipeline.h"
#include "stage2_voter.h"
#include "stage3_decoder.h"
#include "lwip/err.h"
#include "lwip/tcp.h"
#include "xil_printf.h"
#include "xil_cache.h"
#include "sleep.h"
#include "xaxidma.h"
#include "xtime_l.h"
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
static err_t reject_and_close_connection(dna_connection_t *conn,
                                         struct tcp_pcb *tpcb,
                                         struct pbuf *p);
/* validate_decoder_written_beats 已迁至 stage3_decoder.{c,h} */
static void process_complete_packet(dna_connection_t *conn, u8 *packet_data, u32 total_len);
static err_t recv_callback(void *arg, struct tcp_pcb *tpcb, struct pbuf *p, err_t err);
static err_t accept_callback(void *arg, struct tcp_pcb *newpcb, err_t err);
static err_t poll_callback(void *arg, struct tcp_pcb *tpcb);

/* DMA 与 BD 环全局变量已迁至 bd_ring.{c,h} (g_bdring_ctx) */

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




/* ===== 通用字节视图打印工具（已迁至 fw_log.{c,h}） ===== */

/*============================================================================
 * IP核 START 信号控制（已迁至 reg_timing.{c,h}）
 *============================================================================*/

/* DMA 与 BD 环设置已迁至 bd_ring.{c,h} 与 dma_dna.{c,h} */

/*============================================================================
 * 第一级: DNA Accelerator (滑动窗+预加载)
 *============================================================================*/
/* 流水线状态 pipe_state_e、pipe_state、pipe_step_rc_e 与 pipeline_set_state 已迁至 pipeline.{c,h} */

/* 第一级计数 */
static int wm_tx_expected = 0;
static int rx_expected    = 0;
static int tx_expected    = 0;
static int tx_done        = 0;
static int rx_done        = 0;

static u32 wm_region = 0;      /* 预载到第几个区域（修订 B1） */

/* 【WM 批量化】—— 为什么是 16，以及为什么不会饿死 lwIP
 *
 * 改之前：PIPE_WM_TX 提交一个区域的 DMA 就 return，PIPE_WM_WAIT 在**下一个** poll
 * 里回收 BD。一个区域两个 poll 周期，50 个区域 ≈ 100 步；而 poll 有效间隔实测
 * 250~500 ms（见 S1_NO_PROGRESS_LIMIT 处的机理说明），于是白等出 ~29 s 的固定开销
 * ——与读段条数无关，任何规模都白等（docs/18 P1 第 3 项五档拟合的常数项）。
 *
 * 改之后：一次 poll 连续走 WM_REGIONS_PER_POLL 个区域，每个区域在**同一次调用内**
 * 有界忙等 BD 回收。50 个区域 = ceil(50/16) = 4 个 poll 步，加上 PIPE_WM_PREP 共 5 步。
 *
 * 为什么 16 是安全的（poll_callback 是 lwIP 回调，久不返回会饿死 TCP 处理）：
 *   - 单区域是 957 个符号 × 4 B = 3,828 B 一个 BD。DNA 核预载时 TREADY 恒 1、
 *     一拍一个符号，957 拍 @100 MHz ≈ 9.6 us；加上三次 usleep(10) 的寄存器时序，
 *     **典型单区域 ≈ 50 us**，16 个区域 ≈ 0.8 ms —— 比 250 ms 的 poll 间隔小两个半数量级。
 *   - 硬件真挂住时也有上界：单区域忙等封顶 WM_BD_WAIT_US = 5 ms，
 *     一次 poll 最坏 16 × 5 ms = 80 ms，仍小于一个 poll 间隔，且结局是 PIPE_FAIL
 *     而不是原来那种「停在 WM_WAIT 里无限等」。
 * 为什么不干脆一次 poll 走完 50 个：最坏情况会涨到 250 ms（整整一个 poll 间隔），
 *   而且把唯一的让出点也丢了；换来的只是再省 ~0.8 s，不划算。
 * 为什么不是 8：8 要 7 步（≈2 s）而 16 只要 4 步（≈1.1 s），
 *   而 16 的**典型**在 poll 时间仍是亚毫秒级，等于白拿。
 */
#define WM_REGIONS_PER_POLL   16U

static u32   wm_poll_steps = 0;  /* 水印预载实际占用了几个 poll 步（留证用） */
static XTime wm_t_start    = 0;  /* 预载区域循环的起点（XTime 直接测量，不是推断） */
static u32   pipe_poll_steps = 0;/* 整条流水线一共占了几个 poll 步（留证用） */
static XTime pipe_t_start    = 0;
static u32 tx_frames_total = 0;
static u32 tx_frames_sent  = 0;
static u32 tx_frames_done  = 0;

/* 【B21】RX 改为「一条 48 B 记录一个 BD」后的滚动补投计数 */
static u32 rx_records_total     = 0;   /* 本次任务应收的记录条数 = 实际读段数 */
static u32 rx_records_submitted = 0;   /* 已交给硬件的 BD（记录）条数 */

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
    wm_poll_steps=0; wm_t_start=0;
}

/* 【B21】按「一条记录一个 BD」滚动补投 RX 描述符。
 * 返回本次投出的 BD 数（0 表示暂时不需要补），-1 表示失败。 */
static inline int submit_rx_records(void)
{
    dna_rx_state_t st = {
        .records_total = rx_records_total,
        .records_submitted = rx_records_submitted,
        .rx_done = rx_done
    };
    int bd = dna_submit_rx_records(&st);
    rx_records_submitted = st.records_submitted;
    return bd;
}

/* 小批提交 READS */
static inline int submit_reads_chunk(void)
{
    dna_tx_state_t st = {
        .frames_total = tx_frames_total,
        .frames_sent = tx_frames_sent,
        .frames_done = tx_frames_done,
        .tx_done = tx_done,
        .tx_expected = tx_expected
    };
    int bd = dna_submit_reads_chunk(&st);
    tx_frames_sent = st.frames_sent;
    tx_frames_done = st.frames_done;
    tx_done = st.tx_done;
    tx_expected = st.tx_expected;
    return bd;
}

/* 【WM 批量化】单个水印区域的 BD 有界忙等。
 * 返回 0 成功，-1 失败（BD 报错或超时）。 */
static inline int wm_wait_region_bd(int expected)
{
    return dna_wait_wm_region_bd(wm_region, expected);
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
        /* 【WM 批量化】开始批量预载前先把 TX ring 排空。
         * 批量化之后，「本区域的 BD 完成了没有」是靠 reclaim 的**计数**判断的，
         * 而 XAxiDma_BdRingFromHw 是按提交顺序返回的：如果环上还压着上一次任务
         * 失败时残留的已完成 BD，region 0 的等待会被那个残留 BD 顶掉计数，
         * 于是在自己的 957 拍还没走完时就撤掉 preload —— 残余拍会被当成 read 数据
         * 推进 in_fifo。原实现整整等一个 poll 周期（250 ms），自己的 BD 早就完成了，
         * 所以这个隐患一直被时间余量盖住；批量化把余量压到几十微秒，必须显式排空。
         * 正常路径下 Stage1 要 tx_done >= tx_expected 才退出，这里应当一个都收不到。 */
        {
            int stale = reclaim_some_bd(TxRingPtr, MAX_BD_COUNT);
            if (stale < 0) {
                xil_printf("[WM] ERROR: TX ring 残留 BD 带错误状态\n\r");
                pipeline_set_state(PIPE_FAIL);
                return PIPE_STEP_FAIL;
            }
            if (stale > 0)
                xil_printf("[WM] WARN: 排空了 %d 个残留 TX BD（上一次任务未收尾？）\n\r",
                           stale);
        }

        wm_region = 0;
        wm_poll_steps = 0;
        XTime_GetTime(&wm_t_start);
        pipeline_set_state(PIPE_WM_TX);
        return PIPE_STEP_PROGRESS;
    }
    case PIPE_WM_TX: {
        /* 【WM 批量化】一次 poll 批量走 WM_REGIONS_PER_POLL 个区域。
         * 每个区域的寄存器写序列与原来**逐字节一致**（选区域 → usleep(10) →
         * 置 preload → usleep(10) → DMA → 等完成 → 清 preload → usleep(10)）：
         * 寄存器写序列本身就是被测对象（B27 的教训），这里只收掉 poll 周期的白等，
         * 不「整理」时序。 */
        u32 done_this_poll = 0;

        wm_poll_steps++;

        while (wm_region < WM_NUM_LC && done_this_poll < WM_REGIONS_PER_POLL) {
            /* 先选区域，再进预载模式；顺序不能反 */
            dna_select_wm_region(wm_region);
            dna_enter_preload();

            wm_tx_expected = submit_bd_transfer(TxRingPtr,
                                                DDR_WM_REGIONS_BASE + wm_region * WM_REGION_BYTES,
                                                WM_REGION_BYTES, TxMaxTransferLen,
                                                "TX-WM-REGION", XFER_TX_WM);
            if (wm_tx_expected < 0) { pipeline_set_state(PIPE_FAIL); return PIPE_STEP_FAIL; }

            if (wm_wait_region_bd(wm_tx_expected) < 0) {
                pipeline_set_state(PIPE_FAIL);
                return PIPE_STEP_FAIL;
            }

            /* MM2S 的 BD 完成意味着这 957 拍已经在 AXIS 上握手完毕
             * （预载模式下 DNA 核 TREADY 恒 1，见 Dna_accelerator_core_v1_0.v:173），
             * 所以 wm_waddr 已经从 956 回绕到 0。原实现靠「下一个 poll 才回收」
             * 天然有 250 ms 余量，现在只隔几十微秒，这里再留 10 us（≈1,000 个 aclk）
             * 的余量后才撤 preload —— 撤早了残余拍会被当成 read 数据推进 in_fifo。 */
            usleep(10);

            /* 每个区域传完都退出预载模式，确保 wm_waddr 与区域边界对齐 */
            dna_leave_preload();

            wm_region++;
            done_this_poll++;
        }

        if (wm_region >= WM_NUM_LC) {
            XTime t_end;
            XTime_GetTime(&t_end);
            u32 elapsed_ms = (u32)((t_end - wm_t_start) /
                                   (XTime)(COUNTS_PER_SECOND / 1000U));
            xil_printf("[STAGE1] WM preload done: %u regions x %u symbols, "
                       "%u poll steps, %u ms\n\r",
                       (u32)WM_NUM_LC, (u32)WM_REF_LEN, wm_poll_steps, elapsed_ms);
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
        dna_start();
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
            dna_stop(); usleep(100);
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

/* voter_configure_and_verify 与 pipeline_step_stage2 已迁至 stage2_voter.{c,h} */
/* pipeline_step_stage3 已迁至 stage3_decoder.{c,h} */

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

/* parse_header、board_caps、send_framed_pkt 已迁至 proto.{c,h} */

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

/* process_caps、process_config 已迁至 proto.{c,h} */


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

/* send_ack_byte 已迁至 proto.{c,h} */

static err_t poll_callback(void *arg, struct tcp_pcb *tpcb)
{
    dna_connection_t *conn = (dna_connection_t *)arg;
    keep_tcp_alive();

    switch (g_proc_state) {
    case PROC_REQUESTED:
        pipeline_reset_counters(); pipeline_set_state(PIPE_WM_PREP);
        /* 【WM 批量化·留证】整条流水线一共占了几个 poll 步、走了多少墙钟时间。
         * 固定开销的量纲就是「poll 步数 × 250~500 ms」，把步数直接打出来，
         * 下一个人就不必再靠分档拟合去反推常数项（docs/18 P1 第 3 项的教训：
         * 扣除法推断一旦进了表格就会被当成实测引用）。 */
        pipe_poll_steps = 0;
        XTime_GetTime(&pipe_t_start);
        g_proc_state = PROC_RUNNING; break;
    case PROC_RUNNING: {
        int st = run_processing_pipeline(conn);
        pipe_poll_steps++;
        if (pipe_state == PIPE_FAIL) g_proc_state = PROC_FAILED;
        else if (pipe_state == PIPE_DONE_STAGE3 && st == XST_SUCCESS) {
            XTime t_end;
            XTime_GetTime(&t_end);
            xil_printf("[PIPE] total %u poll steps, %u ms "
                       "(WM preload: %u steps)\n\r",
                       pipe_poll_steps,
                       (u32)((t_end - pipe_t_start) /
                             (XTime)(COUNTS_PER_SECOND / 1000U)),
                       wm_poll_steps);
            g_proc_state = PROC_DONE;
        }
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

/* apply_watermark_differential 已迁至 stage2_voter.{c,h} */

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

/* validate_decoder_written_beats 已迁至 stage3_decoder.{c,h} */
