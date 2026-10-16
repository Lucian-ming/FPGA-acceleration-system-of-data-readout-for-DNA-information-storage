// =============================================================
// tb_desparsifier.v — Stage3 反稀疏化核的文件型 Testbench
//
// 用黄金向量做判据，不是"能跑就算过"：
//   激励  tests/golden/sparse_ideal.hex        81,000 bit 稀疏流（1,266 拍）
//   期望  tests/golden/stage3_ideal_expect.hex 64,800 bit 码字（1,013 拍）
//   不匹配立即 $fatal。
//
// 含一个简易 AXI4 从机（内存模型）和一个真正会驱动 AWVALID/WVALID 的
// AXI-Lite BFM —— 旧的 tb_dna_quick.v 把写使能固定为 0，控制寄存器从未被写入。
//
// 运行：
//   iverilog -g2005 -o /tmp/tb_desp \
//       hw/ip/desparsification_decoder_1_0/hdl/desparsification_decoder_v1_0.v \
//       hw/sim/ip_tb/tb_desparsifier.v
//   vvp /tmp/tb_desp
// =============================================================
`timescale 1ns/1ps

module tb_desparsifier;

    localparam integer IN_BEATS   = 1266;   // ceil(81000/64)
    localparam integer OUT_BEATS  = 1013;   // ceil(64800/64)
    localparam integer OUT_BITS   = 64800;
    // ---- 从机的严格程度：默认取最苛刻的设置 ----
    // B_LATENCY=0  → WLAST 后立刻给 B，暴露「电平等 BVALID」的竞争（原 B7）
    // Q_DEPTH=1    → 只允许 1 个未完成地址，暴露「无限发 AR 又阻塞等握手」（原 B8）
    localparam integer B_LATENCY = 0;
    localparam integer Q_DEPTH   = 1;

    localparam [31:0]  IN_ADDR    = 32'h1000_0000;
    localparam [31:0]  OUT_ADDR   = 32'h2000_0000;

    reg clk = 0, rstn = 0;
    always #5 clk = ~clk;               // 100 MHz

    // ---------------- AXI-Lite ----------------
    reg  [5:0]  s_awaddr;  reg s_awvalid;  wire s_awready;
    reg  [31:0] s_wdata;   reg [3:0] s_wstrb; reg s_wvalid; wire s_wready;
    wire [1:0]  s_bresp;   wire s_bvalid;  reg s_bready;
    reg  [5:0]  s_araddr;  reg s_arvalid;  wire s_arready;
    wire [31:0] s_rdata;   wire [1:0] s_rresp; wire s_rvalid; reg s_rready;

    // ---------------- AXI4 Master ----------------
    wire [31:0] m_awaddr;  wire [7:0] m_awlen;  wire m_awvalid;  reg m_awready;
    wire [63:0] m_wdata;   wire [7:0] m_wstrb;  wire m_wlast;
    wire        m_wvalid;  reg  m_wready;
    reg  [1:0]  m_bresp;   reg  m_bvalid;       wire m_bready;
    wire [31:0] m_araddr;  wire [7:0] m_arlen;  wire m_arvalid;  reg m_arready;
    reg  [63:0] m_rdata;   reg  [1:0] m_rresp;  reg m_rlast;     reg m_rvalid;
    wire        m_rready;

    desparsification_decoder_v1_0 dut (
        .S00_AXI_ACLK(clk), .S00_AXI_ARESETN(rstn),
        .S00_AXI_AWADDR(s_awaddr), .S00_AXI_AWVALID(s_awvalid), .S00_AXI_AWREADY(s_awready),
        .S00_AXI_WDATA(s_wdata), .S00_AXI_WSTRB(s_wstrb),
        .S00_AXI_WVALID(s_wvalid), .S00_AXI_WREADY(s_wready),
        .S00_AXI_BRESP(s_bresp), .S00_AXI_BVALID(s_bvalid), .S00_AXI_BREADY(s_bready),
        .S00_AXI_ARADDR(s_araddr), .S00_AXI_ARVALID(s_arvalid), .S00_AXI_ARREADY(s_arready),
        .S00_AXI_RDATA(s_rdata), .S00_AXI_RRESP(s_rresp),
        .S00_AXI_RVALID(s_rvalid), .S00_AXI_RREADY(s_rready),

        .M00_AXI_ACLK(clk), .M00_AXI_ARESETN(rstn),
        .M00_AXI_AWADDR(m_awaddr), .M00_AXI_AWLEN(m_awlen), .M00_AXI_AWSIZE(),
        .M00_AXI_AWBURST(), .M00_AXI_AWLOCK(), .M00_AXI_AWCACHE(),
        .M00_AXI_AWPROT(), .M00_AXI_AWQOS(),
        .M00_AXI_AWVALID(m_awvalid), .M00_AXI_AWREADY(m_awready),
        .M00_AXI_WDATA(m_wdata), .M00_AXI_WSTRB(m_wstrb), .M00_AXI_WLAST(m_wlast),
        .M00_AXI_WVALID(m_wvalid), .M00_AXI_WREADY(m_wready),
        .M00_AXI_BRESP(m_bresp), .M00_AXI_BVALID(m_bvalid), .M00_AXI_BREADY(m_bready),
        .M00_AXI_ARADDR(m_araddr), .M00_AXI_ARLEN(m_arlen), .M00_AXI_ARSIZE(),
        .M00_AXI_ARBURST(), .M00_AXI_ARLOCK(), .M00_AXI_ARCACHE(),
        .M00_AXI_ARPROT(), .M00_AXI_ARQOS(),
        .M00_AXI_ARVALID(m_arvalid), .M00_AXI_ARREADY(m_arready),
        .M00_AXI_RDATA(m_rdata), .M00_AXI_RRESP(m_rresp), .M00_AXI_RLAST(m_rlast),
        .M00_AXI_RVALID(m_rvalid), .M00_AXI_RREADY(m_rready)
    );

    // =========================================================
    // 存储模型
    // =========================================================
    reg [63:0] mem_in  [0:IN_BEATS-1];
    reg [63:0] mem_out [0:OUT_BEATS+15];
    reg [63:0] expect  [0:OUT_BEATS-1];
    reg        written [0:OUT_BEATS+15];

    integer i;
    initial begin
        for (i=0; i<OUT_BEATS+16; i=i+1) begin mem_out[i]=64'hx; written[i]=1'b0; end
    end

    // ---------------- 读通道从机 ----------------
    // 主机会在上一段突发还没做完时就流水发下一个 AR。若从机此时撤掉 ARREADY
    // 做背压，会与「输入池满 → RREADY=0」互锁；真实互连有地址缓冲不会这样。
    // 因此这里用一个深度 16 的地址队列来模拟。
    //
    // ⚠️ 深度必须够大：DUT 每次回到 S_ADDR 都会再发一个 AR，且不限制未完成读突发数，
    //    同时又阻塞在 S_ADDR 等 AR 握手。一旦输入池满（RREADY=0）而地址队列也满，
    //    就会形成死锁环 —— 这是 DUT 侧的缺陷（见 docs/03-status.md B8）。
    //    本 TB 把队列做深以绕开它，从而先验证数据通路（B5/B6）。
    integer arq_idx [0:15];
    integer arq_len [0:15];
    integer arq_cnt, arq_w, arq_r;
    reg     r_active;
    integer r_left, r_idx;

    wire ar_push = m_arvalid && m_arready;
    wire ar_pop  = (!r_active) && (arq_cnt != 0);

    always @(posedge clk) begin
        if (!rstn) begin
            arq_cnt <= 0; arq_w <= 0; arq_r <= 0;
            m_arready <= 1'b1; m_rvalid <= 1'b0; m_rlast <= 1'b0; m_rresp <= 2'b00;
            r_active <= 1'b0; r_left <= 0; r_idx <= 0;
        end else begin
            if (ar_push) begin
                arq_idx[arq_w] <= (m_araddr - IN_ADDR) >> 3;
                arq_len[arq_w] <= m_arlen + 1;
                arq_w <= (arq_w + 1) % 16;
            end
            if (ar_pop) begin
                r_idx    <= arq_idx[arq_r];
                r_left   <= arq_len[arq_r];
                arq_r    <= (arq_r + 1) % 16;
                r_active <= 1'b1;
            end
            arq_cnt   <= arq_cnt + (ar_push ? 1 : 0) - (ar_pop ? 1 : 0);
            m_arready <= (arq_cnt + (ar_push ? 1 : 0) - (ar_pop ? 1 : 0)) < Q_DEPTH;

            if (r_active && (!m_rvalid || m_rready)) begin
                if (r_left != 0) begin
                    m_rdata  <= (r_idx < IN_BEATS) ? mem_in[r_idx] : 64'd0;
                    m_rvalid <= 1'b1;
                    m_rlast  <= (r_left == 1);
                    r_idx    <= r_idx + 1;
                    r_left   <= r_left - 1;
                end else begin
                    m_rvalid <= 1'b0; m_rlast <= 1'b0;
                    r_active <= 1'b0;
                end
            end else if (m_rvalid && m_rready) begin
                m_rvalid <= 1'b0; m_rlast <= 1'b0;
            end
        end
    end

    // ---------------- 写通道从机 ----------------
    integer awq_idx [0:15];
    integer awq_len [0:15];
    integer awq_cnt, awq_w, awq_r;
    reg     w_active;
    integer w_left, w_idx, w_count;
    integer b_timer;

    wire aw_push = m_awvalid && m_awready;
    wire aw_pop  = (!w_active) && (awq_cnt != 0) && !m_bvalid;

    always @(posedge clk) begin
        if (!rstn) begin
            awq_cnt <= 0; awq_w <= 0; awq_r <= 0;
            m_awready <= 1'b1; m_wready <= 1'b0; m_bvalid <= 1'b0; m_bresp <= 2'b00;
            w_active <= 1'b0; w_left <= 0; w_idx <= 0; w_count <= 0; b_timer <= 0;
        end else begin
            if (aw_push) begin
                awq_idx[awq_w] <= (m_awaddr - OUT_ADDR) >> 3;
                awq_len[awq_w] <= m_awlen + 1;
                awq_w <= (awq_w + 1) % 16;
            end
            if (aw_pop) begin
                w_idx    <= awq_idx[awq_r];
                w_left   <= awq_len[awq_r];
                awq_r    <= (awq_r + 1) % 16;
                w_active <= 1'b1;
                m_wready <= 1'b1;
            end
            awq_cnt   <= awq_cnt + (aw_push ? 1 : 0) - (aw_pop ? 1 : 0);
            m_awready <= (awq_cnt + (aw_push ? 1 : 0) - (aw_pop ? 1 : 0)) < Q_DEPTH;

            if (w_active && m_wvalid && m_wready) begin
                if (w_idx <= OUT_BEATS+15) begin
                    mem_out[w_idx] <= m_wdata;
                    written[w_idx] <= 1'b1;
                end
                w_idx   <= w_idx + 1;
                w_count <= w_count + 1;
                w_left  <= w_left - 1;
                if (m_wlast || w_left == 1) begin
                    m_wready <= 1'b0;
                    w_active <= 1'b0;
                    b_timer  <= B_LATENCY;      // 见下方说明：B 必须有时延
                end
            end

            // ⚠️ B 响应刻意延迟 B_LATENCY 拍。
            // DUT 在写完一段突发后要过 2 拍才进入 S_WAITB，而 S_WAITB 是
            // 【电平】等待 M00_AXI_BVALID。若从机在 WLAST 后立刻给 B，
            // DUT 会在进入 S_WAITB 之前就把它消费掉，然后死等一个不会再来的
            // BVALID —— 这是 DUT 侧的竞争缺陷（见 docs/03-status.md B7）。
            // 真实互连/DDR 的 B 时延足够大，掩盖了这个问题。
            if (B_LATENCY == 0) begin
                if (w_active && m_wvalid && m_wready && (m_wlast || w_left == 1))
                    m_bvalid <= 1'b1;          // WLAST 同拍即给 B（最苛刻）
            end else if (b_timer != 0) begin
                b_timer <= b_timer - 1;
                if (b_timer == 1) m_bvalid <= 1'b1;
            end
            if (m_bvalid && m_bready) m_bvalid <= 1'b0;
        end
    end

    // =========================================================
    // AXI-Lite 写任务（真正驱动 AWVALID / WVALID）
    // =========================================================
    task axil_write(input [5:0] addr, input [31:0] data);
        integer wait_cycles;
        begin
            @(negedge clk);
            s_awaddr = addr; s_awvalid = 1'b1; s_bready = 1'b1;
            wait_cycles = 0;
            while (!s_awready && wait_cycles < 20) begin
                @(negedge clk); wait_cycles = wait_cycles + 1;
            end
            if (!s_awready) $fatal(1, "AXI-Lite AW 握手超时");
            @(posedge clk); @(negedge clk); s_awvalid = 1'b0;

            s_wdata = data; s_wstrb = 4'hF; s_wvalid = 1'b1;
            wait_cycles = 0;
            while (!s_wready && wait_cycles < 20) begin
                @(negedge clk); wait_cycles = wait_cycles + 1;
            end
            if (!s_wready) $fatal(1, "AXI-Lite W 握手超时");
            @(posedge clk); @(negedge clk); s_wvalid = 1'b0;

            wait_cycles = 0;
            while (!s_bvalid && wait_cycles < 20) begin
                @(negedge clk); wait_cycles = wait_cycles + 1;
            end
            if (!s_bvalid) $fatal(1, "AXI-Lite B 响应超时");
            @(posedge clk); @(negedge clk); s_bready = 1'b0;
        end
    endtask

    task axil_read(input [5:0] addr, output [31:0] data);
        begin
            @(posedge clk);
            s_araddr <= addr; s_arvalid <= 1'b1;
            wait (s_arready);
            @(posedge clk);
            s_arvalid <= 1'b0;
            wait (s_rvalid);
            data = s_rdata;
            @(posedge clk);
        end
    endtask

    // =========================================================
    // 主流程
    // =========================================================
    integer errors = 0;
    integer bit_errors = 0;
    integer k, b;
    reg [63:0] got, exp, mask;
    integer timeout;
    reg [31:0] cyc_total, cyc_rd_busy, cyc_wr_busy, cyc_rd_wait;
    reg [8*256-1:0] input_path, expect_path, dump_stage3_path;
    integer plusarg_result;
    integer dump_stage3_en, dump_fd;

    // 导出的文件来自 AXI 写内存模型中的 DUT 实际输出，不复制期望向量。
    initial dump_stage3_en = $value$plusargs("dump_stage3=%s", dump_stage3_path);

    initial begin
        s_awvalid=0; s_wvalid=0; s_bready=0; s_arvalid=0; s_rready=1;
        s_awaddr=0; s_wdata=0; s_wstrb=0; s_araddr=0;

        input_path = "tests/golden/sparse_ideal.hex";
        expect_path = "tests/golden/stage3_ideal_expect.hex";
        plusarg_result = $value$plusargs("input=%s", input_path);
        plusarg_result = $value$plusargs("expect=%s", expect_path);
        $readmemh(input_path, mem_in);
        $readmemh(expect_path, expect);
        $display("[TB] 已载入激励 %0d 拍 / 期望 %0d 拍", IN_BEATS, OUT_BEATS);

        repeat (10) @(posedge clk);
        rstn = 1;
        repeat (10) @(posedge clk);

        axil_write(6'h00, IN_ADDR);
        axil_write(6'h04, IN_BEATS);
        axil_write(6'h08, OUT_ADDR);
        axil_write(6'h0C, OUT_BEATS);
        axil_write(6'h10, 32'd1);          // START
        $display("[TB] 已配置寄存器并启动");

        timeout = 0;
        while (w_count < OUT_BEATS && timeout < 3_000_000) begin
            @(posedge clk);
            timeout = timeout + 1;
        end
        repeat (200) @(posedge clk);

        if (w_count < OUT_BEATS) begin
            $display("[TB] ✗ 超时：只写出 %0d/%0d 拍", w_count, OUT_BEATS);
            $fatal(1);
        end
        $display("[TB] 写出 %0d 拍（期望 %0d）", w_count, OUT_BEATS);

        // P7: 硬件周期计数器读出与验证
        axil_read(6'h14, cyc_total);
        axil_read(6'h1C, cyc_rd_busy);
        axil_read(6'h20, cyc_wr_busy);
        axil_read(6'h24, cyc_rd_wait);
        $display("[TB] 硬件周期：总计 %0d，读引擎活动 %0d，写引擎活动 %0d，读等待DDR %0d",
                 cyc_total, cyc_rd_busy, cyc_wr_busy, cyc_rd_wait);
        if (cyc_total == 0) begin
            $display("[TB] ✗ CYCLES_TOTAL 未正确计数 (0)");
            errors = errors + 1;
        end

        for (k=0; k<OUT_BEATS; k=k+1) begin
            // 最后一拍只有 OUT_BITS-64*(OUT_BEATS-1) 位有效
            mask = (k == OUT_BEATS-1) ? ((64'd1 << (OUT_BITS-64*(OUT_BEATS-1))) - 64'd1)
                                      : {64{1'b1}};
            got = mem_out[k] & mask;
            exp = expect[k]  & mask;
            if (!written[k]) begin
                if (errors < 10) $display("[TB] ✗ 第 %0d 拍未被写入", k);
                errors = errors + 1;
            end else if (got !== exp) begin
                for (b=0; b<64; b=b+1)
                    if (mask[b] && (got[b] !== exp[b])) bit_errors = bit_errors + 1;
                if (errors < 10)
                    $display("[TB] ✗ 第 %0d 拍不符  实得 %h  期望 %h", k, got, exp);
                errors = errors + 1;
            end
        end

        $display("--------------------------------------------------");
        if (errors == 0) begin
            $display("[TB] ✓ PASS  %0d 拍 / %0d bit 与黄金向量逐位相同", OUT_BEATS, OUT_BITS);
            if (dump_stage3_en) begin
                dump_fd = $fopen(dump_stage3_path, "w");
                if (dump_fd == 0) begin
                    $display("[TB] ✗ 无法打开 Stage3 checkpoint: %s", dump_stage3_path);
                    $fatal(1);
                end
                for (k = 0; k < OUT_BEATS; k = k + 1)
                    $fdisplay(dump_fd, "%016h", mem_out[k]);
                $fclose(dump_fd);
                $display("[TB] ✓ 已导出实际 Stage3 checkpoint: %s", dump_stage3_path);
            end
        end else
            $display("[TB] ✗ FAIL  %0d 拍不符，共 %0d bit 错", errors, bit_errors);
        $display("--------------------------------------------------");
        if (errors != 0) $fatal(1);
        $finish;
    end

endmodule
