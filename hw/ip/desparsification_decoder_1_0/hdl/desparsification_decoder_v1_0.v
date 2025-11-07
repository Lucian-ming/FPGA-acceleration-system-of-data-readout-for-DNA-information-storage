// ================================================================
// File   : desparsification_decoder_v1_0.v (FIXED VERSION)
// Desc   : 5b->4b ????¨€?-?è§?? ????è?"?…? 81,000 bit (1266?-64b) ??' è?"??? 64,800 B (1013?-64b)
// Notes  : è??????…? + è?????è§?è€?
// ??… FIXES APPLIED:
//   (1) ?? é?¤????????'é?????1???é????? - ?…?è????€?¤§256????????'
//   (2) ?????€out_pool?????????96???
//   (3) ??????è§?? ?é€?è?'???????‰??±?
//   (4) ??????WLAST?????·?-????
//   (5) ?????-????€????è???????????
// ================================================================
`timescale 1 ns / 1 ps

module desparsification_decoder_v1_0 #
(
    parameter integer C_S00_AXI_DATA_WIDTH    = 32,
    parameter integer C_S00_AXI_ADDR_WIDTH    = 6,
    parameter integer C_M00_AXI_DATA_WIDTH    = 64,
    parameter integer C_M00_AXI_ADDR_WIDTH    = 32,
    parameter integer MAX_BURST_LEN           = 256
)
(
    // ---------------- AXI-Lite (Control) ----------------
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

    // ---------------- AXI4 Master (MM) ----------------
    input  wire                               M00_AXI_ACLK,
    input  wire                               M00_AXI_ARESETN,

    // AW
    output wire [C_M00_AXI_ADDR_WIDTH-1:0]    M00_AXI_AWADDR,
    output wire [7:0]                         M00_AXI_AWLEN,
    output wire [2:0]                         M00_AXI_AWSIZE,
    output wire [1:0]                         M00_AXI_AWBURST,
    output wire [0:0]                         M00_AXI_AWLOCK,
    output wire [3:0]                         M00_AXI_AWCACHE,
    output wire [2:0]                         M00_AXI_AWPROT,
    output wire [3:0]                         M00_AXI_AWQOS,
    output wire                               M00_AXI_AWVALID,
    input  wire                               M00_AXI_AWREADY,

    // W
    output wire [C_M00_AXI_DATA_WIDTH-1:0]    M00_AXI_WDATA,
    output wire [C_M00_AXI_DATA_WIDTH/8-1:0]  M00_AXI_WSTRB,
    output wire                               M00_AXI_WLAST,
    output wire                               M00_AXI_WVALID,
    input  wire                               M00_AXI_WREADY,

    // B
    input  wire [1:0]                         M00_AXI_BRESP,
    input  wire                               M00_AXI_BVALID,
    output wire                               M00_AXI_BREADY,

    // AR
    output wire [C_M00_AXI_ADDR_WIDTH-1:0]    M00_AXI_ARADDR,
    output wire [7:0]                         M00_AXI_ARLEN,
    output wire [2:0]                         M00_AXI_ARSIZE,
    output wire [1:0]                         M00_AXI_ARBURST,
    output wire [0:0]                         M00_AXI_ARLOCK,
    output wire [3:0]                         M00_AXI_ARCACHE,
    output wire [2:0]                         M00_AXI_ARPROT,
    output wire [3:0]                         M00_AXI_ARQOS,
    output wire                               M00_AXI_ARVALID,
    input  wire                               M00_AXI_ARREADY,

    // R
    input  wire [C_M00_AXI_DATA_WIDTH-1:0]    M00_AXI_RDATA,
    input  wire [1:0]                         M00_AXI_RRESP,
    input  wire                               M00_AXI_RLAST,
    input  wire                               M00_AXI_RVALID,
    output wire                               M00_AXI_RREADY
);

    // ---------------- AXI-Lite ?? ?°? ----------------
    wire [31:0] in_addr_s, out_addr_s;
    wire [31:0] in_beats_s, out_beats_s;
    wire        start_pulse_s, done_clr_s;
    reg         done_s, idle_s;

    axi_slave_decoder #(
        .C_S_AXI_DATA_WIDTH(C_S00_AXI_DATA_WIDTH),
        .C_S_AXI_ADDR_WIDTH(C_S00_AXI_ADDR_WIDTH)
    ) u_axil (
        .S_AXI_ACLK   (S00_AXI_ACLK),
        .S_AXI_ARESETN(S00_AXI_ARESETN),
        .S_AXI_AWADDR (S00_AXI_AWADDR),
        .S_AXI_AWVALID(S00_AXI_AWVALID),
        .S_AXI_AWREADY(S00_AXI_AWREADY),
        .S_AXI_WDATA  (S00_AXI_WDATA),
        .S_AXI_WSTRB  (S00_AXI_WSTRB),
        .S_AXI_WVALID (S00_AXI_WVALID),
        .S_AXI_WREADY (S00_AXI_WREADY),
        .S_AXI_BRESP  (S00_AXI_BRESP),
        .S_AXI_BVALID (S00_AXI_BVALID),
        .S_AXI_BREADY (S00_AXI_BREADY),
        .S_AXI_ARADDR (S00_AXI_ARADDR),
        .S_AXI_ARVALID(S00_AXI_ARVALID),
        .S_AXI_ARREADY(S00_AXI_ARREADY),
        .S_AXI_RDATA  (S00_AXI_RDATA),
        .S_AXI_RRESP  (S00_AXI_RRESP),
        .S_AXI_RVALID (S00_AXI_RVALID),
        .S_AXI_RREADY (S00_AXI_RREADY),
        .in_addr      (in_addr_s),
        .in_beats     (in_beats_s),
        .out_addr     (out_addr_s),
        .out_beats    (out_beats_s),
        .start_pulse  (start_pulse_s),
        .done_clr     (done_clr_s),
        .done         (done_s),
        .idle         (idle_s)
    );

    // ---------------- è·¨?-?é'?????????? ----------------
    reg [31:0] in_addr, out_addr, in_beats, out_beats;
    always @(posedge M00_AXI_ACLK) begin
        if (!M00_AXI_ARESETN) begin
            in_addr   <= 32'd0;
            out_addr  <= 32'd0;
            in_beats  <= 32'd0;
            out_beats <= 32'd0;
        end else begin
            in_addr   <= in_addr_s;
            out_addr  <= out_addr_s;
            in_beats  <= in_beats_s;
            out_beats <= out_beats_s;
        end
    end

    // START è?‰?????????
    reg s1_m, s2_m, s3_m;
    always @(posedge M00_AXI_ACLK) {s1_m, s2_m, s3_m} <= {start_pulse_s, s1_m, s2_m};
    wire start_latched_pulse = s2_m & ~s3_m;

    reg done_p_m;

    // ---------------- ???????€???? ----------------
    localparam S_IDLE  = 3'd0,
               S_ADDR  = 3'd1,
               S_STREAM= 3'd2,
               S_FLUSH = 3'd3,
               S_WAITB = 3'd4;

    reg [2:0] state, nstate;
    always @(posedge M00_AXI_ACLK) begin
        if (!M00_AXI_ARESETN) state <= S_IDLE;
        else                   state <= nstate;
    end

    // è????°/??°??€/?????'é?????
    reg [31:0] r_beats_left, w_beats_left;
    reg [31:0] r_cnt_total,  w_cnt_total;
    reg [31:0] r_cnt_burst,  w_cnt_burst;
    reg [C_M00_AXI_ADDR_WIDTH-1:0] ar_addr_reg, aw_addr_reg;

    // ?????'é?????è????-
    function [8:0] beats_to_4k;
        input [C_M00_AXI_ADDR_WIDTH-1:0] addr;
        reg [11:0] off4k;
        reg [12:0] bytes_left;
        reg [8:0]  beats_calc;
        begin
            off4k      = addr[11:0];
            bytes_left = 13'd4096 - {1'b0, off4k};
            beats_calc = bytes_left[12:3];
            if (beats_calc > MAX_BURST_LEN) beats_to_4k = MAX_BURST_LEN[8:0];
            else if (beats_calc == 0)       beats_to_4k = 9'd1;
            else                            beats_to_4k = beats_calc;
        end
    endfunction

    reg [8:0] max_ar_4k_reg, max_aw_4k_reg;
    always @(posedge M00_AXI_ACLK) begin
        if (!M00_AXI_ARESETN) begin
            max_ar_4k_reg <= 9'd0;
            max_aw_4k_reg <= 9'd0;
        end else begin
            max_ar_4k_reg <= beats_to_4k(ar_addr_reg);
            max_aw_4k_reg <= beats_to_4k(aw_addr_reg);
        end
    end
    wire [8:0] max_ar_4k_eff = (max_ar_4k_reg != 9'd0) ? max_ar_4k_reg : beats_to_4k(ar_addr_reg);
    wire [8:0] max_aw_4k_eff = (max_aw_4k_reg != 9'd0) ? max_aw_4k_reg : beats_to_4k(aw_addr_reg);

    wire [31:0] ar_c1 = (r_beats_left < MAX_BURST_LEN) ? r_beats_left : MAX_BURST_LEN;
    wire [31:0] aw_c1 = (w_beats_left < MAX_BURST_LEN) ? w_beats_left : MAX_BURST_LEN;
    
    wire [31:0] cur_arlen_w = (r_beats_left==0) ? 32'd0
                         : ((max_ar_4k_eff!=0 && ar_c1>max_ar_4k_eff) ? {23'd0,max_ar_4k_eff} : ar_c1);
    wire [31:0] cur_awlen_w_pre = (w_beats_left==0) ? 32'd0
                         : ((max_aw_4k_eff!=0 && aw_c1>max_aw_4k_eff) ? {23'd0,max_aw_4k_eff} : aw_c1);
    
    // ??… FIX #1: ?? é?¤????????'é?????é????? - ?…?è????€?¤§256????????'
    wire [31:0] cur_awlen_w = cur_awlen_w_pre;

    // ??… FIX #2: ?????€???????????‰ - out_pool???96???
    reg  [127:0] in_pool;
    reg  [95:0]  out_pool;
    reg  [7:0]   in_bits;
    reg  [6:0]   out_bits;

    // è??????????°
    function [31:0] conv40_32;
        input [39:0] x;
        integer k;
        reg [3:0] r [0:7];
        reg [39:0] grp;
        begin
            for (k=0; k<8; k=k+1) begin
                grp = x[(5*k)+:5];
                if (grp[4]) r[k] = ~grp[3:0];
                else        r[k] =  grp[3:0];
            end
            conv40_32 = {r[7],r[6],r[5],r[4],r[3],r[2],r[1],r[0]};
        end
    endfunction

    // ????¨???§???
    reg ar_done_r, aw_done_r;
    reg read_complete;
    reg [31:0] cur_awlen_active;
    reg [31:0] stream_cycle_count, flush_cycle_count;

    wire read_starvation  = (r_beats_left != 0) && (in_bits < 8'd64);
    wire can_write        = (out_bits >= 7'd64);
    wire write_blockage   = (can_write && ~M00_AXI_WREADY);

    // ---------------- ?-????è???¨? ----------------
    always @(posedge M00_AXI_ACLK) begin
        if (!M00_AXI_ARESETN) begin
            in_pool <= 128'd0; out_pool <= 96'd0;
            in_bits <= 8'd0;   out_bits <= 7'd0;
            r_beats_left <= 32'd0; w_beats_left <= 32'd0;
            r_cnt_total  <= 32'd0; w_cnt_total  <= 32'd0;
            r_cnt_burst  <= 32'd0; w_cnt_burst  <= 32'd0;
            ar_addr_reg  <= {C_M00_AXI_ADDR_WIDTH{1'b0}};
            aw_addr_reg  <= {C_M00_AXI_ADDR_WIDTH{1'b0}};
            ar_done_r <= 1'b1; aw_done_r <= 1'b1;
            read_complete <= 1'b0;
            cur_awlen_active <= 32'd0;
            stream_cycle_count <= 32'd0; flush_cycle_count <= 32'd0;
            done_p_m <= 1'b0;
        end else begin
            done_p_m <= 1'b0;

            // ??'??? AR
            if ((state==S_ADDR) && ~ar_done_r && (cur_arlen_w!=0) && M00_AXI_ARVALID && M00_AXI_ARREADY) begin
                r_cnt_burst   <= 32'd0;
                read_complete <= 1'b0;
                ar_done_r     <= 1'b1;
            end

            // ??'??? AW
            if ((state==S_ADDR) && ~aw_done_r && (cur_awlen_w!=0) && M00_AXI_AWVALID && M00_AXI_AWREADY) begin
                w_cnt_burst       <= 32'd0;
                cur_awlen_active  <= cur_awlen_w;
                aw_done_r         <= 1'b1;
            end

            // è????°???
            if (M00_AXI_RVALID && M00_AXI_RREADY) begin
                in_pool <= {in_pool[63:0], M00_AXI_RDATA};
                in_bits <= in_bits + 8'd64;
                r_cnt_total <= r_cnt_total + 1;
                r_cnt_burst <= r_cnt_burst + 1;
                if (M00_AXI_RLAST) read_complete <= 1'b1;
            end

            // ??… FIX #3: ??????è§?? ?é€?è?' - ???????¤????96???out_pool
            if (in_bits >= 8'd40 && out_bits <= 7'd64) begin
                out_pool <= out_pool | ({64'd0, conv40_32(in_pool[39:0])} << out_bits);
                in_pool  <= {40'd0, in_pool[127:40]};
                in_bits  <= in_bits - 8'd40;
                out_bits <= out_bits + 7'd32;
            end

            // ?????°???
            if (can_write && M00_AXI_WREADY && ((state==S_STREAM)||(state==S_FLUSH))) begin
                out_pool   <= out_pool >> 64;
                out_bits   <= out_bits - 7'd64;
                w_cnt_total<= w_cnt_total + 1;
                w_cnt_burst<= w_cnt_burst + 1;
            end

            // è?…?-?è????°
            if (state == S_STREAM) stream_cycle_count <= stream_cycle_count + 1; else stream_cycle_count <= 0;
            if (state == S_FLUSH)  flush_cycle_count  <= flush_cycle_count + 1;  else flush_cycle_count  <= 0;

            // B ?"???"
            if (M00_AXI_BVALID && M00_AXI_BREADY) begin
                if (w_cnt_total >= out_beats && r_cnt_total >= in_beats) begin
                    done_p_m <= 1'b1;
                end
                if (w_cnt_total < out_beats) aw_done_r <= 1'b0;
                if (r_cnt_total < in_beats)  ar_done_r <= 1'b0;
            end

            // ?????° S_ADDR ?‰?????¤?
            if (state == S_STREAM && nstate == S_ADDR) begin
                if (r_beats_left > 0 && read_starvation) ar_done_r <= 1'b0;
                if (w_beats_left > 0 && (out_bits >= 7'd64 || (out_bits > 0 && r_beats_left==0)))
                    aw_done_r <= 1'b0;
            end

            // START
            if (start_latched_pulse && in_beats!=0 && out_beats!=0) begin
                r_beats_left <= in_beats;
                w_beats_left <= out_beats;
                ar_addr_reg  <= {in_addr [C_M00_AXI_ADDR_WIDTH-1:3], 3'b000};
                aw_addr_reg  <= {out_addr[C_M00_AXI_ADDR_WIDTH-1:3], 3'b000};
                ar_done_r    <= 1'b0;
                aw_done_r    <= 1'b0;
                read_complete<= 1'b0;
                r_cnt_total  <= 32'd0;
                w_cnt_total  <= 32'd0;
                in_pool      <= 128'd0;  out_pool <= 96'd0;
                in_bits      <= 8'd0;    out_bits <= 7'd0;
                cur_awlen_active <= 32'd0;
            end

            // ??°??€??¨è??
            if ((state==S_ADDR) && M00_AXI_ARVALID && M00_AXI_ARREADY && cur_arlen_w!=0) begin
                r_beats_left <= r_beats_left - cur_arlen_w;
                ar_addr_reg  <= ar_addr_reg + (cur_arlen_w << 3);
            end
            if ((state==S_ADDR) && M00_AXI_AWVALID && M00_AXI_AWREADY && cur_awlen_w!=0) begin
                w_beats_left <= w_beats_left - cur_awlen_w;
                aw_addr_reg  <= aw_addr_reg + (cur_awlen_w << 3);
            end
        end
    end

    // ---------------- ????€?é€?è?' ----------------
    localparam integer STREAM_TIMEOUT = 32'd200000;
    localparam integer FLUSH_TIMEOUT  = 32'd200000;

    always @* begin
        nstate = state;
        case (state)
            S_IDLE  : if (start_latched_pulse && in_beats!=0 && out_beats!=0) nstate = S_ADDR;
            S_ADDR  : if ((ar_done_r || cur_arlen_w==0) && (aw_done_r || cur_awlen_w==0)) nstate = S_STREAM;
            // ??… FIX #5: ?????-????€????è???????????
            S_STREAM: begin
                if (cur_awlen_active!=0 && w_cnt_burst >= cur_awlen_active) nstate = S_WAITB;
                else if ((out_bits < 7'd64) && (w_beats_left == 0) && (r_beats_left == 0)) nstate = S_WAITB;
                else if (read_starvation && ~write_blockage && r_beats_left > 0) nstate = S_ADDR;
                else if (read_complete && r_cnt_total >= in_beats && in_bits < 8'd40 && out_bits < 7'd64 && w_cnt_total > 32'd0) nstate = S_FLUSH;
                else if (stream_cycle_count >= STREAM_TIMEOUT && w_cnt_total > 32'd0) nstate = S_FLUSH;
            end
            S_FLUSH: if (flush_cycle_count >= FLUSH_TIMEOUT || (out_bits < 7'd64 && in_bits < 8'd40 && r_beats_left == 0) || (w_cnt_total == 0 && stream_cycle_count > 32'd10000))
                         nstate = S_WAITB;
            S_WAITB: if (M00_AXI_BVALID)
                         nstate = (w_cnt_total < out_beats || r_cnt_total < in_beats) ? S_ADDR : S_IDLE;
            default: nstate = S_IDLE;
        endcase
    end

    // ---------------- AXI ??§????????· ----------------
    localparam integer DW = C_M00_AXI_DATA_WIDTH;
    assign M00_AXI_AWADDR  = aw_addr_reg;
    assign M00_AXI_ARADDR  = ar_addr_reg;
    assign M00_AXI_AWBURST = 2'b01;
    assign M00_AXI_ARBURST = 2'b01;
    assign M00_AXI_AWSIZE  = (DW==64)?3'b011:3'b010;
    assign M00_AXI_ARSIZE  = (DW==64)?3'b011:3'b010;
    assign M00_AXI_AWLOCK  = 1'b0;
    assign M00_AXI_ARLOCK  = 1'b0;
    assign M00_AXI_AWCACHE = 4'b0010;
    assign M00_AXI_ARCACHE = 4'b0010;
    assign M00_AXI_AWPROT  = 3'b000;
    assign M00_AXI_ARPROT  = 3'b000;
    assign M00_AXI_AWQOS   = 4'b0000;
    assign M00_AXI_ARQOS   = 4'b0000;

    assign M00_AXI_AWVALID = (state==S_ADDR) && (cur_awlen_w!=0) && ~aw_done_r;
    assign M00_AXI_ARVALID = (state==S_ADDR) && (cur_arlen_w!=0) && ~ar_done_r;
    assign M00_AXI_AWLEN   = (cur_awlen_w==0) ? 8'd0 : (cur_awlen_w[7:0] - 8'd1);
    assign M00_AXI_ARLEN   = (cur_arlen_w==0) ? 8'd0 : (cur_arlen_w[7:0] - 8'd1);

    assign M00_AXI_RREADY  = ((state==S_ADDR) || (state==S_STREAM)) &&
                             (r_cnt_total < in_beats) &&
                             (in_bits <= 8'd64);

    assign M00_AXI_WDATA   = out_pool[63:0];
    wire is_last_beat = (w_cnt_total == (out_beats - 32'd1));
    assign M00_AXI_WSTRB  = is_last_beat ? 8'h0F : 8'hFF;

    assign M00_AXI_WVALID = ((state==S_STREAM)||(state==S_FLUSH)) && can_write;
    
    // ??… FIX #4: ??????WLAST?????·?-????
    // FIX #4+#6: 修正WLAST信号，添加cur_awlen_active安全检查
    assign M00_AXI_WLAST  = ((state==S_STREAM)||(state==S_FLUSH)) && can_write && (cur_awlen_active != 32'd0) && (w_cnt_burst == (cur_awlen_active - 32'd1));

    assign M00_AXI_BREADY = 1'b1;

    // ---------------- idle/done ?????? ----------------
    reg idle_m;
    always @(posedge M00_AXI_ACLK) begin
        if (!M00_AXI_ARESETN) idle_m <= 1'b1;
        else                  idle_m <= (state==S_IDLE);
    end

    reg idle_sync1_s, idle_sync2_s;
    reg d1_s, d2_s, d3_s;
    always @(posedge S00_AXI_ACLK) begin
        if (!S00_AXI_ARESETN) begin
            idle_sync1_s <= 1'b1;
            idle_sync2_s <= 1'b1;
            idle_s       <= 1'b1;
            done_s       <= 1'b0;
            {d1_s, d2_s, d3_s} <= 3'b000;
        end else begin
            idle_sync1_s <= idle_m;
            idle_sync2_s <= idle_sync1_s;
            idle_s       <= idle_sync2_s;

            {d1_s, d2_s, d3_s} <= {done_p_m, d1_s, d2_s};
            if (done_clr_s)        done_s <= 1'b0;
            else if (d2_s & ~d3_s) done_s <= 1'b1;
        end
    end

endmodule

// ================================================================
// AXI-Lite Slave
// ================================================================
module axi_slave_decoder #
(
    parameter C_S_AXI_DATA_WIDTH = 32,
    parameter C_S_AXI_ADDR_WIDTH = 6
)
(
    input  wire                             S_AXI_ACLK,
    input  wire                             S_AXI_ARESETN,
    input  wire [C_S_AXI_ADDR_WIDTH-1:0]    S_AXI_AWADDR,
    input  wire                             S_AXI_AWVALID,
    output reg                              S_AXI_AWREADY,
    input  wire [C_S_AXI_DATA_WIDTH-1:0]    S_AXI_WDATA,
    input  wire [C_S_AXI_DATA_WIDTH/8-1:0]  S_AXI_WSTRB,
    input  wire                             S_AXI_WVALID,
    output reg                              S_AXI_WREADY,
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

    output reg  [31:0]                      in_addr,
    output reg  [31:0]                      in_beats,
    output reg  [31:0]                      out_addr,
    output reg  [31:0]                      out_beats,
    output reg                               start_pulse,
    output reg                               done_clr,
    input  wire                               done,
    input  wire                               idle
);
    wire [3:0] waddr = S_AXI_AWADDR[5:2];
    wire [3:0] raddr = S_AXI_ARADDR[5:2];

    // ???é€?é?"
    always @(posedge S_AXI_ACLK) begin
        if (!S_AXI_ARESETN) begin
            S_AXI_AWREADY <= 1'b0;
            S_AXI_WREADY  <= 1'b0;
            S_AXI_BVALID  <= 1'b0;
            S_AXI_BRESP   <= 2'b00;
            in_addr <= 32'd0; in_beats <= 32'd0; out_addr <= 32'd0; out_beats <= 32'd0;
            start_pulse <= 1'b0; done_clr <= 1'b0;
        end else begin
            start_pulse <= 1'b0;
            done_clr    <= 1'b0;

            if (~S_AXI_AWREADY && S_AXI_AWVALID) S_AXI_AWREADY <= 1'b1;
            else                                 S_AXI_AWREADY <= 1'b0;

            if (~S_AXI_WREADY && S_AXI_WVALID)   S_AXI_WREADY  <= 1'b1;
            else                                 S_AXI_WREADY  <= 1'b0;

            if ((~S_AXI_BVALID) && S_AXI_AWREADY && S_AXI_AWVALID && S_AXI_WREADY && S_AXI_WVALID) begin
                case (waddr)
                    4'd0: in_addr   <= S_AXI_WDATA;
                    4'd1: in_beats  <= S_AXI_WDATA;
                    4'd2: out_addr  <= S_AXI_WDATA;
                    4'd3: out_beats <= S_AXI_WDATA;
                    4'd4: start_pulse <= 1'b1;
                    default: ;
                endcase
                S_AXI_BVALID <= 1'b1;
                S_AXI_BRESP  <= 2'b00;
            end else if (S_AXI_BVALID && S_AXI_BREADY) begin
                S_AXI_BVALID <= 1'b0;
            end
        end
    end

    // è??é€?é?"
    always @(posedge S_AXI_ACLK) begin
        if (!S_AXI_ARESETN) begin
            S_AXI_ARREADY<=1'b0; S_AXI_RVALID<=1'b0; S_AXI_RRESP<=2'b00; S_AXI_RDATA<=32'd0;
        end else begin
            if (~S_AXI_ARREADY && S_AXI_ARVALID) S_AXI_ARREADY <= 1'b1;
            else                                  S_AXI_ARREADY <= 1'b0;

            if (S_AXI_ARREADY && S_AXI_ARVALID && ~S_AXI_RVALID) begin
                S_AXI_RVALID <= 1'b1;
                case (raddr)
                    4'd0: S_AXI_RDATA <= in_addr;
                    4'd1: S_AXI_RDATA <= in_beats;
                    4'd2: S_AXI_RDATA <= out_addr;
                    4'd3: S_AXI_RDATA <= out_beats;
                    4'd6: S_AXI_RDATA <= {30'd0, done, idle};
                    default: S_AXI_RDATA <= 32'd0;
                endcase
                S_AXI_RRESP <= 2'b00;
            end else if (S_AXI_RVALID && S_AXI_RREADY) begin
                S_AXI_RVALID <= 1'b0;
            end
        end
    end
endmodule