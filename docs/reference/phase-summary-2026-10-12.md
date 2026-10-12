# 阶段总结（截至 2026-10-12）

> 本文是阶段性整理，供后续报告取材，不是最终报告。最终报告应等全面优化完成并停止修改后再写，顺序见[05 执行计划 §7](../05-implementation-plan.md)。本摘要以[03 当前状态 §1d](../03-status.md)、[BKB220 来源表 §9–§15](../board/bkb220/migration-source-table.md)及[P4/P16 构建记录](../benchmarks/bkb220-p4-p16-100mhz-build.md)为准；较早交接快照若与这些更新冲突，以新记录为准。

## 一句话现状

BKB220 的 F0–F5、P4 整机 G3 与 P4 板端深化 A 组已完成，P16 已完成整机重建并通过 smoke、全量三轮和连续状态复位；接下来仍需补 P16 故障探针、正式性能矩阵、泛化、长稳及比赛合规项。

## 已完成：阶段与判据

| 阶段 | 判据与结果 | 证据路径 |
|---|---|---|
| F0 接管与现场核对 | 主会话记录仓库绑定同步为 `main...origin/main = 0/0`，并核对工具链、板卡与已有状态后按现成计划接手。此处引用主会话记录，本子任务未重跑绑定门禁。 | `docs/03-status.md` §1d |
| F1 已有成果确认 | P4/P16 正式源集与 `PACKAGED_VARIANTS.txt` 一致、没有未覆盖打包文件；主会话复跑 `check_ip_packaging.sh` 与 `check_repo_hygiene.sh` 均 exit 0。 | `logs/agents/rtl-16way-20261012/audit-report.md`；`logs/agents/verify-system-20261012/implementation-report.md`；`docs/03-status.md` §1d |
| F2 新板配置 | BKB220 来源与 PS7 配置经 Vivado 2022.2 属性验证；PS_CLK、DDR 参数、UART 映射及 ENET0 配置有来源或实测支撑。 | `docs/board/bkb220/migration-source-table.md` §8、§10、§12；`hw/boards/bkb220.tcl`；`hw/build/bkb220-ps7-probe/20261012T114440Z-board-migrate-r3/` |
| F3 最小启动 | `ps7_init`/`ps7_post_config` 返回 0；DDR 测试区 1024 字写读 0 不符；PS UART0/MIO14–15 经 FT4232H 通道 C 输出正确 ASCII；MDIO 读到 RTL8211E，1000BASE-T 全双工 link up。DDR 结果只覆盖本次测试区，不代表全容量或板级时序已验证。 | `docs/board/bkb220/migration-source-table.md` §9；`logs/bringup/20261012T120117Z-bkb220-f3-v1/` |
| F4 P4 整机基线 | SE150、P4（4/0）在 `xc7z020clg400-2` 完成 100 MHz 整机 route；WNS/WHS 为正、失败端点 0、DRC 0 errors。其同源硬软包完成 G3 7/7：CAPS、4096 条板端记录、四级 DDR 取证、串口输出与最终图片判据均通过。图片 SHA-256 为 **`fcd0cf90bd680e7bbdc203e3398119504da0897acac9e2117008b4efb6b1f2c3`**。 | 构建：`hw/build/bkb220-p4-100mhz-20261012T123158Z-board-migrate-p4/`；G3 制品：`hw/build/bkb220-p4-enet0-software-20261012T140800Z-board-migrate/`；板测：`D:\bkb220_board_smoke\g3_runs\20261012T142924Z\`；汇总：来源表 §13、构建记录 |
| F5 P16 整机候选 | SE150、P16（16/1）完成 100 MHz 整机 route；P16 manifest 参数为 `P_WAYS=16 / PIPE_TREE=1`，ENET0 MIO 配置进入 `ps7_init`。P16 的上板结果另列于 B2。 | 初次整机构建：`hw/build/bkb220-p16-100mhz-20261012T123936Z-board-migrate-p16/`；B1 重建包：`hw/build/bkb220-p16-enet0-100mhz-20261012T144141Z-board-migrate/`、`hw/build/bkb220-p16-enet0-software-20261012T144141Z-board-migrate/`；汇总：构建记录、来源表 §15.1 |

## 已完成：A 组 P4 板端深化

以下五项均使用 P4 包，判据和留证分别记录在[来源表 §14](../board/bkb220/migration-source-table.md)。它们不能替代 P16 对应故障探针。

| 项目 | 判据与结果 | 留证目录或文件 |
|---|---|---|
| A1 全量三轮 | 每轮 103,616 条记录；三轮图片 SHA 相同且等于上述 SHA；四级 DDR 取证通过。 | `D:\bkb220_board_smoke\g3_runs\20261012T144029Z\` |
| A2 连续运行与状态复位 | 先执行弄脏轮，再验证干净轮；两轮原始回传相差 **1500/64800 bit**，证明复位判据有鉴别力；后续 2048 档和全量判据通过。 | `D:\bkb220_board_smoke\g3_runs\20261012T144314Z\` |
| A3-1 配置/容量守卫 | **7/7** 注入符合预期接受或拒绝，且每次注入后板端仍存活。 | `logs/g3/a3-faults/config-guard/config_guard.jsonl` |
| A3-2 断连/畸变包恢复 | **30/30**；各异常连接注入后都能再次完成 CAPS 握手。 | `logs/g3/a3-faults/recovery.jsonl` |
| A3-3 中途断网与上位机强杀 | **3/3**；双向断流并 `SIGKILL` 上位机后，板端在 2 秒内恢复可服务。 | `logs/g3/a3-faults/netfault.jsonl` |

## 已完成：B1/B2 P16

| 项目 | 判据与结果 | 留证目录 |
|---|---|---|
| B1 P16 重建 | 重建硬件和软件包；`P_WAYS=16 / PIPE_TREE=1`；ENET0 MIO 写入进入 `ps7_init`；100 MHz、WNS/WHS 为正、失败端点 0、DRC 0 errors。 | `hw/build/bkb220-p16-enet0-100mhz-20261012T144141Z-board-migrate/`；`hw/build/bkb220-p16-enet0-software-20261012T144141Z-board-migrate/` |
| B2 smoke | 2048 源读段、4096 条记录；制品一致性、烧录、CAPS、最终图片 SHA、四级 DDR 取证和串口输出均通过。 | `D:\bkb220_board_smoke\g3_runs\20261012T150336Z\` |
| B2 全量三轮 | 三轮各 103,616 条记录，三轮图片 SHA 相同；四级 DDR 取证通过。 | `D:\bkb220_board_smoke\g3_runs\20261012T150552Z\` |
| B2 连续运行与状态复位 | 弄脏轮到干净轮相差 1500/64800 bit；后续 2048 档及全量图片判据通过，连续执行无退化。 | `D:\bkb220_board_smoke\g3_runs\20261012T150740Z\` |

## 关键数字与口径

| 指标 | P4（4/0） | P16（16/1） |
|---|---:|---:|
| 整机时钟 | 100.000 MHz | 100.000 MHz |
| WNS / TNS | +0.680 ns / 0 | +0.617 ns / 0 |
| WHS / THS | +0.036 ns / 0 | +0.017 ns / 0 |
| Setup 失败端点 | 0 / 51,506 | 0 / 86,415 |
| Hold 失败端点 | 0 / 51,506 | 0 / 86,415 |
| LUT | 15,447 / 53,200（29.04%） | 33,987 / 53,200（63.89%） |

同板端到端结果接收时间 `t_result`：

| 输入档 | P4 | P16 | 记录的对照 |
|---|---:|---:|---:|
| Smoke（2048 源读段） | 1.45 s | 0.75 s | 约 1.9× |
| 全量 | 26.51 s | 8.61 s（三轮为 8.61/8.71/8.61 s） | 约 3.05× |

**口径边界：** `t_result` 不含上传与 LDPC，也不是一整轮耗时；不能当作正式整机总耗时或最终性能结论。正式性能口径待 C1 六档矩阵（128/512/2048/8192/32768/full，各至少三次，并统计中位数、离散程度、斜率和截距）。数值来源：[构建记录](../benchmarks/bkb220-p4-p16-100mhz-build.md)及[来源表 §15](../board/bkb220/migration-source-table.md)。

## 踩过的坑与纠正

- **MDIO 完成标志与使能位读写错误：** 早期探测轮询了错误寄存器，并把 `NETWORK_CONTROL` 的 TXEN 当成 MDEN。按驱动头文件更正为 `NETWORK_STATUS[2]` 判完成、`NETWORK_CONTROL` bit 4 置 MDEN 后，PHY 应答并确认链路。详见来源表 §9.6、§12.5。
- **`lwip220` 假阻塞：** WSL Vitis 2022.2 提供 `lwip211_*`，仓库生成脚本也按 `lwip213→lwip211→lwip210` 回落；`lwip220` 是 2026.1 才有。缺少 `lwip220` 不代表 2022.2 无法构建，版本差异应按实际安装记录。详见[03 工具链说明](../03-status.md) §1b及来源表 §12.5。
- **探针配置不等于制品配置：** 探针 `ps7_init` 有 ENET0 MIO 配置，但实际 P4 profile 曾缺少相关属性，造成首轮 G3 网络不通。将完整 ENET0 配置写回 `hw/boards/bkb220.tcl`，重建硬软包并重跑 G3 后通过。详见来源表 §12–§13。
- **CRLF 假 FAIL：** Windows 侧采集输出带 `\r`，导致 `CAPTURE_DONE` 行尾匹配失败，误报没有串口输出；读取时归一化换行后，最终 G3 按 7781 字符的实收输出通过。详见来源表 §13.1。

## 仍未做 / 单列项

- **P16 故障探针未做：** 配置/容量守卫、断连畸变包恢复、中途断网恢复。P4 A 组的通过结果不能替代它们。
- **C1 性能矩阵未做：** 同板 P4/P16 六档、每档至少三次及统计汇总。
- **C2 泛化未做：** 至少 5 个独立 payload，覆盖 sub/ins/del、覆盖度、阈值和至少 3 个种子；FAR 真值只从合成 header 取得。
- **D 长稳未做：** 按 2 小时后 8 小时的实际墙钟计划验收。
- **冷启动与接口：** QSPI/SD 冷启动未测；UART 反方向（PC→PS）未测。
- **板级参数：** DDR 板级延迟与 DQS-to-CLK 未测；工业级器件精确料号/实物顶标未核实。
- **功耗：** 缺少测量仪器，未测；不得用估算替代实测。
- **SE250：** 另一个 profile 与几何，本阶段 SE150 结果不代表 SE250 已验证。
- **比赛合规：** 仓库根目录无 `LICENSE`；开发主线使用 Vivado/Vitis 2022.2，而评分要求 Vivado 2026.1 或 2025.2（若维持其他版本，报告需说明版本并保证可复现）；LLM 提示词、回答和自我纠错材料已有素材但尚未整理成提交记录；决赛一页英文海报未做。文件/目录名合规自查也列在 05 §7 的 P2。

## 下一步：按 05 §7 的 P1–P7

1. **P1 本轮收口：** 完成 P16 剩余故障探针 → C1 六档性能矩阵 → C2 泛化 → D 长稳。
2. **P2 合规与得分缺口：** 补 LICENSE、整理 LLM 协作记录并完善技能包、补工具版本说明与可复现保证、完成文件名自查；冷启动、UART 反向和工业级料号核实列入本阶段。
3. **P3 全面优化：** 优化时间消耗与性能，按实测优先处理 PS 侧瓶颈；DDR 板级延迟与 DQS-to-CLK 作为相关事项核查。
4. **P4 冻结 22 主线：** 优化完成后停止修改。
5. **P5 写最终报告：** 仅在冻结后撰写；这份阶段总结不替代最终报告。
6. **P6 最后切 26 开发：** 用 Windows 2026.1 完整硬件与软件开发链做独立复核。
7. **P7 交付收尾：** 同步交付文档与制品证据、完成收尾材料及决赛英文海报。

