# =============================================================
# synth_check.tcl — 对单个 IP 顶层跑综合，检查可综合性、资源与时序
#
# 用途：RTL 改动之后确认「能综合、装得下、时序收敛」。仿真通过不代表能上板。
#
#   vivado -mode batch -source hw/scripts/synth_check.tcl -tclargs <顶层模块名> <时钟MHz> <文件...>
#
# 例：
#   vivado -mode batch -source hw/scripts/synth_check.tcl -tclargs \
#       srpe_batch 100 hw/ip/Dna_accelerator_core_1_0/hdl/srpe_batch.v
# =============================================================

set part_name "xc7z010clg400-1"

if {[llength $argv] < 3} {
    puts "用法: -tclargs <top> <clk_mhz> <file.v> \[file.v ...\]"
    exit 1
}
set top     [lindex $argv 0]
set clk_mhz [lindex $argv 1]
set files   [lrange $argv 2 end]
set period  [expr {1000.0 / $clk_mhz}]

set outdir "hw/build/synth_$top"
file mkdir $outdir

puts "===> 综合 $top  器件 $part_name  时钟 ${clk_mhz}MHz (周期 ${period}ns)"

create_project -in_memory -part $part_name
foreach f $files {
    puts "     读入 $f"
    read_verilog $f
}

synth_design -top $top -part $part_name -flatten_hierarchy rebuilt

# 综合后再约束：自动给所有时钟端口（clk / *ACLK）建时钟
set clk_ports [get_ports -quiet -filter {DIRECTION == IN} *]
set n 0
foreach pt $clk_ports {
    set nm [get_property NAME $pt]
    if {[string match -nocase "clk" $nm] || [string match -nocase "*aclk*" $nm]} {
        create_clock -period $period -name clk_$n [get_ports $nm]
        puts "     约束时钟 $nm @ ${clk_mhz}MHz"
        incr n
    }
}
if {$n == 0} { puts "     ⚠️ 未找到时钟端口，时序报告无意义" }
opt_design -quiet

puts "\n===== 资源占用 ($top) ====="
report_utilization -hierarchical -file $outdir/util.rpt
set r [open $outdir/util.rpt r]
set txt [read $r]; close $r
foreach line [split $txt "\n"] {
    if {[regexp {\| (Slice LUTs|LUT as Logic|LUT as Memory|Slice Registers|Register as Flip Flop|Block RAM Tile|RAMB36|RAMB18|DSPs)\s*\|} $line]} {
        puts "  $line"
    }
}

puts "\n===== 时序 ($top) ====="
report_timing_summary -file $outdir/timing.rpt -max_paths 5
set wns [get_property SLACK [get_timing_paths -delay_type max -max_paths 1]]
puts "  WNS = $wns ns   (>=0 表示在 ${clk_mhz}MHz 下收敛)"
if {$wns ne "" && $wns < 0} {
    puts "  ⚠️  时序未收敛，最高可用频率约 [format %.1f [expr {1000.0/($period - $wns)}]] MHz"
} else {
    puts "  ✓ 时序收敛"
}

puts "\n报告已写入 $outdir/"
exit 0
