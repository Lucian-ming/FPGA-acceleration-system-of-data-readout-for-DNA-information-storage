`timescale 1ns/1ps
`ifndef CFG_NUM_LC
`define CFG_NUM_LC 50
`endif

// LC50 单批状态分解：只在 testbench 层次读取 DUT 的 st，不修改被测 RTL。
// 输入/输出无额外背压；计数范围与 cycles_total 一样，从接受 start_batch 到 S_DONE。
module tb_stage1_state_split;
  localparam integer LC = `CFG_NUM_LC;
  reg clk=0; always #5 clk=~clk;
  reg rst_n=0, start_batch=0, clear_counters=0;
  reg bram_write_en=0;
  reg [5:0] bram_sel=0;
  reg [10:0] bram_write_addr=0;
  reg [1:0] bram_write_data=0;
  reg [1:0] wm[0:LC*957-1];
  reg [299:0] reads[0:63];
  reg [325:0] expected[0:63];

  wire cw_req;
  reg cw_valid=0;
  reg [299:0] cw_data=0;
  integer read_index=0;
  reg read_issued=0, read_pending=0;
  reg [1:0] read_wait=0;
  reg [299:0] pending_data=0;

  wire res_wr, busy, done;
  wire [325:0] res_din;
  wire [31:0] cycles_total, cycles_prefill, cycles_run, cycles_tree;
  wire [31:0] blocks_done, batches_done;
  integer output_count=0;
  integer state_cycles[0:15];
  integer state_hits[0:15];
  integer measured_cycles=0;
  integer last_state=-1;
  integer last_progress_blocks=0;
  reg measuring=0;

  srpe_batch_pway #(
    .P_WAYS(16), .PIPE_TREE(1), .BATCH(64), .NUM_LC(LC),
    .STRIDE(807), .REF_LEN(957), .READ_BPS(150)
  ) u_dut (
    .clk(clk), .rst_n(rst_n), .start_batch(start_batch),
    .clear_counters(clear_counters),
    .cw_req(cw_req), .cw_valid(cw_valid), .cw_data(cw_data),
    .bram_write_en(bram_write_en), .bram_sel(bram_sel),
    .bram_write_addr(bram_write_addr), .bram_write_data(bram_write_data),
    .res_wr(res_wr), .res_din(res_din), .res_full(1'b0),
    .busy(busy), .done(done),
    .cycles_total(cycles_total), .cycles_prefill(cycles_prefill),
    .cycles_run(cycles_run), .cycles_tree(cycles_tree),
    .blocks_done(blocks_done), .batches_done(batches_done)
  );

  // 模拟顶层的 rd_issued 单次取数和同步 FIFO 响应延迟；每条结果均与独立 oracle 比较。
  always @(posedge clk) begin
    if (!rst_n) begin
      read_index <= 0;
      output_count = 0;
      read_issued <= 0;
      read_pending <= 0;
      read_wait <= 0;
      cw_valid <= 0;
      cw_data <= 0;
    end else begin
      cw_valid <= 0;
      if (!cw_req)
        read_issued <= 0;
      if (cw_req && !read_issued && read_index < 64) begin
        read_issued <= 1;
        read_pending <= 1;
        read_wait <= 3;
        pending_data <= reads[read_index];
        read_index <= read_index + 1;
      end else if (read_pending) begin
        if (read_wait > 1)
          read_wait <= read_wait - 1'b1;
        else begin
          cw_data <= pending_data;
          cw_valid <= 1;
          read_pending <= 0;
        end
      end
      if (res_wr) begin
        if (output_count >= 64)
          $fatal(1, "Stage1 多输出记录");
        if (res_din !== expected[output_count])
          $fatal(1, "record=%0d result=%h oracle=%h",
                 output_count, res_din, expected[output_count]);
        output_count = output_count + 1;
      end
    end
  end

  // 在 posedge 采样旧状态，与 RTL 周期计数器的非阻塞更新口径一致。
  always @(posedge clk) begin : count_fsm_states
    integer s;
    if (!rst_n) begin
      measured_cycles = 0;
      last_state = -1;
    end else if (measuring && (busy || ((u_dut.st == 4'd0) && start_batch))) begin
      if ((^u_dut.st) === 1'bx)
        $fatal(1, "Stage1 FSM 状态未知");
      s = u_dut.st;
      state_cycles[s] = state_cycles[s] + 1;
      measured_cycles = measured_cycles + 1;
      if (last_state != s)
        state_hits[s] = state_hits[s] + 1;
      last_state = s;
    end else if (measuring) begin
      measuring = 0;
      last_state = -1;
    end
    if (rst_n && busy && (blocks_done >= last_progress_blocks + ((LC == 50) ? 510 : 51))) begin
      last_progress_blocks = blocks_done;
      $display("[STATE-SPLIT] progress blocks_done=%0d state=%0d cycles=%0d", blocks_done, u_dut.st, cycles_total);
    end
  end

  function [8*12-1:0] state_name;
    input integer state_id;
    begin
      case (state_id)
        0: state_name="S_IDLE";
        1: state_name="S_CLR";
        2: state_name="S_LOAD";
        3: state_name="S_LOAD_R";
        4: state_name="S_PREFILL";
        5: state_name="S_INITC";
        6: state_name="S_LAUNCH";
        7: state_name="S_RUN";
        8: state_name="S_UPD1";
        9: state_name="S_UPD2";
        10: state_name="S_NEXT";
        11: state_name="S_EMIT";
        12: state_name="S_EMIT2";
        13: state_name="S_EMIT_FINAL";
        14: state_name="S_DONE";
        15: state_name="S_EMIT_W";
        default: state_name="UNKNOWN";
      endcase
    end
  endfunction

  integer lc, row, i, state_sum, delta;
  real per_block;
  reg [8*1024-1:0] fixture_dir;
  reg [8*12-1:0] label;
  initial begin
    for (i=0; i<16; i=i+1) begin
      state_cycles[i]=0;
      state_hits[i]=0;
    end
    if (!$value$plusargs("fixture_dir=%s", fixture_dir))
      $fatal(1, "必须显式提供 fixture_dir");
    $readmemh({fixture_dir,"/wm.hex"}, wm);
    $readmemh({fixture_dir,"/reads.hex"}, reads);
    $readmemh({fixture_dir,"/expect.hex"}, expected);
    $display("[STATE-SPLIT] started LC=%0d BATCH=64 fixture=%0s", LC, fixture_dir);

    repeat (5) @(negedge clk);
    rst_n=1;
    repeat (5) @(negedge clk);
    for (lc=0; lc<LC; lc=lc+1) begin
      for (row=0; row<957; row=row+1) begin
        @(negedge clk);
        bram_write_en=1;
        bram_sel=lc;
        bram_write_addr=row;
        bram_write_data=wm[lc*957+row];
      end
    end
    @(negedge clk); bram_write_en=0;
    repeat (5) @(negedge clk);

    // 独立清零后再发 start，确保接收启动拍也纳入 total 与状态统计。
    @(negedge clk); clear_counters=1;
    @(negedge clk); clear_counters=0;
    repeat (2) @(negedge clk);
    measuring=1;
    start_batch=1;
    @(negedge clk); start_batch=0;
    wait(done);
    repeat (4) @(negedge clk);

    if (read_index!=64 || output_count!=64)
      $fatal(1, "输入/输出条数错误：reads=%0d outputs=%0d", read_index, output_count);
    if (blocks_done != LC*51 || batches_done != 1)
      $fatal(1, "DUT 块/批计数错误：blocks=%0d expected=%0d batches=%0d",
             blocks_done, LC*51, batches_done);

    state_sum=0;
    for (i=0; i<16; i=i+1)
      state_sum=state_sum+state_cycles[i];
    delta=cycles_total-state_sum;
    if (measured_cycles!=cycles_total || delta!=0)
      $fatal(1, "逐状态计数不自洽：monitor=%0d total=%0d sum=%0d delta=%0d",
             measured_cycles, cycles_total, state_sum, delta);
    if (state_cycles[4]!=cycles_prefill || state_cycles[7]!=cycles_run ||
        state_cycles[8]+state_cycles[9]!=cycles_tree)
      $fatal(1, "逐状态分项与 DUT 计数器不符");

    $display("[STATE-SPLIT] config LC=%0d BATCH=64 P_WAYS=16 PIPE_TREE=1 STRIDE=807 REF_LEN=957 READ_BPS=150", LC);
    $display("[STATE-SPLIT] blocks_done=%0d batches_done=%0d cycles_total=%0d measured=%0d", blocks_done, batches_done, cycles_total, measured_cycles);
    $display("[STATE-SPLIT] state / hits / cycles / cycles_per_block");
    for (i=0; i<16; i=i+1) begin
      label=state_name(i);
      per_block=state_cycles[i];
      per_block=per_block/blocks_done;
      $display("[STATE-SPLIT] %-12s %8d %10d %12.4f", label, state_hits[i], state_cycles[i], per_block);
    end
    per_block=cycles_total;
    per_block=per_block/blocks_done;
    $display("[STATE-SPLIT] %-12s %8s %10d %12.4f", "TOTAL", "-", cycles_total, per_block);
    per_block=delta;
    per_block=per_block/blocks_done;
    $display("[STATE-SPLIT] %-12s %8s %10d %12.4f", "DELTA", "-", delta, per_block);
    $display("[STATE-SPLIT] prefill=%0d run=%0d tree=%0d PASS", cycles_prefill, cycles_run, cycles_tree);
    $finish;
  end

  initial begin
    #(LC == 50 ? 10000000 : 1000000);
    $display("[STATE-SPLIT] timeout st=%0d busy=%b done=%b req=%b valid=%b reads=%0d outputs=%0d blocks=%0d batches=%0d total=%0d",
             u_dut.st, busy, done, cw_req, cw_valid, read_index, output_count,
             blocks_done, batches_done, cycles_total);
    $fatal(1, "单批状态分解超时");
  end
endmodule
