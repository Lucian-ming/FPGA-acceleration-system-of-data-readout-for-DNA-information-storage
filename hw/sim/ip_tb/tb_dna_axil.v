`timescale 1ns / 1ps

// DNA 控制口 AXI-Lite 判据：AW/W 是独立通道，任一通道都不能等待另一通道才握手。
module tb_dna_axil;
    localparam integer CLK_PERIOD = 10;

    reg clk = 1'b0;
    reg rst_n = 1'b0;
    always #(CLK_PERIOD/2) clk = ~clk;

    reg [3:0] awaddr = 4'd0;
    reg awvalid = 1'b0;
    wire awready;
    reg [31:0] wdata = 32'd0;
    reg [3:0] wstrb = 4'hF;
    reg wvalid = 1'b0;
    wire wready;
    wire [1:0] bresp;
    wire bvalid;
    reg bready = 1'b1;
    wire [31:0] reg0;
    wire [31:0] reg1;

    Dna_accelerator_core_v1_0_S_AXI_LITE_CTRL dut (
        .slv_reg0_out(reg0),
        .slv_reg1_out(reg1),
        .slv_reg2_out(),
        .slv_reg3_out(),
        .S_AXI_ACLK(clk),
        .S_AXI_ARESETN(rst_n),
        .S_AXI_AWADDR(awaddr),
        .S_AXI_AWPROT(3'd0),
        .S_AXI_AWVALID(awvalid),
        .S_AXI_AWREADY(awready),
        .S_AXI_WDATA(wdata),
        .S_AXI_WSTRB(wstrb),
        .S_AXI_WVALID(wvalid),
        .S_AXI_WREADY(wready),
        .S_AXI_BRESP(bresp),
        .S_AXI_BVALID(bvalid),
        .S_AXI_BREADY(bready),
        .S_AXI_ARADDR(4'd0),
        .S_AXI_ARPROT(3'd0),
        .S_AXI_ARVALID(1'b0),
        .S_AXI_ARREADY(),
        .S_AXI_RDATA(),
        .S_AXI_RRESP(),
        .S_AXI_RVALID(),
        .S_AXI_RREADY(1'b1)
    );

    task wait_awready;
        integer cycles;
        begin
            cycles = 0;
            while (!awready && cycles < 10) begin
                @(posedge clk);
                cycles = cycles + 1;
            end
            if (!awready) begin
                $display("[TB] AW 通道等待 WVALID，独立握手死锁");
                $fatal(1);
            end
        end
    endtask

    task wait_wready;
        integer cycles;
        begin
            cycles = 0;
            while (!wready && cycles < 10) begin
                @(posedge clk);
                cycles = cycles + 1;
            end
            if (!wready) begin
                $display("[TB] W 通道等待 AWVALID，独立握手死锁");
                $fatal(1);
            end
        end
    endtask

    task wait_bvalid;
        integer cycles;
        begin
            cycles = 0;
            while (!bvalid && cycles < 10) begin
                @(posedge clk);
                cycles = cycles + 1;
            end
            if (!bvalid || bresp != 2'b00) begin
                $display("[TB] 写响应缺失或错误: bvalid=%b bresp=%b", bvalid, bresp);
                $fatal(1);
            end
            @(posedge clk);
        end
    endtask

    initial begin
        repeat (5) @(posedge clk);
        rst_n = 1'b1;
        repeat (2) @(posedge clk);

        // 地址先于数据。
        @(negedge clk);
        awaddr = 4'h0;
        awvalid = 1'b1;
        wait_awready;
        @(negedge clk);
        awvalid = 1'b0;
        wdata = 32'h12345678;
        wvalid = 1'b1;
        wait_wready;
        @(negedge clk);
        wvalid = 1'b0;
        wait_bvalid;
        if (reg0 !== 32'h12345678) $fatal(1, "AW->W 写入值错误");

        // 数据先于地址，并检查字节写使能。
        @(negedge clk);
        wdata = 32'hAABBCCDD;
        wstrb = 4'b0011;
        wvalid = 1'b1;
        wait_wready;
        @(negedge clk);
        wvalid = 1'b0;
        awaddr = 4'h4;
        awvalid = 1'b1;
        wait_awready;
        @(negedge clk);
        awvalid = 1'b0;
        wait_bvalid;
        if (reg1 !== 32'h0000CCDD) $fatal(1, "W->AW 写入值错误");

        $display("[TB] PASS: AW/W 独立握手与 WSTRB 正确");
        $finish;
    end

    initial begin
        #(CLK_PERIOD * 200);
        $fatal(1, "AXI-Lite 测试超时");
    end
endmodule
