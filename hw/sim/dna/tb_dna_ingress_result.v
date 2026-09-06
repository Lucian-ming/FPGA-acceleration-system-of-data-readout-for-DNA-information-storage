`timescale 1ns/1ps
//=============================================================================
// tb_dna_ingress_result —— DNA 核「入口逐条」判据（缺陷 B26 的复现与回归）
//
// 为什么需要这个 TB：
//   出口那一侧已经有 tb_dna_result_axis.v（B23/B24 的逐拍判据），
//   但**入口**这一侧至今是空白：
//     - tb_srpe_batch.v 直接把 cw_data 摆在引擎端口上，**不经过** in_fifo，
//       也不经过 Dna_accelerator_core_v1_0.v 的 in_rd / eng_cw_vld 握手；
//     - tb_dna_ingress.v 只看 S_AXIS_DATA_TREADY 的背压行为，
//       从不检查「送进去的第 k 条读段，是不是真的成了第 k 条结果」。
//   于是 B26（板上结果整体错位一条读段：result[k] == read[k+1]，read[0] 的结果
//   丢失、末尾多一条黄金里没有的记录）在所有仿真里都是绿的，只有上板才暴露。
//
// 本 TB 的做法（与 tb_dna_result_axis.v 同一风格）：
//   用真实 DUT（Dna_accelerator_core_v1_0），不复制任何被测逻辑；
//   真实 AXI-Lite 写 reg0/reg1、真实 S_AXIS 送水印与读段、真实 M_AXIS 收结果。
//   为了让一个 batch 在秒级跑完，只把**扫描几何**改小（NUM_LC=1、STRIDE=8、
//   BATCH=8）；READ_BPS / CODEBITS / REF_LEN / 两个 FIFO 与生产完全一致 ——
//   入口装载通路（in_fifo -> in_rd -> eng_cw_vld -> S_LOAD_R）逐比特与生产相同，
//   NUM_LC/STRIDE 只决定比对阶段要跑多少拍，不参与装载。
//
// 判据（任一条不满足即 FAIL 并以非零码退出）：
//   1. 送入 N 条读段必须收到恰好 N 条 72 B 记录（不许多、不许少）；
//   2. **第 k 条结果记录的码字（bit 525:26）必须逐位等于送入的第 k 条读段的码字**
//      —— 这正是 B26 的判据；
//   3. 每条记录恰好 9 拍、TLAST 只在第 9 拍、末拍高 50 bit 为 0；
//   4. 码字字段不得含 X/Z（不许把 X 当 0）；
//   5. 全程在随机上游空档与随机 TREADY 背压下成立；
//   6. 超时即 FATAL。
//
// 运行：bash tools/run_xsim.sh ingress_result
//=============================================================================
module tb_dna_ingress_result;

    // ---- 与生产一致的部分（不许改小）----
    localparam integer READ_BPS  = 150;
    localparam integer CODEBITS  = READ_BPS*2;                  // 500
    localparam integer SCORE_W   = 10;
    localparam integer POS_W     = 16;
    localparam integer RESULT_W  = CODEBITS + POS_W + SCORE_W;  // 526
    localparam integer REF_LEN   = 957;   // 与核里 wm_waddr 的 956 回绕绑定，不能改
    localparam integer BEATS     = 6;     // 每条记录 6 拍 x 64 bit = 48 B

    // ---- 只为缩短仿真时间而改小的扫描几何 ----
    localparam integer NUM_LC    = 1;     // 生产 50
    localparam integer STRIDE    = 8;     // 生产 805
    localparam integer BATCH     = 8;     // 生产 64

    localparam integer NBATCH    = 4;                 // 4 个 batch，覆盖跨 batch 的连续装载
    localparam integer NREADS    = NBATCH * BATCH;    // 送入的读段条数
    localparam integer NWORDS    = 10;                // 每条读段 10 个 32 bit 字（末字 12 bit 有效）
    localparam integer WM_SYMS   = NUM_LC * REF_LEN;

    localparam [3:0] REG0 = 4'h0;   // [0]=start [1]=preload [2]=soft_reset
    localparam [3:0] REG1 = 4'h4;   // [5:0]=wm_sel

    reg aclk = 1'b0;
    reg aresetn = 1'b0;
    always #5 aclk = ~aclk;         // 100 MHz

    integer errors = 0;
    integer cw_bad = 0;

    // ================= DUT =================
    reg  [3:0]  awaddr  = 4'd0;
    reg         awvalid = 1'b0;
    wire        awready;
    reg  [31:0] wdata   = 32'd0;
    reg         wvalid  = 1'b0;
    wire        wready;
    wire [1:0]  bresp;
    wire        bvalid;
    reg         bready  = 1'b0;

    reg  [31:0] s_tdata  = 32'd0;
    reg         s_tvalid = 1'b0;
    reg         s_tlast  = 1'b0;
    wire        s_tready;

    reg         m_tready = 1'b0;
    wire        m_tvalid, m_tlast;
    wire [63:0] m_tdata;

    Dna_accelerator_core_v1_0 #(
        .READ_BPS (READ_BPS),
        .SCORE_W  (SCORE_W),
        .POS_W    (POS_W),
        .NUM_LC   (NUM_LC),
        .REF_LEN  (REF_LEN),
        .STRIDE   (STRIDE),
        .BATCH    (BATCH)
    ) dut (
        .s_axi_lite_ctrl_aclk    (aclk),
        .s_axi_lite_ctrl_aresetn (aresetn),
        .s_axi_lite_ctrl_awaddr  (awaddr),
        .s_axi_lite_ctrl_awprot  (3'd0),
        .s_axi_lite_ctrl_awvalid (awvalid),
        .s_axi_lite_ctrl_awready (awready),
        .s_axi_lite_ctrl_wdata   (wdata),
        .s_axi_lite_ctrl_wstrb   (4'hF),
        .s_axi_lite_ctrl_wvalid  (wvalid),
        .s_axi_lite_ctrl_wready  (wready),
        .s_axi_lite_ctrl_bresp   (bresp),
        .s_axi_lite_ctrl_bvalid  (bvalid),
        .s_axi_lite_ctrl_bready  (bready),
        .s_axi_lite_ctrl_araddr  (4'd0),
        .s_axi_lite_ctrl_arprot  (3'd0),
        .s_axi_lite_ctrl_arvalid (1'b0),
        .s_axi_lite_ctrl_arready (),
        .s_axi_lite_ctrl_rdata   (),
        .s_axi_lite_ctrl_rresp   (),
        .s_axi_lite_ctrl_rvalid  (),
        .s_axi_lite_ctrl_rready  (1'b1),

        .S_AXIS_DATA_ACLK    (aclk),
        .S_AXIS_DATA_ARESETN (aresetn),
        .S_AXIS_DATA_TREADY  (s_tready),
        .S_AXIS_DATA_TDATA   (s_tdata),
        .S_AXIS_DATA_TSTRB   (4'hF),
        .S_AXIS_DATA_TLAST   (s_tlast),
        .S_AXIS_DATA_TVALID  (s_tvalid),

        .M_AXIS_RESULT_ACLK    (aclk),
        .M_AXIS_RESULT_ARESETN (aresetn),
        .M_AXIS_RESULT_TVALID  (m_tvalid),
        .M_AXIS_RESULT_TDATA   (m_tdata),
        .M_AXIS_RESULT_TSTRB   (),
        .M_AXIS_RESULT_TLAST   (m_tlast),
        .M_AXIS_RESULT_TREADY  (m_tready)
    );

    // ================= 黄金激励 =================
    // reads_cw.hex：每行一条读段的 300 bit 码字（位平面布局，bit k = 码流第 k 位），
    // 与 make_golden.py 的 reads.hex 同源。它既是**激励**也是本判据的**期望值**：
    // 引擎把装载进来的码字原样搬进结果记录的 bit 325:26，所以
    // 「结果 k 的码字 == 读段 k 的码字」是一条不依赖比对算法的强判据。
    reg [CODEBITS-1:0] read_cw [0:NREADS-1];
    reg [1:0]          wm_sym  [0:WM_SYMS-1];

    task load_golden;
        integer fd, code, i;
        reg [CODEBITS-1:0] v;
        reg [31:0] s;
        begin
            fd = $fopen("tests/golden/reads_cw.hex", "r");
            if (fd == 0) begin
                $display("[TB] FATAL: 打不开 tests/golden/reads_cw.hex");
                $fatal(1);
                $finish;
            end
            for (i = 0; i < NREADS; i = i + 1) begin
                code = $fscanf(fd, "%h", v);
                if (code != 1) begin
                    $display("[TB] FATAL: reads_cw.hex 只有 %0d 行，少于需要的 %0d 行", i, NREADS);
                    $fatal(1);
                    $finish;
                end
                read_cw[i] = v;
            end
            $fclose(fd);

            fd = $fopen("tests/golden/wm_regions.hex", "r");
            if (fd == 0) begin
                $display("[TB] FATAL: 打不开 tests/golden/wm_regions.hex");
                $fatal(1);
                $finish;
            end
            for (i = 0; i < WM_SYMS; i = i + 1) begin
                code = $fscanf(fd, "%h", s);
                if (code != 1) begin
                    $display("[TB] FATAL: wm_regions.hex 只有 %0d 行，少于需要的 %0d 行", i, WM_SYMS);
                    $fatal(1);
                    $finish;
                end
                wm_sym[i] = s[1:0];
            end
            $fclose(fd);
            $display("[TB] 已载入 %0d 条读段码字 + %0d 个水印符号", NREADS, WM_SYMS);
        end
    endtask

    // ================= 伪随机（LFSR，与 tb_dna_result_axis 同风格）=================
    reg [15:0] lfsr_tx = 16'hACE1;
    reg [15:0] lfsr_rx = 16'h1B26;
    always @(posedge aclk) begin
        lfsr_rx <= {lfsr_rx[14:0], lfsr_rx[15] ^ lfsr_rx[13] ^ lfsr_rx[12] ^ lfsr_rx[10]};
        if (!aresetn) m_tready <= 1'b0;
        else          m_tready <= (lfsr_rx[3:0] != 4'd0);   // 约 1/16 的拍撤 TREADY
    end

    function [15:0] lfsr_next;
        input [15:0] v;
        begin
            lfsr_next = {v[14:0], v[15] ^ v[13] ^ v[12] ^ v[10]};
        end
    endfunction

    // ================= AXI-Lite 写 =================
    // AWREADY/WREADY 在本从机里是组合的（~pending & ~bvalid），可以同时发起。
    task axil_write;
        input [3:0]  addr;
        input [31:0] data;
        begin
            @(posedge aclk);
            awaddr  <= addr;
            wdata   <= data;
            awvalid <= 1'b1;
            wvalid  <= 1'b1;
            bready  <= 1'b1;
            @(posedge aclk);
            while (!(awready && wready)) @(posedge aclk);
            awvalid <= 1'b0;
            wvalid  <= 1'b0;
            while (!bvalid) @(posedge aclk);
            if (bresp !== 2'b00) begin
                errors = errors + 1;
                $display("[TB] FAIL: 写 reg[0x%0h] 返回 BRESP=%b", addr, bresp);
            end
            @(posedge aclk);
            bready <= 1'b0;
            @(posedge aclk);
        end
    endtask

    // ================= S_AXIS 送一拍 =================
    // gap_lvl：LFSR 低位小于该值时先插 1~3 拍空档，模拟 DMA 的不连续供数。
    task axis_beat;
        input [31:0] data;
        input        last;
        input integer gap_lvl;
        integer g;
        begin
            lfsr_tx = lfsr_next(lfsr_tx);
            if (lfsr_tx[3:0] < gap_lvl[3:0]) begin
                g = 1 + (lfsr_tx[5:4]);
                repeat (g) begin
                    @(posedge aclk);
                    s_tvalid <= 1'b0;
                end
            end
            @(posedge aclk);
            s_tdata  <= data;
            s_tlast  <= last;
            s_tvalid <= 1'b1;
            @(posedge aclk);
            while (!s_tready) @(posedge aclk);   // VALID 已置起就不许撤，只等 READY
            s_tvalid <= 1'b0;
            s_tlast  <= 1'b0;
        end
    endtask

    // ================= 水印预载（走真实 preload 通路）=================
    task preload_watermark;
        integer r, k;
        begin
            for (r = 0; r < NUM_LC; r = r + 1) begin
                axil_write(REG1, r);            // 先选区域
                repeat (20) @(posedge aclk);
                axil_write(REG0, 32'h2);        // 再进预载模式
                repeat (20) @(posedge aclk);
                for (k = 0; k < REF_LEN; k = k + 1)
                    axis_beat({30'd0, wm_sym[r*REF_LEN + k]}, (k == REF_LEN-1), 2);
                repeat (50) @(posedge aclk);
                axil_write(REG0, 32'h0);        // 退出预载模式
                repeat (20) @(posedge aclk);
                if (dut.wm_waddr !== 11'd0) begin
                    errors = errors + 1;
                    $display("[TB] FAIL: 区域 %0d 预载后 wm_waddr=%0d，应回到 0", r, dut.wm_waddr);
                end
            end
            $display("[TB] 水印预载完成：%0d 区域 x %0d 符号 @%0t", NUM_LC, REF_LEN, $time);
        end
    endtask

    // ================= 送读段 =================
    task send_reads;
        integer i, w;
        reg [31:0] word;
        begin
            for (i = 0; i < NREADS; i = i + 1) begin
                for (w = 0; w < NWORDS; w = w + 1) begin
                    if (w == NWORDS-1)
                        word = {20'd0, read_cw[i][CODEBITS-1:288]};   // 末字只有低 12 bit 有效
                    else
                        word = read_cw[i][32*w +: 32];
                    // TLAST 打在每「帧」（BATCH 条）的最后一拍，模拟 MM2S 每个 BD 一个包
                    axis_beat(word, ((i % BATCH) == BATCH-1) && (w == NWORDS-1), 3);
                end
                // 第一帧送完就拉 start（照抄 echo.c：PIPE_TX_PREFILL -> PIPE_START_IP）
                if (i == BATCH-1) begin
                    axil_write(REG0, 32'h1);
                    $display("[TB] [STAGE1] IP core START @%0t（已预填 %0d 条）", $time, BATCH);
                end
            end
            $display("[TB] %0d 条读段全部送入 @%0t", NREADS, $time);
        end
    endtask

    // ================= 收结果并逐条比对 =================
    integer rec_cnt  = 0;
    integer beat_cnt = 0;
    reg [383:0] rec_acc = 384'd0;

    task check_record;
        input integer idx;
        input [383:0] acc;
        reg [RESULT_W-1:0] rec;
        reg [CODEBITS-1:0] got_cw, exp_cw;
        reg [POS_W-1:0]    got_pos;
        reg [SCORE_W-1:0]  got_sc;
        integer j;
        begin
            rec     = acc[RESULT_W-1:0];
            got_sc  = rec[SCORE_W-1:0];
            got_pos = rec[SCORE_W+POS_W-1:SCORE_W];
            got_cw  = rec[RESULT_W-1:SCORE_W+POS_W];

            if (acc[383:RESULT_W] !== 58'd0) begin
                errors = errors + 1;
                $display("[TB] FAIL: 记录 %0d 末拍高 58 bit 非零（0x%0h）", idx, acc[575:RESULT_W]);
            end
            if (idx >= NREADS) begin
                errors = errors + 1;
                $display("[TB] FAIL: 收到第 %0d 条记录，但只送入了 %0d 条读段（多出来的记录）",
                         idx+1, NREADS);
            end else begin
                exp_cw = read_cw[idx];
                if (^got_cw === 1'bx) begin
                    cw_bad = cw_bad + 1;
                    if (cw_bad <= 6)
                        $display("[TB] FAIL: 记录 %0d 的码字含 X/Z（装载到了从未写入的 FIFO 槽位）", idx);
                end else if (got_cw !== exp_cw) begin
                    cw_bad = cw_bad + 1;
                    if (cw_bad <= 6) begin
                        $display("[TB] FAIL: 记录 %0d 的码字 != 送入的第 %0d 条读段", idx, idx);
                        $display("[TB]        got = %75h", got_cw);
                        $display("[TB]        exp = %75h", exp_cw);
                        for (j = 0; j < NREADS; j = j + 1)
                            if (got_cw === read_cw[j])
                                $display("[TB]        >>> 它其实等于读段 %0d（错位 %0d 条）", j, j - idx);
                    end
                end
            end
            if (idx < 3)
                $display("[TB]   记录 %0d: score=%0d pos=%0d", idx, got_sc, got_pos);
        end
    endtask

    always @(posedge aclk) begin
        if (aresetn && m_tvalid && m_tready) begin
            if (m_tvalid === 1'bx || m_tlast === 1'bx) begin
                errors = errors + 1;
                $display("[TB] FAIL: M_AXIS_RESULT 的 TVALID/TLAST 含 X @%0t", $time);
            end
            rec_acc[64*beat_cnt +: 64] = m_tdata;
            if (m_tlast) begin
                if (beat_cnt != BEATS-1) begin
                    errors = errors + 1;
                    $display("[TB] FAIL: 记录 %0d 的 TLAST 出现在第 %0d 拍（应为第 %0d 拍）",
                             rec_cnt, beat_cnt+1, BEATS);
                end
                check_record(rec_cnt, rec_acc);
                rec_acc  = 384'd0;
                beat_cnt = 0;
                rec_cnt  = rec_cnt + 1;
            end else begin
                if (beat_cnt == BEATS-1) begin
                    errors = errors + 1;
                    $display("[TB] FAIL: 记录 %0d 第 %0d 拍仍未拉 TLAST", rec_cnt, BEATS);
                end
                beat_cnt = beat_cnt + 1;
            end
        end
    end

    // ================= 主流程 =================
    integer wait_cyc;
    initial begin
        $display("[TB] ====== DNA 核入口逐条判据（B26 复现/回归）======");
        $display("[TB] 几何：READ_BPS=%0d CODEBITS=%0d REF_LEN=%0d（与生产一致）；NUM_LC=%0d STRIDE=%0d BATCH=%0d（仅为缩短仿真）",
                 READ_BPS, CODEBITS, REF_LEN, NUM_LC, STRIDE, BATCH);
        load_golden();

        aresetn = 1'b0;
        repeat (20) @(posedge aclk);
        aresetn = 1'b1;
        repeat (20) @(posedge aclk);

        axil_write(REG0, 32'h0);
        axil_write(REG1, 32'h0);

        preload_watermark();
        if (errors != 0) finish_report;

        send_reads();

        wait_cyc = 0;
        while (rec_cnt < NREADS && wait_cyc < 2000000) begin
            @(posedge aclk);
            wait_cyc = wait_cyc + 1;
        end
        repeat (100000) @(posedge aclk);   // 再多跑一段，抓「多吐记录」的情况

        $display("[TB] --------------------------------------------------");
        $display("[TB] RESULT reads_sent=%0d records_received=%0d cw_mismatch=%0d",
                 NREADS, rec_cnt, cw_bad);
        if (rec_cnt != NREADS) begin
            errors = errors + 1;
            $display("[TB] FAIL: 送入 %0d 条读段，收到 %0d 条记录", NREADS, rec_cnt);
            $display("[TB]        S_AXIS TVALID=%b TREADY=%b | M_AXIS TVALID=%b TREADY=%b | in_count=%0d empty=%b | eng st=%0d busy=%b",
                     s_tvalid, s_tready, m_tvalid, m_tready,
                     dut.in_count, dut.in_empty, dut.u_srpe_batch.st, dut.eng_busy);
        end
        if (cw_bad != 0) begin
            errors = errors + 1;
            $display("[TB] FAIL: %0d / %0d 条记录的码字与送入的读段不符（B26 特征）",
                     cw_bad, rec_cnt);
        end else if (rec_cnt == NREADS) begin
            $display("[TB]   ok  %0d 条记录的码字逐位等于送入的第 k 条读段", rec_cnt);
        end
        finish_report;
    end

    task finish_report;
        begin
            $display("[TB] --------------------------------------------------");
            // 【XSim 2022.2 的坑】$fatal 在这里**不会**终止仿真、也不会让 xsim 非零退出
            // （实测：$fatal 之后代码继续往下跑）。所以：
            //   1. 用 if/else 保证「失败路径绝不打印 PASS」；
            //   2. $fatal 之后显式 $finish，避免仿真挂死到看门狗；
            //   3. 真正的判定由 tools/run_xsim.sh 做：日志里出现 FAIL 关键字即判失败，
            //      且必须出现 PASS 标记才算通过。
            if (errors != 0) begin
                $display("[TB] tb_dna_ingress_result FAIL（%0d 项）", errors);
                $fatal(1);
                $finish;
            end else begin
                $display("[TB] PASS  送入 %0d 条 -> 收到 %0d 条，第 k 条结果的码字 == 第 k 条读段的码字",
                         NREADS, rec_cnt);
                $finish;
            end
        end
    endtask

    // 全局看门狗
    initial begin
        #200_000_000;                 // 200 ms
        $display("[TB] FATAL: tb_dna_ingress_result 超时（rec_cnt=%0d）—— 判 FAIL", rec_cnt);
        $fatal(1);
        $finish;
    end

endmodule
