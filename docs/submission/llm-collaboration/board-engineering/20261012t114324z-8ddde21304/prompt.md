> 脱敏副本，原件 `20261012T114324Z-8ddde21304/{prompt.txt,answer.md}`。本机绝对路径、邮箱、凭据形模式及非白名单私网 IP 已替换；除脱敏与换行规范化外保留原文。

你是 board-migrate（看板名 board-migrate）。这是**第二阶段任务**，第一阶段你已交付 docs/board/bkb220/migration-source-table.md 与 hw/boards/bkb220.tcl（ready=0），main 已独立复核通过（profile schema 8 字段 29 对属性、`tclsh hw/scripts/build.tcl board=bkb220 dry_run=1` exit=1 在 create_project 前拒绝且未建目录）。不要重做第一阶段。

先读 docs/agent-prompts/board-migrate.md（角色全文）、AGENTS.md、CLAUDE.md、你那两份产物，以及 tools/README.md。

【看板】workspace-write，自己 `tools/agent_view.sh start --agent board-migrate --doing ... --why ... --next ...`，阶段 update，受阻 block，收工 done。
【禁止】任何 Git 写操作；不建分支/worktree；不派生子 Agent；**不触板**（JTAG/串口/下载/reset/DDR dump 全归 main）；不修改第一阶段已交付的两份文件的结论（可追加§新章节）。
【更正】不要运行 `tools/verify_repo_binding.sh`（那是 main 的门禁，沙箱把 git 目录挂只读，跑了必失败）。

============ main 已实测的现场（直接采信）============
- 板卡已由 main 在 JTAG 上确认并可安全访问：链 `Xilinx HW-Z1-ZCU104 FT4232H 15051A` → `arm_dap (4ba00477)` → `xc7z020 (23727093)`。走 WSL：usbipd 直通后 `<本机路径>`=JTAG、`<本机路径>`=三个串口；Linux hw_server 2022.2 在 `TCP:127.0.0.1:3132`。
- **BOOT_MODE = 0（JTAG 模式）**，PS 处于干净的 JTAG 待机态：`DDR_PLL_CTRL=0x3F`（DDR PLL 掉电）、`FPGA0_CLK_CTRL` bit0=0（FCLK0 关）、`GEM0_NETWORK_CONTROL=0`、`UART0/1_CTRL=0x128`（都关）。CPU 在跑 BootROM。
- **PS_CLK = 33.333 MHz**：main 从 `IO_PLL_CTRL` FBDIV=26 推出 IO PLL=433.33 MHz。BootROM 能正常跑本身就说明 PS_CLK 是标准 33.333 MHz。请把它写进你的来源表（标为「推导+可复现的寄存器证据」，不是厂商书面确认）。
- 旧板 MIO 寄存器格式参考（本仓库 sw/workspace/dna_platform_b27/hw/ps7_init.tcl）：MIO_PIN 值 = (IO_Type<<12)|(L3_SEL<<9)|(L2_SEL<<6)|(L1_SEL<<3)|L0_SEL。旧板 UART1 在 MIO48/49 写作 `0x12E0/0x12E1`，MDIO 在 MIO52/53 写作 `0x1280`。**这是旧板（7010/1.8V bank）的值，不能直接套新板。**

============ 本阶段唯一目标 ============
让 main 能立刻在真板上做 F3 最小启动，为此产出**经过真实 Vivado 2022.2 catalog 验证的 PS7 配置**与**可下载的 ps7_init 候选**。

具体做四件事：

**A. 用真实 Vivado 2022.2 验证候选 PS7 属性（最高优先级）**
显式用 `VIVADO_ROOT=<本机路径>`（或 `VIVADO`），在一个**全新、独立的目录**（建议 `hw/build/bkb220-ps7-probe/<run-id>/`，不要碰 `hw/build/export/`）跑 Vivado batch。做一个**只有 PS7 的最小工程**（不综合、不实现、不跑 BD 之外的东西），把 hw/boards/bkb220.tcl 里那份候选 `ps7_properties` 逐条 `set_property` 应用到 `processing_system7_0`，然后 `generate_target`（或等价方式）产出 `ps7_init.tcl`/`ps7_init.html`/`.xci`。
必须逐条记录：
- 哪些属性名 Vivado **接受**、哪些**报错或警告**（原文引用日志）。
- **`CONFIG.PCW_UIPARAM_DDR_PARTNO {MT41K256M16TW-107}` 是否被 catalog 接受**？如果被拒，列出 catalog 里可用的最接近项，并说明差异（这是硬阻塞项，必须查清）。
- `PCW_PRESET_BANK0_VOLTAGE`/`BANK1_VOLTAGE`、`PCW_QSPI_GRP_SINGLE_SS_IO`、`PCW_UIPARAM_DDR_*` 时序值的接受情况。
- Vivado 对 32bit/1GB DDR 组合实际生成的参数（tRC/tRAS/tFAW/CL/CWL 等）与你的草案是否一致；不一致要如实记录 Vivado 的取值。
- **part `xc7z020clg400-2` 是否在 2022.2 器件库中**；手册写的是工业级 XC7Z020-2CLG400I，请查清 2022.2 里工业级该怎么写（是 part 后缀还是单独属性），不要猜。

**B. 产出 4 个 UART 候选变体（供 main 在板上逐一试）**
PS UART 的 MIO 分配是手册没给、必须实测确定的项。请在同一 Vivado 流程里生成 **4 套独立的 ps7_init**，各自独立目录，除 UART 外其余配置完全相同（含 DDR 与 ENET0）：
- `v1-uart0-mio14-15`：UART0，MIO 14..15
- `v2-uart0-mio46-47`：UART0，MIO 46..47
- `v3-uart1-mio08-09`：UART1，MIO 8..9
- `v4-uart1-mio48-49`：UART1，MIO 48..49
每个变体标明对应的属性写法（如 `CONFIG.PCW_UART0_UART0_IO {MIO 14 .. 15}`）与生成结果。若某个组合 Vivado 不接受，如实记录并跳过。
**同时把 ENET0 配成候选**：`CONFIG.PCW_ENET0_PERIPHERAL_ENABLE {1}`、`PCW_ENET0_ENET0_IO {MIO 16 .. 27}`、`PCW_ENET0_GRP_MDIO_ENABLE {1}`、`PCW_ENET0_GRP_MDIO_IO {MIO 52 .. 53}`、`PCW_ENET0_PERIPHERAL_FREQMHZ {1000 Mbps}`——这是 Zynq RGMII 的标准接法、也与旧板一致，但**手册没给，属于待实测确认的候选**，请在报告里明确标注为「候选，需 main 用 MDIO 读 PHY ID 验证」。
UART 一律 115200 8N1。

**C. 写一份 main 可直接照做的 F3 上板清单**
写进 docs/board/bkb220/migration-source-table.md 的**新增章节**（不要改动已有章节的结论），内容：
- 每个变体的 ps7_init 路径与 SHA256。
- main 在板上试一个变体的**确切步骤**：用 xsdb 连 `TCP:127.0.0.1:3132` → 选 APU 目标 → `rst -system` → `source <ps7_init.tcl>` → `ps7_init` → `ps7_post_config`；然后**串口判据**：在 WSL 侧同时监听 `<本机路径>` @115200，看哪个收到数据。注意 main 还需要一个能打印的固件；请说明「先只验证 DDR 训练是否成功（ps7_init 返回值/UART 打印的 DDR 校准信息），UART 通道归属用后续最小 hello ELF 确定」的分步顺序，并给出 DDR 训练成功/失败的判据。
- **风险提示**：`rst -system` 会复位整板；每试一个变体都要复位并重跑；如果 ps7_init 里 DDR 参数错，可能出现训练失败甚至挂死——请给出「失败后如何回到干净 JTAG 态」的恢复步骤。
**不要**在 Windows 侧起任何 hw_server（该机器今天因 Windows hw_server + FTDI 驱动蓝屏两次，用户已暂停该路径）。

**D. 不要做的事**
不要修改 hw/boards/bkb220.tcl 的 ready（保持 0）；不要生成 bit/XSA（那是 F4）；不要跑综合/实现；不要碰 data/、archive/、hw/build/export/、既有 run 目录。

【验收出口】报告里给出：① 候选 PS7 属性在 2022.2 的**逐条**接受/拒绝结果与实际日志；② DDR part 是否被接受及最终生效参数；③ 4 个 UART 变体的 ps7_init 路径+SHA+属性写法；④ ENET0 候选写法与其「待 MDIO 验证」的边界；⑤ main 的 F3 分步清单与恢复步骤；⑥ 实际命令、退出码、PASS/FAIL/未测。收工 `tools/agent_view.sh done --agent board-migrate`。