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
#
# 可选环境变量：
#   SYNTH_BOARD=bkb220              选择 hw/boards/<board>.tcl profile（默认 bkb220）
#   SYNTH_PART=...                  显式覆盖器件（默认取板卡 profile 的 part）
#   SYNTH_GENERICS="P_WAYS=16 ..."  顶层参数覆盖，逐个传给 synth_design -generic
#   SYNTH_TAG=z020_p16              报告目录后缀，避免多次摸底互相覆盖
#   SYNTH_IMPL=1                    再跑 OOC 布局布线，给出布线后 WNS（综合后 WNS 偏乐观：
#                                   4-way 综合后 +2.197 ns，整机布线后只剩约 +0.2 ns）
# 例（BKB220 7020 摸底；器件从 profile 读取）：
#   SYNTH_BOARD=bkb220 SYNTH_GENERICS="P_WAYS=16" SYNTH_TAG=bkb220_p16 \
#     vivado -mode batch -source hw/scripts/synth_check.tcl -tclargs \
#       srpe_batch_pway 100 hw/experimental/srpe_batch_pway.v
# =============================================================

set _here [file normalize [file dirname [info script]]]
set repo_root [file normalize "$_here/../.."]
source [file join $repo_root hw boards load_board.tcl]
set board_id bkb220
if {[info exists ::env(SYNTH_BOARD)] && $::env(SYNTH_BOARD) ne ""} {
    set board_id $::env(SYNTH_BOARD)
}
set board_config [dna_load_board $repo_root $board_id]
set part_name [dict get $board_config part]
if {[info exists ::env(SYNTH_PART)] && $::env(SYNTH_PART) ne ""} { set part_name $::env(SYNTH_PART) }
set generics {}
if {[info exists ::env(SYNTH_GENERICS)]} {
    foreach g $::env(SYNTH_GENERICS) { lappend generics -generic $g }
}

if {[llength $argv] < 3} {
    puts "用法: -tclargs <top> <clk_mhz> <file.v> \[file.v ...\]"
    exit 1
}
set top     [lindex $argv 0]
set clk_mhz [lindex $argv 1]
set files   [lrange $argv 2 end]
set period  [expr {1000.0 / $clk_mhz}]

set outdir "hw/build/synth_$top"
if {[info exists ::env(SYNTH_TAG)] && $::env(SYNTH_TAG) ne ""} { append outdir "_$::env(SYNTH_TAG)" }
file mkdir $outdir

puts "===> 综合 $top  器件 $part_name  时钟 ${clk_mhz}MHz (周期 ${period}ns)  参数 $generics"

create_project -in_memory -part $part_name
foreach f $files {
    puts "     读入 $f"
    read_verilog $f
}

set do_impl [expr {[info exists ::env(SYNTH_IMPL)] && $::env(SYNTH_IMPL) eq "1"}]
set ooc {}
if {$do_impl} { set ooc {-mode out_of_context} }
synth_design -top $top -part $part_name -flatten_hierarchy rebuilt {*}$ooc {*}$generics

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
set wns [get_property SLACK [get_timing_paths -delay_type max -max_paths 1]]
puts "  WNS = $wns ns   (>=0 表示在 ${clk_mhz}MHz 下收敛)"
if {$wns ne "" && $wns < 0} {
    puts "  ⚠️  时序未收敛，最高可用频率约 [format %.1f [expr {1000.0/($period - $wns)}]] MHz"
} else {
    puts "  ✓ 时序收敛"
}

puts "\n报告已写入 $outdir/"
exit 0
