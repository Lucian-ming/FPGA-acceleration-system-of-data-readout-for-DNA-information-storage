> 脱敏副本，原件 `20261012T131141Z-39a08a710a/{prompt.txt,answer.md}`。本机绝对路径、邮箱、凭据形模式及非白名单私网 IP 已替换；除脱敏与换行规范化外保留原文。

你是 board-migrate（看板名 board-migrate）。第四阶段任务重派：**用 P4 的 XSA 生成完整同源软件包**。

**上一轮你因「lwip220 不在 Vitis 2022.2 安装树」而 block —— 那不是你的错，是 main 阶段卡写错了。** main 已核实并更正：**Vitis 2022.2 只有 lwip211_v1_5/1_6/1_7/1_8；仓库自己的 `sw/scripts/create_vitis.tcl` 本就按 `lwip213 → lwip211 → lwip210` 回落；旧板已验证的 BSP 用的正是 `lwip211_v1_8`。lwip220 属于 Windows 2026.1（F9）路径。** 该任务已取消，你的部分产物保留着，本轮继续用。你上一轮"不静默替换、如实 block"是**正确行为**，继续保持这个纪律。

**你上一轮已完成的准备工作**（在 `hw/build/bkb220-p4-software-20261012T130201Z-board-migrate-f4/`，可直接复用、不要重做）：
`export/{dna_accel.xsa, top_bd_wrapper.bit, ps7_init.tcl, hardware_build_config.txt}`、
`reports/partial_hardware_inputs.sha256`、`reports/source_snapshot.sha256`、
`logs/{toolchain-probe.log, ps7_init_vs_f3_probe.diff, g3_preflight.log, host-tests.log}`。

先读 docs/agent-prompts/board-migrate.md、AGENTS.md、CLAUDE.md、**docs/07-board-build-and-acceptance.md（§3 已就地更正 lwIP 段落，请重读）**、docs/05-implementation-plan.md（F4 行）、docs/benchmarks/bkb220-p4-p16-100mhz-build.md、docs/board/bkb220/migration-source-table.md（§9/§9.6/§10）。

【看板】workspace-write，自己 `tools/agent_view.sh start/update/block/done --agent board-migrate`，三字段具体。
【禁止】Git 写操作；不建分支/worktree；不派生 Agent；**不触板**；不改 docs 根目录 01～09；不要跑 `tools/verify_repo_binding.sh`。

============ 本阶段任务：把 P4 同源软件包做完整 ============
用 **WSL Vitis/XSCT 2022.2**（`<本机路径>`；ARM GCC 在 `gnu/aarch32/lin/gcc-arm-none-eabi`），在上述 F4 目录里继续：

1. **BSP**：从 `export/dna_accel.xsa` 生成 `ps7_cortexa9_0` / `standalone` 的 BSP。
   **lwIP 版本按实际安装树选**——优先沿用 `sw/scripts/create_vitis.tcl` 现成的回落逻辑（会选 `lwip211`）；
   **在报告里明确写出实际选中的版本**，以及它与 26 路径 `lwip220` 的差异标注。不要为了对齐版本号而判失败。
2. **应用 ELF**：编译 `sw/app/`（**唯一权威源，不改生成副本**）。遵守 07：
   - 排除 `sw/app/xparameters.h` 历史快照，用实际 BSP 的地址/查询键；
   - SDT 全局计时器与共享 GIC 用实际 BSP；
   - `stage1_dna.c` 的 30 秒墙钟超时先转 64 位；
   - 保持网络/cache/DMA 寄存器行为不变。若必须改动 `sw/app`，改完**必须**跑
     `bash tests/host/run_host_tests.sh --worktree` 证明行为未变，并在报告里列出逐处改动与依据。
3. **FSBL**、**BOOT.bin**（bootgen，含 bit + FSBL + ELF）。
4. **readback 核验** + **六制品 SHA256SUMS**。
5. **G3 manifest**：产出 `artifact_manifest.json`，字段以 `tools/board/g3_artifacts.py` 实际读取为准；
   用 `python3 tools/board/g3_artifacts.py --artifact-dir <你的包目录>`（只读预检）自查，直到它接受。
6. **软件构建摘要**：实际命令、退出码、工具版本、成功哨兵、非空产物、readback 结果、实际 lwIP 版本。

**成功判据**（不能只看 launcher `exit 0`）：成功哨兵 + build 状态 0 + 实际非空产物 + Bootgen readback + 六 SHA。
**若仍卡住**：如实说明卡在哪一步、缺什么、你已排除什么，**不要**用替代版本或跳过门禁来"凑过"。

**不要做**：Windows 2026.1 软件重建（F9）；下载到板；改 `sw/app` 的语义行为。

============ 报告要求 ============
① 命令/退出码/产物路径与大小；② 六制品与 manifest 的 SHA 核验；③ 成功哨兵原文；④ **实际选中的 lwIP 版本**及与 lwip220 的差异说明；⑤ 对 `sw/app` 的任何改动 + 工作树行为回归结果（无改动也明说）；⑥ PASS/FAIL/未测；⑦ **给 main 的板测移交清单**：用哪个 bit/ps7_init/ELF、UART 端口 `<本机路径>`、预期启动打印、以及 G3 该传哪些参数。收工 `tools/agent_view.sh done --agent board-migrate`。