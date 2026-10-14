`timescale 1ns/1ps

// AXI4-Lite 控制器：按客户端 LSB-first 位序将结果缓冲装入/读回 LDPC 核。
module ldpc_decoder_v1_0 #(
    parameter integer C_S00_AXI_DATA_WIDTH = 32,
    parameter integer C_S00_AXI_ADDR_WIDTH = 6,
    parameter BT_ROM_FILE = "hw/ip/ldpc_decoder_1_0/data/bt_col_by_res.hex",
    parameter BT_OFF_FILE = "hw/ip/ldpc_decoder_1_0/data/bt_res_off.hex"
) (
    input  wire                                  S00_AXI_ACLK,
    input  wire                                  S00_AXI_ARESETN,
    input  wire [C_S00_AXI_ADDR_WIDTH-1:0]       S00_AXI_AWADDR,
    input  wire                                  S00_AXI_AWVALID,
    output wire                                  S00_AXI_AWREADY,
    input  wire [C_S00_AXI_DATA_WIDTH-1:0]       S00_AXI_WDATA,
    input  wire [C_S00_AXI_DATA_WIDTH/8-1:0]     S00_AXI_WSTRB,
    input  wire                                  S00_AXI_WVALID,
    output wire                                  S00_AXI_WREADY,
    output reg  [1:0]                            S00_AXI_BRESP,
    output reg                                   S00_AXI_BVALID,
    input  wire                                  S00_AXI_BREADY,
    input  wire [C_S00_AXI_ADDR_WIDTH-1:0]       S00_AXI_ARADDR,
    input  wire                                  S00_AXI_ARVALID,
    output wire                                  S00_AXI_ARREADY,
    output reg  [C_S00_AXI_DATA_WIDTH-1:0]       S00_AXI_RDATA,
    output reg  [1:0]                            S00_AXI_RRESP,
    output reg                                   S00_AXI_RVALID,
    input  wire                                  S00_AXI_RREADY
);
    // AXI4-Lite 寄存器：00 控制，04 状态，08 装载字地址，0c 装载字数据，
    // 10 结果字地址，14 结果字数据。地址寄存器单位为 32 位字，合法范围 0..2024。
    // 每个数据字按 bit0→bit31 展开/拼回，对应客户端每字节 LSB-first 的码流顺序。
    localparam [5:0] REG_CONTROL          = 6'h00;
    localparam [5:0] REG_STATUS           = 6'h04;
    localparam [5:0] REG_LOAD_WORD_ADDR   = 6'h08;
    localparam [5:0] REG_LOAD_WORD_DATA   = 6'h0c;
    localparam [5:0] REG_RESULT_WORD_ADDR = 6'h10;
    localparam [5:0] REG_RESULT_WORD_DATA = 6'h14;
    localparam [31:0] LAST_WORD_ADDR      = 32'd2024;

    reg aw_pending;
    reg [C_S00_AXI_ADDR_WIDTH-1:0] awaddr_hold;
    reg w_pending;
    reg [C_S00_AXI_DATA_WIDTH-1:0] wdata_hold;
    reg [C_S00_AXI_DATA_WIDTH/8-1:0] wstrb_hold;

    reg [31:0] load_word_addr_q;
    reg [31:0] load_word_data_q;
    reg [31:0] result_word_addr_q;
    reg [16:0] load_base_q;
    reg [4:0] load_bit_index;
    reg loader_active;
    reg load_response_pending;

    reg [16:0] result_base_q;
    reg [5:0] read_issue_index;
    reg [4:0] read_capture_index;
    reg [31:0] result_word_buffer;
    reg reader_active;
    reg read_capture_valid;

    reg start_pulse;
    reg core_reset_pulse;
    reg done_sticky;

    wire core_rst = !S00_AXI_ARESETN || core_reset_pulse;
    wire core_busy;
    wire core_done;
    wire core_converged;
    wire core_error;
    wire signed [7:0] core_iter_count;
    wire core_result_bit;
    wire core_load_we = loader_active;
    wire [16:0] core_load_addr = load_base_q + {12'd0, load_bit_index};
    wire core_load_bit = load_word_data_q[load_bit_index];
    wire [16:0] core_result_addr;

    wire aw_take = S00_AXI_AWVALID && S00_AXI_AWREADY;
    wire w_take = S00_AXI_WVALID && S00_AXI_WREADY;
    wire have_aw = aw_pending || aw_take;
    wire have_w = w_pending || w_take;
    wire write_pair = have_aw && have_w && !S00_AXI_BVALID &&
                      !loader_active && !reader_active;
    wire [C_S00_AXI_ADDR_WIDTH-1:0] write_addr = aw_pending ? awaddr_hold : S00_AXI_AWADDR;
    wire [C_S00_AXI_DATA_WIDTH-1:0] write_data = w_pending ? wdata_hold : S00_AXI_WDATA;
    wire [C_S00_AXI_DATA_WIDTH/8-1:0] write_strb = w_pending ? wstrb_hold : S00_AXI_WSTRB;
    wire ar_take = S00_AXI_ARVALID && S00_AXI_ARREADY;
    wire result_read_accept = ar_take &&
                              (S00_AXI_ARADDR[5:0] == REG_RESULT_WORD_DATA) &&
                              (result_word_addr_q <= LAST_WORD_ADDR) && !core_busy;

    function [31:0] merge_wstrb;
        input [31:0] old_value;
        input [31:0] new_value;
        input [3:0] strobe;
        integer lane;
        begin
            merge_wstrb = old_value;
            for (lane = 0; lane < 4; lane = lane + 1)
                if (strobe[lane])
                    merge_wstrb[lane*8 +: 8] = new_value[lane*8 +: 8];
        end
    endfunction

    wire [31:0] load_addr_merged = merge_wstrb(load_word_addr_q, write_data, write_strb);
    wire [31:0] result_addr_merged = merge_wstrb(result_word_addr_q, write_data, write_strb);
    wire [31:0] status_word = {16'd0, core_iter_count[7:0], 2'b00,
                               reader_active, loader_active, core_error,
                               core_converged, done_sticky, core_busy};

    assign S00_AXI_AWREADY = !aw_pending && !S00_AXI_BVALID &&
                             !loader_active && !reader_active;
    assign S00_AXI_WREADY = !w_pending && !S00_AXI_BVALID &&
                            !loader_active && !reader_active;
    // 不在一个未完成写事务中途接收读请求，避免 AW/W 分离握手被长读回占住。
    assign S00_AXI_ARREADY = !reader_active && !S00_AXI_RVALID && !loader_active &&
                             !aw_pending && !w_pending;

    // result_bit 是核心同步读输出。首位与 AR 握手同拍发起，随后每拍发起一位；
    // 下一拍捕获上一位，因此 32 位在 32 个时钟周期内完成。
    assign core_result_addr = reader_active ?
                              (result_base_q + {12'd0, read_issue_index[4:0]}) :
                              (result_read_accept ?
                               {1'b0, result_word_addr_q[10:0], 5'b00000} : 17'd0);

    ldpc_decoder_p1 #(
        .BT_ROM_FILE(BT_ROM_FILE),
        .BT_OFF_FILE(BT_OFF_FILE)
    ) decoder_core (
        .clk(S00_AXI_ACLK),
        .rst(core_rst),
        .load_we(core_load_we),
        .load_addr(core_load_addr),
        .load_bit(core_load_bit),
        .start(start_pulse),
        .result_addr(core_result_addr),
        .result_bit(core_result_bit),
        .busy(core_busy),
        .done(core_done),
        .converged(core_converged),
        .error(core_error),
        .iter_count(core_iter_count)
    );

    always @(posedge S00_AXI_ACLK) begin
        if (!S00_AXI_ARESETN) begin
            aw_pending          <= 1'b0;
            awaddr_hold         <= {C_S00_AXI_ADDR_WIDTH{1'b0}};
            w_pending           <= 1'b0;
            wdata_hold          <= {C_S00_AXI_DATA_WIDTH{1'b0}};
            wstrb_hold          <= {C_S00_AXI_DATA_WIDTH/8{1'b0}};
            load_word_addr_q    <= 32'd0;
            load_word_data_q    <= 32'd0;
            result_word_addr_q  <= 32'd0;
            load_base_q         <= 17'd0;
            load_bit_index      <= 5'd0;
            loader_active       <= 1'b0;
            load_response_pending <= 1'b0;
            result_base_q       <= 17'd0;
            read_issue_index    <= 6'd0;
            read_capture_index  <= 5'd0;
            result_word_buffer  <= 32'd0;
            reader_active       <= 1'b0;
            read_capture_valid  <= 1'b0;
            start_pulse         <= 1'b0;
            core_reset_pulse    <= 1'b0;
            done_sticky         <= 1'b0;
            S00_AXI_BRESP       <= 2'b00;
            S00_AXI_BVALID      <= 1'b0;
            S00_AXI_RDATA       <= {C_S00_AXI_DATA_WIDTH{1'b0}};
            S00_AXI_RRESP       <= 2'b00;
            S00_AXI_RVALID      <= 1'b0;
        end else begin
            start_pulse      <= 1'b0;
            core_reset_pulse <= 1'b0;

            if (aw_take) begin
                aw_pending  <= 1'b1;
                awaddr_hold <= S00_AXI_AWADDR;
            end
            if (w_take) begin
                w_pending  <= 1'b1;
                wdata_hold <= S00_AXI_WDATA;
                wstrb_hold <= S00_AXI_WSTRB;
            end

            if (S00_AXI_BVALID && S00_AXI_BREADY)
                S00_AXI_BVALID <= 1'b0;
            if (S00_AXI_RVALID && S00_AXI_RREADY)
                S00_AXI_RVALID <= 1'b0;
            if (core_done)
                done_sticky <= 1'b1;

            if (loader_active) begin
                if (load_bit_index == 5'd31) begin
                    loader_active  <= 1'b0;
                    load_bit_index <= 5'd0;
                    if (load_response_pending) begin
                        load_response_pending <= 1'b0;
                        S00_AXI_BRESP  <= 2'b00;
                        S00_AXI_BVALID <= 1'b1;
                    end
                end else begin
                    load_bit_index <= load_bit_index + 1'b1;
                end
            end

            if (reader_active && read_capture_valid) begin
                result_word_buffer[read_capture_index] <= core_result_bit;
                if (read_capture_index == 5'd31) begin
                    S00_AXI_RDATA  <= {core_result_bit, result_word_buffer[30:0]};
                    S00_AXI_RRESP  <= 2'b00;
                    S00_AXI_RVALID <= 1'b1;
                    reader_active      <= 1'b0;
                    read_capture_valid <= 1'b0;
                    read_issue_index   <= 6'd0;
                end else begin
                    read_capture_index <= read_capture_index + 1'b1;
                end
            end
            if (reader_active && (read_issue_index < 6'd32))
                read_issue_index <= read_issue_index + 1'b1;

            if (write_pair) begin
                aw_pending <= 1'b0;
                w_pending  <= 1'b0;
                if (write_addr[1:0] != 2'b00) begin
                    S00_AXI_BRESP  <= 2'b10;
                    S00_AXI_BVALID <= 1'b1;
                end else begin
                    case (write_addr[5:0])
                        REG_CONTROL: begin
                            if (write_strb[0] && write_data[1]) begin
                                core_reset_pulse <= 1'b1;
                                done_sticky      <= 1'b0;
                                S00_AXI_BRESP    <= 2'b00;
                                S00_AXI_BVALID   <= 1'b1;
                            end else if (write_strb[0] && write_data[0]) begin
                                if (core_busy) begin
                                    S00_AXI_BRESP  <= 2'b10;
                                    S00_AXI_BVALID <= 1'b1;
                                end else begin
                                    start_pulse   <= 1'b1;
                                    done_sticky   <= 1'b0;
                                    S00_AXI_BRESP <= 2'b00;
                                    S00_AXI_BVALID <= 1'b1;
                                end
                            end else begin
                                S00_AXI_BRESP  <= 2'b00;
                                S00_AXI_BVALID <= 1'b1;
                            end
                        end
                        REG_LOAD_WORD_ADDR: begin
                            if (load_addr_merged <= LAST_WORD_ADDR) begin
                                load_word_addr_q <= load_addr_merged;
                                S00_AXI_BRESP    <= 2'b00;
                            end else begin
                                S00_AXI_BRESP    <= 2'b10;
                            end
                            S00_AXI_BVALID <= 1'b1;
                        end
                        REG_LOAD_WORD_DATA: begin
                            if ((write_strb == 4'b1111) &&
                                (load_word_addr_q <= LAST_WORD_ADDR) && !core_busy) begin
                                load_word_data_q      <= write_data;
                                load_base_q           <= {1'b0, load_word_addr_q[10:0], 5'b00000};
                                load_bit_index        <= 5'd0;
                                loader_active         <= 1'b1;
                                load_response_pending <= 1'b1;
                            end else begin
                                S00_AXI_BRESP  <= 2'b10;
                                S00_AXI_BVALID <= 1'b1;
                            end
                        end
                        REG_RESULT_WORD_ADDR: begin
                            if (result_addr_merged <= LAST_WORD_ADDR) begin
                                result_word_addr_q <= result_addr_merged;
                                S00_AXI_BRESP      <= 2'b00;
                            end else begin
                                S00_AXI_BRESP      <= 2'b10;
                            end
                            S00_AXI_BVALID <= 1'b1;
                        end
                        default: begin
                            S00_AXI_BRESP  <= 2'b10;
                            S00_AXI_BVALID <= 1'b1;
                        end
                    endcase
                end
            end

            if (ar_take) begin
                if (S00_AXI_ARADDR[1:0] != 2'b00) begin
                    S00_AXI_RDATA  <= 32'd0;
                    S00_AXI_RRESP  <= 2'b10;
                    S00_AXI_RVALID <= 1'b1;
                end else begin
                    case (S00_AXI_ARADDR[5:0])
                        REG_CONTROL: begin
                            S00_AXI_RDATA  <= 32'd0;
                            S00_AXI_RRESP  <= 2'b00;
                            S00_AXI_RVALID <= 1'b1;
                        end
                        REG_STATUS: begin
                            S00_AXI_RDATA  <= status_word;
                            S00_AXI_RRESP  <= 2'b00;
                            S00_AXI_RVALID <= 1'b1;
                        end
                        REG_LOAD_WORD_ADDR: begin
                            S00_AXI_RDATA  <= load_word_addr_q;
                            S00_AXI_RRESP  <= 2'b00;
                            S00_AXI_RVALID <= 1'b1;
                        end
                        REG_LOAD_WORD_DATA: begin
                            S00_AXI_RDATA  <= load_word_data_q;
                            S00_AXI_RRESP  <= 2'b00;
                            S00_AXI_RVALID <= 1'b1;
                        end
                        REG_RESULT_WORD_ADDR: begin
                            S00_AXI_RDATA  <= result_word_addr_q;
                            S00_AXI_RRESP  <= 2'b00;
                            S00_AXI_RVALID <= 1'b1;
                        end
                        REG_RESULT_WORD_DATA: begin
                            if ((result_word_addr_q <= LAST_WORD_ADDR) && !core_busy) begin
                                result_base_q      <= {1'b0, result_word_addr_q[10:0], 5'b00000};
                                read_issue_index   <= 6'd1;
                                read_capture_index <= 5'd0;
                                result_word_buffer <= 32'd0;
                                reader_active      <= 1'b1;
                                read_capture_valid <= 1'b1;
                            end else begin
                                S00_AXI_RDATA  <= 32'd0;
                                S00_AXI_RRESP  <= 2'b10;
                                S00_AXI_RVALID <= 1'b1;
                            end
                        end
                        default: begin
                            S00_AXI_RDATA  <= 32'd0;
                            S00_AXI_RRESP  <= 2'b10;
                            S00_AXI_RVALID <= 1'b1;
                        end
                    endcase
                end
            end
        end
    end
endmodule
