# G6 · 长稳、故障注入与恢复实测报告

> **评测日期**：2026-09-11
> **制品**：`hw/build/export/`（制品与源码同源，`SHA256SUMS` 5 项 OK；含 B29/B30、
> P0 poll 批量化修复与 `TOTAL_READS=129600`）
> **对照门禁**：[13](../archive/history/2026/pre-bkb220-handoff-2026-10-10/final-delivery-roadmap.md) §4 G6
> **留证**：`tests/stress_results/g6_campaign_20260911T040151Z/`、
> `logs/g3_2026/g6_*.log`
>
> **本报告不含功耗**。G6 出口门禁的「能耗为实测值」一条**未关闭**——
> 无功率计，`recovery.jsonl` 里的 `power_w` 字段全为空、`power_note` 标记未测。
> 不得据本报告做任何能效表述。

---

## 1. 连续任务：跨规模四轮，含弄脏轮

一次上电内连续下发四轮，中间不复位、不重烧
（`tools/run_g3.sh --runs 4 --run-limits full,2048,8192,2048 --run-score-mins 0,67,67,67`）：

| 轮次 | 规模 | `score_min` | 角色 | 结果 |
|---:|---|---:|---|---|
| 1 | 全量 103,616 记录 | **0** | **弄脏轮**（让所有读段都进投票累加器） | 执行完成 |
| 2 | 4,096 记录 | 67 | 判据轮 | ✅ 哈希 `fcd0cf90…f2c3` |
| 3 | 16,384 记录 | 67 | 判据轮 | ✅ 哈希相同 |
| 4 | 4,096 记录 | 67 | 判据轮 | ✅ 哈希相同 |

**鉴别力自证**：第 1→2 轮回传相差 **1,500 / 64,800 bit**——证明弄脏轮确实往累加器里
写进了不同向的票，第 2 轮不是「本来就干净所以过了」。
**这一条是本节的关键**：没有它，「连续多轮都通过」可能只是因为状态从没被真正污染过。

**无性能退化**：同参数轮次逐轮耗时 `61 / 4 / 12 / 4` 秒，判据轮之间 < 1.5x。

---

## 2. 故障注入与恢复

三类注入，**每类注入完都补一轮判据轮**——只证明「连接恢复了」不够，
必须证明**数据通路仍然逐位正确**。

### 2.1 畸变包注入（10 类，10/10 恢复）

`tools/board/g3_recovery_probe.py`：

```text
baseline_caps · half_header · bad_magic · unknown_pkt_type · oversized_length
truncated_payload · reset_mid_caps · idle_then_close · second_connection · flood_bad_headers
```

全部 `recovered=true`，恢复恒 **2.0 s / 1 次尝试**。
**注入后判据轮**：哈希 `fcd0cf90…f2c3` 逐位相同。

### 2.2 断网注入（3 类，3/3 恢复）

`tools/board/g3_netfault_probe.py`（iptables 黑洞，含任务中途断网并杀掉上位机）：

```text
idle_outage · mid_task_outage_kill · mid_task_outage_kill_repeat
```

全部恢复，恒 **2.0 s / 1 次尝试**，`iptables` 规则清理干净无残留。
**注入后判据轮**：哈希逐位相同，四级逐级取证全过。

### 2.3 非法配置注入（7 类，7/7 正确）

`tools/board/g3_config_guard_probe.py`，手工拼 CONFIG 字节绕开客户端全部校验：

| 用例 | 板端应答 |
|---|---|
| 恰好等于容量上限 129,600 | ✅ 接受 `rc=0` |
| 超容量一帧 / 远超容量 / 非 64 对齐 / 空任务 | ✅ 拒绝 `rc=5 total_reads 非法` |
| `read_bps=250`（比特流仅 150bp） | ✅ 拒绝 `rc=2 read_bps 不被支持` |
| 后置守卫 | ✅ 被前置拦住，走不到后置 |

全部注入后 `board_alive_after=true`，**板子没有挂死**。

> 该项同时关闭 [13](../archive/history/2026/pre-bkb220-handoff-2026-10-10/final-delivery-roadmap.md) §7.4 **G3**
> 「读长自动识别可靠，150/250 混用被明确拒绝」。

---

## 3. 对照 G6 出口门禁

| 门禁 | 状态 | 依据 |
|---|---|---|
| 产品失败与预期故障注入分开统计 | ✅ | 20 类注入全部记 `failure_class`/`injection` 字段，与正常轮分离 |
| 连续任务无不可诊断挂死 | ✅ | 四轮连续 + 20 类注入，`board_alive_after` 全 true，无挂死 |
| 任何异常都能定位到协议/固件/RTL/数据层 | ✅ | 每类注入都有 `inject_error`/`last_error`/`board_response` 与串口实录 |
| **能耗为实测值** | ❌ **未关闭** | **无功率计**，`power_w` 全空 |

**G6 因此是「除功耗外全部达成」**，不能写成 G6 通过。

---

## 4. 事实边界

1. **不含功耗与温度**。`power_w` 字段存在但全为空，`power_note` 标记未测，
   不得据此做任何能效或散热表述。
2. **恢复时间 2.0 s 是探针的重试节奏**，不是板端最小恢复时延——
   探针以 2 s 为间隔重试，首次即成功，因此真实恢复时间 **≤ 2.0 s**，
   下界未测。
3. **长时温漂未测**。本轮最长连续为一次上电内四轮（约 81 s 计算），
   G6 要求的「长期温度运行」尚无数据。
4. 全部数据来自 SE150 / 150 bp 配置；SE250 端到端仍受限于比特流（仅支持 150 bp）。
