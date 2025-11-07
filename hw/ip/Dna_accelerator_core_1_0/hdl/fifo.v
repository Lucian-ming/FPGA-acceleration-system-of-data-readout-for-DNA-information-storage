`timescale 1 ns / 1 ps

// ============================================================================
// Generic, Parameterizable, Register-Based FIFO Module
// ============================================================================
module generic_fifo #(
    parameter DATA_WIDTH = 32,
    parameter FIFO_DEPTH = 16
) (
    input wire clk,
    input wire rst, // Active-high reset
    
    // Write Port
    input wire wr_en,
    input wire [DATA_WIDTH-1:0] din,
    output wire full,
    
    // Read Port
    input wire rd_en,
    output wire [DATA_WIDTH-1:0] dout,
    output wire empty
);

    // Calculate the width of the address pointers
    localparam ADDR_WIDTH = $clog2(FIFO_DEPTH);

    // FIFO memory implemented as an array of registers
    reg [DATA_WIDTH-1:0] mem [0:FIFO_DEPTH-1];
    
    // Write and Read Pointers
    // The extra bit is used to easily distinguish between full and empty
    reg [ADDR_WIDTH:0] wr_ptr, rd_ptr;
    
    // Full/Empty logic
    wire is_full = (wr_ptr[ADDR_WIDTH] != rd_ptr[ADDR_WIDTH]) && (wr_ptr[ADDR_WIDTH-1:0] == rd_ptr[ADDR_WIDTH-1:0]);
    wire is_empty = (wr_ptr == rd_ptr);

    assign full = is_full;
    assign empty = is_empty;
    assign dout = mem[rd_ptr[ADDR_WIDTH-1:0]];

    // Main FIFO logic for writing and reading
    always @(posedge clk) begin
        if (rst) begin
            wr_ptr <= 0;
            rd_ptr <= 0;
        end else begin
            // Write operation
            if (wr_en && !is_full) begin
                mem[wr_ptr[ADDR_WIDTH-1:0]] <= din;
                wr_ptr <= wr_ptr + 1;
            end
            
            // Read operation
            if (rd_en && !is_empty) begin
                rd_ptr <= rd_ptr + 1;
            end
        end
    end

endmodule