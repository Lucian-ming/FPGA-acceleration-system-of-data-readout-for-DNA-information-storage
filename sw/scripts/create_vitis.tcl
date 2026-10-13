# =========================================
# create_vitis.tcl
# 用法（仓库根目录）：
#   xsct sw/scripts/create_vitis.tcl
# 此入口仅用于仍支持XSCT的旧版Vitis。2026.1 XSCT已disabled，使用create_vitis_modern.py。
# 可选参数（-tclargs 覆盖）：
#   -tclargs xsa=/abs/path/to/xxx.xsa ws=/abs/path/to/workspace app=my_app plat=my_platform dom=my_domain ip=192.168.1.10 mask=255.255.255.0 gw=192.168.1.1 phy_link_speed=CONFIG_LINKSPEED_AUTODETECT
# phy_link_speed 可选：CONFIG_LINKSPEED_AUTODETECT / CONFIG_LINKSPEED1000 / CONFIG_LINKSPEED100 / CONFIG_LINKSPEED10
# =========================================

# ---------- 默认参数 ----------
set plat "dna_platform"
set dom  "standalone_domain"
set app  "dna_lwip_app"
set _here [file normalize [file dirname [info script]]]
set _root [file normalize "$_here/../.."]
set ws   "$_root/sw/workspace"

# 自动搜 XSA（优先使用 -tclargs 指定）
proc _find_xsa {} {
  set cand {}
  foreach p [list \
    "$::_root/hw/build/export/*.xsa" \
    "$::_root/*.xsa" \
    "$::_root/hw/**/*.xsa" \
  ] {
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
set uart "ps7_uart_1"
set phy_link_speed "CONFIG_LINKSPEED_AUTODETECT"

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
_arg uart $uart
_arg phy_link_speed $phy_link_speed
if {$uart ni {ps7_uart_0 ps7_uart_1}} {error "uart必须为本板PS UART实例名"}
if {$phy_link_speed ni {CONFIG_LINKSPEED_AUTODETECT CONFIG_LINKSPEED1000 CONFIG_LINKSPEED100 CONFIG_LINKSPEED10}} {
  error "phy_link_speed必须是CONFIG_LINKSPEED_AUTODETECT/1000/100/10之一"
}
foreach command {setws platform domain app bsp importsources} {
  if {![llength [info commands $command]]} {error "当前工具不提供XSCT命令$command；Vitis2026.1请使用Python入口"}
}

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
puts "     PHY : $phy_link_speed"
puts "     APP : $app"

# ---------- 路径（相对仓库根） ----------
set app_src   "$_root/sw/app"
set linker_ld "$_root/sw/linker/lscript.ld"

# ---------- Workspace / Platform ----------
# 注意：`platform reset` 在 Vitis 2022.2 的 XSCT 里不是合法子命令，会直接报错退出。
catch { platform reset }
file mkdir $ws
setws $ws

# 创建平台（从 XSA）
if {[catch {platform create -name $plat -hw $xsa -out $ws} err]} {
  puts "NOTE: platform exists, trying to 'platform active' and reuse."
  platform active $plat
} else {
  puts "===> Platform created: $plat"
}

# 创建 standalone 域
# 注意：Vitis 2022.2 的 `-runtime` 只接受 cpp / ocl，写 c 会直接报错退出。
#       cpp 运行时同样可以编译纯 C 源码。
# 处理不同版本 CPU 名称（Zynq PS7）
# 【修复】原来这里是一行括号不配对的 Tcl（`[lindex [array names [dict create] 0]`），
# 直接导致整个脚本解析失败、根本跑不到构建那一步。它本身也是个 no-op，删掉即可。
set proc_name "ps7_cortexa9_0"

# 如果 domain 已存在则跳过创建
set need_dom 1
if {![catch {domain active $dom} _]} { set need_dom 0 }
if {$need_dom} {
  domain create -name $dom -os standalone -proc $proc_name -runtime cpp
}

# ---------- BSP 配置：启用 lwIP 并设置网络参数 ----------
# 不同 Vitis 版本的 lwIP 名称可能不同，尝试 2.13 与 2.11
set lwip_lib ""
foreach name {lwip213 lwip211 lwip210} {
  if {![catch {bsp setlib -name $name} _]} { set lwip_lib $name; break }
}
if {$lwip_lib eq ""} {
  error "本工具未提供受支持lwIP；不能继续生成网络固件"
} else {
  puts "===> Using lwIP library: $lwip_lib"
  # 常用选项（按需调整）
  catch { bsp config lwip_dhcp 0 } _
  catch { bsp config lwip_tcp  1 } _
  catch { bsp config lwip_udp  1 } _
  catch { bsp config lwip_pbuf_pool_size 256 } _
  # 由 BSP 元数据生成 lwipopts.h；不要直接修改生成头文件。
  bsp config phy_link_speed $phy_link_speed
}

# 默认保留旧板UART1；新板须按对应XSA显式选择uart。
bsp config stdin $uart
bsp config stdout $uart

platform write

# ---------- 提高 lwIP 接收窗口 TCP_WND ----------
# 【2026-10-13】默认模板里是 `#define TCP_WND 2048`，把读段上传限在 ≈7.8 Mbps：
# 接收窗口限速时吞吐 ≈ TCP_WND ÷ RTT，2048 B ÷ ~2 ms ≈ 1 MB/s，与实测吻合。
# 提到 32768 后发送端才能一直有帧可飞；配合固件的「空闲多取帧」
# （`PIPE_IDLE_FETCH_N`，见 sw/app/main.c）实测可到 ~170 Mbps。
# 见 docs/benchmarks/bkb220-p16-speed-a-upload.md。
#
# 为什么必须在这里就地把头文件改掉，而不是 `bsp config` 一个参数：
#   1) TCP_WND 是**编译进 liblwip4.a** 的（tcp_in.c/tcp_out.c 按它算窗口），
#      应用侧再 `-D` 也改不了已编译的库；
#   2) 现有 lwIP 版本的 lwipopts.h 由库自带模板**拷贝**而来，不是 BSP 元数据参数，
#      所以没有对应的 `bsp config` 旋钮；
#   3) 必须在 `platform generate`（它会编译 BSP 库）**之前**改，改完才会被编进去。
# 找不到文件或找不到 `#define TCP_WND` 一律**报错退出**，不静默跳过 ——
# 静默跳过会产出「TCP_WND 还是 2048」的包而没人发现。
set tcp_wnd 32768
set patched 0
foreach lwipopts [glob -nocomplain \
        "$ws/$plat/$proc_name/$dom/bsp/*/include/lwipopts.h" \
        "$ws/$plat/$proc_name/$dom/bsp/*/libsrc/lwip*/src/contrib/ports/xilinx/include/lwipopts.h"] {
  set fh [open $lwipopts r]
  set body [read $fh]
  close $fh
  if {![regexp -line {^#define[ \t]+TCP_WND[ \t]+\S+} $body]} {
    error "lwipopts.h 里没有 '#define TCP_WND'，拒绝凭空注入：$lwipopts"
  }
  regsub -line {^#define[ \t]+TCP_WND[ \t]+\S+} $body "#define TCP_WND $tcp_wnd" body
  set fh [open $lwipopts w]
  puts -nonewline $fh $body
  close $fh
  incr patched
  puts "===> lwipopts.h TCP_WND -> $tcp_wnd : $lwipopts"
}
if {$patched == 0} {
  error "找不到任何 lwipopts.h，无法设置 TCP_WND（BSP 未按预期生成？）"
}

platform generate

# ---------- 应用 ----------
# 若存在则复用，否则创建
# 注意：workspace 里一个应用都没有时，`app list` 会**抛错**而不是返回空列表。
set apps {}
catch { set apps [app list] }
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
  # sw/app/xparameters.h is a historical generated snapshot. The selected
  # XSA's BSP owns these values; exclude the copied snapshot in this app only.
  set copied_xparameters [file join $ws $app src xparameters.h]
  if {[file isfile $copied_xparameters]} {file delete $copied_xparameters}
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
