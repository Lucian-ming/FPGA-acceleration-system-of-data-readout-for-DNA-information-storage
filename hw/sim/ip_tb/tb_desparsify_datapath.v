// =============================================================
// tb_desparsify_datapath.v — 用黄金向量逐位验证 5b→4b 数据通路
//
//   激励  tests/golden/sparse_ideal.hex        81,000 bit 稀疏流（1,266 拍）
//   期望  tests/golden/stage3_ideal_expect.hex 64,800 bit 码字（1,013 拍）
//
// 同时用随机背压压测 valid/ready 握手，确保数据通路对停顿免疫。
// 任何一位不符即 $fatal。
//
// 运行：
//   iverilog -g2005 -o /tmp/tb_dp \
//       hw/ip/desparsification_decoder_1_0/hdl/desparsify_datapath.v \
//       hw/ip/desparsification_decoder_1_0/hdl/tb_desparsify_datapath.v
//   vvp /tmp/tb_dp
// =============================================================
`timescale 1ns/1ps

module tb_desparsify_datapath;

    localparam integer IN_BEATS  = 1266;
    localparam integer OUT_BEATS = 1013;
    localparam integer OUT_BITS  = 64800;

    reg clk = 0, rstn = 0;
    always #5 clk = ~clk;

    reg  [63:0] mem_in  [0:IN_BEATS-1];
    reg  [63:0] expect  [0:OUT_BEATS-1];
    reg  [63:0] got     [0:OUT_BEATS+7];

    reg         in_valid = 0, in_done = 0;
    reg  [63:0] in_data  = 0;
    wire        in_ready;
    wire        out_valid;
    reg         out_ready = 0;
    wire [63:0] out_data;

    desparsify_datapath dut (
        .clk(clk), .rstn(rstn),
        .in_valid(in_valid), .in_ready(in_ready), .in_data(in_data), .in_done(in_done),
        .out_valid(out_valid), .out_ready(out_ready), .out_data(out_data)
    );

    integer in_idx  = 0;
    integer out_idx = 0;
    integer seed    = 32'h1234_5678;

    // 上游：随机插入停顿
    // 注意 nxt_idx —— 握手发生的那一拍 in_idx 还没更新（非阻塞赋值），
    // 直接用 in_idx 取数会把同一拍重发一次。
    wire [31:0] nxt_idx = in_idx + ((in_valid && in_ready) ? 32'd1 : 32'd0);

    always @(posedge clk) begin
        if (!rstn) begin
            in_valid <= 1'b0; in_idx <= 0; in_done <= 1'b0;
        end else begin
            if (in_valid && in_ready) begin
                in_idx   <= in_idx + 1;
                in_valid <= 1'b0;
            end
            if (!in_valid || in_ready) begin
                if (nxt_idx < IN_BEATS && ($random(seed) % 4) != 0) begin
                    in_data  <= mem_in[nxt_idx];
                    in_valid <= 1'b1;
                end
            end
            // 全部拍都已被接收后才置 in_done，避免过早冲刷出半拍
            in_done <= (nxt_idx >= IN_BEATS) && !(in_valid && !in_ready);
        end
    end

    // 下游：随机背压
    always @(posedge clk) begin
        if (!rstn) begin
            out_ready <= 1'b0; out_idx <= 0;
        end else begin
            out_ready <= (($random(seed) % 5) != 0);
            if (out_valid && out_ready) begin
                if (out_idx <= OUT_BEATS+7) got[out_idx] <= out_data;
                out_idx <= out_idx + 1;
            end
        end
    end

    integer k, b, errors, bit_errors, timeout;
    reg [63:0] mask, g, e;

    initial begin
        $readmemh("tests/golden/sparse_ideal.hex", mem_in);
        $readmemh("tests/golden/stage3_ideal_expect.hex", expect);
        $display("[TB] 激励 %0d 拍 / 期望 %0d 拍（含随机背压）", IN_BEATS, OUT_BEATS);

        repeat (5) @(posedge clk);
        rstn = 1;

        timeout = 0;
        while (out_idx < OUT_BEATS && timeout < 200000) begin
            @(posedge clk);
            timeout = timeout + 1;
        end

        if (out_idx < OUT_BEATS) begin
            $display("[TB] ✗ 超时：只收到 %0d/%0d 拍（输入已送 %0d 拍）",
                     out_idx, OUT_BEATS, in_idx);
            $fatal(1);
        end

        errors = 0; bit_errors = 0;
        for (k=0; k<OUT_BEATS; k=k+1) begin
            mask = (k == OUT_BEATS-1)
                 ? ((64'd1 << (OUT_BITS-64*(OUT_BEATS-1))) - 64'd1) : {64{1'b1}};
            g = got[k] & mask;
            e = expect[k] & mask;
            if (g !== e) begin
                for (b=0; b<64; b=b+1)
                    if (mask[b] && (g[b] !== e[b])) bit_errors = bit_errors + 1;
                if (errors < 8)
                    $display("[TB] ✗ 第 %0d 拍不符  实得 %h  期望 %h", k, g, e);
                errors = errors + 1;
            end
        end

        $display("--------------------------------------------------");
        if (errors == 0)
            $display("[TB] ✓ PASS  %0d 拍 / %0d bit 与黄金向量逐位相同（用时 %0d 周期）",
                     OUT_BEATS, OUT_BITS, timeout);
        else
            $display("[TB] ✗ FAIL  %0d 拍不符，共 %0d bit 错", errors, bit_errors);
        $display("--------------------------------------------------");
        if (errors != 0) $fatal(1);
        $finish;
    end

endmodule
