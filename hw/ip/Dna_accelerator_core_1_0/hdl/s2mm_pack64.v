`timescale 1 ns / 1 ps
module s2mm_pack64 #(
    parameter integer R = 326
)(
    input  wire         clk,
    input  wire         rst_n,
    input  wire         din_vld,
    input  wire [R-1:0] din,
    output reg          m_vld,
    output reg [63:0]   m_dat,
    output reg          m_last,
    input  wire         m_rdy
);
    localparam [2:0] S_IDLE  = 3'd0,
                     S_PACK0 = 3'd1,
                     S_PACK1 = 3'd2,
                     S_PACK2 = 3'd3,
                     S_PACK3 = 3'd4,
                     S_PACK4 = 3'd5,
                     S_PACK5 = 3'd6;

    reg [2:0]   state, next_state;
    reg [R-1:0] lat;

    // ×´Ì¬¼Ä´æ
    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) state <= S_IDLE;
        else        state <= next_state;
    end

    // ÏÂÒ»×´Ì¬Âß¼­
    always @(*) begin
        next_state = state;
        case (state)
            S_IDLE:  if (din_vld) next_state = S_PACK0;
            S_PACK0: if (m_rdy)   next_state = S_PACK1;
            S_PACK1: if (m_rdy)   next_state = S_PACK2;
            S_PACK2: if (m_rdy)   next_state = S_PACK3;
            S_PACK3: if (m_rdy)   next_state = S_PACK4;
            S_PACK4: if (m_rdy)   next_state = S_PACK5;
            S_PACK5: if (m_rdy)   next_state = S_IDLE;
            default: next_state = S_IDLE;
        endcase
    end

    // Êä³öÓë»º´æ
    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            m_vld  <= 1'b0;
            m_last <= 1'b0;
            m_dat  <= 64'd0;
            lat    <= {R{1'b0}};
        end else begin
            m_vld  <= 1'b0;
            m_last <= 1'b0;

            case (state)
                S_IDLE: begin
                    if (din_vld) lat <= din;
                end

                S_PACK0: begin
                    if (m_rdy) begin
                        m_vld <= 1'b1;
                        m_dat <= lat[63:0];
                    end
                end

                S_PACK1: begin
                    if (m_rdy) begin
                        m_vld <= 1'b1;
                        m_dat <= lat[127:64];
                    end
                end

                S_PACK2: begin
                    if (m_rdy) begin
                        m_vld <= 1'b1;
                        m_dat <= lat[191:128];
                    end
                end

                S_PACK3: begin
                    if (m_rdy) begin
                        m_vld <= 1'b1;
                        m_dat <= lat[255:192];
                    end
                end

                S_PACK4: begin
                    if (m_rdy) begin
                        m_vld <= 1'b1;
                        m_dat <= lat[319:256];
                    end
                end

                S_PACK5: begin
                    if (m_rdy) begin
                        m_vld  <= 1'b1;
                        m_last <= 1'b1;
                        m_dat  <= {58'b0, lat[325:320]};
                    end
                end
            endcase
        end
    end
endmodule