// =============================================================
// File: Dna_accelerator_core_v1_0.v
// Desc: DNA Accelerator top (AXI-Lite + AXIS IN/OUT)
// Note: Complete fix - (1) cw_valid align with BRAM read
//                      (2) continuous batch processing with idle timeout
//                      (3) TREADY fixed to prevent DMA deadlock
// Std : Verilog-2001
// =============================================================
`timescale 1 ns / 1 ps

module Dna_accelerator_core_v1_0 #(
    // ===== AXI-Lite =====
    parameter integer C_S_AXI_LITE_CTRL_DATA_WIDTH = 32,
    parameter integer C_S_AXI_LITE_CTRL_ADDR_WIDTH = 4,
    // ===== AXIS widths =====
    parameter integer C_S_AXIS_DATA_TDATA_WIDTH    = 32,
    parameter integer C_M_AXIS_RESULT_TDATA_WIDTH  = 64,
    // ===== Algorithm/Data params =====
    parameter integer READ_BPS  = 150,                     // bits per read (symbols*2)
    parameter integer CODEBITS  = READ_BPS*2,              // e.g. 300
    parameter integer SCORE_W   = 10,
    parameter integer POS_W     = 16,
    // 【修改1】全局参数调整
    parameter integer NUM_LC    = 50,      // 参考片段数量：50
    parameter integer REF_LEN   = 957,     // 每段参考长度：957 bp
    parameter integer STRIDE    = 807,     // 每段可滑动位置数：807
    // 【修改2】结果宽度 = CODEBITS + POS_W + SCORE_W（region 信息已合并到 global_pos 中）
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
    output reg                                      M_AXIS_RESULT_TVALID,
    output wire [C_M_AXIS_RESULT_TDATA_WIDTH-1:0]   M_AXIS_RESULT_TDATA,
    output wire [(C_M_AXIS_RESULT_TDATA_WIDTH/8)-1:0] M_AXIS_RESULT_TSTRB,
    output reg                                      M_AXIS_RESULT_TLAST,
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
    Dna_accelerator_core_v1_0_S_AXI_LITE_CTRL #(
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

    // 预载不经过输入 FIFO；正常读段只有在 FIFO 可接纳时才握手。
    // 一条读段完成后 in_wr 延迟一拍，因此 FIFO 满时必须直接阻止下一拍进入。
    assign S_AXIS_DATA_TREADY = preload_mode_s ? 1'b1 : ~in_full;

    // Assemble read data
    always @* begin
        next_in_buf = in_buf;
        if (S_AXIS_DATA_TVALID && S_AXIS_DATA_TREADY && ~preload_mode_s) begin
            case (in_cnt)
                4'd0: next_in_buf[ 31:  0] = S_AXIS_DATA_TDATA;
                4'd1: next_in_buf[ 63:  32] = S_AXIS_DATA_TDATA;
                4'd2: next_in_buf[ 95:  64] = S_AXIS_DATA_TDATA;
                4'd3: next_in_buf[127:  96] = S_AXIS_DATA_TDATA;
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

    // 【深度优化】输入 FIFO: 2048 → 1024
    fifo_sync_sdpram_b64 #(.WIDTH(CODEBITS), .DEPTH(1024)) u_in_fifo (
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
    reg [9:0]  wm_waddr;
    reg [1:0]  wm_wdata;

    always @(posedge aclk or negedge aresetn) begin
        wm_we <= 1'b0;
        if (!aresetn || soft_reset_s) begin
            wm_waddr <= 10'd0;
        end else if (preload_mode_s && S_AXIS_DATA_TVALID && S_AXIS_DATA_TREADY) begin
            wm_we    <= 1'b1;
            wm_wdata <= S_AXIS_DATA_TDATA[1:0];
            // 【修复3】防溢出：写满 957 个 symbol 后自动归零
            wm_waddr <= (wm_waddr == 10'd956) ? 10'd0 : (wm_waddr + 10'd1);
        end
    end

    // =================================================
    // Batch processing engine handshake:
    //  - Sync FIFO read delay is 1 cycle => cw_valid = in_rd (previous cycle read, current cycle data valid)
    //  - Each cw_req only triggers one in_rd
    // =================================================
    wire eng_cw_req;
    reg  eng_cw_vld;
    reg  rd_issued;

    always @(posedge aclk or negedge aresetn) begin
        if (!aresetn || soft_reset_s) begin
            in_rd      <= 1'b0;
            eng_cw_vld <= 1'b0;
            rd_issued  <= 1'b0;
        end else begin
            // Default pull low
            in_rd      <= 1'b0;
            eng_cw_vld <= in_rd;   // <--- KEY: valid = previous cycle's read (aligned with dout)

            // req released, allow next trigger
            if (!eng_cw_req)
                rd_issued <= 1'b0;

            // Has request, not yet read, and FIFO not empty -> issue one rd_en
            if (eng_cw_req && ~rd_issued && ~in_empty) begin
                in_rd     <= 1'b1;
                rd_issued <= 1'b1;
            end
        end
    end

    // =================================================
    // *** FIX 2: Start logic with idle timeout for partial batches ***
    //  - Latch start signal (don't clear it on eng_busy)
    //  - Use eng_done to automatically trigger next batch
    //  - Track idle time when data < BATCH to handle last partial batch
    //  - This enables processing all 108000 reads continuously
    // =================================================
    reg  start_rise_latched;
    reg  arm_start;
    reg  [16:0] idle_counter;  // Track engine idle time with data in FIFO

    // Latch the start signal - don't clear it when engine is busy
    always @(posedge aclk or negedge aresetn) begin
        if (!aresetn || soft_reset_s)
            start_rise_latched <= 1'b0;
        else if (start_rise)
            start_rise_latched <= 1'b1;
    end

    // Track how long engine has been idle with data in FIFO
    always @(posedge aclk or negedge aresetn) begin
        if (!aresetn || soft_reset_s)
            idle_counter <= 17'd0;
        else if (eng_busy)
            idle_counter <= 17'd0;  // Reset when engine is working
        else if (~eng_busy && (in_count > 0) && (idle_counter < 17'h1FFFF))
            idle_counter <= idle_counter + 1'b1;  // Increment when idle with data
    end

    // Generate arm_start pulse for batch processing
    wire trigger_full_batch;
    wire trigger_timeout;
    wire can_trigger;
           
    assign trigger_full_batch = (in_count >= BATCH);
    assign trigger_timeout = (in_count > 0) && 
                                   (in_count < BATCH) && 
                                   (idle_counter >= 17'd100000);
    assign can_trigger = trigger_full_batch | trigger_timeout;                              
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
    reg                  res_rd;
    wire [RESULT_W-1:0]  res_out;

    wire                  eng_res_wr;
    wire [RESULT_W-1:0]   eng_res_din;

    // 【修改3】实例化 srpe_batch: .NUM_LC(50), .STRIDE(807), .REF_LEN(957) 
    srpe_batch #(
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
        .cw_data          (in_dout),
        .bram_write_en    (wm_we),
        .bram_sel         (wm_sel_s),
        .bram_write_addr  (wm_waddr),
        .bram_write_data  (wm_wdata),
        .res_wr           (eng_res_wr),
        .res_din          (eng_res_din),
        .res_full         (res_full),
        .busy             (eng_busy),
        .done             (eng_done)
    );

    // 【深度优化】输出 FIFO: 256 → 128
    fifo_sync_sdpram_b64 #(.WIDTH(RESULT_W), .DEPTH(128)) u_res_fifo (
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

    // ===== FIX: Add delay register to align with FIFO synchronous read =====
    reg res_empty_q;
    always @(posedge aclk or negedge aresetn) begin
        if (!aresetn || soft_reset_s)
            res_empty_q <= 1'b1;
        else
            res_empty_q <= res_empty;
    end

    s2mm_pack64 #(.R(RESULT_W)) u_pack (
        .clk   (aclk),
        .rst_n (aresetn & ~soft_reset_s),
        .din_vld(~res_empty_q),
        .din    (res_out),
        .m_vld  (pack_vld),
        .m_dat  (pack_dat),
        .m_last (pack_last),
        .m_rdy  (M_AXIS_RESULT_TREADY)
    );

    // Read result FIFO (when downstream ready and pack can output, read next)
    always @(posedge aclk or negedge aresetn) begin
        if (!aresetn || soft_reset_s)
            res_rd <= 1'b0;
        else
            res_rd <= ~res_empty & M_AXIS_RESULT_TREADY & pack_vld;
    end

    // AXIS OUT
    always @(posedge aclk or negedge aresetn) begin
        if (!aresetn || soft_reset_s) begin
            M_AXIS_RESULT_TVALID <= 1'b0;
            M_AXIS_RESULT_TLAST  <= 1'b0;
        end else if (M_AXIS_RESULT_TREADY || ~M_AXIS_RESULT_TVALID) begin
            M_AXIS_RESULT_TVALID <= pack_vld;
            M_AXIS_RESULT_TLAST  <= pack_last;
        end
    end

    assign M_AXIS_RESULT_TDATA = pack_dat;
    assign M_AXIS_RESULT_TSTRB = {(C_M_AXIS_RESULT_TDATA_WIDTH/8){1'b1}};

endmodule

