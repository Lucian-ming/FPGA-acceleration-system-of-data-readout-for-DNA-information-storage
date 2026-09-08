# -nworst 1 保证「每个失败端点只取最差 1 条」，从而覆盖全部 43 个失败端点
set outdir /home/lucian/projects/FPGA/FpgaAccelerationSystemOfDataReadout/logs/vivado/recovery_20260909
open_checkpoint /home/lucian/projects/FPGA/FpgaAccelerationSystemOfDataReadout/hw/build/dna_accel.runs/impl_1/top_bd_wrapper_routed.dcp
set paths [get_timing_paths -delay_type max -slack_lesser_than 0 -max_paths 5000 -nworst 1 -sort_by slack]
puts "===> ENDPOINTS_FOUND [llength $paths]"
set fh [open $outdir/failing_endpoints_complete.tsv w]
puts $fh "slack\tstartpoint\tendpoint"
set n_acc 0; set n_other 0
foreach p $paths {
    set s [get_property SLACK $p]
    set sp [get_property STARTPOINT_PIN $p]
    set ep [get_property ENDPOINT_PIN $p]
    puts $fh "$s\t$sp\t$ep"
    if {[regexp {Dna_accelerator_core|srpe_batch|voter|best_|sel_tree|winner} "$sp $ep"]} {incr n_acc} else {incr n_other}
}
close $fh
puts "===> COMPLETE_VERDICT endpoints=[llength $paths] accelerator=$n_acc other=$n_other"
puts "===> DONE."
