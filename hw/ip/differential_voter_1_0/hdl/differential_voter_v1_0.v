// ================================================================
// File   : differential_voter_v1_0_fixed_final.v
// Desc   : Voter(第二个IP核) -- BRAM推断 + DONE语义修正 + ARADDR时序稳固 + 末拍WSTRB硬件推导
//
// Key Fixes:
//   1) BRAM: UG901 模板（读地址打一拍 + 同步读），(* ram_style="block" *)
//   2) DONE: 进入 S_DONE 即置位；在 START / DONE_CLR 时清零
//   3) AXI-Read: ARVALID 标准脉冲握手；ARADDR 用寄存器锁存
//   4) WSTRB: 由 TOTAL_BITS 硬件推导末拍掩码，不依赖软件 out_beats
//   5) RREADY: 在 S_READ_SETUP 与 S_READ_DATA 均为 1，避免 DDR 读超时
//   6) 调试增强：采样并暴露 last_rresp 到 AXI-Lite 0x0E
//
// 2026-08-16 黄金 Testbench 修复（判据见 docs/03-status.md B13~B15/C4）：
//   B13) 投票读流水线错位：bram_addr→bram_dout_r 共 3 拍，而每位投票循环
//        只有 3 拍，S_VOTE_UPDATE 读到的是【上一位】的累加器。修复：循环
//        改为 4 拍（插入 S_VOTE_WAIT），判决改用 2 拍对齐的 bram_dout。
//   B14) 输出判决 (bram_dout > 0) 是无符号比较，负票（如 -1=10'h3FF）
//        被判成 1。修复：按符号位 + 非零判断。
//   B15) 每 64-bit 字丢 1 bit：字装满后 FSM 先绕回 S_OUTPUT_ADDR/PACK 多
//        打包一拍，随后 S_WAIT_BRESP 清 output_word 把它抹掉（81000/65≈1247，
//        与实测少写 19 拍吻合）。修复：装满当拍直接转 S_OUTPUT_SETUP。
//   C4)  第二次 START 不再复用旧累加器：每次 START 都走 S_INIT_BRAM 清零。
//   B16) S_READ_DATA 完成条件 (beat_count>=6 && RVALID) 依赖最后一个 beat
//        握手后 RVALID 仍保持——合规从机会在 RLAST 握手后撤下 RVALID，
//        真实互连上 DUT 将死锁。修复：只看握手计数。
//   D1/D2) 新增 AXI-Lite 0x30 SCORE_MIN：score < SCORE_MIN 的记录在
//        S_PARSE_READ 直接跳过、不投票（反向互补方案 B 的板端取舍；
//        上位机正反双向发送，错误方向/补零记录分数低于阈值被丢弃）。
//        复位默认 0 = 不过滤，与旧行为兼容。
//
// Date  : 2025-11-04 初版 / 2026-08-16 黄金向量对齐修复
// ================================================================

`timescale 1 ns / 1 ps

module differential_voter_v1_0 #
(
    parameter integer C_S00_AXI_DATA_WIDTH = 32,
    parameter integer C_S00_AXI_ADDR_WIDTH = 7,
    parameter integer C_M00_AXI_DATA_WIDTH = 64,
    parameter integer C_M00_AXI_ADDR_WIDTH = 32,
    parameter integer MAX_BURST_LEN        = 16,
    parameter integer TOTAL_BITS           = 81000,
    parameter integer CODEWORD_BITS        = 300,
    parameter integer UPPER_LAYER_BITS     = 150,
    parameter integer LAYER_SIZE           = 40500,
    parameter integer FAST_INIT            = 0
)
(
    // AXI-Lite
    input  wire                               S00_AXI_ACLK,
    input  wire                               S00_AXI_ARESETN,
    input  wire [C_S00_AXI_ADDR_WIDTH-1:0]    S00_AXI_AWADDR,
    input  wire                               S00_AXI_AWVALID,
    output wire                               S00_AXI_AWREADY,
    input  wire [C_S00_AXI_DATA_WIDTH-1:0]    S00_AXI_WDATA,
    input  wire [C_S00_AXI_DATA_WIDTH/8-1:0]  S00_AXI_WSTRB,
    input  wire                               S00_AXI_WVALID,
    output wire                               S00_AXI_WREADY,
    output wire [1:0]                         S00_AXI_BRESP,
    output wire                               S00_AXI_BVALID,
    input  wire                               S00_AXI_BREADY,
    input  wire [C_S00_AXI_ADDR_WIDTH-1:0]    S00_AXI_ARADDR,
    input  wire                               S00_AXI_ARVALID,
    output wire                               S00_AXI_ARREADY,
    output wire [C_S00_AXI_DATA_WIDTH-1:0]    S00_AXI_RDATA,
    output wire [1:0]                         S00_AXI_RRESP,
    output wire                               S00_AXI_RVALID,
    input  wire                               S00_AXI_RREADY,

    // AXI-Full master
    input  wire                               M00_AXI_ACLK,
    input  wire                               M00_AXI_ARESETN,

    // Read address
    output wire [C_M00_AXI_ADDR_WIDTH-1:0]    M00_AXI_ARADDR,
    output wire [7:0]                         M00_AXI_ARLEN,
    output wire [2:0]                         M00_AXI_ARSIZE,
    output wire [1:0]                         M00_AXI_ARBURST,
    output wire                               M00_AXI_ARLOCK,
    output wire [3:0]                         M00_AXI_ARCACHE,
    output wire [2:0]                         M00_AXI_ARPROT,
    output wire [3:0]                         M00_AXI_ARQOS,
    output reg                                M00_AXI_ARVALID,
    input  wire                               M00_AXI_ARREADY,
    input  wire [C_M00_AXI_DATA_WIDTH-1:0]    M00_AXI_RDATA,
    input  wire [1:0]                         M00_AXI_RRESP,
    input  wire                               M00_AXI_RLAST,
    input  wire                               M00_AXI_RVALID,
    output wire                               M00_AXI_RREADY,

    // Write address/data
    output reg  [C_M00_AXI_ADDR_WIDTH-1:0]    M00_AXI_AWADDR,
    output reg  [7:0]                         M00_AXI_AWLEN,
    output wire [2:0]                         M00_AXI_AWSIZE,
    output wire [1:0]                         M00_AXI_AWBURST,
    output wire                               M00_AXI_AWLOCK,
    output wire [3:0]                         M00_AXI_AWCACHE,
    output wire [2:0]                         M00_AXI_AWPROT,
    output wire [3:0]                         M00_AXI_AWQOS,
    output reg                                M00_AXI_AWVALID,
    input  wire                               M00_AXI_AWREADY,
    output wire [C_M00_AXI_DATA_WIDTH-1:0]    M00_AXI_WDATA,
    output wire [C_M00_AXI_DATA_WIDTH/8-1:0]  M00_AXI_WSTRB,
    output reg                                M00_AXI_WLAST,
    output reg                                M00_AXI_WVALID,
    input  wire                               M00_AXI_WREADY,
    input  wire [1:0]                         M00_AXI_BRESP,
    input  wire                               M00_AXI_BVALID,
    output wire                               M00_AXI_BREADY
);

    // ----------------- 常量/辅助 -----------------
    localparam integer WORDS_PER_READ   = 6; // 6 x 64b
    localparam integer TOTAL_BEATS_HW   = (TOTAL_BITS + 63) / 64; // 硬件应写拍数
    localparam [31:0] TIMEOUT_CYCLES    = 32'd1000000000; // 10 s @100 MHz
    localparam [31:0] NO_PROGRESS_CYCLES = 32'd100000000; // 1 s without AXI/FSM progress

    // ----------------- AXI-Lite 映射 -----------------
    wire [31:0] in_addr_s, out_addr_s, in_beats_s, out_beats_s;
    wire [31:0] total_reads_cfg_s;
    wire [31:0] score_min_cfg_s;   // 【D1/D2】分数阈值（0x30），0 = 不过滤
    wire        start_pulse_s, done_clr_s;
    reg         done_s, idle_s, error_s;

    // 调试寄存器
    reg [31:0] debug_state_count;
    reg [31:0] debug_pack_count;
    reg [31:0] debug_setup_count;
    reg [31:0] debug_write_count;
    reg [31:0] debug_first_write_addr;

    reg        axi_bresp_error;

    // >>> 新增：读通道最后一次 RRESP 采样（[1:0]）
    reg [1:0]  last_rresp;

    // =========================================================================
    // P7: 独立硬件周期计数器（10 ns @ 100 MHz）
    // =========================================================================
    reg [31:0] cycles_total;
    reg [31:0] cycles_init;
    reg [31:0] cycles_read;
    reg [31:0] cycles_vote;
    reg [31:0] cycles_write;

    axi_slave_voter u_axil (
        .S_AXI_ACLK    (S00_AXI_ACLK),
        .S_AXI_ARESETN (S00_AXI_ARESETN),
        .S_AXI_AWADDR  (S00_AXI_AWADDR),
        .S_AXI_AWVALID (S00_AXI_AWVALID),
        .S_AXI_AWREADY (S00_AXI_AWREADY),
        .S_AXI_WDATA   (S00_AXI_WDATA),
        .S_AXI_WSTRB   (S00_AXI_WSTRB),
        .S_AXI_WVALID  (S00_AXI_WVALID),
        .S_AXI_WREADY  (S00_AXI_WREADY),
        .S_AXI_BRESP   (S00_AXI_BRESP),
        .S_AXI_BVALID  (S00_AXI_BVALID),
        .S_AXI_BREADY  (S00_AXI_BREADY),
        .S_AXI_ARADDR  (S00_AXI_ARADDR),
        .S_AXI_ARVALID (S00_AXI_ARVALID),
        .S_AXI_ARREADY (S00_AXI_ARREADY),
        .S_AXI_RDATA   (S00_AXI_RDATA),
        .S_AXI_RRESP   (S00_AXI_RRESP),
        .S_AXI_RVALID  (S00_AXI_RVALID),
        .S_AXI_RREADY  (S00_AXI_RREADY),

        .in_addr       (in_addr_s),
        .in_beats      (in_beats_s),
        .out_addr      (out_addr_s),
        .out_beats     (out_beats_s),
        .total_reads_cfg(total_reads_cfg_s),
        .score_min_cfg (score_min_cfg_s),
        .start_pulse   (start_pulse_s),
        .done_clr      (done_clr_s),

        .done          (done_s),
        .idle          (idle_s),
        .error_flag    (error_s),
        .bresp_err_flag(axi_bresp_error),

        .debug_state_count     (debug_state_count),
        .debug_pack_count      (debug_pack_count),
        .debug_setup_count     (debug_setup_count),
        .debug_write_count     (debug_write_count),
        .debug_first_write_addr(debug_first_write_addr),

    // >>> 新增映射：RRESP 只读视图
        .last_rresp            (last_rresp),

        // >>> P7: 硬件周期计数器
        .cycles_total          (cycles_total),
        .cycles_init           (cycles_init),
        .cycles_read           (cycles_read),
        .cycles_vote           (cycles_vote),
        .cycles_write          (cycles_write)
    );

    // ----------------- 跨时钟域同步到 M00_AXI_ACLK -----------------
    reg [31:0] in_addr, out_addr, in_beats, out_beats, total_reads_cfg;
    reg [31:0] score_min_cfg;
    always @(posedge M00_AXI_ACLK) begin
        if (!M00_AXI_ARESETN) begin
            in_addr         <= 32'd0;
            out_addr        <= 32'd0;
            in_beats        <= 32'd0;
            out_beats       <= 32'd0;
            total_reads_cfg <= 32'd0;
            score_min_cfg   <= 32'd0;   // 复位默认不过滤（向后兼容）
        end else begin
            in_addr         <= in_addr_s;
            out_addr        <= out_addr_s;
            in_beats        <= in_beats_s;
            out_beats       <= out_beats_s;
            total_reads_cfg <= total_reads_cfg_s;
            score_min_cfg   <= score_min_cfg_s;
        end
    end

    // START 单脉冲 CDC
    reg [2:0] start_sync_reg;
    always @(posedge M00_AXI_ACLK) begin
        if (!M00_AXI_ARESETN)
            start_sync_reg <= 3'b000;
        else
            start_sync_reg <= {start_pulse_s, start_sync_reg[2:1]};
    end
    wire start_latched_pulse = start_sync_reg[1] & ~start_sync_reg[0];

    // ----------------- 主状态机 -----------------
    localparam [4:0]
        S_IDLE            = 5'd0,
        S_INIT_BRAM       = 5'd1,
        S_READ_SETUP      = 5'd2,
        S_READ_DATA       = 5'd3,
        S_PARSE_READ      = 5'd4,
        S_CALC_ADDR       = 5'd5,
        S_VOTE_READ       = 5'd6,
        S_VOTE_WAIT       = 5'd17,  // 【修订 B13】等 bram_dout 对齐（2 拍读延迟）
        S_VOTE_UPDATE     = 5'd7,
        S_NEXT_READ       = 5'd8,
        S_OUTPUT_PREFETCH = 5'd9,
        S_OUTPUT_ADDR     = 5'd10,
        S_OUTPUT_PACK     = 5'd11,
        S_OUTPUT_SETUP    = 5'd12,
        S_OUTPUT_WRITE    = 5'd13,
        S_WAIT_BRESP      = 5'd14,
        S_DONE            = 5'd15,
        S_ERROR           = 5'd16,
        S_VOTE_PIPE       = 5'd18,
        S_VOTE_DRAIN      = 5'd19;

    reg [4:0] state, next_state;

    // ----------------- 数据路径寄存器 -----------------
    reg [63:0] read_words [0:5];
    reg [2:0]  read_beat_count;

    // 【S1 时序改造 2026-09-03】原为 reg [299:0] current_codeword，判决处按
    // bit_in_codeword 随机索引，综合成 300 选 1 多路选择器（SE250 下是 500 选 1）。
    // 那是 implementation-timing.rpt 第 1~4 名关键路径的共同源头
    // （LUT6→MUXF7→MUXF8→LUT6→MUXF7→LUT6→CARRY4×2→LUT2，9 级逻辑，
    //  9.666 ns 数据路径、走线占 66.5%），整机 WNS 只剩 +0.088 ns。
    // bit_in_codeword 在投票循环里严格 0→CODEWORD_BITS-1 顺序递增，
    // 根本不需要随机访问：改成移位寄存器，每拍只看最低位。
    // 位宽同时改为跟随 CODEWORD_BITS（原字面量 300 不随 parameter 变，是 SE250 的坑）。
    reg [CODEWORD_BITS-1:0] codeword_sr;
    reg [15:0]  current_position;

    reg [8:0]   bit_in_codeword;

    reg [16:0]  bram_addr;        // 读/写地址
    reg  signed [9:0] bram_din;
    reg               bram_we;

    // 投票读写地址分离；元数据与两级 BRAM 读延迟对齐。
    reg [16:0] bram_wr_addr;
    reg [16:0] vote_addr_stage0, vote_addr_stage1;
    reg        vote_bit_stage0, vote_bit_stage1;
    reg        vote_valid_stage0, vote_valid_stage1;

    // BRAM 实体 + 同步读寄存器
    // 【修订 B13】读通路只有两级：bram_addr →（打一拍）bram_raddr_q →
    // （同步读出）bram_dout。原先还有一级 bram_dout_r，使数据晚 3 拍才到，
    // 与 3 拍的投票循环错开一位——已被删除，改由 FSM 插入 S_VOTE_WAIT 对齐。
    (* ram_style = "block" *) reg [9:0] bram [0:TOTAL_BITS-1];
    reg [16:0] bram_raddr_q;
    reg [9:0]  bram_dout;


    wire [9:0]  parse_score    = read_words[0][9:0];
    wire [15:0] parse_position = read_words[0][25:10];

    reg [16:0] init_addr;          // 17位，足够覆盖 81000
    reg [31:0] read_count;
    reg [31:0] total_reads;

    reg [31:0] read_addr;
    reg [31:0] read_addr_reg;      // ARADDR 锁存
    // B20 修复：AXI 规范 A3.4.1 要求突发不得跨越 4KB 边界。每条记录 48B、步长
    // 也是 48B，而 4096 不是 48 的整数倍，固定 6 拍突发会周期性跨页（4096 条
    // 记录中 32 次，首次在记录 85 / 0x...0ff0）。这里把跨页的读拆成两笔：
    // 先读到页边界，再从页边界读完本条记录剩余的拍。
    reg [31:0] rd_ptr;             // 本条记录下一笔突发的起始地址
    reg [3:0]  rd_burst_beats;     // 本笔突发的拍数（1..9）
    reg [3:0]  rd_burst_done;      // 本笔突发已收到的拍数

    // 输出打包
    reg [16:0] output_bit_count;
    reg [63:0] output_word;
    reg [5:0]  bit_in_output;

    reg [31:0] write_addr;
    reg [31:0] total_write_count;
    reg [31:0] remaining_beats;    // 仅供调试，WSTRB 不再依赖此值

    reg        pack_trigger;
    reg        pack_pending;
    reg  [1:0] output_addr_wait;   // 【修订 B13】输出读对齐要等 2 拍（bram_dout 两级）
    reg        first_write_captured;

    // ----------------- 位置/安全函数 -----------------
    function [16:0] calc_layer_position;
        input [8:0]  bit_idx;
        input [15:0] position;
        begin
            if (bit_idx < UPPER_LAYER_BITS)
                calc_layer_position = bit_idx + position;
            else
                calc_layer_position = (bit_idx - UPPER_LAYER_BITS) + position + LAYER_SIZE;
        end
    endfunction

    function [16:0] safe_address;
        input [16:0] addr;
        begin
            if (addr >= TOTAL_BITS) safe_address = TOTAL_BITS - 1;
            else                    safe_address = addr;
        end
    endfunction

    wire [16:0] vote_issue_addr =
        safe_address(calc_layer_position(bit_in_codeword, current_position));
    wire [16:0] bram_read_addr =
        (state == S_VOTE_PIPE) ? vote_issue_addr : bram_addr;
    wire signed [9:0] vote_read_value =
        (bram_we && (bram_wr_addr == vote_addr_stage1)) ? bram_din : bram_dout;

    function signed [9:0] safe_vote_value;
        input signed [9:0] vote;
        begin
            if (vote > 10'sd511)       safe_vote_value = 10'sd511;
            else if (vote < -10'sd512) safe_vote_value = -10'sd512;
            else                       safe_vote_value = vote;
        end
    endfunction

    // ----------------- 条件/超时 -----------------
    wire init_complete        = (FAST_INIT) ? (init_addr >= 17'd63) : (init_addr >= (TOTAL_BITS - 1));
    wire read_setup_complete  = 1'b1;
    // 【修订 B16】完成条件只看握手计数：第 6 次握手发生在 RLAST 那拍，
    // beat_count 要到下一拍才等于 6；而合规从机在 RLAST 握手后即撤下 RVALID。
    // 原条件 (beat_count>=6 && RVALID) 依赖残留的 RVALID 电平，真实互连上会死锁。
    wire read_data_complete   = (read_beat_count >= 3'd6);
    // 页内剩余拍数（rd_ptr 恒为 8B 对齐）与本记录剩余拍数，取较小者为本笔突发长度
    wire [9:0] rd_beats_to_page_end = (13'd4096 - {1'b0, rd_ptr[11:0]}) >> 3;
    wire [2:0] rd_beats_remaining   = WORDS_PER_READ[2:0] - read_beat_count;
    wire [3:0] rd_next_burst_beats  =
        (rd_beats_to_page_end < {6'd0, rd_beats_remaining}) ? rd_beats_to_page_end[3:0]
                                                           : rd_beats_remaining;
    wire rd_burst_complete    = (rd_burst_done >= rd_burst_beats);
    // 【D1/D2】比对分低于阈值的记录不参与投票（含上位机补零的尾批记录）。
    // parse_score 在 S_PARSE_READ 拍从 read_words[0] 组合读出，天然有效。
    wire score_below_min      = ({22'd0, parse_score} < score_min_cfg);
    wire vote_issue_complete  = (bit_in_codeword >= CODEWORD_BITS - 1);
    wire vote_drain_complete  = !vote_valid_stage0 && !vote_valid_stage1 && !bram_we;

    // A long task is valid as long as AXI or the internal pipeline is advancing.
    // The absolute counter catches runaway tasks; the no-progress counter catches
    // a missing R/B response without penalising large record counts.
    wire progress_event =
        (M00_AXI_ARVALID && M00_AXI_ARREADY) ||
        (M00_AXI_RVALID  && M00_AXI_RREADY)  ||
        (M00_AXI_AWVALID && M00_AXI_AWREADY) ||
        (M00_AXI_WVALID  && M00_AXI_WREADY)  ||
        (M00_AXI_BVALID  && M00_AXI_BREADY)  ||
        (state == S_INIT_BRAM && init_addr <= (TOTAL_BITS - 1)) ||
        (state == S_VOTE_PIPE) ||
        (state == S_VOTE_DRAIN) ||
        (state == S_OUTPUT_PACK && output_bit_count < TOTAL_BITS);

    reg [31:0] global_timeout_counter;
    reg [31:0] no_progress_counter;

    // ----------------- BRAM 同步读写（UG901 模板） -----------------
    always @(posedge M00_AXI_ACLK) begin
        if (bram_we)
            bram[bram_wr_addr] <= bram_din;  // 独立写地址，允许读写同时前进
        bram_raddr_q <= bram_read_addr;      // 读地址打一拍
        bram_dout    <= bram[bram_raddr_q];  // 同步读
    end

    // ----------------- 状态寄存 & 超时计数 -----------------
    always @(posedge M00_AXI_ACLK) begin
        if (!M00_AXI_ARESETN) state <= S_IDLE;
        else                  state <= next_state;
    end

    always @(posedge M00_AXI_ACLK) begin
        if (!M00_AXI_ARESETN) begin
            global_timeout_counter <= 32'd0;
            no_progress_counter    <= 32'd0;
        end else if (state == S_IDLE) begin
            global_timeout_counter <= 32'd0;
            no_progress_counter    <= 32'd0;
        end else begin
            if (global_timeout_counter < TIMEOUT_CYCLES)
                global_timeout_counter <= global_timeout_counter + 1;
            if (progress_event)
                no_progress_counter <= 32'd0;
            else if (no_progress_counter < NO_PROGRESS_CYCLES)
                no_progress_counter <= no_progress_counter + 1;
        end
    end

    // ----------------- 数据路径（时序） -----------------
    always @(posedge M00_AXI_ACLK) begin
        if (!M00_AXI_ARESETN) begin

            init_addr           <= 17'd0;
            read_count          <= 32'd0;
            read_beat_count     <= 4'd0;
            bit_in_codeword     <= 9'd0;

            bram_addr           <= 17'd0;
            bram_wr_addr        <= 17'd0;
            bram_din            <= 10'sd0;
            bram_we             <= 1'b0;
            vote_addr_stage0    <= 17'd0;
            vote_addr_stage1    <= 17'd0;
            vote_bit_stage0     <= 1'b0;
            vote_bit_stage1     <= 1'b0;
            vote_valid_stage0   <= 1'b0;
            vote_valid_stage1   <= 1'b0;

            output_bit_count    <= 17'd0;
            output_word         <= 64'd0;
            bit_in_output       <= 6'd0;

            write_addr          <= 32'd0;
            total_write_count   <= 32'd0;
            remaining_beats     <= 32'd0;

            pack_trigger        <= 1'b0;
            pack_pending        <= 1'b0;
            output_addr_wait    <= 2'd0;
            first_write_captured<= 1'b0;

            codeword_sr         <= {CODEWORD_BITS{1'b0}};
            current_position    <= 16'd0;

            debug_state_count   <= 32'd0;
            debug_pack_count    <= 32'd0;
            debug_setup_count   <= 32'd0;
            debug_write_count   <= 32'd0;
            debug_first_write_addr <= 32'd0;

            read_addr_reg       <= 32'd0;
            read_addr           <= 32'd0;
            rd_ptr              <= 32'd0;
            rd_burst_beats      <= 3'd0;
            rd_burst_done       <= 3'd0;
            total_reads         <= 32'd0;

            // >>> 新增复位
            last_rresp          <= 2'b00;
        end else begin
            bram_we      <= 1'b0;
            pack_trigger <= 1'b0;

            // 两级票元数据与 bram_dout 对齐；消费票通过单级待写结果旁路。
            vote_valid_stage0 <= (state == S_VOTE_PIPE);
            vote_valid_stage1 <= vote_valid_stage0;
            vote_addr_stage1  <= vote_addr_stage0;
            vote_bit_stage1   <= vote_bit_stage0;
            if (state == S_VOTE_PIPE) begin
                vote_addr_stage0 <= vote_issue_addr;
                vote_bit_stage0  <= codeword_sr[0];
            end
            if (vote_valid_stage1) begin
                if (vote_bit_stage1)
                    bram_din <= safe_vote_value(vote_read_value + 10'sd1);
                else
                    bram_din <= safe_vote_value(vote_read_value - 10'sd1);
                bram_wr_addr <= vote_addr_stage1;
                bram_we      <= 1'b1;
            end

            if (state == S_OUTPUT_PACK)  debug_pack_count  <= debug_pack_count + 1;
            if (state == S_OUTPUT_SETUP) debug_setup_count <= debug_setup_count + 1;
            if (state == S_OUTPUT_WRITE && M00_AXI_WVALID && M00_AXI_WREADY) begin
                debug_write_count <= debug_write_count + 1;
                if (!first_write_captured) begin
                    debug_first_write_addr <= write_addr;
                    first_write_captured   <= 1'b1;
                end
            end

            case (state)
                S_IDLE: begin
                    if (start_latched_pulse) begin
                        read_count        <= 32'd0;
                        total_reads       <= total_reads_cfg;
                        read_addr         <= in_addr;
                        rd_ptr            <= in_addr;
                        read_beat_count   <= 3'd0;

                        output_bit_count  <= 17'd0;
                        output_word       <= 64'd0;
                        bit_in_output     <= 6'd0;
                        write_addr        <= out_addr;
                        remaining_beats   <= out_beats;
                        total_write_count <= 32'd0;

                        pack_pending      <= 1'b0;
                        output_addr_wait  <= 2'd0;

                        first_write_captured <= 1'b0;
                        debug_state_count    <= state;
                        debug_pack_count     <= 32'd0;
                        debug_setup_count    <= 32'd0;
                        debug_write_count    <= 32'd0;

                        // 【修订 C4】每次任务都从零累加：原实现靠 bram_initialized
                        // 只在首次 START 清零，第二次任务会在上一轮的旧票上叠加。
                        init_addr          <= 17'd0;
                    end
                end

                S_INIT_BRAM: begin
                    if ((FAST_INIT && init_addr <= 17'd63) || (!FAST_INIT && init_addr <= (TOTAL_BITS - 1))) begin
                        bram_addr    <= init_addr;
                        bram_wr_addr <= init_addr;
                        bram_din     <= 10'sd0;
                        bram_we   <= 1'b1;
                        init_addr <= init_addr + 1;
                    end
                    debug_state_count <= state;
                end

                S_READ_SETUP: begin
                    // 用 rd_ptr 而非 read_addr：拆分后的第二笔要从页边界开始。
                    // read_beat_count 是「本条记录」的拍索引，需跨两笔突发连续，
                    // 因此不能在这里清零，改到记录切换处清。
                    read_addr_reg   <= rd_ptr;      // 锁存AR地址
                    rd_burst_beats  <= rd_next_burst_beats;
                    rd_burst_done   <= 3'd0;
                    debug_state_count <= state;
                end

                S_READ_DATA: begin
                    if (M00_AXI_RVALID && M00_AXI_RREADY) begin
                        read_words[read_beat_count] <= M00_AXI_RDATA;
                        read_beat_count <= read_beat_count + 1;
                        rd_burst_done   <= rd_burst_done + 1;
                        rd_ptr          <= rd_ptr + 32'd8;
                        // >>> 新增：采样 RRESP（只在握手成功时）
                        last_rresp <= M00_AXI_RRESP;
                    end
                    debug_state_count <= state;
                end

                S_PARSE_READ: begin
                    current_position            <= parse_position;

                    codeword_sr[37:0]     <= read_words[0][63:26];
                    codeword_sr[101:38]   <= read_words[1][63:0];
                    codeword_sr[165:102]  <= read_words[2][63:0];
                    codeword_sr[229:166]  <= read_words[3][63:0];
                    codeword_sr[293:230]  <= read_words[4][63:0];
                    codeword_sr[299:294]  <= read_words[5][5:0];

                    bit_in_codeword <= 9'd0;

                    debug_state_count <= state;
                end

                S_VOTE_PIPE: begin
                    // 每拍发射一位；地址由当前索引计算，元数据随后与读数据对齐。
                    bram_addr <= vote_issue_addr;
                    if (!vote_issue_complete)
                        bit_in_codeword <= bit_in_codeword + 1'b1;
                    codeword_sr <= {1'b0, codeword_sr[CODEWORD_BITS-1:1]};
                    debug_state_count <= state;
                end

                S_VOTE_DRAIN: begin
                    debug_state_count <= state;
                end

                S_NEXT_READ: begin
                    if (read_count < total_reads - 1) begin
                        read_count <= read_count + 1;
                        read_addr  <= read_addr + (WORDS_PER_READ * 8);
                        rd_ptr     <= read_addr + (WORDS_PER_READ * 8);
                    end
                    read_beat_count <= 3'd0;
                    debug_state_count <= state;
                end

                S_OUTPUT_PREFETCH: begin
                    bram_addr <= 17'd0;
                    debug_state_count <= state;
                end

                S_OUTPUT_ADDR: begin
                    // 【修订 B13】bram_dout 两级读管线：给地址后要等 2 拍数据才到，
                    // 因此 ADDR 共 3 拍（给地址 + 等 2 拍），PACK 拍正好取到本位。
                    if (output_addr_wait == 2'd0) begin
                        if (output_bit_count < TOTAL_BITS)
                            bram_addr <= output_bit_count;
                        output_addr_wait <= 2'd1;
                    end else if (output_addr_wait != 2'd2) begin
                        output_addr_wait <= output_addr_wait + 2'd1;
                    end else begin
                        output_addr_wait <= 2'd0;
                    end
                    debug_state_count <= state;
                end

                S_OUTPUT_PACK: begin
                    debug_state_count <= state;
                    if (output_bit_count < TOTAL_BITS) begin
                        // 【修订 B14】bram_dout 是无符号的：负票（如 -1=10'h3FF）
                        // 直接 >0 比较会误判成 1。按补码语义：非负且非零才是 1。
                        output_word[bit_in_output] <= ~bram_dout[9] && (bram_dout != 10'd0);

                        if (bit_in_output == 6'd63) begin
                            pack_trigger  <= 1'b1;   // 满 64b
                            pack_pending  <= 1'b1;
                            bit_in_output <= 6'd0;
                        end else if (output_bit_count == TOTAL_BITS - 1) begin
                            pack_trigger  <= 1'b1;   // 尾包 <64b
                            pack_pending  <= 1'b1;
                            bit_in_output <= 6'd0;
                        end else begin
                            bit_in_output <= bit_in_output + 6'd1;
                        end

                        output_bit_count <= output_bit_count + 17'd1;
                    end
                end

                S_OUTPUT_SETUP: begin
                    debug_state_count <= state;
                end

                S_OUTPUT_WRITE: begin
                    debug_state_count <= state;
                    if (M00_AXI_WVALID && M00_AXI_WREADY) begin
                        total_write_count <= total_write_count + 1;
                        write_addr        <= write_addr + 32'd8;
                        if (remaining_beats != 0)
                            remaining_beats <= remaining_beats - 32'd1;
                    end
                end

                S_WAIT_BRESP: begin
                    if (M00_AXI_BVALID && M00_AXI_BRESP == 2'b00) begin
                        pack_pending  <= 1'b0;     // 本拍写清空待写
                        output_word   <= 64'd0;
                        bit_in_output <= 6'd0;
                    end
                    debug_state_count <= state;
                end

                S_DONE:  debug_state_count <= state;
                S_ERROR: begin
                    // 出错也清理待写，避免残留
                    pack_pending  <= 1'b0;
                    output_word   <= 64'd0;
                    bit_in_output <= 6'd0;
                    debug_state_count <= state;
                end

                default: ;
            endcase
        end
    end

    // ----------------- 状态转移 -----------------
    // 【修订 B15】本拍是否装满一个字（含尾包）：装满当拍直接转 S_OUTPUT_SETUP。
    wire word_done = (bit_in_output == 6'd63) || (output_bit_count == TOTAL_BITS - 1);

    always @(*) begin
        next_state = state;

        if (global_timeout_counter >= TIMEOUT_CYCLES ||
            no_progress_counter >= NO_PROGRESS_CYCLES) begin
            next_state = S_ERROR;
        end else begin
            case (state)
                // 【修订 C4】每次 START 都走清零路径（81,000 拍 ≈ 0.81 ms @100 MHz）
                S_IDLE:            next_state = start_latched_pulse ? S_INIT_BRAM : S_IDLE;
                S_INIT_BRAM:       next_state = init_complete ? S_READ_SETUP : S_INIT_BRAM;
                S_READ_SETUP:      next_state = read_setup_complete ? S_READ_DATA  : S_READ_SETUP;
                S_READ_DATA:       next_state = !rd_burst_complete ? S_READ_DATA
                                              : (read_data_complete ? S_PARSE_READ : S_READ_SETUP);
                // 【D1/D2】低分记录直接跳到下一条，不进入投票循环
                S_PARSE_READ:      next_state = score_below_min ? S_NEXT_READ : S_VOTE_PIPE;
                S_VOTE_PIPE:       next_state = vote_issue_complete
                                              ? ((read_count >= total_reads - 1) ? S_VOTE_DRAIN : S_NEXT_READ)
                                              : S_VOTE_PIPE;
                S_VOTE_DRAIN:      next_state = vote_drain_complete ? S_NEXT_READ : S_VOTE_DRAIN;
                S_NEXT_READ:       next_state = (read_count >= total_reads - 1) ? S_OUTPUT_PREFETCH : S_READ_SETUP;
                S_OUTPUT_PREFETCH: next_state = S_OUTPUT_ADDR;

                S_OUTPUT_ADDR: begin
                    next_state = (output_addr_wait == 2'd2) ? S_OUTPUT_PACK : S_OUTPUT_ADDR;
                end

                S_OUTPUT_PACK: begin
                    // 【修订 B15】装满当拍直接去发写请求。原实现先绕回 ADDR/PACK
                    // 多打包一拍，而 S_WAIT_BRESP 会清 output_word，那一 bit 被
                    // 静默丢弃（每 64 bit 丢 1 bit，实测只写出 1,247/1,266 拍）。
                    if (word_done)                        next_state = S_OUTPUT_SETUP;
                    else if (output_bit_count >= TOTAL_BITS) next_state = S_DONE;
                    else                                     next_state = S_OUTPUT_ADDR;
                end

                S_OUTPUT_SETUP: begin
                    if (M00_AXI_AWVALID && M00_AXI_AWREADY) next_state = S_OUTPUT_WRITE;
                    else                                     next_state = S_OUTPUT_SETUP;
                end

                S_OUTPUT_WRITE: begin
                    if (M00_AXI_WVALID && M00_AXI_WREADY) next_state = S_WAIT_BRESP;
                    else                                  next_state = S_OUTPUT_WRITE;
                end

                S_WAIT_BRESP: begin
                    if (M00_AXI_BVALID) begin
                        if (M00_AXI_BRESP != 2'b00)                      next_state = S_ERROR;
                        else if (output_bit_count >= TOTAL_BITS && !pack_pending) next_state = S_DONE; // 写完最后一拍
                        else                                              next_state = S_OUTPUT_ADDR;
                    end else next_state = S_WAIT_BRESP;
                end

                // >>> 与修复方案一致：S_ERROR 必须退出
                S_DONE:  next_state = S_IDLE;
                S_ERROR: next_state = S_IDLE;
                default: next_state = S_IDLE;
            endcase
        end
    end

    // ----------------- AXI Read Channel -----------------
    // ARVALID：在 S_READ_SETUP 拉高一次，ARREADY 接受后拉低（不依赖 next_state）
    always @(posedge M00_AXI_ACLK) begin
        if (!M00_AXI_ARESETN) begin
            M00_AXI_ARVALID <= 1'b0;
        end else begin
            if (state == S_READ_SETUP && !M00_AXI_ARVALID)
                M00_AXI_ARVALID <= 1'b1;
            else if (M00_AXI_ARREADY)
                M00_AXI_ARVALID <= 1'b0;
        end
    end

    assign M00_AXI_ARADDR  = read_addr_reg; // 地址已在 S_READ_SETUP 锁存
    assign M00_AXI_ARLEN   = {5'd0, rd_burst_beats} - 8'd1; // 本笔突发拍数-1（B20）
    assign M00_AXI_ARSIZE  = 3'b011;        // 8B
    assign M00_AXI_ARBURST = 2'b01;         // INCR
    assign M00_AXI_ARLOCK  = 1'b0;
    assign M00_AXI_ARCACHE = 4'b0011;
    assign M00_AXI_ARPROT  = 3'b000;
    assign M00_AXI_ARQOS   = 4'b0000;

    // >>> 关键修复：RREADY must be high during AR handshake to avoid DDR timeout
    // 原：assign M00_AXI_RREADY = (state == S_READ_DATA);
    // 现：
    assign M00_AXI_RREADY  = (state == S_READ_DATA) || (state == S_READ_SETUP);

    // ----------------- AXI Write Channel -----------------
    assign M00_AXI_AWSIZE  = 3'b011;
    assign M00_AXI_AWBURST = 2'b01;
    assign M00_AXI_AWLOCK  = 1'b0;
    assign M00_AXI_AWCACHE = 4'b0011;
    assign M00_AXI_AWPROT  = 3'b000;
    assign M00_AXI_AWQOS   = 4'b0000;

    // AW
    always @(posedge M00_AXI_ACLK) begin
        if (!M00_AXI_ARESETN) begin
            M00_AXI_AWVALID <= 1'b0;
            M00_AXI_AWADDR  <= 32'd0;
            M00_AXI_AWLEN   <= 8'd0; // 单拍
        end else begin
            if (state == S_OUTPUT_SETUP && pack_pending) begin
                if (!M00_AXI_AWVALID) begin
                    M00_AXI_AWADDR  <= write_addr;
                    M00_AXI_AWLEN   <= 8'd0;
                    M00_AXI_AWVALID <= 1'b1;
                end else if (M00_AXI_AWREADY) begin
                    M00_AXI_AWVALID <= 1'b0;
                end
            end else begin
                M00_AXI_AWVALID <= 1'b0;
            end
        end
    end

    // 硬件推导末拍 WSTRB 掩码
    wire [5:0] last_bits  = TOTAL_BITS[5:0];                                // TOTAL_BITS % 64
    wire [3:0] last_bytes = (last_bits == 0) ? 4'd8 : ((last_bits + 6'd7) >> 3);
    wire [7:0] last_mask  = (last_bytes == 8) ? 8'hFF : ((8'h01 << last_bytes) - 1);
    wire       is_last_hw_beat_now = (state == S_OUTPUT_WRITE) && (total_write_count == (TOTAL_BEATS_HW - 1));

    assign M00_AXI_WDATA = output_word;
    assign M00_AXI_WSTRB = is_last_hw_beat_now ? last_mask : 8'hFF;

    always @(posedge M00_AXI_ACLK) begin
        if (!M00_AXI_ARESETN) begin
            M00_AXI_WVALID <= 1'b0;
            M00_AXI_WLAST  <= 1'b0;
        end else begin
            if (state == S_OUTPUT_WRITE && pack_pending) begin
                if (!M00_AXI_WVALID) begin
                    M00_AXI_WVALID <= 1'b1;
                    M00_AXI_WLAST  <= 1'b1; // 单拍
                end else if (M00_AXI_WREADY) begin
                    M00_AXI_WVALID <= 1'b0;
                    M00_AXI_WLAST  <= 1'b0;
                end
            end else begin
                M00_AXI_WVALID <= 1'b0;
                M00_AXI_WLAST  <= 1'b0;
            end
        end
    end

    // B 通道握手
    assign M00_AXI_BREADY = 1'b1;

    // BRESP 统计
    reg [31:0] bresp_cnt_ok, bresp_cnt_err;
    always @(posedge M00_AXI_ACLK) begin
        if (!M00_AXI_ARESETN) begin
            bresp_cnt_ok    <= 32'd0;
            bresp_cnt_err   <= 32'd0;
            axi_bresp_error <= 1'b0;
        end else if (M00_AXI_BVALID && M00_AXI_BREADY) begin
            if (M00_AXI_BRESP == 2'b00) bresp_cnt_ok  <= bresp_cnt_ok + 1;
            else begin
                bresp_cnt_err   <= bresp_cnt_err + 1;
                axi_bresp_error <= 1'b1;
            end
        end
    end

    // ----------------- DONE / IDLE / ERROR（单点驱动） -----------------
    always @(posedge M00_AXI_ACLK) begin
        if (!M00_AXI_ARESETN) begin
            done_s  <= 1'b0;
            idle_s  <= 1'b1;
            error_s <= 1'b0;
        end else begin
            idle_s <= (state == S_IDLE);

            if (done_clr_s) begin
                done_s  <= 1'b0;
                error_s <= 1'b0;
            end else begin
                if (start_latched_pulse) begin
                    // 启动同时清 DONE/ERROR，避免二次启动残留
                    done_s  <= 1'b0;
                    error_s <= 1'b0;
                end

                if (state == S_ERROR)
                    error_s <= 1'b1;

                // 进入 S_DONE 即置位 DONE（FSM 已确保全部写提交完成）
                if (state == S_DONE)
                    done_s <= 1'b1;
            end
        end
    end

    // =========================================================================
    // P7: 独立硬件周期计数器逻辑（M00_AXI_ACLK 时钟域）
    // =========================================================================
    always @(posedge M00_AXI_ACLK) begin
        if (!M00_AXI_ARESETN) begin
            cycles_total <= 32'd0;
            cycles_init  <= 32'd0;
            cycles_read  <= 32'd0;
            cycles_vote  <= 32'd0;
            cycles_write <= 32'd0;
        end else if (start_latched_pulse) begin
            cycles_total <= 32'd0;
            cycles_init  <= 32'd0;
            cycles_read  <= 32'd0;
            cycles_vote  <= 32'd0;
            cycles_write <= 32'd0;
        end else begin
            if (state != S_IDLE && state != S_DONE && state != S_ERROR) begin
                if (!(&cycles_total))
                    cycles_total <= cycles_total + 1'b1;
            end

            case (state)
                S_INIT_BRAM: begin
                    if (!(&cycles_init))
                        cycles_init <= cycles_init + 1'b1;
                end

                S_READ_SETUP, S_READ_DATA: begin
                    if (!(&cycles_read))
                        cycles_read <= cycles_read + 1'b1;
                end

                S_PARSE_READ, S_VOTE_PIPE, S_VOTE_DRAIN, S_NEXT_READ: begin
                    if (!(&cycles_vote))
                        cycles_vote <= cycles_vote + 1'b1;
                end

                S_OUTPUT_PREFETCH, S_OUTPUT_ADDR, S_OUTPUT_PACK, S_OUTPUT_SETUP, S_OUTPUT_WRITE, S_WAIT_BRESP: begin
                    if (!(&cycles_write))
                        cycles_write <= cycles_write + 1'b1;
                end

                default: ;
            endcase
        end
    end

endmodule


// ================================================================
// AXI-Lite Slave
// Map (word-addressed):
// 0x00: CTRL/STATUS  (W: bit0 START, bit1 DONE_CLR; R: bit0 IDLE, bit1 DONE, bit2 ERROR)
// 0x04: IN_ADDR
// 0x08: IN_BEATS
// 0x0C: OUT_ADDR
// 0x10: OUT_BEATS
// 0x14: TOTAL_READS
// 0x18: DBG_STATE
// 0x1C: DBG_PACK
// 0x20: DBG_SETUP
// 0x24: DBG_WRITE
// 0x28: DBG_FIRST_AWADDR
// 0x2C: ERR_FLAGS (R: bit0 ERROR_S, bit1 AXI_BRESP_ERROR)
// 0x30: SCORE_MIN  【D1/D2】比对分阈值；score < SCORE_MIN 的记录不投票。
//       复位默认 0（不过滤）。注：06-implementation-plan 原写 0x18，
//       但 0x18 已被 DBG_STATE 占用，实际落在 0x30。
// 0x38: LAST_RRESP (R: bit[1:0] 最后一次读通道 RRESP)
// ================================================================
module axi_slave_voter #
(
    parameter C_S_AXI_DATA_WIDTH = 32,
    parameter C_S_AXI_ADDR_WIDTH = 7
)
(
    input  wire                             S_AXI_ACLK,
    input  wire                             S_AXI_ARESETN,
    input  wire [C_S_AXI_ADDR_WIDTH-1:0]    S_AXI_AWADDR,
    input  wire                             S_AXI_AWVALID,
    output wire                             S_AXI_AWREADY,
    input  wire [C_S_AXI_DATA_WIDTH-1:0]    S_AXI_WDATA,
    input  wire [C_S_AXI_DATA_WIDTH/8-1:0]  S_AXI_WSTRB,
    input  wire                             S_AXI_WVALID,
    output wire                             S_AXI_WREADY,
    output reg  [1:0]                       S_AXI_BRESP,
    output reg                              S_AXI_BVALID,
    input  wire                             S_AXI_BREADY,
    input  wire [C_S_AXI_ADDR_WIDTH-1:0]    S_AXI_ARADDR,
    input  wire                             S_AXI_ARVALID,
    output reg                              S_AXI_ARREADY,
    output reg  [C_S_AXI_DATA_WIDTH-1:0]    S_AXI_RDATA,
    output reg  [1:0]                       S_AXI_RRESP,
    output reg                              S_AXI_RVALID,
    input  wire                             S_AXI_RREADY,

    output reg  [31:0] in_addr,
    output reg  [31:0] in_beats,
    output reg  [31:0] out_addr,
    output reg  [31:0] out_beats,
    output reg  [31:0] total_reads_cfg,
    output reg  [31:0] score_min_cfg,
    output reg         start_pulse,
    output reg         done_clr,

    input  wire        done,
    input  wire        idle,
    input  wire        error_flag,
    input  wire        bresp_err_flag,

    input  wire [31:0] debug_state_count,
    input  wire [31:0] debug_pack_count,
    input  wire [31:0] debug_setup_count,
    input  wire [31:0] debug_write_count,
    input  wire [31:0] debug_first_write_addr,

    // >>> 新增：暴露 last_rresp
    input  wire [1:0]  last_rresp,

    // >>> P7: 硬件周期计数器
    input  wire [31:0] cycles_total,
    input  wire [31:0] cycles_init,
    input  wire [31:0] cycles_read,
    input  wire [31:0] cycles_vote,
    input  wire [31:0] cycles_write
);

    reg [C_S_AXI_ADDR_WIDTH-1:0] awaddr_q;
    reg [C_S_AXI_DATA_WIDTH-1:0] wdata_q;
    reg aw_pending, w_pending;
    wire aw_accept = S_AXI_AWVALID && S_AXI_AWREADY;
    wire w_accept = S_AXI_WVALID && S_AXI_WREADY;
    wire write_commit = (aw_pending || aw_accept) &&
                        (w_pending || w_accept) && ~S_AXI_BVALID;
    wire [C_S_AXI_ADDR_WIDTH-1:0] write_addr = aw_pending ? awaddr_q : S_AXI_AWADDR;
    wire [C_S_AXI_DATA_WIDTH-1:0] write_data = w_pending ? wdata_q : S_AXI_WDATA;
    wire [4:0] waddr = write_addr[6:2];
    wire [4:0] raddr = S_AXI_ARADDR[6:2];
    assign S_AXI_AWREADY = ~aw_pending & ~S_AXI_BVALID;
    assign S_AXI_WREADY = ~w_pending & ~S_AXI_BVALID;

    // ----------------- 写通道 -----------------
    always @(posedge S_AXI_ACLK) begin
        if (!S_AXI_ARESETN) begin
            S_AXI_BVALID    <= 1'b0;
            S_AXI_BRESP     <= 2'b00;
            awaddr_q        <= {C_S_AXI_ADDR_WIDTH{1'b0}};
            wdata_q         <= {C_S_AXI_DATA_WIDTH{1'b0}};
            aw_pending      <= 1'b0;
            w_pending       <= 1'b0;

            in_addr         <= 32'd0;
            in_beats        <= 32'd0;
            out_addr        <= 32'd0;
            out_beats       <= 32'd0;
            total_reads_cfg <= 32'd0;
            score_min_cfg   <= 32'd0;
            start_pulse     <= 1'b0;
            done_clr        <= 1'b0;

        end else begin
            if (aw_accept) begin
                awaddr_q <= S_AXI_AWADDR;
                aw_pending <= 1'b1;
            end
            if (w_accept) begin
                wdata_q <= S_AXI_WDATA;
                w_pending <= 1'b1;
            end

            if (write_commit) begin
                aw_pending <= 1'b0;
                w_pending <= 1'b0;
                case (waddr)
                    5'h00: begin
                        start_pulse <= write_data[0];
                        done_clr    <= write_data[1];
                    end
                    5'h01: in_addr         <= write_data;
                    5'h02: in_beats        <= write_data;
                    5'h03: out_addr        <= write_data;
                    5'h04: out_beats       <= write_data;
                    5'h05: total_reads_cfg <= write_data;
                    5'h0C: score_min_cfg   <= write_data;   // 0x30【D1/D2】
                    default: ;
                endcase
                S_AXI_BVALID <= 1'b1;
                S_AXI_BRESP  <= 2'b00;
            end

            if (S_AXI_BVALID && S_AXI_BREADY) begin
                S_AXI_BVALID <= 1'b0;
                start_pulse  <= 1'b0; // 脉冲自动清
                done_clr     <= 1'b0;
            end
        end
    end

    // ----------------- 读通道 -----------------
    reg ar_hs;
    always @(posedge S_AXI_ACLK) begin
        if (!S_AXI_ARESETN) begin
            S_AXI_ARREADY <= 1'b0;
            S_AXI_RVALID  <= 1'b0;
            S_AXI_RRESP   <= 2'b00;
            S_AXI_RDATA   <= {C_S_AXI_DATA_WIDTH{1'b0}};
            ar_hs         <= 1'b0;
        end else begin
            S_AXI_ARREADY <= (S_AXI_ARVALID && !S_AXI_RVALID);
            ar_hs         <= S_AXI_ARVALID && S_AXI_ARREADY;

            if (ar_hs) begin
                case (raddr)
                    5'h00: S_AXI_RDATA <= {29'd0, error_flag, done, idle};
                    5'h01: S_AXI_RDATA <= in_addr;
                    5'h02: S_AXI_RDATA <= in_beats;
                    5'h03: S_AXI_RDATA <= out_addr;
                    5'h04: S_AXI_RDATA <= out_beats;
                    5'h05: S_AXI_RDATA <= total_reads_cfg;
                    5'h06: S_AXI_RDATA <= debug_state_count;
                    5'h07: S_AXI_RDATA <= debug_pack_count;
                    5'h08: S_AXI_RDATA <= debug_setup_count;
                    5'h09: S_AXI_RDATA <= debug_write_count;
                    5'h0A: S_AXI_RDATA <= debug_first_write_addr;
                    5'h0B: S_AXI_RDATA <= {30'd0, bresp_err_flag, error_flag};
                    5'h0C: S_AXI_RDATA <= score_min_cfg;
                    // >>> 新增：0x38
                    5'h0E: S_AXI_RDATA <= {30'd0, last_rresp};
                    // >>> P7: 硬件周期计数器（0x40~0x50）
                    5'h10: S_AXI_RDATA <= cycles_total; // 0x40
                    5'h11: S_AXI_RDATA <= cycles_init;  // 0x44
                    5'h12: S_AXI_RDATA <= cycles_read;  // 0x48
                    5'h13: S_AXI_RDATA <= cycles_vote;  // 0x4C
                    5'h14: S_AXI_RDATA <= cycles_write; // 0x50
                    default: S_AXI_RDATA <= 32'd0;
                endcase
                S_AXI_RRESP  <= 2'b00;
                S_AXI_RVALID <= 1'b1;
            end

            if (S_AXI_RVALID && S_AXI_RREADY)
                S_AXI_RVALID <= 1'b0;
        end
    end

endmodule
