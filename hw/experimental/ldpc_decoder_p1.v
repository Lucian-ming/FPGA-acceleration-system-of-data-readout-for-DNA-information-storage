`timescale 1ns/1ps

// DVB-S2 R=5/6 硬判决 flooding Min-Sum 译码器原型。
// 每个校验行按边串行处理；当前 LLR 在整轮消息累加完成前保持不变。
module ldpc_decoder_p1 #(
    parameter integer N_BITS = 64800,
    parameter integer M_ROWS = 10800,
    parameter integer MAX_ITER = 50,
    parameter BT_ROM_FILE = "logs/ldpc/golden/bt_by_res.hex",
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
    localparam [4:0] ST_SYND_ROW      = 5'd1;
    localparam [4:0] ST_SYND_PREP     = 5'd2;
    localparam [4:0] ST_SYND_ROM      = 5'd3;
    localparam [4:0] ST_SYND_LLR      = 5'd4;
    localparam [4:0] ST_SYND_CAPTURE  = 5'd5;
    localparam [4:0] ST_INIT_SUM      = 5'd6;
    localparam [4:0] ST_GATHER_ROW    = 5'd7;
    localparam [4:0] ST_GATHER_PREP   = 5'd8;
    localparam [4:0] ST_GATHER_ROM    = 5'd9;
    localparam [4:0] ST_GATHER_LLR    = 5'd10;
    localparam [4:0] ST_GATHER_CAPTURE= 5'd11;
    localparam [4:0] ST_EMIT_READ     = 5'd12;
    localparam [4:0] ST_EMIT_WRITE    = 5'd13;
    localparam [4:0] ST_UPDATE_READ   = 5'd14;
    localparam [4:0] ST_UPDATE_WRITE  = 5'd15;

    localparam [16:0] LAST_BIT = N_BITS - 1;
    localparam [13:0] LAST_ROW = M_ROWS - 1;

    reg [4:0] state;

    // 输入位、旧 LLR、下一轮聚合和输出码字分开存放。
    (* ram_style = "block" *) reg                  input_mem   [0:N_BITS-1];
    (* ram_style = "block" *) reg signed [5:0]     llr_mem     [0:N_BITS-1];
    (* ram_style = "block" *) reg signed [11:0]    sum_mem     [0:N_BITS-1];
    (* ram_style = "block" *) reg                  decoded_mem [0:N_BITS-1];

    // B_t 转置桶：每桶 20 项；主表同步读，供 BRAM ROM 推断。
    (* rom_style = "block" *) reg [23:0] bt_rom [0:599];
    (* rom_style = "distributed" *) reg [11:0] bt_off_rom [0:30];
    reg [23:0] bt_data_q;
    reg [11:0] bucket_start_q;

    initial begin
        $readmemh(BT_ROM_FILE, bt_rom);
        $readmemh(BT_OFF_FILE, bt_off_rom);
    end

    reg [13:0] row_q;
    reg [4:0]  row_res_q;
    reg [4:0]  edge_slot_q;
    reg [4:0]  emit_slot_q;
    reg [16:0] scan_idx_q;
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

    wire [13:0] base_x = bt_data_q[21:8];
    wire [7:0] group_t = bt_data_q[7:0];
    wire [14:0] row_plus_mod = {1'b0, row_q} + 15'd10800;
    wire [13:0] delta_x = (row_q >= base_x) ?
                          (row_q - base_x) :
                          (row_plus_mod - {1'b0, base_x});
    // ÷30 改用「乘倒数 + 右移」：Vivado 把常量除法 /30 展开成 11 级进位链，是 WNS 主因
    // （布线后 -1.663 ns、20 级逻辑、11 个 CARRY4）。
    // ⚠️ 乘数必须取 ceil(2^S/30)，不能取 floor——floor 版在 30 的整数倍上会少 1
    //    （30*4369 = 131070 < 2^17 ⇒ 30/30 算成 0）。本处 K=17477、S=19 已在
    //    delta_x ∈ [0,10800) **全范围**穷举核对与 n/30 精确相等（非仅 30 的倍数）。
    wire [28:0] info_m_mul = delta_x * 15'd17477;
    wire [9:0]  info_m = info_m_mul[28:19];              // ≤ 359
    wire [13:0] info_m_x30 = (info_m << 5) - (info_m << 1);  // 30*m，用于等价复检余数
    wire [16:0] group_t_ext = {9'd0, group_t};
    wire [16:0] group_offset = group_t_ext * 17'd360;
    wire [16:0] info_column = 17'd10800 + group_offset + info_m;
    // 等价于原来的 (delta_x % 30 == 0) && (info_m < 360)，但不算取模。
    wire info_addr_valid = (bt_index_full < 12'd600) &&
                           (group_t < 8'd150) &&
                           (info_m < 10'd360) &&
                           (info_m_x30 == delta_x);

    wire [16:0] check_column = (edge_slot_q == 5'd0) ?
                               ((row_q == 14'd0) ? 17'd0 :
                                ({3'd0, row_q} - 17'd1)) :
                               {3'd0, row_q};
    wire [16:0] llr_read_column = slot_is_info ? info_column : check_column;
    wire llr_read_en = ((state == ST_SYND_LLR) ||
                        (state == ST_GATHER_LLR)) &&
                       (!slot_is_info || info_addr_valid);

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

    wire        sum_rd_en   = (state == ST_EMIT_READ) || (state == ST_UPDATE_READ);
    wire [16:0] sum_rd_addr = (state == ST_EMIT_READ) ? row_addr_cache[emit_slot_q] : scan_idx_q;

    // 同步读口：主 B_t ROM、LLR、聚合和输入位均按周期读取。
    always @(posedge clk) begin
        if (rst) begin
            bt_data_q      <= 24'd0;
            llr_rd_q       <= 6'sd0;
            llr_addr_q     <= 17'd0;
            sum_rd_q       <= 12'sd0;
            sum_addr_q     <= 17'd0;
            input_bit_rd_q <= 1'b0;
            result_bit     <= 1'b0;
        end else begin
            if (((state == ST_GATHER_ROM) || (state == ST_SYND_ROM)) &&
                (bt_index_full < 12'd600))
                bt_data_q <= bt_rom[bt_index];

            if (llr_read_en) begin
                llr_rd_q <= llr_mem[llr_read_column];
                llr_addr_q <= llr_read_column;
            end

            // sum_mem 只有一个读口：原先两个状态各写一条读语句，Vivado 会当成两个读端口
            // 而拒绝推断 BRAM（Synth 8-6849 Infeasible ram_style="block"）。合并成单条
            // 读语句 + 地址 mux；两状态互斥，语义不变。
            if (sum_rd_en) begin
                sum_rd_q   <= sum_mem[sum_rd_addr];
                sum_addr_q <= sum_rd_addr;
            end
            if (state == ST_UPDATE_READ)
                input_bit_rd_q <= input_mem[scan_idx_q];

            result_bit <= decoded_mem[result_addr];
        end
    end

    // ---- 单写口存储：Vivado 8-3391 要求「每个 RAM 在一个 process 里只有一个写语句」 ----
    // 装载期（ST_IDLE）与更新期（ST_UPDATE_WRITE）、清零期（ST_INIT_SUM）与累加期
    // （ST_EMIT_WRITE）在时间上互斥，故把多路写合并为单写口的地址/数据 mux。
    wire        llr_wr_load = (load_we == 1'b1) && (state == ST_IDLE) && (load_addr < N_BITS);
    wire        llr_wr_upd  = (state == ST_UPDATE_WRITE);
    wire [16:0] llr_wr_addr = llr_wr_load ? load_addr : sum_addr_q;
    wire [5:0]  llr_wr_data = llr_wr_load ? (load_bit ? 6'sd6 : -6'sd6) : update_llr;
    wire        dec_wr_data = llr_wr_load ? load_bit : ($signed(update_llr) > 0);

    always @(posedge clk) begin
        if (llr_wr_load || llr_wr_upd) begin
            llr_mem[llr_wr_addr]     <= llr_wr_data;
            decoded_mem[llr_wr_addr] <= dec_wr_data;
        end
    end

    wire        sum_wr_clr  = (state == ST_INIT_SUM);
    wire        sum_wr_acc  = (state == ST_EMIT_WRITE);
    wire [16:0] sum_wr_addr = sum_wr_clr ? scan_idx_q : sum_addr_q;
    wire [11:0] sum_wr_data = sum_wr_clr ? 12'sd0 :
                              (sum_rd_q + {{5{message_q[6]}}, message_q});

    always @(posedge clk) begin
        if (sum_wr_clr || sum_wr_acc)
            sum_mem[sum_wr_addr] <= sum_wr_data;
    end

    integer cache_i;
    always @(posedge clk) begin
        if (rst) begin
            state             <= ST_IDLE;
            busy              <= 1'b0;
            done              <= 1'b0;
            converged         <= 1'b0;
            error             <= 1'b0;
            iter_count        <= 8'sd0;
            row_q             <= 14'd0;
            row_res_q         <= 5'd0;
            edge_slot_q       <= 5'd0;
            emit_slot_q       <= 5'd0;
            scan_idx_q        <= 17'd0;
            failed_checks_q   <= 14'd0;
            iteration_q       <= 6'd0;
            initial_check_q   <= 1'b0;
            row_parity_q      <= 1'b0;
            bucket_start_q    <= 12'd0;
            min1_q            <= 6'd63;
            min2_q            <= 6'd63;
            min1_slot_q       <= 5'd0;
            sign_negative_q   <= 1'b0;
            row_has_zero_q    <= 1'b0;
            message_q         <= 7'sd0;
            for (cache_i = 0; cache_i < 22; cache_i = cache_i + 1) begin
                row_addr_cache[cache_i] <= 17'd0;
                row_llr_cache[cache_i] <= 6'sd0;
            end
        end else begin
            done <= 1'b0;

            if ((load_we == 1'b1) && (state == ST_IDLE) &&
                (load_addr < N_BITS)) begin
                input_mem[load_addr] <= load_bit;
            end

            case (state)
                ST_IDLE: begin
                    if (start && !load_we) begin
                        busy            <= 1'b1;
                        converged       <= 1'b0;
                        error           <= 1'b0;
                        iter_count      <= 8'sd0;
                        iteration_q     <= 6'd0;
                        row_q           <= 14'd0;
                        row_res_q       <= 5'd0;
                        edge_slot_q     <= 5'd0;
                        row_parity_q    <= 1'b0;
                        failed_checks_q <= 14'd0;
                        initial_check_q <= 1'b1;
                        state           <= ST_SYND_ROW;
                    end
                end

                ST_SYND_ROW: begin
                    bucket_start_q <= bt_off_rom[row_res_q];
                    edge_slot_q    <= 5'd0;
                    row_parity_q   <= 1'b0;
                    state          <= ST_SYND_PREP;
                end

                ST_SYND_PREP: begin
                    if (edge_slot_q >= row_degree) begin
                        error      <= 1'b1;
                        busy       <= 1'b0;
                        done       <= 1'b1;
                        state      <= ST_IDLE;
                    end else if (slot_is_info) begin
                        state <= ST_SYND_ROM;
                    end else begin
                        state <= ST_SYND_LLR;
                    end
                end

                ST_SYND_ROM: begin
                    if (bt_index_full >= 12'd600) begin
                        error <= 1'b1;
                        busy  <= 1'b0;
                        done  <= 1'b1;
                        state <= ST_IDLE;
                    end else begin
                        state <= ST_SYND_LLR;
                    end
                end

                ST_SYND_LLR: begin
                    if (slot_is_info && !info_addr_valid) begin
                        error <= 1'b1;
                        busy  <= 1'b0;
                        done  <= 1'b1;
                        state <= ST_IDLE;
                    end else begin
                        state <= ST_SYND_CAPTURE;
                    end
                end

                ST_SYND_CAPTURE: begin
                    if (edge_slot_q == row_degree - 1'b1) begin
                        if (row_failed_now)
                            failed_checks_q <= failed_checks_q + 1'b1;
                        if (row_q == LAST_ROW) begin
                            if (failed_checks_with_row == 15'd0) begin
                                converged  <= 1'b1;
                                iter_count <= initial_check_q ? 8'sd0 :
                                               $signed({2'b00, iteration_q});
                                busy       <= 1'b0;
                                done       <= 1'b1;
                                state      <= ST_IDLE;
                            end else if (initial_check_q) begin
                                initial_check_q <= 1'b0;
                                iteration_q     <= 6'd1;
                                scan_idx_q      <= 17'd0;
                                failed_checks_q <= 14'd0;
                                state           <= ST_INIT_SUM;
                            end else if (iteration_q >= MAX_ITER) begin
                                converged  <= 1'b0;
                                iter_count <= -8'sd1;
                                error      <= 1'b1;
                                busy       <= 1'b0;
                                done       <= 1'b1;
                                state      <= ST_IDLE;
                            end else begin
                                iteration_q     <= iteration_q + 1'b1;
                                scan_idx_q      <= 17'd0;
                                failed_checks_q <= 14'd0;
                                state           <= ST_INIT_SUM;
                            end
                        end else begin
                            row_q       <= row_q + 1'b1;
                            row_res_q   <= (row_res_q == 5'd29) ? 5'd0 :
                                           row_res_q + 1'b1;
                            row_parity_q <= 1'b0;
                            state       <= ST_SYND_ROW;
                        end
                    end else begin
                        row_parity_q <= row_parity_q ^ decoded_bit_now;
                        edge_slot_q  <= edge_slot_q + 1'b1;
                        state        <= ST_SYND_PREP;
                    end
                end

                ST_INIT_SUM: begin
                    if (scan_idx_q == LAST_BIT) begin
                        row_q           <= 14'd0;
                        row_res_q       <= 5'd0;
                        edge_slot_q     <= 5'd0;
                        failed_checks_q <= 14'd0;
                        state           <= ST_GATHER_ROW;
                    end else begin
                        scan_idx_q <= scan_idx_q + 1'b1;
                    end
                end

                ST_GATHER_ROW: begin
                    bucket_start_q  <= bt_off_rom[row_res_q];
                    edge_slot_q     <= 5'd0;
                    min1_q          <= 6'd63;
                    min2_q          <= 6'd63;
                    min1_slot_q     <= 5'd0;
                    sign_negative_q <= 1'b0;
                    row_has_zero_q  <= 1'b0;
                    state           <= ST_GATHER_PREP;
                end

                ST_GATHER_PREP: begin
                    if (edge_slot_q >= row_degree) begin
                        error <= 1'b1;
                        busy  <= 1'b0;
                        done  <= 1'b1;
                        state <= ST_IDLE;
                    end else if (slot_is_info) begin
                        state <= ST_GATHER_ROM;
                    end else begin
                        state <= ST_GATHER_LLR;
                    end
                end

                ST_GATHER_ROM: begin
                    if (bt_index_full >= 12'd600) begin
                        error <= 1'b1;
                        busy  <= 1'b0;
                        done  <= 1'b1;
                        state <= ST_IDLE;
                    end else begin
                        state <= ST_GATHER_LLR;
                    end
                end

                ST_GATHER_LLR: begin
                    if (slot_is_info && !info_addr_valid) begin
                        error <= 1'b1;
                        busy  <= 1'b0;
                        done  <= 1'b1;
                        state <= ST_IDLE;
                    end else begin
                        state <= ST_GATHER_CAPTURE;
                    end
                end

                ST_GATHER_CAPTURE: begin
                    row_addr_cache[edge_slot_q] <= llr_addr_q;
                    row_llr_cache[edge_slot_q]  <= llr_rd_q;
                    sign_negative_q <= sign_negative_q ^ llr_rd_q[5];
                    if (llr_rd_q == 6'sd0)
                        row_has_zero_q <= 1'b1;
                    if (abs_llr(llr_rd_q) < min1_q) begin
                        min2_q      <= min1_q;
                        min1_q      <= abs_llr(llr_rd_q);
                        min1_slot_q <= edge_slot_q;
                    end else if (abs_llr(llr_rd_q) < min2_q) begin
                        min2_q <= abs_llr(llr_rd_q);
                    end

                    if (edge_slot_q == row_degree - 1'b1) begin
                        emit_slot_q <= 5'd0;
                        if (row_has_zero_q || (llr_rd_q == 6'sd0)) begin
                            if (row_q == LAST_ROW) begin
                                scan_idx_q <= 17'd0;
                                state      <= ST_UPDATE_READ;
                            end else begin
                                row_q       <= row_q + 1'b1;
                                row_res_q   <= (row_res_q == 5'd29) ? 5'd0 :
                                               row_res_q + 1'b1;
                                state       <= ST_GATHER_ROW;
                            end
                        end else begin
                            state <= ST_EMIT_READ;
                        end
                    end else begin
                        edge_slot_q <= edge_slot_q + 1'b1;
                        state       <= ST_GATHER_PREP;
                    end
                end

                ST_EMIT_READ: begin
                    message_q <= emit_message;
                    state     <= ST_EMIT_WRITE;
                end

                ST_EMIT_WRITE: begin
                    if (emit_slot_q == row_degree - 1'b1) begin
                        if (row_q == LAST_ROW) begin
                            scan_idx_q <= 17'd0;
                            state      <= ST_UPDATE_READ;
                        end else begin
                            row_q       <= row_q + 1'b1;
                            row_res_q   <= (row_res_q == 5'd29) ? 5'd0 :
                                           row_res_q + 1'b1;
                            state       <= ST_GATHER_ROW;
                        end
                    end else begin
                        emit_slot_q <= emit_slot_q + 1'b1;
                        state       <= ST_EMIT_READ;
                    end
                end

                ST_UPDATE_READ: begin
                    state <= ST_UPDATE_WRITE;
                end

                ST_UPDATE_WRITE: begin
                    if (sum_addr_q == LAST_BIT) begin
                        row_q           <= 14'd0;
                        row_res_q       <= 5'd0;
                        edge_slot_q     <= 5'd0;
                        row_parity_q    <= 1'b0;
                        failed_checks_q <= 14'd0;
                        state           <= ST_SYND_ROW;
                    end else begin
                        scan_idx_q <= scan_idx_q + 1'b1;
                        state      <= ST_UPDATE_READ;
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
