// =============================================================
// File: dna_accelerator_core_4way.v
// Desc: DNA Accelerator top with 4-Way Pipelined Stage1 Comparison Engine
// Note: Integrates srpe_batch_4way with:
//       (1) cw_valid aligned with BRAM/FIFO 2-cycle read
//       (2) continuous batch processing with idle timeout
//       (3) TREADY backpressure handling without dropping beats
//       (4) 4-Way pipelined peak finder (1.93x speedup, 0 errors)
// Std : Verilog-2001
// =============================================================
`timescale 1 ns / 1 ps

module dna_accelerator_core_4way #(
    // ===== AXI-Lite =====
    parameter integer C_S_AXI_LITE_CTRL_DATA_WIDTH = 32,
    parameter integer C_S_AXI_LITE_CTRL_ADDR_WIDTH = 4,
    // ===== AXIS widths =====
    parameter integer C_S_AXIS_DATA_TDATA_WIDTH    = 32,
    parameter integer C_M_AXIS_RESULT_TDATA_WIDTH  = 64,
    // ===== Algorithm/Data params =====
    parameter integer READ_BPS  = 150,                     // bits per read (symbols*2)
    parameter integer CODEBITS  = READ_BPS*2,              // 300 for SE150
    parameter integer SCORE_W   = 10,
    parameter integer POS_W     = 16,
    // 几何参数 (SE150 规范)
    parameter integer NUM_LC    = 50,                      // 参考片段数 50
    parameter integer REF_LEN   = 957,                     // 每段参考长度 957 bp
    parameter integer STRIDE    = 807,                     // 每段可滑动位置 807
    // 结果位宽 = CODEBITS + POS_W + SCORE_W (300 + 16 + 10 = 326)
    parameter integer RESULT_W  = CODEBITS + POS_W + SCORE_W,
    parameter integer BATCH     = 64
)(
    // ----------------- AXI-Lite CTRL -----------------
    input  wire                                     s_axi_lite_ctrl_aclk,
    input  wire                                     s_axi_lite_ctrl_aresetn,
    input  wire [C_S_AXI_LITE_CTRL_ADDR_WIDTH-1:0]  s_axi_lite_ctrl_awaddr,
    input  wire [2:0]                               s_axi_lite_ctrl_awprot,
    input  wire                                     s_axi_lite_ctrl_awvalid,
    output wire                                     s_axi_lite_ctrl_awready,
    input  wire [C_S_AXI_LITE_CTRL_DATA_WIDTH-1:0]  s_axi_lite_ctrl_wdata,
    input  wire [(C_S_AXI_LITE_CTRL_DATA_WIDTH/8)-1:0] s_axi_lite_ctrl_wstrb,
    input  wire                                     s_axi_lite_ctrl_wvalid,
    output wire                                     s_axi_lite_ctrl_wready,
    output wire [1:0]                               s_axi_lite_ctrl_bresp,
    output wire                                     s_axi_lite_ctrl_bvalid,
    input  wire                                     s_axi_lite_ctrl_bready,
    input  wire [C_S_AXI_LITE_CTRL_ADDR_WIDTH-1:0]  s_axi_lite_ctrl_araddr,
    input  wire [2:0]                               s_axi_lite_ctrl_arprot,
    input  wire                                     s_axi_lite_ctrl_arvalid,
    output wire                                     s_axi_lite_ctrl_arready,
    output wire [C_S_AXI_LITE_CTRL_DATA_WIDTH-1:0]  s_axi_lite_ctrl_rdata,
    output wire [1:0]                               s_axi_lite_ctrl_rresp,
    output wire                                     s_axi_lite_ctrl_rvalid,
    input  wire                                     s_axi_lite_ctrl_rready,

    // ----------------- AXIS DATA IN ------------------
    input  wire                                     S_AXIS_DATA_ACLK,
    input  wire                                     S_AXIS_DATA_ARESETN,
    output wire                                     S_AXIS_DATA_TREADY,
    input  wire [C_S_AXIS_DATA_TDATA_WIDTH-1:0]     S_AXIS_DATA_TDATA,
    input  wire [(C_S_AXIS_DATA_TDATA_WIDTH/8)-1:0] S_AXIS_DATA_TSTRB,
    input  wire                                     S_AXIS_DATA_TLAST,
    input  wire                                     S_AXIS_DATA_TVALID,

    // ----------------- AXIS RESULT OUT --------------
    input  wire                                     M_AXIS_RESULT_ACLK,
    input  wire                                     M_AXIS_RESULT_ARESETN,
    output wire                                     M_AXIS_RESULT_TVALID,
    output wire [C_M_AXIS_RESULT_TDATA_WIDTH-1:0]   M_AXIS_RESULT_TDATA,
    output wire [(C_M_AXIS_RESULT_TDATA_WIDTH/8)-1:0] M_AXIS_RESULT_TSTRB,
    output wire                                     M_AXIS_RESULT_TLAST,
    input  wire                                     M_AXIS_RESULT_TREADY
);

    // =================================================
    // Clock/Reset domain
    // =================================================
    wire aclk    = S_AXIS_DATA_ACLK;
    wire aresetn = S_AXIS_DATA_ARESETN & M_AXIS_RESULT_ARESETN;

    // =================================================
    // AXI-Lite registers
    //  reg0[0]=start, reg0[1]=preload, reg0[2]=soft_reset
    //  reg1[5:0]=wm_sel
    // =================================================
    wire [31:0] reg0, reg1, reg2, reg3;
    dna_accelerator_core_v1_0_S_AXI_LITE_CTRL #(
        .C_S_AXI_DATA_WIDTH(C_S_AXI_LITE_CTRL_DATA_WIDTH),
        .C_S_AXI_ADDR_WIDTH(C_S_AXI_LITE_CTRL_ADDR_WIDTH)
    ) u_axil (
        .slv_reg0_out(reg0), .slv_reg1_out(reg1), .slv_reg2_out(reg2), .slv_reg3_out(reg3),
        .S_AXI_ACLK   (s_axi_lite_ctrl_aclk),
        .S_AXI_ARESETN(s_axi_lite_ctrl_aresetn),
        .S_AXI_AWADDR (s_axi_lite_ctrl_awaddr),
        .S_AXI_AWPROT (s_axi_lite_ctrl_awprot),
        .S_AXI_AWVALID(s_axi_lite_ctrl_awvalid),
        .S_AXI_AWREADY(s_axi_lite_ctrl_awready),
        .S_AXI_WDATA  (s_axi_lite_ctrl_wdata),
        .S_AXI_WSTRB  (s_axi_lite_ctrl_wstrb),
        .S_AXI_WVALID (s_axi_lite_ctrl_wvalid),
        .S_AXI_WREADY (s_axi_lite_ctrl_wready),
        .S_AXI_BRESP  (s_axi_lite_ctrl_bresp),
        .S_AXI_BVALID (s_axi_lite_ctrl_bvalid),
        .S_AXI_BREADY (s_axi_lite_ctrl_bready),
        .S_AXI_ARADDR (s_axi_lite_ctrl_araddr),
        .S_AXI_ARPROT (s_axi_lite_ctrl_arprot),
        .S_AXI_ARVALID(s_axi_lite_ctrl_arvalid),
        .S_AXI_ARREADY(s_axi_lite_ctrl_arready),
        .S_AXI_RDATA  (s_axi_lite_ctrl_rdata),
        .S_AXI_RRESP  (s_axi_lite_ctrl_rresp),
        .S_AXI_RVALID (s_axi_lite_ctrl_rvalid),
        .S_AXI_RREADY (s_axi_lite_ctrl_rready)
    );

    // CTRL sync into aclk domain
    reg [2:0]  sr_start, sr_preload, sr_soft;
    reg [5:0]  wm_sel_s1, wm_sel_s2;
    always @(posedge aclk or negedge aresetn) begin
        if (!aresetn) begin
            sr_start   <= 3'd0;
            sr_preload <= 3'd0;
            sr_soft    <= 3'd0;
            wm_sel_s1  <= 6'd0;
            wm_sel_s2  <= 6'd0;
        end else begin
            sr_start   <= {sr_start[1:0],   reg0[0]};
            sr_preload <= {sr_preload[1:0], reg0[1]};
            sr_soft    <= {sr_soft[1:0],    reg0[2]};
            wm_sel_s1  <= reg1[5:0];
            wm_sel_s2  <= wm_sel_s1;
        end
    end
    wire start_task_s   = sr_start[2];
    wire preload_mode_s = sr_preload[2];
    wire soft_reset_s   = sr_soft[2];
    wire [5:0] wm_sel_s = wm_sel_s2;

    // start rising edge detection
    reg start_q;
    always @(posedge aclk or negedge aresetn) begin
        if (!aresetn) start_q <= 1'b0;
        else          start_q <= start_task_s;
    end
    wire start_rise = start_task_s & ~start_q;

    // =================================================
    // AXIS IN: 10x32bit assemble to 1 read (CODEBITS)
    // =================================================
    reg  [CODEBITS-1:0] in_buf, next_in_buf;
    reg  [3:0]          in_cnt;
    reg                 in_wr;
    wire                in_full, in_empty;
    reg                 in_rd;
    wire [CODEBITS-1:0] in_dout;
    
    // Forward declare eng_busy and eng_done for TREADY logic and start logic
    wire eng_busy, eng_done;
    
    // Maintain FIFO read count (for start condition and TREADY)
    reg [11:0] in_count;
    always @(posedge aclk or negedge aresetn) begin
        if (!aresetn || soft_reset_s) begin
            in_count <= 12'd0;
        end else begin
            case ({(in_wr && ~in_full), (in_rd && ~in_empty)})
                2'b10: in_count <= in_count + 1'b1;
                2'b01: in_count <= in_count - 1'b1;
                default: in_count <= in_count;
            endcase
        end
    end

    assign S_AXIS_DATA_TREADY = preload_mode_s ? 1'b1 : ~in_full;

    // Assemble read data
    always @* begin
        next_in_buf = in_buf;
        if (S_AXIS_DATA_TVALID && S_AXIS_DATA_TREADY && ~preload_mode_s) begin
            case (in_cnt)
                4'd0: next_in_buf[ 31:  0] = S_AXIS_DATA_TDATA;
                4'd1: next_in_buf[ 63: 32] = S_AXIS_DATA_TDATA;
                4'd2: next_in_buf[ 95: 64] = S_AXIS_DATA_TDATA;
                4'd3: next_in_buf[127: 96] = S_AXIS_DATA_TDATA;
                4'd4: next_in_buf[159:128] = S_AXIS_DATA_TDATA;
                4'd5: next_in_buf[191:160] = S_AXIS_DATA_TDATA;
                4'd6: next_in_buf[223:192] = S_AXIS_DATA_TDATA;
                4'd7: next_in_buf[255:224] = S_AXIS_DATA_TDATA;
                4'd8: next_in_buf[287:256] = S_AXIS_DATA_TDATA;
                4'd9: next_in_buf[CODEBITS-1:288] = S_AXIS_DATA_TDATA[CODEBITS-288-1:0];
                default: ;
            endcase
        end
    end

    always @(posedge aclk or negedge aresetn) begin
        if (!aresetn || soft_reset_s) begin
            in_buf <= {CODEBITS{1'b0}};
            in_cnt <= 4'd0;
            in_wr  <= 1'b0;
        end else begin
            in_buf <= next_in_buf;
            in_wr  <= 1'b0; // default
            if (S_AXIS_DATA_TVALID && S_AXIS_DATA_TREADY && ~preload_mode_s) begin
                if (in_cnt == 4'd9) begin
                    in_cnt <= 4'd0;
                    in_wr  <= 1'b1; // Collected 10x32bit, write 1 read
                end else begin
                    in_cnt <= in_cnt + 1'b1;
                end
            end
        end
    end

    // 输入 FIFO: DEPTH=256
    fifo_sync_sdpram_b64 #(.WIDTH(CODEBITS), .DEPTH(256)) u_in_fifo (
        .clk   (aclk),
        .rst_n (aresetn & ~soft_reset_s),
        .wr_en (in_wr),
        .din   (in_buf),
        .full  (in_full),
        .rd_en (in_rd),
        .dout  (in_dout),
        .empty (in_empty)
    );

    // =================================================
    // Preload watermark with overflow protection
    // =================================================
    reg        wm_we;
    reg [10:0] wm_waddr;     // 递增指针
    reg [10:0] wm_waddr_q;   // [B25] 与 wm_wdata / wm_we 同拍的写地址
    reg [1:0]  wm_wdata;

    always @(posedge aclk or negedge aresetn) begin
        wm_we <= 1'b0;
        if (!aresetn || soft_reset_s) begin
            wm_waddr   <= 11'd0;
            wm_waddr_q <= 11'd0;
        end else if (preload_mode_s && S_AXIS_DATA_TVALID && S_AXIS_DATA_TREADY) begin
            wm_we    <= 1'b1;
            wm_wdata <= S_AXIS_DATA_TDATA[1:0];
            wm_waddr_q <= wm_waddr;
            wm_waddr <= (wm_waddr == 11'd956) ? 11'd0 : (wm_waddr + 11'd1);
        end
    end

    // =================================================
    // Batch processing engine handshake:
    //  - Sync FIFO read delay is 2 cycles => cw_valid = in_rd_d2
    //  - Each cw_req only triggers one in_rd
    // =================================================
    wire eng_cw_req;
    reg  eng_cw_vld;
    reg  rd_issued;
    reg  in_rd_d1, in_rd_d2;
    reg  [CODEBITS-1:0] cw_hold;

    always @(posedge aclk or negedge aresetn) begin
        if (!aresetn || soft_reset_s) begin
            in_rd      <= 1'b0;
            in_rd_d1   <= 1'b0;
            in_rd_d2   <= 1'b0;
            eng_cw_vld <= 1'b0;
            rd_issued  <= 1'b0;
            cw_hold    <= {CODEBITS{1'b0}};
        end else begin
            in_rd      <= 1'b0;
            in_rd_d1   <= in_rd;
            in_rd_d2   <= in_rd_d1;
            if (in_rd_d2)
                cw_hold <= in_dout;
            eng_cw_vld <= in_rd_d2;

            if (!eng_cw_req)
                rd_issued <= 1'b0;

            if (eng_cw_req && ~rd_issued && ~in_empty) begin
                in_rd     <= 1'b1;
                rd_issued <= 1'b1;
            end
        end
    end

    // =================================================
    // Start logic with idle timeout for partial batches
    // =================================================
    reg  start_rise_latched;
    reg  arm_start;
    reg  [16:0] idle_counter;

    always @(posedge aclk or negedge aresetn) begin
        if (!aresetn || soft_reset_s)
            start_rise_latched <= 1'b0;
        else if (start_rise)
            start_rise_latched <= 1'b1;
    end

    always @(posedge aclk or negedge aresetn) begin
        if (!aresetn || soft_reset_s)
            idle_counter <= 17'd0;
        else if (eng_busy)
            idle_counter <= 17'd0;
        else if (~eng_busy && (in_count > 0) && (idle_counter < 17'h1FFFF))
            idle_counter <= idle_counter + 1'b1;
    end

    wire trigger_full_batch = (in_count >= BATCH);
    wire trigger_timeout = (in_count > 0) && 
                           (in_count < BATCH) && 
                           (idle_counter >= 17'd100000);
    wire can_trigger = trigger_full_batch | trigger_timeout;

    always @(posedge aclk or negedge aresetn) begin
        if (!aresetn || soft_reset_s) begin
            arm_start <= 1'b0;
        end else begin
            if ((start_rise_latched | eng_done) & 
                can_trigger & 
                ~preload_mode_s & 
                ~eng_busy & 
                ~arm_start)
                arm_start <= 1'b1;
            else
                arm_start <= 1'b0;
        end
    end

    // =================================================
    // Engine output -> result FIFO -> 64bit pack -> AXIS OUT
    // =================================================
    wire                 res_full, res_empty;
    wire                 res_rd;
    wire [RESULT_W-1:0]  res_out;

    wire                  eng_res_wr;
    wire [RESULT_W-1:0]   eng_res_din;

    // 实例化 4-Way 比对引擎 (srpe_batch_4way)
    srpe_batch_4way #(
        .BATCH    (BATCH),
        .NUM_LC   (NUM_LC),
        .STRIDE   (STRIDE),
        .REF_LEN  (REF_LEN),
        .READ_BPS (READ_BPS),
        .SCORE_W  (SCORE_W),
        .POS_W    (POS_W)
    ) u_srpe_batch (
        .clk              (aclk),
        .rst_n            (aresetn & ~soft_reset_s),
        .start_batch      (arm_start),
        .cw_req           (eng_cw_req),
        .cw_valid         (eng_cw_vld),
        .cw_data          (cw_hold),
        .bram_write_en    (wm_we),
        .bram_sel         (wm_sel_s),
        .bram_write_addr  (wm_waddr_q),
        .bram_write_data  (wm_wdata),
        .res_wr           (eng_res_wr),
        .res_din          (eng_res_din),
        .res_full         (res_full),
        .busy             (eng_busy),
        .done             (eng_done)
    );

    // 输出 FIFO: DEPTH=64 (Distributed RAM)
    fifo_sync_sdpram_b64 #(.WIDTH(RESULT_W), .DEPTH(64), .RAM_STYLE("distributed")) u_res_fifo (
        .clk   (aclk),
        .rst_n (aresetn & ~soft_reset_s),
        .wr_en (eng_res_wr),
        .din   (eng_res_din),
        .full  (res_full),
        .rd_en (res_rd),
        .dout  (res_out),
        .empty (res_empty)
    );

    // 64bit packing
    wire        pack_vld;
    wire [63:0] pack_dat;
    wire        pack_last;

    reg res_empty_q;
    always @(posedge aclk or negedge aresetn) begin
        if (!aresetn || soft_reset_s) res_empty_q <= 1'b1;
        else                          res_empty_q <= res_empty;
    end

    reg [1:0] res_settle;
    always @(posedge aclk or negedge aresetn) begin
        if (!aresetn || soft_reset_s)      res_settle <= 2'd0;
        else if (res_rd)                   res_settle <= 2'd3;
        else if (res_settle != 2'd0)       res_settle <= res_settle - 1'b1;
    end
    wire res_ready = ~res_empty_q & (res_settle == 2'd0);

    s2mm_pack64 #(.R(RESULT_W)) u_pack (
        .clk   (aclk),
        .rst_n (aresetn & ~soft_reset_s),
        .din_vld(res_ready),
        .din    (res_out),
        .din_rd (res_rd),
        .m_vld  (pack_vld),
        .m_dat  (pack_dat),
        .m_last (pack_last),
        .m_rdy  (M_AXIS_RESULT_TREADY)
    );

    // AXIS OUT
    assign M_AXIS_RESULT_TVALID = pack_vld;
    assign M_AXIS_RESULT_TLAST  = pack_last;
    assign M_AXIS_RESULT_TDATA  = pack_dat;
    assign M_AXIS_RESULT_TSTRB = {(C_M_AXIS_RESULT_TDATA_WIDTH/8){1'b1}};

endmodule
