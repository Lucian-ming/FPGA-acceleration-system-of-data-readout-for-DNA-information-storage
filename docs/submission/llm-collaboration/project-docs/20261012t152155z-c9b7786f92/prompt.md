> 脱敏副本，原件 `20261012T152155Z-c9b7786f92/{prompt.txt,answer.md}`。本机绝对路径、邮箱、凭据形模式及非白名单私网 IP 已替换；除脱敏与换行规范化外保留原文。

你是子 Agent，看板名 **skill-package**。任务：**审阅并补齐参赛技能包**。

【紧急时间约束】用户 23:30 断电，你**最多只有约 8 分钟**。**优先做最有价值的**：先审阅现状并写出结论/缺口清单，再补内容。每写完一个文件就保存。

【看板】workspace-write，先 `tools/agent_view.sh start --agent skill-package --doing "..." --why "..." --next "..."`，收工 `done`。
【禁止】Git 写操作；不派生子 Agent；**只写 `docs/submission/skill/` 及其子目录**（`docs/submission/ai-collaboration/` 归另一个 agent）；不改 docs 根 01～09；不改 `tools/`、`hw/`。

**背景**：本项目参加 2026 嵌入式芯片与系统设计竞赛 FPGA 赛道 AMD 自主选题初级组。"**大模型协作与技能包**"占 **15 分**，参赛硬要求里有 **`skill/README.md` 技能包**。

**现状**：`docs/submission/skill/` 下**已有 8 个技能包**，各有 README（部分带脚本）：
`board-stage-evidence`、`board-bringup-debug`、`bottleneck-attribution`、`accel-vs-cpu-baseline`（含 `baremetal_baseline.tcl.in`）、`ai-agent-collaboration`、`ip-packaging-hygiene`、`claims-ledger`、`fpga-timing-probe`（含 `ooc_probe.tcl`）。

**你要做的**：
1. **逐一审阅这 8 个包**，对每个回答：它解决的问题是什么？触发条件写清了吗？步骤可照做吗？判据是"会红"的吗？有没有过时内容（例如还在讲旧板 XC7Z010、旧 export 路径、SE250）？
2. 产出 `docs/submission/skill/AUDIT.md`：上面这些逐包的审阅结论 + **缺口清单**（按价值排序）。
3. **按价值补齐**——优先补与本轮新板工作直接相关的（BKB220 迁移、P16 16 路、ENET0/MDIO 调试、判据鉴别力）。**如果你时间只够做一件事，就把入口 `docs/submission/skill/README.md` 写好**：说清这个技能包整体是什么、8（或更多）个包各自何时用、怎么用、以及它们与本项目的关系。
4. 若发现某个包的文件名或内容违反参赛"文件/目录名纯英文小写"要求，**列进 AUDIT.md**（不要擅自改名，改名前要问 main）。

**纪律**：只写你核证过的（可以读 `docs/board/bkb220/migration-source-table.md`、`docs/benchmarks/`、`tools/README.md`、`AGENTS.md` 取事实）；引用代码位置写**函数名/符号名**不写行号；**不要声称任何未测的东西已通过**；不要把 `logs/`（不入库）里的东西说成已入库。

最终答复给出：改了/新增了哪些文件、每个包审到什么程度、缺口清单要点、哪些没来得及做。