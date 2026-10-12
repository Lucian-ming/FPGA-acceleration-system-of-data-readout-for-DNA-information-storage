# 07 · 板级配置、BKB220迁移与验收

本文件合并原09板级入口与07板级迁移文档。全项目阶段F0～F9、角色分工和监控见[05执行计划](05-implementation-plan.md)，直接派发提示词见[Agent索引](agent-prompts/README.md)。2026-10-10迁移准备有实际验证，新板验收仍待资料及连接。

## 1. 旧基线与新板信息

| 项目 | 旧ZYNQ ECO R6 | BKB220 |
|---|---|---|
| 器件 | xc7z010clg400-1，实际已有板测 | XC7Z020版本目标，候选xc7z020clg400-2；实物完整料号/PCB待核实 |
| PS7/DDR | 单颗16bit MT41J256M16HA-125、512MiB，详细资料在docs/board/zynq-eco-7010/ | 必须使用对应原理图/PS7 preset确认组织、时序/延迟/容量；产品手册不足以生成配置 |
| 时钟/UART/GEM/PHY/MIO/XDC | hw/boards/zynq_eco_7010.tcl保留原已知配置 | **已由原理图补齐**：PS_CLK 33.333MHz、UART0=MIO14/15、ENET0=RGMII、PHY=RTL8211E-VL、MDIO=MIO52/53、**PHY 地址=1**、PHY 复位接 PS_POR_B。XDC 复用 hw/constr/top.xdc（无 PL 外部引脚） |
| 制品/正确性 | hw/build/export历史五项SHA可核对，SE150真板闭环 | 尚无新板完整包、整机时序、真实G3或性能结果 |
| 连接 | 历史板测设备路径不能直接沿用 | **2026-10-12 已实测**：板载 FT4232HL 提供 JTAG（链 `Xilinx HW-Z1-ZCU104 FT4232H 15051A`，单目标 xc7z020/IDCODE `0x23727093`）+ 三串口（Windows COM9/10/11）。直通 WSL 后 `/dev/ttyUSB0`=JTAG、`1/2/3`=串口。ASIX USB 千兆网卡在 Windows 侧 `192.168.1.100/24`。**触板只允许走 WSL（见 §3a）**；PS UART 的 MIO、ENET0 的 PHY 仍未定 |

产品手册已收录：[BKB220产品手册v1.1.pdf](board/bkb220/BKB220产品手册v1.1.pdf)，[资料来源与SHA校验](board/bkb220/README.md)。2026-10-11按用户提供文件原样复制，原件与副本SHA一致。main和board-migrate先完整阅读PDF，在docs/board/bkb220目录运行`sha256sum -c SHA256SUMS.txt`；来源表记录仓库资料路径、手册页码及其对应的PCB/器件。对应原厂原理图/board_files/PS7 preset/例程及实物仍需确认，不把手册示例当实际参数或操作授权。

## 2. 配置与构建门禁

hw/boards/load_board.tcl统一选profile。未知板、ready=0、缺uart/xdc/source_refs/ps7_properties均拒绝create_project。bkb220.tcl当前ready=0保持不变；资料确认并由main审核来源表后才可ready=1。

SE150生产：READ_BPS150、NUM_LC50、STRIDE807、REF_LEN957、BATCH64；PL100MHz；旧板/新板P4=4/0，P16=16/1，拒绝7010/P16或非法组合。每种板/路数/工具版本用独立build/export/report目录，不覆盖旧发布路径。构建后核对实际IP七参数，保存硬件summary、工具版本、完整器件/PCB与资料来源。

完整route必须WNS/WHS≥0、TNS/THS=0、失败端点0、DRC/路由/约束合法；遇到Decoder→HP或其他真实关键路径按受影响接口回归修复，不加无依据false path，不降频冒充100MHz。

## 3. 工具链和同源制品

用户指定的开发顺序（2026-10-11）：先用WSL Vivado2022.2完成硬件开发，PS软件也以补齐后的WSL Vitis2022.2为主；Windows2026.1负责下载/调试。WSL Vitis2022.2已从现有Vivado维护入口补齐：Vivado2022.2、XSCT2022.2.0必需命令及ARM GCC11.2.0实际Cortex-A9 ARM32对象编译通过；完整同XSA软件包仍待迁移阶段重建验证。已有Windows2026.1旧ECO XSA软件兼容探针继续保留，但不替代22主线或新板验收。22主线稳定后，最后独立验证Windows2026.1完整硬件及软件开发链路，按下面三阶段门禁执行。

1. **22主开发**：显式VIVADO_ROOT=/tools/Xilinx/Vivado/2022.2，使用现有run_vivado_build.sh、XSim与独立build/export/report目录。Vitis2022.2/XSCT实际路径、版本、命令及ARM对象编译已通过；接着用同XSA生成BSP/应用；create_vitis.tcl当前只覆盖应用构建，board还必须核对并补齐FSBL/BOOT/readback/manifest整套链路，不能把历史旧BSP编译或一次exit0当完整重建。
2. **26下载**：Windows实际hw_server/XSDB2026.1仅下载22产生的bit、同XSA的ps7_init和ELF。run_g3.sh显式--artifact-dir、--xsdb、--device、--uart-port和实际IP。Hardware Manager只下载PL不能证明PS软件就绪；混合版本下载兼容性必须经真实UART/CAPS/DDR/GEM/G3验证。
3. **最后26开发复核**：22主线通过后，board在同一冻结HEAD/参数/输入上独立用Windows2026.1重建完整P4/P16硬件和同XSA软件包，rtl复核100MHz整机时序，verify复核功能/接口、新板G3、连续恢复、性能矩阵与长稳。独立目录及带SHA只读输入快照，不原地升级22工程；每包核验同源SHA，跨版本按功能/STA/统计比较，不能要求bit/ELF整文件SHA相等。未通过则保持22为发布主线并保存26失败，不能宣称26开发可靠。

Windows Vivado/Vitis2026.1位于D:/xilinx/2026.1；2026.1 XSCT已实测禁用且可能退出0，软件必须用create_vitis_modern.py/run_vitis_modern.ps1。它已在旧ECO XSA完成实际软件构建，只是兼容证据；下面现代API/BOM规则适用于最后26软件重建或main明确指定的辅助探针，不是提前改用26主开发。

完整新包须有bit、含bit的XSA、同XSA的ps7_init.tcl、BSP、应用ELF、FSBL、BOOT.bin、readback、SHA256SUMS、硬/软件summary和G3 artifact_manifest.json。实际manifest字段以g3_artifacts.py读取为准，必须记录完整part、board、工具/源码SHA、几何和P_WAYS/PIPE_TREE，并验证XSA内bit和HWH七参数。

现代软件JSON显式repo_root/workspace/xsa/export_dir/uart/board_id/part/bootgen，workspace全新、UART来自实际BSP、CPU为ps7_cortexa9_0 standalone。排除sw/app/xparameters.h历史快照；SDT地址/查询键/共享GIC/全局timer使用实际BSP，30秒超时先转64位。sw/app是权威源，workspace不手改。

**lwIP 版本按工具链实际提供的选，不要写死。**（2026-10-12 更正：原句在此处写"standalone/lwip220"，被误读成 22 主线也要 lwip220，导致 board-migrate 在 F4 因"lwip220 不在 Vitis 2022.2 安装树"而阻塞一轮。）
- **22 主线（WSL Vitis 2022.2）**：安装树只有 `lwip211_v1_5/1_6/1_7/1_8`；仓库现有 `sw/scripts/create_vitis.tcl` 本来就按 `lwip213 → lwip211 → lwip210` 回落，**以它的选择为准**；旧板已验证的 BSP 用的就是 `lwip211_v1_8`。
- **Windows 2026.1（F9 复核）**：现代 Vitis 提供 **lwip220**，届时由现代入口选择。跨版本不要求 lwIP 主版本相同，按功能/接口/统计比较。
- 通用规则：**BSP 选择必须来自实际安装树**；缺指定版本时**如实报告并按实际可用版本构建 + 标注差异**，不得静默替换，也不得因为版本号不同就判整包失败。

本机lwIP BOM兼容副本由prepare_vitis_compat_repo.py创建并验证414文件manifest；只移除描述文件BOM，不改安装或原厂库实现。构建同时要求成功哨兵、build状态0、实际非空产物、Bootgen readback和六SHA；不能仅依赖launcher exit0。完整命令及A14边界见[工具核查](benchmarks/bkb220-toolchain-audit.md)。

## 3a. 触板通道：只走 WSL，禁止 Windows hw_server（2026-10-12 新增）

2026-10-12 连接测试期间 **Windows 主机两次蓝屏**（BugCheck `0x139`，参数1=`0xA`；两份转储当前进程均为 `hw_server.exe`，栈均为 `ftdibus+0xf4d4`）。用户当日已建立安全通道，本文件据此规定触板方式：

| 项 | 规定 |
|---|---|
| 设备归属 | 用 `usbipd attach --wsl --busid 4-2` 把新板 FT4232H（序列号 15051）**直通 WSL**；Windows 不再持有该设备 |
| 硬件服务 | 跑 WSL 的 `/tools/Xilinx/Vivado/2022.2/bin/hw_server -sTCP:127.0.0.1:3132` |
| 连接入口 | WSL `/tools/Xilinx/Vitis/2022.2/bin/xsdb` 连 `TCP:127.0.0.1:3132` |
| **禁止** | 启动 Windows 原生 `hw_server.exe`（`D:\xilinx\2026.1\...`）——已知崩溃路径，用户已暂停 |
| 重挂规则 | **杀掉 hw_server 后必须真正重新枚举 USB**（`usbipd detach` 再 `attach`，确认设备号变化）才能再取到 `arm_dap`；只重启 hw_server 会只看到 `xc7z020`，容易误判「PS 不在链上」 |
| 供电 | **用户 2026-10-12 明确：USB 供电即可**，不必接手册 p.15 的 10 号 5V-DC。此前"USB 供电不足"假设不再作为待办 |
| Windows 26 编程 | **用户 2026-10-12 明确：Windows 已可用 Vivado 26 烧录**，故上表「禁止 Windows hw_server」可解除。**但两次 BugCheck `0x139` 的根因并未因此被查明或根治**，历史证据保持不变；恢复直连后须记录实际观察时长与是否复现 |
| 厂商 board file | 2026-10-12 在 `D:\xilinx\2026.1`、`D:\Xilinx\2026.1`、`C:\Xilinx`、`E:\` 递归搜 `*b220*/*B220*/*bkb*/*BKB*`：**只命中 Xilinx 自带内容（Model_Composer 的 libkbd*.a 等），无 BKB220 板卡文件**；2026.1 的 `Vivado\data\xhub\boards\XilinxBoardStore` 仅有 Xilinx 官方板。**厂商 board_files/PS7 preset 仍缺**；但**厂商原理图已由用户于 2026-10-12 提供并入库**（[BK_B220_SchDoc.pdf](board/bkb220/BK_B220_SchDoc.pdf)，逐条核对见[来源表 §10](board/bkb220/migration-source-table.md)） |

由此，本文件 §3 第 2 阶段「Windows 2026.1 负责下载/调试」以及 F9 的 Windows 26 复核入口**在 FTDI 问题被证明根治前不可用**；下载/调试改走 WSL 2022.2。这不是把 26 结论改成通过，而是如实记录入口被阻塞。恢复 Windows 直连需先有「驱动/服务版本对照 + 供电条件明确 + 单次受控验证」的证据。

## 4. 本轮已验证准备成果

| 内容 | 结果/摘要 |
|---|---|
| 正式可选P4/P16、源集、参数/包装 | 打包与2022.2真实catalog通过；[集成摘要](benchmarks/stage1-16way-ip-integration.md) |
| LC50模块与真实包装接口 | Windows2026.1 XSim两个case各两轮PASS，Icarus模块同周期；约3.27倍仅模块周期 |
| G3严格制品选择、串口与性能入口 | 47项主机fixture/替身测试通过；[主机摘要](benchmarks/bkb220-host-verification.md) |
| Windows2026.1软件路线 | 旧ECO XSA A14：BSP/应用/FSBL/BOOT/readback/六SHA PASS；不是新板制品 |
| **BKB220 P4/P16 整机 100MHz 构建** | **PASS**（[benchmark](benchmarks/bkb220-p4-p16-100mhz-build.md)）：均为 `Physopt postRoute`，P4 WNS+0.680/WHS+0.036、P16 WNS+0.617/WHS+0.017，**失败端点均 0**，DRC 各 **0 errors**，`clk_fpga_0`=100.000 MHz，XSA 内 `PART=xc7z020clg400-2`；P16 33,987 LUT（63.89%）。**未做**：板测与同 XSA 软件包 |
| **BKB220 PS7 catalog 验证** | 29 属性经 Vivado 2022.2 逐条检查（[来源表 §8](board/bkb220/migration-source-table.md)）。`MT41K256M16TW-107` **被 catalog 拒绝**，改用 `Custom` + 自定义容量/时序；`xc7z020clg400-2` 在库中，但手册的工业级条目未确认 |
| **BKB220 F3 实板最小启动** | **通过**（[来源表 §9](board/bkb220/migration-source-table.md)）：`ps7_init`/`ps7_post_config` RC=0；DDR 0x10000000 起 1024 字写读 0 不符；PS UART = UART0/MIO14-15 → FT4232H 通道 C（`/dev/ttyUSB2`）115200 8N1 明文正确；PS_CLK 33.333 MHz、DDR 533.33 MHz、FCLK0 100 MHz；**ENET0 MDIO 通、PHY = RTL8211E、1000BASE-T 全双工 link up**。尚缺 CAPS（需固件，属 F4） |

计划与索引曾先推送c4d7ad4；后续用户已明确授权代码和完整整理交付。原三子Agent额度中断后main接管。新板core门禁仍未关闭。

## 5. 迁移顺序与真实验收

1. 对应PCB/part/原理图/preset来源表核对；实际电源、USB调试和网口；确定唯一JTAG（**已实测**：`15051A` 单目标 xc7z020）、实际PS UART（**仍未定**：FT4232H 通道 B/C/D 对应 `/dev/ttyUSB1/2/3`，用最小 hello 固件逐一实测，不选蓝牙兜底）。
2. 最小同XSA包验证UART、DDR训练/容量/安全区读写、GEM链路和CAPS；不要先跑整机来定位未知DDR。
3. 新板P4/SE150/100MHz合法route及完整软件包；smoke2048、全量、四级DDR、最终SHA，冻结同板P4基线。
4. P16/16/1正式LC50独立模块/真实包装PASS、完整route及完整同XSA软件包；smoke→全量≥3次→连续/脏干净/恢复。
5. 同板P4/P16六档≥3次性能矩阵，相关泛化/鲁棒/长稳；功耗无仪器保持未测。完整样本和失败保留，详情在06/08。
6. 22主线稳定后完成上述独立Windows2026.1硬件及软件开发可靠性比较；最终源/参数/工具/制品/SHA、报告、复现命令、限制和文档齐全，main按路径提交推送0/0，释放本任务资源并整理源码工作区。

板端G3唯一入口是run_g3.sh --artifact-dir完整包，加显式XSDB/device/PS串口/IP；矩阵脚本不自动下载，先确认已加载对应包。JTAG成功不能证明SD/QSPI冷启动；BOOT打包不能当冷启动PASS，非易失介质出厂镜像不默认覆盖。

## 6. 完成定义和回退

新板配置、P4基线、P16合法100MHz整机、同XSA软硬制品、全量/连续/恢复与公平性能均通过才能宣布迁移完成。旧SE250成功、P14 OOC、新准备仿真和A14兼容软件探针均不能替代。失败保留独立run和报告，退回已验P4，不覆盖历史数据、export或失败证据。
