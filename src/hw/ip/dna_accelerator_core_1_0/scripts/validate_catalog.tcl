set repo [file normalize [lindex $argv 0]]
set run [file normalize [lindex $argv 1]]
file mkdir $run
if {[file exists [file join $run project]]} {error "Use a fresh run directory; previous evidence must be retained"}
# Icarus2005不识别Vivado生成的attribute长字符串反斜杠换行；只在run副本
# 拼接延续行。原wrapper、全部参数和源文件保留，不改生产源码。
proc portable_wrapper {run name content} {
    set path [file join $run ${name}.portable.v]
    set fd [open $path w]
    puts -nonewline $fd [string map [list [format "%c%c" 92 10] ""] $content]
    close $fd
    return $path
}
set component [file join $repo hw ip dna_accelerator_core component.xml]
file copy -force $component [file join $run component.before.xml]
set core [ipx::open_core $component]
ipx::check_integrity $core
if {[lindex $argv 2] eq "1"} {
    ipx::update_checksums $core
    ipx::save_core $core
}
ipx::unload_core $core
file copy -force $component [file join $run component.after.xml]

create_project stage1_catalog [file join $run project] -part xc7z020clg400-1 -force
set_property target_language Verilog [current_project]
set_property ip_repo_paths [list [file join $repo hw ip]] [current_project]
update_ip_catalog
create_bd_design stage1_config_check
set cell [create_bd_cell -type ip -vlnv xilinx.com:user:dna_accelerator_core:1.0 dna_accelerator_core_0]
if {[get_property CONFIG.C_STAGE1_P_WAYS $cell] != 4 || [get_property CONFIG.C_STAGE1_PIPE_TREE $cell] != 0} {
    error "BD default is not P4=4/0"
}
puts "[format {STAGE1-CATALOG: BD default=%s/%s} [get_property CONFIG.C_STAGE1_P_WAYS $cell] [get_property CONFIG.C_STAGE1_PIPE_TREE $cell]]"
set_property -dict {CONFIG.C_STAGE1_P_WAYS 16 CONFIG.C_STAGE1_PIPE_TREE 1} $cell
if {[get_property CONFIG.C_STAGE1_P_WAYS $cell] != 16 || [get_property CONFIG.C_STAGE1_PIPE_TREE $cell] != 1} {
    error "BD set_property dict failed P16=16/1"
}
puts "STAGE1-CATALOG: BD dictionary P16=16/1 PASS"
save_bd_design

foreach {name ways pipe} {dna_p4 4 0 dna_p16 16 1} {
    create_ip -name dna_accelerator_core -vendor xilinx.com -library user -version 1.0 -module_name $name
    set ip [get_ips $name]
    if {$ways == 16} {
        set_property -dict {CONFIG.C_STAGE1_P_WAYS 16 CONFIG.C_STAGE1_PIPE_TREE 1} $ip
    }
    if {[get_property CONFIG.C_STAGE1_P_WAYS $ip] != $ways || [get_property CONFIG.C_STAGE1_PIPE_TREE $ip] != $pipe} {
        error "IP $name config mismatch"
    }
    generate_target all $ip
    set ipdir [file join $run project stage1_catalog.gen sources_1 ip $name]
    set wrappers [glob -nocomplain -directory $ipdir synth/*.v]
    if {[llength $wrappers] != 1} { error "IP $name synthesis wrapper missing: $ipdir" }
    set fd [open [lindex $wrappers 0] r]
    set content [read $fd]
    close $fd
    foreach {param expected} [list C_STAGE1_P_WAYS $ways C_STAGE1_PIPE_TREE $pipe READ_BPS 150 NUM_LC 50 STRIDE 807 REF_LEN 957 BATCH 64] {
        set pattern [format {\.%s\s*\(\s*%s\s*\)} $param $expected]
        if {![regexp $pattern $content]} { error "Generated wrapper $name lacks $param=$expected" }
    }
    set portable [portable_wrapper $run $name $content]
    exec sha256sum [lindex $wrappers 0] $portable {*}[glob -directory $ipdir hdl/*.v] > [file join $run ${name}.sources.sha256]
    exec iverilog -g2005 -t null -s $name $portable {*}[glob -directory $ipdir hdl/*.v]
    puts "STAGE1-CATALOG: generated $name wrapper $ways/$pipe SE150 PASS"
}
create_ip -name dna_accelerator_core -vendor xilinx.com -library user -version 1.0 -module_name dna_invalid
set bad [get_ips dna_invalid]
set rejected [catch {set_property -dict {CONFIG.C_STAGE1_P_WAYS 16 CONFIG.C_STAGE1_PIPE_TREE 0} $bad} reason]
if {!$rejected} {
    generate_target all $bad
    puts "STAGE1-CATALOG: NOTE: catalog saves16/0; CLI/RTL guards must reject it"
    set ipdir [file join $run project stage1_catalog.gen sources_1 ip dna_invalid]
    set fd [open [file join $ipdir synth dna_invalid.v] r]
    set content [read $fd]
    close $fd
    set portable [portable_wrapper $run dna_invalid $content]
    set rejected [catch {exec iverilog -g2005 -t null -s dna_invalid $portable {*}[glob -directory $ipdir hdl/*.v]} reason]
    if {![string match *STAGE1_CONFIGURATION_MUST_BE_P4_OR_P16_PIPELINED* $reason]} {
        error "Illegal configuration failed for unexpected reason: $reason"
    }
}
if {!$rejected} { error "Invalid P16=16/0 escaped actual RTL elaboration" }
puts "STAGE1-CATALOG: invalid16/0 actual RTL REJECTED: $reason"
report_ip_status -file [file join $run ip_status.rpt]
puts "STAGE1-CATALOG: PASS"
close_project
