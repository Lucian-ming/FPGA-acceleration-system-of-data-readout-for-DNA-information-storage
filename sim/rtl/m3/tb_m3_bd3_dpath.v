// ================================================================
// tb_m3_bd3_dpath.v —— M3 / BD-3：实际 Block Design 的数据面事务
//
// DUT 仍是 bd.tcl 生成的**实际** top_bd_wrapper：
//   PS7 VIP（含 DDR 模型）→ M_AXI_GP0 → 实际 ic_lite → 三个自研 IP 的 AXI-Lite；
//   Voter / Decoder 的 **实际 AXI4 主口** → 实际 ic_hp → PS7 S_AXI_HP0 → VIP DDR。
//
// 与 BD-2 的区别：BD-2 只证明「能配寄存器」，BD-3 让 IP 真的经由实际 Interconnect
// 去 DDR 读写业务数据，覆盖突发、WSTRB/WLAST、背压和响应码。
//
// 真实性红线（与 M2 一致，见 docs/archive/history/2026/xsim-simulation-plan.md §6.3）：
//   - DDR 的输入镜像由外部脚本从**上一级实际输出**派生，黄金向量只用于最终比较；
//   - 本 TB 不读取任何 *_expect 文件，不做任何「期望值注入」；
//   - 每一级都跑在实际地址（docs/04-interfaces.md §4）上。
//
// 用 plusarg 选择本次跑哪一级，便于像 run_m2_full.sh 那样把 PS 等价 XOR
// 放在两次仿真之间的 Python 里，保持级间数据是真实的。
//
//   +stage=voter|decoder      本次驱动哪个 IP
//   +mem_in=<file>            DDR 输入镜像（VIP 32bit 字格式）
//   +mem_out=<file>           运行后把该级输出区 dump 出来
//   +total_reads=<N>          Voter 的记录数（默认 4096）
//   +latency=<0|1|2>          HP0 从机延迟档：0=BEST(零延迟) 2=WORST(带背压)
// ================================================================

`timescale 1 ps / 1 ps

module tb_m3_bd3_dpath;

    top_bd_wrapper dut ();

    `define PS7 dut.top_bd_i.ps_0.inst

    // 地址（docs/04-interfaces.md §3、§4，BD-1 已核对 bd_address.txt）
    localparam [31:0] ADDR_VOTER = 32'h43C2_0000;
    localparam [31:0] ADDR_DEC   = 32'h43C1_0000;

    // 默认使用 docs/04-interfaces.md §4 的真实地址；可用 plusarg 覆盖，
    // 用于诊断「地址是否落在仿真内存模型可服务范围内」这类问题。
    reg [31:0] DDR_STAGE1_OUT = 32'h1060_0000;  // Voter 输入
    reg [31:0] DDR_STAGE2_OUT = 32'h1100_0000;  // Voter 输出 / Decoder 输入
    reg [31:0] DDR_STAGE3_OUT = 32'h1110_0000;  // Decoder 输出

    localparam VOTER_OUT_BEATS_N = 1266;   // 81,000 bit
    localparam DEC_IN_BEATS_N    = 1266;
    localparam DEC_OUT_BEATS_N   = 1013;   // 64,800 bit

    // Voter 寄存器
    localparam VOTER_STATUS      = 8'h00;
    localparam VOTER_IN_ADDR     = 8'h04;
    localparam VOTER_IN_BEATS    = 8'h08;
    localparam VOTER_OUT_ADDR    = 8'h0C;
    localparam VOTER_OUT_BEATS   = 8'h10;
    localparam VOTER_TOTAL_READS = 8'h14;
    localparam VOTER_ERR_FLAGS   = 8'h2C;
    localparam VOTER_SCORE_MIN   = 8'h30;
    localparam VOTER_LAST_RRESP  = 8'h38;

    // Decoder 寄存器
    localparam DEC_IN_ADDR   = 8'h00;
    localparam DEC_IN_BEATS  = 8'h04;
    localparam DEC_OUT_ADDR  = 8'h08;
    localparam DEC_OUT_BEATS = 8'h0C;
    localparam DEC_START     = 8'h10;
    localparam DEC_STATUS    = 8'h18;

    integer errors = 0;

    reg [2047:0] wbuf;
    reg [2047:0] rbuf;
    reg [1:0]    resp;
    reg [31:0]   rd;

    reg [1023:0] stage_arg;
    reg [1023:0] mem_in;
    reg [1023:0] mem_out;
    integer      total_reads;
    integer      latency_mode;
    integer      poll;
    integer      vip_debug;

    localparam POLL_LIMIT = 2000000;   // 轮询上限，超过即判超时失败

    task axi_write32;
        input [31:0] addr;
        input [31:0] data;
        begin
            wbuf = {2048{1'b0}};
            wbuf[31:0] = data;
            `PS7.write_data(addr, 4, wbuf, resp);
            if (resp !== 2'b00) begin
                errors = errors + 1;
                $display("[TB] FAIL: write 0x%08x 返回 BRESP=%b", addr, resp);
            end
        end
    endtask

    task axi_read32;
        input  [31:0] addr;
        output [31:0] data;
        begin
            rbuf = {2048{1'b0}};
            `PS7.read_data(addr, 4, rbuf, resp);
            data = rbuf[31:0];
            if (resp !== 2'b00) begin
                errors = errors + 1;
                $display("[TB] FAIL: read 0x%08x 返回 RRESP=%b", addr, resp);
            end
        end
    endtask

    // 写后回读，配置必须真的落进 IP（对应 echo.c 的回读校验）
    task write_verify32;
        input [31:0] addr;
        input [31:0] data;
        reg   [31:0] back;
        begin
            axi_write32(addr, data);
            axi_read32(addr, back);
            if (back !== data) begin
                errors = errors + 1;
                $display("[TB] FAIL: 配置回读 0x%08x = 0x%08x，期望 0x%08x",
                         addr, back, data);
            end
        end
    endtask

    initial begin
        $display("[TB] ============ M3 / BD-3 数据面事务 ============");

        if (!$value$plusargs("stage=%s", stage_arg)) begin
            $display("[TB] FATAL: 必须指定 +stage=voter|decoder");
            $fatal(1, "missing +stage");
        end
        if (!$value$plusargs("mem_in=%s", mem_in)) begin
            $display("[TB] FATAL: 必须指定 +mem_in=<file>");
            $fatal(1, "missing +mem_in");
        end
        if (!$value$plusargs("mem_out=%s", mem_out)) begin
            $display("[TB] FATAL: 必须指定 +mem_out=<file>");
            $fatal(1, "missing +mem_out");
        end
        if (!$value$plusargs("total_reads=%d", total_reads)) total_reads = 4096;
        if ($value$plusargs("s1_addr=%h", DDR_STAGE1_OUT)) ;
        if ($value$plusargs("s2_addr=%h", DDR_STAGE2_OUT)) ;
        if ($value$plusargs("s3_addr=%h", DDR_STAGE3_OUT)) ;
        if (!$value$plusargs("latency=%d", latency_mode))    latency_mode = 0;

        `PS7.set_stop_on_error(0);
        // +vipdebug=1 打开 VIP 内部（含 DDR 读写端口与 HP 交换开关）的详细日志，
        // 只用于定位，不作为判据。
        if ($value$plusargs("vipdebug=%d", vip_debug) && vip_debug != 0)
            `PS7.set_debug_level_info(1);

        // HP0 从机延迟档：0=BEST_CASE（零延迟），2=WORST_CASE（最坏延迟/带背压）。
        // 两档都必须通过，才能说明 IP 不依赖某种理想内存时序。
        `PS7.set_slave_profile("S_AXI_HP0", latency_mode[1:0]);
        $display("[TB] HP0 从机延迟档 = %0d (0=BEST/零延迟, 2=WORST/带背压)", latency_mode);

        wait (dut.top_bd_i.rst_ps_peripheral_aresetn === 1'b1);
        repeat (50) @(posedge dut.top_bd_i.clk_wiz_0_clk_out1);
        $display("[TB] PL 复位已释放 @%0t ps", $time);

        if (stage_arg == "voter") run_voter;
        else if (stage_arg == "decoder") run_decoder;
        else begin
            $display("[TB] FATAL: 未知 stage=%0s", stage_arg);
            $fatal(1, "bad stage");
        end

        $display("[TB] --------------------------------------------------");
        if (errors != 0) begin
            $display("[TB] BD-3 FAIL（%0d 项）", errors);
            $fatal(1, "BD-3 数据面用例失败");
        end
        $display("[TB] PASS  BD-3 %0s：经实际 Interconnect 完成 DDR 读写", stage_arg);
        $display("[TB] --------------------------------------------------");
        $finish;
    end

    // ---------------- Stage2 / Voter ----------------
    task run_voter;
        begin
            $display("[TB] ---- Voter：%0d 条记录，输入 0x%08x，输出 0x%08x ----",
                     total_reads, DDR_STAGE1_OUT, DDR_STAGE2_OUT);

            // 预载 Stage1 实际输出（外部脚本派生，非期望值）
            `PS7.pre_load_mem_from_file(mem_in, DDR_STAGE1_OUT, total_reads * 48);
            $display("[TB] 已预载 %0d B 到 0x%08x", total_reads * 48, DDR_STAGE1_OUT);

            // 按 echo.c PIPE_VOTER_* 的顺序配置并回读校验
            write_verify32(ADDR_VOTER + VOTER_IN_ADDR,     DDR_STAGE1_OUT);
            write_verify32(ADDR_VOTER + VOTER_IN_BEATS,    total_reads);
            write_verify32(ADDR_VOTER + VOTER_OUT_ADDR,    DDR_STAGE2_OUT);
            write_verify32(ADDR_VOTER + VOTER_OUT_BEATS,   VOTER_OUT_BEATS_N);
            write_verify32(ADDR_VOTER + VOTER_TOTAL_READS, total_reads);
            write_verify32(ADDR_VOTER + VOTER_SCORE_MIN,   32'd67);

            // start_pulse
            axi_write32(ADDR_VOTER + VOTER_STATUS, 32'h1);
            $display("[TB] Voter 已启动，等待 done ...");

            poll = 0;
            rd = 0;
            while (rd[1] !== 1'b1 && poll < POLL_LIMIT) begin
                repeat (200) @(posedge dut.top_bd_i.clk_wiz_0_clk_out1);
                axi_read32(ADDR_VOTER + VOTER_STATUS, rd);
                poll = poll + 1;
            end
            if (rd[1] !== 1'b1) begin
                errors = errors + 1;
                $display("[TB] FAIL: Voter done 超时（STATUS=0x%08x）", rd);
            end else begin
                $display("[TB] Voter done @%0t ps（轮询 %0d 次）", $time, poll);
            end

            // 错误标志与最后一次 RRESP：任何 AXI 层面的错误都必须暴露
            axi_read32(ADDR_VOTER + VOTER_ERR_FLAGS, rd);
            if (rd !== 32'd0) begin
                errors = errors + 1;
                $display("[TB] FAIL: Voter 错误标志 0x%08x（bit0=error, bit1=bresp_err）", rd);
            end else $display("[TB]   ok  Voter 错误标志 = 0");

            axi_read32(ADDR_VOTER + VOTER_LAST_RRESP, rd);
            if (rd[1:0] !== 2'b00) begin
                errors = errors + 1;
                $display("[TB] FAIL: Voter 最后一次读响应 RRESP=%b（期望 OKAY）", rd[1:0]);
            end else $display("[TB]   ok  Voter 最后一次 RRESP = OKAY");

            // dump 实际写进 DDR 的结果，交给外部脚本与黄金向量比较
            `PS7.peek_mem_to_file(mem_out, DDR_STAGE2_OUT, VOTER_OUT_BEATS_N * 8);
            $display("[TB] 已 dump %0d B 到 %0s", VOTER_OUT_BEATS_N * 8, mem_out);
        end
    endtask

    // ---------------- Stage3 / Decoder ----------------
    task run_decoder;
        begin
            $display("[TB] ---- Decoder：输入 0x%08x，输出 0x%08x ----",
                     DDR_STAGE2_OUT, DDR_STAGE3_OUT);

            // 预载「Stage2 实际输出 经 PS 等价 XOR」的结果（外部脚本派生）
            `PS7.pre_load_mem_from_file(mem_in, DDR_STAGE2_OUT, DEC_IN_BEATS_N * 8);
            $display("[TB] 已预载 %0d B 到 0x%08x", DEC_IN_BEATS_N * 8, DDR_STAGE2_OUT);

            write_verify32(ADDR_DEC + DEC_IN_ADDR,   DDR_STAGE2_OUT);
            write_verify32(ADDR_DEC + DEC_IN_BEATS,  DEC_IN_BEATS_N);
            write_verify32(ADDR_DEC + DEC_OUT_ADDR,  DDR_STAGE3_OUT);
            write_verify32(ADDR_DEC + DEC_OUT_BEATS, DEC_OUT_BEATS_N);

            axi_write32(ADDR_DEC + DEC_START, 32'h1);
            $display("[TB] Decoder 已启动，等待 done ...");

            poll = 0;
            rd = 0;
            while (rd[1] !== 1'b1 && poll < POLL_LIMIT) begin
                repeat (200) @(posedge dut.top_bd_i.clk_wiz_0_clk_out1);
                axi_read32(ADDR_DEC + DEC_STATUS, rd);
                poll = poll + 1;
            end
            if (rd[1] !== 1'b1) begin
                errors = errors + 1;
                $display("[TB] FAIL: Decoder done 超时（STATUS=0x%08x）", rd);
            end else begin
                $display("[TB] Decoder done @%0t ps（轮询 %0d 次）", $time, poll);
            end

            `PS7.peek_mem_to_file(mem_out, DDR_STAGE3_OUT, DEC_OUT_BEATS_N * 8);
            $display("[TB] 已 dump %0d B 到 %0s", DEC_OUT_BEATS_N * 8, mem_out);
        end
    endtask

    // HP0 AR/R 通道探针（仅 +vipdebug=1 时打印），用于定位读事务卡死。
    integer ar_seen = 0;
    integer r_seen  = 0;
    always @(posedge dut.top_bd_i.clk_wiz_0_clk_out1) begin
        if (dut.top_bd_i.ic_hp_M00_AXI_ARVALID &&
            dut.top_bd_i.ic_hp_M00_AXI_ARREADY) begin
            ar_seen = ar_seen + 1;
            if (vip_debug != 0 && ar_seen < 20)
                $display("[PROBE] %0t AR#%0d addr=0x%08x len=%0d size=%0d burst=%b id=%b cache=%b prot=%b lock=%b",
                         $time, ar_seen,
                         dut.top_bd_i.ic_hp_M00_AXI_ARADDR,
                         dut.top_bd_i.ic_hp_M00_AXI_ARLEN,
                         dut.top_bd_i.ic_hp_M00_AXI_ARSIZE,
                         dut.top_bd_i.ic_hp_M00_AXI_ARBURST,
                         dut.top_bd_i.ic_hp_M00_AXI_ARID,
                         dut.top_bd_i.ic_hp_M00_AXI_ARCACHE,
                         dut.top_bd_i.ic_hp_M00_AXI_ARPROT,
                         dut.top_bd_i.ic_hp_M00_AXI_ARLOCK);
        end
        if (dut.top_bd_i.ic_hp_M00_AXI_RVALID &&
            dut.top_bd_i.ic_hp_M00_AXI_RREADY) begin
            r_seen = r_seen + 1;
            if (vip_debug != 0 && r_seen < 20)
                $display("[PROBE] %0t R#%0d data=0x%016x last=%b resp=%b",
                         $time, r_seen,
                         dut.top_bd_i.ic_hp_M00_AXI_RDATA,
                         dut.top_bd_i.ic_hp_M00_AXI_RLAST,
                         dut.top_bd_i.ic_hp_M00_AXI_RRESP);
        end
    end

    // 全局看门狗。
    // 注意：无尺寸十进制字面量默认 32 bit，200_000_000_000 ps 会溢出并退化成 0 延迟，
    // 让看门狗在 0 时刻立刻开火。这里拆成 200 × 1 ms，每段都在 32 bit 内。
    initial begin
        repeat (200) #1_000_000_000;   // 200 × 1 ms = 200 ms
        $display("[TB] FATAL: BD-3 全局超时");
        $fatal(1, "BD-3 超时");
    end

endmodule
