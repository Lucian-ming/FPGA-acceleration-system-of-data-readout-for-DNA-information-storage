`timescale 1 ns / 1 ps
module Dna_accelerator_core_v1_0_S_AXI_LITE_CTRL #(
    parameter integer C_S_AXI_DATA_WIDTH = 32,
    parameter integer C_S_AXI_ADDR_WIDTH = 4
)(
    output wire [C_S_AXI_DATA_WIDTH-1:0] slv_reg0_out,
    output wire [C_S_AXI_DATA_WIDTH-1:0] slv_reg1_out,
    output wire [C_S_AXI_DATA_WIDTH-1:0] slv_reg2_out,
    output wire [C_S_AXI_DATA_WIDTH-1:0] slv_reg3_out,
    input  wire                           S_AXI_ACLK,
    input  wire                           S_AXI_ARESETN,
    input  wire [C_S_AXI_ADDR_WIDTH-1:0]  S_AXI_AWADDR,
    input  wire [2:0]                     S_AXI_AWPROT,
    input  wire                           S_AXI_AWVALID,
    output wire                           S_AXI_AWREADY,
    input  wire [C_S_AXI_DATA_WIDTH-1:0]  S_AXI_WDATA,
    input  wire [(C_S_AXI_DATA_WIDTH/8)-1:0] S_AXI_WSTRB,
    input  wire                           S_AXI_WVALID,
    output wire                           S_AXI_WREADY,
    output wire [1:0]                     S_AXI_BRESP,
    output wire                           S_AXI_BVALID,
    input  wire                           S_AXI_BREADY,
    input  wire [C_S_AXI_ADDR_WIDTH-1:0]  S_AXI_ARADDR,
    input  wire [2:0]                     S_AXI_ARPROT,
    input  wire                           S_AXI_ARVALID,
    output wire                           S_AXI_ARREADY,
    output wire [C_S_AXI_DATA_WIDTH-1:0]  S_AXI_RDATA,
    output wire [1:0]                     S_AXI_RRESP,
    output wire                           S_AXI_RVALID,
    input  wire                           S_AXI_RREADY
);
    reg [C_S_AXI_ADDR_WIDTH-1:0] axi_awaddr;
    reg axi_bvalid;
    reg [1:0] axi_bresp;
    reg [C_S_AXI_ADDR_WIDTH-1:0] axi_araddr;
    reg axi_arready, axi_rvalid;
    reg [1:0] axi_rresp;
    reg [C_S_AXI_DATA_WIDTH-1:0] axi_rdata;
    reg aw_pending, w_pending;
    reg [C_S_AXI_DATA_WIDTH-1:0] axi_wdata;
    reg [(C_S_AXI_DATA_WIDTH/8)-1:0] axi_wstrb;
    assign S_AXI_AWREADY = ~aw_pending & ~axi_bvalid;
    assign S_AXI_WREADY  = ~w_pending & ~axi_bvalid;
    assign S_AXI_BRESP   = axi_bresp;
    assign S_AXI_BVALID  = axi_bvalid;
    assign S_AXI_ARREADY = axi_arready;
    assign S_AXI_RRESP   = axi_rresp;
    assign S_AXI_RVALID  = axi_rvalid;
    assign S_AXI_RDATA   = axi_rdata;

    reg [C_S_AXI_DATA_WIDTH-1:0] slv_reg0, slv_reg1, slv_reg2, slv_reg3;
    wire aw_accept = S_AXI_AWVALID && S_AXI_AWREADY;
    wire w_accept  = S_AXI_WVALID && S_AXI_WREADY;
    wire slv_reg_wren = (aw_pending || aw_accept) &&
                        (w_pending || w_accept) && ~axi_bvalid;
    wire [C_S_AXI_ADDR_WIDTH-1:0] write_addr = aw_pending ? axi_awaddr : S_AXI_AWADDR;
    wire [C_S_AXI_DATA_WIDTH-1:0] write_data = w_pending ? axi_wdata : S_AXI_WDATA;
    wire [(C_S_AXI_DATA_WIDTH/8)-1:0] write_strb = w_pending ? axi_wstrb : S_AXI_WSTRB;
    integer i;
    localparam integer ADDR_LSB = (C_S_AXI_DATA_WIDTH/32) + 1;
    localparam integer OPT_MEM_ADDR_BITS = 1;
    always @(posedge S_AXI_ACLK) begin
        if (!S_AXI_ARESETN) begin
            axi_awaddr <= {C_S_AXI_ADDR_WIDTH{1'b0}};
            axi_wdata <= {C_S_AXI_DATA_WIDTH{1'b0}};
            axi_wstrb <= {(C_S_AXI_DATA_WIDTH/8){1'b0}};
            aw_pending <= 1'b0;
            w_pending <= 1'b0;
            axi_bvalid <= 1'b0;
            axi_bresp <= 2'b00;
            slv_reg0 <= 0;
            slv_reg1 <= 0;
            slv_reg2 <= 0;
            slv_reg3 <= 0;
        end else begin
            if (axi_bvalid && S_AXI_BREADY)
                axi_bvalid <= 1'b0;
            if (aw_accept) begin
                axi_awaddr <= S_AXI_AWADDR;
                aw_pending <= 1'b1;
            end
            if (w_accept) begin
                axi_wdata <= S_AXI_WDATA;
                axi_wstrb <= S_AXI_WSTRB;
                w_pending <= 1'b1;
            end
            if (slv_reg_wren) begin
                aw_pending <= 1'b0;
                w_pending <= 1'b0;
                axi_bvalid <= 1'b1;
                axi_bresp <= 2'b00;
                case (write_addr[ADDR_LSB+OPT_MEM_ADDR_BITS:ADDR_LSB])
                    2'h0: for (i=0;i<(C_S_AXI_DATA_WIDTH/8);i=i+1) if (write_strb[i]) slv_reg0[(i*8)+:8] <= write_data[(i*8)+:8];
                    2'h1: for (i=0;i<(C_S_AXI_DATA_WIDTH/8);i=i+1) if (write_strb[i]) slv_reg1[(i*8)+:8] <= write_data[(i*8)+:8];
                    2'h2: for (i=0;i<(C_S_AXI_DATA_WIDTH/8);i=i+1) if (write_strb[i]) slv_reg2[(i*8)+:8] <= write_data[(i*8)+:8];
                    2'h3: for (i=0;i<(C_S_AXI_DATA_WIDTH/8);i=i+1) if (write_strb[i]) slv_reg3[(i*8)+:8] <= write_data[(i*8)+:8];
                    default: ;
                endcase
            end
        end
    end
    always @(posedge S_AXI_ACLK) begin
        if (!S_AXI_ARESETN) axi_arready <= 1'b0;
        else if (~axi_arready && S_AXI_ARVALID) axi_arready <= 1'b1;
        else axi_arready <= 1'b0;
    end
    always @(posedge S_AXI_ACLK) begin
        if (!S_AXI_ARESETN) axi_araddr <= {C_S_AXI_ADDR_WIDTH{1'b0}};
        else if (~axi_arready && S_AXI_ARVALID) axi_araddr <= S_AXI_ARADDR;
    end
    wire slv_reg_rden = axi_arready & S_AXI_ARVALID & ~axi_rvalid;
    reg [C_S_AXI_DATA_WIDTH-1:0] reg_data_out;
    always @(*) begin
        case (axi_araddr[ADDR_LSB+OPT_MEM_ADDR_BITS:ADDR_LSB])
            2'h0: reg_data_out = slv_reg0;
            2'h1: reg_data_out = slv_reg1;
            2'h2: reg_data_out = slv_reg2;
            2'h3: reg_data_out = slv_reg3;
            default: reg_data_out = 0;
        endcase
    end
    always @(posedge S_AXI_ACLK) begin
        if (!S_AXI_ARESETN) begin axi_rvalid <= 1'b0; axi_rresp <= 2'b0; end
        else if (slv_reg_rden) begin
            axi_rvalid <= 1'b1; axi_rresp <= 2'b00; axi_rdata <= reg_data_out;
        end else if (axi_rvalid && S_AXI_RREADY) begin
            axi_rvalid <= 1'b0;
        end
    end
    assign slv_reg0_out = slv_reg0;
    assign slv_reg1_out = slv_reg1;
    assign slv_reg2_out = slv_reg2;
    assign slv_reg3_out = slv_reg3;
endmodule
