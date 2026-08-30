// =============================================================
// tb_dec_ddr_restart.v — Stage3 Decoder 的「真实 DDR / 真实 AXI 主口」级判据
//
// 【为什么要这条 TB】（B27）
// 已有的 tb_desparsifier / tb_desparsify_datapath / M3 BD-3ext 全都 PASS，
// 但第四次上板 Stage3 输出与黄金 49.46% 误码。原因不在数据通路，而在
// **控制时序 + 真实 AXI 从机的行为**：
//   1) desparsification_decoder_v1_0.v 的 AXI-Lite 写 START(0x10) 时
//      `start_pulse <= 1'b1` —— 不看 wdata[0]，**写 0 也会启动**；
//   2) 固件 sw/app/echo.c 的 PIPE_DECODER_START 写完 START=1 之后
//      隔 100 us 又写了一次 START=0（注释写「脉冲结束」），于是**任务跑到
//      一半被重启**；
//   3) 重启只复位了 FSM 和数据通路，**没有清掉已经发出去、还在飞行中的
//      读突发**。真实 DDR/互连不会因为主机复位就取消已接受的 AR，
//      剩下的 R 拍会继续回来，被新任务当成输入流的开头 —— 整条输入被
//      旋转了「上一段突发的残留拍数」。
// 老 TB 抓不到，是因为它只写一次 START=1、而且从机模型很温柔。
//
// 因此本 TB：
//   * 用真实 DUT（desparsification_decoder_v1_0 + desparsify_datapath），不复制逻辑；
//   * 用真实板上地址（IN 0x1100_0000 / OUT 0x1110_0000）和真实黄金向量
//     （tests/golden/sparse_expect.hex 就是第四次上板 DDR 里逐位相同的那份）；
//   * 从机模型像真 DDR：AR/AW 有延迟、R 拍有随机空档、W/AW/B 随机背压，
//     **已接受的读突发一定把 ARLEN+1 拍发完**，不因主机重启而取消；
//   * 逐字节回放固件的寄存器时序（含那次致命的 START=0）；
//   * 逐拍比对输出，显式 PASS/FAIL，失败 $fatal(1) 非零退出。
//
// plusargs:
//   +input=<hex>        输入稀疏流（默认 tests/golden/sparse_expect.hex）
//   +expect=<hex>       期望码字（默认 tests/golden/stage3_expect.hex）
//   +restart_ns=<int>   START=1 之后隔多久再写一次 START=0；0 表示不写（干净时序）
//   +seed=<int>         背压随机种子
//   +dump=<file>        把从机内存里 DUT 实际写出的内容导出（用于与板上 dump 对照）
//   +allow_fail         只报告不 $fatal（用于取证时扫描 restart_ns）
// =============================================================
`timescale 1ns/1ps

module tb_dec_ddr_restart;

    localparam integer IN_BEATS  = 1266;
    localparam integer OUT_BEATS = 1013;
    localparam integer OUT_BITS  = 64800;

    // 板上真实地址（docs/05-interfaces.md / sw/app/echo.h）
    localparam [31:0] IN_ADDR  = 32'h1100_0000;
    localparam [31:0] OUT_ADDR = 32'h1110_0000;

    // 寄存器偏移（desparsification_decoder_v1_0.v 的 axi_slave_decoder）
    localparam [5:0] REG_IN_ADDR   = 6'h00;
    localparam [5:0] REG_IN_BEATS  = 6'h04;
    localparam [5:0] REG_OUT_ADDR  = 6'h08;
    localparam [5:0] REG_OUT_BEATS = 6'h0C;
    localparam [5:0] REG_START     = 6'h10;
    localparam [5:0] REG_STATUS    = 6'h18;

    reg clk = 0, rstn = 0;
    always #5 clk = ~clk;                       // 100 MHz，与板上 FCLK0 相同

    // ---------------- AXI-Lite ----------------
    reg  [5:0]  s_awaddr;  reg s_awvalid;  wire s_awready;
    reg  [31:0] s_wdata;   reg [3:0] s_wstrb; reg s_wvalid; wire s_wready;
    wire [1:0]  s_bresp;   wire s_bvalid;  reg s_bready;
    reg  [5:0]  s_araddr;  reg s_arvalid;  wire s_arready;
    wire [31:0] s_rdata;   wire [1:0] s_rresp; wire s_rvalid; reg s_rready;

    // ---------------- AXI4 Master ----------------
    wire [31:0] m_awaddr;  wire [7:0] m_awlen;  wire m_awvalid;  reg m_awready;
    wire [63:0] m_wdata;   wire [7:0] m_wstrb;  wire m_wlast;
    wire        m_wvalid;  reg  m_wready;
    reg  [1:0]  m_bresp;   reg  m_bvalid;       wire m_bready;
    wire [31:0] m_araddr;  wire [7:0] m_arlen;  wire m_arvalid;  reg m_arready;
    reg  [63:0] m_rdata;   reg  [1:0] m_rresp;  reg m_rlast;     reg m_rvalid;
    wire        m_rready;

    desparsification_decoder_v1_0 dut (
        .S00_AXI_ACLK(clk), .S00_AXI_ARESETN(rstn),
        .S00_AXI_AWADDR(s_awaddr), .S00_AXI_AWVALID(s_awvalid), .S00_AXI_AWREADY(s_awready),
        .S00_AXI_WDATA(s_wdata), .S00_AXI_WSTRB(s_wstrb),
        .S00_AXI_WVALID(s_wvalid), .S00_AXI_WREADY(s_wready),
        .S00_AXI_BRESP(s_bresp), .S00_AXI_BVALID(s_bvalid), .S00_AXI_BREADY(s_bready),
        .S00_AXI_ARADDR(s_araddr), .S00_AXI_ARVALID(s_arvalid), .S00_AXI_ARREADY(s_arready),
        .S00_AXI_RDATA(s_rdata), .S00_AXI_RRESP(s_rresp),
        .S00_AXI_RVALID(s_rvalid), .S00_AXI_RREADY(s_rready),

        .M00_AXI_ACLK(clk), .M00_AXI_ARESETN(rstn),
        .M00_AXI_AWADDR(m_awaddr), .M00_AXI_AWLEN(m_awlen), .M00_AXI_AWSIZE(),
        .M00_AXI_AWBURST(), .M00_AXI_AWLOCK(), .M00_AXI_AWCACHE(),
        .M00_AXI_AWPROT(), .M00_AXI_AWQOS(),
        .M00_AXI_AWVALID(m_awvalid), .M00_AXI_AWREADY(m_awready),
        .M00_AXI_WDATA(m_wdata), .M00_AXI_WSTRB(m_wstrb), .M00_AXI_WLAST(m_wlast),
        .M00_AXI_WVALID(m_wvalid), .M00_AXI_WREADY(m_wready),
        .M00_AXI_BRESP(m_bresp), .M00_AXI_BVALID(m_bvalid), .M00_AXI_BREADY(m_bready),
        .M00_AXI_ARADDR(m_araddr), .M00_AXI_ARLEN(m_arlen), .M00_AXI_ARSIZE(),
        .M00_AXI_ARBURST(), .M00_AXI_ARLOCK(), .M00_AXI_ARCACHE(),
        .M00_AXI_ARPROT(), .M00_AXI_ARQOS(),
        .M00_AXI_ARVALID(m_arvalid), .M00_AXI_ARREADY(m_arready),
        .M00_AXI_RDATA(m_rdata), .M00_AXI_RRESP(m_rresp), .M00_AXI_RLAST(m_rlast),
        .M00_AXI_RVALID(m_rvalid), .M00_AXI_RREADY(m_rready)
    );

    // =========================================================
    // 类 DDR 的 AXI4 从机内存模型
    //   - 已接受的读突发一定发满 ARLEN+1 拍（真实 DDR 不会因为主机重启而取消）
    //   - AR->第一拍 R 有固定+随机延迟；突发中间有随机空档
    //   - AW/W/B 也有延迟和随机背压
    // =========================================================
    localparam integer MEM_OUT_WORDS = OUT_BEATS + 64;

    reg [63:0] mem_in  [0:IN_BEATS-1];
    reg [63:0] mem_out [0:MEM_OUT_WORDS-1];
    reg [63:0] expect  [0:OUT_BEATS-1];
    reg        written [0:MEM_OUT_WORDS-1];

    integer seed;

    // ---- 读通道 ----
    integer r_pending;              // 已接受但还没发完的突发数（本模型一次只处理一个）
    integer r_idx, r_left;
    reg     r_active;
    integer arq_idx [0:7];
    integer arq_len [0:7];
    integer arq_cnt, arq_w, arq_r;
    integer r_delay;
    integer rd_beats_total;         // 统计：从机总共发出去多少 R 拍

    wire ar_hs = m_arvalid && m_arready;

    always @(posedge clk) begin
        if (!rstn) begin
            arq_cnt <= 0; arq_w <= 0; arq_r <= 0;
            m_arready <= 1'b1; m_rvalid <= 1'b0; m_rlast <= 1'b0; m_rresp <= 2'b00;
            r_active <= 1'b0; r_left <= 0; r_idx <= 0; r_delay <= 0;
            rd_beats_total <= 0;
        end else begin
            if (ar_hs) begin
                arq_idx[arq_w] <= (m_araddr - IN_ADDR) >> 3;
                arq_len[arq_w] <= m_arlen + 1;
                arq_w   <= (arq_w + 1) % 8;
                arq_cnt <= arq_cnt + 1;
            end
            // 地址通道背压：随机撤 ARREADY，但保证队列没满时最终会接受
            m_arready <= (arq_cnt < 4) && (($random(seed) % 4) != 0);

            if (!r_active && arq_cnt != 0 && !ar_hs) begin
                r_idx    <= arq_idx[arq_r];
                r_left   <= arq_len[arq_r];
                arq_r    <= (arq_r + 1) % 8;
                arq_cnt  <= arq_cnt - 1;
                r_active <= 1'b1;
                r_delay  <= 12 + ({$random(seed)} % 20);   // 类 DDR 首拍延迟
            end else if (r_active) begin
                if (r_delay != 0) begin
                    r_delay <= r_delay - 1;
                end else if (!m_rvalid || m_rready) begin
                    if (r_left != 0) begin
                        // 突发中间的随机空档
                        if (({$random(seed)} % 8) == 0 && m_rvalid && m_rready) begin
                            m_rvalid <= 1'b0; m_rlast <= 1'b0;
                        end else begin
                            m_rdata  <= (r_idx >= 0 && r_idx < IN_BEATS) ? mem_in[r_idx] : 64'hDEAD_BEEF_DEAD_BEEF;
                            m_rvalid <= 1'b1;
                            m_rlast  <= (r_left == 1);
                            r_idx    <= r_idx + 1;
                            r_left   <= r_left - 1;
                            rd_beats_total <= rd_beats_total + 1;
                        end
                    end else begin
                        m_rvalid <= 1'b0; m_rlast <= 1'b0;
                        r_active <= 1'b0;
                    end
                end
            end
        end
    end

    // ---- 写通道 ----
    integer awq_idx [0:7];
    integer awq_len [0:7];
    integer awq_cnt, awq_w, awq_r;
    reg     w_active;
    integer w_left, w_idx, w_count;
    integer b_delay;
    integer aw_count;

    wire aw_hs = m_awvalid && m_awready;

    always @(posedge clk) begin
        if (!rstn) begin
            awq_cnt <= 0; awq_w <= 0; awq_r <= 0;
            m_awready <= 1'b1; m_wready <= 1'b0; m_bvalid <= 1'b0; m_bresp <= 2'b00;
            w_active <= 1'b0; w_left <= 0; w_idx <= 0; w_count <= 0; b_delay <= 0;
            aw_count <= 0;
        end else begin
            if (aw_hs) begin
                awq_idx[awq_w] <= (m_awaddr - OUT_ADDR) >> 3;
                awq_len[awq_w] <= m_awlen + 1;
                awq_w   <= (awq_w + 1) % 8;
                awq_cnt <= awq_cnt + 1;
                aw_count <= aw_count + 1;
            end
            m_awready <= (awq_cnt < 4) && (($random(seed) % 4) != 0);

            if (!w_active && awq_cnt != 0 && !m_bvalid && !aw_hs) begin
                w_idx    <= awq_idx[awq_r];
                w_left   <= awq_len[awq_r];
                awq_r    <= (awq_r + 1) % 8;
                awq_cnt  <= awq_cnt - 1;
                w_active <= 1'b1;
                m_wready <= 1'b1;
            end else if (w_active) begin
                // 数据通道随机背压
                m_wready <= (({$random(seed)} % 6) != 0);
                if (m_wvalid && m_wready) begin
                    if (w_idx >= 0 && w_idx < MEM_OUT_WORDS) begin
                        if (m_wstrb[7:4] == 4'hF)
                            mem_out[w_idx][63:32] <= m_wdata[63:32];
                        if (m_wstrb[3:0] == 4'hF)
                            mem_out[w_idx][31:0]  <= m_wdata[31:0];
                        written[w_idx] <= 1'b1;
                    end
                    w_idx   <= w_idx + 1;
                    w_count <= w_count + 1;
                    w_left  <= w_left - 1;
                    if (m_wlast || w_left == 1) begin
                        m_wready <= 1'b0;
                        w_active <= 1'b0;
                        b_delay  <= 3 + ({$random(seed)} % 12);   // 真实互连的 B 时延
                    end
                end
            end

            if (b_delay != 0) begin
                b_delay <= b_delay - 1;
                if (b_delay == 1) m_bvalid <= 1'b1;
            end
            if (m_bvalid && m_bready) m_bvalid <= 1'b0;
        end
    end

    // =========================================================
    // AXI-Lite 写任务（真正驱动 AWVALID / WVALID）
    // =========================================================
    integer start_writes;

    task axil_write(input [5:0] addr, input [31:0] data);
        integer wait_cycles;
        begin
            if (addr == REG_START) start_writes = start_writes + 1;
            @(negedge clk);
            s_awaddr = addr; s_awvalid = 1'b1; s_bready = 1'b1;
            wait_cycles = 0;
            while (!s_awready && wait_cycles < 50) begin
                @(negedge clk); wait_cycles = wait_cycles + 1;
            end
            if (!s_awready) $fatal(1, "AXI-Lite AW 握手超时 addr=0x%02h", addr);
            @(posedge clk); @(negedge clk); s_awvalid = 1'b0;

            s_wdata = data; s_wstrb = 4'hF; s_wvalid = 1'b1;
            wait_cycles = 0;
            while (!s_wready && wait_cycles < 50) begin
                @(negedge clk); wait_cycles = wait_cycles + 1;
            end
            if (!s_wready) $fatal(1, "AXI-Lite W 握手超时 addr=0x%02h", addr);
            @(posedge clk); @(negedge clk); s_wvalid = 1'b0;

            wait_cycles = 0;
            while (!s_bvalid && wait_cycles < 50) begin
                @(negedge clk); wait_cycles = wait_cycles + 1;
            end
            if (!s_bvalid) $fatal(1, "AXI-Lite B 响应超时 addr=0x%02h", addr);
            @(posedge clk); @(negedge clk); s_bready = 1'b0;
        end
    endtask

    // =========================================================
    // 主流程：一次仿真里跑两个场景
    //   场景 1「干净时序」  ：只写一次 START=1                 —— 必须 PASS
    //   场景 2「固件原时序」：写 0 → 10 us → 写 1 → N us → 写 0 —— 修好后也必须 PASS
    // 修复前场景 2 会 FAIL（核被跑到一半重启，飞行中的读突发残留拍
    // 被当成新任务输入流的开头），这正是 B27 的板上现象。
    // =========================================================
    integer errors, bit_errors, first_bad, total_errors;
    integer k, b, i;
    reg [63:0] got, exp, mask;
    integer timeout;
    reg [8*256-1:0] input_path, expect_path, dump_path;
    integer restart_ns, seed_arg, dump_en, allow_fail, dump_fd;
    integer dummy;
    reg [8*32-1:0] scen_name;

    task do_reset;
        begin
            rstn = 1'b0;
            repeat (12) @(posedge clk);
            for (i = 0; i < MEM_OUT_WORDS; i = i + 1) begin
                // 与固件一致：跑之前整片填 DECODER_SENTINEL_U64
                mem_out[i] = 64'h0A55AA55AA55AA55;
                written[i] = 1'b0;
            end
            s_awvalid=0; s_wvalid=0; s_bready=0; s_arvalid=0; s_rready=1;
            s_awaddr=0; s_wdata=0; s_wstrb=0; s_araddr=0;
            start_writes = 0;
            repeat (4) @(posedge clk);
            rstn = 1'b1;
            repeat (10) @(posedge clk);
        end
    endtask

    task run_scenario(input [8*32-1:0] name, input integer rst_ns);
        begin
            scen_name = name;
            errors = 0; bit_errors = 0; first_bad = -1;
            do_reset;

            axil_write(REG_IN_ADDR,   IN_ADDR);
            axil_write(REG_OUT_ADDR,  OUT_ADDR);
            axil_write(REG_OUT_BEATS, OUT_BEATS);
            axil_write(REG_IN_BEATS,  IN_BEATS);      // 固件里 IN_BEATS 最后写

            if (rst_ns != 0) begin
                // sw/app/echo.c PIPE_DECODER_START 的原样时序
                axil_write(REG_START, 32'd0);         // echo.c: 先写 0
                #10000;                               // echo.c: usleep(10)
                axil_write(REG_START, 32'd1);         // echo.c: 再写 1，真正启动
                #(rst_ns);                            // echo.c: usleep(100)
                axil_write(REG_START, 32'd0);         // echo.c:「脉冲结束」← B27 致命的一笔
            end else begin
                axil_write(REG_START, 32'd1);         // 对照组：只写一次
            end

            timeout = 0;
            while (w_count < OUT_BEATS && timeout < 2_000_000) begin
                @(posedge clk);
                timeout = timeout + 1;
            end
            repeat (2000) @(posedge clk);

            $display("[TB] [%0s] 对 START 写了 %0d 次；从机收到 %0d 个写突发 / %0d 个写拍，发出 %0d 个读拍",
                     scen_name, start_writes, aw_count, w_count, rd_beats_total);

            // 判据一：AXI 流量必须刚好，不多不少
            if (rd_beats_total != IN_BEATS) begin
                $display("[TB] [FAIL] [%0s] 读拍数 %0d != %0d：核被重启过（飞行中的突发残留会污染输入流）",
                         scen_name, rd_beats_total, IN_BEATS);
                errors = errors + 1;
            end
            if (w_count != OUT_BEATS) begin
                $display("[TB] [FAIL] [%0s] 写拍数 %0d != %0d", scen_name, w_count, OUT_BEATS);
                errors = errors + 1;
            end

            // 判据二：逐拍逐位等于黄金码字
            for (k = 0; k < OUT_BEATS; k = k + 1) begin
                mask = (k == OUT_BEATS-1) ? ((64'd1 << (OUT_BITS-64*(OUT_BEATS-1))) - 64'd1)
                                          : {64{1'b1}};
                got = mem_out[k] & mask;
                exp = expect[k]  & mask;
                if (!written[k]) begin
                    if (errors < 8) $display("[TB] x [%0s] 第 %0d 拍未被写入", scen_name, k);
                    if (first_bad < 0) first_bad = k;
                    errors = errors + 1;
                end else if (got !== exp) begin
                    for (b = 0; b < 64; b = b + 1)
                        if (mask[b] && (got[b] !== exp[b])) bit_errors = bit_errors + 1;
                    if (errors < 8)
                        $display("[TB] x [%0s] 第 %0d 拍不符  实得 %h  期望 %h", scen_name, k, got, exp);
                    if (first_bad < 0) first_bad = k;
                    errors = errors + 1;
                end
            end

            if (dump_en) begin
                dump_fd = $fopen(dump_path, "w");
                if (dump_fd == 0) $fatal(1, "无法打开 dump 文件 %0s", dump_path);
                for (k = 0; k < OUT_BEATS; k = k + 1) $fdisplay(dump_fd, "%016h", mem_out[k]);
                $fclose(dump_fd);
                $display("[TB] [%0s] 已导出 DUT 实际写出的内容：%0s", scen_name, dump_path);
            end

            if (errors == 0)
                $display("[TB] PASS [%0s] %0d 拍 / %0d bit 与黄金逐位相同",
                         scen_name, OUT_BEATS, OUT_BITS);
            else
                $display("[TB] [FAIL] [%0s] %0d 处不符（首个错拍 %0d），共 %0d bit 错，误码 %0d/10000",
                         scen_name, errors, first_bad, bit_errors, (bit_errors*10000)/OUT_BITS);
            total_errors = total_errors + errors;
        end
    endtask

    initial begin
        input_path  = "tests/golden/sparse_expect.hex";
        expect_path = "tests/golden/stage3_expect.hex";
        restart_ns  = 100000;          // 固件 echo.c 的 usleep(100) = 100 us
        seed_arg    = 32'h5EEDB27;
        dummy = $value$plusargs("input=%s",      input_path);
        dummy = $value$plusargs("expect=%s",     expect_path);
        dummy = $value$plusargs("restart_ns=%d", restart_ns);
        dummy = $value$plusargs("seed=%d",       seed_arg);
        dump_en    = $value$plusargs("dump=%s",  dump_path);
        allow_fail = $test$plusargs("allow_fail");
        seed = seed_arg;
        total_errors = 0;

        $readmemh(input_path,  mem_in);
        $readmemh(expect_path, expect);
        $display("[TB] 输入 %0s（%0d 拍） 期望 %0s（%0d 拍） restart_ns=%0d seed=%0d",
                 input_path, IN_BEATS, expect_path, OUT_BEATS, restart_ns, seed_arg);

        run_scenario("clean-single-start", 0);
        run_scenario("firmware-sequence", restart_ns);

        $display("--------------------------------------------------");
        if (total_errors == 0)
            $display("[TB] PASS  两个场景都逐位正确（真实 DDR 时序 + 真实 AXI 主口 + 固件寄存器时序）");
        else
            $display("[TB] [FAIL] 共 %0d 处不符", total_errors);
        $display("--------------------------------------------------");
        if (total_errors != 0 && !allow_fail) $fatal(1);
        $finish;
    end

endmodule
