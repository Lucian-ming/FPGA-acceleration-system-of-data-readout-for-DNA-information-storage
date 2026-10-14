`timescale 1ns/1ps

module tb_ldpc_decoder_p1;
    reg clk = 1'b0;
    reg rst = 1'b1;
    reg load_we = 1'b0;
    reg [16:0] load_addr = 17'd0;
    reg load_bit = 1'b0;
    reg start = 1'b0;
    reg [16:0] result_addr = 17'd0;
    wire result_bit;
    wire busy;
    wire done;
    wire converged;
    wire error;
    wire signed [7:0] iter_count;

    reg [7:0] input_bytes [0:8099];
    reg [7:0] output_bytes [0:8099];

    string selected_tag;
    string input_path;
    string output_path;
    string summary_tag;
    string summary_input_sha;
    string summary_converged;
    string summary_output_sha;
    reg [8*256-1:0] summary_header;
    integer summary_fd;
    integer scan_rc;
    integer expected_iters;
    integer expected_converged;
    integer codeword_input_mode;
    integer found_sample;
    integer i;
    integer mismatch_count;
    integer first_mismatch;
    integer status_mismatch;
    integer hex_fd;
    integer char_hi;
    integer char_lo;
    reg expected_bit;

    // 仅在 testbench 中只读观察 DUT 现有 state；不增加或修改译码器端口/逻辑。
    // 周期按 start 被接受的上升沿到 done 拉高的上升沿计，分桶覆盖这段区间内的 FSM 状态。
    reg cycle_active = 1'b0;
    reg [4:0] state_snapshot;
    reg [13:0] row_snapshot;
    reg [4:0] edge_snapshot;
    reg [4:0] row_degree_snapshot;
    reg start_snapshot;
    integer cycle_count = 0;
    integer bucket_addr_cycles = 0;
    integer gather_cycles = 0;
    integer emit_cycles = 0;
    integer column_update_cycles = 0;
    integer init_sum_cycles = 0;
    integer syndrome_cycles = 0;
    integer other_cycles = 0;
    integer syndrome_sweeps = 0;

    function [3:0] hex_nibble;
        input integer ascii_value;
        begin
            if ((ascii_value >= 8'h30) && (ascii_value <= 8'h39))
                hex_nibble = ascii_value - 8'h30;
            else if ((ascii_value >= 8'h41) && (ascii_value <= 8'h46))
                hex_nibble = ascii_value - 8'h41 + 4'd10;
            else if ((ascii_value >= 8'h61) && (ascii_value <= 8'h66))
                hex_nibble = ascii_value - 8'h61 + 4'd10;
            else
                hex_nibble = 4'hx;
        end
    endfunction

    always #5 clk = ~clk;

    // state 编码与 ldpc_decoder_p1.v 中的 ST_* 对应：
    // 1..5 syndrome，6 init_sum，7..9 桶/地址调度，10..11 GATHER，
    // 12..13 EMIT，14..15 逐列读写更新。
    always @(posedge clk) begin
        state_snapshot = dut.state;
        row_snapshot = dut.row_q;
        edge_snapshot = dut.edge_slot_q;
        row_degree_snapshot = dut.row_degree;
        start_snapshot = (start === 1'b1) && (load_we === 1'b0);
        #1;
        if (rst) begin
            cycle_active = 1'b0;
            cycle_count = 0;
            bucket_addr_cycles = 0;
            gather_cycles = 0;
            emit_cycles = 0;
            column_update_cycles = 0;
            init_sum_cycles = 0;
            syndrome_cycles = 0;
            other_cycles = 0;
            syndrome_sweeps = 0;
        end else if (start_snapshot && !cycle_active) begin
            // start 接受沿作为计数起点；其后的每个 FSM 周期计一次。
            cycle_active = 1'b1;
            cycle_count = 0;
            bucket_addr_cycles = 0;
            gather_cycles = 0;
            emit_cycles = 0;
            column_update_cycles = 0;
            init_sum_cycles = 0;
            syndrome_cycles = 0;
            other_cycles = 0;
            syndrome_sweeps = 0;
        end else if (cycle_active) begin
            cycle_count = cycle_count + 1;
            case (state_snapshot)
                5'd1, 5'd2, 5'd3, 5'd4, 5'd5:
                    syndrome_cycles = syndrome_cycles + 1;
                5'd6: begin
                    // 每轮开始时清零 sum_mem，作为逐列处理的独立子项统计。
                    init_sum_cycles = init_sum_cycles + 1;
                    column_update_cycles = column_update_cycles + 1;
                end
                5'd7, 5'd8, 5'd9:
                    bucket_addr_cycles = bucket_addr_cycles + 1;
                5'd10, 5'd11:
                    gather_cycles = gather_cycles + 1;
                5'd12, 5'd13:
                    emit_cycles = emit_cycles + 1;
                5'd14, 5'd15:
                    column_update_cycles = column_update_cycles + 1;
                default:
                    other_cycles = other_cycles + 1;
            endcase
            if ((state_snapshot == 5'd5) &&
                (row_snapshot == 14'd10799) &&
                (edge_snapshot == row_degree_snapshot - 5'd1)) begin
                syndrome_sweeps = syndrome_sweeps + 1;
                $display("PROGRESS sample=%s syndrome_sweep=%0d iteration_q=%0d converged=%0d done=%0d",
                         selected_tag, syndrome_sweeps, dut.iteration_q,
                         converged, done);
            end
            // 此上升沿执行的是 state_snapshot 中的最后一个状态周期。
            if (done === 1'b1)
                cycle_active = 1'b0;
        end
    end

    ldpc_decoder_p1 dut (
        .clk(clk),
        .rst(rst),
        .load_we(load_we),
        .load_addr(load_addr),
        .load_bit(load_bit),
        .start(start),
        .result_addr(result_addr),
        .result_bit(result_bit),
        .busy(busy),
        .done(done),
        .converged(converged),
        .error(error),
        .iter_count(iter_count)
    );

    initial begin
        if (!$value$plusargs("TAG=%s", selected_tag)) begin
            $display("FAIL 缺少 +TAG=<summary.tsv 样本名>");
            $fatal(1);
        end

        summary_fd = $fopen("logs/ldpc/golden/summary.tsv", "r");
        if (summary_fd == 0) begin
            $display("FAIL 无法打开 logs/ldpc/golden/summary.tsv");
            $fatal(1);
        end
        scan_rc = $fgets(summary_header, summary_fd);
        found_sample = 0;
        expected_iters = -999;
        expected_converged = 0;
        while (!$feof(summary_fd) && !found_sample) begin
            scan_rc = $fscanf(summary_fd, "%s %s %s %d %s\n",
                              summary_tag, summary_input_sha,
                              summary_converged, expected_iters,
                              summary_output_sha);
            if ((scan_rc == 5) && (summary_tag == selected_tag)) begin
                found_sample = 1;
                expected_converged = (summary_converged == "YES");
            end
        end
        $fclose(summary_fd);
        if (!found_sample) begin
            $display("FAIL summary.tsv 中没有样本 %s", selected_tag);
            $fatal(1);
        end

        codeword_input_mode = $test$plusargs("CODEWORD_INPUT");
        if (codeword_input_mode) begin
            expected_converged = 1;
            expected_iters = 0;
            $sformat(output_path, "logs/ldpc/golden/out_%s.hex", selected_tag);
            input_path = output_path;
        end else begin
            $sformat(input_path, "logs/ldpc/golden/in_%s.hex", selected_tag);
        end
        hex_fd = $fopen(input_path, "r");
        if (hex_fd == 0) begin
            $display("FAIL 无法打开 %s", input_path);
            $fatal(1);
        end
        for (i = 0; i < 8100; i = i + 1) begin
            char_hi = $fgetc(hex_fd);
            char_lo = $fgetc(hex_fd);
            if ((char_hi < 0) || (char_lo < 0)) begin
                $display("FAIL %s 在第 %0d 字节前结束", input_path, i);
                $fatal(1);
            end
            input_bytes[i] = {hex_nibble(char_hi), hex_nibble(char_lo)};
        end
        $fclose(hex_fd);
        if (expected_converged) begin
            if (!codeword_input_mode)
                $sformat(output_path, "logs/ldpc/golden/out_%s.hex", selected_tag);
            hex_fd = $fopen(output_path, "r");
            if (hex_fd == 0) begin
                $display("FAIL 无法打开 %s", output_path);
                $fatal(1);
            end
            for (i = 0; i < 8100; i = i + 1) begin
                char_hi = $fgetc(hex_fd);
                char_lo = $fgetc(hex_fd);
                if ((char_hi < 0) || (char_lo < 0)) begin
                    $display("FAIL %s 在第 %0d 字节前结束", output_path, i);
                    $fatal(1);
                end
                output_bytes[i] = {hex_nibble(char_hi), hex_nibble(char_lo)};
            end
            $fclose(hex_fd);
        end

        $display("START sample=%s codeword_input=%0d expected_converged=%0d expected_iters=%0d",
                 selected_tag, codeword_input_mode,
                 expected_converged, expected_iters);

        repeat (4) @(posedge clk);
        @(negedge clk);
        rst = 1'b0;

        // packbits(bitorder="big")：每字节按 bit7、bit6……bit0 顺序装载。
        for (i = 0; i < 64800; i = i + 1) begin
            @(negedge clk);
            load_we = 1'b1;
            load_addr = i[16:0];
            load_bit = input_bytes[i >> 3][7 - (i & 7)];
        end
        @(negedge clk);
        load_we = 1'b0;
        start = 1'b1;
        @(negedge clk);
        start = 1'b0;

        wait (done === 1'b1);
        // 给周期监视器完成同一上升沿的最后一次分桶计数。
        #2;
        status_mismatch = 0;
        if ((converged !== expected_converged[0]) ||
            (error !== !converged)) begin
            status_mismatch = 1;
            $display("FAIL sample=%s status expected=(conv:%0d,iters:%0d) actual=(conv:%0d,iters:%0d,error:%0d)",
                     selected_tag, expected_converged, expected_iters,
                     converged, $signed(iter_count), error);
        end

        mismatch_count = 0;
        first_mismatch = -1;
        if (expected_converged && converged) begin
            for (i = 0; i < 64800; i = i + 1) begin
                @(negedge clk);
                result_addr = i[16:0];
                @(posedge clk);
                #1;
                expected_bit = output_bytes[i >> 3][7 - (i & 7)];
                if (result_bit !== expected_bit) begin
                    mismatch_count = mismatch_count + 1;
                    if (first_mismatch < 0)
                        first_mismatch = i;
                end
            end
            if (mismatch_count != 0) begin
                $display("FAIL sample=%s converged=1 iter_count=%0d bit_mismatches=%0d first_bit=%0d",
                         selected_tag, $signed(iter_count), mismatch_count,
                         first_mismatch);
            end else begin
                $display("OUTPUT MATCH sample=%s compared_bits=64800 bit_mismatches=0",
                         selected_tag);
            end
        end

        if (status_mismatch || (mismatch_count != 0)) begin
            $display("FAIL sample=%s converged=%0d iter_count=%0d status_mismatch=%0d bit_mismatches=%0d",
                     selected_tag, converged, $signed(iter_count),
                     status_mismatch, mismatch_count);
            $fatal(1);
        end

        $display("CYCLES sample=%s total=%0d bucket_addr=%0d gather=%0d emit=%0d column_update=%0d init_sum_included=%0d syndrome=%0d other=%0d",
                 selected_tag, cycle_count, bucket_addr_cycles, gather_cycles,
                 emit_cycles, column_update_cycles, init_sum_cycles,
                 syndrome_cycles, other_cycles);
        $display("PASS sample=%s converged=%0d expected_iters=%0d actual_iters=%0d bit_mismatches=%0d compared_bits=%0d",
                 selected_tag, converged, expected_iters, $signed(iter_count), mismatch_count,
                 expected_converged ? 64800 : 0);
        $finish;
    end
endmodule
