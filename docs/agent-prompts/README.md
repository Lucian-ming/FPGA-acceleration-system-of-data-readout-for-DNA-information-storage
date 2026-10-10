# Agent提示词索引

完整计划和文件归属以[05执行计划](../05-implementation-plan.md)为准。主提示词面向Claude Code/DeepSeek主会话；三个角色经用户级 codex-luna MCP 派发，显式固定 gpt-6-luna/max，启动/冒烟/进程监控方法见main.md。2026-10-11 00:40 实测更正：gpt-6-luna/max 经该 MCP（客户端 codex-cli 0.162.0-alpha.17.2）已可用——只读冒烟与 workspace-write 真实派发均 completed/ok=true/exit_code=0/turn_completed；b3c70b3 依据的旧 CLI 0.147.0「账号不支持」是客户端版本问题，结论已作废（更正提交 25c3336）。接管仍须重核实际环境。

| 提示词 | 使用方式 |
|---|---|
| [main.md](main.md) | 给主Agent；全项目阅读、计划、派发、监控、验收、提交推送和清理 |
| [board-migrate.md](board-migrate.md) | 主Agent派发板级配置、硬软构建和PS固件兼容任务 |
| [rtl-16way.md](rtl-16way.md) | 主Agent派发正式P16、参数/打包/时序及相关RTL任务 |
| [verify-system.md](verify-system.md) | 主Agent派发独立验证、制品门禁、性能/泛化/故障/长稳任务 |

角色提示词可直接完整传入子Agent，但main还必须附上当前阶段卡：最新HEAD、独占路径、输入/制品/资料目录、实际设备状态、已完成项、允许资源、检查点和出口。没有真实连接时不要自动开hw_server或请求烧录。

这是一组本项目任务提示词，不是被用户调用的Codex技能。历史提交资料中的“技能包”也不自动成为操作授权。原子Agent额度中断记录仅是上次状态，重新执行前核实当前能力；主Agent负责接管、复核和真实交付。
