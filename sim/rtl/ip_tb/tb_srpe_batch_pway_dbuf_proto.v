`timescale 1ns/1ps
`ifndef CFG_NUM_LC
`define CFG_NUM_LC 6
`endif
`ifndef CFG_BATCH
`define CFG_BATCH 4
`endif
`ifndef CFG_BATCHES
`define CFG_BATCHES 3
`endif

// 非生产双 bank 原型短冒烟：连续批次、满背压、逐条与单缓冲生产参考比较。
module tb_srpe_batch_pway_dbuf_proto;
  localparam integer LC = `CFG_NUM_LC;
  localparam integer NB = `CFG_BATCHES;
  localparam integer BR = `CFG_BATCH;
  localparam integer TOTAL = NB * BR;
  localparam integer RESULT_W = 326;

  reg clk = 0;
  always #5 clk = ~clk;
  reg rst_n = 0;
  reg proto_start = 0;
  reg ref_start = 0;
  reg we = 0;
  reg [5:0] sel = 0;
  reg [10:0] addr = 0;
  reg [1:0] data = 0;

  wire proto_req, proto_wr, proto_busy, proto_done;
  wire [299:0] proto_cw_data;
  reg proto_valid = 0;
  reg proto_full = 0;
  reg ref_full = 0;
  wire [325:0] proto_result;

  wire ref_req, ref_wr, ref_busy, ref_done;
  wire [299:0] ref_cw_data;
  reg ref_valid = 0;
  wire [325:0] ref_result;

  reg proto_fed = 0;
  reg ref_fed = 0;
  integer proto_feed = 0;
  integer ref_feed = 0;
  integer cyc = 0;
  integer p_count = 0;
  integer r_count = 0;
  integer p_start_cycle = -1;
  integer p_done_cycle = -1;
  reg p_done_seen = 0;
  integer ref_first_start = -1;
  integer ref_last_done = -1;
  integer ref_batch_start_cycle [0:NB-1];
  integer ref_batch_cycles [0:NB-1];
  integer p_batch_start_cycle [0:NB-1];
  integer p_batch_cycles [0:NB-1];
  integer run_cycles [0:NB-1];
  integer load_service [0:NB-1];
  integer emit_service [0:NB-1];
  integer hidden_load [0:NB-1];
  integer hidden_emit [0:NB-1];
  integer full_block_cycles = 0;
  integer ref_full_block_cycles = 0;
  reg [325:0] proto_captured [0:TOTAL-1];
  reg [325:0] ref_captured [0:TOTAL-1];
  integer batch_i, mon_batch, record_i, idx, lc_i, row_i;
  integer b, i;

  srpe_batch_pway_dbuf_proto #(
    .BATCH_COUNT(NB), .P_WAYS(16), .PIPE_TREE(1), .BATCH(BR),
    .NUM_LC(LC), .STRIDE(807), .REF_LEN(957), .READ_BPS(150)
  ) u_proto (
    .clk(clk), .rst_n(rst_n), .start_batch(proto_start), .clear_counters(proto_start),
    .cw_req(proto_req), .cw_valid(proto_valid), .cw_data(proto_cw_data),
    .bram_write_en(we), .bram_sel(sel), .bram_write_addr(addr), .bram_write_data(data),
    .res_wr(proto_wr), .res_din(proto_result), .res_full(proto_full),
    .busy(proto_busy), .done(proto_done),
    .cycles_total(), .cycles_prefill(), .cycles_run(), .cycles_tree(),
    .blocks_done(), .batches_done()
  );

  srpe_batch_pway #(
    .P_WAYS(16), .PIPE_TREE(1), .BATCH(BR),
    .NUM_LC(LC), .STRIDE(807), .REF_LEN(957), .READ_BPS(150)
  ) u_ref (
    .clk(clk), .rst_n(rst_n), .start_batch(ref_start), .clear_counters(ref_start),
    .cw_req(ref_req), .cw_valid(ref_valid), .cw_data(ref_cw_data),
    .bram_write_en(we), .bram_sel(sel), .bram_write_addr(addr), .bram_write_data(data),
    .res_wr(ref_wr), .res_din(ref_result), .res_full(ref_full),
    .busy(ref_busy), .done(ref_done),
    .cycles_total(), .cycles_prefill(), .cycles_run(), .cycles_tree(),
    .blocks_done(), .batches_done()
  );

  function [299:0] make_cw;
    input integer sequence_no;
    integer q;
    integer v;
    begin
      make_cw = 300'd0;
      for (q=0; q<150; q=q+1) begin
        v = (sequence_no * 7 + q * 3 + (q / 11) + (sequence_no / 3)) % 4;
        make_cw[q] = v[0];
        make_cw[150+q] = v[1];
      end
    end
  endfunction

  function [1:0] make_wm;
    input integer region_no;
    input integer offset;
    begin
      make_wm = (region_no * 13 + offset * 7 + (offset / 5)) % 4;
    end
  endfunction

  assign proto_cw_data = make_cw(proto_feed);
  assign ref_cw_data = make_cw(ref_feed);

  // 两个输入源按各自 req 喂同一序列；valid 只打一拍。
  always @(posedge clk) begin
    if (!rst_n) begin
      proto_valid <= 0;
      ref_valid <= 0;
      proto_fed <= 0;
      ref_fed <= 0;
      proto_feed <= 0;
      ref_feed <= 0;
    end else begin
      proto_valid <= 0;
      ref_valid <= 0;
      if (!proto_req) proto_fed <= 0;
      else if (!proto_fed && proto_feed < TOTAL) begin
        proto_valid <= 1;
        proto_fed <= 1;
        proto_feed <= proto_feed + 1;
      end
      if (!ref_req) ref_fed <= 0;
      else if (!ref_fed && ref_feed < TOTAL) begin
        ref_valid <= 1;
        ref_fed <= 1;
        ref_feed <= ref_feed + 1;
      end
    end
  end

  // 两个 DUT 使用相同周期图样注入满背压。参考核没有 S_EMIT_FINAL 等待，
  // 因此在它进入 S_EMIT_FINAL 时强制 full=0，避免把参考核的已知接口时序假设当作 DUT 错误。
  always @(negedge clk) begin
    if (!rst_n) begin
      proto_full <= 0;
      ref_full <= 0;
    end else begin
      if (proto_wr) proto_full <= 0;
      else proto_full <= ((cyc % 101) < 19) || ((cyc % 389) >= 201 && (cyc % 389) < 239);
      if (ref_wr || u_ref.st == u_ref.S_EMIT_FINAL) ref_full <= 0;
      else ref_full <= ((cyc % 101) < 19) || ((cyc % 389) >= 201 && (cyc % 389) < 239);
    end
  end

  // 统计真实状态驻留拍。LD_LOAD_R 与 EM_ADDR/WAIT/CAPTURE 分别是 3 拍/位置服务；
  // 只把正在 S_RUN 时发生的服务算作隐藏周期，res_full 下的 EM_ADDR 等待不计工作量。
  always @(posedge clk) begin
    if (rst_n) begin
      cyc = cyc + 1;
      if (u_proto.load_start) begin
        mon_batch = u_proto.load_batch;
        if (mon_batch < NB) p_batch_start_cycle[mon_batch] = cyc;
        if (mon_batch == 0 && p_start_cycle < 0) p_start_cycle = cyc;
      end
      if (u_proto.st == u_proto.S_RUN) begin
        mon_batch = u_proto.bank_batch[u_proto.scan_bank];
        if (mon_batch < NB) begin
          run_cycles[mon_batch] = run_cycles[mon_batch] + 1;
          if (u_proto.ld_state == u_proto.LD_LOAD_R) begin
            hidden_load[mon_batch] = hidden_load[mon_batch] + 1;
          end
          if ((u_proto.em_state == u_proto.EM_ADDR && !proto_full) ||
              u_proto.em_state == u_proto.EM_WAIT ||
              u_proto.em_state == u_proto.EM_CAPTURE) begin
            hidden_emit[mon_batch] = hidden_emit[mon_batch] + 1;
          end
        end
      end
      if (u_proto.ld_state == u_proto.LD_LOAD_R) begin
        mon_batch = u_proto.load_batch;
        if (mon_batch < NB) load_service[mon_batch] = load_service[mon_batch] + 1;
      end
      if ((u_proto.em_state == u_proto.EM_ADDR && !proto_full) ||
          u_proto.em_state == u_proto.EM_WAIT ||
          u_proto.em_state == u_proto.EM_CAPTURE) begin
        mon_batch = u_proto.bank_batch[u_proto.emit_bank];
        if (mon_batch < NB) emit_service[mon_batch] = emit_service[mon_batch] + 1;
      end
      if (proto_full &&
          (u_proto.em_state == u_proto.EM_ADDR || u_proto.em_state == u_proto.EM_FINAL))
        full_block_cycles = full_block_cycles + 1;
      if (ref_full && u_ref.st == u_ref.S_EMIT)
        ref_full_block_cycles = ref_full_block_cycles + 1;

      if (proto_wr) begin
        if (proto_full) $fatal(1, "原型 res_wr 在 res_full=1 时仍写入");
        if (p_count >= TOTAL) $fatal(1, "原型结果超出总记录数");
        proto_captured[p_count] = proto_result;
        p_count = p_count + 1;
      end
      if (ref_wr) begin
        if (ref_full) $fatal(1, "参考 res_wr 在 res_full=1 时仍写入");
        if (r_count >= TOTAL) $fatal(1, "参考结果超出总记录数");
        ref_captured[r_count] = ref_result;
        r_count = r_count + 1;
      end
      if (u_proto.emit_done) begin
        mon_batch = u_proto.bank_batch[u_proto.emit_bank];
        if (mon_batch < NB) p_batch_cycles[mon_batch] = cyc - p_batch_start_cycle[mon_batch];
      end
      if (proto_done) begin
        p_done_seen = 1'b1;
        if (p_done_cycle < 0) p_done_cycle = cyc;
      end
      if (ref_done) ref_last_done = cyc;
    end
  end

  initial begin
    for (i=0; i<NB; i=i+1) begin
      p_batch_start_cycle[i] = -1;
      p_batch_cycles[i] = 0;
      ref_batch_start_cycle[i] = -1;
      ref_batch_cycles[i] = 0;
      run_cycles[i] = 0;
      load_service[i] = 0;
      emit_service[i] = 0;
      hidden_load[i] = 0;
      hidden_emit[i] = 0;
    end
    repeat (5) @(negedge clk);
    rst_n = 1;

    // 两个 DUT 的 watermark BRAM 接收完全相同的预载数据。
    for (lc_i=0; lc_i<LC; lc_i=lc_i+1) begin
      for (row_i=0; row_i<957; row_i=row_i+1) begin
        @(negedge clk);
        we = 1;
        sel = lc_i;
        addr = row_i;
        data = make_wm(lc_i, row_i);
      end
    end
    @(negedge clk);
    we = 0;
    repeat (4) @(negedge clk);

    $display("[TB] LC=%0d BATCH=%0d BATCHES=%0d watermark preload complete", LC, BR, NB);
    proto_start = 1;
    @(negedge clk);
    proto_start = 0;
    for (batch_i=0; batch_i<NB; batch_i=batch_i+1) begin
      @(negedge clk);
      ref_start = 1;
      ref_batch_start_cycle[batch_i] = cyc;
      if (batch_i == 0) ref_first_start = cyc;
      @(negedge clk);
      ref_start = 0;
      wait (ref_done === 1'b1);
      ref_batch_cycles[batch_i] = cyc - ref_batch_start_cycle[batch_i];
      @(negedge clk);
    end

    wait (p_done_seen === 1'b1);
    repeat (3) @(negedge clk);

    if (p_count != TOTAL || r_count != TOTAL)
      $fatal(1, "结果条数不符：原型=%0d 参考=%0d 期望=%0d", p_count, r_count, TOTAL);
    if (proto_feed != TOTAL || ref_feed != TOTAL)
      $fatal(1, "输入条数不符：原型=%0d 参考=%0d 期望=%0d", proto_feed, ref_feed, TOTAL);

    for (idx=0; idx<TOTAL; idx=idx+1) begin
      if (proto_captured[idx] !== ref_captured[idx])
        $fatal(1, "逐条结果不一致 idx=%0d proto=%h ref=%h", idx, proto_captured[idx], ref_captured[idx]);
      batch_i = idx / BR;
      record_i = idx % BR;
      $display("[CMP] batch=%0d record=%0d cw=%h pos=%0d score=%0d PASS",
               batch_i, record_i, proto_captured[idx][325:26],
               proto_captured[idx][25:10], proto_captured[idx][9:0]);
    end

    for (b=0; b<NB; b=b+1) begin
      $display("[PROTO BATCH] batch=%0d total_from_load_to_emit=%0d run=%0d load_service=%0d emit_service=%0d hidden_load_in_run=%0d hidden_emit_in_run=%0d",
               b, p_batch_cycles[b], run_cycles[b], load_service[b], emit_service[b],
               hidden_load[b], hidden_emit[b]);
      $display("[REFERENCE BATCH] batch=%0d total=%0d", b, ref_batch_cycles[b]);
    end
    $display("[PROTO SUMMARY] LC=%0d BATCH=%0d BATCHES=%0d total=%0d single_buffer_total=%0d proto_full_blocks=%0d ref_full_blocks=%0d",
             LC, BR, NB, p_done_cycle-p_start_cycle, ref_last_done-ref_first_start, full_block_cycles, ref_full_block_cycles);
    $display("[PROTO SUMMARY] PASS: %0d records bit-exact cw/pos/score; %0d consecutive batches; res_full backpressure observed",
             TOTAL, NB);
    $finish;
  end

  initial begin
    #100000000;
    $fatal(1, "双缓冲原型 TB 超时: proto_busy=%b proto_st=%0d ld=%0d em=%0d ref_busy=%b ref_st=%0d",
           proto_busy, u_proto.st, u_proto.ld_state, u_proto.em_state, ref_busy, u_ref.st);
  end
endmodule
