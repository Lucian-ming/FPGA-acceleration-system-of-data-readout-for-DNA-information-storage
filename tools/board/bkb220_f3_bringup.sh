#!/usr/bin/env bash
# =============================================================================
# tools/board/bkb220_f3_bringup.sh —— BKB220 F3 最小启动（UART / DDR）判据入口
#
# 为什么要有它
# ------------
# verify-system 2026-10-12 只读审计指出：仓库**没有独立的 F3 最小启动判据入口**。
# 当时可用的只有 g3_wait_ready.py（只确认 CAPS 包格式，不校验几何或器件），
# 以及 arm_baseline.py（会复位整板且写死旧 BSP/PS7，不能用于新板）。于是
# 「DDR 到底训没训起来、PS UART 落在哪个 FTDI 通道」这两个 F3 必答问题没有入口。
#
# 本脚本只做 F3，不做 G3：
#   1) 前置：WSL 里恰好一个 FT4232H、hw_server 在 127.0.0.1:3132、唯一 APU 目标
#   2) 按 bInterfaceNumber 枚举 FT4232H interface 01/02/03 并被动抓串口；
#      /dev/ttyUSBn 的编号会随 USB 重枚举漂移（DTR/RTS 不拉）
#   3) xsdb：选 APU -> rst -system -> source <ps7_init.tcl> -> ps7_init -> ps7_post_config
#   4) 读回关键寄存器作为 DDR/UART/时钟的可留证判据
#   5) 报告哪个 interface 收到字节；PS UART 的权威归属是 FT4232H interface 02
#
# 判据边界（别把它读成超过它证明的东西）
# ------------------------------------
# * `ps7_post_config` 退出 0 **不等于** DDR 训练通过。真正判据是 DDR 控制器状态
#   寄存器与随后的读写回环；本脚本只读状态并如实分类，不宣称「DDR PASS」除非
#   `--ddr-window` 真的做了写读比对。
# * 串口没字节 **不等于** 该通道不是 PS UART：PS 初始化后若没有固件打印，本来就没输出。
#   通道归属最终要靠最小 hello ELF 连续输出序号来确定。
# * JTAG 启动通过 **不证明** QSPI/SD 冷启动通过。
#
# 用法
# ----
#   tools/board/bkb220_f3_bringup.sh --ps7-init <ps7_init.tcl> --run-dir <全新目录>
#   tools/board/bkb220_f3_bringup.sh --ps7-init ... --run-dir ... --serial-seconds 20
#   tools/board/bkb220_f3_bringup.sh --ps7-init ... --run-dir ... --ddr-window 0x10000000,0x1000
#
# 恢复：任何步骤失败都保留 run 目录全部原始输出。要回到干净 JTAG 态，重新挂载 USB：
#   usbipd detach --busid 4-2 && usbipd attach --wsl --busid 4-2
# 然后重跑本脚本。**不要**在 Windows 侧起 hw_server（已知蓝屏路径，见 docs/07 §3a）。
# =============================================================================
set -uo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd -P)"
cd "$REPO"

XSDB="${F3_XSDB:-/tools/Xilinx/Vitis/2022.2/bin/xsdb}"
HW_SERVER_BIN="${F3_HW_SERVER:-/tools/Xilinx/Vivado/2022.2/bin/hw_server}"
HW_SERVER_URL="${F3_HW_SERVER_URL:-TCP:127.0.0.1:3132}"
CABLE_SERIAL="${F3_CABLE_SERIAL:-15051A}"
PS7_INIT=""
RUN_DIR=""
SERIAL_SECONDS=15
DDR_WINDOW=""
SERIAL_PORTS=""
SERIAL_PORTS_OVERRIDE=0
SERIAL_PORT_DISCOVERY=""

usage() { sed -n '2,40p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'; exit 0; }

while [[ $# -gt 0 ]]; do
    case "$1" in
        --ps7-init)      PS7_INIT="$2"; shift 2 ;;
        --run-dir)       RUN_DIR="$2"; shift 2 ;;
        --serial-seconds) SERIAL_SECONDS="$2"; shift 2 ;;
        --ddr-window)    DDR_WINDOW="$2"; shift 2 ;;
        --ports)         SERIAL_PORTS="$2"; SERIAL_PORTS_OVERRIDE=1; shift 2 ;;
        -h|--help)       usage ;;
        *) printf '未知参数：%s\n' "$1" >&2; exit 2 ;;
    esac
done

# ttyUSB 编号不是 FT4232H 通道号。默认依据 sysfs interface number 选择
# B/C/D（01/02/03）；若 sysfs 映射不完整，则回退扫描全部 ttyUSB 节点，避免漏口。
if (( ! SERIAL_PORTS_OVERRIDE )); then
    serial_devices=""
    serial_candidates=""
    serial_device_count=0
    serial_candidate_count=0
    serial_lookup_incomplete=0
    for p in /dev/ttyUSB*; do
        [[ -e "$p" ]] || continue
        serial_devices+="${serial_devices:+ }$p"
        serial_device_count=$((serial_device_count + 1))
        name=${p##*/}
        interface_file="/sys/class/tty/$name/device/../bInterfaceNumber"
        if [[ ! -r "$interface_file" ]]; then
            serial_lookup_incomplete=1
            continue
        fi
        interface_number=$(<"$interface_file")
        case "$interface_number" in
            01|02|03)
                serial_candidates+="${serial_candidates:+ }$p"
                serial_candidate_count=$((serial_candidate_count + 1))
                ;;
        esac
    done
    if (( serial_lookup_incomplete )) || { (( serial_device_count > 0 )) && (( serial_candidate_count == 0 )); }; then
        SERIAL_PORTS="$serial_devices"
        SERIAL_PORT_DISCOVERY="全部 /dev/ttyUSB*（interface 映射不可用，回退扫描）"
    else
        SERIAL_PORTS="$serial_candidates"
        SERIAL_PORT_DISCOVERY="按 bInterfaceNumber 01/02/03 枚举"
    fi
else
    SERIAL_PORT_DISCOVERY="使用 --ports 显式指定"
fi

[[ -n "$PS7_INIT" ]] || { echo "--ps7-init 必填" >&2; exit 2; }
[[ -n "$RUN_DIR"  ]] || { echo "--run-dir 必填（必须是不存在的全新目录）" >&2; exit 2; }
[[ -f "$PS7_INIT" ]] || { printf 'ps7_init 不存在：%s\n' "$PS7_INIT" >&2; exit 2; }
[[ -x "$XSDB" ]]     || { printf 'xsdb 不可执行：%s\n' "$XSDB" >&2; exit 127; }
if [[ -e "$RUN_DIR" ]]; then printf 'run 目录已存在，拒绝覆盖：%s\n' "$RUN_DIR" >&2; exit 2; fi

# Windows 原生 hw_server 是已知蓝屏路径，出现即停止（只警告，不擅自杀进程）
if command -v powershell.exe >/dev/null 2>&1; then
    if powershell.exe -NoProfile -Command \
        "if (Get-Process -Name hw_server -ErrorAction SilentlyContinue) { 'YES' } else { 'NO' }" \
        </dev/null 2>/dev/null | grep -q YES; then
        echo "! 检测到 Windows 侧存在 hw_server 进程。这是已知蓝屏路径（docs/07 §3a）。" >&2
        echo "  请先确认它不属于你的任务；本脚本不会替你结束它，但触板前应排除争用。" >&2
    fi
fi

mkdir -p "$RUN_DIR"
exec > >(tee "$RUN_DIR/f3_bringup.log") 2>&1

fail=0
note() { printf '%s\n' "$*"; }
check() { # check <描述> <0|非0>
    if [[ "$2" -eq 0 ]]; then note "  ✓ $1"; else note "  ✗ $1"; fail=1; fi
}

note "=== BKB220 F3 最小启动 ==="
note "run_dir   : $RUN_DIR"
note "ps7_init  : $PS7_INIT  (sha256 $(sha256sum "$PS7_INIT" | cut -d' ' -f1))"
note "xsdb      : $XSDB"
note "串口节点  : ${SERIAL_PORTS:-（未发现）}（$SERIAL_PORT_DISCOVERY）"
note "PS UART   : FT4232H channel C / bInterfaceNumber=02；按 cat /sys/class/tty/ttyUSB<n>/device/../bInterfaceNumber 判定，ttyUSBn 名称会漂"

# --- 1) 前置：唯一 FT4232H ---------------------------------------------------
note
note "--- 1) 前置检查 ---"
ftdi_count=$(lsusb -d 0403:6011 2>/dev/null | wc -l)
note "  WSL 中的 FT4232H 数量：$ftdi_count"
check "WSL 中恰好一个 FT4232H" "$([[ "$ftdi_count" -eq 1 ]] && echo 0 || echo 1)"
[[ "$ftdi_count" -eq 1 ]] || { note "  请先 usbipd attach --wsl --busid 4-2"; exit 1; }

# --- 2) hw_server ------------------------------------------------------------
note
note "--- 2) hw_server ---"
if ss -lnt 2>/dev/null | awk '{print $4}' | grep -q ':3132$'; then
    note "  端口 3132 已在监听，复用现有 hw_server"
else
    note "  启动 Linux hw_server: $HW_SERVER_BIN"
    nohup "$HW_SERVER_BIN" -sTCP:127.0.0.1:3132 -p0 -I1800 \
        >"$RUN_DIR/hw_server.stdout.txt" 2>"$RUN_DIR/hw_server.stderr.txt" </dev/null &
    echo $! >"$RUN_DIR/hw_server.pid"
    for _ in $(seq 1 60); do
        ss -lnt 2>/dev/null | awk '{print $4}' | grep -q ':3132$' && break
        sleep 0.3
    done
fi
if ss -lnt 2>/dev/null | awk '{print $4}' | grep -q ':3132$'; then
    check "hw_server 在 127.0.0.1:3132 监听" 0
else
    check "hw_server 在 127.0.0.1:3132 监听" 1
    exit 1
fi

# --- 3) 被动串口抓取 ---------------------------------------------------------
note
note "--- 3) 被动串口抓取（${SERIAL_SECONDS}s） ---"
# 刻意不依赖 pyserial：本机没装，而为一个只读抓取引入依赖不值得。
# 用 stty + cat，纯接收、不主动写字节。
#
# DTR/RTS 说明（别把这段当废话）：Linux 的 ftdi_sio 在 open 时会拉起 DTR/RTS，
# 而这两根线在部分板上接到 PS 复位。抓取因此**刻意排在 `rst -system` 之前**：
# 就算真有 DTR 脉冲，它落在复位之前，不会干扰本次 PS 初始化。顺序倒过来就会。
capture_pids=()
for p in $SERIAL_PORTS; do
    [[ -e "$p" ]] || { note "  (跳过不存在的 $p)"; continue; }
    name=$(basename "$p")
    interface_file="/sys/class/tty/$name/device/../bInterfaceNumber"
    if [[ -r "$interface_file" ]]; then
        interface_number=$(<"$interface_file")
    else
        interface_number="unknown"
    fi
    if stty -F "$p" 115200 cs8 -cstopb -parenb -crtscts -ixon -ixoff raw -echo 2>"$RUN_DIR/serial-$name.stty.err"; then
        note "  $p（bInterfaceNumber=$interface_number）已配置 115200 8N1 raw"
    else
        note "  $p（bInterfaceNumber=$interface_number）stty 配置失败（见 serial-$name.stty.err），仍尝试读取"
    fi
    ( timeout "$SERIAL_SECONDS" cat "$p" >"$RUN_DIR/serial-$name.bin" 2>"$RUN_DIR/serial-$name.err" ) &
    capture_pids+=($!)
done
note "  抓取已在后台启动（先于 rst -system）"

# --- 4) xsdb：复位 + PS 初始化 + 读回 ----------------------------------------
note
note "--- 4) xsdb: rst -system -> ps7_init -> ps7_post_config -> 读回 ---"
cat >"$RUN_DIR/f3.tcl" <<TCL
proc rd {label addr} {
    if {[catch { mrd -value \$addr } v]} { error "$label read failed at $addr: $v" }
    puts [format "%-26s %s 0x%08X" \$label \$addr \$v]
}
set rc [catch {
    connect -url $HW_SERVER_URL
    after 800
    puts "JTAG_CHAIN=[jtag targets]"

    set apu {}
    for {set i 0} {\$i < 10} {incr i} {
        foreach e [targets -target-properties] {
            if {[dict get \$e name] eq "APU" && [dict exists \$e jtag_cable_serial] \
                && [dict get \$e jtag_cable_serial] eq "$CABLE_SERIAL"} {
                set apu [dict get \$e target_id]
            }
        }
        if {\$apu ne ""} break
        after 1000
    }
    if {\$apu eq ""} { error "cable $CABLE_SERIAL 上找不到唯一 APU 目标（是否忘了重挂 USB？）" }
    targets \$apu
    puts "DEBUG_TARGETS=[targets]"

    puts "== 复位前 =="
    rd BOOT_MODE 0xF800025C
    rd DDR_PLL_CTRL 0xF800010C
    rd DDR_CTRL 0xF8006000

    targets -set -nocase -filter {name =~ "APU*"}
    rst -system
    after 2000
    puts "== rst -system 完成 =="

    targets -set -nocase -filter {name =~ "*Cortex-A9*#0*"}
    source {$PS7_INIT}
    puts "== sourcing ps7_init 完成 =="
    set r1 [catch { ps7_init } e1]
    puts "PS7_INIT_RC=\$r1 \${e1}"
    if {\$r1 != 0} { error "ps7_init failed: \$e1" }
    set r2 [catch { ps7_post_config } e2]
    puts "PS7_POST_CONFIG_RC=\$r2 \${e2}"
    if {\$r2 != 0} { error "ps7_post_config failed: \$e2" }

    puts "== 初始化后 =="
    rd BOOT_MODE 0xF800025C
    rd IO_PLL_CTRL 0xF8000108
    rd DDR_PLL_CTRL 0xF800010C
    rd FPGA0_CLK_CTRL 0xF8000170
    rd FPGA_RST_CTRL 0xF8000240
    rd DDR_CTRL 0xF8006000
    rd MIO_PIN_14 0xF8000738
    rd MIO_PIN_15 0xF800073C
    rd MIO_PIN_16 0xF8000740
    rd MIO_PIN_27 0xF800076C
    rd MIO_PIN_48 0xF80007C0
    rd MIO_PIN_49 0xF80007C4
    rd UART0_CTRL 0xE0000000
    rd UART1_CTRL 0xE0001000
    rd GEM0_NETWORK_CONTROL 0xE000B000
    disconnect
} emsg]
if {\$rc != 0} { puts "F3_XSDB_FAIL: \$emsg"; catch { disconnect }; exit 1 }
puts "F3_XSDB_OK"
exit 0
TCL
"$XSDB" "$RUN_DIR/f3.tcl" 2>&1 | tee "$RUN_DIR/f3.out"
xsdb_rc=${PIPESTATUS[0]}
if [[ "$xsdb_rc" -eq 0 ]] && grep -q '^F3_XSDB_OK$' "$RUN_DIR/f3.out"; then
    check "xsdb 流程完成（含 rst -system 与 ps7_init）" 0
else
    check "xsdb 流程完成（含 rst -system 与 ps7_init）" 1
fi

# --- 5) 等串口抓完并汇总 -----------------------------------------------------
note
note "--- 5) 等串口抓取结束 ---"
for pid in "${capture_pids[@]:-}"; do [[ -n "$pid" ]] && wait "$pid" 2>/dev/null; done

note
note "--- 串口字节汇总（确定 PS UART 落在哪个 FTDI 通道） ---"
for p in $SERIAL_PORTS; do
    name=$(basename "$p")
    bin="$RUN_DIR/serial-$name.bin"
    [[ -e "$bin" ]] || continue
    n=$(stat -c%s "$bin")
    interface_file="/sys/class/tty/$name/device/../bInterfaceNumber"
    if [[ -r "$interface_file" ]]; then
        interface_number=$(<"$interface_file")
    else
        interface_number="unknown"
    fi
    note "  $p（bInterfaceNumber=$interface_number）: $n bytes"
    if [[ "$n" -gt 0 ]]; then
        note "    --- 前 200 字节 ---"
        head -c 200 "$bin" | tr -d '\000' | sed 's/^/    /'
    fi
done
note
note "  判据提醒：**本步没有字节不等于该通道不是 PS UART** —— 只有当 ps7_init 之后"
note "  有固件主动打印时才会有输出。通道归属最终由最小 hello ELF 的连续序号输出确定。"

# --- 6) 可选 DDR 窗口回环 ----------------------------------------------------
if [[ -n "$DDR_WINDOW" ]]; then
    note
    note "--- 6) DDR 窗口写读回环：$DDR_WINDOW ---"
    base="${DDR_WINDOW%%,*}"; len="${DDR_WINDOW##*,}"
    cat >"$RUN_DIR/ddr_window.tcl" <<TCL
proc rd {label addr} { puts [format "%-20s %s 0x%08X" \$label \$addr [mrd -value \$addr]] }
set rc [catch {
    connect -url $HW_SERVER_URL
    after 500
    set apu {}
    foreach e [targets -target-properties] {
        if {[dict get \$e name] eq "APU" && [dict exists \$e jtag_cable_serial] \
            && [dict get \$e jtag_cable_serial] eq "$CABLE_SERIAL"} { set apu [dict get \$e target_id] }
    }
    if {\$apu eq ""} { error "no APU" }
    targets \$apu
    targets -set -nocase -filter {name =~ "*Cortex-A9*#0*"}
    set base $base
    set words [expr {$len} / 4]
    puts "DDR_WINDOW base=\$base words=\$words"
    # walking-1：每字写 1<<(i%32)，读回比对
    set bad 0
    for {set i 0} {\$i < \$words} {incr i} {
        set v [expr {1 << (\$i % 32)}]
        mwr -force [expr {\$base + \$i*4}] \$v
    }
    for {set i 0} {\$i < \$words} {incr i} {
        set exp [expr {1 << (\$i % 32)}]
        set got [mrd -value [expr {\$base + \$i*4}]]
        if {\$got != \$exp} { incr bad; if {\$bad < 6} { puts "  MISMATCH off=\$i exp=0x[format %08X \$exp] got=0x[format %08X \$got]" } }
    }
    puts "DDR_WINDOW_WALKING1_MISMATCHES=\$bad of \$words"
    # 固定 pattern
    set bad2 0
    for {set i 0} {\$i < \$words} {incr i} { mwr -force [expr {\$base + \$i*4}] 0xA5A55A5A }
    for {set i 0} {\$i < \$words} {incr i} {
        set got [mrd -value [expr {\$base + \$i*4}]]
        if {\$got != 0xA5A55A5A} { incr bad2 }
    }
    puts "DDR_WINDOW_PATTERN_MISMATCHES=\$bad2 of \$words"
    disconnect
} emsg]
if {\$rc != 0} { puts "DDR_WINDOW_FAIL: \$emsg"; catch { disconnect }; exit 1 }
puts "DDR_WINDOW_OK"
exit 0
TCL
    "$XSDB" "$RUN_DIR/ddr_window.tcl" 2>&1 | tee "$RUN_DIR/ddr_window.out"
    if grep -q '^DDR_WINDOW_OK$' "$RUN_DIR/ddr_window.out" \
        && grep -qE 'DDR_WINDOW_(WALKING1|PATTERN)_MISMATCHES=0 of' "$RUN_DIR/ddr_window.out"; then
        check "DDR 窗口 walking-1 与固定 pattern 全部逐字一致" 0
    else
        check "DDR 窗口 walking-1 与固定 pattern 全部逐字一致" 1
    fi
else
    note
    note "  (未给 --ddr-window，跳过 DDR 读写回环；仅凭寄存器无法宣称 DDR 训练通过)"
fi

# --- 7) 结论 ----------------------------------------------------------------
note
if [[ "$fail" -eq 0 ]]; then
    note "######## F3_BRINGUP: 已执行的检查项全部通过（不自动判 DDR PASS）########"
else
    note "######## F3_BRINGUP: 有检查项失败，见上面 ✗ ########"
fi
note "原始证据全部保留在：$RUN_DIR"
if [[ -n "$DDR_WINDOW" && "$fail" -eq 0 ]]; then
    note "DDR 结论：仅指定窗口 walking-1/固定 pattern 回环通过；不等同于全容量/温压范围训练验证。"
else
    note "DDR 结论：未做写读回环，不判 DDR 训练或读写 PASS。"
fi
note "PS UART 结论：无字节不等于通道错误；需最小 hello ELF 连续序号输出才能定位。"
exit "$fail"
