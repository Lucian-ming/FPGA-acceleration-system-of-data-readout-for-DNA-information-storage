# =========================================
# create_vitis.tcl
# 用法（仓库根目录）：
#   xsct sw/scripts/create_vitis.tcl
# 可选参数（-tclargs 覆盖）：
#   -tclargs xsa=/abs/path/to/xxx.xsa ws=/abs/path/to/workspace app=my_app plat=my_platform dom=my_domain ip=192.168.1.10 mask=255.255.255.0 gw=192.168.1.1
# =========================================

# ---------- 默认参数 ----------
set plat "dna_platform"
set dom  "standalone_domain"
set app  "dna_lwip_app"
set ws   "[file normalize ../../sw/workspace]"

# 自动搜 XSA（优先使用 -tclargs 指定）
proc _find_xsa {} {
  set cand {}
  foreach p {
    ../../hw/build/export/*.xsa
    ../hw/build/export/*.xsa
    ./hw/build/export/*.xsa
    ../../hw/**/*.xsa
  } {
    set g [glob -nocomplain -types f $p]
    set cand [concat $cand $g]
  }
  if {[llength $cand] > 0} {
    return [file normalize [lindex $cand 0]]
  }
  return ""
}

set xsa  ""
set ip   "192.168.1.10"
set mask "255.255.255.0"
set gw   "192.168.1.1"

# ---------- 解析 -tclargs ----------
proc _arg {name default} {
  upvar $name var
  if {![info exists var]} { set var $default }
  foreach a $::argv {
    if {[string match "${name}=*" $a]} {
      set var [string range $a [expr {[string length "${name}="]}] end]
    }
  }
}
_arg plat $plat
_arg dom  $dom
_arg app  $app
_arg ws   $ws
_arg xsa  $xsa
_arg ip   $ip
_arg mask $mask
_arg gw   $gw

if {$xsa eq ""} { set xsa [_find_xsa] }
if {$xsa eq ""} {
  puts "FATAL: XSA not found. Use -tclargs xsa=/abs/path/to/xxx.xsa"
  return -code error
}

puts "===> XSCT starting"
puts "     XSA : $xsa"
puts "     WS  : $ws"
puts "     PLAT: $plat"
puts "     DOM : $dom"
puts "     APP : $app"

# ---------- 路径（相对仓库根） ----------
set app_src   [file normalize ../../sw/app]
set linker_ld [file normalize ../../sw/linker/lscript.ld]

# ---------- Workspace / Platform ----------
platform reset
file mkdir $ws
setws $ws

# 创建平台（从 XSA）
if {[catch {platform create -name $plat -hw $xsa -out $ws} err]} {
  puts "NOTE: platform exists, trying to 'platform active' and reuse."
  platform active $plat
} else {
  puts "===> Platform created: $plat"
}

# 创建 standalone 域（C 或 C++ 均可，这里用 C）
# 处理不同版本 CPU 名称（Zynq PS7）
set proc_name "ps7_cortexa9_0"
catch { set proc_name [lindex [array names [dict create] 0]  } _ ;# no-op
# 如果平台中处理器命名不同，可在此修改 proc_name

# 如果 domain 已存在则跳过创建
set need_dom 1
if {![catch {domain active $dom} _]} { set need_dom 0 }
if {$need_dom} {
  domain create -name $dom -os standalone -proc $proc_name -runtime c
}

# ---------- BSP 配置：启用 lwIP 并设置网络参数 ----------
# 不同 Vitis 版本的 lwIP 名称可能不同，尝试 2.13 与 2.11
set lwip_lib ""
foreach name {lwip213 lwip211 lwip210} {
  if {![catch {bsp setlib -name $name} _]} { set lwip_lib $name; break }
}
if {$lwip_lib eq ""} {
  puts "WARN: lwIP library not found in this Vitis version. Continuing without lwIP setlib."
} else {
  puts "===> Using lwIP library: $lwip_lib"
  # 常用选项（按需调整）
  catch { bsp config lwip_dhcp 0 } _
  catch { bsp config lwip_tcp  1 } _
  catch { bsp config lwip_udp  1 } _
  catch { bsp config lwip_pbuf_pool_size 256 } _
}

# 标准 I/O 走 UART1（常见默认；你的板若为 UART0 可改）
catch { bsp config stdin ps7_uart_1 } _
catch { bsp config stdout ps7_uart_1 } _

platform write
platform generate

# ---------- 应用 ----------
# 若存在则复用，否则创建
set apps [app list]
set exists 0
foreach a $apps { if {[string equal $a $app]} { set exists 1 } }
if {!$exists} {
  app create -name $app -platform $plat -domain $dom -template "Empty Application"
} else {
  puts "NOTE: App '$app' already exists, will re-import sources."
}

# 清空模板 src 并导入你的源码
catch { app config -name $app -removeSrc all } _
if {[file exists $app_src]} {
  importsources -name $app -path $app_src
  puts "===> Imported sources from $app_src"
} else {
  puts "WARN: Source dir not found: $app_src"
}

# 覆盖链接脚本
if {[file exists $linker_ld]} {
  file copy -force $linker_ld "$ws/$app/src/lscript.ld"
  puts "===> Copied linker script: $linker_ld"
} else {
  puts "WARN: Linker script not found: $linker_ld"
}

# 可选：为应用注入网络参数的头文件（若你的代码读取这些宏）
set cfg_h "$ws/$app/src/app_net_config.h"
set fh [open $cfg_h w]
puts $fh "#pragma once"
puts $fh "#define APP_IP_ADDR      \"$ip\""
puts $fh "#define APP_IP_MASK      \"$mask\""
puts $fh "#define APP_GW_ADDR      \"$gw\""
close $fh
puts "===> Generated $cfg_h (IP=$ip MASK=$mask GW=$gw)"

# ---------- 编译 ----------
app build -name $app
puts "===> Build done."

# 输出可执行/ELF 路径提示
set elf_glob [glob -nocomplain "$ws/$app/Debug/*.elf" "$ws/$app/Release/*.elf"]
if {[llength $elf_glob] > 0} {
  puts "===> ELF(s):"
  foreach e $elf_glob { puts "     $e" }
} else {
  puts "NOTE: ELF not found yet; check build logs above."
}

puts "===> XSCT script finished."
