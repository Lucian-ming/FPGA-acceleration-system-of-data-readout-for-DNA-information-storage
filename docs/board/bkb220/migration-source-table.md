# BKB220 板级来源表与 PS7 配置草案

更新：2026-10-13。本表最初用于 F2 配置核对与 F3 启动规划，§1–§8 保留当时的来源核对记录。现 `hw/boards/bkb220.tcl` 的 BKB220 profile 为 `ready=1`；P4/P16 整机 route、P4 G3、P16 板测、性能矩阵和 v2 数据集对照已有记录。迁移仍有明确边界：8 h 长稳、v2 `score_min=67`、新载荷四级逐级取证、冷启动、UART 反向、功耗和 F9 未完成。后续各节按证据日期记录，不将旧草案状态当作当前状态。

来源状态标签（用于保留当时的核对记录）严格区分：

- **已证实（main 现场）**：来自 main 在阶段卡中记录的 2026-10-12 实测；本子任务不触板、不复测。
- **手册给出**：产品手册明确写出；只证明手册陈述，不证明当前 PCB 修订与实物一致。
- **仍缺**：仓库手册和阶段卡都未提供足以写入最终 PS7 profile 的依据。
- **推导草案**：从器件资料/接口契约推导出的待验证起始值，不能当作实测或已通过的 PS7 参数。

## 1. 手册校验与阅读记录

仓库资料：[BKB220 产品手册 v1.1](bkb220-product-manual-v1.1.pdf)、[资料索引](README.md)。复核命令在 `docs/board/bkb220/` 执行：

```text
$ sha256sum -c SHA256SUMS.txt
bkb220-product-manual-v1.1.pdf: OK
exit_code=0
```

校验值为 `40b50e666ecab4ee83fbcfb1eea816a04a0989f73b001d9b9432e4778c8cd086`，与 `SHA256SUMS.txt` 一致。`pdfinfo` 报告 30 页。用 `pdftotext -layout` 完整提取了第 1–30 页；另将第 5–10、15–17、27 页渲染成 PNG 目视核对，图文页码与提取文本一致。渲染只用于核对手册，不是 PCB 原理图或实物照片核验。

实际提取命令：

```text
pdftotext -layout -f 1 -l 15 'docs/board/bkb220/bkb220-product-manual-v1.1.pdf' -   # exit 0
pdftotext -layout -f 16 -l 30 'docs/board/bkb220/bkb220-product-manual-v1.1.pdf' - # exit 0
pdfinfo 'docs/board/bkb220/bkb220-product-manual-v1.1.pdf'                           # exit 0，Pages: 30
pdftoppm -f 5 -l 10 -r 110 -png 'docs/board/bkb220/bkb220-product-manual-v1.1.pdf' /tmp/board-migrate-bkb220 # exit 0
pdftoppm -f 15 -l 17 -r 110 -png 'docs/board/bkb220/bkb220-product-manual-v1.1.pdf' /tmp/board-migrate-bkb220 # exit 0
pdftoppm -f 27 -l 27 -r 110 -png 'docs/board/bkb220/bkb220-product-manual-v1.1.pdf' /tmp/board-migrate-bkb220 # exit 0
```

## 2. 板级来源表

| 状态 | 规格或事实 | 出处与适用边界 |
|---|---|---|
| 手册给出 | 产品系列列出 XC7Z020-2CLG400I（另有 XC7Z010 选项）；正文亦写 XC7Z020-2CLG400I。 | 仓库手册 pp.5–6。阶段卡要求 Vivado profile 候选写 `xc7z020clg400-2`；main 的 JTAG 只识别到 xc7z020 与 IDCODE，尚未用芯片顶标/PCB 修订核对完整 speed/package/temperature 后缀。候选 part 不是完整料号已证实。 |
| 已证实（main 现场） | JTAG 串链名 `Xilinx HW-Z1-ZCU104 FT4232H 15051A`，单一目标 xc7z020，IDCODE `0x23727093`。 | 2026-10-12 阶段卡；实际枚举事实由 main 提供，本任务未启动 XSDB/JTAG。手册 p.7 说明板载 FT4232HL JTAG bridge。 |
| 手册给出 | 板载 FT4232HL 实现 USB 到 ZYNQ JTAG，无需外置 Xilinx 下载器。 | 仓库手册 p.7。USB 外观/桥片型号仍需对照当前 PCB 修订；main 的链名与此相符。 |
| 已证实（main 现场） | Windows COM9、COM10、COM11 对应 FT4232H B/C/D 通道，序列号 15051B/C/D；WSL 未枚举 `/dev/ttyUSB*`。 | 2026-10-12 阶段卡。三个 FTDI COM 口中哪个接 PS UART 尚未确认；端口枚举不是串口功能验证。 |
| 手册给出 | FTDI USB 转串口一路接 PL、一路接 PS，并有 USB JTAG。 | 仓库手册 p.16。不能从此推出 PS UART 的具体 COM 号或 MIO。 |
| 手册给出 | PS 有 2 个 UART；板级 automation 示意勾选 UART0。 | 仓库手册 pp.6、27。手册未列 PS UART MIO；p.17 的 F16/F17 是 **PL UART** 引脚，不能作为 PS UART MIO。 |
| 仍缺 | PS UART 实际选择、UART0/1 MIO、串口电平/通道对应、线速配置。 | 厂商原理图、board_files/PS7 preset、对应板卡例程或逐候选 MIO/COM 实测；不能照抄旧 ECO UART1 MIO48..49。 |
| 手册给出 | PS MIO bank 电压：VCCO_MIO0=3.3V、VCCO_MIO1=1.8V、VCCO_DDR=1.5V。 | 仓库手册 p.8。该项是 PS bank 电压；不等于 DDR 芯片 VDD/VDDQ 已确认。 |
| 手册给出 | 两颗 Micron MT41K256M16TW-107，各 256M×16bit / 4Gbit；合计 32bit、8Gbit，即 1GB；连接 PS BANK502；手册称最高 533MHz / 1066Mbps。 | 仓库手册 pp.9–10，DDR 引脚表继续在 pp.11–14。p.16 的资源摘要写“双路 DDR3，共 1Gb”，与 p.9–10 的“两颗 4Gbit”矛盾；本表采用详细器件表并按容量算出 1GB，将 p.16 视作摘要单位/数值疑点，仍需厂商确认。 |
| 手册给出 | QSPI 为 Winbond W25Q256、32MByte、3.3V；QSPI_CLK/CS/D0..D3 分配到 PS_MIO6/1/2/3/4/5（MIO1..6）。 | 仓库手册 pp.8–9。板卡和焊接器件的修订对应仍待实物核对。 |
| 手册给出 | 支持 JTAG、QSPI、SD 三种启动；BOOT_CFG 拨码表列出三种模式及无效组合。 | 仓库手册 pp.8、15。未验证任何冷启动镜像；本轮不切换拨码、不写 QSPI/SD。 |
| 手册给出 | 有 PS 端 TF 卡；PS 泛型资源支持 SD/SDIO；block automation 示意勾选 SD0。 | 仓库手册 pp.6、15、27。SD0 MIO、CD/WP/供电和当前板上的具体走线仍待确认。 |
| 手册给出 | PS 泛型资源有 USB OTG；板卡资源页列 USB2.0 host 与 USB2.0 slave Type-C；板级 automation 示意勾选 USB0。 | 仓库手册 pp.6、15–16、27。USB0 MIO、PHY、复位/供电和各 USB 口功能映射仍待确认。 |
| 手册给出 | PS 有两个千兆网控制器的一般能力；板卡资源页列 PS 以太网；block automation 示意勾选 ENET0。 | 仓库手册 pp.6、16、27。没有给出本板 PHY 型号或 MIO、接口模式、MDIO/复位脚。 |
| 已证实（main 现场） | Windows ASIX USB 千兆网卡“以太网 2”为 192.168.1.100/24、链路 Up、1Gbps；ReceivedBytes=0。 | 2026-10-12 阶段卡。这是主机侧适配器状态；因 PS 尚未发包，不能宣称 BKB220 GEM/PHY 链路已通。 |
| 仍缺 | ENET0 PHY/地址、RGMII/GMII/SGMII、MIO 组、MDIO MIO、PHY reset MIO/极性、参考时钟及协商行为。 | 对应 PCB 原理图、PHY 数据表/板级 preset 和 main 持板逐项探测。不能复制旧 ECO 的 MIO16..27、MDIO52..53 或 reset MIO。 |
| 手册给出 | PL 系统时钟输入 U18；PL UART 为 F16/F17。 | 仓库手册 p.17 的 XDC 示例。它描述 PL 外部引脚，不给出 PS_CLK 频率，F16/F17 也不是 PS UART。 |
| 手册给出 | Vivado 2022.1 示例里对 Zynq 执行 block automation，会勾选 UART0、GPIO、SD0、USB0、ENET0；后续 connection automation 导入 PS 配置。 | 仓库手册 pp.26–28。手册没有随附 board_files、preset 内容或实际工程 XSA；界面示例不能替代厂商 preset/当前 Vivado 2022.2 catalog 验证。 |
| 已证实（main 现场） | WSL Vivado=/tools/Xilinx/Vivado/2022.2/bin/vivado；WSL Vitis/XSCT=/tools/Xilinx/Vitis/2022.2；Windows 2026.1 根目录 D:/xilinx/2026.1，XSDB 为 `D:\xilinx\2026.1\Vitis\bin\xsdb.bat`。 | 2026-10-12 阶段卡。只是工具路径核实，不代表本任务运行 Vivado 或生成新板制品。 |
| 仍缺 | PS_CLK 输入频率/来源、PS7 preset、当前 PCB 原理图、厂家 board_files 和裸机例程。 | 本任务开始前 `docs/board/bkb220/` 的原始资料只有产品手册、SHA 清单和 README；本任务未发现随仓库提供上述资料。需要向厂商/用户补齐。 |

## 3. PS7 配置草案

以下值写在 `hw/boards/bkb220.tcl` 的候选 `ps7_properties` 中，便于 main 审阅。只有数据手册值可直接归因；所有 board-specific pin mux、PS_CLK、DDR delay 与 PS7 catalog 接受情况未通过 Vivado 2022.2 实证。**ready=0 时 `build.tcl` 不会把这些值应用到 PS7。**

### 3.1 互联、时钟和 MIO bank

| 候选属性 | 草案值 | 来源 / 确信度 | 条件 |
|---|---|---|---|
| `CONFIG.PCW_USE_M_AXI_GP0` | `1` | `hw/scripts/bd.tcl` 的现有互联拓扑；**高（项目接口需求）**，不是 BKB220 手册事实。 | FCLK/PS 时钟稳定后用于当前 BD。 |
| `CONFIG.PCW_USE_S_AXI_HP0` | `1` | `hw/scripts/bd.tcl` 的现有互联拓扑；**高（项目接口需求）**。 | 确认 PS7 HP0 与 DDR 地址空间可用。 |
| `CONFIG.PCW_EN_CLK0_PORT` | `1` | 当前 BD 使用 PS FCLK_CLK0；**高（项目接口需求）**。 | PS_CLK/PLL 尚未核实。 |
| `CONFIG.PCW_FPGA0_PERIPHERAL_FREQMHZ` | `100` | `hw/scripts/bd.tcl`、`docs/07-board-build-and-acceptance.md` 的 100MHz 项目目标；**高（项目目标）**，手册未给 FCLK 输出值。 | PS_CLK 确定后须复核 PS7 PLL 与实现后的时钟报告。 |
| `CONFIG.PCW_PRESET_BANK0_VOLTAGE` | `LVCMOS 3.3V` | 手册 p.8 的 VCCO_MIO0；**中（电压规格明确，Vivado 属性映射待核）**。 | 按当前板修订的 PS7 preset/catalog 验证。 |
| `CONFIG.PCW_PRESET_BANK1_VOLTAGE` | `LVCMOS 1.8V` | 手册 p.8 的 VCCO_MIO1；**中（电压规格明确，Vivado 属性映射待核）**。 | 按当前板修订的 PS7 preset/catalog 验证。 |

### 3.2 DDR3

| 候选属性 | 草案值 | 来源 / 确信度 | 说明 |
|---|---|---|---|
| `CONFIG.PCW_UIPARAM_DDR_ENABLE` | `1` | 手册 pp.9–10；**中高（手册规格）**。 | 精确 DRAM 电源与 DDR3/DDR3L 兼容配置仍需原理图/电源资料。 |
| `CONFIG.PCW_UIPARAM_DDR_MEMORY_TYPE` | `DDR 3` | 手册 pp.9–10 称 DDR3；**中高（手册规格）**。 | Micron 器件资料含 DDR3L 系列属性，板上供电仍需核对。 |
| `CONFIG.PCW_UIPARAM_DDR_BUS_WIDTH` | `32 Bit` | 手册 p.9 两颗 x16 合成 32bit；**高（手册明确）**。 | 原理图确认两颗都装配、rank/片选组织与 PCB 修订。 |
| `CONFIG.PCW_UIPARAM_DDR_PARTNO` | `MT41K256M16TW-107` | 手册 p.9；**中（手册给出型号，PS7 catalog 项未验证）**。 | 检查完整器件后缀、温度等级和 catalog 映射。 |
| `CONFIG.PCW_UIPARAM_DDR_DRAM_WIDTH` | `16 Bits` | 手册 p.9 的单颗 256M×16；**高（手册明确）**。 | 等原理图/实物确认。 |
| `CONFIG.PCW_UIPARAM_DDR_DEVICE_CAPACITY` | `4096 MBits` | 手册 p.9 单颗 4Gbit；**高（手册明确，PS7 单颗容量字段语义待 catalog 复核）**。 | 两颗合计 8Gbit=1GB。 |
| `CONFIG.PCW_UIPARAM_DDR_SPEED_BIN` | `DDR3_1066F` | 手册 p.9 的 1066Mbps；**中（候选运行点，catalog 未验证）**。 | Micron 将 `-107` 器件标为 933MHz/1866MT/s 能力等级；`DDR3_1066F` 是本草案采用的较低运行点，不把二者混为同一 bin。见 [Micron 料号页](https://www.micron.com/products/memory/dram-components/ddr3-sdram/part-catalog/part-detail/mt41k256m16tw-107-m-p)。 |
| `CONFIG.PCW_UIPARAM_DDR_FREQ_MHZ` | `533.333333` | 手册 p.9 的 533MHz；**中（板级目标/上限来自手册，PS_CLK/PLL 未验证）**。 | 必须先确定 PS_CLK、DDR PLL 和 board delay。 |
| `CONFIG.PCW_UIPARAM_DDR_CL` | `7` | tCK≈1.875ns；Micron 4Gb DDR3L Table 53 DDR3L-1066 7-7-7 档；**推导，不是实测**。 | 1066工作点，不代表 `-107` 料号本身是 -1066。 |
| `CONFIG.PCW_UIPARAM_DDR_CWL` | `6` | Micron Table 53 在 1.875ns tCK 支持 CL7/CWL6；**推导，不是实测**。 | 待 PS7 catalog/板测。 |
| `CONFIG.PCW_UIPARAM_DDR_T_RCD` | `7` CK（13.125ns） | Micron Table 53 的 DDR3L-1066 tRCD=13.125ns；**推导，不是实测**。 | `ceil(13.125/1.875)=7`。 |
| `CONFIG.PCW_UIPARAM_DDR_T_RP` | `7` CK（13.125ns） | Micron Table 53 的 DDR3L-1066 tRP=13.125ns；**推导，不是实测**。 | `ceil(13.125/1.875)=7`。 |
| `CONFIG.PCW_UIPARAM_DDR_T_RC` | `50.625ns` | Micron Table 53 的 DDR3L-1066 tRC；**推导，不是实测**。 | 不能沿用旧 ECO profile 的 48.91ns。 |
| `CONFIG.PCW_UIPARAM_DDR_T_RAS_MIN` | `37.5ns` | Micron Table 53 的 DDR3L-1066 tRAS；**推导，不是实测**。 | 不能沿用旧 ECO profile 的 35ns。 |
| `CONFIG.PCW_UIPARAM_DDR_T_FAW` | `50.0ns` | Micron Table 58 对 x16/2KB page 的 DDR3L-1066 tFAW；**推导，不是实测**。 | 本手册器件为 x16；不能沿用旧 ECO profile 的 40ns。 |
| `PCW_UIPARAM_DDR_BOARD_DELAY0..3`、`PCW_UIPARAM_DDR_DQS_TO_CLK_DELAY_0..3` | **不设置** | 手册未给；**仍缺**。 | 不复制 ECO profile 的 0.25ns/0ns；须有本板走线/延迟来源。 |

DDR 时序参考：Micron-authored [4Gb x4/x8/x16 DDR3L SDRAM datasheet, Rev. R](https://datasheet.lcsc.com/datasheet/pdf/5dffd7a5abc502f4a8d151b6c508c1b4.pdf?productCode=C2888412)，Table 53（印刷页 78）给出 DDR3L-1066 CL/tRCD/tRP/tRAS/tRC，Table 58（印刷页 85）给出 x16/2KB page 的 tFAW。它是器件级时序表，不含 BKB220 的 PS_CLK、PCB 走线、DQS-to-CLK 或 Vivado 2022.2 preset；以上只能作为待验证草案。

### 3.3 UART、ENET0、QSPI、SD、USB

| 外设 / 候选属性 | 草案值 | 手册支持与确信度 | 待实物确认 |
|---|---|---|---|
| `uart` profile 字段 | `ps7_uart_0` | p.16 说一路 USB 转串口接 PS；p.27 automation 选 UART0；**中（功能选择）**。 | 不能据此确定哪个 COM 或 UART MIO。 |
| `CONFIG.PCW_UART0_PERIPHERAL_ENABLE` | `1` | 手册 p.27；**中（示例 automation）**。 | UART0 实际 MIO、FTDI COM9/10/11 对应、波特率/电平；p.17 的 PL F16/F17 不是 PS UART。 |
| `CONFIG.PCW_ENET0_PERIPHERAL_ENABLE` | `1` | p.16 列 PS 以太网，p.27 automation 选 ENET0；**中（功能选择）**。 | MIO、PHY 型号/地址、RGMII/GMII/SGMII、MDIO、reset、时钟及链路协商。 |
| `CONFIG.PCW_QSPI_PERIPHERAL_ENABLE` | `1` | p.8–9 的 W25Q256/32MB；**中高（手册规格）**。 | 当前实物器件与 PS 端接线。 |
| `CONFIG.PCW_QSPI_QSPI_IO` | `MIO 1 .. 6` | p.9 的 QSPI MIO1..6 逐信号表；**中高（手册明确 pin mapping）**。 | 当前 PCB revision 与 Vivado 2022.2 catalog 属性值。 |
| `CONFIG.PCW_QSPI_GRP_SINGLE_SS_ENABLE` | `1` | p.9 单颗 W25Q256；**中（单片选候选）**。 | 检查当前 PS7 IP 单片选属性/board preset。 |
| `CONFIG.PCW_QSPI_GRP_SINGLE_SS_IO` | `MIO 1 .. 6` | p.9 的 QSPI_CLK/CS/D0..D3 映射；**中（属性映射待 catalog 验证）**。 | 确认 catalog 对 group I/O 的接受格式及实际 PCB 连线。 |
| `CONFIG.PCW_SD0_PERIPHERAL_ENABLE` | `1` | p.6 列 SD/SDIO，p.15 为 PS TF 卡，p.27 automation 选 SD0；**中（功能选择）**。 | SD0 MIO、CD/WP/供电脚、卡槽和实际读写；不从 automation 猜 MIO。 |
| `CONFIG.PCW_USB0_PERIPHERAL_ENABLE` | `1` | p.6 列 USB OTG，p.15–16 列 host/slave Type-C/串口/JTAG，p.27 automation 选 USB0；**中（功能选择）**。 | USB0 MIO、PHY、复位/供电、host/slave 口与 FTDI 功能对应关系。 |

## 4. 进入 F3 前的硬缺项

1. **芯片/PCB 身份**：拍照并核对完整 FPGA 顶标（含 speed/temperature）、板卡 PCB 修订、两颗 DDR 实装型号；解释手册 p.16 “1Gb”与 p.9 的 8Gbit 总量差异。
2. **PS_CLK**：频率、振荡器来源、容差与对应 bank/管脚；FCLK0=100MHz 是项目输出目标，不是 PS_CLK 输入值。
3. **厂商设计资料**：当前板修订的原理图、PS7 preset 或 board_files、Vivado 工程/裸机例程、DDR 引脚/布线资料。手册 pp.26–28 的 automation 截图不是 preset 文件。
4. **DDR 供电与控制器参数**：DRAM VDD/VDDQ、DDR bank 电压/布线、rank/片选/组织、speed-bin 与 Vivado 2022.2 catalog 映射；DDR 板级走线延迟和各 byte lane 的 DQS-to-CLK 延迟/长度、传播延迟。不要从 ECO profile 复制。
5. **PS UART**：PS UART0/1 的 MIO 分配、UART 对应的 FTDI 通道与 Windows COM9/10/11、I/O 电压和实际波特率。F16/F17 只属于 PL UART。
6. **GEM0**：PHY 厂牌/型号/地址、MIO pin group、RGMII/GMII/SGMII 模式、MDIO/MDC、reset pin/极性、参考时钟及 PHY 电源/复位时序。
7. **QSPI/SD/USB**：以当前 PCB 原理图核对 PS MIO、复位/卡检测/写保护/供电及端口角色；手册给 QSPI 的 MIO1..6 仍需当前 PCB 修订确认。
8. **启动资料**：BOOT_CFG 拨码实际状态和厂商冷启动流程；JTAG 启动通过不证明 QSPI/SD 冷启动通过。

## 5. F3 最小启动计划（由 main 持板执行）

本子任务没有操作 JTAG、COM 口、网络适配器或板卡。以下操作均由 main 持板执行；board-migrate 只准备经审阅的配置/同 XSA 软件包并分析 main 回传的日志。进入物理步骤前先由 main 审核本表、取得足以填写最终 PS7 参数的厂商资料，并在配置属性通过 Vivado 2022.2 catalog 检查后另行解除 `ready=0` 守卫。不得仅为启动测试把未知值猜入 profile。

| 顺序 | main 执行的最小步骤 | PASS 判据 | 失败分类与下一检查 |
|---|---|---|---|
| 0. 输入冻结 | 核对板卡顶标/PCB rev、PS7 preset、手册 SHA、Vivado 2022.2 版本和唯一的独立 run 目录；用 `tclsh hw/scripts/build.tcl board=bkb220 dry_run=1` 检查 profile。 | 输入来源明确；profile 只有在缺项补齐并经 main 审核后才可转 `ready=1`；候选运行目录独立。 | dry-run 仍报未验证/缺项则停在 F2，不生成工程；part/catalog 不匹配回到板卡身份/器件映射核对。 |
| 1. JTAG/PS 初始化 | main 使用阶段卡记录的唯一目标（xc7z020 / IDCODE `0x23727093`），从 JTAG 下载同一 XSA 的 PS 初始化与最小 UART ELF。先确认 BOOT_CFG 为 JTAG 模式；不要下载混搭的历史 bit/XSA/ELF。 | XSDB 只选中一个目标；PS 初始化与下载成功，无多个同类目标歧义。 | 无目标/IDCODE 变化：FT4232 驱动、USB 线/供电/BOOT_CFG；PS 初始化失败：PS_CLK、完整 part、preset、DDR/PLL 参数分开追查。由 main 执行，不在本轮复测。 |
| 2. UART 确认 | 依据原理图/preset 逐个构建合法的 UART MIO 候选配置；每次启动 hello 固件输出独特递增串 `BKB220-UART0-<seq>`。main 依次打开 Windows COM9、COM10、COM11，115200 8N1 先作候选，再按实际 PS 外设/串口配置调整；保存端口、MIO、baud、时间戳和原始日志。不得对无资料的 MIO 任意驱动/盲扫。 | 唯一的 MIO/COM 组合连续收到至少 10 条序号递增、无乱码输出；冷启动 PS init 后复测仍一致。 | 无字节：PS init/UART mux/COM通道/线缆；有乱码：baud/时钟/电平；多个通道重复：映射未唯一；检查 USB 串口驱动与 UART 引脚来源。由 main 执行。 |
| 3. DDR 初始化与安全区 | hello 固件代码/栈放 OCM，按最终 PS7 初始化执行 DDR write leveling/read gate/data-eye 等训练；记录初始化返回码/状态。由 main 先划定不覆盖 ELF、栈、FSBL、旧制品或项目数据的 scratch window，再做 walking-1/0、`0xAA55...`、地址线、固定种子 PRBS 写读；按合法容量边界做地址别名检查。测试范围/地址和恢复策略写入 run 记录。 | DDR 初始化/训练完成；每个 pattern 多轮逐字节一致；不同地址窗口无 alias；确认可用容量为至少产品手册规格 1GB。 | 初始化失败：先核 PS_CLK、DDR 类型/组织、时序、rail、delay；pattern 随机错：lane/DQS/走线/训练裕量；高地址 alias/读写失配：容量、地址位/片选或焊接；错误保留 raw log，不扩大到全系统数据区。由 main 执行。 |
| 4. GEM0/PHY 链路 | 仅在获取 PHY 资料/正确 MIO/reset 后启动 GEM0；通过 MDIO 读取 PHY ID/状态，记录 autoneg、速度/双工/错误计数。使用 main 已测 Windows 网卡 `192.168.1.100/24`，按记录的板 IP 做 ping 和最小 TCP 回环。 | 读到与原理图一致的 PHY ID，link up；Windows 与 PS 双向 ping/TCP 连续传输通过且计数增长、无链路反复掉线。 | MDIO 无响应：MIO/MDIO/reset/PHY 供电；PHY ID 不匹配：板型/地址/器件；PHY link down：RGMII 时钟/复位/线缆/协商；Host NIC Up 只证明 PC 侧，不能算 GEM PASS。由 main 执行。 |
| 5. CAPS | 最小应用运行协议栈，仅发送 `PKT_CAPS (0x06)`；不发送 WM/BATCH/POST、不启动数据流水线。按 `docs/04-interfaces.md` 解码 24B `CAPS_INFO (0x16)`。 | 收到版本1、read_bps=150、num_lc=50、stride=807、max_symbols=40500、max_reads=129600、features bit0=1；至少重复 3 次内容一致。 | TCP 无连接：回到 GEM；TCP 通但无响应：固件/监听端口；包头/长度不符：协议/缓冲；字段不符：XSA/ELF/编译参数不同源。由 main 执行并保存 PC 请求、板 UART 与原始响应。 |

F3 最小项仅覆盖 JTAG、PS UART、DDR、GEM0 与 CAPS；不会证明 QSPI/SD 冷启动、USB host/slave、生产 G3、P4/P16 timing 或性能。每个失败保留独立日志和报告；修复后重跑受影响步骤，不删除失败证据。

## 6. 板级入口审计与 ready=0 守卫

| 入口 | 审计结论 |
|---|---|
| `hw/boards/load_board.tcl` / `dna_load_board` | `id`、`ready`、`part` 是最先检查的必填字段；`id` 必须等于所选 profile 名。仅当 `ready` 字符串等于 `1` 时才继续检查非空 `uart`、`xdc`、`source_refs`、`ps7_properties`；通过后附加规范化的 `config_path` 并返回 dict。`pending` 不在 ready=1 的字段循环里，但 `ready!=1` 错误会读取它来说明拒绝原因，因此此 profile 保留该字段。非法板名、缺 profile、ID 不符和未 ready 都明确 `error`。 |
| `hw/boards/bkb220.tcl` | profile 有完整字段 `id/ready/part/uart/xdc/source_refs/ps7_properties/pending`，`ready=0`。`ps7_properties` 是候选草案，不会绕过守卫；pending 列出未核对的资料和 PS7 参数。 |
| `hw/boards/zynq_eco_7010.tcl` | 旧 ECO 的已验证基线；含旧板 DDR/MIO/时钟延迟，不作为 BKB220 的数值来源。 |
| `hw/scripts/build.tcl` / `dna_load_board` | 先解析参数和 P4/P16/100MHz 约束，随后调用 `dna_load_board`、核 part、XDC 与目录；`dry_run` 判断及 `create_project` 都在 loader 之后。因而 BKB220 `ready=0` 时在 `create_project` 前清晰失败，也不会 mkdir 构建目录。 |
| `hw/scripts/bd.tcl` | build 传入已验证的 `::dna_board_config` 后使用其中 `ps7_properties`。如果直接 source 且没有传入配置，脚本有历史兼容分支会选择 `zynq_eco_7010`；因此新板必须从 build/load_board 入口调用，不能把该 fallback 当 BKB220 默认。 |
| `tools/run_vivado_build.sh` | 选择显式 Vivado/VIVADO_ROOT/PATH，创建 `logs/vivado/<run-id>/` 再调用 Vivado；入口帮助已指出可用 `tclsh hw/scripts/build.tcl board=... dry_run=1` 做配置预检。此任务直接调用 tclsh，不启动 Vivado。 |
| `hw/constr/top.xdc` | 当前仅有说明注释；顶层没有 PL 外部引脚。PL 时钟由 BD 中 PS7 `FCLK_CLK0` 经 `clk_wiz_0` 输出，PS 固定 IO/DDR 由 PS7 及 BD 参数管理。因此候选 profile 复用 `hw/constr/top.xdc`，不把手册中的 PL U18/F16/F17 接入本系统顶层。 |

## 7. 本次执行结果

| 检查 | 实际命令/结果 | 状态 |
|---|---|---|
| 手册 SHA | `sha256sum -c SHA256SUMS.txt`（在 `docs/board/bkb220/`）；完整输出见本节上方。 | PASS，exit 0 |
| PDF 阅读/页面 | `pdfinfo`、两段 `pdftotext -layout` 和三次 `pdftoppm`；均 exit 0。目标页面 5–10、15–17、27 已目视检查。 | PASS（文档阅读与页码核对）；不含实物核验 |
| Profile 字段/属性列表语法 | 下方 `source hw/boards/bkb220.tcl` 的 Tcl 结构预检；exit 0，8 个必需字段齐全、29 对 PS7 key/value 无重复。 | PASS（仅 Tcl 结构，不验证 Vivado catalog） |
| ready=0 构建守卫 | `tclsh hw/scripts/build.tcl board=bkb220 dry_run=1`；exit 1，`dna_load_board` 报出未验证原因，调用栈显示在 `build.tcl` 的 profile 加载处停止。 | PASS（预期拒绝）；在 `create_project` 前失败 |
| 仓库根工具残留 | `find . -maxdepth 1 -type f \( -name '*.log' -o -name '*.jou' -o -name '*.str' -o -name '*.pb' \)`；exit 0、无输出。 | PASS |
| 新板实物/PS7/Vivado | 无触板、无 XSDB、无 Vivado、无 PS7 catalog 验证。 | 未测；由 main 按 F2/F3 资源门禁执行 |

字段/PS7 属性预检实际命令和输出：

```text
$ tclsh <<'TCL'
source hw/boards/bkb220.tcl
set required {id ready part uart xdc source_refs ps7_properties pending}
foreach key $required {
  if {![dict exists $board_config $key]} {error "missing field $key"}
}
if {[dict get $board_config id] ne "bkb220"} {error "wrong id"}
if {[dict get $board_config ready] ne "0"} {error "ready must remain 0"}
if {[llength $ps7_properties] % 2 != 0} {error "ps7_properties is not key/value pairs"}
set seen {}
foreach {key value} $ps7_properties {
  if {$key in $seen} {error "duplicate ps7 property $key"}
  lappend seen $key
}
puts "PROFILE_SCHEMA_PASS id=[dict get $board_config id] ready=[dict get $board_config ready] part=[dict get $board_config part] fields=[llength $required] ps7_property_pairs=[expr {[llength $ps7_properties] / 2}]"
TCL
PROFILE_SCHEMA_PASS id=bkb220 ready=0 part=xc7z020clg400-2 fields=8 ps7_property_pairs=29
exit_code=0
```

ready 守卫预检完整输出：

```text
$ tclsh hw/scripts/build.tcl board=bkb220 dry_run=1
板配置 'bkb220' 尚未验证：未核对实物完整器件顶标与PCB修订；PS_CLK来源及频率缺失；DDR VDD/VDDQ、板级走线/延迟与DQS-to-CLK缺失；UART0的PS MIO和COM映射缺失；ENET0的PHY型号、MIO/RGMII/MDIO/复位与时钟缺失；QSPI/SD0/USB0的实物连线和对应MIO/复位仍须核对；厂商board_files、PS7 preset、原理图和例程未提供；候选PS7属性名/器件支持情况尚未由Vivado 2022.2 catalog验证
    while executing
"error "板配置 '$board_id' 尚未验证：[dict get $board_config pending]""
    (procedure "dna_load_board" line 17)
    invoked from within
"dna_load_board $repo_root $board"
    invoked from within
"set ::dna_board_config [dna_load_board $repo_root $board]"
    (file "hw/scripts/build.tcl" line 25)
exit_code=1
```

该错误发生在 `dna_load_board` 对 `ready` 的守卫中；`build.tcl` 尚未走到输出目录 `file mkdir`、dry-run PASS 分支或 `create_project`。profile 文件已被 Tcl 解释并完成字段/属性列表检查；Vivado 属性名、值域、器件支持仍未验证。

本次改动路径：`hw/boards/bkb220.tcl`、`docs/board/bkb220/migration-source-table.md`。仍缺项和下一步依赖见第 4 节；进入 F3 的依赖是厂商/PCB 来源补齐、main 审核配置、Vivado 2022.2 PS7/catalog 验证以及 ready 守卫通过。

## 8. F3 阶段二：Vivado 2022.2 PS7 catalog 验证与上板候选

更新：2026-10-12。**本节只追加阶段二结果；第 1–7 节保留第一阶段当时的结论。**`hw/boards/bkb220.tcl` 未改，`ready=0` 保持不变。本阶段没有连接 JTAG、串口或板卡，没有下载、reset、DDR 读写，也没有生成 bit/XSA 或运行综合/实现。所有板端步骤仍由 main 执行。

### 8.1 Vivado 工程与可复现入口

- 工具：`/tools/Xilinx/Vivado/2022.2/bin/vivado`，版本输出 `Vivado v2022.2 (64-bit) / SW Build 3671981 / IP Build 3669848`。
- 最终探测 run：`hw/build/bkb220-ps7-probe/20261012T114440Z-board-migrate-r3/`。其中 `ps7_probe.tcl` 从仓库的 `hw/boards/bkb220.tcl` 读取原始 29 对 `ps7_properties`，逐条设置并读回；每个变体创建独立工程和 standalone `processing_system7:5.5` IP，调用 `validate_ip` 与 `generate_target all`。输出 `.xci`、`ps7_init.tcl`、`ps7_init.html`；没有 `synth_design`、综合 run、implementation run 或 XSA/bit 导出。
- 最终实际命令：

```bash
VIVADO_ROOT=/tools/Xilinx/Vivado/2022.2 \
/tools/Xilinx/Vivado/2022.2/bin/vivado -mode batch \
  -source hw/build/bkb220-ps7-probe/20261012T114440Z-board-migrate-r3/ps7_probe.tcl \
  -log hw/build/bkb220-ps7-probe/20261012T114440Z-board-migrate-r3/vivado.log \
  -journal hw/build/bkb220-ps7-probe/20261012T114440Z-board-migrate-r3/vivado.jou \
  > hw/build/bkb220-ps7-probe/20261012T114440Z-board-migrate-r3/vivado.stdout.txt 2>&1
```

  实际以 `> .../vivado.stdout.txt 2>&1` 捕获控制台；shell `exit_code=0`。四个 `IP_VALIDATE` 与四个 `GENERATE_TARGET` 均为 `rc=0`，四个变体都生成了 `ps7_init.tcl/.html/.xci`。完整命令记录和逐属性结果分别在 `vivado.log`、各变体的 `property-results.tsv` 与 `effective-ddr.txt`。
- 保留的中间失败：首轮 `20261012T114440Z-board-migrate` 因 Vivado Tcl 不含 `lmap` 退出 1；第二轮 `...-r2/` 的属性探测完成，但其 standalone PS7 被放入空 BD 后 `generate_target` 对四个变体均报未连接 M_AXI_GP0/时钟、BD 生成失败（`BD 41-2670`、`BD 41-758`、`BD 41-1031`）。两轮均保留；r3 改为独立 standalone PS7 IP 后通过。r2 的逐属性日志仍用于记录**原始 profile 直设**时的拒绝/忽略情况，r3 用于最终生成候选。
- Vivado 启动日志有本机环境提示：`CRITICAL WARNING: [Common 17-741] No write access right to the local Tcl store ... XilinxTclStore is reverted to the installation area.` Vivado 回退安装目录 Tcl Store，命令继续完成；此项不是 PS7 属性错误。r3 `validate_ip` 另记录 `[Vivado 12-3672]` / `[Vivado 12-3670]` 两条“`is_managed` / `generate_synth_checkpoint` should only be queried on the file object”警告，来自探测脚本把 IP 对象交给 `validate_ip`，四次 `validate_ip` 仍为 `rc=0`，`generate_target` 也全部 `rc=0`；完整原文见 r3 `vivado.log`。

### 8.2 器件 part 与工业级表示

Vivado 2022.2 实际 `get_parts` 结果中，与 CLG400 有关的 Z020 条目是：

| Vivado part | Catalog 属性 | 结论 |
|---|---|---|
| `xc7z020clg400-1` / `-2` / `-3` | `DEVICE=xc7z020`；`SPEED=-1/-2/-3`；`TEMPERATURE_GRADE_LETTER` 为空，温度上下限属性为 0。 | 三项均在库；profile 的 `xc7z020clg400-2` **被 catalog 接受**，表示普通 `xc7z020` 的 -2 档，不能据此声称工业级。 |
| `xc7z020iclg400-1L` | `DEVICE=xc7z020i`、`SPEED=-1L`、`TEMPERATURE_GRADE_LETTER=I`、`MIN_OPERATING_TEMPERATURE=-40`、`MAX_OPERATING_TEMPERATURE=100`。 | Vivado 此库中 CLG400 的工业级条目；命名中 `i` 位于 device 后、package 前，part 对象的温度等级属性是只读信息。 |
| `xc7z020iclg400-2`、`xc7z020clg400-2i` | `get_parts` 精确查找均不存在。 | 手册料号 `XC7Z020-2CLG400I` 对应的工业级 -2 CLG400 在本机 2022.2 catalog **未找到**。近似的 `xc7z020iclg400-1L` 速度档不同，不能当作等价别名。 |

`xc7z020clg400-2` 的存在性为 PASS；手册完整料号与已安装 catalog 的工业级 -2 part 对应关系仍未解决。须由 main 核对芯片顶标/PCB 修订并决定实际 `part`，此项不解除 `ready=0`。

### 8.3 profile 的 29 项属性逐条结果

下表“直设结果”来自 r2 中每次单独 `set_property` 后的异常、日志警告和 `get_property` 读回。DDR partno 被拒后，Vivado 将 DDR 回滚到默认 `MT41J128M8 JP-125`；此时后续标记为 disabled 的 DDR 参数**即使读回刚好等于草案，也不代表新值已生效**。最终可生成的四个 r3 变体在 `DDR_PARTNO=Custom` 下重新逐项设置，并通过 IP 验证与 `generate_target`。

| `hw/boards/bkb220.tcl` 属性 | 草案值 | 直设结果 | r3 `Custom` 最终有效值 |
|---|---:|---|---|
| `PCW_USE_M_AXI_GP0` | `1` | 接受，读回 `1` | `1` |
| `PCW_USE_S_AXI_HP0` | `1` | 接受，读回 `1` | `1` |
| `PCW_EN_CLK0_PORT` | `1` | 接受，读回 `1` | `1` |
| `PCW_FPGA0_PERIPHERAL_FREQMHZ` | `100` | 接受，读回 `100` | `100` MHz |
| `PCW_PRESET_BANK0_VOLTAGE` | `LVCMOS 3.3V` | 接受，读回相同 | `LVCMOS 3.3V` |
| `PCW_PRESET_BANK1_VOLTAGE` | `LVCMOS 1.8V` | 接受，读回相同 | `LVCMOS 1.8V` |
| `PCW_UIPARAM_DDR_ENABLE` | `1` | 接受，读回 `1` | `1` |
| `PCW_UIPARAM_DDR_MEMORY_TYPE` | `DDR 3` | 接受，读回相同 | `DDR 3` |
| `PCW_UIPARAM_DDR_BUS_WIDTH` | `32 Bit` | 接受，读回相同 | `32 Bit` |
| `PCW_UIPARAM_DDR_PARTNO` | `MT41K256M16TW-107` | **拒绝**；读回恢复为 `MT41J128M8 JP-125` | `Custom`；手动几何/时序可用，但 XCI 不再绑定目标 Micron part 名称 |
| `PCW_UIPARAM_DDR_DRAM_WIDTH` | `16 Bits` | disabled 警告，**忽略**；有效值仍为 `8 Bits` | `16 Bits` |
| `PCW_UIPARAM_DDR_DEVICE_CAPACITY` | `4096 MBits` | disabled 警告，**忽略**；有效值仍为 `1024 MBits` | `4096 MBits`（每颗 x16 器件） |
| `PCW_UIPARAM_DDR_SPEED_BIN` | `DDR3_1066F` | disabled 警告，**忽略**；读回同值是默认值巧合 | `DDR3_1066F` |
| `PCW_UIPARAM_DDR_FREQ_MHZ` | `533.333333` | 接受，读回相同 | `533.333333` MHz |
| `PCW_UIPARAM_DDR_CL` | `7` | disabled 警告，**忽略**；读回同值是默认值巧合 | `7` |
| `PCW_UIPARAM_DDR_CWL` | `6` | disabled 警告，**忽略**；读回同值是默认值巧合 | `6` |
| `PCW_UIPARAM_DDR_T_RCD` | `7` | disabled 警告，**忽略**；读回同值是默认值巧合 | `7` CK |
| `PCW_UIPARAM_DDR_T_RP` | `7` | disabled 警告，**忽略**；读回同值是默认值巧合 | `7` CK |
| `PCW_UIPARAM_DDR_T_RC` | `50.625` | disabled 警告，**忽略**；有效值 `48.75` | `50.625` ns |
| `PCW_UIPARAM_DDR_T_RAS_MIN` | `37.5` | disabled 警告，**忽略**；有效值 `35.0` | `37.5` ns |
| `PCW_UIPARAM_DDR_T_FAW` | `50.0` | disabled 警告，**忽略**；有效值 `30.0` | `50.0` ns |
| `PCW_UART0_PERIPHERAL_ENABLE` | `1` | 接受，读回 `1` | UART0 变体 `1`；UART1 变体覆盖为 `0` |
| `PCW_ENET0_PERIPHERAL_ENABLE` | `1` | 接受，读回 `1` | `1`（候选，见 §8.6） |
| `PCW_QSPI_PERIPHERAL_ENABLE` | `1` | 接受，读回 `1` | `1` |
| `PCW_QSPI_QSPI_IO` | `MIO 1 .. 6` | 接受，读回相同 | `MIO 1 .. 6` |
| `PCW_QSPI_GRP_SINGLE_SS_ENABLE` | `1` | 接受，读回 `1` | `1` |
| `PCW_QSPI_GRP_SINGLE_SS_IO` | `MIO 1 .. 6` | 接受，读回相同 | `MIO 1 .. 6` |
| `PCW_SD0_PERIPHERAL_ENABLE` | `1` | 接受，读回 `1` | `1` |
| `PCW_USB0_PERIPHERAL_ENABLE` | `1` | 接受，读回 `1` | `1` |

DDR partno 原始日志（r2 `vivado.log`，PS7 BD Cell）：

```text
ERROR: [IP_Flow 19-3478] Validation failed for parameter 'PCW UIPARAM DDR PARTNO(PCW_UIPARAM_DDR_PARTNO)' with value 'MT41K256M16TW-107' for BD Cell 'processing_system7_0'. PARAM PCW_UIPARAM_DDR_PARTNO :: MT41K256M16TW-107 is out of range { MT41J128M8 JP-125,MT41J128M8 JP-15E,MT41J64M16 JT-125G,MT41J64M16 JT-15E,MT41J256M8 DA-107,MT41K128M16 JT-125,MT41J256M8 HX-125,MT41J256M8 HX-15E,MT41J256M8 HX-187E,MT41J128M16 HA-107G,MT41J128M16 HA-125,MT41J128M16 HA-15E,MT41J128M16 HA-187E,MT41J512M8 RA-15E,MT41K128M16 HA-15E,MT41K256M16 RE-125,MT41K256M16 RE-15E,MT41K256M8 DA-125,MT41K256M8 DA-15E,MT41K256M8 HX-15E,MT41J256M16 RE-125,Custom }
```

按器件名/组织最接近的 PS7 下拉项是 `MT41K256M16 RE-125` 与 `MT41K256M16 RE-15E`：它们和手册 `MT41K256M16TW-107` 共享 `MT41K256M16` 基名，但 catalog 后缀/速度档代码不同，Vivado 不会把它们自动视作同一料号。安装树的 DDR memory IP CSV 虽列有 `MT41K256M16TW-107`，PS7 IP 自己的 `PCW_UIPARAM_DDR_PARTNO` 允许值仍明确拒绝它；不能以通用 CSV 存在代替 PS7 接受。

直设期间的原始 disabled 警告示例（同类警告也覆盖 speed bin、CL/CWL、tRCD/tRP、tRC/tRAS/tFAW）：

```text
WARNING: [BD 41-721] Attempt to set value '16 Bits' on disabled parameter 'PCW_UIPARAM_DDR_DRAM_WIDTH' of cell '/processing_system7_0' is ignored
WARNING: [BD 41-721] Attempt to set value '4096 MBits' on disabled parameter 'PCW_UIPARAM_DDR_DEVICE_CAPACITY' of cell '/processing_system7_0' is ignored
WARNING: [BD 41-721] Attempt to set value 'DDR3_1066F' on disabled parameter 'PCW_UIPARAM_DDR_SPEED_BIN' of cell '/processing_system7_0' is ignored
WARNING: [BD 41-721] Attempt to set value '7' on disabled parameter 'PCW_UIPARAM_DDR_CL' of cell '/processing_system7_0' is ignored
WARNING: [BD 41-721] Attempt to set value '6' on disabled parameter 'PCW_UIPARAM_DDR_CWL' of cell '/processing_system7_0' is ignored
WARNING: [BD 41-721] Attempt to set value '7' on disabled parameter 'PCW_UIPARAM_DDR_T_RCD' of cell '/processing_system7_0' is ignored
WARNING: [BD 41-721] Attempt to set value '7' on disabled parameter 'PCW_UIPARAM_DDR_T_RP' of cell '/processing_system7_0' is ignored
WARNING: [BD 41-721] Attempt to set value '50.625' on disabled parameter 'PCW_UIPARAM_DDR_T_RC' of cell '/processing_system7_0' is ignored
WARNING: [BD 41-721] Attempt to set value '37.5' on disabled parameter 'PCW_UIPARAM_DDR_T_RAS_MIN' of cell '/processing_system7_0' is ignored
WARNING: [BD 41-721] Attempt to set value '50.0' on disabled parameter 'PCW_UIPARAM_DDR_T_FAW' of cell '/processing_system7_0' is ignored
```

r3 先将 `PCW_UIPARAM_DDR_PARTNO` 设为 PS7 接受的 `Custom`，再设置 profile 的其余 DDR 属性；四个变体的 `validate_ip` 和 `generate_target all` 都成功。最终有效值与草案中的容量、速度档和 tRC/tRAS/tFAW 一致：32-bit bus、单颗配置 16-bit/4096 Mbit、533.333333 MHz、CL7/CWL6、tRCD/tRP 7 CK、tRC 50.625 ns、tRAS 37.5 ns、tFAW 50.0 ns；地址几何为 row=15/column=10/bank=3、BL=8。两颗 x16 组成总线 32-bit，对应手册所述 1GB。**这证明的是 Vivado `Custom` 配置接受并写入 PS7 IP，不是实物训练/读写通过。**

由于 profile 未提供走线延迟，四个最终 XCI 还带有 Vivado 默认 `PCW_UIPARAM_DDR_BOARD_DELAY0..3=0.25`、`PCW_UIPARAM_DDR_DQS_TO_CLK_DELAY_0..3=0.0`；它们不是 BKB220 测量值。`DDR_HIGH_TEMP` 仍为工具默认 `Normal (0-85)`。这两项连同 PCB 走线、VDD/VDDQ 与实际器件后缀仍需 main/厂商资料确认，不能由 `Custom` 模式或生成成功升级为板级 PASS。

### 8.4 PS_CLK 与其余候选属性

main 提供的 2026-10-12 现场证据：`IO_PLL_CTRL` 的 FBDIV=26，推导 IO PLL=433.33 MHz；BootROM 在 JTAG 待机态正常运行。由此把 PS_CLK 记为 **33.333 MHz（推导 + 可复现寄存器证据）**，不是厂商书面确认。本次在每套 IP 额外设置 `CONFIG.PCW_CRYSTAL_PERIPHERAL_FREQMHZ {33.333333}`，Vivado 读回完全相同；PS7 其余读回包括 IO PLL=1000 MHz、APU=666.666666 MHz、UART peripheral clock=100 MHz。

四套候选都额外设置并被 Vivado 精确读回：

| 属性 | 值 | 验证边界 |
|---|---|---|
| `PCW_ENET0_ENET0_IO` | `MIO 16 .. 27` | Vivado 接受，板级 RGMII 接线仍未核实。 |
| `PCW_ENET0_GRP_MDIO_ENABLE` | `1` | Vivado 接受。 |
| `PCW_ENET0_GRP_MDIO_IO` | `MIO 52 .. 53` | Vivado 接受；不是旧板值已被证明适用于 BKB220。 |
| `PCW_ENET0_PERIPHERAL_FREQMHZ` | `1000 Mbps` | Vivado 接受该枚举值；不是链路已建立。 |
| `PCW_CRYSTAL_PERIPHERAL_FREQMHZ` | `33.333333` | Vivado 接受；PS_CLK 来源仍属 main 的寄存器推导。 |

ENET0 是交给 main 的**待实测候选**。必须由 main 用 MDIO 读到与实物一致的 PHY ID，再核 PHY reset、参考时钟、协商和链路；在此之前不宣称 PHY 型号、RGMII 时序或网络 PASS。

### 8.5 四套 UART 初始化候选

四个 UART MIO 组合在 Vivado 2022.2 均被接受；r3 每个属性逐条读回一致，`IP_VALIDATE=rc 0`、`GENERATE_TARGET=rc 0`。路径以 repo root 为基准；每个目录还保留独立 `.xci`、`.html`、`property-results.tsv` 和 Vivado project。

| 变体 | 逐条 UART 属性 | `ps7_init.tcl` | SHA-256 |
|---|---|---|---|
| `v1-uart0-mio14-15` | `PCW_UART0_PERIPHERAL_ENABLE=1`；`PCW_UART1_PERIPHERAL_ENABLE=0`；`PCW_UART0_UART0_IO={MIO 14 .. 15}`；`PCW_UART0_BAUD_RATE=115200` | `hw/build/bkb220-ps7-probe/20261012T114440Z-board-migrate-r3/v1-uart0-mio14-15/ps7_init.tcl` | `2f80e045cb18d7c37d5144bf0a819cd8fd42d09a622fca164f2ef7b007b6c81f` |
| `v2-uart0-mio46-47` | `PCW_UART0_PERIPHERAL_ENABLE=1`；`PCW_UART1_PERIPHERAL_ENABLE=0`；`PCW_UART0_UART0_IO={MIO 46 .. 47}`；`PCW_UART0_BAUD_RATE=115200` | `hw/build/bkb220-ps7-probe/20261012T114440Z-board-migrate-r3/v2-uart0-mio46-47/ps7_init.tcl` | `4e401a4886ccade2e97de36de2a5bda80be792828fbb2de488bf8c9168f9e2d2` |
| `v3-uart1-mio08-09` | `PCW_UART0_PERIPHERAL_ENABLE=0`；`PCW_UART1_PERIPHERAL_ENABLE=1`；`PCW_UART1_UART1_IO={MIO 8 .. 9}`；`PCW_UART1_BAUD_RATE=115200` | `hw/build/bkb220-ps7-probe/20261012T114440Z-board-migrate-r3/v3-uart1-mio08-09/ps7_init.tcl` | `b06959ccdeb9f867933411bc45dc061e9d6c3eff48ff4bb2ee08e10c7685d16a` |
| `v4-uart1-mio48-49` | `PCW_UART0_PERIPHERAL_ENABLE=0`；`PCW_UART1_PERIPHERAL_ENABLE=1`；`PCW_UART1_UART1_IO={MIO 48 .. 49}`；`PCW_UART1_BAUD_RATE=115200` | `hw/build/bkb220-ps7-probe/20261012T114440Z-board-migrate-r3/v4-uart1-mio48-49/ps7_init.tcl` | `308390212b257f3263c1e6f5e84e22a57d5cce8454110939980e38be8b6e456e` |

UART baud 属性均为 115200；PS7 IP 没有独立 PCW 数据位/校验/停止位属性，8N1 应由后续最小 UART ELF 驱动设置/确认。生成 Tcl 的 MIO 写寄存器也随候选变化（例如 UART0 MIO14/15 对应 `0xF8000738/0xF800073C`，MIO46/47 对应 `0xF80007B8/0xF80007BC`），说明不是同一份被改名的文件。四种组合仍都是**待主机串口实测的 MIO 候选**，catalog 通过不等于知道哪个 FTDI 通道接 PS UART。

### 8.6 main 可直接照做的 F3 清单

**风险边界：`rst -system` 会复位整板。每试一套都必须 reset 并重新运行该套 `ps7_init`/`ps7_post_config`。错误 DDR 参数、未知板级延迟或错 MIO 可能导致训练失败、XSDB 失去目标或系统挂起。只使用 main 已运行的 Linux `hw_server` `TCP:127.0.0.1:3132`；禁止在 Windows 启动 hw_server。**

1. 在 WSL 开三个终端，分别持续监听 main 已确认的 `/dev/ttyUSB1`、`/dev/ttyUSB2`、`/dev/ttyUSB3`，每个端口 115200、8N1。例如每个终端分别执行（换成对应设备）：

   ```bash
   stty -F /dev/ttyUSB1 115200 cs8 -cstopb -parenb raw -echo
   cat -v /dev/ttyUSB1
   ```

   本任务没有打开这些设备。当前 WSL 没有 `picocom`/`minicom`/`tio`/`screen` 或 pyserial，因此上面的 `stty`+`cat` 使用系统自带工具；三路要在三个终端同时监听。**只运行 PS7 init 时没有 hello 固件，三个串口都可能保持静默；静默不能判断 UART MIO，也不单独表示 DDR 失败。**

2. 先选一个候选（如 v1），启动 WSL XSDB 2022.2：

   ```text
   /tools/Xilinx/Vitis/2022.2/bin/xsdb
   xsdb% connect -url TCP:127.0.0.1:3132
   xsdb% targets
   xsdb% targets -set -filter {name =~ "APU*"}
   xsdb% rst -system
   xsdb% source /home/lucian/projects/FPGA/FpgaAccelerationSystemOfDataReadout/hw/build/bkb220-ps7-probe/20261012T114440Z-board-migrate-r3/v1-uart0-mio14-15/ps7_init.tcl
   xsdb% ps7_init
   xsdb% ps7_post_config
   ```

   XSDB 本机版本只读检查为 `2022.2`；此任务没有执行 `connect`。若 target 列表实际名称不同，main 以 `targets` 输出中唯一 APU/CPU0 目标为准，不要选 PL 目标。

3. 先把 init-only 结果记作**PS7 初始化/DDR 控制器轮询初筛**，不要把它当作完整 DDR 容量或读写 PASS。生成的 `ps7_init.tcl` 中 `ps7_init` 没有显式 `return 0/DDR_PASS`；DDR 初始化过程包含 `mask_poll 0xF8000B74 0x00002000` 和 `mask_poll 0xF8006054 0x00000007`，超时时会在 XSDB 控制台打印 `Timeout Reached. Mask poll failed at ADDRESS: ...`，但 `mask_poll` 是打印后 break，不会可靠地向上层返回失败码。因此初筛 PASS 条件是：`ps7_init` 与 `ps7_post_config` 都执行结束、APU 仍可响应，且两个 DDR 轮询均无 `Timeout Reached`/XSDB 错误；任一超时、异常或 APU 丢失均 FAIL。PS7 Tcl 自身没有 DDR 校准的 UART 打印。

4. 真实 DDR 访问和 UART 通道归属需要 main 另准备**最小 hello ELF**：代码、向量和栈放 OCM，分别为 UART0 / UART1 构建合适的串口驱动配置；串口 115200 8N1。ELF 先输出唯一递增标记，再只对 main 划定的 DDR scratch window 做 bounded write/read（固定图样、反码/地址相关图样、多轮逐字比较），全匹配才打印 `DDR_SMOKE_PASS`，否则打印 `DDR_SMOKE_FAIL` 并停下。不能用旧 ECO 的 UART1 ELF 假设新板管脚，也不要在没有划定 scratch 区前访问 DDR。这个 ELF 本阶段未构建。

   - DDR smoke PASS：hello 从 OCM 启动；出现 `DDR_SMOKE_PASS`；指定 scratch 区所有读回与写入逐字一致；XSDB/CPU 无挂死。该结果只证明本次安全区可用，不证明完整 1GB 容量或全地址无 alias，后续按 F3 容量/地址线检查补测。
   - UART 映射 PASS：同一 hello 的至少 10 条递增标记无乱码，且只在 `/dev/ttyUSB1/2/3` 中唯一一路收到；记录 UART 编号、MIO、ttyUSB、波特率、原始日志与 `ps7_init.tcl` SHA。没有串口字节时映射仍为未测，不能把“没看到打印”归因于 DDR。

5. 对 v2/v3/v4 重复：三路监听保持开启，重新 `targets` 选择 APU、`rst -system`、source 对应绝对路径、执行 `ps7_init` 与 `ps7_post_config`，再下载匹配 UART0/1 的 OCM hello。每个 variant 都单独记录 run、串口原始输出、DDR scratch 地址/长度/图样和上述哈希；不把一次变体的 init 套用到下一变体。

**失败后恢复干净 JTAG 态：**停止当前 hello/串口采集，XSDB 仍可用时重新选 APU 并执行 `rst -system`；若 target 消失，先 `connect -url TCP:127.0.0.1:3132`、等待 `targets` 重新枚举，再选 APU 执行 `rst -system`。当前 BOOT_MODE=0 时复位回 BootROM 的 JTAG 待机态；main 按初始现场基线复核 JTAG/BOOT_MODE、DDR PLL 掉电、FCLK0/GEM/UART 未被旧配置保持开启。恢复后不要 source 错误候选或继续 DDR 访问，先保存 XSDB/串口日志，再由 main 决定下一项；不切换拨码、不写 QSPI/SD、不启动 Windows hw_server。若 JTAG reset 后仍不可访问，停止候选测试并由 main 处理供电/线缆/硬件恢复。

### 8.7 阶段结果与未完成项

| 验收项 | 结果 |
|---|---|
| PS7 profile 29 属性逐条 Vivado 检查 | 已测。非 DDR 组和 bank/QSPI 等读回通过；目标 DDR partno 被拒，依赖该 part 的手工容量/时序在默认 part 下 disabled；改用 `Custom` 后最终手动参数有效。原文日志及逐属性 TSV 均保留。 |
| `xc7z020clg400-2` 在 2022.2 catalog | PASS（存在）；它不是 catalog 中标记工业级 `I` 的 part。手册工业级 -2 的精确 catalog 条目未找到。 |
| 四套 UART `ps7_init` + SHA | PASS（四套 IP validate/generate 均 `rc=0`，SHA 见 §8.5）；UART/COM 实际归属未测。 |
| ENET0 候选属性 | PASS（Vivado 接受）；MDIO PHY ID/链路未测。 |
| Vivado 综合、实现、bit/XSA | 未测/未运行（本任务明确不做）。 |
| JTAG、串口、DDR 训练实板结果 | 未测/未触板，由 main 按 §8.6 执行。 |
| 最小 OCM hello ELF / DDR scratch smoke | 未完成；main 需要按 UART0/1 分别准备可打印 ELF。 |
| `ready` 与第一阶段两份产物 | `ready=0` 未变；第一阶段表与 profile 结论未改。 |

## 9. F3 实板最小启动结果（2026-10-12，main 持板执行）

本节由 main 在真板上执行并记录，**取代** §8.7 中「未触板」的对应行。执行通道是 WSL：`usbipd` 直通 FT4232H → Linux `/tools/Xilinx/Vivado/2022.2/bin/hw_server -sTCP:127.0.0.1:3132` → `/tools/Xilinx/Vitis/2022.2/bin/xsdb`。**全程未启动 Windows hw_server**（见 `docs/07` §3a）。

- 运行目录（仓库内，`logs/` 已被 .gitignore 覆盖）：`logs/bringup/20261012T120117Z-bkb220-f3-v1/`
- 使用的 ps7_init：`hw/build/bkb220-ps7-probe/20261012T114440Z-board-migrate-r3/v1-uart0-mio14-15/ps7_init.tcl`，SHA-256 `2f80e045cb18d7c37d5144bf0a819cd8fd42d09a622fca164f2ef7b007b6c81f`

### 9.1 已实测通过

| 项 | 判据 | 实际结果 |
|---|---|---|
| JTAG | 单目标、器件正确 | 链 `Xilinx HW-Z1-ZCU104 FT4232H 15051A` → `arm_dap (4ba00477)` → `xc7z020 (23727093)`；APU 目标唯一 |
| PS 初始化 | `ps7_init` / `ps7_post_config` 退出码 | 两者 **RC=0** |
| MIO 生效 | 回读寄存器等于生成值 | `MIO_PIN_14 = 0x000016E1`、`MIO_PIN_15 = 0x000016E0`（与 ps7_init 写入逐位一致） |
| 时钟 | 回读 PLL/时钟寄存器 | `0xF800010C` 是 **PLL_STATUS**（本文档早前误称 DDR_PLL_CTRL，已更正）= `0x3F`，三个 PLL 全部 lock+stable；ARM PLL FBDIV=40 → 666.67 MHz；**DDR PLL FBDIV=32 → 533.33 MHz（DDR3-1066）**；IO PLL FBDIV=30 → 500 MHz，FCLK0 分频 5 → **100 MHz** |
| **DDR 训练与读写** | 0x10000000 起 1024 字写入后逐字回读 | **0/1024 不符**，写入模式 `0xA5A50000 \| i`。DDR 可用 |
| **PS UART 归属** | 经 JTAG 直接写 UART0 TX FIFO（`0xE0000030`），三路串口同时被动抓取 | **`/dev/ttyUSB2` 收到 8 条 `BKB220-UART0-1..8` 共 128 字节，ASCII 完全正确**；`/dev/ttyUSB1`、`/dev/ttyUSB3` 各 0 字节 |

**结论（可以对外说）**：BKB220 的 PS UART 是 **UART0、MIO 14/15**，经 FT4232H **通道 C** 接到主机，**115200 8N1**（ASCII 明文正确即证明波特率正确）。项目 `--ip`/`--uart-port` 中的串口项在新板应取该通道。

### 9.2 仍未通过 / 未测（不得写成通过）

| 项 | 状态 | 观察与下一步 |
|---|---|---|
| **ENET0 / PHY** | ~~未通过~~ → **通过（2026-10-12 更正，见 §9.6）** | 一度报"未通过"，实为 main 读错完成标志（应读 `NETWORK_STATUS[2]`）且写错管理端口使能位（MDEN = `NETWORK_CONTROL` bit4，不是 bit3）。改对后 PHY 正常应答：**Realtek RTL8211E**、自协商完成、**1000BASE-T 全双工 link up**。RGMII MIO16-27 + MDIO MIO52-53 配置**已实测可用**。 |
| UART 反向（PC→PS） | 未测 | 本次只证明了 PS→PC 方向；交互式使用还需确认 RX 方向 |
| CAPS / 协议栈 | 未测 | 需要能跑 lwIP 的 hello 固件，依赖 GEM |
| QSPI / SD 冷启动 | 未测 | JTAG 启动通过不证明冷启动 |
| bit / XSA / 整机 route | 未生成 | 属 F4 |
| DDR 板级延迟、DQS-to-CLK | 未测 | 本轮用 Vivado `Custom` 默认值；DDR 能读写不等于这些参数已优化或已由数据手册确认 |
| 工业级器件精确料号 | 未定 | `xc7z020clg400-2` 在 catalog 中存在，但手册写的 `XC7Z020-2CLG400I` 对应的工业级条目未确认 |

### 9.3 对 `ready` 的判断

~~**`ready` 保持 `0`**~~（2026-10-12 更新）：ENET0 已实测通过（§9.6），本表原先"ENET0 未证实故不能置 1"的理由不再成立。`ready` 现为 **1**，依据是用户明确授权"先建 P4、ENET0 留到板测再验"，**且 ENET0 随后也已实测通过**。仍属未证实、板测须验的项：工业级料号等级、DDR 板级延迟与 DQS-to-CLK（用 Custom 默认值）、QSPI/SD 冷启动。

### 9.4 环境侧教训（供后续 agent 复用）

1. **杀掉 hw_server 后必须真正重新枚举 USB**（`usbipd detach` 再 `attach`，确认设备号变化），否则 JTAG 链只显示 `xc7z020`、看不到 `arm_dap`，会误判成「PS 不在链上」。仅重启 hw_server 无效。
2. `0xF800010C` 是 **PLL_STATUS**，不是 DDR_PLL_CTRL；DDR PLL 控制寄存器是 `0xF8000104`。本文档 §9.1 已按此更正。
3. WSL 内 `/dev/ttyUSB*` 属 `root:plugdev`，普通用户需临时放开权限或用 sudo 才能做串口采集（JTAG 走 libusb，不受此限）。
5. **断电复位后必须先跑 `ps7_init`，MDIO 才会有反应。** 2026-10-12 实测：板子断电重上后，MDIO 对 PHY 0/1 的**所有寄存器都读回 `0x0000`**（连 `PHYID` 都是 0），而同一时刻 Windows 侧 ASIX 网卡显示 **Up 1 Gbps**（说明 PHY 本身活着、已 link）。原因不是故障：**MDIO 要 `MIO52/53` 被 mux 成 GEM 的 MDIO 功能才通**，断电后 PS 回到 BootROM 默认态、MIO 未配置。跑完 `ps7_init` 后 `MIO_PIN_52/53 = 0x1280`，MDIO 立刻恢复（`PHYID=0x001C/0xC915`）。**所以：任何 MDIO/PHY 观测都必须排在 `ps7_init` 之后**；断电后的第一次读为 0 不代表 PHY 或线有问题。
6. **`BMSR` bit2（链路状态）是 latching-low，单次读会误判。** 实测同上：link 事件后的第一次读 bit2=0（锁存"曾掉线"），**后续读稳定为 1**（`0x796D`）。**判断链路当前状态至少要读两次**，或用非锁存的佐证 —— `reg10 (1000BASE-T 状态) bit11 = 对端千兆全双工能力`、`ANLPAR != 0`。这条不影响此前网线 A/B 的结论（坏线那组连续 20 次采样 bit2 全为 0，是真没起来），但它解释了旧线复测时"第一次读是 down"的现象。
7. **Windows 侧硬件服务与 USB 归属不跨断电存活。** 板子断电后 FT4232H 回落到 Windows（COM9/10/11 重新出现），`usbipd` 直通断开且状态回到 `Shared`；端口 3132 上会留下一个**已经没有设备的旧 `hw_server`**。恢复顺序：按端口找 PID 杀掉旧实例 → `usbipd attach --wsl --busid 4-2` → 起新 `hw_server`。
4. 被动抓串口刻意排在 `rst -system` 之前：ftdi_sio 在 open 时会拉起 DTR/RTS，若该线接 PS 复位，顺序倒过来会干扰初始化。

### 9.5 ENET0/PHY 探测记录（供下一步接手，避免重复）

按顺序实际做过、并已排除的假设：

| # | 尝试 | 结果 | 排除的假设 |
|---|---|---|---|
| 1 | 直接读 `GEM0{0xE000B000}` 的 NETWORK_CONTROL/CONFIG/STATUS/PHY_MAINT | CONTROL=0、CONFIG=0x80000、STATUS=0x6、PHY_MAINT=0 | —— |
| 2 | 设 MDC 分频（`NETWORK_CONFIG[7:4]=0xF`）后扫 PHY 0..31 的 reg 2/3 | **全部 IDLE 位不置位（超时）** | 「不设分频就能读」 |
| 3 | 释放 APER 复位（`0xF8000244=0`）后再扫 | APER 本来就是 `0`（GEM0 未被复位）；改 `[7:4]=8` 后**读能完成但全地址无有效 ID** | 「GEM0 被 APER 复位挡住」 |
| 4 | 改回最慢 `[7:4]=0xF` 扫 12 个常见 PHY 地址 | **又变成全部超时** | —— |

由此可确定的与仍不能确定的：

- **可确定**：GEM0 的时钟（`0xF8000140=0x00100801`，IO PLL/8=62.5 MHz）与复位状态都正常；MIO52/53 已写 `0x1280`（与旧 ECO 板 UART 版 ps7_init 里 MDIO 的编码一致）。
- **不能确定**（不要写成事实）：MDC 分频字段究竟取 `[7:4]` 还是 `[6:4]`——两次结果互相矛盾，说明**仅靠寄存器回读无法自证 MDC 频率**；以及 PHY 是否被某个未驱动脚保持复位、MDIO 是否真的在 MIO52/53、板卡是否其实用 GEM1。
- **下一步的正当做法**（任一即可让步）：① 拿到厂商 PCB 原理图或 board_files preset；② 用示波器/逻辑分析仪看 MDC/MDIO 是否真的翻转（本机无此仪器，不得声称已测）；③ 在能跑 lwIP 的固件里用 Xilinx 驱动做 PHY 探测并按驱动报错定位。
- **不要做**：把某组猜测值写进 profile 后置 `ready=1` 声称 PHY 已确认；也不要反复盲扫寄存器制造看似进展的记录。

#### 9.5.1 第 5 轮：修正完成标志后仍未发现 PHY（2026-10-12 main）

前四轮把「完成标志」读错了寄存器，第 5 轮已纠正并重测：

- **纠正**：Cadence/Zynq GEM 的 MDIO 完成标志是 **`NETWORK_STATUS[2]`**（Xilinx 驱动里 `XEMACPS_NWSR_MDIOIDLE_MASK = 0x4`），**不是** `PHY_MAINT` 里的某一位。前四轮轮询 `PHY_MAINT` 的 bit2 属读错寄存器；`NETWORK_STATUS` 一直读到 `0x6`，即 bit2=1（idle）本来就成立。
- **另外补上**：`NETWORK_CONTROL[3] = Management Port Enable`，前四轮也未置位。
- **修正后重测**（MPE=1、MDC 分频=8、按 `NETWORK_STATUS[2]` 判完成、扫 PHY 0..31 的 reg2/3）：**`MDIO_PHYS_FOUND=0`**，全部返回 0xFFFF/0x0000。
- 旁证：`GEM0` 的模块 ID 寄存器 `0xE000B0FC = 0x00020118`（Cadence GEM 存在）；`NETWORK_CONTROL` 写入能读回（寄存器块可写，未被复位挡住）；`PHY_MAINT` 写入也能读回（如 `0x6F8E0000`，SOF/OP/PHY/REG 字段编码正确）。
- 注意 `0xE000B0F8` 被 XSDB 标为 **"Blocked address ... Access can hang PS interconnect"**，读取它会报错——这不是板卡故障，是 XSDB 对 Zynq 保留地址的保护。

**结论不变但更强**：GEM0 控制器本身存在、可写、完成标志正常，**但对端 PHY 完全不回应**。已排除「完成标志读错」「管理端口未开」「GEM0 被 APER 复位挡住」。剩下的可能集中在**物理层**：MDIO/MDC 是否真在 MIO52/53、PHY 是否被某个未驱动脚保持复位、或板卡其实用 GEM1。**这些都要原理图或实测仪器，不能靠寄存器回读继续推进。**

### 9.6 ENET0/PHY 结论更正：**通过**（2026-10-12 main）

§9.2 与 §9.5 里"ENET0 未通过"的结论**作废**。失败原因是 **main 自己的两个寄存器错误**，不是板卡问题：

| # | 我写错的 | 正确的是 | 依据 |
|---|---|---|---|
| 1 | 轮询 `PHY_MAINT` 的某一位当完成标志 | 完成标志是 **`NETWORK_STATUS[2]`**（`XEMACPS_NWSR_MDIOIDLE_MASK = 0x4`） | Xilinx `xemacps_hw.h` |
| 2 | `NETWORK_CONTROL` 写 `0x8`（那是 TXEN） | **MDEN = bit 4 = `0x10`**（`XEMACPS_NWCTRL_MDEN_MASK`） | 同上 |

改对之后 PHY 立刻应答。完整只读证据（`logs/bringup/20261012T120117Z-bkb220-f3-v1/phy_dump.out`）：

| 寄存器 | 值 | 含义 |
|---|---|---|
| reg2/reg3 PHYID | `0x001C` / `0xC915` | OUI `0x001CC9` = **Realtek**，model `0x11` rev 5 → **RTL8211E** |
| reg0 BMCR | `0x1140` | 自协商使能 + 1000 Mbps |
| reg1 BMSR | `0x7969` | **bit2 = 1 → link up** |
| reg5 ANLPAR | `0xCDE1` | 对端能力，协商完成 |
| reg6 ANER | `0x000F` | 无自协商错误 |
| reg9 1000BASE-T CTRL | `0x0200` | 手动主/从配置位 |
| reg10 1000BASE-T STS | `0x78FF` | **bit11 = 1 → 1000BASE-T 全双工** |

**因此可以对外说**：BKB220 的 PS ENET0 按 **RGMII on MIO16-27 + MDIO on MIO52-53** 配置**在真板上被证实可用**——MDIO 能读写、PHY 是 Realtek RTL8211E、自协商完成、**1000BASE-T 全双工 link up**，与主机 ASIX 网卡报的 1 Gbps 互相印证。profile 里那组 ENET0 属性**从"候选"升级为"已实测"**。

**教训（值得写下来）**：前四轮的"MDIO 无应答"看起来像硬件/原理图问题，实际是**读错寄存器 + 写错使能位**。寄存器级探测的第一件事应该是**对着厂商驱动的头文件核对位定义**，而不是凭对同名外设（这里是 Cadence GEM）的印象推断；否则会把两个自己制造的 bug 误判成板卡缺陷，并据此把"需要原理图"写成结论。

**仍未完成**（与本项无关）：CAPS 需要能跑 lwIP 的固件，属 F4；QSPI/SD 冷启动、UART 反方向仍未测。

## 10. 原理图核对（2026-10-12，用户提供 `BK_B220_SchDoc.pdf`）

用户提供 Altium 导出的原理图（23 页 A4 横版），已按原字节入库为 [BK_B220_SchDoc.pdf](BK_B220_SchDoc.pdf)，SHA-256 `fb7947dfa762a58d7e6a178fc612d8ec48a1d05c677e60c357acc0697e8955a6`，已记入 `SHA256SUMS.txt` 并 `sha256sum -c` 通过。**这份资料关闭了此前"无原理图"的缺项。**

页结构：p1/p2/p14 = `DDR_unit`；p13 = `zynq_7000_ddr` + `zynq_7000_ps`（连接器侧）；**p15 = `PHY`**；**p16 = `ZYNQ_PL`**；**p17 = `ZYNQ_PS`**；p18/p19 = 电源/PMIC；p20 = 根图。

| 事实 | 出处 | 与既有结论的关系 |
|---|---|---|
| **PS_CLK = 33.333 MHz 晶振（X2）**，网络 `PS_CLK_500` 接 Zynq `E7` | p17、p23 | **确认**了 main 此前从 `IO_PLL_CTRL` FBDIV 推出的 33.333 MHz |
| **UART0 = MIO14(TXD→PS) / MIO15(RXD←PS)**，经 `ZYNQ_UART0` 引出 | p13（`ZYNQ_UART0` 簇内 `B0MIO14`→`UART_TXD_PS`、`B0MIO15`→`UART_RXD_PS`） | **确认**了实测的 UART0/MIO14-15 |
| 主机侧串口：**`UARTC_TXD/RXD` = PS UART**，`UARTD_TXD/RXD` = PL UART | p6（FT4232 引脚 38 等）、p11 | **确认**了实测的"PS UART 在 FT4232 **通道 C**"；通道 D 是 PL UART |
| FT4232 **通道 A = JTAG**（`FT4232_TCK/TDI/TDO/TMS`），另有 `FT4232_JTAG_ON` 与 `FT4232_JTAG_RST`；JTAG 经电平转换 IC1 出 `FPGA_TCK/TMS/TDI/TDO` | p6 | 与实测链名 `Xilinx HW-Z1-ZCU104 FT4232H 15051A` 一致 |
| **ENET0 为 RGMII**（`ETH_TCLK/TXD0..3/TCTL/RCLK/RXD0..3/RCTL` 共 12 根） | p13、p15 | **确认** RGMII 而非 MII；否则 RGMII 时序参数与 RXDLY/TXDLY 都不成立 |
| **PHY = `RTL8211E-VL`（U19，QFN40）** | p15、p23 | **确认**了 main 从 MDIO 读出的 PHYID `0x001C/0xC915`（Realtek RTL8211E） |
| **PHY Address = 1**（strap），带 `RXDLY`/`TXDLY` 子，RGMII 1.8V 上拉 | p15 | **新信息**：lwIP/驱动应使用 **PHY 地址 1**。main 的 MDIO 扫描在地址 0 和 1 都读到同一 ID，以原理图的 1 为准 |
| **PHY 复位 `PHYRSTB`（U19 脚 29）接 `PS_POR_B`**，不是 GPIO | p15 | **新信息且重要**：固件**不需要**驱动任何 PHY 复位脚；PHY 随 PS_POR_B 释放。这也解释了只跑 `ps7_init` 时 PHY 已是活的 |
| DDR = 两片 `MT41K256M16TW-107`（`U18_ZYNQ_7000_DDR_UA` 等） | p1/p2/p14 | 与手册 p.9-10 一致 |

**据此更新的判断**：§9.3 里"工业级料号未定""ENET0 候选"两项，ENET0 侧已被原理图补齐（RGMII + RTL8211E + PHY 地址 1 + 复位由 PS_POR_B 驱动）；**仍未定**的只剩工业级精确料号、DDR 板级延迟与 DQS-to-CLK、QSPI/SD 冷启动。

**边界**：原理图证明的是**设计意图与连接关系**，不等于板子实物与该版图一致（PCB 修订/改板未核对）；也不等于整机 G3 通过。

## 11. F4 首次整机 G3：烧录成功、以 FAIL 结束，根因已定位（2026-10-12）

### 11.1 做得对的部分（都是 PASS）

- **烧录走 Windows 2026.1**（用户指定的分工）：`usbipd` 把 FT4232H 还给 Windows，用 `D:\xilinx\2026.1\Vitis\bin\xsdb.bat` 下载 22 产出的制品。
- 制品选择：`--strict-artifacts`、`--artifact-dir <P4软件包>`、`--device xc7z020`，`g3_artifacts.py` 预检 exit 0（`board_id=bkb220`、`part=xc7z020clg400-2`、几何 150/50/807/957/64、`P_WAYS=4/PIPE_TREE=0`、`legacy=false`）。
- **板上启动链全通**：`rst -system` → `fpga`（PL 编程）→ `ps7_init`+`post_config` → `dow`（ELF）→ `con`。串口（COM10）实录到完整应用启动：
  `DNA Accelerator Complete Pipeline`、Voter/Decoder 复位 IDLE=1、DMA `MM2S/S2MM` 描述符与无错误、`[INIT] DNA Accelerator ready`、
  `Board IP: 192.168.1.10`、`[TCP] Server ready`、`*** Waiting for connections ***`。
- 留证目录：`D:\bkb220_board_smoke\g3_runs\20261012T132657Z\`（`uart.log`、`artifact_selection.json`、`wait_ready.out` 等）。

### 11.2 FAIL 的直接判据

```
PASS  完整制品包一致性
PASS  烧录
FAIL  板端应用层就绪（CAPS）  — 90 s 内 192.168.1.10:7 没有正常应答
SKIP  四级逐级取证  — 任务未跑到出结果
FAIL  串口实录  — 采集器报"没有可确认的输出"（实际 uart.log 有 1757 B 内容，见 §11.4）
######## G3 FAIL ########
```
主机侧独立佐证：`ping 192.168.1.10` 100% 丢包；TCP 7 报 `No route to host`（连 ARP 都不通）。

### 11.3 根因：PHY 自协商在驱动侧超时，GEM 从未被启用

串口实录**开头**就有决定性三行：

```
Start PHY autonegotiation
Waiting for PHY to complete autonegotiation.
Auto negotiation error
Phy setup error
Phy setup failure init_emacps
```

定位到 BSP 的 `xemacpsif_physpeed.c` → `get_Realtek_phy_speed()` 里的等待循环：

```c
while ( !(status & IEEE_STAT_AUTONEGOTIATE_COMPLETE) ) {   /* BMSR bit5 */
    sleep(1); timeout_counter++;
    if (timeout_counter == 30) { xil_printf("Auto negotiation error \r\n"); return XST_FAILURE; }
    XEmacPs_PhyRead(xemacpsp, phy_addr, IEEE_STATUS_REG_OFFSET, &status);
}
```

30 秒内 BMSR bit5 一直没置位 → `XST_FAILURE` → `phy_setup_emacps` 失败 → **GEM0 从未被启用** → 应用能起 lwIP 与 TCP server 但链路层不通。这也解释了紧随其后的 `Ethernet Link down`（应用每秒调 `eth_link_detect`，用的是从未建立起来的 `phyaddrforemac`）。

**为什么是这颗 PHY 出问题**：新旧 BSP 的 `lwipopts.h` **逐行相同**（都是 `CONFIG_LINKSPEED_AUTODETECT 1`），`xemacpsif_physpeed.c` 也是同一份 BSP 源码；**旧板 10 份 UART 实录取样全都打出 `autonegotiation complete`，新板超时**。差别只在 PHY：新板 `PHYID1=0x001C` → 走 **`get_Realtek_phy_speed()`** 分支；旧板不是 Realtek，走别的分支。**所以这是 Realtek 分支与这颗 RTL8211E 的适配问题，不是板子或连线问题。**

**一条必须并存的观察（防止归因错）**：main 从前端经 JTAG 读同一颗 PHY 时，`BMSR=0x796D`（**bit5=1 自协商完成**）、`ANLPAR=0xCDE1`、`GBTSTS=0x7800`（1000BASE-T 全双工）。**PHY 自己能协商成功**，是**驱动的时序/写法**在这颗 PHY 上拿不到结果。金线与 PHY 都是好的（Windows ASIX 网卡也一直显示 1 Gbps link up）。

### 11.4 一个次要的判据缺陷（需修）

G3 把"串口实录"判成 FAIL，理由是采集器报"没有可确认的输出（count=未报告）"，**但 `uart.log` 实际有 1757 字节完整启动日志**。也就是说这一格的裁决逻辑与实际内容不符——它可能只认某几个特定标记，或 count 没回传。**这是判据侧的 bug，不是板子的问题**，但它会把"串口其实录到了"误报成失败，应当修掉后再跑（否则每次都会多一个假 FAIL）。

### 11.5 下一步（不在此轮下结论）

修 PHY 初始化，候选方向（**都要以能变红的判据验证，不许猜着改**）：
1. **换用固定速率路径**：把 BSP 的 `CONFIG_LINKSPEED_AUTODETECT` 换成 `CONFIG_LINKSPEED1000`，走 `configure_IEEE_phy_speed()` —— 那条路径会写 **page2/reg0x15 的 RGMII 收发时钟延迟**（`IEEE_RGMII_TXRX_CLOCK_DELAYED_MASK`），正是原理图 p.15「RGMII clock timing control / RXDLY」提示的东西，而 AUTODETECT 路径**不碰**这些寄存器。
2. **确认驱动实际用的 PHY 地址**：`detect_phy` 填 `phymapemac0[]` 后由 `phy_setup_emacps` 取用；main 的前端扫描在地址 0 和 1 都读到同一 ID，而驱动的取用循环是 `for (i=31; i>0; i--)`。要用板上实测（而非推断）确认驱动最终用的是哪个地址。
3. **RTL8211E 特有的初始化**：若 1/2 都无效，再考虑在 `sw/app` 或 BSP 层加 Realtek 专页配置。

**边界**：本轮**没有**改动 `sw/app` 或 BSP 源码；以上是定位与候选方向，不是已完成的修复。

## 12. F4 板测失败的真根因：profile 从未包含 ENET0 的 MIO 配置（2026-10-12 结案）

§11 把失败定位到 `get_Realtek_phy_speed()` 自协商超时，**方向对但根因不对**。真根因是**配置缺失**，而且**是我这边的**：

### 12.1 证据链

| # | 观测 | 结论 |
|---|---|---|
| 1 | 带时间戳启动：`Waiting for PHY to complete autonegotiation.` → **28.55 秒后**才 `Auto negotiation error` | 驱动**真的睡满 30 次**，`sleep(1)` 正常（BSP 的 `COUNTS_PER_SECOND=333333343`，实测全局定时器 ~333 MHz，对得上）。**"sleep 坏了"的假设被推翻** |
| 2 | 用 JTAG **原样重放**驱动的寄存器序列（写 ANAR/GBCR/BMCR → 写 BMCR 软复位 0x8000 → 等 bit5） | 复位位 1 次轮询自清，ANAR/GBCR **没被擦掉**，**BMSR bit5 在 t=3s 置位**。**寄存器序列本身没问题，软复位也不是元凶** |
| 3 | 应用跑完后读驱动决策变量（ELF 符号表地址）：`phyaddrforemac = 0`、**`phymapemac0[]` 全 0** | **`detect_phy()` 一个 PHY 都没扫到** → 走 `phy_setup_emacps(..., 0)` 兜底 → 后面的自协商与链路轮询全在错的 PHY 地址上 |
| 4 | 读 GEM 留下的 MIO：**`MIO_PIN_52 = 0x1201`、`MIO_PIN_53 = 0x1201`** | 正确值是 **`0x1280`**（L3_SEL=4 = GEM MDIO）。**MDIO 引脚根本没 mux 出来**，所以驱动在 MDIO 线上什么都读不到 |
| 5 | 对比两份 `ps7_init`：**P4 包的 MIO16-27 / MIO52-53 写入 = 0 行**；v1 探针的 = 各 6 行（`0x1280`） | **P4 整机的 PS7 完全没配 ENET0 的 MIO** |
| 6 | `git log`：`hw/boards/bkb220.tcl` 里 `PCW_ENET0` **历次提交都只有 1 行**（只有 `ENET0_PERIPHERAL_ENABLE`） | **那 4 行 `ENET0_ENET0_IO`/`GRP_MDIO_ENABLE`/`GRP_MDIO_IO`/`PERIPHERAL_FREQMHZ` 从来没进过 profile**，只活在 board-migrate 的一次性探针变体里 |

### 12.2 因果链

`hw/boards/bkb220.tcl` 缺 4 行 ENET0 属性 → `bd.tcl` 把它们整体 `set_property` 给 PS7 时**没有这些配置** → P4 XSA 的 `ps7_init.tcl` **不写 MIO16-27/MIO52-53** → 板上 MDIO 引脚未 mux → 驱动的 `detect_phy` 扫不到 PHY → 自协商必然超时 → `phy_setup_emacps` 失败 → GEM 从未启用 → 应用起得来但网络不通 → **G3 CAPS FAIL**。

### 12.3 必须更正 §9.6 的说法

§9.6 写「ENET0 从候选升级为已实测」——**这个说法要限定**：那些 MDIO/PHY 读数是在 **v1 探针的 `ps7_init`**（含 ENET0 配置）下得到的，**而真正构建进 P4 的 profile 里压根没有这些配置**。所以它证明的是"**这组属性在这块板子上可用**"，**没有**证明"**构建出来的东西带着这组属性**"——这正是一个我会犯的经典错误：拿探针/仿真的结论去替代制品的结论。

（同类教训 09 台账里已经写过一条：**仿真喂黄金数据不等于真实接口正确**。这次是**探针配置对不等于制品配置对**。）

### 12.4 已做的修复与仍待做的

- **已修**：`hw/boards/bkb220.tcl` 补回那 4 行（写法取自 v1 探针 `property-results.tsv` 里 `ACCEPTED_EXACT` 的原文），profile 现 35 对属性、无重复。ENET0 由 `PCW_ENET0_PERIPHERAL_ENABLE` 单行变为完整的 RGMII MIO16-27 + MDIO MIO52-53 + 1000 Mbps。
- **仍待做**：**重建 P4 的 XSA 与同源软件包**（PS7 配置变了 → `ps7_init` 与 XSA 都要重出；PL 网表本身没变，但要走一遍正规流程），然后重跑 F4 G3。
- **判据**：新包 `ps7_init.tcl` 里必须出现 `0xF80007D0/0xF80007D4 = 0x1280`；板端 uart.log 必须出现 `autonegotiation complete`（且**不应**再出现 `Auto negotiation error`）。

### 12.5 本轮我在 PHY 这条线上犯的三个错（都记下来）

1. MDIO 读错完成标志（应读 `NETWORK_STATUS[2]`）+ 漏写 `MDEN`（`NETWORK_CONTROL` bit4）→ 误判「ENET0 未通过」，差点写成"需要原理图"。
2. 给 board-migrate 的阶段卡里写死了 Vitis 2022.2 并不存在的 `lwip220` → 造成一次假阻塞。
3. **本次**：把探针配置下的实测结论当成制品已验证，而 profile 里根本没有那几行配置 —— 直接导致 P4 建出来后以太网必然不通。

三次都是"结论比证据跑得快"。共同解药是同一件事：**先量、再下结论；并且要量「真正被构建/被烧录的那一份」，不是旁边那份更好看的。**

## 13. F4 整机 G3 在 BKB220 上通过（2026-10-12）

补回 ENET0 MIO 配置、重建 P4 硬软包后，**F4 的整机 G3 在新板上全绿**：

```
结果     步骤
PASS    完整制品包一致性（所选SHA/XSA内bit/part/参数）
PASS    烧录
PASS    板端应用层就绪（CAPS）        — READY 9.0 2
PASS    第 1 轮 first.py             — 4096 条记录 / score_min=67
PASS    第 1 轮 唯一判据（图片 SHA-256）— fcd0cf90bd680e7bbdc203e3398119504da0897acac9e2117008b4efb6b1f2c3
PASS    四级逐级取证（board_stage_check.py）
PASS    串口收到板端输出              — 7781 个字符
######## G3 PASS ########
```

- 制品包：`hw/build/bkb220-p4-enet0-software-20261012T140800Z-board-migrate/`（P4 4/0、SE150 150/50/807/957/64、`part=xc7z020clg400-2`、`legacy=false`、`SHA256SUMS` 59 项全 OK）
- 留证：`D:\bkb220_board_smoke\g3_runs\20261012T142924Z\`（含 `uart.log`，其中可见 **`autonegotiation complete`** —— §11/§12 那条链的修复判据达成）
- 通道：**Windows 2026.1 XSDB 烧录 22 产出的制品**（`D:/xilinx/2026.1/Vitis/bin/xsdb.bat`，`--device xc7z020`，CH340 无、用 **COM10** 抓 PS UART），符合 [07 §3a](07-board-build-and-acceptance.md) 的工具链分工。

**可以对外说**：BKB220（xc7z020）上，P4/SE150/100MHz 的同源硬软包完成真实下载与端到端任务，板端回传经 LDPC 后重建的 JPEG SHA-256 与判据 `fcd0cf90…f2c3` **逐位相同**，四级 DDR 逐级取证通过。

**边界**：这是 **2048 源读段**的 smoke 档（4096 板端记录），等价于旧板 G3 默认档；**全量三轮、连续/脏干净、断连恢复、性能矩阵、泛化/长稳都还没做**（F6～F8）。也**不等于** P16 已上板 —— 板上跑的是 P4。

### 13.1 顺带修掉一个判据侧 bug（CRLF）

首轮 G3 除"串口实录"外全 PASS，那一步误报 FAIL：采集器实际报了 `CAPTURE_DONE chars=7781`，但 `run_g3.sh` 用
`^CAPTURE_DONE (bytes|chars)=[1-9][0-9]*$` 判读，而 `uart_cap.out` **由 Windows 侧脚本写、行尾是 CRLF**，
`$` 锚点被 `\r` 顶掉 → 明明收到了 7781 个字符却判成"没有可确认的输出"。

修法：对该文件的所有读取先 `tr -d '\r'` 归一化（`run_g3.sh` 内已加注释说明原因）。
**这条会稳定地把 PASS 报成 FAIL**——不是板子的问题，但它会污染每一次验收结论，所以必须修。

## 14. F6 板端深化：全量三轮 / 连续与状态复位 / 故障恢复（2026-10-12 起）

用 §13 那个已通过的 P4 包（`hw/build/bkb220-p4-enet0-software-20261012T140800Z-board-migrate/`），通道 Windows 2026.1 XSDB + COM10。

### 14.1 A1 全量三轮 —— **PASS**

```
PASS  第 1/2/3 轮 first.py  — 103616 条记录 / 26.51 s 每轮
PASS  第 1/2/3 轮 唯一判据（图片 SHA-256）— fcd0cf90…f2c3
PASS  多轮一致性（3 个判据轮同一张图片）
PASS  连续运行无退化（逐轮耗时：33 32 33）
PASS  四级逐级取证    PASS  串口收到板端输出 — 25797 字符
```
留证 `D:\bkb220_board_smoke\g3_runs\20261012T144029Z\`。
**103,616 板端记录**与文档记载的 SE150 全量值吻合（51,781 源读段 × 正反向 + 64 补帧）。全量 26.51 s/轮，与旧板 P4 的 25.69 s 中位数基本持平。**这是当时 P4 与旧板的全量耗时比较**；不能据此归因当前 P16 处理段的系统瓶颈，后续 P16 分解推导中 PL 约占 87.8%（见时间预算记录）。

### 14.2 A2 连续 + 状态复位 —— **PASS，且鉴别力自证通过**

```
PASS  第 1 轮 弄脏轮已执行          — score_min=0，103616 条记录
PASS  ★ 第 1→2 轮 弄脏轮鉴别力自证   — 两轮回传相差 1500/64800 bit
PASS  第 2 轮 唯一判据（2048 条）    — fcd0cf90…f2c3
PASS  第 3 轮 唯一判据（全量）       — fcd0cf90…f2c3
PASS  多轮一致性 / 连续无退化（33 2 33）
```
留证 `…/20261012T144314Z/`。

**为什么"鉴别力自证"这一行才是关键**：若两轮原始回传完全相同，"哈希相同"证明不了累加器被复位（两轮同参数时票更新单调、符号判决必然不变——本项目已推导过这一点）。实测两轮**相差 1500/64800 bit**，说明弄脏轮确实写进了不同向的票，**因此干净轮通过才算数**。

**顺带一个正面证据**：构建报告里的 **`REQP-1839/1840`**（BRAM 异步复位控制、提示"复位期间可能影响存储内容且默认 STA 不分析"）在本次状态复位测试中**没有发作**。这不等于该风险不存在，但该场景实测未触发。

### 14.3 A3-1 配置/容量守卫故障注入 —— **7/7 PASS**

```
✓ capacity_ok_boundary          期望接受 / 实测接受 —— 恰好等于容量上限，守卫没有过度拒绝
✓ capacity_exceed_by_one_frame  期望拒绝 / 实测拒绝  rc=5 total_reads 非法
✓ capacity_exceed_large         期望拒绝 / 实测拒绝  rc=5
✓ not_frame_aligned             期望拒绝 / 实测拒绝  rc=5（非 64 整数倍，C2）
✓ zero_reads                    期望拒绝 / 实测拒绝  rc=5
✓ wrong_read_bps                期望拒绝 / 实测拒绝  rc=2（read_bps=250 与 150bp 比特流不符）
```
每次注入后板端**存活**。留证 `logs/g3/a3-faults/config-guard/config_guard.jsonl`。
**注意**：拒绝理由码取自 `PKT_CONFIG_OK` 载荷里的 u32 —— **0 才是接受**，光看"收到应答"会把拒绝当接受（本项目初版探针踩过）。

### 14.4 A3-2 断连/畸变包恢复探针 —— **30/30 全部恢复**

```
共 30 个用例，未恢复 0 个
```
覆盖的注入（每个都独立验证"注入后板子还能不能完成一次完整 CAPS 握手"，每轮注入前有 `baseline_caps` 对照）：

| 注入 | 结果 |
|---|---|
| `half_header`（半截包头） | OK，恢复 2.0 s / 1 次尝试 |
| `bad_magic` | OK，2.0 s |
| `unknown_pkt_type` | OK，板端回 `ee`（明确拒绝） |
| `oversized_length` | OK，回 `ee` |
| `truncated_payload` | OK，2.0 s |
| `reset_mid_caps`（CAPS 中途 RST） | OK，2.0 s |
| `idle_then_close`（连上不发就走） | OK，2.0 s |
| `second_connection`（第二条连接） | OK |
| `flood_bad_headers`（坏头洪水） | OK |
| 三轮 `c1/c2/c3` 重复 | 全部 OK |
```
留证 logs/g3/a3-faults/recovery.jsonl
```
**为什么这条对长稳重要**：板端 lwIP 的 `g_conn` 是**单例**，一旦异常连接没被正确回收，后面所有任务都连不上 —— 而这在正常回归里一次也测不到（`run_g3.sh` 只走正常会话）。

### 14.5 A3-3 任务中途断网 + 上位机被 SIGKILL —— **3/3 恢复**

```
[OK] idle_outage                    恢复 2.0 s / 1 次尝试
[OK] mid_task_outage_kill           恢复 2.0 s / 1 次尝试
[OK] mid_task_outage_kill_repeat    恢复 2.0 s / 1 次尝试
iptables 规则已清理干净。共 3 个用例，未恢复 0 个
```
这是**最难的那一种**：任务传输中途双向黑洞掉流量，板端**连 FIN 都收不到**；而且上位机是被 `kill -9` 的（不是优雅断开）。板端仍能在 2 秒内回到可服务状态。留证 `logs/g3/a3-faults/netfault.jsonl`。

**安全性**：探针只在 `finally` 里临时插入针对板卡 IP 的 DROP 规则并删除；本轮结束后 main 复核 `iptables -L` **INPUT/OUTPUT 里针对 192.168.1.10 的残留规则数均为 0**。

### 14.6 A（P4 板端深化）小结

| 项 | 结果 |
|---|---|
| A1 全量三轮 | **PASS**（三轮同哈希、连续无退化、四级 DDR 取证） |
| A2 连续 + 状态复位 | **PASS**，弄脏轮鉴别力自证（相差 1500/64800 bit） |
| A3-1 配置/容量守卫 | **7/7 PASS** |
| A3-2 断连/畸变包恢复 | **30/30 恢复** |
| A3-3 任务中途断网 + SIGKILL | **3/3 恢复** |

**边界**：以上都是 **P4**。P16 的同等门禁要在 B（重建 P16 包 → 上板）之后另跑，不能用 P4 的结论代替。

## 15. B2 P16 首次上板（2026-10-12）

### 15.1 重建后的 P16 包（B1）

| | |
|---|---|
| 硬件包 | `hw/build/bkb220-p16-enet0-100mhz-20261012T144141Z-board-migrate/` |
| 软件包 | `hw/build/bkb220-p16-enet0-software-20261012T144141Z-board-migrate/` |
| 时序（main 读原始报告） | WNS **+0.617** / TNS 0 / WHS **+0.017** / THS 0；失败端点 **0/86,415**；`clk_fpga_0`=100.000 MHz；DRC 0 errors |
| 资源 | LUT **33,987/53,200（63.89%）**、FF 36,067、BRAM 45/140、DSP 3/220 |
| **ENET0 自查（main 亲自 grep）** | `ps7_init.tcl` **`F80007D0/D4 = 0x1280`** ✓，MIO16-27 RGMII 行齐 ✓ |
| **P16 身份核对** | `g3_artifacts.py` 读出 **`C_STAGE1_P_WAYS=16 / C_STAGE1_PIPE_TREE=1`** ✓（P4 为 4/0）——这是 TCP/CAPS 层**分不出来**、只能从 manifest/XSA 认的字段 |
| 与修复前 P16 对照 | WNS/WHS/失败端点/LUT/DRC 全部一致（合理：ENET0 修复只动 PS7 配置，PL 网表未变） |

### 15.2 P16 smoke（2048 源读段）—— **PASS**

```
PASS  完整制品包一致性 / 烧录 / CAPS READY 6.1 1
PASS  第 1 轮 first.py  — 4096 条记录 / score_min=67；Result: 8100 bytes, 0.75s
PASS  第 1 轮 唯一判据（图片 SHA-256）— fcd0cf90…f2c3
PASS  四级逐级取证    PASS  串口收到板端输出 — 7780 字符
```
留证 `D:\bkb220_board_smoke\g3_runs\20261012T150336Z\`。

**★ 同板 P4/P16 首个端到端对照**（同 smoke 档、同输入、同判据）：

| | `t_result`（POST→收齐 8100B） | 轮耗时 |
|---|---|---|
| P4 | 1.45 s | 2 s |
| **P16** | **0.75 s** | **1 s** |

即 **P16 在该档快约 1.9 倍**。**口径注意**：`t_result` **不含**上传与 LDPC，也不是整轮；正式性能矩阵（六档 ≥3 次、中位数/离散/斜率）见 F7，**不要拿这一个点外推整机倍率**。

### 15.3 P16 全量三轮 —— **PASS，且首次量出全量档的 P4/P16 倍率**

```
PASS  第 1/2/3 轮 first.py  — 103616 条记录 / score_min=67
PASS  第 1/2/3 轮 唯一判据（图片 SHA-256）— fcd0cf90…f2c3
PASS  多轮一致性（3 个判据轮同一张图片）
PASS  连续运行无退化（逐轮耗时：12 15 13）
PASS  四级逐级取证    PASS  串口收到板端输出 — 25774 字符
```
留证 `D:\bkb220_board_smoke\g3_runs\20261012T150552Z\`。

**同板全量档 P4/P16 对照**（同输入、同判据）：

| | `t_result`（POST→收齐 8100B） | 轮耗时 |
|---|---|---|
| P4 | 26.51 s（三轮一致） | 33 s |
| **P16** | **8.61 / 8.71 / 8.61 s** | **12 / 15 / 13 s** |

→ 全量档 **约 3.05 倍**，接近模块周期的 3.27 倍（全量把 PS 侧固定开销摊薄，所以比 smoke 档的 1.9 倍更接近模块倍率）。
**另外**：`docs/08` 里"估算的 P16 全量约 8.6 s"这个**估算值与实测 8.61 s 几乎一致**——这是估算第一次被实测校准。

**口径仍要守住**：`t_result` 不含上传与 LDPC、不是整轮；正式性能矩阵（六档 ≥3 次、中位数/离散/斜率/截距）见 F7。

### 15.4 P16 连续 + 状态复位 —— **PASS，鉴别力自证通过**

```
PASS  第 1 轮 弄脏轮已执行（score_min=0，全量 103616 条）
PASS  ★ 第 1→2 轮 弄脏轮鉴别力自证 — 两轮回传相差 1500/64800 bit
PASS  第 2 轮 唯一判据（2048）/ 第 3 轮 唯一判据（全量）— fcd0cf90…f2c3
PASS  多轮一致性 / 连续无退化（14 2 15）
PASS  四级逐级取证    PASS  串口 25852 字符
```
留证 `D:\bkb220_board_smoke\g3_runs\20261012T150740Z\`。与 P4 的 A2 结果同形（同一 1500/64800 bit 鉴别力签名）。

## 16. C2 泛化首测：板子成功恢复用户提供的新载荷（2026-10-12）

用户提供外部数据包 `E:\桌面\scientific-image-datasets-20261012`（4 张 USC-SIPI 标准测试图 × D1 干净 / D2 加 1% 替换噪声 = 8 套）。

### 16.1 为什么能直接跑（无需重建比特流）

| 检查 | 结果 |
|---|---|
| 几何 | 每套 `reference_sequence.txt` = **40,500 符号**，与板端 `NUM_LC*STRIDE + READ_BPS = 50×807+150` **完全一致** |
| 契约 | SE150 / 150 bp / 81,000-bit 水印 / 4b→5b 稀疏码 / DVB-S2 R=5/6 / 8100 B 结果 —— 与本项目同契约 |
| **水印是否可换** | **可以，且不用重综合**：水印是**每任务上传**的（`echo.c` 的 `PKT_WM` → `stage1_dna.c` 的 preload 逐区域 DMA 进 Stage1 BRAM），`run_g3.sh` 提供 `--reads`/`--watermark`/`--expect-sha`/`--score-min` 覆盖 |
| 水印内容 | 数据包的 `common/watermark.txt` 与 R0.83 水印**逐位相同**（剥掉行尾差异后整串一致）——即**复用同一水印，只有载荷不同** |

### 16.2 实跑结果：**成功**

```
PASS  完整制品包一致性 / 烧录 / CAPS READY 6.1 1
PASS  第 1 轮 first.py  — 4096 条记录 / score_min=65
PASS  ★ 唯一判据（图片 SHA-256）— e0e65925814e07374dd4188939dd13e9d647cd2ecfb3480b050fe4775119242b
FAIL  四级逐级取证（board_stage_check.py）
PASS  串口收到板端输出 — 7780 字符
```
用 P4 包 + `--reads D1_image_peppers/reads_se150.fastq --watermark <包>/datasets/common/watermark.txt --expect-sha e0e65925… --score-min 65`。
**板端回传经 LDPC 重建的 JPEG，SHA 与数据包 manifest 里的 payload SHA 逐字符相同** —— 即板子独立恢复出了这张图。
留证 `D:\bkb220_board_smoke\g3_runs\20261012T153017Z\`。

### 16.3 那个 FAIL 是**判据不适用**，不是失败（已核实）

`board_stage_check.py` 的四级取证**写死了 `tests/golden/` 里的 R0.83 黄金向量**（脚本内 `GOLDEN = tests/golden`），而本次载荷是 peppers：
- **展开水印 vs `wm_regions.hex`：PASS（47850/47850）** —— 因为水印本就复用 R0.83 的，所以这一级对得上 ✓
- **Stage2 ⊕ 水印 vs `sparse_expect.hex`：FAIL 41.64%**、**Stage3 vs `stage3_expect.hex`：FAIL 49.53%** —— 这两份黄金是 **R0.83 载荷专用**的，拿来比一张**新图**当然对不上（≈随机水平）

**判定依据**：端到端图片 SHA 是权威判据，它**精确通过**；若 Stage2 真坏，R=5/6 的 LDPC 不可能从 8100 B 精确还原该图。故四级 FAIL 属**判据范围**问题。

**改进项（记入 C2）**：要让四级取证也覆盖新数据集，需**为每个载荷生成对应的 `stage2_in/sparse_expect/stage3_expect` 黄金向量**；`tests/golden` 目前只有 R0.83 一套。**在此之前，对新载荷只能采信端到端判据。**

**边界**：本次只跑了 **1 套**（D1_peppers，干净、`score_min=65`）。数据包自报的软件侧结果是在 **65 下 8/8、67 下 4/8**，**板端尚未逐套复核**；D2 噪声集、其余 3 张图、以及 67 阈值下的表现都未测。

### 16.4 八套全跑：**8/8 全部恢复**（2026-10-12 深夜）

在 §16.2 的 1 套基础上，把用户数据包**全部 8 套**依次在板上跑完（每套完整启动：`rst -system` → 编程 PL → `ps7_init` → `down ELF` → 任务），参数 `--score-min 65 --limit 4096`，用 P4 包。

| 数据集 | 期望 payload SHA（前16） | 板端判据 SHA（前16） | 一致？ | 各步 |
|---|---|---|---|---|
| D1_image_jellybeans | `650fc2224140741f` | `650fc2224140741f` | **✓** | PASS 6 / FAIL 1 |
| D1_image_mandrill | `2e3c7b450b57f8d2` | `2e3c7b450b57f8d2` | **✓** | PASS 6 / FAIL 1 |
| D1_image_peppers | `e0e65925814e0737` | `e0e65925814e0737` | **✓** | PASS 6 / FAIL 1 |
| D1_image_tree | `69af770eea71b098` | `69af770eea71b098` | **✓** | PASS 6 / FAIL 1 |
| D2_image_jellybeans_sub1pct | `650fc2224140741f` | `650fc2224140741f` | **✓** | PASS 6 / FAIL 1 |
| D2_image_mandrill_sub1pct | `2e3c7b450b57f8d2` | `2e3c7b450b57f8d2` | **✓** | PASS 6 / FAIL 1 |
| D2_image_peppers_sub1pct | `e0e65925814e0737` | `e0e65925814e0737` | **✓** | PASS 6 / FAIL 1 |
| D2_image_tree_sub1pct | `69af770eea71b098` | `69af770eea71b098` | **✓** | PASS 6 / FAIL 1 |

**四张图 ×（干净 / 加 1% 替换噪声），板端回传经 LDPC 重建的图片 SHA 全部与 manifest 的 payload SHA 逐字符相同。**
八套的步骤分布**完全一致**：`PASS=6 FAIL=1`，**唯一的 FAIL 都是「四级逐级取证」** —— 与 §16.3 的判定吻合（`board_stage_check.py` 写死 R0.83 黄金向量，对新载荷不适用）。留证 `logs/g3/c2-sweep/`（`SUMMARY.tsv` 与逐套 `.out`；`logs/` 不入库，文件保留）。

### 16.5 为拿到无歧义判定，另跑一轮 `--skip-dump`

上表的 `G3 FAIL` 会误导读者。所以另跑一轮 `--skip-dump`（把不适用四级取证降为 SKIP）以获得**无歧义的 PASS/FAIL**，留证 `logs/g3/c2-sweep/SUMMARY-skipdump.tsv`。
**注意**：`--skip-dump` **只跳过 DDR 取证，不改变判据本身**；端到端图片 SHA 仍是唯一权威判据，两轮都应给出同一结果。

**2026-10-13 重跑结果（板子接回后补跑，8/8 全部无歧义 PASS）**：

```
dataset                         verdict    judge_sha16        matches
D1_image_jellybeans             G3 PASS    650fc2224140741f   YES
D1_image_mandrill               G3 PASS    2e3c7b450b57f8d2   YES
D1_image_peppers                G3 PASS    e0e65925814e0737   YES
D1_image_tree                   G3 PASS    69af770eea71b098   YES
D2_image_jellybeans_sub1pct     G3 PASS    650fc2224140741f   YES
D2_image_mandrill_sub1pct       G3 PASS    2e3c7b450b57f8d2   YES
D2_image_peppers_sub1pct        G3 PASS    e0e65925814e0737   YES
D2_image_tree_sub1pct           G3 PASS    69af770eea71b098   YES
```
留证 `logs/g3/c2-sweep/SUMMARY-skipdump.tsv` 与逐套 `sd-*.out`。
**这一轮给出了与 §16.4 首轮完全一致的结论（同一批 SHA），但 verdict 是无歧义 PASS** —— 反证了 §16.7 那次失败纯属板子断电的环境问题。

### 16.6 结论与边界

**可以对外说**：在 BKB220（xc7z020）P4 包上，**用户提供的 4 张独立图像（含 1% 替换噪声版本）共 8 套 SE150 数据，全部经真实板端回传、LDPC 译码后重建成功**，图片 SHA 与数据包 manifest 逐字符一致。**无需重建比特流**（水印随任务上传，且该包复用 R0.83 水印）。

**边界**：
- 只测了 **`score_min=65`**；数据包自报软件侧在 **67 下只有 4/8 通过**，**板端 67 未测**。
- **四级逐级取证对新载荷不适用**（黄金向量是 R0.83 专用）。需**为每个载荷生成 `stage2_in/sparse_expect/stage3_expect` 黄金**后，四级取证才能覆盖它们；在此之前新载荷只能采信端到端判据。
- 数据包是**模拟测序数据**（质量值固定合成 `F`，覆盖为平铺+随机抽样而非纯泊松），**不是湿实验数据**。
- 噪声只含**替换**（D2 目标 1%），**不含插入/缺失**。

### 16.7 一次重跑失败的环境归因（2026-10-12 23:41 起）

为拿到无歧义判定，首轮 8/8 之后又跑了 `--skip-dump` 重跑，**8 套全部 FAIL 且判据 SHA 为空**。查明是**环境问题，不是板子或固件问题**：

```
FAIL  串口实录 — 不能明确确定 USB/PS 串口
FAIL  烧录     — xsdb 退出码为 0 但没打印 BOOT> running
       error "no targets found with $params(filter)"
SKIP  板端应用层就绪（CAPS）— 前置步骤已失败
```

排查（2026-10-12 23:44）：
- `usbipd list` 的 **Connected 列表里没有 `0403:6011`**；
- `Get-PnpDevice -PresentOnly` 匹配 `VID_0403` / `6011` **均为空**；
- WSL `lsusb` 里也没有。
- 那些 `Status: Unknown` 的 `FTDIBUS\VID_0403+PID_6011+15051B/C/D` 是**记忆中的幽灵条目**，不是在线设备。

**结论**：**板子的 FT4232H USB 桥整个从系统里消失了** —— 而板子正是靠这根 USB 供电。时间线上首轮 8 套在 23:30 市电切断前干净跑完，切换后板子 USB 掉了。**故重跑的 FAIL 是环境归因，不构成对 §16.4 那 8/8 结果的反例。**

**操作教训（并入 §9.4 一类的环境记录）**：
1. **市电切换/休眠会导致板子 USB 桥掉线**；恢复后必须重新确认在线枚举（`Get-PnpDevice -PresentOnly` 而非只看 `usbipd list` 的回显或幽灵条目）。
2. 连续多次烧录（本轮 8+8 次）后，即使设备仍在线，也可能出现**目标枚举退化**（`no targets found`）——按 §9.4 的办法**真正重新枚举 USB**再试。
3. **`--skip-dump` 那轮重跑尚未取得有效结果**，待板子恢复后补跑；在此之前**无歧义判定的留证以首轮 `SUMMARY.tsv` + 逐套 `.out` 为准**，并已在 §16.5/§16.6 说明 `G3 FAIL` 的成因是四级取证不适用于新载荷。

## 17. C2 泛化：v2 多媒体测试集 **21/21 在板上全部恢复**（2026-10-13）

用户提供的第二个外部数据包 `E:\桌面\dna-multimedia-simulation-v2-20261013`（下称 **v2**）。**21 个资产、baseline 与 challenge 两套、25 个编码块**；其自报软件侧结果为 `baseline_pass 21/21`、`challenge_pass 13 / fail 8`（**难例失败如实保留**）。

### 17.1 为什么 v2 比 v1 更严

| 维度 | v1 | **v2** |
|---|---|---|
| 水印 | 复用 R0.83 单一水印 | **每块独立随机水印** → 每次任务都要重新下发水印（验证"换水印"能力） |
| 载荷类型 | 只有 JPEG | **JPEG + WAV + MP4 + TXT + CSV + BIN**（任意文件字节） |
| 规模 | 8 套 | 21 资产（+ challenge 21） |

### 17.2 跑之前先修了一个真问题：非 JPEG 载荷的截断

`clients/python/native_ldpc.py` 的 `bits_to_jpeg_bytes` 用 `data.rfind(b"\xff\xd9")`（JPEG EOI）截断。对 JPEG 正确，但对非 JPEG **必然得不到真实长度**：含 `FF D9` 会截错，不含则返回带零填充的 6750 B 全长。v2 的 README 明确禁止对 WAV/MP4/二进制套用该规则。
**已修**（verify-system 实现，main 独立复核 diff 与回归后提交）：新增 `bits_to_payload_bytes(bits, input_bytes=None)` —— **不给长度时走原 JPEG 路径（零行为变化）**，给了长度按字节截断；`ldpc_decode.py` 新增 `--payload` 出口，`run_g3.sh` 透传 `--input-bytes N`；长度校验为正且 ≤6750。
**回归**：59 项 G3 主机用例、固件工作树、打包、卫生全 PASS；**R0.83 自检改动前后完全一致**（332 起始失败校验、5 轮、91 bit、6624 B、`fcd0cf90bd680e7b…`）。
**反向验证**：N 设对时 SHA 与 `input_sha256` 相同；**故意设 N+1 则 SHA 改变** —— 通路有鉴别力。

### 17.3 板上结果：**21/21 判据一致**

用 P4 包，`--score-min 65 --limit 4096 --skip-dump`；JPEG 走原 `FF D9` 路径，非 JPEG 显式传 `--input-bytes`（取自各块 `encoding.json`）。

| 类别 | 数量 | 结果 |
|---|---|---|
| 图像 (jpg) | 12 | **12/12 一致** |
| 音频 (wav) | 4 | **4/4 一致** |
| 视频 (mp4) | 2 | **2/2 一致** |
| 文本/CSV/二进制 (txt/csv/bin) | 3 | **3/3 一致** |
| **合计** | **21** | **21/21 一致，0 不一致** |

留证 `logs/g3/c2-v2/SUMMARY-all.tsv` 与逐资产 `all-<asset>.out`（`logs/` 不入库，文件保留）。

**可以对外说**：BKB220（xc7z020）P4 包在**真板**上，对 21 个独立资产（图像/音频/视频/文本/CSV/随机二进制）完成端到端恢复，**重建字节的 SHA-256 与各资产 `input_sha256` 逐字符相同**；且每个编码块使用**独立随机水印**，即依次重新下发水印后仍正确 —— 这同时证明了"每任务换水印"能力。

### 17.4 边界（不得外推）

- ~~**只跑了 baseline 集**。v2 的 **challenge 集（21 例，其软件侧 13 通过 / 8 失败）板端完全未测**~~（**2026-10-13 已关闭，见 §18**：challenge 集全量上板，板端判定与软件 **42/42 一致**，8 个难例失败模式同为 LDPC 不收敛）。
- 只测 `score_min=65`；**67 未测**。
- 数据包是 **in-silico 模拟测序**，不是湿实验数据；噪声模型为该包自述。
- **四级逐级取证对新载荷仍不适用**（`board_stage_check.py` 写死 R0.83 黄金向量），故本轮用 `--skip-dump`；端到端 SHA 为权威判据。
- 用 P4 包；P16 对同一 42 例、同一 `score_min=65` 的复测已在 §18.5 完成并与 P4/软件三方一致。该结论不覆盖 `score_min=67`。

## 18. C2 泛化：v2 **挑战集**上板 —— 板端判定与软件验证器 **42/42 完全一致**（2026-10-13）

§17 只跑了 v2 的 baseline 集，并把「challenge 集板端完全未测」列为边界。本节关掉这一项。

### 18.1 跑法

- 数据集：`E:\桌面\dna-multimedia-simulation-v2-20261013`，**全部 42 例**（21 资产 × baseline/challenge）。
- 每例用**该资产自己** `encoded/<asset>/block000/watermark.txt` 与 `encoding.json` 的 `input_sha256` / `input_bytes`；**不再无条件套用 R0.83 的水印**。
- JPEG 载荷走 EOI 截断；WAV/MP4/CSV/TXT/BIN **一律走 `--input-bytes` 裸字节截断**（`tools/run_g3.sh` 2026-10-13 新增通路）。
- **全量输入**：`--full`（每块 8192 条源读段 → 板端 16384 条记录）。**不是**之前的 `--limit 4096` 半量档——软件验证器用的是整份 `se150.fastq`，板端必须同量才可比。
- 判据阈值 `--score-min 65`，与数据集软件验证器一致；`--skip-dump`（四级取证对新载荷仍不适用，见 §18.4）。
- 板端身份：P4 包 `hw/build/bkb220-p4-enet0-software-20261012T140800Z-board-migrate`，首例整包烧录，其余例 `--skip-boot`（**42 例中 0 例出现烧录/就绪失败**，说明整轮期间板端应用未挂）。
- 留证：`logs/g3/c2-v2-challenge/SUMMARY.tsv` + 逐例 `<asset>-<class>.out`；每次运行的 `g3_runs/20261013T04*Z/` 在 Windows 侧 `D:\bkb220_board_smoke\` 下。`logs/` 不入库。

### 18.2 结果

| | 板端 | 软件验证器 | 一致 |
| --- | --- | --- | --- |
| baseline 21 例 | **21 PASS** | 21 PASS | 21/21 |
| challenge 21 例 | **13 PASS / 8 FAIL** | 13 PASS / 8 FAIL | 21/21 |
| 合计 | 34 PASS / 8 FAIL | 34 PASS / 8 FAIL | **42/42** |

**8 个失败例与软件逐例相同**，且失败**模式**也相同 —— 全部是 **LDPC 硬判决 50 轮不收敛**（`RuntimeError: LDPC 译码未收敛（50 轮后仍有 N 个失败校验）`），**不是"译出了错误的字节"**：

| 资产 | 挑战机制 | 残余失败校验 |
| --- | --- | ---: |
| `mandrill` | 同聚物富集的 indel | 636 |
| `tree` | GC 相关采样 + 宽丰度分布 | 4878 |
| `moon` | 参考序列存在未被观测到的连续区段 | 4261 |
| `grass` | 单一 founder 家族压倒性占优 | 279 |
| `beach_sand` | Type-II 内部 indel | 661 |
| `sea_waves` | 合成家族相关的连续缺失 | 4421 |
| `water_drops` | ONT-like 5% IDS、变长读段 | 5192 |
| `utf8_text` | 低覆盖且无覆盖度保证 | 1831 |

### 18.3 可以对外说 / 不可以说

**可以对外说**：

1. BKB220（xc7z020）**P4** 包在真板上对 **21 个独立资产 × 2 种测序条件 = 42 例**跑了全量端到端恢复，**板端判定与数据集软件验证器 42/42 完全一致**——包括 8 个难例的失败。
2. **每例使用该资产独立的随机水印**，逐例重新下发后仍正确或仍按同一机制失败，证明"每任务换水印"在本套数据上成立。
3. 这套数据覆盖 **JPEG / WAV / MP4 / UTF-8 文本 / CSV / 随机二进制**六类载荷，其中 5 类走的是**新的 `--input-bytes` 裸字节通路**（不再依赖 JPEG 的 `FF D9` 截断），说明该通路在真板上对任意载荷字节可用。
4. 失败**以"译码不收敛"的形式暴露，而不是静默给出错误字节**——这是当前硬判决算法在超出纠错能力的缺陷机制下的**正确表现**，也是判据没有被人为放宽的旁证。

**不可以说**：

- ❌「板端支持这些缺陷机制」——8 例失败就是失败，**必须保留，不得降难度后宣布泛化通过**（数据集 HANDOFF 明确要求）。
- ~~❌「P16 也测过」——本轮全部用 **P4** 包。~~（**2026-10-13 当天已补，见 §18.5**：P16 包跑同一套 42 例，与 P4 及软件三方一致。）
- ❌「已做四级逐级取证」——本轮 `--skip-dump`。

### 18.4 边界（相对 §17.4 更新）

- ✅ **已完成**：challenge 集板端测试及 P16 对同一 42 例的复测（见 §18.5，P4/P16 与软件判定三方 42/42 一致；其中 8 个 challenge 例仍以 LDPC 不收敛失败）。
- ❌ **仍未测**：v2 `score_min=67`；四级逐级取证对新载荷（`board_stage_check.py` 仍写死 R0.83 黄金向量）；8 h 长稳。2 h 长稳已完成，见 [2 h 长稳记录](../benchmarks/bkb220-p16-soak-2h.md)。
- 数据仍是 **in-silico 模拟测序**，非湿实验数据；噪声模型为该包自述，本项目未独立标定。
- 板端与软件一致**只说明两者跑的是同一套算法且判据同源**；它**不证明**该算法在真实测序误差下的恢复率，也不构成对论文中 FBA/软判决方法的评价。
- 本轮**未测量**功耗与硬件周期（`hardware_cycles`/`power_w` 无采集）。

### 18.5 P16 跑同一套 42 例：与 P4 及软件**三方逐例一致**（2026-10-13 当天补测）

§18 全部用 P4 包；本节用 **P16** 包（`hw/build/bkb220-p16-enet0-software-20261012T144141Z-board-migrate`，`C_STAGE1_P_WAYS=16` / `PIPE_TREE=1`）跑**完全相同**的 42 例、完全相同的输入与 `score_min=65`，脚本与目录见 `logs/g3/c2-v2-p16/`。

| 判定来源 | baseline 21 例 | challenge 21 例 | 合计 |
| --- | --- | --- | --- |
| 数据集软件验证器 | 21 PASS | 13 PASS / 8 FAIL | 34 / 8 |
| 板端 **P4** | 21 PASS | 13 PASS / 8 FAIL | 34 / 8 |
| 板端 **P16** | 21 PASS | 13 PASS / 8 FAIL | 34 / 8 |

- **三方一致 42/42**，不一致 0 例。
- **34 个成功例上，P4 与 P16 的判据 SHA-256 逐例相同**——P16 不是"另一种近似"，在这套数据上是**位对位等价**的实现。
- P16 轮同样 **0 例**烧录/就绪失败（首例整包烧录，其余 `--skip-boot`）。

### 18.6 顺带得到的真载荷性能交叉验证

同一轮扫描里，客户端对每例打印了板端结果耗时（与 [性能矩阵](benchmarks/bkb220-p4-p16-performance-matrix.md) 的 `t_result` 同口径：POST → 8100 B 收齐，不含上传与 LDPC）：

| | 中位 | 最小 | 最大 |
| --- | ---: | ---: | ---: |
| P4 | 4.470 s | 0.950 s | 6.430 s |
| P16 | 1.720 s | 0.600 s | 2.250 s |

- 逐例加速比：**中位 2.57×**，范围 1.58× ~ 3.11×。
- 42 例中 36~37 例的板端记录数正是 **16384**（其余 5 例因挑战库读段数不同而落在 2048~22720）。而 C1 矩阵在 **16384 记录档**独立测得 P4 4.5809 s / P16 1.7623 s（2.60×）——**两次互不相关的测量在中位与倍率上都对上了**。
- 这条交叉验证的价值：C1 矩阵是**单载荷、受控档位**的测量，本节是**42 个不同载荷、不同记录数**的真实任务。两者给出同一个倍率，说明该倍率不是某个载荷或某个档位的偶然。

**边界**：这里的耗时是客户端打印值，**不是** `hardware_cycles`；本轮仍**无**硬件周期与功耗采集。不同资产记录数不同，逐例加速比差异（1.58×~3.11×）主要来自记录数与调度抖动，**不要**拿它当"某类载荷更快"的结论。

### 18.7 外部数据包的独立核验（2026-10-13，main 亲自做）

§18 的全部结论都建立在一个**仓库外**的数据包上，而该包的自述（`audit_results.json` / `SHA256SUMS`）
属于**其作者的自报**。按本项目的判据纪律，自述不能当证据，故 main 另行独立复核了两件事：

| 核验项 | 自述 | main 独立复核结果 |
| --- | --- | --- |
| v2 包自洽（`SHA256SUMS`） | 612 条 | **612/612 全部 OK**（`sha256sum -c`，exit 0） |
| v1 旧包未被本次工作改动（`old_package_preservation.json`，183 条） | `all_original_hashes_equal: true` | **183/183 逐字节相同**，不同 0、缺失 0 |

⚠️ **核验时踩到的坑（与 `run_g3.sh` 那个 CRLF 判据 bug 同源）**：`SHA256SUMS` 是 Windows 写的，
行尾是 **CRLF**；直接 `sha256sum -c SHA256SUMS` 会把 `\r` 当成文件名的一部分，于是**612 条全部报
`FAILED open or read`**——看起来像"包被改坏了"，其实是行尾问题。必须先 `tr -d '\r'` 归一化再核。
**任何跨 Windows/Linux 的哈希清单校验都要先怀疑行尾**，这与本仓库里 UART 判据那条是同一类错误。

**边界**：以上只证明该外部包**自身完整、且 v1 未被 v2 的生成过程改动**；
它**不证明**该包内 FASTQ 的生物学真实性（仍是 in-silico 模拟），也不证明其噪声模型的正确性。

## 19. C2 泛化：v2 在**出厂门限 `score_min=67`** 下重跑 —— **26 PASS / 16 安全失败 / 0 危险**（2026-10-16）

### 19.1 为什么会有这一节

§17/§18 把 v2 的 42 例全部跑完了，但用的是 **`--score-min 65`** —— 那是**数据集自带软件验证器**
的门限，**不是出厂门限**。客户端的 `default_score_min(150) == 67`（`clients/python/task_protocol.py`），
发布件的 G3 与 8 h 长稳也都跑 67。
⇒ 此前的「泛化 42/42 一致」**建立在一个比出厂更松的门限上**，这一点在文档里**长期只写"未板测"、
没写要证明什么**。

**67 下数据包内没有软件基准可比**（它的验证器就是 65），所以这一项**不是"一致性"验收**。
它回答的是：

> 门限收紧到出厂值之后，**失败是不是安全的** —— 即板端以「纠不动」暴露、
> **不吐任何字节**，而**不是**静默给出错误字节？

### 19.2 怎么跑的

- 入口 `logs/g3/c2-v2-67/run_all_67.sh`（**已入库**）：42 例全量输入（每块 8192 源读段 → 板端
  16384 条记录），每例用**该资产自己**的水印与 `input_bytes`/`input_sha256`；
  JPEG 走 EOI 截断，其余走 `--input-bytes` 裸字节；`--score-min 67`、`--skip-dump`。
- 被测包：`hw/build/bkb220-p16-k2-ldpc-release-stage3poll-20261016T000308Z-board-migrate`
  （当日推广包，bit 与发布候选逐字节相同）；首例真烧录，其余 `--skip-boot`。
- ⚠️ 该脚本的 `failmode` 列**不可用**（字符串匹配只找"不收敛"字样，而 `run_g3.sh` 这一情形
  写的是「主机译码退出码=1」，匹配不上 ⇒ 全落 `OTHER_SEE_LOG`，**分类器失效但脚本照跑**）。
  **权威分类由 `.out` 原文离线重判**：`logs/g3/c2-v2-67/reclassify.py`（不改运行中的脚本）。
- 留证：`logs/g3/c2-v2-67/`（逐例 `.out`、`SUMMARY.tsv`、`SUMMARY-classified.tsv`、`run.log`）。

### 19.3 结果：安全性质成立，且单调

| | `score_min=65`（§18） | **`score_min=67`（本节）** |
| --- | ---: | ---: |
| PASS | 34 | **26** |
| FAIL | 8 | **16** |
| 其中**危险**（架构 PASS 却给错载荷） | 0 | **0** |
| PASS→FAIL / FAIL→PASS | — | **8 / 0** |

**16 例失败全部是 `SAFE_NOCONV`**：架构判据 FAIL（syndrome 非零）、
**系统判据输出「SHA-256 无载荷」** ⇒ 板端明确报告"纠不动"，**一个字节都没有吐出来**。

⇒ **在出厂门限下，板子失败得安全**，没有出现"译出合法码字但载荷不是期望的那一份"这类
**静默错误输出**。这是本项要回答的核心问题，答案是肯定的。

**单调性**：8 例 `PASS→FAIL`、**0 例 `FAIL→PASS`** —— 门限收紧只会让原本通过的变失败，
**没有反向翻转**。这是判据自洽的一条旁证（若出现反向翻转，说明门限与判据的耦合有问题）。

**8 例翻转**：`chirping_birds`(b/c)、`peppers`(b/c)、`rain`(b/c)、`sea_waves`(baseline)、
`water_drops`(baseline)。
⚠️ **观察，不是结论**：其中 **4 个 WAV 资产全部中招**（`chirping_birds`/`rain`/`sea_waves`/
`water_drops`），另加 `peppers`(jpg) 两例。**"为什么偏偏是音频"没有做机理分析**，
不得据此宣称"67 对音频不利"。

### 19.4 可以对外说 / 不可以说

**可以对外说**：

1. 在**出厂默认门限** `score_min=67` 下，板端对 v2 全部 42 例的失败**全部是安全的**
   —— 以「无可比较载荷」暴露，**没有一例静默给出错误字节**。
2. 门限从 65 收到 67 后，通过数 34 → 26（**8 例翻转，0 例反向**），**单调**。

**不可以说**：

- ❌「v2 在 67 下 42/42 与软件一致」—— **67 下数据包内没有软件基准**，本项不是一致性验收。
- ❌「泛化在出厂门限下同样通过」—— **没有**。67 下通过的是 **26/42**，不是 34/42。
- ❌ 任何关于"67 对某类载荷（如音频）有害"的**因果**说法 —— 只观察到相关性，未做机理分析。
- ❌「已做四级逐级取证」—— 全程 `--skip-dump`。

### 19.5 边界

- 这**不构成**对出厂默认值 67 的评价。67 从何而来（是否针对 R0.83 定的）**本节未追溯**；
  本节只说明：**用 67 跑这批为 65 设计的数据，会多失败 8 例，且失败方式安全**。
- 单次运行，**不是成功率统计**。
- 数据仍是 **in-silico 模拟测序**；噪声模型为该包自述，本项目未独立标定。
