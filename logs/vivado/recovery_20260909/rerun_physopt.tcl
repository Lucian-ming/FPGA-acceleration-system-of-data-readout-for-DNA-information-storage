# 方案(c)：零 RTL 改动，仅换 implementation 策略为 Performance_ExplorePostRoutePhysOpt，
# 验证能否自动补回 0.252 ns。复用已有 synth_1，不重跑综合。
set root /home/lucian/projects/FPGA/FpgaAccelerationSystemOfDataReadout
set outdir $root/logs/vivado/recovery_20260909/physopt

open_project $root/hw/build/dna_accel.xpr

# 综合结果必须可复用，否则本次对比不成立（策略变量之外不得引入第二个变量）
if {[get_property PROGRESS [get_runs synth_1]] ne "100%"} {
    puts "===> ERROR: synth_1 未完成，终止（避免引入综合差异）"
    exit 1
}
puts "===> synth_1 复用 OK，未重跑综合"

set old_strategy [get_property STRATEGY [get_runs impl_1]]
puts "===> 原 impl 策略: $old_strategy"
set_property strategy Performance_ExplorePostRoutePhysOpt [get_runs impl_1]
puts "===> 新 impl 策略: [get_property STRATEGY [get_runs impl_1]]"

reset_run impl_1
launch_runs impl_1 -to_step write_bitstream -jobs 8
wait_on_runs impl_1

if {[get_property PROGRESS [get_runs impl_1]] ne "100%"} {
    puts "===> ERROR: impl_1 未完成 status=[get_property STATUS [get_runs impl_1]]"
    exit 1
}

open_run impl_1
report_timing_summary -max_paths 10 -file $outdir/timing.rpt
report_utilization -hierarchical -file $outdir/util.rpt

set wns [get_property SLACK [get_timing_paths -delay_type max -max_paths 1]]
set paths [get_timing_paths -delay_type max -slack_lesser_than 0 -max_paths 5000 -nworst 1 -sort_by slack]
set fh [open $outdir/summary.log w]
puts $fh "design   : dna_accel (方案c Performance_ExplorePostRoutePhysOpt)"
puts $fh "date     : [clock format [clock seconds] -format {%Y-%m-%d %H:%M:%S}]"
puts $fh "strategy : [get_property STRATEGY [get_runs impl_1]]  (原: $old_strategy)"
puts $fh "WNS      : $wns ns"
puts $fh "failing_endpoints : [llength $paths]"
if {$wns >= 0} {
    puts $fh "结论     : ✓ 100MHz 收敛，方案(c)成功，无需改 RTL/BD"
} else {
    puts $fh "结论     : ✗ 仍未收敛（基线 -0.252ns），需转入 (b) Register Slice 或 (a) WVALID 打拍"
}
close $fh

set fh2 [open $outdir/failing_endpoints_complete.tsv w]
puts $fh2 "slack\tstartpoint\tendpoint"
foreach p $paths {
    puts $fh2 "[get_property SLACK $p]\t[get_property STARTPOINT_PIN $p]\t[get_property ENDPOINT_PIN $p]"
}
close $fh2
puts "===> RESULT WNS=$wns failing_endpoints=[llength $paths]"
puts "===> DONE."
