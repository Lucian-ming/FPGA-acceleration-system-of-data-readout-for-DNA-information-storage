// ============================================================================
// File: srpe_batch_4way.v
// Desc: 64-read batch engine using bit-plane BRAM & 4-Way Multi-Position Sliding Window
// ----------------------------------------------------------------------------
// 【打包变体与架构契约】（docs/05-implementation-plan.md的热整理门禁）
// 1. 本文件是 hw/ip/Dna_accelerator_core_1_0/component.xml 当前打包的生产实现变体，
//    与 hw/ip/PACKAGED_VARIANTS.txt 保持严格一致（模块名通过宏别名定义为 srpe_batch）。
// 2. 4-Way 展开微架构：
//    - 保持位平面 BRAM 与码字装载/结果输出逻辑 100% 兼容不变；
//    - 引入 4 拍水印滑窗移位寄存器与 4 组独立比对累加器（PE0~PE3）；
//    - 单时钟周期推进 1 个碱基的同时并行比对 4 个滑动位置（pos_cnt 步进 4）；
//    - 1 拍流水选优树（4选1比较器）在 100 MHz 下确保流水线时序深度收敛；
//    - 与 2-way 参考模型在 64/64 读段上给出逐位相同的 pos 与 score 结果。
// 3. 时序收敛策略与资源开销：
//    - 策略：Performance_ExplorePostRoutePhysOpt；
//    - 关键指标：WNS = +0.246 ns @ 100 MHz（XC7Z010CLG400-1）；
//    - 资源占用：~9.4k LUTs (约占 XC7Z010 资源的 53%)，安全适配 XC7Z010 器件。
// 4. 板级实测边界（docs/benchmarks/measured_4way_board.md）：
//    - 核心比对加速比 1.929x，端到端每记录成本降低 1.218x（符合 Amdahl 定律，
//      实测反解证实 Stage1 占每记录成本的 37.1%，其余 62.9% 为 DMA/Voter/回写）。
// ----------------------------------------------------------------------------
// Synth: Verilog-2001
// ============================================================================
`timescale 1 ns / 1 ps

`ifndef SRPE_BATCH_4WAY_MODNAME
`define SRPE_BATCH_4WAY_MODNAME srpe_batch
`endif

(* keep_hierarchy = "yes" *)
module `SRPE_BATCH_4WAY_MODNAME #(
    parameter integer BATCH     = 64,
    parameter integer NUM_LC    = 50,      // 参考区域数量
    parameter integer STRIDE    = 805,     // 每区域可滑动位置数
    parameter integer REF_LEN   = 1055,    // 每段参考长度
    parameter integer READ_BPS  = 250,
    parameter integer SCORE_W   = 10,
    parameter integer POS_W     = 16
)(
    input  wire                   clk,
    input  wire                   rst_n,
    input  wire                   start_batch,

    // 从上层依次读取 BATCH 条码字，每条宽 2*READ_BPS bit。
    output reg                    cw_req,     // 请求一条读段
    input  wire                   cw_valid,   // 本周期 cw_data 有效
    input  wire [READ_BPS*2-1:0]  cw_data,    // 500b when READ_BPS=250

    // 预载水印写入口
    input  wire                   bram_write_en,
    input  wire [5:0]             bram_sel,
    input  wire [10:0]            bram_write_addr,  // 0..REF_LEN-1 (1055-1=1054)
    input  wire [1:0]             bram_write_data,

    // 结果输出到上层 FIFO
    output reg                    res_wr,
    output reg  [READ_BPS*2+POS_W+SCORE_W-1:0] res_din,
    input  wire                   res_full,

    output reg                    busy,
    output reg                    done
);

    localparam integer CODEBITS = READ_BPS*2;
    localparam integer RESULT_W = CODEBITS + POS_W + SCORE_W;

    // 区域索引与水印存储几何
    localparam integer REGION_W = 6;                     // 0~49
    localparam integer WM_DEPTH = NUM_LC * REF_LEN;      // 50*957 or 50*1055
    localparam integer WM_AW    = CLOG2(WM_DEPTH);
    localparam integer P_WAYS   = 4;                     // 4路滑窗并行

    // ----------------------------------------------------------
    // 辅助函数
    // ----------------------------------------------------------
    function integer CLOG2; input integer v; integer t,i; begin
        t=v-1; i=0; while(t>0) begin t=t>>1; i=i+1; end CLOG2=i;
    end endfunction

    // ----------------------------------------------------------
    // 水印 BRAM：NUM_LC * REF_LEN 个 2-bit 符号
    // ----------------------------------------------------------
    (* ram_style="block", rom_style="block" *)
    reg [1:0] wm_bram [0:WM_DEPTH-1];

    // 写地址：wm_wr_addr = bram_sel * REF_LEN + bram_write_addr
    wire [15:0] wm_wr_addr_lin = bram_sel * REF_LEN + bram_write_addr;
    wire [WM_AW-1:0] wm_wr_addr = wm_wr_addr_lin[WM_AW-1:0];

    // 读地址与数据寄存器
    reg  [5:0]       lc_idx;
    reg  [15:0]      wm_rd_offset;
    wire [15:0]      wm_rd_addr_lin = lc_idx * REF_LEN + wm_rd_offset;
    wire [WM_AW-1:0] wm_rd_addr_d   = wm_rd_addr_lin[WM_AW-1:0];

    reg  [WM_AW-1:0] wm_rd_addr_q;
    reg  [1:0]       wm_sym_q;

    // ----------------------------------------------------------
    // 读段位平面 BRAM：READ_BPS 行，每行并行保存 64 条读段。
    // Port A 用于比对同步读，Port B 用于装载/输出的读改写。
    // ----------------------------------------------------------
    (* ram_style = "block" *) reg [63:0] plane_lo [0:READ_BPS-1];
    (* ram_style = "block" *) reg [63:0] plane_hi [0:READ_BPS-1];

    // Port A：比对阶段同步读
    reg [8:0]  a_addr;
    reg [63:0] a_lo_q, a_hi_q;
    always @(posedge clk) begin
        a_lo_q <= plane_lo[a_addr];
        a_hi_q <= plane_hi[a_addr];
    end

    // Port B：装载/输出阶段读改写
    reg [8:0]  b_addr;
    reg [63:0] b_lo_q, b_hi_q;
    reg        b_we_lo, b_we_hi;
    reg [63:0] b_lo_d,  b_hi_d;
    always @(posedge clk) begin
        b_lo_q <= plane_lo[b_addr];
        b_hi_q <= plane_hi[b_addr];
        if (b_we_lo) plane_lo[b_addr] <= b_lo_d;
        if (b_we_hi) plane_hi[b_addr] <= b_hi_d;
    end

    // ----------------------------------------------------------
    // 状态机编码
    // ----------------------------------------------------------
    localparam [3:0] S_IDLE       = 4'd0,
                     S_CLR        = 4'd1,
                     S_LOAD       = 4'd2,
                     S_LOAD_R     = 4'd3,
                     S_PREFILL    = 4'd4,
                     S_INITC      = 4'd5,
                     S_LAUNCH     = 4'd6,
                     S_RUN        = 4'd7,
                     S_UPD1       = 4'd8,
                     S_UPD2       = 4'd9,
                     S_NEXT       = 4'd10,
                     S_EMIT       = 4'd11,
                     S_EMIT2      = 4'd12,
                     S_EMIT_FINAL = 4'd13,
                     S_DONE       = 4'd14,
                     S_EMIT_W     = 4'd15;

    reg [3:0]  st;

    // 读段装载阶段
    reg [6:0]  cw_idx;
    reg [8:0]  row_i;
    reg [1:0]  phase;
    reg [5:0]  bit_sel;

    reg [READ_BPS-1:0] cw_hi_sr;
    reg [READ_BPS-1:0] cw_lo_sr;

    // 位置比对控制
    reg [15:0]  pos_cnt;
    reg [15:0]  pos_base;
    reg [8:0]   pre_cnt;
    reg [8:0]   run_cnt;

    // 64 条读段的最优位置与分数记录
    reg [SCORE_W-1:0]  best_sc     [0:BATCH-1];
    reg [POS_W-1:0]    best_pos    [0:BATCH-1];
    reg [REGION_W-1:0] best_region [0:BATCH-1];

    // 4 路并行滑窗移位寄存器
    // wm_win[p] 对应位置 pos_base + p
    reg [1:0] wm_win [0:P_WAYS-1];

    // 4 组独立分数累加器：score[p][t]
    reg [SCORE_W-1:0] score [0:P_WAYS-1][0:BATCH-1];

    // 4 个候选位置有效标志（防止超出 STRIDE 越界，包含 STRIDE 边界）
    wire [3:0] pos_valid;
    genvar gv;
    generate
        for (gv=0; gv<P_WAYS; gv=gv+1) begin: gen_pos_val
            assign pos_valid[gv] = (pos_base + gv <= STRIDE);
        end
    endgenerate

    // 流水选优树第一级寄存器（S_UPD1 -> S_UPD2）
    reg                   stage1_res_valid;
    reg [REGION_W-1:0]    stage1_lc_idx;
    reg [POS_W-1:0]       stage1_pos   [0:BATCH-1];
    reg [SCORE_W-1:0]     stage1_score [0:BATCH-1];
    reg [CODEBITS-1:0]    stage1_cw    [0:BATCH-1];

    // 匹配比较矩阵：match_mask[p][t] 表示位置 p 对读段 t 的当前碱基是否完全一致
    wire [63:0] match_mask [0:P_WAYS-1];
    generate
        for (gv=0; gv<P_WAYS; gv=gv+1) begin: gen_match
            assign match_mask[gv] = ~( (a_lo_q ^ {64{wm_win[gv][0]}}) |
                                       (a_hi_q ^ {64{wm_win[gv][1]}}) );
        end
    endgenerate

    // 输出装载阶段
    reg [5:0]  emit_idx;
    reg [8:0]  emit_i;
    reg [CODEBITS-1:0] cw_acc;

    wire [15:0] region_mul_stride = best_region[emit_idx] * STRIDE;
    wire [POS_W-1:0] global_pos   = region_mul_stride + best_pos[emit_idx];

    integer p, t;

    // 水印 BRAM 同步读写
    always @(posedge clk) begin
        if (bram_write_en) begin
            wm_bram[wm_wr_addr] <= bram_write_data;
        end
        wm_rd_addr_q <= wm_rd_addr_d;
        wm_sym_q     <= wm_bram[wm_rd_addr_q];
    end

    // ----------------------------------------------------------
    // 主控制状态机
    // ----------------------------------------------------------
    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            st              <= S_IDLE;
            busy            <= 1'b0;
            done            <= 1'b0;
            cw_req          <= 1'b0;
            cw_idx          <= 7'd0;
            row_i           <= 9'd0;
            phase           <= 2'd0;
            bit_sel         <= 6'd0;
            b_we_lo         <= 1'b0;
            b_we_hi         <= 1'b0;
            b_addr          <= 9'd0;
            b_lo_d          <= 64'd0;
            b_hi_d          <= 64'd0;
            cw_hi_sr        <= {READ_BPS{1'b0}};
            cw_lo_sr        <= {READ_BPS{1'b0}};
            lc_idx          <= 6'd0;
            pos_cnt         <= 16'd0;
            pos_base        <= 16'd0;
            pre_cnt         <= 9'd0;
            run_cnt         <= 9'd0;
            a_addr          <= 9'd0;
            wm_rd_offset    <= 16'd0;
            res_wr          <= 1'b0;
            res_din         <= {RESULT_W{1'b0}};
            emit_idx        <= 6'd0;
            emit_i          <= 9'd0;
            cw_acc          <= {CODEBITS{1'b0}};
            stage1_res_valid <= 1'b0;
            stage1_lc_idx    <= {REGION_W{1'b0}};
            for (t=0; t<BATCH; t=t+1) begin
                best_sc[t]      <= {SCORE_W{1'b0}};
                best_pos[t]     <= {POS_W{1'b0}};
                best_region[t]  <= {REGION_W{1'b0}};
                stage1_score[t] <= {SCORE_W{1'b0}};
                stage1_pos[t]   <= {POS_W{1'b0}};
                stage1_cw[t]    <= {CODEBITS{1'b0}};
                for (p=0; p<P_WAYS; p=p+1) score[p][t] <= {SCORE_W{1'b0}};
            end
            for (p=0; p<P_WAYS; p=p+1) wm_win[p] <= 2'b00;
        end else begin
            cw_req  <= 1'b0;
            res_wr  <= 1'b0;
            b_we_lo <= 1'b0;
            b_we_hi <= 1'b0;

            case (st)
                S_IDLE: begin
                    done <= 1'b0;
                    if (start_batch) begin
                        busy    <= 1'b1;
                        row_i   <= 0;
                        b_we_lo <= 1'b1;
                        b_we_hi <= 1'b1;
                        b_lo_d  <= 64'd0;
                        b_hi_d  <= 64'd0;
                        b_addr  <= 0;
                        st      <= S_CLR;
                    end
                end

                S_CLR: begin
                    b_addr <= row_i;
                    b_lo_d <= 64'd0; b_hi_d <= 64'd0;
                    b_we_lo<= 1'b1;  b_we_hi<= 1'b1;
                    if (row_i == READ_BPS-1) begin
                        cw_idx  <= 0; row_i <= 0; phase <= 2'd0; bit_sel <= 0;
                        st      <= S_LOAD;
                    end else begin
                        row_i <= row_i + 1'b1;
                    end
                end

                S_LOAD: begin
                    cw_req <= 1'b1;
                    if (cw_valid) begin
                        row_i    <= 0;
                        phase    <= 2'd0;
                        cw_hi_sr <= cw_data[READ_BPS-1:0];
                        cw_lo_sr <= cw_data[CODEBITS-1:READ_BPS];
                        st       <= S_LOAD_R;
                    end
                end

                S_LOAD_R: begin
                    if (phase == 2'd0) begin
                        b_addr <= row_i;
                        phase  <= 2'd1;
                    end else if (phase == 2'd1) begin
                        phase  <= 2'd2;
                    end else begin
                        b_hi_d <= (cw_hi_sr[0]) ?
                                  (b_hi_q | (64'h1 << bit_sel)) :
                                  (b_hi_q & ~(64'h1 << bit_sel));
                        b_lo_d <= (cw_lo_sr[0]) ?
                                  (b_lo_q | (64'h1 << bit_sel)) :
                                  (b_lo_q & ~(64'h1 << bit_sel));
                        cw_hi_sr <= {1'b0, cw_hi_sr[READ_BPS-1:1]};
                        cw_lo_sr <= {1'b0, cw_lo_sr[READ_BPS-1:1]};
                        b_we_lo<= 1'b1; b_we_hi<= 1'b1;

                        phase  <= 2'd0;
                        if (row_i == READ_BPS-1) begin
                            if (cw_idx == BATCH-1) begin
                                st <= S_INITC;
                            end else begin
                                cw_idx  <= cw_idx + 1'b1;
                                bit_sel <= bit_sel + 1'b1;
                                st      <= S_LOAD;
                            end
                        end else begin
                            row_i <= row_i + 1'b1;
                        end
                    end
                end

                S_INITC: begin
                    lc_idx           <= 0;
                    pos_cnt          <= 0;
                    pos_base         <= 0;
                    stage1_res_valid <= 1'b0;
                    stage1_lc_idx    <= {REGION_W{1'b0}};
                    for (t=0; t<BATCH; t=t+1) begin
                        best_sc[t]      <= {SCORE_W{1'b0}};
                        best_pos[t]     <= {POS_W{1'b0}};
                        best_region[t]  <= {REGION_W{1'b0}};
                        stage1_score[t] <= {SCORE_W{1'b0}};
                        stage1_pos[t]   <= {POS_W{1'b0}};
                    end
                    st <= S_LAUNCH;
                end

                S_LAUNCH: begin
                    pos_base         <= pos_cnt;
                    pre_cnt          <= 0;
                    run_cnt          <= 0;
                    stage1_res_valid <= 1'b0;
                    for (t=0; t<BATCH; t=t+1) begin
                        for (p=0; p<P_WAYS; p=p+1) score[p][t] <= {SCORE_W{1'b0}};
                    end
                    wm_rd_offset <= (pos_cnt >= REF_LEN) ? (REF_LEN-1) : pos_cnt;
                    st <= S_PREFILL;
                end

                // 预充填阶段：4 拍移位寄存器装填
                S_PREFILL: begin
                    pre_cnt <= pre_cnt + 1'b1;

                    if (pre_cnt < 5) begin
                        wm_rd_offset <= ((pos_base + pre_cnt + 1) >= REF_LEN) ? 
                                        (REF_LEN - 1) : (pos_base + pre_cnt + 1);
                    end

                    if (pre_cnt >= 2) begin
                        wm_win[0] <= wm_win[1];
                        wm_win[1] <= wm_win[2];
                        wm_win[2] <= wm_win[3];
                        wm_win[3] <= wm_sym_q;
                    end

                    if (pre_cnt == 4) begin
                        a_addr <= 9'd0;
                    end else if (pre_cnt == 5) begin
                        a_addr <= 9'd1;
                    end

                    if (pre_cnt == 5) begin
                        run_cnt <= 0;
                        wm_rd_offset <= ((pos_base + 6) >= REF_LEN) ? (REF_LEN - 1) : (pos_base + 6);
                        st <= S_RUN;
                    end
                end

                // 比对运行阶段：持续 READ_BPS 拍
                S_RUN: begin
                    run_cnt <= run_cnt + 1'b1;

                    for (p=0; p<P_WAYS; p=p+1) begin
                        if (pos_valid[p]) begin
                            for (t=0; t<BATCH; t=t+1) begin
                                if (match_mask[p][t]) score[p][t] <= score[p][t] + 1'b1;
                            end
                        end
                    end

                    wm_win[0] <= wm_win[1];
                    wm_win[1] <= wm_win[2];
                    wm_win[2] <= wm_win[3];
                    wm_win[3] <= wm_sym_q;

                    if (run_cnt + 2 < READ_BPS) begin
                        a_addr <= run_cnt + 2;
                    end
                    wm_rd_offset <= ((pos_base + 7 + run_cnt) >= REF_LEN) ? 
                                    (REF_LEN - 1) : (pos_base + 7 + run_cnt);

                    if (run_cnt == READ_BPS - 1) begin
                        st <= S_UPD1;
                    end
                end

                // 选优流水级 1：4 选 1 局部选优，结果打入流水寄存器
                S_UPD1: begin
                    stage1_res_valid <= 1'b1;
                    stage1_lc_idx    <= lc_idx;

                    for (t=0; t<BATCH; t=t+1) begin: blk_upd1
                        reg [SCORE_W-1:0] s01, s23, top_sc;
                        reg [1:0]         p01, p23, top_p;

                        // 0 vs 1
                        if (!pos_valid[1] || (score[0][t] >= score[1][t])) begin
                            s01 = score[0][t]; p01 = 2'd0;
                        end else begin
                            s01 = score[1][t]; p01 = 2'd1;
                        end

                        // 2 vs 3
                        if (!pos_valid[2]) begin
                            s23 = {SCORE_W{1'b0}}; p23 = 2'd0;
                        end else if (!pos_valid[3] || (score[2][t] >= score[3][t])) begin
                            s23 = score[2][t]; p23 = 2'd2;
                        end else begin
                            s23 = score[3][t]; p23 = 2'd3;
                        end

                        // 4 选 1（并列严格偏向低序号）
                        if (s01 >= s23) begin
                            top_sc = s01; top_p = p01;
                        end else begin
                            top_sc = s23; top_p = p23;
                        end

                        stage1_score[t] <= top_sc;
                        stage1_pos[t]   <= pos_base + top_p;
                    end
                    st <= S_UPD2;
                end

                // 选优流水级 2：与全局历史最优比较并更新
                S_UPD2: begin
                    for (t=0; t<BATCH; t=t+1) begin: blk_upd2
                        if (stage1_res_valid && (stage1_score[t] > best_sc[t])) begin
                            best_sc[t]     <= stage1_score[t];
                            best_pos[t]    <= stage1_pos[t];
                            best_region[t] <= stage1_lc_idx;
                        end
                    end
                    stage1_res_valid <= 1'b0;
                    st <= S_NEXT;
                end

                // 步进推进：每次前进 4 个位置
                S_NEXT: begin
                    if (pos_cnt + 4 > STRIDE) begin
                        pos_cnt <= 16'd0;
                        if (lc_idx == NUM_LC-1) begin
                            emit_idx <= 0; emit_i <= 0; cw_acc <= {CODEBITS{1'b0}};
                            st <= S_EMIT;
                        end else begin
                            lc_idx <= lc_idx + 1'b1;
                            st     <= S_LAUNCH;
                        end
                    end else begin
                        pos_cnt <= pos_cnt + 4;
                        st      <= S_LAUNCH;
                    end
                end

                // 结果输出阶段
                S_EMIT: begin
                    if (!res_full) begin
                        b_addr <= emit_i;
                        st     <= S_EMIT_W;
                    end
                end

                S_EMIT_W: st <= S_EMIT2;

                S_EMIT2: begin
                    cw_acc[emit_i]            <= b_hi_q[emit_idx];
                    cw_acc[READ_BPS + emit_i] <= b_lo_q[emit_idx];

                    if (emit_i == READ_BPS-1) begin
                        emit_i <= 0;
                        st     <= S_EMIT_FINAL;
                    end else begin
                        emit_i <= emit_i + 1'b1;
                        st     <= S_EMIT;
                    end
                end

                S_EMIT_FINAL: begin
                    res_din <= {cw_acc, global_pos, best_sc[emit_idx]};
                    res_wr  <= 1'b1;
                    cw_acc  <= {CODEBITS{1'b0}};

                    if (emit_idx == BATCH-1) begin
                        st <= S_DONE;
                    end else begin
                        emit_idx <= emit_idx + 1'b1;
                        st       <= S_EMIT;
                    end
                end

                S_DONE: begin
                    busy <= 1'b0; done <= 1'b1; st <= S_IDLE;
                end

                default: st <= S_IDLE;
            endcase
        end
    end

endmodule
