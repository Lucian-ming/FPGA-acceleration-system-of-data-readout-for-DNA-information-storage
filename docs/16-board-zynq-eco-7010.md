# 16 · 目标开发板：ZYNQ ECO（XC7Z010）板级基准

本文是**板级配置的唯一权威来源**。凡涉及 PS7 外设、DDR、MIO、Bank 电压、启动模式，
以本文和 `docs/board/zynq-eco-7010/` 的原始资料为准；**历史 XSA 不再是板级配置依据**（见 §3）。

资料包：`docs/board/zynq-eco-7010/`，`sha256sum -c SHA256SUMS.txt` 15/15 通过。
体积过大的教学视频（13 MB）按 `.gitignore` 排除，其余全部纳入版本管理。

---

## 1. 板卡身份（已独立核实）

- 型号：**ZYNQ ECO**，器件 `XC7Z010-1CLG400C`（Vivado part `xc7z010clg400-1`）。
- **本项目使用的实物是 R6 版本**（用户 2026-08-29 确认：板上有 OLED）。
  - R5：左侧有 USB HUB、4 个 USB Host 口，无 OLED。
  - R6：去掉 USB HUB，中间 Type-C 改为 Zynq USB2.0 Host/Device，新增 128×64 单色 OLED。
  - 两版核心器件、DDR 组织、以太网、UART、JTAG、LED 和主要 PL 引脚相同；
    **USB 与 OLED 必须查 R6 原理图** `01_board_official/03_ZYNQ_ECO_R6_原理图.pdf`。

核实方式（不是转述资料自带的 README）：官方 LED 示例工程
`03_examples/ECO_LED_官方示例工程.zip` 的 part 为 `xc7z010clg400-1`，
XDC 引脚 `T12/U12/V12/W13`、时钟 `K17`，与硬件规格说明书逐项一致。

---

## 2. 板级关键参数

| 项目 | 实物确认值 | 来源 |
| --- | --- | --- |
| Zynq | `XC7Z010-1CLG400C` | 规格书 / LED 例程 |
| PS 晶振 | 33.3333 MHz | 规格书 §三 |
| PL 板载时钟 | 50 MHz，`K17`，LVCMOS33（SRCC 的 P 脚） | 规格书 §三 |
| **DDR3** | **单颗 `MT41J256M16HA-125`，16 bit 总线，512 MiB** | 规格书 §五 |
| 千兆网口 | RTL8211E-VL，GEM0 `MIO 16..27`，MDIO `MIO 52..53` | 规格书 §六 |
| 串口 | CH340，UART1 `MIO 48/49`，115200 | 规格书 §四 |
| JTAG | 板载 FT232H | 规格书 §四 |
| QSPI | W25Q128FV，16 MiB，`MIO 1..6` | 资料包 README |
| 主 SD | SD0，`MIO 40..45`，经 TXS02512 电平转换，可启动 | 资料包 README |
| PS Bank 电压 | Bank 500 = 3.3 V；**Bank 501 = 1.8 V** | 规格书 §二 |
| PL Bank 电压 | Bank 34 / 35 = 3.3 V；40 针扩展口在 Bank 34 | 规格书 §二 |
| 用户 LED（PL） | LED1 `T12`、LED2 `U12`、LED3 `V12`、LED4 `W13`，LVCMOS33，Bank 34 | 规格书 §八 + LED 例程 XDC |
| PL 按键 | `M20`、`M19`（Bank 35） | 规格书 §八 |
| PS 按键 | KEY1 → MIO0 | 资料包 README |
| EEPROM | 24C02，SDA `G17`、SCL `G18`（Bank 35） | 规格书 §七 |
| OLED（仅 R6） | D0 `E18`、D1 `E19`、DC `H20`、RST `G20` | 资料包 README |

### BOOT 拨码（SW1 的 1、2 位）

| 模式 | SW1 |
| --- | --- |
| JTAG | `00` |
| QSPI | `10` |
| SD | `11` |

任何模式下都可 JTAG 调试。**首次验证一律用 `00`，只经 JTAG 临时下载，不写 QSPI、不动 SD 卡内容。**

---

## 3. 关键修正：DDR 配置曾指向另一块板

### 3.1 问题

硬件规格说明书 §五原文：

> 我们开发板由于只有一颗16比特的DDR3，所以我们的PS在使用ARM的时候，
> **配置DDR3必须是16位，默认配置32位，如果不更改不能运行**。

而 2026-08-29 之前，`hw/scripts/bd.tcl` 固化的是：

| 参数 | 修正前 | 实物 |
| --- | --- | --- |
| `PCW_UIPARAM_DDR_BUS_WIDTH` | `32 Bit` | **16 Bit** |
| `PCW_UIPARAM_DDR_PARTNO` | `MT41J128M16 HA-125` | `MT41J256M16HA-125`（单颗） |
| `PCW_UIPARAM_DDR_DEVICE_CAPACITY` | `2048 MBits` | `4096 MBits` |

后果：DDR 训练失败，ARM 起不来，连串口都不会有输出。

### 3.2 来源追溯（重要）

`bd.tcl` 的板级参数原本注明「来自只读历史快照 `design_2_wrapper.xsa` 的 `design_1.hwh`」。
本次直接解包该 XSA 核对，发现**历史 XSA 自身就是 32 bit 双颗 `MT41J128M16`**：

```
PCW_UIPARAM_DDR_BUS_WIDTH        32 Bit
PCW_UIPARAM_DDR_PARTNO           MT41J128M16 HA-125
PCW_UIPARAM_DDR_DEVICE_CAPACITY  2048 MBits
```

即**历史演示跑在另一块板上**，不是这块 ECO。`bd.tcl` 只是忠实复制了它。
这为文档里长期强调的「历史 XSA 不能当作当前构建证据」补上了具体证据。

> **禁止**据历史 XSA 回退 DDR 配置。历史 XSA 在 GEM0/MDIO/UART1/Bank 电压/晶振/FCLK0
> 这些项上与 ECO 一致（已逐项复核），但 DDR 一项必须以本文为准。

### 3.3 修正内容

`bd.tcl` 改为 `16 Bit` + `MT41J256M16 RE-125` + `4096 MBits`，`T_RC` 同步为预设值 `48.91`。
`MT41J256M16 RE-125` 是 Vivado 2022.2 预设中与实物同组织（256Meg×16，4 Gbit）、
同速率（-125）的型号，仅 die revision 不同。

### 3.4 影响面（很窄）

- **DDR 总容量不变**，仍为 512 MiB。`docs/05-interfaces.md` §4 的 DDR 布局
  （`0x1000_0000`–`0x1190_0000`）**无需改动**，最高用到约 294 MiB，远在容量内。
- **PL 侧完全不受影响**：本设计不引出任何 PL 外部引脚，也不使用板载 50 MHz 时钟
  （PL 时钟来自 PS 的 FCLK0），因此 RTL、三个 IP、`hw/constr/top.xdc` 与时序结论都不动。
- **DDR 带宽减半**：32 bit → 16 bit，理论峰值由约 4.3 GB/s 降到约 2.1 GB/s。
  本流水线单次任务的 DDR 流量在 10 MiB 量级，瓶颈在 Stage1 比对计算而非内存搬运，
  故对端到端性能无实质影响。
- **既有制品作废**：`hw/build/export/` 中的 `dna_accel.xsa` / `top_bd_wrapper.bit` /
  `fsbl.elf` / 应用 ELF / `BOOT.bin` 全部是按 32 bit DDR 生成的，**不能烧到 ECO 板**，
  必须整套重建。

---

## 4. 与当前工程的逐项核对结果

除 DDR 外全部吻合（`bd.tcl` 与 ECO 资料对比）：

| 项 | 工程 | 实物 | 结论 |
| --- | --- | --- | --- |
| part | `xc7z010clg400-1` | `XC7Z010-1CLG400C` | ✅ |
| PS 晶振 | 33.333333 MHz | 33.3333 MHz | ✅ |
| GEM0 | `MIO 16..27` | 同 | ✅ |
| MDIO | `MIO 52..53` | 同 | ✅ |
| UART1 | `MIO 48..49` @115200 | 同 | ✅ |
| Bank 500 / 501 | 3.3 V / 1.8 V | 同 | ✅ |
| FCLK0 | 100 MHz | PL 时钟由 PS 提供 | ✅ |
| PL 外部引脚 | 无（`top.xdc` 无引脚约束） | LED/KEY/HDMI 均未使用 | ✅ 不冲突 |
| DDR | 见 §3 | 见 §3 | ❌ 已修正 |
| SD0 / QSPI / USB | 未启用 | 板上均有 | ⚠️ 见 §5 |

---

## 5. 尚未处理的板级项

1. **SD0 / QSPI 未在 PS7 中启用**。JTAG 调试不需要；要做 SD 或 QSPI 启动镜像，
   必须按 `MIO 40..45`（SD0）和 `MIO 1..6`（QSPI）补齐配置并重建 FSBL/BOOT.bin。
2. **DDR 板级走线延迟未知**。当前 `PCW_UIPARAM_DDR_BOARD_DELAY*` 仍是从历史（错误）
   板卡继承的 `0.25`，ECO 资料未给出该参数。写均衡、读门控、数据眼三项训练均已开启
   （`TRAIN_WRITE_LEVEL` / `TRAIN_READ_GATE` / `TRAIN_DATA_EYE` = 1），通常可自适应，
   但这是**上板才能确认**的残留风险；若 DDR 自检不过，优先怀疑此处。
   16 bit 单颗时 `BOARD_DELAY2/3` 与 `DQS_TO_CLK_DELAY_2/3` 不参与。
3. **WSL 连不上开发板**：检查时 WSL 无 Xilinx/FTDI udev 规则，Windows 未装 `usbipd-win`，
   也未发现已连接的 FT232H/CH340。两条可选路径：Windows 侧运行 AMD Hardware Server
   让 WSL 的 Vivado 通过网络连接；或安装 `usbipd-win` 把 USB 设备附加给 WSL。
   选型前先在 Windows 设备管理器确认实物 VID/PID。

---

## 6. 首次上板顺序（B 阶段，尚未执行）

1. 断电拍摄正反面，确认 PCB 版本与接口布局（本板已确认为 R6：有 OLED）。
2. SW1 拨到 JTAG `00`，只接标注 DEBUG 的 Type-C 口，不接任何外部扩展模块。
3. 在 Windows 设备管理器确认 FT232H（JTAG）与 CH340（串口）。
4. **先烧官方 LED 例程的 PL-only bit 做最小冒烟**——它的 part 与四个 LED 引脚已与原理图核对一致。
   这一步的目的是把「板子/下载器/供电」与「我们的设计」两个变量分开。
5. 再下载本项目重建后的 bitstream + ELF，经 JTAG 跑 DDR 自检与串口日志。
6. 验证以太网 `192.168.1.10:7`，最后才考虑制作 SD/QSPI 启动镜像。

---

## 7. 原始资料索引

| 路径 | 内容 |
| --- | --- |
| `01_board_official/01_ZYNQ_ECO_硬件规格说明书.pdf` | R6 及以后版本硬件说明（15 页），**DDR 结论出处** |
| `01_board_official/02_ZYNQ_ECO_R5_原理图.pdf` | R5 原理图（11 页），仅作对比 |
| `01_board_official/03_ZYNQ_ECO_R6_原理图.pdf` | **R6 原理图（12 页），本板适用** |
| `02_amd_reference/DS190_Zynq-7000_Overview.pdf` | AMD Zynq-7000 概览 |
| `02_amd_reference/DS187_XC7Z010-XC7Z020_DC-AC.pdf` | AMD 电气与时序规格 |
| `03_examples/ECO_LED_官方示例工程.zip` | 官方 PL-only LED 工程（含 XDC 与已生成 bit），冒烟测试用 |
| `04_photos/` | 板卡接口标注图 |
| `00_sources/*.json` | 产品/附件/教程的原始站点元数据 |
| `SHA256SUMS.txt` | 全部文件 SHA-256 |

教学视频 `03_examples/tutorials/ECO_蜂鸣器上板演示.mp4`（13 MB）按 `.gitignore` 排除，
校验和仍记录在 `SHA256SUMS.txt`，需要时另行获取。

在线参考见 `docs/board/zynq-eco-7010/README.md` §9。
