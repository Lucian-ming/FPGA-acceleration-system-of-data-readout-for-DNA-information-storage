> 脱敏副本，原件 `20261013T123933Z-10429d714c/{prompt.txt,answer.md}`。本机绝对路径、邮箱、凭据形模式及非白名单私网 IP 已替换；除脱敏与换行规范化外保留原文。

## 1. 必须改

1. [README.md](<仓库根目录>/README.md) →「当前状态」及「完整同XSA软件包仍待迁移阶段重建验证」：仍写 `ready=0`、没有新板 bit/XSA、整机时序和 G3。与 [P4/P16 构建记录](<仓库根目录>/docs/benchmarks/bkb220-p4-p16-100mhz-build.md)、[故障探针](<仓库根目录>/docs/benchmarks/bkb220-p16-fault-probes.md)、[性能矩阵](<仓库根目录>/docs/benchmarks/bkb220-p4-p16-performance-matrix.md) 及 [上传提速转正记录](<仓库根目录>/docs/benchmarks/bkb220-p16-upload-promotion.md) 不符。建议更新为 `ready=1`、P4/P16 route 与板测已完成，并列出真实剩余项：8h 长稳、v2 的 `score_min=67`、新载荷四级取证、冷启动、UART 反向、功耗和 F9。注明完整 P16 包已构建并 G3 PASS；若自动化构建流程仍未闭环，另行限定。

2. [AGENTS.md](<仓库根目录>/AGENTS.md) →「事实边界」：“BKB220 未验证前 ready=0”；“公平基准和 Stage1 展开仍是下一阶段”。`ready=0` 已由当前配置与板测状态取代；P4/P16 六档矩阵和 CPU 对照已有结果，Stage1 K2 工作也已进入进行中阶段。建议改为当前判据和进度，并保留“P16 仍慢于 16 线程 CPU”的边界；不要把 Stage1 试验写成已完成。

3. [docs/03-status.md](<仓库根目录>/docs/03-status.md)：
   - 「当前目标」仍称新板没有完整配置、bit/XSA、整机时序或真板 G3；「F3 实板结果摘要」仍称缺整机 route 与 G3。现有构建、G3 和 P16 矩阵记录已分别关闭这些项。建议重写当前状态，并用实际剩余项说明为何尚未宣布迁移完成。
   - §1a 的串口事实表说“哪个是 PS UART 仍未确定”，与 §1b 确认 UART0/MIO14-15、FT4232H C 通道、COM10/`ttyUSB2` 冲突。建议修正表格。
   - §1e「明天待办」仍列 B2、C1、C2 未完成；后面的白天进度已标记探针和矩阵完成，且 C2 有 42 例结果。傍晚追加还把 `PIPE_IDLE_SLEEP_US=0`、上传 0.19 s 写成当前改法。建议将旧待办明确标成历史快照，并把当前上传配置改为默认 `PIPE_IDLE_FETCH_N=16`、实测 0.40 s；同时保留 v2 的 67 阈值尚未板测等剩余边界。

4. [docs/04-interfaces.md](<仓库根目录>/docs/04-interfaces.md) → §3.1“AXIS 时序与 BRAM 实际写入仍待顶层仿真或上板确认”、§5“整链端到端仍待上板”：BKB220 G3 已在板上完成端到端判据，水印路径也已参与实际任务。建议写明真板功能链路已通过；若仍缺逐拍 AXIS 波形或单独 BRAM 写入判据，应具体限定未覆盖的信号级细节。

5. [docs/05-implementation-plan.md](<仓库根目录>/docs/05-implementation-plan.md)：
   - §2「当前基线与尚未完成」和 §3 的 F2～F8 进度仍把新板 route、同 XSA 包、板测和矩阵列为下一步。现有 benchmark 已覆盖 P4/P16 route、G3、B2、C1、C2 和 2h 长稳。建议把这些移入“已完成”，当前状态仅列剩余门禁。
   - §7 把 P16 的 8.9486 s 写成“今日实测”并按此计算当前 CPU 差距；矩阵文件已说明该值是一次矩阵测量，最新同小时参考 `t_result` 为 9.33 s。上传段和“下一步”仍写 0.19 s、`PIPE_IDLE_SLEEP_US=0`、尚待转正。建议明确区分矩阵历史中位数与最新同小时值，并更新为已转正配置 0.40 s；保留 0.19 s 为实验变体记录。

6. [docs/07-board-build-and-acceptance.md](<仓库根目录>/docs/07-board-build-and-acceptance.md) → 开头、§1、§2、§4、§5：“新板验收仍待资料及连接”“ready=0”“P16 未上板”“PS UART 仍未定”等均已过时；§3 又称完整软件包待重建。另 §1 连接行写“触板只允许走 WSL”，与本文件 §3a 及用户指定的 Windows 2026.1 烧录路径冲突。建议更新现状表：profile 已 `ready=1`，P4/P16 已 route 和上板，Windows 2026.1 可烧录 22 产物；未完成项按当前证据逐项列明。

7. [docs/08-performance-and-strategy.md](<仓库根目录>/docs/08-performance-and-strategy.md) → 开头“六档矩阵与长稳都做过”：矩阵已完成，长稳目前完成的是 **2h**，**8h 未做**。建议改成“六档矩阵完成、2h 长稳完成，8h 尚待执行”，避免“长稳完成”扩大边界。

8. [docs/09-evidence-ledger.md](<仓库根目录>/docs/09-evidence-ledger.md)：
   - §3 P8/P8a/P8b 将 0.19 s 和整轮 10.18 s 当作上传提速的正式当前结果。它们来自 `PIPE_IDLE_SLEEP_US=0` 的派生实验包；正式转正包是 `PIPE_IDLE_FETCH_N=16`，上传 **0.40 s**，整轮约 **10.4 s**。建议保留旧测量并标为实验包结果，补入正式包结果。
   - §8 的 C2 行仍称 P16 未跑同一套数据；紧随其后的条目记录了 P16 与 P4、软件三方 42/42 一致。B2 行称 2h/8h 长稳均未做，下一行却记录 2h 完成。建议同步这些边界：P16 42 例已测、2h 已完成、8h 未完成。
   - §8 P3 账以 8.86 s / PL 7.77 s / PS 1.08 s 作为当前 P16 绝对值。该分解对应旧矩阵采样；最新同小时 `t_result` 为 9.33 s，处理段 PL 约 87.8%、PS 约 12.2%。建议标明旧分解的测量口径和时间，并补充最新值。

9. [docs/board/bkb220/migration-source-table.md](<仓库根目录>/docs/board/bkb220/migration-source-table.md)：
   - 开头仍称草案、`ready=0`，与 §9.3 的 `ready=1` 及当前已构建、上板结果矛盾。建议更新开头摘要；§1–§8 的旧阶段资料可保留为历史记录。
   - §14.1 将 P4 与旧板同路数结果相近概括为“瓶颈在 PS”。这不能代表当前 P16 处理段；最新拆分显示 PL 约占 87.8%。建议限定为当时的 P4 比较观察，不作为当前系统瓶颈结论。
   - §17.4、§18.4 仍称 P16 未测该数据集，§18.4 还称长稳/soak 未做；§18.5 与 2h benchmark 已分别关闭 P16 同集测试和 2h 档。建议统一为 P16 42 例已完成、2h 完成、8h 未完成，并保留 v2 `score_min=67` 未测的限定。

10. [docs/benchmarks/bkb220-p16-time-budget.md](<仓库根目录>/docs/benchmarks/bkb220-p16-time-budget.md) → §2、§3、§5、§8：3.916 s/29.5%、8.682 s、PL 7.77 s 和“上传 0.19 s 已完成”混在时间预算与交接建议中，容易被读成当前值；§8 还把上传优化列为下一步。建议把 3.916/8.682/0.19 明确标成各自旧包或旧时段的实测，补入当前正式包 0.40 s、同小时 `t_result` 9.33 s、整轮约 10.4 s，并从当前待办中移除已完成的上传优化。

11. [docs/benchmarks/bkb220-p16-speed-a-upload.md](<仓库根目录>/docs/benchmarks/bkb220-p16-speed-a-upload.md) → §3.3、§4、§6、§7.2：文中多处把 0.19/0.27 s 写成当前上传上限或零拷贝优化收益，并提供 `PIPE_IDLE_SLEEP_US=0` 派生包命令。数字作为实验有效，但需标清它们是无睡眠实验包结果，当前转正包为 0.40 s、默认 `PIPE_IDLE_FETCH_N=16`；不要把复现实验命令当当前推荐配置。

12. [docs/benchmarks/bkb220-p16-upload-promotion.md](<仓库根目录>/docs/benchmarks/bkb220-p16-upload-promotion.md) → 开头“G3 没有运行到 XSDB/下载阶段”“没有本轮上传耗时”：后续“补记”已记录主会话 G3 PASS、SHA 正确、上传 0.40 s。建议将开头结论改成最终结论，把沙箱前置失败保留为过程记录。文中泛化和长稳未在**这个精确转正包**上重跑的边界仍应保留。

13. [docs/benchmarks/bkb220-p16-fault-probes.md](<仓库根目录>/docs/benchmarks/bkb220-p16-fault-probes.md) → §5“长稳（2 h / 8 h）仍未做”：同包的 [2h 长稳记录](<仓库根目录>/docs/benchmarks/bkb220-p16-soak-2h.md) 已证明 2.003h、274 轮 PASS。建议改成“2h 已完成，8h 未完成”。

14. [docs/benchmarks/bkb220-p4-p16-performance-matrix.md](<仓库根目录>/docs/benchmarks/bkb220-p4-p16-performance-matrix.md) → §3.2、§6：“整机瓶颈在 PS 侧、不在 PL”。矩阵本身给出 P4/P16 加速斜率，但后续精细预算显示处理段 PL 占 87.8%、PS 可归因工作约 2.1%。建议保留矩阵数值和其内部对比，改正这两处当前瓶颈归因，并引用时间预算的处理段边界。

15. [docs/reference/speed-handoff-2026-10-13.md](<仓库根目录>/docs/reference/speed-handoff-2026-10-13.md) → 顶部勘误之后的 §1、§2、§4、§7–§8：勘误已说明转正包为 0.40 s、默认 `PIPE_IDLE_FETCH_N=16`，但正文仍称 0.19 s 配置是“推荐配置”，仍建议“把推荐配置转正”，并把 K2/K4、上传实验等旧结论写成当前待办。建议把这些小节对齐顶部勘误；旧 0.19 s 保留为实验值。

16. [tools/README.md](<仓库根目录><本机路径>) → 末尾 Vitis 2022.2 构建说明：“完整 FSBL/BOOT/readback/manifest 须另补齐并实测”。转正记录展示了完整 P16 包和 G3 PASS。建议改为区分“已验证的完整包”和“可重复自动化路径仍需完善”，不要再写成尚未生成或验证包。

17. `docs/agent-prompts/` 中仍有过时的启动状态：
   - [main.md](<仓库根目录>/docs/agent-prompts/main.md) → 开头及「现场与授权」仍以板卡未到货、`ready=0`、没有 FTDI/JTAG 为背景，后文要求从 P4/P16 构建和板测开始。
   - [board-migrate.md](<仓库根目录>/docs/agent-prompts/board-migrate.md) → “`ready=0` 直至可靠资料确认”、新板 P4/P16 包待构建。
   - [verify-system.md](<仓库根目录>/docs/agent-prompts/verify-system.md) → 明写 `ready=0`、无 route/G3，并把矩阵、故障探针和泛化流程列为待执行。
   - [rtl-16way.md](<仓库根目录>/docs/agent-prompts/rtl-16way.md) → 仍要求等待 profile/P4 基线后再分析 P16 route，且不应声称新板 route/板测通过。
   
   以上均被新板构建、G3 和后续 benchmark 取代。建议重写为当前阶段卡提示，列明已完成项目与剩余依赖；这不涉及把当前 K2 实验分支当作发布结论。
   
18. [docs/agent-prompts/speed.md](<仓库根目录>/docs/agent-prompts/speed.md) → §2–§4 与接手约束：仍以 3.916 s/29.5%、8.682 s、8.9486 s 为当前基线，仍要求 `PIPE_RUN_SLEEP_US=0` 测量，并将上传停等、上传重叠列为待优化方向。实验结果可留，但建议将当前正式配置和已证伪方向换成 0.40 s、9.33 s、`PIPE_IDLE_FETCH_N=16`，并把 8h 作为未完成长稳项。

19. [docs/agent-prompts/readme.md](<仓库根目录>/docs/agent-prompts/readme.md) →“已补齐的 Vitis22 及待完整重建验证的软件链”：与已有 P16 完整包、G3 实测不符。建议说明已有包已验、自动化链路若仍有缺口则单独表述。

20. [docs/submission/skill/audit.md](<仓库根目录>/docs/submission/skill/audit.md) →“六档矩阵仍待完成”“P16 故障探针尚未闭环”及命名缺口清单：矩阵、B2 探针已完成；文件命名状态也已在 03/05 记为完成。建议加审计后记，更新矩阵、探针、泛化、2h/8h 和命名状态；保留 8h、功耗等真正未完成项。

21. [docs/submission/skill/claims-ledger/readme.md](<仓库根目录>/docs/submission/skill/claims-ledger/readme.md) →“不能说：正式性能矩阵、P16 故障恢复、泛化、长稳尚未完成”：矩阵和故障探针已完成；P4/P16 对 v2 42 例的三方比较也已完成，2h 长稳完成。建议改成准确边界：8 个 challenge 例仍失败、v2 的 67 阈值未测、8h 未做。

22. [docs/submission/skill/accel-vs-cpu-baseline/readme.md](<仓库根目录>/docs/submission/skill/accel-vs-cpu-baseline/readme.md) →“当前性能矩阵仍待六档各至少 3 次”；[docs/submission/skill/bottleneck-attribution/readme.md](<仓库根目录>/docs/submission/skill/bottleneck-attribution/readme.md) →“正式性能结论仍要补齐六档矩阵”。六档矩阵已有正式报告。建议把已完成矩阵作为当前 P4/P16 比较证据，并将旧 8.61 s 单轮样本标成历史样本；同小时当前 `t_result` 参考 9.33 s。

23. [docs/submission/skill/board-stage-evidence/readme.md](<仓库根目录>/docs/submission/skill/board-stage-evidence/readme.md) →“六档矩阵、泛化、长稳或功耗尚未完成”：矩阵、P4/P16 v2 泛化对照与 2h 长稳已完成。建议改为区分已完成的范围与仍未完成的 8h、功耗及新载荷四级取证。

## 2. 待确认

- [上传提速转正记录](<仓库根目录>/docs/benchmarks/bkb220-p16-upload-promotion.md) 的“泛化与长稳未在这个转正包上重跑”是按**精确制品包**限定的；v1/v2 泛化及 2h 长稳是在之前的 P16 包上测得。建议保留这一边界，避免把 P16 配置层面的通过误写成转正包逐制品复测通过。
- 旧报告中的 0.19 s 和 8.61/8.9486 s 本身是有效历史测量；问题在于有些正文把它们写成当前值。建议只改状态标签和当前结论，不抹掉这些历史数据。

## 3. 已核对无问题的文件

- 根目录：[CLAUDE.md](<仓库根目录>/CLAUDE.md)。
- 当前架构、契约和验证计划：[docs/01-architecture.md](<仓库根目录>/docs/01-architecture.md)、[docs/02-data-contract.md](<仓库根目录>/docs/02-data-contract.md)、[docs/06-verification-plan.md](<仓库根目录>/docs/06-verification-plan.md)。
- 当前基准中范围和结果仍准确的文件：[P4/P16 100MHz 构建](<仓库根目录>/docs/benchmarks/bkb220-p4-p16-100mhz-build.md)、[2h 长稳](<仓库根目录>/docs/benchmarks/bkb220-p16-soak-2h.md)、`bkb220-host-verification.md`、`bkb220-toolchain-audit.md`、`stage1-16way-ip-integration.md`、`stage1-multibase-ooc-probe.md`，以及其余明确作为历史实验/旧配置记录的 `measured_*`、鲁棒性、CPU 对照和 Stage1 摸底报告。
- [BKB220 资料索引](<仓库根目录>/docs/board/bkb220/README.md)和校验清单 `SHA256SUMS.txt`。
- 其余 `docs/reference/` 文件均是明确日期化的阶段记录、归档说明、调研或历史清单；除上列 speed handoff 外，未发现把旧状态伪装成当前状态的确凿问题。
- `docs/submission/` 中的 `ai-collaboration/{readme,agent-usage,prompts,self-correction}.md`、技能包 `readme.md`、`board-bringup-debug`、`fpga-timing-probe`、`ip-packaging-hygiene`、`ai-agent-collaboration` 文件未发现确凿过时状态。

## 4. 范围与方法说明

- 范围按用户所列目录和文件核对；排除 `docs/archive/**`。依据 `docs/09`、最新 P16 上传/时间预算/矩阵/故障/长稳 benchmark 与 `docs/03` 交叉比对；历史测量按其明确配置与日期保留，不把历史数据本身报成错误。
- `migration-source-table.md` 较长，检查了摘要、板级事实、瓶颈归因及 §17–§18 的新增与边界段，并跨文档检索状态关键词；不是对其 1,060 行逐行复述。
- `docs/board/bkb220/` 下两份 PDF 是板卡原始资料，本次未重新提取或渲染页面；只核对资料索引、SHA 清单，以及来源表中已有的抽取/核对结论。`docs/submission/` 下 Tcl/模板文件作为脚本或模板检查，不当作当前项目状态文档。
- 只读检查了 `git status --short --branch`，当前为 `exp/stage1-k2`；该分支是用户指定的进行中实验，未将 Stage1 参数化/集成差异报告为文档不一致。未运行仿真、测试、Vivado/XSim 或板卡操作；未执行 Git 写操作，也未改任何文件。看板属于只读任务，由 main 代登记。
