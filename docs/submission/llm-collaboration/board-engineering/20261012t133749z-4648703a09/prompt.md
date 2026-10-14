> 脱敏副本，原件 `20261012T133749Z-4648703a09/{prompt.txt,answer.md}`。本机绝对路径、邮箱、凭据形模式及非白名单私网 IP 已替换；除脱敏与换行规范化外保留原文。

你是 board-migrate（看板名 board-migrate）。第五阶段任务：**修 F4 板测暴露的 PHY 初始化失败**。前四阶段的成果（来源表/PS7 profile/4 套 ps7_init/P4+P16 整机 100MHz 构建/LwIP 软件包）都已交付并入库，不要重做。

先读 **`docs/board/bkb220/migration-source-table.md` 的 §11（必读，本轮全部依据）**、docs/07（含 §3a 分工）、docs/agent-prompts/board-migrate.md、AGENTS.md、CLAUDE.md。

【看板】workspace-write，自己 `tools/agent_view.sh start/update/block/done --agent board-migrate`。
【禁止】Git 写操作；不建分支/worktree；不派生 Agent；**不触板**（下载/reset/串口全归 main）；不改 docs 根目录 01～09；不要跑 `tools/verify_repo_binding.sh`。

============ main 已实测的现场（直接采信，§11 有完整证据）============
- **烧录链全通**：Windows 2026.1 XSDB 把 22 产出的 bit/ps7_init/ELF 下载成功，板端应用完整启动（DMA/lwIP/TCP server 都起来，打印 `Board IP: 192.168.1.10`、`*** Waiting for connections ***`）。
- **失败点**：串口实录开头三行 —— `Start PHY autonegotiation` / `Waiting for PHY to complete autonegotiation.` / **`Auto negotiation error`** / `Phy setup error` / **`Phy setup failure init_emacps`**。
- 定位到 BSP `xemacpsif_physpeed.c` 的 `get_Realtek_phy_speed()`：`while(!(status & IEEE_STAT_AUTONEGOTIATE_COMPLETE))` 30 次 `sleep(1)` 后返回 `XST_FAILURE`，导致 `phy_setup_emacps` 失败、**GEM0 从未启用**。
- **新旧 BSP 的 `lwipopts.h` 逐行相同**（都是 `CONFIG_LINKSPEED_AUTODETECT 1`），驱动源码同源；**旧板 10 份 UART 实录全都打出 `autonegotiation complete`，新板超时**。差别只在 PHY：新板 `PHYID1=0x001C` 走 **Realtek 分支**，旧板不是。
- **PHY 与连线都是好的**：main 从前端经 JTAG 读同一颗 PHY 得 `BMSR=0x796D`（bit5=1 自协商完成）、`ANLPAR=0xCDE1`、`GBTSTS=0x7800`（1000BASE-T 全双工）；Windows 侧 ASIX 网卡一直显示 1 Gbps link up。所以**是驱动的时序/写法在这颗 PHY 上拿不到结果**。
- 原理图 p.15 给了线索：**「RGMII clock timing control」+ `RXDLY`/`TXDLY` 带子**，PHY = **RTL8211E-VL**，PHY 地址 strap = 1。
- 已知 `configure_IEEE_phy_speed()`（**固定速率路径**）会写 **page2/reg0x15 的 RGMII 收发时钟延迟**（`IEEE_RGMII_TXRX_CLOCK_DELAYED_MASK`），而 AUTODETECT 路径**不碰**这些寄存器。

============ 本阶段任务 ============
**目标：让 `phy_setup_emacps` 成功，判据是板端 `uart.log` 出现 `autonegotiation complete`（而不是 `Auto negotiation error`）。**

1. **先做静态取证，别急着改**：
   - 完整读 `xemacpsif_physpeed.c` 里 `detect_phy()` / `phy_setup_emacps()` / `get_Realtek_phy_speed()` / `configure_IEEE_phy_speed()` 与 `xemacpsif_hw.c` 里 `phyaddrforemac` 的赋值路径，**确认驱动最终会用哪个 PHY 地址**（`detect_phy` 填 `phymapemac0[]`，取用循环是 `for (i=31;i>0;i--)`）。给出代码级依据，不要推断。
   - 确认 `CONFIG_LINKSPEED1000` 路径**具体会写哪些寄存器**（page/reg/value），并与 RTL8211E 手册的 RGMII 延迟要求对照。
2. **给出候选修复并做成可切换**：优先评估**把 BSP 的 `CONFIG_LINKSPEED_AUTODETECT` 换成 `CONFIG_LINKSPEED1000`**（走 `configure_IEEE_phy_speed`，会配 RGMII 延迟）。若你判断这条不足以解决，或需要 Realtek 专页配置，就给出你依据代码与 RTL8211E 手册得出的方案。**注意 Vitis 流程里 lwipopts 是由 BSP 配置生成的**——要用 `bsp config`（或改 `.mss` 后重生成）的方式做，不要只手改生成出来的 `lwipopts.h` 就交差。
3. **构建一个新的、独立的软件包**（新目录，不要覆盖 F4 那份），让 main 能直接拿去板测：bit/ps7_init 复用**同一份 P4 XSA**（不要重综合，硬件没变），重生成 BSP + 应用 ELF + FSBL + BOOT.bin + readback + SHA 清单 + manifest。**必须过 `python3 tools/board/g3_artifacts.py --artifact-dir <新包>` 预检。**
4. **说明预期与失败判据**：这次改动预期让 uart.log 出现 `autonegotiation complete` 并拿到 link speed；若仍失败，uart.log 会给出新的具体错误行。**把"看哪一行判断是否修好"写清楚给 main。**

【硬要求】
- 不许为了让门禁过而放宽门禁；不许静默改 `sw/app` 语义（若必须改，列出逐处改动并跑 `bash tests/host/run_host_tests.sh --worktree` 证明行为未变）。
- 若你**不能**确定哪条修复正确，**如实说明**并给出你已确认的代码事实与不确定点，不要赌一个改动了事。
- 保留原始失败证据，不删除。

【报告要求】① 你确认的驱动取值路径（含 PHY 地址）与代码依据；② 你选的修复、依据（代码行/手册页）、以及**为什么另一个方案不选**；③ 新包的路径、六制品 SHA、`g3_artifacts.py` 预检结果；④ 给 main 的板测判据（看哪一行、期望什么）；⑤ 明确区分 **已确认代码事实 / 推断 / 未测**。收工 `tools/agent_view.sh done --agent board-migrate`。