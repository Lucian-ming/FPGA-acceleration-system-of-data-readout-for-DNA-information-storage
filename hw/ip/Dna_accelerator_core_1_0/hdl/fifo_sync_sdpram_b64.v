`timescale 1 ns / 1 ps
module fifo_sync_sdpram_b64 #(
    parameter integer WIDTH = 8,
    parameter integer DEPTH = 16
)(
    input  wire                 clk,
    input  wire                 rst_n,     // active-low
    input  wire                 wr_en,
    input  wire [WIDTH-1:0]     din,
    output wire                 full,
    input  wire                 rd_en,
    output reg  [WIDTH-1:0]     dout,
    output wire                 empty
);
    // log2 计算
    function integer CLOG2; input integer v; integer t,i; begin t=v-1; i=0; while(t>0) begin t=t>>1; i=i+1; end CLOG2=i; end endfunction
    localparam integer AW = CLOG2(DEPTH);

    // 存储体（单端口写 + 同步读，综合成 BRAM/URAM 由工具决定）
    (* ram_style = "block" *) reg [WIDTH-1:0] mem [0:DEPTH-1];

    reg [AW-1:0] wptr, rptr, raddr_q;
    reg [AW:0]   count;

    assign full  = (count == DEPTH[AW:0]);
    assign empty = (count == { (AW+1){1'b0} });

    // 写端口
    always @(posedge clk) begin
        if (wr_en && !full) mem[wptr] <= din;
    end

    // 读地址打一拍，下一拍输出（同步读 1 拍延迟）
    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            raddr_q <= {AW{1'b0}};
            dout    <= {WIDTH{1'b0}};
        end else begin
            raddr_q <= rptr;
            dout    <= mem[raddr_q];
        end
    end

    // 指针/计数
    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            wptr<=0; rptr<=0; count<=0;
        end else begin
            case ({wr_en && !full, rd_en && !empty})
                2'b10: begin wptr<=wptr+1'b1; count<=count+1'b1; end
                2'b01: begin rptr<=rptr+1'b1; count<=count-1'b1; end
                2'b11: begin wptr<=wptr+1'b1; rptr<=rptr+1'b1; end
                default: ;
            endcase
        end
    end
endmodule