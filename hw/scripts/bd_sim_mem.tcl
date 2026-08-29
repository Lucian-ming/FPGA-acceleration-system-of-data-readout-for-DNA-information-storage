# =========================================
# bd_sim_mem.tcl —— BD-3 的**仿真专用**变体：把 HP0 内存端点换成 AXI VIP 从机
#
# ⚠️ 本脚本只用于仿真，**绝不能用于综合或上板**。
#    生产 BD 永远是 hw/scripts/bd.tcl，本脚本在其基础上做一处替换。
#
# 为什么需要它（详见 docs/15-m3-bd-simulation-2026-08-29.md §5）：
#   Vivado 2022.2 的 processing_system7_vip 的 HP/AFI 从机读通路在本配置下
#   接受 AR 之后不返回任何 RDATA。已逐条排除跨 4KB 边界、地址范围、DDR 容量、
#   未完成事务上限、三档从机延迟、单个 IP、时钟/复位、RDISSUECAP1_EN
#   （VIP 中该端口只声明、从不使用）和从机 agent 未启动（VIP 自动 start_slave）。
#   即数据面被仿真模型挡住，而不是设计有缺陷。
#
# 本变体保留：实际 ic_lite / ic_hp、实际 AXI DMA、三个实际自研 IP、
#             实际 PS7 VIP 的 GP0 控制通路、以及**完全相同的地址映射**。
# 本变体替换：ps_0/S_AXI_HP0 这一个内存端点 -> axi_vip(SLAVE) 内存模型。
#
# 报告纪律：凡引用本变体得到的结论，必须写明「内存端点不是实际 PS7 的 AFI 通路」。
#
#   vivado -mode batch -source hw/scripts/bd_sim_mem.tcl -tclargs ...
#   （由 hw/scripts/m3_bd_sim.tcl 通过 bd_script= 参数调用）
# =========================================

set _here_mem [file normalize [file dirname [info script]]]

# 先构建完整的生产 BD
source [file join $_here_mem bd.tcl]

puts "===> \[sim-only\] 开始把 HP0 内存端点替换为 AXI VIP 从机"

# ---- 1. 断开 ic_hp/M00_AXI -> ps_0/S_AXI_HP0 ----
set hp_net [get_bd_intf_nets -quiet -of_objects [get_bd_intf_pins ic_hp/M00_AXI]]
if {[llength $hp_net]} {
  delete_bd_objs $hp_net
  puts "===> \[sim-only\] 已断开 ic_hp/M00_AXI -> ps_0/S_AXI_HP0"
} else {
  puts "FATAL: 找不到 ic_hp/M00_AXI 的连接"; exit 1
}

# PS7 的 HP0 在本变体中不再使用，关掉以免留下悬空从机接口
set_property -dict [list CONFIG.PCW_USE_S_AXI_HP0 {0}] [get_bd_cells ps_0]

# ---- 2. 建立 AXI VIP 从机（带内存模型）----
set memvip [create_bd_cell -type ip -vlnv xilinx.com:ip:axi_vip mem_vip]
set_property -dict [list \
  CONFIG.INTERFACE_MODE   {SLAVE} \
  CONFIG.PROTOCOL         {AXI4} \
  CONFIG.READ_WRITE_MODE  {READ_WRITE} \
  CONFIG.ADDR_WIDTH       {32} \
  CONFIG.DATA_WIDTH       {64} \
  CONFIG.HAS_BURST        {1} \
  CONFIG.SUPPORTS_NARROW  {1} \
] $memvip

connect_bd_net [get_bd_pins clk_wiz_0/clk_out1]        [get_bd_pins mem_vip/aclk]
connect_bd_net [get_bd_pins rst_ps/peripheral_aresetn] [get_bd_pins mem_vip/aresetn]
connect_bd_intf_net [get_bd_intf_pins ic_hp/M00_AXI] [get_bd_intf_pins mem_vip/S_AXI]
puts "===> \[sim-only\] ic_hp/M00_AXI -> mem_vip/S_AXI 已连接"

# ---- 3. 地址：与生产 BD 的 HP0 段完全一致（0x00000000 + 512 MiB）----
# 五个主设备（DMA MM2S/S2MM/SG、Voter、Decoder）都必须能用**真实地址**访问，
# 否则 BD-3 就失去了「跑在真实地址上」这一条判据。
set mem_seg [get_bd_addr_segs mem_vip/S_AXI/Reg]
foreach sp {
  axi_dma_0/Data_MM2S
  axi_dma_0/Data_S2MM
  axi_dma_0/Data_SG
  differential_voter_0/M00_AXI
  desparsification_dec_0/M00_AXI
} {
  set space [get_bd_addr_spaces -quiet $sp]
  if {![llength $space]} { puts "FATAL: 找不到地址空间 $sp"; exit 1 }
  assign_bd_address -offset 0x00000000 -range 0x20000000 \
      -target_address_space $space $mem_seg -force
  puts "===> \[sim-only\] $sp -> mem_vip 0x00000000+512MiB"
}

validate_bd_design
save_bd_design
puts "===> \[sim-only\] BD 变体生成完毕：HP0 已由 AXI VIP 内存模型替代"
