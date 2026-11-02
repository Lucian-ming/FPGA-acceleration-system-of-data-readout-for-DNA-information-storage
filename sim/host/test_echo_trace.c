/******************************************************************************
 * test_echo_trace.c — 「行为等价」判据：把整条流水线跑一遍，逐行比对行为轨迹
 *
 * 为什么需要它：2,206 行的 echo.c 要拆成多个模块，如果没有「拆完之后行为没变」
 * 的判据，出了问题只能靠上板试 —— 那正是 B22/B27 的产生方式。
 *
 * 判据是什么：本测试驱动**真实固件**走完
 *     accept → CONFIG → WM → BATCH×2 → POST → 100+ 次 poll → 回传结果
 * 并把每一个**对外可见的效应**按发生顺序记成一行文本：
 *     REGW/REGR（AXI-Lite 寄存器读写，含值）
 *     SLEEP    （usleep，"写 0 → 写 1 → usleep → 写 0" 里的那一段）
 *     CACHE    （invalidate / flush 的地址与长度）
 *     DMA      （BD 环创建/投递/回收）
 *     TCP      （tcp_write / tcp_output 的字节数与顺序）
 *     NETIF    （keep_tcp_alive 的位置）
 * 拆分前后这份轨迹必须**逐行相同**。日志文本刻意不在其中：措辞可以改，行为不行。
 *
 * 用法：
 *   test_echo_trace <golden 目录> <黄金轨迹文件> [--record]
 *     --record  重录黄金轨迹（只在**有意**改变行为之后用，并说明理由）
 ******************************************************************************/
#include "echo_under_test.h"

#define TASK_READS   128u          /* 2 帧 × 64 条：够覆盖滚动补投与两次 chunk */
#define TASK_SCORE   67u
#define MAX_POLLS    400

static int g_fail = 0;
static const char *g_golden_dir = "../sim/golden";

static void ok(int cond, const char *fmt, ...)
{
    va_list ap;
    printf(cond ? "  ✓ " : "  ✗ ");
    va_start(ap, fmt); vprintf(fmt, ap); va_end(ap);
    printf("\n");
    if (!cond) g_fail++;
}

/*==== 把一个完整的协议包喂进 recv_callback（走真实的收包/分帧路径）========*/
static u8 g_pkt[1 << 17];

static void feed_packet(struct tcp_pcb *pcb, u8 type, const u8 *payload, u32 len)
{
    struct pbuf p;
    g_pkt[0] = (PROTOCOL_MAGIC >> 8) & 0xFF;
    g_pkt[1] = PROTOCOL_MAGIC & 0xFF;
    g_pkt[2] = type;
    g_pkt[3] = 0;
    g_pkt[4] = (u8)(len >> 24); g_pkt[5] = (u8)(len >> 16);
    g_pkt[6] = (u8)(len >> 8);  g_pkt[7] = (u8)len;
    if (len) memcpy(g_pkt + PROTOCOL_HDR_SIZE, payload, len);

    memset(&p, 0, sizeof p);
    p.payload = g_pkt;
    p.tot_len = (u16)(PROTOCOL_HDR_SIZE + len);
    p.len     = p.tot_len;
    recv_callback(pcb->cb_arg, pcb, &p, ERR_OK);
}

static u8 g_wm[MAX_WATERMARK_SIZE];
static u8 g_batch[4 + 64u * READ_SIZE_BYTES];

static int load_watermark(void)
{
    char path[512]; FILE *f; size_t n;
    snprintf(path, sizeof path, "%s/watermark_packed.bin", g_golden_dir);
    f = fopen(path, "rb");
    if (!f) { printf("  ✗ 打不开 %s\n", path); return -1; }
    n = fread(g_wm, 1, sizeof g_wm, f);
    fclose(f);
    return (n == WM_PACKED_BYTES) ? (int)n : -1;
}

/* 确定性读段数据：内容不进判据，但必须每次都一样，否则轨迹不可复现 */
static void fill_batch(unsigned frame)
{
    wr_u32_be(g_batch, 64u);
    for (unsigned r = 0; r < 64u; r++)
        for (unsigned b = 0; b < READ_SIZE_BYTES; b++)
            g_batch[4 + r * READ_SIZE_BYTES + b] =
                (u8)(frame * 173u + r * 37u + b * 11u + 5u);
}

/*==== 跑一次完整任务 ======================================================*/
typedef struct {
    int polls;
    int completed;          /* 走到 PROC_IDLE 且结果已发出 */
    int failed;             /* 走到 PROC_FAILED */
} run_result_t;

static run_result_t run_one_task(void)
{
    run_result_t rr = { 0, 0, 0 };
    struct tcp_pcb *pcb = host_tcp_client();
    u8 cfg[TASK_CONFIG_PAYLOAD_LEN];
    task_config_t c = { 1, 150, 50, 807, 40500u, TASK_READS, TASK_SCORE };
    int seen_done = 0;

    dna_accelerator_init();
    start_application();
    accept_callback(NULL, pcb, ERR_OK);

    task_config_serialize(&c, cfg);
    feed_packet(pcb, PKT_CONFIG, cfg, sizeof cfg);
    feed_packet(pcb, PKT_WM, g_wm, WM_PACKED_BYTES);
    for (unsigned f = 0; f < TASK_READS / 64u; f++) {
        fill_batch(f);
        feed_packet(pcb, PKT_BATCH, g_batch, sizeof g_batch);
    }
    feed_packet(pcb, PKT_POST, NULL, 0);

    for (rr.polls = 0; rr.polls < MAX_POLLS; rr.polls++) {
        proc_state_e before = g_proc_state;
        poll_callback(pcb->cb_arg, pcb);
        if (g_proc_state == PROC_FAILED) { rr.failed = 1; break; }
        if (before == PROC_DONE) { seen_done = 1; rr.completed = 1; break; }
        host_hw_tick();
    }
    (void)seen_done;
    return rr;
}

/*==== 结果检查 ============================================================*/
static void check_result_frame(void)
{
    unsigned long n; const u8 *b = host_tcp_txbuf(&n);
    long hdr = -1;
    /* 从尾部往回找 PKT_RESULT 帧头 */
    for (long i = (long)n - 8 - (long)DECODER_OUTPUT_BYTES; i >= 0; i--)
        if (b[i]==0xBE && b[i+1]==0xEF && b[i+2]==PKT_RESULT) { hdr = i; break; }

    ok(hdr >= 0, "回传里能找到 PKT_RESULT 帧头");
    if (hdr < 0) return;
    {
        u32 declared = ((u32)b[hdr+4]<<24)|((u32)b[hdr+5]<<16)|((u32)b[hdr+6]<<8)|b[hdr+7];
        ok(declared == DECODER_OUTPUT_BYTES,
           "帧头声明 %u B = DECODER_OUTPUT_BYTES(%u)", declared, (u32)DECODER_OUTPUT_BYTES);
        ok(n - (unsigned long)hdr == 8UL + DECODER_OUTPUT_BYTES,
           "帧头之后正好 %u B，不多不少", (u32)DECODER_OUTPUT_BYTES);
        ok(memcmp(b + hdr + 8, (const void *)(UINTPTR)DDR_DECODER_OUT_BASE,
                  DECODER_OUTPUT_BYTES) == 0,
           "回传字节 = DDR_DECODER_OUT_BASE 起 %u B，逐字节相同", (u32)DECODER_OUTPUT_BYTES);
    }
}

/*==== 主流程 ==============================================================*/
int main(int argc, char **argv)
{
    const char *golden_path = "../sim/host/golden/echo_trace_se150_128reads.txt";
    int record = 0;
    run_result_t rr;

    if (argc > 1) g_golden_dir = argv[1];
    if (argc > 2) golden_path  = argv[2];
    for (int i = 1; i < argc; i++) if (strcmp(argv[i], "--record") == 0) record = 1;

    printf("== echo.c 行为轨迹判据（SE150 / %u 条 / score_min=%u）==\n",
           TASK_READS, TASK_SCORE);

    host_env_init();
    if (load_watermark() < 0) { printf("✗ FAIL 水印黄金数据缺失\n"); return 1; }

    /* ---------- 1) 正常一轮：录制/比对轨迹 ---------- */
    host_hw_cfg.dec_mode = HOST_DEC_FIXED;
    host_trace_clear();
    host_trace_enable(1);
    rr = run_one_task();
    host_trace_enable(0);

    ok(!rr.failed, "流水线没有进 PROC_FAILED");
    ok(rr.completed, "%d 次 poll 内跑完整条流水线并发出结果", rr.polls);
    ok(host_wm_regions_loaded() == WM_NUM_LC,
       "水印预载覆盖全部 %u 个区域（B1：原实现只写进第 0 个）", (u32)WM_NUM_LC);
    ok(host_wm_region_len_ok(),
       "每个区域收到的符号数都等于 REF_LEN=%u", (u32)WM_REF_LEN);
    ok(host_dna_reads_fed() == TASK_READS,
       "喂进 DNA 核的读段 = %u 条", TASK_READS);
    ok(host_dna_records_made() == TASK_READS,
       "收回的 48 B 记录 = %u 条（B21：滚动补投，RX 环不能空）", TASK_READS);
    ok(!host_dna_stalled(),
       "全程没有因结果 FIFO 满而停摆（B21 的锁死机理）");
    ok(host_dec_start_pulses() == 1,
       "Decoder 只被启动 **1** 次");
    ok(host_dec_start_writes() == 5,
       "但固件对 DECODER_REG_START 一共写了 5 次（PREP 两次 0、START 一次 1、"
       "WAIT 里 DONE 后一次 0、Stage3 收尾 decoder_reset_regs() 与 "
       "decoder_confirm_idle_zero() 各一次 0）：**正确性靠 RTL 只认 wdata[0]=1 "
       "且忙时不接受**。拆分时这 5 次写的**次数与顺序**都不许动 —— 这就是 B27。"
       "⚠️ 2026-10-16：原为 4 次，收尾清理（decoder_reset_regs / "
       "decoder_confirm_idle_zero）加入后为 5 次；写序的**逐行**约束由本文件末尾的"
       "行为轨迹判据承担（它把全部寄存器写的顺序钉死），此处只作计数快检");
    check_result_frame();

    if (record) {
        if (host_trace_write(golden_path) != 0) {
            printf("  ✗ 写不了 %s\n", golden_path); g_fail++;
        } else {
            printf("  ● 已重录黄金轨迹 %s（%lu 行）\n", golden_path, host_trace_lines());
        }
    } else {
        g_fail += host_trace_compare(golden_path, "行为轨迹");
    }

    /* ---------- 2) 鉴别力自证：把 B27 那版 RTL 语义放回去 ----------
     * 固件对 DECODER_REG_START 写了不止一次（PREP 里两次 0、START 一次 1、
     * WAIT 里 DONE 后一次 0）。在「对 START 写任何值都启动」的旧 RTL 下，
     * 这些写会把核重启。本段证明：这条判据**能失败**。 */
    printf("\n-- 鉴别力自证：把 B27 那版 Decoder RTL 语义放回去 --\n");
    host_env_init();
    host_hw_cfg.dec_mode = HOST_DEC_LEGACY;
    host_trace_enable(0);
    load_watermark();
    rr = run_one_task();
    ok(host_dec_start_writes() == 1 && host_dec_start_pulses() == 1,
       "旧语义下：PREP 里那句 `write START=0x00` **本身**就把核启动了"
       "（写 %d 次、启动 %d 次，写的值是 0）",
       host_dec_start_writes(), host_dec_start_pulses());
    ok(rr.failed && !rr.completed,
       "于是 `Status before config` 读回非 IDLE，流水线在 STAGE3 PREP 就失败 —— "
       "判据有鉴别力，不是恒绿");

    printf("\n--------------------------------------------------\n");
    if (g_fail == 0) printf("✓ PASS  行为轨迹判据通过\n");
    else             printf("✗ FAIL  %d 项不符\n", g_fail);
    host_env_fini();
    return g_fail ? 1 : 0;
}
