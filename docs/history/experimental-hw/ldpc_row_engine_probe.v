// p=1 flooding Min-Sum 行引擎的 OOC 资源/时序探针。
// 这是结构探针，不是完整 LDPC 译码器，也不得加入 IP 打包源集。

module ldpc_h_addr_gen (
    input  wire        clk,
    input  wire        req,
    input  wire [13:0] r,
    input  wire [9:0]  edge_idx,
    output reg  [16:0] addr,
    output reg         valid
);
    // 探针内容非真实 B_t，仅为避免被折叠；仿射序列使每个行余数恰有 20 个信息候选。
    (* rom_style = "block" *) reg [13:0] bt_rom [0:599];
    integer init_i;
    initial begin
        for (init_i = 0; init_i < 600; init_i = init_i + 1)
            bt_rom[init_i] = (init_i * 137 + 593) % 10800;
    end

    reg [13:0] row_q;
    reg [13:0] base_q;
    reg [9:0]  edge_idx_q;
    reg        req_q;

    reg        stage2_req;
    reg        stage2_is_info;
    reg        stage2_check_valid;
    reg [16:0] stage2_check_addr;
    reg [13:0] stage2_delta;
    reg [7:0]  stage2_group_t;

    wire [9:0] table_i = (edge_idx_q >= 10'd2) ? edge_idx_q - 10'd2 : 10'd0;
    reg [7:0] group_t_comb;
    reg [13:0] delta_comb;
    reg [14:0] row_plus_mod;
    wire [13:0] m_full = stage2_delta / 14'd30;
    wire [13:0] rem_full = stage2_delta % 14'd30;

    // 同步 ROM 读：edge_idx 0/1 是双对角校验边；2..601 扫描 600 个基地址候选。
    always @(posedge clk) begin
        req_q <= req;
        if (req) begin
            row_q      <= r;
            edge_idx_q <= edge_idx;
            if ((edge_idx >= 10'd2) && (edge_idx <= 10'd601))
                base_q <= bt_rom[edge_idx - 10'd2];
        end
    end

    // 第 2 级先算 14-bit 环形差和组号，避免把除法/地址合成压在 ROM 输出同一拍。
    always @* begin
        group_t_comb = 8'd0;
        if (table_i < 10'd195)
            group_t_comb = table_i / 10'd13;
        else
            group_t_comb = 8'd15 + ((table_i - 10'd195) / 10'd3);

        row_plus_mod = {1'b0, row_q} + 15'd10800;
        if (row_q >= base_q)
            delta_comb = row_q - base_q;
        else
            delta_comb = row_plus_mod - {1'b0, base_q};
    end

    always @(posedge clk) begin
        stage2_req         <= req_q;
        stage2_is_info     <= req_q && (edge_idx_q >= 10'd2) && (edge_idx_q <= 10'd601) &&
                              (row_q < 14'd10800);
        stage2_check_valid <= req_q && (row_q < 14'd10800) &&
                              ((edge_idx_q == 10'd0) ||
                               ((edge_idx_q == 10'd1) && (row_q != 14'd0)));
        stage2_check_addr  <= (edge_idx_q == 10'd0) ?
                              ((row_q == 14'd0) ? 17'd0 : {3'b0, row_q} - 17'd1) :
                              {3'b0, row_q};
        stage2_delta       <= delta_comb;
        stage2_group_t     <= group_t_comb;
    end

    // 第 3 级完成 /30 和列地址拼装；输出 valid 与 addr 同步对齐。
    always @(posedge clk) begin
        addr  <= 17'd0;
        valid <= 1'b0;
        if (stage2_req) begin
            if (stage2_is_info) begin
                if ((rem_full == 14'd0) && (m_full < 14'd360)) begin
                    addr  <= 17'd10800 + (stage2_group_t * 9'd360) + m_full;
                    valid <= 1'b1;
                end
            end else if (stage2_check_valid) begin
                addr  <= stage2_check_addr;
                valid <= 1'b1;
            end
        end
    end
endmodule


module ldpc_row_engine_probe #(
    parameter integer N       = 64800,
    parameter integer MAXDEG  = 22,
    parameter integer LLR_W   = 6,
    parameter integer ACC_W   = 10,
    parameter integer AW      = 17,
    parameter integer DEG_W   = (MAXDEG < 2) ? 1 : $clog2(MAXDEG + 1)
) (
    input  wire                    clk,
    input  wire                    rst,
    input  wire                    start,
    input  wire [DEG_W-1:0]        deg,
    input  wire [13:0]             row,
    input  wire                    use_h_addr,
    input  wire [AW-1:0]           edge_addr,
    input  wire                    edge_valid,
    input  wire                    load_we,
    input  wire [AW-1:0]           load_addr,
    input  wire signed [LLR_W-1:0] load_llr,
    input  wire signed [ACC_W-1:0] load_acc,
    output reg                     done,
    output reg                     update_valid,
    output reg  [AW-1:0]            update_addr,
    output reg signed [ACC_W-1:0]   update_data
);
    localparam [1:0] ST_IDLE  = 2'd0;
    localparam [1:0] ST_GATHER = 2'd1;
    localparam [1:0] ST_EMIT  = 2'd2;
    localparam integer WORK_W = (ACC_W > LLR_W) ? ACC_W + 1 : LLR_W + 1;
    localparam [ACC_W-1:0] ACC_MAX_BITS = {1'b0, {(ACC_W-1){1'b1}}};
    localparam [ACC_W-1:0] ACC_MIN_BITS = {1'b1, {(ACC_W-1){1'b0}}};

    reg [1:0] state;
    reg [DEG_W-1:0] deg_q;
    reg [DEG_W-1:0] accepted_count;
    reg [DEG_W-1:0] stored_count;
    reg [DEG_W-1:0] emit_idx;
    reg [DEG_W-1:0] acc_rd_idx_q;
    reg [AW-1:0] acc_rd_addr_q;
    reg [13:0] row_q;
    reg use_h_addr_q;
    reg [9:0] h_scan_idx;
    reg h_scan_done;

    reg [AW-1:0] row_addr_cache [0:MAXDEG-1];
    reg [LLR_W-1:0] row_llr_cache [0:MAXDEG-1];
    reg [LLR_W-1:0] min1;
    reg [LLR_W-1:0] min2;
    reg sign_product;

    // 仅由 load_we 写、同步随机读，综合为 simple dual-port block RAM。
    (* ram_style = "block" *) reg signed [LLR_W-1:0] llr_mem [0:N-1];
    reg signed [LLR_W-1:0] llr_rd_data;

    // 由 load_we 初始化、由 EMIT 读改写，综合为 simple dual-port block RAM。
    (* ram_style = "block" *) reg signed [ACC_W-1:0] acc_mem [0:N-1];
    reg signed [ACC_W-1:0] acc_rd_data;

    reg rd_valid_q;
    reg [AW-1:0] rd_addr_q;
    reg acc_rd_pending;

    function [LLR_W-1:0] abs_llr;
        input [LLR_W-1:0] value;
        begin
            if (value[LLR_W-1])
                abs_llr = (~value) + 1'b1;
            else
                abs_llr = value;
        end
    endfunction

    wire [16:0] h_addr;
    wire        h_valid;
    wire        h_req = (state == ST_GATHER) && use_h_addr_q && !h_scan_done;
    ldpc_h_addr_gen h_addr_gen (
        .clk      (clk),
        .req      (h_req),
        .r        (row_q),
        .edge_idx (h_scan_idx),
        .addr     (h_addr),
        .valid    (h_valid)
    );

    wire [AW-1:0] selected_addr = use_h_addr_q ? h_addr : edge_addr;
    wire selected_valid = use_h_addr_q ? h_valid : edge_valid;
    wire llr_rd_en = (state == ST_GATHER) && selected_valid &&
                     (accepted_count < deg_q);

    // LLR BRAM：同步读口与独立装载写口。
    always @(posedge clk) begin
        if (llr_rd_en)
            llr_rd_data <= llr_mem[selected_addr];
    end
    always @(posedge clk) begin
        if (load_we && (state == ST_IDLE))
            llr_mem[load_addr] <= load_llr;
    end

    wire acc_rd_en = (state == ST_EMIT) && (emit_idx < deg_q);
    wire acc_wr_en = (load_we && (state == ST_IDLE)) || acc_rd_pending;
    wire [AW-1:0] acc_wr_addr = (load_we && (state == ST_IDLE)) ? load_addr : acc_rd_addr_q;

    reg signed [WORK_W-1:0] acc_work;
    reg signed [WORK_W-1:0] msg_work;
    reg signed [WORK_W-1:0] max_work;
    reg signed [WORK_W-1:0] min_work;
    reg signed [WORK_W-1:0] sum_work;
    reg [ACC_W-1:0] sat_acc;
    wire [LLR_W-1:0] emit_abs = (abs_llr(row_llr_cache[acc_rd_idx_q]) == min1) ?
                                  min2 : min1;
    wire emit_sign = sign_product ^ row_llr_cache[acc_rd_idx_q][LLR_W-1];
    wire signed [LLR_W:0] emit_message = emit_sign ?
        -$signed({1'b0, emit_abs}) : $signed({1'b0, emit_abs});

    // LLR_W/ACC_W 均可覆盖；扩展后比较有符号上下限，溢出时饱和而非回绕。
    always @* begin
        acc_work = {{(WORK_W-ACC_W){acc_rd_data[ACC_W-1]}}, acc_rd_data};
        msg_work = {{(WORK_W-(LLR_W+1)){emit_message[LLR_W]}}, emit_message};
        max_work = {{(WORK_W-ACC_W){1'b0}}, ACC_MAX_BITS};
        min_work = {{(WORK_W-ACC_W){1'b1}}, ACC_MIN_BITS};
        sum_work = acc_work + msg_work;
        sat_acc  = sum_work[ACC_W-1:0];
        if (sum_work > max_work)
            sat_acc = ACC_MAX_BITS;
        else if (sum_work < min_work)
            sat_acc = ACC_MIN_BITS;
    end

    // 累加器 BRAM：同步读口、一个写口；load 与内部饱和写回互斥使用。
    always @(posedge clk) begin
        if (acc_rd_en)
            acc_rd_data <= acc_mem[row_addr_cache[emit_idx]];
    end
    always @(posedge clk) begin
        if (acc_wr_en) begin
            if (load_we && (state == ST_IDLE))
                acc_mem[acc_wr_addr] <= load_acc;
            else
                acc_mem[acc_wr_addr] <= sat_acc;
        end
    end

    always @(posedge clk) begin
        if (rst) begin
            state          <= ST_IDLE;
            deg_q          <= {DEG_W{1'b0}};
            accepted_count <= {DEG_W{1'b0}};
            stored_count   <= {DEG_W{1'b0}};
            emit_idx       <= {DEG_W{1'b0}};
            acc_rd_idx_q   <= {DEG_W{1'b0}};
            acc_rd_addr_q  <= {AW{1'b0}};
            row_q          <= 14'd0;
            use_h_addr_q   <= 1'b0;
            h_scan_idx     <= 10'd0;
            h_scan_done    <= 1'b0;
            min1           <= {LLR_W{1'b1}};
            min2           <= {LLR_W{1'b1}};
            sign_product   <= 1'b0;
            rd_valid_q     <= 1'b0;
            rd_addr_q      <= {AW{1'b0}};
            acc_rd_pending <= 1'b0;
            done           <= 1'b0;
            update_valid   <= 1'b0;
            update_addr    <= {AW{1'b0}};
            update_data    <= {ACC_W{1'b0}};
        end else begin
            done           <= 1'b0;
            update_valid   <= 1'b0;
            rd_valid_q     <= llr_rd_en;
            acc_rd_pending <= acc_rd_en;

            // 让每次 BRAM 累加写回都有可观察负载，避免综合删除整条数据通路。
            if (acc_rd_pending) begin
                update_valid <= 1'b1;
                update_addr  <= acc_rd_addr_q;
                update_data  <= sat_acc;
            end

            if (llr_rd_en)
                rd_addr_q <= selected_addr;

            if (acc_rd_en) begin
                acc_rd_addr_q <= row_addr_cache[emit_idx];
                acc_rd_idx_q  <= emit_idx;
                emit_idx      <= emit_idx + 1'b1;
            end

            if (h_req) begin
                if (h_scan_idx == 10'd601)
                    h_scan_done <= 1'b1;
                else
                    h_scan_idx <= h_scan_idx + 1'b1;
            end

            case (state)
                ST_IDLE: begin
                    if (start) begin
                        if (deg == {DEG_W{1'b0}}) begin
                            done <= 1'b1;
                        end else begin
                            state          <= ST_GATHER;
                            deg_q          <= (deg > MAXDEG) ? MAXDEG : deg;
                            accepted_count <= {DEG_W{1'b0}};
                            stored_count   <= {DEG_W{1'b0}};
                            emit_idx       <= {DEG_W{1'b0}};
                            row_q          <= row;
                            use_h_addr_q   <= use_h_addr;
                            h_scan_idx     <= 10'd0;
                            h_scan_done    <= 1'b0;
                            min1           <= {LLR_W{1'b1}};
                            min2           <= {LLR_W{1'b1}};
                            sign_product   <= 1'b0;
                            acc_rd_pending <= 1'b0;
                        end
                    end
                end

                ST_GATHER: begin
                    if (llr_rd_en)
                        accepted_count <= accepted_count + 1'b1;

                    if (rd_valid_q && (stored_count < MAXDEG)) begin
                        row_addr_cache[stored_count] <= rd_addr_q;
                        row_llr_cache[stored_count]  <= llr_rd_data;
                        sign_product <= sign_product ^ llr_rd_data[LLR_W-1];
                        if (abs_llr(llr_rd_data) < min1) begin
                            min2 <= min1;
                            min1 <= abs_llr(llr_rd_data);
                        end else if (abs_llr(llr_rd_data) < min2) begin
                            min2 <= abs_llr(llr_rd_data);
                        end

                        if (stored_count == (deg_q - 1'b1)) begin
                            state    <= ST_EMIT;
                            emit_idx <= {DEG_W{1'b0}};
                        end
                        stored_count <= stored_count + 1'b1;
                    end
                end

                ST_EMIT: begin
                    if (acc_rd_pending && !acc_rd_en && (emit_idx == deg_q)) begin
                        state <= ST_IDLE;
                        done  <= 1'b1;
                    end
                end

                default: state <= ST_IDLE;
            endcase
        end
    end
endmodule
