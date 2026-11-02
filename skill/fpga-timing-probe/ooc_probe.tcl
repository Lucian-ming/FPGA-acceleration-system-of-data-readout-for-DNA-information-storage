# =============================================================
# ooc_probe.tcl — 对单个 IP 顶层跑综合，检查可综合性、资源与时序
#
# 用途：RTL 改动之后确认「能综合、装得下、时序收敛」。仿真通过不代表能上板。
#
#   SYNTH_PART=<器件完整型号> vivado -mode batch -source ooc_probe.tcl \
#       -tclargs <顶层模块名> <时钟MHz> <文件...>
#
# 例：
#   SYNTH_PART=xc7z020clg400-2 vivado -mode batch -source ooc_probe.tcl -tclargs \
#       my_top 100 rtl/my_top.v
#
# 必需环境变量：
#   SYNTH_PART=xc7z020clg400-2      Vivado 器件库中的完整器件型号；不会默认选本项目器件
# 可选环境变量：
#   SYNTH_GENERICS="WIDTH=16 ..."  顶层参数覆盖，逐个传给 synth_design -generic
#   SYNTH_VERILOG_DEFINE="MACRO=1 ..."  编译期开关，逐个传给 synth_design -verilog_define
#   SYNTH_TAG=z020_w16              报告目录后缀，避免多次摸底互相覆盖
#   SYNTH_OUT_ROOT=logs/vivado/id/reports  报告根目录（默认 build/）
#   SYNTH_IMPL=1                    再跑 OOC 布局布线，给出布线后 WNS（综合后 WNS 偏乐观：
#                                   实测案例：同一模块综合后 +2.197 ns，整机布线后只剩约 +0.2 ns）
# 成功：打印资源、WNS/WHS 与报告目录；SYNTH_IMPL=1 时非负 slack 且有路径才算 OOC 时序通过。
# 失败：器件/参数/文件无效时 exit 1；无时钟/路径或布线后 slack 为负时 exit 2。
#       综合-only 负 slack 仅打印估算，不会因此失败；综合-only exit 0 不代表时序通过。
# 例（换器件 / 换参数摸底）：
#   SYNTH_PART=xc7z020clg400-2 SYNTH_GENERICS="WIDTH=16" SYNTH_TAG=z020_w16 \
#     vivado -mode batch -source ooc_probe.tcl -tclargs \
#       my_top 100 rtl/my_top.v
# =============================================================

set part_name ""
if {[info exists ::env(SYNTH_PART)] && $::env(SYNTH_PART) ne ""} { set part_name $::env(SYNTH_PART) }
if {$part_name eq ""} {
    puts stderr "FAIL: 必须设置 SYNTH_PART=<Vivado 器件完整型号>，避免误用其他项目的器件"
    exit 1
}
set generics {}
if {[info exists ::env(SYNTH_GENERICS)]} {
    foreach g $::env(SYNTH_GENERICS) { lappend generics -generic $g }
}
set verilog_defines {}
if {[info exists ::env(SYNTH_VERILOG_DEFINE)] && $::env(SYNTH_VERILOG_DEFINE) ne ""} {
    foreach d $::env(SYNTH_VERILOG_DEFINE) { lappend verilog_defines -verilog_define $d }
}

if {[llength $argv] < 3} {
    puts stderr "用法: SYNTH_PART=<器件> vivado -mode batch -source ooc_probe.tcl -tclargs <top> <clk_mhz> <file.v> \[file.v ...\]"
    exit 1
}
set top     [lindex $argv 0]
set clk_mhz [lindex $argv 1]
set files   [lrange $argv 2 end]
if {![string is double -strict $clk_mhz] || $clk_mhz <= 0} {
    puts stderr "FAIL: clk_mhz 必须是大于 0 的数字，收到 '$clk_mhz'"
    exit 1
}
set period  [expr {1000.0 / $clk_mhz}]

foreach f $files {
    if {![file isfile $f]} {
        puts stderr "FAIL: HDL 文件不存在或不是普通文件: $f"
        exit 1
    }
}

set outroot "build"
if {[info exists ::env(SYNTH_OUT_ROOT)] && $::env(SYNTH_OUT_ROOT) ne ""} { set outroot $::env(SYNTH_OUT_ROOT) }
set outdir [file join $outroot "synth_$top"]
if {[info exists ::env(SYNTH_TAG)] && $::env(SYNTH_TAG) ne ""} { append outdir "_$::env(SYNTH_TAG)" }
file mkdir $outdir

puts "===> 综合 $top  器件 $part_name  时钟 ${clk_mhz}MHz (周期 ${period}ns)  参数 $generics  defines $verilog_defines"

create_project -in_memory -part $part_name
foreach f $files {
    puts "     读入 $f"
    read_verilog $f
}

set do_impl [expr {[info exists ::env(SYNTH_IMPL)] && $::env(SYNTH_IMPL) eq "1"}]
set failed 0
set ooc {}
if {$do_impl} { set ooc {-mode out_of_context} }
synth_design -top $top -part $part_name -flatten_hierarchy rebuilt {*}$ooc {*}$generics {*}$verilog_defines

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
if {$n == 0} {
    puts "     FAIL: 未找到时钟端口，时序报告无意义"
    exit 2
}
opt_design -quiet
if {$do_impl} {
    place_design
    phys_opt_design
    route_design
    puts "     已完成 OOC 布局布线（下面的资源与 WNS 为布线后数据）"
}

puts "\n===== 资源占用 ($top) ====="
report_utilization -hierarchical -file $outdir/util_hier.rpt
report_utilization -file $outdir/util.rpt
set r [open $outdir/util.rpt r]
set txt [read $r]; close $r
foreach line [split $txt "\n"] {
    if {[regexp {\| (Slice LUTs|LUT as Logic|LUT as Memory|Slice Registers|Register as Flip Flop|Block RAM Tile|RAMB36|RAMB18|DSPs)\s*\|} $line]} {
        puts "  $line"
    }
}

puts "\n===== 时序 ($top) ====="
report_timing_summary -file $outdir/timing.rpt -max_paths 5
set setup_paths [get_timing_paths -delay_type max -max_paths 1]
set hold_paths  [get_timing_paths -delay_type min -max_paths 1]
set wns ""
set whs ""
if {[llength $setup_paths] > 0} { set wns [get_property SLACK $setup_paths] }
if {[llength $hold_paths] > 0} { set whs [get_property SLACK $hold_paths] }

puts "  WNS = $wns ns   WHS = $whs ns"
if {$wns eq "" || $whs eq ""} {
    puts "  FAIL: 找不到 setup 或 hold 时序路径"
    set failed 1
} elseif {$wns < 0 || $whs < 0} {
    if {$do_impl} {
        puts "  FAIL: 布线后 setup/hold 未收敛"
    } else {
        puts "  综合-only 估算为负；此结果不构成时序验收判据"
    }
    if {$wns < 0} {
        puts "  setup 最高频率估算约 [format %.1f [expr {1000.0/($period - $wns)}]] MHz"
    }
    if {$do_impl} { set failed 1 }
} else {
    puts "  ✓ setup/hold 时序收敛"
}

puts "\n报告已写入 $outdir/"
if {$failed} { exit 2 }
exit 0
