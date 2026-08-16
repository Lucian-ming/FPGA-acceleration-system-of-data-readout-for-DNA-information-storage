# =============================================================
# top.xdc — 顶层约束（build.tcl 会把它加入 constrs_1）
#
# 时钟说明：
#   PL 逻辑时钟来自 PS7 的 FCLK_CLK0，经 BD 内 clk_wiz_0 缓冲输出 100 MHz。
#   时钟源在 BD 内部（PS7 单元），完整的 BD 构建流程里 Vivado 会自动创建
#   并传播该时钟，无需手工 create_clock。
#   这里只在「自动约束缺失」的场景兜底（例如内存工程只综合 RTL 顶层、
#   或 OOC 流程），找不到引脚时静默跳过，不影响正常构建。
# =============================================================

set fclk_pins [get_pins -hier -quiet -filter {REF_PIN_NAME == FCLK_CLK0}]
if {[llength $fclk_pins] > 0
    && [llength [get_clocks -quiet -of_objects $fclk_pins]] == 0} {
    create_clock -period 10.000 -name ps7_fclk0 $fclk_pins
    puts "top.xdc: 兜底创建 ps7_fclk0 100MHz 时钟约束"
}
