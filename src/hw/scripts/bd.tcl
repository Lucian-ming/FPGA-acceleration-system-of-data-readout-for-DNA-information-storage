# =========================================
# bd.tcl
# 设备/PS7: 由已验证的 hw/boards/<board>.tcl 显式选择
# IP:
#   - xilinx.com:user:dna_accelerator_core:1.0
#       IF: S_AXI_LITE_CTRL (AXI4-Lite), S_AXIS_DATA (AXIS in), M_AXIS_RESULT (AXIS out)
#   - xilinx.com:user:differential_voter:1.0
#       IF: S00_AXI (AXI4-Lite), M00_AXI (AXI4 master)
#   - xilinx.com:user:desparsification_decoder:1.0
#       IF: S00_AXI (AXI4-Lite), M00_AXI (AXI4 master)
#   - xilinx.com:user:ldpc_decoder:1.0
#       IF: S00_AXI (AXI4-Lite), 64,800-bit LDPC decode control/data window
# DMA: axi_dma_0 with Scatter-Gather (c_include_sg=1)
# 拓扑：
#   GP0 -> AXI-Lite IC -> {DMA S_AXI_LITE, DNA S_AXI_LITE_CTRL, Voter S00_AXI, Decoder S00_AXI, LDPC S00_AXI}
#   {DMA M_AXI_MM2S, DMA M_AXI_S2MM, DMA M_AXI_SG, Voter M00_AXI, Decoder M00_AXI} -> HP IC -> PS HP0
#   AXIS: DMA MM2S -> DNA S_AXIS_DATA; DNA M_AXIS_RESULT -> DMA S2MM
# =========================================

# 读取时钟频率
set clk_mhz 100
if {[info exists ::env(BD_CLK_MHZ)]} { set clk_mhz $::env(BD_CLK_MHZ) }
puts "===> BD clock: ${clk_mhz} MHz"

# 新建BD
create_bd_design "top_bd"

# PS7
set ps_0 [create_bd_cell -type ip -vlnv xilinx.com:ip:processing_system7 ps_0]
apply_bd_automation -rule xilinx.com:bd_rule:processing_system7 -config { make_external "FIXED_IO, DDR" } [get_bd_cells ps_0]

# 板级 PS7 参数来自当前受支持的 hw/boards/bkb220.tcl profile。
# 正常构建由 build.tcl 显式传入配置；直接 source 时使用当前 BKB220 profile。
if {![info exists ::dna_board_config]} {
  set _bd_here [file normalize [file dirname [info script]]]
  set _bd_root [file normalize [file join $_bd_here ../..]]
  source [file join $_bd_root hw boards load_board.tcl]
  set ::dna_board_config [dna_load_board $_bd_root bkb220]
}
set_property -dict [dict get $::dna_board_config ps7_properties] [get_bd_cells ps_0]

# 时钟/复位
set clk_wiz_0 [create_bd_cell -type ip -vlnv xilinx.com:ip:clk_wiz clk_wiz_0]
set_property -dict [list CONFIG.PRIM_SOURCE {No_buffer} CONFIG.CLKOUT1_REQUESTED_OUT_FREQ $clk_mhz] $clk_wiz_0
set rst_ps   [create_bd_cell -type ip -vlnv xilinx.com:ip:proc_sys_reset rst_ps]
connect_bd_net [get_bd_pins ps_0/FCLK_CLK0]     [get_bd_pins clk_wiz_0/clk_in1]
connect_bd_net [get_bd_pins ps_0/FCLK_RESET0_N] [get_bd_pins rst_ps/ext_reset_in]
connect_bd_net [get_bd_pins clk_wiz_0/clk_out1] [get_bd_pins rst_ps/slowest_sync_clk]
# PS AXI 主/从端口也必须接入同一时钟，否则 validate_bd_design 会拒绝
# M_AXI_GP0 和 S_AXI_HP0 的接口连接。
connect_bd_net [get_bd_pins clk_wiz_0/clk_out1] [get_bd_pins ps_0/M_AXI_GP0_ACLK]
connect_bd_net [get_bd_pins clk_wiz_0/clk_out1] [get_bd_pins ps_0/S_AXI_HP0_ACLK]

# AXI-Lite 互联 (GP0 -> 多从)
set ic_lite [create_bd_cell -type ip -vlnv xilinx.com:ip:axi_interconnect ic_lite]
set_property -dict [list CONFIG.NUM_SI {1} CONFIG.NUM_MI {5}] $ic_lite
foreach pin {ACLK S00_ACLK M00_ACLK M01_ACLK M02_ACLK M03_ACLK M04_ACLK} {
  connect_bd_net [get_bd_pins clk_wiz_0/clk_out1] [get_bd_pins ic_lite/$pin]
}
connect_bd_net [get_bd_pins rst_ps/interconnect_aresetn] [get_bd_pins ic_lite/ARESETN]
foreach pin {S00_ARESETN M00_ARESETN M01_ARESETN M02_ARESETN M03_ARESETN M04_ARESETN} {
  connect_bd_net [get_bd_pins rst_ps/peripheral_aresetn] [get_bd_pins ic_lite/$pin]
}
connect_bd_intf_net [get_bd_intf_pins ps_0/M_AXI_GP0] [get_bd_intf_pins ic_lite/S00_AXI]

# AXI 高带宽互联 (汇聚到 HP0)
# 需要 5 个从口：MM2S、S2MM、SG、Voter、Decoder
set ic_hp [create_bd_cell -type ip -vlnv xilinx.com:ip:axi_interconnect ic_hp]
set_property -dict [list CONFIG.NUM_SI {5} CONFIG.NUM_MI {1}] $ic_hp
foreach pin {ACLK S00_ACLK S01_ACLK S02_ACLK S03_ACLK S04_ACLK M00_ACLK} {
  connect_bd_net [get_bd_pins clk_wiz_0/clk_out1] [get_bd_pins ic_hp/$pin]
}
connect_bd_net [get_bd_pins rst_ps/interconnect_aresetn] [get_bd_pins ic_hp/ARESETN]
foreach pin {S00_ARESETN S01_ARESETN S02_ARESETN S03_ARESETN S04_ARESETN M00_ARESETN} {
  connect_bd_net [get_bd_pins rst_ps/peripheral_aresetn] [get_bd_pins ic_hp/$pin]
}
connect_bd_intf_net [get_bd_intf_pins ic_hp/M00_AXI] [get_bd_intf_pins ps_0/S_AXI_HP0]

# AXI DMA（开启 SG，与项目一致）
set dma [create_bd_cell -type ip -vlnv xilinx.com:ip:axi_dma axi_dma_0]
set_property -dict [list CONFIG.c_include_sg {1} CONFIG.c_sg_include_stscntrl_strm {0}] $dma
# 时钟/复位
connect_bd_net [get_bd_pins clk_wiz_0/clk_out1]        [get_bd_pins axi_dma_0/m_axi_mm2s_aclk]
connect_bd_net [get_bd_pins clk_wiz_0/clk_out1]        [get_bd_pins axi_dma_0/m_axi_s2mm_aclk]
connect_bd_net [get_bd_pins clk_wiz_0/clk_out1]        [get_bd_pins axi_dma_0/m_axi_sg_aclk]
connect_bd_net [get_bd_pins clk_wiz_0/clk_out1]        [get_bd_pins axi_dma_0/s_axi_lite_aclk]
connect_bd_net [get_bd_pins rst_ps/peripheral_aresetn] [get_bd_pins axi_dma_0/axi_resetn]

# 自研 IP（使用你实际的 VLNV）
set ip1 [create_bd_cell -type ip -vlnv xilinx.com:user:dna_accelerator_core:1.0       dna_accelerator_core_0]
set ip2 [create_bd_cell -type ip -vlnv xilinx.com:user:differential_voter:1.0          differential_voter_0]
set ip3 [create_bd_cell -type ip -vlnv xilinx.com:user:desparsification_decoder:1.0    desparsification_dec_0]
set ip4 [create_bd_cell -type ip -vlnv xilinx.com:user:ldpc_decoder:1.0                ldpc_decoder_0]
set _bd_root [file normalize [file join [file dirname [info script]] ../..]]
set_property -dict [list \
  CONFIG.BT_ROM_FILE [file normalize [file join $_bd_root hw/ip/ldpc_decoder_1_0/data/bt_col_by_res.hex]] \
  CONFIG.BT_OFF_FILE [file normalize [file join $_bd_root hw/ip/ldpc_decoder_1_0/data/bt_res_off.hex]] \
] $ip4

# Stage1 可选生产参数：默认保留 ECO P4/组合树；P16 必须显式选择。
set stage1_p_ways 4
set stage1_pipe_tree 0
if {[info exists ::dna_stage1_p_ways]} {set stage1_p_ways $::dna_stage1_p_ways}
if {[info exists ::dna_stage1_pipe_tree]} {set stage1_pipe_tree $::dna_stage1_pipe_tree}
set_property -dict [list \
  CONFIG.C_STAGE1_P_WAYS $stage1_p_ways \
  CONFIG.C_STAGE1_PIPE_TREE $stage1_pipe_tree \
  CONFIG.READ_BPS 150 CONFIG.NUM_LC 50 CONFIG.STRIDE 807 CONFIG.REF_LEN 957 CONFIG.BATCH 64] $ip1
# 取实际 IP CONFIG 值；不能靠摘要中的硬编码证明几何正确。
set ::dna_stage1_actual [dict create]
foreach {key expected} [list C_STAGE1_P_WAYS $stage1_p_ways C_STAGE1_PIPE_TREE $stage1_pipe_tree \
  READ_BPS 150 NUM_LC 50 STRIDE 807 REF_LEN 957 BATCH 64] {
  set actual [get_property CONFIG.$key $ip1]
  if {$actual ne "$expected"} {error "生产Stage1参数 $key=$actual，期望$expected"}
  dict set ::dna_stage1_actual $key $actual
}
puts "===> Stage1 actual parameters: $::dna_stage1_actual"

# ===== 时钟/复位到各IP =====
# DNA (AXIS 两侧 + AXI-Lite)
foreach pin {S_AXIS_DATA_ACLK M_AXIS_RESULT_ACLK s_axi_lite_ctrl_aclk} {
  if {[llength [get_bd_pins dna_accelerator_core_0/$pin -quiet]]} {
    connect_bd_net [get_bd_pins clk_wiz_0/clk_out1] [get_bd_pins dna_accelerator_core_0/$pin]
  }
}
foreach pin {S_AXIS_DATA_ARESETN M_AXIS_RESULT_ARESETN s_axi_lite_ctrl_aresetn} {
  if {[llength [get_bd_pins dna_accelerator_core_0/$pin -quiet]]} {
    connect_bd_net [get_bd_pins rst_ps/peripheral_aresetn] [get_bd_pins dna_accelerator_core_0/$pin]
  }
}
# Voter/Decoder：S00_AXI 与 M00_AXI 的时钟/复位
foreach c {differential_voter_0 desparsification_dec_0} {
  foreach pin {S00_AXI_ACLK M00_AXI_ACLK} {
    if {[llength [get_bd_pins $c/$pin -quiet]]} {
      connect_bd_net [get_bd_pins clk_wiz_0/clk_out1] [get_bd_pins $c/$pin]
    }
  }
  foreach pin {S00_AXI_ARESETN M00_AXI_ARESETN} {
    if {[llength [get_bd_pins $c/$pin -quiet]]} {
      connect_bd_net [get_bd_pins rst_ps/peripheral_aresetn] [get_bd_pins $c/$pin]
    }
  }
}
foreach pin {S00_AXI_ACLK} {
  connect_bd_net [get_bd_pins clk_wiz_0/clk_out1] [get_bd_pins ldpc_decoder_0/$pin]
}
connect_bd_net [get_bd_pins rst_ps/peripheral_aresetn] [get_bd_pins ldpc_decoder_0/S00_AXI_ARESETN]

# ===== AXI-Lite：GP0 -> ic_lite -> (DMA, DNA, Voter, Decoder) =====
connect_bd_intf_net [get_bd_intf_pins ic_lite/M01_AXI] [get_bd_intf_pins axi_dma_0/S_AXI_LITE]
connect_bd_intf_net [get_bd_intf_pins ic_lite/M00_AXI] [get_bd_intf_pins dna_accelerator_core_0/S_AXI_LITE_CTRL]
connect_bd_intf_net [get_bd_intf_pins ic_lite/M02_AXI] [get_bd_intf_pins differential_voter_0/S00_AXI]
connect_bd_intf_net [get_bd_intf_pins ic_lite/M03_AXI] [get_bd_intf_pins desparsification_dec_0/S00_AXI]
connect_bd_intf_net [get_bd_intf_pins ic_lite/M04_AXI] [get_bd_intf_pins ldpc_decoder_0/S00_AXI]

# ===== 高带宽 AXI（Master 汇聚到 HP0）=====
# DMA 三个 master 口：MM2S, S2MM, SG
connect_bd_intf_net [get_bd_intf_pins axi_dma_0/M_AXI_MM2S] [get_bd_intf_pins ic_hp/S00_AXI]
connect_bd_intf_net [get_bd_intf_pins axi_dma_0/M_AXI_S2MM] [get_bd_intf_pins ic_hp/S01_AXI]
connect_bd_intf_net [get_bd_intf_pins axi_dma_0/M_AXI_SG]   [get_bd_intf_pins ic_hp/S04_AXI]
# Voter / Decoder 的 M00_AXI
connect_bd_intf_net [get_bd_intf_pins differential_voter_0/M00_AXI]    [get_bd_intf_pins ic_hp/S02_AXI]
connect_bd_intf_net [get_bd_intf_pins desparsification_dec_0/M00_AXI]  [get_bd_intf_pins ic_hp/S03_AXI]

# ===== AXI-Stream：DMA ↔ DNA =====
# MM2S -> DNA 输入
connect_bd_intf_net [get_bd_intf_pins axi_dma_0/M_AXIS_MM2S]     [get_bd_intf_pins dna_accelerator_core_0/S_AXIS_DATA]
# DNA 输出 -> S2MM
connect_bd_intf_net [get_bd_intf_pins dna_accelerator_core_0/M_AXIS_RESULT] [get_bd_intf_pins axi_dma_0/S_AXIS_S2MM]

# ===== 地址分配 =====
assign_bd_address
# 与历史 XSA 及 sw/app/xparameters.h 固定一致，禁止依赖自动分配顺序。
set ps_data [get_bd_addr_spaces ps_0/Data]
assign_bd_address -offset 0x40400000 -range 0x00010000 -target_address_space $ps_data \
  [get_bd_addr_segs axi_dma_0/S_AXI_LITE/Reg] -force
assign_bd_address -offset 0x43C00000 -range 0x00010000 -target_address_space $ps_data \
  [get_bd_addr_segs dna_accelerator_core_0/S_AXI_LITE_CTRL/S_AXI_LITE_CTRL_reg] -force
assign_bd_address -offset 0x43C10000 -range 0x00010000 -target_address_space $ps_data \
  [get_bd_addr_segs desparsification_dec_0/S00_AXI/S00_AXI_reg] -force
assign_bd_address -offset 0x43C20000 -range 0x00010000 -target_address_space $ps_data \
  [get_bd_addr_segs differential_voter_0/S00_AXI/S00_AXI_reg] -force
assign_bd_address -offset 0x43C30000 -range 0x00010000 -target_address_space $ps_data \
  [get_bd_addr_segs ldpc_decoder_0/S00_AXI/S00_AXI_reg] -force

# 校验/保存
validate_bd_design
save_bd_design
puts "===> BD generated: top_bd"
