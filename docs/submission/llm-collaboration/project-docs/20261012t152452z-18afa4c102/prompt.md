> 脱敏副本，原件 `20261012T152452Z-18afa4c102/{prompt.txt,answer.md}`。本机绝对路径、邮箱、凭据形模式及非白名单私网 IP 已替换；除脱敏与换行规范化外保留原文。

你是子 Agent，看板名 **llm-collab-record**。任务：**整理"大模型协作"参赛材料**。上一轮你因误把仓库绑定门禁当自己的前置而阻塞退出（那是主会话漏写提醒，已写进 AGENTS.md，不怪你），现在已更正，请继续。

**【必须先读】不要运行 `tools/verify_repo_binding.sh`（含 `--remote`/`--require-synced`）。** 那是 **main 的门禁**，main 已代跑并留证（见 `docs/03-status.md`）。codex 沙箱把 git 目录（本仓库 gitdir 是 `.git-data`）挂成**只读**，脚本要写 `FETCH_HEAD` 必然报 `Read-only file system` —— **这是沙箱特性不是仓库故障，据此阻塞等于白跑一轮**。读 `AGENTS.md` 的「子 Agent 的承载通道与模型」一节有同样说明。

【看板】workspace-write，动手前 `tools/agent_view.sh start --agent llm-collab-record --doing "..." --why "..." --next "..."`，收工 `done`。
【禁止】Git 写操作；不派生子 Agent；**只写 `docs/submission/ai-collaboration/` 这个目录**（`docs/submission/skill/` 归另一个 agent）；不改 docs 根 01～09。

**背景**：本项目参加 2026 嵌入式芯片与系统设计竞赛 FPGA 赛道 AMD 自主选题初级组，评分含「**大模型协作与技能包 15 分**」，硬性要求提交 **LLM 交互记录（提示词、回答、自我纠错轨迹）**。素材已经在仓库里，只是没被整理成可提交件。

**产出**（新目录 `docs/submission/ai-collaboration/`）：
1. `README.md` — 入口：说清本项目如何用大模型协作完成、各文件是什么、怎么复现。
2. `prompts.md` — 提示词记录。素材：`docs/agent-prompts/main.md`（主 Agent 长提示词）、`board-migrate.md`/`rtl-16way.md`/`verify-system.md`（三个角色）、`agent-prompts/README.md`。**不要整篇复制**（那些文件已在仓库里），要**摘录并说明每类提示词解决什么问题、约束怎么下的**。
3. `self-correction.md` — **自我纠错轨迹**（最有价值的一份）。四条真实素材，全部可查证，都在 `docs/board/bkb220/migration-source-table.md`：
   - **MDIO 读错完成标志 + 漏写 MDEN**（§9.5/§9.6）：现象"MDIO 无应答"一度被写成"需原理图"；真因是完成标志应读 `NETWORK_STATUS[2]`（不是 `PHY_MAINT`）、管理端口使能是 `NETWORK_CONTROL` bit4（不是 bit3）。
   - **假阻塞：阶段卡写死了 Vitis 2022.2 里不存在的 `lwip220`**（§12.5 与 `docs/07` 的 lwIP 段落；Vitis 2022.2 只有 lwip211，lwip220 属 2026.1）。
   - **最典型：探针配置 ≠ 制品配置**（§12，尤其 §12.3/§12.5）：F4 板测失败的真根因是 `hw/boards/bkb220.tcl` 从来没写过 ENET0 的 MIO 属性，而 F3 阶段全部 MDIO/PHY 结论都取自**探针**的 ps7_init。
   - **判据侧 bug：CRLF 让 PASS 报成 FAIL**（§13.1）：`tools/run_g3.sh` 读 Windows 侧写的 `uart_cap.out`，`$` 锚点被 `\r` 顶掉。
   每条写：**当时的错误结论 → 什么证据推翻它 → 改成什么做法 → 沉淀成哪条规则**。
4. `agent-usage.md` — 协作方式：主会话（Claude Code/DeepSeek）+ 子 Agent（codex-luna MCP、gpt-6-luna、max 强度）分工；看板 `tools/agent_view.sh` 用法；"writer 停写后才提交 Git"等纪律。素材见 `AGENTS.md` 的「子 Agent 的承载通道与模型」「工作可见性：view.md 看板」两节。说明每次 MCP 任务的原始 `prompt.txt`/`answer.md`/`result.json` 在仓库外 `~/.local/state/codex-subagent/runs/<job_id>/`，**`logs/` 不入库**——所以本目录要留下**可提交的摘要**并写清原始件在哪。

**纪律**：只写你核证过的；引用代码位置写**函数名/符号名**不写行号；不要把 `logs/` 或 `~/.local/state` 里的东西说成"已入库"。最终答复给出：产出文件路径、每份写到什么程度、哪些没做完。