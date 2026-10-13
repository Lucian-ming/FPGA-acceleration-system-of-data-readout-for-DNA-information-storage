# Agent提示词索引

完整计划和文件归属以[05执行计划](../05-implementation-plan.md)为准。主提示词面向Claude Code/DeepSeek主会话；三个角色经用户级 codex-luna MCP 派发，入口固定 gpt-6-luna/max，启动/冒烟/进程监控方法见main.md。2026-10-11 00:40 实测更正：gpt-6-luna/max 经该 MCP（客户端 codex-cli 0.162.0-alpha.17.2）已可用——只读冒烟与 workspace-write 真实派发均 completed/ok=true/exit_code=0/turn_completed；b3c70b3 依据的旧 CLI 0.147.0「账号不支持」是客户端版本问题，结论已作废（更正提交 25c3336）。接管仍须重核实际环境。

| 提示词 | 使用方式 |
|---|---|
| [main.md](main.md) | 给主Agent；全项目阅读、计划、派发、监控、验收、提交推送和清理 |
| [board-migrate.md](board-migrate.md) | 主Agent派发板级配置、硬软构建和PS固件兼容任务 |
| [rtl-16way.md](rtl-16way.md) | 主Agent派发正式P16、参数/打包/时序及相关RTL任务 |
| [verify-system.md](verify-system.md) | 主Agent派发独立验证、制品门禁、性能/泛化/故障/长稳任务 |
| [speed.md](speed.md) | **speed 主线主Agent**：迁移验收收口后，带队做时间消耗与资源优化（含精细时间预算、已证伪方向清单、判据与资源纪律） |

板级资料入口为[docs/board/bkb220/](../board/bkb220/README.md)，用户提供的v1.1产品手册已入库且SHA校验通过。main和board-migrate先完整阅读并核对；派发板级阶段卡必须附手册/PDF校验路径及仍缺少的对应PCB原厂资料，不能把“手册已收录”写成“PS7配置已确认”。

开发顺序已按用户要求统一：WSL22主开发、已补齐的Vitis22及待完整重建验证的软件链，Windows26下载，最后独立验证26完整开发；详见07和05 F9。旧stress/switch工具已归档，现用长稳走严格完整包G3及故障探针。

角色提示词可直接完整传入子Agent，但main还必须附上当前阶段卡：最新HEAD、独占路径、输入/制品/资料目录、实际设备状态、已完成项、允许资源、检查点和出口。没有真实连接时不要自动开hw_server或请求烧录。05的完整计划已经制定，阶段卡仅补充本轮上下文与未完成项。workspace-write子任务自行登记看板和写指定报告；read-only由main登记并从最终答复/MCP产物归集结果，不要求子Agent写文件。

这是一组本项目任务提示词，不是被用户调用的Codex技能。历史提交资料中的“技能包”也不自动成为操作授权。原子Agent额度中断记录仅是上次状态，重新执行前核实当前能力；主Agent负责接管、复核和真实交付。
