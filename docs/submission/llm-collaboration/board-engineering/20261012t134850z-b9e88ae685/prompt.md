> 脱敏副本，原件 `20261012T134850Z-b9e88ae685/{prompt.txt,answer.md}`。本机绝对路径、邮箱、凭据形模式及非白名单私网 IP 已替换；除脱敏与换行规范化外保留原文。

你是 board-migrate（看板名 board-migrate）。第五阶段任务（**方案已由 main 变更，覆盖上一轮的 CONFIG_LINKSPEED1000 思路 —— 那个任务已取消**）：**把 lwip220 里修好的 Realtek PHY 实现移植进 lwip211，修掉 F4 板测暴露的自协商失败。**

先读 **`docs/board/bkb220/migration-source-table.md` §11（必读）**、docs/07（含 §3a 分工）、AGENTS.md、CLAUDE.md。

【看板】workspace-write，自己 `tools/agent_view.sh start/update/block/done --agent board-migrate`。
【禁止】Git 写操作；不建分支/worktree；不派生 Agent；**不触板**；不改 docs 根目录 01～09；不跑 `tools/verify_repo_binding.sh`。

============ main 已完成的取证（可直接采信，不必重做）============
**失败现象**（板端 uart.log 实录）：
```
Start PHY autonegotiation / Waiting for PHY to complete autonegotiation.
Auto negotiation error / Phy setup error / Phy setup failure init_emacps
```
→ BSP `xemacpsif_physpeed.c` 的 `get_Realtek_phy_speed()` 等 `BMSR bit5` 30 秒超时 → `phy_setup_emacps` 失败 → **GEM0 从未启用** → 应用起得来但网络不通。

**根因方向**：本机安装的 `lwip211_v1_8` 里那版 `get_Realtek_phy_speed()` 与报错的 PHY（**RTL8211E-VL**，原理图 p.15）不适配。**同一份 lwip211 源码在旧板上没走过 Realtek 分支**（旧板 PHY 非 Realtek），所以历史上没暴露。

**关键本地资料（不必上网）**：本机有更新版 lwIP 2.2.0（`lwip220_v1_4`）的同一文件，Realtek 部分被重写过：
```
<本机路径>
```
（原始对照副本在 `.../lwip-original-repo/ThirdParty/sw_services/lwip220_v1_4/...`）

**main 已核对的版本差异**：
- `xemac_ieee_reg.h` 的 `IEEE_*` 宏在两版之间**完全相同**（`IEEE_SPECIFIC_STATUS_REG=17`、`IEEE_SPEED_MASK=0xC000`、`IEEE_SPEED_1000=0x8000`、`IEEE_SPEED_100=0x4000`、`IEEE_CTRL_RESET_MASK=0x8000`、`IEEE_STAT_AUTONEGOTIATE_COMPLETE=0x0020`、`IEEE_RGMII_TXRX_CLOCK_DELAYED_MASK=0x0030`）。**所以移植不需要动宏，只动 .c 实现。**
- lwip220 把 Realtek 路径拆成了 `Configure_Phy_Speed()` + **`Reset_Realtek_Phy()`** + `Wait_Autoneg_Complete()` + 重写的 `get_Realtek_phy_speed()`。
- lwip211 原来的写法是：写 ANAR/GBCR → 写 BMCR(自协商使能+重启) → **再写 BMCR 软复位** → 等自协商；lwip220 在复位后加了 **`sleep(1)` 稳定延时**，并把等待抽成带超时参数的 `Wait_Autoneg_Complete()`。

============ 本阶段任务 ============
**目标：让板端 uart.log 出现 `autonegotiation complete`（不再是 `Auto negotiation error`），从而让 GEM0 起来。**

1. **先做代码级取证**（别急着改）：逐行读通 lwip220 的 `Configure_Phy_Speed` / `Reset_Realtek_Phy` / `Wait_Autoneg_Complete` / `get_Realtek_phy_speed`，与 lwip211 的对应实现做**逐行对照**，明确写出：
   - **到底哪些差异是"修 bug"，哪些只是重构**；
   - 哪些是 lwip220 新增、而 lwip211 没有的依赖（宏、函数、头文件）；`Configure_Phy_Speed` 在 lwip220 里还被谁调用（移植时要保证 lwip211 侧编译得过）。
   **如果对照下来你认为差异不足以解释超时**，**如实说明**并给出你认为真正的原因 —— 不要为了交差硬说"移植就能修"。
2. **做最小忠实移植**：把 lwip220 的实现移植进 **lwip211** 的 `xemacpsif_physpeed.c`。**不要整文件替换**（两版 lwIP 主版本不同，整替必然编译不过）。
   - 改的是**安装树**里那份：`<本机路径>`（该文件当前可写）。
   - **改前先按社区/Digilent 的惯例做 `.orig` 备份**，并在报告里给出备份路径与原文件 SHA。
   - 补丁要**尽量小且可读**，在改动处加注释说明「来自 lwip220 的对应实现，为什么改」。
3. **必须新建 BSP 工程重新生成**（不要只在旧工程上 `make` —— 社区反复强调这种补丁在既有工程里重建不生效）。**用同一份 P4 XSA**（硬件没变，不要重综合），产出**独立的新软件包**：BSP + 应用 ELF + FSBL + BOOT.bin + bootgen readback + 六制品 SHA + `manifest.json`。
   - 必须过 `python3 tools/board/g3_artifacts.py --artifact-dir <新包>` 预检。
   - 应用侧仍用 `sw/app`（唯一权威源）；`sw/app` 若无需改动就明说。
4. **给 main 明确的板测判据**：看 uart.log 的哪一行、期望变成什么；如果还是失败，日志应该出现什么新行。**把"这次改动若无效，下一个该看什么"也写上。**

【硬要求】
- 不许放宽门禁；不许静默改 `sw/app` 语义（若改了，列出逐处并跑 `bash tests/host/run_host_tests.sh --worktree`）。
- **保留原始失败证据**；安装树原文件必须留 `.orig` 备份，**且要在报告里写清如何回滚**。
- 诚实区分：**代码事实 / 推断 / 未测**。本轮不可能有板测结论（不触板），不要暗示已修好。

【报告要求】① 逐行对照结论（哪些是 bug 修复、哪些是重构、哪些不足采信）；② 补丁 diff 全文与安装树改动前后 SHA、`.orig` 路径与回滚方法；③ 新包路径、六制品 SHA、`g3_artifacts.py` 预检；④ 给 main 的板测判据与下一手；⑤ PASS/FAIL/未测。收工 `tools/agent_view.sh done --agent board-migrate`。