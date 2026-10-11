// ================================================================
// tb_m3_bd3b_dma.sv —— M3 / BD-3b：AXI DMA <-> DNA 加速核 数据面
//
// 这是 docs/06-verification-plan.md的BD接口验证 的第 1、2 项，也是缺陷 B21（Stage1 板上硬卡死）
// 唯一从未被 BD 级仿真覆盖的一段链路：
//
//     AXI DMA MM2S      -> DNA S_AXIS_DATA        （水印预载 + 读段下发）
//     DNA M_AXIS_RESULT -> AXI DMA S2MM           （48 B/条 结果回写 DDR）
//
// DUT 是 hw/scripts/bd_sim_mem.tcl 生成的实际 BD 变体：真实 PS7 VIP 的 GP0
// 控制面、真实 ic_lite / ic_hp、真实 AXI DMA（SG 模式）、真实 DNA 核，
// 只把 ps_0/S_AXI_HP0 这一个内存端点换成 AXI VIP 内存模型
// （原因见 docs/archive/history/2026/m3-bd-simulation-2026-08-29.md的HP0仿真缺陷：Vivado 2022.2 的 PS7 VIP 的 HP0 读通路不返回 RDATA）。
//
// !! 结论边界：内存端点不是实际 PS7 的 AFI 通路。本 TB 能证明
//    「AXI DMA 与 DNA 核之间的 AXIS 链路 + SG 描述符管理」的行为，
//    不能证明 PS7 AFI / DDR 控制器本身。
//
// 本 TB 完全按 sw/app/echo.c 的顺序、地址和参数驱动硬件：
//   1) 逐区域水印预载：写 reg1=区域号 -> 置 reg0[1]=preload -> DMA 957x4 B -> 清 reg0
//   2) 提交 RX BD 环 -> 提交第一帧读段 -> 写 reg0[0]=start -> 继续下发剩余帧
// 因此它复现的是板上真实发生的时序，而不是理想化的激励。
//
// [B26] 2026-08-29 补上本项目至今完全没有的**入口逐条判据**：
//   「送入第 k 条读段 -> 引擎第 k 个槽位装的就是第 k 条读段
//     -> 第 k 条结果记录的码字就是第 k 条读段的码字」。
//   这正是 docs/06-verification-plan.md的BD接口验证 第 1 项、docs/06-verification-plan.md的AXIS握手判据 点名的那一段，
//   也是 B26（板上 result[k] == read[k+1]、read[0] 的结果丢失、末尾多一条）
//   唯一能在 BD 级坐实的判据。
//
// plusargs：
//   +phase=wm|load|full     wm  =只做水印预载
//                           load=预载 + 送读段 + 校验引擎装载进来的 64 个槽位
//                                （~3 万拍即可判定，用于 B26 的快速复现/回归）
//                           full=在 load 之上再等结果经 S2MM 回写 DDR 并逐条比码字
//                                （引擎一个 batch 要扫 50x808x156 ≈ 6.3M 拍，很慢）
//   +rx_bd_mode=fw|perrec   RX BD 环的配额方式
//                             fw     = 照抄 echo.c：per_bd=align_down(min(MaxLen,16K),8)=16376 B
//                             perrec = 每条 48 B 记录一个 BD
//   +reads=<N>              读段条数（必须是 64 的整数倍，默认 64）
//   +require=all|repro      判据：
//                             all   = 必须「送入 N 条 -> 收到 N 条」且无错误
//                             repro = 必须复现 B21（收到条数 < N 且链路停在
//                                     M_AXIS_RESULT TVALID=1/TREADY=0）；跑通反而 FAIL
//   +wm_file=<file>         tests/golden/wm_regions.hex（每行一个符号 0..3）
//   +reads_file=<file>      读段镜像：每行一个 32 bit 字，每条读段 10 个字
//   +mem_out=<file>         把 Stage1 输出区 dump 成 VIP 32 bit 字格式，供逐位比较
//
// 判据纪律（docs/06-verification-plan.md的故障鉴别力要求）：编译过、跑完、有波形都不算 PASS。
// 每一条判据都有显式 PASS/FAIL、超时保护和逐位比较，不屏蔽 X/Z。
// ================================================================

`timescale 1 ps / 1 ps

import axi_vip_pkg::*;
import top_bd_mem_vip_0_pkg::*;

module tb_m3_bd3b_dma;

    top_bd_wrapper dut ();

    `define PS7  dut.top_bd_i.ps_0.inst
    `define DNA  dut.top_bd_i.Dna_accelerator_core_0.inst
    `define ENG  dut.top_bd_i.Dna_accelerator_core_0.inst.u_srpe_batch
    `define ACLK dut.top_bd_i.clk_wiz_0_clk_out1

    top_bd_mem_vip_0_slv_mem_t mem_agent;

    // ---------------- 地址（与 sw/app/echo.h、docs/05 完全一致）----------------
    localparam [31:0] ADDR_DNA = 32'h43C0_0000;
    localparam [31:0] ADDR_DMA = 32'h4040_0000;

    localparam [7:0] MM2S_DMACR    = 8'h00;
    localparam [7:0] MM2S_DMASR    = 8'h04;
    localparam [7:0] MM2S_CURDESC  = 8'h08;
    localparam [7:0] MM2S_TAILDESC = 8'h10;
    localparam [7:0] S2MM_DMACR    = 8'h30;
    localparam [7:0] S2MM_DMASR    = 8'h34;
    localparam [7:0] S2MM_CURDESC  = 8'h38;
    localparam [7:0] S2MM_TAILDESC = 8'h40;

    localparam [7:0] DNA_REG0 = 8'h00;   // [0]=start [1]=preload [2]=soft_reset
    localparam [7:0] DNA_REG1 = 8'h04;   // [5:0]=wm_sel

    localparam [31:0] DDR_WM_REGIONS = 32'h1004_0000;
    localparam [31:0] DDR_READS      = 32'h1010_0000;
    localparam [31:0] DDR_STAGE1_OUT = 32'h1060_0000;
    localparam [31:0] BD_BASE_TX     = 32'h1180_0000;
    localparam [31:0] BD_BASE_RX     = 32'h1190_0000;

    localparam int TX_BD_CNT = 2048;    // MAX_BD_COUNT_TX
    localparam int RX_BD_CNT = 1024;    // MAX_BD_COUNT_RX
    localparam int BD_BYTES  = 64;      // BD_ALIGNMENT

    localparam int WM_NUM_LC       = 50;
    localparam int WM_REF_LEN      = 957;
    localparam int WM_REGION_BYTES = WM_REF_LEN * 4;          // 3828
    localparam int READ_BYTES      = 40;                      // READ_SIZE_BYTES
    localparam int READ_WORDS      = READ_BYTES / 4;          // 10
    localparam int FRAME_READS     = 64;
    localparam int FRAME_BYTES     = FRAME_READS * READ_BYTES; // 2560
    localparam int REC_BYTES       = 48;                      // DNA_ACC_RESULT_PACKED_BYTES

    // [B26] 结果记录的字段布局（与 srpe_batch 的 res_din = {cw_acc, global_pos, best_sc} 一致）
    localparam int READ_BPS = 150;
    localparam int CODEBITS = READ_BPS * 2;                   // 300
    localparam int SCORE_W  = 10;
    localparam int POS_W    = 16;
    localparam int RESULT_W = CODEBITS + POS_W + SCORE_W;     // 326
    localparam int BATCH    = 64;                             // srpe_batch 的 BATCH
    localparam [3:0] ENG_S_INITC = 4'd5;                      // srpe_batch 的 S_INITC

    // C_SG_LENGTH_WIDTH = 14（已在生成的 BD 中核实）-> MaxTransferLen = 16383
    localparam int SG_LEN_WIDTH = 14;
    localparam int SG_MAX_LEN   = (1 << SG_LEN_WIDTH) - 1;    // 16383
    localparam int SG_LEN_MASK  = SG_MAX_LEN;
    // echo.c: target = min(MaxTransferLen, 16*1024); per_bd = align_down(target, 8)
    localparam int FW_RX_PER_BD = ((SG_MAX_LEN < 16384) ? SG_MAX_LEN : 16384) & ~3;

    localparam [31:0] BD_CTRL_TXSOF = 32'h0800_0000;
    localparam [31:0] BD_CTRL_TXEOF = 32'h0400_0000;
    localparam [31:0] BD_STS_CMPLT  = 32'h8000_0000;
    localparam [31:0] BD_STS_ERRALL = 32'h7000_0000;   // DecErr|SlvErr|IntErr
    localparam [31:0] BD_STS_RXSOF  = 32'h0800_0000;
    localparam [31:0] BD_STS_RXEOF  = 32'h0400_0000;

    // 轮询参数：引擎跑完一个 batch 约需 6.36M 周期
    // （50 区域 x 808 位置 x 156 周期 + 装载/输出），这段时间本来就没有输出。
    localparam int POLL_CYCLES = 2000;
    localparam int MAX_POLL    = 9000;    // 18M 周期 = 180 ms @100MHz
    localparam int STALL_POLLS = 100;     // 首条记录之后 200k 周期无进展即判停滞

    // ---------------- 运行参数 ----------------
    string phase_arg   = "full";
    string rx_mode_arg = "fw";
    string require_arg = "all";
    bit    inject_b26  = 1'b0;   // 故障注入自检：把 cw_data 接回 in_dout（= B26 修复前的接法）
    string wm_file     = "";
    string reads_file  = "";
    string mem_out     = "";
    int    n_reads     = 64;

    int errors = 0;

    reg [2047:0] wbuf;
    reg [2047:0] rbuf;
    reg [1:0]    resp;
    logic [31:0] rd;

    int tx_head = 0;
    int rx_head = 0;

    int plane_bad   = 0;
    int rec_cw_bad  = 0;
    bit load_seen   = 0;

    int rx_bd_used  = 0;
    int recs_expect = 0;
    int recs_got    = 0;
    int rx_bytes    = 0;
    int rx_cmplt    = 0;
    int wm_mismatch = 0;

    // ================================================================
    // 基础事务
    // ================================================================
    task automatic step(input int n);
        repeat (n) @(posedge `ACLK);
    endtask

    task automatic axi_write32(input [31:0] addr, input [31:0] data);
        wbuf = '0;
        wbuf[31:0] = data;
        `PS7.write_data(addr, 4, wbuf, resp);
        if (resp !== 2'b00) begin
            errors++;
            $display("[TB] FAIL: 写 0x%08x 返回 BRESP=%b", addr, resp);
        end
    endtask

    task automatic axi_read32(input [31:0] addr, output logic [31:0] data);
        rbuf = '0;
        `PS7.read_data(addr, 4, rbuf, resp);
        data = rbuf[31:0];
        if (resp !== 2'b00) begin
            errors++;
            $display("[TB] FAIL: 读 0x%08x 返回 RRESP=%b", addr, resp);
        end
    endtask

    task automatic mem_wr32(input [31:0] addr, input [31:0] data);
        mem_agent.mem_model.backdoor_memory_write_4byte(addr, data);
    endtask

    function automatic logic [31:0] mem_rd32(input [31:0] addr);
        return mem_agent.mem_model.backdoor_memory_read_4byte(addr);
    endfunction

    // ================================================================
    // 内存镜像装载 / 导出（格式与 tools/m3_mem.py 一致：每行一个 32 bit 字）
    // ================================================================
    task automatic load_words(input string fname, input [31:0] base, input int nwords,
                              input string label);
        int fd, code, i;
        logic [31:0] w;
        fd = $fopen(fname, "r");
        if (fd == 0) begin
            $display("[TB] FATAL: 打不开 %0s（%0s）", fname, label);
            $fatal(1, "input file open failed");
            $finish;
        end
        for (i = 0; i < nwords; i++) begin
            code = $fscanf(fd, "%h", w);
            if (code != 1) break;
            mem_wr32(base + 4*i, w);
        end
        $fclose(fd);
        // 注意：XSim 2022.2 打印 SystemVerilog string 里的非 ASCII 会变乱码，
        // 所以所有 label 一律传 ASCII（内容在下面的中文字面量里说清楚）。
        $display("[TB] 已装载 %s：%0d 个 32bit 字（%0d B）-> 0x%08x", label, i, 4*i, base);
        if (i < nwords) begin
            errors++;
            $display("[TB] FAIL: %s 只有 %0d 字，少于需要的 %0d 字", label, i, nwords);
        end
    endtask

    task automatic zero_mem(input [31:0] base, input int nwords);
        int i;
        for (i = 0; i < nwords; i++) mem_wr32(base + 4*i, 32'h0);
    endtask

    task automatic dump_mem(input string fname, input [31:0] base, input int nwords);
        int fd, i;
        if (fname == "") return;
        fd = $fopen(fname, "w");
        if (fd == 0) begin
            $display("[TB] FATAL: 打不开输出文件 %0s", fname);
            $fatal(1, "mem_out open failed");
            $finish;
        end
        for (i = 0; i < nwords; i++) $fdisplay(fd, "%08x", mem_rd32(base + 4*i));
        $fclose(fd);
        $display("[TB] 已 dump %0d 个 32bit 字（%0d B）到 %0s", nwords, 4*nwords, fname);
    endtask

    // ================================================================
    // BD 环：完全按 XAxiDma_BdRingCreate/Clone/ToHw 的语义在内存里搭出来
    // ================================================================
    task automatic bd_ring_init(input [31:0] base, input int cnt);
        int i, j;
        logic [31:0] nxt;
        for (i = 0; i < cnt; i++) begin
            for (j = 0; j < BD_BYTES/4; j++) mem_wr32(base + i*BD_BYTES + 4*j, 32'h0);
            nxt = base + ((i + 1) % cnt) * BD_BYTES;
            mem_wr32(base + i*BD_BYTES + 32'h00, nxt);   // NXTDESC
        end
    endtask

    task automatic bd_submit(input [31:0] base, input int cnt, ref int head,
                             input [31:0] buf_addr, input int total_len,
                             input int per_bd, input bit is_tx,
                             output int first_idx, output int last_idx, output int n_bd);
        int i, this_len, remaining, offset, idx;
        logic [31:0] ctrl;
        n_bd      = (total_len + per_bd - 1) / per_bd;
        first_idx = head;
        remaining = total_len;
        offset    = 0;
        for (i = 0; i < n_bd; i++) begin
            idx      = (head + i) % cnt;
            this_len = (remaining > per_bd) ? per_bd : remaining;
            ctrl     = this_len & SG_LEN_MASK;
            if (is_tx) ctrl |= (BD_CTRL_TXSOF | BD_CTRL_TXEOF);
            mem_wr32(base + idx*BD_BYTES + 32'h08, buf_addr + offset);  // BUFADDR
            mem_wr32(base + idx*BD_BYTES + 32'h0C, 32'h0);              // BUFADDR MSB
            mem_wr32(base + idx*BD_BYTES + 32'h18, ctrl);               // CONTROL
            mem_wr32(base + idx*BD_BYTES + 32'h1C, 32'h0);              // STATUS 清零
            remaining -= this_len;
            offset    += this_len;
        end
        last_idx = (head + n_bd - 1) % cnt;
        head     = (head + n_bd) % cnt;
    endtask

    function automatic logic [31:0] bd_sts(input [31:0] base, input int idx);
        return mem_rd32(base + idx*BD_BYTES + 32'h1C);
    endfunction

    // ================================================================
    // AXI DMA（SG 模式）启动
    // ================================================================
    task automatic dma_reset();
        int guard;
        axi_write32(ADDR_DMA + MM2S_DMACR, 32'h4);     // Reset（复位两个通道）
        guard = 0;
        forever begin
            axi_read32(ADDR_DMA + MM2S_DMACR, rd);
            if (rd[2] !== 1'b1) break;
            step(10);
            guard++;
            if (guard > 1000) begin
                errors++;
                $display("[TB] FAIL: AXI DMA 复位未自清（MM2S_DMACR=0x%08x）", rd);
                break;
            end
        end
        $display("[TB] AXI DMA 已复位");
    endtask

    task automatic dma_channel_start(input [7:0] cr_off, input [7:0] sr_off,
                                     input [7:0] cur_off, input [31:0] first_bd,
                                     input string name);
        int guard;
        axi_write32(ADDR_DMA + cur_off, first_bd);
        axi_write32(ADDR_DMA + cr_off,  32'h1);        // RS=1
        guard = 0;
        forever begin
            axi_read32(ADDR_DMA + sr_off, rd);
            if (rd[0] !== 1'b1) break;                 // Halted 已清
            step(10);
            guard++;
            if (guard > 2000) begin
                errors++;
                $display("[TB] FAIL: %0s 通道启动后仍 Halted（DMASR=0x%08x）", name, rd);
                break;
            end
        end
        $display("[TB] %0s 通道已启动：CURDESC=0x%08x DMASR=0x%08x", name, first_bd, rd);
    endtask

    task automatic dma_kick_tx(input int last_idx);
        axi_write32(ADDR_DMA + MM2S_TAILDESC, BD_BASE_TX + last_idx*BD_BYTES);
    endtask

    task automatic dma_kick_rx(input int last_idx);
        axi_write32(ADDR_DMA + S2MM_TAILDESC, BD_BASE_RX + last_idx*BD_BYTES);
    endtask

    task automatic wait_tx_group(input int first_idx, input int n_bd,
                                 input int expect_len, input int max_cycles,
                                 input string label);
        int waited, i, idx, done_cnt;
        logic [31:0] s;
        waited   = 0;
        done_cnt = 0;
        while (done_cnt < n_bd && waited < max_cycles) begin
            done_cnt = 0;
            for (i = 0; i < n_bd; i++) begin
                idx = (first_idx + i) % TX_BD_CNT;
                s   = bd_sts(BD_BASE_TX, idx);
                if (s & BD_STS_CMPLT) done_cnt++;
            end
            if (done_cnt < n_bd) begin
                step(200);
                waited += 200;
            end
        end
        if (done_cnt < n_bd) begin
            errors++;
            $display("[TB] FAIL: %0s TX BD 超时，%0d/%0d 完成（等待 %0d 周期）",
                     label, done_cnt, n_bd, waited);
            dump_diag(label);
            return;
        end
        for (i = 0; i < n_bd; i++) begin
            idx = (first_idx + i) % TX_BD_CNT;
            s   = bd_sts(BD_BASE_TX, idx);
            if (s & BD_STS_ERRALL) begin
                errors++;
                $display("[TB] FAIL: %0s TX BD[%0d] 错误位置位 STATUS=0x%08x", label, idx, s);
            end
            if (expect_len > 0 && (s & SG_LEN_MASK) != expect_len) begin
                errors++;
                $display("[TB] FAIL: %0s TX BD[%0d] 传输长度 %0d，期望 %0d（STATUS=0x%08x）",
                         label, idx, s & SG_LEN_MASK, expect_len, s);
            end
        end
    endtask

    // 只统计，不判错；错误检查放在最后一次做，避免轮询期间重复计数
    task automatic rx_scan();
        int i;
        logic [31:0] s;
        rx_cmplt = 0;
        rx_bytes = 0;
        for (i = 0; i < rx_bd_used; i++) begin
            s = bd_sts(BD_BASE_RX, i % RX_BD_CNT);
            if (s & BD_STS_CMPLT) begin
                rx_cmplt++;
                rx_bytes += (s & SG_LEN_MASK);
            end
        end
        recs_got = rx_bytes / REC_BYTES;
    endtask

    // 每个完成的 RX BD 必须是「一条完整记录」：Cmplt + RXSOF + RXEOF + 48 B。
    // 这正是板上取证到的 0x8c000030，也是「S2MM 每条记录吃掉一个 BD」的直接证据。
    task automatic rx_check_bds();
        int i, bad;
        logic [31:0] s;
        bad = 0;
        for (i = 0; i < rx_bd_used; i++) begin
            s = bd_sts(BD_BASE_RX, i % RX_BD_CNT);
            if (!(s & BD_STS_CMPLT)) continue;
            if (s & BD_STS_ERRALL) begin
                errors++;
                $display("[TB] FAIL: RX BD[%0d] 错误位置位 STATUS=0x%08x", i, s);
            end
            if (((s & SG_LEN_MASK) != REC_BYTES) ||
                !(s & BD_STS_RXSOF) || !(s & BD_STS_RXEOF)) begin
                bad++;
                if (bad <= 4)
                    $display("[TB]   RX BD[%0d] STATUS=0x%08x（长度 %0d，SOF=%0d EOF=%0d）",
                             i, s, s & SG_LEN_MASK,
                             (s & BD_STS_RXSOF) ? 1 : 0, (s & BD_STS_RXEOF) ? 1 : 0);
            end
        end
        if (bad != 0) begin
            errors++;
            $display("[TB] FAIL: %0d 个已完成 RX BD 不是「Cmplt+RXSOF+RXEOF+48B」形态", bad);
        end else if (rx_cmplt > 0) begin
            $display("[TB]   ok  %0d 个已完成 RX BD 全部为 Cmplt+RXSOF+RXEOF+48B（每条记录一个 BD）",
                     rx_cmplt);
        end
    endtask

    // ================================================================
    // [B26] 入口逐条判据
    //
    // 「送入第 k 条读段 -> 第 k 条结果的码字等于该读段的码字」拆成两段来判：
    //   (a) check_planes()  ：DMA 送进来的第 k 条读段，是否真的进了引擎的第 k 个槽位。
    //       这一段只需要等引擎装完一个 batch（约 3 万拍），是 B26 的**快速**判据。
    //   (b) check_records() ：回写 DDR 的第 k 条 48 B 记录，其码字字段（bit 325:26）
    //       是否等于第 k 条读段。这一段要等引擎扫完 50x808 个位置（约 6.3M 拍），很慢。
    // 两段的期望值都直接从 **VIP 内存里实际被 DMA 读走的那份读段数据** 反推，
    // 不引入第二份「理想」数据源。
    // ================================================================

    // 从 VIP 内存里取回第 k 条读段的 300 bit 码字（与 MM2S 实际读走的字节完全一致）
    function automatic logic [CODEBITS-1:0] read_cw_of(input int k);
        logic [CODEBITS-1:0] cw;
        logic [31:0] w;
        int i;
        cw = '0;
        for (i = 0; i < READ_WORDS-1; i++)
            cw[32*i +: 32] = mem_rd32(DDR_READS + k*READ_BYTES + 4*i);
        w = mem_rd32(DDR_READS + k*READ_BYTES + 4*(READ_WORDS-1));
        cw[CODEBITS-1:288] = w[CODEBITS-288-1:0];   // 末字只有低 12 bit 有效
        return cw;
    endfunction

    // 等引擎把一个 batch 装完（st 进入 S_INITC），再多等几拍让最后一行的写生效
    task automatic wait_batch_loaded(input int max_cycles, output bit ok);
        int c;
        c  = 0;
        ok = 1'b0;
        while (c < max_cycles) begin
            step(1);
            c++;
            if (`ENG.st === ENG_S_INITC) begin
                ok = 1'b1;
                break;
            end
        end
        step(8);   // S_LOAD_R 最后一行的 b_we 要下一拍才写进 plane BRAM
        if (ok)
            $display("[TB] 引擎第一个 batch 装载完成 @%0t ps（等待 %0d 拍）", $time, c);
        else begin
            errors++;
            $display("[TB] FAIL: 等了 %0d 拍引擎仍未装完一个 batch（st=%0d busy=%b in_count=%0d）",
                     max_cycles, `ENG.st, `DNA.eng_busy, `DNA.in_count);
        end
    endtask

    // (a) 引擎第 k 个槽位装的必须是第 (batch_base+k) 条读段
    task automatic check_planes(input int batch_base);
        logic [CODEBITS-1:0] got, exp;
        int k, r, j, bad, shift_hit, off_by_one, has_x, other;
        bad = 0; off_by_one = 0; has_x = 0; other = 0;
        for (k = 0; k < BATCH; k++) begin
            for (r = 0; r < READ_BPS; r++) begin
                got[r]            = `ENG.plane_hi[r][k];
                got[READ_BPS + r] = `ENG.plane_lo[r][k];
            end
            exp = read_cw_of(batch_base + k);
            if (got !== exp) begin
                bad++;
                // 错位统计：+1 条 / 含 X（装到了从未写入的 FIFO 槽位）/ 其它
                if (^got === 1'bx)                              has_x++;
                else if (got === read_cw_of(batch_base + k + 1)) off_by_one++;
                else                                            other++;
                if (bad <= 4) begin
                    $display("[TB] FAIL: 引擎槽位 %0d 装的不是第 %0d 条读段", k, batch_base + k);
                    $display("[TB]        got = %075h", got);
                    $display("[TB]        exp = %075h", exp);
                    shift_hit = 0;
                    for (j = 0; j < n_reads && shift_hit < 2; j++)
                        if (got === read_cw_of(j)) begin
                            $display("[TB]        >>> 它其实是读段 %0d（错位 %0d 条）",
                                     j, j - (batch_base + k));
                            shift_hit++;
                        end
                    if (shift_hit == 0 && (^got === 1'bx))
                        $display("[TB]        >>> 槽位内容含 X/Z：装到了从未写入的 in_fifo 槽位");
                end
            end
        end
        plane_bad = bad;
        if (bad != 0) begin
            errors++;
            $display("[TB] FAIL: 引擎装载的 %0d 个槽位里有 %0d 个不是对应的读段（B26 特征）",
                     BATCH, bad);
            $display("[TB]        其中：整体错位 +1 条 %0d 个，含 X（装到从未写入的 FIFO 槽位）%0d 个，其它 %0d 个",
                     off_by_one, has_x, other);
        end else begin
            $display("[TB]   ok  引擎 %0d 个槽位逐位等于送入的第 %0d..%0d 条读段",
                     BATCH, batch_base, batch_base + BATCH - 1);
        end
    endtask

    // (b) 回写 DDR 的第 k 条记录，其码字字段必须等于第 k 条读段
    task automatic check_records(input int n);
        logic [383:0] rec;
        logic [CODEBITS-1:0] got, exp;
        int k, i, j, bad, shift_hit;
        bad = 0;
        for (k = 0; k < n; k++) begin
            for (i = 0; i < REC_BYTES/4; i++)
                rec[32*i +: 32] = mem_rd32(DDR_STAGE1_OUT + k*REC_BYTES + 4*i);
            if (rec[383:RESULT_W] !== 58'd0) begin
                errors++;
                $display("[TB] FAIL: 记录 %0d 的末拍高 58 bit 非零（0x%0h）", k, rec[383:RESULT_W]);
            end
            got = rec[RESULT_W-1 : SCORE_W+POS_W];
            exp = read_cw_of(k);
            if (got !== exp) begin
                bad++;
                if (bad <= 4) begin
                    $display("[TB] FAIL: 记录 %0d 的码字 != 第 %0d 条读段的码字", k, k);
                    $display("[TB]        got = %075h", got);
                    $display("[TB]        exp = %075h", exp);
                    shift_hit = 0;
                    for (j = 0; j < n_reads && shift_hit < 2; j++)
                        if (got === read_cw_of(j)) begin
                            $display("[TB]        >>> 它其实是读段 %0d（错位 %0d 条）", j, j - k);
                            shift_hit++;
                        end
                end
            end
        end
        rec_cw_bad = bad;
        if (bad != 0) begin
            errors++;
            $display("[TB] FAIL: %0d / %0d 条记录的码字与送入的读段不符（B26 特征）", bad, n);
        end else begin
            $display("[TB]   ok  %0d 条记录的码字逐位等于送入的第 k 条读段", n);
        end
    endtask

    // ================================================================
    // 现场诊断
    // ================================================================
    task automatic dump_diag(input string tag);
        logic [31:0] mm2s_sr, s2mm_sr, mm2s_cur, mm2s_tail, s2mm_cur, s2mm_tail;
        axi_read32(ADDR_DMA + MM2S_DMASR,    mm2s_sr);
        axi_read32(ADDR_DMA + S2MM_DMASR,    s2mm_sr);
        axi_read32(ADDR_DMA + MM2S_CURDESC,  mm2s_cur);
        axi_read32(ADDR_DMA + MM2S_TAILDESC, mm2s_tail);
        axi_read32(ADDR_DMA + S2MM_CURDESC,  s2mm_cur);
        axi_read32(ADDR_DMA + S2MM_TAILDESC, s2mm_tail);
        $display("[TB] ---- 现场诊断 @%0t ps（%0s）----", $time, tag);
        $display("[TB]   MM2S_DMASR=0x%08x CURDESC=0x%08x TAILDESC=0x%08x",
                 mm2s_sr, mm2s_cur, mm2s_tail);
        $display("[TB]   S2MM_DMASR=0x%08x CURDESC=0x%08x TAILDESC=0x%08x",
                 s2mm_sr, s2mm_cur, s2mm_tail);
        $display("[TB]   S_AXIS_DATA   TVALID=%b TREADY=%b TLAST=%b",
                 `DNA.S_AXIS_DATA_TVALID, `DNA.S_AXIS_DATA_TREADY, `DNA.S_AXIS_DATA_TLAST);
        $display("[TB]   M_AXIS_RESULT TVALID=%b TREADY=%b TLAST=%b",
                 `DNA.M_AXIS_RESULT_TVALID, `DNA.M_AXIS_RESULT_TREADY, `DNA.M_AXIS_RESULT_TLAST);
        $display("[TB]   in_fifo  full=%b empty=%b count=%0d",
                 `DNA.in_full, `DNA.in_empty, `DNA.in_count);
        $display("[TB]   res_fifo full=%b empty=%b", `DNA.res_full, `DNA.res_empty);
        $display("[TB]   wm_waddr=%0d 引擎 st=%0d busy=%b done=%b",
                 `DNA.wm_waddr, `ENG.st, `DNA.eng_busy, `DNA.eng_done);
        $display("[TB]   RX BD：提交 %0d 个，完成 %0d 个，累计 %0d B = %0d 条记录",
                 rx_bd_used, rx_cmplt, rx_bytes, recs_got);
    endtask

    // ================================================================
    // 阶段 1：水印预载（50 个区域）
    // ================================================================
    task automatic run_watermark();
        int r, first_idx, last_idx, n_bd;
        int waddr_before, waddr_after;

        $display("[TB] ==== 水印预载：%0d 区域 x %0d 符号 ====", WM_NUM_LC, WM_REF_LEN);
        load_words(wm_file, DDR_WM_REGIONS, WM_NUM_LC * WM_REF_LEN, "wm_regions");

        for (r = 0; r < WM_NUM_LC; r++) begin
            waddr_before = `DNA.wm_waddr;
            if (waddr_before != 0) begin
                errors++;
                $display("[TB] FAIL: 区域 %0d 开始前 wm_waddr=%0d，应为 0", r, waddr_before);
            end

            // echo.c PIPE_WM_TX：先选区域，再进预载模式；顺序不能反
            axi_write32(ADDR_DNA + DNA_REG1, r);
            step(20);
            axi_write32(ADDR_DNA + DNA_REG0, 32'h2);      // preload=1
            step(20);

            bd_submit(BD_BASE_TX, TX_BD_CNT, tx_head, DDR_WM_REGIONS + r*WM_REGION_BYTES,
                      WM_REGION_BYTES, FW_RX_PER_BD, 1'b1, first_idx, last_idx, n_bd);
            dma_kick_tx(last_idx);
            wait_tx_group(first_idx, n_bd, WM_REGION_BYTES, 1000000,
                          $sformatf("wm_region %0d", r));
            if (errors != 0) return;

            step(50);
            // echo.c PIPE_WM_WAIT：每个区域传完都退出预载模式
            axi_write32(ADDR_DNA + DNA_REG0, 32'h0);
            step(20);

            waddr_after = `DNA.wm_waddr;
            if (waddr_after != 0) begin
                errors++;
                $display("[TB] FAIL: 区域 %0d 传完后 wm_waddr=%0d，应回到 0（957 次写自动归零）",
                         r, waddr_after);
            end
        end
        $display("[TB] 50 个区域预载完成 @%0t ps", $time);

        check_wm_bram();
    endtask

    // wm BRAM 逐符号比较：这是「水印真的进对了区域」的唯一硬判据
    task automatic check_wm_bram();
        int fd, code, k;
        logic [31:0] sym;
        logic [1:0]  got;
        wm_mismatch = 0;
        fd = $fopen(wm_file, "r");
        if (fd == 0) begin
            errors++;
            $display("[TB] FAIL: 复核时打不开 %0s", wm_file);
            return;
        end
        for (k = 0; k < WM_NUM_LC * WM_REF_LEN; k++) begin
            code = $fscanf(fd, "%h", sym);
            if (code != 1) begin
                errors++;
                $display("[TB] FAIL: 水印文件在第 %0d 个符号提前结束", k);
                break;
            end
            got = `ENG.wm_bram[k];
            if (got !== sym[1:0]) begin
                if (wm_mismatch < 8)
                    $display("[TB]   wm_bram[%0d]（区域 %0d 行 %0d）= %0d，期望 %0d",
                             k, k / WM_REF_LEN, k % WM_REF_LEN, got, sym[1:0]);
                wm_mismatch++;
            end
        end
        $fclose(fd);
        if (wm_mismatch != 0) begin
            errors++;
            $display("[TB] FAIL: 水印 BRAM 有 %0d / %0d 个符号不符",
                     wm_mismatch, WM_NUM_LC * WM_REF_LEN);
        end else begin
            $display("[TB]   ok  水印 BRAM %0d 个符号逐个相同（50 区域 x 957 行）",
                     WM_NUM_LC * WM_REF_LEN);
        end
    endtask

    // ================================================================
    // 阶段 2：读段下发 + 结果回写
    // ================================================================
    task automatic run_reads();
        int frames, f, first_idx, last_idx, n_bd;
        int rx_first, rx_lastidx, rx_n;
        int rx_per_bd, rx_total;
        int poll, no_progress, last_bytes;
        int tx_first_all, tx_n_all;

        frames      = n_reads / FRAME_READS;
        rx_total    = n_reads * REC_BYTES;
        recs_expect = n_reads;

        $display("[TB] ==== 读段：%0d 条 = %0d 帧 x %0d 条 ====", n_reads, frames, FRAME_READS);
        load_words(reads_file, DDR_READS, n_reads * READ_WORDS, "reads");
        zero_mem(DDR_STAGE1_OUT, n_reads * REC_BYTES / 4);

        // ---- echo.c PIPE_RX_PREP：提交 RX BD 环 ----
        if (rx_mode_arg == "fw")          rx_per_bd = FW_RX_PER_BD;
        else if (rx_mode_arg == "perrec") rx_per_bd = REC_BYTES;
        else begin
            $display("[TB] FATAL: 未知 rx_bd_mode=%0s", rx_mode_arg);
            $fatal(1, "bad rx_bd_mode");
            $finish;
        end
        bd_submit(BD_BASE_RX, RX_BD_CNT, rx_head, DDR_STAGE1_OUT, rx_total,
                  rx_per_bd, 1'b0, rx_first, rx_lastidx, rx_n);
        rx_bd_used = rx_n;
        $display("[TB] RX BD 配额（%0s）：per_bd=%0d B，总 %0d B -> %0d 个 BD",
                 rx_mode_arg, rx_per_bd, rx_total, rx_n);
        $display("[TB] 参考：DNA 核每条 48 B 记录发一次 TLAST，S2MM 每个 TLAST 关闭一个 BD，实际需要的 BD 数 = 记录条数 = %0d",
                 n_reads);
        dma_kick_rx(rx_lastidx);

        // ---- echo.c PIPE_TX_PREFILL：先送第一帧 ----
        tx_first_all = tx_head;
        tx_n_all     = 0;
        bd_submit(BD_BASE_TX, TX_BD_CNT, tx_head, DDR_READS, FRAME_BYTES,
                  FRAME_BYTES, 1'b1, first_idx, last_idx, n_bd);
        tx_n_all += n_bd;
        dma_kick_tx(last_idx);

        // ---- echo.c PIPE_START_IP ----
        axi_write32(ADDR_DNA + DNA_REG0, 32'h1);       // start=1
        step(50);
        $display("[TB] [STAGE1] IP core START @%0t ps", $time);

        // ---- [B26] 入口逐条判据（a）：引擎装完第一个 batch 就能判定 ----
        // 装载一条读段要 150x3 拍，一个 batch 约 3 万拍；比等结果（6.3M 拍）快两个量级。
        wait_batch_loaded(200000, load_seen);
        if (load_seen) check_planes(0);
        if (phase_arg == "load") begin
            $display("[TB] phase=load：入口装载判据已完成，不再等待引擎扫完 50x808 个位置");
            return;
        end

        // ---- echo.c PIPE_TX_STREAM：继续下发剩余帧 ----
        for (f = 1; f < frames; f++) begin
            bd_submit(BD_BASE_TX, TX_BD_CNT, tx_head, DDR_READS + f*FRAME_BYTES,
                      FRAME_BYTES, FRAME_BYTES, 1'b1, first_idx, last_idx, n_bd);
            tx_n_all += n_bd;
            dma_kick_tx(last_idx);
            step(500);
        end

        // ---- 等结果：收齐 / 停滞 / 超时 ----
        poll        = 0;
        no_progress = 0;
        last_bytes  = 0;
        while (poll < MAX_POLL) begin
            step(POLL_CYCLES);
            poll++;
            rx_scan();
            if (rx_bytes != last_bytes) begin
                last_bytes  = rx_bytes;
                no_progress = 0;
            end else if (rx_bytes > 0) begin
                no_progress++;
            end
            if (rx_bytes >= rx_total) break;
            if (no_progress >= STALL_POLLS) begin
                $display("[TB] 检测到停滞：连续 %0d 次轮询（%0d 周期）无新记录",
                         no_progress, no_progress * POLL_CYCLES);
                break;
            end
        end
        if (poll >= MAX_POLL)
            $display("[TB] 轮询到上限 %0d 次（%0d 周期）", MAX_POLL, MAX_POLL * POLL_CYCLES);

        rx_scan();
        $display("[TB] --------------------------------------------------");
        $display("[TB] RESULT records_expected=%0d records_received=%0d rx_bd_submitted=%0d rx_bd_completed=%0d rx_bytes=%0d",
                 recs_expect, recs_got, rx_bd_used, rx_cmplt, rx_bytes);
        dump_diag("读段阶段结束");
        rx_check_bds();

        dump_mem(mem_out, DDR_STAGE1_OUT, n_reads * REC_BYTES / 4);

        // ---- 判据 ----
        if (require_arg == "all") begin
            if (recs_got != recs_expect) begin
                errors++;
                $display("[TB] FAIL: 送入 %0d 条读段，只收到 %0d 条 48 B 记录",
                         recs_expect, recs_got);
            end else begin
                $display("[TB]   ok  送入 %0d 条 -> 收到 %0d 条 48 B 记录", recs_expect, recs_got);
            end
            wait_tx_group(tx_first_all, tx_n_all, FRAME_BYTES, 1000000, "read_frames");
            // [B26] 入口逐条判据（b）：第 k 条结果的码字必须等于第 k 条读段的码字
            if (recs_got > 0) check_records((recs_got < recs_expect) ? recs_got : recs_expect);
        end else if (require_arg == "repro") begin
            if (recs_got >= recs_expect) begin
                errors++;
                $display("[TB] FAIL: 预期复现 B21（收到条数 < %0d），实际收齐 %0d 条，说明根因假设不成立",
                         recs_expect, recs_got);
            end else if (`DNA.M_AXIS_RESULT_TVALID !== 1'b1 ||
                         `DNA.M_AXIS_RESULT_TREADY !== 1'b0) begin
                errors++;
                $display("[TB] FAIL: 记录数不足（%0d/%0d），但 M_AXIS_RESULT 没有停在 TVALID=1/TREADY=0（TVALID=%b TREADY=%b），停滞原因与假设不符",
                         recs_got, recs_expect,
                         `DNA.M_AXIS_RESULT_TVALID, `DNA.M_AXIS_RESULT_TREADY);
            end else begin
                $display("[TB]   ok  B21 REPRODUCED：送入 %0d 条只回写 %0d 条；RX BD 环只提供 %0d 个描述符，S2MM 用尽后 M_AXIS_RESULT 停在 TVALID=1/TREADY=0",
                         recs_expect, recs_got, rx_bd_used);
            end
        end else begin
            errors++;
            $display("[TB] FAIL: 未知 require=%0s", require_arg);
        end
    endtask

    task automatic finish_report();
        $display("[TB] --------------------------------------------------");
        if (inject_b26) begin
            // 注入模式：判据**必须**失败才算这条判据有效
            if (errors == 0) begin
                $display("[TB] 故障注入自检不通过：注入 B26 后判据却仍然通过，说明判据没有鉴别力");
                $fatal(1, "BD-3b 判据没有鉴别力");
                $finish;
            end
            $display("[TB] 故障注入自检 PASS：注入 B26 后判据如期失败（%0d 项，槽位不符 %0d）",
                     errors, plane_bad);
            $finish;
        end
        // 【XSim 2022.2 的坑】$fatal 既不终止仿真也不让 xsim 非零退出（实测会继续往下跑，
        // 一路跑到看门狗）。所以这里用 if/else 保证失败路径**绝不打印 PASS**，
        // 并在 $fatal 之后显式 $finish；真正的判定由 tools/run_m3_bd.sh 的日志判据做。
        if (errors != 0) begin
            $display("[TB] BD-3b FAIL（%0d 项）", errors);
            $fatal(1, "BD-3b 用例失败");
            $finish;
        end else begin
            $display("[TB] PASS  BD-3b phase=%s rx_bd_mode=%s require=%s（槽位不符 %0d，记录码字不符 %0d）",
                     phase_arg, rx_mode_arg, require_arg, plane_bad, rec_cw_bad);
            $display("[TB] --------------------------------------------------");
            $finish;
        end
    endtask

    // ================================================================
    // 主流程
    // ================================================================
    initial begin
        $display("[TB] ====== M3 / BD-3b：AXI DMA <-> DNA 加速核 数据面 ======");
        $display("[TB] 注意：内存端点是 AXI VIP，不是实际 PS7 的 AFI 通路");

        void'($value$plusargs("phase=%s",      phase_arg));
        void'($value$plusargs("rx_bd_mode=%s", rx_mode_arg));
        void'($value$plusargs("require=%s",    require_arg));
        void'($value$plusargs("reads=%d",      n_reads));
        void'($value$plusargs("inject_b26=%d", inject_b26));
        void'($value$plusargs("mem_out=%s",    mem_out));
        if (!$value$plusargs("wm_file=%s", wm_file)) begin
            $fatal(1, "必须指定 +wm_file=<tests/golden/wm_regions.hex>");
            $finish;
        end
        if (phase_arg != "wm" && phase_arg != "load" && phase_arg != "full") begin
            $fatal(1, "未知 phase（只接受 wm / load / full）");
            $finish;
        end
        if (phase_arg != "wm" && !$value$plusargs("reads_file=%s", reads_file)) begin
            $fatal(1, "load/full 阶段必须指定 +reads_file=<32bit 字镜像>");
            $finish;
        end
        if (n_reads % FRAME_READS != 0) begin
            $fatal(1, "reads 不是 64 的整数倍");
            $finish;
        end

        $display("[TB] phase=%0s rx_bd_mode=%0s require=%0s reads=%0d",
                 phase_arg, rx_mode_arg, require_arg, n_reads);
        $display("[TB] C_SG_LENGTH_WIDTH=%0d -> MaxTransferLen=%0d，固件 RX per_bd=%0d B",
                 SG_LEN_WIDTH, SG_MAX_LEN, FW_RX_PER_BD);

        `PS7.set_stop_on_error(0);

        mem_agent = new("mem_agent", dut.top_bd_i.mem_vip.inst.IF);
        mem_agent.set_agent_tag("mem_vip");
        mem_agent.start_slave();
        $display("[TB] AXI VIP 从机内存模型已启动");

        wait (dut.top_bd_i.rst_ps_peripheral_aresetn === 1'b1);
        step(50);
        $display("[TB] PL 复位已释放 @%0t ps", $time);

        // [B26 故障注入自检 / docs/06-verification-plan.md的故障鉴别力要求]
        // 把引擎的 cw_data 强行接回 in_fifo 的 dout —— 这正是修复前的接法。
        // 用它证明本用例的判据真的能抓住 B26，而不是「编译过、跑完、没报错」。
        // 注入后本用例**必须失败**；如果仍然通过，说明判据没有鉴别力，同样判 FAIL。
        if (inject_b26) begin
            force `ENG.cw_data = `DNA.in_dout;
            $display("[TB] 【故障注入】cw_data 强制接回 in_dout（复现 B26 修复前的接法）");
        end

        bd_ring_init(BD_BASE_TX, TX_BD_CNT);
        bd_ring_init(BD_BASE_RX, RX_BD_CNT);
        $display("[TB] TX/RX BD 环已初始化（%0d / %0d 个，每个 %0d B）",
                 TX_BD_CNT, RX_BD_CNT, BD_BYTES);

        dma_reset();
        dma_channel_start(MM2S_DMACR, MM2S_DMASR, MM2S_CURDESC, BD_BASE_TX, "MM2S");
        dma_channel_start(S2MM_DMACR, S2MM_DMASR, S2MM_CURDESC, BD_BASE_RX, "S2MM");
        if (errors != 0) finish_report();

        axi_write32(ADDR_DNA + DNA_REG0, 32'h0);
        axi_write32(ADDR_DNA + DNA_REG1, 32'h0);
        axi_read32 (ADDR_DNA + DNA_REG1, rd);
        if (rd[5:0] !== 6'd0) begin
            errors++;
            $display("[TB] FAIL: DNA reg1 复位回读 = 0x%08x", rd);
        end

        run_watermark();

        if (phase_arg != "wm" && errors == 0) run_reads();

        finish_report();
    end

    // 全局看门狗：无尺寸十进制字面量默认 32 bit，不能直接写 400_000_000_000
    initial begin
        repeat (400) #1_000_000_000;   // 400 x 1 ms = 400 ms
        $display("[TB] FATAL: BD-3b 全局超时");
        $fatal(1, "BD-3b 超时");
        $finish;
    end

endmodule
