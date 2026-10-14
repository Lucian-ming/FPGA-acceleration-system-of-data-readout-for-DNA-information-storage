> 脱敏副本，原件 `20261012T111757Z-da68ff4265/{prompt.txt,answer.md}`。本机绝对路径、邮箱、凭据形模式及非白名单私网 IP 已替换；除脱敏与换行规范化外保留原文。

你是本项目的 board-migrate 子Agent（任务短名/看板名：board-migrate）。上一轮你误把「仓库绑定预检」当成自己的门禁而阻塞，现在已更正，请继续。

【重要更正，先读】`bash tools/verify_repo_binding.sh --remote` 是 **main 的门禁，不是你的**。main 已在 2026-10-12 实跑并通过（origin 为唯一指定仓库、main...origin/main = 0/0）。codex 沙箱会把 git 目录（本仓库的 gitdir 是 `.git-data`，不在 `.git`）挂成只读，所以你跑 `--remote` 必然报 `READ-ONLY file system` 写 `FETCH_HEAD` 失败——这是**沙箱特性，不是仓库故障**。你**不要**再运行该脚本，也不要运行任何会写 git 的命令（fetch/pull/add/commit/rebase/stash/reset/clean/push）。只读 git 命令（status/log/show/diff）可以用，但本任务基本不需要。
看板上你上一轮留了一个 block 条目，请用 `tools/agent_view.sh start --agent board-migrate --doing "..." --why "..." --next "..."` 重新登记为进行中后继续干活。

先完整阅读 docs/agent-prompts/board-migrate.md（你的角色提示词全文）、AGENTS.md、CLAUDE.md，再读 docs/03-status.md、docs/05-implementation-plan.md、docs/07-board-build-and-acceptance.md、docs/02-data-contract.md、docs/04-interfaces.md。

【看板】你是 workspace-write 任务，自己登记（start/update/block/done），三个字段写具体内容。
【禁止】任何 Git 写操作，不建分支/worktree，不派生子 Agent，不跑 Vivado 综合/实现（大型 EDA 须 main 授权），不触板（JTAG/串口/下载/reset/dump 全归 main）。

============ 阶段卡（2026-10-12，main 已实测核对）============
当前 HEAD：22a0874fbd64bce3354a2f27c6f1584740dd4a0a，main == origin/main（0/0）。
本阶段：F2（新板配置落实）。BKB220 已到货并连接，main 已在 JTAG 上实测确认。

【main 实测的现场事实，直接采信，不必重测】
1. JTAG：板载 FT4232HL，XSDB(Windows 2026.1) 枚举链名 "Xilinx HW-Z1-ZCU104 FT4232H 15051A"，单目标 xc7z020，IDCODE 0x23727093。
2. Windows 串口：COM9 / COM10 / COM11（FT4232H 通道 B/C/D，序列号 15051B/C/D）。WSL 内无 <本机路径> Windows 侧）。
3. 网络：Windows 侧 ASIX USB 千兆网卡「以太网 2」= <内网IP已脱敏>/24，链路 Up 1 Gbps，ReceivedBytes=0（板端 PS 尚未发过包）。
4. 工具链：WSL Vivado 2022.2 = <本机路径> Vitis/XSCT 2022.2 = <本机路径> GCC 在 gnu/aarch32/lin/gcc-arm-none-eabi）；Windows 2026.1 = <本机路径> = <本机路径>

【仓库内产品手册已实测校验】docs/board/bkb220/BKB220产品手册v1.1.pdf，SHA-256 40b50e666ecab4ee83fbcfb1eea816a04a0989f73b001d9b9432e4778c8cd086，`sha256sum -c SHA256SUMS.txt` 通过。main 已 pdftotext 抽全文核对，以下规格务必**自己在 PDF 里复核页码**后再引用：
- 器件 XC7Z020-2CLG400I（p.5-6）
- JTAG 由板载 FTDI FT4232HL 实现，无需外置下载器（p.7）
- DDR3：2 片 Micron MT41K256M16TW-107，每片 256M×16bit，共 32bit 位宽 / 1GB，最高 533MHz(1066Mbps)，接 PS BANK502（p.9-10）
- QSPI：W25Q256 32MB，接 PS_MIO1..6（p.8-9）
- 启动：JTAG / QSPI / SD，BOOT_CFG 拨码（p.15）
- PS MIO 电压：VCCO_MIO0=3.3V、VCCO_MIO1=1.8V、VCCO_DDR=1.5V（p.8）
- PL 系统时钟引脚 U18、PL 侧 UART 引脚 F16/F17（p.17，是 PL 引脚不是 PS MIO）
- 厂商 board automation 勾选 uart0/gpio/sd0/usb0/enet0（p.27）
手册里**没有**、仍属真实缺项：厂商 board_files/PS7 preset、PCB 原理图、PS_CLK 参考时钟频率、PS UART 的 MIO 分配、ENET0 PHY 型号/MDIO/RGMII/复位脚。

【已完成、不要重做】P4=4/0 与 P16=16/1 正式源集与参数、2022.2 真实 catalog 打包已通过；LC50 模块与真实 AXI 包装在 Windows2026.1 XSim 各两轮通过；47 项 G3 主机用例与工作树固件行为回归通过；Windows2026.1 旧 ECO XSA 软件兼容探针完成。都不能替代新板验收。

============ 你的本阶段任务（只做这些）============
目标：产出**可审计的 BKB220 板级来源表 + PS7 配置草案**，让 main 能据此审核并进入 F3 最小启动。

1. 完整阅读仓库内 BKB220 v1.1 手册 PDF（不是只看 main 摘要），按页码登记每条规格；运行 sha256sum -c 复核并把输出记进报告。
2. 审计现有板级入口：hw/boards/load_board.tcl、hw/boards/bkb220.tcl、hw/boards/zynq_eco_7010.tcl、hw/scripts/bd.tcl、hw/scripts/build.tcl、tools/run_vivado_build.sh、hw/constr/top.xdc。说明 load_board 的字段契约（id/ready/part/uart/xdc/source_refs/ps7_properties）与 bkb220 ready=0 的现有守卫逻辑（引用函数名/变量名，不要写行号）。
3. 新建 docs/board/bkb220/migration-source-table.md，至少包含：
   - 来源表：每条规格 → 出处（仓库文件路径 + 手册页码 / main 实测 / 待实物确认），严格区分「已证实」「手册给出」「仍缺」。
   - PS7 配置草案：候选 ps7_properties 逐条标注来源与确信度。DDR3 按 32bit / MT41K256M16TW-107 / 533.333MHz / 1GB 给出（CL/CWL/tRCD/tRP/tRC/tRAS/tFAW 按 -107 速度等级与 JEDEC DDR3-1066 常规值给出，并**注明是推导不是实测**）；UART/ENET0/QSPI/SD/USB 分别给「手册支持」与「待实物确认」两类。
   - 进入 F3 前仍缺的硬缺项清单（至少含 PS_CLK 频率、PS UART MIO、ENET0 PHY/MDIO/RGMII/复位、厂商 preset/原理图、DDR 板级延迟与 DQS-to-CLK）。
   - F3 最小启动计划：如何用「UART 打印 / DDR 训练与安全区读写 / GEM 链路 / CAPS」逐步**经验性确定**上述缺项（例如 JTAG 模式下载最小 hello 固件、遍历候选 UART MIO 与 COM 口号），每步的判据与失败分类，并标明哪些步骤由 main 持板执行。
4. 更新 hw/boards/bkb220.tcl：结构完整、语法正确的 profile（id/ready/part/uart/xdc/source_refs/ps7_properties/pending），**ready 保持 0**；part 用 xc7z020clg400-2，但手册写的是工业级 XC7Z020-2CLG400I，请把速度等级/温度等级的不确定性写进注释或 pending，不要静默当已证实。若 xdc 复用 hw/constr/top.xdc，在来源表说明理由（该 xdc 无 PL 外部引脚、时钟来自 PS7 FCLK_CLK0）。
5. 用 tclsh 跑配置预检（如 `tclsh hw/scripts/build.tcl board=bkb220 dry_run=1` 或仓库等价入口），验证 ready=0 时必须在 create_project 前明确失败且错误信息可读。记录实际命令与完整输出。

【独占路径】hw/boards、hw/constr、hw/scripts/bd.tcl、hw/scripts/build.tcl、tools/run_vivado_build.sh、sw/scripts、sw/app、sw/linker，以及新文件 docs/board/bkb220/migration-source-table.md。不要改其他角色独占文件（hw/sim、tests、tools/board、run_g3.sh 归 verify-system；IP hdl/component.xml 归 rtl-16way）；不要改 docs 根目录 01～09（归 main）；不要碰 data/、archive/、hw/build/export/、既有 run 目录。

【资源许可】不授权任何板卡操作与 Vivado 综合/实现。只允许只读命令、tclsh 预检、pdftotext、sha256sum、只读 git。
【验收出口】① 来源表完整、每条有出处、缺项不含糊；② bkb220.tcl 语法正确且 ready=0 守卫仍生效、预检失败信息可读；③ F3 计划有可执行步骤与判据；④ 报告写明实际命令、退出码、改动文件路径、PASS/FAIL/未测、仍缺项与下一步依赖。收工前 tools/agent_view.sh done --agent board-migrate，并在最终答复给出完整摘要。