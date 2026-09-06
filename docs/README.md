# 文档索引（精简版）

新会话只需按以下顺序阅读，不要默认扫描历史归档：

| 文档 | 用途 |
|---|---|
| [01-architecture.md](01-architecture.md) | 系统架构、三级流水线和实现边界 |
| [02-data-contract.md](02-data-contract.md) | 编码、位序、几何和 5b4b 唯一契约 |
| [03-status.md](03-status.md) | 当前已闭环结论、未关闭问题和证据纪律 |
| [04-roadmap.md](04-roadmap.md) | 总体开发顺序与阶段验收 |
| [05-interfaces.md](05-interfaces.md) | TCP、寄存器、DMA、DDR 地址和协议 |
| [06-implementation-plan.md](06-implementation-plan.md) | 开发前检查、变更分类和提交门禁 |
| [07-performance.md](07-performance.md) | CPU/FPGA 基线、Stage1 瓶颈和性能口径 |
| [08-verification-plan.md](08-verification-plan.md) | 仿真、真实接口、BD 和 G3 验证层级 |
| [09-board-build-and-acceptance.md](09-board-build-and-acceptance.md) | 板级配置、构建、BOOT.bin 和上板验收 |
| [10-current-handoff.md](10-current-handoff.md) | 当前接手顺序和主线任务 |
| [11-optimization-plan.md](11-optimization-plan.md) | Stage1、数据泛化、错误鲁棒性和上位机优化 |
| [12-stress-analysis.md](12-stress-analysis.md) | 自动压测统计口径和后续改造 |
| [13-final-delivery-roadmap.md](13-final-delivery-roadmap.md) | **从当前状态到最终交付的总收口计划**：终态定义、现状评价、G0～G8 阶段门禁 | 每次排期和收口前必读 |
| [14-git-parallel-workflow.md](14-git-parallel-workflow.md) | 当前有效的共享 main 并行与回收纪律 | 并行任务开始和交接前必读 |
| [15-resume-and-parallel-plan.md](15-resume-and-parallel-plan.md) | 中断恢复、最终目标与 W0～W4 并行计划 | 新主会话执行入口 |
| [16-interrupted-work-audit-2026-09-06.md](16-interrupted-work-audit-2026-09-06.md) | 本轮中断遗留物清点与 dump 复核证据 | 了解本轮审计结果 |
| [prompts/main-resume-supervisor.md](prompts/main-resume-supervisor.md) | 可复制给新主会话的监督提示词 | 启动新会话时使用 |

## 参考资料

- `docs/board/`：板级只读资料、板测运行摘要；
- `docs/benchmarks/`：性能对照数据；
- `docs/reference/`：数据集、旧审计和历史来源；
- `docs/archive/history/2026/`：历史交接、旧计划、旧状态全文，只用于追溯，不作为当前入口。

## 工具入口

```text
tools/golden_model.py verify-code   # 算法契约
bash tools/run_sim.sh               # RTL 回归
bash tools/run_xsim.sh all          # XSim 接口回归
bash tools/run_m2_full.sh           # 三级串联
bash tools/run_g3.sh ...             # 板端 G3
python3 tools/stress_test_suite.py  # 长稳压测
```
