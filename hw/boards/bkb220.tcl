# BKB220 profile。ready=1 于 2026-10-12 由 main 置位，依据与边界如下 ——
# **这不是"配置已全部证实"的声明。**
#
# 【为什么可以置 1】用户 2026-10-12 明确选择"先把 P4 整机建起来，ENET0 留到板测
#   再验"。构建不触板；本次迁移最大的技术未知是"P4/P16 能否在真实 xc7z020 上
#   收敛到 100MHz"，这一项与 ENET0 无关，不必等原理图。用户的这一指示覆盖此前
#   "不得猜 PHY 配置"的一般要求，仅限本项。
#
# 【已实测证实，见 docs/board/bkb220/migration-source-table.md §9】
#   * ps7_init/ps7_post_config RC=0；JTAG 单目标 xc7z020
#   * DDR 在 0x10000000 起 1024 字写读 0/1024 不符（DDR 可用）
#   * PS UART = UART0/MIO14-15 → FT4232H 通道 C（bInterfaceNumber=02），115200 8N1；
#     WSL `/dev/ttyUSBn` 名称随 USB 重枚举漂移，按 sysfs interface number 定位，
#     经 JTAG 直写 TX FIFO 后被正确 ASCII 接收
#   * PS_CLK=33.333MHz、DDR PLL=533.33MHz(DDR3-1066)、FCLK0=100MHz（PLL 寄存器回读）
#
#   * **ENET0/PHY 已实测通过（2026-10-12 更正）**：MDIO 经 MIO52/53 正常读写，
#     PHY = Realtek **RTL8211E**（OUI 0x001CC9 / model 0x11 rev5），自协商完成、
#     **1000BASE-T 全双工 link up**，与主机 ASIX 网卡报的 1Gbps 互相印证。
#     故下面 ENET0 = MIO16-27 RGMII + MDIO52/53 这组属性**已由真板证实**。
#     （早前一度报"MDIO 无应答"，实为 main 读错完成标志——应读
#      NETWORK_STATUS[2]——且漏写 MDEN = NETWORK_CONTROL bit4。见来源表 §9.6。）
#
# 【仍未证实 —— 板测必须验，失败就回来改这里】
#   * 工业级料号：手册写 XC7Z020-2CLG400I，2022.2 catalog 未确认对应条目
#   * DDR 板级延迟与 DQS-to-CLK 用 Vivado Custom 默认值，非数据手册/实测值
#   * QSPI/SD 冷启动、UART 反方向未测
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
  CONFIG.PCW_ENET0_ENET0_IO {MIO 16 .. 27} \
  CONFIG.PCW_ENET0_GRP_MDIO_ENABLE {1} \
  CONFIG.PCW_ENET0_GRP_MDIO_IO {MIO 52 .. 53} \
  CONFIG.PCW_ENET0_PERIPHERAL_FREQMHZ {1000 Mbps} \
  CONFIG.PCW_QSPI_PERIPHERAL_ENABLE {1} \
  CONFIG.PCW_QSPI_QSPI_IO {MIO 1 .. 6} \
  CONFIG.PCW_QSPI_GRP_SINGLE_SS_ENABLE {1} \
  CONFIG.PCW_QSPI_GRP_SINGLE_SS_IO {MIO 1 .. 6} \
  CONFIG.PCW_SD0_PERIPHERAL_ENABLE {1} \
  CONFIG.PCW_USB0_PERIPHERAL_ENABLE {1} \
]

set board_config [dict create \
  id bkb220 ready 1 part xc7z020clg400-2 \
  uart ps7_uart_0 xdc hw/constr/top.xdc \
  source_refs {docs/board/bkb220/migration-source-table.md docs/board/bkb220/README.md docs/board/bkb220/bkb220-product-manual-v1.1.pdf docs/04-interfaces.md docs/07-board-build-and-acceptance.md hw/constr/top.xdc} \
  ps7_properties $ps7_properties \
  pending {未核对实物完整器件顶标与PCB修订（手册写工业级 XC7Z020-2CLG400I，2022.2 catalog 未确认对应条目）；DDR VDD/VDDQ、板级走线延迟与DQS-to-CLK缺失（当前用 Custom 默认值，DDR 可读写不等于已优化）；QSPI/SD0/USB0 的实物连线与对应MIO/复位仍须核对；厂商board_files、PS7 preset、原理图和例程未提供。已实测（来源表 §9/§9.6）：PS_CLK=33.333MHz、DDR 读写可用、UART0/MIO14-15→通道C 115200、FCLK0=100MHz、ENET0 RGMII MIO16-27 + MDIO MIO52/53 可用且 PHY=RTL8211E 1000BASE-T 全双工 link up。}]
