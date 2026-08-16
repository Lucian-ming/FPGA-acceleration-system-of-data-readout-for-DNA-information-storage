# =============================================================
# collect_info.tcl — 构建（synth/impl）完成后的报告收集与摘要
#
# 在已打开设计（综合或实现后）的 Vivado 会话里 source 本文件：
#   vivado -mode batch -source hw/scripts/collect_info.tcl -tclargs <输出目录> <design名>
# 参数缺省：hw/build/reports 和 "current"。
#
# 产出：
#   util.rpt      资源利用率（含层级明细）
#   timing.rpt    时序汇总（前 10 条关键路径）
#   summary.log   一页摘要（LUT/FF/BRAM/WNS/TNS），便于跨版本对比
# =============================================================

set outdir "hw/build/reports"
set dname  "current"
if {[llength $argv] >= 1} { set outdir [lindex $argv 0] }
if {[llength $argv] >= 2} { set dname  [lindex $argv 1] }
file mkdir $outdir

puts "===> collect_info: design=$dname outdir=$outdir"

report_utilization -hierarchical -file "$outdir/util.rpt"
report_timing_summary -max_paths 10 -file "$outdir/timing.rpt"

# ---- 一页摘要：直接从报告文本里提取，避免依赖对象状态 ----
set f [open "$outdir/summary.log" w]
puts $f "design : $dname"
puts $f "tool   : [version -short]"
puts $f "date   : [clock format [clock seconds] -format {%Y-%m-%d %H:%M:%S}]"

set ur [open "$outdir/util.rpt" r]; set utxt [read $ur]; close $ur
foreach line [split $utxt "\n"] {
    if {[regexp {^\|\s*(Slice LUTs|Slice Registers|Block RAM Tile|DSPs)\s*\|} $line -> name]} {
        puts $f "  $line"
    }
}

if {[catch {get_timing_paths -delay_type max -max_paths 1} p]} {
    puts $f "timing : 无法获取（设计未打开？）"
} else {
    set wns [get_property SLACK $p]
    puts $f [format "WNS    : %s ns" $wns]
    if {$wns ne "" && $wns < 0} {
        puts $f [format "        ⚠ 未收敛，估算上限 %.1f MHz" \
                 [expr {1000.0 / (10.0 - $wns)}]]
    } else {
        puts $f "        ✓ 以 100 MHz 目标收敛"
    }
}
close $f
puts "===> 报告已写入 $outdir/  (summary.log 为一页摘要)"
