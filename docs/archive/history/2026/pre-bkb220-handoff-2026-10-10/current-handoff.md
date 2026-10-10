# 10 · 当前交接摘要

## 接手顺序

当前新板迁移任务先读 [20-bkb220-16way-migration-plan.md](bkb220-16way-migration-plan.md)，按其中文件归属和阶段门禁接手；旧生产基线与新板未验边界见03的P13～P16。

```text
docs/README.md
→ 03-status.md
→ 15-resume-and-parallel-plan.md
→ 按任务补读 01/02/05/08/09/11/12/13/14
```

## 新板迁移当前交接

迁移准备源码已在本地落地，计划已推送 `c4d7ad4`，用户已授权这批迁移准备代码提交并推送，main正在完成本阶段提交。P4/P16 参数与正式源集、独立 oracle/包装接口、G3 完整制品门禁和性能入口已完成；47 个主机用例与 LC6 三项检查通过，LC50 正式算法与包装接口在 Windows2026.1 XSim均通过，Icarus LC50模块周期一致。Windows2026.1 在旧 ECO XSA 上已实际生成并核查 BSP/应用 ELF/FSBL/BOOT。详见20计划及其三份 benchmarks 摘要。

main 接管 `sw/app` 和未完成的子任务。需要实物供电、USB 调试口、网线和对应原厂原理图/preset；`bkb220` 配置当前 ready=0，不能自行解除。未生成新板 bit/XSA，也没有新板时序或 G3 真板 PASS。保留全部旧制品、失败探针与源码备份/stash。

## 当前主线

1. 不改动真实数据集；
2. 保留已落盘脚本、数据和失败 dump，审计记录见 [16](interrupted-work-audit-2026-09-06.md)；
3. 按 [15](resume-and-parallel-plan.md) 分波推进公平基准、板端等价模型、上位机 profiling；
4. 4/8-way 保留候选资格，不依靠旧资源表封死，也不承诺线性提速；
5. 构建和板卡独占，Git 主会话统一写入；共享 main 规则见 [14](git-parallel-workflow.md)；
6. 工作规范见 [AGENTS.md](../../../../../AGENTS.md) 与 [14](git-parallel-workflow.md)。

## 历史资料

所有旧交接、并行会话、SE250 调研和产品路线图均保留在 `docs/archive/history/2026/`，新任务不应默认阅读全部历史文件。
