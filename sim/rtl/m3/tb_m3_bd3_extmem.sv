// ================================================================
// tb_m3_bd3_extmem.sv —— M3 / BD-3：数据面（仿真专用内存端点版本）
//
// 与 tb_m3_bd3_dpath.v 的唯一区别是**内存端点**：
//   DUT 用 hw/scripts/bd_sim_mem.tcl 生成的 BD 变体，其中 ps_0/S_AXI_HP0
//   被替换成 axi_vip(SLAVE) 内存模型，其余（实际 ic_lite / ic_hp / AXI DMA /
//   三个自研 IP / PS7 VIP 的 GP0 控制通路 / 全部地址映射）与生产 BD 完全一致。
//
// 为什么需要它：Vivado 2022.2 的 processing_system7_vip 的 HP/AFI 从机读通路
// 在本配置下接受 AR 后不返回任何 RDATA（已逐条排除设计侧因素，见
// docs/archive/history/2026/m3-bd-simulation-2026-08-29.md §5）。本 TB 绕开该仿真模型缺陷，
// 让数据面判据得以执行。
//
// ⚠️ 结论边界：内存端点**不是实际 PS7 的 AFI 通路**。本 TB 能证明
//    「三个自研 IP 经实际 Interconnect 在真实地址上正确读写内存」，
//    **不能**证明 PS7 AFI/DDR 控制器本身的行为。引用本 TB 结论时必须写明这一点。
//
// 真实性红线（与 M2 / BD-3 一致）：
//   - 内存镜像由外部脚本从上一级**实际输出**派生，黄金向量只用于最终比较；
//   - 本 TB 不读取任何 *_expect 文件，不做期望值注入。
//
//   +stage=voter|decoder   本次驱动哪个 IP
//   +mem_in=<file>         内存输入镜像（每行一个 32 bit 十六进制字）
//   +mem_out=<file>        运行后把该级输出区 dump 出来（同格式）
//   +total_reads=<N>       Voter 记录数（默认 4096）
//   +latency=<0|2>         0=无背压；2=对 AW/W/AR 施加随机背压
// ================================================================

`timescale 1 ps / 1 ps

import axi_vip_pkg::*;
import top_bd_mem_vip_0_pkg::*;

module tb_m3_bd3_extmem;

    top_bd_wrapper dut ();

    // PS7 VIP 仍然负责 GP0 控制面（与 BD-2 相同的通路）
    `define PS7 dut.top_bd_i.ps_0.inst

    // 仿真专用内存端点
    top_bd_mem_vip_0_slv_mem_t mem_agent;

    // 地址（与生产 BD 完全一致，docs/04-interfaces.md §3、§4）
    localparam [31:0] ADDR_VOTER = 32'h43C2_0000;
    localparam [31:0] ADDR_DEC   = 32'h43C1_0000;

    localparam [31:0] DDR_STAGE1_OUT = 32'h1060_0000;
    localparam [31:0] DDR_STAGE2_OUT = 32'h1100_0000;
    localparam [31:0] DDR_STAGE3_OUT = 32'h1110_0000;

    localparam int VOTER_OUT_BEATS_N = 1266;
    localparam int DEC_IN_BEATS_N    = 1266;
    localparam int DEC_OUT_BEATS_N   = 1013;

    // Voter 寄存器
    localparam [7:0] VOTER_STATUS      = 8'h00;
    localparam [7:0] VOTER_IN_ADDR     = 8'h04;
    localparam [7:0] VOTER_IN_BEATS    = 8'h08;
    localparam [7:0] VOTER_OUT_ADDR    = 8'h0C;
    localparam [7:0] VOTER_OUT_BEATS   = 8'h10;
    localparam [7:0] VOTER_TOTAL_READS = 8'h14;
    localparam [7:0] VOTER_ERR_FLAGS   = 8'h2C;
    localparam [7:0] VOTER_SCORE_MIN   = 8'h30;
    localparam [7:0] VOTER_LAST_RRESP  = 8'h38;

    // Decoder 寄存器
    localparam [7:0] DEC_IN_ADDR   = 8'h00;
    localparam [7:0] DEC_IN_BEATS  = 8'h04;
    localparam [7:0] DEC_OUT_ADDR  = 8'h08;
    localparam [7:0] DEC_OUT_BEATS = 8'h0C;
    localparam [7:0] DEC_START     = 8'h10;
    localparam [7:0] DEC_STATUS    = 8'h18;

    int errors = 0;

    reg [2047:0] wbuf;
    reg [2047:0] rbuf;
    reg [1:0]    resp;
    reg [31:0]   rd;

    string stage_arg, mem_in, mem_out;
    int    total_reads;
    int    latency_mode;
    int    poll;

    localparam int POLL_LIMIT = 2000000;

    // ---------------- GP0 控制面事务 ----------------
    task automatic axi_write32(input [31:0] addr, input [31:0] data);
        wbuf = '0;
        wbuf[31:0] = data;
        `PS7.write_data(addr, 4, wbuf, resp);
        if (resp !== 2'b00) begin
            errors++;
            $display("[TB] FAIL: write 0x%08x 返回 BRESP=%b", addr, resp);
        end
    endtask

    task automatic axi_read32(input [31:0] addr, output [31:0] data);
        rbuf = '0;
        `PS7.read_data(addr, 4, rbuf, resp);
        data = rbuf[31:0];
        if (resp !== 2'b00) begin
            errors++;
            $display("[TB] FAIL: read 0x%08x 返回 RRESP=%b", addr, resp);
        end
    endtask

    task automatic write_verify32(input [31:0] addr, input [31:0] data);
        logic [31:0] back;
        axi_write32(addr, data);
        axi_read32(addr, back);
        if (back !== data) begin
            errors++;
            $display("[TB] FAIL: 配置回读 0x%08x = 0x%08x，期望 0x%08x", addr, back, data);
        end
    endtask

    // ---------------- 内存镜像装载 / 导出 ----------------
    // 格式与 PS7 VIP 的 pre_load_mem_from_file / peek_mem_to_file 一致：
    // 每行一个 32 bit 十六进制字，字 N 覆盖字节地址 4N..4N+3。
    // 这样 tools/m3_mem.py 无需任何改动即可复用。
    task automatic preload_mem(input string fname, input [31:0] base, input int nwords);
        int fd, code, i;
        logic [31:0] w;
        fd = $fopen(fname, "r");
        if (fd == 0) begin
            $display("[TB] FATAL: 打不开内存镜像 %0s", fname);
            $fatal(1, "mem_in open failed");
        end
        for (i = 0; i < nwords; i++) begin
            code = $fscanf(fd, "%h", w);
            if (code != 1) break;
            mem_agent.mem_model.backdoor_memory_write_4byte(base + 4*i, w);
        end
        $fclose(fd);
        $display("[TB] 已预载 %0d 个 32bit 字（%0d B）到 0x%08x", i, 4*i, base);
        if (i < nwords) begin
            errors++;
            $display("[TB] FAIL: 镜像只有 %0d 字，少于需要的 %0d 字", i, nwords);
        end
    endtask

    // 启动前把输出区清零：这样 DUT 用 WSTRB 有意不写的字节（如末拍超出
    // 有效载荷的部分）读回就是 0，与黄金向量一致；同时若 DUT 漏写，
    // 比较会立刻暴露成 0 而不是被残留数据掩盖。
    task automatic zero_mem(input [31:0] base, input int nwords);
        int i;
        for (i = 0; i < nwords; i++)
            mem_agent.mem_model.backdoor_memory_write_4byte(base + 4*i, 32'h0);
        $display("[TB] 已清零输出区 0x%08x 起 %0d B", base, 4*nwords);
    endtask

    task automatic dump_mem(input string fname, input [31:0] base, input int nwords);
        int fd, i;
        fd = $fopen(fname, "w");
        if (fd == 0) begin
            $display("[TB] FATAL: 打不开输出文件 %0s", fname);
            $fatal(1, "mem_out open failed");
        end
        for (i = 0; i < nwords; i++)
            $fdisplay(fd, "%08x", mem_agent.mem_model.backdoor_memory_read_4byte(base + 4*i));
        $fclose(fd);
        $display("[TB] 已 dump %0d 个 32bit 字（%0d B）到 %0s", nwords, 4*nwords, fname);
    endtask

    // ---------------- 背压 ----------------
    // latency=2 时对 AW/W/AR 三个通道施加随机 ready，模拟带背压的内存。
    //
    // ⚠️ 这里**不能**用 `XIL_AXI_READY_GEN_RANDOM` + `forever send_*ready(g)`。
    //    RANDOM 策略的 ready 对象是**一次性**的（axi_ready_gen 的 event_count 默认为 1），
    //    所以必须不断补充；而 `send_*ready()` 是**非阻塞**的，只把对象排进 VIP 队列就返回。
    //    裸 `forever` 会在同一个 delta 里无限排队，965 ns 就撞上 VIP 的硬上限
    //    「limited to 500 outstanding READY objects」；Stop-On-Error=0 让它此后每个 delta
    //    刷一条 Error —— 实测日志涨到 16 GB，xsim 被 OOM 杀掉（exit 137），
    //    此时 DUT 一拍数据都还没开始传。按时钟限速也治不了：补充速率只要略高于
    //    VIP 的消费速率（约每 low+high 拍一个），队列迟早还是会涨满，
    //    实测每 4 拍补一个只是把撞上限的时刻从 965 ns 推迟到 1,200,495 ns。
    //
    //    正确做法是用 `XIL_AXI_READY_GEN_OSC`：Vivado 的 axi_vip_pkg.sv 明确写着
    //    「the policy repeats until the channel is given different policy」——
    //    它自己无限重复，**只需要 send 一次**，队列深度恒为 1，永远撞不上 500 上限。
    //    三个通道取不同的 low/high 组合，避免相位一致把背压退化成同拍开合。

    task automatic backpressure_aw();
        axi_ready_gen g = mem_agent.wr_driver.create_ready("awready");
        g.set_ready_policy(XIL_AXI_READY_GEN_OSC);
        g.set_low_time(3);          // 低 3 拍
        g.set_high_time(1);         // 高 1 拍，然后无限重复
        mem_agent.wr_driver.send_awready(g);
    endtask

    task automatic backpressure_w();
        axi_ready_gen g = mem_agent.wr_driver.create_ready("wready");
        g.set_ready_policy(XIL_AXI_READY_GEN_OSC);
        g.set_low_time(2);          // 低 2 拍
        g.set_high_time(1);         // 高 1 拍，然后无限重复
        mem_agent.wr_driver.send_wready(g);
    endtask

    task automatic backpressure_ar();
        axi_ready_gen g = mem_agent.rd_driver.create_ready("arready");
        g.set_ready_policy(XIL_AXI_READY_GEN_OSC);
        g.set_low_time(5);          // 低 5 拍
        g.set_high_time(2);         // 高 2 拍，然后无限重复
        mem_agent.rd_driver.send_arready(g);
    endtask

    // ---------------- 主流程 ----------------
    initial begin
        $display("[TB] ====== M3 / BD-3 数据面（仿真专用内存端点）======");
        $display("[TB] 注意：内存端点是 AXI VIP，不是实际 PS7 的 AFI 通路");

        if (!$value$plusargs("stage=%s", stage_arg))
            $fatal(1, "必须指定 +stage=voter|decoder");
        if (!$value$plusargs("mem_in=%s", mem_in))
            $fatal(1, "必须指定 +mem_in=<file>");
        if (!$value$plusargs("mem_out=%s", mem_out))
            $fatal(1, "必须指定 +mem_out=<file>");
        if (!$value$plusargs("total_reads=%d", total_reads)) total_reads = 4096;
        if (!$value$plusargs("latency=%d", latency_mode))    latency_mode = 0;

        `PS7.set_stop_on_error(0);

        // 建立并启动仿真专用内存端点
        mem_agent = new("mem_agent", dut.top_bd_i.mem_vip.inst.IF);
        mem_agent.set_agent_tag("mem_vip");
        mem_agent.start_slave();
        $display("[TB] AXI VIP 从机内存模型已启动");

        if (latency_mode == 2) begin
            fork
                backpressure_aw();
                backpressure_w();
                backpressure_ar();
            join_none
            $display("[TB] 已对 AW/W/AR 施加随机背压（latency=2）");
        end else begin
            $display("[TB] 无背压（latency=0）");
        end

        wait (dut.top_bd_i.rst_ps_peripheral_aresetn === 1'b1);
        repeat (50) @(posedge dut.top_bd_i.clk_wiz_0_clk_out1);
        $display("[TB] PL 复位已释放 @%0t ps", $time);

        case (stage_arg)
            "voter":   run_voter();
            "decoder": run_decoder();
            default:   $fatal(1, "未知 stage=%0s", stage_arg);
        endcase

        $display("[TB] --------------------------------------------------");
        if (errors != 0) begin
            $display("[TB] BD-3(extmem) FAIL（%0d 项）", errors);
            $fatal(1, "BD-3 extmem 用例失败");
        end
        $display("[TB] PASS  BD-3(extmem) %0s：经实际 Interconnect 在真实地址上完成读写",
                 stage_arg);
        $display("[TB] --------------------------------------------------");
        $finish;
    end

    // ---------------- Stage2 / Voter ----------------
    task automatic run_voter();
        $display("[TB] ---- Voter：%0d 条记录，输入 0x%08x，输出 0x%08x ----",
                 total_reads, DDR_STAGE1_OUT, DDR_STAGE2_OUT);

        preload_mem(mem_in, DDR_STAGE1_OUT, total_reads * 12);  // 48 B = 12 个 32bit 字

        write_verify32(ADDR_VOTER + VOTER_IN_ADDR,     DDR_STAGE1_OUT);
        write_verify32(ADDR_VOTER + VOTER_IN_BEATS,    total_reads);
        write_verify32(ADDR_VOTER + VOTER_OUT_ADDR,    DDR_STAGE2_OUT);
        write_verify32(ADDR_VOTER + VOTER_OUT_BEATS,   VOTER_OUT_BEATS_N);
        write_verify32(ADDR_VOTER + VOTER_TOTAL_READS, total_reads);
        write_verify32(ADDR_VOTER + VOTER_SCORE_MIN,   32'd67);

        zero_mem(DDR_STAGE2_OUT, VOTER_OUT_BEATS_N * 2);

        axi_write32(ADDR_VOTER + VOTER_STATUS, 32'h1);
        $display("[TB] Voter 已启动，等待 done ...");

        poll = 0;
        rd   = '0;
        while (rd[1] !== 1'b1 && poll < POLL_LIMIT) begin
            repeat (200) @(posedge dut.top_bd_i.clk_wiz_0_clk_out1);
            axi_read32(ADDR_VOTER + VOTER_STATUS, rd);
            poll++;
        end
        if (rd[1] !== 1'b1) begin
            errors++;
            $display("[TB] FAIL: Voter done 超时（STATUS=0x%08x）", rd);
        end else
            $display("[TB] Voter done @%0t ps（轮询 %0d 次）", $time, poll);

        axi_read32(ADDR_VOTER + VOTER_ERR_FLAGS, rd);
        if (rd !== 32'd0) begin
            errors++;
            $display("[TB] FAIL: Voter 错误标志 0x%08x", rd);
        end else $display("[TB]   ok  Voter 错误标志 = 0");

        axi_read32(ADDR_VOTER + VOTER_LAST_RRESP, rd);
        if (rd[1:0] !== 2'b00) begin
            errors++;
            $display("[TB] FAIL: Voter 最后一次 RRESP=%b", rd[1:0]);
        end else $display("[TB]   ok  Voter 最后一次 RRESP = OKAY");

        dump_mem(mem_out, DDR_STAGE2_OUT, VOTER_OUT_BEATS_N * 2);  // 8 B = 2 个 32bit 字
    endtask

    // ---------------- Stage3 / Decoder ----------------
    task automatic run_decoder();
        $display("[TB] ---- Decoder：输入 0x%08x，输出 0x%08x ----",
                 DDR_STAGE2_OUT, DDR_STAGE3_OUT);

        preload_mem(mem_in, DDR_STAGE2_OUT, DEC_IN_BEATS_N * 2);

        write_verify32(ADDR_DEC + DEC_IN_ADDR,   DDR_STAGE2_OUT);
        write_verify32(ADDR_DEC + DEC_IN_BEATS,  DEC_IN_BEATS_N);
        write_verify32(ADDR_DEC + DEC_OUT_ADDR,  DDR_STAGE3_OUT);
        write_verify32(ADDR_DEC + DEC_OUT_BEATS, DEC_OUT_BEATS_N);

        zero_mem(DDR_STAGE3_OUT, DEC_OUT_BEATS_N * 2);

        axi_write32(ADDR_DEC + DEC_START, 32'h1);
        $display("[TB] Decoder 已启动，等待 done ...");

        poll = 0;
        rd   = '0;
        while (rd[1] !== 1'b1 && poll < POLL_LIMIT) begin
            repeat (200) @(posedge dut.top_bd_i.clk_wiz_0_clk_out1);
            axi_read32(ADDR_DEC + DEC_STATUS, rd);
            poll++;
        end
        if (rd[1] !== 1'b1) begin
            errors++;
            $display("[TB] FAIL: Decoder done 超时（STATUS=0x%08x）", rd);
        end else
            $display("[TB] Decoder done @%0t ps（轮询 %0d 次）", $time, poll);

        dump_mem(mem_out, DDR_STAGE3_OUT, DEC_OUT_BEATS_N * 2);
    endtask

    // 全局看门狗：无尺寸十进制字面量默认 32 bit，直接写 200_000_000_000 会溢出成 0 延迟
    initial begin
        repeat (200) #1_000_000_000;   // 200 × 1 ms = 200 ms
        $display("[TB] FATAL: BD-3(extmem) 全局超时");
        $fatal(1, "BD-3 extmem 超时");
    end

endmodule
