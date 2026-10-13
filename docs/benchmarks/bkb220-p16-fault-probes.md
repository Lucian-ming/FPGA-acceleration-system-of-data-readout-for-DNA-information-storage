# BKB220 P16 故障注入探针（B2 收口，2026-10-13）

本文是 [05 §7](../05-implementation-plan.md)「P1 本轮收口 → B2 剩余」的正式留证。
A 阶段（2026-10-12，**P4** 包）已经在 BKB220 上跑过这三个探针（`docs/03` §A：配置守卫 7/7、断连畸变 30/30、中途断网 3/3）；
**B2 的缺口是换 P16 包复跑**——即「守卫与恢复能力是否只对 P4 成立」。本文关掉这一项。

- 被测包：`hw/build/bkb220-p16-enet0-software-20261012T144141Z-board-migrate`（`C_STAGE1_P_WAYS=16`、`C_STAGE1_PIPE_TREE=1`）；板端身份已由同日的 [P16 v2 扫描](../board/bkb220/migration-source-table.md) 独立确立。
- 目标：`192.168.1.10:7`；板端 CAPS `read_bps=150 num_lc=50 stride=807 max_reads=129600`。
- 留证：`logs/g3/b2-probes/`（`logs/` 不入库，文件保留）；板侧运行目录在 `D:\bkb220_board_smoke\g3_runs\20261013T05*Z\`。

## 1. 配置 / 容量守卫（`g3_config_guard_probe.py`）：7/7

手工拼 CONFIG 字节，**绕开客户端全部校验**，直打固件守卫。

| 用例 | 期望 | 板端实测 |
| --- | --- | --- |
| `capacity_ok_boundary`（恰好 129,600） | 接受 | ✅ 接受 `rc=0` |
| `capacity_exceed_by_one_frame`（超一帧） | 拒绝 | ✅ `rc=5`（total_reads 非法） |
| `capacity_exceed_large` | 拒绝 | ✅ `rc=5` |
| `not_frame_aligned`（非 64 整数倍） | 拒绝 | ✅ `rc=5` |
| `zero_reads`（空任务） | 拒绝 | ✅ `rc=5` |
| `wrong_read_bps`（250） | 拒绝 | ✅ `rc=2`（read_bps 不被支持） |

**6/6 用例 7/7 项判定通过**（含"恰好等于上限必须被接受"这一反例——守卫不能把合法值也拦掉）。

⚠️ 读这份结果时的**坑**（工具文件头已记）：`PKT_CONFIG_OK` 只是**应答**，
payload 里的 u32 **才是理由码，0 才是接受**。把"有应答"当成"接受"会得出完全相反的结论。
后置守卫判定：CONFIG 接受=False、首批 BATCH 接受=None、板子存活=True ——
即**守卫在越界写发生之前就拦住了**，不是"拒绝太晚但 DDR 已经受伤"。

## 2. 畸变包 / 断连恢复（`g3_recovery_probe.py`）：30/30

10 类注入 × 3 遍：

```text
baseline_caps · half_header · bad_magic · unknown_pkt_type · oversized_length
truncated_payload · reset_mid_caps · idle_then_close · second_connection · flood_bad_headers
```

- **30/30 `recovered=true`，全部 1 次尝试**。
- 恢复耗时：26 例 **2.01~2.03 s**，3 例 **4.16~4.50 s**（对应注入本身更慢的用例）。
- 与 A 阶段 P4 的 30/30、与旧板 G6 的 10/10 同结论。

## 3. 中途断网 / 上位机崩溃（`g3_netfault_probe.py`）：3/3

`iptables` 双向黑洞 + `SIGKILL` 上位机，**板端连 FIN 都收不到**——正是现场拔网线的样子。

```text
idle_outage · mid_task_outage_kill · mid_task_outage_kill_repeat
```

- **3/3 恢复，恒 2.02~2.03 s / 1 次尝试**。
- **`iptables` 规则清理干净**：脚本自检 + main 独立复核 `sudo iptables -S | grep 192.168.1.10` 无残留。

## 4. 判据轮：折腾完数据通路仍然逐位正确

三个探针只证明**协议层/连接层**恢复；数据通路的唯一判据仍是译码载荷 SHA。
探针跑完后**立刻**在**同一个 P16 固件实例**上（`--skip-boot`）跑了一轮全量判据：

```
PASS  完整制品包一致性   — …bkb220-p16-enet0-software-20261012T144141Z-board-migrate
PASS  板端应用层就绪     — READY 2.0 1
PASS  第 1 轮 first.py   — 103616 条记录 / score_min=67 / 15s；Result: 8100 bytes, 9.03s
PASS  第 1 轮 唯一判据   — fcd0cf90bd680e7bbdc203e3398119504da0897acac9e2117008b4efb6b1f2c3
PASS  串口收到板端输出   — 8231 字符
```

**全量输入 + `score_min=67`** 下黄金 SHA 逐位相同 → 故障注入**没有在 DDR / Voter 累加器里留下残渣**。
（这一轮同时顺带关闭了「`score_min=67` 在新板上未在全量档验过」这一项——但**仅限 R0.83**，v2 数据集仍未在 67 下测。）

## 5. 边界（不得外推）

- 探针证明的是**协议层/连接层**的恢复与守卫的**拒绝行为**；**数据通路正确性只由第 4 节的判据轮承担**，两者不能互相替代。
- `mid_task_outage_kill` 只跑到"被中断任务"的**中途**；**2 h 长稳已完成，8 h 未做**，短时故障恢复不等于长时稳定。长稳结果见[2 h 长稳记录](bkb220-p16-soak-2h.md)。
- `power_w` 全部为 `null`（`UNMEASURED (no power meter attached)`）——**无功率计，不得用墙钟或电流估算反推**。
- 本轮只测 **P16**；P4 侧的对应结论来自 A 阶段，两轮数值同量级但**不是同一批运行**，不要合成一条"7/7 + 30/30 + 3/3 + 7/7 + 30/30 + 3/3"的合并计数。
- 探针**主动注入错误流量**（交换机/主机的网络状态会被临时改动），不是只读健康检查；`netfault` 依赖 `sudo iptables`，只在 `finally` 清理。
