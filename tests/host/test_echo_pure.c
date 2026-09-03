/******************************************************************************
 * test_echo_pure.c — sw/app/echo.c 里**纯逻辑**部分的主机单元测试
 *
 * 被测对象是真实固件源码本身（见 echo_under_test.h：整份 #include "echo.c"），
 * 不是它的一份抄写。抄一份来测，测的是抄件，对 echo.c 的回归零鉴别力。
 *
 * 覆盖：
 *   A. parse_header        协议头解析：magic / 大端长度 / 失败时的副作用
 *   B. align_down/min_u32  BD 长度对齐的小工具
 *   C. board_caps          能力值必须与 docs/05-interfaces.md 1.3 节一致
 *   D. process_batch       条数/长度/容量/声明数的四类边界
 *   E. process_config      **连接层**的拒绝码 8/9（task_config.h 不判这两个）
 *   F. process_post        进流水线前的 DDR 布局校验拒绝
 *   G. expand_watermark_regions  黄金向量：50×957 个符号逐个相同
 *   H. apply_watermark_differential  共识 ⊕ 水印，含「只动前 10,125 B」
 *   I. validate_decoder_written_beats  哨兵计数
 *   J. run_processing_pipeline 的状态分派：**PIPE_SEND_RESULT 落在所有区间之外**
 *
 * 用法：  test_echo_pure <tests/golden 目录>
 ******************************************************************************/
#include "echo_under_test.h"

static int g_fail = 0;
static const char *g_golden_dir = "tests/golden";

static void ok(int cond, const char *fmt, ...)
{
    va_list ap;
    printf(cond ? "  ✓ " : "  ✗ ");
    va_start(ap, fmt); vprintf(fmt, ap); va_end(ap);
    printf("\n");
    if (!cond) g_fail++;
}

static void section(const char *s) { printf("\n-- %s\n", s); }

/*=========================== A. parse_header ==============================*/
static void t_parse_header(void)
{
    u8 buf[8];
    u16 magic; u8 type; u32 len;

    section("A. parse_header：协议头解析");

    /* 合法头：magic=0xBEEF, type=0x02, 长度大端 */
    buf[0]=0xBE; buf[1]=0xEF; buf[2]=0x02; buf[3]=0x00;
    buf[4]=0x00; buf[5]=0x01; buf[6]=0x02; buf[7]=0x03;
    ok(parse_header(buf,&magic,&type,&len)==0, "合法头返回 0");
    ok(magic==0xBEEF && type==0x02 && len==0x00010203u,
       "magic=0x%04X type=0x%02X len=%u（大端 4 字节）", magic, type, len);

    /* buf[3] 是保留字节，不参与解析 —— 拆分时别顺手把它当长度高位 */
    buf[3]=0xFF;
    parse_header(buf,&magic,&type,&len);
    ok(len==0x00010203u, "buf[3] 不参与长度解析（置 0xFF 后 len 不变）");

    /* 长度上下边界 */
    buf[4]=buf[5]=buf[6]=buf[7]=0x00;
    parse_header(buf,&magic,&type,&len);
    ok(len==0u, "len=0 可解析");
    buf[4]=buf[5]=buf[6]=buf[7]=0xFF;
    parse_header(buf,&magic,&type,&len);
    ok(len==0xFFFFFFFFu, "len=0xFFFFFFFF 不溢出/不截断");

    /* magic 错：返回 -1，但**输出参数仍已被写入** —— recv_callback 的逐字节
     * 重同步循环依赖「返回值」而不是输出值，拆分时不要改成「失败不写出参」 */
    buf[0]=0xDE; buf[1]=0xAD; buf[2]=0x77;
    ok(parse_header(buf,&magic,&type,&len)==-1, "magic 错返回 -1");
    ok(magic==0xDEAD && type==0x77, "失败路径仍写出参（magic=0x%04X type=0x%02X）",
       magic, type);

    /* 差一位也必须拒绝 */
    buf[0]=0xBE; buf[1]=0xEE;
    ok(parse_header(buf,&magic,&type,&len)==-1, "magic 0xBEEE（差 1）被拒绝");
    buf[0]=0xBF; buf[1]=0xEF;
    ok(parse_header(buf,&magic,&type,&len)==-1, "magic 0xBFEF（差 1）被拒绝");
}

/*=========================== B. 小工具 ====================================*/
static void t_align(void)
{
    section("B. align_down / min_u32：BD 长度对齐");
    ok(align_down(16383u,8u)==16376u,
       "align_down(16383,8)=16376 —— 板上 B21 现场 ceil(196608/16376)=13 的那个 16376");
    ok(align_down(0u,8u)==0u,        "align_down(0,8)=0（会触发 per_bd 兜底）");
    ok(align_down(7u,8u)==0u,        "align_down(7,8)=0");
    ok(align_down(8u,8u)==8u,        "align_down(8,8)=8");
    ok(align_down(16384u,8u)==16384u,"align_down(16K,8)=16K");
    ok(min_u32(3u,5u)==3u && min_u32(5u,3u)==3u && min_u32(4u,4u)==4u, "min_u32 三种情形");
}

/*=========================== C. board_caps ================================*/
static void t_caps(void)
{
    task_caps_t c = board_caps();
    section("C. board_caps：必须与 docs/05-interfaces.md 1.3 节一致");
    ok(c.version==1,            "version=1");
    ok(c.read_bps==150,         "read_bps=150（SE150，SE250 不可混用）");
    ok(c.num_lc==50,            "num_lc=50");
    ok(c.stride==807,           "stride=807");
    ok(c.max_symbols==40500u,   "max_symbols=40500 = 50*807+150");
    ok(c.max_reads==107968u,    "max_reads=107968 = 64*1687（容量内最大 64 对齐条数）");
    ok(c.features==1u,          "features bit0=1（SCORE_MIN 可用）");
    ok(c.max_symbols == c.num_lc*c.stride + c.read_bps,
       "契约 L = num_lc*stride + read_bps 自洽");
}

/*=========================== 协议辅助 =====================================*/
static u8  g_pkt[200000];
static void conn_fresh(dna_connection_t *conn)
{
    memset(conn, 0, sizeof *conn);
    conn->tpcb = host_tcp_client();
    conn->tpcb->closed = 0;
    conn->tpcb->sndbuf = 8192;
    host_tcp_txbuf_reset();
}
static void conn_configure(dna_connection_t *conn, u32 total_reads, u32 score_min)
{
    u8 p[TASK_CONFIG_PAYLOAD_LEN];
    task_config_t c = { 1, 150, 50, 807, 40500u, total_reads, score_min };
    task_config_serialize(&c, p);
    process_config(conn, p, sizeof p);
}
/* 取最后一个 PKT_CONFIG_OK 帧里的 4B 状态码；没有则返回 (u32)-1 */
static u32 last_config_code(void)
{
    unsigned long n; const u8 *b = host_tcp_txbuf(&n);
    for (long i = (long)n - 12; i >= 0; i--)
        if (b[i]==0xBE && b[i+1]==0xEF && b[i+2]==PKT_CONFIG_OK)
            return ((u32)b[i+8]<<24)|((u32)b[i+9]<<16)|((u32)b[i+10]<<8)|b[i+11];
    return (u32)-1;
}
static int last_byte_is(u8 v)
{
    unsigned long n; const u8 *b = host_tcp_txbuf(&n);
    return n > 0 && b[n-1] == v;
}

/*=========================== D. process_batch =============================*/
static void t_batch(void)
{
    dna_connection_t conn;
    section("D. process_batch：条数 / 长度 / 容量 / 声明数");

    conn_fresh(&conn);
    ok(process_batch(&conn, g_pkt, 4u + READ_SIZE_BYTES) == -1,
       "未 CONFIG 直接拒绝（强制 CONFIG）");

    conn_fresh(&conn); conn_configure(&conn, 128u, 67u);
    ok(conn.configured == 1, "CONFIG 被接受（前置条件）");

    ok(process_batch(&conn, g_pkt, 3u) == -1, "payload < 4 B 拒绝");

    memset(g_pkt, 0, sizeof g_pkt);
    wr_u32_be(g_pkt, 0u);
    ok(process_batch(&conn, g_pkt, 4u) == -1, "num_reads=0 拒绝");

    wr_u32_be(g_pkt, 2u);
    ok(process_batch(&conn, g_pkt, 4u + 2u*READ_SIZE_BYTES - 1u) == -1,
       "声明 2 条但负载少 1 B 拒绝");
    ok(process_batch(&conn, g_pkt, 4u + 2u*READ_SIZE_BYTES + 1u) == -1,
       "声明 2 条但负载多 1 B 拒绝（长度必须精确相等）");
    ok(process_batch(&conn, g_pkt, 4u + 2u*READ_SIZE_BYTES) == 0,
       "声明 2 条、负载 4+80 B 接受");
    ok(conn.total_reads_received == 2u, "累计条数 = 2");

    /* 超出本任务声明的 total_reads（128）→ 拒绝，且计数不变 */
    wr_u32_be(g_pkt, 127u);
    ok(process_batch(&conn, g_pkt, 4u + 127u*READ_SIZE_BYTES) == -1,
       "2+127 > 声明的 128 → 拒绝");
    ok(conn.total_reads_received == 2u, "拒绝后累计条数不变（无副作用）");
    wr_u32_be(g_pkt, 126u);
    ok(process_batch(&conn, g_pkt, 4u + 126u*READ_SIZE_BYTES) == 0, "2+126 = 128 恰好接受");
    ok(conn.total_reads_received == 128u, "累计条数 = 128");

    /* 容量上限：TOTAL_READS = 108000 */
    conn_fresh(&conn); conn_configure(&conn, 107968u, 0u);
    conn.total_reads_received = TOTAL_READS - 1u;
    wr_u32_be(g_pkt, 2u);
    ok(process_batch(&conn, g_pkt, 4u + 2u*READ_SIZE_BYTES) == -1,
       "越过 DDR 预留容量 TOTAL_READS=%u → 拒绝", (u32)TOTAL_READS);
}

/*=========================== E. process_config 的 8/9 =====================*/
static void t_config_conn_codes(void)
{
    dna_connection_t conn;
    section("E. process_config：连接层拒绝码 8/9（task_config.h 不判这两个）");

    conn_fresh(&conn);
    conn_configure(&conn, 128u, 67u);
    ok(last_config_code() == 0u, "首次 CONFIG → 状态码 0（接受）");

    conn_configure(&conn, 128u, 67u);
    ok(last_config_code() == 8u, "同一连接再次 CONFIG → 拒绝码 8（重复配置）");

    conn_fresh(&conn);
    conn.watermark_size = 10125u;          /* 数据先到、CONFIG 后到 */
    conn_configure(&conn, 128u, 67u);
    ok(last_config_code() == 9u, "已收数据后才 CONFIG → 拒绝码 9（顺序非法）");
    ok(conn.configured == 0, "拒绝时不得置 configured");

    conn_fresh(&conn);
    process_config(&conn, g_pkt, TASK_CONFIG_PAYLOAD_LEN - 1u);
    ok(last_byte_is(PKT_ERROR), "负载长度不等于 44 B → 裸 PKT_ERROR（不带包头）");

    conn_fresh(&conn);
    { u8 p[TASK_CONFIG_PAYLOAD_LEN];
      task_config_t c = { 1, 150, 50, 807, 40500u, 128u, 67u };
      task_config_serialize(&c, p);
      p[40] ^= 0x01;                        /* 破坏 CRC */
      process_config(&conn, p, sizeof p);
      ok(last_config_code() == 7u, "CRC 被破坏 → 拒绝码 7"); }
}

/*=========================== F. process_post ==============================*/
static void t_post(void)
{
    dna_connection_t conn;
    section("F. process_post：进流水线前的布局校验");

    conn_fresh(&conn);
    process_post(&conn);
    ok(last_byte_is(PKT_ERROR) && g_proc_state == PROC_IDLE, "未 CONFIG → PKT_ERROR，不启动");

    conn_fresh(&conn); conn_configure(&conn, 128u, 67u);
    host_tcp_txbuf_reset();
    process_post(&conn);
    ok(last_byte_is(PKT_ERROR) && g_proc_state == PROC_IDLE, "没有数据 → PKT_ERROR，不启动");

    conn.watermark_size = WM_PACKED_BYTES;
    conn.total_reads_received = 64u;        /* 声明 128 实收 64 */
    host_tcp_txbuf_reset();
    process_post(&conn);
    ok(last_byte_is(PKT_ERROR) && g_proc_state == PROC_IDLE,
       "声明 128 实收 64 → PKT_ERROR，不启动");

    /* 非 64 整数倍：先让声明数与实收数一致，才轮得到布局校验 -2 */
    conn_fresh(&conn); conn_configure(&conn, 128u, 67u);
    conn.cfg.total_reads = 100u;            /* 绕过 CONFIG 的整帧校验，直击布局校验 */
    conn.watermark_size = WM_PACKED_BYTES;
    conn.total_reads_received = 100u;
    host_tcp_txbuf_reset();
    process_post(&conn);
    ok(last_byte_is(PKT_ERROR) && g_proc_state == PROC_IDLE,
       "100 条（非 64 整数倍）→ ddr_layout_validate 返回 -2，不启动");

    conn_fresh(&conn); conn_configure(&conn, 128u, 67u);
    conn.watermark_size = WM_PACKED_BYTES;
    conn.total_reads_received = 128u;
    host_tcp_txbuf_reset();
    process_post(&conn);
    ok(g_proc_state == PROC_REQUESTED && conn.state == STATE_PROCESSING,
       "全部合法 → PROC_REQUESTED（流水线由下一次 poll 启动）");
    g_proc_state = PROC_IDLE;
}

/*=========================== G. 水印展开（黄金向量）=======================*/
static void t_wm_expand(void)
{
    char path[512];
    FILE *f;
    dna_connection_t conn;
    unsigned long i, bad = 0, n = 0;
    const volatile u32 *dst = (const volatile u32 *)DDR_WM_REGIONS_BASE;

    section("G. expand_watermark_regions：对 tests/golden/wm_regions.hex 逐符号");

    snprintf(path, sizeof path, "%s/watermark_packed.bin", g_golden_dir);
    f = fopen(path, "rb");
    if (!f) { ok(0, "打不开 %s", path); return; }
    conn_fresh(&conn);
    conn.configured = 1;
    { size_t rd = fread((void *)DDR_WATERMARK_BASE, 1, MAX_WATERMARK_SIZE, f);
      fclose(f);
      conn.watermark_size = (u32)rd;
      ok(rd == WM_PACKED_BYTES, "打包水印 %lu B = WM_PACKED_BYTES(%u)",
         (unsigned long)rd, (u32)WM_PACKED_BYTES); }

    ok(expand_watermark_regions(&conn) == 0, "展开返回 0");

    snprintf(path, sizeof path, "%s/wm_regions.hex", g_golden_dir);
    f = fopen(path, "r");
    if (!f) { ok(0, "打不开 %s", path); return; }
    for (i = 0; i < (unsigned long)WM_NUM_LC * WM_REGION_SYMBOLS; i++) {
        unsigned g;
        if (fscanf(f, "%u", &g) != 1) break;
        n++;
        if ((unsigned)dst[i] != g && bad++ < 3)
            printf("      首个不符 @%lu：黄金 %u 实测 %u\n", i, g, (unsigned)dst[i]);
    }
    fclose(f);
    ok(n == (unsigned long)WM_NUM_LC * WM_REGION_SYMBOLS,
       "黄金向量 %lu 行 = 50×957", n);
    ok(bad == 0, "50×957 = 47,850 个符号逐个相同");

    /* 未加载水印时必须拒绝，不能拿脏 DDR 展开 */
    conn.watermark_size = WM_PACKED_BYTES - 1u;
    ok(expand_watermark_regions(&conn) == -1, "水印字节数不足 → 返回 -1");
}

/*=========================== H. 差分 ======================================*/
static void t_diff(void)
{
    volatile u8 *cons = (volatile u8 *)DDR_VOTER_OUT_BASE;
    const volatile u8 *wm = (const volatile u8 *)DDR_WATERMARK_BASE;
    u8 before[16];
    u32 i;
    int bad = 0;

    section("H. apply_watermark_differential：共识 ⊕ 水印");

    for (i = 0; i < VOTER_OUTPUT_BYTES + 16u; i++) cons[i] = (u8)(i * 31u + 7u);
    memcpy(before, (const void *)(cons + WM_PACKED_BYTES), 16);

    ok(apply_watermark_differential() == 0, "返回 0");
    for (i = 0; i < WM_PACKED_BYTES; i++)
        if (cons[i] != (u8)(((u8)(i * 31u + 7u)) ^ wm[i])) { bad++; break; }
    ok(bad == 0, "前 %u B 逐字节 = 原值 ⊕ 水印", (u32)WM_PACKED_BYTES);
    ok(memcmp(before, (const void *)(cons + WM_PACKED_BYTES), 16) == 0,
       "只动前 10,125 B：VOTER_OUTPUT_BYTES 之后的字节没被碰");

    /* 幂等性：再异或一次应回到原值 —— 拆分时若把这一级调用了两次，这里会红 */
    apply_watermark_differential();
    for (i = 0, bad = 0; i < WM_PACKED_BYTES; i++)
        if (cons[i] != (u8)(i * 31u + 7u)) { bad++; break; }
    ok(bad == 0, "异或两次回到原值（这一级被重复调用会被这条判据抓到）");
}

/*=========================== I. 哨兵计数 ==================================*/
static void t_sentinel(void)
{
    u64 *out = (u64 *)DDR_DECODER_OUT_BASE;
    u32 written = 0xDEADBEEFu;
    u32 i;

    section("I. validate_decoder_written_beats：哨兵计数");

    for (i = 0; i < 1013u; i++) out[i] = DECODER_SENTINEL_U64;
    validate_decoder_written_beats(DDR_DECODER_OUT_BASE, 1013u, &written);
    ok(written == 0u, "全是哨兵 → 已写 0 拍");

    out[0] = 0ULL;                       /* 「写了，但值是 0」也算已写 —— B22 教训 */
    validate_decoder_written_beats(DDR_DECODER_OUT_BASE, 1013u, &written);
    ok(written == 1u, "写入 0 也算已写（0 不能当「未写」，这正是 B22 第 2 条的错）");

    for (i = 0; i < 1013u; i++) out[i] = 0x1234ULL;
    validate_decoder_written_beats(DDR_DECODER_OUT_BASE, 1013u, &written);
    ok(written == 1013u, "全部覆盖 → 1013 拍");
}

/*=========================== J. 状态分派 ==================================*/
static void t_dispatch(void)
{
    dna_connection_t conn;
    section("J. run_processing_pipeline 的状态分派（区间判断）");

    memset(&conn, 0, sizeof conn);
    conn.tpcb = host_tcp_client();

    ok(PIPE_SEND_RESULT > PIPE_DONE_STAGE1 && PIPE_SEND_RESULT > PIPE_DONE_STAGE2 &&
       PIPE_SEND_RESULT < PIPE_DECODER_PREP,
       "枚举顺序：PIPE_SEND_RESULT 夹在 DONE_STAGE2 与 DECODER_PREP 之间");

    /* 三个区间是 [IDLE,DONE_STAGE1] / [VOTER_PREP,DONE_STAGE2] /
     * [DECODER_PREP,DONE_STAGE3]，PIPE_SEND_RESULT 一个都不落在里面 →
     * 一旦真的走到这个状态，run_processing_pipeline 直接判 FAIL。
     * 当前固件靠「DECODER_WAIT 里 DONE 置位就把 g_proc_state 推成 PROC_DONE」
     * 绕开了它，所以这条路径在板上从没被走到过。拆分时若改动
     * poll_callback 与 DONE_STAGE3 的先后，就会掉进来。 */
    pipe_state = PIPE_SEND_RESULT;
    ok(run_processing_pipeline(&conn) == XST_FAILURE,
       "pipe_state=PIPE_SEND_RESULT → 落在所有区间之外，直接 XST_FAILURE");
    ok(pipe_state == PIPE_FAIL, "并把状态推成 PIPE_FAIL");

    pipe_state = PIPE_FAIL;
    ok(run_processing_pipeline(&conn) == XST_FAILURE, "pipe_state=PIPE_FAIL → XST_FAILURE");

    pipe_state = PIPE_IDLE;
}

int main(int argc, char **argv)
{
    if (argc > 1) g_golden_dir = argv[1];
    host_env_init();
    host_trace_enable(0);          /* 单元测试不需要轨迹 */

    printf("== echo.c 纯逻辑单元测试（被测对象是真实固件源码本身）==\n");
    t_parse_header();
    t_align();
    t_caps();
    t_batch();
    t_config_conn_codes();
    t_post();
    t_wm_expand();
    t_diff();
    t_sentinel();
    t_dispatch();

    printf("\n--------------------------------------------------\n");
    if (g_fail == 0) printf("✓ PASS  echo.c 纯逻辑全部判据通过\n");
    else             printf("✗ FAIL  %d 项不符\n", g_fail);
    host_env_fini();
    return g_fail ? 1 : 0;
}
