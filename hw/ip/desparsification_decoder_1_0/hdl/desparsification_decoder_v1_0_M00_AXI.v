// FILE: desparsification_decoder_v1_0_M00_AXI.v
// 修复点：
//  - 将 WSTRB 从固定全 1 改为由上层输入（支持尾包部分字节写）
//  - 其他读/写 FSM、握手、计数保持原样

`timescale 1 ns / 1 ps

module desparsification_decoder_v1_0_M00_AXI #
(
    parameter integer C_M_AXI_DATA_WIDTH = 64,
    parameter integer C_M_AXI_ADDR_WIDTH = 32
)
(
    input  wire                              M00_AXI_ACLK,
    input  wire                              M00_AXI_ARESETN,

    // 命令接口
    input  wire                              start_read_transaction,
    input  wire [C_M_AXI_ADDR_WIDTH-1:0]     read_addr,
    input  wire [7:0]                        read_len,
    output reg                               read_data_ready,
    output reg  [C_M_AXI_DATA_WIDTH-1:0]     read_data,

    input  wire                              start_write_transaction,
    input  wire [C_M_AXI_ADDR_WIDTH-1:0]     write_addr,
    input  wire [7:0]                        write_len,
    output reg                               write_data_ready,
    input  wire [C_M_AXI_DATA_WIDTH-1:0]     write_data,
    input  wire                              write_data_valid,
    input  wire [C_M_AXI_DATA_WIDTH/8-1:0]   write_strb,      // ← 新增
    output reg                               write_done,

    // AXI4 Master
    output wire [C_M_AXI_ADDR_WIDTH-1:0]     M00_AXI_AWADDR,
    output wire [7:0]                        M00_AXI_AWLEN,
    output wire [2:0]                        M00_AXI_AWSIZE,
    output wire [1:0]                        M00_AXI_AWBURST,
    output wire [0:0]                        M00_AXI_AWLOCK,
    output wire [3:0]                        M00_AXI_AWCACHE,
    output wire [2:0]                        M00_AXI_AWPROT,
    output wire [3:0]                        M00_AXI_AWQOS,
    output wire                              M00_AXI_AWVALID,
    input  wire                              M00_AXI_AWREADY,

    output wire [C_M_AXI_DATA_WIDTH-1:0]     M00_AXI_WDATA,
    output wire [C_M_AXI_DATA_WIDTH/8-1:0]   M00_AXI_WSTRB,   // ← 改为用 write_strb
    output wire                              M00_AXI_WLAST,
    output wire                              M00_AXI_WVALID,
    input  wire                              M00_AXI_WREADY,

    input  wire [1:0]                        M00_AXI_BRESP,
    input  wire                              M00_AXI_BVALID,
    output wire                              M00_AXI_BREADY,

    output wire [C_M_AXI_ADDR_WIDTH-1:0]     M00_AXI_ARADDR,
    output wire [7:0]                        M00_AXI_ARLEN,
    output wire [2:0]                        M00_AXI_ARSIZE,
    output wire [1:0]                        M00_AXI_ARBURST,
    output wire [0:0]                        M00_AXI_ARLOCK,
    output wire [3:0]                        M00_AXI_ARCACHE,
    output wire [2:0]                        M00_AXI_ARPROT,
    output wire [3:0]                        M00_AXI_ARQOS,
    output wire                              M00_AXI_ARVALID,
    input  wire                              M00_AXI_ARREADY,

    input  wire [C_M_AXI_DATA_WIDTH-1:0]     M00_AXI_RDATA,
    input  wire [1:0]                        M00_AXI_RRESP,
    input  wire                              M00_AXI_RLAST,
    input  wire                              M00_AXI_RVALID,
    output wire                              M00_AXI_RREADY
);

    // 读/写 FSM（与你原文件一致，这里省略不变部分）
    localparam RD_IDLE=2'b00, RD_SEND_ADDR=2'b01, RD_READ_DATA=2'b10;
    localparam WR_IDLE=3'b000, WR_SEND_ADDR=3'b001, WR_WRITE_DATA=3'b010, WR_GET_RESP=3'b011;

    reg [1:0]  rd_state, rd_next_state;
    reg [2:0]  wr_state, wr_next_state;
    reg [C_M_AXI_ADDR_WIDTH-1:0] int_araddr, int_awaddr;
    reg [7:0] int_arlen, int_awlen;
    reg [7:0] write_beat_counter;
    reg arvalid_reg, awvalid_reg, wvalid_reg, wlast_reg, bready_reg, rready_reg;

    // 固定属性
    assign M00_AXI_ARBURST = 2'b01; // INCR
    assign M00_AXI_ARSIZE  = $clog2(C_M_AXI_DATA_WIDTH/8);
    assign M00_AXI_ARLOCK  = 1'b0;
    assign M00_AXI_ARCACHE = 4'b0010;
    assign M00_AXI_ARPROT  = 3'b000;
    assign M00_AXI_ARQOS   = 4'b0000;

    assign M00_AXI_AWBURST = 2'b01; // INCR
    assign M00_AXI_AWSIZE  = $clog2(C_M_AXI_DATA_WIDTH/8);
    assign M00_AXI_AWLOCK  = 1'b0;
    assign M00_AXI_AWCACHE = 4'b0010;
    assign M00_AXI_AWPROT  = 3'b000;
    assign M00_AXI_AWQOS   = 4'b0000;

    // 连接
    assign M00_AXI_ARADDR  = int_araddr;
    assign M00_AXI_ARLEN   = int_arlen;
    assign M00_AXI_ARVALID = arvalid_reg;

    assign M00_AXI_AWADDR  = int_awaddr;
    assign M00_AXI_AWLEN   = int_awlen;
    assign M00_AXI_AWVALID = awvalid_reg;

    assign M00_AXI_WDATA   = write_data;
    assign M00_AXI_WSTRB   = write_strb; // ← 修复：由上层控制，支持尾包部分写
    assign M00_AXI_WLAST   = wlast_reg;
    assign M00_AXI_WVALID  = wvalid_reg;

    assign M00_AXI_BREADY  = bready_reg;
    assign M00_AXI_RREADY  = rready_reg;

    // ---------------- Read FSM ----------------
    always @(posedge M00_AXI_ACLK or negedge M00_AXI_ARESETN) begin
        if (!M00_AXI_ARESETN) rd_state <= RD_IDLE;
        else rd_state <= rd_next_state;
    end
    always @(*) begin
        rd_next_state   = rd_state;
        arvalid_reg     = 1'b0;
        rready_reg      = 1'b0;
        read_data_ready = 1'b0;
        case (rd_state)
            RD_IDLE:       if (start_read_transaction) rd_next_state = RD_SEND_ADDR;
            RD_SEND_ADDR:  begin arvalid_reg = 1'b1; if (M00_AXI_ARREADY) rd_next_state = RD_READ_DATA; end
            RD_READ_DATA:  begin
                                rready_reg = 1'b1;
                                if (M00_AXI_RVALID) begin
                                    read_data_ready = 1'b1;
                                    if (M00_AXI_RLAST) rd_next_state = RD_IDLE;
                                end
                           end
        endcase
    end
    always @(posedge M00_AXI_ACLK) begin
        if (!M00_AXI_ARESETN) begin int_araddr<=0; int_arlen<=0; end
        else if (rd_state==RD_IDLE && start_read_transaction) begin
            int_araddr <= read_addr;
            int_arlen  <= read_len;
        end
    end
    always @(posedge M00_AXI_ACLK) begin
        if (!M00_AXI_ARESETN) read_data <= {C_M_AXI_DATA_WIDTH{1'b0}};
        else if (rd_state==RD_READ_DATA && M00_AXI_RVALID) read_data <= M00_AXI_RDATA;
    end

    // ---------------- Write FSM ----------------
    always @(posedge M00_AXI_ACLK or negedge M00_AXI_ARESETN) begin
        if (!M00_AXI_ARESETN) wr_state <= WR_IDLE;
        else wr_state <= wr_next_state;
    end
    always @(*) begin
        wr_next_state   = wr_state;
        awvalid_reg     = 1'b0;
        wvalid_reg      = 1'b0;
        wlast_reg       = 1'b0;
        bready_reg      = 1'b0;
        write_data_ready= 1'b0;
        write_done      = 1'b0;

        case (wr_state)
            WR_IDLE:       if (start_write_transaction) wr_next_state = WR_SEND_ADDR;
            WR_SEND_ADDR:  begin
                               awvalid_reg = 1'b1;
                               if (M00_AXI_AWREADY) wr_next_state = WR_WRITE_DATA;
                           end
            WR_WRITE_DATA: begin
                               write_data_ready = 1'b1;
                               if (write_data_valid) begin
                                   wvalid_reg = 1'b1;
                                   if (write_beat_counter == int_awlen) wlast_reg = 1'b1;
                                   if (M00_AXI_WREADY && wlast_reg) wr_next_state = WR_GET_RESP;
                               end
                           end
            WR_GET_RESP:   begin
                               bready_reg = 1'b1;
                               if (M00_AXI_BVALID) begin
                                   write_done   = 1'b1;
                                   wr_next_state= WR_IDLE;
                               end
                           end
        endcase
    end
    always @(posedge M00_AXI_ACLK) begin
        if (!M00_AXI_ARESETN) begin int_awaddr<=0; int_awlen<=0; end
        else if (wr_state==WR_IDLE && start_write_transaction) begin
            int_awaddr <= write_addr;
            int_awlen  <= write_len;
        end
    end
    always @(posedge M00_AXI_ACLK) begin
        if (!M00_AXI_ARESETN) write_beat_counter <= 0;
        else if (wr_state==WR_IDLE) write_beat_counter <= 0;
        else if (wr_state==WR_WRITE_DATA && write_data_ready && write_data_valid && M00_AXI_WREADY)
            write_beat_counter <= write_beat_counter + 1'b1;
    end

endmodule
