> 脱敏副本，原件 `20261012T111652Z-40a8ed6c3d/{prompt.txt,answer.md}`。本机绝对路径、邮箱、凭据形模式及非白名单私网 IP 已替换；除脱敏与换行规范化外保留原文。

你是本项目的 verify-system 子Agent（任务短名/看板名：verify-system）。先完整阅读 docs/agent-prompts/verify-system.md（你的角色提示词全文）、AGENTS.md、CLAUDE.md，再读 docs/02-data-contract.md、docs/04-interfaces.md、docs/03-status.md、docs/05-implementation-plan.md、docs/06-verification-plan.md、docs/07-board-build-and-acceptance.md、docs/08-performance-and-strategy.md、docs/09-evidence-ledger.md、tools/README.md、tests/host/README.md。

【重要：你是 read-only 任务】看板由 main 代登记（已登记为 verify-system，进行中），你**不要**运行 tools/agent_view.sh，也**不要写任何文件**。所有结论在最终答复里交付给 main，由 main 归集。禁止 Git 写操作、不建分支/worktree、不改被测生产 RTL/固件、不改 data/archive/黄金参考来掩盖失败、不触板（JTAG/串口/下载/reset/dump/串口采集全归 main）、不跑大型仿真（须 main 授权）、不派生 Agent。

============ 阶段卡（2026-10-12，main 已实测核对）============
当前 HEAD：22a0874fbd64bce3354a2f27c6f1584740dd4a0a，main == origin/main（0/0）。
本阶段：F1 复核 + F4～F8 准备。核心是**把现用板测/性能/故障脚本审计成可用于新板的形态**，因为一旦 board profile 通过，main 会立刻用它们做新板 G3。

【main 实测的新板现场】BKB220 板载 FT4232HL：JTAG 单目标 xc7z020（IDCODE 0x23727093）；Windows 串口只有 COM9/COM10/COM11（FT4232H 通道 B/C/D，序列号 15051B/C/D），**没有**旧板的 CH340/COM6；Windows 侧 ASIX USB 千兆网卡「以太网 2」= <内网IP已脱敏>/24，链路 Up 1Gbps、ReceivedBytes=0；Windows 2026.1 的 xsdb 在 <本机路径> Vivado/Vitis 2022.2 为主开发链。目标仍 SE150、100MHz、几何 150/50/807/957/64、P4=4/0、P16=16/1、最终图片 SHA fcd0cf90bd680e7bbdc203e3398119504da0897acac9e2117008b4efb6b1f2c3、SE150 当前 51781 源读段 / 正反向与 64 补帧后 103616 板端记录。

【已完成、不要重做】47 项 G3 主机用例与工作树固件行为回归通过；LC50 独立 oracle 与真实 AXI 包装接口两轮 XSim 通过；旧板 SE150 全量真板闭环（中位数 25.69s、2016 源读段/s、103616 板端记录）。旧 stress_test_suite.py / switch_export.sh 已成对原样归档至 docs/archive/tools/2026/retired-20261011，不再是现用入口。

============ 你的本阶段任务（只做这些，全部只读）============
A. 硬编码与旧板假设审计（本次最重要）：
   逐个审计这些现用入口，列出每一处**旧板/旧环境硬编码**及其在默认值中的位置，并判断缺省运行时会不会静默用错目标：
   - tools/run_g3.sh（重点看默认 XSDB_VALUE、JTAG_DEVICE、UART_PORT、BOARD_IP、ARTIFACT_DIR、READS_FILE，以及 --artifact-dir/--xsdb/--device/--uart-port/--ip 的校验强度：给了新值但缺 --artifact-dir 时会怎样？给错 device 会不会静默连上？）
   - tools/board/ 下 g3_artifacts.py、g3_wait_ready.py、g3_recovery_probe.py、g3_config_guard_probe.py、g3_netfault_probe.py、g3_performance_matrix.py、g3_overhead_sweep.py、g3_uart_cap.ps1、g3_xsdb.ps1、read_pipe_counters.tcl、arm_baseline.py
   - tools/run_demo.sh、run_multi_payload_regression.py、run_robustness_scan.py、g5_false_accept.py、run_g5_matrix.sh、run_cpu_benchmark.py
   对每一处给出：文件、符号/变量名（引用代码位置写标识符，不要写行号）、当前旧值、新板应对应的值或「须由 main 在运行期显式传入」、以及**如果忘记传会静默走旧值还是明确失败**。特别确认：能否传蓝牙 COM3/COM4 或随便一个 COM 号而不被发现；能否用 xc7z010 的 device 名连上新板 xc7z020。
B. 最小启动（F3）与 P4 基线（F4）的判据清单：
   按 docs/06 与新板实际，列出 main 从「最小 UART/DDR/GEM/CAPS」到「新板 P4 全量 G3」每一步的：入口命令（含新板应填的参数占位）、PASS 判据、失败分类（functional/communication/tooling/boundary_expected/fault_injection_expected）、留下的证据文件、以及**这一步的判据有没有鉴别力**（即：错误的板配置/错误的串口/错误的 device 会不会让它变红）。指出当前工具链里**判据鉴别力不足**的环节（例如只验证包内 SHA 一致而不能发现源码到制品不同源）。
C. 需要 main 或 board 配合的适配项：
   把「必须改代码才能适配新板」的项与「只需运行期传参」的项分开列。前者给出建议的最小改动范围与它会影响哪些已通过结论（注意：改 tools/ 属你的独占路径，但本阶段是 read-only，你只提方案不写文件；实际改动等 main 授权后另派 workspace-write 任务）。同时指出哪些脚本在旧板上从未适配过新板默认几何/P_WAYS，直接跑会有假结论风险。
D. fixture 负用例现状：核对 tools/board/g3_artifacts.py 与 tests/host 下的 G3 用例，说明错 part / 错几何 / 缺制品 / SHA 不符 / manifest 缺字段 / 非法 P16 组合 这几类负用例**当前是否真的被拒绝**，以及新板 xc7z020 加入后是否有新的负用例缺口（例如 part 从 xc7z010 换成 xc7z020 后，原来「错 part 必须拒绝」的用例是否仍然有效）。

【判据纪律】不接受「应该没问题」：每条结论给出文件+符号名+默认值证据。区分 PASS / FAIL / 未测。不把主机替身当板测，不把仿真当整机。
【验收出口】最终答复给出：① 硬编码审计表（含「静默走旧值 vs 明确失败」判定）；② F3/F4 判据清单与鉴别力缺陷；③ 必须改代码 vs 只需传参 的分项；④ 负用例缺口。不要写文件。