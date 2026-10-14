`timescale 1ns/1ps
`ifndef CFG_NUM_LC
`define CFG_NUM_LC 50
`endif
// 正式生产两个实现，逐位等价并对独立符号滑窗oracle校验，绝不读实验源。
// 本 TB 有意**不知道**每拍碱基数 K：K 不改变正确性（正确的 K=4 同样会过 oracle），
// 它只改变吞吐与资源。K 的取值由 RTL 内的 localparam 写死，并由证据目录里的
// 源码 SHA256 锁定；本 TB 不另立一个会漂移的 K 副本。
module tb_dna_stage1_p16_equivalence;
  localparam LC=`CFG_NUM_LC;
  reg clk=0,rst=0,start=0; always #5 clk=~clk;
  reg we=0; reg[5:0] sel=0; reg[10:0] addr=0;reg[1:0] data=0;
  wire[1:0] req,wr,busy,done;
  reg[1:0] valid=0,full=0,fed=0;
  reg[299:0] cw0=0,cw1=0;
  wire[325:0] result0,result1;
  reg[1:0] wm[0:LC*957-1];reg[299:0] reads[0:63];reg[325:0] expected[0:63];
  reg[325:0] captured0[0:63],captured1[0:63];
  integer n0=0,n1=0,f0=0,f1=0,cyc=0,c0=0,c1=0,lc,row,i,round;
  reg[8*1024-1:0] fixture_dir;
  srpe_batch #(.BATCH(64),.NUM_LC(LC),.STRIDE(807),.REF_LEN(957),.READ_BPS(150)) p4
   (.clk(clk),.rst_n(rst),.start_batch(start),.cw_req(req[0]),.cw_valid(valid[0]),.cw_data(cw0),
    .bram_write_en(we),.bram_sel(sel),.bram_write_addr(addr),.bram_write_data(data),
    .res_wr(wr[0]),.res_din(result0),.res_full(full[0]),.busy(busy[0]),.done(done[0]));
  srpe_batch_pway #(.P_WAYS(16),.PIPE_TREE(1),.BATCH(64),.NUM_LC(LC),.STRIDE(807),.REF_LEN(957),.READ_BPS(150)) p16
   (.clk(clk),.rst_n(rst),.start_batch(start),.cw_req(req[1]),.cw_valid(valid[1]),.cw_data(cw1),
    .bram_write_en(we),.bram_sel(sel),.bram_write_addr(addr),.bram_write_data(data),
    .res_wr(wr[1]),.res_din(result1),.res_full(full[1]),.busy(busy[1]),.done(done[1]));
  always @(posedge clk) begin
    if(!rst) begin valid<=0;fed<=0;f0<=0;f1<=0;end else begin
      valid<=0;
      if(!req[0]) fed[0]<=0;
      else if(!fed[0] && f0<64) begin cw0<=reads[f0];valid[0]<=1;fed[0]<=1;f0<=f0+1;end
      if(!req[1]) fed[1]<=0;
      else if(!fed[1] && f1<64) begin cw1<=reads[f1];valid[1]<=1;fed[1]<=1;f1<=f1+1;end
    end
    if(rst) begin
      cyc=cyc+1;
      if(wr[0]) begin
        if(full[0] || n0>=64) $fatal(1,"P4结果越界/满时仍写");
        captured0[n0]=result0;n0=n0+1;
      end
      if(wr[1]) begin
        if(full[1] || n1>=64) $fatal(1,"P16结果越界/满时仍写");
        captured1[n1]=result1;n1=n1+1;
      end
      if(done[0] && c0==0)c0=cyc;
      if(done[1] && c1==0)c1=cyc;
    end
  end
  // 独立结果满反馈：必须保持res_wr为0，不允许偷偷推进结果序号。
  // res_wr是寄存的FIFO写脉冲；人工满反馈不能截断已经承诺的在途写拍。
  // 真正AXIS随机背压在wrapper TB检查，这里只在没有在途写时施压。
  always @(negedge clk) full <= rst && !(|wr) && ((cyc%97)<19) ? 2'b11 : 2'b00;
  initial begin
    if(!$value$plusargs("fixture_dir=%s",fixture_dir))$fatal(1,"必须显式提供fixture_dir");
    $readmemh({fixture_dir,"/wm.hex"},wm);
    for(round=0;round<2;round=round+1)begin
      if(round==0)begin
        $readmemh({fixture_dir,"/reads.hex"},reads);$readmemh({fixture_dir,"/expect.hex"},expected);
      end else begin
        $readmemh({fixture_dir,"/repeat_reads.hex"},reads);$readmemh({fixture_dir,"/repeat_expect.hex"},expected);
      end
      @(negedge clk);rst=0;repeat(5)@(negedge clk);n0=0;n1=0;cyc=0;c0=0;c1=0;rst=1;
      for(lc=0;lc<LC;lc=lc+1)for(row=0;row<957;row=row+1)begin
        @(negedge clk);we=1;sel=lc;addr=row;data=round==0?wm[lc*957+row]:0;
      end
      @(negedge clk);we=0;repeat(5)@(negedge clk);cyc=0;start=1;
      @(negedge clk);start=0;
      wait(c0>0 && c1>0);repeat(5)@(negedge clk);
      if(n0!=64||n1!=64)$fatal(1,"条数不符");
      for(i=0;i<64;i=i+1)begin
        if(captured0[i]!==captured1[i]||captured1[i]!==expected[i])
          $fatal(1,"round=%0d record=%0d P4=%h P16=%h oracle=%h",round,i,captured0[i],captured1[i],expected[i]);
      end
      if(c1*100>=c0*60)$fatal(1,"P16未产生应有周期改善，可能选错生产路径：P4=%0d P16=%0d",c0,c1);
      $display("[PRODUCTION EQ] round=%0d LC=%0d P4=%0d P16=%0d PASS",round,LC,c0,c1);
    end
    $display("[PRODUCTION EQ] PASS 独立oracle、末组/807/补零/反向/并列零分/复位再任务");$finish;
  end
  initial begin #100000000;$fatal(1,"生产模块TB超时");end
endmodule
