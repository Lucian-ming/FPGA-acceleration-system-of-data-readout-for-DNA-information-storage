# 文档地图与技术索引 (Documentation Map)

> 本仓库已随竞赛结束冻结于标签 `final-2026-11`。所有文档已按最终重排后的架构完成校验。

---

## 1. 核心架构与现行设计文档 (01 ~ 09)

| 文档编号与名称 | 主要职责与核心内容 | 对应实现载体 |
| :--- | :--- | :--- |
| [01 架构设计](01-architecture.md) | PS/PL/PC 数据流划分、四级硬件流水线与系统设计边界 | `src/hw/`、`src/sw/` |
| [02 数据契约](02-data-contract.md) | 读段几何结构、水印排布、码字映射与 5b/4b 权威规范 | `sim/golden/`、`data/` |
| [03 最终状态与项目冻结](03-status.md) | 完赛状态说明、冻结标签、最终交付指标与交接指引 | 全库 |
| [04 软硬件接口](04-interfaces.md) | AXI-Lite 寄存器映射、AXI-Stream 通道、DMA 环与 TCP 协议 | `src/sw/app/dma_dna.c`、`src/sw/app/proto.h` |
| [05 实施与执行计划](05-implementation-plan.md) | 全生命周期路线图、里程碑拆解与验证判据 | 历史开发记录 |
| [06 验证与压力测试](06-verification-plan.md) | 三层验收判据、长稳测试方案、故障注入与统计学评估 | `src/tools/run_sim.sh`、`src/tools/run_g3.sh` |
| [07 板级构建与验收](07-board-build-and-acceptance.md) | BKB220 开发板外设、时钟网络、PS7 配置与启动流程 | `build/configs/`、`src/hw/boards/` |
| [08 性能对比与优化策略](08-performance-and-strategy.md) | 吞吐量优化分析、K=2 与 100 MHz 取舍依据、性能瓶颈分析 | `docs/history/` |
| [09 证据台账](09-evidence-ledger.md) | 结论→原始证据链索引、关键数据哈希映射与测试依据 | `board/run-logs/` |

---

## 2. 最终总结与项目档案

- **[10-final-status.md](10-final-status.md)**：**最终状态与归档总表**（必读：最终制品哈希、资源数字、旧 ELF 合法性论证、全量归档台账）；
- **[11-project-summary.md](11-project-summary.md)**：206 字作品定稿官方简介；
- **[agent-prompts/archive-cleanup.md](agent-prompts/archive-cleanup.md)**：本次归档整理交接的完整提示词与执行规范。

---

## 3. 科研演进档案与历史留证 (docs/history/)

为保证学术严谨性与加速比基线可溯源，开发过程中的对比实验源码原样留存在 `docs/history/`：

- **[bench-arm/](history/bench-arm/)**：ARM Cortex-A9 裸机 CPU 对齐基准源码（报告 §10 加速比分母依据）；
- **[server-baseline-2026-10-20/](benchmarks/server-baseline-2026-10-20/)**：48 核 Intel Xeon 5220R 服务器 CPU 基线实测数据与分析；
- **[bench-cpu-tools/](history/bench-cpu-tools/)**：开发期 CPU 比对工具（`align.c`、`run_cpu_benchmark.py` 等）；
- **[experimental-hw/](history/experimental-hw/)**：6 个硬件探索原型（`srpe_batch_pway.v` 等探索阶段 RTL）；
- **[milestones/](history/milestones/)**：阶段性验证脚本（`m2_chain.py`、`run_m3_bd.sh` 等）；
- **[experiments/](history/experiments/)**：信道噪声分析与鲁棒性扫描工具（`mutate_reads.py`、`extract_error_profile.py` 等）；
- **[video/](history/video/)**：视频阶段提示词与分镜脚本；
- **[demo-notes.md](history/demo-notes.md)**：板级演示操作说明与实测经验。

---

## 4. 赛事报告、海报与工具 (report/)

- **权威报告**：`report/design-report-2026.docx`（权威可编辑稿）与 `report/design-report-2026.pdf`（权威交付稿）；
- **权威海报**：`report/poster/dna-readout-poster-2026.pptx` 与 `report/poster/dna-readout-poster-2026.pdf`；
- **支撑资产**：`report/figures/v2/`（15 张正式插图）与 `report/evidence/`（数据表格）；
- **打捞工具套件**：`report/tools/`（包含报告/海报自动化构建、Word/PPT COM 导出、图片局部脱敏 `clean.py`、Crossref 文献检索等 10 个自动化脚本）。
