# 项目历史导航索引

> **本文件不是当前状态来源。** 当前状态一律以[03 当前状态与交接](../03-status.md)为准，证据一律以[09 证据台账](../09-evidence-ledger.md)为准。本文件只做导航；历史正文、数据、run、SHA、判据与结论请回到链接所指原文核对。

## 时间线

下表只标出日期、事项和原始资料入口。板卡、配置、制品、数据集及门限分开列，避免把不同测量合成一条结果。

| 日期 | 事件 | 原始资料 |
|---|---|---|
| 2026-09-22 | 旧板 ZYNQ ECO R6 / XC7Z010，P13 的 SE150 全量板测与性能基线。 | [03 当前状态](../03-status.md)、[08 性能策略](../08-performance-and-strategy.md)、[09 证据台账](../09-evidence-ledger.md) |
| 2026-10-10 | BKB220 / XC7Z020 迁移接手检查点；与旧板记录分开。 | [BKB220 handoff 检查点](bkb220-handoff-checkpoint-2026-10-10.md)、[工作区整理记录](workspace-cleanup-2026-10-10.md)、[BKB220 来源表](../board/bkb220/migration-source-table.md) |
| 2026-10-12 | BKB220 / XC7Z020 / SE150 / P4（4/0）整机重建与板测资料。 | [阶段总结](phase-summary-2026-10-12.md)、[P4/P16 100 MHz 构建记录](../benchmarks/bkb220-p4-p16-100mhz-build.md)、[BKB220 来源表](../board/bkb220/migration-source-table.md) |
| 2026-10-12 | BKB220 / XC7Z020 / SE150 / P16（16/1）整机重建与板测资料，独立于 P4 项。 | [阶段总结](phase-summary-2026-10-12.md)、[P4/P16 100 MHz 构建记录](../benchmarks/bkb220-p4-p16-100mhz-build.md)、[BKB220 来源表](../board/bkb220/migration-source-table.md) |
| 2026-10-13 | BKB220 P16 上传优化交接；历史派生实验包与正式提升包分开追溯。 | [speed 交接](speed-handoff-2026-10-13.md)、[上传 A 组测量](../benchmarks/bkb220-p16-speed-a-upload.md)、[上传提升记录](../benchmarks/bkb220-p16-upload-promotion.md) |
| 2026-10-14 | BKB220 P16 Stage1 K=2，R0.83 / SE150 全量判据的构建、仿真与板测资料。 | [03 当前状态](../03-status.md)、[Stage1 多碱基探针](../benchmarks/stage1-multibase-ooc-probe.md)、[BKB220 来源表](../board/bkb220/migration-source-table.md) |
| 2026-10-14 | BKB220 P16 片上 LDPC 集成与 L7 板端记录；与 Stage1 K=2 记录分开。 | [LDPC handoff](ldpc-onchip-handoff-2026-10-14.md)、[LDPC 集成记录](../benchmarks/ldpc-onchip-integration.md)、[LDPC L7 板测](../benchmarks/ldpc-onchip-l7-board.md) |
| 2026-10-15 | BKB220 P16 诊断打印优化的交替 A/B 记录；与次日 Stage3 等待轮询改动分开。 | [03 当日记录](../03-status.md)、[v1.0 定版记录](release-v1.0.md) |
| 2026-10-16 | BKB220 P16 Stage3 等待轮询改动及其独立板端记录。 | [03 当日记录](../03-status.md)、[v1.0 定版记录](release-v1.0.md) |
| 2026-10-16 | BKB220 P16 / R0.83 / SE150 的 8 小时长稳 run。 | [03 当前状态](../03-status.md)、[8 小时长稳报告](../benchmarks/bkb220-p16-soak-8h.md)、[v1.0 定版记录](release-v1.0.md) |
| 2026-10-16 | v2 challenge 数据集在出厂门限 `score_min=67` 下的独立板测记录；与 R0.83 长稳分开。 | [03 当前状态](../03-status.md)、[BKB220 来源表](../board/bkb220/migration-source-table.md) |
| 2026-10-16 | 多载荷泛化回归记录；其数据集范围单列，不与 v2 的 `score_min=67` 测试合并。 | [v1.0 定版记录](release-v1.0.md)、[03 当前状态](../03-status.md) |
| 2026-10-16 | SD 卡冷启动记录；与 QSPI 启动记录分开查阅。 | [03 当前状态](../03-status.md)、[v1.0 定版记录](release-v1.0.md) |
| 2026-10-16 | BKB220 / XC7Z020 / P16 v1.0 制品包身份、来源和定版记录。 | [v1.0 定版记录](release-v1.0.md)、[03 当前状态](../03-status.md) |

## 历史文档索引表

专项复核判定危险的六份 handoff / cleanup 原文在表中标为“**不压缩**”。其他相关阶段记录也保留各自范围与引用关系；本表只给入口，不替代原文。

| 路径 | 日期 | 独有价值 | 被谁引用（grep 命中） |
|---|---|---|---|
| [bkb220-handoff-checkpoint-2026-10-10.md](bkb220-handoff-checkpoint-2026-10-10.md)（**不压缩**） | 2026-10-10 | 保留 F2 `ready=0` dry-run 的拒绝时点、47 项 G3 主机用例和当日固件/卫生门禁检查。 | [03 当前状态](../03-status.md)、[项目清单](project-inventory-2026-10-10.tsv)、[专项复核②](../../logs/dev/swarm-findings/phase2/verify-findings-c.md)。 |
| [phase-summary-2026-10-12.md](phase-summary-2026-10-12.md)（**不压缩**） | 2026-10-12 | 分别保留 P4、P16 的制品路径、run-id、G3 判据和阶段边界。 | [03 当前状态](../03-status.md)、[专项复核②](../../logs/dev/swarm-findings/phase2/verify-findings-c.md)、[悬空引用扫描](../../logs/dev/swarm-findings/sweep-dangling-refs.md)。 |
| [speed-handoff-2026-10-13.md](speed-handoff-2026-10-13.md)（**不压缩**） | 2026-10-13 | 保留同小时 A/B 规则、上传改动对应的包与测量，以及失败和放弃方向。 | [03 当前状态](../03-status.md)、[P4/P16 性能矩阵](../benchmarks/bkb220-p4-p16-performance-matrix.md)、[专项复核②](../../logs/dev/swarm-findings/phase2/verify-findings-c.md)。 |
| [tool-cleanup-2026-10-11.md](tool-cleanup-2026-10-11.md)（**不压缩**） | 2026-10-11 | 保留退役工具源码 SHA、卫生/IP 门禁记录和当时的工具链安装核查范围。 | [README](../../README.md)、[03 当前状态](../03-status.md)、[05 执行计划](../05-implementation-plan.md)、[09 证据台账](../09-evidence-ledger.md)、[工具索引](../README.md)、[main 提示词](../agent-prompts/main.md)。 |
| [workspace-cleanup-2026-10-10.md](workspace-cleanup-2026-10-10.md)（**不压缩**） | 2026-10-10 | 保留逐路径的原位保留/忽略边界、清理范围及对应留存清单。 | [README](../../README.md)、[.gitignore](../../.gitignore)、[03 当前状态](../03-status.md)、[05 执行计划](../05-implementation-plan.md)、[09 证据台账](../09-evidence-ledger.md)、[项目清单](project-inventory-2026-10-10.tsv)。 |
| [slimming-report-2026-09-11.md](slimming-report-2026-09-11.md)（**不压缩**） | 2026-09-11 | 保留 S-1～S-5 清理批次、门禁变化和各类历史文件处置依据。 | [cleanup inventory](cleanup-inventory.md)、[代码质量复排](code-quality-review-2026-10-14.md)、[项目清单](project-inventory-2026-10-10.tsv)、[专项复核②](../../logs/dev/swarm-findings/phase2/verify-findings-c.md)。 |
| [cleanup-inventory.md](cleanup-inventory.md) | 2026-10-16 | 保留本轮清理清单、不得删除对象及仅盘点而不执行删除的范围。 | [文件孤儿扫描](../../logs/dev/swarm-findings/sweep-orphan-files.md)、[phase2 gap-hunt](../../logs/dev/swarm-findings/phase2/gap-hunt.md)、[专项复核②](../../logs/dev/swarm-findings/phase2/verify-findings-c.md)、[悬空引用扫描](../../logs/dev/swarm-findings/sweep-dangling-refs.md)、[文档扫描](../../logs/dev/swarm-findings/scan-docs.md)。 |
| [code-quality-review-2026-10-14.md](code-quality-review-2026-10-14.md) | 2026-10-14 | 保留只读源码/脚本复排的范围、具体门禁风险及未实施建议。 | [03 当前状态](../03-status.md)、[文档扫描](../../logs/dev/swarm-findings/scan-docs.md)。 |
| [gap-audit.md](gap-audit.md) | 2026-08-05（08-06 补充） | 保留早期复现缺口、当时的数据身份和板级/软件实现缺项分析。 | [仓库结构说明](repo-structure.md)、[项目清单](project-inventory-2026-10-10.tsv)、[归档状态记录](../archive/history/2026/pre-bkb220-handoff-2026-10-10/status.md)。 |
| [ldpc-onchip-handoff-2026-10-14.md](ldpc-onchip-handoff-2026-10-14.md) | 2026-10-14 | 保留 L0–L7 阶段指针、原始 job-id 对应关系、输入顺序边界和交接入口。 | [03 当前状态](../03-status.md)、[LDPC 架构决定](ldpc-architecture-decision-2026-10-14.md)、[文档地图](../README.md)。 |
| [ldpc-architecture-decision-2026-10-14.md](ldpc-architecture-decision-2026-10-14.md) | 2026-10-14 | 说明对 handoff §5.3 的局部替代及 §4.5 资源表口径修正，其他章节仍需回原文读取。 | [文档地图](../README.md)、[09 证据台账](../09-evidence-ledger.md)、[LDPC 行引擎探针](../benchmarks/ldpc-row-engine-ooc-probe.md)、[LDPC L4 记录](../benchmarks/ldpc-decoder-l4.md)。 |
| [release-v1.0.md](release-v1.0.md) | 2026-10-16 | 集中保留 v1.0 制品身份、代码同源核对方式、适用的测试范围和历史包处置指针。 | [cleanup inventory](cleanup-inventory.md)、[第三方声明](../submission/third-party-notices.md)。 |

## 历史归并方案复核结论

曾评估把上表标记的六份 handoff / cleanup 原文压成短索引。专项复核认为该做法**危险**：六份原文各自含独有的 run-id、SHA、判据和失败方向，并被 README、03、05、09、`.gitignore`、性能矩阵、cleanup inventory 等活链引用；短索引无法保全原文证据，也可能断开现有引用。因此**不做压缩、不删除、不改写这六份原文**。第二波复核共 15 项，判定为安全 5、危险 7、待人工定夺 3；逐项依据见[专项复核②](../../logs/dev/swarm-findings/phase2/verify-findings-c.md)。
