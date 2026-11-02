# 从所选 ELF 解出 fw_build_id 地址，并逐字节读取板上 NUL 结尾的构建身份。
# 用法：xsdb read_fw_build_id.tcl --elf <ELF> --hw-server TCP:<主机>:<端口> [--nm <arm-none-eabi-nm>]
# ELF 与 hw_server endpoint 必须显式提供；脚本不使用固定地址或默认 server。

proc normalize_address {value} {
    if {![regexp {^(0[xX])?[0-9a-fA-F]+$} $value]} {
        error "fw_build_id 地址不是十六进制: $value"
    }
    if {[string match -nocase 0x* $value]} { return $value }
    return "0x$value"
}

proc parse_byte {value address} {
    set value [string trim $value]
    if {[regexp {^0[xX]([0-9a-fA-F]+)$} $value -> digits]} {
        scan $digits %x byte
    } elseif {[regexp {^[0-9]+$} $value]} {
        set byte [expr {$value + 0}]
    } else {
        error "mrd 在 $address 返回无法解析的字节值: $value"
    }
    if {$byte < 0 || $byte > 255} {
        error "mrd 在 $address 返回值超出字节范围: $value"
    }
    return $byte
}

proc read_byte {address} {
    # XSDB 的 -size b 让每次 mrd 只访问一个字节；调用方在读到 NUL 后立即停止。
    set result [mrd -value -size b $address]
    if {[llength $result] != 1} {
        error "mrd 在 $address 未返回单个字节: $result"
    }
    return [parse_byte [lindex $result 0] $address]
}

proc main {args} {
    set nm_path "/tools/Xilinx/Vitis/2022.2/gnu/aarch32/lin/gcc-arm-none-eabi/bin/arm-none-eabi-nm"
    set selected_elf ""
    set hw_server ""

    for {set i 0} {$i < [llength $args]} {incr i} {
        set arg [lindex $args $i]
        switch -- $arg {
            --elf {
                incr i
                if {$i >= [llength $args]} { error "--elf 缺少 ELF 路径" }
                set selected_elf [lindex $args $i]
            }
            --hw-server {
                incr i
                if {$i >= [llength $args]} { error "--hw-server 缺少 TCP:<主机>:<端口>" }
                set hw_server [lindex $args $i]
            }
            --nm {
                incr i
                if {$i >= [llength $args]} { error "--nm 缺少 arm-none-eabi-nm 路径" }
                set nm_path [lindex $args $i]
            }
            default { error "未知参数: $arg（必须传 --elf 与 --hw-server）" }
        }
    }

    if {$selected_elf eq ""} { error "必须显式传 --elf <ELF 路径>" }
    if {$hw_server eq ""} { error "必须显式传 --hw-server TCP:<主机>:<端口>；没有默认 hw_server" }
    if {![regexp {^TCP:([A-Za-z0-9.-]+):([0-9]{1,5})$} $hw_server -> host port]} {
        error "--hw-server 格式必须为 TCP:<主机>:<端口>: $hw_server"
    }
    if {$port < 1 || $port > 65535} { error "hw_server 端口超出 1..65535: $port" }
    if {![file isfile $selected_elf]} { error "所选 ELF 不存在: $selected_elf" }
    if {![file executable $nm_path]} { error "arm-none-eabi-nm 不存在或不可执行: $nm_path" }

    if {[catch {exec -- $nm_path $selected_elf} nm_output]} {
        error "nm 解析所选 ELF 失败（$selected_elf）: $nm_output"
    }
    set symbol_addr ""
    foreach line [split $nm_output "\n"] {
        if {[regexp {^([0-9A-Fa-f]+)[ \t]+[A-Za-z?][ \t]+fw_build_id$} $line -> address]} {
            if {$symbol_addr ne ""} { error "ELF 中 fw_build_id 符号不唯一: $selected_elf" }
            set symbol_addr [normalize_address $address]
        }
    }
    if {$symbol_addr eq ""} { error "所选 ELF 缺少 fw_build_id 符号: $selected_elf" }

    puts "FW_BUILD_ID_ELF $selected_elf"
    puts "FW_BUILD_ID_ADDR $symbol_addr"
    puts "FW_BUILD_ID_HW_SERVER $hw_server"

    set connected 0
    if {[catch {
        connect -url $hw_server
        set connected 1
        targets -set -filter {name =~ "ARM*#0"}

        set value ""
        set nul_seen 0
        # ID 固定为 16 个小写十六进制字符，最多再读第 17 个字节作为 NUL。
        # 提前遇到 NUL 会立即停止；超过 16 个非 NUL 字节则失败关闭。
        for {set offset 0} {$offset <= 16} {incr offset} {
            set address [format "0x%X" [expr {$symbol_addr + $offset}]]
            set byte [read_byte $address]
            if {$byte == 0} {
                set nul_seen 1
                break
            }
            if {$offset == 16} {
                error "fw_build_id 在 16 个字符后没有 NUL 终止符"
            }
            append value [format %c $byte]
        }
        if {!$nul_seen} { error "fw_build_id 缺少 NUL 终止符" }
        if {![regexp {^[0-9a-f]{16}$} $value]} {
            error "板上 fw_build_id 格式不是 16 个小写十六进制字符: $value"
        }
    } message]} {
        if {$connected} { catch {disconnect} }
        error $message
    }
    catch {disconnect}
    puts "FW_BUILD_ID $value"
    return 0
}

# ⚠️ 必须写 {*}$argv 而不是 $argv：Tcl 的变量替换**不拆词**，
# `main $argv` 会把整个列表当成**一个**参数传进去（参数解析必然失败）。
# {*} 是 Tcl 8.5+ 的展开算子，等价于把列表拆成多个参数。
if {[catch {main {*}$argv} message]} {
    puts stderr "FW_BUILD_ID_ERROR $message"
    exit 1
}
exit 0
