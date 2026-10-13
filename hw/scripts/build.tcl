# 可复现构建：tools/run_vivado_build.sh board=zynq_eco_7010 part_name=xc7z010clg400-1
# 新板需明确 board、独立 build_dir/export_dir/report_dir；dry_run=1 只检查配置。
# 与工具版本绑定的生成目录必须独立，不能覆盖旧发布制品。
set _here [file normalize [file dirname [info script]]]
set repo_root [file normalize [file join $_here ../..]]
set opts [dict create proj_name dna_accel board zynq_eco_7010 part_name {} clk_mhz 100 \
  build_dir {} export_dir {} report_dir {} stage1_p_ways 4 stage1_pipe_tree 0 stage1_bases_per_cycle 1 jobs 8 dry_run 0]
foreach arg $::argv {
  if {![regexp {^([a-z0-9_]+)=(.*)$} $arg -> key value] || ![dict exists $opts $key]} {
    error "未知构建参数 '$arg'；器件参数应为 part_name，不是 part"
  }
  dict set opts $key $value
}
dict for {key value} $opts {set $key $value}
if {![regexp {^[A-Za-z][A-Za-z0-9_]*$} $proj_name]} {error "非法 proj_name"}
foreach key {stage1_p_ways stage1_pipe_tree stage1_bases_per_cycle jobs dry_run} {
  if {![string is integer -strict [set $key]]} {error "$key 必须为整数"}
}
if {$stage1_p_ways ni {4 16} || $stage1_pipe_tree ni {0 1}} {error "本轮只支持 stage1_p_ways=4|16、stage1_pipe_tree=0|1"}
if {$stage1_p_ways == 16 && $stage1_pipe_tree != 1} {error "P16 必须启用流水选优树 stage1_pipe_tree=1"}
if {$stage1_p_ways == 4 && $stage1_pipe_tree != 0} {error "P4 基线必须使用 stage1_pipe_tree=0"}
if {$stage1_bases_per_cycle ni {1 2 4}} {error "stage1_bases_per_cycle 只支持 1|2|4（每拍推进的碱基数）"}
if {$stage1_bases_per_cycle != 1 && $stage1_p_ways != 16} {error "K>1 只对 16/1 通路有效；P4 请保持 stage1_bases_per_cycle=1"}
if {$jobs < 1 || $jobs > 64 || $dry_run ni {0 1}} {error "jobs/dry_run 超出合法范围"}
if {![string is double -strict $clk_mhz] || $clk_mhz != 100} {error "本轮生产 PL 频率固定为100MHz"}
source [file join $repo_root hw boards load_board.tcl]
set ::dna_board_config [dna_load_board $repo_root $board]
set expected_part [dict get $::dna_board_config part]
if {$part_name eq ""} {set part_name $expected_part}
if {$part_name ne $expected_part} {error "part_name=$part_name 与板配置 $board 的 $expected_part 不匹配"}
if {$board eq "zynq_eco_7010" && $stage1_p_ways != 4} {error "7010基线只支持P4；P16请选择已验证的7020板配置"}
if {$build_dir eq ""} {
  if {$board ne "zynq_eco_7010"} {error "新板必须显式指定独立 build_dir"}
  set build_dir [file join $repo_root hw build]
}
proc dna_build_path {repo_root path} {
  if {[file pathtype $path] ne "absolute"} {set path [file join $repo_root $path]}
  return [file normalize $path]
}
set proj_wk [dna_build_path $repo_root $build_dir]
set bd_script [file join $repo_root hw scripts bd.tcl]
set xdc_file [file normalize [file join $repo_root [dict get $::dna_board_config xdc]]]
if {![file isfile $xdc_file]} {error "板配置XDC不存在：$xdc_file"}
if {$export_dir eq ""} {set export_dir [file join $proj_wk export]}
if {$report_dir eq ""} {set report_dir [file join $proj_wk reports]}
# 历史环境变量仍支持，但显式 Tcl 参数优先。
foreach pair {{export_dir DNA_EXPORT_DIR} {report_dir DNA_REPORT_DIR}} {
  lassign $pair key env_key
  if {[dict get $opts $key] eq "" && [info exists ::env($env_key)] && $::env($env_key) ne ""} {set $key $::env($env_key)}
  set $key [dna_build_path $repo_root [set $key]]
}
if {$board ne "zynq_eco_7010" || $stage1_p_ways != 4} {
  set old_build [file normalize [file join $repo_root hw build]]
  if {$proj_wk eq $old_build || $export_dir eq [file join $old_build export] || $report_dir eq [file join $old_build reports]} {
    error "新板/P16不能覆盖ECO发布目录；请指定独立输出目录"
  }
}
set xsa_out [file join $export_dir ${proj_name}.xsa]
set ip_repo [file join $repo_root hw ip]
set ::dna_stage1_p_ways $stage1_p_ways
set ::dna_stage1_pipe_tree $stage1_pipe_tree
set ::dna_stage1_bases_per_cycle $stage1_bases_per_cycle
puts "===> board=$board part=$part_name clk=${clk_mhz}MHz Stage1=$stage1_p_ways/$stage1_pipe_tree"
puts "===> root=$repo_root build_dir=$proj_wk export_dir=$export_dir report_dir=$report_dir"
if {$dry_run} {puts "BUILD_CONFIG_PASS (仅配置检查，未构建)"; exit 0}
if {![llength [info commands version]]} {error "真实构建必须在Vivado运行"}
puts "===> Vivado [version -short]"

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
launch_runs synth_1 -jobs $jobs
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
# 从零重建将无法复现已交付的收敛结果（违反 docs/05 G7/G8 可复现门禁）。
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

launch_runs impl_1 -to_step write_bitstream -jobs $jobs
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
set routed_bit "$proj_wk/$proj_name.runs/impl_1/top_bd_wrapper.bit"
if {![file isfile $routed_bit] || [file size $routed_bit] == 0} {error "实现未生成非空bit：$routed_bit"}
file copy -force $routed_bit $bit_out
puts "===> BIT: $bit_out"
foreach artifact [list $xsa_out $bit_out] {
  if {![file isfile $artifact] || [file size $artifact] == 0} {error "导出产物缺失/为空：$artifact"}
}
if {![info exists ::dna_stage1_actual]} {error "未取得实际生产IP几何/参数"}
# 硬件摘要供统一发布manifest消费；不是完整发布制品manifest。
set cfg [open [file join $export_dir hardware_build_config.txt] w]
foreach pair [list [list board_id $board] [list part $part_name] [list tool_version [version -short]] \
  [list C_STAGE1_P_WAYS [dict get $::dna_stage1_actual C_STAGE1_P_WAYS]] \
  [list C_STAGE1_PIPE_TREE [dict get $::dna_stage1_actual C_STAGE1_PIPE_TREE]] \
  [list C_STAGE1_BASES_PER_CYCLE [dict get $::dna_stage1_actual C_STAGE1_BASES_PER_CYCLE]] \
  [list READ_BPS [dict get $::dna_stage1_actual READ_BPS]] [list NUM_LC [dict get $::dna_stage1_actual NUM_LC]] \
  [list STRIDE [dict get $::dna_stage1_actual STRIDE]] [list REF_LEN [dict get $::dna_stage1_actual REF_LEN]] \
  [list BATCH [dict get $::dna_stage1_actual BATCH]] \
  [list board_config [dict get $::dna_board_config config_path]] [list build_dir $proj_wk]] {
  lassign $pair key value
  puts $cfg "$key=$value"
}
close $cfg
puts "===> HARDWARE_BUILD_DONE (需继续软件重建与整机时序/板测验收)"
