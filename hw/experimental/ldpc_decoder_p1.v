`timescale 1ns/1ps

// DVB-S2 R=5/6 硬判决 flooding Min-Sum 译码器原型。
// 每个校验行按边串行处理；当前 LLR 在整轮消息累加完成前保持不变。
module ldpc_decoder_p1 #(
    parameter integer N_BITS = 64800,
    parameter integer M_ROWS = 10800,
    parameter integer MAX_ITER = 50,
    parameter BT_ROM_FILE = "logs/ldpc/golden/bt_col_by_res.hex",
    parameter BT_OFF_FILE = "logs/ldpc/golden/bt_res_off.hex"
) (
    input  wire              clk,
    input  wire              rst,
    input  wire              load_we,
    input  wire [16:0]       load_addr,
    input  wire              load_bit,
    input  wire              start,
    input  wire [16:0]       result_addr,
    output reg               result_bit,
    output reg               busy,
    output reg               done,
    output reg               converged,
    output reg               error,
    output reg signed [7:0]  iter_count
);
    localparam [4:0] ST_IDLE          = 5'd0;
    localparam [4:0] ST_INIT_SUM      = 5'd6;
    localparam [4:0] ST_GATHER_ROW    = 5'd7;
    localparam [4:0] ST_GATHER_PIPE   = 5'd8;
    localparam [4:0] ST_EMIT_PIPE     = 5'd9;
    localparam [4:0] ST_UPDATE_PIPE   = 5'd10;

    localparam [16:0] LAST_BIT = N_BITS - 1;
    localparam [13:0] LAST_ROW = M_ROWS - 1;

    reg [4:0] state;

    // 输入位、旧 LLR、下一轮聚合和输出码字分开存放。
    (* ram_style = "block" *) reg                  input_mem   [0:N_BITS-1];
    (* ram_style = "block" *) reg signed [5:0]     llr_mem     [0:N_BITS-1];
    (* ram_style = "block" *) reg signed [11:0]    sum_mem     [0:N_BITS-1];
    (* ram_style = "block" *) reg                  decoded_mem [0:N_BITS-1];

    // B_t 转置桶：每桶 20 项；主表同步读，供 BRAM ROM 推断。
    (* rom_style = "block" *) reg [31:0] bt_rom [0:599];
    (* rom_style = "distributed" *) reg [11:0] bt_off_rom [0:30];
    reg [31:0] bt_data_q;
    reg [11:0] bucket_start_q;

    initial begin
        $readmemh(BT_ROM_FILE, bt_rom);
        $readmemh(BT_OFF_FILE, bt_off_rom);
    end

    reg [13:0] row_q;
    reg [4:0]  row_res_q;
    reg [4:0]  edge_slot_q;
    reg [4:0]  emit_slot_q;
    reg [4:0]  gather_rom_slot_q;
    reg [4:0]  gather_llr_slot_q;
    reg        gather_rom_valid_q;
    reg        gather_llr_valid_q;
    reg        emit_write_valid_q;
    reg        update_write_valid_q;
    reg        update_scan_done_q;
    reg [16:0] scan_idx_q;
    reg [9:0]  row_a_q;                // row_q / 30，每行算一次
    reg [13:0] failed_checks_q;
    reg [5:0]  iteration_q;
    reg        initial_check_q;
    reg        row_parity_q;

    reg [16:0] row_addr_cache [0:21];
    reg signed [5:0] row_llr_cache [0:21];
    reg [5:0] min1_q;
    reg [5:0] min2_q;
    reg [4:0] min1_slot_q;
    reg       sign_negative_q;
    reg       row_has_zero_q;

    reg signed [5:0] llr_rd_q;
    reg [16:0] llr_addr_q;
    reg signed [11:0] sum_rd_q;
    reg [16:0] sum_addr_q;
    reg input_bit_rd_q;
    reg signed [6:0] message_q;

    wire [4:0] row_degree = (row_q == 14'd0) ? 5'd21 : 5'd22;
    wire [4:0] info_first_slot = (row_q == 14'd0) ? 5'd1 : 5'd2;
    wire slot_is_info = (row_q == 14'd0) ?
                        (edge_slot_q >= 5'd1) : (edge_slot_q >= 5'd2);
    wire [4:0] info_slot_index = edge_slot_q - info_first_slot;
    wire [11:0] bt_index_full = bucket_start_q + info_slot_index;
    wire [9:0] bt_index = bt_index_full[9:0];

    // ---- 地址计算：用结构关系消掉除法/乘法/取模（2026-10-14） ----
    // 行 r 与基地址 x 同属 r mod 30 桶。写 r = 30a + ρ、x = 30b + ρ，则
    //   x + 30m ≡ r (mod 10800)  ⟺  b + m ≡ a (mod 360)  ⟺  m = (a − b) mod 360
    // 于是列地址 = base_col + m，其中 base_col = 10800 + 360t 与 b 都**预存在表里**。
    // 这条式子已在 Python 里对全部 10800 行逐行核对（零不一致）。
    // 上一版用「乘倒数 ÷30」，路径仍有 7 个 CARRY4 + 1 个 DSP（11 ns）；本版每边只剩
    // 一次 9 位减、一次条件 +360、一次 17 位加。
    wire [8:0]  base_b     = bt_data_q[8:0];        // b = x/30
    wire [16:0] info_base  = bt_data_q[25:9];       // 10800 + 360t
    wire [9:0]  info_m_raw = {1'b0, row_a_q} - {1'b0, base_b};
    wire [9:0]  info_m     = (row_a_q >= base_b) ? info_m_raw : (info_m_raw + 10'd360);
    wire [16:0] info_column = info_base + {7'd0, info_m};

    wire info_addr_valid = (bt_index_full < 12'd600);

    wire gather_rom_slot_is_info = (row_q == 14'd0) ?
                                   (gather_rom_slot_q >= 5'd1) :
                                   (gather_rom_slot_q >= 5'd2);
    wire [4:0] gather_rom_info_slot = gather_rom_slot_q - info_first_slot;
    wire [11:0] gather_rom_index_full = bucket_start_q + gather_rom_info_slot;
    wire gather_rom_addr_valid = (gather_rom_index_full < 12'd600);
    wire [16:0] gather_check_column = (gather_rom_slot_q == 5'd0) ?
                                      ((row_q == 14'd0) ? 17'd0 :
                                       ({3'd0, row_q} - 17'd1)) :
                                      {3'd0, row_q};
    wire [16:0] gather_llr_column = gather_rom_slot_is_info ?
                                   info_column : gather_check_column;

    wire llr_read_en = (state == ST_GATHER_PIPE) && gather_rom_valid_q &&
                       (!gather_rom_slot_is_info || gather_rom_addr_valid);

    function [5:0] abs_llr;
        input signed [5:0] value;
        begin
            if (value[5])
                abs_llr = (~value) + 6'd1;
            else
                abs_llr = value;
        end
    endfunction

    wire [5:0] emit_magnitude = abs_llr(row_llr_cache[emit_slot_q]);
    wire [5:0] emit_minimum = (emit_slot_q == min1_slot_q) ? min2_q : min1_q;
    wire emit_negative = sign_negative_q ^ row_llr_cache[emit_slot_q][5];
    wire signed [6:0] emit_message = row_has_zero_q ? 7'sd0 :
        (emit_negative ? -$signed({1'b0, emit_minimum}) :
                          $signed({1'b0, emit_minimum}));

    wire decoded_bit_now = ($signed(llr_rd_q) > 0);
    wire row_failed_now = row_parity_q ^ decoded_bit_now;
    wire [14:0] failed_checks_with_row = {1'b0, failed_checks_q} + row_failed_now;

    reg signed [12:0] update_work;
    reg signed [5:0] update_llr;
    always @* begin
        update_work = $signed({sum_rd_q[11], sum_rd_q}) +
                      (input_bit_rd_q ? 13'sd6 : -13'sd6);
        if (update_work > 13'sd31)
            update_llr = 6'sd31;
        else if (update_work < -13'sd32)
            update_llr = -6'sd32;
        else
            update_llr = update_work[5:0];
    end

    wire        sum_rd_en = ((state == ST_EMIT_PIPE) &&
                             (emit_slot_q < row_degree)) ||
                            ((state == ST_UPDATE_PIPE) &&
                             !update_scan_done_q);
    wire [16:0] sum_rd_addr = (state == ST_EMIT_PIPE) ?
                              row_addr_cache[emit_slot_q] : scan_idx_q;

    // 同步读口：主 B_t ROM、LLR、聚合和输入位均按周期读取。
    always @(posedge clk) begin
        if (rst) begin
            bt_data_q      <= 32'd0;
            llr_rd_q       <= 6'sd0;
            llr_addr_q     <= 17'd0;
            sum_rd_q       <= 12'sd0;
            sum_addr_q     <= 17'd0;
            input_bit_rd_q <= 1'b0;
            message_q     <= 7'sd0;
            result_bit     <= 1'b0;
        end else begin
            if ((state == ST_GATHER_PIPE) && (edge_slot_q < row_degree) &&
                slot_is_info && info_addr_valid)
                bt_data_q <= bt_rom[bt_index];

            if (llr_read_en) begin
                llr_rd_q <= llr_mem[gather_llr_column];
                llr_addr_q <= gather_llr_column;
            end

            // sum_mem 只有一个读口：原先两个状态各写一条读语句，Vivado 会当成两个读端口
            // 而拒绝推断 BRAM（Synth 8-6849 Infeasible ram_style="block"）。合并成单条
            // 读语句 + 地址 mux；两状态互斥，语义不变。
            if (sum_rd_en) begin
                sum_rd_q   <= sum_mem[sum_rd_addr];
                sum_addr_q <= sum_rd_addr;
            end
            if ((state == ST_UPDATE_PIPE) && !update_scan_done_q)
                input_bit_rd_q <= input_mem[scan_idx_q];

            if ((state == ST_EMIT_PIPE) && (emit_slot_q < row_degree))
                message_q <= emit_message;

            result_bit <= decoded_mem[result_addr];
        end
    end

    // ---- 单写口存储：Vivado 8-3391 要求「每个 RAM 在一个 process 里只有一个写语句」 ----
    // 装载期与更新期、初始清零与行消息累加在时间上互斥，合并为单写口地址/数据 mux。
    wire        llr_wr_load = (load_we == 1'b1) && (state == ST_IDLE) && (load_addr < N_BITS);
    wire        llr_wr_upd  = (state == ST_UPDATE_PIPE) && update_write_valid_q;
    wire [16:0] llr_wr_addr = llr_wr_load ? load_addr : sum_addr_q;
    wire [5:0]  llr_wr_data = llr_wr_load ? (load_bit ? 6'sd6 : -6'sd6) : update_llr;
    wire        dec_wr_data = llr_wr_load ? load_bit : ($signed(update_llr) > 0);

    // row_a_q 跟随 row_q（1 拍延迟）。GATHER_ROW 提供一拍行准备时间，后续 ROM/LLR 流水
    // 使用时 row_a_q 与 row_q 对齐。÷30 用精确乘倒数（K=17477/S=19 已全范围核对）。
    always @(posedge clk) begin
        if (rst) row_a_q <= 10'd0;
        // ⚠️ 乘法必须显式拓宽：Verilog 里 `a * b` 的结果宽度取两操作数的**较大者**，
        // 写成 (row_q * 15'd17477) 会截成 15 位，再 >>19 恒为 0（踩过一次）。
        else     row_a_q <= (row_q * 29'd17477) >> 19;
    end

    always @(posedge clk) begin
        if (llr_wr_load || llr_wr_upd) begin
            llr_mem[llr_wr_addr]     <= llr_wr_data;
            decoded_mem[llr_wr_addr] <= dec_wr_data;
        end
    end

    wire        sum_wr_clr  = (state == ST_INIT_SUM) ||
                              ((state == ST_UPDATE_PIPE) && update_write_valid_q);
    wire        sum_wr_acc  = (state == ST_EMIT_PIPE) && emit_write_valid_q;
    wire [16:0] sum_wr_addr = (state == ST_INIT_SUM) ? scan_idx_q : sum_addr_q;
    wire [11:0] sum_wr_data = sum_wr_clr ? 12'sd0 :
                              (sum_rd_q + {{5{message_q[6]}}, message_q});

    always @(posedge clk) begin
        if (sum_wr_clr || sum_wr_acc)
            sum_mem[sum_wr_addr] <= sum_wr_data;
    end

    integer cache_i;
    always @(posedge clk) begin
        if (rst) begin
            state                 <= ST_IDLE;
            busy                  <= 1'b0;
            done                  <= 1'b0;
            converged             <= 1'b0;
            error                 <= 1'b0;
            iter_count            <= 8'sd0;
            row_q                 <= 14'd0;
            row_res_q             <= 5'd0;
            edge_slot_q           <= 5'd0;
            emit_slot_q           <= 5'd0;
            gather_rom_slot_q     <= 5'd0;
            gather_llr_slot_q     <= 5'd0;
            gather_rom_valid_q    <= 1'b0;
            gather_llr_valid_q    <= 1'b0;
            emit_write_valid_q    <= 1'b0;
            update_write_valid_q  <= 1'b0;
            update_scan_done_q    <= 1'b0;
            scan_idx_q            <= 17'd0;
            failed_checks_q       <= 14'd0;
            iteration_q           <= 6'd0;
            initial_check_q       <= 1'b0;
            row_parity_q          <= 1'b0;
            bucket_start_q        <= 12'd0;
            min1_q                <= 6'd63;
            min2_q                <= 6'd63;
            min1_slot_q           <= 5'd0;
            sign_negative_q       <= 1'b0;
            row_has_zero_q        <= 1'b0;
            for (cache_i = 0; cache_i < 22; cache_i = cache_i + 1) begin
                row_addr_cache[cache_i] <= 17'd0;
                row_llr_cache[cache_i] <= 6'sd0;
            end
        end else begin
            done <= 1'b0;

            // 每个周期同时推进 ROM→LLR→捕获三级流水；边顺序仍严格保持。
            if (state == ST_GATHER_PIPE) begin
                gather_llr_valid_q <= gather_rom_valid_q;
                if (gather_rom_valid_q)
                    gather_llr_slot_q <= gather_rom_slot_q;
                gather_rom_valid_q <= (edge_slot_q < row_degree);
                if (edge_slot_q < row_degree)
                    gather_rom_slot_q <= edge_slot_q;
            end else begin
                gather_rom_valid_q <= 1'b0;
                gather_llr_valid_q <= 1'b0;
            end

            if (state == ST_EMIT_PIPE)
                emit_write_valid_q <= (emit_slot_q < row_degree);
            else
                emit_write_valid_q <= 1'b0;

            // sum_mem 在更新读出之后的一拍清零，地址落后当前读地址一项，避免同址碰撞。
            if (state == ST_UPDATE_PIPE)
                update_write_valid_q <= !update_scan_done_q;
            else
                update_write_valid_q <= 1'b0;

            if ((load_we == 1'b1) && (state == ST_IDLE) &&
                (load_addr < N_BITS)) begin
                input_mem[load_addr] <= load_bit;
            end

            case (state)
                ST_IDLE: begin
                    if (start && !load_we) begin
                        busy                <= 1'b1;
                        converged           <= 1'b0;
                        error               <= 1'b0;
                        iter_count          <= 8'sd0;
                        iteration_q         <= 6'd0;
                        row_q               <= 14'd0;
                        row_res_q           <= 5'd0;
                        edge_slot_q         <= 5'd0;
                        scan_idx_q          <= 17'd0;
                        row_parity_q        <= 1'b0;
                        failed_checks_q     <= 14'd0;
                        initial_check_q     <= 1'b1;
                        update_scan_done_q  <= 1'b0;
                        state               <= ST_INIT_SUM;
                    end
                end

                ST_INIT_SUM: begin
                    if (scan_idx_q == LAST_BIT) begin
                        row_q           <= 14'd0;
                        row_res_q       <= 5'd0;
                        edge_slot_q     <= 5'd0;
                        failed_checks_q <= 14'd0;
                        row_parity_q    <= 1'b0;
                        state           <= ST_GATHER_ROW;
                    end else begin
                        scan_idx_q <= scan_idx_q + 1'b1;
                    end
                end

                ST_GATHER_ROW: begin
                    bucket_start_q  <= bt_off_rom[row_res_q];
                    edge_slot_q     <= 5'd0;
                    row_parity_q    <= 1'b0;
                    if (row_q == 14'd0)
                        failed_checks_q <= 14'd0;
                    min1_q          <= 6'd63;
                    min2_q          <= 6'd63;
                    min1_slot_q     <= 5'd0;
                    sign_negative_q <= 1'b0;
                    row_has_zero_q  <= 1'b0;
                    state           <= ST_GATHER_PIPE;
                end

                ST_GATHER_PIPE: begin
                    if ((edge_slot_q < row_degree) && slot_is_info &&
                        !info_addr_valid) begin
                        error <= 1'b1;
                        busy  <= 1'b0;
                        done  <= 1'b1;
                        state <= ST_IDLE;
                    end else if (edge_slot_q < row_degree) begin
                        edge_slot_q <= edge_slot_q + 1'b1;
                    end

                    if (gather_llr_valid_q) begin
                        row_addr_cache[gather_llr_slot_q] <= llr_addr_q;
                        row_llr_cache[gather_llr_slot_q]  <= llr_rd_q;
                        sign_negative_q <= sign_negative_q ^ llr_rd_q[5];
                        row_parity_q <= row_parity_q ^ decoded_bit_now;
                        if (llr_rd_q == 6'sd0)
                            row_has_zero_q <= 1'b1;
                        if (abs_llr(llr_rd_q) < min1_q) begin
                            min2_q      <= min1_q;
                            min1_q      <= abs_llr(llr_rd_q);
                            min1_slot_q <= gather_llr_slot_q;
                        end else if (abs_llr(llr_rd_q) < min2_q) begin
                            min2_q <= abs_llr(llr_rd_q);
                        end

                        if (gather_llr_slot_q == row_degree - 1'b1) begin
                            if (row_q != LAST_ROW) begin
                                if (row_failed_now)
                                    failed_checks_q <= failed_checks_q + 1'b1;
                                if (row_has_zero_q || (llr_rd_q == 6'sd0)) begin
                                    row_q     <= row_q + 1'b1;
                                    row_res_q <= (row_res_q == 5'd29) ? 5'd0 :
                                                 row_res_q + 1'b1;
                                    state     <= ST_GATHER_ROW;
                                end else begin
                                    emit_slot_q        <= 5'd0;
                                    emit_write_valid_q <= 1'b0;
                                    state              <= ST_EMIT_PIPE;
                                end
                            end else if (failed_checks_with_row == 15'd0) begin
                                converged  <= 1'b1;
                                iter_count <= initial_check_q ? 8'sd0 :
                                               $signed({2'b00, iteration_q});
                                busy       <= 1'b0;
                                done       <= 1'b1;
                                state      <= ST_IDLE;
                            end else if (initial_check_q) begin
                                initial_check_q <= 1'b0;
                                iteration_q     <= 6'd1;
                                if (row_has_zero_q || (llr_rd_q == 6'sd0)) begin
                                    scan_idx_q         <= 17'd0;
                                    update_scan_done_q <= 1'b0;
                                    state              <= ST_UPDATE_PIPE;
                                end else begin
                                    emit_slot_q        <= 5'd0;
                                    emit_write_valid_q <= 1'b0;
                                    state              <= ST_EMIT_PIPE;
                                end
                            end else if (iteration_q >= MAX_ITER) begin
                                converged  <= 1'b0;
                                iter_count <= -8'sd1;
                                error      <= 1'b1;
                                busy       <= 1'b0;
                                done       <= 1'b1;
                                state      <= ST_IDLE;
                            end else begin
                                iteration_q <= iteration_q + 1'b1;
                                if (row_has_zero_q || (llr_rd_q == 6'sd0)) begin
                                    scan_idx_q         <= 17'd0;
                                    update_scan_done_q <= 1'b0;
                                    state              <= ST_UPDATE_PIPE;
                                end else begin
                                    emit_slot_q        <= 5'd0;
                                    emit_write_valid_q <= 1'b0;
                                    state              <= ST_EMIT_PIPE;
                                end
                            end
                        end
                    end
                end

                ST_EMIT_PIPE: begin
                    if (emit_slot_q < row_degree) begin
                        emit_slot_q <= emit_slot_q + 1'b1;
                    end else if (emit_write_valid_q) begin
                        if (row_q == LAST_ROW) begin
                            scan_idx_q         <= 17'd0;
                            update_scan_done_q <= 1'b0;
                            state              <= ST_UPDATE_PIPE;
                        end else begin
                            row_q     <= row_q + 1'b1;
                            row_res_q <= (row_res_q == 5'd29) ? 5'd0 :
                                         row_res_q + 1'b1;
                            state     <= ST_GATHER_ROW;
                        end
                    end
                end

                ST_UPDATE_PIPE: begin
                    if (!update_scan_done_q) begin
                        if (scan_idx_q == LAST_BIT)
                            update_scan_done_q <= 1'b1;
                        else
                            scan_idx_q <= scan_idx_q + 1'b1;
                    end else if (update_write_valid_q) begin
                        row_q           <= 14'd0;
                        row_res_q       <= 5'd0;
                        edge_slot_q     <= 5'd0;
                        row_parity_q    <= 1'b0;
                        failed_checks_q <= 14'd0;
                        state           <= ST_GATHER_ROW;
                    end
                end

                default: begin
                    state <= ST_IDLE;
                    busy  <= 1'b0;
                    error <= 1'b1;
                end
            endcase
        end
    end
endmodule
