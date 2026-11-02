`timescale 1ns / 1ps

//=========================================================================
// DNA加速器快速测试Testbench
// 特点：测试数据在内部生成，无需外部文件，适合快速验证
//=========================================================================

module tb_dna_quick;

    // ========== 参数 ==========
    parameter CLK_PERIOD = 10;      // 10ns = 100MHz
    parameter READ_BPS   = 150;     // 每条读取150bp
    parameter CODEBITS   = 300;     // 300位编码
    parameter BATCH      = 64;      // 批大小
    
    // 简化测试：只测试16条数据（可以改为64）
    parameter TEST_READS = 16;
    
    // ========== 时钟和复位 ==========
    reg clk;
    reg rst_n;
    
    // ========== 控制信号（简化） ==========
    reg start;
    reg preload;
    
    // ========== AXI-Lite接口（真正驱动 AWVALID/WVALID —— 修订 A9） ==========
    // 原实现把 AWVALID/WVALID 恒置 0，控制寄存器（start/preload）从未被
    // 真正写入，「测试1/测试3」实际什么都没做。现改为标准写任务驱动。
    reg  [3:0]  s_axi_lite_awaddr;
    wire [2:0]  s_axi_lite_awprot;
    reg         s_axi_lite_awvalid;
    wire        s_axi_lite_awready;
    reg  [31:0] s_axi_lite_wdata;
    wire [3:0]  s_axi_lite_wstrb;
    reg         s_axi_lite_wvalid;
    wire        s_axi_lite_wready;
    wire [1:0]  s_axi_lite_bresp;
    wire        s_axi_lite_bvalid;
    wire        s_axi_lite_bready;
    wire [3:0]  s_axi_lite_araddr;
    wire [2:0]  s_axi_lite_arprot;
    wire        s_axi_lite_arvalid;
    wire        s_axi_lite_arready;
    wire [31:0] s_axi_lite_rdata;
    wire [1:0]  s_axi_lite_rresp;
    wire        s_axi_lite_rvalid;
    wire        s_axi_lite_rready;

    assign s_axi_lite_awprot  = 3'b000;
    assign s_axi_lite_wstrb   = 4'hF;
    assign s_axi_lite_bready  = 1'b1;
    assign s_axi_lite_araddr  = 4'h0;
    assign s_axi_lite_arprot  = 3'b000;
    assign s_axi_lite_arvalid = 1'b0;
    assign s_axi_lite_rready  = 1'b1;

    // 标准AXI-Lite写（与 tb_desparsifier 的 BFM 同一模式）
    task axil_write(input [3:0] addr, input [31:0] data);
        begin
            @(posedge clk);
            s_axi_lite_awaddr  <= addr;
            s_axi_lite_wdata   <= data;
            s_axi_lite_awvalid <= 1'b1;
            s_axi_lite_wvalid  <= 1'b1;
            wait (s_axi_lite_awready && s_axi_lite_wready);
            @(posedge clk);
            s_axi_lite_awvalid <= 1'b0;
            s_axi_lite_wvalid  <= 1'b0;
            wait (s_axi_lite_bvalid);
            @(posedge clk);
        end
    endtask
    
    // ========== AXIS输入接口 ==========
    wire        s_axis_tready;
    reg  [31:0] s_axis_tdata;
    reg  [3:0]  s_axis_tstrb;
    reg         s_axis_tlast;
    reg         s_axis_tvalid;
    
    // ========== AXIS输出接口 ==========
    wire        m_axis_tvalid;
    wire [63:0] m_axis_tdata;
    wire [7:0]  m_axis_tstrb;
    wire        m_axis_tlast;
    reg         m_axis_tready;
    
    // ========== 测试变量 ==========
    integer send_count;     // 已发送的读取数量
    integer recv_count;     // 已接收的结果数量
    integer word_count;     // 当前发送的字计数
    reg [CODEBITS-1:0] current_read;
    
    // ========== 实例化DUT ==========
    dna_accelerator_core_v1_0 #(
        .C_S_AXI_LITE_CTRL_DATA_WIDTH(32),
        .C_S_AXI_LITE_CTRL_ADDR_WIDTH(4),
        .C_S_AXIS_DATA_TDATA_WIDTH(32),
        .C_M_AXIS_RESULT_TDATA_WIDTH(64),
        .READ_BPS(READ_BPS),
        .CODEBITS(CODEBITS),
        .BATCH(BATCH)
    ) dut (
        .s_axi_lite_ctrl_aclk(clk),
        .s_axi_lite_ctrl_aresetn(rst_n),
        .s_axi_lite_ctrl_awaddr(s_axi_lite_awaddr),
        .s_axi_lite_ctrl_awprot(s_axi_lite_awprot),
        .s_axi_lite_ctrl_awvalid(s_axi_lite_awvalid),
        .s_axi_lite_ctrl_awready(s_axi_lite_awready),
        .s_axi_lite_ctrl_wdata(s_axi_lite_wdata),
        .s_axi_lite_ctrl_wstrb(s_axi_lite_wstrb),
        .s_axi_lite_ctrl_wvalid(s_axi_lite_wvalid),
        .s_axi_lite_ctrl_wready(s_axi_lite_wready),
        .s_axi_lite_ctrl_bresp(s_axi_lite_bresp),
        .s_axi_lite_ctrl_bvalid(s_axi_lite_bvalid),
        .s_axi_lite_ctrl_bready(s_axi_lite_bready),
        .s_axi_lite_ctrl_araddr(s_axi_lite_araddr),
        .s_axi_lite_ctrl_arprot(s_axi_lite_arprot),
        .s_axi_lite_ctrl_arvalid(s_axi_lite_arvalid),
        .s_axi_lite_ctrl_arready(s_axi_lite_arready),
        .s_axi_lite_ctrl_rdata(s_axi_lite_rdata),
        .s_axi_lite_ctrl_rresp(s_axi_lite_rresp),
        .s_axi_lite_ctrl_rvalid(s_axi_lite_rvalid),
        .s_axi_lite_ctrl_rready(s_axi_lite_rready),
        
        .S_AXIS_DATA_ACLK(clk),
        .S_AXIS_DATA_ARESETN(rst_n),
        .S_AXIS_DATA_TREADY(s_axis_tready),
        .S_AXIS_DATA_TDATA(s_axis_tdata),
        .S_AXIS_DATA_TSTRB(s_axis_tstrb),
        .S_AXIS_DATA_TLAST(s_axis_tlast),
        .S_AXIS_DATA_TVALID(s_axis_tvalid),
        
        .M_AXIS_RESULT_ACLK(clk),
        .M_AXIS_RESULT_ARESETN(rst_n),
        .M_AXIS_RESULT_TVALID(m_axis_tvalid),
        .M_AXIS_RESULT_TDATA(m_axis_tdata),
        .M_AXIS_RESULT_TSTRB(m_axis_tstrb),
        .M_AXIS_RESULT_TLAST(m_axis_tlast),
        .M_AXIS_RESULT_TREADY(m_axis_tready)
    );
    
    // ========== 时钟生成 ==========
    initial begin
        clk = 0;
        forever #(CLK_PERIOD/2) clk = ~clk;
    end
    
    // ========== 测试数据生成函数 ==========
    function [CODEBITS-1:0] generate_test_data;
        input integer seed;
        integer i;
        reg [1:0] base;
        begin
            generate_test_data = {CODEBITS{1'b0}};
            // 生成简单的测试模式
            for (i = 0; i < READ_BPS; i = i + 1) begin
                base = (seed + i) % 4;  // 循环生成A,C,G,T
                generate_test_data[i*2 +: 2] = base;
            end
        end
    endfunction
    
    // ========== 主测试流程 ==========
    initial begin
        // 初始化
        rst_n = 0;
        start = 0;
        preload = 0;
        s_axi_lite_awvalid = 0;
        s_axi_lite_wvalid = 0;
        s_axi_lite_awaddr = 0;
        s_axi_lite_wdata = 0;
        s_axis_tdata = 0;
        s_axis_tstrb = 4'hF;
        s_axis_tlast = 0;
        s_axis_tvalid = 0;
        m_axis_tready = 1;  // 始终准备好接收
        send_count = 0;
        recv_count = 0;
        word_count = 0;
        
        $display("\n========================================");
        $display("  DNA加速器快速测试");
        $display("  测试配置:");
        $display("    - 时钟频率: %0d MHz", 1000/CLK_PERIOD);
        $display("    - 测试数据: %0d 条读取", TEST_READS);
        $display("    - 每条长度: %0d bp", READ_BPS);
        $display("========================================\n");
        
        // 复位
        #(CLK_PERIOD * 20);
        rst_n = 1;
        $display("[%0t] 复位完成", $time);
        #(CLK_PERIOD * 10);
        
        // ==================================================
        // 测试1: 预加载参考序列（简化版）
        // ==================================================
        $display("\n[%0t] ===== 测试1: 预加载参考序列 =====", $time);
        preload = 1;
        axil_write(4'h0, 32'h0002);  // 【修订 A9】真正写入 preload=1
        
        #(CLK_PERIOD * 10);
        
        // 发送一些参考数据（简化，只发送少量）
        repeat (50) begin
            @(posedge clk);
            s_axis_tvalid = 1;
            s_axis_tdata = $random;
            @(posedge clk);
            s_axis_tvalid = 0;
            #(CLK_PERIOD * 2);
        end
        
        preload = 0;
        axil_write(4'h0, 32'h0000);
        $display("[%0t] 预加载完成", $time);
        
        #(CLK_PERIOD * 50);
        
        // ==================================================
        // 测试2: 发送DNA读取数据
        // ==================================================
        $display("\n[%0t] ===== 测试2: 发送DNA读取数据 =====", $time);
        
        // 启动后台发送进程（【修订 A9】fork/join_none 是 SystemVerilog
        // 语法，-g2005 编译不过；改为独立 initial + 使能标志）
        sender_go = 1;

        
        // 等待数据发送
        #(CLK_PERIOD * 100);
        
        // ==================================================
        // 测试3: 启动处理
        // ==================================================
        $display("\n[%0t] ===== 测试3: 启动比对处理 =====", $time);
        start = 1;
        axil_write(4'h0, 32'h0001);  // 【修订 A9】真正写入 start=1
        
        $display("[%0t] 等待处理结果...", $time);
        
        // 等待足够的时间让引擎处理
        #(CLK_PERIOD * 5000);
        
        start = 0;
        axil_write(4'h0, 32'h0000);
        
        // 再等一段时间确保所有结果输出
        #(CLK_PERIOD * 1000);
        
        // ==================================================
        // 测试总结
        // ==================================================
        $display("\n========================================");
        $display("  测试完成!");
        $display("========================================");
        $display("统计:");
        $display("  - 发送数据: %0d 条", send_count);
        $display("  - 接收结果: %0d 条", recv_count);
        
        if (recv_count == send_count) begin
            $display("\n✓ 测试通过：接收数量匹配发送数量");
        end else begin
            $display("\n✗ 警告：接收数量(%0d) != 发送数量(%0d)", recv_count, send_count);
        end
        
        $display("\n详细信息:");
        $display("  - 检查波形中的 eng_busy 信号确认引擎工作");
        $display("  - 检查 in_count 查看输入FIFO状态");
        $display("  - 查看 m_axis_tdata 中的输出数据");
        $display("========================================\n");
        
        #(CLK_PERIOD * 500);
        $display("仿真结束时间: %0t", $time);
        // 注意：在Vivado中不需要$finish，让脚本控制仿真时间
    end
    

    // ========== 后台发送进程（【修订 A9】替代 fork/join_none） ==========
    reg sender_go;

    initial begin : sender_proc
        sender_go = 0;
        wait (rst_n);
        while (!sender_go) @(posedge clk);
        while (send_count < TEST_READS) begin
            // 生成测试数据
            current_read = generate_test_data(send_count);

            // 发送10个32位字（共300位）
            for (word_count = 0; word_count < 10; word_count = word_count + 1) begin
                @(posedge clk);
                while (!s_axis_tready) @(posedge clk);  // 等待ready

                s_axis_tvalid = 1;
                s_axis_tstrb  = 4'hF;
                s_axis_tlast  = (word_count == 9);

                // 选择对应的32位数据
                case (word_count)
                    0: s_axis_tdata = current_read[31:0];
                    1: s_axis_tdata = current_read[63:32];
                    2: s_axis_tdata = current_read[95:64];
                    3: s_axis_tdata = current_read[127:96];
                    4: s_axis_tdata = current_read[159:128];
                    5: s_axis_tdata = current_read[191:160];
                    6: s_axis_tdata = current_read[223:192];
                    7: s_axis_tdata = current_read[255:224];
                    8: s_axis_tdata = current_read[287:256];
                    9: s_axis_tdata = {{20{1'b0}}, current_read[299:288]};
                endcase
            end

            @(posedge clk);
            s_axis_tvalid = 0;
            s_axis_tlast  = 0;

            send_count = send_count + 1;
            $display("[%0t] 已发送读取 #%0d/%0d", $time, send_count, TEST_READS);

            // 小延迟
            #(CLK_PERIOD * 5);
        end

        $display("\n[%0t] 所有数据发送完成 (共%0d条)", $time, send_count);
    end

    // ========== 输出结果监测 ==========
    always @(posedge clk) begin
        if (rst_n && m_axis_tvalid && m_axis_tready) begin
            recv_count = recv_count + 1;
            
            // 解析输出数据（假设格式：{code, pos, score}）
            // score在低10位，pos在中间16位
            $display("[%0t] 结果 #%0d: data=0x%016h, last=%b", 
                     $time, recv_count, m_axis_tdata, m_axis_tlast);
            
            // 可选：详细解析
            if (recv_count <= 5) begin  // 只显示前5个的详细信息
                $display("       └─ 分数=%0d, 位置=%0d", 
                         m_axis_tdata[9:0],      // score (10位)
                         m_axis_tdata[25:10]);   // position (16位)
            end
        end
    end
    
    // ========== 超时监测 ==========
    initial begin
        #(CLK_PERIOD * 20000);  // 200us超时
        if (recv_count < send_count) begin
            $display("\n[WARNING] 仿真超时!");
            $display("  发送: %0d, 接收: %0d", send_count, recv_count);
        end
    end
    
endmodule
