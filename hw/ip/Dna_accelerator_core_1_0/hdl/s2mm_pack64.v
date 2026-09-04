`timescale 1 ns / 1 ps
//=============================================================================
// s2mm_pack64 —— 把一条 R bit 的结果记录切成 6 拍 64 bit 送上 AXI-Stream
//
// [B23/B24] 2026-08-29 重写握手。原实现有两处 AXI-Stream 协议违规：
//   1. m_vld 是「上一拍看到 m_rdy」才拉高的，即 VALID 依赖 READY；
//   2. 状态机按 m_rdy 推进，而不是按真正的握手 (m_vld && m_rdy) 推进。
// 后果：只要下游在包中间撤掉 TREADY，已经推进过的那一拍就再也发不出去（丢拍），
// 或者末拍被重复采样。板上实测每个 48 B 包收到的是 [b1,b2,b3,b4,b5,b5]。
// 现在改为标准写法：有数据就拉 VALID（与 READY 无关），只有 m_vld && m_rdy 才推进，
// 未握手时 m_dat/m_last 保持不变。
//
// 另外新增 din_rd：取走一条记录时的单拍脉冲，给上游 FIFO 当 rd_en 用，
// 保证「一条记录只 pop 一次」（原来的 res_rd 在打包过程中会反复 pop，见 B24）。
//=============================================================================
module s2mm_pack64 #(
    parameter integer R = 526
)(
    input  wire         clk,
    input  wire         rst_n,
    input  wire         din_vld,
    input  wire [R-1:0] din,
    output reg          din_rd,
    output reg          m_vld,
    output reg [63:0]   m_dat,
    output reg          m_last,
    input  wire         m_rdy
);
    localparam integer BEATS = 9;

    reg [3:0]   beat;
    reg         busy;
    reg [R-1:0] lat;

    wire fire = m_vld & m_rdy;      // 真正的握手

    // 526 bit -> 9 x 64 bit（末拍只有 14 bit 有效，高位补零）
    function [63:0] slice_of;
        input [3:0]   idx;
        input [R-1:0] v;
        begin
            case (idx)
                4'd0: slice_of = v[63:0];
                4'd1: slice_of = v[127:64];
                4'd2: slice_of = v[191:128];
                4'd3: slice_of = v[255:192];
                4'd4: slice_of = v[319:256];
                4'd5: slice_of = v[383:320];
                4'd6: slice_of = v[447:384];
                4'd7: slice_of = v[511:448];
                4'd8: slice_of = {50'b0, v[525:512]};
                default: slice_of = 64'd0;
            endcase
        end
    endfunction

    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            busy   <= 1'b0;
            beat   <= 4'd0;
            m_vld  <= 1'b0;
            m_last <= 1'b0;
            m_dat  <= 64'd0;
            lat    <= {R{1'b0}};
            din_rd <= 1'b0;
        end else begin
            din_rd <= 1'b0;

            if (!busy) begin
                if (din_vld) begin
                    lat    <= din;
                    din_rd <= 1'b1;          // 一条记录只 pop 一次
                    busy   <= 1'b1;
                    beat   <= 4'd0;
                    m_vld  <= 1'b1;
                    m_dat  <= slice_of(4'd0, din);
                    m_last <= 1'b0;
                end
            end else if (fire) begin
                if (beat == BEATS-1) begin
                    busy   <= 1'b0;
                    m_vld  <= 1'b0;
                    m_last <= 1'b0;
                end else begin
                    beat   <= beat + 4'd1;
                    m_vld  <= 1'b1;
                    m_dat  <= slice_of(beat + 4'd1, lat);
                    m_last <= ((beat + 4'd1) == (BEATS-1));
                end
            end
            // 未握手时 m_vld / m_dat / m_last 保持不变（AXI-Stream 要求）
        end
    end
endmodule
