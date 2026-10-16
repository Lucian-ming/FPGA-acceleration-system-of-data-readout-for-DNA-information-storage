# 05 · 全项目执行计划与多Agent运行手册

更新时间：2026-10-13。本文把项目地图、文档/脚本入口、从当前准备成果到新板交付的完整流程、子Agent分工和监控收敛放在同一入口。用户已明确授权本批代码与文档提交推送，并要求整理工作区。详细任务提示词在[agent-prompts/](agent-prompts/readme.md)。

## 1. 全项目地图与事实优先级

唯一checkout：`/home/lucian/projects/FPGA/FpgaAccelerationSystemOfDataReadout`，Windows访问为`\\wsl.localhost\Ubuntu\home\lucian\projects\FPGA\FpgaAccelerationSystemOfDataReadout`。唯一远端：`Lucian-ming/FPGA-acceleration-system-of-data-readout-for-DNA-information-storage`，只在main开发，主Agent是唯一Git写入者。

项目的编码侧不在本仓库：54000 bit信息→64800 bit LDPC→81000 bit稀疏流→水印XOR→40500 nt。读出侧包含PC FASTQ处理、协议、PS控制/DDR/cache/DMA、三段PL、PS Stage2.5 XOR、PC LDPC与图像哈希。它包含多种载体，不能把全部计算都称为PL。

| 组件 | 权威入口与应理解的内容 | 接手风险 |
|---|---|---|
| 数据/算法 | 02、data/MANIFEST.md、tools/golden_model.py、readout.py、make_golden.py；碱基A/T/G/C=0/1/2/3，位平面、5b4b码表、LSB位序 | 历史演示水印不同；原始D0不修改、不随意分发 |
| PL Stage1 | hw/ip/Dna_accelerator_core_1_0/component.xml、hdl顶层及两个正式batch核、XGUI、PACKAGED_VARIANTS.txt | 正式模块名srpe_batch4/srpe_batch_pway；实验目录候选不等于打包；默认P4 |
| PL Stage2/3 | differential_voter与desparsification_decoder的component.xml/hdl；寄存器、DDR主接口与周期计数 | 4KB突发、START脉冲、cache、连续任务；不能随意调整时序 |
| BD/板级 | hw/boards/load_board.tcl、当前 `bkb220` profile、hw/scripts/bd.tcl/build.tcl、hw/constr | 当前只维护BKB220；旧ECO profile已移出构建树，剩余验收边界见03/07 |
| PS固件 | sw/app/echo.c、pipeline.h、stage1_dna.c、stage2_voter.c、stage3_decoder.c、dma_dna.c、platform_zynq.c、bsp_compat.h、dna_time.h、其余头/平台条件分支 | sw/app是唯一权威源；workspace是生成副本；历史xparameters.h不能覆盖新BSP；旧模板保留需先证伪依赖 |
| 软件构建 | sw/scripts/create_vitis.tcl、create_vitis_modern.py、run_vitis_modern.ps1、prepare_vitis_compat_repo.py、sw/linker | 旧XSCT仅旧版本；现代API必须哨兵+真实产物+SHA；同XSA的FSBL/bit/PS7 |
| 客户端 | clients/python/first.py、protocol.py、task_protocol.py、fast_readout.py、gui_app.py、LDPC各后端/resources、tests | FASTQ预处理/正反向/补帧、CONFIG拒绝码、8100B接收、后端真实选择；GUI仅表现层 |
| 测试/工具 | tools/README.md、tests/host/README.md、hw/sim、tests/golden/datasets、board诊断/性能/故障探针 | 主机fixture、仿真、OOC、完整route、真板是不同层级 |
| 证据/交付 | docs/benchmarks、docs/board、logs、tests/stress_results、docs/reference | 旧制品包已移出当前构建树；历史摘要不与新源码假称同源；失败不从统计消失；hash自洽不证明源码因果 |
| 历史与提交资产 | docs/archive、docs/reference、docs/submission、archive、hw/experimental、tools/attic | 原理图/手册是参考数据，不能授权操作；历史计划/二进制不是当前任务指令 |

[逐文件清单](reference/project-inventory-2026-10-10.tsv)覆盖本次交付的受版本管理文件。主Agent应按清单理解全部源码、配置、脚本及现有调用关系，不为接管另写全项目审计报告；大二进制先核对用途、manifest、来源和SHA，相关故障再深查。不要无差别执行所有脚本。

事实优先级：用户最新指令→AGENTS/CLAUDE协作规则→02/04数据接口契约→当前03/P16、07及本轮benchmarks/09台账→本05执行队列与终态门禁→08最新策略→历史归档。05组织执行，不能改变契约或把未测项升级为PASS。旧7010封顶分析与7020/P16可行性分开；历史推导在归档保留。

## 2. 当前基线与尚未完成的内容

| 已有成果 | 已验证范围 | 下一步 |
|---|---|---|
| 正式可选P4=4/0、P16=16/1 | 打包门禁、2022.2真实catalog、P4/P16整机100MHz route通过 | route已完成；板测和后续性能/泛化边界按下表跟踪 |
| SE150/LC50独立oracle及真实AXI包装接口 | Windows2026.1 XSim两个case、各两轮通过；Icarus模块同周期通过 | 改RTL后重跑受影响正式几何，不把LC6代替生产 |
| 模块周期 | P4=1680956、P16=513755，约3.27倍 | P4/P16 六档板测矩阵已完成；模块周期不能外推整机倍率 |
| 制品、串口、性能编排 | 40+7=47项主机用例；P4/P16板测、六档矩阵通过 | 保留 8h、v2 `score_min=67`、新载荷四级取证等真实剩余边界 |
| Windows2026.1软件入口 | A14旧ECO XSA兼容探针的BSP/应用/FSBL/BOOT与readback/SHA结果保留为历史证据；PS5 wrapper正反用例通过 | 新板P16完整同XSA软件包已构建并G3 PASS；一键自动化链路仍有补步，F9仍待执行 |
| 数据和历史基线 | 旧发布包已移出当前构建树；历史摘要、原始数据和证据保留 | 新目录独立保存，不覆盖发布包 |

Icarus LC50接口重复长测在XSim正式接口已通过后主动停止，日志标记INTERRUPTED_DUPLICATE_AFTER_XSIM_PRODUCTION_PASS；不是Icarus接口PASS。旧BSP下13个C文件编译通过，但临时旧链接探针因Newlib/VFP ABI失败，不能称旧工具链完整重建。起点参赛agent_view.sh重复附件已改为引用tools唯一源码解决，旧失败日志及附件Git历史保留，未放宽门禁。

2026-10-11已把用户提供的[bkb220-product-manual-v1.1.pdf](board/bkb220/bkb220-product-manual-v1.1.pdf)收录至仓库，原件与副本SHA一致；[资料索引及校验](board/bkb220/README.md)是接管入口。main和board-migrate先完整阅读PDF，在docs/board/bkb220目录运行`sha256sum -c SHA256SUMS.txt`，再核对对应PCB/实物及原厂配置；引用手册规格时注明页码。产品手册已具备，后续只按实际缺项补齐原理图/preset/例程，不重新制定计划。

~~硬件核查快照（2026-10-10/11）：当时只读枚举只有蓝牙COM3/COM4，没有FTDI/JTAG~~（**2026-10-12 作废**：BKB220 已到货连接，JTAG 实测为 xc7z020，FT4232H 提供 JTAG + COM9/10/11；见 [03 §1a](03-status.md) 与 [07 §3a](07-board-build-and-acceptance.md)）。原理图已入库，PS UART 与 ENET0 PHY/复位均已确认；厂商 board_files/PS7 preset/例程、实物完整料号仍待确认。**工具链分工（用户 2026-10-12 明确）：开发全部在 WSL 用 Vivado/Vitis 2022.2；Windows 里的 2026.1 只负责烧录。** 22 主线是唯一发布线，26 不产出新板验收制品；`ready=1` 不代表所有迁移门禁完成。

**当前阶段状态（2026-10-13）**：F0/F1 完成；F2 profile 已核实并置 `ready=1`；F3 UART/DDR/ENET0 已通过；F4 P4 整机 G3 与 P4/P16 route/构建完成；F5 P16 同 XSA 包已构建并 G3 PASS；F6 全量/连续/恢复/故障探针完成；F7 六档矩阵及 P4/P16 v2 42 例对照完成；F8 已完成 2 h，8 h 未完成。v2 的 `score_min=67` 未板测，新载荷四级取证、冷启动、UART 反向、功耗及 F9 仍未完成。证据见 [03](03-status.md)、[07](07-board-build-and-acceptance.md) 与各 benchmark。

用户指定的开发顺序（2026-10-11）：开发全部在 WSL 使用 Vivado/Vitis 2022.2，Windows 2026.1 只负责烧录、下载和调试。P16 完整同 XSA 包已有构建及 G3 证据；自动化构建链仍有 Vitis 生成与应用构建补步。Windows 2026.1 完整开发链复核排在 22 主线优化和报告之后，规则见07。

## 3. 全流程计划与出口门禁

| 阶段 | 工作、负责者和输入 | 交付与出口门禁 |
|---|---|---|
| F0 接管既有计划与现场核对 | main读取本计划、清单及当前文档，核对仓库/HEAD/脏文件/工具/设备和已有证据；按需分配子任务 | 确认已完成/需复核/未完成阶段、具体依赖、路径归属和资源；现成计划直接执行，仅因事实变化修订，不重写计划 |
| F1 已有成果确认 | main对照07和三个benchmark；子Agent复核源集、API/制品、测试边界 | 必要短检查通过；已有长测来源可验证，不无故重跑；已知失败和阻塞有记录 |
| F2 新板配置落实 | main/board校验资料与profile；verify核对工具目标 | **完成**：BKB220 `ready=1`；原理图、PS_CLK、DDR、UART0/MIO14-15、ENET0/PHY/reset 已核实，PS7 配置经 Vivado 2022.2 校验。实物完整料号、PCB修订、DDR板级延迟/DQS-to-CLK仍待确认 |
| F3 新板最小启动 | board准备最小同XSA软硬包；main持板卡锁运行；verify协助留证 | **完成**：唯一JTAG、UART、DDR读写、ENET0链路和CAPS有通过记录（[来源表 §9/13](board/bkb220/migration-source-table.md)）。QSPI/SD冷启动仍未测 |
| F4 新板P4基线 | board以WSL22完整生成SE150/P4/100MHz整机和同XSA软件包；rtl审查路由；main/verify执行板测 | **完成**：合法route、完整包、G3 7/7，最终SHA和四级DDR判据通过；全量/连续结果见后续 F6/F7 |
| F5 P16整机候选 | rtl审查正式P16依赖和关键路径，board按同板profile生成独立目录；改动按层级回归 | **完成**：150/50/807/957/64及16/1贯通；LC50接口、100MHz route（WNS+0.617/WHS+0.017、失败端点0、33,987 LUT）及完整同XSA包通过；正式上传配置包 G3 PASS |
| F6 P16正确性与工程回归 | main持板卡/串口，verify编排；先smoke再全量，再连续和故障恢复 | **完成**：smoke、全量三轮、连续/状态复位、配置守卫、断连畸变和中途断网判据通过；详见相关 benchmark |
| F7 性能与泛化复核 | verify同板P4/P16六档≥3次矩阵；board提供合法完整包；main审核公平口径 | **已完成范围**：六档矩阵；P4/P16 对 v2 42 例与软件验证器 42/42 一致。8 个 challenge 例仍失败，v2 `score_min=67` 未板测，新载荷四级取证未完成 |
| F8 长稳与剩余终态门禁 | verify逐项重核本计划的G0～G8；main安排可用设备 | **部分完成**：2 h 长稳通过；8 h 未做。QSPI/SD冷启动、UART反向、功耗及新载荷四级取证仍未完成；SE250另制品/另几何 |
| F9 最后26开发复核与交付 | 22主线稳定后main冻结输入；board在独立Windows2026.1目录重建完整硬软包，rtl审查route，verify按07比较并独立复现；全部停写后交付 | 26同源包、100MHz合法route、功能/G3/恢复/性能及长稳比较记录；明确PASS/FAIL/未测和发布工具链。完整新板摘要、来源/制品/SHA链、复现命令、03/05/07/09与提示词同步；路径commit后立即push、0/0、源码工作区干净 |

状态表中的 F2～F8 按当前证据更新；已通过阶段不因计划表仍保留执行步骤而重新打开。未完成项继续按明确判据留证；若后续构建或复测失败，保留报告并按实际路径修复或回到已验 P4，不用无依据 false path 或降低频率宣布目标达成。

原迁移计划S2～S4对应F2～F8的新板核心门禁，S5对应F9。原13的G4/G5/G6历史成果要在新板候选上复核相关接口与正确性；G7独立复现仍受D0数据分发边界约束；G8材料制作只按用户需要进行。32路、Linux/PetaLinux、USB数据传输、HDMI、算法重写不纳入本轮。

### 后续总顺序（用户 2026-10-12 二度指示，**覆盖本文件 F9 的相对位置**）

用户明确要求把顺序调整为：

1. **完成本轮剩余门禁** —— B2 三项探针、C1 同板 P4/P16 六档 ≥3 次矩阵、C2 的 P4/P16 42 例对照和 2 h 长稳均已有通过记录；当前剩余是 8 h 长稳、v2 `score_min=67` 板测、新载荷四级取证及其他终态门禁。这些是 22 主线的**正确性与鲁棒性**验证，属于本轮。
2. **冻结 22 主线** —— 之后不再对它做修改。
3. **全面优化（时间消耗优化 + 性能优化）** —— 按当前测量和探针结果推进。旧 P7 的“非 Stage1 等待主要在 PS 侧”只适用于当时固件；当前处理段旧矩阵分解中 PL 约占 87.8%，不能把早期观察概括成当前整机瓶颈。
4. **优化完成即停止修改**（再次冻结）。
5. **写报告** —— 在上述冻结状态上出报告；**报告不早于优化完成**，以免文档与制品漂移。
6. **切到 26 开发** —— **Windows 2026.1 的完整开发/复核（原 F9）整体后移到优化与报告之后**，不再紧跟 22 主线完成。
7. 其余交付材料、清理与最终推送按第 6 节执行。

**因此对本文件前文的影响**：F9 不再是"22 主线稳定后立即做"，而是"优化完成并写报告之后再做"；F6～F8 的位置不变，仍在 22 主线内。旧文字若与本顺序冲突，**以本节为准**。

### 本轮之后的下一阶段：时间消耗优化与性能优化（用户 2026-10-12 指示）

**本轮（BKB220 迁移 + Stage1 16 路改造，F0～F9）走完之后，下一阶段的主题是「时间消耗优化与性能优化」。** 这里先记录方向与它必须遵守的证据纪律，**不改变本轮任何门禁，也不提前开工**。

为什么它是自然的下一步：`docs/09` P7 在 2026-09-11 旧固件、4096 条记录下观察到 Voter 29.6 ms / Decoder 0.022 ms，且非 Stage1 时间主要为 PS 侧等待与 Cache 维护；这只限定当时的阶段观察。当前 P16 处理段的旧矩阵分解显示 PL 约占 87.8%，PS 可归因函数工作约 2.1%（见下文），上传段也已转正为 0.40 s。因此优化方向应由当前同口径测量与探针判据决定，不能用旧 P7 结论否定 PL 优化。

**⚠️ 2026-10-13 更正——P7 的「lwIP poll 空等 2,777 ms」已不是当前固件的瓶颈，不要再照它定优化方向：**

- P7 那次拆解**评测于 2026-09-11**（`docs/benchmarks/measured_p7_cycle_counters.md` 第 3 行，留证 `g3_runs/20260911T140559Z/`），当时固件靠 lwIP 的 `tcp_poll` 回调（250/500 ms 级）驱动状态机，所以文字写的是「固件状态机改造为事件/中断驱动」——**那正是后来已经做完的事**。
- 当前源码 `sw/app/main.c:326` 是 `/* 3) 主动推进流水线 (P12-B 事件驱动，消除 poll 白等) */`，紧跟 `echo_pipeline_poll()`；`docs/03` 的 P13 行也记着「主循环事件推进/cache 优化保留」。**这条优化早已落地，不能再算作待收的 2,777 ms。**
- main 已复核：**冻结的 P4/P16 制品包与当前工作树源码逐字节一致**（各 60 条源清单，59 条相同、0 条不同、1 条为 manifest 显式排除项），所以本轮实测的每条记录成本（P4 0.2519 ms / P16 0.0814 ms）**就是**这份源码跑出来的。
- **当前运行期的头号可疑项变成了主循环节流**：`sw/app/main.c:28-30` 定义 `PIPE_RUN_SLEEP_US`，默认 `200U`，注释写明「流水线运行期主循环每圈的休眠（us），0 = 不休眠。**可用 `-DPIPE_RUN_SLEEP_US=N` 覆盖做对照实验**」，并在 `main.c:329-334` 注明「运行期 `[waiting]` ≈ 主循环次数 × 200 us，**每条记录的斜率由这一行决定**」。
- **所以 P3 的第一个实验应当是 `PIPE_RUN_SLEEP_US` 的 A/B 对照**（源码已内置编译期覆盖开关，改动小、可复现、判据明确），而不是继续找 poll 空等。**但它不能盲删**：`docs/03` P13 明确记着「不能盲删 200us 节流」（Voter/Decoder 曾按 poll 次数误超时，后改为 30 s 墙钟超时）。A/B 必须同时复验：唯一判据 SHA 不变、30 s 超时路径不被触发、连续/多轮任务的轮间行为不变。
- Cache 维护（396 ms）仍是有效目标；只读分析（`ps-opt-scan`，2026-10-13）给出的候选是「合并连续 BD 的 flush 范围」与「按 DDR 所有权去掉重复的全量 flush/invalidate」，两项都要各自带**能失败的判据**（范围覆盖集合必须与提交集合完全相同、环回最多拆两段）。**任何 PS 固件改动都要另存新的同步制品包，不得覆盖已冻结的 P4/P16 包。**

**2026-10-13 的板上实测（把上面的怀疑变成了数字）。** 长稳轮次的 UART 留证里带当前固件自己的分解，P16 包、全量 103616 记录：

```text
[PIPE] total 199214 steps in 42648 callbacks, 9246 ms
  [in-state]  695 ms
  [waiting]  8551 ms   <- 回到 lwIP 等 poll 的空等
[HW-CYCLES] Stage2 Voter: 644.933 ms    Stage3 Decoder: 0.022 ms
```

42648 次回调 × 200 µs = **8.53 s**，与 `[waiting] 8551 ms` 吻合——**92.5% 的流水线时间是那行节流睡的**。

**两个互斥的假设，A/B 就是为了分开它们**：

| 假设 | 预期结果 |
| --- | --- |
| **H1：节流是限制** | 缩短 `PIPE_RUN_SLEEP_US` 后端到端**按比例下降**（H1 成立则 P16 全量 9.0 s → 1~2 s 量级） |
| **H2：硬件才是限制，节流只是把等待记账成 `[waiting]`** | 缩短节流后 `[waiting]` 塌进 `[in-state]`，**端到端几乎不动**——这只是换了个计数器，不是优化 |

**先把 H2 摆在前面**：2026-09-22 旧板上那次 `p13b-no-throttle` 实验（`docs/board/run-logs/20260922T120216Z-p13b-no-throttle-summary.txt`）全量拿到 25.60/25.62 s，而同批次 `p13-release` 是 26.52 s——**只快了约 3.5%**，正是 H2 的样子。那次实验有两点今天必须做得更严：① 它用的是 `--elf` 指向包外临时 ELF，而 `run_g3.sh` 现在**明确禁止**这种混搭（守卫就在第 66 行），所以今天必须**产出完整变体包**；② 它只有两轮，没有分档斜率。

**判据（做完必须逐条回答）**：① 全量档唯一判据 SHA 仍为 `fcd0cf90…b1f2c3`；② 六档斜率是否真降（只降 `[waiting]` 不算数）；③ 30 s 墙钟超时路径未被触发；④ **RX BD 环是否吃紧**——`docs/03` P13 记「不能盲删 200us 节流」，且 2026-09-10 有过 `RX submitted=640 > ring free=512` 导致 Stage1 停顿约 30 s 直接 FAIL 的实录；若出现同类停顿，**说明节流确实在给 DMA 排空留时间**，该项判负并保留失败留证。

已归档可参考的负结果（**不要重复当作新方向**）：
- Voter/Decoder 微架构流水线化 —— 板端周期实测已证伪（即便归零，端到端提速 <1%）。
- 流式阶段批量推进 —— 两次尝试失败，`submitted=640 > ring free=512` 挂死；教训是**控制变量应取"在飞帧数"或 DMA 完成中断，而不是 RX ring 余量**（`docs/09` F3）。
- 多次 TX_STREAM 压缩尝试、精确种子索引 —— 均被实测证伪，见 benchmarks/归档。

下一阶段仍然遵守本文件全部门禁：**任何优化都要有能变红的判别性判据、公平同输入口径、失败证据保留**；不得为"看起来更快"而放宽正确性判据（图片 SHA `fcd0cf90…f2c3` 与四级 DDR 取证仍是硬门禁）。

### 总项目G0～G8终态门禁（保留原13门禁，当前进度重新核对）

| 门禁 | 在新交付中的判据 |
|---|---|
| G0 冻结与基线 | 源码/输入/板/profile/工具/制品可追溯；本轮SE150，SE250单列 |
| G1 统计可靠 | 时间边界/失败分类/重复数/分母一致，原始数据可重算 |
| G2 客户端/传输 | 协议/LDPC/结果完整，性能优化有公平测量，未引入断连/错误码回归 |
| G3 Stage1 | P4同板基线、P16正式功能/接口/整机100MHz/新板G3与性能，不以OOC替代 |
| G4 泛化 | 至少5独立payload，源文件哈希和恢复判据；旧板数据与新板复核分开 |
| G5 鲁棒 | sub/ins/del/覆盖度/阈值曲线、FAR/FRR定义、种子与失败，明确主机/板测范围 |
| G6 工程/功耗 | 冷启动项目单列、全量/连续/脏干净/故障恢复/长稳；有仪器才给功耗 |
| G7 冻结/独立复现 | 同源制品/脚本/manifest、独立复查；D0数据分发边界如实保留 |
| G8 报告/演示/交付 | 最新事实、限制、复现与提交同步；正式材料和发布按用户需要 |

既有负结果可关闭某个优化方向，不能替代产品正确性；旧候选池仅作追溯，不并行开展被证伪方向。

## 4. 子Agent分工、并发与监控

最多main+三子Agent同时运行；后续交接按AGENTS/CLAUDE当前规则（MCP更正见25c3336、f98302c）：主会话为Claude Code/DeepSeek（deepseek-flash[1m]），子Agent经用户级 codex-luna MCP 非交互进程（`codex_run`/`codex_status`）派发，固定 gpt-6-luna 与 model_reasoning_effort=max，不用Claude内置Agent工具，不自行换模型/强度、不再派生子Agent，不新建聊天/分支/worktree。各角色完整输入由角色提示词+最新阶段卡组成，派发前阅读与监控要求在[main提示词](agent-prompts/main.md#按最新文档派发与监控)，具体调用以AGENTS/CLAUDE及实际MCP工具定义为准。

当前执行入口为codex-luna MCP/gpt-6-luna/max，2026-10-11 00:40的只读与workspace-write验证记录见AGENTS/CLAUDE及09台账。旧CLI/gpt-5.6-luna冒烟只作为历史证据保留，不作为当前派发规则或降级依据。接管时核对MCP入口、实际客户端、任务状态及必要只读冒烟；凭据和代理服务由配置会话管理，本项目不擅改配置或关闭其服务。早期中断和原生审计助手记录是历史事实，接管时核实当前任务状态，从未完成项继续。

| 角色/看板名 | 独占文件 | 输入、输出、依赖 |
|---|---|---|
| main | README、docs根目录/索引/证据/交接、agent-prompts、.gitignore；唯一Git写入 | 接管摘要、现有计划进度和必要修订、派发/监控/审查、资源调度、真板操作、远程交付 |
| board-migrate | hw/boards、hw/constr、hw/scripts/bd.tcl/build.tcl、tools/run_vivado_build.sh、sw/scripts、sw/app、sw/linker；独占板级摘要 | 当前板级入口、仓库内BKB220手册/校验、旧ECO配置及对应PCB原厂资料；输出带资料路径/手册页码的来源表、可审计profile、同XSA完整制品、SDT/旧BSP兼容和软件测试报告 |
| rtl-16way | 三IP的相关RTL/component.xml/XGUI及PACKAGED_VARIANTS.txt、tools/check_ip_packaging.sh；独占RTL摘要 | 正式P4/P16代码和独立TB接口；输出源集一致性、参数、修复及综合/时序诊断。大型任务须main授权资源 |
| verify-system | hw/sim、tests、tools/board、run_sim.sh/run_xsim.sh/run_m2*/run_m3*、run_g3.sh、性能/泛化/故障/压测入口；clients/python仅必要迁移测试修复；独占验证摘要 | 生产参数/寄存器契约、板级完整包；输出独立判据、负用例、板测和矩阵报告，明确测试层级 |

按wave派发：F0/F1三Agent可并行审计；F2期间board整理资料、rtl评估源/时序风险、verify准备矩阵与故障脚本；F3/F4主要board/main执行，另两人静态审阅；F5只允许一个综合/XSim长任务；F6～F8只有一位板卡操作者，其他人分析已完成run；F9全部停止写入后main收敛。

共享文件修改必须先向main申请具体移交；main记录旧owner、新owner、路径和停止写入确认。board持有sw/app后main不同时改固件。RTL参数/模块端口/几何变更先通知verify和board，先更新契约再消费，不能各取一套名字。

资源表至少记录`resource/owner/purpose/MCP job_id/实际PID或session/开始时间/run及evidence_directory/释放条件`。资源包括Git、Vivado/XSim大型任务、真实板卡/JTAG、PS串口、下载/DDR dump、发布export。Git恒归main；同一时刻最多一个大型EDA任务、一个真实板任务、一个串口采集进程。下载、reset、halt、dump会影响正在运行的任务，都需要板卡资源。

main的监控循环：派发时附完整角色提示词、独占路径、已完成项、阶段卡及检查点；阶段卡补充本次执行上下文，不另建计划。使用codex_status按job_id查询，核对status=completed、ok=true、exit_code=0、turn_completed=true四项及真实diff；证据从返回的evidence_directory读取prompt.txt/run.jsonl/answer.md/result.json，不套用旧CLI的events.jsonl/final.md名称。MCP单次等待按工具定义分段，避免忙轮询，每10～15分钟或阶段变化核对实际进程、日志与资源并向用户说明新结果。没有原生消息通道时，workspace-write在指定报告中提出依赖，read-only通过最终答复交付，由main协调；改任务先阶段停写再附卡派发。

发现Agent退出、额度限制或长期无日志增长：先查MCP任务状态和实际子进程/文件写入者，停止重叠派发并保存证据；需要中断时优先按当前文档使用codex_cancel，确认终态及子进程停写后移交。必要时main接管，只终止本任务核实过的PID树，不杀全局同名进程。Git操作前要求全部writer停写并确认，不能以看板状态替代实际检查。

每个任务以tools/agent_view.sh登记start/update/block/done，三个字段具体；workspace-write由执行者登记，read-only由main代登记并归集MCP产物，禁止只读子Agent写文件或手改view.md。退出交接提供路径/diff、实际命令和退出码、参数/输入SHA/run-id、PASS/FAIL/未测、失败证据、资源释放和下一依赖。

## 5. 验证入口与判据的鉴别力

| 层级 | 入口 | 判据和边界 |
|---|---|---|
| 仓库/打包/卫生 | verify_repo_binding.sh、check_ip_packaging.sh、check_repo_hygiene.sh | 正确远端main；正式源集一致。重复附件通过唯一源引用解决，旧失败日志保留，门禁未放宽 |
| 算法契约 | `python3 tools/golden_model.py verify-code` | 使用本地只读D0，数据/编码模型正确，不代表真板 |
| 固件行为 | `bash tests/host/run_host_tests.sh --worktree` | 真实工作树C源码的寄存器/DMA/cache/TCP轨迹；默认HEAD测试不能替代未提交工作树 |
| 主机门禁 | `python3 -m unittest discover -s tests/host -p 'test_g3_*.py' -v` | 缺manifest/错part/错几何/SHA/版本、串口歧义、矩阵失败保留等负用例 |
| Stage1短/正式 | run_sim.sh stage1_production / stage1_production_full、run_stage1_xsim.ps1 | LC6排错；LC50生产；独立oracle+P4/P16两轮、末组/并列/补帧/反向、AXI真实包装 |
| 三级/BD | run_xsim.sh all、run_m2_full.sh、run_m3_bd.sh | 源码修改涉及接口时跑受影响层级；黄金几何/当前源集一致 |
| 构建 | run_vivado_build.sh、WSL22软件链；最后26现代Vitis入口 | 完整route/DRC/约束，实际XSA/BSP/ELF/FSBL/BOOT，成功哨兵+六制品SHA |
| 制品选择 | `python3 tools/board/g3_artifacts.py --artifact-dir <完整包>` | XSA内bit/part/HWH七参数、源码manifest、工具版本、SHA一致 |
| 真板唯一入口 | `bash tools/run_g3.sh --artifact-dir <完整包> ...` | 实际下载/任务/LDPC/最终SHA/四级DDR；禁止旧bit与新ELF混用 |
| 性能 | tools/board/g3_performance_matrix.py、run_cpu_benchmark.py、arm_baseline.py | 前者不自动烧录，先确认已加载同一包；ARM工具会复位整板，当前硬件假设先审计 |
| 泛化/故障/长稳 | run_multi_payload_regression.py、run_robustness_scan.py、g5_false_accept.py、run_g5_matrix.sh、board的guard/recovery/netfault、严格G3逐轮编排 | 先审计现用脚本的硬编码export/设备/几何；长稳按实际2h/8h留证。旧stress/switch已归档，不直接运行 |

任何新修复必须有能失败的判据：错误part、缺制品、非法P16组合应明确拒绝；已知START故障注入应变红；完整输入译码/图片失败必须保留并使功能门禁失败。小规模覆盖不足的译码失败不冒充整机故障，也不算完整正确性PASS。禁止为了全绿重录黄金轨迹或改成比较实现本身。

主线仿真使用WSL2022.2现有XSim/仿真入口，先核对实际版本；以下Windows2026.1命令是已有正式证据的复现及最后26开发复核入口，不能反过来要求先在26开发。RUN_ID自行选未使用值，输出目录必须全新：

```bash
python3 tools/board/generate_stage1_fixture.py --num-lc 50 --out-dir logs/iverilog/<RUN_ID>/fixtures
python3 tools/board/create_stage1_xsim_input.py --fixtures-dir logs/iverilog/<RUN_ID>/fixtures --out-dir /mnt/d/Agent/outputs/bkb220-xsim26/<RUN_ID>-input
```

Windows PowerShell用权威脚本或带SHA的脚本快照：

```powershell
& '\\wsl.localhost\Ubuntu\home\lucian\projects\FPGA\FpgaAccelerationSystemOfDataReadout\tools\run_stage1_xsim.ps1' -InputDir 'D:\Agent\outputs\bkb220-xsim26\<RUN_ID>-input' -RunDir 'D:\Agent\outputs\bkb220-xsim26\<RUN_ID>-run'
```

最后26软件重建所用JSON必填`repo_root/workspace/xsa/export_dir/uart/board_id/part/bootgen`，可选`embedded_sw_repo`。uart来自实际BSP/profile，不能照抄旧UART1。BOM兼容脚本仅创建库副本，不修改安装。软件wrapper参数为`-Config/-Vitis/-LogDir/-Script`，完整命令及A14证据见[工具核查](benchmarks/bkb220-toolchain-audit.md)。

新板资料确认后才运行以下模板；尖括号都是待填值，不能照字面执行：

```bash
VIVADO_ROOT=/tools/Xilinx/Vivado/2022.2 bash tools/run_vivado_build.sh board=bkb220 part_name=<实物确认part> clk_mhz=100 stage1_p_ways=16 stage1_pipe_tree=1 build_dir=<独立目录> export_dir=<独立制品目录> report_dir=<独立报告目录>
bash tools/run_g3.sh --artifact-dir <完整制品目录> --xsdb D:/xilinx/2026.1/Vitis/bin/xsdb.bat --device xc7z020 --uart-port <实际PS串口> --ip <实际板IP> --limit 2048 --read-bps 150 --score-min 67
bash tools/run_g3.sh --artifact-dir <完整制品目录> --xsdb D:/xilinx/2026.1/Vitis/bin/xsdb.bat --device xc7z020 --uart-port <实际PS串口> --ip <实际板IP> --full --runs 3 --result-timeout 1800
python3 tools/board/g3_performance_matrix.py --artifact-dir <已加载完整制品目录> --out-dir <新矩阵目录> --limits 128,512,2048,8192,32768,full --repeat 3 --ip <实际板IP>
```

构建模板按用户要求使用WSL2022.2主线，Windows2026.1 XSDB下载；先验证真实Vitis2022.2能力并完善同XSA软件打包，最后按F9独立验证26开发。每次记录实际硬软/下载工具版本组合，不能把模板当作已验证的新板结果。矩阵需先加载相应P4/P16包；UART周期采集复用唯一追加日志，Stage1未测周期和功耗保持null，不能墙钟×时钟代替硬件计数。

旧stress_test_suite.py/switch_export.sh已成对原样归档至docs/archive/tools/2026/retired-20261011，不再作为现用入口。新板长稳以run_g3.sh --artifact-dir完整包、显式XSDB/device/实际PS串口和现用guard/recovery/netfault探针编排，保存逐轮证据，以实际墙钟时长验收2h/8h；禁止自动切SE250或覆盖旧export。ARM基准固定旧BSP/XSA/GCC/XSDB并rst -system，必须适配后再用。多payload/run_demo主要是TCP任务，不下载或复位；run_robustness_scan的board_equivalent为软件模拟。不能将名称当作板测证据。

## 6. 提交、推送、工作区整理与完成定义

每个可验证里程碑由main统一交付：停写确认→核对所有diff/索引/未跟踪文件→备份精确任务路径及SHA→必要时手动限定路径stash并保存OID→pull --rebase（禁止autostash）→恢复并验证SHA/模式→精确add与带路径commit→立即push origin main→require-synced=0/0。若实际失败，保存状态并报告，不force push、不reset/clean掩盖。

提交说明写清问题、变化、测试及未测边界；准备提交不能称为新板迁移完成。大EDA生成目录不提交；可复现源码/入口、参数、fixture/source manifest、必要小证据、结果摘要必须交付。每次迭代更新03/05/07/09和相关benchmark，避免文档互相矛盾。

本轮工具退役及启动器修正见[2026-10-11整理记录](reference/tool-cleanup-2026-10-11.md)，历史工作区整理按[整理记录](reference/workspace-cleanup-2026-10-10.md)：原位保留历史生成物与证据，仅用精确.gitignore规则防止误提交；没有删除数据/旧制品、没有释放其磁盘空间。最终Git status应无源码改动或未知未跟踪文件。ignored不等于已备份到GitHub，目录归档与hash清单仍须保留。未来确需释放空间按本文件清理条款先保留日志/manifest和用户认可的范围，不盲删生成目录，不移动活证据导致路径断裂。

收工前确认没有本任务仍运行的EDA/下载/串口进程；只关闭本任务明确持有的资源，其他用户进程不动。恢复点stash在确认新提交与远端同步后按OID核对是否仍需保留，不能批量drop他人stash。用agent_view.sh对已结束角色done；真实外部阻塞写block或交接，不挂“正在测试”假状态。

可宣布“迁移完成”的最小条件：确认过的新板配置、P4新板基线、P16合法100MHz完整route、同XSA完整软件包、全量/连续/恢复新板G3和同板公平性能、源码制品证据可追溯。功耗/SE250/D0分发/材料未完成单独列项。当前整理交付可以完成，硬件迁移仍按上述门禁继续。

### 清理分类与不可省略的门禁

- 冷整理（文档/生成目录/非综合死源）先证明引用/用途，归档或改精确忽略，复查打包/卫生/相关回归；保存失败和活证据，不把运行证据当死源码。
- 热整理（sw/app、综合RTL、客户端生产逻辑）即使结果看起来相同，也必须重建对应整套制品→真实G3→刷新SHA/source manifest；无工具/板卡窗口只记录deprecated/待办，不假报通过或删除仍用实现。
- sw/app唯一权威，workspace同名源应一致，禁止改生成副本；黄金共享common，不能复制到各数据集。
- 工具必须登记，综合hdl不得含TB/孤儿，同名变体打包唯一且回归覆盖。零引用不是自动可删：依AGENTS退休条件，先保留Git历史与结论，确认已证伪/逐字节重复/已替代才处置。
- archive/submission历史包不删除；若将来移出项目，先明确并得到用户认可目标路径，保存SHA和指针；本次未移动。任何空间修剪先归集日志/manifest，保留窗口必须可审计，不手工盲rm。
- main在Git前冻结全部writers、核实真实进程，恢复时核对文件SHA/模式与stash OID；只终止自己核实的PID树，不清他人改动或恢复点。

### 本轮按计划执行的检查点（2026-10-10）

主Agent按用户要求使用三个低等级gpt-6-luna子Agent完成docs-audit、tools-audit、env-audit两轮短任务，分别核对文档映射/提示词、脚本副作用/打包/47主机用例、实际设备/资料/配置门禁。main复查引用与差异、直接重复只读CIM设备核查并查看测试原始日志；子Agent不做Git写入。

~~F0/F1审计与准备检查已执行：…当前只有蓝牙COM，无FTDI/JTAG、无物理网口/对应原厂preset。~~（该段为 2026-10-10 快照，设备部分已被 2026-10-12 实测取代：FT4232H JTAG + COM9/10/11 已确认，见 §2 上方。）资料搜索仅指定目录一层关键词及仓库文件名，不构成全磁盘不存在资料的证明。

**2026-10-12 回填**：F2 已从「只读 dry-run」推进到「Vivado 2022.2 catalog 逐属性验证 + 来源表」；F3 已在真板执行并大部分通过（DDR 读写、PS UART 归属），仅 ENET0/PHY 未通过。F4～F8 真板依赖**仍未关闭**，前置是 ENET0/PHY。

后续资料/连接到位且必要MCP核查通过后，由main经 codex-luna MCP 固定 gpt-6-luna/max 按角色提示词派发board-migrate/rtl-16way/verify-system；当前审计助手已停写。索引、静态盘点和短检查可优先派发；生产RTL、时序、PS7及真板结论必须main审查，不仅依据子Agent的摘要。

## 7. 按比赛评分表重排的后续计划（2026-10-12 用户指示；**本节覆盖前文所有"后续顺序"**）

参赛：2026 全国大学生嵌入式芯片与系统设计竞赛 · FPGA 创新设计赛道 · AMD · 自主选题**初级组**。
**一切优先级按这张评分表排，不是按"更快"排。**

| 评分项 | 分值 | 本项目现状 | 计划里对应哪一步 |
|---|---|---|---|
| 创新性与应用价值 | **30** | DNA 信息存储读出、真实测序数据、PS/PL/PC 闭环 | P5 报告与叙述（把"创新点"提炼出来，不是堆功能） |
| 性能与资源 | 20 | 新板同板六档矩阵**已完成**：矩阵测量 P16 全量中位 **8.9486s vs P4 26.5393s（2.97×）**，每条记录成本 **0.2519→0.0814 ms（3.10×）**，固定开销 0.4529→0.4182s 基本不变。该值是矩阵时段的测量；上传转正记录中的最新同小时参考 `t_result` 为 **9.33 s**。 | 正式矩阵口径见 `docs/benchmarks/bkb220-p4-p16-performance-matrix.md`；当前处理段 PL 约占 87.8%。Stage1 K2 已有 OOC 与整机 route 证据，相关后续工作仍在进行。P16 仍慢于 16 线程 CPU |
| 功能正确性 | 20 | P4/P16 route、G3、全量/连续恢复、故障探针、六档矩阵及 v2 42 例判定对照已有记录 | 新载荷四级逐级取证、v2 `score_min=67` 板测、冷启动和 UART 反向仍待完成 |
| **大模型协作与技能包** | **15** | 本项目**全程由多 Agent（codex-luna/gpt-6-luna）协作完成**；`docs/submission/skill/` 已有 8 个技能包；`docs/agent-prompts/` 与 `logs/agents/*/prompt.txt` 有真实提示词 | **P2-B 补齐「LLM 交互记录 + skill 包」**——这 15 分目前没被当回事 |
| 文档与可复现 | 15 | 证据台账、复现命令、判据边界极强 | P5；补"工具版本说明"一节 |

**硬要求与合规缺口（必须逐项关闭）**：

| 硬要求 | 现状 | 缺口 |
|---|---|---|
| **Vivado 2026.1 或 2025.2**（其他版本须说明并保证可复现） | 主线用 **2022.2** | 两条路：① P6 用 26 重建（用户已排到最后）；② 若 26 不成，**必须在报告里给出「版本说明 + 可复现保证」**。**这条是合规项，不能只写"未做"** |
| 提交 **LLM 交互记录**（提示词/回答/自我纠错轨迹） | `docs/submission/ai-collaboration/` 已有提示词、回答和自我纠错记录 | 按提交材料复核覆盖范围与来源，不再列为未整理 |
| `skill/README.md` 技能包 | **已有 8 个** | 已有新板/16 路相关内容；交付前核对入口说明与当前证据一致 |
| 文件/目录名纯英文小写 | **提交面已下沉**（2026-10-13）：`docs/submission/**` 与 `docs/agent-prompts/**` 的 12 个文件全部改为小写（11 个 `readme.md` + 1 个 `audit.md`），全仓 0 断链、卫生门禁 PASS。**故意没动**的两类：① `docs/archive/**` 与旧制品——它们有**按路径记录的 SHA 清单**，重命名即破坏保护条款；② `AGENTS.md`/`CLAUDE.md`/`LICENSE`——前两个是 agent 工具的**约定文件名**，改名会让项目指令不再被加载，`LICENSE` 是 GitHub 识别惯例。用户提供的中文名原始资料（如 `docs/board/bkb220/bkb220-product-manual-v1.1.pdf`）保留原名 | 打包提交时按小写重排提交物；报告里说明保留原名的理由 |
| 开源 + MIT/Apache | 根目录已有 MIT `LICENSE`，明确第三方素材适用范围 | GitHub public 状态仍按提交要求单独核对 |
| 板上实测 | ✅ P4/P16 均有新板实测 | 保留 8 个 challenge 例失败、`score_min=67` 未板测及其他未完成边界 |
| 决赛一页英文海报 | 未做 | P6 之后 |
| 初级组推荐 PYNQ；通用 PYNQ Skill 单独加分 | 本项目是裸机，非 PYNQ | **记为机会项**：不改变主线，但可评估是否另附一个 PYNQ 视角的技能包/说明 |

### 重排后的阶段

- **P1 本轮收口（22 主线内）**：B2 三项故障探针、C1 六档矩阵、P4/P16 v2 42 例对照、2 h 长稳均已完成。剩余为 8 h 长稳、v2 `score_min=67` 板测、新载荷四级黄金向量及明确列出的其他终态门禁。
  - **C2 已有首测及后续结果**（[来源表 §16–§18](board/bkb220/migration-source-table.md)）：v1 八套 8/8 恢复；v2 的 42 例 P4/P16 板端与软件验证器 **42/42 判定一致**，其中 challenge 13 通过、8 失败，失败模式为 LDPC 不收敛。v2 `score_min=67` 尚未板测；新载荷四级黄金向量尚未生成。
- **P2 合规与得分缺口（便宜且分值高，先做）**：
  - **A. LICENSE + 开源状态**（几乎零成本）
  - **B. LLM 交互记录 + skill 包补齐**（15 分；素材已在手）
  - **C. 工具版本说明 + 可复现保证**（文档 15 分 + Vivado 合规）
  - **D. 文件名合规自查**
- **P3 全面优化（时间消耗 + 性能）**：旧 P7 测量曾观察到非 Stage1 时间主要在 PS 等待与 cache 维护；这不是当前处理段的瓶颈结论。当前上传转正包为 `TCP_WND=32768` + 默认 `PIPE_IDLE_FETCH_N=16`，上传实测 0.40 s；处理段预算中 PL 约占 87.8%，优化关注点转向 PL。Stage1 K2 已有 OOC 与整机 route 证据，后续工作仍在进行；K4 OOC 探针已过，但整机 route/板测未完成，不能写成 Stage1 优化整体完成。**注意性价比**：性能与资源只占 20 分，优化要挑"改动小、可复现、证据强"的；任何 PS 固件改动都另存新制品包，不覆盖已冻结包。
- **P4 冻结 22 主线**：优化完成即停止修改。
- **P5 写报告**：不早于 P4；含创新点叙述、性能口径、LLM 协作记录、技能包索引、复现命令、限制与未测项。**单列项（功耗/SE250/D0 分发）如实列"未完成"，不用准备成果顶替。**
- **P6 最后切 26 开发**：Windows 2026.1 完整硬件与软件开发复核（原 F9）；并据此满足"Vivado 2026.1"硬要求。
- **P7 交付收尾**：冻结 writer、按路径提交推送、同步文档与 Windows 镜像、各 agent 看板 `done`；决赛海报。

### 单列项中"有价值"的如何编入

| 单列项 | 处置 |
|---|---|
| **功耗/能效** | **仍缺仪器，本轮不编入**。P5 如实列未测。若用户能提供功率计，则作为 P2 尾巴插入（对"性能与资源"20 分有正向） |
| **SE250** | 仍属另 profile、另几何，**不编入本轮**。但 P5 的报告里可作为"可扩展性"论据（说明几何参数化的完整性）——**不得声称 SE250 已通过** |
| **QSPI/SD 冷启动** | **有价值**（对"功能正确性"20 分与"应用价值"30 分都有正向：真正的产品要能脱机启动）。当前 BOOT.bin 已生成，缺的是**实际冷启动验证**（需 SD 卡/QSPI 写入，且**不覆盖出厂镜像**）。**2026-10-16 用户调整排期：往后推，紧挨在「功耗」之前**——两者都要动用户资源（切启动模式 / 上仪器），挨着做省一轮来回；先做 v2 `score_min=67` 与新载荷四级取证 |
| **UART 反方向（PC→PS）** | **编入 P2**（便宜：一次串口发送测试）。交互式使用需要它 |
| **DDR 板级延迟与 DQS-to-CLK** | 编入 P3（与时间优化同批，因为它直接影响 DDR 时序裕量） |
| **工业级器件精确料号** | 编入 P2（查手册/实物顶标即可，成本低，对"文档与可复现"有正向） |
| **P14 OOC / 模块 3.27× / A14 探针等** | **永久单列**：它们不能替代验收，只在报告里作为"过程证据"引用，且必须注明边界 |

### 2026-10-13 P3 第一次实验：节流方向**已被实测证伪**，靶子改到 RX BD 环

按上面的 H1/H2 预登记判据做了 A/B。三个包都由 `tools/build_sw_variant.sh` 派生（bit/XSA/FSBL 与参考包逐字节相同，只有应用 ELF 与 BOOT.bin 不同），
`run_g3.sh --strict-artifacts` 全部放行，六档 ×3 在同一台板、同一天、同一输入背靠背测：

| 变体 | 截距 | **斜率** | R² | 全量判据 |
| --- | ---: | ---: | ---: | --- |
| 休眠 200 µs（参考包） | 0.4343 s | **0.079086 ms/记录** | 0.999844 | PASS |
| 休眠 50 µs | 0.4394 s | **0.078348 ms/记录** | 0.999995 | PASS |
| 休眠 0 µs | 0.4314 s | **0.079057 ms/记录** | 0.999740 | PASS |

**结论：H1 否，H2 立。** 三条斜率在噪声内相同（差异 <1%），**去掉 200 µs 节流端到端一点没快**。
分解说明了时间去了哪：休眠 0 时回调从 42,648 涨到 **5,160,359** 次，`[in-state]` 从 686 ms 涨到 6881 ms，
其中 **`TX_STREAM` 573 万次命中、5892 ms**——而源码注释写明该状态是「按 RX BD 环的剩余容量分批投递」。
**真正的限制是 RX BD 环的回收/补充速率**，睡眠只是把这段等待记在 `[waiting]` 还是 `[in-state]` 的区别。

这条与 2026-09-10 那次 `RX submitted=640 > ring free=512` 导致 Stage1 停顿约 30 s 是**同一机制**；
也与 2026-09-22 旧板 `p13b-no-throttle` 只拿到 25.60 vs 26.52 s（约 3.5%）相互印证。
**不要再考虑删那行节流**；`sw/app/main.c` 里的 200 µs 与「必须让出」注释都是对的。

### P3 的目标改为可量化的「打过 CPU」

公平 CPU 基线（[ARM 基线](benchmarks/measured_arm_baseline.md) §4，i5-13500H 历史实测，SE150 全量 103,616 记录）：

| 实现 | 全量耗时 | 相对 P16 |
| --- | ---: | ---: |
| i5-13500H 单核 C | 37.9 s | P16 快 **4.24×** |
| **i5-13500H 16 线程 C** | **3.70 s** | 对照值 |
| BKB220 P16（矩阵时段测量） | 8.9486 s | 该时段数值比值约 2.42× |
| BKB220 P16（最新同小时参考 `t_result`） | 9.33 s | 该时段数值比值约 2.52× |

8.9486 s 是矩阵时段测量，不作为当前值。最新同小时参考 `t_result` 为 9.33 s；与 CPU 历史基准 3.70 s 作数值对照时仍慢约 2.52×，但两者测量口径不同，不能把该比值写成严格公平加速比。
按 `TX_STREAM` 那 5892 ms 的量级，**这一目标在机制上是有希望的**——但必须先量清楚 RX BD 环到底被什么卡住
（环容量 / 每 BD 的 cache 操作 / lwIP 收包路径 / 客户端上传节奏），**先量后改**。

注意这条对照对**本项目不利**地偏向对方：CPU 数字只计比对，PL 数字是**端到端**（含 DMA/Voter/固定开销）。
所以一旦打平，实际是赢了。

### P3 的历史分解：**该矩阵样本的推导中，PL 占处理段约 87.8%**

用 P4/P16 两档斜率与 Stage1 模块周期比 3.272× 联立解出「每条记录的 PL 分量」与「PS 分量」：

| | 全量 | PL（Stage1 数据通路） | PS 侧 |
| --- | ---: | ---: | ---: |
| P4 | 26.55 s | 25.43 s（95.8%） | 1.12 s（4.2%） |
| **P16（旧矩阵采样）** | **8.86 s** | **7.77 s（87.8%）** | **1.08 s（12.2%）** |

上述 8.86 s / 7.77 s / 1.08 s 是旧矩阵采样基础上的模型分解，不是最新同小时绝对值或独立直接计时；最新同小时参考 `t_result` 为 9.33 s。按该分解比例，当前处理段仍约 87.8% 属 PL；此限定不改变表中原始推导数字。

- 解出 **PS 侧每条仅 0.0064 ms**（P16 的 8%）；其余全部随 `P_WAYS` 缩放，属 PL。
- 按该历史样本和当时的 3.40 s 目标：P16 需再快 **2.63×**。**把 PS 侧全部清零也只能到 7.77 s**；这是该模型的推导，不是最新绝对时间。
- 该样本说明当时的处理段主要由 PL 周期决定；后续优化应以当前测量和探针结果为准。

**RTL 核实结果（2026-10-13，只读分析）——我先前那条推论的单位是错的，已作废：**

- 一个「位置块」= 16 个候选起点 × **同时 64 条记录**（BATCH），整块 **176 拍**：
  `S_LAUNCH 1 + S_PREFILL 18 + S_RUN 150 + S_UPD1 5 + S_UPD2 1 + S_NEXT 1`。
- 每记录块数：`STRIDE=807` → 每区 808 个起点 → 51 块/区 × 50 区 = **2550 块/记录**。
- 摊销后 `2550 × 176 ÷ 64 = **7012 拍/记录**`——**与实测 7500 拍/记录吻合**（差 6.5%，属装载/发射开销）。
- 所以不存在「2.97 周期/位置步」这个量；真实是 **≈2.75 周期/记录·块**，且 `S_RUN` 热循环**没有气泡**——
  **瓶颈不是浪费，而是每拍只推进 1 个碱基索引**（`READ_BPS=150` → 一条读段要 150 拍）。

**三条路的历史估算对比**（旧矩阵分解中 PL 为 7.77 s；目标 3.40 s 时需 PL 快 3.35×。7.77 s 是旧模型绝对值，不是当前值）：

| 路线 | 搜索加速 | 全量估算 | 代价与边界 |
| --- | ---: | ---: | --- |
| 多碱基并行（4 碱基/拍） | ≈2.94× | **3.72–4.30 s** | 新增 4 路读/比较/累加与 BRAM 银行；粗估 +6k~12k LUT（余量仅 19,213 LUT）、时序风险高。**单靠它到不了 3.40 s** |
| 增 P_WAYS | P32 1.79× / P64 3.05× | P32 5.42–5.81 s / P64 3.62–4.22 s | **P32/P64 外推 LUT 58.7k / 108k，均超 XC7Z020 的 53.2k**——不是候选 |
| 缩小每记录位置数 | 需 3.35–4.8× | 理想 ≈3.40 s | 资源代价最低，但**改变搜索含义**，须先明确"哪些起点可以省略、是否仍要求原契约下的全局最优" |

**下一步方向**：早期估算提出把「4 碱基并行」与「块级重叠（下一块的 `S_PREFILL`/选优排空与当前 `S_RUN` 重叠）」结合；这些收益仍是估算。K=1/2/4 OOC 探针和 K=2 整机 route 已有通过证据，K=4 整机 route、板测及正式功能回归仍待完成。后续按当前阶段卡推进并使用独立变体和预登记判据，不把旧估算写成测量结果。

**⚠️ 不要重复的归档负结果**（[08](08-performance-and-strategy.md) §21、旧交接 status）：
TX_STREAM 压缩**已尝试四次并放弃**，结论是「真正约束是**硬件处理每帧的墙钟时间**，原设计是**时间节拍器**而非容量节流器」；
即便把 DMA/poll/回传全消掉，旧板 4096 记录档也只快 1.11×。本次的 PL/PS 分解与那条结论**方向一致**，
因此该历史记录只说明当时的观察；当前处理段需按最新测量和 Stage1 探针结果定位，不能将“PS 在等 PL”扩展为所有阶段的瓶颈结论。

### 2026-10-13 傍晚 P3 第一项完成：上传段实验与正式转正，并给出 C 组的实施判据

**A 组（上位机/协议）已落地一项，见 [上传段 benchmark](benchmarks/bkb220-p16-speed-a-upload.md)：**

- 无睡眠派生实验包测得读段上传 **4.27 → 0.19 s**；正式转正包默认 `PIPE_IDLE_FETCH_N=16`，同小时读段上传 **4.27 → 0.40 s**。整轮实验包测量为 **14.25 → 10.18 s（−28.6%）**。两种包的实测都保留，0.19 s 不作为当前正式值。
- 根因不是「逐批 ACK 停等」（已实测否掉），而是 **`NO_SYS=1` 下一次 `xemacif_input()` 只取一个以太帧**
  × **空闲主循环 `usleep(1000)`**；`TCP_WND=2048` 是第二重限制。
- 派生实验包改法：`PIPE_IDLE_SLEEP_US=0` 与 `TCP_WND=32768`；正式配置已转正为 `TCP_WND=32768`、默认 `PIPE_IDLE_FETCH_N=16`。
- 上传与处理重叠的收益上限按正式包 **0.40 s** 计；是否实施按收益与改动代价评估，不沿用 0.19 s 作为当前值。
- **底稿 §5 第 2 项「上传吞吐」据此关闭**（已完成）。
- **第 3 项「LDPC 与下一轮重叠」仍开放**：0.653 s，占新口径整轮 6.4%。属调度改动，需改 `tools/run_g3.sh`
  的逐轮循环（把 `ldpc_decode.py` 放后台、与下一轮 `first.py` 并行，循环尾 join）。
  **注意它动的是验收脚本本身**，改动后必须重跑 ≥3 轮全量判据自证没改坏。**本轮未做。**

**C 组（PL）设计记录；后续探针与 route 状态已推进：**

- 设计阶段基线：`srpe_batch_pway.v` 的 `S_RUN` 每拍只推进**一个**碱基索引，并行比较 16 起点 × 64 记录 = 1024 个匹配位；
  `score` 是寄存器数组；Stage1 OOC 基线 26,867 LUT / 8 RAMB36。
- K=2：`S_RUN` 150→75 拍，每块 176→101 拍；整机外推 36k～40k LUT。
  ⚠️ **2026-10-15 分母更正**：`176/101/64` 都是**块内 FSM 状态驻留口径**；板端硬件计数器实测
  归一化后每块实际成本是 **116.82 拍**（差额来自不按块计的 `S_LOAD_R` 与 `S_EMIT*`）。
  本组所有"每块拍数"折算成"占 Stage1 时间百分比 / 秒数"的地方，分母都要重算——
  见 [`stage1-block-overhead-plan.md`](benchmarks/stage1-block-overhead-plan.md) 的"分母更正"一节。
- **K=4**：`S_RUN` 150→38 拍，每块 176→**64** 拍；整机外推 **40k～48k LUT**（上限 53,200，**高端只剩约 5.2k 余量**），
  BRAM 需奇偶 bank 拆读段 + 4 bank 读水印；**全量估算 ≈ 3.91 s**（再与 7 拍选优排空重叠 ≈ **3.60 s**，目标 3.70 s）。
- **后续验证进度**：K=1/2/4 OOC 探针已通过；K=2 整机 route 已通过（35,285 LUT、WNS +0.978 ns、失败端点 0）。原 P16 基线 WNS +0.617 ns、布线占比 84.5% 是此前设计门槛观察；K=4 整机 route、板测和正式功能回归仍未完成。
- **探针复核入口**：结果和源集见 `docs/benchmarks/stage1-multibase-ooc-probe.md`。已通过的 OOC 不需为重复而重跑；若后续改动影响该变体，则按 `docs/submission/skill/fpga-timing-probe/ooc_probe.tcl` 的约束重新验证。`SYNTH_IMPL=1` 才执行 route，综合-only 的 WNS 不作收敛判据。
- **能变红的判据**：OOC —— WNS/WHS ≥ 0、失败端点 0、Stage1 LUT ≤ 40,000、K=4 RAMB36 ≤ 12；
  整机 —— 完整 route、LUT ≤ 48,000、DRC 0 errors；上板 —— 全量 103,616 条 ≥3 轮
  SHA 逐位 `fcd0cf90…b1f2c3`，且端到端低于 **3.70 s**。
- **当前剩余**：已完成的 OOC/K2 route 不代表 Stage1 优化整体完成；K4 整机 route、板测与正式功能回归仍待验证。结构性 RTL 改动（参数化、接顶层/`component.xml`/`PACKAGED_VARIANTS.txt`、整机 route、全量回归）必须逐层验收；**改了不验的 RTL 不进主线**。
