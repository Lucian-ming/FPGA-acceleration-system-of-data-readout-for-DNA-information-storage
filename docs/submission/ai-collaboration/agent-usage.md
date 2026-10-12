# 大模型协作方式

## 角色与承载通道

| 角色 | 承载方式 | 职责 |
|---|---|---|
| 主会话 | Claude Code，经用户配置的 DeepSeek Anthropic 兼容端点；模型 deepseek-flash[1m] | 执行项目工作、读取最新状态、制定每轮阶段卡、派发和监控子 Agent、审核结果并承担唯一 Git 写入。 |
| 子 Agent | 用户级 codex-luna MCP；固定 gpt-6-luna，思考强度 max | 执行阶段卡中范围清楚的独占子任务。没有原生消息通道，prompt 必须自带项目背景、范围、产出路径、验收要求和看板任务名。 |

MCP 派发使用 codex_run，之后用 codex_status 查询；超时或需停止时按项目 MCP 规则处理，不把启动成功当作任务完成。成功至少同时核对 status=completed、ok=true、exit_code=0、turn_completed=true。客户端、代理与可用模型按当前项目指南核对，不自行更换模型或退回旧 CLI 入口。

## 每轮任务如何交接

1. main 先从最新状态和既有计划确认尚未完成项，为本轮写阶段卡：HEAD、任务边界、输入与证据目录、独占路径、已完成项、设备状态、资源许可、检查点和出口。
2. 子 Agent 只写授权的独占路径；若依赖或路径有冲突，通过报告和看板交回 main，不越界扩写。
3. main 按任务状态、最终回答、实际退出码、diff 与证据目录复核，不只接受摘要中的 PASS 字样。
4. Git 操作前，所有相关 writer 必须停止写入并确认产物已交接；main 核对共享工作树后才进行路径限定的提交和推送。子 Agent 不执行 add、commit、pull、rebase、stash、reset、switch、clean 或 push。

## 看板登记

workspace-write 任务由执行者通过 [tools/agent_view.sh](../../../tools/agent_view.sh) 更新根目录 view.md；read-only 任务由 main 代登记。任务名应唯一，doing、why、next 三项都写具体。view.md 展示实时状态，证据和结论仍写在对应文档。

    tools/agent_view.sh start --agent <任务短名> --doing <当前动作> --why <任务目的> --next <下一步>
    tools/agent_view.sh update --agent <任务短名> --doing <当前动作> --next <下一步>
    tools/agent_view.sh block --agent <任务短名> --doing <阻塞点> --why <原因> --next <等待事项>
    tools/agent_view.sh done --agent <任务短名> --doing <收尾事项> --next <后续状态>

## 原始交互的保存位置

每个 MCP 任务的原始材料按 job_id 保存在仓库外：~/.local/state/codex-subagent/runs/<job_id>/prompt.txt、answer.md、result.json、run.jsonl。workspace-write/read-only 模式与所有权不能混淆，按 AGENTS.md 的看板规则办理。本目录只留下适合提交的摘要；仓库 logs/ 不纳入这些原始记录，也不在这里声称已经入库。

若需要提交某次任务的完整交互记录，应先从对应 job_id 目录取回并核对原始文件，再按比赛材料目录的范围整理；不要把本摘要当作原始对话全文。

