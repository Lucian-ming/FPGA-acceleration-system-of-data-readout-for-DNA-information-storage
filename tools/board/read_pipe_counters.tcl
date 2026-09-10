connect
targets -set -filter {name =~ "ARM*#0"}
puts "PIPE_POLL_STEPS [format %u [lindex [mrd -value 0x0021a2a4] 0]]"
puts "WM_POLL_STEPS   [format %u [lindex [mrd -value 0x0021af00] 0]]"
puts "PIPE_STATE      [format %u [lindex [mrd -value 0x0021a2a0] 0]]"
exit
# =============================================================================
# tools/board/read_pipe_counters.tcl —— 用 XSDB 只读固件里的流水线 poll 计数器
#
# 为什么需要它
# ------------
# sw/app/echo.c 的 poll_callback 早就打印了
#   [PIPE] total %u poll steps, %u ms (WM preload: %u steps)
# 但那是 xil_printf，走 UART。板子的 CH340 串口线没接时（Windows 侧只有 FTDI/JTAG），
# 这行信息**永远看不到**——2026-09-10 之前没有人读到过它。
#
# 这两个计数器本身是内存里的静态变量，XSDB 可以直接读，不需要串口。
# 地址来自 hw/build/export/dna_lwip_app_b27.elf 的符号表：
#   arm-none-eabi-nm dna_lwip_app_b27.elf | grep -E "pipe_poll_steps|wm_poll_steps"
# 换 ELF 后必须重新取地址，否则读到的是垃圾。
#
# 用法（在任务跑完之后立刻读，计数器保留上一次任务的值）
# ----------------------------------------------------
#   cd /mnt/d/dna_board_smoke && cmd.exe /c "D:\dev_tools\Vivado_Lab\2022.2\bin\xsdb.bat \
#       D:\dna_board_smoke\read_pipe_counters.tcl"
#   注意 WSL 调用 Windows 进程必须重定向 stdin（< /dev/null），否则会挂死等 EOF。
#
# 2026-09-10 实测（256 源读段 / 512 记录，t_result = 5.525 s）
# ------------------------------------------------------------
#   PIPE_POLL_STEPS 20      <- 5.525 s / 20 = 276 ms/步，即 lwIP poll 间隔
#   WM_POLL_STEPS    4      <- 50 区域 / WM_REGIONS_PER_POLL(16) = 4 批
#   结论：5.28 s 固定开销不是计算，是状态机每步白等一个 poll 周期。
# =============================================================================
