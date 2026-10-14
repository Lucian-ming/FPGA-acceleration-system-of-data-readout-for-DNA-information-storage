> 脱敏副本，原件 `20261012T125432Z-9c0526a62f/{prompt.txt,answer.md}`。本机绝对路径、邮箱、凭据形模式及非白名单私网 IP 已替换；除脱敏与换行规范化外保留原文。

你是 board-migrate（看板名 board-migrate）。第四阶段任务：**用 P4 的 XSA 生成完整的同源软件包**（F4 的软件侧）。前三阶段你已交付来源表/PS7 profile、4 套 UART ps7_init、以及 P4/P16 整机 100MHz 构建（均 PASS，已入库），不要重做。

先读 docs/agent-prompts/board-migrate.md、AGENTS.md、CLAUDE.md、docs/07-board-build-and-acceptance.md（**§3「工具链和同源制品」**与 §4）、docs/05-implementation-plan.md（F4 行）、docs/benchmarks/bkb220-p4-p16-100mhz-build.md、docs/board/bkb220/migration-source-table.md（**§9/§9.6/§10，含原理图核对**）。

【看板】workspace-write，自己 `tools/agent_view.sh start/update/block/done --agent board-migrate`，三字段具体。
【禁止】Git 写操作；不建分支/worktree；不派生 Agent；**不触板**（下载/reset/串口全归 main）；不改 docs 根目录 01～09；不要跑 `tools/verify_repo_binding.sh`（沙箱 git 只读必失败）。

============ 输入（已就绪，直接用）============
- **P4 XSA**：`hw/build/bkb220-p4-100mhz-20261012T123158Z-board-migrate-p4/export/dna_accel.xsa`（内含 bit；`PART=xc7z020clg400-2`）
- 同目录还有 `top_bd_wrapper.bit`、`hardware_build_config.txt`
- 板级配置：`hw/boards/bkb220.tcl`（`ready=1`，`uart ps7_uart_0`，part `xc7z020clg400-2`）
- **原理图核对结果（main 已实测+查图确认，可直接采信）**：PS UART = **UART0 / MIO14-15**，接 FT4232H **通道 C**（WSL `<本机路径>`），**115200 8N1**；ENET0 = **RGMII，PHY = Realtek RTL8211E**，**PHY 地址 = 1**，**PHY 复位 `PHYRSTB` 接 `PS_POR_B`（不是 GPIO，固件无需驱动）**；PS_CLK = 33.333 MHz。
- 实板已证实：`ps7_init`/`ps7_post_config` RC=0、DDR 读写可用、UART 通道可收发、MDIO 可读 PHY（1000BASE-T 全双工 link up）。

============ 本阶段任务 ============
按 docs/07 §3 的规则，用 **WSL Vitis/XSCT 2022.2**（`<本机路径>`，ARM GCC 在 `gnu/aarch32/lin/gcc-arm-none-eabi`）在**全新独立目录**生成 P4 的完整同源软件包：

1. **BSP**：从上述 P4 XSA 生成 `ps7_cortexa9_0` / `standalone` / **lwip220** 的 BSP。
2. **应用 ELF**：编译 `sw/app/`（**sw/app 是唯一权威源，不要改生成副本**）。注意 07 的要求：
   - 排除 `sw/app/xparameters.h` 历史快照；用**实际 BSP** 生成的地址/查询键；
   - SDT 全局计时器与共享 GIC 用实际 BSP 的，不要另造私有控制器；
   - `stage1_dna.c` 的 30 秒墙钟超时先转 **64 位**再比较，禁止 SCU/TTC 短计数回绕；
   - 保持网络/cache/DMA 寄存器行为不变。
3. **FSBL**、**BOOT.bin**（用 bootgen，含 bit + FSBL + ELF）。
4. **readback 核验**与 **六制品 SHA256SUMS**。
5. **manifest**：产出 G3 用的 `artifact_manifest.json`，字段以 `tools/board/g3_artifacts.py` 实际读取的为准（XSA 内 bit/part/HWH 七参数、源码 manifest、工具版本、几何、P_WAYS/PIPE_TREE、SHA）。可用 `python3 tools/board/g3_artifacts.py --artifact-dir <你的包目录>` 自查（**只读预检**，它会告诉你缺什么）。
6. **软件构建摘要**：记录实际命令、退出码、工具版本、成功哨兵、非空产物、Bootgen readback 结果。

**硬要求**：不能只靠 launcher `exit 0` 就算成功——必须有**成功哨兵 + build 状态 0 + 实际非空产物 + readback + 六 SHA**。若某一步只能做到部分，如实说明卡在哪、缺什么。

**边界**：不要做 Windows 2026.1 的软件重建（那是 F9）；不要下载到板子；不要改动 `sw/app` 的语义行为（只做 07 明确要求的 SDT/64 位兼容性修改，且必须跑工作树固件行为回归 `bash tests/host/run_host_tests.sh --worktree` 证明行为未变）。

============ 报告要求 ============
① 完整命令、退出码、产物路径与大小；② 六制品与 manifest 的 SHA 核验结果；③ 成功哨兵原文；④ 你对 `sw/app` 做的任何改动及行为回归结果（无改动也要明说）；⑤ 明确 PASS/FAIL/未测；⑥ 给 main 的板测移交清单：用哪个 ELF/ps7_init/bit、UART 端口、预期能观察到的启动打印。收工 `tools/agent_view.sh done --agent board-migrate`。