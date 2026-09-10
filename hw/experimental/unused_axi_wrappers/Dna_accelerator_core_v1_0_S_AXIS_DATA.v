// Filename: Dna_accelerator_core_v1_0_S_AXIS_DATA.v
`timescale 1 ns / 1 ps

module Dna_accelerator_core_v1_0_S_AXIS_DATA #
(
    parameter integer C_S_AXIS_TDATA_WIDTH = 32
)
(
    input  wire                            S_AXIS_ACLK,
    input  wire                            S_AXIS_ARESETN,
    // 仅作"顶层真实 TREADY"的旁路输入；本模块不驱动它
    input  wire                            S_AXIS_TREADY,
    input  wire [C_S_AXIS_TDATA_WIDTH-1:0] S_AXIS_TDATA,
    input  wire [(C_S_AXIS_TDATA_WIDTH/8)-1:0] S_AXIS_TSTRB,
    input  wire                            S_AXIS_TLAST,
    input  wire                            S_AXIS_TVALID
);
    // 占位模块，不包含逻辑
endmodule
