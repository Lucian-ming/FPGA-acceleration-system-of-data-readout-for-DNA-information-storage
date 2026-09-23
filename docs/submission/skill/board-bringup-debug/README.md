# 技能包：开发板连不上时的三步定位（JTAG / 串口 / 网口）

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
Linux 主机把前两步换成 `lsusb`、`dmesg | tail`，判据相同。

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

### 第 3 步：网口与应用层

- 链路层：`Get-NetAdapter` 看网卡是否 `Up`、协商速率是否正常；`Get-NetIPAddress` 确认主机 IP 与板子同网段；
- **板子没跑起固件时 ping 不通是正常的**，先下载固件再 ping，不要用 ping 判断硬件好坏。

## 失效条件

- **只对「USB 调试口」这条路有效**。板子用外置下载器（Platform Cable、J-Link）时按下载器的 VID 查。
- Windows 上装了 Zadig 之类换过驱动的，设备可能不再以 Ports/USB 类出现，得按 VID 查而不是按类查。
- 板子由外部电源供电、USB 只走数据时，USB 没枚举不代表板子没电——两者要分开判断。
- 第 1 步只能证明「电脑看见了这颗芯片」，**不能**证明板上 FPGA/SoC 是好的。

## 已验证效果

2026-09-22 本项目实测：换了两根新 USB 线后，板子上电、网口协商到 1 Gbps，但 `jtag targets` 为空。

1. 第 1 步查 VID：CH340（串口）在，**FTDI 0403:6014 完全没有出现，连枚举失败的未知设备也没有**
   → 判定为物理链路不通，不是驱动问题，省掉了重装驱动的一轮；
2. 查历史设备发现 JTAG 与串口**以前分别挂在主机不同的 USB 口**，
   纠正了「两者共用一个 DEBUG 口」的错误假设，从而定位到是**另一根新线只能充电**；
3. 换线后一次通过：`Digilent JTAG-SMT2 210251A08870`、`xc7z010`、两个 Cortex-A9 全部可见，
   随后板级测试全程无连接问题。

## 来源

这份清单来自一次**四轮反复**的排查：前三轮按「重插、换口、换线」盲试都没结果，
因为没有先回答「USB 到底枚举了没有」。第四轮改用按 VID 查 + 查历史设备，
两条命令就定位到线和接法，并顺带纠正了对板卡接口的错误认知。

教训：**「设备管理器里没有」和「设备管理器里有但报错」是完全不同的两类故障**，
盲目重装驱动只能解决后一类。
