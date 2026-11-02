# =============================================================
# top.xdc — 顶层约束（build.tcl 会把它加入 constrs_1）
#
# 时钟说明：
#   PL 逻辑时钟来自 PS7 的 FCLK_CLK0，经 BD 内 clk_wiz_0 缓冲输出 100 MHz。
#   时钟源在 BD 内部（PS7 单元），完整的 BD 构建流程里 Vivado 会自动创建
#   并传播该时钟，无需手工 create_clock。
#   本顶层没有 PL 外部引脚；DDR/FIXED_IO 都由 PS7 primitive 和 bd.tcl 的
#   PCW 参数约束。实现后的 timing summary 必须显示 clk_fpga_0 为 100 MHz。
#
# 注意：XDC 不支持 Tcl 的 if 控制命令，不能在这里做条件式兜底。PS7 生成的
# IP XDC 已负责 create_clock，重复创建同一时钟反而会覆盖权威约束。
# =============================================================
