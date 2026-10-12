# 大模型协作参赛材料

本目录整理本项目参加 2026 嵌入式芯片与系统设计竞赛 FPGA 赛道 AMD 自主选题初级组时的大模型协作材料，对应评分项“大模型协作与技能包”（15 分）。竞赛要求能看到提示词、回答与自我纠错过程，因此这里把可审阅的提示词设计摘要、真实纠错案例和协作流程放在同一入口。

## 文件索引

- [prompts.md](prompts.md)：主会话与三个子 Agent 角色提示词各自解决的问题、任务边界和约束。原提示词没有整篇复制，见 [docs/agent-prompts](../../agent-prompts/README.md)。
- [self-correction.md](self-correction.md)：从 BKB220 迁移过程核证的四条真实纠错轨迹，每条均给出原结论、反证、修正和沉淀规则。
- [agent-usage.md](agent-usage.md)：主会话与子 Agent 的承载通道、看板登记、任务交接和 Git 写入纪律。

## 如何复核与复现

1. 先读项目的 [提示词索引](../../agent-prompts/README.md) 与对应角色提示词；每次实际派发还应附上当时阶段卡，写清 HEAD、任务范围、独占路径、输入、设备状态、资源许可和验收出口。
2. 对纠错案例，按 [BKB220 来源表](../../board/bkb220/migration-source-table.md) 的 §9.5、§9.6、§12、§12.5、§13.1 逐条复核；lwIP 版本选择另见 [板级构建与验收说明](../../07-board-build-and-acceptance.md) 的工具链段落。
3. 需要重跑协作流程时，通过项目指定的 codex-luna MCP 派发完整角色提示词与新阶段卡，记录 job_id，并持续核对 MCP 任务终态、成功标志、退出码和完成事件。workspace-write 子任务按 [看板脚本](../../../tools/agent_view.sh) 登记；只读任务由 main 代登记。
4. 查阅某次任务的原始交互时，用该任务的 job_id 到仓库外目录定位原始件：~/.local/state/codex-subagent/runs/<job_id>/ 中的 prompt.txt、answer.md、result.json，以及完整事件记录 run.jsonl。

## 原始记录边界

本目录保存的是经过来源核对的提交摘要，不声称包含每次 MCP 任务的逐字交互。按项目约定，原始 prompt.txt、answer.md、result.json 和 run.jsonl 保存在仓库外的 codex-subagent runs 目录；仓库 logs/ 不作为本目录的原始交互档案，也不在此声称已入库。正式归档或提交具体任务的完整交互记录时，应从对应 job_id 的外部目录取回并单独核对，不要把摘要误标成原始日志。

