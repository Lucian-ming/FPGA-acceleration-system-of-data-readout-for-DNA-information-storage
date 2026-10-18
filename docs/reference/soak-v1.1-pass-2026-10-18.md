# v1.1 的 8 h 长稳：**PASS**（2026-10-18）

> ✅ **v1.1 的 8 h 长稳通过。本文是 v1.1 长稳的唯一留证。**
> 本场之前有过几次尝试，均因**断电 / 主机挂起**中断，不是板端或判据问题，
> 按要求不单独留档（见 §4）。

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

## 4. 本场之前的尝试

本场之前有过几次尝试，**均因断电 / 主机挂起而中断**（用户确认），
不是板端失败，也不是判据失败。其中一次中断时伴有一次板端网络短暂失联，
**未再复现**；相关代码风险见 §6。按要求这些中断记录**不单独留档**，
v1.1 的长稳结论**只引用本场**。

## 5. 边界（**不要读成"v1.1 全面验收完成"**）

- `hardware_cycles` 与 `power_w` 恒为 `null`：**无外部周期采集、无功率计**；
  `result_s` 是客户端打印值，**不得反推周期或功耗**。
- 长稳只证明「8 小时内 1736 轮判据全过 + 173 次探针全过」，
  **不证明**真实测序数据下的正确性（数据仍是 in-silico）。
- 板端仍存在已知的 `send_result()` 无界重试风险（静态分析，见 §6）——
  **本次通过不等于该风险不存在**。
- QSPI 冷启动仍未做；F9 独立复核仍未做。

## 6. 已知代码风险：`send_result()` 的两处重试**没有时间上限**（静态分析，本次未触发）

源码事实（`sw/app/echo.c`）：

| 位置 | 形态 | 上限 |
| --- | --- | --- |
| `echo.c:802` 发头部 | `for (;;)`，`ERR_MEM/ERR_WOULDBLOCK` 就 `tcp_output` + `usleep(1000)` + `continue` | **无** |
| `echo.c:826` 发正文（8100 B） | `while (sent < result_size)`，`tcp_sndbuf()==0` 就 `usleep(1000)` + `continue` | **无** |
| `echo.c:869` 等 ACK 排空 | 有 `wait_ack_cycles < 2000` | 2000 ms |

`send_result()` 由 **`poll_callback` 的 `PROC_DONE` 分支同步调用**（`echo.c:527`），
所以一旦 TCP 发送窗口不再打开（对端不 ACK、链路瞬断、TX BD 耗尽），
回调**永不返回** ⇒ lwIP 不再处理 RX ⇒ 板子网络整体失联。

另外：这两处重试诊断用的是裸 `xil_printf`，在 `FW_DIAG_LEVEL=1` 下**被编译成空操作**
（`fw_diag.h`；只有 `FW_ERR_PRINTF` 在 1 级仍输出），所以卡住时串口是 0 字节。

**全仓审计**：`sw/app/*.c` 的全部 `for(;;)` / `while(...)` 中，无上限的只有上述两处
（`stage3_decoder.c:335` 有墙钟上限，`echo.c:314` 每轮消耗缓冲，`main.c:350` 是主轮询循环）。

**建议修法（未实施，需拍板；会换制品与新 `fw_build_id`）**：
给两处加墙钟上限（建议 30 s），超时 `tcp_abort` 并回到 `PROC_IDLE`，
把永久挂死降级为单轮失败；同时把重试诊断改为 `FW_ERR_PRINTF` 以留下证据。
不动判据、不动 RTL（同一个 bit）。
