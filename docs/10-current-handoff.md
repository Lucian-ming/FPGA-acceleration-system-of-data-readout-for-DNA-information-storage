# 10 · 当前交接摘要

## 接手顺序

```text
docs/README.md
→ 03-status.md
→ 15-resume-and-parallel-plan.md
→ 按任务补读 01/02/05/08/09/11/12/13/14
```

## 当前主线

1. 不改动真实数据集；
2. 保留已落盘脚本、数据和失败 dump，审计记录见 [16](16-interrupted-work-audit-2026-09-06.md)；
3. 按 [15](15-resume-and-parallel-plan.md) 分波推进公平基准、板端等价模型、上位机 profiling；
4. 4/8-way 保留候选资格，不依靠旧资源表封死，也不承诺线性提速；
5. 构建和板卡独占，Git 主会话统一写入；共享 main 规则见 [14](14-git-parallel-workflow.md)；
6. 工作规范见 [AGENTS.md](../AGENTS.md) 与 [14](14-git-parallel-workflow.md)。

## 历史资料

所有旧交接、并行会话、SE250 调研和产品路线图均保留在 `docs/archive/history/2026/`，新任务不应默认阅读全部历史文件。
