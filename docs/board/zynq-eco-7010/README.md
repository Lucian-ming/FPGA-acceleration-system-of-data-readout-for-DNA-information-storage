# ZYNQ ECO（XC7Z010）板卡资料包

整理日期：2026-08-29  
WSL 目标目录：`/home/kyb/board_docs/zynq-eco-7010`

## 1. 先确认是不是同一块板

公开检索到的“Xilinx ZYNQ ECO 开发板”原始资料来自成电国芯 / FPGA 云课堂，文档页眉为“小熊猫学堂”。板卡型号、器件和接口与要找的 ECO 板一致：`XC7Z010-1CLG400C`、双 TF 卡、千兆网口、HDMI、40 针扩展口、三个 Type-C 口、板载 FT232H JTAG 与 CH340 串口。

成都博宸精芯官网当前没有检索到名为“ECO”的公开产品页。因此，上电前请把实物与 `04_photos/` 中的照片比较，并查看 PCB 丝印是 `R5`、`R6` 还是其他版本。若布局或丝印不一致，不要直接套用这里的引脚和启动拨码。

## 2. 已下载内容

| 路径 | 内容 | 校验结果 |
| --- | --- | --- |
| `01_board_official/01_ZYNQ_ECO_硬件规格说明书.pdf` | R6 及以后版本硬件说明，15 页 | PDF 可打开、未加密、页面已渲染检查 |
| `01_board_official/02_ZYNQ_ECO_R5_原理图.pdf` | R5 原理图，11 页 | PDF 可打开、未加密、页面已渲染检查 |
| `01_board_official/03_ZYNQ_ECO_R6_原理图.pdf` | R6 原理图，12 页 | PDF 可打开、未加密、页面已渲染检查 |
| `02_amd_reference/DS190_Zynq-7000_Overview.pdf` | AMD Zynq-7000 系列概览 | PDF 可打开、未加密 |
| `02_amd_reference/DS187_XC7Z010-XC7Z020_DC-AC.pdf` | AMD XC7Z010/015/020 电气与时序规格 | PDF 可打开、未加密 |
| `03_examples/ECO_LED_官方示例工程.zip` | 官方 PL-only LED 工程，含 Vivado 工程、XDC 和已生成 bit | ZIP 完整性通过 |
| `03_examples/tutorials/ECO_蜂鸣器上板演示.mp4` | 官方蜂鸣器实验上板视频 | MP4 格式通过 |
| `04_photos/ECO_板卡介绍.png` | R5 风格板卡接口标注图 | 可打开 |
| `04_photos/ECO_R5_接口标注.jpg` | R5 接口位置图 | 可打开 |
| `00_sources/*.json` | 产品、附件和教程的 WordPress 原始元数据 | JSON 可解析 |
| `SHA256SUMS.txt` | 下载文件的 SHA-256 校验清单 | `sha256sum -c` 通过 |

## 3. R5 与 R6 的主要区别

- R5：左侧有 USB HUB，板上提供 4 个 USB Host 口，没有板载 OLED。
- R6 及以后：去掉 USB HUB；左侧三个 Type-C 口的中间口改为 Zynq USB2.0 Host/Device 接口；新增 128x64 单色 OLED。
- 两个版本的核心器件、DDR 组织、以太网、UART、JTAG、LED 和主要 PL 引脚相同。USB 与 OLED 部分必须按版本选原理图。

## 4. 板级关键参数

| 项目 | 资料确认值 |
| --- | --- |
| Zynq | `XC7Z010-1CLG400C`（Vivado part：`xc7z010clg400-1`） |
| PS 时钟 | 33.3333 MHz |
| PL 板载时钟 | 50 MHz，`K17`，LVCMOS33 |
| DDR3 | 单颗 `MT41J256M16HA-125`，16-bit，总容量 512 MiB |
| 千兆网口 | RTL8211E-VL，GEM0 MIO 16..27，MDIO MIO 52..53，Bank 501 为 1.8 V |
| 串口 | CH340，UART1 MIO 48/49，板卡/现有工程使用 115200 baud |
| JTAG | FT232H 板载下载器 |
| QSPI | W25Q128FV，16 MiB，MIO 1..6 |
| 主 SD 卡 | SD0，MIO 40..45，经 TXS02512 电平转换，支持启动 |
| 副 SD 卡 | SD1，Bank 500 侧 3.3 V |
| PL Bank 电压 | Bank 34 / 35 为 3.3 V；40 针扩展口在 Bank 34 |
| 用户 LED | LED1 `T12`、LED2 `U12`、LED3 `V12`、LED4 `W13`，LVCMOS33 |
| PL 按键 | KEY2/PL_KEY1 `M20`、KEY3/PL_KEY2 `M19` |
| PS 按键 | KEY1 -> MIO0 |
| EEPROM | 24C02，SDA `G17`、SCL `G18` |

R6 OLED 引脚：D0 `E18`、D1 `E19`、DC `H20`、RST `G20`。

## 5. BOOT 拨码

以板上 `SW1` 的 1、2 顺序为准：

| 模式 | SW1 |
| --- | --- |
| JTAG | `00` |
| QSPI | `10` |
| SD | `11` |

任何启动模式下都可以进行 JTAG 调试；第一次验证建议先用 `00`，只通过 JTAG 临时下载，不写 QSPI，也不替换 SD 卡内容。

## 6. 与当前 DNA-FPGA 工程的核对结果

当前工程：`/home/kyb/projects/dna-fpga-sim`

已经匹配的项目：

- part 为 `xc7z010clg400-1`；
- GEM0 使用 MIO 16..27、MDIO 使用 MIO 52..53；
- UART1 使用 MIO 48..49；
- PS Bank 1 使用 1.8 V；
- FCLK0 为 100 MHz，GP0/HP0 连接适合现有 DNA 加速器。

必须先修正的项目：

- 当前 `hw/scripts/bd.tcl` 固化的是两颗 `MT41J128M16`、32-bit DDR；ECO R5/R6 实物是单颗 `MT41J256M16`、16-bit DDR。虽然总容量同为 512 MiB，但总线宽度、器件参数和 DDR 训练配置不同。
- 当前 PS7 配置没有完整启用 ECO 的 SD0/QSPI/USB 外设。要从 SD 或 QSPI 启动，必须按本板 MIO 重新生成 XSA、FSBL 和 `BOOT.bin`。
- 因此，现有 `hw/build/export/BOOT.bin` 不能当作已经适配 ECO 的镜像直接烧写。先做 PL-only LED/JTAG 冒烟测试，再重建板级工程。

## 7. 推荐的第一次上板顺序

1. 断电拍摄开发板正反面，确认 PCB 版本和接口布局；特别确认是否有 OLED。
2. 拨码设为 JTAG `00`，只接标为“调试和供电口 / DEBUG”的 Type-C 口。
3. 在 Windows 设备管理器中确认 FT232H/JTAG 设备与 CH340 串口，不要先接外部扩展模块。
4. 用官方 LED 工程中的 PL-only bit 做最小冒烟测试；它的 part 和四个 LED 引脚已经与原理图核对一致。
5. 修正 DNA 工程的 PS7 DDR、SD/QSPI 和板级 MIO 配置，重新生成 XSA、FSBL、应用 ELF 与 `BOOT.bin`。
6. 先通过 JTAG 运行 DDR 自检和串口日志，再验证以太网 `192.168.1.10:7`，最后才制作 SD/QSPI 启动镜像。

## 8. WSL 连接开发板的现状

检查日期：2026-08-29。

- WSL 中的 Vivado 2022.2 自带 cable driver 安装脚本；
- WSL 当前没有检测到 Xilinx/FTDI udev 规则；
- Windows 当前未安装 `usbipd-win`；
- 检查时没有发现已连接的 FT232H、CH340 或 Xilinx USB 设备。

因此，开发板插上 Windows 后，WSL Vivado 不会自动获得 USB 设备。后续有两条路：在 Windows 运行 AMD Hardware Server、让 WSL Vivado 通过网络连接；或者安装 `usbipd-win` 后把板载 USB 设备附加给 WSL。选择方案前先确认实物在 Windows 设备管理器中的 VID/PID。

## 9. 原始网页与在线参考

- ECO 产品页：https://z.shaonianxue.cn/product/962.html
- ECO 硬件规格说明书发布页：https://z.shaonianxue.cn/9516.html
- R5 原理图发布页：https://z.shaonianxue.cn/9514.html
- ECO 蜂鸣器上板教程：https://z.shaonianxue.cn/432.html
- AMD Zynq-7000 TRM（UG585）：https://docs.amd.com/r/en-US/ug585-zynq-7000-SoC-TRM
- AMD Vivado 2022.2 编程与调试（UG908）：https://docs.amd.com/r/2022.2-English/ug908-vivado-programming-debugging
- AMD Zynq-7000 2022.2 嵌入式设计教程（UG1165）：https://docs.amd.com/v/u/2022.2-English/ug1165-zynq-embedded-design-tutorial
- AMD Vivado 2022.2 cable driver 安装说明：https://docs.amd.com/r/2022.2-English/ug973-vivado-release-notes-install-license/Install-Cable-Drivers
- FTDI 驱动页：https://ftdichip.com/drivers/d2xx-drivers/
- WCH CH340 产品页：https://www.wch.cn/products/CH340

