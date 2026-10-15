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
#include "stage1_dna.h"
#include "stage2_voter.h"
#include "stage3_decoder.h"
#include "ldpc_onchip.h"
#include "lwip/err.h"
#include "lwip/tcp.h"
#include "xil_printf.h"
#include "fw_diag.h"
#include "xil_cache.h"
#include "sleep.h"
#include "xaxidma.h"
#include "dna_time.h"
#include "prof.h"
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

/* 单次 poll 回调内最多推进多少个流水线状态。
 * 取 64：整条流水线约 20 步（17 个 PIPE_* 状态 + PIPE_WM_TX 的 4 批），
 * 64 足以一次跑完，留 3 倍余量以防未来加状态；同时它是一道保险——
 * 万一某个状态因缺陷不推进，回调也会在 64 次内让出 CPU，
 * 不至于饿死 lwIP 的 TCP 处理与重传定时器。 */
#define PIPE_MAX_STEPS_PER_POLL  64U

/* poll 回调次数，与 pipe_poll_steps（状态推进次数）分开统计：
 * 改动生效后前者应降到个位数，后者基本不变。 */
static u32 pipe_poll_cbs = 0;

/* 【P0 分解】按流水线状态累计耗时。
 * 2026-09-10 已测出固定开销总量：修复前 5.284 s、修复后 1.505 s
 * （tools/board/g3_overhead_sweep.py 七档拟合）。但「剩下这 1.5 s 花在哪个状态」
 * 一直是空白——docs/08 §3 那一项因此还打着 ⬜。
 *
 * 做法：在 run_processing_pipeline() 前后取 XTime，把这段时间**记在进入该次调用
 * 时所处的状态**头上。纯观测，不改任何控制流与寄存器写序列（B27 纪律）。
 * PIPE_FAIL 是枚举最后一项，+1 即为状态总数。 */
#define PIPE_STATE_COUNT   ((int)PIPE_FAIL + 1)
static u64 pipe_state_cyc[PIPE_STATE_COUNT];
static u32 pipe_state_hits[PIPE_STATE_COUNT];

/* 阶段墙钟跨度：边界间经过的主循环节流时间也归入当前阶段。 */
#define PIPE_STAGE_COUNT   4U
#define PIPE_STAGE_NONE    0xFFFFFFFFU
enum {
    PIPE_STAGE_STAGE1 = 0,
    PIPE_STAGE_STAGE2,
    PIPE_STAGE_STAGE3,
    PIPE_STAGE_LDPC
};
static u64 pipe_stage_cyc[PIPE_STAGE_COUNT];
static u32 pipe_stage_hits[PIPE_STAGE_COUNT];
static u32 pipe_stage_active = PIPE_STAGE_NONE;
static XTime pipe_stage_t_start;

static u32 pipe_cycles_to_ms_x1000(u64 cycles)
{
    return (u32)((cycles * 1000000ULL) / (u64)COUNTS_PER_SECOND);
}

static void pipe_stage_switch(u32 next, XTime at)
{
    if (pipe_stage_active < PIPE_STAGE_COUNT) {
        pipe_stage_cyc[pipe_stage_active] += (u64)(at - pipe_stage_t_start);
    }
    pipe_stage_active = next;
    if (next < PIPE_STAGE_COUNT) {
        pipe_stage_t_start = at;
        pipe_stage_hits[next]++;
    }
}

static const char *pipe_state_name(int st)
{
    switch (st) {
    case PIPE_IDLE:          return "IDLE";
    case PIPE_WM_PREP:       return "WM_PREP";
    case PIPE_WM_TX:         return "WM_TX";
    case PIPE_RX_PREP:       return "RX_PREP";
    case PIPE_TX_PREFILL:    return "TX_PREFILL";
    case PIPE_START_IP:      return "START_IP";
    case PIPE_TX_STREAM:     return "TX_STREAM";
    case PIPE_PROGRESS:      return "PROGRESS";
    case PIPE_DONE_STAGE1:   return "DONE_STAGE1";
    case PIPE_VOTER_PREP:    return "VOTER_PREP";
    case PIPE_VOTER_START:   return "VOTER_START";
    case PIPE_VOTER_WAIT:    return "VOTER_WAIT";
    case PIPE_DONE_STAGE2:   return "DONE_STAGE2";
    case PIPE_SEND_RESULT:   return "SEND_RESULT";
    case PIPE_DECODER_PREP:  return "DECODER_PREP";
    case PIPE_DECODER_START: return "DECODER_START";
    case PIPE_DECODER_WAIT:  return "DECODER_WAIT";
    case PIPE_DONE_STAGE3:   return "DONE_STAGE3";
    case PIPE_LDPC_PREP:     return "LDPC_PREP";
    case PIPE_LDPC_RUN:      return "LDPC_RUN";
    case PIPE_LDPC_READBACK: return "LDPC_READBACK";
    default:                 return "FAIL";
    }
}




/* ===== 通用字节视图打印工具（已迁至 fw_log.{c,h}） ===== */

/*============================================================================
 * IP核 START 信号控制（已迁至 reg_timing.{c,h}）
 *============================================================================*/

/* DMA 与 BD 环设置已迁至 bd_ring.{c,h} 与 dma_dna.{c,h} */

/* 第一级: DNA Accelerator (pipeline_step_stage1 与计数器) 已迁至 stage1_dna.{c,h} */

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
    } else if (pipe_state >= PIPE_LDPC_PREP && pipe_state <= PIPE_LDPC_READBACK) {
        rc = pipeline_step_ldpc();
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
        FW_ERR_PRINTF("[PKT] Invalid header\n\r");
        if (conn->tpcb) send_ack_byte(conn->tpcb, PKT_ERROR);
        return;
    }
    if (total_len != PROTOCOL_HDR_SIZE + payload_len) {
        FW_ERR_PRINTF("[PKT] Size mismatch\n\r");
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
    default:       FW_ERR_PRINTF("[PKT] Unknown type\n\r"); send_ack_byte(conn->tpcb, PKT_ERROR); break;
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
        FW_ERR_PRINTF("[TCP] Buffer overflow; closing connection\n\r");
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
            FW_ERR_PRINTF("[TCP] Declared payload %u exceeds receive capacity %u; "
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
    if (g_proc_state == PROC_RUNNING && (pipe_poll_steps % 100u) == 0u) {
        if (conn && conn->tpcb) {
            arp_keepalive(&conn->tpcb->remote_ip);
        }
    }

    switch (g_proc_state) {
    case PROC_REQUESTED:
        prof_reset();
        pipeline_reset_counters(); pipeline_set_state(PIPE_WM_PREP);
        /* 【WM 批量化·留证】整条流水线一共占了几个 poll 步、走了多少墙钟时间。
         * 固定开销的量纲就是「poll 步数 × 250~500 ms」，把步数直接打出来，
         * 下一个人就不必再靠分档拟合去反推常数项（docs/09 P1 第 3 项的教训：
         * 扣除法推断一旦进了表格就会被当成实测引用）。 */
        pipe_poll_steps = 0;
        pipe_poll_cbs = 0;
        for (int _i = 0; _i < PIPE_STATE_COUNT; ++_i) {
            pipe_state_cyc[_i] = 0; pipe_state_hits[_i] = 0;
        }
        for (u32 _i = 0; _i < PIPE_STAGE_COUNT; ++_i) {
            pipe_stage_cyc[_i] = 0; pipe_stage_hits[_i] = 0;
        }
        pipe_stage_active = PIPE_STAGE_NONE;
        XTime_GetTime(&pipe_t_start);
        /* WM_PREP 及其 WM_TX/RX_PREP/TX_PREFILL 前置从任务起点归入 Stage1。 */
        pipe_stage_switch(PIPE_STAGE_STAGE1, pipe_t_start);
        g_proc_state = PROC_RUNNING; break;
    case PROC_RUNNING: {
        /* 【P0 固定开销】改之前：这里每次 poll 回调只推进**一个**流水线状态就 break，
         * 于是每个状态都要白等一个 lwIP poll 周期。2026-09-10 用 XSDB 读
         * pipe_poll_steps 实测：256 源读段的任务走了 20 步、t_result = 5.525 s，
         * 即 276 ms/步 —— 这 5.5 s 里没有任何一毫秒是真实计算，硬件早算完了，
         * PS 在等定时器。（也解释了历史文档那个 4.25 s 常数：17 个 PIPE_* 状态
         * × 250 ms，量纲完全吻合。）
         *
         * 改之后：在**同一次回调内**连续推进，直到终态或用尽 guard 配额。
         * 三条不能碰的约束：
         *   1. 不改任何状态**内部**的寄存器写序列与其相对时序 —— 写序列本身就是
         *      被测对象（B27 的教训：TB 里只写一次 START 根本测不出真实固件时序）；
         *   2. 各状态原有的有界忙等（wm_wait_region_bd、各级 DONE 轮询）原样保留，
         *      本改动只收掉「状态之间」的白等，不动「状态之内」的等待；
         *   3. 必须有 guard 上限，否则单次回调可能长时间不返回，饿死 lwIP 的
         *      TCP 收发与重传定时器，反而制造断连。
         *
         * 注意 do-while 里还有一处「必须让出」的判断，见循环末尾：
         * 流式状态不能批量推进，否则会撑爆 BD 环。
         *
         * pipe_poll_steps 的语义随之变化：它现在计的是**状态推进次数**而不是
         * poll 回调次数，所以不能再用「pipe_poll_steps x poll 间隔」估算耗时。
         * 新增 pipe_poll_cbs 单独统计回调次数，两者一起打印才能看出改动是否生效。 */
        int st = XST_SUCCESS;
        u32 steps_this_cb = 0;

        pipe_poll_cbs++;

        do {
            int st_before = (int)pipe_state;
            XTime t_a, t_b;
            XTime_GetTime(&t_a);
            st = run_processing_pipeline(conn);
            XTime_GetTime(&t_b);
            if (st_before >= 0 && st_before < PIPE_STATE_COUNT) {
                pipe_state_cyc[st_before]  += (u64)(t_b - t_a);
                pipe_state_hits[st_before] += 1u;
            }
            pipe_poll_steps++;
            steps_this_cb++;

            /* 只在状态机实际跨过阶段入口时打点；两个打点之间的 poll 节流
             * 墙钟自然留在当前阶段跨度内。 */
            if (st == XST_SUCCESS) {
                if (pipe_stage_active == PIPE_STAGE_STAGE1 &&
                    pipe_state == PIPE_VOTER_PREP) {
                    pipe_stage_switch(PIPE_STAGE_STAGE2, t_b);
                } else if (pipe_stage_active == PIPE_STAGE_STAGE2 &&
                           pipe_state == PIPE_DECODER_PREP) {
                    pipe_stage_switch(PIPE_STAGE_STAGE3, t_b);
                } else if (pipe_stage_active == PIPE_STAGE_STAGE3 &&
                           pipe_state == PIPE_LDPC_PREP) {
                    pipe_stage_switch(PIPE_STAGE_LDPC, t_b);
                }
            }

            if (pipe_state == PIPE_FAIL) { g_proc_state = PROC_FAILED; break; }

            if (pipe_state == PIPE_SEND_RESULT && st == XST_SUCCESS) {
                XTime t_end;
                XTime_GetTime(&t_end);
                /* SEND_RESULT 是终止标记，没有独立的状态执行区间；按实际到达
                 * 路径结束当前阶段。当前 LDPC 路径因此把它作为 LDPC 的终点。 */
                pipe_stage_switch(PIPE_STAGE_NONE, t_end);
                FW_RESULT_PRINTF("[PIPE] total %u steps in %u callbacks, %u ms "
                           "(WM preload: %u steps)\n\r",
                           pipe_poll_steps, pipe_poll_cbs,
                           (u32)((t_end - pipe_t_start) /
                                 (XTime)(COUNTS_PER_SECOND / 1000U)),
                           wm_poll_steps);
                {
                    const u64 total_cyc = (u64)(t_end - pipe_t_start);
                    const u64 stage_sum_cyc = pipe_stage_cyc[PIPE_STAGE_STAGE1] +
                                              pipe_stage_cyc[PIPE_STAGE_STAGE2] +
                                              pipe_stage_cyc[PIPE_STAGE_STAGE3] +
                                              pipe_stage_cyc[PIPE_STAGE_LDPC];
                    const u64 head_cyc = 0;
                    const u64 tail_cyc = 0;
                    const u64 accounted_cyc = head_cyc + stage_sum_cyc + tail_cyc;
                    const char diff_sign = (accounted_cyc >= total_cyc) ? '+' : '-';
                    const u64 diff_cyc = (accounted_cyc >= total_cyc)
                                       ? accounted_cyc - total_cyc
                                       : total_cyc - accounted_cyc;
                    const u32 stage1_ms = pipe_cycles_to_ms_x1000(pipe_stage_cyc[PIPE_STAGE_STAGE1]);
                    const u32 stage2_ms = pipe_cycles_to_ms_x1000(pipe_stage_cyc[PIPE_STAGE_STAGE2]);
                    const u32 stage3_ms = pipe_cycles_to_ms_x1000(pipe_stage_cyc[PIPE_STAGE_STAGE3]);
                    const u32 ldpc_ms = pipe_cycles_to_ms_x1000(pipe_stage_cyc[PIPE_STAGE_LDPC]);
                    const u32 head_ms = pipe_cycles_to_ms_x1000(head_cyc);
                    const u32 tail_ms = pipe_cycles_to_ms_x1000(tail_cyc);
                    const u32 sum_ms = pipe_cycles_to_ms_x1000(accounted_cyc);
                    const u32 total_ms = pipe_cycles_to_ms_x1000(total_cyc);
                    const u32 diff_ms = pipe_cycles_to_ms_x1000(diff_cyc);
                    xil_printf("[STAGE-TIME] stage1=%u.%03u ms (hits=%u) "
                               "stage2=%u.%03u ms (hits=%u) "
                               "stage3=%u.%03u ms (hits=%u) "
                               "ldpc=%u.%03u ms (hits=%u) "
                               "head=%u.%03u ms tail=%u.%03u ms "
                               "sum=%u.%03u ms total=%u.%03u ms diff=%c%u.%03u ms\n\r",
                               stage1_ms / 1000U, stage1_ms % 1000U,
                               pipe_stage_hits[PIPE_STAGE_STAGE1],
                               stage2_ms / 1000U, stage2_ms % 1000U,
                               pipe_stage_hits[PIPE_STAGE_STAGE2],
                               stage3_ms / 1000U, stage3_ms % 1000U,
                               pipe_stage_hits[PIPE_STAGE_STAGE3],
                               ldpc_ms / 1000U, ldpc_ms % 1000U,
                               pipe_stage_hits[PIPE_STAGE_LDPC],
                               head_ms / 1000U, head_ms % 1000U,
                               tail_ms / 1000U, tail_ms % 1000U,
                               sum_ms / 1000U, sum_ms % 1000U,
                               total_ms / 1000U, total_ms % 1000U,
                               diff_sign, diff_ms / 1000U, diff_ms % 1000U);
                }
                /* 【P0 分解】只打印有耗时的状态，按 ms 给出。
                 * 注意这里统计的是**状态内部**的执行时间，不含主循环两次状态推进
                 * 之间让出的 PIPE_RUN_SLEEP_US 节流时间；末行是由总墙钟减状态和得到的
                 * 残差，并不单独表示 lwIP 空等。 */
                {
                    u64 sum = 0; int _i;
                    const u32 per_ms = (u32)(COUNTS_PER_SECOND / 1000U);
                    xil_printf("[PIPE-BREAKDOWN] state / hits / ms\n\r");
                    for (_i = 0; _i < PIPE_STATE_COUNT; ++_i) {
                        sum += pipe_state_cyc[_i];
                        if (pipe_state_cyc[_i] == 0) continue;
                        xil_printf("  %-14s %5u  %6u\n\r",
                                   pipe_state_name(_i), pipe_state_hits[_i],
                                   (u32)(pipe_state_cyc[_i] / per_ms));
                    }
                    xil_printf("  %-14s %5s  %6u\n\r", "[in-state]", "-",
                               (u32)(sum / per_ms));
                    xil_printf("  %-14s %5s  %6u  <- 两次 poll 之间让出的时间（主循环 PIPE_RUN_SLEEP_US 节流，非 lwIP 空等）\n\r",
                               "[waiting]", "-",
                               (u32)(((t_end - pipe_t_start) - sum) / per_ms));
                }
                g_proc_state = PROC_DONE;
                break;
            }
            /* 【必须让出】PIPE_TX_STREAM / PIPE_PROGRESS 这两个状态**依赖 poll 节流**：
             * 它们按 RX BD 环的剩余容量分批投递，靠「回到 lwIP 再等下一次 poll」
             * 给 DMA 排空与 BD 回收留出时间。2026-09-10 实测过把它们也纳入批量推进
             * 的后果：TX 64/64 帧一次投完但 TX BD 只完成 7/64，
             * RX submitted=640 超过 ring free=512，Stage1 停顿 ~30 s 直接 FAIL
             * （串口实录 g3_runs/20260910T113222Z/uart.log）。
             * 也就是说原来那个「一次 poll 一步」不只是浪费，它同时是**节流机制**，
             * 而 stage1_dna.c 的 PIPE_WM_TX 分支里那句「原实现靠『下一个 poll 才
             * 回收』天然有 250 ms 余量」早就写明了这一点。
             * （2026-09-11：此处原写作 stage1_dna.c:178，该行号在 WM 批量化补进
             *  注释后已失效——**行号引用会静默过期，一律改按标识符引用**。）
             * 所以这里只批量推进「配置/等待完成」类状态，一旦进入流式状态立刻让出。 */
            if (pipe_state == PIPE_TX_STREAM || pipe_state == PIPE_PROGRESS) break;
        } while (steps_this_cb < PIPE_MAX_STEPS_PER_POLL);

        break;
    }
    case PROC_DONE:
        send_result(conn);
        g_proc_state = (conn->state == STATE_IDLE) ? PROC_IDLE : PROC_FAILED;
        prof_dump_once();
        break;
    case PROC_FAILED:
        FW_ERR_PRINTF("[POST] Pipeline failed\n\r");
        send_ack_byte(conn->tpcb, PKT_ERROR);
        g_proc_state = PROC_IDLE;
        prof_dump_once();
        break;
    default: break;
    }
    return ERR_OK;
}

int echo_pipeline_is_running(void)
{
    return (g_proc_state != PROC_IDLE);
}

void echo_pipeline_poll(void)
{
    if (g_proc_state != PROC_IDLE && g_conn.tpcb != NULL) {
        poll_callback(&g_conn, g_conn.tpcb);
    }
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
    if (!g_server_pcb) { FW_ERR_PRINTF("[ERROR] tcp_new failed\n\r"); return -1; }
    err = tcp_bind(g_server_pcb, IP_ADDR_ANY, 7);
    if (err != ERR_OK) { FW_ERR_PRINTF("[ERROR] bind failed: %d\n\r", err); return -1; }
    g_server_pcb = tcp_listen(g_server_pcb);
    if (!g_server_pcb) { FW_ERR_PRINTF("[ERROR] listen failed\n\r"); return -1; }
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
        FW_ERR_PRINTF("[WM] rejected: no PKT_CONFIG on this connection\n\r");
        conn->watermark_size = 0;
        return -1;
    }
    /* 【修订 B1】原实现是 `if (len > MAX) len = MAX;` —— 静默截断。
       MAX 当时还是 10120，比 81,000 bit 所需的 10,125 B 还小，
       尾部 40 bit 直接被丢掉，而上位机完全无从得知。 */
    if (len > MAX_WATERMARK_SIZE) {
        FW_ERR_PRINTF("[WM] ERROR: %u bytes exceeds MAX_WATERMARK_SIZE %u\n\r",
                   len, (u32)MAX_WATERMARK_SIZE);
        conn->watermark_size = 0;
        return -1;
    }
    if (len < WM_PACKED_BYTES) {
        FW_ERR_PRINTF("[WM] ERROR: %u bytes < required %u (%u bits)\n\r",
                   len, (u32)WM_PACKED_BYTES, (u32)WM_TOTAL_BITS);
        conn->watermark_size = 0;
        return -1;
    }
    memcpy((void *)DDR_WATERMARK_BASE, data, len);
    PROF_CACHE_FLUSH(DDR_WATERMARK_BASE, len);
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
        FW_ERR_PRINTF("[WM] ERROR: watermark not loaded (%u bytes)\n\r",
                   conn->watermark_size);
        return -1;
    }

    PROF_CACHE_INVALIDATE(DDR_WATERMARK_BASE, conn->watermark_size);

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

    PROF_CACHE_FLUSH(DDR_WM_REGIONS_BASE, WM_REGIONS_TOTAL_BYTES);
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
        FW_ERR_PRINTF("[BATCH] rejected: no PKT_CONFIG on this connection\n\r");
        return -1;
    }
    if (len < 4u) {
        FW_ERR_PRINTF("[BATCH] invalid payload: %u bytes\n\r", len);
        return -1;
    }
    u32 num_reads = (data[0]<<24)|(data[1]<<16)|(data[2]<<8)|data[3];
    if (num_reads == 0u || num_reads > (len - 4u) / READ_SIZE_BYTES) {
        FW_ERR_PRINTF("[BATCH] invalid read count %u for payload %u\n\r",
                   num_reads, len);
        return -1;
    }
    u32 data_size = num_reads * READ_SIZE_BYTES;
    if (len != 4u + data_size) {
        FW_ERR_PRINTF("[BATCH] size mismatch: payload=%u expected=%u\n\r",
                   len, 4u + data_size);
        return -1;
    }

    /* 【C3】容量防溢出：DDR 只预留了 TOTAL_READS 条的空间；
     * 【P3】也不得超过声明的本任务条数 */
    if (conn->total_reads_received + num_reads > TOTAL_READS) {
        FW_ERR_PRINTF("[BATCH] ✗ capacity exceeded: %u + %u > %u\n\r",
                   conn->total_reads_received, num_reads, (u32)TOTAL_READS);
        return -1;
    }
    if (conn->total_reads_received + num_reads > conn->cfg.total_reads) {
        FW_ERR_PRINTF("[BATCH] ✗ exceeds declared total_reads: %u + %u > %u\n\r",
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
        FW_ERR_PRINTF("[POST] rejected: no PKT_CONFIG on this connection\n\r");
        if (conn->tpcb) send_ack_byte(conn->tpcb, PKT_ERROR);
        return;
    }
    if (conn->total_reads_received == 0 || conn->watermark_size == 0) {
        FW_ERR_PRINTF("[POST] No data\n\r");
        if (conn->tpcb) send_ack_byte(conn->tpcb, PKT_ERROR);
        return;
    }
    /* 【P3】声明条数与实际收到的必须一致 */
    if (conn->total_reads_received != conn->cfg.total_reads) {
        FW_ERR_PRINTF("[POST] ✗ count mismatch: declared %u, received %u\n\r",
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
        FW_ERR_PRINTF("[POST] ✗ DDR layout validation failed (rc=%d, reads=%u)\n\r",
                   layout_rc, conn->total_reads_received);
        FW_ERR_PRINTF("[POST]    -1=空任务 -2=非64整数倍(补零缺失) "
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
    PROF_TIME_BEGIN(sendres);
    u32 result_size = DECODER_OUTPUT_BYTES; /* 64800 (或 SE150 的 8100) */
    xil_printf("\n\r[RESULT] Sending %u bytes (initial sndbuf=%u)\n\r",
               result_size, tcp_sndbuf(conn->tpcb));

    /* 【B29 根除加固】发送前主动刷新 ARP，防止长时间计算后 ARP 老化导致首包丢弃 */
    if (conn->tpcb) {
        arp_keepalive(&conn->tpcb->remote_ip);
        usleep(2000);
    }

    u8 header[8];
    header[0] = (PROTOCOL_MAGIC >> 8) & 0xFF;
    header[1] = PROTOCOL_MAGIC & 0xFF;
    header[2] = PKT_RESULT;
    header[3] = 0;
    header[4] = (result_size >> 24) & 0xFF;
    header[5] = (result_size >> 16) & 0xFF;
    header[6] = (result_size >> 8) & 0xFF;
    header[7] = (result_size) & 0xFF;

    u32 hdr_retry_cnt = 0;
    /* 头 */
    for (;;) {
        err_t e = tcp_write(conn->tpcb, header, 8, TCP_WRITE_FLAG_COPY);
        if (e == ERR_OK) break;
        if (e == ERR_MEM || e == ERR_WOULDBLOCK) {
            hdr_retry_cnt++;
            if ((hdr_retry_cnt % 100u) == 1u) {
                xil_printf("[RESULT][B29-DIAG] Header retry #%u (err=%d, sndbuf=%u)\n\r",
                           hdr_retry_cnt, e, tcp_sndbuf(conn->tpcb));
            }
            tcp_output(conn->tpcb);
            keep_tcp_alive();
            usleep(1000);
            continue;
        }
        FW_ERR_PRINTF("[ERROR] Header write failed: %d\n\r", e);
        PROF_SEND_RESULT_END(sendres, 0U);
        return;
    }
    tcp_output(conn->tpcb);

    /* 正文：从 DDR_DECODER_OUT_BASE 连续发送结果字节 */
    u32 sent = 0;
    u32 data_retry_cnt = 0;
    u32 sndbuf_zero_cnt = 0;
    while (sent < result_size) {
        u16 snd_avail = tcp_sndbuf(conn->tpcb);
        if (snd_avail == 0) {
            sndbuf_zero_cnt++;
            if ((sndbuf_zero_cnt % 100u) == 1u) {
                xil_printf("[RESULT][B29-DIAG] Wait sndbuf retry #%u @%u/%u\n\r",
                           sndbuf_zero_cnt, sent, result_size);
            }
            tcp_output(conn->tpcb);
            keep_tcp_alive();
            usleep(1000);
            continue;
        }
        u32 remain = result_size - sent;
        u32 to_send = (remain < snd_avail) ? remain : snd_avail;
        if (to_send > 1460) to_send = 1460;

        err_t e = tcp_write(conn->tpcb, (void *)(DDR_DECODER_OUT_BASE + sent), to_send, TCP_WRITE_FLAG_COPY);
        if (e == ERR_OK) {
            sent += to_send;
            if ((sent & 0x7FF) == 0) { tcp_output(conn->tpcb); keep_tcp_alive(); }
        } else if (e == ERR_MEM || e == ERR_WOULDBLOCK) {
            data_retry_cnt++;
            if ((data_retry_cnt % 100u) == 1u) {
                xil_printf("[RESULT][B29-DIAG] Data write retry #%u @%u/%u (err=%d, sndbuf=%u)\n\r",
                           data_retry_cnt, sent, result_size, e, tcp_sndbuf(conn->tpcb));
            }
            tcp_output(conn->tpcb);
            keep_tcp_alive();
            usleep(1000);
        } else {
            FW_ERR_PRINTF("[ERROR] Data write failed: %d @%u\n\r", e, sent);
            PROF_SEND_RESULT_END(sendres, sent);
            return;
        }
    }
    tcp_output(conn->tpcb);
    /* 【B29 澄清】sent 为 tcp_write 入队成功计数，非对端接收 ACK 计数；记录重试与余量以备排查 */
    xil_printf("[RESULT] Enqueued %u bytes (retries: hdr=%u, data=%u, sndbuf_zero=%u, sndbuf_avail=%u)\n\r",
               sent, hdr_retry_cnt, data_retry_cnt, sndbuf_zero_cnt, tcp_sndbuf(conn->tpcb));

    /* 【B29 根除加固】等待发送队列中的数据被物理发送并确认（最多等 2000ms） */
    int wait_ack_cycles = 0;
    while (conn->tpcb != NULL &&
           (conn->tpcb->unsent != NULL || conn->tpcb->unacked != NULL) &&
           wait_ack_cycles < 2000) {
        tcp_output(conn->tpcb);
        keep_tcp_alive();
        usleep(1000);
        wait_ack_cycles++;
    }
    const int delivery_settled =
        conn->tpcb != NULL && conn->tpcb->unsent == NULL && conn->tpcb->unacked == NULL;
    xil_printf("[RESULT] Delivery settled after %d ms (unsent=%d, unacked=%d)\n\r",
               wait_ack_cycles,
               (conn->tpcb && conn->tpcb->unsent) ? 1 : 0,
               (conn->tpcb && conn->tpcb->unacked) ? 1 : 0);

    if (!delivery_settled) {
        FW_ERR_PRINTF("[ERROR] Result delivery timeout; refusing to report success\n\r");
        PROF_SEND_RESULT_END(sendres, sent);
        return;
    }
    conn->state = STATE_IDLE;
    PROF_SEND_RESULT_END(sendres, sent);
}

/* validate_decoder_written_beats 已迁至 stage3_decoder.{c,h} */
