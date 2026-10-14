> 脱敏副本，原件 `20261012T152518Z-49ce406164/{prompt.txt,answer.md}`。本机绝对路径、邮箱、凭据形模式及非白名单私网 IP 已替换；除脱敏与换行规范化外保留原文。

你是子 Agent，看板名 **skill-package**。任务：**审阅并补齐参赛技能包**。上一轮你因误把仓库绑定门禁当自己的前置而阻塞退出（那是主会话漏写提醒，已写进 AGENTS.md，不怪你），现在已更正，请继续。

**【必须先读】不要运行 `tools/verify_repo_binding.sh`（含 `--remote`/`--require-synced`）。** 那是 **main 的门禁**，main 已代跑留证（见 `docs/03-status.md`）。codex 沙箱把 git 目录（本仓库 gitdir 是 `.git-data`）挂成**只读**，脚本写 `FETCH_HEAD` 必报 `Read-only file system` —— **沙箱特性，不是仓库故障**。`AGENTS.md`「子 Agent 的承载通道与模型」一节有同样说明。

【看板】workspace-write，动手前 `tools/agent_view.sh start --agent skill-package --doing "..." --why "..." --next "..."`，收工 `done`。
【禁止】Git 写操作；不派生子 Agent；**只写 `docs/submission/skill/` 及其子目录**（`docs/submission/ai-collaboration/` 归另一个 agent）；不改 docs 根 01～09；不改 `tools/`、`hw/`。

**背景**：本项目参加 2026 嵌入式芯片与系统设计竞赛 FPGA 赛道 AMD 自主选题初级组。「**大模型协作与技能包**」占 **15 分**，硬要求含 **`skill/README.md` 技能包**。

**现状**：`docs/submission/skill/` 下已有 **8 个技能包**，各有 README（部分带脚本）：`board-stage-evidence`、`board-bringup-debug`、`bottleneck-attribution`、`accel-vs-cpu-baseline`（含 `baremetal_baseline.tcl.in`）、`ai-agent-collaboration`、`ip-packaging-hygiene`、`claims-ledger`、`fpga-timing-probe`（含 `ooc_probe.tcl`），入口 `README.md` 也在。

**任务**：
1. **逐一审阅这 8 个包**，对每个回答：解决什么问题？触发条件写清了吗？步骤能照做吗？**判据是"会红"的吗**？有没有过时内容（还在讲旧板 XC7Z010、旧 export 路径、SE250、或与本轮 BKB220/P16 现实不符的地方）？
2. 产出 `docs/submission/skill/AUDIT.md`：逐包结论 + **缺口清单（按价值排序）**。
3. **按价值补齐**：优先补与本轮新板工作直接相关的（BKB220 迁移、P16 16 路、ENET0/MDIO 调试、判据鉴别力）。事实来源可用 `docs/board/bkb220/migration-source-table.md`（§9～§15）、`docs/benchmarks/bkb220-p4-p16-100mhz-build.md`、`docs/05-implementation-plan.md`、`tools/README.md`、`AGENTS.md`。
4. 若发现某个包的文件名或内容违反参赛「文件/目录名纯英文小写」要求，**列进 AUDIT.md**（**不要擅自改名**，改名前要问 main）。

**纪律**：只写你核证过的；引用代码位置写**函数名/符号名**不写行号；**不得声称任何未测的东西已通过**；不要把 `logs/`（不入库）里的东西说成已入库。

最终答复给出：改了/新增了哪些文件、每个包审到什么程度、缺口清单要点、哪些没做完。