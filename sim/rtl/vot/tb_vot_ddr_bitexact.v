// =============================================================
// tb_vot_ddr_bitexact.v — Stage2 Voter 的「真实 DDR / 真实 AXI 主口 +
//                          固件原样寄存器时序」级判据
//
// 【为什么要这条 TB】（docs/06-verification-plan.md的AXI读通路判据）
// Voter 已有的判据全都不走真实 DDR：
//   * hw/ip/differential_voter_1_0/hdl/tb_differential_voter.v 的从机太温柔——
//     ARREADY 恒为 1、AR 到首拍 R 零延迟、突发中间没有空档、WREADY 恒为 1、
//     B 响应固定 1 拍；而且只写一次 START=1，没有回放固件那串写序列；
//   * M3 的 BD-3ext 虽然逐位通过，但内存端点是 AXI VIP 内存模型
//     （docs/archive/history/2026/m3-bd-simulation-2026-08-29.md的HP0仿真缺陷 已注明），不是「PS 用 CPU 写 DDR → Voter 用 AXI 主口读 DDR」。
// B27 的教训正是：Decoder 喂 VIP 内存连综合后网表都 PASS，板上照样 49.46% 误码。
// 2026-08-29~30 修掉的 7 个缺陷里有 5 个在所有仿真里都是绿的，全落在这条缝上。
//
// 因此本 TB：
//   * 用真实 DUT（differential_voter_v1_0，含 axi_slave_voter），不复制逻辑；
//   * **一片共享 DDR**：输入区 0x1060_0000（Stage1 输出）与输出区 0x1100_0000
//     （Stage2 输出）在同一个数组里，用板上真实地址寻址。PS 侧先把
//     ../sim/golden/stage2_in.hex 写进输入区、把输出区填成固件的哨兵值，
//     然后 Voter 用自己的 AXI 主口去读同一片内存——Voter 若把结果写回输入区、
//     或读到区外，都会被抓住，而不是像分离数组那样被下标掩盖；
//   * 从机模型像真 DDR：AR/AW 有延迟且随机撤 READY、R 拍有随机空档、
//     偶发长停顿（模拟刷新）、W/B 有背压和时延，**已接受的读突发一定把
//     ARLEN+1 拍发完**，不因主机被重启/被写 START 而取消；
//   * 逐条回放 sw/app/echo.c 的寄存器时序（含 DONE 清除、配置回读校验、
//     以及 START=1 之后 100 us 又写一次 START=0 那一笔）；
//   * 逐拍逐位比对输出，显式 PASS/FAIL。
//
// 【判据纪律】docs/06-verification-plan.md的故障鉴别力要求：编译通过、跑完、有波形都不算 PASS。
// XSim 2022.2 的 $fatal 既不终止仿真也不让 xsim 非零退出，所以失败路径一律
// 显式 $finish，并用 if/else 保证失败时绝不打印 PASS；判据靠日志内容判定。
//
// 场景（默认全跑）：
//   1 fw-board-cfg    固件时序 + SCORE_MIN=67  -> ../sim/golden/stage2_expect.hex
//                     （= 第五次上板那一组参数）
//   2 fw-second-task  不复位，紧接着第二次任务（走固件的 DONE 清除通路），
//                     换 SCORE_MIN=0 -> ../sim/golden/stage2_rtl_expect.hex
//                     换阈值是有意的：两次任务用同一份输入时，「累加器没清零」
//                     **结构性地**不可观测——票的更新是 x <- clip(x ± 1)，对起始值
//                     单调不减，所以第一轮终值 v>0 => w>=v>0、v<0 => w<=v<0、
//                     v=0 => w=0，符号判决三种情况全不变，任何输入都抓不到。
//                     （别用「票数翻倍所以保号」解释：撞上 [-512,+511] 饱和后
//                     「翻倍」这个描述本身就不成立。推导见 docs/03-status.md。）
//                     换阈值后两轮的票集不同，残留才可观测。
//   3 fw-raw-score0   复位后单独跑 SCORE_MIN=0 -> stage2_rtl_expect.hex
//                     （给场景 2 做对照：区分「第二次任务坏了」和「score0 语义坏了」）
//   4 late-start0     START=1 之后 5 ms（投票途中）才写 START=0，必须无害
//   5 spurious-start  投票途中再写一次 START=1，必须被忽略且结果不变
//
// plusargs:
//   +input=<hex>       输入（默认 ../sim/golden/stage2_in.hex，4096 条 48B 记录）
//   +expect_thr=<hex>  SCORE_MIN=67 的期望（默认 ../sim/golden/stage2_expect.hex）
//   +expect_raw=<hex>  SCORE_MIN=0  的期望（默认 ../sim/golden/stage2_rtl_expect.hex）
//   +start0_ns=<int>   固件 START=1 之后隔多久写 START=0（默认 100000 = usleep(100)）
//   +late_ns=<int>     场景 4/5 的注入时刻（默认 5000000 = 5 ms）
//   +rseed / +wseed    读/写通道背压随机种子
//   +dump=<file>       把 DDR 输出区里 DUT 实际写出的内容导出
//   +inject=<name>     故障注入自检（none|c4|b20|rot），见文件末尾说明
// =============================================================
`timescale 1ns/1ps

module tb_vot_ddr_bitexact;

    // ---------------- 规模常量（与 sw/app/echo.h、黄金向量一致）----------------
    localparam integer NUM_RECORDS   = 4096;              // make_golden.py --limit 2048 x 正反向
    localparam integer WORDS_PER_REC = 6;                 // 每条记录 72 B (9 拍 x 64 bit)
    localparam integer IN_WORDS      = NUM_RECORDS * WORDS_PER_REC;   // 36864
    localparam integer OUT_BEATS     = 1266;              // ceil(81000/64)
    localparam integer OUT_BITS      = 81000;
    localparam integer LAST_BITS     = OUT_BITS - 64*(OUT_BEATS-1);   // 40

    // 板上真实地址（sw/app/echo.h: DDR_DNA_ACC_OUT_BASE / DDR_VOTER_OUT_BASE）
    localparam [31:0] IN_ADDR  = 32'h1060_0000;
    localparam [31:0] OUT_ADDR = 32'h1100_0000;

    // 固件写在输出区的哨兵值（sw/app/echo.h DECODER_SENTINEL_U64）：
    // 没被 DUT 写过的拍留着哨兵，判据里「未被写入」因此可判。
    localparam [63:0] SENTINEL = 64'h0A55_AA55_AA55_AA55;

    // 寄存器偏移（axi_slave_voter；sw/app/echo.h VOTER_REG_*）
    localparam [6:0] REG_CTRL        = 7'h00;   // W: bit0 START, bit1 DONE_CLR / R: bit0 IDLE, bit1 DONE
    localparam [6:0] REG_IN_ADDR     = 7'h04;
    localparam [6:0] REG_IN_BEATS    = 7'h08;
    localparam [6:0] REG_OUT_ADDR    = 7'h0C;
    localparam [6:0] REG_OUT_BEATS   = 7'h10;
    localparam [6:0] REG_TOTAL_READS = 7'h14;
    localparam [6:0] REG_DBG_WRITE   = 7'h24;
    localparam [6:0] REG_DBG_AWADDR  = 7'h28;
    localparam [6:0] REG_ERR_FLAGS   = 7'h2C;
    localparam [6:0] REG_SCORE_MIN   = 7'h30;
    localparam [6:0] REG_LAST_RRESP  = 7'h38;

    // DUT 状态编码（用于「R 拍是否只在 S_READ_DATA 被消费」的判据）
    localparam [4:0] ST_INIT_BRAM = 5'd1;
    localparam [4:0] ST_READ_DATA = 5'd3;

    localparam integer SCORE_MIN_THR = 67;      // int(0.45*150)，与 make_golden.py 一致

    reg clk = 0, rstn = 0;
    always #5 clk = ~clk;                       // 100 MHz，与板上 FCLK0 相同

    // ---------------- AXI-Lite ----------------
    reg  [6:0]  s_awaddr;  reg s_awvalid;  wire s_awready;
    reg  [31:0] s_wdata;   reg [3:0] s_wstrb; reg s_wvalid; wire s_wready;
    wire [1:0]  s_bresp;   wire s_bvalid;  reg s_bready;
    reg  [6:0]  s_araddr;  reg s_arvalid;  wire s_arready;
    wire [31:0] s_rdata;   wire [1:0] s_rresp; wire s_rvalid; reg s_rready;

    // ---------------- AXI4 Master ----------------
    wire [31:0] m_awaddr;  wire [7:0] m_awlen;  wire m_awvalid;  reg m_awready;
    wire [63:0] m_wdata;   wire [7:0] m_wstrb;  wire m_wlast;
    wire        m_wvalid;  reg  m_wready;
    reg  [1:0]  m_bresp;   reg  m_bvalid;       wire m_bready;
    wire [31:0] m_araddr;  wire [7:0] m_arlen;  wire m_arvalid;  reg m_arready;
    reg  [63:0] m_rdata;   reg  [1:0] m_rresp;  reg m_rlast;     reg m_rvalid;
    wire        m_rready;
    wire [2:0]  m_arsize;  wire [1:0] m_arburst;
    wire [2:0]  m_awsize;  wire [1:0] m_awburst;

    differential_voter_v1_0 dut (
        .S00_AXI_ACLK(clk), .S00_AXI_ARESETN(rstn),
        .S00_AXI_AWADDR(s_awaddr), .S00_AXI_AWVALID(s_awvalid), .S00_AXI_AWREADY(s_awready),
        .S00_AXI_WDATA(s_wdata), .S00_AXI_WSTRB(s_wstrb),
        .S00_AXI_WVALID(s_wvalid), .S00_AXI_WREADY(s_wready),
        .S00_AXI_BRESP(s_bresp), .S00_AXI_BVALID(s_bvalid), .S00_AXI_BREADY(s_bready),
        .S00_AXI_ARADDR(s_araddr), .S00_AXI_ARVALID(s_arvalid), .S00_AXI_ARREADY(s_arready),
        .S00_AXI_RDATA(s_rdata), .S00_AXI_RRESP(s_rresp),
        .S00_AXI_RVALID(s_rvalid), .S00_AXI_RREADY(s_rready),

        .M00_AXI_ACLK(clk), .M00_AXI_ARESETN(rstn),
        .M00_AXI_AWADDR(m_awaddr), .M00_AXI_AWLEN(m_awlen), .M00_AXI_AWSIZE(m_awsize),
        .M00_AXI_AWBURST(m_awburst), .M00_AXI_AWLOCK(), .M00_AXI_AWCACHE(),
        .M00_AXI_AWPROT(), .M00_AXI_AWQOS(),
        .M00_AXI_AWVALID(m_awvalid), .M00_AXI_AWREADY(m_awready),
        .M00_AXI_WDATA(m_wdata), .M00_AXI_WSTRB(m_wstrb), .M00_AXI_WLAST(m_wlast),
        .M00_AXI_WVALID(m_wvalid), .M00_AXI_WREADY(m_wready),
        .M00_AXI_BRESP(m_bresp), .M00_AXI_BVALID(m_bvalid), .M00_AXI_BREADY(m_bready),
        .M00_AXI_ARADDR(m_araddr), .M00_AXI_ARLEN(m_arlen), .M00_AXI_ARSIZE(m_arsize),
        .M00_AXI_ARBURST(m_arburst), .M00_AXI_ARLOCK(), .M00_AXI_ARCACHE(),
        .M00_AXI_ARPROT(), .M00_AXI_ARQOS(),
        .M00_AXI_ARVALID(m_arvalid), .M00_AXI_ARREADY(m_arready),
        .M00_AXI_RDATA(m_rdata), .M00_AXI_RRESP(m_rresp), .M00_AXI_RLAST(m_rlast),
        .M00_AXI_RVALID(m_rvalid), .M00_AXI_RREADY(m_rready)
    );

    // =========================================================
    // 一片共享 DDR：输入区与输出区用板上真实地址落在同一个数组里。
    // 索引 = (地址 - IN_ADDR) >> 3；两区之间的 10 MB 空洞保持 X，
    // DUT 若读到那里会把 X 带进码字，逐位比较必然失败（不屏蔽 X）。
    // =========================================================
    localparam integer OUT_OFF   = (OUT_ADDR - IN_ADDR) >> 3;      // 1,310,720
    localparam integer DDR_WORDS = OUT_OFF + OUT_BEATS + 64;

    reg [63:0] ddr     [0:DDR_WORDS-1];
    reg        wr_seen [0:OUT_BEATS+63];      // 输出窗口内每拍是否被 DUT 写过
    reg [7:0]  wr_strb [0:OUT_BEATS+63];      // 该拍的 WSTRB，用于末拍掩码判据

    reg [63:0] expect_thr [0:OUT_BEATS-1];    // SCORE_MIN=67 期望
    reg [63:0] expect_raw [0:OUT_BEATS-1];    // SCORE_MIN=0  期望

    // =========================================================
    // 故障注入（docs/06-verification-plan.md的故障鉴别力要求：每条判据必须自证有鉴别力）
    //   c4  第二次任务的 BRAM 清零被压制（force bram_we=0 @ S_INIT_BRAM）
    //       —— 复现缺陷 C4「二次任务复用旧累加器」
    //   b20 读突发长度强行退回「每条记录固定 6 拍、从不按 4KB 页拆分」
    //       —— 复现缺陷 B20，必须被从机的 AXI A3.4.1 页边界判据抓住
    //   rot 从机把读回的数据流整体旋转一个字
    //       —— 复现 B27 那类「输入流被旋转」的真实读通路损坏
    // =========================================================
    integer inj_c4, inj_b20, inj_rot;
    reg [8*16-1:0] inject_name;
    reg inj_c4_arm, inj_c4_active;

    always @(posedge clk) begin
        if (inj_c4 && inj_c4_arm && dut.state == ST_INIT_BRAM) begin
            if (!inj_c4_active) begin
                force dut.bram_we = 1'b0;
                inj_c4_active <= 1'b1;
            end
        end else if (inj_c4_active) begin
            release dut.bram_we;
            inj_c4_active <= 1'b0;
        end
    end

    // =========================================================
    // 类 DDR 的 AXI4 从机（读通道）
    //   - AR 队列深度 8，ARREADY 随机撤下（但队列没满时必然最终接受）
    //   - AR -> 首拍 R 有 12..31 拍延迟，偶发 +200 拍长停顿（模拟刷新）
    //   - 突发中间随机插空档
    //   - **已接受的突发一定发满 ARLEN+1 拍**：真实 DDR/互连不会因为主机
    //     被写 START 或被复位就取消飞行中的读
    //   - 协议判据：4KB 页边界、地址区间、对齐、ARSIZE/ARBURST
    // =========================================================
    integer arq_idx [0:7];
    integer arq_len [0:7];
    integer arq_cnt, arq_w, arq_r;
    integer r_idx, r_left, r_delay;
    reg     r_active;
    integer rseed;

    integer rd_beats_total;      // 从机总共发出去的 R 拍数
    integer rd_page_errors;      // 违反 AXI A3.4.1（跨 4KB）的突发数
    integer rd_range_errors;     // 落在输入区之外 / 未对齐的读
    integer rd_attr_errors;      // ARSIZE/ARBURST 不符
    integer rd_stable_errors;    // ARVALID 期间 ARADDR/ARLEN 变化（AXI 要求保持）
    integer rd_offbeat_errors;   // R 拍在 DUT 不处于 S_READ_DATA 时被握手掉

    reg [31:0] ar_hold_addr; reg [7:0] ar_hold_len; reg ar_held;

    wire ar_hs = m_arvalid && m_arready;
    wire r_hs  = m_rvalid  && m_rready;

    always @(posedge clk) begin
        if (!rstn) begin
            arq_cnt <= 0; arq_w <= 0; arq_r <= 0;
            m_arready <= 1'b1; m_rvalid <= 1'b0; m_rlast <= 1'b0; m_rresp <= 2'b00;
            r_active <= 1'b0; r_left <= 0; r_idx <= 0; r_delay <= 0;
            ar_held <= 1'b0;
        end else begin
            // ---- AR 地址/控制在 VALID 期间必须保持不变 ----
            if (m_arvalid && !m_arready) begin
                if (ar_held && ((m_araddr !== ar_hold_addr) || (m_arlen !== ar_hold_len)))
                    rd_stable_errors <= rd_stable_errors + 1;
                ar_hold_addr <= m_araddr; ar_hold_len <= m_arlen; ar_held <= 1'b1;
            end else begin
                ar_held <= 1'b0;
            end

            if (ar_hs) begin
                // AXI A3.4.1：突发不得跨越 4KB 边界（缺陷 B20 的判据）
                if (({1'b0, m_araddr[11:0]} + ((m_arlen + 1) << 3)) > 13'd4096)
                    rd_page_errors <= rd_page_errors + 1;
                // 地址必须 8B 对齐，且整笔突发落在输入区内
                if ((m_araddr[2:0] != 3'd0) || (m_araddr < IN_ADDR) ||
                    ((m_araddr + ((m_arlen + 1) << 3)) > (IN_ADDR + IN_WORDS*8)))
                    rd_range_errors <= rd_range_errors + 1;
                if ((m_arsize != 3'b011) || (m_arburst != 2'b01))
                    rd_attr_errors <= rd_attr_errors + 1;

                arq_idx[arq_w] <= ((m_araddr - IN_ADDR) >> 3) + inj_rot;
                arq_len[arq_w] <= m_arlen + 1;
                arq_w   <= (arq_w + 1) % 8;
                arq_cnt <= arq_cnt + 1;
            end

            // 地址通道随机背压（队列没满时最终一定会接受）
            m_arready <= (arq_cnt < 6) && (({$random(rseed)} % 4) != 0);

            if (!r_active && arq_cnt != 0 && !ar_hs) begin
                r_idx    <= arq_idx[arq_r];
                r_left   <= arq_len[arq_r];
                arq_r    <= (arq_r + 1) % 8;
                arq_cnt  <= arq_cnt - 1;
                r_active <= 1'b1;
                // 类 DDR 首拍延迟；1/32 的概率叠加一次长停顿（刷新/仲裁）
                r_delay  <= 12 + ({$random(rseed)} % 20)
                              + ((({$random(rseed)} % 32) == 0) ? 200 : 0);
            end else if (r_active) begin
                if (r_delay != 0) begin
                    r_delay <= r_delay - 1;
                end else if (!m_rvalid || m_rready) begin
                    if (r_left != 0) begin
                        if ((({$random(rseed)} % 8) == 0) && m_rvalid && m_rready) begin
                            m_rvalid <= 1'b0; m_rlast <= 1'b0;      // 突发中间的空档
                        end else begin
                            m_rdata  <= ((r_idx >= 0) && (r_idx < DDR_WORDS)) ? ddr[r_idx] : {64{1'bx}};
                            m_rvalid <= 1'b1;
                            m_rlast  <= (r_left == 1);
                            r_idx    <= r_idx + 1;
                            r_left   <= r_left - 1;
                        end
                    end else begin
                        m_rvalid <= 1'b0; m_rlast <= 1'b0;
                        r_active <= 1'b0;
                    end
                end
            end
        end
    end

    // R 拍统计与「只能在 S_READ_DATA 被消费」判据：
    // DUT 的 RREADY 在 S_READ_SETUP 也是 1，但只有 S_READ_DATA 才把数据存进
    // read_words。真实 DDR 有延迟时若有拍落在别的状态，就是静默丢数据。
    always @(posedge clk) begin
        if (!rstn) begin
            rd_beats_total <= 0;
        end else if (r_hs) begin
            rd_beats_total <= rd_beats_total + 1;
            if (dut.state !== ST_READ_DATA)
                rd_offbeat_errors <= rd_offbeat_errors + 1;
        end
    end

    // =========================================================
    // 类 DDR 的 AXI4 从机（写通道）
    //   - AW 队列深度 4，AWREADY/WREADY 随机撤下，B 有时延
    //   - 协议判据：地址区间/对齐、AWSIZE/AWBURST、W 拍数与 WLAST、
    //     无 AW 时不得有 W、写地址不得落进输入区（共享 DDR 的踩踏判据）
    // =========================================================
    integer awq_idx [0:3];
    integer awq_len [0:3];
    integer awq_cnt, awq_w, awq_r;
    reg     w_active;
    integer w_left, w_idx, w_count, b_delay, aw_count;
    integer wseed;

    integer wr_range_errors;     // 写地址越界 / 未对齐 / 踩进输入区
    integer wr_attr_errors;      // AWSIZE/AWBURST 不符
    integer wr_last_errors;      // W 拍数与 AWLEN 不符或 WLAST 位置错
    integer wr_orphan_errors;    // 没有 AW 就来 W
    integer wr_stable_errors;    // AWVALID 期间 AWADDR/AWLEN 变化

    reg [31:0] aw_hold_addr; reg [7:0] aw_hold_len; reg aw_held;
    reg [63:0] wr_tmp; integer wb;

    wire aw_hs = m_awvalid && m_awready;

    always @(posedge clk) begin
        if (!rstn) begin
            awq_cnt <= 0; awq_w <= 0; awq_r <= 0;
            m_awready <= 1'b1; m_wready <= 1'b0; m_bvalid <= 1'b0; m_bresp <= 2'b00;
            w_active <= 1'b0; w_left <= 0; w_idx <= 0; b_delay <= 0;
            aw_held <= 1'b0;
        end else begin
            if (m_awvalid && !m_awready) begin
                if (aw_held && ((m_awaddr !== aw_hold_addr) || (m_awlen !== aw_hold_len)))
                    wr_stable_errors <= wr_stable_errors + 1;
                aw_hold_addr <= m_awaddr; aw_hold_len <= m_awlen; aw_held <= 1'b1;
            end else begin
                aw_held <= 1'b0;
            end

            if (aw_hs) begin
                if ((m_awaddr[2:0] != 3'd0) || (m_awaddr < OUT_ADDR) ||
                    ((m_awaddr + ((m_awlen + 1) << 3)) > (OUT_ADDR + OUT_BEATS*8)))
                    wr_range_errors <= wr_range_errors + 1;
                if ((m_awsize != 3'b011) || (m_awburst != 2'b01))
                    wr_attr_errors <= wr_attr_errors + 1;
                awq_idx[awq_w] <= (m_awaddr - OUT_ADDR) >> 3;
                awq_len[awq_w] <= m_awlen + 1;
                awq_w   <= (awq_w + 1) % 4;
                awq_cnt <= awq_cnt + 1;
                aw_count <= aw_count + 1;
            end
            m_awready <= (awq_cnt < 3) && (({$random(wseed)} % 4) != 0);

            if (!w_active && awq_cnt != 0 && !m_bvalid && !aw_hs) begin
                w_idx    <= awq_idx[awq_r];
                w_left   <= awq_len[awq_r];
                awq_r    <= (awq_r + 1) % 4;
                awq_cnt  <= awq_cnt - 1;
                w_active <= 1'b1;
                m_wready <= 1'b1;
            end else if (w_active) begin
                m_wready <= (({$random(wseed)} % 6) != 0);          // 数据通道随机背压
                if (m_wvalid && m_wready) begin
                    if ((w_idx >= 0) && (w_idx < OUT_BEATS+64)) begin
                        // 共享 DDR：**逐字节**按 WSTRB 写。不能按 32 bit 粒度近似——
                        // 末拍 WSTRB=0x1F 只写低 5 字节，字节 4 会被 32 bit 粒度的
                        // 模型漏掉，留着哨兵值去和黄金比，凭空多出几个 bit 差。
                        wr_tmp = ddr[OUT_OFF + w_idx];
                        for (wb = 0; wb < 8; wb = wb + 1)
                            if (m_wstrb[wb]) wr_tmp[wb*8 +: 8] = m_wdata[wb*8 +: 8];
                        ddr[OUT_OFF + w_idx] <= wr_tmp;
                        wr_seen[w_idx] <= 1'b1;
                        wr_strb[w_idx] <= m_wstrb;
                    end
                    if (m_wlast !== (w_left == 1)) wr_last_errors <= wr_last_errors + 1;
                    w_idx   <= w_idx + 1;
                    w_count <= w_count + 1;
                    w_left  <= w_left - 1;
                    if (m_wlast || (w_left == 1)) begin
                        m_wready <= 1'b0;
                        w_active <= 1'b0;
                        b_delay  <= 3 + ({$random(wseed)} % 12);   // 真实互连的 B 时延
                    end
                end
            end else begin
                m_wready <= 1'b0;
                if (m_wvalid) wr_orphan_errors <= wr_orphan_errors + 1;
            end

            if (b_delay != 0) begin
                b_delay <= b_delay - 1;
                if (b_delay == 1) m_bvalid <= 1'b1;
            end
            if (m_bvalid && m_bready) m_bvalid <= 1'b0;
        end
    end

    // =========================================================
    // AXI-Lite BFM：真正驱动 AWVALID/WVALID/ARVALID，逐笔回放固件写序列
    // =========================================================
    integer axil_timeouts;

    task axil_write(input [6:0] addr, input [31:0] data);
        integer wc;
        begin
            @(negedge clk);
            s_awaddr = addr; s_awvalid = 1'b1; s_bready = 1'b1;
            wc = 0;
            while (!s_awready && wc < 200) begin @(negedge clk); wc = wc + 1; end
            if (!s_awready) begin
                $display("[TB] [FAIL] AXI-Lite AW handshake timeout addr=0x%02h", addr);
                axil_timeouts = axil_timeouts + 1;
            end
            @(posedge clk); @(negedge clk); s_awvalid = 1'b0;

            s_wdata = data; s_wstrb = 4'hF; s_wvalid = 1'b1;
            wc = 0;
            while (!s_wready && wc < 200) begin @(negedge clk); wc = wc + 1; end
            if (!s_wready) begin
                $display("[TB] [FAIL] AXI-Lite W handshake timeout addr=0x%02h", addr);
                axil_timeouts = axil_timeouts + 1;
            end
            @(posedge clk); @(negedge clk); s_wvalid = 1'b0;

            wc = 0;
            while (!s_bvalid && wc < 200) begin @(negedge clk); wc = wc + 1; end
            if (!s_bvalid) begin
                $display("[TB] [FAIL] AXI-Lite B response timeout addr=0x%02h", addr);
                axil_timeouts = axil_timeouts + 1;
            end
            @(posedge clk); @(negedge clk); s_bready = 1'b0;
        end
    endtask

    task axil_read(input [6:0] addr, output [31:0] data);
        integer wc;
        begin
            @(negedge clk);
            s_araddr = addr; s_arvalid = 1'b1;
            wc = 0;
            while (!s_arready && wc < 200) begin @(negedge clk); wc = wc + 1; end
            if (!s_arready) begin
                $display("[TB] [FAIL] AXI-Lite AR handshake timeout addr=0x%02h", addr);
                axil_timeouts = axil_timeouts + 1;
            end
            @(posedge clk); @(negedge clk); s_arvalid = 1'b0;
            wc = 0;
            while (!s_rvalid && wc < 200) begin @(negedge clk); wc = wc + 1; end
            if (!s_rvalid) begin
                $display("[TB] [FAIL] AXI-Lite R response timeout addr=0x%02h", addr);
                axil_timeouts = axil_timeouts + 1;
            end
            data = s_rdata;
            @(posedge clk); @(negedge clk);
        end
    endtask

    // =========================================================
    // PS 侧：用 CPU 写 DDR（写进和 Voter 读的同一片内存）
    // =========================================================
    integer i;
    reg [8*256-1:0] input_path, expect_thr_path, expect_raw_path, dump_path;

    task ps_write_ddr;
        begin
            // 输入区：Stage1 的输出记录（板上由 DMA 写、PS 做 cache invalidate）
            $readmemh(input_path, ddr, 0, IN_WORDS-1);
            // 输出区：填固件哨兵，未被 DUT 写过的拍因此可判
            for (i = 0; i < OUT_BEATS+64; i = i + 1) begin
                ddr[OUT_OFF + i] = SENTINEL;
                wr_seen[i]       = 1'b0;
                wr_strb[i]       = 8'h00;
            end
        end
    endtask

    // =========================================================
    // 主流程
    // =========================================================
    integer errors, bit_errors, first_bad, total_errors, proto_errors;
    integer k, b;
    integer w_count0, rd_beats0, polls, timeout;
    integer start0_ns, late_ns, rseed_arg, wseed_arg, second_score_min;
    integer dump_en, dump_fd, dummy;
    integer scen_run, scen_fail;
    reg [63:0] got, exp, mask;
    reg [31:0] rdata, status;
    reg [8*24-1:0] scen_name;

    task do_reset;
        begin
            rstn = 1'b0;
            s_awvalid=0; s_wvalid=0; s_bready=0; s_arvalid=0; s_rready=1;
            s_awaddr=0; s_wdata=0; s_wstrb=0; s_araddr=0;
            repeat (16) @(posedge clk);
            rstn = 1'b1;
            repeat (10) @(posedge clk);
        end
    endtask

    // 固件 sw/app/echo.c 的配置 + 回读校验（voter_configure_and_verify）
    task fw_configure(input integer total_reads, input integer score_min);
        begin
            axil_write(REG_IN_ADDR,     IN_ADDR);
            axil_write(REG_IN_BEATS,    total_reads * WORDS_PER_REC);   // 固件写的是 total_reads * 9
            axil_write(REG_OUT_ADDR,    OUT_ADDR);
            axil_write(REG_OUT_BEATS,   OUT_BEATS);
            axil_write(REG_TOTAL_READS, total_reads);
            axil_write(REG_SCORE_MIN,   score_min);
            #10000;                                         // echo.c: usleep(10)
            axil_read(REG_IN_ADDR, rdata);
            if (rdata !== IN_ADDR)          begin $display("[TB] [FAIL] IN_ADDR readback %h", rdata);      errors = errors + 1; end
            axil_read(REG_IN_BEATS, rdata);
            if (rdata !== total_reads*WORDS_PER_REC) begin $display("[TB] [FAIL] IN_BEATS readback %0d", rdata);    errors = errors + 1; end
            axil_read(REG_OUT_ADDR, rdata);
            if (rdata !== OUT_ADDR)         begin $display("[TB] [FAIL] OUT_ADDR readback %h", rdata);     errors = errors + 1; end
            axil_read(REG_OUT_BEATS, rdata);
            if (rdata !== OUT_BEATS)        begin $display("[TB] [FAIL] OUT_BEATS readback %0d", rdata);   errors = errors + 1; end
            axil_read(REG_TOTAL_READS, rdata);
            if (rdata !== total_reads)      begin $display("[TB] [FAIL] TOTAL_READS readback %0d", rdata); errors = errors + 1; end
            axil_read(REG_SCORE_MIN, rdata);
            if (rdata !== score_min)        begin $display("[TB] [FAIL] SCORE_MIN readback %0d", rdata);   errors = errors + 1; end
        end
    endtask

    // 固件的 DONE 清除通路（二次任务时才走到）
    task fw_clear_done;
        begin
            axil_read(REG_CTRL, status);
            if (status[1]) begin
                axil_write(REG_CTRL, 32'h0000_0002);   // bit1 = done_clr
                #500000;                               // echo.c: usleep(500)
                axil_write(REG_CTRL, 32'h0000_0000);
                #100000;                               // echo.c: usleep(100)
                axil_read(REG_CTRL, status);
                if (status[1]) begin
                    $display("[TB] [FAIL] DONE flag survived the firmware clear sequence (status=%h)", status);
                    errors = errors + 1;
                end
            end
            if (!status[0]) begin                      // echo.c: 非 IDLE 的轻量复位
                axil_write(REG_CTRL,        32'd0);
                axil_write(REG_IN_BEATS,    32'd0);
                axil_write(REG_OUT_BEATS,   32'd0);
                axil_write(REG_TOTAL_READS, 32'd0);
                #2000000;                              // echo.c: usleep(2000)
                axil_read(REG_CTRL, status);
                if (!status[0]) begin
                    $display("[TB] [FAIL] core never returned to IDLE (status=%h)", status);
                    errors = errors + 1;
                end
            end
        end
    endtask

    // 固件的 START 脉冲：写 0 -> 读 STATUS -> 写 1 -> usleep(100) -> 写 0
    // 最后那笔 START=0 就是 B27 在 Decoder 上致命的那种写法；Voter 的
    // axi_slave_voter 是 start_pulse<=wdata[0]，写 0 不该启动——但这件事
    // 在真实 DDR 时序下从来没有被证明过，所以必须原样回放。
    // late_start1：投票途中再写一次 START=1，必须被忽略（FSM 只在 S_IDLE 响应）。
    task fw_start_pulse(input integer gap_ns, input integer late_start1);
        begin
            axil_write(REG_CTRL, 32'h0000_0000);
            #100000;                                   // echo.c: usleep(100)
            axil_read(REG_CTRL, status);
            if (!status[0]) begin
                $display("[TB] [FAIL] core not IDLE before START (status=%h)", status);
                errors = errors + 1;
            end
            axil_write(REG_CTRL, 32'h0000_0001);       // START
            #(gap_ns);
            if (late_start1) axil_write(REG_CTRL, 32'h0000_0001);   // 途中再来一发 START
            else             axil_write(REG_CTRL, 32'h0000_0000);   // echo.c 的「脉冲结束」
            #100000;
        end
    endtask

    // 一个完整场景：配置 -> 启动 -> 轮询 DONE -> 逐位比对 -> 协议判据
    //   name        ASCII 标签（XSim 2022.2 打印非 ASCII 的 %s 会变乱码）
    //   need_reset  是否先复位（0 = 同一会话内的第二次任务）
    //   score_min   本轮阈值
    //   use_thr     1 = 比 expect_thr，0 = 比 expect_raw
    //   gap_ns      START=1 到下一笔 CTRL 写之间的间隔
    //   late_start1 途中那笔写 1 还是写 0
    task run_scenario(input [8*24-1:0] name, input integer need_reset,
                      input integer score_min, input integer use_thr,
                      input integer gap_ns, input integer late_start1);
        begin
            scen_name = name;
            scen_run  = scen_run + 1;
            errors = 0; bit_errors = 0; first_bad = -1;
            $display("[TB] ---- scenario %0s : reset=%0d score_min=%0d expect=%0s gap=%0d ns start1=%0d ----",
                     scen_name, need_reset, score_min, use_thr ? "thr" : "raw", gap_ns, late_start1);

            if (need_reset) begin
                do_reset;
                ps_write_ddr;                 // 复位档：PS 重新铺一遍 DDR
            end else begin
                fw_clear_done;                // 二次任务：走固件的 DONE 清除通路
                ps_write_ddr;                 // 输入不变，输出区重新填哨兵
            end

            w_count0  = w_count;
            rd_beats0 = rd_beats_total;
            inj_c4_arm = (inj_c4 && !need_reset) ? 1'b1 : 1'b0;   // C4 只注在第二次任务上

            fw_configure(NUM_RECORDS, score_min);
            fw_start_pulse(gap_ns, late_start1);

            // 固件用 AXI-Lite 轮询 STATUS 等 DONE（PIPE_VOTER_WAIT）
            // 每次 axil_read 约 6 拍；一轮任务约 5.2M 拍（81,000 拍清 BRAM +
            // 4,096 x 300 位投票 + 输出打包），所以轮询上限要留到百万量级。
            polls = 0; status = 32'd0;
            while (!status[1] && polls < 3000000) begin
                axil_read(REG_CTRL, status);
                polls = polls + 1;
            end
            if (!status[1]) begin
                $display("[TB] [FAIL] %0s : DONE never asserted (status=%h, polls=%0d)",
                         scen_name, status, polls);
                errors = errors + 1;
            end
            repeat (200) @(posedge clk);
            inj_c4_arm = 1'b0;

            axil_read(REG_CTRL, status);
            if (!status[0]) begin
                $display("[TB] [FAIL] %0s : IDLE not restored after DONE (status=%h)", scen_name, status);
                errors = errors + 1;
            end

            // ---- 判据一：AXI 流量刚好，不多不少 ----
            if ((rd_beats_total - rd_beats0) != NUM_RECORDS*WORDS_PER_REC) begin
                $display("[TB] [FAIL] %0s : slave delivered %0d R beats, expected %0d",
                         scen_name, rd_beats_total - rd_beats0, NUM_RECORDS*WORDS_PER_REC);
                errors = errors + 1;
            end
            if ((w_count - w_count0) != OUT_BEATS) begin
                $display("[TB] [FAIL] %0s : %0d write beats, expected %0d",
                         scen_name, w_count - w_count0, OUT_BEATS);
                errors = errors + 1;
            end

            // ---- 判据二：AXI 协议 ----
            proto_errors = rd_page_errors + rd_range_errors + rd_attr_errors
                         + rd_stable_errors + rd_offbeat_errors
                         + wr_range_errors + wr_attr_errors + wr_last_errors
                         + wr_orphan_errors + wr_stable_errors;
            if (proto_errors != 0) begin
                $display("[TB] [FAIL] %0s : AXI protocol violations", scen_name);
                $display("[TB]        read : page(4KB)=%0d range=%0d attr=%0d stable=%0d offbeat=%0d",
                         rd_page_errors, rd_range_errors, rd_attr_errors,
                         rd_stable_errors, rd_offbeat_errors);
                $display("[TB]        write: range=%0d attr=%0d wlast=%0d orphan=%0d stable=%0d",
                         wr_range_errors, wr_attr_errors, wr_last_errors,
                         wr_orphan_errors, wr_stable_errors);
                errors = errors + 1;
            end

            // ---- 判据三：调试寄存器 / 错误标志 ----
            axil_read(REG_DBG_WRITE, rdata);
            if (rdata !== OUT_BEATS) begin
                $display("[TB] [FAIL] %0s : DBG_WRITE=%0d, expected %0d", scen_name, rdata, OUT_BEATS);
                errors = errors + 1;
            end
            axil_read(REG_DBG_AWADDR, rdata);
            if (rdata !== OUT_ADDR) begin
                $display("[TB] [FAIL] %0s : DBG_FIRST_AWADDR=%h, expected %h", scen_name, rdata, OUT_ADDR);
                errors = errors + 1;
            end
            axil_read(REG_ERR_FLAGS, rdata);
            if (rdata !== 32'd0) begin
                $display("[TB] [FAIL] %0s : ERR_FLAGS=%h, expected 0", scen_name, rdata);
                errors = errors + 1;
            end
            axil_read(REG_LAST_RRESP, rdata);
            if (rdata[1:0] !== 2'b00) begin
                $display("[TB] [FAIL] %0s : LAST_RRESP=%h, expected OKAY", scen_name, rdata[1:0]);
                errors = errors + 1;
            end

            // ---- 判据四：逐拍逐位比对 DDR 输出区（末拍只比低 40 bit）----
            for (k = 0; k < OUT_BEATS; k = k + 1) begin
                mask = (k == OUT_BEATS-1) ? ((64'd1 << LAST_BITS) - 64'd1) : {64{1'b1}};
                got = ddr[OUT_OFF + k] & mask;
                exp = (use_thr ? expect_thr[k] : expect_raw[k]) & mask;
                if (wr_strb[k] !== ((k == OUT_BEATS-1) ? 8'h1F : 8'hFF)) begin
                    if (errors < 10)
                        $display("[TB] x %0s : beat %0d WSTRB=%h, expected %h", scen_name, k,
                                 wr_strb[k], (k == OUT_BEATS-1) ? 8'h1F : 8'hFF);
                    errors = errors + 1;
                end
                if (!wr_seen[k]) begin
                    if (errors < 10) $display("[TB] x %0s : beat %0d never written", scen_name, k);
                    if (first_bad < 0) first_bad = k;
                    errors = errors + 1;
                end else if (got !== exp) begin
                    for (b = 0; b < 64; b = b + 1)
                        if (mask[b] && (got[b] !== exp[b])) bit_errors = bit_errors + 1;
                    if (errors < 10)
                        $display("[TB] x %0s : beat %0d got %h expected %h", scen_name, k, got, exp);
                    if (first_bad < 0) first_bad = k;
                    errors = errors + 1;
                end
            end

            if (errors == 0) begin
                $display("[TB] ok   %0s : %0d beats / %0d bit identical to golden (real DDR timing)",
                         scen_name, OUT_BEATS, OUT_BITS);
            end else begin
                $display("[TB] [FAIL] %0s : %0d checks failed (first bad beat %0d), %0d bit errors, BER %0d/10000",
                         scen_name, errors, first_bad, bit_errors, (bit_errors*10000)/OUT_BITS);
                scen_fail = scen_fail + 1;
            end
            total_errors = total_errors + errors;

            if (dump_en) begin
                dump_fd = $fopen(dump_path, "w");
                if (dump_fd != 0) begin
                    for (k = 0; k < OUT_BEATS; k = k + 1) $fdisplay(dump_fd, "%016h", ddr[OUT_OFF + k]);
                    $fclose(dump_fd);
                end
            end
        end
    endtask

    // 全局看门狗：XSim 2022.2 的 $fatal 不会终止仿真，所以这里显式 $finish，
    // 并且只打 [FAIL]，绝不打 PASS。
    initial begin
        repeat (4) #1_000_000_000;   // 4 s 仿真时间；单个 #4_000_000_000 会溢出 32 bit
        $display("[TB] [FAIL] global watchdog expired");
        $display("--------------------------------------------------");
        $finish;
    end

    initial begin
        input_path      = "../sim/golden/stage2_in.hex";
        expect_thr_path = "../sim/golden/stage2_expect.hex";
        expect_raw_path = "../sim/golden/stage2_rtl_expect.hex";
        start0_ns       = 100000;      // echo.c: START=1 之后 usleep(100)
        late_ns         = 5000000;     // 5 ms：投票途中
        second_score_min = 0;          // 场景 2 的阈值：默认换成 0，让残留可观测
        rseed_arg       = 32'h5EED_1207;
        wseed_arg       = 32'h5EED_2101;
        inject_name     = "none";

        dummy = $value$plusargs("input=%s",      input_path);
        dummy = $value$plusargs("expect_thr=%s", expect_thr_path);
        dummy = $value$plusargs("expect_raw=%s", expect_raw_path);
        dummy = $value$plusargs("start0_ns=%d",  start0_ns);
        dummy = $value$plusargs("late_ns=%d",    late_ns);
        dummy = $value$plusargs("second_score_min=%d", second_score_min);
        dummy = $value$plusargs("rseed=%d",      rseed_arg);
        dummy = $value$plusargs("wseed=%d",      wseed_arg);
        dummy = $value$plusargs("inject=%s",     inject_name);
        dump_en = $value$plusargs("dump=%s",     dump_path);

        inj_c4  = (inject_name == "c4")  ? 1 : 0;
        inj_b20 = (inject_name == "b20") ? 1 : 0;
        inj_rot = (inject_name == "rot") ? 1 : 0;

        rseed = rseed_arg; wseed = wseed_arg;
        total_errors = 0; scen_run = 0; scen_fail = 0; axil_timeouts = 0;
        w_count = 0; aw_count = 0; rd_beats_total = 0;
        rd_page_errors = 0; rd_range_errors = 0; rd_attr_errors = 0;
        rd_stable_errors = 0; rd_offbeat_errors = 0;
        wr_range_errors = 0; wr_attr_errors = 0; wr_last_errors = 0;
        wr_orphan_errors = 0; wr_stable_errors = 0;
        inj_c4_arm = 1'b0; inj_c4_active = 1'b0;

        $readmemh(expect_thr_path, expect_thr);
        $readmemh(expect_raw_path, expect_raw);

        $display("[TB] input=%0s", input_path);
        $display("[TB] expect(score_min=%0d)=%0s  expect(score_min=0)=%0s",
                 SCORE_MIN_THR, expect_thr_path, expect_raw_path);
        $display("[TB] records=%0d  out_beats=%0d  out_bits=%0d  IN=0x%08h OUT=0x%08h",
                 NUM_RECORDS, OUT_BEATS, OUT_BITS, IN_ADDR, OUT_ADDR);
        $display("[TB] start0_ns=%0d late_ns=%0d rseed=%0d wseed=%0d inject=%0s",
                 start0_ns, late_ns, rseed_arg, wseed_arg, inject_name);

        // b20 注入：把读突发强行退回「每条记录固定 9 拍、从不按 4KB 页拆分」，
        // 即缺陷 B20 修复前的行为。必须被从机的 4KB 页边界判据抓住。
        if (inj_b20) begin
            force dut.rd_burst_beats = 4'd9;
            $display("[TB] inject b20 : rd_burst_beats forced to 9 (pre-B20 behaviour)");
        end
        if (inj_rot) $display("[TB] inject rot : DDR read stream rotated by one 64-bit word");
        if (inj_c4)  $display("[TB] inject c4  : BRAM clear suppressed on the second task");

        if (inj_b20 || inj_rot) begin
            // 这两档只需要单轮就能证伪
            run_scenario("fw-board-cfg", 1, SCORE_MIN_THR, 1, start0_ns, 0);
        end else if (inj_c4) begin
            // C4 要两轮：第一轮建立累加器残留，第二轮换阈值后残留才可观测
            run_scenario("fw-board-cfg",   1, SCORE_MIN_THR, 1, start0_ns, 0);
            run_scenario("fw-second-task", 0, second_score_min,
                         (second_score_min == SCORE_MIN_THR), start0_ns, 0);
        end else begin
            run_scenario("fw-board-cfg",   1, SCORE_MIN_THR, 1, start0_ns, 0);
            run_scenario("fw-second-task", 0, second_score_min,
                         (second_score_min == SCORE_MIN_THR), start0_ns, 0);
            run_scenario("fw-raw-score0",  1, 0,             0, start0_ns, 0);
            run_scenario("late-start0",    1, SCORE_MIN_THR, 1, late_ns,   0);
            run_scenario("spurious-start", 1, SCORE_MIN_THR, 1, late_ns,   1);
        end

        total_errors = total_errors + axil_timeouts;

        $display("--------------------------------------------------");
        if (inj_c4 || inj_b20 || inj_rot) begin
            // 故障注入档：**期望失败**。判据是「注入后确实变红」。
            if (total_errors != 0) begin
                $display("[TB] inject=%0s produced %0d failed checks in %0d scenario(s)",
                         inject_name, total_errors, scen_run);
                $display("[TB] 故障注入自检 PASS：注入已知缺陷后判据确实报错");
            end else begin
                $display("[TB] 判据没有鉴别力：注入 %0s 之后所有检查仍然通过", inject_name);
            end
        end else begin
            if (total_errors == 0) begin
                $display("[TB] PASS  %0d scenarios bit-exact over a DDR-like AXI slave", scen_run);
                $display("[TB]       (real DUT + real board addresses + firmware register sequence)");
            end else begin
                $display("[TB] [FAIL] %0d checks failed across %0d scenario(s)", total_errors, scen_fail);
            end
        end
        $display("--------------------------------------------------");
        $finish;
    end

endmodule
