`timescale 1ns/1ps

// Stage1 P16 硬件计数器自证：同一任务连续启动两个 64-read 子批次，
// 检查块/批累计、阶段驻留拍数、总数下界与 done 后稳定性。
module tb_stage1_cycle_counters;
  localparam P_WAYS=16, PIPE_TREE=1, BATCH=2, NUM_LC=2;
  localparam STRIDE=15, REF_LEN=17, READ_BPS=4;
  localparam CODEBITS=READ_BPS*2, RESULT_W=CODEBITS+5+3;

  reg clk=0; always #5 clk=~clk;
  reg rst_n=0, start_batch=0, clear_counters=0;
  reg bram_write_en=0;
  reg [5:0] bram_sel=0;
  reg [10:0] bram_write_addr=0;
  reg [1:0] bram_write_data=0;
  wire cw_req;
  reg cw_valid=0;
  reg [CODEBITS-1:0] cw_data=0;
  wire res_wr;
  wire [RESULT_W-1:0] res_din;
  wire busy,done;
  wire [31:0] cycles_total,cycles_prefill,cycles_run,cycles_tree;
  wire [31:0] blocks_done,batches_done;
  reg [31:0] read_count=0;
  reg cw_fed=0;
  integer result_count=0;
  integer lc,row;
  reg [31:0] first_total;

  srpe_batch_pway #(
    .P_WAYS(P_WAYS),.PIPE_TREE(PIPE_TREE),.BATCH(BATCH),.NUM_LC(NUM_LC),
    .STRIDE(STRIDE),.REF_LEN(REF_LEN),.READ_BPS(READ_BPS),.SCORE_W(3),.POS_W(5)
  ) dut (
    .clk(clk),.rst_n(rst_n),.start_batch(start_batch),.clear_counters(clear_counters),
    .cw_req(cw_req),.cw_valid(cw_valid),.cw_data(cw_data),
    .bram_write_en(bram_write_en),.bram_sel(bram_sel),
    .bram_write_addr(bram_write_addr),.bram_write_data(bram_write_data),
    .res_wr(res_wr),.res_din(res_din),.res_full(1'b0),.busy(busy),.done(done),
    .cycles_total(cycles_total),.cycles_prefill(cycles_prefill),.cycles_run(cycles_run),
    .cycles_tree(cycles_tree),.blocks_done(blocks_done),.batches_done(batches_done)
  );

  always @(posedge clk) begin
    if (!rst_n) begin
      cw_valid <= 0;
      cw_fed <= 0;
      read_count <= 0;
      result_count <= 0;
    end else begin
      cw_valid <= 0;
      if (start_batch) begin
        read_count <= 0;
        cw_fed <= 0;
      end else if (!cw_req) begin
        cw_fed <= 0;
      end else if (!cw_fed && read_count < BATCH) begin
        cw_data <= {CODEBITS{1'b0}};
        cw_valid <= 1;
        cw_fed <= 1;
        read_count <= read_count + 1;
      end
      if (res_wr) result_count <= result_count + 1;
    end
  end

  initial begin
    repeat(5) @(negedge clk);
    rst_n=1;
    for(lc=0;lc<NUM_LC;lc=lc+1)
      for(row=0;row<REF_LEN;row=row+1) begin
        @(negedge clk);bram_write_en=1;bram_sel=lc;
        bram_write_addr=row;bram_write_data=0;
      end
    @(negedge clk);bram_write_en=0;

    @(negedge clk);start_batch=1;
    @(negedge clk);start_batch=0;
    wait(done);
    @(negedge clk);
    if (blocks_done!==2 || batches_done!==1)
      $fatal(1,"第一批计数错误：blocks=%0d batches=%0d",blocks_done,batches_done);
    if (cycles_prefill!==22 || cycles_run!==4 || cycles_tree!==12)
      $fatal(1,"第一批阶段拍数错误：prefill=%0d run=%0d tree=%0d",
             cycles_prefill,cycles_run,cycles_tree);
    if (cycles_total < cycles_prefill+cycles_run+cycles_tree)
      $fatal(1,"第一批 total 小于三个阶段之和");
    first_total=cycles_total;
    repeat(12) @(negedge clk);
    if (cycles_total!==first_total || blocks_done!==2 || batches_done!==1)
      $fatal(1,"第一批 done 后计数仍在变化");
    $display("[STAGE1 COUNTERS] batch1 total=%0d prefill=%0d run=%0d tree=%0d blocks=%0d batches=%0d PASS",
             cycles_total,cycles_prefill,cycles_run,cycles_tree,blocks_done,batches_done);

    @(negedge clk);start_batch=1;
    @(negedge clk);start_batch=0;
    wait(done);
    @(negedge clk);
    if (blocks_done!==4 || batches_done!==2)
      $fatal(1,"累计块/批错误：blocks=%0d batches=%0d",blocks_done,batches_done);
    if (cycles_prefill!==44 || cycles_run!==8 || cycles_tree!==24)
      $fatal(1,"累计阶段拍数错误：prefill=%0d run=%0d tree=%0d",
             cycles_prefill,cycles_run,cycles_tree);
    if (cycles_total!==first_total*2)
      $fatal(1,"两批总周期未累加：first=%0d total=%0d",first_total,cycles_total);
    if (cycles_total < cycles_prefill+cycles_run+cycles_tree)
      $fatal(1,"累计 total 小于三个阶段之和");
    if (result_count!=BATCH*2)
      $fatal(1,"输出条数错误：got=%0d expected=%0d",result_count,BATCH*2);
    first_total=cycles_total;
    repeat(12) @(negedge clk);
    if (cycles_total!==first_total || cycles_prefill!==44 || cycles_run!==8 ||
        cycles_tree!==24 || blocks_done!==4 || batches_done!==2)
      $fatal(1,"第二批 done 后计数仍在变化");
    $display("[STAGE1 COUNTERS] after2 total=%0d prefill=%0d run=%0d tree=%0d blocks=%0d batches=%0d; hand=%0d batches x %0d LC x 1 tile = 4 blocks PASS",
             cycles_total,cycles_prefill,cycles_run,cycles_tree,blocks_done,batches_done,
             batches_done,NUM_LC);
    @(negedge clk);clear_counters=1;
    @(negedge clk);clear_counters=0;
    if (cycles_total!==0 || cycles_prefill!==0 || cycles_run!==0 || cycles_tree!==0 ||
        blocks_done!==0 || batches_done!==0)
      $fatal(1,"新任务清零脉冲未清除全部计数器");
    $display("[STAGE1 COUNTERS] new-task clear resets all six counters PASS");
    $finish;
  end

  initial begin
    #10000000;
    $fatal(1,"Stage1 计数器自证 TB 超时");
  end
endmodule
