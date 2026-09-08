# =========================================
# build.tcl
#   vivado -mode batch -source hw/scripts/build.tcl
# 可选参数：
#   -tclargs proj_name=dna_accel part=xc7z010clg400-1 clk_mhz=100
#
# 2026-08-16 修复 A2：
#   - 仓库根路径改由「脚本自身位置」推导，不再依赖启动时的 pwd；
#   - 注册 hw/ip 为 IP 仓库并 update_ip_catalog（否则找不到三个自研 IP）；
#   - 把 hw/constr/top.xdc 加入 constrs_1（此前 XDC 完全不进构建流）。
# =========================================

# 默认
set proj_name "dna_accel"
set part_name "xc7z010clg400-1"
set clk_mhz   100

# 覆盖参数
proc _arg {k def} {upvar $k v; if {![info exists v]} {set v $def}; foreach a $::argv {if {[string match "${k}=*" $a]} {set v [string range $a [expr {[string length "${k}="]}] end]}}}
_arg proj_name $proj_name
_arg part_name $part_name
_arg clk_mhz   $clk_mhz

# 路径：按脚本自身位置推导（可在任意目录启动）
set _here     [file normalize [file dirname [info script]]]
set repo_root [file normalize "$_here/../.."]
set proj_wk    [file join $repo_root hw/build]
set bd_script  [file join $repo_root hw/scripts/bd.tcl]
set xdc_file   [file join $repo_root hw/constr/top.xdc]
# 导出与报告目录：默认沿用 hw/build/export 与 hw/build/reports（历史行为不变）。
# 可用环境变量 DNA_EXPORT_DIR / DNA_REPORT_DIR 覆盖，避免新构建覆盖既有生产制品
# （例如 4-way 构建导出到 hw/build/export_4way，保住 2-way 基线的 BOOT.bin/bit/xsa）。
set export_dir [file join $proj_wk export]
if {[info exists ::env(DNA_EXPORT_DIR)] && $::env(DNA_EXPORT_DIR) ne ""} {
  set export_dir [file normalize $::env(DNA_EXPORT_DIR)]
}
set report_dir [file join $proj_wk reports]
if {[info exists ::env(DNA_REPORT_DIR)] && $::env(DNA_REPORT_DIR) ne ""} {
  set report_dir [file normalize $::env(DNA_REPORT_DIR)]
}
set xsa_out    [file join $export_dir ${proj_name}.xsa]
set ip_repo    [file join $repo_root hw/ip]

puts "===> Vivado [version -short]"
puts "===> proj=$proj_name part=$part_name clk=${clk_mhz}MHz"
puts "===> root=$repo_root"
puts "===> export_dir=$export_dir"
puts "===> report_dir=$report_dir"

proc require_run_success {run_name} {
  set run [get_runs $run_name]
  set status [get_property STATUS $run]
  set progress [get_property PROGRESS $run]
  if {$progress ne "100%" || ![string match "*Complete*" $status]} {
    puts "FATAL: run $run_name failed: status='$status', progress='$progress'"
    exit 1
  }
}

# 工程
file mkdir $proj_wk
create_project $proj_name $proj_wk -force
set_property part $part_name [current_project]

# 【A2】注册自研 IP 仓库（hw/ip 下三个 *_1_0 目录各含 component.xml）
if {[file isdirectory $ip_repo]} {
  set_property ip_repo_paths $ip_repo [current_project]
  update_ip_catalog
  puts "===> IP repo: $ip_repo"
} else {
  puts "FATAL: IP repo not found: $ip_repo"; exit 1
}

# 生成 BD
if {![file exists $bd_script]} { puts "FATAL: Missing $bd_script"; exit 1 }
set ::env(BD_CLK_MHZ) $clk_mhz
source $bd_script

# BD wrapper 顶层
set bdpath "$proj_wk/$proj_name.srcs/sources_1/bd/top_bd/top_bd.bd"
make_wrapper -files [get_files $bdpath] -top
add_files "$proj_wk/$proj_name.srcs/sources_1/bd/top_bd/hdl/top_bd_wrapper.v"
set_property top top_bd_wrapper [current_fileset]

# 【A2】约束进构建流
if {[file exists $xdc_file]} {
  add_files -fileset constrs_1 $xdc_file
  puts "===> XDC: $xdc_file"
}

# 综合/实现/bit
launch_runs synth_1 -jobs 8
wait_on_runs synth_1
require_run_success synth_1

# 【实现策略】必须固化，不要改回 "Vivado Implementation Defaults"。
#
# 原因（2026-09-09 实测，证据见 logs/vivado/recovery_20260909/findings.md）：
#   4-way 加速核合入后，用默认实现策略构建的整机 **100MHz 时序不收敛**：
#     WNS = -0.252 ns，TNS = -4.073 ns，43 个失败端点（估算上限仅 97.5 MHz）。
#   失败路径与 4-way 选优树无关（全部 43 个端点枚举，Dna_accelerator_core/srpe_batch
#   出现 0 次），而是 desparsification_dec -> AXI HP 写通道的 WVALID/WREADY
#   未打拍组合握手链；该链在 2-way 基线时就已是关键路径，仅剩 +0.136 ns 裕量，
#   4-way 只是把这点裕量吃光。
#
#   仅把实现策略换成 Performance_ExplorePostRoutePhysOpt（零 RTL / 零 BD 改动）后：
#     WNS = +0.246 ns，TNS = 0，失败端点 0 —— 100MHz 收敛，
#   且资源未变差（LUT 15499 -> 15483，RAMB36 44 不变）。
#
# 因此这不是"随手设的调优参数"：去掉它，整机会退回 WNS = -0.252 ns 的不收敛状态，
# 从零重建将无法复现已交付的收敛结果（违反 docs/13 G7/G8 可复现门禁）。
#
# 注意：AXI 握手链本身**并未被修复**，只是靠实现策略赢回了裕量。
# 后续若继续增加逻辑或提高频率目标，它仍会第一个失败；
# 届时正解是给 ic_hp S04 口加 AXI Register Slice，或把 desparsification_dec 的
# M00_AXI_WVALID 寄存输出，而不是继续寄望于实现策略。
set impl_strategy "Performance_ExplorePostRoutePhysOpt"
if {[info exists ::env(DNA_IMPL_STRATEGY)] && $::env(DNA_IMPL_STRATEGY) ne ""} {
  set impl_strategy $::env(DNA_IMPL_STRATEGY)
}
set_property strategy $impl_strategy [get_runs impl_1]
puts "===> impl 策略: [get_property STRATEGY [get_runs impl_1]]"

launch_runs impl_1 -to_step write_bitstream -jobs 8
wait_on_runs impl_1
require_run_success impl_1

# 收集报告（可选，失败不阻断）
if {[file exists [file join $repo_root hw scripts collect_info.tcl]]} {
  open_run impl_1
  set ::collect_info_outdir $report_dir
  set ::collect_info_design $proj_name
  catch {source [file join $repo_root hw scripts collect_info.tcl]}
  unset ::collect_info_outdir
  unset ::collect_info_design
}

# 导出 XSA（含bit）
file mkdir [file dirname $xsa_out]
write_hw_platform -fixed -include_bit -force -file $xsa_out
puts "===> XSA: $xsa_out"
set bit_out [file join $export_dir top_bd_wrapper.bit]
if {[file exists "$proj_wk/$proj_name.runs/impl_1/top_bd_wrapper.bit"]} {
  file copy -force "$proj_wk/$proj_name.runs/impl_1/top_bd_wrapper.bit" $bit_out
  puts "===> BIT: $bit_out"
}
puts "===> DONE."
