> 脱敏副本，原件 `20261012T152126Z-13fc211641/{prompt.txt,answer.md}`。本机绝对路径、邮箱、凭据形模式及非白名单私网 IP 已替换；除脱敏与换行规范化外保留原文。

你是子 Agent，看板名 **llm-collab-record**。任务：**整理"大模型协作"参赛材料**。

【紧急时间约束】用户 23:30 断电，你**最多只有约 8 分钟**。**先写出能独立成立的骨架文件，再逐步补细节**——宁可交一份完整但朴素的东西，也不要交一份写了一半的。每写完一个文件就保存。

【看板】workspace-write，先 `tools/agent_view.sh start --agent llm-collab-record --doing "..." --why "..." --next "..."`，收工 `done`。
【禁止】Git 写操作；不派生子 Agent；不改 `docs/submission/skill/`（归另一个 agent）；不改 docs 根 01～09。

**背景**：本项目参加 2026 嵌入式芯片与系统设计竞赛 FPGA 赛道 AMD 自主选题初级组，评分含"**大模型协作与技能包 15 分**"，且**硬性要求提交 LLM 交互记录（提示词、回答、自我纠错轨迹）**。这套素材已经存在，只是没被整理成可提交的东西。

**你要产出**（新目录 `docs/submission/ai-collaboration/`，**只写这个目录**）：
1. `README.md` —— 入口：说清"本项目如何用大模型协作完成"，以及各文件是什么、怎么复现。
2. `prompts.md` —— 提示词记录。素材：`docs/agent-prompts/main.md`（主 Agent 长提示词）、`board-migrate.md`/`rtl-16way.md`/`verify-system.md`（三个角色提示词）、`docs/agent-prompts/README.md`。**不要整篇复制**（那些文件已在仓库里），要**摘录并说明每一类提示词解决什么问题、约束是怎么下的**。
3. `self-correction.md` —— **自我纠错轨迹**（这是最有价值的一份，评审要看的"轨迹"）。真实素材（全都可查证）：
   - **MDIO 读错完成标志 + 漏写 MDEN**：`docs/board/bkb220/migration-source-table.md` §9.5/§9.6。现象是"MDIO 无应答"，一度被写成"需原理图"；真因是完成标志应读 `NETWORK_STATUS[2]`（不是 `PHY_MAINT`）、管理端口使能是 `NETWORK_CONTROL` bit4（不是 bit3）。
   - **假阻塞：阶段卡写死了 Vitis 2022.2 里不存在的 `lwip220`**：见同表 §12.5 与 `docs/07` §3 的 lwIP 段落。
   - **最典型的一条：探针配置 ≠ 制品配置**：F4 板测失败的**真根因**是 `hw/boards/bkb220.tcl` 从来没写过 ENET0 的 MIO 属性，而 F3 阶段所有 MDIO/PHY 结论都是在**探针**的 ps7_init 下得到的。见同表 §12（尤其 §12.3、§12.5）。
   - **判据侧 bug：CRLF 让 PASS 报成 FAIL**：`tools/run_g3.sh` 读 Windows 侧写的 `uart_cap.out`，`$` 锚点被 `\r` 顶掉。见 §13.1。
   每条请写：**当时的错误结论 → 是什么证据推翻它的 → 改成了什么做法 → 沉淀成了哪条规则**。
4. `agent-usage.md` —— 协作方式：主会话（Claude Code/DeepSeek）+ 子 Agent（codex-luna MCP、gpt-6-luna、max 强度）的分工、看板 `tools/agent_view.sh` 的用法、"writer 停写后才能提交 Git"等纪律。素材见 `AGENTS.md` 的「子 Agent 的承载通道与模型」「工作可见性」两节。
   说明：每次 MCP 任务的原始 `prompt.txt`/`answer.md`/`result.json` 在仓库外的 `~/.local/state/codex-subagent/runs/<job_id>/`，**logs/ 不入库**——所以本目录里要留下**可提交的摘要**，并写清原始件在哪。

**纪律**：只写你核证过的；引用代码位置写**函数名/符号名**，不要写行号；不要把 `logs/` 或 `~/.local/state` 里的东西说成"已入库"。最终答复里给出：产出的文件路径、每份写到什么程度、哪些没来得及写。