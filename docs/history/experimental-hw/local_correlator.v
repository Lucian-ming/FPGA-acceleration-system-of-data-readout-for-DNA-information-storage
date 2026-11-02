// Filename: local_correlator.v
// FIXED & UPGRADED: Added base-level two-plane correlation
// Each DNA base (2-bit) is now split into two separate bit planes (first bit, second bit)
// and correlated independently, then summed to produce the total match score.
// Other FSM, interfaces, and pipeline logic remain unchanged.

`timescale 1ns / 1ps

module local_correlator #(
    parameter integer WATERMARK_SEGMENT_BPS   = 1000,
    parameter integer READ_BPS                = 150,
    parameter integer SCORE_WIDTH             = 9,
    parameter integer POS_WIDTH               = 10,
    parameter integer STRIDE                  = 850
)(
    input  wire                       clk,
    input  wire                       rst_n,
    input  wire                       start_corr,
    input  wire                       bram_write_en,
    input  wire [POS_WIDTH-1:0]       bram_write_addr,
    input  wire [1:0]                 bram_write_data,
    output reg                        corr_done,
    input  wire [READ_BPS*2-1:0]      read_in,
    output reg [SCORE_WIDTH-1:0]      local_peak_score,
    output reg [POS_WIDTH-1:0]        local_peak_pos,
    output reg [READ_BPS*2-1:0]       local_peak_codeword
);

// FSM states
localparam IDLE    = 2'b00;
localparam PRELOAD = 2'b01;
localparam CORR    = 2'b10;
reg [1:0] state, next_state;

// Internal BRAM & Registers
reg [1:0] watermark_bram [0:WATERMARK_SEGMENT_BPS-1];
reg [READ_BPS*2-1:0]      read_buffer;
reg [POS_WIDTH-1:0]       corr_pos_counter;
reg [POS_WIDTH-1:0]       preload_counter;
reg [READ_BPS*2-1:0]      watermark_window_sr;

// MODIFIED: Registers for pipelined score calculation
reg [2:0]                 calc_phase_counter;
reg [SCORE_WIDTH-1:0]     accumulated_score_reg;

// ====================
// ADDED: Two-Plane Base Separation Logic
// ====================
// Each base (2-bit) is split into plane0 (first bit) and plane1 (second bit)
wire [READ_BPS-1:0] read_plane0;
wire [READ_BPS-1:0] read_plane1;
wire [READ_BPS-1:0] watermark_plane0;
wire [READ_BPS-1:0] watermark_plane1;

genvar b;
generate
    for (b = 0; b < READ_BPS; b = b + 1) begin : plane_split
        assign read_plane0[b] = read_buffer[2*b];        // first bit
        assign read_plane1[b] = read_buffer[2*b + 1];    // second bit
        assign watermark_plane0[b] = watermark_window_sr[2*b];
        assign watermark_plane1[b] = watermark_window_sr[2*b + 1];
    end
endgenerate

// ====================
// NEW: Two-Plane Correlation
// ====================
// Separate XNOR match results per plane
wire [READ_BPS-1:0] xnor_plane0 = ~(read_plane0 ^ watermark_plane0);
wire [READ_BPS-1:0] xnor_plane1 = ~(read_plane1 ^ watermark_plane1);

// Independent popcounts per plane
integer i_p0, i_p1;
reg [SCORE_WIDTH-1:0] plane0_score;
reg [SCORE_WIDTH-1:0] plane1_score;
always @(*) begin
    plane0_score = 0;
    plane1_score = 0;
    for (i_p0 = 0; i_p0 < READ_BPS; i_p0 = i_p0 + 1)
        plane0_score = plane0_score + xnor_plane0[i_p0];
    for (i_p1 = 0; i_p1 < READ_BPS; i_p1 = i_p1 + 1)
        plane1_score = plane1_score + xnor_plane1[i_p1];
end

// Combine plane scores (sum both bit-planes)
wire [SCORE_WIDTH-1:0] combined_score = plane0_score + plane1_score;

// ====================
// FSM & Datapath Logic (mostly unchanged)
// ====================

// 1. BRAM Write Logic
always @(posedge clk) begin
    if (bram_write_en) begin
        watermark_bram[bram_write_addr] <= bram_write_data;
    end
end

// 2. Control FSM
always @(posedge clk) begin
    if (!rst_n) state <= IDLE;
    else        state <= next_state;
end

always @(*) begin
    next_state = state;
    case (state)
        IDLE:    if (start_corr) next_state = PRELOAD;
        PRELOAD: if (preload_counter == READ_BPS - 1) next_state = CORR;
        CORR:    if (corr_pos_counter == STRIDE && calc_phase_counter == 5) next_state = IDLE;
        default: next_state = IDLE;
    endcase
end

// 4. Peak Finding Pipeline registers
reg [SCORE_WIDTH-1:0]     score_pipe_d0, score_pipe_d1, score_pipe_d2;
reg [READ_BPS*2-1:0]      xor_pipe_d0, xor_pipe_d1, xor_pipe_d2;
reg [POS_WIDTH-1:0]       pos_pipe_d0, pos_pipe_d1, pos_pipe_d2;
// 3. Main Control and Register Logic
always @(posedge clk) begin
    if (!rst_n) begin
        corr_done <= 1'b0;
        corr_pos_counter <= 0;
        preload_counter <= 0;
        local_peak_score <= 0;
        local_peak_pos <= 0;
        local_peak_codeword <= 0;
        read_buffer <= 0;
        watermark_window_sr <= 0;
        calc_phase_counter <= 0;
        accumulated_score_reg <= 0;
    end else begin
        corr_done <= 1'b0;

        case(state)
            IDLE: begin
                preload_counter <= 0;
                corr_pos_counter <= 0;
                calc_phase_counter <= 0;
                if (start_corr) begin
                    read_buffer <= read_in;
                    local_peak_score <= 0;
                    local_peak_pos <= 0;
                    local_peak_codeword <= 0;
                end
            end
            PRELOAD: begin
                watermark_window_sr[preload_counter*2 +: 2] <= watermark_bram[preload_counter];
                preload_counter <= preload_counter + 1;
            end
            CORR: begin
                // Use combined_score instead of current_50bit_score
                accumulated_score_reg <= combined_score;
                
                if (calc_phase_counter == 5) begin
                    calc_phase_counter <= 0;
                    
                    score_pipe_d0 <= accumulated_score_reg;
                    pos_pipe_d0 <= corr_pos_counter;
                    xor_pipe_d0 <= read_buffer ^ watermark_window_sr;

                    if ((pos_pipe_d2 > 1) && (score_pipe_d2 > local_peak_score)) begin
                        local_peak_score  <= score_pipe_d2;
                        local_peak_pos    <= pos_pipe_d2;
                        local_peak_codeword <= xor_pipe_d2;
                    end

                    if (corr_pos_counter == STRIDE) begin
                        corr_done <= 1'b1;
                    end else begin
                        corr_pos_counter <= corr_pos_counter + 1;
                        watermark_window_sr <= {watermark_window_sr[READ_BPS*2-3:0],
                                                watermark_bram[corr_pos_counter + READ_BPS]};
                    end
                end else begin
                    calc_phase_counter <= calc_phase_counter + 1;
                end
            end
        endcase
    end
end



always @(posedge clk) begin
    if (!rst_n) begin
        score_pipe_d1 <= 0; score_pipe_d2 <= 0;
        xor_pipe_d1 <= 0;   xor_pipe_d2 <= 0;
        pos_pipe_d1 <= 0;   pos_pipe_d2 <= 0;
    end else begin
        pos_pipe_d1   <= pos_pipe_d0;
        xor_pipe_d1   <= xor_pipe_d0;
        score_pipe_d1 <= score_pipe_d0;
        
        pos_pipe_d2   <= pos_pipe_d1;
        xor_pipe_d2   <= xor_pipe_d1;
        score_pipe_d2 <= score_pipe_d1;
    end
end

endmodule
