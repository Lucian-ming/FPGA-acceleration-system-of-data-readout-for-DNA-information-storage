# 2026-10-10 文档合并与工作区整理记录

用户要求整理整个项目、合并精简文档、归档旧内容、给出完整流程/主子Agent提示词并继续执行，已明确授权代码及文档提交推送。

## 文档整理

原根目录20份编号文档收敛为9份，目录和映射见docs/README。原20份内容保存到docs/archive/history/2026/pre-bkb220-handoff-2026-10-10，归档文件去编号；原内容保存在本地Git交付备份，归档正文仅调整链接以匹配新位置，归档manifest记录原/新SHA。架构/数据/接口保留契约，状态/性能剔除旧推断冒充当前结论，执行计划集中角色/监控/验收/Git/清理。

现行引用统一改到9份入口；历史资料中的相对链接只修复目标，不改历史结论。主提示词和三个角色提示词在docs/agent-prompts；当前逐文件职责清单在project-inventory-2026-10-10.tsv。

## 工作区清理边界

| 精确路径 | 处置与理由 |
|---|---|
| hw/build/attic/ | 原位保留时序不收敛中间版/实现备份，精确忽略 |
| hw/build/export_4way_physopt/ | 历史G3用过的活制品证据，原位保留、精确忽略；相关文档路径不移动 |
| logs/multi_payload/repeat3_20260910T200339Z/dumps/ | 多payload原始dump原位保留，报告已跟踪，精确忽略大型原始数据 |
| logs/vivado/recovery_20260909/failing_endpoints.tsv、failing_paths_all.rpt | 历史失败时序证据原位保留，精确忽略，已跟踪小摘要不受影响 |
| tests/stress_results/g6_config_guard_20260911T035705Z/、g6_continuous_20260908T121731Z/、g6_postfault_20260908T165423Z/ | 运行/探针失败和恢复证据原位保留，精确忽略；已跟踪文件继续跟踪 |
| data、archive、hw/build/export、历史XSA、sw/workspace | 不删除；workspace是生成副本，已有源码同步备份；原始BSP/ELF和旧发布包不覆盖 |
| 本任务新EDA/Vitis/XSim输入、输出、日志与Git恢复点 | 保留源/fixture/产物SHA、run-id和失败；不批量drop stash或删除输出，不终止其他用户进程 |

本次“工作区干净”指源码和Git状态，不代表历史证据已上传远端，也不代表释放其磁盘空间。保留内容的逐文件SHA见workspace-retention-manifest-2026-10-10.json。未来释放空间须依06清理规则先确认可重建性和证据归集，不能git clean删除忽略数据。

## 起点卫生重复告警的处理

tools/agent_view.sh与参赛技能包本地附件在任务起点逐字节相同。按用户整理脚本/清理工作区要求及AGENTS唯一源规则，保留tools中的源码，参赛README直接链接它；删除的只是重复源码副本，原字节本机保存到D:/Agent/outputs/fpga-migration-handoff-20261010/duplicate-source-backup/，Git历史也可恢复。SHA-256为32f921031fbde7602d21f2e4a426627c1eee141fc1c99fdc45182de232a7439d，tools源码未变，独立下载/复制脚本的使用方式保留。原始卫生失败日志与修复后重跑结果都保存，未豁免或放宽门禁，不删除任何运行证据或数据。

迁移准备仿真、47主机用例、现代旧XSA软件探针不能证明新板完成。实际BKB220资料/连接、P4新板基线、P16整机时序和真板全量/连续/恢复/性能仍按06/09依赖执行。

黄金GEOMETRY元数据及make_golden生成模板保留冻结字节，内部旧编号仅为历史元数据；当前契约查02/05，不为修文档重生成输入或改变黄金SHA。源码中少量文档引用注释已更新，不改变算法/接口；A14软件构建证据针对其留存源码快照，不将其称为当前新板发布包。
