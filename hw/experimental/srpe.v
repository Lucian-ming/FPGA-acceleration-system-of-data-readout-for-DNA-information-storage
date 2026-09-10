// DEPRECATED：未进入 component.xml 文件集，也未被生产顶层实例化。
// 生产 Stage1 实现为 srpe_batch.v；本文件仅保留作历史参考，禁止接回数据通路。
// Filename: srpe.v
// FINAL FIX: Changed wire declarations to reg for variables assigned within procedural blocks.
// UPDATED: SCORE_WIDTH increased to 10 to match combined-plane scoring.

`timescale 1ns / 1ps

module srpe #(
    parameter integer NUM_LC = 48,
    parameter integer STRIDE = 850,
    parameter integer WATERMARK_SEGMENT_BPS = 1000,
    parameter integer READ_BPS = 150,
    parameter integer SCORE_WIDTH = 10, // increased from 9 to 10 to fit combined-plane score
    parameter integer POS_WIDTH = 10
)(
    input  wire                       clk,
    input  wire                       rst_n,
    input  wire                       start_engine,
    input  wire                       bram_write_en,
    input  wire [5:0]                 bram_sel,
    input  wire [POS_WIDTH-1:0]       bram_write_addr,
    input  wire [1:0]                 bram_write_data,
    output reg                        engine_done,
    input  wire [READ_BPS*2-1:0]      read_in,
    output wire [SCORE_WIDTH-1:0]     global_peak_score,
    output wire [15:0]                global_peak_pos,
    output wire [READ_BPS*2-1:0]      global_peak_codeword
);

// Wires for connecting to NUM_LC LCs
wire [NUM_LC-1:0]         corr_done_vec;
wire [SCORE_WIDTH-1:0]    local_peak_score_vec [NUM_LC-1:0];
wire [POS_WIDTH-1:0]      local_peak_pos_vec [NUM_LC-1:0];
wire [READ_BPS*2-1:0]     local_peak_codeword_vec [NUM_LC-1:0];
wire [NUM_LC-1:0]         bram_write_en_vec;
reg engine_active;

// 1. Instantiate NUM_LC Local Correlators
genvar i;
generate
    for (i = 0; i < NUM_LC; i = i + 1) begin : lc_inst_gen
        assign bram_write_en_vec[i] = bram_write_en && (bram_sel == i);
        local_correlator #(
            .WATERMARK_SEGMENT_BPS  (WATERMARK_SEGMENT_BPS),
            .READ_BPS               (READ_BPS),
            .SCORE_WIDTH            (SCORE_WIDTH),
            .POS_WIDTH              (POS_WIDTH),
            .STRIDE                 (STRIDE)
        ) lc_inst (
            .clk                    (clk),
            .rst_n                  (rst_n),
            .start_corr             (start_engine),
            .bram_write_en          (bram_write_en_vec[i]),
            .bram_write_addr        (bram_write_addr),
            .bram_write_data        (bram_write_data),
            .corr_done              (corr_done_vec[i]),
            .read_in                (read_in),
            .local_peak_score       (local_peak_score_vec[i]),
            .local_peak_pos         (local_peak_pos_vec[i]),
            .local_peak_codeword    (local_peak_codeword_vec[i])
        );
    end
endgenerate

// Engine done logic
always @(posedge clk) begin
    if (!rst_n) begin
        engine_done <= 1'b0;
        engine_active <= 1'b0;
    end else begin
        if (start_engine) begin
            engine_active <= 1'b1;
            engine_done <= 1'b0;
        end else if (engine_active && (&corr_done_vec)) begin
            engine_done <= 1'b1;
            engine_active <= 1'b0;
        end else if (!start_engine) begin
            engine_done <= 1'b0;
        end
    end
end

// 2. Global Peak Finder - Pipelined
localparam NUM_STAGE1 = (NUM_LC + 1) / 2; // 24
// Use reg arrays for stage aggregation
reg [SCORE_WIDTH-1:0]     stage1_scores [NUM_STAGE1-1:0];
reg [5:0]                 stage1_indices [NUM_STAGE1-1:0];
reg [READ_BPS*2-1:0]      stage1_codewords [NUM_STAGE1-1:0];
reg [POS_WIDTH-1:0]       stage1_positions [NUM_STAGE1-1:0];

// Pipeline registers for stage 1
reg [SCORE_WIDTH-1:0]     stage1_scores_reg [NUM_STAGE1-1:0];
reg [5:0]                 stage1_indices_reg [NUM_STAGE1-1:0];
reg [READ_BPS*2-1:0]      stage1_codewords_reg [NUM_STAGE1-1:0];
reg [POS_WIDTH-1:0]       stage1_positions_reg [NUM_STAGE1-1:0];

localparam NUM_STAGE2 = (NUM_STAGE1 + 1) / 2; // 12
reg [SCORE_WIDTH-1:0]     stage2_scores [NUM_STAGE2-1:0];
reg [5:0]                 stage2_indices [NUM_STAGE2-1:0];
reg [READ_BPS*2-1:0]      stage2_codewords [NUM_STAGE2-1:0];
reg [POS_WIDTH-1:0]       stage2_positions [NUM_STAGE2-1:0];

// Pipeline registers for stage 2
reg [SCORE_WIDTH-1:0]     stage2_scores_reg [NUM_STAGE2-1:0];
reg [5:0]                 stage2_indices_reg [NUM_STAGE2-1:0];
reg [READ_BPS*2-1:0]      stage2_codewords_reg [NUM_STAGE2-1:0];
reg [POS_WIDTH-1:0]       stage2_positions_reg [NUM_STAGE2-1:0];

reg [SCORE_WIDTH-1:0]     final_score;
reg [5:0]                 final_index;
reg [READ_BPS*2-1:0]      final_codeword;
reg [POS_WIDTH-1:0]       final_local_pos;

// Stage 1 comparisons (Combinational)
integer k;
always @(*) begin
    for (k = 0; k < NUM_STAGE1; k = k + 1) begin
        if (k*2 + 1 < NUM_LC) begin
            if (local_peak_score_vec[k*2] >= local_peak_score_vec[k*2 + 1]) begin
                stage1_scores[k] = local_peak_score_vec[k*2];
                stage1_indices[k] = k*2;
                stage1_codewords[k] = local_peak_codeword_vec[k*2];
                stage1_positions[k] = local_peak_pos_vec[k*2];
            end else begin
                stage1_scores[k] = local_peak_score_vec[k*2 + 1];
                stage1_indices[k] = k*2 + 1;
                stage1_codewords[k] = local_peak_codeword_vec[k*2 + 1];
                stage1_positions[k] = local_peak_pos_vec[k*2 + 1];
            end
        end else begin
            stage1_scores[k] = local_peak_score_vec[k*2];
            stage1_indices[k] = k*2;
            stage1_codewords[k] = local_peak_codeword_vec[k*2];
            stage1_positions[k] = local_peak_pos_vec[k*2];
        end
    end
end

// Stage 2 comparisons (Combinational, using registered inputs)
integer m;
always @(*) begin
    for (m = 0; m < NUM_STAGE2; m = m + 1) begin
        if (m*2 + 1 < NUM_STAGE1) begin
            if (stage1_scores_reg[m*2] >= stage1_scores_reg[m*2 + 1]) begin
                stage2_scores[m] = stage1_scores_reg[m*2];
                stage2_indices[m] = stage1_indices_reg[m*2];
                stage2_codewords[m] = stage1_codewords_reg[m*2];
                stage2_positions[m] = stage1_positions_reg[m*2];
            end else begin
                stage2_scores[m] = stage1_scores_reg[m*2 + 1];
                stage2_indices[m] = stage1_indices_reg[m*2 + 1];
                stage2_codewords[m] = stage1_codewords_reg[m*2 + 1];
                stage2_positions[m] = stage1_positions_reg[m*2 + 1];
            end
        end else begin
            stage2_scores[m] = stage1_scores_reg[m*2];
            stage2_indices[m] = stage1_indices_reg[m*2];
            stage2_codewords[m] = stage1_codewords_reg[m*2];
            stage2_positions[m] = stage1_positions_reg[m*2];
        end
    end
end

// Final stage - find maximum (Combinational, using registered inputs)
integer n;
always @(*) begin
    final_score = stage2_scores_reg[0];
    final_index = stage2_indices_reg[0];
    final_codeword = stage2_codewords_reg[0];
    final_local_pos = stage2_positions_reg[0];
    for (n = 1; n < NUM_STAGE2; n = n + 1) begin
        if (stage2_scores_reg[n] > final_score) begin
            final_score = stage2_scores_reg[n];
            final_index = stage2_indices_reg[n];
            final_codeword = stage2_codewords_reg[n];
            final_local_pos = stage2_positions_reg[n];
        end
    end
end

// Pipeline register updates
integer p, q;
always @(posedge clk) begin
    if(!rst_n) begin
        for (p = 0; p < NUM_STAGE1; p = p + 1) begin
            stage1_scores_reg[p]    <= 0;
            stage1_indices_reg[p]   <= 0;
            stage1_codewords_reg[p] <= 0;
            stage1_positions_reg[p] <= 0;
        end
        for (q = 0; q < NUM_STAGE2; q = q + 1) begin
            stage2_scores_reg[q]    <= 0;
            stage2_indices_reg[q]   <= 0;
            stage2_codewords_reg[q] <= 0;
            stage2_positions_reg[q] <= 0;
        end
    end else begin
        for (p = 0; p < NUM_STAGE1; p = p + 1) begin
            stage1_scores_reg[p]    <= stage1_scores[p];
            stage1_indices_reg[p]   <= stage1_indices[p];
            stage1_codewords_reg[p] <= stage1_codewords[p];
            stage1_positions_reg[p] <= stage1_positions[p];
        end
        for (q = 0; q < NUM_STAGE2; q = q + 1) begin
            stage2_scores_reg[q]    <= stage2_scores[q];
            stage2_indices_reg[q]   <= stage2_indices[q];
            stage2_codewords_reg[q] <= stage2_codewords[q];
            stage2_positions_reg[q] <= stage2_positions[q];
        end
    end
end

// Output assignment
(* use_dsp = "yes" *) reg [15:0] global_position_calc;
always @(posedge clk) begin
    if (!rst_n) begin
        global_position_calc <= 0;
    end else begin
        global_position_calc <= (final_index * STRIDE) + final_local_pos;
    end
end

reg [SCORE_WIDTH-1:0]     global_peak_score_reg;
reg [15:0]                global_peak_pos_reg;
reg [READ_BPS*2-1:0]      global_peak_codeword_reg;

always @(posedge clk) begin
    if (!rst_n) begin
        global_peak_score_reg <= 0;
        global_peak_pos_reg <= 0;
        global_peak_codeword_reg <= 0;
    end else begin
        global_peak_score_reg <= final_score;
        global_peak_pos_reg <= global_position_calc;
        global_peak_codeword_reg <= final_codeword;
    end
end

assign global_peak_score = global_peak_score_reg;
assign global_peak_pos = global_peak_pos_reg;
assign global_peak_codeword = global_peak_codeword_reg;

endmodule
