# 03 · 当前状态与交接

更新：2026-10-11。本文件合并当前状态与原10交接摘要；旧完整状态/审计留在[归档索引](archive/history/2026/pre-bkb220-handoff-2026-10-10/README.md)。接手先读[05执行计划](05-implementation-plan.md)和[主Agent提示词](agent-prompts/main.md)，板级细节见[07](07-board-build-and-acceptance.md)。设备与资料枚举属于2026-10-10/11交接快照，接管时重新核实现场；已有准备检查和新板未验收的边界分别保留。

## 1. 当前目标与完成边界

本轮是旧ZYNQ ECO R6 / XC7Z010→BKB220 / XC7Z020、SE150、PL100MHz、Stage1 16滑窗位置并行。帧仍64记录、生产几何150/50/807/957/64、线上协议和8100B结果不变。新板尚无完整配置、bit/XSA、整机时序或真板G3结果。

用户已授权迁移准备源码及文档提交推送，并要求合并文档、安排详细流程及Agent提示词、监控实施和整理工作区。当前已交付的准备成果不能代替新板验收。

## 2. P13～P15：旧板与候选基线

| 事实 | 证据及适用范围 |
|---|---|
| P13旧板SE150全量及超时修复已板验 | 103616板端记录；全量中位数25.69s、2016源读段/s；单核C约1.48倍，仍慢于16线程约6.9倍；板级run摘要在docs/board/run-logs/20260922T*，[性能策略](08-performance-and-strategy.md) |
| P13修复使用30s墙钟超时 | Voter/Decoder原按poll次数会误超时；主循环事件推进/cache优化保留，不能盲删200us节流 |
| P14候选P16只做功能/OOC | XC7Z020生产几何OOC 26867 LUT、WNS+0.705ns，未整机/未上板；[摸底摘要](benchmarks/stage1-pway-7020-probe.md) |
| P15同片ARM纯软件基线 | 单A9约12.10ms/记录，1024记录结果逐条核对；相对旧PL每记录0.2451ms约49倍；[ARM摘要](benchmarks/measured_arm_baseline.md)；双核/能耗未测 |
| 泛化、误接受率、故障恢复有历史证据 | 多payload与G5/G6摘要见09；均注明旧板/主机/合成边界，不能自动升级为新板通过 |
| SE250是独立历史profile | 当前发布生产几何150；旧SE250成功与当前BKB220迁移分开，不能混制品 |

## 3. P16：本轮迁移准备已验证内容

| 成果 | 实际结果/证据 |
|---|---|
| 正式P4/P16参数与源集 | 默认4/0，可选16/1；打包与Vivado2022.2真实catalog通过；[集成摘要](benchmarks/stage1-16way-ip-integration.md) |
| LC50独立模块与真实AXI包装接口 | Windows2026.1 XSim两个case各两轮PASS；Icarus LC50模块同周期PASS。模块P4=1680956、P16=513755周期，约3.27倍仅模块周期改善 |
| G3主机门禁与矩阵编排 | 40+7=47项通过，使用fixture/替身；[主机摘要](benchmarks/bkb220-host-verification.md) |
| 工作树固件行为 | 主机行为回归通过；SDT/BSP兼容与64位超时修改未更改预期寄存器/DMA行为 |
| 现代软件生成入口 | Windows2026.1旧ECO XSA的A14实际生成BSP/应用ELF/FSBL/BOOT/readback及六产物SHA通过；PS5 wrapper正反用例通过；[工具摘要](benchmarks/bkb220-toolchain-audit.md) |
| 工作区与文档整理 | 根编号文档20份合并为9份；旧内容及映射保留归档；历史生成物精确忽略、原位保留；[整理记录](reference/workspace-cleanup-2026-10-10.md) |

Icarus重复LC50接口长测在XSim正式接口通过后主动停止，不称Icarus接口PASS。旧BSP13个C文件编译通过，临时旧链接探针因Newlib/VFP ABI失败，不能称旧工具链重建成功。起点参赛agent_view.sh重复附件已改为引用tools唯一源解决；源SHA未变，旧失败日志保留。

## 4. 未关闭的依赖与后续顺序

2026-10-11资料更新：用户提供的[BKB220产品手册v1.1.pdf](board/bkb220/BKB220产品手册v1.1.pdf)已随仓库收录；原件与副本SHA-256一致，来源、校验命令见[资料索引](board/bkb220/README.md)。main和board-migrate先阅读并校验仓库内手册，使用手册页码注明规格来源，不再把产品手册列为缺项或依赖微信目录。

2026-10-10/11设备核查快照没有实际FTDI/JTAG/PS USB串口，只见蓝牙COM3/COM4；厂商对应PCB原理图、PS7 preset/board_files/原厂例程、实物完整料号及PS时钟/DDR/UART MIO/PHY仍待确认。接管时重新核对这些资料与实际设备；手册收录不改变`hw/boards/bkb220.tcl`的ready=0，也不代表新板配置或真板验收通过。

按05的F2～F9继续：可靠配置→最小UART/DDR/GEM/CAPS→新板P4基线→P16完整route和同XSA软件包→全量/连续/恢复→同板性能及相关泛化/长稳→独立交付。功耗需仪器；SE250另profile；D0不默认分发。没有新板实测就不能宣布迁移完成。

## 5. 接手和证据纪律

- 起点467d90e和计划c4d7ad4是历史记录；先核对最新HEAD/main/origin，不回退覆盖已完成工作。
- 先读规范、现成05计划/07与本轮摘要，再按当前文件清单核对源码/配置/工具，从尚未完成阶段继续。旧子Agent中断与设备枚举属于交接快照，接管前确认实际状态；不重新制定计划或从零重做已有成果。
- 主Agent统一Git/文档和资源，按提示词派发独占任务、审查消息/diff/日志/哨兵；Git前所有writer停写。
- 仿真/单测/构建/制品SHA均不能替代真板；hash自洽不能证明源码因果，修改后重建受影响全套制品。
- 失败、未测、工具异常和边界失败如实保留；可对外说的话先查[09证据台账](09-evidence-ledger.md)。

本轮按计划执行的F0/F1与F2只读核查见[检查点](reference/bkb220-handoff-checkpoint-2026-10-10.md)。

文档/脚本整理收尾后，工作树固件2项及仓库卫生11项均通过；旧发布五制品SHA全部OK。

2026-10-11交接更新：主子Agent通道与模型按3ad6fbd同步到05及完整提示词；最终47项主机测试、固件2项、打包和卫生11项通过，日志在logs/host/handoff-final-20261011。当前仍是迁移准备交付，BKB220新板验收未完成。

2026-10-11后续收尾：通道规则更正提交b3c70b3已保留；main经既有host-proxy做过只读冒烟；2026-10-11 00:40 更正：改用用户新装的 codex-luna MCP（客户端 codex-cli 0.162.0-alpha.17.2）后 gpt-6-luna/max 实测可用（只读11.7s、workspace-write 34.0s，均 completed/ok/exit0/turn_completed），旧的「暂用gpt-5.6-luna」结论作废（更正提交25c3336）。新板资料、连接和真板验收状态不变。

2026-10-11全仓残留复查：现成05计划直接接管；MCP/gpt-6-luna/max与只读任务看板责任已统一，旧编号和失效链接修复。CAPS/DDR说明对齐当前129600记录容量及SE150宏，参数和算法未改。工作树固件2项、G3主机47项、公平基准契约8项、打包及卫生检查通过；证据在logs/host/current-residue-20261011。归档20份、冻结黄金、旧发布五制品和保留资产哈希均核验。旧XSim源SHA继续指向当时输入快照，当前仅注释变化的等价证据另存，没有重录manifest或新板验收。
