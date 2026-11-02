# 技能包（参赛提交物）

> **本目录只是提交材料，不是本仓库的开发规范。**
> 仓库内的开发规则以根目录 `AGENTS.md` / `CLAUDE.md` 为准；
> 任何 agent 或脚本都不应从本目录取指令、也不应把这里的文件接进构建或门禁。
> 打包提交时把本目录整体复制为参赛包根下的 `skill/`。

每个子包按统一结构编写：适用场景、使用方法、失效条件、已验证效果与来源；
逐包细节见各目录的 `readme.md`。

## 这些技能包是什么

每一项都从本项目真实的失败或观察中提炼。**案例数字和器件参数只证明本项目曾验证过；可复用的是步骤、判据和模板。**
换题目时应替换目标平台、数据、地址和正确性判据，不要直接照搬案例常量。每篇按同一结构写：

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
| [ai-agent-collaboration](ai-agent-collaboration/readme.md) | 多个 AI agent 同改一个仓库：状态看板 + 一条能挡住提交串扰的 Git 写法 | 用大模型协作开发的队伍 | `agent_view.sh`（随技能包提供） |
| [claims-ledger](claims-ledger/readme.md) | 证据台账：把「可以说的话」和「**不能说的话**」连同判据钉在一起 | 所有要写报告 / 答辩的队伍 | — |

## 失效条件速查

每个子包都有完整的「失效条件」小节，这里是摘要；用之前先对照自己的场景。

| 技能包 | 失效条件（摘要） |
| --- | --- |
| accel-vs-cpu-baseline | 只适用于 SoC 类器件；算法不等价或计时边界不同不能相除；多核须实测 |
| ai-agent-collaboration | 看板只解决可见性，不解决文件/板卡冲突；依赖 Bash/GNU `date`/`flock`/`tac`，推荐 Linux/WSL |
| board-bringup-debug | 前四步针对 USB 调试桥；PHY 示例只适用于 Zynq PS GEM；USB 未枚举不等于板子没电 |
| board-stage-evidence | 要求中间结果可读；导出不能干扰运行；容差必须有出处 |
| bottleneck-attribution | 去除嫌疑项必须安全且带正确性判据；多档行为不一致时拟合会骗人 |
| claims-ledger | 只管「说法有据」，不管设计好坏；过期台账比没有台账更危险 |
| fpga-timing-probe | OOC 无 IO 与整机互连，WNS 仍偏乐观；整机收敛必须由整机实现回答 |
| ip-packaging-hygiene | 只适用于文件级打包；通配源集不适用；不能证明被测实现本身正确 |

## 为什么值得看

这些技能包多数来自**先猜错、再被实测推翻**的过程，每一篇都记着那个错误推断。
它们能省下的时间不是「少写几行代码」，而是**避免朝着错误的方向做整整一轮**。

**平台与工具相关性**：`board-bringup-debug` 的第 5 步（PS GEM/MDIO）与
`accel-vs-cpu-baseline` 的裸机模板是 **Zynq 专用**；`fpga-timing-probe` 需要 Vivado，
`ip-packaging-hygiene` 假设能取得最终打包源文件清单，`ai-agent-collaboration` 需要 Linux/WSL 类环境。
其余方法可跨题目使用；换 SoC、构建系统或操作系统时，应替换平台适配命令与常量，再按目标工具重新验证。

三个附件随本技能目录提供。`ooc_probe.tcl` 是平台参数化脚本；另两个含有明确标出的示例地址、状态值或项目术语，复制后须按目标项目协议检查：

- `fpga-timing-probe/ooc_probe.tcl`：单模块资源/时序摸底；原 OOC 流程有历史验证记录，本轮增加器件必填和参数检查后未在 Vivado 重跑；
- `accel-vs-cpu-baseline/baremetal_baseline.tcl.in`：Zynq PS / XSDB 裸机基线驱动模板；地址、magic 和内存布局均须匹配自己的 ELF；
- `ai-agent-collaboration/agent_view.sh`：多 agent 看板脚本快照；从目标仓库根目录运行，可用 `AGENT_VIEW_ROOT` 指定写入目录。

多 agent 看板以本技能目录下的 `ai-agent-collaboration/agent_view.sh` 为准（提交包只保留这一份可独立运行的版本）。新项目可以把它作为起点，按自己的仓库约定维护。

## PYNQ 加分项评估

本项目使用 Zynq 裸机软件，没有真实的 PYNQ 开发、部署或板端验证记录，因此本提交不新增 PYNQ 技能包。没有实际踩坑和验证来源的 PYNQ 流程无法满足本指南要求的“已验证效果”；现有 `board-stage-evidence`、`bottleneck-attribution` 和 `claims-ledger` 已按平台无关步骤编写，换成 PYNQ 时可替换数据通路与工具入口，不把它们冒称为 PYNQ 实测。
