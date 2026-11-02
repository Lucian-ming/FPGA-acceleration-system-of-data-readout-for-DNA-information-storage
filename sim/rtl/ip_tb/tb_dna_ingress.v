`timescale 1ns / 1ps

// DNA 顶层 AXIS 入口判据：
// 1. 10x32 bit 必须组装成一条 300 bit 读段；
// 2. 引擎长时间 busy 时，输入 FIFO 满后必须对 DMA 施加背压，不能静默丢数据。
module tb_dna_ingress;
    localparam integer CLK_PERIOD = 10;
    localparam integer OFFER_READS = 1100;

    reg clk = 1'b0;
    reg rst_n = 1'b0;
    always #(CLK_PERIOD/2) clk = ~clk;

    wire s_ready;
    reg [31:0] s_data = 32'd0;
    reg [3:0] s_strb = 4'hF;
    reg s_last = 1'b0;
    reg s_valid = 1'b0;

    wire m_valid;
    wire [63:0] m_data;
    wire [7:0] m_strb;
    wire m_last;

    reg [299:0] expected_read;
    integer word_index;
    integer offered_word;
    integer accepted_words;
    integer saw_backpressure;

    dna_accelerator_core_v1_0 dut (
        .s_axi_lite_ctrl_aclk(clk),
        .s_axi_lite_ctrl_aresetn(rst_n),
        .s_axi_lite_ctrl_awaddr(4'd0),
        .s_axi_lite_ctrl_awprot(3'd0),
        .s_axi_lite_ctrl_awvalid(1'b0),
        .s_axi_lite_ctrl_awready(),
        .s_axi_lite_ctrl_wdata(32'd0),
        .s_axi_lite_ctrl_wstrb(4'd0),
        .s_axi_lite_ctrl_wvalid(1'b0),
        .s_axi_lite_ctrl_wready(),
        .s_axi_lite_ctrl_bresp(),
        .s_axi_lite_ctrl_bvalid(),
        .s_axi_lite_ctrl_bready(1'b1),
        .s_axi_lite_ctrl_araddr(4'd0),
        .s_axi_lite_ctrl_arprot(3'd0),
        .s_axi_lite_ctrl_arvalid(1'b0),
        .s_axi_lite_ctrl_arready(),
        .s_axi_lite_ctrl_rdata(),
        .s_axi_lite_ctrl_rresp(),
        .s_axi_lite_ctrl_rvalid(),
        .s_axi_lite_ctrl_rready(1'b1),
        .S_AXIS_DATA_ACLK(clk),
        .S_AXIS_DATA_ARESETN(rst_n),
        .S_AXIS_DATA_TREADY(s_ready),
        .S_AXIS_DATA_TDATA(s_data),
        .S_AXIS_DATA_TSTRB(s_strb),
        .S_AXIS_DATA_TLAST(s_last),
        .S_AXIS_DATA_TVALID(s_valid),
        .M_AXIS_RESULT_ACLK(clk),
        .M_AXIS_RESULT_ARESETN(rst_n),
        .M_AXIS_RESULT_TVALID(m_valid),
        .M_AXIS_RESULT_TDATA(m_data),
        .M_AXIS_RESULT_TSTRB(m_strb),
        .M_AXIS_RESULT_TLAST(m_last),
        .M_AXIS_RESULT_TREADY(1'b1)
    );

    task send_compliant_word;
        input [31:0] data;
        input last;
        begin
            @(negedge clk);
            s_data = data;
            s_last = last;
            s_valid = 1'b1;
            while (!s_ready) @(negedge clk);
            @(posedge clk);
            @(negedge clk);
            s_valid = 1'b0;
            s_last = 1'b0;
        end
    endtask

    initial begin
        expected_read = 300'd0;
        accepted_words = 0;
        saw_backpressure = 0;

        repeat (8) @(posedge clk);
        rst_n = 1'b1;
        repeat (4) @(posedge clk);

        // 尾批超时阈值为 100000，计数器必须能表示并触发该值。
        force dut.in_count = 12'd1;
        force dut.idle_counter = 17'd100000;
        #1;
        if (!dut.trigger_timeout) begin
            $display("[TB] idle_counter 位宽不足，100000 周期超时不可达");
            $fatal(1);
            $finish;
        end
        release dut.idle_counter;
        release dut.in_count;
        rst_n = 1'b0;
        repeat (2) @(posedge clk);
        rst_n = 1'b1;
        repeat (4) @(posedge clk);

        // 一条带独特尾拍的读段，钉死 10 拍组装位序。
        for (word_index = 0; word_index < 10; word_index = word_index + 1) begin
            if (word_index < 9)
                expected_read[word_index*32 +: 32] = 32'hA5000000 + word_index;
            else
                expected_read[299:288] = (32'hA5000000 + word_index) & 12'hFFF;
            send_compliant_word(32'hA5000000 + word_index, word_index == 9);
        end
        repeat (3) @(posedge clk);
        if (dut.u_in_fifo.mem[0] !== expected_read) begin
            $display("[TB] 组装错误: got=%h expect=%h", dut.u_in_fifo.mem[0], expected_read);
            $fatal(1);
            $finish;
        end

        // 隔离入口流控：模拟引擎长时间计算，不让它从 FIFO 取数。
        force dut.eng_busy = 1'b1;
        for (offered_word = 0; offered_word < OFFER_READS*10; offered_word = offered_word + 1) begin
            @(negedge clk);
            s_valid = 1'b1;
            s_data = offered_word;
            s_last = ((offered_word % 10) == 9);
            @(posedge clk);
            if (s_ready)
                accepted_words = accepted_words + 1;
            else
                saw_backpressure = 1;
        end
        @(negedge clk);
        s_valid = 1'b0;
        s_last = 1'b0;
        repeat (4) @(posedge clk);

        if (!saw_backpressure) begin
            $display("[TB] FIFO 满后 TREADY 从未拉低，%0d 个拍全部被接受", accepted_words);
            $fatal(1);
            $finish;
        end
        if (dut.u_in_fifo.count !== 256 || dut.in_count !== 256) begin
            $display("[TB] 计数漂移: fifo_count=%0d in_count=%0d",
                     dut.u_in_fifo.count, dut.in_count);
            $fatal(1);
            $finish;
        end

        release dut.eng_busy;
        $display("[TB] PASS: 读段组装正确，FIFO 满后施加背压且计数一致");
        $finish;
    end

    initial begin
        #(CLK_PERIOD * 20000);
        $display("[TB] 超时");
        $fatal(1);
    end
endmodule
