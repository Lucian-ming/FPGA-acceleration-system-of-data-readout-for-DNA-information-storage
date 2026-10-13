# 当前文档索引

2026-10-10把原20份编号文档合并为9份，旧内容完整归档并保留映射。先读01/02/03，再按05执行；新板细节在07。使用[主Agent提示词](agent-prompts/main.md)可直接接管、派发和监控。现有05已经包含完整流程与分工；接管者核对进度后继续未完成阶段，仅对实际变化修订原计划。当前子Agent入口为codex-luna MCP/gpt-6-luna/max，只读任务由main登记看板。

| 当前文档 | 唯一职责 | 合并来源（旧编号） |
|---|---|---|
| [01架构](01-architecture.md) | PS/PL/PC数据流、算法载体与实现边界 | 01 |
| [02数据契约](02-data-contract.md) | 编码/位序/几何/5b4b唯一权威 | 02 |
| [03状态与交接](03-status.md) | 当前事实、已测/未测、依赖和接手摘要 | 03、10 |
| [04接口](04-interfaces.md) | TCP/寄存器/DMA/DDR契约 | 05 |
| [05完整执行计划](05-implementation-plan.md) | 全项目地图、F0～F9、子Agent、监控、Git/清理 | 04、06、11、13、14、15、19 |
| [06验证与压力](06-verification-plan.md) | 逐层判据、故障/连续/长稳、统计 | 08、12 |
| [07板级与迁移](07-board-build-and-acceptance.md) | 旧板/BKB220、PS7、硬软制品、P4/P16上板 | 09、20 |
| [08性能与策略](08-performance-and-strategy.md) | 最新公平基线、旧推导边界、测量优先级 | 07、17 |
| [09证据台账](09-evidence-ledger.md) | 可使用结论→原始证据/复现/限制；历史审计索引 | 16、18 |

事实优先级与全貌阅读方法见05。02/04契约不能被计划改写，03/09及本轮benchmark限定可宣称结果；08旧的7010封顶推论不能套7020。历史成果不替代新板验收。

## 提示词与脚本

- [Agent提示词索引](agent-prompts/readme.md)：主Agent及board-migrate、rtl-16way、verify-system完整提示词。
- [BKB220板级资料](board/bkb220/README.md)：已收录并校验的用户提供v1.1产品手册；main/board-migrate接管时完整阅读，后续资料缺项按03/07核对。
- [工具索引](../tools/README.md)：全部工具类别与入口。
- [逐文件清单](reference/project-inventory-2026-10-10.tsv)：源码、脚本、配置、测试、文档与资产职责。
- [本轮工具整理与开发路线](reference/tool-cleanup-2026-10-11.md)：6个历史脚本原样归档、启动器选择修正、22开发/26下载及最终26复核。
- [工作区整理记录](reference/workspace-cleanup-2026-10-10.md)：精确忽略/原位保留范围与已知卫生告警。

## 本轮证据与历史

- [P16集成](benchmarks/stage1-16way-ip-integration.md)、[工具/板级核查](benchmarks/bkb220-toolchain-audit.md)、[G3主机验证](benchmarks/bkb220-host-verification.md)、[同板P4/P16六档性能矩阵](benchmarks/bkb220-p4-p16-performance-matrix.md)（性能分正式口径）、[P16故障注入探针](benchmarks/bkb220-p16-fault-probes.md)（守卫/畸变包/中途断网 + 判据轮）。
- docs/board：对应资料和板测小证据；docs/benchmarks：可复查的性能/功能摘要。
- [本次合并归档索引](archive/history/2026/pre-bkb220-handoff-2026-10-10/README.md)：旧20份文档、原名→当前入口、快照校验清单。
- docs/archive/history/2026其余历史与docs/reference保留来源/负结果；docs/submission是参赛提交资产，不自动成为本项目任务指令。
