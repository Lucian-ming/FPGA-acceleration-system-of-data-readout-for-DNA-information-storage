// FILE: desparsification_decoder_v1_0_S00_AXI.v
// 修复点：
//  - 写通道采用 Xilinx 模板式握手：AW/W 分拍到达也能正确应答 BVALID
//  - 32-bit AXI-Lite，地址映射：
//    0x00 CTRL[0]=ap_start(W1P)，0x04 STATUS{idle,done}
//    0x10/0x14 输入基地址低/高，0x18/0x1C 输出基地址低/高

`timescale 1 ns / 1 ps

module desparsification_decoder_v1_0_S00_AXI #
(
    parameter integer C_S_AXI_DATA_WIDTH = 32,
    parameter integer C_S_AXI_ADDR_WIDTH = 6
)
(
    // To core
    output reg        ap_start,
    output reg [63:0] ddr_input_base_addr,
    output reg [63:0] ddr_output_base_addr,
    input  wire       ap_done,
    input  wire       ap_idle,

    // AXI-Lite
    input  wire                           S00_AXI_ACLK,
    input  wire                           S00_AXI_ARESETN,
    input  wire [C_S_AXI_ADDR_WIDTH-1:0]  S00_AXI_AWADDR,
    input  wire                           S00_AXI_AWVALID,
    output wire                           S00_AXI_AWREADY,
    input  wire [C_S_AXI_DATA_WIDTH-1:0]  S00_AXI_WDATA,
    input  wire [C_S_AXI_DATA_WIDTH/8-1:0]S00_AXI_WSTRB,
    input  wire                           S00_AXI_WVALID,
    output wire                           S00_AXI_WREADY,
    output wire [1:0]                     S00_AXI_BRESP,
    output wire                           S00_AXI_BVALID,
    input  wire                           S00_AXI_BREADY,
    input  wire [C_S_AXI_ADDR_WIDTH-1:0]  S00_AXI_ARADDR,
    input  wire                           S00_AXI_ARVALID,
    output wire                           S00_AXI_ARREADY,
    output wire [C_S_AXI_DATA_WIDTH-1:0]  S00_AXI_RDATA,
    output wire [1:0]                     S00_AXI_RRESP,
    output wire                           S00_AXI_RVALID,
    input  wire                           S00_AXI_RREADY
);

    // 地址映射（word 地址）
    localparam ADDR_CTRL      = 6'h00;
    localparam ADDR_STATUS    = 6'h04;
    localparam ADDR_IN_L      = 6'h10;
    localparam ADDR_IN_H      = 6'h14;
    localparam ADDR_OUT_L     = 6'h18;
    localparam ADDR_OUT_H     = 6'h1C;

    // 内部 AXI 信号
    reg [C_S_AXI_ADDR_WIDTH-1:0] axi_awaddr, axi_araddr;
    reg axi_awready, axi_wready, axi_bvalid;
    reg [1:0] axi_bresp;
    reg axi_arready, axi_rvalid;
    reg [1:0] axi_rresp;
    reg [C_S_AXI_DATA_WIDTH-1:0] axi_rdata;
    reg aw_en;

    // 写寄存器（用户）
    reg        int_ap_start;
    reg [31:0] in_l, in_h, out_l, out_h;

    // 连接到端口
    assign S00_AXI_AWREADY = axi_awready;
    assign S00_AXI_WREADY  = axi_wready;
    assign S00_AXI_BVALID  = axi_bvalid;
    assign S00_AXI_BRESP   = axi_bresp;
    assign S00_AXI_ARREADY = axi_arready;
    assign S00_AXI_RVALID  = axi_rvalid;
    assign S00_AXI_RRESP   = axi_rresp;
    assign S00_AXI_RDATA   = axi_rdata;

    localparam integer ADDR_LSB = 2; // 32-bit 对齐

    // AWREADY（模板写法）
    always @(posedge S00_AXI_ACLK) begin
        if (!S00_AXI_ARESETN) begin
            axi_awready <= 1'b0; aw_en <= 1'b1;
        end else begin
            if (~axi_awready && S00_AXI_AWVALID && S00_AXI_WVALID && aw_en) begin
                axi_awready <= 1'b1; aw_en <= 1'b0;
            end else if (S00_AXI_BREADY && axi_bvalid) begin
                aw_en <= 1'b1; axi_awready <= 1'b0;
            end else begin
                axi_awready <= 1'b0;
            end
        end
    end

    // 记录 AWADDR
    always @(posedge S00_AXI_ACLK) begin
        if (!S00_AXI_ARESETN) axi_awaddr <= 0;
        else if (~axi_awready && S00_AXI_AWVALID && S00_AXI_WVALID && aw_en)
            axi_awaddr <= S00_AXI_AWADDR;
    end

    // WREADY（模板写法）
    always @(posedge S00_AXI_ACLK) begin
        if (!S00_AXI_ARESETN) axi_wready <= 1'b0;
        else if (~axi_wready && S00_AXI_WVALID && S00_AXI_AWVALID && aw_en)
            axi_wready <= 1'b1;
        else
            axi_wready <= 1'b0;
    end

    // 写数据到用户寄存器
    integer i;
    wire slv_reg_wren = axi_wready && S00_AXI_WVALID && axi_awready && S00_AXI_AWVALID;
    always @(posedge S00_AXI_ACLK) begin
        if (!S00_AXI_ARESETN) begin
            int_ap_start <= 1'b0; in_l<=0; in_h<=0; out_l<=0; out_h<=0;
        end else if (slv_reg_wren) begin
            case (axi_awaddr[C_S_AXI_ADDR_WIDTH-1:ADDR_LSB])
                ADDR_CTRL[5:ADDR_LSB]: begin
                    int_ap_start <= S00_AXI_WDATA[0];
                end
                ADDR_IN_L [5:ADDR_LSB]: for (i=0;i<4;i=i+1)
                    if (S00_AXI_WSTRB[i]) in_l [8*i +: 8] <= S00_AXI_WDATA[8*i +: 8];
                ADDR_IN_H [5:ADDR_LSB]: for (i=0;i<4;i=i+1)
                    if (S00_AXI_WSTRB[i]) in_h [8*i +: 8] <= S00_AXI_WDATA[8*i +: 8];
                ADDR_OUT_L[5:ADDR_LSB]: for (i=0;i<4;i=i+1)
                    if (S00_AXI_WSTRB[i]) out_l[8*i +: 8] <= S00_AXI_WDATA[8*i +: 8];
                ADDR_OUT_H[5:ADDR_LSB]: for (i=0;i<4;i=i+1)
                    if (S00_AXI_WSTRB[i]) out_h[8*i +: 8] <= S00_AXI_WDATA[8*i +: 8];
                default:;
            endcase
        end else if (ap_done) begin
            // 完成后自动清 0（W1P）
            int_ap_start <= 1'b0;
        end
    end

    // BRESP（模板写法）
    always @(posedge S00_AXI_ACLK) begin
        if (!S00_AXI_ARESETN) begin
            axi_bvalid <= 1'b0; axi_bresp <= 2'b00;
        end else if (axi_awready && S00_AXI_AWVALID && ~axi_bvalid && axi_wready && S00_AXI_WVALID) begin
            axi_bvalid <= 1'b1; axi_bresp <= 2'b00;
        end else if (S00_AXI_BREADY && axi_bvalid) begin
            axi_bvalid <= 1'b0;
        end
    end

    // ARREADY
    always @(posedge S00_AXI_ACLK) begin
        if (!S00_AXI_ARESETN) begin
            axi_arready <= 1'b0; axi_araddr <= 0;
        end else begin
            if (~axi_arready && S00_AXI_ARVALID) begin
                axi_arready <= 1'b1; axi_araddr <= S00_AXI_ARADDR;
            end else begin
                axi_arready <= 1'b0;
            end
        end
    end

    // RVALID/RRESP
    always @(posedge S00_AXI_ACLK) begin
        if (!S00_AXI_ARESETN) begin
            axi_rvalid <= 1'b0; axi_rresp <= 2'b00;
        end else begin
            if (axi_arready && S00_AXI_ARVALID && ~axi_rvalid) begin
                axi_rvalid <= 1'b1; axi_rresp <= 2'b00;
            end else if (S00_AXI_RREADY && axi_rvalid) begin
                axi_rvalid <= 1'b0;
            end
        end
    end

    // RDATA
    always @(posedge S00_AXI_ACLK) begin
        if (!S00_AXI_ARESETN) begin
            axi_rdata <= 0;
        end else if (axi_arready && S00_AXI_ARVALID) begin
            case (axi_araddr[C_S_AXI_ADDR_WIDTH-1:ADDR_LSB])
                ADDR_CTRL  [5:ADDR_LSB]: axi_rdata <= {31'b0, int_ap_start};
                ADDR_STATUS[5:ADDR_LSB]: axi_rdata <= {30'b0, ap_idle, ap_done};
                ADDR_IN_L  [5:ADDR_LSB]: axi_rdata <= in_l;
                ADDR_IN_H  [5:ADDR_LSB]: axi_rdata <= in_h;
                ADDR_OUT_L [5:ADDR_LSB]: axi_rdata <= out_l;
                ADDR_OUT_H [5:ADDR_LSB]: axi_rdata <= out_h;
                default:                  axi_rdata <= 0;
            endcase
        end
    end

    // 输出到顶层
    always @(*) begin
        ap_start             = int_ap_start & ~ap_done;
        ddr_input_base_addr  = {in_h,  in_l};
        ddr_output_base_addr = {out_h, out_l};
    end

endmodule
