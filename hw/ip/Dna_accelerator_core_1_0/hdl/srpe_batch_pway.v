// ============================================================================
// File: srpe_batch_pway.v
// Desc: 64-read batch engine, bit-plane BRAM, P_WAYS-position sliding window
// ----------------------------------------------------------------------------
// 【生产P路变体】由2026-09-22 XC7Z020候选纳入正式IP，实验原件保留供追溯。
// 顶层 Dna_accelerator_core_v1_0 用 C_STAGE1_P_WAYS=16 / C_STAGE1_PIPE_TREE=1 选择。
// 默认几何为SE150；顶层仍显式透传全部几何参数。
// 2026-10-14：每拍碱基数 K 已由可配置参数**写死为 2**（见下方 localparam BASES_PER_CYCLE）。
//   写死前 K 是 parameter，顶层/BD/component/xgui 均有传参通道，现已全部撤销；
//   K=2 已由 tb_dna_stage1_p16_equivalence.v 以「生产P4 + 独立oracle」双重逐位判定通过。
// 左>=右取左，保证并列取低位置；pos_valid在S_LAUNCH寄存且包含STRIDE边界；
// PIPE_TREE=1逐级打拍，S_UPD1等待log2(P)拍，保留同步BRAM装载/输出协议。
// 历史OOC: docs/benchmarks/stage1-pway-7020-probe.md；不是新板整机时序证据。
// ----------------------------------------------------------------------------
// Synth: Verilog-2001
// ============================================================================
`timescale 1 ns / 1 ps

`ifndef SRPE_BATCH_PWAY_MODNAME
`define SRPE_BATCH_PWAY_MODNAME srpe_batch_pway
`endif

(* keep_hierarchy = "yes" *)
module `SRPE_BATCH_PWAY_MODNAME #(
    parameter integer P_WAYS    = 4,       // 并行滑窗位置数，2 的幂
    parameter integer PIPE_TREE = 0,       // 1 = 选优树逐级打拍（P>=8 在 100 MHz 下必需）
    parameter integer BATCH     = 64,
    parameter integer NUM_LC    = 50,      // 参考区域数量
    parameter integer STRIDE    = 807,     // 每区域可滑动位置数
    parameter integer REF_LEN   = 957,    // 每段参考长度
    parameter integer READ_BPS  = 150,
    parameter integer SCORE_W   = 10,
    parameter integer POS_W     = 16
)(
    input  wire                   clk,
    input  wire                   rst_n,
    input  wire                   start_batch,

    // 从上层依次读取 BATCH 条码字，每条宽 2*READ_BPS bit。
    output reg                    cw_req,     // 请求一条读段
    input  wire                   cw_valid,   // 本周期 cw_data 有效
    input  wire [READ_BPS*2-1:0]  cw_data,    // SE150: 300b

    // 预载水印写入口
    input  wire                   bram_write_en,
    input  wire [5:0]             bram_sel,
    input  wire [10:0]            bram_write_addr,  // 0..REF_LEN-1 (SE150: 956)
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

    // 2026-10-14 冻结：每拍推进 2 个碱基。原为可配置 parameter（支持 1/2/4），
    // 整机 route 实测 K=4 硬失败（LUT 63,246 > 容量 53,200），K=2 通过
    // （35,702 LUT / WNS +0.313 / 0 失败端点），故写死为 2 并撤销全部构建期传参通道。
    // 依据与判据见 docs/benchmarks/stage1-multibase-ooc-probe.md。
    // 读段 150 个碱基被 K 整除（150/2=75），故 score_inc 的末组掩码路径在本配置下恒为真。
    localparam integer BASES_PER_CYCLE = 2;

    // 【压缩项 A，2026-10-14】预充填只需发出「返回后会落进窗口」的那几组地址。
    // 窗口 17 深、每拍进 K 个；S_LAUNCH 已用 pos_cnt 那一个地址覆盖了窗口的前 K 项，
    // 故还差 ceil((WM_WINDOW_SIZE-K)/K) 组。原写法按 P_WAYS-1 = 15 组发，其中
    // 7 组返回的 tag 落在窗口外、被位置守卫丢弃 —— 实测：18 拍预充填里只有
    // 9.02 拍真正写窗口（docs/benchmarks/stage1-block-overhead-plan.md §2.1）。
    // 本式在 K=2 下为 8，要求 WM_WINDOW_SIZE >= BASES_PER_CYCLE。
    localparam integer PREFILL_BODY =
        (WM_WINDOW_SIZE - BASES_PER_CYCLE + BASES_PER_CYCLE - 1) / BASES_PER_CYCLE;

    // 区域索引与水印存储几何
    localparam integer REGION_W = 6;                     // 0~49
    localparam integer WM_DEPTH = NUM_LC * REF_LEN;      // 50*957 or 50*1055
    localparam integer P_LOG    = CLOG2(P_WAYS);        // 选优树级数 / 位置序号位宽
    localparam integer WM_BANK_DEPTH = (WM_DEPTH + BASES_PER_CYCLE - 1) / BASES_PER_CYCLE;
    localparam integer WM_BANK_AW    = CLOG2(WM_BANK_DEPTH);
    localparam integer PLANE_BANK_DEPTH = (READ_BPS + BASES_PER_CYCLE - 1) / BASES_PER_CYCLE;
    localparam integer WM_WINDOW_SIZE = P_WAYS + BASES_PER_CYCLE - 1;
    localparam integer RUN_GROUPS = (READ_BPS + BASES_PER_CYCLE - 1) / BASES_PER_CYCLE;
    localparam integer SCORE_INC_W = CLOG2(BASES_PER_CYCLE + 1);

    // ----------------------------------------------------------
    // 辅助函数
    // ----------------------------------------------------------
    function integer CLOG2; input integer v; integer t,i; begin
        t=v-1; i=0; while(t>0) begin t=t>>1; i=i+1; end CLOG2=i;
    end endfunction

    // ----------------------------------------------------------
    // 水印 BRAM：按原扁平地址 (LC*REF_LEN+offset) mod K 分 bank，每 bank 一个同步读口。
    // ----------------------------------------------------------
    wire [31:0] wm_wr_addr_lin = bram_sel * REF_LEN + bram_write_addr;
    wire [31:0] wm_wr_addr_wide = wm_wr_addr_lin / BASES_PER_CYCLE;
    wire [WM_BANK_AW-1:0] wm_wr_addr = wm_wr_addr_wide[WM_BANK_AW-1:0];
    wire [31:0] wm_wr_bank = wm_wr_addr_lin % BASES_PER_CYCLE;

    reg  [5:0]       lc_idx;
    reg  [15:0]      wm_rd_offset;
    reg  [WM_BANK_AW-1:0] wm_rd_addr_q [0:BASES_PER_CYCLE-1];
    reg  [1:0]       wm_sym_q [0:BASES_PER_CYCLE-1];
    reg  [15:0]      wm_tag_q, wm_tag_qq;
    reg  [5:0]       wm_tag_lc_q, wm_tag_lc_qq;

    genvar gb;
    generate
        for (gb=0; gb<BASES_PER_CYCLE; gb=gb+1) begin: gen_wm_bank
            (* ram_style="block", rom_style="block" *)
            reg [1:0] mem [0:WM_BANK_DEPTH-1];
            // 本 bank 对应当前扁平连续地址区间中的一个符号地址。
            wire [31:0] wm_rd_addr_lin = lc_idx * REF_LEN + wm_rd_offset;
            wire [15:0] delta = (gb + BASES_PER_CYCLE -
                                  (wm_rd_addr_lin % BASES_PER_CYCLE)) % BASES_PER_CYCLE;
            wire [31:0] raw_symbol = wm_rd_offset + delta;
            wire [15:0] bank_symbol = (raw_symbol >= REF_LEN) ? (REF_LEN-1) : raw_symbol[15:0];
            wire [31:0] read_addr_wide = (lc_idx * REF_LEN + bank_symbol) /
                                         BASES_PER_CYCLE;
            wire [WM_BANK_AW-1:0] read_addr = read_addr_wide[WM_BANK_AW-1:0];
            always @(posedge clk) begin
                wm_rd_addr_q[gb] <= read_addr;
                wm_sym_q[gb] <= mem[wm_rd_addr_q[gb]];
                if (bram_write_en && wm_wr_bank == gb)
                    mem[wm_wr_addr] <= bram_write_data;
            end
        end
    endgenerate

    // 地址标签与 BRAM 输出保持相同的两级同步延迟，用于预填窗口定位。
    always @(posedge clk) begin
        wm_tag_q    <= wm_rd_offset;
        wm_tag_qq   <= wm_tag_q;
        wm_tag_lc_q  <= lc_idx;
        wm_tag_lc_qq <= wm_tag_lc_q;
    end

    wire [1:0] wm_sym_lane [0:BASES_PER_CYCLE-1];
    genvar gwl;
    generate
        for (gwl=0; gwl<BASES_PER_CYCLE; gwl=gwl+1) begin: gen_wm_lane
            wire [15:0] source_addr = wm_tag_qq + gwl;
            wire [31:0] source_abs_addr = wm_tag_lc_qq * REF_LEN +
                ((source_addr >= REF_LEN) ? (REF_LEN-1) : source_addr);
            wire [31:0] source_bank = source_abs_addr % BASES_PER_CYCLE;
            assign wm_sym_lane[gwl] = wm_sym_q[source_bank];
        end
    endgenerate

    // ----------------------------------------------------------
    // 读段位平面：地址 addr mod K 选择 bank，bank 内地址为 addr / K。
    // 每个 bank 各有 Port A 比对读口与 Port B 装载/输出读改写口；不复制整块 RAM。
    // ----------------------------------------------------------
    reg [8:0]  a_addr;
    reg [8:0]  b_addr;
    reg        b_we_lo, b_we_hi;
    reg [63:0] b_lo_d,  b_hi_d;
    wire [63:0] a_lo_q [0:BASES_PER_CYCLE-1];
    wire [63:0] a_hi_q [0:BASES_PER_CYCLE-1];
    wire [63:0] plane_b_lo_q [0:BASES_PER_CYCLE-1];
    wire [63:0] plane_b_hi_q [0:BASES_PER_CYCLE-1];
    wire [63:0] b_lo_q = plane_b_lo_q[b_addr % BASES_PER_CYCLE];
    wire [63:0] b_hi_q = plane_b_hi_q[b_addr % BASES_PER_CYCLE];
    generate
        for (gb=0; gb<BASES_PER_CYCLE; gb=gb+1) begin: gen_plane_bank
            (* ram_style="block" *) reg [63:0] lo_mem [0:PLANE_BANK_DEPTH-1];
            (* ram_style="block" *) reg [63:0] hi_mem [0:PLANE_BANK_DEPTH-1];
            reg [63:0] a_lo_bank_q, a_hi_bank_q;
            reg [63:0] b_lo_bank_q, b_hi_bank_q;
            assign a_lo_q[gb] = a_lo_bank_q;
            assign a_hi_q[gb] = a_hi_bank_q;
            assign plane_b_lo_q[gb] = b_lo_bank_q;
            assign plane_b_hi_q[gb] = b_hi_bank_q;
            always @(posedge clk) begin
                a_lo_bank_q <= lo_mem[a_addr / BASES_PER_CYCLE];
                a_hi_bank_q <= hi_mem[a_addr / BASES_PER_CYCLE];
                b_lo_bank_q <= lo_mem[b_addr / BASES_PER_CYCLE];
                b_hi_bank_q <= hi_mem[b_addr / BASES_PER_CYCLE];
                if (b_we_lo && (b_addr % BASES_PER_CYCLE) == gb)
                    lo_mem[b_addr / BASES_PER_CYCLE] <= b_lo_d;
                if (b_we_hi && (b_addr % BASES_PER_CYCLE) == gb)
                    hi_mem[b_addr / BASES_PER_CYCLE] <= b_hi_d;
            end
        end
    endgenerate

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
    reg [4:0]  upd_wait;     // PIPE_TREE=1 时 S_UPD1 等待选优树流水排空的拍数

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

    // P_WAYS 路并行滑窗移位寄存器
    // wm_win[p] 对应位置 pos_base + p
    reg [1:0] wm_win [0:WM_WINDOW_SIZE-1];

    // P_WAYS 组独立分数累加器：score[p][t]
    reg [SCORE_W-1:0] score [0:P_WAYS-1][0:BATCH-1];

    // P_WAYS 个候选位置有效标志（防止超出 STRIDE 越界，包含 STRIDE 边界）
    // 在 S_LAUNCH 按 pos_cnt 算好并寄存：整组 PREFILL/RUN/UPD 期间 pos_base 不变，
    // 所以与 4-way 的组合写法逐周期等价，但把「pos_base 比较 → 高扇出 → 选优树」
    // 这条 8-way 布线后 -3.058 ns 的关键路径从组合链上拿掉。
    reg  [P_WAYS-1:0] pos_valid;
    genvar gv;

    // 流水选优树第一级寄存器（S_UPD1 -> S_UPD2）
    reg                   stage1_res_valid;
    reg [REGION_W-1:0]    stage1_lc_idx;
    reg [POS_W-1:0]       stage1_pos   [0:BATCH-1];
    reg [SCORE_W-1:0]     stage1_score [0:BATCH-1];
    reg [CODEBITS-1:0]    stage1_cw    [0:BATCH-1];

    // 匹配比较矩阵：match_mask[p][t] 表示位置 p 对读段 t 的当前碱基是否完全一致
    wire [63:0] match_mask [0:P_WAYS*BASES_PER_CYCLE-1];
    generate
        for (gv=0; gv<P_WAYS; gv=gv+1) begin: gen_match
            genvar gmk;
            for (gmk=0; gmk<BASES_PER_CYCLE; gmk=gmk+1) begin: gen_match_lane
                assign match_mask[gv*BASES_PER_CYCLE+gmk] =
                    ~( (a_lo_q[gmk] ^ {64{wm_win[gv+gmk][0]}}) |
                       (a_hi_q[gmk] ^ {64{wm_win[gv+gmk][1]}}) );
            end
        end
    endgenerate

    // 每个候选位置/记录的 K 路匹配数；尾组无效 lane 被屏蔽。
    wire [SCORE_INC_W-1:0] score_inc [0:P_WAYS*BATCH-1];
    genvar gsp, gst;
    generate
        for (gsp=0; gsp<P_WAYS; gsp=gsp+1) begin: gen_score_pos
            for (gst=0; gst<BATCH; gst=gst+1) begin: gen_score_record
                wire [SCORE_INC_W-1:0] sum_lane [0:BASES_PER_CYCLE];
                assign sum_lane[0] = {SCORE_INC_W{1'b0}};
                genvar gsl;
                for (gsl=0; gsl<BASES_PER_CYCLE; gsl=gsl+1) begin: gen_score_lane
                    wire lane_valid = (run_cnt * BASES_PER_CYCLE + gsl < READ_BPS);
                    assign sum_lane[gsl+1] = sum_lane[gsl] +
                        (match_mask[gsp*BASES_PER_CYCLE+gsl][gst] && lane_valid);
                end
                assign score_inc[gsp*BATCH+gst] = sum_lane[BASES_PER_CYCLE];
            end
        end
    endgenerate

    // 选优树（组合）：每条读段一棵 log2(P_WAYS) 级二叉树，堆式编号，
    // 叶子 P_WAYS..2*P_WAYS-1 对应位置 0..P_WAYS-1，根为 1 号节点。
    // 节点规则「左 >= 右取左」→ 最大分数，并列取最低序号（与 4-way 相同）。
    // 无效叶子分数置 0：它们只出现在有效叶子右侧，并列时必然输给左侧。
    // 各读段树根按 t 拼成扁平向量，供状态机用变量下标 +: 取出
    wire [SCORE_W*BATCH-1:0] tree_sc_flat;
    wire [P_LOG*BATCH-1:0]   tree_p_flat;
    generate
        for (gv=0; gv<BATCH; gv=gv+1) begin: gen_tree
            wire [SCORE_W-1:0] ns [1:2*P_WAYS-1];
            wire [P_LOG-1:0]   np [1:2*P_WAYS-1];
            genvar gl;
            for (gl=0; gl<P_WAYS; gl=gl+1) begin: gen_leaf
                assign ns[P_WAYS+gl] = pos_valid[gl] ? score[gl][gv] : {SCORE_W{1'b0}};
                assign np[P_WAYS+gl] = gl;
            end
            for (gl=1; gl<P_WAYS; gl=gl+1) begin: gen_node
                wire               take_l = (ns[2*gl] >= ns[2*gl+1]);
                wire [SCORE_W-1:0] s_d    = take_l ? ns[2*gl] : ns[2*gl+1];
                wire [P_LOG-1:0]   p_d    = take_l ? np[2*gl] : np[2*gl+1];
                if (PIPE_TREE != 0) begin: gen_q
                    // 每个节点一级寄存器：叶子（score）冻结后第 k 拍，第 k 层才反映终值；
                    // S_UPD1 等满 P_LOG 拍再取根，见状态机。
                    reg [SCORE_W-1:0] s_q;
                    reg [P_LOG-1:0]   p_q;
                    always @(posedge clk) begin
                        s_q <= s_d;
                        p_q <= p_d;
                    end
                    assign ns[gl] = s_q;
                    assign np[gl] = p_q;
                end else begin: gen_c
                    assign ns[gl] = s_d;
                    assign np[gl] = p_d;
                end
            end
            assign tree_sc_flat[gv*SCORE_W +: SCORE_W] = ns[1];
            assign tree_p_flat [gv*P_LOG   +: P_LOG]   = np[1];
        end
    endgenerate

    // 输出装载阶段
    reg [5:0]  emit_idx;
    reg [8:0]  emit_i;
    reg [CODEBITS-1:0] cw_acc;

    wire [15:0] region_mul_stride = best_region[emit_idx] * STRIDE;
    wire [POS_W-1:0] global_pos   = region_mul_stride + best_pos[emit_idx];

    integer p, t, k;

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
            pos_valid        <= {P_WAYS{1'b0}};
            upd_wait         <= 5'd0;
            for (t=0; t<BATCH; t=t+1) begin
                best_sc[t]      <= {SCORE_W{1'b0}};
                best_pos[t]     <= {POS_W{1'b0}};
                best_region[t]  <= {REGION_W{1'b0}};
                stage1_score[t] <= {SCORE_W{1'b0}};
                stage1_pos[t]   <= {POS_W{1'b0}};
                stage1_cw[t]    <= {CODEBITS{1'b0}};
                for (p=0; p<P_WAYS; p=p+1) score[p][t] <= {SCORE_W{1'b0}};
            end
            for (p=0; p<WM_WINDOW_SIZE; p=p+1) wm_win[p] <= 2'b00;
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
                    upd_wait         <= 5'd0;
                    for (p=0; p<P_WAYS; p=p+1) pos_valid[p] <= (pos_cnt + p <= STRIDE);
                    pre_cnt          <= 0;
                    run_cnt          <= 0;
                    stage1_res_valid <= 1'b0;
                    for (t=0; t<BATCH; t=t+1) begin
                        for (p=0; p<P_WAYS; p=p+1) score[p][t] <= {SCORE_W{1'b0}};
                    end
                    for (p=0; p<WM_WINDOW_SIZE; p=p+1) wm_win[p] <= 2'b00;
                    wm_rd_offset <= pos_cnt;
                    st <= S_PREFILL;
                end

                // 预充填 PREFILL_BODY+3 拍（K=2 时 11 拍，原为 18 拍）：组装初始窗口，
                // 末三拍预取 RUN 前两组。地址序列的首尾两段与改前逐项相同。
                S_PREFILL: begin
                    pre_cnt <= pre_cnt + 1'b1;

                    if (wm_tag_lc_qq == lc_idx) begin
                        for (k=0; k<BASES_PER_CYCLE; k=k+1) begin
                            if ((wm_tag_qq + k >= pos_base) &&
                                (wm_tag_qq + k < pos_base + WM_WINDOW_SIZE)) begin
                                wm_win[wm_tag_qq + k - pos_base] <= wm_sym_lane[k];
                            end
                        end
                    end

                    if (pre_cnt < PREFILL_BODY) begin
                        wm_rd_offset <= pos_base + (pre_cnt + 1) * BASES_PER_CYCLE;
                    end else if (pre_cnt == PREFILL_BODY) begin
                        wm_rd_offset <= pos_base + WM_WINDOW_SIZE;
                    end else if (pre_cnt == PREFILL_BODY+1) begin
                        wm_rd_offset <= pos_base + WM_WINDOW_SIZE + BASES_PER_CYCLE;
                    end else if (pre_cnt == PREFILL_BODY+2) begin
                        wm_rd_offset <= pos_base + WM_WINDOW_SIZE + 2*BASES_PER_CYCLE;
                    end

                    if (pre_cnt == PREFILL_BODY+1) begin
                        a_addr <= 9'd0;
                    end else if (pre_cnt == PREFILL_BODY+2) begin
                        a_addr <= BASES_PER_CYCLE;
                    end

                    if (pre_cnt == PREFILL_BODY+2) begin
                        run_cnt <= 0;
                        st <= S_RUN;
                    end
                end

                // 每拍比较 K 个连续碱基；最后一组的越界 lane 由 score_inc 屏蔽。
                S_RUN: begin
                    run_cnt <= run_cnt + 1'b1;

                    for (p=0; p<P_WAYS; p=p+1) begin
                        if (pos_valid[p]) begin
                            for (t=0; t<BATCH; t=t+1) begin
                                score[p][t] <= score[p][t] + score_inc[p*BATCH+t];
                            end
                        end
                    end

                    for (p=0; p<WM_WINDOW_SIZE-BASES_PER_CYCLE; p=p+1)
                        wm_win[p] <= wm_win[p+BASES_PER_CYCLE];
                    for (k=0; k<BASES_PER_CYCLE; k=k+1)
                        wm_win[WM_WINDOW_SIZE-BASES_PER_CYCLE+k] <= wm_sym_lane[k];

                    if (run_cnt + 2 < RUN_GROUPS) begin
                        a_addr <= (run_cnt + 2) * BASES_PER_CYCLE;
                    end
                    wm_rd_offset <= pos_base + WM_WINDOW_SIZE +
                                    (run_cnt + 3) * BASES_PER_CYCLE;

                    if (run_cnt == RUN_GROUPS - 1) begin
                        st <= S_UPD1;
                    end
                end

                // 选优流水级 1：P_WAYS 选 1 局部选优（组合树 gen_tree），结果打入流水寄存器
                S_UPD1: begin
                    if (PIPE_TREE != 0 && upd_wait != P_LOG) begin
                        upd_wait <= upd_wait + 1'b1;
                    end else begin
                        stage1_res_valid <= 1'b1;
                        stage1_lc_idx    <= lc_idx;
                        for (t=0; t<BATCH; t=t+1) begin
                            stage1_score[t] <= tree_sc_flat[t*SCORE_W +: SCORE_W];
                            stage1_pos[t]   <= pos_base + tree_p_flat[t*P_LOG +: P_LOG];
                        end
                        st <= S_UPD2;
                    end
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

                // 步进推进：每次前进 P_WAYS 个位置
                S_NEXT: begin
                    if (pos_cnt + P_WAYS > STRIDE) begin
                        pos_cnt <= 16'd0;
                        if (lc_idx == NUM_LC-1) begin
                            emit_idx <= 0; emit_i <= 0; cw_acc <= {CODEBITS{1'b0}};
                            st <= S_EMIT;
                        end else begin
                            lc_idx <= lc_idx + 1'b1;
                            st     <= S_LAUNCH;
                        end
                    end else begin
                        pos_cnt <= pos_cnt + P_WAYS;
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
