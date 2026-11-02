# =========================================
# create_vitis.tcl
# 用法（仓库根目录）：
#   xsct sw/scripts/create_vitis.tcl
# 此入口仅用于仍支持XSCT的旧版Vitis。2026.1 XSCT已disabled，使用create_vitis_modern.py。
# 可选参数（-tclargs 覆盖）：
#   -tclargs xsa=/abs/path/to/xxx.xsa ws=/abs/path/to/workspace app=my_app plat=my_platform dom=my_domain ip=192.168.1.10 mask=255.255.255.0 gw=192.168.1.1 phy_link_speed=CONFIG_LINKSPEED_AUTODETECT uart=ps7_uart_0
#   build_app=0 仅生成平台/BSP/FSBL，由调用方使用固定构建器编译应用
# phy_link_speed 可选：CONFIG_LINKSPEED_AUTODETECT / CONFIG_LINKSPEED1000 / CONFIG_LINKSPEED100 / CONFIG_LINKSPEED10
# =========================================

# ---------- 默认参数 ----------
set plat "dna_platform"
set dom  "standalone_domain"
set app  "dna_lwip_app"
set build_app 1
set _here [file normalize [file dirname [info script]]]
set _root [file normalize "$_here/../.."]
set ws   "$_root/sw/workspace"

# 自动搜 hw/build 下的硬件包 XSA（优先使用 -tclargs 指定；多个候选时要求显式选择）
proc _find_xsa {} {
  set pattern [file join $::_root hw build * export *.xsa]
  set cand [glob -nocomplain -types f $pattern]
  if {[llength $cand] > 1} {
    error "找到多个硬件包 XSA；请显式传入 -tclargs xsa=/abs/path/to/xxx.xsa：$cand"
  }
  if {[llength $cand] == 1} {
    return [file normalize [lindex $cand 0]]
  }
  return ""
}

set xsa  ""
set ip   "192.168.1.10"
set mask "255.255.255.0"
set gw   "192.168.1.1"
set uart ""
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
_arg build_app $build_app
_arg ws   $ws
_arg xsa  $xsa
_arg ip   $ip
_arg mask $mask
_arg gw   $gw
_arg uart $uart
_arg phy_link_speed $phy_link_speed
if {$build_app ni {0 1}} {error "build_app必须为0或1"}
if {$uart ni {ps7_uart_0 ps7_uart_1}} {error "uart必须为本板PS UART实例名"}
if {$phy_link_speed ni {CONFIG_LINKSPEED_AUTODETECT CONFIG_LINKSPEED1000 CONFIG_LINKSPEED100 CONFIG_LINKSPEED10}} {
  error "phy_link_speed必须是CONFIG_LINKSPEED_AUTODETECT/1000/100/10之一"
}
foreach command {setws platform domain app bsp importsources} {
  if {![llength [info commands $command]]} {error "当前工具不提供XSCT命令$command；Vitis2026.1请使用Python入口"}
}

if {$xsa eq ""} { set xsa [_find_xsa] }
if {$xsa eq ""} {
  puts "FATAL: 未找到硬件包 XSA（搜索 hw/build/*/export/*.xsa）；请传 -tclargs xsa=/abs/path/to/xxx.xsa"
  return -code error
}
set xsa [file normalize $xsa]
if {![file isfile $xsa]} {error "指定 XSA 不存在：$xsa"}

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

# UART须按板卡profile显式指定；stdin/stdout共用该PS UART。
bsp config stdin $uart
bsp config stdout $uart

platform write

# 新建 workspace 的 BSP include 目录要到首次 platform generate 才会出现。
# 先生成一次以物化 lwipopts.h；随后下方将 TCP_WND 改为目标值，再生成一次，
# 让该配置进入 lwIP 库。直接复用已有 BSP 时第一次生成是增量操作。
puts "===> Initial platform generate (materialize BSP headers)"
platform generate

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
  # 2026-10-14 修正：原替换模式末尾是 `\S+`，只吃掉值的**第一个 token**。
  # Vitis 2022.2 的原始模板是 `#define TCP_WND                 6 * 1024`（两个 token），
  # 于是产出 `#define TCP_WND 32768 * 1024`（= 33,554,432）——是错的，
  # 而且它看起来像"补丁打过了"，不会有人再去看。冻结包里的正确值 `32768`
  # 并非这条路径产出，说明该改动的可复现性当时并未真正闭合。
  # 改为吃掉整行剩余部分，并在替换后**回读断言**，让错值必然变红。
  regsub -line {^#define[ \t]+TCP_WND[ \t]+[^\r\n]*} $body "#define TCP_WND $tcp_wnd" body
  set want "#define TCP_WND $tcp_wnd"
  # 允许行尾可选 CR，避免把 CRLF 行尾误判成替换失败
  if {![regexp -line "^${want}\r?\[ \t\]*\$" $body]} {
    error "TCP_WND 替换后回读不符（期望 '$want'）：$lwipopts"
  }
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
if {$build_app} {
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

# 为应用生成必需的网络参数头文件；main.c 显式包含并校验这些宏。
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
} else {
  puts "===> Skipping XSCT app create/build (build_app=0)."
}

puts "===> XSCT script finished."
