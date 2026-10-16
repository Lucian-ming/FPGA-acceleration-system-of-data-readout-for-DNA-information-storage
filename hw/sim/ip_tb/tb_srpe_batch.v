// =============================================================
// tb_srpe_batch.v — Stage1 比对引擎的文件型 Testbench
//
// 判据来自黄金模型，不是"能跑就算过"：
//   水印  tests/golden/wm_regions.hex      50 区域 × 957 符号（TB 直接预载 BRAM，
//                                          绕开 PS 侧仍未修复的预载通路 B1）
//   读段  tests/golden/reads_cw.hex        每行 300 bit 位平面码字
//   期望  tests/golden/stage1_fwd_expect.txt  每条读段的正向 (pos, score)
//
// srpe_batch 只做正向比对，所以判据用 fwd 那一份。
// score 必须逐条完全相同；pos 允许「并列峰」差异（同分的另一个位置），
// TB 会分别统计并对超标即 $fatal。
//
// 运行（一批 64 条约需 6.2 M 周期，Icarus 上约 1~3 分钟）：
//   iverilog -g2005 -o /tmp/tb_srpe \
//       hw/ip/Dna_accelerator_core_1_0/hdl/srpe_batch.v \
//       hw/sim/ip_tb/tb_srpe_batch.v
//   vvp /tmp/tb_srpe
// =============================================================
`timescale 1ns/1ps

module tb_srpe_batch;

    localparam integer BATCH    = 64;
    localparam integer NUM_LC   = 50;
    localparam integer STRIDE   = 807;
    localparam integer REF_LEN  = 957;
    localparam integer READ_BPS = 150;
    localparam integer CODEBITS = READ_BPS * 2;
    localparam integer SCORE_W  = 10;
    localparam integer POS_W    = 16;
    localparam integer RESULT_W = CODEBITS + POS_W + SCORE_W;
    localparam integer WM_DEPTH = NUM_LC * REF_LEN;

    reg clk = 0, rst_n = 0;
    always #5 clk = ~clk;

    reg                 start_batch = 0;
    wire                cw_req;
    reg                 cw_valid = 0;
    reg  [CODEBITS-1:0] cw_data  = 0;

    reg                 bram_write_en = 0;
    reg  [5:0]          bram_sel = 0;
    reg  [10:0]         bram_write_addr = 0;
    reg  [1:0]          bram_write_data = 0;

    wire                res_wr;
    wire [RESULT_W-1:0] res_din;
    reg                 res_full = 0;
    wire                busy, done;

    srpe_batch #(
        .BATCH(BATCH), .NUM_LC(NUM_LC), .STRIDE(STRIDE),
        .REF_LEN(REF_LEN), .READ_BPS(READ_BPS),
        .SCORE_W(SCORE_W), .POS_W(POS_W)
    ) dut (
        .clk(clk), .rst_n(rst_n), .start_batch(start_batch),
        .cw_req(cw_req), .cw_valid(cw_valid), .cw_data(cw_data),
        .bram_write_en(bram_write_en), .bram_sel(bram_sel),
        .bram_write_addr(bram_write_addr), .bram_write_data(bram_write_data),
        .res_wr(res_wr), .res_din(res_din), .res_full(res_full),
        .busy(busy), .done(done)
    );

    // ---------------- 黄金数据 ----------------
    reg [1:0]          wm_sym [0:WM_DEPTH-1];
    reg [CODEBITS-1:0] reads  [0:BATCH-1];
    integer exp_pos [0:BATCH-1];
    integer exp_sc  [0:BATCH-1];

    // ---------------- 结果收集 ----------------
    integer got_n = 0;
    integer got_pos [0:BATCH-1];
    integer got_sc  [0:BATCH-1];
    reg [CODEBITS-1:0] got_cw [0:BATCH-1];

    always @(posedge clk) begin
        if (res_wr && got_n < BATCH) begin
            got_sc [got_n] <= res_din[SCORE_W-1:0];
            got_pos[got_n] <= res_din[SCORE_W+POS_W-1:SCORE_W];
            got_cw [got_n] <= res_din[RESULT_W-1:SCORE_W+POS_W];
            got_n = got_n + 1;
        end
    end

    // ---------------- 供数：每次 cw_req 只给一拍 ----------------
    // cw_req 在 DUT 进入 S_LOAD_R 后还会多持续一拍。若不加 fed 标志，
    // TB 会在 DUT 正逐位读取 cw_data 的过程中把它改写成下一条读段，
    // 装载出来的数据就是两条读段的混合。DNA 顶层用的也是同样的 rd_issued 模式。
    integer feed_i = 0;
    reg     fed = 1'b0;
    always @(posedge clk) begin
        if (!rst_n) begin
            cw_valid <= 1'b0; feed_i <= 0; fed <= 1'b0;
        end else begin
            cw_valid <= 1'b0;
            if (!cw_req) begin
                fed <= 1'b0;
            end else if (!fed && feed_i < BATCH) begin
                cw_data  <= reads[feed_i];
                cw_valid <= 1'b1;
                feed_i   <= feed_i + 1;
                fed      <= 1'b1;
            end
        end
    end

    // ---------------- 主流程 ----------------
    integer fd, i, j, lc, row, idx, code, dummy;
    integer sc_err, pos_err, pos_tie, cw_err, max_ties;
    reg [CODEBITS-1:0] exp_cw;
    integer timeout;
    reg [8*256-1:0] reads_path, expect_path, dump_stage1_path;
    integer plusarg_result;
    integer dump_stage1_en;
    integer dump_fd;
    reg [383:0] dump_rec;

    // Optional checkpoint export for a real stage-to-stage regression.  The
    // default golden test remains unchanged; when requested, this file is
    // the actual Stage1 result, six LSB-first 64-bit words per record.
    initial dump_stage1_en = $value$plusargs("dump_stage1=%s", dump_stage1_path);

    initial begin
        reads_path = "tests/golden/reads_cw.hex";
        expect_path = "tests/golden/stage1_fwd_expect.txt";
        max_ties = (BATCH * 5) / 100;
        plusarg_result = $value$plusargs("reads=%s", reads_path);
        plusarg_result = $value$plusargs("expect=%s", expect_path);
        plusarg_result = $value$plusargs("max_ties=%d", max_ties);
        $readmemh("tests/golden/wm_regions.hex", wm_sym);
        $readmemh(reads_path, reads);

        // 读正向期望：跳过以 '#' 开头的注释行
        fd = $fopen(expect_path, "r");
        if (fd == 0) begin $display("[TB] 打不开 Stage1 期望文件: %s", expect_path); $fatal(1); end
        code = $fgetc(fd);                       // 吃掉注释行
        while (code != "\n" && code != -1) code = $fgetc(fd);
        for (i = 0; i < BATCH; i = i + 1) begin
            code = $fscanf(fd, "%d %d %d\n", dummy, exp_pos[i], exp_sc[i]);
            if (code != 3) begin
                $display("[TB] 期望文件第 %0d 行解析失败", i); $fatal(1);
            end
        end
        $fclose(fd);
        $display("[TB] 已载入 水印 %0d 符号 / 读段 %0d 条 / 期望 %0d 条",
                 WM_DEPTH, BATCH, BATCH);

        // 注意：控制信号一律错开时钟沿再变，否则与 DUT 的采样构成竞争，
        //       Icarus 下会直接采不到（曾导致 start_batch 完全失效）。
        repeat (5) @(posedge clk);
        #1 rst_n = 1;
        repeat (5) @(posedge clk);

        // ---- 预载水印 BRAM：逐区域写 957 个符号 ----
        // 注意：这里绕开了 PS 侧的预载通路（B1 尚未修复），
        //       只验证比对引擎本身。
        for (lc = 0; lc < NUM_LC; lc = lc + 1) begin
            for (row = 0; row < REF_LEN; row = row + 1) begin
                @(posedge clk);
                bram_write_en   <= 1'b1;
                bram_sel        <= lc[5:0];
                bram_write_addr <= row[10:0];
                bram_write_data <= wm_sym[lc*REF_LEN + row];
            end
        end
        @(posedge clk);
        bram_write_en <= 1'b0;
        $display("[TB] 水印预载完成（%0d 个符号）", NUM_LC*REF_LEN);

        repeat (5) @(posedge clk);
        #1 start_batch = 1;
        @(posedge clk);
        #1 start_batch = 0;
        $display("[TB] 开始比对一批 %0d 条读段（约 %0d 万周期，请稍候）",
                 BATCH, (NUM_LC*(STRIDE+1)*153)/10000);

        timeout = 0;
        while (got_n < BATCH && timeout < 20_000_000) begin
            @(posedge clk);
            timeout = timeout + 1;
        end

        if (got_n < BATCH) begin
            $display("[TB] ✗ 超时：只收到 %0d/%0d 条结果", got_n, BATCH);
            $fatal(1);
        end
        // 计数满的那一拍，最后一笔非阻塞写还没落盘，多等几拍再比对
        repeat (5) @(posedge clk);

        // ---- 判定 ----
        sc_err = 0; pos_err = 0; pos_tie = 0; cw_err = 0;
        for (i = 0; i < BATCH; i = i + 1) begin
            if (got_sc[i] !== exp_sc[i]) begin
                if (sc_err < 8)
                    $display("[TB] ✗ read %0d 分数不符：硬件 %0d，期望 %0d",
                             i, got_sc[i], exp_sc[i]);
                sc_err = sc_err + 1;
            end else if (got_pos[i] !== exp_pos[i]) begin
                // 分数相同但位置不同 = 并列峰，可接受但要统计
                pos_tie = pos_tie + 1;
                if (pos_tie <= 4)
                    $display("[TB]   ~ read %0d 并列峰：硬件 pos=%0d，模型 pos=%0d（同为 %0d 分）",
                             i, got_pos[i], exp_pos[i], got_sc[i]);
            end
            // 回传的码字必须原样等于输入
            exp_cw = reads[i];
            if (got_cw[i] !== exp_cw) begin
                if (cw_err < 4)
                    $display("[TB] ✗ read %0d 回传码字与输入不符", i);
                cw_err = cw_err + 1;
            end
        end

        $display("--------------------------------------------------");
        $display("[TB] 分数不符 %0d 条 / 码字不符 %0d 条 / 并列峰 %0d 条（共 %0d 条）",
                 sc_err, cw_err, pos_tie, BATCH);
        if (sc_err == 0 && cw_err == 0 && pos_tie <= max_ties)
            $display("[TB] ✓ PASS  与黄金模型一致（并列峰 %0d 条，门限 %0d）", pos_tie, max_ties);
        else begin
            $display("[TB] ✗ FAIL");
            $display("--------------------------------------------------");
            $fatal(1);
        end
        $display("--------------------------------------------------");
        if (dump_stage1_en) begin
            dump_fd = $fopen(dump_stage1_path, "w");
            if (dump_fd == 0) begin
                $display("[TB] ✗ 无法打开 Stage1 checkpoint: %s", dump_stage1_path);
                $fatal(1);
            end
            for (i = 0; i < BATCH; i = i + 1) begin
                dump_rec = {RESULT_W{1'b0}};
                dump_rec[SCORE_W-1:0] = got_sc[i];
                dump_rec[SCORE_W+POS_W-1:SCORE_W] = got_pos[i];
                dump_rec[RESULT_W-1:SCORE_W+POS_W] = got_cw[i];
                for (j = 0; j < 6; j = j + 1)
                    $fdisplay(dump_fd, "%016h", dump_rec[j*64 +: 64]);
            end
            $fclose(dump_fd);
            $display("[TB] ✓ 已导出实际 Stage1 checkpoint: %s", dump_stage1_path);
        end
        $finish;
    end

endmodule
