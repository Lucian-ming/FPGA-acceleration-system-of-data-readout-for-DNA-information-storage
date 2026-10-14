> 脱敏副本，原件 `20261012T140623Z-b3587145ed/{prompt.txt,answer.md}`。本机绝对路径、邮箱、凭据形模式及非白名单私网 IP 已替换；除脱敏与换行规范化外保留原文。

你是 board-migrate（看板名 board-migrate）。第六阶段任务：**用修好的 profile 重建 P4 硬件包与同源软件包**，供 main 重跑 F4 G3。

先读 **`docs/board/bkb220/migration-source-table.md` §12（必读，本轮全部依据）** 与 §11、docs/07（含 §3a 分工）、AGENTS.md、CLAUDE.md。

【看板】workspace-write，自己 `tools/agent_view.sh start/update/block/done --agent board-migrate`。
【禁止】Git 写操作；不建分支/worktree；不派生 Agent；**不触板**；不改 docs 根目录 01～09；不跑 `tools/verify_repo_binding.sh`。

============ main 已查明的根因（已修，直接采信）============
F4 板测失败的**真根因是配置缺失**：`hw/boards/bkb220.tcl` 里**从来没有那 4 行 ENET0 MIO 属性**
（`PCW_ENET0_ENET0_IO {MIO 16 .. 27}` / `GRP_MDIO_ENABLE {1}` / `GRP_MDIO_IO {MIO 52 .. 53}` / `PERIPHERAL_FREQMHZ {1000 Mbps}`），
所以 P4 的 `ps7_init.tcl` 对 **MIO16-27/MIO52-53 写入 0 行**，板上 MDIO 引脚没 mux → 驱动 `detect_phy` 扫不到 PHY → 自协商超时 → GEM 从未启用。

**main 已把那 4 行补进 `hw/boards/bkb220.tcl`**（写法取自你上一轮探针 `property-results.tsv` 里 `ACCEPTED_EXACT` 的原文），profile 现 **35 对属性**、`ready=1` 不变、无重复。**不要再改 profile**（要改先报告 main）。

============ 本阶段任务 ============
1. **重建 P4 硬件包**（**全新独立目录**，不要覆盖任何旧目录）：
   ```
   VIVADO_ROOT=<本机路径> bash tools/run_vivado_build.sh \
     board=bkb220 part_name=xc7z020clg400-2 clk_mhz=100 \
     stage1_p_ways=4 stage1_pipe_tree=0 \
     build_dir=<全新> export_dir=<全新> report_dir=<全新>
   ```
   报告：route 是否完成、WNS/WHS/TNS/THS、失败端点、DRC、资源占用、`clk_fpga_0` 是否 100MHz。
   （PL 网表预期不变，所以时序应与上一轮 P4 基本一致；**仍要实测复核，不要假设**。）

2. **★ 最关键的自查（必须做，且在报告里给出证据）**：新包 `export/ps7_init.tcl` 里
   **必须能查到 `0xF80007D0` 与 `0xF80007D4` 的写入且值为 `0x1280`**，以及 MIO16-27 的 RGMII 配置行。
   用 `grep -n` 把实际命中行贴进报告。**如果还是 0 行，立刻停下报告 main，不要继续做软件包。**

3. **重建同源软件包**（独立新目录）：BSP（standalone，lwIP 用安装树实际提供的 `lwip211`）+ 应用 ELF（`sw/app` 权威源）+ FSBL + BOOT.bin + bootgen readback + 六制品 SHA + `manifest.json`。
   必须过 `python3 tools/board/g3_artifacts.py --artifact-dir <新包>` 预检。
   应用构建与上一轮同样的现实约束（XSCT `app create` 因本地 socket 被拒）如仍存在，**如实说明并沿用同样的直接 GCC 构建方式**，不要假装成功。

4. **给 main 的板测移交清单**：新包的 bit / ps7_init / ELF 路径、SHA、以及"看 uart.log 哪一行判断是否修好"
   （期望 **`autonegotiation complete`** 且不再出现 `Auto negotiation error`）。
   另外明确：**若这次还是失败，下一个该看什么**（例如新 ps7_init 是否真的生效、PHY 地址是否被 detect_phy 认到）。

【硬要求】
- 不许放宽门禁；不许改 `sw/app` 语义（改了要列逐处并跑 `bash tests/host/run_host_tests.sh --worktree`）。
- 保留旧包与失败证据，不删。
- 诚实区分 **已测 / 未测**：本轮不触板，**不得暗示已修好**。

【报告要求】① 新 P4 包的完整命令/退出码/路径 + 时序与资源；② **新 ps7_init 里 ENET0 MIO 配置的 grep 实际输出**（这是本轮的核心判据）；③ 新软件包路径、六制品 SHA、`g3_artifacts.py` 预检；④ 板测移交清单与失败时的下一手；⑤ PASS/FAIL/未测。收工 `tools/agent_view.sh done --agent board-migrate`。