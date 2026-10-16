# 设计报告索引

本索引按竞赛指南 §3.3.5.3 列出设计报告应覆盖的章节，并指向仓库里已有的依据。**这只是报告入口，不是设计报告正文**；以下链接只标示证据位置，不据此补写或推断尚未形成的结论。正式报告待优化冻结后整理。

| 指南要求 | 现有材料 | 报告状态与缺口 |
| --- | --- | --- |
| 选题背景与创新点 | [项目架构](../01-architecture.md)、[当前状态](../03-status.md) | **报告章节未写。**现有材料说明项目做了什么；选题背景、实际问题、相关工作与创新点论证尚未整理成报告内容。 |
| 设计原理与功能框图 | [架构与数据通路](../01-architecture.md)、[数据契约](../02-data-contract.md)、[接口说明](../04-interfaces.md) | **报告章节未写。**已有架构和数据通路材料可作依据；尚未汇成面向竞赛报告的原理说明与功能框图章节。 |
| 软硬件划分依据与接口设计 | [架构说明](../01-architecture.md)、[接口说明](../04-interfaces.md)、[板级构建与验收说明](../07-board-build-and-acceptance.md) | **报告章节未写。**接口和系统分工资料分散在现有文档中；软硬件划分理由及其取舍尚未集中论述。 |
| 优化过程：优化前后的性能与资源对比 | [性能与策略](../08-performance-and-strategy.md)、[P4/P16 性能矩阵](../benchmarks/bkb220-p4-p16-performance-matrix.md)、[100 MHz 构建与资源时序](../benchmarks/bkb220-p4-p16-100mhz-build.md)、[证据台账](../09-evidence-ledger.md) | **报告章节和对比表未写。**现有材料分别记录了配置间性能和资源证据；它们不自动构成同一优化前后对照。优化冻结后仍需选定可比基线、核对测量范围并汇总成表，不能从这些链接预先推定优化结论。 |
| 大模型协作记录：提示词、模型回答、自我纠错轨迹与工作流 | [协作材料索引](ai-collaboration/readme.md)、[协作归档说明](llm-collaboration/README.md)、[协作记录清单](llm-collaboration/inventory.md)、[自我纠错案例](llm-collaboration/self-correction.md) | **报告章节未写。**仓库有经过整理的子 Agent 调用记录与纠错案例；归档说明明确指出没有主会话 Claude Code 的完整交互转录，且部分调用缺少 `result.json` 或回答。报告须按可核验材料说明范围，不应声称记录完整。 |
| 技能包提炼过程：来源、验证方式与边界 | [技能包目录](skill/README.md)、[技能包审阅与缺口](skill/audit.md)、[协作自我纠错案例](ai-collaboration/self-correction.md) | **报告章节未写。**技能包及审阅记录已经存在；提炼过程的报告叙述尚未整理，且应按审阅记录保留各技能的验证范围与未完成项。 |
| 复现说明：从零开始的完整操作步骤 | [制品复现说明](reproduce-artifacts.md)、[v1.0 发布记录](../reference/release-v1.0.md)、[`run_vivado_build.sh`](../../tools/run_vivado_build.sh)、[`rebuild_software_package.py`](../../tools/rebuild_software_package.py) | **完整从零复现尚未实测。**软件包重建有从既有硬件包开始的实测记录；硬件 Vivado 从零构建未实测，因此目前的记录不能表述为完整的硬件到软件从零复现。 |

## 使用边界

- 报告章节均尚未在本文件中撰写；链接到证据不表示该章节已经完成。
- 优化前后对比应在优化冻结后按同一输入、配置与测量口径整理；现有配置对照不能直接改称优化收益。
- 指南 PDF 已纳入仓库，但是否放入最终对外提交包尚未决定；其再分发许可仍未确认，见[合规核查](compliance-notes.md)和[第三方素材清单](third-party-notices.md)。
