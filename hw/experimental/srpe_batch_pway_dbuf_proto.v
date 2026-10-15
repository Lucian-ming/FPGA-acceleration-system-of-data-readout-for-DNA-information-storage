// ============================================================================
// File: srpe_batch_pway_dbuf_proto.v
// Desc: 64-read batch engine, bit-plane BRAM, P_WAYS-position sliding window
// ----------------------------------------------------------------------------
// 非生产周期级双缓冲原型：算法体复制自生产 P-way 核，调度拆为装载/扫描/发放。
// 不接入 component.xml；此文件不提供整机资源、时序或板测证据。
// 默认几何为SE150；顶层仍显式透传全部几何参数。
// 2026-10-14：每拍碱基数 K 已由可配置参数**写死为 2**（见下方 localparam BASES_PER_CYCLE）。
//   写死前 K 是 parameter，顶层/BD/component/xgui 均有传参通道，现已全部撤销；
//   K=2 已由 tb_dna_stage1_p16_equivalence.v 以「生产P4 + 独立oracle」双重逐位判定通过。
// 左>=右取左，保证并列取低位置；pos_valid在S_LAUNCH寄存且包含STRIDE边界；
// PIPE_TREE=1逐级打拍，S_UPD1等待log2(P)拍，保留同步BRAM装载/输出协议。
// Port A 扫描当前 bank，Port B 在两个 bank 间共享给装载器与发放器。
// ----------------------------------------------------------------------------
// Synth: Verilog-2001
// ============================================================================
`timescale 1 ns / 1 ps

(* keep_hierarchy = "yes" *)
module srpe_batch_pway_dbuf_proto #(
    parameter integer BATCH_COUNT = 3,     // 一次启动连续处理的批次数（仅原型）
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
    input  wire                   clear_counters, // 新任务开始脉冲；不改变引擎控制状态

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
    output reg                    done,

    // Stage1 累计计数器：clear_counters 在每个任务的 start 上升沿清零，
    // 后续各个 64-read 引擎批次累加，直到下一个任务开始。
    // STAGE1_CYCLE_COUNTERS 默认未定义；仅仪表化构建显式定义它。
    output wire [31:0]             cycles_total,
    output wire [31:0]             cycles_prefill,
    output wire [31:0]             cycles_run,
    output wire [31:0]             cycles_tree,
    output wire [31:0]             blocks_done,
    output wire [31:0]             batches_done
);

    localparam integer CODEBITS = READ_BPS*2;
    localparam integer RESULT_W = CODEBITS + POS_W + SCORE_W;

    // 2026-10-14 冻结：每拍推进 2 个碱基。原为可配置 parameter（支持 1/2/4），
    // 整机 route 实测 K=4 硬失败（LUT 63,246 > 容量 53,200），K=2 通过
    // （35,702 LUT / WNS +0.313 / 0 失败端点），故写死为 2 并撤销全部构建期传参通道。
    // 依据与判据见 docs/benchmarks/stage1-multibase-ooc-probe.md。
    // 读段 150 个碱基被 K 整除（150/2=75），故 score_inc 的末组掩码路径在本配置下恒为真。
    localparam integer BASES_PER_CYCLE = 2;

    // 区域索引与水印存储几何
    localparam integer REGION_W = 6;                     // 0~49
    localparam integer WM_DEPTH = NUM_LC * REF_LEN;      // 50*957 or 50*1055
    localparam integer P_LOG    = CLOG2(P_WAYS);        // 选优树级数 / 位置序号位宽
    localparam integer WM_BANK_DEPTH = (WM_DEPTH + BASES_PER_CYCLE - 1) / BASES_PER_CYCLE;
    localparam integer WM_BANK_AW    = CLOG2(WM_BANK_DEPTH);
    localparam integer PLANE_BANK_DEPTH = (READ_BPS + BASES_PER_CYCLE - 1) / BASES_PER_CYCLE;
    localparam integer WM_WINDOW_SIZE = P_WAYS + BASES_PER_CYCLE - 1;

    // 【压缩项 A，2026-10-14】预充填只需发出「返回后会落进窗口」的那几组地址。
    // 窗口 17 深、每拍进 K 个；S_LAUNCH 已用 pos_cnt 那一个地址覆盖了窗口的前 K 项，
    // 故还差 ceil((WM_WINDOW_SIZE-K)/K) 组。原写法按 P_WAYS-1 = 15 组发，其中
    // 7 组返回的 tag 落在窗口外、被位置守卫丢弃 —— 实测：18 拍预充填里只有
    // 9.02 拍真正写窗口（docs/benchmarks/stage1-block-overhead-plan.md §2.1）。
    // 本式在 K=2 下为 8，要求 WM_WINDOW_SIZE >= BASES_PER_CYCLE。
    // ⚠️ 位置必须在 WM_WINDOW_SIZE **之后**——它引用了后者，写前面会被判"声明前引用"
    // （Vivado 会出告警；虽然当前能两遍展开算对，但不能依赖这一点）。
    localparam integer PREFILL_BODY =
        (WM_WINDOW_SIZE - BASES_PER_CYCLE + BASES_PER_CYCLE - 1) / BASES_PER_CYCLE;

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
    // 读段位平面双 bank 原型。每 bank 仍按 BASES_PER_CYCLE 拆符号 lane。
    // Port A 只服务正在扫描的 scan_bank；Port B 由装载器/发放器共享仲裁。
    reg [8:0] a_addr;
    reg [8:0] ld_b_addr, em_b_addr;
    reg [63:0] ld_b_lo_d, ld_b_hi_d;
    reg ld_b_we_lo, ld_b_we_hi;
    wire [8:0] b_addr = load_busy ? ld_b_addr : em_b_addr;
    wire b_bank = load_busy ? load_bank : emit_bank;
    wire [63:0] a_lo_q [0:BASES_PER_CYCLE-1];
    wire [63:0] a_hi_q [0:BASES_PER_CYCLE-1];
    wire [63:0] plane_b_lo_q [0:BASES_PER_CYCLE-1];
    wire [63:0] plane_b_hi_q [0:BASES_PER_CYCLE-1];
    wire [63:0] b_lo_q = plane_b_lo_q[b_addr % BASES_PER_CYCLE];
    wire [63:0] b_hi_q = plane_b_hi_q[b_addr % BASES_PER_CYCLE];
    generate
        for (gb=0; gb<BASES_PER_CYCLE; gb=gb+1) begin: gen_plane_bank
            (* ram_style="block" *) reg [63:0] lo_mem [0:1][0:PLANE_BANK_DEPTH-1];
            (* ram_style="block" *) reg [63:0] hi_mem [0:1][0:PLANE_BANK_DEPTH-1];
            reg [63:0] a_lo_bank_q, a_hi_bank_q;
            reg [63:0] b_lo_bank_q, b_hi_bank_q;
            assign a_lo_q[gb] = a_lo_bank_q;
            assign a_hi_q[gb] = a_hi_bank_q;
            assign plane_b_lo_q[gb] = b_lo_bank_q;
            assign plane_b_hi_q[gb] = b_hi_bank_q;
            always @(posedge clk) begin
                a_lo_bank_q <= lo_mem[scan_bank][a_addr / BASES_PER_CYCLE];
                a_hi_bank_q <= hi_mem[scan_bank][a_addr / BASES_PER_CYCLE];
                b_lo_bank_q <= lo_mem[b_bank][b_addr / BASES_PER_CYCLE];
                b_hi_bank_q <= hi_mem[b_bank][b_addr / BASES_PER_CYCLE];
                if (ld_b_we_lo && (ld_b_addr % BASES_PER_CYCLE) == gb)
                    lo_mem[load_bank][ld_b_addr / BASES_PER_CYCLE] <= ld_b_lo_d;
                if (ld_b_we_hi && (ld_b_addr % BASES_PER_CYCLE) == gb)
                    hi_mem[load_bank][ld_b_addr / BASES_PER_CYCLE] <= ld_b_hi_d;
            end
        end
    endgenerate

    // 三个独立时序域：单一扫描器、单一 Port-B 所有者、双 bank 生命周期调度。
    localparam [3:0] S_WAIT=4'd0, S_INITC=4'd1, S_LAUNCH=4'd2,
                     S_PREFILL=4'd3, S_RUN=4'd4, S_UPD1=4'd5,
                     S_UPD2=4'd6, S_NEXT=4'd7;
    localparam [1:0] LD_IDLE=2'd0, LD_WAIT_CW=2'd1,
                     LD_LOAD_R=2'd2, LD_DRAIN=2'd3;
    localparam [2:0] EM_IDLE=3'd0, EM_ADDR=3'd1, EM_WAIT=3'd2,
                     EM_CAPTURE=3'd3, EM_FINAL=3'd4;
    localparam [2:0] BK_FREE=3'd0, BK_LOADING=3'd1, BK_READY=3'd2,
                     BK_RUNNING=3'd3, BK_WAIT_EMIT=3'd4, BK_EMITTING=3'd5;

    reg [3:0] st;
    reg [1:0] ld_state;
    reg [2:0] em_state;
    reg [4:0] upd_wait;
    reg [6:0] cw_idx;
    reg [8:0] row_i;
    reg [1:0] phase;
    reg [5:0] bit_sel;
    reg [READ_BPS-1:0] cw_hi_sr, cw_lo_sr;
    reg [15:0] pos_cnt, pos_base;
    reg [8:0] pre_cnt, run_cnt;
    reg [SCORE_W-1:0] best_sc [0:BATCH-1];
    reg [POS_W-1:0] best_pos [0:BATCH-1];
    reg [REGION_W-1:0] best_region [0:BATCH-1];
    reg [1:0] wm_win [0:WM_WINDOW_SIZE-1];
    reg [SCORE_W-1:0] score [0:P_WAYS-1][0:BATCH-1];
    reg [P_WAYS-1:0] pos_valid;
    genvar gv;
    reg stage1_res_valid;
    reg [REGION_W-1:0] stage1_lc_idx;
    reg [POS_W-1:0] stage1_pos [0:BATCH-1];
    reg [SCORE_W-1:0] stage1_score [0:BATCH-1];

    // 每个 bank 保存该批次的输出元数据，避免后续扫描覆盖前一批结果。
    reg [SCORE_W-1:0] meta_best_sc [0:1][0:BATCH-1];
    reg [POS_W-1:0] meta_best_pos [0:1][0:BATCH-1];
    reg [REGION_W-1:0] meta_best_region [0:1][0:BATCH-1];
    reg [2:0] bank_state [0:1];
    reg [15:0] bank_batch [0:1];
    reg [15:0] next_load_batch, output_count;
    reg load_busy, scan_busy, emit_busy;
    reg load_start, emit_start, comp_start;
    reg load_bank, emit_bank, scan_bank;
    reg [15:0] load_batch;
    reg [8:0] emit_i;
    reg [6:0] emit_idx;
    reg [CODEBITS-1:0] cw_acc;
    reg [CODEBITS+POS_W+SCORE_W-1:0] emit_result;
    wire [15:0] emit_global_pos =
        meta_best_region[emit_bank][emit_idx] * STRIDE +
        meta_best_pos[emit_bank][emit_idx];
    wire [RESULT_W-1:0] emit_packed =
        {cw_acc, emit_global_pos, meta_best_sc[emit_bank][emit_idx]};
    reg load_done, compute_done, emit_done;
    integer p, t, k;

    wire ready0 = (bank_state[0] == BK_READY);
    wire ready1 = (bank_state[1] == BK_READY);
    wire ready_valid = ready0 || ready1;
    wire ready_bank = ready1 && (!ready0 || bank_batch[1] < bank_batch[0]);
    wire emit_wait0 = (bank_state[0] == BK_WAIT_EMIT);
    wire emit_wait1 = (bank_state[1] == BK_WAIT_EMIT);
    wire emit_wait_valid = emit_wait0 || emit_wait1;
    wire emit_wait_bank = emit_wait1 && (!emit_wait0 || bank_batch[1] < bank_batch[0]);
    wire free0 = (bank_state[0] == BK_FREE);
    wire free1 = (bank_state[1] == BK_FREE);
    wire free_valid = free0 || free1;
    wire free_bank = free1 && !free0;

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

    // 本原型的时间域划分：load、scan、emit 三个 FSM 可并行；load 与 emit
    // 共用单个 Port-B 所有权，调度器保证它们不会同拍访问位平面。
    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            busy <= 1'b0;
            done <= 1'b0;
            load_start <= 1'b0;
            emit_start <= 1'b0;
            comp_start <= 1'b0;
            load_busy <= 1'b0;
            scan_busy <= 1'b0;
            emit_busy <= 1'b0;
            load_bank <= 1'b0;
            emit_bank <= 1'b0;
            scan_bank <= 1'b0;
            load_batch <= 16'd0;
            next_load_batch <= 16'd0;
            output_count <= 16'd0;
            bank_state[0] <= BK_FREE;
            bank_state[1] <= BK_FREE;
            bank_batch[0] <= 16'd0;
            bank_batch[1] <= 16'd0;
        end else begin
            done <= 1'b0;
            load_start <= 1'b0;
            emit_start <= 1'b0;
            comp_start <= 1'b0;
            if (!busy && start_batch) begin
                busy <= 1'b1;
                output_count <= 16'd0;
                next_load_batch <= 16'd1;
                bank_state[0] <= BK_LOADING;
                bank_state[1] <= BK_FREE;
                bank_batch[0] <= 16'd0;
                load_bank <= 1'b0;
                load_batch <= 16'd0;
                load_busy <= 1'b1;
                load_start <= 1'b1;
            end else if (busy) begin
                if (load_done) begin
                    load_busy <= 1'b0;
                    bank_state[load_bank] <= BK_READY;
                    bank_batch[load_bank] <= load_batch;
                end
                if (compute_done) begin
                    scan_busy <= 1'b0;
                    bank_state[scan_bank] <= BK_WAIT_EMIT;
                end
                if (emit_done) begin
                    emit_busy <= 1'b0;
                    bank_state[emit_bank] <= BK_FREE;
                    output_count <= output_count + 1'b1;
                    if (output_count + 1'b1 >= BATCH_COUNT) begin
                        busy <= 1'b0;
                        done <= 1'b1;
                    end
                end

                // 扫描器按批次序处理 READY bank，与 Port-B 活动互不争用。
                if (!scan_busy && ready_valid) begin
                    scan_bank <= ready_bank;
                    bank_state[ready_bank] <= BK_RUNNING;
                    scan_busy <= 1'b1;
                    comp_start <= 1'b1;
                end

                // Port-B 优先继续装入未来批次；没有待装批次时发放已扫描结果。
                if (!load_busy && !emit_busy &&
                    (next_load_batch < BATCH_COUNT) && free_valid) begin
                    load_bank <= free_bank;
                    load_batch <= next_load_batch;
                    bank_batch[free_bank] <= next_load_batch;
                    bank_state[free_bank] <= BK_LOADING;
                    next_load_batch <= next_load_batch + 1'b1;
                    load_busy <= 1'b1;
                    load_start <= 1'b1;
                end else if (!load_busy && !emit_busy && emit_wait_valid) begin
                    emit_bank <= emit_wait_bank;
                    bank_state[emit_wait_bank] <= BK_EMITTING;
                    emit_busy <= 1'b1;
                    emit_start <= 1'b1;
                end
            end
        end
    end

    // 输入装载 FSM：cw_req/cw_valid 每批顺序握手；三拍/位置与生产 S_LOAD_R
    // 对齐，末拍的同步 BRAM 写在 LD_DRAIN 周期提交。
    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            ld_state <= LD_IDLE;
            cw_req <= 1'b0;
            cw_idx <= 7'd0;
            row_i <= 9'd0;
            phase <= 2'd0;
            bit_sel <= 6'd0;
            cw_hi_sr <= {READ_BPS{1'b0}};
            cw_lo_sr <= {READ_BPS{1'b0}};
            ld_b_addr <= 9'd0;
            ld_b_lo_d <= 64'd0;
            ld_b_hi_d <= 64'd0;
            ld_b_we_lo <= 1'b0;
            ld_b_we_hi <= 1'b0;
            load_done <= 1'b0;
        end else begin
            cw_req <= 1'b0;
            ld_b_we_lo <= 1'b0;
            ld_b_we_hi <= 1'b0;
            load_done <= 1'b0;
            if (load_start) begin
                cw_idx <= 7'd0;
                row_i <= 9'd0;
                phase <= 2'd0;
                bit_sel <= 6'd0;
                ld_state <= LD_WAIT_CW;
            end else begin
                case (ld_state)
                    LD_IDLE: begin end
                    LD_WAIT_CW: begin
                        cw_req <= 1'b1;
                        if (cw_valid) begin
                            row_i <= 9'd0;
                            phase <= 2'd0;
                            cw_hi_sr <= cw_data[READ_BPS-1:0];
                            cw_lo_sr <= cw_data[CODEBITS-1:READ_BPS];
                            ld_state <= LD_LOAD_R;
                        end
                    end
                    LD_LOAD_R: begin
                        if (phase == 2'd0) begin
                            ld_b_addr <= row_i;
                            phase <= 2'd1;
                        end else if (phase == 2'd1) begin
                            phase <= 2'd2;
                        end else begin
                            ld_b_hi_d <= cw_hi_sr[0] ?
                                (b_hi_q | (64'h1 << bit_sel)) :
                                (b_hi_q & ~(64'h1 << bit_sel));
                            ld_b_lo_d <= cw_lo_sr[0] ?
                                (b_lo_q | (64'h1 << bit_sel)) :
                                (b_lo_q & ~(64'h1 << bit_sel));
                            cw_hi_sr <= {1'b0, cw_hi_sr[READ_BPS-1:1]};
                            cw_lo_sr <= {1'b0, cw_lo_sr[READ_BPS-1:1]};
                            ld_b_we_lo <= 1'b1;
                            ld_b_we_hi <= 1'b1;
                            phase <= 2'd0;
                            if (row_i == READ_BPS-1) begin
                                if (cw_idx == BATCH-1) begin
                                    ld_state <= LD_DRAIN;
                                end else begin
                                    cw_idx <= cw_idx + 1'b1;
                                    bit_sel <= bit_sel + 1'b1;
                                    ld_state <= LD_WAIT_CW;
                                end
                            end else begin
                                row_i <= row_i + 1'b1;
                            end
                        end
                    end
                    LD_DRAIN: begin
                        load_done <= 1'b1;
                        ld_state <= LD_IDLE;
                    end
                    default: ld_state <= LD_IDLE;
                endcase
            end
        end
    end

    // 扫描 FSM：从 scan_bank 的 Port-A 位平面读数；算法体与生产 P-way 保持一致。
    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            st <= S_WAIT;
            lc_idx <= 6'd0;
            pos_cnt <= 16'd0;
            pos_base <= 16'd0;
            pre_cnt <= 9'd0;
            run_cnt <= 9'd0;
            a_addr <= 9'd0;
            wm_rd_offset <= 16'd0;
            stage1_res_valid <= 1'b0;
            stage1_lc_idx <= {REGION_W{1'b0}};
            pos_valid <= {P_WAYS{1'b0}};
            upd_wait <= 5'd0;
            compute_done <= 1'b0;
            for (t=0; t<BATCH; t=t+1) begin
                best_sc[t] <= {SCORE_W{1'b0}};
                best_pos[t] <= {POS_W{1'b0}};
                best_region[t] <= {REGION_W{1'b0}};
                stage1_score[t] <= {SCORE_W{1'b0}};
                stage1_pos[t] <= {POS_W{1'b0}};
                for (p=0; p<P_WAYS; p=p+1) score[p][t] <= {SCORE_W{1'b0}};
            end
            for (p=0; p<WM_WINDOW_SIZE; p=p+1) wm_win[p] <= 2'b00;
        end else begin
            compute_done <= 1'b0;
            if (comp_start) begin
                st <= S_INITC;
            end else begin
                case (st)
                    S_WAIT: begin end
                    S_INITC: begin
                        lc_idx <= 0;
                        pos_cnt <= 0;
                        pos_base <= 0;
                        stage1_res_valid <= 1'b0;
                        stage1_lc_idx <= {REGION_W{1'b0}};
                        for (t=0; t<BATCH; t=t+1) begin
                            best_sc[t] <= {SCORE_W{1'b0}};
                            best_pos[t] <= {POS_W{1'b0}};
                            best_region[t] <= {REGION_W{1'b0}};
                            stage1_score[t] <= {SCORE_W{1'b0}};
                            stage1_pos[t] <= {POS_W{1'b0}};
                            meta_best_sc[scan_bank][t] <= {SCORE_W{1'b0}};
                            meta_best_pos[scan_bank][t] <= {POS_W{1'b0}};
                            meta_best_region[scan_bank][t] <= {REGION_W{1'b0}};
                        end
                        st <= S_LAUNCH;
                    end
                    S_LAUNCH: begin
                        pos_base <= pos_cnt;
                        upd_wait <= 5'd0;
                        for (p=0; p<P_WAYS; p=p+1) pos_valid[p] <= (pos_cnt + p <= STRIDE);
                        pre_cnt <= 0;
                        run_cnt <= 0;
                        stage1_res_valid <= 1'b0;
                        for (t=0; t<BATCH; t=t+1)
                            for (p=0; p<P_WAYS; p=p+1) score[p][t] <= {SCORE_W{1'b0}};
                        for (p=0; p<WM_WINDOW_SIZE; p=p+1) wm_win[p] <= 2'b00;
                        wm_rd_offset <= pos_cnt;
                        st <= S_PREFILL;
                    end
                    S_PREFILL: begin
                        pre_cnt <= pre_cnt + 1'b1;
                        if (wm_tag_lc_qq == lc_idx) begin
                            for (k=0; k<BASES_PER_CYCLE; k=k+1) begin
                                if ((wm_tag_qq + k >= pos_base) &&
                                    (wm_tag_qq + k < pos_base + WM_WINDOW_SIZE))
                                    wm_win[wm_tag_qq + k - pos_base] <= wm_sym_lane[k];
                            end
                        end
                        if (pre_cnt < PREFILL_BODY)
                            wm_rd_offset <= pos_base + (pre_cnt + 1) * BASES_PER_CYCLE;
                        else if (pre_cnt == PREFILL_BODY)
                            wm_rd_offset <= pos_base + WM_WINDOW_SIZE;
                        else if (pre_cnt == PREFILL_BODY+1)
                            wm_rd_offset <= pos_base + WM_WINDOW_SIZE + BASES_PER_CYCLE;
                        else if (pre_cnt == PREFILL_BODY+2)
                            wm_rd_offset <= pos_base + WM_WINDOW_SIZE + 2*BASES_PER_CYCLE;
                        if (pre_cnt == PREFILL_BODY+1)
                            a_addr <= 9'd0;
                        else if (pre_cnt == PREFILL_BODY+2)
                            a_addr <= BASES_PER_CYCLE;
                        if (pre_cnt == PREFILL_BODY+2) begin
                            run_cnt <= 0;
                            st <= S_RUN;
                        end
                    end
                    S_RUN: begin
                        run_cnt <= run_cnt + 1'b1;
                        for (p=0; p<P_WAYS; p=p+1) begin
                            if (pos_valid[p]) begin
                                for (t=0; t<BATCH; t=t+1)
                                    score[p][t] <= score[p][t] + score_inc[p*BATCH+t];
                            end
                        end
                        for (p=0; p<WM_WINDOW_SIZE-BASES_PER_CYCLE; p=p+1)
                            wm_win[p] <= wm_win[p+BASES_PER_CYCLE];
                        for (k=0; k<BASES_PER_CYCLE; k=k+1)
                            wm_win[WM_WINDOW_SIZE-BASES_PER_CYCLE+k] <= wm_sym_lane[k];
                        if (run_cnt + 2 < RUN_GROUPS)
                            a_addr <= (run_cnt + 2) * BASES_PER_CYCLE;
                        wm_rd_offset <= pos_base + WM_WINDOW_SIZE +
                                        (run_cnt + 3) * BASES_PER_CYCLE;
                        if (run_cnt == RUN_GROUPS - 1) st <= S_UPD1;
                    end
                    S_UPD1: begin
                        if (PIPE_TREE != 0 && upd_wait != P_LOG) begin
                            upd_wait <= upd_wait + 1'b1;
                        end else begin
                            stage1_res_valid <= 1'b1;
                            stage1_lc_idx <= lc_idx;
                            for (t=0; t<BATCH; t=t+1) begin
                                stage1_score[t] <= tree_sc_flat[t*SCORE_W +: SCORE_W];
                                stage1_pos[t] <= pos_base + tree_p_flat[t*P_LOG +: P_LOG];
                            end
                            st <= S_UPD2;
                        end
                    end
                    S_UPD2: begin
                        for (t=0; t<BATCH; t=t+1) begin
                            if (stage1_res_valid && (stage1_score[t] > best_sc[t])) begin
                                best_sc[t] <= stage1_score[t];
                                best_pos[t] <= stage1_pos[t];
                                best_region[t] <= stage1_lc_idx;
                                meta_best_sc[scan_bank][t] <= stage1_score[t];
                                meta_best_pos[scan_bank][t] <= stage1_pos[t];
                                meta_best_region[scan_bank][t] <= stage1_lc_idx;
                            end
                        end
                        stage1_res_valid <= 1'b0;
                        st <= S_NEXT;
                    end
                    S_NEXT: begin
                        if (pos_cnt + P_WAYS > STRIDE) begin
                            pos_cnt <= 16'd0;
                            if (lc_idx == NUM_LC-1) begin
                                st <= S_WAIT;
                                compute_done <= 1'b1;
                            end else begin
                                lc_idx <= lc_idx + 1'b1;
                                st <= S_LAUNCH;
                            end
                        end else begin
                            pos_cnt <= pos_cnt + P_WAYS;
                            st <= S_LAUNCH;
                        end
                    end
                    default: st <= S_WAIT;
                endcase
            end
        end
    end

    // 发放 FSM：cw/pos/score 均从完成扫描的同一 bank 取；FINAL 持有完整记录，
    // 直到 res_full 拉低才写出，因而满反馈不会丢记录或推进 emit_idx。
    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            em_state <= EM_IDLE;
            emit_i <= 9'd0;
            emit_idx <= 7'd0;
            cw_acc <= {CODEBITS{1'b0}};
            res_wr <= 1'b0;
            res_din <= {RESULT_W{1'b0}};
            em_b_addr <= 9'd0;
            emit_done <= 1'b0;
        end else begin
            res_wr <= 1'b0;
            emit_done <= 1'b0;
            if (emit_start) begin
                emit_i <= 9'd0;
                emit_idx <= 7'd0;
                cw_acc <= {CODEBITS{1'b0}};
                em_state <= EM_ADDR;
            end else begin
                case (em_state)
                    EM_IDLE: begin end
                    EM_ADDR: begin
                        if (!res_full) begin
                            em_b_addr <= emit_i;
                            em_state <= EM_WAIT;
                        end
                    end
                    EM_WAIT: em_state <= EM_CAPTURE;
                    EM_CAPTURE: begin
                        cw_acc[emit_i] <= b_hi_q[emit_idx];
                        cw_acc[READ_BPS + emit_i] <= b_lo_q[emit_idx];
                        if (emit_i == READ_BPS-1) begin
                            emit_i <= 9'd0;
                            em_state <= EM_FINAL;
                        end else begin
                            emit_i <= emit_i + 1'b1;
                            em_state <= EM_ADDR;
                        end
                    end
                    EM_FINAL: begin
                        if (!res_full) begin
                            res_din <= emit_packed;
                            res_wr <= 1'b1;
                            cw_acc <= {CODEBITS{1'b0}};
                            if (emit_idx == BATCH-1) begin
                                emit_done <= 1'b1;
                                em_state <= EM_IDLE;
                            end else begin
                                emit_idx <= emit_idx + 1'b1;
                                em_state <= EM_ADDR;
                            end
                        end
                    end
                    default: em_state <= EM_IDLE;
                endcase
            end
        end
    end

    // 计数端口仅为与生产模块接口保持一致；周期证据由 TB 按各 FSM 状态采样。
    assign cycles_total = 32'd0;
    assign cycles_prefill = 32'd0;
    assign cycles_run = 32'd0;
    assign cycles_tree = 32'd0;
    assign blocks_done = 32'd0;
    assign batches_done = 32'd0;

endmodule
