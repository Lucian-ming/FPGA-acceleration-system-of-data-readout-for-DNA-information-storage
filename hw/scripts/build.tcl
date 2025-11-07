# =========================================
# build.tcl#   vivado -mode batch -source hw/scripts/build.tcl
# 可选参数：
#   -tclargs proj_name=dna_accel part=xc7z010clg400-1 clk_mhz=100
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

# 路径
set repo_root  [file normalize [file join [pwd] ../..]]
set proj_wk    [file join $repo_root hw/build]
set bd_script  [file join $repo_root hw/scripts/bd.tcl]
set xsa_out    [file join $proj_wk export ${proj_name}.xsa]

puts "===> Vivado [version -short]"
puts "===> proj=$proj_name part=$part_name clk=${clk_mhz}MHz"
puts "===> root=$repo_root"

# 工程
file mkdir $proj_wk
create_project $proj_name $proj_wk -force
set_property part $part_name [current_project]

# 生成 BD
if {![file exists $bd_script]} { puts "FATAL: Missing $bd_script"; exit 1 }
set ::env(BD_CLK_MHZ) $clk_mhz
source $bd_script

# BD wrapper 顶层
set bdpath "$proj_wk/$proj_name.srcs/sources_1/bd/top_bd/top_bd.bd"
make_wrapper -files [get_files $bdpath] -top
add_files "$proj_wk/$proj_name.srcs/sources_1/bd/top_bd/hdl/top_bd_wrapper.v"
set_property top top_bd_wrapper [current_fileset]

# 综合/实现/bit
launch_runs synth_1 -jobs 8
wait_on_runs synth_1
launch_runs impl_1 -to_step write_bitstream -jobs 8
wait_on_runs impl_1

# 导出 XSA（含bit）
file mkdir [file dirname $xsa_out]
write_hw_platform -fixed -include_bit -force -file $xsa_out
puts "===> XSA: $xsa_out"
puts "===> DONE."
