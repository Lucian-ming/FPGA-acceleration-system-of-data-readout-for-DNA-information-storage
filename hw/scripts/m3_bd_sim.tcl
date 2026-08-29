# =========================================
# m3_bd_sim.tcl —— M3：实际 Block Design 集成仿真的工程生成器
#
#   vivado -mode batch -source hw/scripts/m3_bd_sim.tcl -tclargs \
#       outdir=<绝对路径> [part=xc7z010clg400-1] [clk_mhz=100] \
#       [tb_top=<顶层>] [tb_srcs=<以逗号分隔的 TB 源文件>] [stage=bd1|sim] \
#       [sim_time=<如 2ms>] [bd_script_sel=prod|sim_mem]
#
# 设计约束（对应 docs/13-xsim-simulation-plan.md §7.1）：
#   - 工程建在 outdir 下的一次性目录，**绝不触碰** hw/build/dna_accel.xpr；
#     那是用户保留的构建证据，M3 不得覆盖或清理。
#   - BD 由 hw/scripts/bd.tcl 重新生成，不从现存 .xpr 复制，保证「干净目录可复现」。
#   - 路径全部由脚本自身位置推导，不依赖调用者 pwd。
# =========================================

set outdir   ""
set part_name "xc7z010clg400-1"
set clk_mhz   100
set tb_top    ""
set tb_srcs   ""
set stage     "bd1"
set sim_time  "2ms"
# 默认用生产 BD；命令行传 bd_script_sel=sim_mem 时改用仿真专用变体
# （HP0 内存端点换成 AXI VIP 从机，见 hw/scripts/bd_sim_mem.tcl）
set bd_script_sel "prod"

proc _arg {k def} {
  upvar $k v
  if {![info exists v]} { set v $def }
  foreach a $::argv {
    if {[string match "${k}=*" $a]} {
      set v [string range $a [expr {[string length "${k}="]}] end]
    }
  }
}
_arg outdir   $outdir
_arg part_name $part_name
_arg clk_mhz  $clk_mhz
_arg tb_top   $tb_top
_arg tb_srcs  $tb_srcs
_arg stage    $stage
_arg sim_time $sim_time
_arg bd_script_sel $bd_script_sel

if {$outdir eq ""} { puts "FATAL: outdir= is required"; exit 1 }

set _here     [file normalize [file dirname [info script]]]
set repo_root [file normalize "$_here/../.."]
if {$bd_script_sel eq "sim_mem"} {
  set bd_script [file join $repo_root hw/scripts/bd_sim_mem.tcl]
} else {
  set bd_script [file join $repo_root hw/scripts/bd.tcl]
}
set ip_repo   [file join $repo_root hw/ip]
set proj_wk   [file join $outdir proj]
set proj_name "m3_bd"

puts "===> Vivado [version -short]"
puts "===> M3 stage=$stage part=$part_name clk=${clk_mhz}MHz bd=$bd_script_sel"
puts "===> repo=$repo_root"
puts "===> outdir=$outdir"

if {![file isdirectory $ip_repo]} { puts "FATAL: IP repo not found: $ip_repo"; exit 1 }
if {![file exists $bd_script]}    { puts "FATAL: missing $bd_script"; exit 1 }

# ---- 工程与 IP 仓库 ----
file mkdir $proj_wk
create_project $proj_name $proj_wk -part $part_name -force
set_property ip_repo_paths $ip_repo [current_project]
update_ip_catalog
puts "===> IP repo registered: $ip_repo"

# ---- 由 bd.tcl 重新生成实际 BD ----
set ::env(BD_CLK_MHZ) $clk_mhz
source $bd_script

set bdpath "$proj_wk/$proj_name.srcs/sources_1/bd/top_bd/top_bd.bd"
if {![file exists $bdpath]} { puts "FATAL: BD not created at $bdpath"; exit 1 }

# ---- BD-1 静态检查：地址图、未连接接口 ----
puts "===> ---------- BD-1 static checks ----------"

# 地址段落盘，供外部脚本与 sw/app/xparameters.h 对表
set addr_report [file join $outdir bd_address.txt]
set fh [open $addr_report w]
foreach seg [get_bd_addr_segs -quiet -of_objects [get_bd_addr_spaces]] {
  set off [get_property -quiet OFFSET $seg]
  set rng [get_property -quiet RANGE  $seg]
  # 从机侧 segment（如 IP 自身的 Reg）没有 OFFSET，只有映射到某个地址空间的
  # segment 才有；两类都记录，便于核对是否真的被映射进 ps_0/Data。
  if {$off eq "" || $rng eq ""} {
    puts $fh [format "%-72s (unmapped/slave-side)" $seg]
  } else {
    puts $fh [format "%-72s offset=0x%08X range=0x%08X" $seg $off $rng]
  }
}
close $fh
puts "===> address map -> $addr_report"

# 未连接的接口引脚（排除有意外部化的 DDR/FIXED_IO）
set unconnected {}
foreach ip [get_bd_intf_pins -quiet -of_objects [get_bd_cells]] {
  if {[llength [get_bd_intf_nets -quiet -of_objects $ip]] == 0} {
    lappend unconnected $ip
  }
}
set unconn_report [file join $outdir bd_unconnected.txt]
set fh [open $unconn_report w]
foreach u $unconnected { puts $fh $u }
close $fh
puts "===> unconnected intf pins: [llength $unconnected] -> $unconn_report"

# IP 状态：任何 IP 需要升级/锁定都要暴露出来，不能默默用旧输出
set ip_status [file join $outdir bd_ip_status.txt]
set fh [open $ip_status w]
foreach ipc [get_ips -quiet] {
  puts $fh [format "%-48s vlnv=%-56s locked=%s upgrade=%s" \
    $ipc [get_property IPDEF $ipc] \
    [get_property IS_LOCKED $ipc] [get_property UPGRADE_VERSIONS $ipc]]
}
close $fh
puts "===> ip status -> $ip_status"

# ---- 生成 wrapper 与 simulation target ----
make_wrapper -files [get_files $bdpath] -top
set wrapper "$proj_wk/$proj_name.gen/sources_1/bd/top_bd/hdl/top_bd_wrapper.v"
if {![file exists $wrapper]} {
  set wrapper "$proj_wk/$proj_name.srcs/sources_1/bd/top_bd/hdl/top_bd_wrapper.v"
}
if {![file exists $wrapper]} { puts "FATAL: wrapper not generated"; exit 1 }
add_files -norecurse $wrapper
puts "===> wrapper: $wrapper"

puts "===> generate_target simulation (this takes a while)"
generate_target simulation [get_files $bdpath]
export_ip_user_files -of_objects [get_files $bdpath] -no_script -force -quiet

# 仿真源文件清单落盘（供 manifest 与黑盒排查）
set simfiles [get_files -quiet -compile_order sources -used_in simulation -of_objects [get_filesets sources_1]]
set simlist [file join $outdir bd_sim_sources.txt]
set fh [open $simlist w]
foreach f $simfiles { puts $fh $f }
close $fh
puts "===> simulation sources: [llength $simfiles] -> $simlist"

# ---- Testbench 与仿真 ----
if {$tb_srcs ne ""} {
  foreach f [split $tb_srcs ","] {
    if {$f eq ""} { continue }
    if {![file exists $f]} { puts "FATAL: TB source not found: $f"; exit 1 }
    add_files -fileset sim_1 -norecurse $f
    puts "===> TB source: $f"
  }
}

if {$tb_top ne ""} {
  set_property top $tb_top [get_filesets sim_1]
} else {
  set_property top top_bd_wrapper [get_filesets sim_1]
}
set_property top_lib xil_defaultlib [get_filesets sim_1]
update_compile_order -fileset sim_1

set_property -name {xsim.simulate.runtime} -value $sim_time -objects [get_filesets sim_1]
if {$stage eq "bd1"} {
  # 只做编译 + elaborate，不跑仿真：BD-1 的退出判据
  puts "===> launch_simulation -step compile"
  launch_simulation -step compile
  puts "===> launch_simulation -step elaborate"
  launch_simulation -step elaborate
  puts "===> BD-1 compile+elaborate finished"
} else {
  puts "===> launch_simulation (full)"
  launch_simulation
  puts "===> simulation finished"
}

# 仿真运行目录固定路径，外部脚本据此收集日志
set simdir "$proj_wk/$proj_name.sim/sim_1/behav/xsim"
puts "===> SIMDIR=$simdir"
puts "===> DONE."
