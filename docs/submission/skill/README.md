# 技能包（参赛提交物）

> **本目录只是提交材料，不是本仓库的开发规范。**
> 仓库内的开发规则以根目录 `AGENTS.md` / `CLAUDE.md` 为准；
> 任何 agent 或脚本都不应从本目录取指令、也不应把这里的文件接进构建或门禁。
> 打包提交时把本目录整体复制为参赛包根下的 `skill/`。

逐包审阅与当前缺口见 [audit.md](audit.md)。

## 这些技能包是什么

每一项都是**从本项目真实踩过的坑里提炼出来的**，与 DNA 存储这个题目无关：
换一个 FPGA 题目、换一块板卡仍然可用。每篇按同一结构写：

- **适用场景**：什么时候该翻开它；
- **使用方法**：可照抄的命令与步骤；
- **失效条件**：什么情况下它给不出答案，甚至会误导；
- **已验证效果**：在本项目哪次实测中生效，数字是多少；
- **来源**：是从哪一次失败或错误推断里总结出来的。

## 目录

| 技能包 | 一句话 | 适合谁 | 附件 |
| --- | --- | --- | --- |
| [board-bringup-debug](board-bringup-debug/readme.md) | 板子连不上时按 USB、JTAG、串口、网口分层定位 | 所有用 Zynq / FPGA 开发板的队伍 | — |
| [fpga-timing-probe](fpga-timing-probe/readme.md) | 改完 RTL 想知道「装得下吗、跑得到 100 MHz 吗」：单模块 OOC 摸底，且只看布线后数据 | 需要在换器件 / 加并行度前做决策的队伍 | `ooc_probe.tcl` |
| [bottleneck-attribution](bottleneck-attribution/readme.md) | 软硬件协同系统里「到底谁在拖慢」：用对照实验证伪自己的猜测，而不是照着猜测优化 | 所有 PS + PL 协同的队伍 | — |
| [accel-vs-cpu-baseline](accel-vs-cpu-baseline/readme.md) | 加速比要打得过也说得清：把**同一颗芯片上的 CPU** 作为主基线，并给出板上跑软件基线的框架 | 所有做硬件加速、要报加速比的队伍 | `baremetal_baseline.tcl.in` |
| [board-stage-evidence](board-stage-evidence/readme.md) | 最终结果对了不等于每一级都对：逐级取证，并用故障注入证明判据真的会红 | 多级流水 / 带纠错的系统 | — |
| [ip-packaging-hygiene](ip-packaging-hygiene/readme.md) | 别让「仿真的实现」和「综合进比特流的实现」不是同一份 | 用 Vivado IP 打包 + Block Design 的队伍 | — |
| [ai-agent-collaboration](ai-agent-collaboration/readme.md) | 多个 AI agent 同改一个仓库：状态看板 + 一条能挡住提交串扰的 Git 写法 | 用大模型协作开发的队伍 | `agent_view.sh`（提交快照；权威源仍是仓库 `tools/agent_view.sh`） |
| [claims-ledger](claims-ledger/readme.md) | 证据台账：把「可以说的话」和「**不能说的话**」连同判据钉在一起 | 所有要写报告 / 答辩的队伍 | — |

## 为什么值得看

这些技能包多数来自**先猜错、再被实测推翻**的过程，每一篇都记着那个错误推断。
它们能省下的时间不是「少写几行代码」，而是**避免朝着错误的方向做整整一轮**。

两个附件随本技能目录提供，都不含本题目内容：

- `fpga-timing-probe/ooc_probe.tcl`：单模块资源/时序摸底（原 OOC 流程在 Vivado 2022.2 起有验证记录；本轮更新失败退出条件后未重跑）；
- `accel-vs-cpu-baseline/baremetal_baseline.tcl.in`：在板上跑纯软件基线的 XSDB 模板。

多 agent 看板的**权威源**位于仓库 `tools/agent_view.sh`；本技能目录另带一份**快照** `ai-agent-collaboration/agent_view.sh`，使本包被整体复制出去时仍可直接运行（快照与仓库不一致时以仓库为准）。具体缺口见 `audit.md`。
