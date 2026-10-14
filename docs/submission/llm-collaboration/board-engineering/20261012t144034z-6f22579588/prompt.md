> 脱敏副本，原件 `20261012T144034Z-6f22579588/{prompt.txt,answer.md}`。本机绝对路径、邮箱、凭据形模式及非白名单私网 IP 已替换；除脱敏与换行规范化外保留原文。

你是 board-migrate（看板名 board-migrate）。第七阶段任务：**重建 P16 硬件包与同源软件包**（因为现有 P16 XSA 建于 ENET0 配置修复之前，同样缺配置）。

先读 **`docs/board/bkb220/migration-source-table.md` §12、§13（必读）**、docs/07（含 §3a 分工）、docs/benchmarks/bkb220-p4-p16-100mhz-build.md、AGENTS.md、CLAUDE.md。

【看板】workspace-write，自己 `tools/agent_view.sh start/update/block/done --agent board-migrate`。
【禁止】Git 写操作；不建分支/worktree；不派生 Agent；**不触板**（板卡现在归 main，正在跑全量三轮）；不改 docs 根目录 01～09；不跑 `tools/verify_repo_binding.sh`。

**★ 重要：main 此刻正在板上跑 P4 全量三轮 G3，占用板卡与串口。你只做构建，绝不碰板、不碰串口。**

============ 背景（main 已查明并已修，直接采信）============
`hw/boards/bkb220.tcl` 此前**缺 4 行 ENET0 MIO 属性**，导致 `ps7_init` 不配 MIO16-27/MIO52-53、板上 MDIO 引脚没 mux、以太网必不通。main 已补回（profile 现 35 对属性）并重建了 **P4**：

- 已通过的 P4 包：`hw/build/bkb220-p4-enet0-software-20261012T140800Z-board-migrate/`（其 `ps7_init.tcl` 已确认含 `0xF80007D0/D4 = 0x1280`，板端 G3 **7/7 全绿**）。
- **P16 的旧 XSA（`hw/build/bkb220-p16-100mhz-20261012T123936Z-board-migrate-p16/`，20:49 生成）早于该修复，因此同样缺配置，不能用。**

============ 本阶段任务 ============
1. **重建 P16 硬件包**（**全新独立目录**，不覆盖旧的）：
   ```
   VIVADO_ROOT=<本机路径> bash tools/run_vivado_build.sh \
     board=bkb220 part_name=xc7z020clg400-2 clk_mhz=100 \
     stage1_p_ways=16 stage1_pipe_tree=1 \
     build_dir=<全新> export_dir=<全新> report_dir=<全新>
   ```
   报告：route 完成、**WNS/WHS/TNS/THS、失败端点、DRC、资源占用、`clk_fpga_0`=100MHz**。
   **参照系**：修复前那次 P16 是 WNS +0.617 / WHS +0.017 / 失败端点 0 / 33,987 LUT(63.89%) / DRC 0 errors。ENET0 修复只动 PS7 配置、PL 网表不应变，所以**预期与那次基本一致**——但仍要实测复核，不要假设。

2. **★ 核心自查（必须给出 grep 实际输出）**：新 P16 包 `export/ps7_init.tcl` 里
   **必须能查到 `0xF80007D0` 与 `0xF80007D4` 且值为 `0x1280`**，以及 MIO16-27 的 RGMII 行。
   **若是 0 行，立刻停下报告 main，不要继续做软件包。**

3. **重建同源软件包**（独立新目录）：BSP（standalone；lwIP 用安装树实际提供的 `lwip211`）+ 应用 ELF（`sw/app` 权威源）+ FSBL + BOOT.bin + bootgen readback + 六制品 SHA + `manifest.json`。
   必须过 `python3 tools/board/g3_artifacts.py --artifact-dir <新包>` 预检，并**在报告里确认 `C_STAGE1_P_WAYS=16 / C_STAGE1_PIPE_TREE=1`**（这是区分 P16 与 P4 的关键字段）。
   XSCT `app create` 若仍因本地 socket 被拒而退出 1，**如实说明并沿用同样的直接 GCC 构建方式**，不要假装成功。

4. **给 main 的板测移交清单**：新 P16 包的 bit / ps7_init / ELF 路径与 SHA；以及"怎么确认板上加载的是 P16 而不是 P4"（例如 manifest 里的 P_WAYS、或 XSA/HWH 七参数）。

【硬要求】
- 不许放宽门禁；不许改 `sw/app` 语义（改了要列逐处并跑 `bash tests/host/run_host_tests.sh --worktree`）。
- 保留旧 P16 包与失败证据，不删。
- 诚实区分 **已测 / 未测**：本轮不触板，**不得暗示 P16 已上板或已通过验收**。

【报告要求】① 新 P16 包命令/退出码/路径 + 时序与资源（并与修复前那次对照）；② **新 ps7_init 的 ENET0 MIO grep 实际输出**；③ 新软件包路径、六制品 SHA、`g3_artifacts.py` 预检结论（含 P_WAYS/PIPE_TREE）；④ 板测移交清单；⑤ PASS/FAIL/未测。收工 `tools/agent_view.sh done --agent board-migrate`。