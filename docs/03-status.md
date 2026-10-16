# 03 · 当前状态与交接

更新：2026-10-13。本文件合并当前状态与原10交接摘要；旧完整状态/审计留在[归档索引](archive/history/2026/pre-bkb220-handoff-2026-10-10/README.md)。接手先读[05执行计划](05-implementation-plan.md)和[主Agent提示词](agent-prompts/main.md)，板级细节见[07](07-board-build-and-acceptance.md)。**2026-10-10/11 的「新板未到货、只见蓝牙 COM3/COM4、无 FTDI/JTAG」设备枚举已作废**，以本文件 §1a 的 2026-10-12 实测为准。

## 1a. 2026-10-12 新板现场实测（取代此前交接快照）

BKB220 已到货并连接，main 已在 JTAG 上核实：

| 事实 | 证据 |
|---|---|
| 器件 **xc7z020**，IDCODE `0x23727093` | JTAG 链 `Xilinx HW-Z1-ZCU104 FT4232H 15051A` → `arm_dap (4ba00477)` → `xc7z020`；手册 p.5-6 写 XC7Z020-2CLG400I |
| 板载 **FT4232HL** 桥，无需外置下载器 | 手册 p.7；三串口 + JTAG 与手册 p.16「一路 PL、一路 PS 加 JTAG」相符 |
| 串口：通道 A=JTAG，B/C/D=三串口 | Windows 为 COM9/10/11；直通 WSL 后 `/dev/ttyUSB0`=JTAG、`1/2/3`=串口。已确认 PS UART 为 UART0/MIO14-15，FT4232H C 通道（COM10 / `/dev/ttyUSB2`） |
| 网口：ASIX USB 千兆网卡在 Windows 侧 `192.168.1.100/24`，链路 1Gbps | 已确认网线是**板子直连该 ASIX 网卡**。2026-10-12 经 JTAG 用 MDIO 实测：PHY = **Realtek RTL8211E**（OUI 0x001CC9），自协商完成、**1000BASE-T 全双工 link up**，与 1Gbps 互相印证。板端仍尚未发过 TCP 包（ReceivedBytes=0，属正常：还没跑固件） |
| `BOOT_MODE` 0xF800025C = `0` | **JTAG 启动模式**；`DDR_PLL_CTRL=0x3F`（DDR PLL 掉电）、`FPGA0_CLK_CTRL` bit0=0、`GEM0_NETWORK_CONTROL=0`、`UART0/1_CTRL=0x128` → PS 是干净的 JTAG 待机态，只有 BootROM 在跑 |
| **PS_CLK = 33.333 MHz** | 由 `IO_PLL_CTRL` FBDIV=26 推出 IO PLL=433.33 MHz，且 BootROM 能正常执行。属推导+寄存器证据，非厂商书面确认 |
| **原理图已入库**（2026-10-12 用户提供） | [BK_B220_SchDoc.pdf](board/bkb220/BK_B220_SchDoc.pdf)（Altium，23 页，SHA `fb7947df…`）。**补齐**：PS_CLK 33.333MHz 晶振、UART0=MIO14/15、ENET0 **RGMII**+PHY=**RTL8211E-VL**、**PHY 地址=1**、**PHY 复位 `PHYRSTB` 接 `PS_POR_B`（非 GPIO）**。逐条见[来源表 §10](board/bkb220/migration-source-table.md) |
| 手册给出的可采信规格 | DDR3 **两片 Micron MT41K256M16TW-107、32bit、1GB、最高 533MHz/1066Mbps**（p.9-10，与旧板单颗 16bit MT41J256M16HA-125 **完全不同**）；QSPI W25Q256 32MB 在 MIO1..6（p.8-9）；启动 JTAG/QSPI/SD（p.15）；MIO0=3.3V、MIO1=1.8V、DDR=1.5V（p.8） |

**仍缺**：厂商 board_files/PS7 preset、原厂例程、DDR 板级延迟与 DQS-to-CLK、工业级精确料号，以及**板卡实物与该版原理图修订是否一致（未核对）**。~~PCB 原理图~~、~~PS UART 的 MIO~~、~~ENET0 的 PHY/MDIO/RGMII/复位~~ 均已由原理图关闭；PS_CLK 已由寄存器证据 + 原理图双重确定。

## 1b. 工具链分工与触板通道（2026-10-12 重写）

**用户 2026-10-12 明确的分工：开发全部在 WSL 用 2022.2；Windows 里的 2026.1 只负责烧录。**

| 用途 | 工具链 | 位置 |
|---|---|---|
| **RTL / BD / 约束 / 综合 / 实现 / 时序 / bit / XSA** | **Vivado 2022.2** | WSL `/tools/Xilinx/Vivado/2022.2` |
| **PS 软件（BSP / 应用 ELF / FSBL / BOOT / readback）** | **Vitis + XSCT 2022.2** | WSL `/tools/Xilinx/Vitis/2022.2`（ARM GCC 11.2） |
| **烧录 / 下载 / 调试** | **Vivado / Vitis 2026.1** | Windows `D:/xilinx/2026.1`（XSDB / hw_server / Hardware Manager） |
| F9：26 完整开发链的独立复核 | Vivado / Vitis 2026.1 | 同上，22 主线稳定后才做 |

- **22 主线是唯一发布线**：F0～F8 的构建、软件包与判据都来自 WSL 2022.2；Windows 26 不产出新板验收制品，只烧录 22 产出的 bit / ps7_init / ELF。
- **软件版本按各自安装树实际提供的选**：WSL Vitis 2022.2 只有 `lwip211_*`（仓库 `sw/scripts/create_vitis.tcl` 本就按 `lwip213→lwip211→lwip210` 回落）；`lwip220` 是 **2026.1** 才有的（见 [工具核查](benchmarks/bkb220-toolchain-audit.md) 的 BOM 绕行记录）。跨版本不要求 lwIP 主版本相同。
- **2026.1 的已知坑**：`xsct.bat` 实测 disabled 且可能 **exit 0**，软件必须走现代 Python 入口（`create_vitis_modern.py`/`run_vitis_modern.ps1`）；**launcher 退出 0 不能单独作为成功判据**。

**串口与 JTAG 的通道映射（2026-10-12 实测 + 原理图双重确认）**

| FT4232H 通道 | 功能 | 序列号 | Windows | WSL |
|---|---|---|---|---|
| A | JTAG | 15051A | （XSDB 直接用） | `/dev/ttyUSB0` |
| B | 未使用/备用 | 15051B | COM9 | `/dev/ttyUSB1` |
| **C** | **PS UART（UART0 / MIO14-15）** | **15051C** | **COM10** | **`/dev/ttyUSB2`** |
| D | PL UART | 15051D | COM11 | `/dev/ttyUSB3` |

> 按序列号认通道比按 COM 号稳（重枚举后 COM 号可能变）。**不要用蓝牙 COM3/COM4 兜底。**

**触板操作要点**

1. **两种可用路径**：Windows 26（烧录，指定路径）与 WSL 22（`usbipd` 直通 + Linux hw_server，**F3 就是这么做通的，已验证**）。设备同一时刻只能归一边：归 Windows 就用 `COMx` + Windows XSDB；归 WSL 就用 `/dev/ttyUSBn` + Linux hw_server。
2. **切换归属后必须真正重新枚举 USB**（`usbipd attach/detach`，确认设备号变化）；只重启 hw_server 会只看到 `xc7z020` 而看不到 `arm_dap`，容易误判「PS 不在链上」。
3. **断电后 FT4232H 回落到 Windows**，usbipd 直通断开，且会在 3132 端口留下一个**已无设备的旧 hw_server**——恢复时要先按端口找 PID 杀掉它再起新的。
4. **任何 MDIO / PHY 观测必须排在 `ps7_init` 之后**（MDIO 要 MIO52/53 被 mux 才通；断电后 MIO 未配置，直接读会全回 0）。
5. **`BMSR` bit2 是 latching-low**，判断链路当前状态至少读两次。

**蓝屏历史的处置（2026-10-12 用户确认已解决）**

2026-10-12 连接测试期间 Windows 主机**蓝屏两次**（BugCheck `0x139`/参数1=`0xA`，两份转储当前进程均为 `hw_server.exe`，栈均为 `ftdibus+0xf4d4`）。同日用户自行处置，并**明确告知崩溃风险已解决**；此前也已确认 **USB 供电即可**（不必接手册 p.15 的 10 号 5V-DC）。

据此，**Windows 2026.1 作为烧录路径按正常状态使用**，不再附加"仅限根因根治前"的限定。

**但两点要说清楚（不是唱反调，是留证纪律）**：
- 原始诊断与修复记录保留在仓库外（`D:\Agent\outputs\reboot-diagnosis-20261012\`、`ftdi-repair-20261012\`）。**具体修复项没有记进本仓库**，所以"已解决"是**环境所有者（用户）的判断**，不是本项目独立复现出来的结论。
- WSL 22 路径（`usbipd` 直通 + Linux hw_server，**F3 就是这么跑通的**）作为**已验证的替代入口保留**。它不是"必须的回退"，只是当 Windows 侧再出现异常时，有一条当场就能用的路。

证据（仓库外，保留）：`D:\Agent\outputs\reboot-diagnosis-20261012\`、`ftdi-repair-20261012\`、`bkb220-connectivity-20261012\`。仓库内 JTAG 只读证据在 `logs/jtag/`（`logs/` 已被 .gitignore 覆盖，未入库）。

## 1. 当前目标与完成边界

本轮是旧 ZYNQ ECO R6 / XC7Z010 到 BKB220 / XC7Z020 的 SE150、PL 100 MHz 迁移，Stage1 使用 16 滑窗位置并行。生产几何 150/50/807/957/64、64 记录/帧、线上协议和 8100 B 结果格式不变。BKB220 配置为 `ready=1`；P4/P16 完成整机 route 与 bit/XSA 构建，P4 G3 和 P16 多项板测已有记录。P16 六档矩阵、42 例 v2 数据集板测对照、故障探针和 2 h 长稳已完成。

当前未完成项：v2 的 `score_min=67` 尚未板测；8 个 challenge 例仍以 LDPC 不收敛失败；新载荷四级板端取证、8 h 长稳、QSPI/SD 冷启动、**UART 反向（✅ 2026-10-14 已实测通过，见 [UART 反向实测](benchmarks/bkb220-uart-reverse.md)）**、功耗及 F9 独立复核未完成。四级工具现按 G3 期望载荷 SHA 选择基准；没有登记基准时明确输出 `UNVERIFIED`，不再拿 R0.83 向量裁决新载荷。当前四级基准仍只覆盖 R0.83 的 SE150/SE250，两种几何均不代表 D1/D2 已取证。完整 P16 手工包已有 G3 PASS 记录；从硬件包到软件验收包的自动化入口现为 `tools/rebuild_software_package.py`，2026-10-14 用当天硬件包重建并通过 2965/2965 SHA 自检及 `--strict-artifacts --plan-only`。该次 plan-only 不是新包的板端 G3；复现步骤、XSCT socket 回退及字段/哈希对照见[制品复现说明](submission/reproduce-artifacts.md)与[任务报告](../logs/submission/vitis-chain.md)。P16 仍慢于 16 线程 CPU；Stage1 K2 已有 OOC 与整机 route 证据，后续工作仍在进行，不能据此写成 Stage1 优化已完成。详见下文和对应 benchmark。

工具链按用户指定分工：开发全部在 WSL 用 Vivado/Vitis 2022.2；Windows 2026.1 只负责烧录、下载和调试。22 主线稳定并完成优化报告后，再做 Windows 2026.1 完整开发链独立复核，规则见 05/07。

~~用户最新说明板卡尚待数小时到货~~（2026-10-12 作废：板卡已到货并连接，见 §1a）。6个历史工具已原样归档，现用入口与启动器版本选择修正见[工具整理记录](reference/tool-cleanup-2026-10-11.md)。

## 2. P13～P15：旧板与候选基线

| 事实 | 证据及适用范围 |
|---|---|
| P13旧板SE150全量及超时修复已板验 | 103616板端记录；全量中位数25.69s、2016源读段/s；单核C约1.48倍，仍慢于16线程约6.9倍；板级run摘要在docs/board/run-logs/20260922T*，[性能策略](08-performance-and-strategy.md) |
| P13修复使用30s墙钟超时 | Voter/Decoder原按poll次数会误超时；主循环事件推进/cache优化保留，不能盲删200us节流 |
| P14候选P16只做功能/OOC | XC7Z020生产几何OOC 26867 LUT、WNS+0.705ns，未整机/未上板；[摸底摘要](benchmarks/stage1-pway-7020-probe.md) |
| P15同片ARM纯软件基线 | 单A9约12.10ms/记录，1024记录结果逐条核对；相对旧PL每记录0.2451ms约49倍；[ARM摘要](benchmarks/measured_arm_baseline.md)；双核/能耗未测 |
| 泛化、误接受率、故障恢复有历史证据 | 多payload与G5/G6摘要见09；均注明旧板/主机/合成边界，不能自动升级为新板通过 |
| SE250是独立历史profile | 当前发布生产几何150；旧SE250成功与当前BKB220迁移分开，不能混制品 |

## 3. P16：本轮迁移准备已验证内容

| 成果 | 实际结果/证据 |
|---|---|
| 正式P4/P16参数与源集 | 默认4/0，可选16/1；打包与Vivado2022.2真实catalog通过；[集成摘要](benchmarks/stage1-16way-ip-integration.md) |
| LC50独立模块与真实AXI包装接口 | Windows2026.1 XSim两个case各两轮PASS；Icarus LC50模块同周期PASS。模块P4=1680956、P16=513755周期，约3.27倍仅模块周期改善 |
| G3主机门禁与矩阵编排 | 40+7=47项通过，使用fixture/替身；[主机摘要](benchmarks/bkb220-host-verification.md) |
| 工作树固件行为 | 主机行为回归通过；SDT/BSP兼容与64位超时修改未更改预期寄存器/DMA行为 |
| 现代软件生成入口 | Windows2026.1旧ECO XSA的A14实际生成BSP/应用ELF/FSBL/BOOT/readback及六产物SHA通过；PS5 wrapper正反用例通过；[工具摘要](benchmarks/bkb220-toolchain-audit.md) |
| 工作区与文档整理 | 根编号文档20份合并为9份；旧内容及映射保留归档；历史生成物精确忽略、原位保留；[整理记录](reference/workspace-cleanup-2026-10-10.md) |

Icarus重复LC50接口长测在XSim正式接口通过后主动停止，不称Icarus接口PASS。旧BSP13个C文件编译通过，临时旧链接探针因Newlib/VFP ABI失败，不能称旧工具链重建成功。起点参赛agent_view.sh重复附件已改为引用tools唯一源解决；源SHA未变，旧失败日志保留。

## 4. 未关闭的依赖与后续顺序

2026-10-11资料更新：用户提供的[BKB220产品手册v1.1.pdf](board/bkb220/BKB220产品手册v1.1.pdf)已随仓库收录；原件与副本SHA-256一致，来源、校验命令见[资料索引](board/bkb220/README.md)。main和board-migrate先阅读并校验仓库内手册，使用手册页码注明规格来源，不再把产品手册列为缺项或依赖微信目录。

~~2026-10-10/11设备核查快照没有实际FTDI/JTAG/PS USB串口，只见蓝牙COM3/COM4~~（2026-10-12 作废：已实测到 FT4232HL JTAG 与 COM9/10/11，见 §1a）。**仍然**待确认的是：厂商对应 PCB 原理图、PS7 preset/board_files、原厂例程、实物完整料号（顶标/温度等级/PCB 修订），以及 ~~PS UART 的 MIO~~、~~ENET0 的 PHY/MDIO/RGMII/复位~~（均已由原理图 §10 关闭）、DDR 板级延迟与 DQS-to-CLK。~~`hw/boards/bkb220.tcl` 的 `ready=0` 不变~~（2026-10-12 已按用户授权置 1 并实板验证，见 §1c）。

按05承接已完成阶段，不重开通过的门禁：`ready=1`、P4/P16 route 与构建、P4 G3、P16 全量/连续/恢复/故障探针、六档矩阵和 P4/P16 v2 42 例对照均有记录；2 h 长稳完成。当前剩余为 v2 `score_min=67` 板测、新载荷四级板端取证、8 h 长稳、QSPI/SD 冷启动、UART 反向、功耗和 F9。四级检查器已能将无基准明确分成未取证，但 D1/D2 尚无四级向量和板端四级证据。完整 P16 包已有 G3 PASS，但 Vitis 自动化生成仍需补步；Stage1 K2 后续工作仍在进行。功耗需仪器；SE250另profile；D0不默认分发。剩余门禁通过前不宣布迁移完成。

**工具链分工不变**：开发与构建全部在 WSL 2022.2，**Windows 2026.1 只负责烧录**；F9 用 26 做完整开发链的独立复核（22 主线稳定后）。见 §1b。

### 2026-10-12 接管进度（历史阶段快照，已由后续进度取代）

| 阶段 | 状态 |
|---|---|
| F0 接管与现场核对 | **完成**：仓库绑定 PASS（main/origin 0/0，HEAD `22a0874`）、工具链与真实设备枚举、`agent_view` 以 main 登记、按现成 05 计划接管 |
| F1 已有成果确认 | 子 Agent 只读复核完成：P4/P16 正式源集与 `PACKAGED_VARIANTS.txt` 条目集合一致、无未覆盖文件、`check_ip_packaging.sh` 与 `check_repo_hygiene.sh` main 复跑均 **exit 0 PASS**（子 Agent 报的 packaging FAIL 是只读沙箱无法建临时输入所致，非真实缺陷）。P16 整机 LUT 先验约 33.9k（64%），仅 OOC 外推 |
| **F2 新板配置** | **基本完成**：来源表与候选 PS7 profile 已产出并经 Vivado 2022.2 逐属性验证（[来源表](board/bkb220/migration-source-table.md) §8、`hw/boards/bkb220.tcl`，`ready=0`）。**实测已定**：PS_CLK=33.333 MHz、DDR=533.33 MHz(DDR3-1066)、FCLK0=100 MHz、PS UART=UART0/MIO14-15→FT4232H 通道 C。`MT41K256M16TW-107` 被 PS7 catalog 拒绝，改用自定义 DDR 参数 |
| **F3 最小启动** | **全部通过**：`ps7_init`/`ps7_post_config` RC=0；DDR 0x10000000 起 1024 字写读 **0 不符**；UART0 经 JTAG 回环被 `/dev/ttyUSB2` 以正确 ASCII 收到；**ENET0 经 MDIO 实测 PHY=RTL8211E、1000BASE-T 全双工 link up**。尚缺 CAPS（需固件，属 F4）。详见 §1c |
| **F4/F5 构建与整机时序** | **通过**：P4(4/0) 与 P16(16/1) 均在 `xc7z020clg400-2` 完成完整 route + bitstream + XSA，**WNS +0.680/+0.617、WHS +0.036/+0.017、失败端点 0、DRC 0 errors、`clk_fpga_0`=100.000MHz**。P16 资源 33,987 LUT(63.89%)，与先验 33.9k/64% 吻合。详见 [benchmark](benchmarks/bkb220-p4-p16-100mhz-build.md) |
| **F4 整机 G3** | **通过（7/7 全绿）**（[来源表 §13](board/bkb220/migration-source-table.md)）：补回 profile 缺失的 ENET0 MIO 配置并重建后，CAPS 握手、4096 板端记录、**图片 SHA `fcd0cf90…f2c3` 逐位相同**、四级 DDR 取证通过、串口实录 7781 字符。通道为 Windows 2026.1 烧录 22 制品 + COM10，符合 §1b 分工 |
| F6～F8 | 未开始：全量≥3 次、连续/脏干净、断连恢复、性能矩阵、泛化/长稳；`REQP-1839/1840` 异步复位 BRAM 警告待 RTL 复核。**板上是 P4，P16 尚未上板** |
| F9 | 未开始：22 主线稳定后，用 Windows 2026.1 独立重建 P4/P16 硬软包并复核（分工见 §1b） |

## 1d. 断点：2026-10-12 23:30 断电，次日白天继续

**已完成并全部推送**（`main...origin/main` = 0/0，工作树干净）：

| 阶段 | 状态 |
|---|---|
| F0～F5 | 完成（含 P4/P16 整机 100MHz 收敛） |
| **F4 整机 G3** | **PASS 7/7**（图片 SHA `fcd0cf90…f2c3`） |
| **A P4 板端深化** | **全完成**：A1 全量三轮、A2 连续+状态复位（鉴别力自证 1500/64800 bit）、A3-1 配置守卫 7/7、A3-2 断连畸变恢复 30/30、A3-3 中途断网+SIGKILL 3/3 |
| **B1 P16 重建** | 完成（WNS+0.617/WHS+0.017/失败端点 0/100MHz/33,987LUT；`ps7_init` 已含 ENET0；manifest 核出 `P_WAYS=16/PIPE_TREE=1`） |
| **B2 P16 上板** | smoke **PASS**、全量三轮 **PASS**、连续+状态复位 **PASS** |

**P16 首个端到端对照**（同板/同输入/同判据）：smoke 档 `t_result` 0.75s vs P4 1.45s（≈1.9×）；全量档 **8.61s vs 26.51s（≈3.05×）**。口径：`t_result` 不含上传与 LDPC、不是整轮，正式口径见 F7 矩阵。

**断电后从这里继续**（**权威顺序见 [05 §7 按比赛评分表重排的后续计划](05-implementation-plan.md)**，那里把评分权重、合规缺口和单列项都编进去了）：

### 1e. 2026-10-12 深夜补记：板子已断电，收尾后的准确断点

**板子状态：已断电（用户 23:30 市电切断，板子靠该 USB 供电，FT4232H 已从系统消失）。**
清查方式（**别被幽灵条目骗**）：`Get-PnpDevice -PresentOnly` 匹配 `VID_0403` 应为空、`usbipd list` 的 **Connected 段**无 `0403:6011`。那些 `Status: Unknown` 的 `FTDIBUS\VID_0403+PID_6011+15051B/C/D` 是**记忆条目**，不是在线设备。
**明天开工第一步：重新接上板子 USB，按 [07 §3a](07-board-build-and-acceptance.md) 确认通道**（`usbipd` 归属 → `hw_server` → **COM10** / `ttyUSB2`）。

**今晚新增（全部已提交推送，`main...origin/main` = 0/0，工作树干净）**：

| 项 | 结果 |
|---|---|
| **C2 泛化首测（重要）** | 用户外部数据包 **8 套全跑，8/8 成功** —— 4 张 SIPI 图 ×（干净 / 加 1% 替换噪声），**板端回传经 LDPC 重建的图片 SHA 全部与 manifest 的 payload SHA 逐字符相同**；**无需重建比特流**（水印随任务上传）。见[来源表 §16](board/bkb220/migration-source-table.md) |
| 大模型协作出赛材料 | `docs/submission/ai-collaboration/`（含 `self-correction.md` 四条纠错轨迹） |
| 技能包 | `docs/submission/skill/` 8 个包审阅补齐 + `audit.md`；**修了一个真缺陷**：`ooc_probe.tcl` 原来 WNS 为负也 `exit 0`，现在会红 |
| 阶段总结 | `docs/reference/phase-summary-2026-10-12.md`（**非最终报告**） |
| 计划重排 | [05 §7](05-implementation-plan.md)：按比赛评分表重排 + 单列项编入 |
| 纪律补强 | `AGENTS.md` 新增：**子 agent 在沙箱内不要跑 `verify_repo_binding.sh`**（今晚因漏写这条白跑四个子任务） |

**“明天待办”是 2026-10-12 深夜的历史快照；完成情况以紧随其后的 2026-10-13 白天进度和傍晚追加为准。**

**当时待办（按优先级）**：

1. **接回板子** → 补跑 C2 的 `--skip-dump` 那轮（首轮 8/8 已有效，这轮只为拿无歧义 PASS 留证；脚本在 `logs/g3/c2-sweep/rerun_skipdump.sh`）。
2. **C2 收尾**：`score_min=67` 下逐套复测（数据包自报软件侧 67 只 4/8，**板端未测**）；**为每个载荷生成四级黄金向量**（`tests/golden` 现在只有 R0.83 一套，导致四级取证对新载荷误报 FAIL）。
3. **C1 六档矩阵**：同板 P4/P16 各 ≥3 次（性能与资源 20 分的正式证据）。
4. **P2 合规缺口**：**仓库根无 `LICENSE`**（比赛要求开源 MIT/Apache）；Vivado 版本说明（主线 2022.2 vs 硬要求 2026.1/2025.2）；`README.md`/`AUDIT.md` 大写命名与"纯英文小写"的冲突待用户定。
5. **B2 剩余**：P16 的配置守卫 / 断连畸变 / 中途断网三个探针（**中途断网那个用 `sudo iptables`，只在 `finally` 清理**）。
6. 之后按 [05 §7](05-implementation-plan.md) 的 P3～P7：全面优化 → 冻结 → 报告 → 26 → 交付与海报。

### 2026-10-13 白天进度（上面那份「明天待办」的逐条处置）

| 待办 | 状态 |
| --- | --- |
| 1. 补跑 C2 `--skip-dump` 无歧义留证 | ✅ 已完成（8/8 clean PASS） |
| 2. C2 收尾 | 部分：**v2 challenge 集已上板**（见下）；`score_min=67` 与「每载荷四级黄金向量」仍未做 |
| 3. C1 六档矩阵 | ✅ 已完成，正式口径见 [性能矩阵](benchmarks/bkb220-p4-p16-performance-matrix.md) |
| 4. P2 合规缺口 | 部分：**`LICENSE`（MIT）已入库**并写明第三方素材适用范围；**命名已下沉**——`docs/submission/**` 与 `docs/agent-prompts/**` 共 12 个文件改为小写（0 断链、卫生 PASS），`archive/**` 因有按路径 SHA 留证而故意不动；Vivado 版本说明仍待处理 |
| 5. B2 剩余三个探针 | ✅ 已完成（P16 包：配置守卫 7/7、畸变包 30/30、中途断网 3/3，之后判据轮全量 `score_min=67` PASS）见 [探针 benchmark](benchmarks/bkb220-p16-fault-probes.md) |
| 6. P3～P7 | 未开始；**P3 方向已于今日更正**，见下 |

**今日新增的两项实质结论**：

1. **C2 泛化在 v2 challenge 集上收口**：42 例（21 资产 × baseline/challenge）**全量输入**上板，板端判定与数据集软件验证器 **42/42 完全一致**（baseline 21/21 过；challenge 13 过 / 8 失败，与软件同一批）。8 个失败例的失败模式全部是 **LDPC 硬判决不收敛**，不是译出错误字节。详见[来源表 §18](board/bkb220/migration-source-table.md)。
2. ~~**P3 的靶子换了**（当日已作废，见下）~~：当时把主循环节流 `PIPE_RUN_SLEEP_US` 当成头号可疑项。
   **2026-10-13 当天实测否掉了这条**：三档 200/50/0 的斜率 0.079086/0.078348/0.079057 ms/记录，
   **差异 <1%，端到端一点没快**。真正的问题是**读段上传段**（见下面「傍晚追加」），
   而它既不在 `[waiting]` 里、也不在任何一个被函数级计时的函数上——是**主循环的轮询周期**。

**板端仍未做的**：新载荷的四级逐级黄金向量；长稳 **8h**（2h 已完成）；QSPI/SD 冷启动；UART 反向；功耗（无仪器）。

**2026-10-13 下午追加**：P16 长稳 **2 h 完成**——274 轮连续判据全过、非预期 SHA 0、间隔插入的 90 例畸变包注入全部恢复，见[长稳 benchmark](benchmarks/bkb220-p16-soak-2h.md)。`score_min=67` 已在 R0.83 全量档经判据轮验过（见 [B2 探针](benchmarks/bkb220-p16-fault-probes.md)）；P16 对 v1/v2 新数据集已由 §18.5 关闭。

**2026-10-13 傍晚追加：上传优化已转正；无睡眠派生实验包的读段上传段快了约 22×。**

底稿把上传段（3.916 s，占整轮 29.5%）的原因猜成「逐批 ACK 停等」。**实测把这个猜测否掉了**：
批次从 208 降到 52，上传耗时只降 6%。真正的限速器是**两条**，都在 PS 侧但**都不在底稿的函数级预算里**：

1. **`NO_SYS=1` 下每圈只收一帧**：BSP 是裸机 lwIP，而 Xilinx `xemacpsif_input()` 那个取包
   `while (1)` 整个包在 `#if !NO_SYS` 里——**一次 `xemacif_input()` 只取一个以太帧**。
   上传阶段流水线还没起来，`main()` 走「空闲」那一支并固定 `usleep(1000)`，
   于是吞吐 ≈ 1514 B ÷ 1.18 ms ≈ 1.28 MB/s，与实测 8.4 Mbps 吻合。
2. **`TCP_WND` 只有 2048**（BSP `lwipopts.h`）：放大到 32768 才能让发送方一直有帧可发。

该数值来自 `TCP_WND=32768`、`PIPE_IDLE_SLEEP_US=0` 的派生实验包，不是当前正式配置。正式转正包已将窗口设为 32768、默认空闲取帧设为 `PIPE_IDLE_FETCH_N=16`，板测上传为 **0.40 s**（见[转正记录](benchmarks/bkb220-p16-upload-promotion.md)）；0.19 s 保留为无睡眠实验值。
**该派生包的四档 × 3 次实验结果**（2048/8192/32768/全量，参考包与实验包各烧一次背靠背）：
参考包恒 **7.76～7.80 Mbps**，新包 **125～177 Mbps**，全量档中位 **4.27 → 0.19 s（≈22×）**。
全量 `--runs 3` 判据轮 SHA **逐位不变**（`fcd0cf90…b1f2c3`），`--strict-artifacts` G3 PASS。

**整轮墙钟 14.25 → 10.18 s（−28.6%）**；但 `t_result` 一动没动（同小时 9.34 → 9.33 s），
**对 CPU 的倍率本轮没有改变**——真要缩短与 16 线程 CPU 的距离只能动 PL（见下）。
⚠️ **同一天内 `t_result` 会漂移**（今晨 8.68 s vs 同小时 9.34 s，+7.5%），
**任何 A/B 必须同小时重测参考包**，否则会把结论做反。详见
[上传段 benchmark](benchmarks/bkb220-p16-speed-a-upload.md)。

**P3 剩余方向**：PL 侧（板端 9.33 s 里 PL 约 8.2 s）。

> **勘误（2026-10-14）**：本段上一版写「K=2 整机 route 也已通过（**35,285 LUT、WNS +0.978 ns**）」，
> **那是已作废的构建**——参数当时没进 HDL，K=2 与 K=4 两次实际都编成了 K=1（两次产物逐字节相同）。
> 有效的 K=2 整机是 **35,702 LUT、WNS +0.313 ns**。

**K 已定：K=2，并已于 2026-10-14 写死。** 判据是器件容量而非价值判断——
K=4 整机实测 63,246 LUT（合计）/ 54,164（组合）**超过 XC7Z020 的 53,200**，`place_design` 硬失败；
K=2 通过（35,702 LUT、WNS +0.313 / WHS +0.036、失败端点 0、DRC 0 Error）。
K 已由 `parameter` 改为 RTL 内 `localparam BASES_PER_CYCLE = 2`，全部构建期传参通道撤销。

**K=2 功能判据**（2026-10-14）：

- `tb_dna_stage1_p16_equivalence.v` 以「生产 P4 + 独立符号滑窗 oracle」对 P16 做
  score/pos/cw **三重逐位**比对，**CL6 通过**；且写死前后**周期数逐位相同**
  （258,875 / 95,873）⇒ 写死未改变行为。
- **全量回归 `bash tools/run_sim.sh all`：25 项通过、0 项失败**（日志 `logs/iverilog/`，`logs/` 已忽略）。
  覆盖 `srpe_batch` / `4way` / `pway`(p4+p16) / `dna_stage1`(等价+接口) / `accelerator_core_4way` /
  `ingress` / `dna_axil` / `voter` / 主机单元测试 / 三顶层语法检查。
- **LC50 生产几何判据也已通过**（`stage1_production_full` 的等价用例）：
  同样是「生产 P4 + 独立 oracle」score/pos/cw 三重逐位，两轮均 PASS；
  周期比 **5.21×**（1,680,956 → 322,507）。**该倍数与 LC6 的 2.70× 不是同一口径**，
  因为 P4 的周期随 NUM_LC 扩张更快。
  同一入口的第二个用例 `dna_stage1_p16_interface`（AXI-Lite + S_AXIS + M_AXIS 背压）
  在 LC50 也通过（`P4cycles=1674229 / P16cycles=315778`）。
  **`stage1_production_full` 整轮 3 项通过 / 0 项失败。**
- 打包门禁已按约定**显式替换**（旧的 P14 字节等价 → 源码 SHA 冻结 + 行为判据）并 PASS。
- **整机重建**：35,702 LUT / RAMB36 48 / DSP 5、WNS +0.313 / WHS +0.036、
  **0 失败端点（共 88,748）、DRC 0 Error**，与写死前逐项相同。
- **板端验收 G3 PASS（2026-10-14，生产几何全量）**：103,616 条记录、`score_min=67`，
  判据 `fcd0cf90…b1f2c3` **逐位相同**；载荷回传段实测 **6.06 s**。
  包 `hw/build/bkb220-p16-k2freeze-20261014T000848Z-board-migrate`。
  ⚠️ K=1 的 9.33 s 是异时段值，**不得据此算加速比**（见下「测量纪律」）。
  同小时背靠背 A/B 已做：K=1 参照包 **9.08 s** → K=2 **6.06 s**，**快 1.50×**。
  **K=2 已并入 main**（`main == origin/main == b9813c3`）。

**片上 LDPC：L0–L7 已跑完，但 L7 的结论是「集成漏做解交织」——这一版在板上从不真正纠错。**
接手入口见[片上 LDPC 交接](reference/ldpc-onchip-handoff-2026-10-14.md)，集成记录见
[L6 集成](benchmarks/ldpc-onchip-integration.md)。
L0（矩阵身份）、L1（定点正确性）**已证**；L4 译码器**对黄金逐位相同**、OOC 布线后 WNS +0.444 ns；
L5 内层优化**累计周期 4.42×**；L6 已把 AXI 包装 IP 并入整机
（**整机布线后 WNS +0.334 ns**，`ldpc_decoder_0` 855 LUT/41 BRAM）并交付可构建的软件包。
**定位是集成度不是提速**——性能上已被证伪（重叠后稳态省 ≈0）。
**L7 已上板（2026-10-14）**，见[L7 记录](benchmarks/ldpc-onchip-l7-board.md)：
G3 载荷 SHA `fcd0cf90…` **逐位相同**、四级取证 PASS，
但串口是 `converged=0 iterations=-1 error=1` —— **走的是兜底**（软件保留了 Stage3 原码字），
所以 **G3 判的是「兜底没搞坏东西」，不是「译码成功」；收敛路径在板端一次都没被验证过**。

**根因已双向验证：L6 漏做解交织。** RTL 被验的输入是自然序
（`logs/ldpc/golden/build_golden.py` 里 `natural=L.deinterleave(rx,perm)`），
板端喂的是结果缓冲原样 `rx`，**31,958/64,800 位不同**。双臂仿真（本轮板端真实输入）：
臂A=rx → 50 轮不收敛、20,802,990 周期（逐项复现板上）；臂B=natural → **5 轮收敛**，
与主机 `tools/ldpc_decode.py` 的「起始失败校验 332，5 轮收敛」完全一致。
⇒ **核是对的，集成是错的**；AXI 边界的**字内位序没有问题**（原列为疑点的这一条已排除）。
**不能靠把 B_t 表列号重标号白嫖**——`perm⁻¹` 在信息列分组上不保持等差，会毁掉 p=1 的仿射地址算术。

同小时背靠背 A/B（19:03 LDPC 包 / 19:09 冻结 K=2 参考包）：板端流水线 **724 → 890 ms**、
`t_result` **0.78 → 0.94 s**，即 **+166 ms / +22.9%**，且是**永远走兜底**时付的。
**Stage1 未回退**已确认：两包 65/107/45/65/73 ms 逐项相同到毫秒。

**置换已在 PS 侧补上并复测通过**（2026-10-14）：`sw/app/ldpc_perm.c` + 由
`tools/gen_ldpc_perm_table.py` 生成的 `inv` 表（126.6 KiB 进 `.rodata`），
**不动 `hw/ip/`，比特流与整机 WNS 保值**。
板上串口：**`converged=1 iterations=5`**（与臂 B 仿真逐项一致），
`deinterleaved in 2 ms` / `reinterleaved in 1 ms`。
主机侧签名由 `起始失败校验 332，5 轮收敛` 变为 **`起始失败校验 0，0 轮收敛`**。

⚠️ **勘误（同日）**：早先那句「片上 LDPC 从 +166 ms 降到 +1 ms」是**对照包选错**得出的——
当时用的 `upload-promoted` 来自 2026-10-12 构建（`hardware_build_config.txt` 记 WNS +0.617），
是 **K 参数化之前**的 P16，把 **K=1→K=2** 与 **LDPC 有无** 混在一起了。
**按真基线 `bkb220-p16-k2freeze-20261014T000848Z`（K=2、无 LDPC）重做**：

| | K | 片上 LDPC | 默认档 板端 | 全量档 `t_result` |
| --- | :-: | :-: | ---: | ---: |
| `upload-promoted`（K 参数化之前） | 1 | 无 | 724 ms | 8.90 s |
| `k2freeze`（真基线） | 2 | 无 | **602 ms** | **5.89 s** |
| `k2-ldpc-perm`（当前主线） | 2 | 有 | 725 ms | 6.06 s |

⇒ **K 与 LDPC 两个因素各自干净**：K=1→K=2 默认档 −17%、全量档 **−34%**；
**片上 LDPC 的净代价 ≈ +120 ms/任务，与数据量基本无关**（默认档 +123 / 全量档 +118）；
修复本身（50 轮→4~5 轮）省下约 165 ms。
可归因部分只有 ≈50 ms（PS 状态机 17 + 置换 3 + PL 译码 29~35），**剩下 ≈70 ms 未归因**。
置换的正确性由 `tools/test_ldpc_perm.sh` 在 **x86 上逐位核验**（含板端真实样本与往返），
**不靠上板试错**。

**仍未做**：修复后的收敛只在**单一 G3 样本**上验证过；修复后的**不收敛路径**未再复测；
L4 的 8 收敛/6 不收敛分布在板上没复现。

**K=4 已关闭**（不是「未完成」）。Stage1 优化整体仍在进行；详见
[多碱基探针报告](benchmarks/stage1-multibase-ooc-probe.md)及[speed交接](reference/speed-handoff-2026-10-13.md)。

### 2026-10-14 当日其余进展

详见[台账](09-evidence-ledger.md)与各 benchmark。**每条都标了它是实测还是推导。**

- **Stage1 压时间第一步已落地并上板验收**（[分解与方案](benchmarks/stage1-block-overhead-plan.md)）：
  `S_PREFILL` 只发能落进窗口的地址，每块 **101→94 拍**（**块内 FSM 状态驻留口径**）；
  整机 **LUT −299**；
  ⚠️ **2026-10-15 分母更正**：实测归一化后每块实际硬件成本是 **116.82 拍**，
  故那 7 拍占 Stage1 硬件时间的 `7/123.82 ≈ 5.7%`，**不是 `7/101 = 6.9%`**（见下文 §Stage1 硬件周期实测）；
  **板端全量档 `[PIPE] total` 6,259 → 5,970 ms（−289 ms / −4.6%）**，判据 SHA **逐位不变**。
  两个独立验收员（功能等价 / 时序资源）各自复现了数字，并把整轮折算**更正为 −4.50%**
  （我原算的 −4.8% 是把 `t_result` 当成了整轮）。
  ⚠️ **那次板测的 bit（`8d17d17e…`）不覆盖当前源码**——它的 `source_manifest.json` 记的是
  `srpe_batch_pway.v = 8c9b26f4…`（声明顺序修复**之前**）与 voter `9decc377…`（Stage2 **之前**）。
  详见下面「整合构建」一条与 `logs/verify/prefillfix-provenance.md`。
- **Stage2 投票循环流水化已实现（模块级）**：周期 **2.69×（−62.86%）**，差分仿真 **0 不符**，
  OOC WNS 仍 **+2.832 ns**。**未上板**；折算整轮全量约 −7.5%（**推导**）。
  顺带发现旧 RTL 的 **+511 饱和缺陷**（跨 +511 写成 `10'h200`），本提交**保留旧行为**。
- **客户端架构变更**：PC 端**彻底不译码**，改为只校验 syndrome；校验不过即**判失败**。
  界面同步（含 3 个行为回归的修复）。**UART 反向（PC→PS）实测通过**，两个方向至此都通。
- **三个周期探针**：**Stage3 到顶**（81,000→64,800 bit 只用 2,054 拍，气泡全消也只省 1.41%）；
  **Stage2 是最大未开垦项**；**PS 的旧「194 ms 可直接归因」在新固件上复核不了**
  （当前 UART 留证**没有 `[PROF]` 分项**）。
- **G3 三层判据更正并落地**：`tools/board/g3_judge.py` + `tools/run_g3.sh --offline-recheck`。
  裁决口径由"仅架构判据决定"**更正为"架构与系统都须过"**（原写法在"合法但错误的码字"上
  比旧判据更宽）。三个方向离线实测 + 今日 13 份留证复算，详见
  [07 §5a](07-board-build-and-acceptance.md) 与 [09 台账](09-evidence-ledger.md)。
- **代码质量复排（P5）已出清单**：[复排清单](reference/code-quality-review-2026-10-14.md)。
  逐条复核了上一轮，给出新一轮问题（测试下限把 skip 计入、客户端阈值静默回落、
  TB 注释指向旧副本等），并明确列出**动不得**的项与其理由。**本轮未改任何代码**；
  低风险那一档已另派修复任务，其余等用户批准或板卡窗口。
- **提交材料**：[复现入口](submission/reproduce-artifacts.md)、
  [LLM 协作归档](submission/llm-collaboration/)、[合规核查记录](submission/compliance-notes.md)。

- **整合构建已出（含今日两处改动，待上板）**：`bkb220-p16-k2-ldpc-prefillfix-20261014T151544Z-board-migrate`，
  bit `14c43aaa…`，route 后 **WNS +0.147 / WHS +0.036 ns，setup/hold 失败端点均为 0**，
  布线 error 0、DRC error 0，Slice LUT 36,282 / FF 37,627，工具功耗估算 2.134 W。
   ⚠️ **目录名 `prefillfix` 说了假话**：它同时含 Stage2（voter 22:47 改、构建 23:15:44 启动）。
   一次独立验收员按层级表核清了资源归属（Stage1 只 −2 LUT、voter 整机口径 −9 LUT/+44 FF、
   另有 −4 无法归因），并从构建工程 `ipshared/` 的副本**逐字节证实**两份改动过的 RTL 就是当前源码。
   ⚠️ **三代 WNS +0.334 → +0.233 → +0.147 ns 单调收窄**（周期余量 3.34% → 2.33% → **1.47%**），
   全部仍 MET，但这是**三份不同构建之间的相关趋势、不是单变量实验**，**不得归因到某一次改动**。

### 2026-10-15 上板结果：整合包 G3 通过，全量档 −7.5%

板卡恢复后跑完两轮（留证 `g3_runs/20261015T021106Z` 默认档、`20261015T021613Z` 全量档），
完整记录见 [`logs/board/stage2-prefill-g3-20261015.md`](../logs/board/stage2-prefill-g3-20261015.md)。

- **三层判据都过**（两个档位）：架构 syndrome **0/10800**、系统载荷 SHA 命中、
  主机译码 **0 轮**（板端真收敛）、**PC 兜底未发生**。⇒ **当前源码已由板测覆盖**，
  补上了上面那条"板测 bit 不覆盖当前源码"的欠账。
- **全量档 `[PIPE] total` 5,970 → 5,522 ms（−448 ms / −7.5%）**，斜率 79.1 → **53.3 µs/记录**。
  当初"折算整轮约 −7.5%"是推导，**板端实测就是 −7.5%**。
- ⚠️ **默认档分辨不出这个收益**（714 → 710 ms）：默认档下 voter 硬件只占约 30/710 ms。
  比 Stage2 的收益**必须用全量档**。
- ⚠️ 与 `prefillopt` 之间差两处改动，**无法拆分归因**；但声明顺序修复是净表等价，
  故这 −7.5% 基本可归于 Stage2。

**同日一并纠正的一处误读**：main 见全量档 `[waiting]` 占 5,522 ms 的 87%，
误判"下一个大项在 PS 侧"。查清后：`[waiting]` 是**残差**且恒等于
`callbacks × PIPE_RUN_SLEEP_US`（7 份留证误差 +0.3%~+0.5%），即**有意的 200 µs 节流**，
**不是 lwIP 空等**（打印标签是错的）；且方向早有反证——P3 三变体端到端只差 0.06%。
详见 [09 台账](09-evidence-ledger.md) 末两行。

### 2026-10-15 按阶段归因：**Stage1 占全量档 89.5%**

纯固件仪表化包（bit 与上一份逐字节相同，只改 `sw/app/echo.c`）上板两轮，三层判据均 PASS。
完整记录见 [`logs/board/stage-time-attribution-20261015.md`](../logs/board/stage-time-attribution-20261015.md)。

| 阶段 | 默认档 | **全量档** | 占比 |
| --- | ---: | ---: | ---: |
| **Stage1** | 294.6 ms | **4,938.4 ms** | **89.5%** |
| Stage2 | 194.1 ms | 363.4 ms | 6.6% |
| Stage3 | 170.2 ms | 170.2 ms | 3.1% |
| LDPC | 49.6 ms | 43.9 ms | 0.8% |
| **合计** | **708.4**（=total 708） | **5,515.9**（=total 5,516） | 差 **0.000 ms** |

- **`sum` 与 `total` 精确相等** ⇒ 这是**无残差**的归因，与此前那个把 87% 塞进
  `[waiting]` 残差桶的口径是两回事。
- **Stage1 的占比远高于此前"约 65%"的推导估计**（那个数不是实测）。
- ⚠️ **这是墙钟不是硬件周期**：Stage1 **没有**硬件周期计数器（Stage2/Stage3 有，
  核心 AXI-Lite 只有 4 个写向寄存器，且 `srpe_batch_pway.v` 的 SHA 是门禁冻结值），
  所以"4,938 ms 里硬件占多少、PS 侧流式投递占多少"**目前答不了**。
- ⚠️ **Stage3 的 170.2 ms 在两种规模下完全相同** ⇒ 与数据量无关的固定开销，
  且其 `DECODER_PREP`(65) / `DONE_STAGE3`(73) 都是**单次命中**就要这么多。**下一个可疑项。**

**同日发现并修复的软件构建确定性缺陷**：旧入口在 XSCT `app create` 成功时以模板默认
`-O0` 编 app，遇到时有时无的 `Socket create error` 时则用手写 Makefile 的 `-O2`。
现入口仍由 Vitis 2022.2 XSCT 生成平台/BSP/FSBL，但通过 `build_app=0` 跳过 XSCT app
create/build；app 一律由 `write_fallback_makefile` 路径以固定 `-O2` 编译，并将优化级别和
CFLAGS 写入 `reports/software_build_summary.md` 与 `manifest.json`。
连续两次完整重建均通过，110 条源码清单逐项相同；`echo.c` 编译行除输出目录外逐字一致。
新包 bit SHA-256 为 `14c43aaa93fab3a9d2e244045f3af2fb95f8cbb09c8b10889a8cb28c04a3383f`；
`nm` 显示新包为 712 个 ELF 符号，与同源 `-O2` stagetime 包一致，而非旧 `-O0` 包的 883 个；
两次 SHA 自检与 G3 strict plan-only 均通过。**没有触板**，不据此声称板端验收或性能变化。
旧包测时中 `-O0` 5,522 ms vs `-O2` 5,516 ms，差 0.13%；同级别 `prefillopt` (`-O2`)
5,970 → 5,516 = **−7.6%**，故 −7.5% 站得住。改动前分析见
[`logs/dev/software-build-optimization-nondeterminism.md`](../logs/dev/software-build-optimization-nondeterminism.md)，
实现与复建留证见 [`logs/dev/build-determinism.md`](../logs/dev/build-determinism.md)。

### 2026-10-15 Stage1 硬件周期实测：**116.82 拍/块，模型少算 24%**

给 Stage1 装了硬件周期计数器（6 项，经 DNA AXI-Lite 读回）后上板全量档，**三层判据 PASS**。
完整记录见 [`logs/board/stage1-hardware-cycles-20261015.md`](../logs/board/stage1-hardware-cycles-20261015.md)。

板端读数：`total 482,301,719 cyc (4823.017 ms), blocks 4,128,450, batches 1,619`。

| 项 | 实测拍/块 | 模型 | |
| --- | ---: | ---: | --- |
| `prefill` | **11.0000** | 11 | ✅ 逐拍吻合 |
| `run` | **75.0000** | 75 | ✅ 逐拍吻合 |
| `tree`(UPD1+UPD2) | **6.0000** | 6 | ✅ 逐拍吻合 |
| **`total`** | **116.8239** | **94** | ❌ **高 24.3%** |
| 残差(total−三段) | 24.82 | 2 | ❌ 完全未建模 |

- **块数 4,128,450 ÷ 1,619 批 = 2,550.0**，与模型完全相同。
- ⇒ **模型三段分项精确，但总量少算 22.82 拍/块 = 942 ms**（≈全量档端到端 5,531 ms 的 **17%**）。
  **`94 拍/块` 这条一直被用来做 Stage1 优化分母的基准本身不完整。**
- ⚠️ **"可回收"尚未证明**：这 22.8 拍/块（其中 **`S_LOAD_R` 与 `S_EMIT*` 占 932.5 ms**，
  其余零散小状态 9.7 ms——见 [`logs/dev/stage1-overlap-study.md`](../logs/dev/stage1-overlap-study.md)）
  可能是真气泡，也可能是每块必做之事。
  **先按状态定位，再谈可回收性**——不要重蹈 `[waiting]` 那次"见残差就当优化空间"的错。
- **排除**了"批间没接上"：硬件 4,823.0 ms vs 墙钟跨度 4,953.8 ms ⇒ **占用率 97.4%**，
  批间空隙仅 130.8 ms（2.6%）。**是硬件在忙，不是 PS 在等。**
- **另**：Stage3 硬件仅 **0.022 ms**，而墙钟跨度 **170.188 ms** ⇒ 那 170 ms **99.99% 是 PS 侧**。

**逐状态分解（仿真侧，未改 RTL）**：入口 `bash tools/run_sim.sh stage1_state_split`。
LC50/单批 `total=297,901`、`blocks=2,550`、逐状态之和 297,901、**差额 0**；
**仿真 116.82392157 拍/块 vs 板端 116.82392157，差 0.0000** ⇒ 分解可采信
（这同时验证了此前所有基于仿真的等价证据）。

那 **22.82 未建模拍/块**由两块各占一半：

| 状态 | 次数/批 | 拍/块 | 每次 | 板端折算 |
| --- | ---: | ---: | ---: | ---: |
| **`S_LOAD_R`** | 64（每记录一次） | **11.2941** | **450 拍** | ≈466 ms |
| **`S_EMIT`+`S_EMIT2`+`S_EMIT_W`** | **9,600**（每碱基位一次） | **11.2941** | 3 拍（各 1） | ≈466 ms |

⇒ **两块都是必要工作**（装载参考 / 发出结果），**不是浪费，是模型漏写**。
⚠️ **但不等于可回收**：它们串行在 FSM 里，能否与 `S_RUN` 重叠（预取/流水化）
是**尚未评估的 RTL 设计任务**。
⚠️ **`94 拍/块` 这条基准应退役**（真实 116.82）："101→94 拍 = −6.9%" 的分母是错的，
真实占比 `7/123.82 ≈ 5.7%`——**相关文档的口径需要改**。

⚠️ **代价**：6 个计数器花 **+624 LUT / +149 FF**，hold 余量 **+0.036 → +0.016 ns**。
建议测完做成**默认关闭的编译期选项**，发布制品不带。

### 2026-10-15 串口打印的实测代价：**367 ms（−6.66%）**

由 Stage3 那个 170 ms 怪现象追出来的：全量档 UART 共 **9,262 字节 ⇒ 线速 804 ms = 端到端 14.6%**
（`xil_printf` 在单线程主循环里忙等 TX FIFO）。用 `build_sw_variant.sh` 派生安静变体做
**交替 A/B（3 轮配对，PL bit 逐字节相同、只差 `-DFW_DIAG_VERBOSE=0`）**：

| 轮 | 啰嗦 | 安静 | 差 |
| --- | ---: | ---: | ---: |
| 1 / 2 / 3 | 5,515 ms | 5,148 ms | **−367 ms**（三轮完全一致） |

六轮 **G3 三层判据全 PASS**。⇒ **打印值 367 ms**。
⚠️ **去掉的 780 ms 里只有 367 ms（47%）在关键路径上**，其余被 PL 等待吸收——
**不能拿 804 ms 当收益**。差值出现在正确位置：节流底几乎没动（4,828 → 4,847 ms），
掉的是"节流之外"那段（687 → 301 ms）。

⚠️ **出厂应取"分级静默"而不是全静默**：全静默把 `[ERROR]`/`[WARNING]` 也一并抑制了。
已实现 `FW_DIAG_LEVEL` 三档（2=啰嗦/1=分级/0=全静默）并**再次实测**：
分级版 `[PIPE] total` = **5,148 ms**，与全静默版**逐毫秒相同**、串口字节也相同（275 B）——
因为**成功路径上不打印任何错误**。⇒ **保留错误/告警是免费的，那 367 ms 全额拿到、
排障能力零损失。** 六轮 G3 三层判据全 PASS。

**副产品**：`[PIPE] total` 在同一配置内**逐毫秒确定**（同配置三次全同），
这让此前跨包单次相减的比较（如 Stage2 的 −7.5%）可信度一并提高。

### 2026-10-15 发布候选与验收（当日后续）

**发布候选 = bit `81229e23…` + 分级静默固件**（Stage1 计数器关闭、`FW_DIAG_LEVEL=1`）。

- **板端三层 G3**：PASS（架构 syndrome 0/10800、系统载荷 SHA 命中、PC 兜底未发生），
  留证 `g3_runs/20261015T142419Z`，**全量档 `[PIPE] total` = 5,148 ms**、串口输出 275 字节。
- **多载荷泛化回归**（`tools/run_multi_payload_regression.py --mode board --extended`）：
  **6/7 PASS**，与既有基线**逐项一致**；唯一 FAIL 是 `D1_random_entropy@60`——
  那是文档要求"必须忠实重现"的出厂门限已知边界，不是新问题。载荷 SHA 全部 100% 吻合。
  见 [`logs/board/multi-payload-release-regression-20261015.md`](../logs/board/multi-payload-release-regression-20261015.md)。
- **8 h 长稳**：已跑 **50 轮连续 PASS**（每轮 103,616 条、`result_s ≈ 5.05 s`、
  判据 SHA 每轮命中），**后按电源计划中止**，未跑满 8 小时。
  ⚠️ 因此"8 h 长稳"**仍未完成**。见 `logs/soak/release-8h/`。
- **全天性能账（同 `-O2` 口径、同板背靠背）**：5,970 ms（起点）→ **5,515**（+Stage2 流水化，
  −455 / −7.6%）→ **5,148**（+打印分级，−367 / −6.66%），**合计 −822 ms ≈ −13.8%**；
  打印那一步用**交替 A/B 三轮配对**验证，每轮差值完全相同。

**同日工具侧修复**：四级取证区分「无基准→`UNVERIFIED`」与「真不符→FAIL」（R0.83 判据不变）；
多载荷回归不再覆盖 `tests/datasets/` 下已提交留证；`g3_soak.py` 补 `--hw-server` 透传
并修正判据 SHA 解析（旧措辞正则已失效）。

⚠️ **仍需你留意的一条尾巴**：`run_g3.sh` 仍把检查器的「退出码 3 = 未取证」归为通用 FAIL——
误报的**理由**对了，但**红还在**，需后续让运行器认这个码。

---

## 2026-10-16 开工计划与当日执行结果（用户 2026-10-15 夜指定顺序）

**用户指定的顺序：两个可选性能项先做，8 h 长稳往后推。**
**→ 当日结果：② 已完成并上板验收通过（−50 ms）；① 仿真实测可省 ≈731 ms，但它那个实现经整机评估**装不下**（`place_design` 硬失败），该实现判死；③ 已启动。逐条见文末「当日执行结果」。**

### 第 1 项：双缓冲原型的 **LC50 正式测量**（离线仿真，不占板子）

- 状态：原型与 TB 已入库（`hw/experimental/srpe_batch_pway_dbuf_proto.v` +
  `hw/sim/ip_tb/tb_srpe_batch_pway_dbuf_proto.v`，LC6 冒烟已过：12 条 `cw/pos/score` 全等）。
  昨夜按用户要求**中止了正在跑的 LC50 仿真**（那时已编译通过、刚开始跑）。
- **一行重启**：
  ```
  mkdir -p logs/iverilog/dbuf-proto-lc50 && iverilog -g2005 -DCFG_NUM_LC=50 -DCFG_BATCH=64 \
    -DCFG_BATCHES=3 -o logs/iverilog/dbuf-proto-lc50/tb_dbuf \
    hw/experimental/srpe_batch_pway_dbuf_proto.v \
    hw/ip/Dna_accelerator_core_1_0/hdl/srpe_batch_pway.v \
    hw/sim/ip_tb/tb_srpe_batch_pway_dbuf_proto.v && \
  vvp logs/iverilog/dbuf-proto-lc50/tb_dbuf | tee logs/iverilog/dbuf-proto-lc50/run.log
  ```
- **要看什么**：装载/发放**实际隐藏在 `S_RUN` 窗口内的周期数与占比**，对照理论上限 **932.5 ms**。
  ⚠️ 预期有固定损失：首批装载与末批发放无法隐藏（各 28,800 拍 ≈ 0.288 ms，合计约 0.576 ms）。
- ⚠️ **测出来之后也不要直接搬进生产件**：发布候选 **WHS 只有 +21 ps**，
  必须先跑 100 MHz 整机 route 看 hold 与失败端点，再谈板测。

### 第 2 项：Stage3 的固定 **50 ms 等待**（要板子）

- 状态：昨夜派出的固件 agent 在探索阶段被**主动取消**，**未留任何改动**（工作树干净）。
  需要重新派。
- **改法方向**（只读调查给的，红线已明确）：把 `PIPE_DONE_STAGE3` 里的**无条件 `usleep(50ms)`**
  改成**有界地轮询 `STATUS.IDLE`**；**不要**退回"按轮询次数超时"（`docs/03` P13 有教训），
  且**必须保留安全下限**——IDLE 一直不置位时仍等满原时长并按原路径处理。
- **三样不许动**：`START` 后的 100 µs 采样等待、`START 只写一次 1` 的 B27 时序、
  主循环 `PIPE_RUN_SLEEP_US` 节流值。
- 顺手：DONE_STAGE3 里那处**重复的输出缓存失效**（确认冗余后合成一次）。
- **验收**：出包 → 上板 → **G3 三层判据仍须 PASS**、真实省下多少、连续任务下 Decoder 是否仍可靠。
  单项收益约 **0.9%**，便宜但不白拿。

### 第 3 项：**8 h 长稳跑满**

- 昨夜跑过 **50 轮连续 PASS**（每轮 103,616 条、`result_s ≈ 5.05 s`、判据 SHA 每轮命中），
  按电源计划中止 ⇒ **仍不算完成**。跑满才入账。
- 命令模板见 `logs/soak/release-8h/`（注意 `--hw-server TCP:127.0.0.1:3132` 与
  先确认板上就是本包再 `--skip-boot`）。

---

### 2026-10-16 当日执行结果

#### ② Stage3 固定 50 ms → 有界墙钟轮询 IDLE：**完成，上板验收通过**

改法（`sw/app/stage3_decoder.c`，与 `sw/workspace/dna_lwip_app_b27/src/` 逐字节同步）：
`PIPE_DONE_STAGE3` 里清零 START/IN_BEATS/OUT_BEATS 之后，把**无条件 `usleep(50000)`**
换成**按墙钟**最多等 50 ms、每 1 ms 读一次 `STATUS.IDLE`；IDLE 置位即继续，直到截止点
仍未置位则再采样一次并**照原 dummy-run 路径**继续。**不是按轮询次数超时**（P13 教训）。
顺手删掉 `DONE_STAGE3` 里那次**重复**的输出缓存失效（`validate_decoder_written_beats()`
入口第一行就是同范围同一次失效，中间无写入）。三条红线未动。

**安全性论证（main 独立核验 RTL，非引用子 Agent 结论）**：
`desparsification_decoder_v1_0.v` 里 `STATUS={30'd0,done,idle}`（bit0=idle）；
`idle_s <= ~b2`（`busy` 打两拍取反）；`busy` **只在**最后一笔 `M00_AXI_BVALID`
（`WR_RESP && w_left==0`）清除；而该模块**自己**的"能否重启"判据
`core_active_m = busy | (rd_state==RD_ADDR) | (rd_state==RD_DATA)` 的注释写明
「**RD_DONE 时所有读突发都已收完，busy=0 时最后一个 B 也已回来，此时重启才是安全的**」。
`DONE_STAGE3` 在 DONE 之后（已过 RD_DONE）⇒ **IDLE 正是 RTL 自己认可的可推进条件**。

**上板 A/B（同板、同 bit、背靠背）**：

| 轮 | `[PIPE] total` | G3 三层 |
| --- | ---: | --- |
| 发布包 ×3（固定 50 ms） | 5148 / 5148 / 5149 ms | PASS ×3 |
| 变体 ×2（有界轮询） | 5098 / 5099 ms | PASS ×2 |

**净收益 −49 ~ −50 ms（−0.96%）**，基线自身抖动 ±1 ms，两档无重叠；
`steps`/`callbacks`/串口字节数**逐字不变**。架构判据 5/5 PASS（syndrome 全零 0/10800）、
系统判据 5/5 PASS（SHA `fcd0cf90…`）。详细留证见 `logs/board/stage3-wait-ab-20261016.md`。

**已出推广包**（bit 与发布候选逐字节相同 `81229e23…`）：
`hw/build/bkb220-p16-k2-ldpc-release-stage3poll-20261016T000308Z-board-migrate`
（ELF 裸 `383fb2cd…` / strip-debug `b967585f…`）。该包已单独跑过
**G3 三层 PASS（5098 ms）** + **多载荷回归 6/7，逐项与发布包基线一致**
（含已知高熵边界 `D1_random_entropy@60` 的 2671 误码）。回归的回传**没有**再覆盖
`tests/datasets/` 下已提交留证（`--out-dir` 修复生效）。

⚠️ **收益口径**：这是**同板同小时**的差值，不得外推；`[PIPE] total` 是板端打印值，
**不得反推周期或功耗**（本次未测功耗、未接周期计数器）。

⚠️ **未覆盖**：本改动**依赖** `DONE_STAGE3` 已确认输出完成；`STATUS.IDLE` 只反映**写引擎**
`busy`，不是所有内部子状态的汇总（那个更全的 `core_active_m` 没接到 STATUS 上）。
单次任务的 5 轮在上表；**连续多任务**可靠性由多载荷回归与 8 h 长稳覆盖。

#### ③ 8 h 长稳：**已在推广包上启动**

板上先烧推广包并跑通 G3，再以 `--skip-boot` 起长稳（`logs/soak/release-8h-stage3poll/`）。
**跑满 8 h 墙钟才算完成**；中途不得据"轮次很多"宣布完成。

#### ① LC50 双缓冲仿真：**已出数**；随后按用户指定做的整机评估 ⇒ **该实现装不下**

**仿真结果**（`logs/iverilog/dbuf-proto-lc50/`，LC=50/BATCH=64/连续 3 批）：

- 功能 **PASS**：192/192 条 `cw/pos/score` 与单缓冲参考核逐位一致，`res_full` 背压确实施加。
- 周期：单缓冲参考 3 批 **922,193 拍** vs 双缓冲原型 **786,675 拍**，差 **135,518 拍**
  ⇒ 45,173 拍/批 = **0.452 ms/批**，× 1,619 批 ⇒ **≈731 ms**，
  即 `S_LOAD_R`+`S_EMIT*` 服务周期（932.5 ms 上限）的 **78.4%**。
- ⚠️ **TB 自带的 `hidden_load/hidden_emit` 计数器少算**（三项之和 91,954，比总额差少 43,564）——
  它只数"服务状态与 `S_RUN` 同拍"的周期。**收益必须用跨度差，不能用那两个计数器。**
- 资源直觉被推翻：双 bank 位平面只值 **≈1 个 RAMB36**（9,600→19,200 bit）。

**整机评估（2026-10-16，用户选定"先做非生产集成包的 route 评估"）⇒ 判死这个实现**：

把原型体并入 IP 源位（**只换 module 名**，其余 RTL `cmp` 逐字节相同），用**与发布候选完全
相同的参数**跑整机 ⇒ `opt_design` 后 DRC `UTLZ-1` 两条 Error，**`place_design` 拒绝运行**：
LUT as Logic 需 **62,588** / Slice LUTs 需 **63,352**，可用 53,200（发布候选整机是 36,282）。

模块级受控 OOC（`synth_check.tcl`，同脚本同器件，只差 RTL）：

| | 生产核 | 双缓冲原型 |
| --- | ---: | ---: |
| Slice LUTs | 28,461（53.5%） | **54,413（102.3%）** |
| Slice Registers | 26,516 | **68,741** |
| F7 / F8 Muxes | 288 / 142 | **9,830 / 4,156** |
| RAMB36 | 12 | 4 |

⇒ 原型**单独一个模块就超过满器件**；两路数字互相印证（54,413 + 系统其余 ≈7,821 ≈ 整机 63,352）。
要装下需把核砍到 **≤约 42,000 LUT**（相对生产核的增量从 +91% 压到约 +45%），**无证据表明做得到**。

⚠️ **判死的是"这个原型实现"，不是"双缓冲这个想法"**——原型是照语义正确写的、从未按面积写。
一条**未验证的猜想**记在留证里：装载与发放本来就争 Port B、必须互串，真需要的也许只是
"第二块位平面（≈1 RAMB36）+ bank 选择 + 小仲裁"，而不是复制两套寻址引擎。

生产核已还原（SHA `54104a96…` 与门禁 pin 三处一致），工作树干净，两项门禁 PASS。
详细留证：`logs/dev/dbuf-proto-lc50-result.md`、`logs/bench/dbuf-integration-route-20261016.md`。


#### 附带核实：**发布包在代码层面可复现**

- 发布包内自带的编译源拷贝（`workspace/dna_lwip_app/src/`）39 个 `.c/.h` 与
  `HEAD:sw/app/` **逐字节全部相同**（`stage3_decoder.c` = `e81fd93e…`）⇒ 发布包源码 = HEAD。
- **HEAD-only 重建**的 ELF strip-debug 后 = `5efeb4f5…`，**与发布候选完全相同**，`.text` 同为 254522。
- **HEAD+② 重建**与发布包**只差一个符号** `pipeline_step_stage3`（`0x4f0`→`0x540`，+80 B），
  与 `.text` 差 254522→254602 完全吻合。
- ⚠️ **判定必须用 strip-debug 后逐字节或符号表**，**不能裸比 ELF SHA**：构建带 `-g`，
  调试信息含构建路径，换个输出目录裸 SHA 就会变（`bit` 和 `FSBL` 的差异也**同样只是路径**：
  FSBL strip 后逐字节相同、569 个符号尺寸全同）。

#### ⚠️ 本次犯的错（已纠正）

为做 HEAD 复现构建，执行了 `git checkout -- <已跟踪路径> <未跟踪路径>`。
**只要有一个路径非法，git 整条命令什么都不做**——但当时 `git status` 里那行 "M" 被我
自己的提示语掩盖，误以为已回退，于是头两次"复现构建"其实**都带着 ② 的改动**。
**是符号表对比（只差一个符号）把它暴露的**。教训：回退后必须**用内容本身核验**
（哈希 / `git status` 真的为空），不能靠"我执行过了"。

#### 附带修复：WSL 侧 JTAG 通路

板子重新接入后 `hw_server` 仍是昨日 17:33 启的**陈旧实例**（libusb 句柄失效）——
能枚举 JTAG 链、但读 DAP 寄存器全空。**按 PID 精确重启**（不用 `pkill`，见 CLAUDE.md 禁令）
后恢复；`usbipd` 的 busid 本次为 **6-2**（昨日 3-2，再次印证**不得写死 busid**）。

### 再往后（板上验收欠账）

QSPI/SD 冷启动（要用户切模式）→ v2 `score_min=67` → 新载荷板端四级取证 → 功耗（要仪器）。

### 工具尾巴（**是验收口径决定，不要抢**）

`run_g3.sh` 仍把四级检查器的「退出码 3 = 未取证」归为通用 FAIL——误报的**理由**修对了、
**红还在**。改它等于改验收口径（四级取证"未取证"时 G3 总裁决该是什么），
**必须连板测一起定**，不能顺手改。

⚠️ **仍未上板/未做**：冷启动（QSPI/SD）、功耗实测、v2 `score_min=67`、
新载荷四级板端取证（D1/D2 暂无四级黄金向量；检查器对缺基准显示 `UNVERIFIED`）。
**8 h 长稳已于 2026-10-16 在推广包上启动，跑满墙钟前不计入已完成。**

1. **B2**：P16 配置守卫 7/7、断连畸变恢复 30/30、中途断网 3/3 已通过；当时使用的 `sudo iptables` 只在 `finally` 清理，操作要求见对应探针记录。
2. **C1 性能矩阵**：同板 P4/P16 六档（128/512/2048/8192/32768/full）各 ≥3 次已完成，正式结果见[性能矩阵](benchmarks/bkb220-p4-p16-performance-matrix.md)。
3. **C2 泛化**：P4/P16 与软件验证器对 v2 42 例判定三方一致；challenge 仍有 8 例 LDPC 不收敛，v2 `score_min=67` 尚未板测，新载荷四级板端取证未完成。四级工具已按目标载荷 SHA 选基准；D1/D2 没有四级黄金向量时会明确报告未取证。
4. **D 长稳**：2 h 已完成，8 h 未做，按实际墙钟验收。
5. **冻结 22 主线 → 全面优化（时间消耗+性能）→ 停止修改 → 写报告 → 最后才切 26 开发**
   （用户 2026-10-12 二度指示，**覆盖**此前「22 主线稳定后立即做 F9/26 复核」的顺序；详见 [05](05-implementation-plan.md) 的「后续总顺序」一节。要点：报告**不早于**优化完成，26 的开发与复核整体后移到优化与报告之后。）
6. **交付收尾**：冻结 writer、按路径提交推送、同步 03/05/07/09 与提示词及 Windows 镜像、各 agent 看板 `done`。

**断电前现场**：板卡已断电（用户 23:30 断电），FT4232H 归属会随机器重启变化 —— **恢复时按 `docs/07` §3a 重新确认通道**（`usbipd` 归属、`hw_server`、COM10/`ttyUSB2`）。所有制品与留证都在磁盘上（`hw/build/bkb220-*`、`D:\bkb220_board_smoke\g3_runs\*`），`logs/` 已被 .gitignore 覆盖但文件保留。

## 1c. 2026-10-12 F3 实板结果摘要

本节只记录 F3 最小启动完成时的状态；当时“CAPS 未测、整机 route/G3 未完成”的边界已由后续 P4/P16 构建与板测关闭。当前结论见本节之前的“当前目标与完成边界”及 2026-10-13 进度。

判据、原始命令与失败细节见[来源表 §9](board/bkb220/migration-source-table.md)。**已通过**：JTAG 单目标 xc7z020、`ps7_init`/`ps7_post_config` RC=0、MIO 回读与生成值逐位一致、三个 PLL 全 lock、**DDR 1024 字写读 0 不符**、**PS UART 归属实测确定**、**ENET0 的 PHY 识别与 1000BASE-T 全双工 link up**。**未测**：CAPS（需固件）、UART 反向、QSPI/SD 冷启动、bit/XSA/整机 route、DDR 板级延迟与 DQS-to-CLK、工业级器件精确料号。

**`ready` 已置 1**：依据用户 2026-10-12 明确授权「先建 P4、ENET0 留到板测再验」，且 ENET0 随后也已实测通过。该日快照当时仍缺整机 route 与 G3；两项已由后续记录关闭，迁移仍有前述剩余门禁。

**方法教训**：一度把 ENET0 判成「未通过、需原理图」，实为 main 读错 MDIO 完成标志（应读 `NETWORK_STATUS[2]`）且漏写 MDEN（`NETWORK_CONTROL` bit4）。寄存器级探测应先对着厂商驱动头文件核位定义。详见来源表 §9.6。

顺带修正一处长期误读：`0xF800010C` 是 **PLL_STATUS** 而非 DDR_PLL_CTRL（后者是 `0xF8000104`）。

## 5. 接手和证据纪律

- 起点467d90e和计划c4d7ad4是历史记录；先核对最新HEAD/main/origin，不回退覆盖已完成工作。
- 先读规范、现成05计划/07与本轮摘要，再按当前文件清单核对源码/配置/工具，从尚未完成阶段继续。旧子Agent中断与设备枚举属于交接快照，接管前确认实际状态；不重新制定计划或从零重做已有成果。
- 主Agent统一Git/文档和资源，按提示词派发独占任务、审查消息/diff/日志/哨兵；Git前所有writer停写。
- 仿真/单测/构建/制品SHA均不能替代真板；hash自洽不能证明源码因果，修改后重建受影响全套制品。
- 失败、未测、工具异常和边界失败如实保留；可对外说的话先查[09证据台账](09-evidence-ledger.md)。

本轮按计划执行的F0/F1与F2只读核查见[检查点](reference/bkb220-handoff-checkpoint-2026-10-10.md)。

文档/脚本整理收尾后，工作树固件2项及仓库卫生11项均通过；旧发布五制品SHA全部OK。

2026-10-11交接更新：主子Agent通道与模型按3ad6fbd同步到05及完整提示词；最终47项主机测试、固件2项、打包和卫生11项通过，日志在logs/host/handoff-final-20261011。当前仍是迁移准备交付，BKB220新板验收未完成。

2026-10-11后续收尾：通道规则更正提交b3c70b3已保留；main经既有host-proxy做过只读冒烟；2026-10-11 00:40 更正：改用用户新装的 codex-luna MCP（客户端 codex-cli 0.162.0-alpha.17.2）后 gpt-6-luna/max 实测可用（只读11.7s、workspace-write 34.0s，均 completed/ok/exit0/turn_completed），旧的「暂用gpt-5.6-luna」结论作废（更正提交25c3336）。新板资料、连接和真板验收状态不变。

2026-10-11全仓残留复查：现成05计划直接接管；MCP/gpt-6-luna/max与只读任务看板责任已统一，旧编号和失效链接修复。CAPS/DDR说明对齐当前129600记录容量及SE150宏，参数和算法未改。工作树固件2项、G3主机47项、公平基准契约8项、打包及卫生检查通过；证据在logs/host/current-residue-20261011。归档20份、冻结黄金、旧发布五制品和保留资产哈希均核验。旧XSim源SHA继续指向当时输入快照，当前仅注释变化的等价证据另存，没有重录manifest或新板验收。
