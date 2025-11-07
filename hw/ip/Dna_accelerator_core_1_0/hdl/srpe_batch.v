// =============================================================
// File: srpe_batch.v
// Desc : 64-read batch engine using bit-plane BRAM
//        - ROM/位平面均推断为 BRAM（同步读）
//        - 计算阶段用 pos_base 固化当前 pos，降低高扇出
//        - 打分路径 8×8 分组（局部使能+匹配位寄存）降低净延迟
//        - ★ 修复：水印 ROM 地址改为线性地址 lc*REF_LEN + row
//        - ★ 最终修复：region_mul_stride 避免中间加法溢出
// Synth: Verilog-2001
// =============================================================
`timescale 1 ns / 1 ps

(* keep_hierarchy = "yes" *)
module srpe_batch #(
    parameter integer BATCH     = 64,
    parameter integer NUM_LC    = 50,      // 参考片段数：50
    parameter integer STRIDE    = 807,     // 每段滑动步长：807
    parameter integer REF_LEN   = 957,     // 每段参考长度：957
    parameter integer READ_BPS  = 150,
    parameter integer SCORE_W   = 10,
    parameter integer POS_W     = 16
)(
    input  wire                   clk,
    input  wire                   rst_n,
    input  wire                   start_batch,

    // 从上层按需获取 BATCH 条 codeword（每条 2*READ_BPS bit）
    output reg                    cw_req,     // 引擎需要一条 read
    input  wire                   cw_valid,   // 顶层在下一拍提供 cw_data
    input  wire [READ_BPS*2-1:0]  cw_data,    // 300b when READ_BPS=150

    // 预加载水印（写 ROM）
    input  wire                   bram_write_en,
    input  wire [5:0]             bram_sel,
    input  wire [9:0]             bram_write_addr,  // 0..REF_LEN-1 (957-1=956)
    input  wire [1:0]             bram_write_data,

    // 结果输出到结果 FIFO
    output reg                    res_wr,
    output reg  [READ_BPS*2+POS_W+SCORE_W-1:0] res_din,
    input  wire                   res_full,

    output reg                    busy,
    output reg                    done
);

    localparam integer CODEBITS = READ_BPS*2;
    localparam integer RESULT_W = CODEBITS + POS_W + SCORE_W;

    // 【修改3-1】新增参数
    localparam integer REGION_W = 6;                     // 0~49
    localparam integer WM_DEPTH = NUM_LC * REF_LEN;      // 50*957
    localparam integer WM_AW = CLOG2(WM_DEPTH);

    // ----------------------------------------------------------
    // 实用函数
    // ----------------------------------------------------------
    function integer CLOG2; input integer v; integer t,i; begin
        t=v-1; i=0; while(t>0) begin t=t>>1; i=i+1; end CLOG2=i;
    end endfunction

    // 【修复1】MUL957 正确实现 + 注释修正
    // 957 = 512 + 256 + 128 + 32 + 16 + 8 + 4 + 1
    //     = 2^9 + 2^8 + 2^7 + 2^5 + 2^4 + 2^3 + 2^2 + 2^0
    function [15:0] MUL957; 
        input [15:0] x; 
    begin
        MUL957 = (x<<9) + (x<<8) + (x<<7) + (x<<5) + (x<<4) + (x<<3) + (x<<2) + x;
    end 
    endfunction

    // ----------------------------------------------------------
    // 水印 ROM：NUM_LC * REF_LEN * 2-bit
    // ----------------------------------------------------------
    (* ram_style="block", rom_style="block" *)
    reg [1:0] wm_bram [0:WM_DEPTH-1];

    // 写地址: wm_wr_addr = MUL957(region) + row 
    wire [15:0] wm_wr_addr_lin = MUL957({10'd0, bram_sel}) + {6'd0, bram_write_addr};
    wire [WM_AW-1:0] wm_wr_addr = wm_wr_addr_lin[WM_AW-1:0];

    // 读地址: wm_rd_addr = MUL957(lc_idx) + ((pos_base + i_idx) % REF_LEN) 
    reg  [WM_AW-1:0] wm_rd_addr_q;
    wire [WM_AW-1:0] wm_rd_addr_d;

    // 同步读输出
    reg [1:0] wm_sym_q;

    // ----------------------------------------------------------
    // 读段位平面 BRAM：每行 64bit × READ_BPS 行（分别存 LSB/MSB）
    // Port A：compute（同步读）；Port B：build/emit（RMW）
    // ----------------------------------------------------------
    (* ram_style = "block" *) reg [63:0] plane_lo [0:READ_BPS-1];
    (* ram_style = "block" *) reg [63:0] plane_hi [0:READ_BPS-1];

    // A 口（compute，同步读）
    reg [7:0]  a_addr;
    reg [63:0] a_lo_q, a_hi_q;
    always @(posedge clk) begin
        a_lo_q <= plane_lo[a_addr];
        a_hi_q <= plane_hi[a_addr];
    end

    // B 口（build/emit，RMW）
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
    // 状态机与索引
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
                     S_EMIT2  = 4'd11,
                     S_EMIT_FINAL = 4'd12,
                     S_DONE   = 4'd13;

    reg [3:0]  st;

    // 输入阶段
    reg [6:0]  cw_idx;
    reg [8:0]  row_i;
    reg        phase;
    reg [5:0]  bit_sel;

    // 计算阶段
    reg [5:0]   lc_idx;
    reg [15:0]  pos_cnt;
    reg [15:0]  pos_base;
    reg [8:0]   i_idx;

    // 64 条读段的累计与最优
    reg [SCORE_W-1:0] score   [0:BATCH-1];
    reg [SCORE_W-1:0] best_sc [0:BATCH-1];
    reg [POS_W-1:0]   best_pos[0:BATCH-1];
    // 【修改3-2】新增：记录最佳 region
    reg [REGION_W-1:0] best_region [0:BATCH-1];

    integer t, g;

    // 向量匹配
    reg [63:0] match_mask;
    always @(*) begin
        case (wm_sym_q)
            2'b00: match_mask = ~a_lo_q & ~a_hi_q;
            2'b01: match_mask =  a_lo_q & ~a_hi_q;
            2'b10: match_mask = ~a_lo_q &  a_hi_q;
            default: match_mask =  a_lo_q &  a_hi_q;
        endcase
    end

    // === 8×8 分组 ===
    wire run_en = (st == S_RUN);
    (* max_fanout = 8, keep = "true", dont_touch = "true" *)
    reg run_en_q0, run_en_q1, run_en_q2, run_en_q3, run_en_q4, run_en_q5, run_en_q6, run_en_q7;
    always @(posedge clk) begin
        run_en_q0 <= run_en; run_en_q1 <= run_en; run_en_q2 <= run_en; run_en_q3 <= run_en;
        run_en_q4 <= run_en; run_en_q5 <= run_en; run_en_q6 <= run_en; run_en_q7 <= run_en;
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
    wire [9:0]  addr_mod = (add_tmp >= REF_LEN) ? (add_tmp - REF_LEN) : add_tmp[9:0];

    // 线性读地址：lc_idx*REF_LEN + addr_mod
    wire [15:0] wm_rd_addr_lin = MUL957({10'd0, lc_idx}) + {6'd0, addr_mod};
    assign wm_rd_addr_d = wm_rd_addr_lin[WM_AW-1:0];

    // 输出成帧
    reg [CODEBITS-1:0] cw_acc;
    reg [8:0]          emit_i;
    reg [6:0]          emit_idx;

    // 【最终修复】避免中间加法溢出：先扩展 best_region 到 POS_W 位宽
    wire [POS_W-1:0] region_ext = 
        {{(POS_W - REGION_W){1'b0}}, best_region[emit_idx]};

    // 正确计算：region * 807（无截断）
    wire [POS_W-1:0] region_mul_stride = 
         (region_ext << 9) + (region_ext << 8) +
         (region_ext << 5) + (region_ext << 2) +
         (region_ext << 1) +  region_ext;  // 512+256+32+4+2+1 = 807

    // 全局绝对位置
    wire [POS_W-1:0] global_pos = region_mul_stride + best_pos[emit_idx];

    // ----------------------------------------------------------
    // 主时序
    // ----------------------------------------------------------
    always @(posedge clk) begin
        if (!rst_n) begin
            st   <= S_IDLE; busy <= 1'b0; done <= 1'b0;
            cw_req <= 1'b0; res_wr <= 1'b0;
            cw_idx <= 0; row_i <= 0; phase <= 1'b0; bit_sel <= 0;
            lc_idx<= 0; pos_cnt <= 0; pos_base <= 0; i_idx <= 0;
            a_addr<= 0; b_addr <= 0; b_we_lo <= 1'b0; b_we_hi <= 1'b0;
            wm_sym_q <= 2'b00; wm_rd_addr_q <= {WM_AW{1'b0}};
            for (t=0; t<BATCH; t=t+1) begin
                best_sc[t]     <= {SCORE_W{1'b0}};
                best_pos[t]    <= {POS_W{1'b0}};
                best_region[t] <= {REGION_W{1'b0}};  // 初始化 region
                score[t]       <= {SCORE_W{1'b0}};
            end
            emit_i <= 0; emit_idx <= 0; cw_acc <= {CODEBITS{1'b0}};
        end else begin
            // ---- 全局默认 ----
            done   <= 1'b0;
            res_wr <= 1'b0;
            b_we_lo<= 1'b0;
            b_we_hi<= 1'b0;
            cw_req <= 1'b0;

            // ---- ROM 同步读 ----
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
                        cw_idx  <= 0; row_i <= 0; phase <= 1'b0; bit_sel <= 0;
                        st      <= S_LOAD;
                    end else begin
                        row_i <= row_i + 1'b1;
                    end
                end

                S_LOAD: begin
                    cw_req <= 1'b1;
                    if (cw_valid) begin
                        row_i <= 0;
                        phase <= 1'b0;
                        st    <= S_LOAD_R;
                    end
                end

                S_LOAD_R: begin
                    if (!phase) begin
                        b_addr <= row_i[7:0];
                        phase  <= 1'b1;
                    end else begin
                        b_lo_d <= (cw_data[(row_i<<1)+0]) ?
                                  (b_lo_q | (64'h1 << bit_sel)) :
                                  (b_lo_q & ~(64'h1 << bit_sel));
                        b_hi_d <= (cw_data[(row_i<<1)+1]) ?
                                  (b_hi_q | (64'h1 << bit_sel)) :
                                  (b_hi_q & ~(64'h1 << bit_sel));
                        b_we_lo<= 1'b1; b_we_hi<= 1'b1;

                        phase  <= 1'b0;
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
                    for (t=0; t<BATCH; t=t+1) begin
                        best_sc[t]     <= {SCORE_W{1'b0}};
                        best_pos[t]    <= {POS_W{1'b0}};
                        best_region[t] <= {REGION_W{1'b0}};  // 清零 region
                        score[t]       <= {SCORE_W{1'b0}};
                    end
                    a_addr   <= 0;
                    pos_base <= 0;
                    st       <= S_LAUNCH;
                end

                S_LAUNCH: begin
                    i_idx    <= 0;
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

                    if (i_idx == READ_BPS-1) begin
                        st <= S_UPD;
                    end else begin
                        i_idx <= i_idx + 1'b1;
                    end
                end    

                S_UPD: begin
                    for (t=0; t<BATCH; t=t+1) begin
                        if (score[t] > best_sc[t]) begin
                            best_sc[t]     <= score[t];
                            best_pos[t]    <= pos_base[POS_W-1:0];
                            best_region[t] <= lc_idx;          // 记录当前 lc_idx
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
                        st     <= S_EMIT2;
                    end
                end

                S_EMIT2: begin
                    cw_acc[(emit_i<<1)+0] <= b_lo_q[emit_idx];
                    cw_acc[(emit_i<<1)+1] <= b_hi_q[emit_idx];

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