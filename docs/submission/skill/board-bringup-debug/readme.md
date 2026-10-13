# 技能包：开发板连接故障分层定位（USB / JTAG / 串口 / 网口）

> 参赛提交物，不是本仓库的开发规范（见上级 README）。

## 适用场景

板子已经上电，但出现下列任一现象：

- Vivado / Vitis 的 hw_server 扫不到器件（`jtag targets` 为空）；
- 设备管理器里看不到串口；
- 换过 USB 线、换过 USB 口、重装过驱动之后仍然不通；
- 以太网能连但板子 ping 不通。

**核心思路**：先分清故障在哪一层——**USB 枚举 → 驱动 → 工具链 → 应用**。
绝大多数「板子坏了」其实停在第一层，而第一层用一条命令就能判定。

## 使用方法

环境：Windows 主机（WSL 里可用 `powershell.exe` 调用），AMD/Xilinx 工具链。
Linux 主机把 USB 枚举查询换成 `lsusb`、`dmesg | tail`；XSDB 可用时，JTAG 步骤仍可用 XSDB。

### 第 1 步：USB 有没有枚举（分清是线的问题还是驱动的问题）

```powershell
# 板载调试芯片的典型 USB ID：FTDI(FT232H/FT2232)=VID_0403，WCH CH340=VID_1A86，
# Digilent HS2/HS3 也是 VID_0403。按 VID 查，不要按名字查。
Get-PnpDevice -PresentOnly | Where-Object { $_.InstanceId -match 'VID_0403|VID_1A86' } |
  Format-Table -AutoSize Status,FriendlyName,InstanceId
```

判读：

| 现象 | 结论 | 下一步 |
| --- | --- | --- |
| 什么都没有，连「未知 USB 设备」都没有 | **物理链路不通**：多半是只能充电的线，或插错口、Type-C 插反 | 换一根确认能传数据的线；插板上标 DEBUG/PROG 的口；把插头翻面再插 |
| 出现了设备但 `Status` 不是 `OK`（黄色感叹号） | 枚举成功、驱动没装上 | 装 FTDI / CH340 驱动，或用 Zadig 换驱动 |
| 设备在且 `Status=OK` | 第一层没问题 | 进入第 2 步 |

补充一条判据：**查历史设备**能告诉你「以前是什么样」。

```powershell
# 去掉 -PresentOnly 就能看到曾经插过、现在不在的设备，
# 包括它以前挂在哪个 USB 口（InstanceId 里的位置码）
Get-PnpDevice | Where-Object { $_.InstanceId -match 'VID_0403' } |
  Format-Table -AutoSize Status,FriendlyName,InstanceId
```

这一步能直接回答「JTAG 和串口本来是一根线还是两根线」——把当前枚举到的设备的位置码
与历史记录对比即可，不用去翻板卡手册。

### 第 2 步：工具链能不能看到器件

```tcl
# 存成 probe.tcl，用 xsdb probe.tcl 运行（Vivado Lab 版自带 xsdb）
connect
puts [jtag targets]     ;# 应当列出下载器与芯片，例如 "Digilent JTAG-SMT2 210251A08870"
puts [targets]          ;# 应当列出 APU / Cortex-A9 / 器件本身
disconnect
exit
```

- 输出为空 → 回到第 1 步，USB 那层还没通；
- 能看到下载器但看不到芯片 → 板子没上电、复位被按住，或电平/排线问题；
- 都能看到 → JTAG 通了。

### 第 3 步：串口端点能不能枚举、输出是否唯一

```powershell
Get-PnpDevice -PresentOnly -Class Ports |
  Format-Table -AutoSize Status,FriendlyName,InstanceId
```

Linux 可用 `ls -l /dev/serial/by-id/` 查看稳定设备名，再用 `dmesg | tail` 对照插拔事件。枚举到 COM/tty 只证明 USB 串口端点存在；要确认映射，按板卡/原理图给出的 UART 与波特率发送唯一递增标记，记录哪个端点收到以及其余端点是否为空。不要把主机端口号当成板上 UART 编号。

### 第 4 步：网口与应用层

- 链路层：`Get-NetAdapter` 看网卡是否 `Up`、协商速率是否正常；`Get-NetIPAddress` 确认主机 IP 与板子同网段；
- **板子没跑起固件时 ping 不通是正常的**，先下载固件再 ping，不要用 ping 判断硬件好坏。

### 第 5 步：Zynq PS GEM 的 MDIO / PHY（BKB220 实例）

主机网卡显示 `Up` 只证明主机侧链路状态。要判定板端 ENET0，按以下顺序取证：

1. **先初始化 PS。** 断电重上后，先对本次实际烧录包执行匹配的 `ps7_init` / `ps7_post_config`。未初始化时 MIO52/53 尚未复用为 MDIO，PHY 寄存器读回 `0` 不能判成 PHY 故障。
2. **核对被烧录制品里的 MIO 配置。** 查同一软件包的 `ps7_init.tcl`，确认 MIO16–27 的 RGMII 配置存在，MIO52/53 的 MDIO 配置写入 `0x1280`。只在独立探针里验证过的 PS7 配置，不代表正式 XSA 含有该配置。
3. **按驱动头文件配置并轮询 GEM。** 对照本工具版本的 `xemacps_hw.h`：`NETWORK_CONTROL` 的 MDEN 是 bit 4（`0x10`），bit 3 是 TXEN；MDIO 事务完成状态看 `NETWORK_STATUS[2]`（`0x4`），不要轮询 `PHY_MAINT` 的 bit 2。寄存器基址和事务字段也以实际驱动头文件为准。
4. **核对 PHY 身份与链路。** BKB220 原理图给出 PHY 地址 1；读 PHY reg2/reg3 应为 `0x001C/0xC915`（RTL8211E）。BMSR reg1 的 link bit 是锁存低，至少连续读两次再判断当前状态，并检查自协商完成位。1000BASE-T 状态 reg10 bit11 表示对端声明支持全双工，不等于当前已协商速率；要宣称实际 1000/full，另用 RTL8211E 的厂商状态寄存器或驱动解析结果确认并留原值。
5. **再验应用层。** PHY link up 不等于 CAPS 或 TCP 任务通过；分别执行 CAPS 握手、双向 ping/TCP，并保留板端和主机端计数。

用 Xilinx standalone `XEmacPs` 驱动时，可将下面流程示意放进一次性诊断 ELF；`gem` 是已初始化的 `XEmacPs *`，每次 API 返回值也要记录。示意代码里的 `FAIL` 接到项目自己的错误处理：

```c
u16 id1 = 0, id2 = 0, bmsr_first = 0, bmsr_now = 0, gb_status = 0;
int rc = XEmacPs_PhyRead(gem, 1, 2, &id1);  /* PHY ID1 */
if (rc != XST_SUCCESS) FAIL("MDIO reg2", rc);
rc = XEmacPs_PhyRead(gem, 1, 3, &id2);      /* PHY ID2 */
if (rc != XST_SUCCESS) FAIL("MDIO reg3", rc);
rc = XEmacPs_PhyRead(gem, 1, 1, &bmsr_first);
if (rc != XST_SUCCESS) FAIL("MDIO BMSR first", rc);
rc = XEmacPs_PhyRead(gem, 1, 1, &bmsr_now); /* BMSR link bit is latch-low */
if (rc != XST_SUCCESS) FAIL("MDIO BMSR second", rc);
rc = XEmacPs_PhyRead(gem, 1, 10, &gb_status);
if (rc != XST_SUCCESS) FAIL("MDIO 1000BASE-T status", rc);
if (id1 != 0x001c || id2 != 0xc915) FAIL("unexpected PHY ID", XST_FAILURE);
if ((bmsr_now & 0x0004) == 0) FAIL("link down", XST_FAILURE);
if ((bmsr_now & 0x0020) == 0) FAIL("autoneg incomplete", XST_FAILURE);
if ((gb_status & 0x0800) == 0) FAIL("partner lacks 1000/full", XST_FAILURE);
/* Reg10 bit11 confirms partner 1000/full capability only.
 * It does not identify the current negotiated speed/duplex. */
```

把 `FAIL` 换成项目自己的错误记录/非零完成状态处理，并把五个读回值写入串口日志或可读内存；不要照抄未知寄存器基址或用一次读到的 BMSR 判 down。若目标不是 BKB220，PHY 地址、ID 和千兆判据必须换成该板原理图/PHY 手册给出的值。

MDIO 每次观察都要关联板型/器件、实际制品、`ps7_init.tcl`、工具版本与原始寄存器输出。地址、MIO 或位定义不确定时先查原理图与驱动头文件，不用盲扫来代替资料核对。

## 失效条件

- **只对「USB 调试口」这条路有效**。板子用外置下载器（Platform Cable、J-Link）时按下载器的 VID 查。
- Windows 上装了 Zadig 之类换过驱动的，设备可能不再以 Ports/USB 类出现，得按 VID 查而不是按类查。
- 板子由外部电源供电、USB 只走数据时，USB 没枚举不代表板子没电——两者要分开判断。
- 第 1 步只能证明「电脑看见了这颗芯片」，**不能**证明板上 FPGA/SoC 是好的。

## 已验证效果

**旧板历史案例（2026-09-22，XC7Z010）**：换了两根新 USB 线后，板子上电、网口协商到 1 Gbps，但 `jtag targets` 为空。

1. 第 1 步查 VID：CH340（串口）在，**FTDI 0403:6014 完全没有出现，连枚举失败的未知设备也没有**
   → 判定为物理链路不通，不是驱动问题，省掉了重装驱动的一轮；
2. 查历史设备发现 JTAG 与串口**以前分别挂在主机不同的 USB 口**，
   纠正了「两者共用一个 DEBUG 口」的错误假设，从而定位到是**另一根新线只能充电**；
3. 换线后一次通过：`Digilent JTAG-SMT2 210251A08870`、`xc7z010`、两个 Cortex-A9 全部可见，
   随后板级测试全程无连接问题。

**BKB220 新板补充（2026-10-12）**：实板 JTAG 识别为 `xc7z020`；PS ENET0 的 RGMII（MIO16–27）和 MDIO（MIO52/53）在正式制品配置补齐后通过板测，PHY ID 为 `0x001C/0xC915`，链路为 1000BASE-T 全双工。一次“MDIO 无应答”并非板卡问题：探测代码漏开 MDEN（误写 TXEN），且轮询了错误寄存器；按 `NETWORK_CONTROL` bit 4 使能、以 `NETWORK_STATUS[2]` 判完成后读数恢复。原理图还确认 PHY 地址为 1、复位随 `PS_POR_B`，固件不应假设另有 GPIO reset。对应逐轮摘要见 `docs/board/bkb220/migration-source-table.md` §9–§15；主机 ASIX 网卡 `Up` 本身不算板端通过。

## 来源

这份清单来自一次**四轮反复**的排查：前三轮按「重插、换口、换线」盲试都没结果，
因为没有先回答「USB 到底枚举了没有」。第四轮改用按 VID 查 + 查历史设备，
两条命令就定位到线和接法，并顺带纠正了对板卡接口的错误认知。

教训：**「设备管理器里没有」和「设备管理器里有但报错」是完全不同的两类故障**，
盲目重装驱动只能解决后一类。
