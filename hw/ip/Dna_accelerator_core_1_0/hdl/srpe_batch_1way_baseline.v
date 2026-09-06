// =============================================================
// File: srpe_batch.v
// Desc : 64-read batch engine using bit-plane BRAM
//        - 水印与位平面存储均推导为 BRAM，采用同步读
//        - 比对阶段由 pos_base 固化当前位置，避免流水线位置漂移
//        - 数据通路按 8x8 分组，降低扇出和组合路径压力
//        - 水印 BRAM 使用线性地址 lc*REF_LEN + row
//        - region_mul_stride 保留完整中间位宽
// Synth: Verilog-2001
// =============================================================
`timescale 1 ns / 1 ps

(* keep_hierarchy = "yes" *)
module srpe_batch #(
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
    localparam integer WM_DEPTH = NUM_LC * REF_LEN;      // 50*957
    localparam integer WM_AW = CLOG2(WM_DEPTH);

    // ----------------------------------------------------------
    // 辅助函数
    // ----------------------------------------------------------
    function integer CLOG2; input integer v; integer t,i; begin
        t=v-1; i=0; while(t>0) begin t=t>>1; i=i+1; end CLOG2=i;
    end endfunction

    // 常量乘法 MUL1055
    // 1055 = 1024 + 16 + 8 + 4 + 2 + 1
    //      = 2^10 + 2^4 + 2^3 + 2^2 + 2^1 + 2^0
    function [15:0] MUL1055; 
        input [15:0] x; 
    begin
        MUL1055 = (x<<10) + (x<<4) + (x<<3) + (x<<2) + (x<<1) + x;
    end 
    endfunction

    // ----------------------------------------------------------
    // 水印 BRAM：NUM_LC * REF_LEN 个 2-bit 符号
    // ----------------------------------------------------------
    (* ram_style="block", rom_style="block" *)
    reg [1:0] wm_bram [0:WM_DEPTH-1];

    // 写地址：wm_wr_addr = MUL1055(region) + row
    wire [15:0] wm_wr_addr_lin = MUL1055({10'd0, bram_sel}) + {5'd0, bram_write_addr};
    wire [WM_AW-1:0] wm_wr_addr = wm_wr_addr_lin[WM_AW-1:0];

    // 读地址：wm_rd_addr = MUL957(lc_idx) + ((pos_base + i_idx) % REF_LEN)
    reg  [WM_AW-1:0] wm_rd_addr_q;
    wire [WM_AW-1:0] wm_rd_addr_d;

    // 同步读数据
    reg [1:0] wm_sym_q;

    // ----------------------------------------------------------
    // 读段位平面 BRAM：READ_BPS 行，每行并行保存 64 条读段。
    // Port A 用于比对同步读，Port B 用于装载/输出的读改写。
    // ----------------------------------------------------------
    (* ram_style = "block" *) reg [63:0] plane_lo [0:READ_BPS-1];
    (* ram_style = "block" *) reg [63:0] plane_hi [0:READ_BPS-1];

    // Port A：比对阶段同步读
    reg [7:0]  a_addr;
    reg [63:0] a_lo_q, a_hi_q;
    always @(posedge clk) begin
        a_lo_q <= plane_lo[a_addr];
        a_hi_q <= plane_hi[a_addr];
    end

    // Port B：装载/输出阶段读改写
    reg [7:0]  b_addr;
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
    localparam [3:0] S_IDLE   = 4'd0,
                     S_CLR    = 4'd1,
                     S_LOAD   = 4'd2,
                     S_LOAD_R = 4'd3,
                     S_INITC  = 4'd5,
                     S_LAUNCH = 4'd6,
                     S_RUN    = 4'd7,
                     S_UPD    = 4'd8,
                     S_NEXT   = 4'd9,
                     S_EMIT   = 4'd10,
                     S_EMIT_W = 4'd14,
                     S_EMIT2  = 4'd11,
                     S_EMIT_FINAL = 4'd12,
                     S_DONE   = 4'd13;

    reg [3:0]  st;

    // 读段装载阶段
    reg [6:0]  cw_idx;
    reg [8:0]  row_i;
    reg [1:0]  phase;      // 0=给地址 1=等BRAM读出 2=读改写（修订 B11）
    reg [5:0]  bit_sel;

    // 【S1 时序改造 2026-09-03】原实现在 S_LOAD_R 里按 row_i 随机索引 cw_data，
    // 综合成两个 READ_BPS 选 1 的多路选择器（150 选 1，SE250 下 250 选 1）。
    // 那是 implementation-timing.rpt 第 5 名关键路径
    // （row_i_reg[1] -> b_lo_d_reg[34]，slack +0.158 ns）。
    // row_i 在 S_LOAD_R 里严格 0→READ_BPS-1 顺序递增，不需要随机访问：
    // 在 S_LOAD 收下码字那一拍把两个位平面各锁进一个移位寄存器，之后每行只看最低位。
    // 顺带把「cw_data 必须在整个 S_LOAD_R 期间保持不变」这条隐式要求也解掉了
    // （tb_srpe_batch.v:87-95 的 fed 标志正是为它而加）。
    reg [READ_BPS-1:0] cw_hi_sr;   // cw_data[0 .. READ_BPS-1]        每个碱基的高位
    reg [READ_BPS-1:0] cw_lo_sr;   // cw_data[READ_BPS .. CODEBITS-1] 每个碱基的低位

    // 位置比对阶段
    reg [5:0]   lc_idx;
    reg [15:0]  pos_cnt;
    reg [15:0]  pos_base;
    reg [8:0]   i_idx;

    // 64 条读段并行的分数与最优位置
    reg [SCORE_W-1:0] score   [0:BATCH-1];
    reg [SCORE_W-1:0] best_sc [0:BATCH-1];
    reg [POS_W-1:0]   best_pos[0:BATCH-1];
    // 记录每条读段的最优区域
    reg [REGION_W-1:0] best_region [0:BATCH-1];

    integer t, g;

    // 64 路符号匹配
    reg [63:0] match_mask;
    always @(*) begin
        case (wm_sym_q)
            2'b00: match_mask = ~a_lo_q & ~a_hi_q;
            2'b01: match_mask =  a_lo_q & ~a_hi_q;
            2'b10: match_mask = ~a_lo_q &  a_hi_q;
            default: match_mask =  a_lo_q &  a_hi_q;
        endcase
    end

    // === 累加使能：必须与数据严格对齐（修订 B12）===
    //
    // 比对流水线的延迟：给出 i_idx 的那一拍记为 C，
    //   C+1  a_addr / wm_rd_addr_q 生效
    //   C+2  a_lo_q / a_hi_q / wm_sym_q 出数 → match_mask 组合有效
    //   C+3  mm_q 寄存好，此时才该累加
    // 原实现直接把 (st==S_RUN) 延迟 1 拍当使能，导致每个位置的前 2 个碱基
    // 用的是上一个位置的残留、自己最后 2 个碱基又没被计入，分数系统性偏差。
    // 这里改成有效性移位链，并让 S_RUN 多跑 3 拍把流水线排空。
    reg [8:0] run_cnt;
    wire idx_valid = (st == S_RUN) && (run_cnt < READ_BPS);
    reg  v0, v1;
    always @(posedge clk) begin
        v0 <= idx_valid;
        v1 <= v0;
    end

    (* max_fanout = 8, keep = "true", dont_touch = "true" *)
    reg run_en_q0, run_en_q1, run_en_q2, run_en_q3, run_en_q4, run_en_q5, run_en_q6, run_en_q7;
    always @(posedge clk) begin
        run_en_q0 <= v1; run_en_q1 <= v1; run_en_q2 <= v1; run_en_q3 <= v1;
        run_en_q4 <= v1; run_en_q5 <= v1; run_en_q6 <= v1; run_en_q7 <= v1;
    end
    (* max_fanout = 8, keep = "true", dont_touch = "true" *)
    reg [7:0] mm_q0, mm_q1, mm_q2, mm_q3, mm_q4, mm_q5, mm_q6, mm_q7;
    always @(posedge clk) begin
        mm_q0 <= match_mask[7:0];   mm_q1 <= match_mask[15:8];
        mm_q2 <= match_mask[23:16]; mm_q3 <= match_mask[31:24];
        mm_q4 <= match_mask[39:32]; mm_q5 <= match_mask[47:40];
        mm_q6 <= match_mask[55:48]; mm_q7 <= match_mask[63:56];
    end

    // (pos_base + i_idx) mod REF_LEN
    wire [16:0] add_tmp  = pos_base + i_idx;
    wire [10:0] addr_mod = (add_tmp >= REF_LEN) ? (add_tmp - REF_LEN) : add_tmp[10:0];

    // 水印线性读地址：lc_idx*REF_LEN + addr_mod
    wire [15:0] wm_rd_addr_lin = MUL1055({10'd0, lc_idx}) + {5'd0, addr_mod};
    assign wm_rd_addr_d = wm_rd_addr_lin[WM_AW-1:0];

    // 结果输出组装
    reg [CODEBITS-1:0] cw_acc;
    reg [8:0]          emit_i;
    reg [6:0]          emit_idx;

    // 先扩展区域索引，保证后续移位加法不截断。
    wire [POS_W-1:0] region_ext = 
        {{(POS_W - REGION_W){1'b0}}, best_region[emit_idx]};

    // 计算 region * 805，完整保留 POS_W 位。
    // 805 = 512 + 256 + 32 + 4 + 1
    wire [POS_W-1:0] region_mul_stride = 
         (region_ext << 9) + (region_ext << 8) +
         (region_ext << 5) + (region_ext << 2) +
          region_ext;  // 512+256+32+4+1 = 805

    // 全局最优位置
    wire [POS_W-1:0] global_pos = region_mul_stride + best_pos[emit_idx];

    // ----------------------------------------------------------
    // 主时序逻辑
    // ----------------------------------------------------------
    always @(posedge clk) begin
        if (!rst_n) begin
            st   <= S_IDLE; busy <= 1'b0; done <= 1'b0;
            cw_req <= 1'b0; res_wr <= 1'b0;
            cw_idx <= 0; row_i <= 0; phase <= 2'd0; bit_sel <= 0;
            lc_idx<= 0; pos_cnt <= 0; pos_base <= 0; i_idx <= 0; run_cnt <= 0;
            a_addr<= 0; b_addr <= 0; b_we_lo <= 1'b0; b_we_hi <= 1'b0;
            wm_sym_q <= 2'b00; wm_rd_addr_q <= {WM_AW{1'b0}};
            for (t=0; t<BATCH; t=t+1) begin
                best_sc[t]     <= {SCORE_W{1'b0}};
                best_pos[t]    <= {POS_W{1'b0}};
                best_region[t] <= {REGION_W{1'b0}};  // 初始化区域
                score[t]       <= {SCORE_W{1'b0}};
            end
            emit_i <= 0; emit_idx <= 0; cw_acc <= {CODEBITS{1'b0}};
            cw_hi_sr <= {READ_BPS{1'b0}}; cw_lo_sr <= {READ_BPS{1'b0}};
        end else begin
            // ---- 全局默认值 ----
            done   <= 1'b0;
            res_wr <= 1'b0;
            b_we_lo<= 1'b0;
            b_we_hi<= 1'b0;
            cw_req <= 1'b0;

            // ---- 水印 BRAM 同步读写 ----
            wm_rd_addr_q <= wm_rd_addr_d;
            wm_sym_q     <= wm_bram[wm_rd_addr_q];
            if (bram_write_en) wm_bram[wm_wr_addr] <= bram_write_data;

            case (st)
                S_IDLE: begin
                    if (start_batch) begin
                        busy  <= 1'b1;
                        row_i <= 0;
                        st    <= S_CLR;
                    end
                end

                S_CLR: begin
                    b_addr <= row_i[7:0];
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
                        row_i <= 0;
                        phase <= 2'd0;
                        // 【S1】cw_valid 这一拍 cw_data 有效（顶层 cw_hold 与
                        // eng_cw_vld 同拍更新，见 Dna_accelerator_core_v1_0.v:280-286），
                        // 在这里整条锁下来，后续 READ_BPS 行只做移位。
                        cw_hi_sr <= cw_data[READ_BPS-1:0];
                        cw_lo_sr <= cw_data[CODEBITS-1:READ_BPS];
                        st    <= S_LOAD_R;
                    end
                end

                S_LOAD_R: begin
                    // 【修订 B11】plane BRAM 是同步读：给出地址的下一拍数据才有效。
                    // 原实现只有两相（给地址→立刻读改写），读到的其实是**上一行**的内容，
                    // 再写回本行，等于把别的读段的位覆盖掉，装载出来的位平面全是错的。
                    // 这里插入一拍等待相。
                    if (phase == 2'd0) begin
                        b_addr <= row_i[7:0];
                        phase  <= 2'd1;
                    end else if (phase == 2'd1) begin
                        phase  <= 2'd2;          // 等 b_lo_q/b_hi_q 出数
                    end else begin
                        // 【修订 B2】码字是「位平面」布局，不是交织：
                        //   cw_data[0 .. READ_BPS-1]        = 每个碱基的高位
                        //   cw_data[READ_BPS .. 2*READ_BPS-1] = 每个碱基的低位
                        // 而 match_mask 里的符号约定是 {a_hi, a_lo}，
                        // 因此第一位平面进 hi、第二位平面进 lo。
                        // 原实现按 cw_data[2i]/cw_data[2i+1] 取（交织布局），
                        // 与 Voter 的 calc_layer_position() 和上位机都对不上。
                        // 【S1】cw_hi_sr[0] / cw_lo_sr[0] 等价于原来的
                        // cw_data[row_i] / cw_data[READ_BPS+row_i]：本相每个 row_i
                        // 只进一次（phase 0→1→2 后 row_i 才 +1），移位次数与 row_i 同步。
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
                    lc_idx  <= 0;
                    pos_cnt <= 0;
                    i_idx   <= 0;
                    run_cnt <= 0;
                    for (t=0; t<BATCH; t=t+1) begin
                        best_sc[t]     <= {SCORE_W{1'b0}};
                        best_pos[t]    <= {POS_W{1'b0}};
                        best_region[t] <= {REGION_W{1'b0}};  // 初始化区域
                        score[t]       <= {SCORE_W{1'b0}};
                    end
                    a_addr   <= 0;
                    pos_base <= 0;
                    st       <= S_LAUNCH;
                end

                S_LAUNCH: begin
                    i_idx    <= 0;
                    run_cnt  <= 0;
                    pos_base <= pos_cnt;
                    for (t=0; t<BATCH; t=t+1) score[t] <= {SCORE_W{1'b0}};
                    a_addr   <= 0;
                    st       <= S_RUN;
                end

                S_RUN: begin
                    a_addr <= i_idx[7:0];
                    for (g=0; g<8; g=g+1) begin
                        if (run_en_q0 && mm_q0[g]) score[g]      <= score[g]      + 1'b1;
                        if (run_en_q1 && mm_q1[g]) score[g+8]    <= score[g+8]    + 1'b1;
                        if (run_en_q2 && mm_q2[g]) score[g+16]   <= score[g+16]   + 1'b1;
                        if (run_en_q3 && mm_q3[g]) score[g+24]   <= score[g+24]   + 1'b1;
                        if (run_en_q4 && mm_q4[g]) score[g+32]   <= score[g+32]   + 1'b1;
                        if (run_en_q5 && mm_q5[g]) score[g+40]   <= score[g+40]   + 1'b1;
                        if (run_en_q6 && mm_q6[g]) score[g+48]   <= score[g+48]   + 1'b1;
                        if (run_en_q7 && mm_q7[g]) score[g+56]   <= score[g+56]   + 1'b1;
                    end

                    // 多跑 3 拍把流水线排空；i_idx 到顶后保持，靠 idx_valid 屏蔽累加
                    run_cnt <= run_cnt + 1'b1;
                    if (i_idx < READ_BPS-1) i_idx <= i_idx + 1'b1;
                    if (run_cnt == READ_BPS + 2) st <= S_UPD;
                end    

                S_UPD: begin
                    for (t=0; t<BATCH; t=t+1) begin
                        if (score[t] > best_sc[t]) begin
                            best_sc[t]     <= score[t];
                            best_pos[t]    <= pos_base[POS_W-1:0];
                            best_region[t] <= lc_idx;          // 记录当前区域
                        end
                    end
                    st <= S_NEXT;
                end

                S_NEXT: begin
                    if (pos_cnt == STRIDE[15:0]) begin
                        pos_cnt <= 16'd0;
                        if (lc_idx == NUM_LC-1) begin
                            emit_idx <= 0; emit_i <= 0; cw_acc <= {CODEBITS{1'b0}};
                            st <= S_EMIT;
                        end else begin
                            lc_idx <= lc_idx + 1'b1;
                            st     <= S_LAUNCH;
                        end
                    end else begin
                        pos_cnt <= pos_cnt + 1'b1;
                        st      <= S_LAUNCH;
                    end
                end

                S_EMIT: begin
                    if (!res_full) begin
                        b_addr <= emit_i[7:0];
                        st     <= S_EMIT_W;     // 【修订 B10】同样要等一拍同步读
                    end
                end

                S_EMIT_W: st <= S_EMIT2;

                S_EMIT2: begin
                    // 【修订 B2】输出同样按位平面布局，与 Voter 的
                    // calc_layer_position()（前 READ_BPS 位属上层）保持一致。
                    cw_acc[emit_i]            <= b_hi_q[emit_idx];
                    cw_acc[READ_BPS + emit_i] <= b_lo_q[emit_idx];

                    if (emit_i == READ_BPS-1) begin
                        emit_i  <= 0;
                        st      <= S_EMIT_FINAL;
                    end else begin
                        emit_i <= emit_i + 1'b1;
                        st <= S_EMIT;
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
                        st <= S_EMIT;
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
