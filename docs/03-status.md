# 03 · 当前状态与交接

更新：2026-10-12。本文件合并当前状态与原10交接摘要；旧完整状态/审计留在[归档索引](archive/history/2026/pre-bkb220-handoff-2026-10-10/README.md)。接手先读[05执行计划](05-implementation-plan.md)和[主Agent提示词](agent-prompts/main.md)，板级细节见[07](07-board-build-and-acceptance.md)。**2026-10-10/11 的「新板未到货、只见蓝牙 COM3/COM4、无 FTDI/JTAG」设备枚举已作废**，以本文件 §1a 的 2026-10-12 实测为准。

## 1a. 2026-10-12 新板现场实测（取代此前交接快照）

BKB220 已到货并连接，main 已在 JTAG 上核实：

| 事实 | 证据 |
|---|---|
| 器件 **xc7z020**，IDCODE `0x23727093` | JTAG 链 `Xilinx HW-Z1-ZCU104 FT4232H 15051A` → `arm_dap (4ba00477)` → `xc7z020`；手册 p.5-6 写 XC7Z020-2CLG400I |
| 板载 **FT4232HL** 桥，无需外置下载器 | 手册 p.7；三串口 + JTAG 与手册 p.16「一路 PL、一路 PS 加 JTAG」相符 |
| 串口：通道 A=JTAG，B/C/D=三串口 | Windows 为 COM9/10/11；直通 WSL 后 `/dev/ttyUSB0`=JTAG、`1/2/3`=串口。**哪个是 PS UART 仍未确定** |
| 网口：ASIX USB 千兆网卡在 Windows 侧 `192.168.1.100/24`，链路 1Gbps | 已确认网线是**板子直连该 ASIX 网卡**。2026-10-12 经 JTAG 用 MDIO 实测：PHY = **Realtek RTL8211E**（OUI 0x001CC9），自协商完成、**1000BASE-T 全双工 link up**，与 1Gbps 互相印证。板端仍尚未发过 TCP 包（ReceivedBytes=0，属正常：还没跑固件） |
| `BOOT_MODE` 0xF800025C = `0` | **JTAG 启动模式**；`DDR_PLL_CTRL=0x3F`（DDR PLL 掉电）、`FPGA0_CLK_CTRL` bit0=0、`GEM0_NETWORK_CONTROL=0`、`UART0/1_CTRL=0x128` → PS 是干净的 JTAG 待机态，只有 BootROM 在跑 |
| **PS_CLK = 33.333 MHz** | 由 `IO_PLL_CTRL` FBDIV=26 推出 IO PLL=433.33 MHz，且 BootROM 能正常执行。属推导+寄存器证据，非厂商书面确认 |
| 手册给出的可采信规格 | DDR3 **两片 Micron MT41K256M16TW-107、32bit、1GB、最高 533MHz/1066Mbps**（p.9-10，与旧板单颗 16bit MT41J256M16HA-125 **完全不同**）；QSPI W25Q256 32MB 在 MIO1..6（p.8-9）；启动 JTAG/QSPI/SD（p.15）；MIO0=3.3V、MIO1=1.8V、DDR=1.5V（p.8） |

**仍缺**（手册没有、不可猜）：厂商 board_files/PS7 preset、PCB 原理图、PS UART 的 MIO、ENET0 的 PHY 型号/MDIO/RGMII/复位、DDR 板级延迟与 DQS-to-CLK。PS_CLK 已由寄存器证据确定。

## 1b. 触板通道：只能走 WSL，禁止 Windows hw_server（2026-10-12 新增）

2026-10-12 用户做连接测试时 **Windows 主机蓝屏两次**（BugCheck `0x139 KERNEL_SECURITY_CHECK_FAILURE`，参数1=`0xA`；两份转储当前进程均为 `hw_server.exe`，调用栈均为 `ftdibus+0xf4d4`）。用户当日已修复并建立安全通道：

- 统一 7 个 FTDI 子设备驱动到 `2.12.36.20`；安装 usbipd-win 5.3.0。
- **把新板 USB 桥（序列号 15051，busid 4-2）直通 WSL**，Windows 不再持有该设备。
- 在 WSL 起 **Vivado 2022.2 的 `hw_server`**（`-sTCP:127.0.0.1:3132`），用 WSL `xsdb` 连接。

**操作规则（硬性）**：

1. **禁止启动 Windows 原生 hw_server**（`D:\xilinx\2026.1\Vivado\bin\unwrapped\win64.o\hw_server.exe`）——已知崩溃路径，用户已暂停。
2. 因此原计划「Windows 2026.1 负责下载/调试」在 FTDI 问题被证明根治前**不可用**；下载/调试同样走 WSL 2022.2。F9 的 26 复核需重新评估入口。
3. **杀掉 hw_server 后必须真正重新枚举 USB**（`usbipd detach` + `attach`，确认设备号变化）才能再取到 `arm_dap`；仅重启 hw_server 不够，会只看到 `xc7z020` 而误判「PS 不在链上」。
4. **供电（2026-10-12 用户明确）**：**用 USB 供电即可**，不必接手册 p.15 的 10 号 5V-DC。此前诊断提出的"USB 供电不足"假设据此不再作为待办项。
5. **Windows 26 编程入口恢复（2026-10-12 用户明确）**：**Windows 已可用 Vivado 26 进行烧录**，故上面第 1 条的暂停可解除，Windows 2026.1 重新作为下载/调试入口。**但这不等于两次 BugCheck `0x139` 的根因已被查明或根治**——历史证据原样保留；恢复直连后要记录实际观察时长与是否复现，不能凭"用户说可用"就写成"已根治"。

证据（仓库外，保留）：`D:\Agent\outputs\reboot-diagnosis-20261012\`、`D:\Agent\outputs\ftdi-repair-20261012\`、`D:\Agent\outputs\bkb220-connectivity-20261012\`。仓库内 JTAG 只读证据在 `logs/jtag/20261012T*-bkb220-wsl-jtag/`（`logs/` 已被 .gitignore 覆盖，未入库）。

## 1. 当前目标与完成边界

本轮是旧ZYNQ ECO R6 / XC7Z010→BKB220 / XC7Z020、SE150、PL100MHz、Stage1 16滑窗位置并行。帧仍64记录、生产几何150/50/807/957/64、线上协议和8100B结果不变。新板尚无完整配置、bit/XSA、整机时序或真板G3结果。

用户已授权迁移准备源码及文档提交推送，并要求合并文档、安排详细流程及Agent提示词、监控实施和整理工作区。当前已交付的准备成果不能代替新板验收。

用户指定的开发顺序（2026-10-11）：先用WSL Vivado2022.2完成硬件开发，PS软件也以补齐后的WSL Vitis2022.2为主；Windows2026.1负责下载/调试。WSL Vitis2022.2已从现有Vivado维护入口补齐：Vivado2022.2、XSCT2022.2.0必需命令及ARM GCC11.2.0实际Cortex-A9 ARM32对象编译通过；完整同XSA软件包仍待迁移阶段重建验证。已有Windows2026.1旧ECO XSA软件兼容探针继续保留，但不替代22主线或新板验收。22主线稳定后，最后独立验证Windows2026.1完整硬件及软件开发链路，规则见07。

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

~~2026-10-10/11设备核查快照没有实际FTDI/JTAG/PS USB串口，只见蓝牙COM3/COM4~~（2026-10-12 作废：已实测到 FT4232HL JTAG 与 COM9/10/11，见 §1a）。**仍然**待确认的是：厂商对应 PCB 原理图、PS7 preset/board_files、原厂例程、实物完整料号（顶标/温度等级/PCB 修订），以及 PS UART 的 MIO、ENET0 的 PHY/MDIO/RGMII/复位、DDR 板级延迟与 DQS-to-CLK。`hw/boards/bkb220.tcl` 的 `ready=0` 不变，手册收录与器件枚举都不代表新板配置或真板验收通过。

按05的F2～F9继续：可靠配置→最小UART/DDR/GEM/CAPS→新板P4基线→P16完整route和同XSA软件包→全量/连续/恢复→同板性能及相关泛化/长稳→最后独立复核→独立交付。功耗需仪器；SE250另profile；D0不默认分发。没有新板实测就不能宣布迁移完成。

~~最后Windows2026.1完整开发可靠性比较~~：因 §1b 的 Windows hw_server 崩溃路径被暂停，F9 的「Windows2026.1 负责下载/调试」与 26 复核入口须重新评估；在 FTDI 问题被证明根治前，下载/调试走 WSL 2022.2。

### 2026-10-12 接管进度（F0 完成 / F2 进行中）

| 阶段 | 状态 |
|---|---|
| F0 接管与现场核对 | **完成**：仓库绑定 PASS（main/origin 0/0，HEAD `22a0874`）、工具链与真实设备枚举、`agent_view` 以 main 登记、按现成 05 计划接管 |
| F1 已有成果确认 | 子 Agent 只读复核完成：P4/P16 正式源集与 `PACKAGED_VARIANTS.txt` 条目集合一致、无未覆盖文件、`check_ip_packaging.sh` 与 `check_repo_hygiene.sh` main 复跑均 **exit 0 PASS**（子 Agent 报的 packaging FAIL 是只读沙箱无法建临时输入所致，非真实缺陷）。P16 整机 LUT 先验约 33.9k（64%），仅 OOC 外推 |
| **F2 新板配置** | **基本完成**：来源表与候选 PS7 profile 已产出并经 Vivado 2022.2 逐属性验证（[来源表](board/bkb220/migration-source-table.md) §8、`hw/boards/bkb220.tcl`，`ready=0`）。**实测已定**：PS_CLK=33.333 MHz、DDR=533.33 MHz(DDR3-1066)、FCLK0=100 MHz、PS UART=UART0/MIO14-15→FT4232H 通道 C。`MT41K256M16TW-107` 被 PS7 catalog 拒绝，改用自定义 DDR 参数 |
| **F3 最小启动** | **全部通过**：`ps7_init`/`ps7_post_config` RC=0；DDR 0x10000000 起 1024 字写读 **0 不符**；UART0 经 JTAG 回环被 `/dev/ttyUSB2` 以正确 ASCII 收到；**ENET0 经 MDIO 实测 PHY=RTL8211E、1000BASE-T 全双工 link up**。尚缺 CAPS（需固件，属 F4）。详见 §1c |
| F4～F8 | 未开始。F4 前置：ENET0/PHY 归属被证实（否则 CAPS/G3 无从谈起）；脚本适配已由 verify-system 完成一轮 |
| F9 | 入口因 §1b 需重评 |

## 1c. 2026-10-12 F3 实板结果摘要

判据、原始命令与失败细节见[来源表 §9](board/bkb220/migration-source-table.md)。**已通过**：JTAG 单目标 xc7z020、`ps7_init`/`ps7_post_config` RC=0、MIO 回读与生成值逐位一致、三个 PLL 全 lock、**DDR 1024 字写读 0 不符**、**PS UART 归属实测确定**、**ENET0 的 PHY 识别与 1000BASE-T 全双工 link up**。**未测**：CAPS（需固件）、UART 反向、QSPI/SD 冷启动、bit/XSA/整机 route、DDR 板级延迟与 DQS-to-CLK、工业级器件精确料号。

**`ready` 已置 1**：依据用户 2026-10-12 明确授权「先建 P4、ENET0 留到板测再验」，且 ENET0 随后也已实测通过。仍未宣布迁移完成（缺整机 route 与 G3）。

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
