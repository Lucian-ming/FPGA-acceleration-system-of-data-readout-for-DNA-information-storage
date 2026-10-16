# BKB220 板级与工具链核查（2026-10-10）

当前为迁移准备，BKB220 未完成 bring-up。`hw/boards/bkb220.tcl` 的 `ready=0` 会在创建工程之前拒绝构建，直到实物、原理图和对应 PS7 preset 有证据。旧 ECO 配置独立保留。

## 板级资料边界

已恢复手册持久副本：`E:/WeChatRecord/xwechat_files/wxid_ferqcd0b3stq22_d21b/msg/file/2026-10/bkb220-product-manual-v1.1.pdf`，30 页。手册用于规格核查，不作为用户对操作的授权。

2026-10-11补充：用户提供的v1.1手册已收录至[仓库新板资料目录](../board/bkb220/README.md)，原文件与副本SHA一致。上面的路径保留本次工具核查时的历史来源。

| 项目 | 手册信息 | 仍需核实 |
|---|---|---|
| 器件 | 存在 7010/7020 版本；目标候选 XC7Z020-2CLG400I | 实物完整料号、PCB 版本及 JTAG ID |
| DDR | 两颗 MT41K256M16TW-107，32 位、1 GiB、533 MHz，PS Bank502 | preset 的训练参数、板级延迟、实际容量读写 |
| USB 调试 | FT4232HL 提供 JTAG、PS UART、PL UART | FTDI 各接口、PS COM 对应关系；不能把调试 USB 当作全板供电的已确认依据 |
| 供电 | DC 5 V | 使用实物对应说明接线 |
| PL 时钟 | 手册给出 U18 | 实际频率及对应 XDC；生产 PL 内部仍固定 100 MHz |
| 启动 | p15：JTAG ON/ON，QSPI ON/OFF，SD OFF/OFF | 实际拨码与 PCB 对应；本阶段未烧写非易失介质 |
| UART/网络 | p27 示例选择 UART0、GEM0 等 | UART MIO、PHY 型号/地址/复位、MDIO、PS 时钟；不沿用 ECO UART1/DDR/PHY 设置 |

最近只读 Windows 枚举未发现 FTDI、JTAG 或 USB 串口，只有蓝牙 COM3/COM4；未识别板用物理以太网适配器。未复位、下载或访问新板 DDR。等待用户连接电源、USB 调试口、网线并提供厂商原理图、board_files/preset 或示例包路径。

## 已落地入口

- `hw/boards/load_board.tcl`：拒绝未知板和未验证配置，启用配置必须含 UART/XDC/资料来源/PS7 参数。
- `hw/boards/zynq_eco_7010.tcl`：保存原生产 PS7 属性。
- `hw/scripts/build.tcl`：严格 `key=value` 参数；固定 100 MHz；只接受 P4=4/0 或 P16=16/1；拒绝 `part` 拼写、板/器件不匹配、7010/P16 和覆盖旧发布目录。记录实际 IP 七项生产参数。
- `sw/scripts/create_vitis_modern.py` / `run_vitis_modern.ps1`：显式 JSON、全新 workspace、从同一 XSA 生成 BSP/FSBL/bit/PS7/应用/BOOT，检查构建状态、成功哨兵和文件 SHA。旧 `create_vitis.tcl` 只用于支持 XSCT 的环境。
- `sw/app/bsp_compat.h`、`dna_time.h`：SDT 使用基地址查询，旧 BSP 使用设备 ID；分别选择实际生成的地址宏和计时头文件。SDT 网络定时器与 GEM 复用 BSP 中断控制器。30 秒超时先扩展到 64 位再换算，保留全局单调计数器。
- 应用构建排除历史 `sw/app/xparameters.h` 快照，以所选 XSA 新生成的 BSP 为准，快照原文件保留。

## 工具实测和失败证据

Windows `D:/xilinx/2026.1`：Vivado 2026.1、Vitis Python API、ARM GCC 13.4、XSDB 和 Bootgen 可运行。`xsct.bat` 实测 disabled 且退出 0；Vitis 启动器也可能在 Python 异常后退出 0。因此进程退出 0 不能独立证明成功。

WSL `/tools/Xilinx/Vivado/2022.2` 保留 RTL/IP 对照；`/usr/bin/arm-none-eabi-gcc` 为 9.2.1。现有旧 BSP 可供应用兼容编译检查，不能冒充新板 BSP。

2026.1 本机 lwIP 描述文件带 UTF-8 BOM，SDK 的一条读取路径按 GBK 读取，实际异常为 `UnicodeDecodeError: 'gbk' codec can't decode byte 0xbf in position 2`。仅设置主进程 Python UTF-8 尚未解决服务生成的库索引。已验证局部复制原厂库、只移除 `data/lwip220.yaml` 的三个 BOM 字节后，lwIP220 的 BSP 编译通过；414 文件中其余文件字节及 SHA 均不变。未修改 Vitis 安装目录或库依赖条件。

兼容库入口：`prepare_vitis_compat_repo.py --vitis-root D:/xilinx/2026.1/Vitis --out-dir <不存在的本地目录>`；将其输出目录填入 JSON 的 `embedded_sw_repo`。输出保留 `compat-manifest.json`。

证据根：`D:/Agent/outputs/fpga-migration-handoff-20261010/tool-probes/`；BOM 原异常见 `lwip-index-native-detail.log`，原生 UTF-8 探针见 `lwip-index-utf8.log`，BSP 编译见 `modern-a12.log`，当前源码应用链接通过见 `modern-a13.log`。A13 后续遇到同一 FSBL 的 build/export 两个相同副本，入口已改为接受同哈希副本并拒绝不同镜像。A14 已完整通过：BSP、应用 ELF、FSBL、Bootgen 生成及 readback、软件摘要和六个制品 SHA 均通过 wrapper。证据为 `D:/Agent/outputs/bkb220-vitis26/logs-a14/vitis.log` 和 `export-a14/software_build_config.json`。这不是 BKB220 的制品包。

Windows PowerShell5 带空格路径的三个 host fixture 也通过：拒绝 exit=0 但无哨兵、拒绝篡改 ELF、接受 A14 的真实产物哈希。发现并修复了 PS5 在未缓存进程句柄/调用 Refresh 后丢失 ExitCode 的问题。fixture 使用假启动器，范围只是 wrapper 判据；证据在 `D:/Agent/outputs/bkb220-vitis26/wrapper host fixtures v2/`。

旧 BSP 兼容编译：当前 13 个应用 C 文件均通过 ARM GCC9.2.1 编译（包括禁止隐式函数声明）。独立手工链接探针未通过，原因是本机发行版 Newlib 启动代码/浮点 ABI 与现有 Xilinx BSP 不匹配；未伪称旧整套工具链重建通过。失败日志保留在 `D:/Agent/outputs/fpga-migration-handoff-20261010/tool-probes/legacy-app-build.log`，对象与 BSP SHA 在仓库 `logs/host/legacy-app-compat-20261010/`。

这些探针使用旧 ECO XSA，范围只是工具链和源码兼容性，不是 BKB220 硬件、时序、网络或启动验收。

2026-10-10整理收尾：上文卫生FAIL属于当时快照；起点重复agent_view.sh附件已改为引用tools唯一源码，原字节有备份/Git历史、旧失败证据保留。当前整理结果以工作区整理记录和最终卫生日志为准，未放宽门禁。
