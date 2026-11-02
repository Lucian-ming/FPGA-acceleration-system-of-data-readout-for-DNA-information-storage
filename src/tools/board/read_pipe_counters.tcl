# XSDB 只读本轮固件 ELF 中的 pipeline poll 计数器。
#
# 用法（在任务完成后立即读取）：
#   xsdb tools/board/read_pipe_counters.tcl --elf <本轮制品目录>/dna_lwip_app.elf
#   xsdb tools/board/read_pipe_counters.tcl --addresses <PIPE> <WM> <STATE>
#
# 第二种显式地址模式只供符号工具不可用时排错；脚本没有旧地址兜底。
# 默认 nm 是 WSL Vitis 2022.2 的 ARM GCC 工具。可用 --nm 覆盖。

set nm_path "/tools/Xilinx/Vitis/2022.2/gnu/aarch32/lin/gcc-arm-none-eabi/bin/arm-none-eabi-nm"
set selected_elf ""
set explicit_addresses {}

for {set i 0} {$i < [llength $argv]} {incr i} {
    set arg [lindex $argv $i]
    switch -- $arg {
        --elf {
            incr i
            if {$i >= [llength $argv]} { error "--elf 缺少 ELF 路径" }
            set selected_elf [lindex $argv $i]
        }
        --nm {
            incr i
            if {$i >= [llength $argv]} { error "--nm 缺少 nm 路径" }
            set nm_path [lindex $argv $i]
        }
        --addresses {
            if {$i + 3 >= [llength $argv]} {
                error "--addresses 必须依次给出 PIPE_POLL_STEPS WM_POLL_STEPS PIPE_STATE 三个地址"
            }
            set explicit_addresses [lrange $argv [expr {$i + 1}] [expr {$i + 3}]]
            incr i 3
        }
        default { error "未知参数: $arg（用 --elf ELF 或 --addresses PIPE WM STATE）" }
    }
}

proc normalize_address {value label} {
    if {![regexp {^(0[xX])?[0-9a-fA-F]+$} $value]} {
        error "$label 地址不是十六进制: $value"
    }
    if {[string match -nocase 0x* $value]} { return $value }
    return "0x$value"
}

if {[llength $explicit_addresses] == 3} {
    if {$selected_elf ne ""} { error "--elf 与 --addresses 不能同时使用" }
    lassign $explicit_addresses pipe_addr wm_addr state_addr
    set pipe_addr [normalize_address $pipe_addr PIPE_POLL_STEPS]
    set wm_addr [normalize_address $wm_addr WM_POLL_STEPS]
    set state_addr [normalize_address $state_addr PIPE_STATE]
} else {
    if {$selected_elf eq "" && [info exists env(G3_COUNTER_ELF)]} {
        set selected_elf $env(G3_COUNTER_ELF)
    }
    if {$selected_elf eq ""} {
        error "必须传本轮选中的 --elf；没有旧 B27 地址回退。排错时可显式传 --addresses PIPE WM STATE。"
    }
    if {![file isfile $selected_elf]} { error "本轮 ELF 不存在: $selected_elf" }
    if {![file executable $nm_path]} { error "arm-none-eabi-nm 不存在或不可执行: $nm_path" }

    if {[catch {exec -- $nm_path $selected_elf} nm_output]} {
        error "nm 解析本轮 ELF 失败（$selected_elf）: $nm_output"
    }
    array set symbols {}
    foreach line [split $nm_output "\n"] {
        if {[regexp {^([0-9A-Fa-f]+)[ \t]+[A-Za-z?][ \t]+(pipe_poll_steps|wm_poll_steps|pipe_state)$} \
                $line -> address symbol]} {
            set symbols($symbol) "0x$address"
        }
    }
    foreach symbol {pipe_poll_steps wm_poll_steps pipe_state} {
        if {![info exists symbols($symbol)]} {
            error "本轮 ELF 缺少符号 $symbol: $selected_elf"
        }
    }
    set pipe_addr $symbols(pipe_poll_steps)
    set wm_addr $symbols(wm_poll_steps)
    set state_addr $symbols(pipe_state)
    puts "PIPE_COUNTER_ELF $selected_elf"
    puts "PIPE_COUNTER_NM  $nm_path"
}

puts "PIPE_COUNTER_ADDR pipe_poll_steps=$pipe_addr wm_poll_steps=$wm_addr pipe_state=$state_addr"
connect
targets -set -filter {name =~ "ARM*#0"}
puts "PIPE_POLL_STEPS [format %u [lindex [mrd -value $pipe_addr] 0]]"
puts "WM_POLL_STEPS   [format %u [lindex [mrd -value $wm_addr] 0]]"
puts "PIPE_STATE      [format %u [lindex [mrd -value $state_addr] 0]]"
disconnect
exit
