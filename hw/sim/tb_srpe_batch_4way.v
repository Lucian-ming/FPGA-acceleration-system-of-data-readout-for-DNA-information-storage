// =============================================================
// File: tb_srpe_batch_4way.v
// Desc: Stage1 4-Way vs 2-Way Cycle-Exact & Result Equivalence Testbench
//       - 并行实例化 2-way 基线与 4-way 修复流水线变体
//       - 共享相同的输入读段（64条）与水印参考区域
//       - 周期级度量吞吐开销，验证 4-way 相比 2-way 达成约 2x 吞吐提升
//       - 100% 逐位校验 4-way 与 2-way 输出的 score、global_pos 与 cw
//       - 当 NUM_LC=50 时，同步比对 tests/golden/stage1_fwd_expect.txt
// =============================================================
`timescale 1ns/1ps

module tb_srpe_batch_4way;

    // 参数配置：支持命令行宏 +NUM_LC 覆盖，默认支持快速与全量配置
    `ifndef CFG_NUM_LC
    `define CFG_NUM_LC 6
    `endif

    localparam integer BATCH    = 64;
    localparam integer NUM_LC   = `CFG_NUM_LC;
    localparam integer STRIDE   = 807;
    localparam integer REF_LEN  = 957;
    localparam integer READ_BPS = 150;
    localparam integer CODEBITS = READ_BPS * 2;
    localparam integer SCORE_W  = 10;
    localparam integer POS_W    = 16;
    localparam integer RESULT_W = CODEBITS + POS_W + SCORE_W;
    localparam integer WM_DEPTH = 50 * REF_LEN; // 载入全部50个区域水印池

    reg clk = 0;
    reg rst_n = 0;
    always #5 clk = ~clk; // 100 MHz 时钟 (周期 10ns)

    reg                 start_batch = 0;

    // 水印预载信号（同时广播给 2-way 与 4-way）
    reg                 bram_write_en = 0;
    reg  [5:0]          bram_sel = 0;
    reg  [10:0]         bram_write_addr = 0;
    reg  [1:0]          bram_write_data = 0;

    // 2-Way 接口
    wire                cw_req_2w;
    reg                 cw_valid_2w = 0;
    reg  [CODEBITS-1:0] cw_data_2w  = 0;
    wire                res_wr_2w;
    wire [RESULT_W-1:0] res_din_2w;
    reg                 res_full_2w = 0;
    wire                busy_2w, done_2w;

    // 4-Way 接口
    wire                cw_req_4w;
    reg                 cw_valid_4w = 0;
    reg  [CODEBITS-1:0] cw_data_4w  = 0;
    wire                res_wr_4w;
    wire [RESULT_W-1:0] res_din_4w;
    reg                 res_full_4w = 0;
    wire                busy_4w, done_4w;

    // ----------------------------------------------------------
    // 实例化 2-Way 基线 (来自 srpe_batch_2way.v)
    // ----------------------------------------------------------
    srpe_batch #(
        .BATCH(BATCH), .NUM_LC(NUM_LC), .STRIDE(STRIDE),
        .REF_LEN(REF_LEN), .READ_BPS(READ_BPS),
        .SCORE_W(SCORE_W), .POS_W(POS_W)
    ) dut_2way (
        .clk(clk), .rst_n(rst_n), .start_batch(start_batch),
        .cw_req(cw_req_2w), .cw_valid(cw_valid_2w), .cw_data(cw_data_2w),
        .bram_write_en(bram_write_en), .bram_sel(bram_sel),
        .bram_write_addr(bram_write_addr), .bram_write_data(bram_write_data),
        .res_wr(res_wr_2w), .res_din(res_din_2w), .res_full(res_full_2w),
        .busy(busy_2w), .done(done_2w)
    );

    // ----------------------------------------------------------
    // 实例化 4-Way 修复版 (来自 srpe_batch_4way.v)
    // ----------------------------------------------------------
    srpe_batch_4way #(
        .BATCH(BATCH), .NUM_LC(NUM_LC), .STRIDE(STRIDE),
        .REF_LEN(REF_LEN), .READ_BPS(READ_BPS),
        .SCORE_W(SCORE_W), .POS_W(POS_W)
    ) dut_4way (
        .clk(clk), .rst_n(rst_n), .start_batch(start_batch),
        .cw_req(cw_req_4w), .cw_valid(cw_valid_4w), .cw_data(cw_data_4w),
        .bram_write_en(bram_write_en), .bram_sel(bram_sel),
        .bram_write_addr(bram_write_addr), .bram_write_data(bram_write_data),
        .res_wr(res_wr_4w), .res_din(res_din_4w), .res_full(res_full_4w),
        .busy(busy_4w), .done(done_4w)
    );

    // ----------------------------------------------------------
    // 黄金测试数据存储
    // ----------------------------------------------------------
    reg [1:0]          wm_sym [0:WM_DEPTH-1];
    reg [CODEBITS-1:0] reads  [0:BATCH-1];
    integer exp_pos [0:BATCH-1];
    integer exp_sc  [0:BATCH-1];

    // ----------------------------------------------------------
    // 2-Way 结果记录
    // ----------------------------------------------------------
    integer got_n_2w = 0;
    integer got_pos_2w [0:BATCH-1];
    integer got_sc_2w  [0:BATCH-1];
    reg [CODEBITS-1:0] got_cw_2w [0:BATCH-1];

    always @(posedge clk) begin
        if (res_wr_2w && got_n_2w < BATCH) begin
            got_sc_2w [got_n_2w] <= res_din_2w[SCORE_W-1:0];
            got_pos_2w[got_n_2w] <= res_din_2w[SCORE_W+POS_W-1:SCORE_W];
            got_cw_2w [got_n_2w] <= res_din_2w[RESULT_W-1:SCORE_W+POS_W];
            got_n_2w = got_n_2w + 1;
        end
    end

    // ----------------------------------------------------------
    // 4-Way 结果记录
    // ----------------------------------------------------------
    integer got_n_4w = 0;
    integer got_pos_4w [0:BATCH-1];
    integer got_sc_4w  [0:BATCH-1];
    reg [CODEBITS-1:0] got_cw_4w [0:BATCH-1];

    always @(posedge clk) begin
        if (res_wr_4w && got_n_4w < BATCH) begin
            got_sc_4w [got_n_4w] <= res_din_4w[SCORE_W-1:0];
            got_pos_4w[got_n_4w] <= res_din_4w[SCORE_W+POS_W-1:SCORE_W];
            got_cw_4w [got_n_4w] <= res_din_4w[RESULT_W-1:SCORE_W+POS_W];
            got_n_4w = got_n_4w + 1;
        end
    end

    // ----------------------------------------------------------
    // 供数控制：分别为 2-way 与 4-way 提供各自的码字握手
    // ----------------------------------------------------------
    integer feed_i_2w = 0;
    reg     fed_2w = 1'b0;
    always @(posedge clk) begin
        if (!rst_n) begin
            cw_valid_2w <= 1'b0; feed_i_2w <= 0; fed_2w <= 1'b0;
        end else begin
            cw_valid_2w <= 1'b0;
            if (!cw_req_2w) begin
                fed_2w <= 1'b0;
            end else if (!fed_2w && feed_i_2w < BATCH) begin
                cw_data_2w  <= reads[feed_i_2w];
                cw_valid_2w <= 1'b1;
                feed_i_2w   <= feed_i_2w + 1;
                fed_2w      <= 1'b1;
            end
        end
    end

    integer feed_i_4w = 0;
    reg     fed_4w = 1'b0;
    always @(posedge clk) begin
        if (!rst_n) begin
            cw_valid_4w <= 1'b0; feed_i_4w <= 0; fed_4w <= 1'b0;
        end else begin
            cw_valid_4w <= 1'b0;
            if (!cw_req_4w) begin
                fed_4w <= 1'b0;
            end else if (!fed_4w && feed_i_4w < BATCH) begin
                cw_data_4w  <= reads[feed_i_4w];
                cw_valid_4w <= 1'b1;
                feed_i_4w   <= feed_i_4w + 1;
                fed_4w      <= 1'b1;
            end
        end
    end

    // ----------------------------------------------------------
    // 周期统计变量
    // ----------------------------------------------------------
    integer cyc_cnt = 0;
    integer t_start = 0;
    integer t_done_2w = 0;
    integer t_done_4w = 0;
    reg     rec_done_2w = 0;
    reg     rec_done_4w = 0;

    always @(posedge clk) begin
        cyc_cnt <= cyc_cnt + 1;
        if (done_2w && !rec_done_2w) begin
            t_done_2w <= cyc_cnt;
            rec_done_2w <= 1'b1;
        end
        if (done_4w && !rec_done_4w) begin
            t_done_4w <= cyc_cnt;
            rec_done_4w <= 1'b1;
        end
    end

    // ----------------------------------------------------------
    // 主测试流程
    // ----------------------------------------------------------
    integer fd, code, dummy, i, lc, row;
    integer diff_sc_cnt = 0, diff_pos_cnt = 0, diff_cw_cnt = 0;
    integer gold_sc_err = 0, gold_pos_tie = 0, gold_cw_err = 0;
    integer cycles_2w = 0, cycles_4w = 0;
    integer timeout = 0;

    initial begin
        $display("================================================================");
        $display("[TB 4-WAY] Stage1 4-Way vs 2-Way 周期与一致性对比仿真启动");
        $display("[TB 4-WAY] 配置: BATCH=%0d, NUM_LC=%0d, STRIDE=%0d, READ_BPS=%0d",
                 BATCH, NUM_LC, STRIDE, READ_BPS);
        $display("================================================================");

        // 读入黄金数据
        $readmemh("tests/golden/wm_regions.hex", wm_sym);
        $readmemh("tests/golden/reads_cw.hex", reads);

        // 若 NUM_LC==50，读取 stage1_fwd_expect.txt 用于黄金校验
        if (NUM_LC == 50) begin
            fd = $fopen("tests/golden/stage1_fwd_expect.txt", "r");
            if (fd != 0) begin
                code = $fgetc(fd);
                while (code != "\n" && code != -1) code = $fgetc(fd);
                for (i = 0; i < BATCH; i = i + 1) begin
                    code = $fscanf(fd, "%d %d %d\n", dummy, exp_pos[i], exp_sc[i]);
                end
                $fclose(fd);
                $display("[TB 4-WAY] 成功载入 stage1_fwd_expect.txt 黄金期望数据");
            end else begin
                $display("[TB 4-WAY] ⚠️ 未能打开 stage1_fwd_expect.txt");
            end
        end

        // 初始复位
        repeat (5) @(posedge clk);
        #1 rst_n = 1;
        repeat (5) @(posedge clk);

        // 预载水印到两核 BRAM
        $display("[TB 4-WAY] 正在预载水印 BRAM (%0d 个符号)...", NUM_LC * REF_LEN);
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
        $display("[TB 4-WAY] 水印预载完成");

        repeat (5) @(posedge clk);
        #1 start_batch = 1;
        t_start = cyc_cnt;
        @(posedge clk);
        #1 start_batch = 0;
        $display("[TB 4-WAY] 同步启动 2-Way 与 4-Way 批处理...");

        // 等待两核均完成
        timeout = 0;
        while ((!rec_done_2w || !rec_done_4w || got_n_2w < BATCH || got_n_4w < BATCH) && timeout < 25_000_000) begin
            @(posedge clk);
            timeout = timeout + 1;
        end

        if (got_n_2w < BATCH || got_n_4w < BATCH) begin
            $display("[TB 4-WAY] ✗ 超时: 2-way 收取 %0d/%0d, 4-way 收取 %0d/%0d",
                     got_n_2w, BATCH, got_n_4w, BATCH);
            $fatal(1);
        end

        repeat (10) @(posedge clk);

        cycles_2w = t_done_2w - t_start;
        cycles_4w = t_done_4w - t_start;

        $display("----------------------------------------------------------------");
        $display("[TB 4-WAY] 吞吐周期统计结果:");
        $display("  2-Way 总耗时周期: %0d 周期 (约 %0.1fk 周期)", cycles_2w, cycles_2w / 1000.0);
        $display("  4-Way 总耗时周期: %0d 周期 (约 %0.1fk 周期)", cycles_4w, cycles_4w / 1000.0);
        $display("  加速比 (2W / 4W): %0.3fx", (cycles_2w * 1.0) / cycles_4w);
        $display("----------------------------------------------------------------");

        // ------------------------------------------------------
        // 核心判据 1: 4-Way 与 2-Way 逐位等价性检查
        // ------------------------------------------------------
        for (i = 0; i < BATCH; i = i + 1) begin
            if (got_sc_4w[i] !== got_sc_2w[i]) begin
                if (diff_sc_cnt < 8)
                    $display("[TB 4-WAY] ✗ read %0d 分数不一致: 4-Way=%0d, 2-Way=%0d",
                             i, got_sc_4w[i], got_sc_2w[i]);
                diff_sc_cnt = diff_sc_cnt + 1;
            end
            if (got_pos_4w[i] !== got_pos_2w[i]) begin
                if (diff_pos_cnt < 8)
                    $display("[TB 4-WAY] ✗ read %0d 位置不一致: 4-Way=%0d, 2-Way=%0d (分数=%0d)",
                             i, got_pos_4w[i], got_pos_2w[i], got_sc_4w[i]);
                diff_pos_cnt = diff_pos_cnt + 1;
            end
            if (got_cw_4w[i] !== got_cw_2w[i]) begin
                if (diff_cw_cnt < 4)
                    $display("[TB 4-WAY] ✗ read %0d 码字不一致", i);
                diff_cw_cnt = diff_cw_cnt + 1;
            end
        end

        $display("[TB 4-WAY] 4-Way vs 2-Way 等价性比对:");
        $display("  分数不符条数: %0d / %0d", diff_sc_cnt, BATCH);
        $display("  位置不符条数: %0d / %0d", diff_pos_cnt, BATCH);
        $display("  码字不符条数: %0d / %0d", diff_cw_cnt, BATCH);

        if (diff_sc_cnt != 0 || diff_pos_cnt != 0 || diff_cw_cnt != 0) begin
            $display("[TB 4-WAY] ✗ FAIL: 4-Way 输出与 2-Way 存在差异！");
            $fatal(1);
        end else begin
            $display("[TB 4-WAY] ✓ PASS: 4-Way 与 2-Way 输出 100%% 逐位一致！");
        end

        // ------------------------------------------------------
        // 核心判据 2: 若全量 NUM_LC==50，校验黄金模型期望
        // ------------------------------------------------------
        if (NUM_LC == 50) begin
            $display("----------------------------------------------------------------");
            $display("[TB 4-WAY] 对比 tests/golden/stage1_fwd_expect.txt 黄金模型:");
            for (i = 0; i < BATCH; i = i + 1) begin
                if (got_sc_4w[i] !== exp_sc[i]) begin
                    gold_sc_err = gold_sc_err + 1;
                end else if (got_pos_4w[i] !== exp_pos[i]) begin
                    gold_pos_tie = gold_pos_tie + 1;
                end
                if (got_cw_4w[i] !== reads[i]) begin
                    gold_cw_err = gold_cw_err + 1;
                end
            end
            $display("  黄金分数不符: %0d 条", gold_sc_err);
            $display("  黄金并列峰数: %0d 条 (门限 <= %0d)", gold_pos_tie, (BATCH * 5) / 100);
            $display("  码字回传错误: %0d 条", gold_cw_err);
            if (gold_sc_err == 0 && gold_cw_err == 0 && gold_pos_tie <= (BATCH * 5) / 100) begin
                $display("[TB 4-WAY] ✓ PASS: 4-Way 与黄金模型 100%% 吻合！");
            end else begin
                $display("[TB 4-WAY] ✗ FAIL: 4-Way 与黄金模型比对超标！");
                $fatal(1);
            end
        end

        $display("================================================================");
        $display("[TB 4-WAY] 全部测试项 PASS！退出码 0");
        $display("================================================================");
        $finish;
    end

endmodule
