// ================================================================
// tb_m3_bd2_ctrl.v —— M3 / BD-2：实际 Block Design 的控制面事务
//
// DUT 是 hw/scripts/bd.tcl 生成的**实际** top_bd_wrapper，不是简化模型：
// 真实 PS7（仿真时为 Xilinx processing_system7_vip）→ M_AXI_GP0 →
// 实际 axi_interconnect(ic_lite) → 四个实际从机（DNA / Decoder / Voter / AXI DMA）。
//
// 覆盖 docs/archive/history/2026/xsim-simulation-plan.md §7.2 BD-2 的判据：
//   1) GP0 经 Interconnect 到各从机的地址译码；
//   2) 三个自研 IP 的寄存器写/读回；
//   3) 从机之间无地址混叠（写一个不影响另一个）；
//   4) 无效地址返回 DECERR，而不是静默成功或挂死；
//   5) 复位后的 idle/done 初值。
//
// 边界（必须写进报告，不得夸大）：
//   - PS7 VIP 不是真实 ARM：不覆盖 cache、lwIP、PHY、SG 描述符管理和 ELF。
//   - 本用例只驱动控制面，不搬运业务数据；数据面在 BD-3。
// ================================================================

`timescale 1 ps / 1 ps

module tb_m3_bd2_ctrl;

    // 实际 BD 顶层。DDR/FIXED_IO 均为 inout，由 VIP 内部建模，这里全部悬空。
    top_bd_wrapper dut ();

    // PS7 VIP 实例路径：top_bd_wrapper -> top_bd_i -> ps_0 -> inst
    `define PS7 dut.top_bd_i.ps_0.inst

    // 与 sw/app/xparameters.h 严格一致的地址（BD-1 已核对 bd_address.txt）
    localparam [31:0] ADDR_DNA      = 32'h43C0_0000;
    localparam [31:0] ADDR_DEC      = 32'h43C1_0000;
    localparam [31:0] ADDR_VOTER    = 32'h43C2_0000;
    localparam [31:0] ADDR_DMA      = 32'h4040_0000;
    // ic_lite 的四个 M 口之外、仍落在 GP0 段内的地址：应当被译码为错误
    localparam [31:0] ADDR_UNMAPPED = 32'h43C3_0000;

    // Voter 寄存器（docs/04-interfaces.md §3.2）
    localparam VOTER_IN_ADDR    = 8'h04;
    localparam VOTER_IN_BEATS   = 8'h08;
    localparam VOTER_OUT_ADDR   = 8'h0C;
    localparam VOTER_OUT_BEATS  = 8'h10;
    localparam VOTER_TOTAL_READS= 8'h14;
    localparam VOTER_SCORE_MIN  = 8'h30;
    localparam VOTER_STATUS     = 8'h00;

    // Decoder 寄存器（docs/04-interfaces.md §3.3）
    localparam DEC_IN_ADDR   = 8'h00;
    localparam DEC_IN_BEATS  = 8'h04;
    localparam DEC_OUT_ADDR  = 8'h08;
    localparam DEC_OUT_BEATS = 8'h0C;
    localparam DEC_STATUS    = 8'h18;

    // DNA 寄存器（docs/04-interfaces.md §3.1）
    localparam DNA_CTRL   = 8'h00;
    localparam DNA_WMSEL  = 8'h04;

    integer errors = 0;
    integer checks = 0;

    reg [2047:0] wbuf;   // VIP master API 数据宽度 = max_transfer_bytes(256)*8
    reg [2047:0] rbuf;
    reg [1:0]    resp;

    // ---------------- 基础事务 ----------------

    // 写 32 bit，并要求 BRESP = OKAY
    task axi_write32;
        input [31:0] addr;
        input [31:0] data;
        begin
            wbuf = {2048{1'b0}};
            wbuf[31:0] = data;
            `PS7.write_data(addr, 4, wbuf, resp);
            checks = checks + 1;
            if (resp !== 2'b00) begin
                errors = errors + 1;
                $display("[TB] FAIL: write 0x%08x <= 0x%08x 返回 BRESP=%b（期望 OKAY）",
                         addr, data, resp);
            end
        end
    endtask

    // 读 32 bit，并要求 RRESP = OKAY
    task axi_read32;
        input  [31:0] addr;
        output [31:0] data;
        begin
            rbuf = {2048{1'b0}};
            `PS7.read_data(addr, 4, rbuf, resp);
            data = rbuf[31:0];
            checks = checks + 1;
            if (resp !== 2'b00) begin
                errors = errors + 1;
                $display("[TB] FAIL: read 0x%08x 返回 RRESP=%b（期望 OKAY）", addr, resp);
            end
        end
    endtask

    // 写入后立刻回读并逐位比较
    task write_check32;
        input [31:0] base;
        input [7:0]  off;
        input [31:0] data;
        input [8*96-1:0] name;
        reg   [31:0] rd;
        begin
            axi_write32(base + off, data);
            axi_read32(base + off, rd);
            checks = checks + 1;
            if (rd !== data) begin
                errors = errors + 1;
                $display("[TB] FAIL: %0s @0x%08x 回读 0x%08x，期望 0x%08x",
                         name, base + off, rd, data);
            end else begin
                $display("[TB]   ok  %0s @0x%08x = 0x%08x", name, base + off, data);
            end
        end
    endtask

    // 只读比较（不写）
    task expect32;
        input [31:0] addr;
        input [31:0] expected;
        input [8*96-1:0] name;
        reg   [31:0] rd;
        begin
            axi_read32(addr, rd);
            checks = checks + 1;
            if (rd !== expected) begin
                errors = errors + 1;
                $display("[TB] FAIL: %0s @0x%08x 读到 0x%08x，期望 0x%08x",
                         name, addr, rd, expected);
            end else begin
                $display("[TB]   ok  %0s @0x%08x = 0x%08x", name, addr, rd);
            end
        end
    endtask

    // ---------------- 主流程 ----------------

    reg [31:0] rd;
    integer    i;

    initial begin
        $display("[TB] ============ M3 / BD-2 控制面事务 ============");
        $display("[TB] DUT = 实际 top_bd_wrapper（bd.tcl 生成），主设备 = PS7 VIP GP0");

        // VIP 报错时不要直接 $stop，交给本 TB 统计并给出显式 PASS/FAIL
        `PS7.set_stop_on_error(0);

        // 等待 PL 复位释放：由 PS7 FCLK_RESET0_N 经 proc_sys_reset 产生
        wait (dut.top_bd_i.rst_ps_peripheral_aresetn === 1'b1);
        $display("[TB] PL 复位已释放 @%0t ps", $time);
        repeat (50) @(posedge dut.top_bd_i.clk_wiz_0_clk_out1);

        // ---- 1. 复位后的状态位 ----
        $display("[TB] ---- 1. 复位初值 ----");
        // Voter 0x00 读回 {done, idle}：复位后应 idle=1, done=0
        expect32(ADDR_VOTER + VOTER_STATUS, 32'h0000_0001, "Voter STATUS(idle)");
        // Decoder 0x18 读回 {done, idle}：复位后应 idle=1, done=0
        expect32(ADDR_DEC + DEC_STATUS, 32'h0000_0001, "Decoder STATUS(idle)");

        // ---- 2. 地址译码：AXI DMA ----
        // 只读 DMA 状态寄存器证明 GP0->ic_lite->M01 的译码通路成立。
        // MM2S_DMASR(0x04) 复位后 Halted(bit0)=1。
        $display("[TB] ---- 2. AXI DMA 地址译码 ----");
        axi_read32(ADDR_DMA + 32'h04, rd);
        checks = checks + 1;
        if (rd[0] !== 1'b1) begin
            errors = errors + 1;
            $display("[TB] FAIL: MM2S_DMASR=0x%08x，复位后 Halted(bit0) 应为 1", rd);
        end else begin
            $display("[TB]   ok  MM2S_DMASR @0x%08x = 0x%08x (Halted=1)", ADDR_DMA + 32'h04, rd);
        end

        // ---- 3. Voter 寄存器写/读回 ----
        $display("[TB] ---- 3. Voter 寄存器写/读回 ----");
        write_check32(ADDR_VOTER, VOTER_IN_ADDR,     32'h1060_0000, "Voter IN_ADDR");
        write_check32(ADDR_VOTER, VOTER_IN_BEATS,    32'd4096,      "Voter IN_BEATS");
        write_check32(ADDR_VOTER, VOTER_OUT_ADDR,    32'h1100_0000, "Voter OUT_ADDR");
        write_check32(ADDR_VOTER, VOTER_OUT_BEATS,   32'd1266,      "Voter OUT_BEATS");
        write_check32(ADDR_VOTER, VOTER_TOTAL_READS, 32'd4096,      "Voter TOTAL_READS");
        write_check32(ADDR_VOTER, VOTER_SCORE_MIN,   32'd67,        "Voter SCORE_MIN");

        // ---- 4. Decoder 寄存器写/读回 ----
        $display("[TB] ---- 4. Decoder 寄存器写/读回 ----");
        write_check32(ADDR_DEC, DEC_IN_ADDR,   32'h1100_0000, "Dec IN_ADDR");
        write_check32(ADDR_DEC, DEC_IN_BEATS,  32'd1266,      "Dec IN_BEATS");
        write_check32(ADDR_DEC, DEC_OUT_ADDR,  32'h1110_0000, "Dec OUT_ADDR");
        write_check32(ADDR_DEC, DEC_OUT_BEATS, 32'd1013,      "Dec OUT_BEATS");

        // ---- 5. DNA 寄存器写/读回 ----
        // 只动 wm_sel（0x04）；不置 start，避免在控制面用例里启动 Stage1。
        $display("[TB] ---- 5. DNA 寄存器写/读回 ----");
        for (i = 0; i < 50; i = i + 50/5) begin
            write_check32(ADDR_DNA, DNA_WMSEL, i, "DNA wm_sel");
        end
        write_check32(ADDR_DNA, DNA_WMSEL, 32'd49, "DNA wm_sel(末区域)");

        // ---- 6. 从机隔离：写 Voter 不得影响 Decoder ----
        // 三个 IP 的基址只差 0x0001_0000，若 ic_lite 地址位宽或 range 配错，
        // 这一步会立刻暴露成互相串写。
        $display("[TB] ---- 6. 从机隔离（无地址混叠）----");
        axi_write32(ADDR_VOTER + VOTER_IN_ADDR, 32'hDEAD_BEEF);
        expect32(ADDR_DEC + DEC_IN_ADDR,  32'h1100_0000, "写 Voter 后 Dec IN_ADDR 不变");
        expect32(ADDR_DNA + DNA_WMSEL,    32'd49,        "写 Voter 后 DNA wm_sel 不变");
        // 复原 Voter IN_ADDR
        write_check32(ADDR_VOTER, VOTER_IN_ADDR, 32'h1060_0000, "Voter IN_ADDR(复原)");

        // 反向：写 Decoder 不得影响 Voter
        axi_write32(ADDR_DEC + DEC_IN_BEATS, 32'h5A5A_5A5A);
        expect32(ADDR_VOTER + VOTER_IN_BEATS, 32'd4096, "写 Dec 后 Voter IN_BEATS 不变");
        write_check32(ADDR_DEC, DEC_IN_BEATS, 32'd1266, "Dec IN_BEATS(复原)");

        // ---- 7. 无效地址：必须返回错误响应，且不得挂死 ----
        // ic_lite 只映射了四个从机；GP0 段内的其它地址应由 interconnect 的
        // 译码错误从机回 DECERR。这里显式要求「非 OKAY」。
        $display("[TB] ---- 7. 无效地址响应 ----");
        rbuf = {2048{1'b0}};
        `PS7.read_data(ADDR_UNMAPPED, 4, rbuf, resp);
        checks = checks + 1;
        if (resp === 2'b00) begin
            errors = errors + 1;
            $display("[TB] FAIL: 未映射地址 0x%08x 读返回 OKAY（期望 DECERR/SLVERR）",
                     ADDR_UNMAPPED);
        end else begin
            $display("[TB]   ok  未映射地址 0x%08x 读返回 RRESP=%b（非 OKAY）",
                     ADDR_UNMAPPED, resp);
        end

        // ---- 8. 无效地址之后总线仍可用 ----
        // 错误响应不能把 interconnect 或 VIP 卡死。
        $display("[TB] ---- 8. 错误响应后总线仍可用 ----");
        expect32(ADDR_VOTER + VOTER_SCORE_MIN, 32'd67, "错误后 Voter SCORE_MIN 仍可读");

        // ---- 结果 ----
        $display("[TB] --------------------------------------------------");
        $display("[TB] 检查项 %0d，失败 %0d", checks, errors);
        if (errors != 0) begin
            $display("[TB] BD-2 FAIL");
            $fatal(1, "BD-2 控制面用例失败");
        end
        $display("[TB] PASS  BD-2 控制面：地址译码/寄存器回读/从机隔离/无效地址响应全部正确");
        $display("[TB] --------------------------------------------------");
        $finish;
    end

    // 全局看门狗：仿真必须自行超时失败，不允许无限挂起
    initial begin
        #500_000_000;   // 500 us
        $display("[TB] FATAL: BD-2 全局超时");
        $fatal(1, "BD-2 超时");
    end

endmodule
