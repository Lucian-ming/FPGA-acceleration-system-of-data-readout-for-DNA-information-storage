`timescale 1ns/1ps
//=============================================================================
// tb_dna_result_axis —— DNA 核 M_AXIS_RESULT 输出级的逐拍判据（缺陷 B23 的回归）
//
// 为什么需要这个 TB：
//   `AXI DMA MM2S -> DNA S_AXIS` 与 `DNA M_AXIS -> AXI DMA S2MM` 这条链此前
//   没有任何仿真覆盖（docs/06-verification-plan.md的真实AXIS/BD接口判据）。
//   run_m2_full.sh 的 Stage1 只编译 srpe_batch.v + tb_srpe_batch.v，直接抓引擎的
//   res_din 记录，**完全绕开** Dna_accelerator_core_v1_0.v 的 AXIS 输出级和
//   s2mm_pack64。于是 B23（TDATA 组合直连、TVALID 寄存，数据比 valid 早一拍）
//   在所有仿真里都是绿的，只有上板才暴露。
//
// 本 TB 的做法：
//   用真实的 DUT（Dna_accelerator_core_v1_0），不复制被测逻辑；引擎不启动，
//   改为 force 内部的 eng_res_wr / eng_res_din，把已知的 326 bit 记录直接压进结果
//   FIFO，然后在 M_AXIS_RESULT 上逐拍核对。
//
// 判据（任一条不满足即 FAIL 并以非零码退出）：
//   1. 每个 packet 恰好 9 拍，TLAST 只在第 9 拍拉高；
//   2. 第 k 拍必须逐位等于 tests/golden/se250/stage2_in.hex 里该记录的第 k 个 64-bit 字；
//   3. 记录条数、总拍数都必须与送入的一致（不许多、不许少）；
//   4. 全程在随机 TREADY 背压下成立（B23 正是在真实 DMA 背压下才显形）。
//=============================================================================
module tb_dna_result_axis;

    localparam integer NREC      = 64;      // 核对的记录条数
    localparam integer BEATS     = 6;       // 每条记录 6 拍 x 64 bit = 48 B
    localparam integer RESULT_W  = 326;     // CODEBITS(300) + POS_W(16) + SCORE_W(10)
    localparam integer GOLD_LINES= 24576;   // stage2_in.hex 全长：4096 条 x 6 字
    localparam integer GAP       = 64;      // 两条记录之间的间隔拍数（模拟引擎产出节奏）

    reg aclk = 1'b0;
    reg aresetn = 1'b0;
    always #5 aclk = ~aclk;                 // 100 MHz

    // ---- DUT 端口 ----
    reg         m_tready = 1'b0;
    wire        m_tvalid, m_tlast;
    wire [63:0] m_tdata;

    Dna_accelerator_core_v1_0 dut (
        .s_axi_lite_ctrl_aclk    (aclk),
        .s_axi_lite_ctrl_aresetn (aresetn),
        .s_axi_lite_ctrl_awaddr  (4'd0),
        .s_axi_lite_ctrl_awprot  (3'd0),
        .s_axi_lite_ctrl_awvalid (1'b0),
        .s_axi_lite_ctrl_awready (),
        .s_axi_lite_ctrl_wdata   (32'd0),
        .s_axi_lite_ctrl_wstrb   (4'd0),
        .s_axi_lite_ctrl_wvalid  (1'b0),
        .s_axi_lite_ctrl_wready  (),
        .s_axi_lite_ctrl_bresp   (),
        .s_axi_lite_ctrl_bvalid  (),
        .s_axi_lite_ctrl_bready  (1'b1),
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
        .S_AXIS_DATA_TREADY  (),
        .S_AXIS_DATA_TDATA   (32'd0),
        .S_AXIS_DATA_TSTRB   (4'hF),
        .S_AXIS_DATA_TLAST   (1'b0),
        .S_AXIS_DATA_TVALID  (1'b0),

        .M_AXIS_RESULT_ACLK    (aclk),
        .M_AXIS_RESULT_ARESETN (aresetn),
        .M_AXIS_RESULT_TVALID  (m_tvalid),
        .M_AXIS_RESULT_TDATA   (m_tdata),
        .M_AXIS_RESULT_TSTRB   (),
        .M_AXIS_RESULT_TLAST   (m_tlast),
        .M_AXIS_RESULT_TREADY  (m_tready)
    );

    // ---- 黄金向量：tests/golden/se250/stage2_in.hex（每行一个 64 bit 字，9 行一条记录）----
    reg [63:0] gold [0:GOLD_LINES-1];

    // ---- 注入侧 ----
    reg                  inj_wr  = 1'b0;
    reg [RESULT_W-1:0]   inj_din = {RESULT_W{1'b0}};
    integer sent = 0;

    // ---- 收侧计数与判据 ----
    integer got_beats = 0;      // 已收到的总拍数
    integer errors    = 0;
    integer rec_idx, beat_idx;
    reg [63:0] expected;

    // 随机背压
    reg [15:0] lfsr = 16'hACE1;
    always @(posedge aclk) begin
        lfsr <= {lfsr[14:0], lfsr[15] ^ lfsr[13] ^ lfsr[12] ^ lfsr[10]};
        if (sent < 16)
            m_tready <= 1'b1;                 // 前 16 条：无背压
        else
            m_tready <= (lfsr[3:0] != 4'd0);  // 之后：约 1/16 的拍拉低 TREADY
    end

    //-------------------------------------------------------------------------
    // 逐拍核对
    //-------------------------------------------------------------------------
    always @(posedge aclk) begin
        if (aresetn && m_tvalid && m_tready) begin
            rec_idx  = got_beats / BEATS;
            beat_idx = got_beats % BEATS;
            expected = gold[rec_idx*BEATS + beat_idx];

            if (m_tdata !== expected) begin
                errors = errors + 1;
                if (errors <= 10)
                    $display("[FAIL] rec %0d beat %0d: got %016x expected %016x",
                             rec_idx, beat_idx, m_tdata, expected);
            end
            if (m_tlast !== (beat_idx == BEATS-1)) begin
                errors = errors + 1;
                if (errors <= 10)
                    $display("[FAIL] rec %0d beat %0d: TLAST=%b expected %b",
                             rec_idx, beat_idx, m_tlast, (beat_idx == BEATS-1));
            end
            got_beats = got_beats + 1;
        end
    end

    //-------------------------------------------------------------------------
    // 注入：把黄金记录的低 326 bit 直接写进结果 FIFO
    //-------------------------------------------------------------------------
    reg [383:0] rec_full;
    integer i, k;
    initial begin
        $readmemh("tests/golden/stage2_in.hex", gold);

        repeat (10) @(posedge aclk);
        aresetn = 1'b1;
        repeat (10) @(posedge aclk);

        // 引擎不启动（AXI-Lite 全程空闲），改为直接驱动结果 FIFO 的写口
        force dut.eng_res_wr  = inj_wr;
        force dut.eng_res_din = inj_din;

        for (i = 0; i < NREC; i = i + 1) begin
            rec_full = 384'd0;
            for (k = 0; k < BEATS; k = k + 1)
                rec_full[k*64 +: 64] = gold[i*BEATS + k];

            // FIFO 满就等
            while (dut.res_full === 1'b1) @(posedge aclk);

            // 写入结果 FIFO（低 326 bit 是有效记录内容）
            @(negedge aclk);
            inj_din = rec_full[RESULT_W-1:0];
            inj_wr  = 1'b1;
            @(negedge aclk);
            inj_wr  = 1'b0;
            sent    = i + 1;

            // 按引擎的真实节奏投喂：srpe_batch 每条读段要几百拍才吐一条结果，
            // 板上结果 FIFO 因此始终很浅。这里留 GAP 拍间隔来复现板上工况。
            // （把 GAP 调到 0 会让 FIFO 积压，那是另一个régime，见 docs/03-status.md B24。）
            repeat (GAP) @(posedge aclk);
        end

        // 等收齐（或超时）
        i = 0;
        while (got_beats < NREC*BEATS && i < 200000) begin
            @(posedge aclk);
            i = i + 1;
        end

        // 再多等一段，确认没有多余的拍冒出来
        repeat (200) @(posedge aclk);

        $display("---------------------------------------------");
        $display("送入记录 %0d 条，应收 %0d 拍，实收 %0d 拍，逐拍不符 %0d 处",
                 NREC, NREC*BEATS, got_beats, errors);

        if (errors != 0) begin
            $display("[FAIL] M_AXIS_RESULT 逐拍比对不通过（B23 未修复或再次回归）");
            $fatal(1);
            $finish;   // [XSim 2022.2] $fatal 在这里既不终止仿真也不让 xsim 非零退出，必须显式收尾
        end else if (got_beats != NREC*BEATS) begin
            $display("[FAIL] 拍数不符：实收 %0d，应为 %0d", got_beats, NREC*BEATS);
            $fatal(1);
            $finish;   // [XSim 2022.2] $fatal 在这里既不终止仿真也不让 xsim 非零退出，必须显式收尾
        end else begin
            $display("PASS: %0d 条记录 x %0d 拍在随机 TREADY 背压下逐位正确，TLAST 位置正确",
                     NREC, BEATS);
            $finish;
        end
    end

    // 硬超时保护
    initial begin
        #5_000_000;
        $display("[FAIL] 仿真超时，未在限定时间内收齐 %0d 拍（实收 %0d）",
                 NREC*BEATS, got_beats);
        $fatal(1);
        $finish;   // [XSim 2022.2] $fatal 在这里既不终止仿真也不让 xsim 非零退出，必须显式收尾
    end

endmodule
