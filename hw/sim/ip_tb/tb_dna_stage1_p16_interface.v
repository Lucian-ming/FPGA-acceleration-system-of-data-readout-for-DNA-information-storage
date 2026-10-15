`timescale 1ns/1ps
`ifndef CFG_NUM_LC
`define CFG_NUM_LC 50
`endif
// 真实生产wrapper双路径，全部读段和水印经过AXI输入，不force结果或预载内存。
module tb_dna_stage1_p16_interface;
  reg clk=0;always #5 clk=~clk;
  wire done4,done16;wire[31:0] cycles4,cycles16;
  stage1_interface_driver #(.WAYS(4),.TREE(0),.LC(`CFG_NUM_LC)) p4(clk,done4,cycles4);
  stage1_interface_driver #(.WAYS(16),.TREE(1),.LC(`CFG_NUM_LC)) p16(clk,done16,cycles16);
  initial begin
    wait(done4 && done16);
    if(cycles16*100 >= cycles4*60)$fatal(1,"wrapper P16选择/周期无改善，P4=%0d P16=%0d",cycles4,cycles16);
    $display("[PRODUCTION AXIS] PASS LC=%0d P4cycles=%0d P16cycles=%0d",`CFG_NUM_LC,cycles4,cycles16);$finish;
  end
  initial begin #120000000;$fatal(1,"真实wrapper测试超时");end
endmodule

module stage1_interface_driver #(parameter WAYS=16,TREE=1,LC=50)
  (input clk,output reg finished=0,output reg[31:0] compute_cycles=0);
  reg rst=0;
  reg[3:0] awaddr=0;reg awvalid=0;wire awready;
  reg[31:0] wdata=0;reg[3:0] wstrb=15;reg wvalid=0;wire wready;
  wire[1:0] bresp;wire bvalid;reg bready=0;
  reg[3:0] araddr=0;reg arvalid=0;wire arready;
  wire[31:0] rdata;wire[1:0] rresp;wire rvalid;reg rready=0;
  reg[31:0] sdata=0;reg svalid=0,slast=0;wire sready;
  wire[63:0] mdata;wire[7:0] mstrb;wire mvalid,mlast;reg mready=0;
  reg[1:0] wm[0:LC*957-1];reg[299:0] reads[0:63];reg[325:0] expected[0:63];
  reg[383:0] accum=0;
  reg stall_previous=0;reg[63:0] stall_data;reg stall_last;
  reg[31:0] prng=32'h0F12AB78;reg collect=0;
  integer word_n=0,record_n=0,lc,row,i,k,round,cycles=0,start_cycle,wait_n;
  reg[31:0] hw_cycles_total,hw_cycles_prefill,hw_cycles_run,hw_cycles_tree;
  reg[31:0] hw_blocks_done,hw_batches_done,hw_cycles_total_confirm;
  reg[8*1024-1:0] fixture_dir;
  Dna_accelerator_core_v1_0 #(.C_STAGE1_P_WAYS(WAYS),.C_STAGE1_PIPE_TREE(TREE),
    .READ_BPS(150),.NUM_LC(LC),.STRIDE(807),.REF_LEN(957),.BATCH(64)) dut
   (.s_axi_lite_ctrl_aclk(clk),.s_axi_lite_ctrl_aresetn(rst),
    .s_axi_lite_ctrl_awaddr(awaddr),.s_axi_lite_ctrl_awprot(3'd0),.s_axi_lite_ctrl_awvalid(awvalid),.s_axi_lite_ctrl_awready(awready),
    .s_axi_lite_ctrl_wdata(wdata),.s_axi_lite_ctrl_wstrb(wstrb),.s_axi_lite_ctrl_wvalid(wvalid),.s_axi_lite_ctrl_wready(wready),
    .s_axi_lite_ctrl_bresp(bresp),.s_axi_lite_ctrl_bvalid(bvalid),.s_axi_lite_ctrl_bready(bready),
    .s_axi_lite_ctrl_araddr(araddr),.s_axi_lite_ctrl_arprot(3'd0),.s_axi_lite_ctrl_arvalid(arvalid),.s_axi_lite_ctrl_arready(arready),
    .s_axi_lite_ctrl_rdata(rdata),.s_axi_lite_ctrl_rresp(rresp),.s_axi_lite_ctrl_rvalid(rvalid),.s_axi_lite_ctrl_rready(rready),
    .S_AXIS_DATA_ACLK(clk),.S_AXIS_DATA_ARESETN(rst),.S_AXIS_DATA_TDATA(sdata),.S_AXIS_DATA_TSTRB(4'hF),
    .S_AXIS_DATA_TLAST(slast),.S_AXIS_DATA_TVALID(svalid),.S_AXIS_DATA_TREADY(sready),
    .M_AXIS_RESULT_ACLK(clk),.M_AXIS_RESULT_ARESETN(rst),.M_AXIS_RESULT_TDATA(mdata),.M_AXIS_RESULT_TSTRB(mstrb),
    .M_AXIS_RESULT_TLAST(mlast),.M_AXIS_RESULT_TVALID(mvalid),.M_AXIS_RESULT_TREADY(mready));

  task axi_write;
    input[3:0] address;input[31:0] value;input[3:0] strobe;input integer mode;
    begin
      @(negedge clk);awaddr=address;wdata=value;wstrb=strobe;bready=0;
      // 两通道分别完成后才发送另一通道；两种次序都会红出互相等待缺陷。
      if(mode==0)begin
        awvalid=1;wait_n=0;
        @(posedge clk);while(!awready && wait_n<20)begin wait_n=wait_n+1;@(posedge clk);end
        if(!awready)$fatal(1,"P%0d AW等待W死锁",WAYS);
        @(negedge clk);awvalid=0;repeat(3)@(negedge clk);wvalid=1;
        @(posedge clk);wait_n=0;while(!wready && wait_n<20)begin wait_n=wait_n+1;@(posedge clk);end
        if(!wready)$fatal(1,"P%0d W握手失败",WAYS);
        @(negedge clk);wvalid=0;
      end else begin
        wvalid=1;wait_n=0;
        @(posedge clk);while(!wready && wait_n<20)begin wait_n=wait_n+1;@(posedge clk);end
        if(!wready)$fatal(1,"P%0d W等待AW死锁",WAYS);
        @(negedge clk);wvalid=0;repeat(3)@(negedge clk);awvalid=1;
        @(posedge clk);wait_n=0;while(!awready && wait_n<20)begin wait_n=wait_n+1;@(posedge clk);end
        if(!awready)$fatal(1,"P%0d AW握手失败",WAYS);
        @(negedge clk);awvalid=0;
      end
      wait_n=0;@(posedge clk);while(!bvalid && wait_n<20)begin wait_n=wait_n+1;@(posedge clk);end
      if(!bvalid||bresp!==0)$fatal(1,"AXIL响应错误");
      repeat(3)@(posedge clk);if(!bvalid)$fatal(1,"BVALID未在背压时保持");
      @(negedge clk);bready=1;@(negedge clk);bready=0;
    end
  endtask

  task axi_read;
    input[3:0] address;output[31:0] value;
    begin
      @(negedge clk);araddr=address;arvalid=1;rready=0;wait_n=0;
      @(posedge clk);while(!arready && wait_n<20)begin wait_n=wait_n+1;@(posedge clk);end
      if(!arready)$fatal(1,"AXIL AR等待超时");
      @(negedge clk);arvalid=0;
      wait_n=0;@(posedge clk);while(!rvalid && wait_n<20)begin wait_n=wait_n+1;@(posedge clk);end
      if(!rvalid||rresp!==0)$fatal(1,"AXIL读响应错误");
      value=rdata;
      @(negedge clk);rready=1;@(negedge clk);rready=0;
    end
  endtask

  task read_stage1_counter;
    input[31:0] index;output[31:0] value;
    begin
      axi_write(4'h8,index,4'hf,index[0]);
      axi_read(4'hc,value);
    end
  endtask

  task stream_word;
    input[31:0] value;input last;
    begin
      @(negedge clk);sdata=value;slast=last;svalid=1;
      @(posedge clk);while(!sready)@(posedge clk);
      @(negedge clk);svalid=0;slast=0;
    end
  endtask

  always @(negedge clk) begin
    if(!rst || !collect)mready=0;
    else begin
      prng={prng[30:0],prng[31]^prng[21]^prng[1]^prng[0]};
      // 确定性伪随机背压，且每2048拍有128拍连续停顿。
      mready=(prng[1:0]!=0) && (cycles%2048>=128);
    end
  end
  always @(posedge clk)begin
    cycles=cycles+1;
    if(!rst || !collect)stall_previous=0;
    else begin
      if(stall_previous && (!mvalid || mdata!==stall_data || mlast!==stall_last))
        $fatal(1,"P%0d AXIS背压期间VALID/DATA/TLAST变化",WAYS);
      stall_previous=mvalid && !mready;stall_data=mdata;stall_last=mlast;
      if(mvalid && mready)begin
        if(record_n>=64)$fatal(1,"P%0d多输出记录",WAYS);
        if(mstrb!==8'hFF||mlast!==(word_n==5))$fatal(1,"P%0d TSTRB/TLAST/拍数错误 record=%0d word=%0d",WAYS,record_n,word_n);
        accum[word_n*64+:64]=mdata;
        if(word_n==5)begin
          if(accum!=={58'd0,expected[record_n]})$fatal(1,"P%0d round=%0d record=%0d output=%h oracle=%h",WAYS,round,record_n,accum,expected[record_n]);
          record_n=record_n+1;word_n=0;accum=0;
        end else word_n=word_n+1;
      end
    end
  end

  initial begin
    if(!$value$plusargs("fixture_dir=%s",fixture_dir))$fatal(1,"必须显式fixture_dir");
    if(dut.C_STAGE1_P_WAYS!=WAYS||dut.C_STAGE1_PIPE_TREE!=TREE||dut.NUM_LC!=LC||dut.READ_BPS!=150||dut.STRIDE!=807||dut.REF_LEN!=957||dut.BATCH!=64)
      $fatal(1,"wrapper生产参数错误");
    $readmemh({fixture_dir,"/wm.hex"},wm);
    repeat(5)@(negedge clk);rst=1;repeat(5)@(negedge clk);
    // 独立入口流控压力；force仅隔离消费者，之后硬复位，真实计算不force任何数据。
    force dut.eng_busy=1'b1;
    for(i=0;i<256;i=i+1)for(k=0;k<10;k=k+1)stream_word((i<<8)|k,k==9);
    repeat(5)@(negedge clk);
    if(sready!==0||dut.in_count!==256||dut.u_in_fifo.count!==256)$fatal(1,"P%0d FIFO满未背压或组装计数错误",WAYS);
    svalid=1;sdata=32'hbad0cafe;repeat(8)@(negedge clk);
    if(sready!==0||dut.in_count!==256)$fatal(1,"FIFO满后仍接受数据");
    svalid=0;release dut.eng_busy;rst=0;repeat(5)@(negedge clk);rst=1;
    for(round=0;round<2;round=round+1)begin
      if(round==0)begin
        $readmemh({fixture_dir,"/reads.hex"},reads);$readmemh({fixture_dir,"/expect.hex"},expected);
      end else begin
        // 第二次任务用固件软复位并改水印，测真实残留清理；不重例化DUT。
        collect=0;axi_write(0,4,15,1);repeat(8)@(negedge clk);axi_write(0,0,15,0);repeat(8)@(negedge clk);
        $readmemh({fixture_dir,"/repeat_reads.hex"},reads);$readmemh({fixture_dir,"/repeat_expect.hex"},expected);
      end
      if(!dut.in_empty||dut.in_count!=0)$fatal(1,"P%0d复位后FIFO非空",WAYS);
      for(lc=0;lc<LC;lc=lc+1)begin
        axi_write(4,lc,15,lc%2);axi_write(0,2,15,1);repeat(8)@(negedge clk);
        for(row=0;row<957;row=row+1)stream_word(round==0?wm[lc*957+row]:0,row==956);
        repeat(4)@(negedge clk);
      end
      axi_write(0,0,15,0);repeat(8)@(negedge clk);
      // byte mask不能误触发START。
      axi_write(0,32'hffffffff,4'b1000,1);
      if(dut.reg0[7:0]!==0)$fatal(1,"WSTRB错误");
      for(i=0;i<64;i=i+1)for(k=0;k<10;k=k+1)
        stream_word(k==9 ? {20'habcde,reads[i][299:288]} : (reads[i]>>(k*32)),k==9);
      axi_write(0,0,15,0);repeat(12)@(negedge clk);
      if(dut.eng_busy||mvalid)$fatal(1,"START=0触发任务");
      record_n=0;word_n=0;accum=0;collect=1;start_cycle=cycles;
      axi_write(0,1,15,1);repeat(10000)@(negedge clk);axi_write(0,0,15,0);
      wait(record_n==64);repeat(8)@(negedge clk);
      if(round==0)compute_cycles=cycles-start_cycle;
      if(mvalid||dut.in_count!=0||!dut.in_empty)$fatal(1,"任务结束记录残留/多输出");
      if(WAYS==16)begin
        read_stage1_counter(0,hw_cycles_total);
        read_stage1_counter(1,hw_cycles_prefill);
        read_stage1_counter(2,hw_cycles_run);
        read_stage1_counter(3,hw_cycles_tree);
        read_stage1_counter(4,hw_blocks_done);
        read_stage1_counter(5,hw_batches_done);
        if(hw_blocks_done!==LC*((807+16)/16)||hw_batches_done!==1)
          $fatal(1,"Stage1计数器块/批错误：blocks=%0d expect=%0d batches=%0d",
                 hw_blocks_done,LC*((807+16)/16),hw_batches_done);
        if(hw_cycles_total < hw_cycles_prefill+hw_cycles_run+hw_cycles_tree)
          $fatal(1,"Stage1 total 小于三个阶段之和");
        if(hw_cycles_prefill==0||hw_cycles_run==0||hw_cycles_tree==0)
          $fatal(1,"Stage1阶段计数器未递增");
        axi_write(4'hc,32'hdeadbeef,4'hf,1);
        read_stage1_counter(0,hw_cycles_total_confirm);
        if(hw_cycles_total_confirm!==hw_cycles_total)
          $fatal(1,"写 0x0C 改变了只读计数值");
        repeat(16)@(negedge clk);
        read_stage1_counter(0,hw_cycles_total_confirm);
        if(hw_cycles_total_confirm!==hw_cycles_total)
          $fatal(1,"Stage1 done 后 cycles_total 仍在增长");
        $display("[STAGE1 CYCLES] round=%0d total=%0d prefill=%0d run=%0d tree=%0d blocks=%0d batches=%0d PASS",
                 round,hw_cycles_total,hw_cycles_prefill,hw_cycles_run,hw_cycles_tree,
                 hw_blocks_done,hw_batches_done);
      end
      $display("[PRODUCTION AXIS] P%0d round=%0d LC=%0d PASS records=%0d",WAYS,round,LC,record_n);
    end
    collect=0;finished=1;
  end
endmodule
