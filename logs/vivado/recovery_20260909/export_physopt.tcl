# 导出方案(c)收敛版制品到独立目录，绝不触碰旧的 hw/build/export_4way/（那里是未收敛版证据）
set root /home/lucian/projects/FPGA/FpgaAccelerationSystemOfDataReadout
set export_dir $root/hw/build/export_4way_physopt
set proj $root/hw/build/dna_accel.xpr

open_project $proj

# 硬校验：必须是收敛版 impl，且策略正确，否则拒绝导出（防止误导出未收敛比特流）
if {[get_property PROGRESS [get_runs impl_1]] ne "100%"} {
    puts "===> ERROR: impl_1 未完成，拒绝导出"; exit 1
}
set strat [get_property STRATEGY [get_runs impl_1]]
if {$strat ne "Performance_ExplorePostRoutePhysOpt"} {
    puts "===> ERROR: impl_1 策略为 '$strat'，不是收敛版策略，拒绝导出"; exit 1
}
open_run impl_1
set wns [get_property SLACK [get_timing_paths -delay_type max -max_paths 1]]
if {$wns < 0} {
    puts "===> ERROR: WNS=$wns < 0，未收敛，拒绝导出"; exit 1
}
puts "===> 校验通过 strategy=$strat WNS=$wns"

file mkdir $export_dir
set xsa_out [file join $export_dir dna_accel.xsa]
write_hw_platform -fixed -include_bit -force -file $xsa_out
puts "===> XSA: $xsa_out"

set src_bit $root/hw/build/dna_accel.runs/impl_1/top_bd_wrapper.bit
set bit_out [file join $export_dir top_bd_wrapper.bit]
if {![file exists $src_bit]} { puts "===> ERROR: 找不到 $src_bit"; exit 1 }
file copy -force $src_bit $bit_out
puts "===> BIT: $bit_out"

# 报告一并留在制品目录，便于板测方核对自己烧的是哪一版
file mkdir $export_dir/reports
report_timing_summary -max_paths 10 -file $export_dir/reports/timing.rpt
report_utilization -hierarchical -file $export_dir/reports/util.rpt
set fh [open $export_dir/reports/summary.log w]
puts $fh "design   : dna_accel 4-way (方案c 收敛版)"
puts $fh "date     : [clock format [clock seconds] -format {%Y-%m-%d %H:%M:%S}]"
puts $fh "tool     : 2022.2"
puts $fh "strategy : $strat"
puts $fh "WNS      : $wns ns"
puts $fh "结论     : ✓ 100MHz 收敛 (对照: 默认策略同一设计 WNS=-0.252ns 未收敛)"
puts $fh "警告     : 整机静态时序收敛 != 板级实测证据，上板功能验证仍须单独进行"
close $fh
puts "===> RESULT WNS=$wns"
puts "===> EXPORT_DONE."
