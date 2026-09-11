// =============================================================
// tb_differential_voter.v — Stage2 差分投票核的文件型 Testbench
//
// 用黄金向量做判据，不是"能跑就算过"。连跑三轮，覆盖两种语义：
//   激励  tests/golden/stage2_in.hex         4,096 条 Stage1 输出记录
//                                          （2048 读段 × 正向+反向互补，
//                                           与 first.py orient="both" 一致）
//   第1轮 SCORE_MIN=67（标定阈值，int(0.45×150)，与生成
//        stage2_expect.hex 的 make_golden.py --min-score 0.45 一致）
//        → 期望 tests/golden/stage2_expect.hex（阈值过滤版，D1 语义）
//   第2轮 SCORE_MIN=67 再跑一遍 → 同一期望（验证累加器重新清零）
//   第3轮 SCORE_MIN=0（复位默认，不过滤）
//        → 期望 tests/golden/stage2_rtl_expect.hex（旧板端语义）
//
// 判据内容：
//   1) 每轮 1,266 拍输出与对应黄金向量逐位相同（末拍只比低 40 bit）；
//   2) AXI 协议：每条记录共 6 拍读数据，但**允许拆成多笔突发**（B20 修复后，
//      跨 4KB 页边界的读必须拆分）；内存模型按 ARLEN 返回拍数，并检查
//      「突发不得跨越 4KB 边界」（AXI A3.4.1）；每次写单拍（WLAST=1）；
//      末拍 WSTRB=0x1F（81000 bit = 1265×64 + 40）；
//   3) done/idle 状态位、调试寄存器（写拍数/首写地址/错误标志）正确；
//   4) SCORE_MIN 可从 AXI-Lite 0x30 读回。
//
// 运行：
//   iverilog -g2005 -o /tmp/tb_voter \
//       hw/ip/differential_voter_1_0/hdl/differential_voter_v1_0.v \
//       hw/ip/differential_voter_1_0/hdl/tb_differential_voter.v
//   vvp /tmp/tb_voter            # +dump_bram 可转储累加器做逐位置 diff
// =============================================================
`timescale 1ns/1ps

module tb_differential_voter #(
    parameter integer NUM_RECORDS = 4096,
    parameter integer RUNS = 3
);

    // 黄金向量由 make_golden.py --limit 2048 生成：2,048 × (正向+反向互补)
    localparam integer WORDS_PER_REC = 6;             // 每条记录 48 B (6 拍)
    localparam integer IN_WORDS  = NUM_RECORDS * WORDS_PER_REC;
    localparam integer OUT_BEATS = 1266;              // ceil(81000/64)
    localparam integer OUT_BITS  = 81000;

    // 与 sw/app/echo.h 的 DDR 布局一致
    localparam [31:0] IN_ADDR  = 32'h1060_0000;       // Stage1 输出区
    localparam [31:0] OUT_ADDR = 32'h1100_0000;       // Stage2 输出区

    reg clk = 0, rstn = 0;
    always #5 clk = ~clk;                             // 100 MHz

    // ---------------- AXI-Lite ----------------
    reg  [6:0]  s_awaddr;  reg s_awvalid;  wire s_awready;
    reg  [31:0] s_wdata;   reg [3:0] s_wstrb; reg s_wvalid; wire s_wready;
    wire [1:0]  s_bresp;   wire s_bvalid;  reg s_bready;
    reg  [6:0]  s_araddr;  reg s_arvalid;  wire s_arready;
    wire [31:0] s_rdata;   wire [1:0] s_rresp; wire s_rvalid; reg s_rready;

    // ---------------- AXI4 Master ----------------
    wire [31:0] m_awaddr;  wire [7:0] m_awlen;  wire m_awvalid;  reg m_awready;
    wire [63:0] m_wdata;   wire [7:0] m_wstrb;  wire m_wlast;
    wire        m_wvalid;  reg  m_wready;
    reg  [1:0]  m_bresp;   reg  m_bvalid;       wire m_bready;
    wire [31:0] m_araddr;  wire [7:0] m_arlen;  wire m_arvalid;  reg m_arready;
    reg  [63:0] m_rdata;   reg  [1:0] m_rresp;  reg  m_rlast;    reg m_rvalid;
    wire        m_rready;

    differential_voter_v1_0 dut (
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
    reg [63:0] mem_in  [0:IN_WORDS-1];
    reg [63:0] mem_out [0:OUT_BEATS+15];
    reg [63:0] expect  [0:OUT_BEATS-1];
    reg        written [0:OUT_BEATS+15];

    // ---------------- 读通道从机 ----------------
    // DUT 每条记录共取 6 拍，但可能拆成多笔突发（B20：跨 4KB 页边界必须拆分）。
    // 做完一笔才发下一笔，因此仍不需要地址队列：一次只接受一个 AR。
    // 内存模型必须**按 ARLEN 返回拍数**，绝不能写死 6——写死正是当初掩盖 B20 的原因。
    integer r_idx, r_left;
    reg     r_busy;
    integer arlen_errors;    // 现含义：违反 AXI 4KB 边界规则的突发数
    integer rec_beats;       // 本条记录已收到的拍数，用于校验每条记录恰好 6 拍
    integer recbeat_errors;  // 每条记录拍数不等于 6 的次数

    always @(posedge clk) begin
        if (!rstn) begin
            m_arready <= 1'b1; m_rvalid <= 1'b0; m_rlast <= 1'b0; m_rresp <= 2'b00;
            r_busy <= 1'b0; r_idx <= 0; r_left <= 0; arlen_errors <= 0;
            rec_beats <= 0; recbeat_errors <= 0;
        end else begin
            if (m_arvalid && m_arready && !r_busy) begin
                // AXI A3.4.1：突发不得跨越 4KB 边界
                if ((m_araddr[11:0] + ((m_arlen + 1) << 3)) > 13'd4096)
                    arlen_errors <= arlen_errors + 1;
                r_idx <= (m_araddr - IN_ADDR) >> 3;
                r_left <= m_arlen + 1;   // 按 ARLEN 返回，不得写死
                r_busy <= 1'b1;
                m_arready <= 1'b0;
            end else if (r_busy && (!m_rvalid || m_rready)) begin
                if (r_left != 0) begin
                    m_rdata  <= mem_in[r_idx];
                    m_rvalid <= 1'b1;
                    m_rlast  <= (r_left == 1);
                    r_idx    <= r_idx + 1;
                    r_left   <= r_left - 1;
                    // 每条记录必须恰好累计 9 拍（可跨多笔突发）
                    if (rec_beats == 5) rec_beats <= 0;
                    else                rec_beats <= rec_beats + 1;
                end else begin
                    // 最后一个 beat 已被消费：必须撤下 RVALID/RLAST，
                    // 否则残留电平会在下一个突发的 READ_SETUP 期间被 DUT
                    // 提前握手，后续记录的字序列错位两拍（真实互连不会这样）。
                    m_rvalid  <= 1'b0;
                    m_rlast   <= 1'b0;
                    r_busy    <= 1'b0;
                    m_arready <= 1'b1;
                end
            end
        end
    end

    // ---------------- 写通道从机 ----------------
    // DUT 每拍一个单笔写（AWLEN=0、WLAST=1），逐字递增。
    // B 响应延迟 1 拍；同时做 WLAST / WSTRB 协议检查。
    integer w_idx, w_count, b_timer;
    integer wlast_errors;
    reg [7:0] wstrb_log [0:4095];   // 每笔写当时的 WSTRB，主流程按本轮序号检查

    always @(posedge clk) begin
        if (!rstn) begin
            m_awready <= 1'b1; m_wready <= 1'b1;
            m_bvalid <= 1'b0; m_bresp <= 2'b00;
            w_idx <= 0; w_count <= 0; b_timer <= 0;
            wlast_errors <= 0;
        end else begin
            if (m_awvalid && m_awready) begin
                w_idx <= (m_awaddr - OUT_ADDR) >> 3;   // 每笔写按地址定位
                m_awready <= 1'b0;                     // 等这笔写完成再接待下一个
            end

            if (m_wvalid && m_wready) begin
                if (!m_wlast)
                    wlast_errors <= wlast_errors + 1;
                wstrb_log[w_count] <= m_wstrb;
                mem_out[w_idx] <= m_wdata;
                written[w_idx] <= 1'b1;
                w_idx   <= w_idx + 1;
                w_count <= w_count + 1;
                m_wready <= 1'b0;
                b_timer  <= 1;                          // 下一拍给 B
                m_awready <= 1'b1;                      // 重新开放 AW
            end

            if (b_timer != 0) begin
                b_timer <= b_timer - 1;
                if (b_timer == 1) m_bvalid <= 1'b1;
            end
            if (m_bvalid && m_bready) m_bvalid <= 1'b0;

            if (!m_wvalid && !m_wready) m_wready <= 1'b1; // 空闲时重新开放 W
        end
    end

    // =========================================================
    // AXI-Lite BFM（真正驱动 AWVALID/WVALID/ARVALID）
    // =========================================================
    task axil_write(input [6:0] addr, input [31:0] data);
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

    task axil_read(input [6:0] addr, output [31:0] data);
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
    // 主流程：连跑三轮，覆盖阈值/复位两种语义
    //   第 1、2 轮 SCORE_MIN=67 → stage2_expect.hex（D1 阈值语义 + 清零复验）
    //   第 3 轮   SCORE_MIN=0  → stage2_rtl_expect.hex（复位默认，不过滤）
    // =========================================================
    localparam integer SCORE_MIN_THR = 67;   // = int(0.45×150)，与 make_golden 一致

    integer errors, bit_errors, proto_errors;
    integer k, b, j, run, timeout, polls, score_min_run, run_limit;
    integer w_count0, wlast0, arlen0;
    reg [63:0] got, exp, mask;
    reg [7:0]  wstrb_got;
    reg [31:0] status, errflags, dbg;
    reg [31:0] cyc_total, cyc_init, cyc_read, cyc_vote, cyc_write;

    reg [63:0] expect_thr  [0:OUT_BEATS-1];  // 阈值版（stage2_expect.hex）
    reg [63:0] exp_work    [0:OUT_BEATS-1];  // 本轮选用的期望
    reg [8*256-1:0] input_path, expect_path, expect_thr_path;
    reg [8*256-1:0] dump_stage2_path;
    integer dump_stage2_en;
    integer plusarg_result;
    integer dump_fd;

    // Optional checkpoint export.  The file is emitted from the actual AXI
    // write memory, never from a golden vector.
    initial dump_stage2_en = $value$plusargs("dump_stage2=%s", dump_stage2_path);

    // 看门狗
    initial begin
        #2_000_000_000;
        $display("[TB] ✗ 全局看门狗超时");
        $fatal(1);
    end

    // +dump_bram：第 1 轮结束后把 81,000 个累加器转储到 /tmp（调试用）
    reg dump_en;
    initial dump_en = $test$plusargs("dump_bram");

    initial begin
        s_awvalid=0; s_wvalid=0; s_bready=0; s_arvalid=0; s_rready=1;
        s_awaddr=0; s_wdata=0; s_wstrb=0; s_araddr=0;

        input_path = "tests/golden/stage2_in.hex";
        expect_path = "tests/golden/stage2_rtl_expect.hex";
        expect_thr_path = "tests/golden/stage2_expect.hex";
        run_limit = RUNS;
        plusarg_result = $value$plusargs("input=%s", input_path);
        plusarg_result = $value$plusargs("expect=%s", expect_path);
        plusarg_result = $value$plusargs("expect_thr=%s", expect_thr_path);
        plusarg_result = $value$plusargs("runs=%d", run_limit);
        $readmemh(input_path, mem_in);
        $readmemh(expect_path, expect);
        $readmemh(expect_thr_path, expect_thr);
        $display("[TB] 已载入激励 %0d 条记录 / 阈值版与无阈值版期望各 %0d 拍",
                 NUM_RECORDS, OUT_BEATS);

        repeat (10) @(posedge clk);
        rstn = 1;
        repeat (10) @(posedge clk);

        errors = 0;
        for (run = 1; run <= run_limit; run = run + 1) begin
            // 本轮语义：1/2 轮阈值过滤，第 3 轮复位默认（不过滤）
            if (run <= 2) begin
                score_min_run = SCORE_MIN_THR;
                for (k = 0; k < OUT_BEATS; k = k + 1) exp_work[k] = expect_thr[k];
            end else begin
                score_min_run = 0;
                for (k = 0; k < OUT_BEATS; k = k + 1) exp_work[k] = expect[k];
            end

            // 清输出区（DUT 空闲时无写活动，可与从机共存）
            for (k = 0; k < OUT_BEATS+16; k = k + 1) begin
                mem_out[k] = 64'hx; written[k] = 1'b0;
            end
            w_count0 = w_count; wlast0 = wlast_errors; arlen0 = arlen_errors;

            axil_write(7'h04, IN_ADDR);                // IN_ADDR
            axil_write(7'h08, NUM_RECORDS * WORDS_PER_REC); // IN_BEATS (4096 * 9)
            axil_write(7'h0C, OUT_ADDR);               // OUT_ADDR
            axil_write(7'h10, OUT_BEATS);              // OUT_BEATS
            axil_write(7'h14, NUM_RECORDS);            // TOTAL_READS
            axil_write(7'h30, score_min_run);          // SCORE_MIN（0x30）
            axil_read (7'h30, dbg);                    // 读回校验
            if (dbg != score_min_run) begin
                $display("[TB] ✗ 第 %0d 轮 SCORE_MIN 读回 %0d（期望 %0d）",
                         run, dbg, score_min_run);
                errors = errors + 1;
            end
            axil_write(7'h00, 32'd1);                  // START
            $display("[TB] 第 %0d 轮：SCORE_MIN=%0d，已启动", run, score_min_run);

            // 轮询 0x00 的 DONE（bit1）
            polls = 0; status = 32'd0;
            while (!status[1] && polls < 3_000_000) begin
                axil_read(7'h00, status);
                polls = polls + 1;
            end
            repeat (100) @(posedge clk);

            if (!status[1]) begin
                $display("[TB] ✗ 第 %0d 轮超时：DONE 未置位（status=%h）", run, status);
                $fatal(1);
            end
            // DONE 在 S_DONE 那一拍就置位，此时 IDLE 还是 0；等状态机回到
            // S_IDLE 再确认 IDLE=1。
            repeat (10) @(posedge clk);
            axil_read(7'h00, status);
            if (!status[0]) begin
                $display("[TB] ✗ 第 %0d 轮 DONE 后 IDLE 未回 1（status=%h）", run, status);
                errors = errors + 1;
            end
            // 调试：+dump_bram 时转储累加器（与 tools/debug_vote_diff.py 配合用）
            if (run == 1 && dump_en) $writememh("/tmp/voter_bram_dump.hex", dut.bram);

            // 调试寄存器：写拍数 / 首写地址 / 错误标志
            axil_read(7'h24, dbg);
            if (dbg != OUT_BEATS) begin
                $display("[TB] ✗ 第 %0d 轮 DBG_WRITE=%0d（期望 %0d）", run, dbg, OUT_BEATS);
                errors = errors + 1;
            end
            axil_read(7'h28, dbg);
            if (dbg != OUT_ADDR) begin
                $display("[TB] ✗ 第 %0d 轮 DBG_FIRST_AWADDR=%h（期望 %h）", run, dbg, OUT_ADDR);
                errors = errors + 1;
            end
            axil_read(7'h2C, errflags);
            if (errflags != 32'd0) begin
                $display("[TB] ✗ 第 %0d 轮 ERR_FLAGS=%h（期望 0）", run, errflags);
                errors = errors + 1;
            end

            // P7: 硬件周期计数器读出与验证
            axil_read(7'h40, cyc_total);
            axil_read(7'h44, cyc_init);
            axil_read(7'h48, cyc_read);
            axil_read(7'h4C, cyc_vote);
            axil_read(7'h50, cyc_write);
            $display("[TB] 第 %0d 轮硬件周期：总计 %0d，BRAM清零 %0d，DDR读 %0d，投票流水 %0d，DDR写回 %0d",
                     run, cyc_total, cyc_init, cyc_read, cyc_vote, cyc_write);
            if (cyc_total == 0 || cyc_total != (cyc_init + cyc_read + cyc_vote + cyc_write)) begin
                $display("[TB] ✗ 第 %0d 轮周期计数器守恒校验失败：total=%0d != init(%0d)+read(%0d)+vote(%0d)+write(%0d)",
                         run, cyc_total, cyc_init, cyc_read, cyc_vote, cyc_write);
                errors = errors + 1;
            end

            // 协议检查
            proto_errors = (w_count  - w_count0 - OUT_BEATS)
                         + (wlast_errors - wlast0)
                         + (arlen_errors - arlen0)
                         + recbeat_errors;
            if (w_count - w_count0 != OUT_BEATS)
                $display("[TB] ✗ 第 %0d 轮写出 %0d 拍（期望 %0d）",
                         run, w_count - w_count0, OUT_BEATS);
            if (wlast_errors != wlast0)
                $display("[TB] ✗ 第 %0d 轮出现 %0d 拍 WLAST=0（单拍写必须 WLAST=1）",
                         run, wlast_errors - wlast0);
            if (arlen_errors != arlen0)
                $display("[TB] ✗ 第 %0d 轮出现 %0d 笔跨 4KB 边界的读突发（违反 AXI A3.4.1）",
                         run, arlen_errors - arlen0);
            errors = errors + (proto_errors > 0 ? 1 : 0);

            // 逐位比对：末拍只有低 OUT_BITS-64*(OUT_BEATS-1)=40 位有效
            bit_errors = 0;
            for (k = 0; k < OUT_BEATS; k = k + 1) begin
                mask = (k == OUT_BEATS-1)
                     ? ((64'd1 << (OUT_BITS-64*(OUT_BEATS-1))) - 64'd1)
                     : {64{1'b1}};
                got = mem_out[k] & mask;
                exp = exp_work[k] & mask;
                // WSTRB：末拍（第 1266 拍）只写低 5 字节，其余拍全字节
                wstrb_got = wstrb_log[w_count0 + k];
                if (k == OUT_BEATS-1 ? (wstrb_got != 8'h1F) : (wstrb_got != 8'hFF)) begin
                    if (errors < 10)
                        $display("[TB] ✗ 第 %0d 轮第 %0d 拍 WSTRB=%h（期望 %h）",
                                 run, k, wstrb_got, (k == OUT_BEATS-1) ? 8'h1F : 8'hFF);
                    errors = errors + 1;
                end
                if (!written[k]) begin
                    if (errors < 10) $display("[TB] ✗ 第 %0d 轮第 %0d 拍未被写入", run, k);
                    errors = errors + 1;
                end else if (got !== exp) begin
                    for (b = 0; b < 64; b = b + 1)
                        if (mask[b] && (got[b] !== exp[b])) bit_errors = bit_errors + 1;
                    if (errors < 10)
                        $display("[TB] ✗ 第 %0d 轮第 %0d 拍不符  实得 %h  期望 %h",
                                 run, k, got, exp);
                    errors = errors + 1;
                end
            end
            if (bit_errors == 0 && errors == 0)
                $display("[TB] 第 %0d 轮：1,266 拍 / 81,000 bit 与黄金向量逐位相同", run);
            if (dump_stage2_en && run == run_limit) begin
                dump_fd = $fopen(dump_stage2_path, "w");
                if (dump_fd == 0) begin
                    $display("[TB] ✗ 无法打开 Stage2 checkpoint: %s", dump_stage2_path);
                    $fatal(1);
                end
                for (j = 0; j < OUT_BEATS; j = j + 1)
                    $fdisplay(dump_fd, "%016h", mem_out[j]);
                $fclose(dump_fd);
                $display("[TB] ✓ 已导出实际 Stage2 checkpoint: %s", dump_stage2_path);
            end
        end

        $display("--------------------------------------------------");
        if (errors == 0)
            $display("[TB] ✓ PASS  %0d 轮与黄金向量逐位相同", run_limit);
        else
            $display("[TB] ✗ FAIL  共 %0d 项不符", errors);
        $display("--------------------------------------------------");
        if (errors != 0) $fatal(1);
        $finish;
    end

endmodule
