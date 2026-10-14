> 脱敏副本，原件 `20261012T111547Z-11872629a5/{prompt.txt,answer.md}`。本机绝对路径、邮箱、凭据形模式及非白名单私网 IP 已替换；除脱敏与换行规范化外保留原文。

你是本项目的 board-migrate 子Agent（任务短名/看板名：board-migrate）。先完整阅读 docs/agent-prompts/board-migrate.md（你的角色提示词全文）、AGENTS.md、CLAUDE.md，再读 docs/03-status.md、docs/05-implementation-plan.md、docs/07-board-build-and-acceptance.md、docs/02-data-contract.md、docs/04-interfaces.md。

【看板】你是 workspace-write 任务，动手前自己登记：
tools/agent_view.sh start --agent board-migrate --doing "..." --why "..." --next "..."
阶段变化用 update，受阻用 block，收工用 done。三个字段都要写具体内容。
【禁止】任何 Git 写操作（add/commit/pull/rebase/stash/reset/clean/push），不建分支/worktree。不派生任何子 Agent。不跑 Vivado 综合/实现（大型 EDA 任务须 main 授权）。

============ 阶段卡（2026-10-12，main 已实测核对）============
当前 HEAD：22a0874fbd64bce3354a2f27c6f1584740dd4a0a，main == origin/main（0/0）。
本阶段：F2（新板配置落实）。BKB220 已到货并连接，main 已在 JTAG 上实测确认。

【main 实测的现场事实，可直接采信，不必重测】
1. JTAG：板载 FT4232HL，XSDB(Windows 2026.1) 枚举链名 "Xilinx HW-Z1-ZCU104 FT4232H 15051A"，单目标 xc7z020，IDCODE 0x23727093。无第二个 JTAG 目标。
2. Windows 串口：COM9 / COM10 / COM11（FT4232H 通道 B/C/D，序列号 15051B/C/D）。WSL 内无 <本机路径> Windows 侧，板测走 Windows 工具）。
3. 网络：Windows 侧 ASIX USB 千兆网卡「以太网 2」= <内网IP已脱敏>/24，链路 Up 1 Gbps，但 ReceivedBytes=0（板端 PS 尚未发过包）。
4. 工具链：WSL Vivado 2022.2 = <本机路径> Vitis/XSCT 2022.2 = <本机路径> GCC 在 gnu/aarch32/lin/gcc-arm-none-eabi）；Windows 2026.1 = <本机路径> = <本机路径>

【仓库内产品手册已实测校验】docs/board/bkb220/BKB220产品手册v1.1.pdf，SHA-256 40b50e666ecab4ee83fbcfb1eea816a04a0989f73b001d9b9432e4778c8cd086，`sha256sum -c SHA256SUMS.txt` 通过。main 已用 pdftotext 抽取全文（755 行）核对，其中可采信的规格（务必自己在 PDF 里复核页码后再引用）：
- 器件 XC7Z020-2CLG400I（p.5-6）
- JTAG 由板载 FTDI FT4232HL 实现，无需外置下载器（p.7）
- DDR3：2 片 Micron MT41K256M16TW-107，每片 256M×16bit，总计 32bit 位宽 / 1GB，最高 533MHz(1066Mbps)，接 PS BANK502（p.9-10）
- QSPI：W25Q256 32MB，接 PS_MIO1..6（p.8-9）
- 启动：JTAG / QSPI / SD，由 BOOT_CFG 拨码选择（p.15）
- PS MIO 电压：VCCO_MIO0=3.3V、VCCO_MIO1=1.8V、VCCO_DDR=1.5V（p.8）
- PL 系统时钟引脚 U18、PL 侧 UART 引脚 F16/F17（p.17，注意这是 PL 引脚，不是 PS MIO）
- 厂商 board automation 勾选 uart0/gpio/sd0/usb0/enet0（p.27）
手册里**没有**、因而仍是真实缺项的：厂商 board_files/PS7 preset、PCB 原理图、PS_CLK 参考时钟频率、PS UART 的 MIO 分配、ENET0 PHY 型号/MDIO/RGMII/复位脚。

【已完成、不要重做】P4=4/0 与 P16=16/1 正式源集、参数与 2022.2 真实 catalog 打包已通过；LC50 模块与真实 AXI 包装在 Windows2026.1 XSim 各两轮通过；47 项 G3 主机用例与工作树固件行为回归通过；Windows2026.1 用旧 ECO XSA 做过软件兼容探针。这些都不能替代新板验收。

============ 你的本阶段任务（只做这些）============
目标：产出一份**可审计的 BKB220 板级来源表 + PS7 配置草案**，让 main 能据此审核并进入 F3 最小启动。**不要跑综合，不要触板**（JTAG/串口/下载/reset 全归 main）。

1. 完整阅读仓库内 BKB220 v1.1 手册 PDF（不是只看 main 给的摘要），按页码登记每条规格。运行 sha256sum -c 复核。
2. 读取并审计现有板级入口：hw/boards/load_board.tcl、hw/boards/bkb220.tcl、hw/boards/zynq_eco_7010.tcl、hw/scripts/bd.tcl、hw/scripts/build.tcl、tools/run_vivado_build.sh、hw/constr/top.xdc。说明 load_board 的字段契约（id/ready/part/uart/xdc/source_refs/ps7_properties）与 bkb220 ready=0 的现有守卫。
3. 产出新文件 docs/board/bkb220/migration-source-table.md，内容至少：
   - 来源表：每条规格 → 出处（仓库文件路径 + 手册页码 / main 实测 / 需实物确认），明确区分「已证实」「手册给出」「仍缺」。
   - PS7 配置草案：以 dict/list 形式给出候选 ps7_properties，逐条标注来源与确信度。DDR3 部分按 32bit / MT41K256M16TW-107 / 533.333MHz / 1GB 给出（CL/CWL/tRCD/tRP/tRC/tRAS/tFAW 等按 107 速度等级与 JEDEC DDR3-1066 常规值给出，并**注明是推导而非实测**）；UART、ENET0、QSPI、SD、USB 分别给出「手册支持」与「待实物确认」两类。
   - 明确列出进入 F3 前仍缺的硬缺项（至少含：PS_CLK 频率、PS UART MIO、ENET0 PHY/MDIO/RGMII/复位、厂商 preset/原理图、DDR 板级延迟与 DQS-to-CLK）。
   - F3 最小启动计划：如何用「UART 打印 / DDR 训练与安全区读写 / GEM 链路 / CAPS」逐步**经验性确定**上述缺项（例如：在 JTAG 模式下下载最小 hello 固件遍历候选 UART MIO 与 COM 口号），以及每步的判据与失败分类。说明哪些步骤需要 main 持板执行。
4. 更新 hw/boards/bkb220.tcl：写入结构完整、语法正确的 profile（id/ready/part/uart/xdc/source_refs/ps7_properties/pending），**ready 必须保持 0**，pending 里写清剩余缺项；part 用 xc7z020clg400-2（注意手册写的是工业级 XC7Z020-2CLG400I，请把速度等级/温度等级的不确定性写进 pending 或注释，不要静默当作已证实）。xdc 若复用 hw/constr/top.xdc，请在来源表说明理由。
5. 用 `tclsh hw/scripts/build.tcl board=bkb220 dry_run=1`（或仓库等价预检入口）验证：ready=0 时必须在 create_project 前明确失败，且失败信息可读。把实际命令与输出保存到你的报告里。

【独占路径】hw/boards、hw/constr、hw/scripts/bd.tcl、hw/scripts/build.tcl、tools/run_vivado_build.sh、sw/scripts、sw/app、sw/linker，以及新文件 docs/board/bkb220/migration-source-table.md。不要改其他角色独占文件（hw/sim、tests、tools/board、run_g3.sh 归 verify-system；IP hdl/component.xml 归 rtl-16way）。不要改 docs 根目录的 01～09 编号文档（归 main）。不要碰 data/、archive/、hw/build/export/、既有 run 目录。

【资源许可】本阶段不授权任何板卡操作（JTAG/串口/下载/reset/DDR dump）与 Vivado 综合。只允许只读命令、tclsh 配置预检、pdftotext、sha256sum、git status/read（只读）。若你判断某项必须触板，写进报告的 block 项交给 main。

【验收出口】① 来源表完整、每条规格有出处、缺项不含糊；② bkb220.tcl 语法正确、ready=0 守卫仍生效且预检失败信息可读；③ F3 最小启动计划有可执行步骤与判据；④ 报告写明：实际命令、退出码、生成/修改文件的路径、PASS/FAIL/未测、仍缺项与下一步依赖。结束时把结论写入 docs/board/bkb220/migration-source-table.md 并在最终答复里给出完整摘要（含你在看板上登记的状态）。收工前 tools/agent_view.sh done --agent board-migrate。