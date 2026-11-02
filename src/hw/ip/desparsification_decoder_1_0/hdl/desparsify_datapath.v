// =============================================================
// desparsify_datapath.v — 5b→4b 反稀疏化的纯数据通路
//
// 从 desparsification_decoder.v 里抽出来的核心运算，去掉了 AXI 控制状态机，
// 换成简单的 valid/ready 流接口，因此可以被黄金向量逐位验证（见 tb_desparsify_datapath.v）。
//
// 之所以要抽出来：原顶层的控制 FSM 有多个独立的死锁缺陷
// （docs/03-status.md B7/B8/B9），无法在仿真里跑通；但决定输出对错的是这段数据通路。
// 把它验证好之后，重写 FSM 时就有一个已证明正确的内核可用。
//
// 契约（docs/02-data-contract.md 第 4 节）：
//   每 5 bit 一组，按码流顺序 b0..b4，输出 4 bit 为 b1^b0, b2^b0, b3^b0, b4^b0
//   —— 组内第一个 bit 是取反标志。
//   码流按 LSB-first 装进 64-bit 拍。
//
// 吞吐：每拍进 64 bit / 出 64 bit（比值 5:4，故约 4/5 的周期有输出）。
// =============================================================
`timescale 1 ns / 1 ps

module desparsify_datapath (
    input  wire        clk,
    input  wire        rstn,

    // 输入流：稀疏比特流，64 bit/拍
    input  wire        in_valid,
    output wire        in_ready,
    input  wire [63:0] in_data,
    input  wire        in_done,      // 上游已无更多数据，冲刷尾部

    // 输出流：码字比特流，64 bit/拍（末拍可能不足 64 bit 有效）
    output wire        out_valid,
    input  wire        out_ready,
    output wire [63:0] out_data
);

    reg [127:0] in_pool;
    reg [7:0]   in_bits;
    reg [95:0]  out_pool;
    reg [6:0]   out_bits;

    // ---- 5b -> 4b：标志位是组内第一个 bit（修订 B5）----
    function [31:0] conv40_32;
        input [39:0] x;
        integer k;
        reg [3:0] r [0:7];
        reg [4:0] grp;
        begin
            for (k=0; k<8; k=k+1) begin
                grp  = x[(5*k)+:5];
                r[k] = grp[4:1] ^ {4{grp[0]}};
            end
            conv40_32 = {r[7],r[6],r[5],r[4],r[3],r[2],r[1],r[0]};
        end
    endfunction

    // 入口容量：接收后最多 128 bit，故 in_bits<=64 时才收
    assign in_ready  = (in_bits <= 8'd64);
    // 出口：攒够 64 bit 就送；冲刷阶段不足 64 bit 也送
    assign out_valid = (out_bits >= 7'd64) || (in_done && (out_bits != 7'd0) && (in_bits < 8'd40));
    assign out_data  = out_pool[63:0];

    // ---- 接收 / 消费 / 送出 合并成一条组合链后统一寄存（修订 B6）----
    reg [127:0] in_pool_n;
    reg [7:0]   in_bits_n;
    reg [95:0]  out_pool_n;
    reg [6:0]   out_bits_n;

    always @* begin
        in_pool_n  = in_pool;
        in_bits_n  = in_bits;
        out_pool_n = out_pool;
        out_bits_n = out_bits;

        // 1) 收一拍：按已有位数移位插入，绝不覆盖尾部残留
        if (in_valid && in_ready) begin
            in_pool_n = in_pool_n | ({64'd0, in_data} << in_bits_n);
            in_bits_n = in_bits_n + 8'd64;
        end

        // 2) 消费 40 bit -> 产出 32 bit
        if (in_bits_n >= 8'd40 && out_bits_n <= 7'd64) begin
            out_pool_n = out_pool_n | ({64'd0, conv40_32(in_pool_n[39:0])} << out_bits_n);
            in_pool_n  = in_pool_n >> 40;
            in_bits_n  = in_bits_n - 8'd40;
            out_bits_n = out_bits_n + 7'd32;
        end

        // 3) 送出一拍：握手用寄存后的 out_valid，与 out_data 对齐
        if (out_valid && out_ready) begin
            out_pool_n = out_pool_n >> 64;
            out_bits_n = (out_bits_n >= 7'd64) ? (out_bits_n - 7'd64) : 7'd0;
        end
    end

    always @(posedge clk) begin
        if (!rstn) begin
            in_pool  <= 128'd0; in_bits  <= 8'd0;
            out_pool <= 96'd0;  out_bits <= 7'd0;
        end else begin
            in_pool  <= in_pool_n;
            in_bits  <= in_bits_n;
            out_pool <= out_pool_n;
            out_bits <= out_bits_n;
        end
    end

endmodule
