# v1.1 的 8 h 长稳：**PASS**（2026-10-18，第五次尝试）

> ✅ **这是 v1.1 第一次真正跑满 8 小时并通过。**
> 前四次尝试的失败记录保留在 [soak-v1.1-2026-10-17.md](soak-v1.1-2026-10-17.md)，
> **不得删除或改写**——它们解释了为什么这场是第五次。

## 1. 身份（可归属）

| 项 | 值 |
| --- | --- |
| 制品包 | `hw/build/bkb220-v1.1-release-20261016T134556Z-fwid` |
| bit SHA-256 | `2ec76c7dfbe3d92ef706d8f5a60f8062e1e714fcd424b6ca9c7cee7fc313d1aa` |
| `fw_build_id` | `db5705fb4d0bc003`（**启动核对 PASS**，期望=实读） |
| 核对时刻 | `2026-10-18T02:39:07Z`（本地 10:39） |
| `--tag` | `v11-fwid-db5705fb-bit2ec76c7d-soak5-20261018` |
| 留证目录 | `/mnt/d/bkb220_board_smoke/soak-v1.1-20261018T0239Z/` |
| 板端运行方式 | SD 卡冷启动；每轮 `--skip-boot`（不做 JTAG 复位/烧录） |

## 2. 结果（`soak_summary.json` 原值）

| 字段 | 值 |
| --- | --- |
| `verdict` | **PASS** |
| `wall_s` | **28,810.3 s = 8 h 0 m 10.3 s** |
| 目标 / 最低线 | 8.0 h / 28,224 s（7 h 50 m 24 s） |
| `wall_target_delta_s` | **+10.3 s**（超过目标） |
| `wall_time_sufficient` | **True** |
| `rounds` | **1736** |
| `rounds_pass_with_expected_sha` | **1736** |
| `rounds_failed` | **0** |
| `rounds_unverified` | **0** |
| `recovery_probes` | **173** |
| `recovery_probes_pass` | **173** |
| `recovery_probes_failed` | **0** |
| `stop_reason` | **`wall_clock_target_reached`** |
| `stopped_early` | **False** |
| `hardware_cycles` / `power_w` | `null`（**无仪器，不得反推**） |

每轮口径：全量输入，板端回传 **103,616 条记录**、`score_min=67`、
系统载荷 SHA-256 `fcd0cf90bd680e7bbdc203e3398119504da0897acac9e2117008b4efb6b1f2c3`。
累计处理约 **1.799 亿条**板端记录（1736 × 103,616）。

## 3. 逐轮证据

- 逐轮 TSV：`soak-v1.1-20261018T0239Z/soak.tsv`（1736 行，每行 `process_rc=0`）；
- 每轮完整输出：`roundNNNN.out`；
- 每次恢复探针的结构化结果：`recovery.jsonl`（1730 个用例，全部 `case_status=pass`）；
- 每轮 G3 留证：`g3_runs/20261018T0239Z` ~ `g3_runs/20261018T103907Z`；
- 启动身份：`fw_build_id_startup.json`。

> ⚠️ `logs/` 与 `/mnt/d/` 均不进 Git，提交材料若只留本文，审阅者无法复核逐轮。
> 这是已知缺陷，见验收文档 §6。

## 4. 与前四次尝试的关系（**必须一起读**）

| 场次 | 结果 | 原因 |
| --- | --- | --- |
| 1（2026-10-16） | 中止 | 仅 18.3 分钟 / 69 轮，当晚断电被叫停 |
| 2（2026-10-17） | **FAIL** | 第 1008 轮板子整体失联（网络 + JTAG 同时不可达），4.906 h 后止损 |
| 3（2026-10-17） | FAIL（作废） | 主机侧：残留 `g3_uart_cap.py` 抢占串口，判据其实全过 |
| 4（2026-10-17） | **FAIL** | 1690 轮判据全过，但恢复探针 `connect()` 5 s 超时；**已查明是主机断电/休眠**；墙钟差 11 分半 |
| **5（2026-10-18）** | **PASS** | **1736 轮 / 8 h 0 m 10.3 s / 0 失败 / 173 探针全过** |

**不能只引用第 5 场**：第 2 场暴露的板端整体失联至今**未解释**（`send_result` 的无界重试是候选假设，
见 soak-v1.1-2026-10-17.md §11），它没有在第 5 场复现，但**也没有被证伪**。

## 5. 边界（**不要读成"v1.1 全面验收完成"**）

- `hardware_cycles` 与 `power_w` 恒为 `null`：**无外部周期采集、无功率计**；
  `result_s` 是客户端打印值，**不得反推周期或功耗**。
- 长稳只证明「8 小时内 1736 轮判据全过 + 173 次探针全过」，
  **不证明**真实测序数据下的正确性（数据仍是 in-silico）。
- 板端仍存在已知的 `send_result()` 无界重试缺陷（候选根因，未修复）——
  **本次通过不等于该缺陷不存在**。
- QSPI 冷启动仍未做；F9 独立复核仍未做。
