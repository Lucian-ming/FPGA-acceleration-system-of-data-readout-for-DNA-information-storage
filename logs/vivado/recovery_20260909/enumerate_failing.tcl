# 枚举 routed DCP 中全部负裕量 setup 端点，按层次归类，
# 用于回答「关键路径是否落在 4-way 选优树上」
set outdir /home/lucian/projects/FPGA/FpgaAccelerationSystemOfDataReadout/logs/vivado/recovery_20260909
open_checkpoint /home/lucian/projects/FPGA/FpgaAccelerationSystemOfDataReadout/hw/build/dna_accel.runs/impl_1/top_bd_wrapper_routed.dcp

# 1) 全部失败路径明细（足够大的 max_paths 覆盖 43 个失败端点）
report_timing -delay_type max -slack_lesser_than 0 -max_paths 200 -nworst 200 \
              -sort_by slack -file $outdir/failing_paths_all.rpt

# 2) 机器可读的 startpoint/endpoint/slack 三元组
set fh [open $outdir/failing_endpoints.tsv w]
puts $fh "slack\tstartpoint\tendpoint"
set paths [get_timing_paths -delay_type max -slack_lesser_than 0 -max_paths 200 -nworst 200 -sort_by slack]
puts "===> NUM_FAILING_PATHS [llength $paths]"
foreach p $paths {
    set s  [get_property SLACK $p]
    set sp [get_property STARTPOINT_PIN $p]
    set ep [get_property ENDPOINT_PIN $p]
    puts $fh "$s\t$sp\t$ep"
}
close $fh

# 3) 判定：是否有任何失败路径穿过 4-way 加速核 / 选优树
set fh2 [open $outdir/verdict.txt w]
set n_acc 0
set n_other 0
foreach p $paths {
    set sp [get_property STARTPOINT_PIN $p]
    set ep [get_property ENDPOINT_PIN $p]
    if {[regexp {Dna_accelerator_core|srpe_batch|voter|best_|sel_tree|winner} "$sp $ep"]} {
        incr n_acc
    } else {
        incr n_other
    }
}
puts $fh2 "failing_paths_total   : [llength $paths]"
puts $fh2 "touching_accelerator  : $n_acc"
puts $fh2 "elsewhere             : $n_other"
close $fh2
puts "===> VERDICT accelerator=$n_acc other=$n_other"

# 4) 资源与拥塞
report_utilization -file $outdir/util_flat.rpt
report_design_analysis -congestion -file $outdir/congestion.rpt
puts "===> DONE."
