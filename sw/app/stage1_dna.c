/******************************************************************************
 * stage1_dna.c — PS 固件第一阶段流水线实现
 *
 * 包含 pipeline_reset_counters、pipeline_step_stage1 及其辅助函数。
 ******************************************************************************/

#include "stage1_dna.h"
#include "echo.h"
#include "bd_ring.h"
#include "dma_dna.h"
#include "reg_timing.h"
#include "fw_log.h"
#include "ddr_layout.h"
#include "xil_printf.h"
#include "xil_cache.h"
#include "sleep.h"
#include "dna_time.h"
#include "prof.h"

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
 * ——与读段条数无关，任何规模都白等（docs/08-performance-and-strategy.md的P12前后固定开销边界）。
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

u32   wm_poll_steps = 0;  /* 水印预载实际占用了几个 poll 步（留证用） */
static XTime wm_t_start    = 0;  /* 预载区域循环的起点（XTime 直接测量，不是推断） */
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
static int   s1_last_tx_done = -1;
static int   s1_last_rx_done = -1;
static XTime s1_last_progress_time = 0;

void pipeline_reset_counters(void){
    wm_tx_expected=0; rx_expected=0; tx_expected=0; tx_done=0; rx_done=0;
    tx_frames_total=0; tx_frames_sent=0; tx_frames_done=0; wm_region=0;
    rx_records_total=0; rx_records_submitted=0;
    s1_last_tx_done=-1; s1_last_rx_done=-1;
    XTime_GetTime(&s1_last_progress_time);
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
pipe_step_rc_e pipeline_step_stage1(dna_connection_t *conn)
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
        int expand_rc;
        PROF_TIME_BEGIN(wmx);
        expand_rc = expand_watermark_regions(conn);
        PROF_TIME_END(wmx, wmx_ticks);
        if (expand_rc != 0) {
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
            /* WM_PREP 记录起点；此处汇总到最后一个区域 DMA 预载完成。 */
            PROF_ADD_TICKS(wmpre_ticks, (u64)(t_end - wm_t_start));
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
        PROF_CACHE_INVALIDATE(DDR_DNA_ACC_OUT_BASE, out_size);
        rx_records_total     = total_reads;
        rx_records_submitted = 0;
        rx_expected          = (int)total_reads;
        if (submit_rx_records() < 0) { pipeline_set_state(PIPE_FAIL); return PIPE_STEP_FAIL; }
        xil_printf("  RX BD: 1 BD/记录(%u B)，预投 %u/%u 条\n\r",
                   DNA_ACC_RESULT_PACKED_BYTES, rx_records_submitted, rx_records_total);
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
        PROF_CACHE_FLUSH(addr, len);

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
        PROF_TSTREAM_ENTER();
        PROF_HELPER_BEGIN(ts_rx_reclaim, helper_rx_reclaim_calls);
        int got_rx = reclaim_some_bd(RxRingPtr, 512);
        PROF_HELPER_END(ts_rx_reclaim);
        if (got_rx < 0) { dump_dma_regs("TX_STREAM reclaim RX failed"); pipeline_set_state(PIPE_FAIL); return PIPE_STEP_FAIL; }
        if (got_rx > 0) {
            rx_done += got_rx;

        }
        /* 【B21】立刻补投 RX BD：一条记录一个 BD，ring 不能空，否则 S2MM 进 Idle
         * → 结果 FIFO 满 → 输入 FIFO 满 → S_AXIS_DATA_TREADY 拉低 → MM2S 永久停摆 */
        PROF_HELPER_BEGIN(ts_rx_submit, helper_rx_submit_calls);
        int rx_submit_rc = submit_rx_records();
        PROF_HELPER_END(ts_rx_submit);
        if (rx_submit_rc < 0) { dump_dma_regs("RX resubmit failed"); pipeline_set_state(PIPE_FAIL); return PIPE_STEP_FAIL; }

        int free_rx = XAxiDma_BdRingGetFreeCnt(RxRingPtr);
        if (free_rx < 100 && tx_frames_sent < tx_frames_total) {
            PROF_TSTREAM_LOW_BEGIN(ts_lowwater);
            static u32 rx_stall_count = 0; rx_stall_count++;
            for (int i = 0; i < 5; i++) {
                PROF_HELPER_BEGIN(ts_low_reclaim, helper_low_reclaim_calls);
                got_rx = reclaim_some_bd(RxRingPtr, 512);
                PROF_HELPER_END(ts_low_reclaim);
                if (got_rx > 0) {
                    rx_done += got_rx;
                    free_rx = XAxiDma_BdRingGetFreeCnt(RxRingPtr);
                    if (free_rx >= 150) { rx_stall_count = 0; break; }
                }
                PROF_TSTREAM_USLEEP();
                usleep(50);
            }
            PROF_TIME_END(ts_lowwater, tstream_lowwater_ticks);
            if (rx_stall_count > 5000) { xil_printf("[WARN] RX recovery timeout, forcing TX continue\n\r"); rx_stall_count = 0; }
            else return PIPE_STEP_PROGRESS;
        }

        PROF_HELPER_BEGIN(ts_read_submit, helper_read_submit_calls);
        int bd = submit_reads_chunk();
        PROF_HELPER_END(ts_read_submit);
        if (bd < 0) { dump_dma_regs("TX_STREAM submit failed"); pipeline_set_state(PIPE_FAIL); return PIPE_STEP_FAIL; }

        PROF_HELPER_BEGIN(ts_tx_reclaim, helper_tx_reclaim_calls);
        int got_tx = reclaim_some_bd(TxRingPtr, 512);
        PROF_HELPER_END(ts_tx_reclaim);
        if (got_tx < 0) { dump_dma_regs("TX_STREAM reclaim TX failed"); pipeline_set_state(PIPE_FAIL); return PIPE_STEP_FAIL; }
        if (got_tx > 0) { tx_done += got_tx; tx_frames_done = tx_done; }

        /* 【B21】可达的无进展看门狗。
         * 本函数由 lwIP 的 poll_callback 驱动，实测约 280 ms 走一次（见 S1_NO_PROGRESS_LIMIT
         * 处的说明：两个独立的 tcp_slowtmr 驱动源叠加，有效间隔 250~500 ms，不是 500 ms）；
         * 原来的 stuck_count>10000 需要约 83 分钟才会触发，等于永远打不出证据，
         * 这正是上一轮板上「IP core START 之后再无任何输出」的原因。 */
        /* 【B21】基于 XTime 真实墙钟时间的无进展看门狗（30 秒）。
         * 无论轮询频率多高，只在连续 30 秒没有任何 BD 进展时判定卡死。 */
        if (rx_done != s1_last_rx_done || tx_done != s1_last_tx_done) {
            s1_last_rx_done = rx_done;
            s1_last_tx_done = tx_done;
            XTime_GetTime(&s1_last_progress_time);
        } else {
            XTime t_now;
            XTime_GetTime(&t_now);
            if ((t_now - s1_last_progress_time) > DNA_TIMEOUT_TICKS(30U)) {
                xil_printf("\n\r[ERROR] STAGE1 停滞 30 s 无任何 BD 进展\n\r");
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

        static XTime t_last_wait_print = 0;
        XTime t_now_wait;
        XTime_GetTime(&t_now_wait);
        if ((t_now_wait - t_last_wait_print) >= (XTime)(COUNTS_PER_SECOND)) {
            t_last_wait_print = t_now_wait;
            xil_printf("[STAGE1] WAIT tx=%u/%u rx=%d/%d (submitted=%u)\n\r",
                       tx_frames_done, tx_frames_total, rx_done, rx_expected,
                       rx_records_submitted);
        }

        if (tx_frames_done >= tx_frames_total && rx_done >= rx_expected) {
            pipeline_set_state(PIPE_DONE_STAGE1);
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
        xil_printf("  Data format: %u bytes/read × %u reads (actual)\n\r",
                   DNA_ACC_RESULT_PACKED_BYTES, conn->total_reads_received);
        xil_printf("  Total size: %u bytes\n\r",
                   (u32)ddr_layout_stage1_bytes(conn->total_reads_received,
                                                DNA_ACC_RESULT_PACKED_BYTES));

        /* 验证前 10 个 read 的数据新鲜度 */
        PROF_CACHE_INVALIDATE(DDR_DNA_ACC_OUT_BASE, DNA_ACC_RESULT_PACKED_BYTES * 10U);
        __asm__ volatile("dsb sy");
        __asm__ volatile("isb");

        /* 统计前 10 个 read 的非零字节（更直观），并展示第 0 read 的完整 48B */
        const volatile u8 *pbytes = (const volatile u8 *)DDR_DNA_ACC_OUT_BASE;
        u32 nonzero_bytes = 0;
        for (u32 i = 0; i < 10U * DNA_ACC_RESULT_PACKED_BYTES; i++) {
            if (pbytes[i] != 0) nonzero_bytes++;
        }

        xil_printf("\n\r[DEBUG] Output Statistics (first 10 reads):\n\r");
        xil_printf("  Non-zero bytes: %u / %u (%.1f%%)\n\r",
                   nonzero_bytes, 10U * DNA_ACC_RESULT_PACKED_BYTES,
                   (float)nonzero_bytes * 100.0f / (float)(10U * DNA_ACC_RESULT_PACKED_BYTES));

        xil_printf("\n\r[DEBUG] First read (%u bytes):\n\r", DNA_ACC_RESULT_PACKED_BYTES);
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
        PROF_CACHE_FLUSH(DDR_DNA_ACC_OUT_BASE,
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
