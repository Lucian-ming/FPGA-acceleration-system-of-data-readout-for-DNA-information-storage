# 文档索引

按「先看什么」的顺序排列。

| 文档 | 回答什么问题 | 什么时候看 |
| --- | --- | --- |
| [01-architecture.md](01-architecture.md) | 系统应该是什么样、每一级在算什么 | 第一次接手项目 |
| [02-data-contract.md](02-data-contract.md) | 编码、位序、码表的**唯一权威规范** | 改任何数据格式之前 |
| [03-status.md](03-status.md) | 现在哪里是坏的、证据在哪一行 | 决定动手改什么之前 |
| [04-roadmap.md](04-roadmap.md) | 接下来按什么顺序做、每步的验收判据 | 排期与分工 |
| [06-implementation-plan.md](06-implementation-plan.md) | **详细实施计划**：阶段、任务、判据、工作量、风险 | 开工前 / 每周对表 |
| [05-interfaces.md](05-interfaces.md) | TCP 协议、寄存器、DDR 地址 | 写 PS 固件或上位机 |
| [07-performance.md](07-performance.md) | CPU/FPGA 性能实测与加速价值分析 | 讨论选型、立项、答辩 |
| [08-handoff-2026-08-10.md](08-handoff-2026-08-10.md) | 历史快照：Stage1/Stage3 修复与复核 | 追溯 2026-08-06~10 的工作 |
| [09-handoff-2026-08-16.md](09-handoff-2026-08-16.md) | 历史快照：Stage2 黄金 TB + 同日完成的 D1/C1~C4/P5 全部离线任务 | 追溯离线闭环 |
| [10-three-end-audit-2026-08-16.md](10-three-end-audit-2026-08-16.md) | 三端审查、R1/R2/R3 提交与回退记录 | 追踪本轮修复与验证 |
| [11-github-sync-handoff-2026-08-21.md](11-github-sync-handoff-2026-08-21.md) | 两分支 GitHub 同步、可上板制品与排除项 | 获取代码或准备上板前 |
| [12-main-handoff-2026-08-21.md](12-main-handoff-2026-08-21.md) | **当前主分支最终交接**：接手顺序、验证、构建、上板和风险 | 新开发者首先阅读 |
| [13-xsim-simulation-plan.md](13-xsim-simulation-plan.md) | **XSim 高质量仿真提示与计划**：单 IP、三级流水线、Block Design、网表 | 开始完整仿真前 |
| [14-next-steps-2026-08-29.md](14-next-steps-2026-08-29.md) | **下一步行动计划**：本机已验证基线、M3/G3 的排序与判据、需要用户决定的事 | 想知道「现在该做什么」 |
| [15-m3-bd-simulation-2026-08-29.md](15-m3-bd-simulation-2026-08-29.md) | **M3 实际 BD 集成仿真结果**：BD-1/BD-2 通过、BD-3 被 PS7 VIP HP0 阻塞的完整证据链 | 接手 M3 或想知道 BD 级验证到哪一步 |
| [16-board-zynq-eco-7010.md](16-board-zynq-eco-7010.md) | **板级配置的唯一权威**：ZYNQ ECO(R6) 实物参数、DDR 配置修正与首次上板顺序 | 改 PS7 配置、准备上板之前必读 |
| [17-parallel-tasks-2026-08-29.md](17-parallel-tasks-2026-08-29.md) | 并行任务简报（历史）：定位 B21 的两条独立路径（BD-3b 仿真 / 板上诊断）与互斥约定 | 开新会话接手 B21 时 |
| [18-next-steps-2026-08-30.md](18-next-steps-2026-08-30.md) | **当前行动计划**：G3 闭环后的排队、闭环适用范围、技术债与接口判据现状 | 想知道「接下来做什么」时先读这份 |
| [19-parallel-sessions-2026-08-30.md](19-parallel-sessions-2026-08-30.md) | 并行会话简报（**历史，三个会话已于 08-31 全部收工**）：分工与互斥约定、提示词；§3 留了一个被实测推翻的结论及成因 | 想参考并行分工的做法时 |
| [20-se250-study-2026-08-30.md](20-se250-study-2026-08-30.md) | **SE250 扩展评估**（只调研不改 RTL）：几何推导、硬编码清单（RTL 11/固件 8/上位机 3/黄金 3 处）、资源与时序判据、分阶段方案 | 要把流水线从 150 bp 扩到 250 bp 时 |

## 参考资料（历史审计结果，只读）

| 文档 | 内容 |
| --- | --- |
| [reference/dataset.md](reference/dataset.md) | R0.83 数据集的来源、SHA-256、格式与使用限制 |
| [reference/repo-structure.md](reference/repo-structure.md) | 逐文件的职责索引 |
| [reference/gap-audit.md](reference/gap-audit.md) | 复现缺口与风险清单（2026-08-05 审计） |
| [reference/submission-archive.md](reference/submission-archive.md) | 2025-11-07 提交资产的校验和与黄金参考关系 |
| [reference/legacy-tech-note.md](reference/legacy-tech-note.md) | 旧技术说明。⚠️ 其寄存器表是「示例模板」，与实现不符，已被 05 取代 |

## 工具

| 工具 | 用途 |
| --- | --- |
| `tools/golden_model.py` | 黄金参考模型：验证算法契约、生成各级期望输出、软件复现整条流水线 |
| `tools/extract_ldpc_dlls.py` | 从历史 `gui_app.exe` 提取 LDPC EXE 缺失的 3 个 MinGW 运行时 DLL |
| `tools/make_golden.py` | 生成各级黄金向量到 `tests/golden/`（RTL Testbench 与端到端回归的判据） |
| `tools/run_sim.sh` | Icarus 仿真回归：用黄金向量逐位判定 RTL（含 DNA ingress/AXI-Lite、stage1/2/3/host/syntax） |
| `tools/run_xsim.sh` | Vivado/XSim 单 IP 黄金回归：6 个功能/AXI 用例，自动 PASS/FAIL 与日志归档 |
| `tools/run_m2_quick.sh` | 64 条快速三级串联：Stage1 实际输出 → Stage2 → PS XOR → Stage3 |
| `tools/run_m2_full.sh` | **2,048 条完整三级串联**：4,096 条正反记录、LDPC/JPEG 哈希与单 bit 故障注入 |
| `tools/run_m3_bd.sh` | **M3 实际 Block Design 集成仿真**：BD-1 静态/elaboration、BD-2 控制面、BD-3 数据面 |
| `tools/m3_mem.py` | M3 辅助：黄金 64bit 向量 ⇄ PS7 VIP DDR 的 32bit 字镜像格式互转与逐位比较 |
| `tools/verify_repo_binding.sh` | 开发前 Git 强制门禁：核对唯一目录、main、origin 和私有仓库推送权限 |
| `tools/debug_vote_diff.py` | 调试辅助：重算逐位置票值，与 Voter TB `+dump_bram` 转储的累加器做 diff |
| `tools/ldpc_decode.py` | **P5 纯 Python 硬判决 LDPC 译码器**（Linux 替代 Windows EXE）：`verify` 用 R0.83 黄金数据自检，`decode` 译码 0/1 文本并可重建 JPEG |
| `tools/test_ddr_layout.c` | C2/C3 的主机单元测试：按实际条数校验 DDR 区间（与固件共用 `sw/app/ddr_layout.h`） |
| `tools/test_task_config.c` | P3 的主机单元测试：PKT_CONFIG 解析/校验/CRC32（与固件共用 `sw/app/task_config.h`） |
| `tools/readout.py` | **干净的纯软件读出实现**：只吃 FASTQ + 水印，产出 dec_input.txt，可 `--prove-inputs` 自证不碰参考答案 |
| `tools/bench_align.py` + `tools/align.c` | Stage1 比对的 CPU 性能基准，以及「种子法为何失效」的实证 |

## 文档维护约定

- 改协议 / 寄存器 / 数据格式：先改 `02-data-contract.md` 或 `05-interfaces.md`，再改代码。
- 修好一个缺陷：在 `03-status.md` 里划掉它并记录判据结果，不要静默删除。
- 新增数据集版本：在 `reference/dataset.md` 追加一节，保留 SHA-256，不覆盖旧记录。
- 审查分支只承载相对 `main` 的临时审查修改；核查无误后必须及时合并并推送 `main`，
  后续开发回到主分支。未通过时必须记录具体阻塞项，不得长期悬置已验证修改。
- 仿真/构建证据目录（`hw/build/xsim/`、Vivado 生成目录）不入 Git，只存在于跑它的那台机器。
  文档里引用运行 ID 时必须写明是哪一次、哪台 checkout；换机器后要宣称同样结论，
  必须本机重跑生成自己的证据，不得直接沿用他机的运行 ID。
