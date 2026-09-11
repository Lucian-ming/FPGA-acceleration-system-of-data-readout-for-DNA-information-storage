// ================================================================
// desparsification_decoder_v1_0.v — Stage3 反稀疏化核（控制层重写版）
//
// 功能：从 DDR 读 in_beats 拍（81,000 bit 稀疏流），做 5b→4b 反稀疏化，
//       把 out_beats 拍（64,800 bit 码字）写回 DDR。
//
// 【2026-08-07 重写说明】
// 原版把读、转换、写揉进一个共享状态机，暴露出三个独立的死锁缺陷
// （docs/03-status.md B7/B8/B9）：
//   B7 S_WAITB 用电平等 BVALID，可能等一个已经被消费掉的响应；
//   B8 无限制发 AR 又阻塞等 AR 握手，池满时形成死锁环；
//   B9 在写突发中途丢下 burst 去等 B，违反 AXI 协议。
// 三者的共同根因是「读和写共用一个状态机」——任何一方阻塞都会卡死另一方。
//
// 重写后的结构：
//   读引擎 ─┐
//           ├─ desparsify_datapath（已用黄金向量逐位验证）
//   写引擎 ─┘
// 读、写是两个**完全独立**的状态机，只通过数据通路的 valid/ready 耦合，
// 因此不存在互锁；每段突发一旦发出 AW/AR 就一定走完，不中途放弃。
//
// 判据：hw/ip/desparsification_decoder_1_0/hdl/tb_desparsifier.v
//       （bash tools/run_sim.sh）
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

    output wire [C_M00_AXI_DATA_WIDTH-1:0]    M00_AXI_WDATA,
    output wire [C_M00_AXI_DATA_WIDTH/8-1:0]  M00_AXI_WSTRB,
    output wire                               M00_AXI_WLAST,
    output wire                               M00_AXI_WVALID,
    input  wire                               M00_AXI_WREADY,

    input  wire [1:0]                         M00_AXI_BRESP,
    input  wire                               M00_AXI_BVALID,
    output wire                               M00_AXI_BREADY,

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

    input  wire [C_M00_AXI_DATA_WIDTH-1:0]    M00_AXI_RDATA,
    input  wire [1:0]                         M00_AXI_RRESP,
    input  wire                               M00_AXI_RLAST,
    input  wire                               M00_AXI_RVALID,
    output wire                               M00_AXI_RREADY
);

    localparam integer DW = C_M00_AXI_DATA_WIDTH;

    // =============================================================
    // AXI-Lite 控制寄存器
    //   0x00 IN_ADDR   0x04 IN_BEATS   0x08 OUT_ADDR
    //   0x0C OUT_BEATS 0x10 START      0x18 STATUS{done,idle}
    // =============================================================
    wire [31:0] in_addr_s, out_addr_s, in_beats_s, out_beats_s;
    wire        start_pulse_s, done_clr_s;
    reg         done_s, idle_s;

    // P7: 硬件周期计数器
    wire [31:0] dec_cycles_total;
    wire [31:0] dec_cycles_rd_busy;
    wire [31:0] dec_cycles_wr_busy;
    wire [31:0] dec_cycles_rd_wait;

    axi_slave_decoder #(
        .C_S_AXI_DATA_WIDTH(C_S00_AXI_DATA_WIDTH),
        .C_S_AXI_ADDR_WIDTH(C_S00_AXI_ADDR_WIDTH)
    ) u_axil (
        .S_AXI_ACLK(S00_AXI_ACLK), .S_AXI_ARESETN(S00_AXI_ARESETN),
        .S_AXI_AWADDR(S00_AXI_AWADDR), .S_AXI_AWVALID(S00_AXI_AWVALID),
        .S_AXI_AWREADY(S00_AXI_AWREADY),
        .S_AXI_WDATA(S00_AXI_WDATA), .S_AXI_WSTRB(S00_AXI_WSTRB),
        .S_AXI_WVALID(S00_AXI_WVALID), .S_AXI_WREADY(S00_AXI_WREADY),
        .S_AXI_BRESP(S00_AXI_BRESP), .S_AXI_BVALID(S00_AXI_BVALID),
        .S_AXI_BREADY(S00_AXI_BREADY),
        .S_AXI_ARADDR(S00_AXI_ARADDR), .S_AXI_ARVALID(S00_AXI_ARVALID),
        .S_AXI_ARREADY(S00_AXI_ARREADY),
        .S_AXI_RDATA(S00_AXI_RDATA), .S_AXI_RRESP(S00_AXI_RRESP),
        .S_AXI_RVALID(S00_AXI_RVALID), .S_AXI_RREADY(S00_AXI_RREADY),
        .in_addr(in_addr_s), .in_beats(in_beats_s),
        .out_addr(out_addr_s), .out_beats(out_beats_s),
        .start_pulse(start_pulse_s), .done_clr(done_clr_s),
        .done(done_s), .idle(idle_s),
        .cycles_total(dec_cycles_total),
        .cycles_rd_busy(dec_cycles_rd_busy),
        .cycles_wr_busy(dec_cycles_wr_busy),
        .cycles_rd_wait(dec_cycles_rd_wait)
    );

    // ---- 配置值同步到 M00_AXI_ACLK 域 ----
    reg [31:0] in_addr, out_addr, in_beats, out_beats;
    always @(posedge M00_AXI_ACLK) begin
        if (!M00_AXI_ARESETN) begin
            in_addr <= 32'd0; out_addr <= 32'd0;
            in_beats <= 32'd0; out_beats <= 32'd0;
        end else begin
            in_addr <= in_addr_s; out_addr <= out_addr_s;
            in_beats <= in_beats_s; out_beats <= out_beats_s;
        end
    end

    // ---- START 脉冲跨时钟域 ----
    reg s1_m, s2_m, s3_m;
    always @(posedge M00_AXI_ACLK) {s1_m, s2_m, s3_m} <= {start_pulse_s, s1_m, s2_m};
    wire start_pulse_m = s2_m & ~s3_m;

    // ---- [B27] 只有核完全静止时 START 才生效 ----
    // 跑到一半被重启是致命的：复位只清掉本模块的 FSM 和数据通路，
    // **已经发出去的 AXI 读突发不会被取消** —— 真实 DDR/互连会把剩下的
    // R 拍继续送回来，落进刚被清空的 in_pool，被当成新任务输入流的开头。
    // 于是整条输入被旋转了「残留拍数」，输出与黄金完全不相关：
    // 第四次上板 Stage3 与 stage3_expect.hex 49.46% 误码就是这么来的
    // （固件 echo.c 在 START=1 之后 100 us 又写了一次 START=0，
    //   而上面那个寄存器当时对任何写都产生脉冲）。
    // 判据见 hw/sim/dec/tb_dec_ddr_restart.v。
    wire core_active_m;
    wire start_eff_m = start_pulse_m & ~core_active_m;

    // =============================================================
    // 4K 边界：从 addr 到下一个 4K 边界还能放几拍
    // =============================================================
    // ⚠️ 返回值必须是 10 bit：地址 4K 对齐时结果是 512，9 bit 装不下会被截成 0。
    //    原版就是 [8:0]，靠「等于 0 就当没有 4K 限制」的补丁绕过去的。
    function [9:0] beats_to_4k;
        input [C_M00_AXI_ADDR_WIDTH-1:0] addr;
        reg [12:0] bytes_left;
        begin
            bytes_left  = 13'd4096 - {1'b0, addr[11:0]};
            beats_to_4k = bytes_left[12:3];      // /8，范围 1..512
        end
    endfunction

    function [31:0] burst_len;                    // 本段突发拍数
        input [31:0] left;
        input [C_M00_AXI_ADDR_WIDTH-1:0] addr;
        reg [31:0] a, b;
        begin
            a = (left < MAX_BURST_LEN) ? left : MAX_BURST_LEN;
            b = {22'd0, beats_to_4k(addr)};
            burst_len = (a < b) ? a : b;
        end
    endfunction

    // =============================================================
    // 数据通路（已用黄金向量逐位验证，见 tb_desparsify_datapath.v）
    // =============================================================
    wire        dp_in_valid, dp_in_ready, dp_in_done;
    wire [63:0] dp_in_data;
    wire        dp_out_valid, dp_out_ready;
    wire [63:0] dp_out_data;

    desparsify_datapath u_dp (
        .clk(M00_AXI_ACLK), .rstn(M00_AXI_ARESETN & ~start_eff_m),
        .in_valid(dp_in_valid), .in_ready(dp_in_ready),
        .in_data(dp_in_data),   .in_done(dp_in_done),
        .out_valid(dp_out_valid), .out_ready(dp_out_ready), .out_data(dp_out_data)
    );

    // =============================================================
    // 读引擎 —— 与写引擎完全独立
    // =============================================================
    localparam RD_IDLE = 2'd0, RD_ADDR = 2'd1, RD_DATA = 2'd2, RD_DONE = 2'd3;
    reg [1:0]  rd_state;
    reg [31:0] r_left;                 // 还没请求的拍数
    reg [31:0] r_recv;                 // 已收到的拍数
    reg [31:0] r_burst;                // 本段还没收完的拍数
    reg [C_M00_AXI_ADDR_WIDTH-1:0] ar_addr;
    reg [7:0]  ar_len_r;
    reg        ar_valid_r;

    wire [31:0] rd_this = burst_len(r_left, ar_addr);

    assign M00_AXI_ARADDR  = ar_addr;
    assign M00_AXI_ARLEN   = ar_len_r;
    assign M00_AXI_ARVALID = ar_valid_r;
    // 只有在等待本段数据时才收；由数据通路背压
    assign M00_AXI_RREADY  = (rd_state == RD_DATA) && dp_in_ready;
    assign dp_in_valid     = (rd_state == RD_DATA) && M00_AXI_RVALID;
    assign dp_in_data      = M00_AXI_RDATA;
    assign dp_in_done      = (rd_state == RD_DONE);

    always @(posedge M00_AXI_ACLK) begin
        if (!M00_AXI_ARESETN) begin
            rd_state <= RD_IDLE; ar_valid_r <= 1'b0; ar_len_r <= 8'd0;
            r_left <= 32'd0; r_recv <= 32'd0; r_burst <= 32'd0;
            ar_addr <= {C_M00_AXI_ADDR_WIDTH{1'b0}};
        end else if (start_eff_m) begin
            rd_state <= (in_beats != 0) ? RD_ADDR : RD_IDLE;
            ar_addr  <= {in_addr[C_M00_AXI_ADDR_WIDTH-1:3], 3'b000};
            r_left   <= in_beats;
            r_recv   <= 32'd0;
            r_burst  <= 32'd0;
            ar_valid_r <= 1'b0;
        end else case (rd_state)
            RD_IDLE: ;

            // 发起一段读突发；发出后一定把这段收完
            RD_ADDR: begin
                if (!ar_valid_r) begin
                    ar_len_r   <= rd_this[7:0] - 8'd1;
                    r_burst    <= rd_this;
                    ar_valid_r <= 1'b1;
                end else if (M00_AXI_ARREADY) begin
                    ar_valid_r <= 1'b0;
                    r_left     <= r_left - r_burst;
                    ar_addr    <= ar_addr + (r_burst << 3);
                    rd_state   <= RD_DATA;
                end
            end

            RD_DATA: begin
                if (M00_AXI_RVALID && M00_AXI_RREADY) begin
                    r_recv  <= r_recv + 1;
                    r_burst <= r_burst - 1;
                    if (r_burst == 1)
                        rd_state <= (r_left != 0) ? RD_ADDR : RD_DONE;
                end
            end

            RD_DONE: ;
        endcase
    end

    // =============================================================
    // 写引擎 —— 与读引擎完全独立；一旦发出 AW 就必定交付 AWLEN+1 拍 W
    // =============================================================
    localparam WR_IDLE = 2'd0, WR_ADDR = 2'd1, WR_DATA = 2'd2, WR_RESP = 2'd3;
    reg [1:0]  wr_state;
    reg [31:0] w_left;                 // 还没请求的拍数
    reg [31:0] w_sent;                 // 已发出的拍数
    reg [31:0] w_burst;                // 本段还没发完的拍数
    reg [C_M00_AXI_ADDR_WIDTH-1:0] aw_addr;
    reg [7:0]  aw_len_r;
    reg        aw_valid_r;
    reg        busy;

    // [B27] 核是否还在动：写引擎 busy，或读引擎还在发地址/收数据。
    // 只要它为 1，外面写 START 就不生效（见上）。RD_DONE 时所有读突发都已收完，
    // busy=0 时最后一个 B 也已回来，此时重启才是安全的。
    assign core_active_m = busy | (rd_state == RD_ADDR) | (rd_state == RD_DATA);

    wire [31:0] wr_this = burst_len(w_left, aw_addr);
    // 整个任务的最后一拍：64,800 = 1012*64 + 32，故末拍只有低 4 字节有效
    wire        last_beat_overall = (w_sent == out_beats - 1);

    assign M00_AXI_AWADDR  = aw_addr;
    assign M00_AXI_AWLEN   = aw_len_r;
    assign M00_AXI_AWVALID = aw_valid_r;
    assign M00_AXI_WDATA   = dp_out_data;
    assign M00_AXI_WSTRB   = last_beat_overall ? 8'h0F : 8'hFF;
    assign M00_AXI_WLAST   = (wr_state == WR_DATA) && (w_burst == 1);
    assign M00_AXI_WVALID  = (wr_state == WR_DATA) && dp_out_valid;
    assign dp_out_ready    = (wr_state == WR_DATA) && M00_AXI_WREADY;
    assign M00_AXI_BREADY  = (wr_state == WR_RESP);

    always @(posedge M00_AXI_ACLK) begin
        if (!M00_AXI_ARESETN) begin
            wr_state <= WR_IDLE; aw_valid_r <= 1'b0; aw_len_r <= 8'd0;
            w_left <= 32'd0; w_sent <= 32'd0; w_burst <= 32'd0; busy <= 1'b0;
            aw_addr <= {C_M00_AXI_ADDR_WIDTH{1'b0}};
        end else if (start_eff_m) begin
            wr_state <= (out_beats != 0) ? WR_ADDR : WR_IDLE;
            aw_addr  <= {out_addr[C_M00_AXI_ADDR_WIDTH-1:3], 3'b000};
            w_left   <= out_beats;
            w_sent   <= 32'd0;
            w_burst  <= 32'd0;
            aw_valid_r <= 1'b0;
            busy     <= (out_beats != 0);
        end else case (wr_state)
            WR_IDLE: ;

            // 等到确实有数据可写再占用地址通道，避免长时间空占互连
            WR_ADDR: begin
                if (!aw_valid_r) begin
                    if (dp_out_valid) begin
                        aw_len_r   <= wr_this[7:0] - 8'd1;
                        w_burst    <= wr_this;
                        aw_valid_r <= 1'b1;
                    end
                end else if (M00_AXI_AWREADY) begin
                    aw_valid_r <= 1'b0;
                    w_left     <= w_left - w_burst;
                    aw_addr    <= aw_addr + (w_burst << 3);
                    wr_state   <= WR_DATA;
                end
            end

            // 进了这里就一定把 w_burst 拍全部发完，绝不中途放弃（修订 B9）
            WR_DATA: begin
                if (M00_AXI_WVALID && M00_AXI_WREADY) begin
                    w_sent  <= w_sent + 1;
                    w_burst <= w_burst - 1;
                    if (w_burst == 1) wr_state <= WR_RESP;
                end
            end

            // 用状态而非电平等待 B：进入本状态才拉高 BREADY，
            // 因此不可能错过或提前消费掉响应（修订 B7）
            WR_RESP: if (M00_AXI_BVALID) begin
                if (w_left != 0) wr_state <= WR_ADDR;
                else begin
                    wr_state <= WR_IDLE;
                    busy     <= 1'b0;
                end
            end
        endcase
    end

    // =============================================================
    // 状态位
    // =============================================================
    reg done_m;
    always @(posedge M00_AXI_ACLK) begin
        if (!M00_AXI_ARESETN)      done_m <= 1'b0;
        else if (start_eff_m)      done_m <= 1'b0;
        else if (busy && (wr_state == WR_RESP) && M00_AXI_BVALID && (w_left == 0))
                                   done_m <= 1'b1;
    end

    reg d1, d2, b1, b2;
    always @(posedge S00_AXI_ACLK) begin
        if (!S00_AXI_ARESETN) begin
            {d1,d2} <= 2'b00; {b1,b2} <= 2'b00; done_s <= 1'b0; idle_s <= 1'b1;
        end else begin
            {d2,d1} <= {d1, done_m};
            {b2,b1} <= {b1, busy};
            if (done_clr_s) done_s <= 1'b0;
            else if (d2)    done_s <= 1'b1;
            idle_s <= ~b2;
        end
    end

    // =============================================================
    // P7: 独立硬件周期计数器逻辑（M00_AXI_ACLK 域）
    // =============================================================
    reg [31:0] dec_cycles_total_r;
    reg [31:0] dec_cycles_rd_busy_r;
    reg [31:0] dec_cycles_wr_busy_r;
    reg [31:0] dec_cycles_rd_wait_r;
    reg        dec_running;

    assign dec_cycles_total   = dec_cycles_total_r;
    assign dec_cycles_rd_busy = dec_cycles_rd_busy_r;
    assign dec_cycles_wr_busy = dec_cycles_wr_busy_r;
    assign dec_cycles_rd_wait = dec_cycles_rd_wait_r;

    always @(posedge M00_AXI_ACLK) begin
        if (!M00_AXI_ARESETN) begin
            dec_cycles_total_r   <= 32'd0;
            dec_cycles_rd_busy_r  <= 32'd0;
            dec_cycles_wr_busy_r  <= 32'd0;
            dec_cycles_rd_wait_r  <= 32'd0;
            dec_running           <= 1'b0;
        end else if (start_eff_m) begin
            dec_cycles_total_r   <= 32'd0;
            dec_cycles_rd_busy_r  <= 32'd0;
            dec_cycles_wr_busy_r  <= 32'd0;
            dec_cycles_rd_wait_r  <= 32'd0;
            dec_running           <= (out_beats != 0) || (in_beats != 0);
        end else begin
            if (dec_running) begin
                if (busy && (wr_state == WR_RESP) && M00_AXI_BVALID && (w_left == 0))
                    dec_running <= 1'b0;
                else if (!(&dec_cycles_total_r))
                    dec_cycles_total_r <= dec_cycles_total_r + 1'b1;
            end

            if (rd_state != RD_IDLE && rd_state != RD_DONE) begin
                if (!(&dec_cycles_rd_busy_r))
                    dec_cycles_rd_busy_r <= dec_cycles_rd_busy_r + 1'b1;
            end

            if (wr_state != WR_IDLE) begin
                if (!(&dec_cycles_wr_busy_r))
                    dec_cycles_wr_busy_r <= dec_cycles_wr_busy_r + 1'b1;
            end

            if ((rd_state == RD_ADDR && ar_valid_r && !M00_AXI_ARREADY) ||
                (rd_state == RD_DATA && !M00_AXI_RVALID)) begin
                if (!(&dec_cycles_rd_wait_r))
                    dec_cycles_rd_wait_r <= dec_cycles_rd_wait_r + 1'b1;
            end
        end
    end

    // ---- AXI 静态属性 ----
    assign M00_AXI_AWBURST = 2'b01;
    assign M00_AXI_ARBURST = 2'b01;
    assign M00_AXI_AWSIZE  = (DW==64) ? 3'b011 : 3'b010;
    assign M00_AXI_ARSIZE  = (DW==64) ? 3'b011 : 3'b010;
    assign M00_AXI_AWLOCK  = 1'b0;
    assign M00_AXI_ARLOCK  = 1'b0;
    assign M00_AXI_AWCACHE = 4'b0010;
    assign M00_AXI_ARCACHE = 4'b0010;
    assign M00_AXI_AWPROT  = 3'b000;
    assign M00_AXI_ARPROT  = 3'b000;
    assign M00_AXI_AWQOS   = 4'b0000;
    assign M00_AXI_ARQOS   = 4'b0000;

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
    output wire                             S_AXI_AWREADY,
    input  wire [C_S_AXI_DATA_WIDTH-1:0]    S_AXI_WDATA,
    input  wire [C_S_AXI_DATA_WIDTH/8-1:0]  S_AXI_WSTRB,
    input  wire                             S_AXI_WVALID,
    output wire                             S_AXI_WREADY,
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
    input  wire                              done,
    input  wire                              idle,

    // P7: 硬件周期计数器
    input  wire [31:0]                      cycles_total,
    input  wire [31:0]                      cycles_rd_busy,
    input  wire [31:0]                      cycles_wr_busy,
    input  wire [31:0]                      cycles_rd_wait
);
    reg [C_S_AXI_ADDR_WIDTH-1:0] awaddr_q;
    reg [C_S_AXI_DATA_WIDTH-1:0] wdata_q;
    reg aw_pending, w_pending;
    wire aw_accept = S_AXI_AWVALID && S_AXI_AWREADY;
    wire w_accept = S_AXI_WVALID && S_AXI_WREADY;
    wire write_commit = (aw_pending || aw_accept) &&
                        (w_pending || w_accept) && ~S_AXI_BVALID;
    wire [C_S_AXI_ADDR_WIDTH-1:0] write_addr = aw_pending ? awaddr_q : S_AXI_AWADDR;
    wire [C_S_AXI_DATA_WIDTH-1:0] write_data = w_pending ? wdata_q : S_AXI_WDATA;
    wire [3:0] waddr = write_addr[5:2];
    wire [3:0] raddr = S_AXI_ARADDR[5:2];
    assign S_AXI_AWREADY = ~aw_pending & ~S_AXI_BVALID;
    assign S_AXI_WREADY = ~w_pending & ~S_AXI_BVALID;

    // ???����?��?"
    always @(posedge S_AXI_ACLK) begin
        if (!S_AXI_ARESETN) begin
            S_AXI_BVALID  <= 1'b0;
            S_AXI_BRESP   <= 2'b00;
            awaddr_q <= {C_S_AXI_ADDR_WIDTH{1'b0}};
            wdata_q <= {C_S_AXI_DATA_WIDTH{1'b0}};
            aw_pending <= 1'b0;
            w_pending <= 1'b0;
            in_addr <= 32'd0; in_beats <= 32'd0; out_addr <= 32'd0; out_beats <= 32'd0;
            start_pulse <= 1'b0; done_clr <= 1'b0;
        end else begin
            start_pulse <= 1'b0;
            done_clr    <= 1'b0;

            if (aw_accept) begin
                awaddr_q <= S_AXI_AWADDR;
                aw_pending <= 1'b1;
            end
            if (w_accept) begin
                wdata_q <= S_AXI_WDATA;
                w_pending <= 1'b1;
            end

            if (write_commit) begin
                aw_pending <= 1'b0;
                w_pending <= 1'b0;
                case (waddr)
                    4'd0: in_addr   <= write_data;
                    4'd1: in_beats  <= write_data;
                    4'd2: out_addr  <= write_data;
                    4'd3: out_beats <= write_data;
                    4'd4: start_pulse <= write_data[0];   // [B27] 只有写 1 才启动
                    default: ;
                endcase
                S_AXI_BVALID <= 1'b1;
                S_AXI_BRESP  <= 2'b00;
            end else if (S_AXI_BVALID && S_AXI_BREADY) begin
                S_AXI_BVALID <= 1'b0;
            end
        end
    end

    // ��??����?��?"
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
                    4'd5: S_AXI_RDATA <= cycles_total;    // 0x14
                    4'd6: S_AXI_RDATA <= {30'd0, done, idle}; // 0x18
                    4'd7: S_AXI_RDATA <= cycles_rd_busy;  // 0x1C
                    4'd8: S_AXI_RDATA <= cycles_wr_busy;  // 0x20
                    4'd9: S_AXI_RDATA <= cycles_rd_wait;  // 0x24
                    default: S_AXI_RDATA <= 32'd0;
                endcase
                S_AXI_RRESP <= 2'b00;
            end else if (S_AXI_RVALID && S_AXI_RREADY) begin
                S_AXI_RVALID <= 1'b0;
            end
        end
    end
endmodule
