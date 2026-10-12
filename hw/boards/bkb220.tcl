# BKB220 候选 profile。ready 必须保持 0，直到 main 审核来源表并补齐实物资料。
# 手册中的 XC7Z020-2CLG400I 与仓库候选 xc7z020clg400-2 的温度/完整料号对应关系
# 尚未由芯片顶标、PCB 修订和 Vivado 2022.2 catalog 交叉确认；不得据此开启构建。

# 候选值只用于审阅。load_board.tcl 在 ready=0 时会在 create_project 前拒绝该 profile。
# DDR 时序是 DDR3-1066 工作点的 JEDEC/Micron 数据表推导，不是板测值；
# -107 器件速度等级、板级延迟与 DQS-to-CLK 仍须经原厂资料和实板确认。
#
# 【2026-10-12 F3 实板结果，见 docs/board/bkb220/migration-source-table.md §9】
#   已实测：ps7_init/ps7_post_config RC=0；DDR 在 0x10000000 起 1024 字写读 0 不符
#   （DDR 训练可用）；PS UART = UART0/MIO14-15 → FT4232H 通道 C（/dev/ttyUSB2）
#   115200 8N1，ASCII 明文正确。PS_CLK=33.333MHz、DDR PLL=533.33MHz(DDR3-1066)、
#   FCLK0=100MHz 由 PLL 寄存器回读证实。
#   仍未通过：ENET0/PHY —— GEM0 时钟与复位都正常但 MDIO 读不到任何 PHY ID，
#   疑为 PHY 复位脚未驱动或 MDIO 不在此 MIO。**因此 ready 保持 0。**
set ps7_properties [list \
  CONFIG.PCW_USE_M_AXI_GP0 {1} \
  CONFIG.PCW_USE_S_AXI_HP0 {1} \
  CONFIG.PCW_EN_CLK0_PORT {1} \
  CONFIG.PCW_FPGA0_PERIPHERAL_FREQMHZ {100} \
  CONFIG.PCW_PRESET_BANK0_VOLTAGE {LVCMOS 3.3V} \
  CONFIG.PCW_PRESET_BANK1_VOLTAGE {LVCMOS 1.8V} \
  CONFIG.PCW_UIPARAM_DDR_ENABLE {1} \
  CONFIG.PCW_UIPARAM_DDR_MEMORY_TYPE {DDR 3} \
  CONFIG.PCW_UIPARAM_DDR_BUS_WIDTH {32 Bit} \
  CONFIG.PCW_UIPARAM_DDR_PARTNO {MT41K256M16TW-107} \
  CONFIG.PCW_UIPARAM_DDR_DRAM_WIDTH {16 Bits} \
  CONFIG.PCW_UIPARAM_DDR_DEVICE_CAPACITY {4096 MBits} \
  CONFIG.PCW_UIPARAM_DDR_SPEED_BIN {DDR3_1066F} \
  CONFIG.PCW_UIPARAM_DDR_FREQ_MHZ {533.333333} \
  CONFIG.PCW_UIPARAM_DDR_CL {7} \
  CONFIG.PCW_UIPARAM_DDR_CWL {6} \
  CONFIG.PCW_UIPARAM_DDR_T_RCD {7} \
  CONFIG.PCW_UIPARAM_DDR_T_RP {7} \
  CONFIG.PCW_UIPARAM_DDR_T_RC {50.625} \
  CONFIG.PCW_UIPARAM_DDR_T_RAS_MIN {37.5} \
  CONFIG.PCW_UIPARAM_DDR_T_FAW {50.0} \
  CONFIG.PCW_UART0_PERIPHERAL_ENABLE {1} \
  CONFIG.PCW_UART0_UART0_IO {MIO 14 .. 15} \
  CONFIG.PCW_UART0_BAUD_RATE {115200} \
  CONFIG.PCW_ENET0_PERIPHERAL_ENABLE {1} \
  CONFIG.PCW_QSPI_PERIPHERAL_ENABLE {1} \
  CONFIG.PCW_QSPI_QSPI_IO {MIO 1 .. 6} \
  CONFIG.PCW_QSPI_GRP_SINGLE_SS_ENABLE {1} \
  CONFIG.PCW_QSPI_GRP_SINGLE_SS_IO {MIO 1 .. 6} \
  CONFIG.PCW_SD0_PERIPHERAL_ENABLE {1} \
  CONFIG.PCW_USB0_PERIPHERAL_ENABLE {1} \
]

set board_config [dict create \
  id bkb220 ready 0 part xc7z020clg400-2 \
  uart ps7_uart_0 xdc hw/constr/top.xdc \
  source_refs {docs/board/bkb220/migration-source-table.md docs/board/bkb220/README.md docs/board/bkb220/BKB220产品手册v1.1.pdf docs/04-interfaces.md docs/07-board-build-and-acceptance.md hw/constr/top.xdc} \
  ps7_properties $ps7_properties \
  pending {未核对实物完整器件顶标与PCB修订（手册写工业级 XC7Z020-2CLG400I，2022.2 catalog 未确认对应条目）；DDR VDD/VDDQ、板级走线延迟与DQS-to-CLK缺失（当前用 Custom 默认值，DDR 可读写不等于已优化）；ENET0/PHY 未通过——GEM0 时钟/复位正常但 MDIO 0..31 地址无任何 PHY 应答，疑 PHY 复位脚未驱动或 MDIO 非 MIO52/53，须原理图或受控探测；QSPI/SD0/USB0 的实物连线与对应MIO/复位仍须核对；厂商board_files、PS7 preset、原理图和例程未提供。已实测（见 §9）：PS_CLK=33.333MHz、DDR 读写可用、UART0/MIO14-15→通道C 115200、FCLK0=100MHz。}]
