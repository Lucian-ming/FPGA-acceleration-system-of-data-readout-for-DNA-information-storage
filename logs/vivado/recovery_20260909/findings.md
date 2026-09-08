# 4-way 整机构建：时序未收敛调查（findings）

- **run-id**：`recovery_20260909`
- **agent**：`vivado-4way-build`（2026-09-08 20:2x 因 5 小时用量限额被杀，2026-09-09 00:47 恢复）
- **被调查产物**：`hw/build/export_4way/`（构建于 2026-09-08 20:32:46）
- **基线对照**：`hw/build/export/`（2-way，构建于 2026-09-06 14:11:22）
- **器件**：xc7z010-clg400，Speed `-1` PRODUCTION 1.12，Vivado 2022.2

---

## 0. 一句话结论

**4-way 整机比特流已成功生成，但 100 MHz 时序未收敛（WNS = −0.252 ns）。
失败路径与 4-way 选优树无关**——它落在 `desparsification_dec` → AXI HP 互联的
写通道握手链上；该路径在 2-way 基线中**本来就是关键路径**，只剩 +0.136 ns 裕量。
4-way 没有制造这个瓶颈，而是把它仅存的裕量吃光了（路径起点被推远、逻辑级数 11→13）。

**全部 43 个失败端点的源点是同一个寄存器 `desparsification_dec_0/u_dp/in_bits_reg[3]`。**
靶点极小，这决定了修复方案应当对症而非降频或回退。

---

## 1. 中断点澄清：那次「重启构建」其实跑完了

看板最后停在 20:24:57「重新启动Vivado整机构建」，形似半途而废，实则不然：

- `logs/vivado/20260908T122457Z-552420/vivado.log` 末尾为
  `===> DONE.` + `Exiting Vivado at Tue Sep 8 20:32:46 2026` —— 构建在会话被杀前**完整跑完**。
- 产物齐全且时间戳一致（20:32）：
  `top_bd_wrapper.bit` (2 083 850 B)、`dna_accel.xsa` (771 181 B)、
  `reports/{summary.log,timing.rpt,util.rpt}`。
- 对 `component.xml` 的 10 处 SE250 残留重复 `<spirit:value>` 修复**有效**：
  IP 被 IP Catalog 接受，否则综合根本无法开始。该 schema 缺陷已排除。

## 2. 核心数字：整机 implementation 时序

`hw/build/export_4way/reports/summary.log`：

```
design : dna_accel
tool   : 2022.2
date   : 2026-09-08 20:32:42
WNS    : -0.252 ns
        ⚠ 未收敛，估算上限 97.5 MHz
```

Design Timing Summary（`timing.rpt`）：

| 指标 | 2-way 基线 | 4-way | 判定 |
| --- | --- | --- | --- |
| WNS (ns) | **+0.136** | **−0.252** | ✗ 回归 −0.388 ns |
| TNS (ns) | 0.000 | −4.073 | ✗ |
| TNS 失败端点 | 0 / 45286 | **43 / 51515** | ✗ |
| WHS (ns) | +0.007 | +0.014 | ✓ 保持时间无违例 |
| THS 失败端点 | 0 | 0 | ✓ |
| WPWS (ns) | 3.000 | 3.000 | ✓ |

- 时钟约束正确：`clk_out1_top_bd_clk_wiz_0_0` = 100.000 MHz / 10.000 ns。
- `check_timing` 全 0 违例：**0 个 unconstrained_internal_endpoints**、0 个 no_clock。
  → 这不是「约束漏写导致的假收敛/假失败」，**违例是真实的**。
- 失败集中：43 / 51515 端点，TNS 仅 −4.073 ns，属**小幅、集中**的违例。

## 3. 关键路径定性：不在 4-way 选优树上

`timing.rpt` 报告的 10 条最差 setup 路径，**源点完全相同**：

- **Source**：`top_bd_i/desparsification_dec_0/inst/u_dp/in_bits_reg[3]/C`
- **Destination**：`top_bd_i/ic_hp/s04_couplers/auto_us/inst/.../M_AXI_WDATA_I_reg[57..60,40..45]/CE`
- **Data Path Delay**：9.897 ns —— **logic 2.552 ns (25.8%)，route 7.345 ns (74.2%)**
- **Logic Levels**：13（LUT2×3 LUT3×3 LUT4×2 LUT5×3 LUT6×1 MUXF7×1）

路径形态（组合握手链）：

```
desparsification_dec/u_dp/in_bits_reg[3]
  → M00_AXI_WVALID (组合产生)
  → ic_hp/xbar  gen_slave_slots[3] wdata_router
  → ic_hp/xbar  gen_master_slots[0] wdata_mux / wmux_aw_fifo
  → m00_couplers/auto_pc  AXI4→AXI3 协议转换 cmd_queue → s_axi_wready
  → 回流 xbar  s_axi_wready[4]（MUXF7）
  → s04_couplers/auto_us  upsizer  M_AXI_WDATA_I_reg[*]/CE
```

这是**典型的 AXI `WVALID → WREADY` 组合回路**：WVALID 穿过 crossbar 与协议转换器，
WREADY 再组合地绕回来驱动 upsizer 数据寄存器的 CE。全程未打拍。

**判定（回答 main 的问题）：关键路径不落在 4-way 新增的两拍选优树上。**
在 4-way 的 10 条最差路径中，`Dna_accelerator_core_0` / `srpe_batch` **一次都没有出现**。
反而是 2-way 基线的第 6~9 条路径源点为
`Dna_accelerator_core_0/inst/u_srpe_batch/pos_base_reg[6]` —— 也就是说，
**加速核在基线里还排得进最差路径榜，在 4-way 里已经掉出榜外**。
4-way 微架构本身不是整机不收敛的主因。

### 3.1 全量枚举：43/43 失败端点已完整覆盖

不满足于 `report_timing_summary -max_paths 10` 的前 10 条，已打开 routed DCP 做两轮枚举：

| 脚本 | 查询 | 结果 |
| --- | --- | --- |
| `enumerate_failing.tcl` | `-max_paths 200 -nworst 200` | 200 条路径，触及加速核 **0** 条（撞 200 上限，覆盖 39/43 端点） |
| `enumerate_all_endpoints.tcl` | `-max_paths 5000 -nworst 1` | **43/43 端点完整覆盖** |

完整枚举结论（`failing_endpoints_complete.tsv`）：

- **`Dna_accelerator_core` / `srpe_batch` 在全部 43 个失败端点中出现 0 次。**
- **全部 43 个端点共享同一个源点**：`desparsification_dec_0/inst/u_dp/in_bits_reg[3]/C`。
- 端点分布：`ic_hp/s04_couplers`（upsizer）30 个、`axi_dma_0`（SG engine）9 个、
  `differential_voter_0` 4 个。
- slack 分布：−0.252 ns（最差）～ −0.003 ns（最轻）。

> 关于那 4 个 `differential_voter_0` 端点：自动判定脚本的正则含 `voter` 故将其计入
> "touching_accelerator"，但**逐条核对后它们不属于 4-way 选优树**——
> 它们是 `debug_write_count_reg[30,31]/CE` 与 `total_write_count_reg[29,30]/CE`，
> 即**调试/统计计数器的时钟使能**，slack 均为 −0.003 ns（43 个里最轻，几乎贴零），
> 且源点同样是 desparsifier 的 `in_bits_reg[3]`。
> 它们是同一条握手链的末梢负载，不是独立的时序问题。
> **修正记录**：`verdict.txt` 中 `touching_accelerator: 0` 来自被截断的 200 条查询；
> 完整查询为 `accelerator=4 other=39`，该 4 条即上述调试计数器。结论不变，但数字以此处为准。

## 4. 这个瓶颈是既有的，不是 4-way 引入的

2-way 基线的最差路径**终点完全相同**：

| | 2-way 基线 | 4-way |
| --- | --- | --- |
| Slack | +0.136 ns (MET) | −0.252 ns (VIOLATED) |
| Source | `ic_hp/xbar/.../wmux_aw_fifo/storage_data1_reg[0]/C` | `desparsification_dec_0/u_dp/in_bits_reg[3]/C` |
| Destination | `ic_hp/s04_couplers/auto_us/.../M_AXI_WDATA_I_reg[56]/CE` | 同族 `..._reg[57]/CE` |
| Data Path Delay | 9.510 ns | 9.897 ns |
| logic / route | 2.276 (23.9%) / 7.234 (**76.1%**) | 2.552 (25.8%) / 7.345 (**74.2%**) |
| Logic Levels | 11 | 13 |

**同一条 AXI HP 写握手链，在 2-way 时就已经是关键路径，且只剩 0.136 ns（1.4% 周期）裕量。**
它 route 占比常年 ~75%，是布线主导的既有结构性弱点。

回归量分解（9.510 → 9.897，+0.387 ns，与 WNS 差 −0.388 ns 吻合）：
- logic +0.276 ns（逻辑级数 11 → 13，**+2 级**）
- route  +0.111 ns

即：**回归以「路径起点被推得更远、逻辑级数 +2」为主，布线恶化为辅**。

## 5. 资源：全部在门限内，但 LUT 已逼近上限

`util.rpt` 顶层 `top_bd_wrapper`：

| 资源 | 2-way | 4-way | Δ | 门限 | 4-way 占用率 |
| --- | --- | --- | --- | --- | --- |
| Total LUTs | 12 232 | **15 499** | **+3 267 (+26.7%)** | 17 600 | **88.1%** ⚠ |
| Logic LUTs | 11 553 | 14 820 | +3 267 | — | — |
| LUTRAMs | 456 | 456 | 0 | — | — |
| SRLs | 223 | 223 | 0 | — | — |
| FFs | 14 830 | 16 908 | +2 078 (+14.0%) | 35 200 | 48.0% |
| RAMB36 | 44 | 44 | **0** | 60 | 73.3% ✓ |
| RAMB18 | 2 | 2 | 0 | — | — |
| DSP | 3 | 3 | 0 | 80 | 3.8% |

- **验收判据 RAMB36 ≤ 60：PASS**（44，且 4-way 未增加 BRAM）。
- **验收判据 LUT ≤ 17600：PASS**（15 499），但占用率从 69.5% → **88.1%**。
  **资源判据通过 ≠ 时序判据通过**。

> **修正：拥塞假设不成立。** 本文初稿推测「88.1% LUT 占用 → 布局拥塞 → 时序恶化」，
> 但 `report_design_analysis -congestion`（见 `congestion.rpt`）明确显示：
> Placer Final Level 与 Initial Estimated Router **均无 level > 5 的拥塞窗口**。
> 因此**不能**把这次回归归因于布线拥塞。证据支持的机制是：
> 路径起点被推得更远（源点从 xbar 内部退到 desparsifier 的 `in_bits_reg`）、
> **逻辑级数 11 → 13**，导致 logic 延迟 +0.276 ns（占回归 −0.388 ns 的 71%），
> route 仅 +0.111 ns。高 LUT 占用可能是背景因素，但没有拥塞数据支撑因果断言。

## 6. ⚠ 交付口径修正：OOC 综合 ≠ 整机收敛

已提交文档 `docs/benchmarks/stage1_4way_ip_integration.md` 中的 **WNS = +2.197 ns**
是 **OOC（Out-of-Context）综合**结果，作用域仅为 **srpe 比对核单模块**：
不含 PS7、AXI 互联、DMA、BD 顶层，且**不含真实布线**（OOC 用估算线延迟）。

本文测得的 **WNS = −0.252 ns** 是**整机 implementation（route_design 后）**，
包含全部逻辑与真实布线。

**两者不是同一个量，OOC 正裕量绝不蕴含整机收敛。**
本例即为反证：模块级 +2.197 ns，整机 −0.252 ns。
文档目前只写了前者，读者极易误读为「4-way 整机时序已过」。
此为 `AGENTS.md`「不得把仿真/综合当板级证据」同类错误，需在文档中显式区分。

## 7. 对交付口径的影响

- ❌ 不可表述为「4-way 整机构建通过」。
- ✅ 可表述为：「4-way 整机构建**可完成**，`component.xml` schema 缺陷已修复，
  资源判据（LUT 15499≤17600、RAMB36 44≤60）通过；
  但 **100 MHz 整机时序未收敛，WNS = −0.252 ns，估算上限 97.5 MHz**，
  失败路径位于 `desparsification_dec` → AXI HP 写握手链（既有瓶颈），
  与 4-way 选优树无关。」
- ⛔ `hw/build/export_4way/*.bit` / `*.xsa` **不入库**：一个 100 MHz 未收敛的比特流
  一旦进仓会成为事实基线，后患大。按 `docs/13` §8.2「失败也算产出」，
  留**证据**（本 findings + 报告摘要）而非**产物**。
  同理，基于该 bit 的任何板测结果都**不能**作为时序合格证据——它等于超频运行。

## 8. 备选方案（待定，需 main 决策）

既然瓶颈是既有 AXI 握手链而非 4-way 微架构，三选一的答案倾向明确：

1. **回退 2-way** —— ✗ 不推荐。会白白丢掉 4-way 已验证的 1.929x 顶层加速比，
   而瓶颈根本不在 4-way。属于「治错了病」。
2. **降频至 95 MHz** —— △ 可行但是钝器。−0.252 ns 意味着 97.5 MHz 上限，
   降到 95 MHz 有裕量。代价：全系统吞吐按比例损失 5%，且掩盖了真实结构问题。
3. **在 AXI 写握手链上插流水 / 减负** —— ✓ 首选方向，且是对症的。候选手段：
   a. 在 `desparsification_dec` 的 `M00_AXI_WVALID` 上**寄存输出**，
      切断 `in_bits_reg → WVALID` 的组合前段（这是 4-way 相对基线新增的 2 级逻辑所在）；
   b. 给 `ic_hp` 的 S04 slave 口启用 **AXI Register Slice**（BD 中一个属性开关，
      代价是 +1 拍延迟，对流式写入吞吐影响可忽略）；
   c. 降低 LUT 占用以缓解拥塞（88.1% 偏高），或对 impl 启用
      `Performance_ExplorePostRoutePhysOpt` 等更激进策略先看能否自动补回 0.252 ns。

   建议顺序：先试 (c) 的 impl 策略（零 RTL 改动，只差 0.252 ns，最快证伪），
   再做 (b)（BD 属性改动，风险低），最后才动 (a)（需改 RTL 并重跑功能验证）。

   **靶点极小这一点值得强调**：全部 43 个失败端点由**同一个源寄存器**
   `in_bits_reg[3]` 驱动。方案 (a) 只需在该寄存器到 `M00_AXI_WVALID` 的组合段上打一拍，
   理论上可一次性消除整个违例集合，而非逐条修补。
   注意 (a) 改的是 `desparsification_dec`，属**既有 IP**，不是 4-way 新增逻辑——
   这与「瓶颈是既有的」结论一致。
   另注：由于拥塞假设已被证伪（见 §5 修正），(c) 若失败不应解释为「拥塞太严重」，
   而应直接转入 (b)/(a) 的打拍方案。

## 9. 复现方式

```bash
# 本文全部数字可直接从已存报告复核，无需重跑 Vivado：
cat hw/build/export_4way/reports/summary.log          # 4-way WNS
cat hw/build/export/reports/summary.log               # 2-way 基线 WNS
grep -A6 "Design Timing Summary" hw/build/export_4way/reports/timing.rpt
grep -E "^Slack |^  Source: |^  Destination: |^  Data Path Delay:|^  Logic Levels:" \
     hw/build/export_4way/reports/timing.rpt | head -20
grep -E "^\| +top_bd_wrapper" hw/build/export_4way/reports/util.rpt   # 资源
```

## 10. 变更文件清单（交 main 审阅提交）

- `logs/vivado/recovery_20260909/findings.md`（本文，新增）
- `logs/vivado/recovery_20260909/enumerate_failing.tcl`（新增，失败路径枚举脚本，200 条上限）
- `logs/vivado/recovery_20260909/enumerate_all_endpoints.tcl`（新增，43/43 端点完整枚举）
- `logs/vivado/recovery_20260909/failing_endpoints.tsv` / `failing_endpoints_complete.tsv`（证据数据）
- `logs/vivado/recovery_20260909/verdict.txt`（自动判定，数字以 §3.1 为准）
- `logs/vivado/recovery_20260909/congestion.rpt`（证伪拥塞假设的关键证据）
- `logs/vivado/recovery_20260909/failing_paths_all.rpt` / `util_flat.rpt` / `enumerate*.log`
- `hw/ip/Dna_accelerator_core_1_0/component.xml`（已改：修复 10 处重复 `<spirit:value>`）
- `hw/scripts/build.tcl`（已改：新增 `DNA_EXPORT_DIR` / `DNA_REPORT_DIR`，避免覆盖 2-way 基线）
- **不提交**：`hw/build/export_4way/`（含未收敛比特流与 XSA）

---

# 11. 方案 (c) 执行结果：**成功，100 MHz 已收敛**

- 执行时间：2026-09-09 00:57:17 → 01:05:11（约 8 分钟）
- 脚本：`rerun_physopt.tcl`　日志：`physopt_run.log`　产物：`physopt/`
- 变更内容：**仅把 `impl_1` 策略由 `Vivado Implementation Defaults`
  改为 `Performance_ExplorePostRoutePhysOpt`。零 RTL 改动、零 BD 改动。**
- 复用 `synth_1`（脚本硬性校验 `PROGRESS == 100%`，否则退出），
  确保「策略」是本次 A/B 的唯一变量。

## 11.1 结果

```
design   : dna_accel (方案c Performance_ExplorePostRoutePhysOpt)
date     : 2026-09-09 01:05:11
strategy : Performance_ExplorePostRoutePhysOpt  (原: Vivado Implementation Defaults)
WNS      : 0.246 ns
failing_endpoints : 0
结论     : ✓ 100MHz 收敛，方案(c)成功，无需改 RTL/BD
```

| 指标 | 2-way 基线 | 4-way 默认策略 | **4-way 方案(c)** |
| --- | --- | --- | --- |
| WNS (ns) | +0.136 | −0.252 | **+0.246** ✓ |
| TNS (ns) | 0.000 | −4.073 | **0.000** ✓ |
| TNS 失败端点 | 0 / 45286 | 43 / 51515 | **0 / 51501** ✓ |
| WHS (ns) | +0.007 | +0.014 | +0.013 ✓ |
| THS 失败端点 | 0 | 0 | 0 ✓ |
| WPWS (ns) | 3.000 | 3.000 | 3.000 ✓ |

**WNS 从 −0.252 ns 摆到 +0.246 ns，改善 +0.498 ns，且裕量比 2-way 基线（+0.136）还高。**
setup / hold / pulse-width 三项全部收敛，43 个失败端点**全部消除**。

## 11.2 关键路径已转移进加速核（且满足时序）

方案 (c) 后的最差路径不再是 AXI 握手链：

- **Source**：`top_bd_i/Dna_accelerator_core_0/inst/u_srpe_batch/plane_lo_reg_0/CLKARDCLK`
- **Destination**：`top_bd_i/Dna_accelerator_core_0/inst/u_srpe_batch/cw_acc_reg[169]/D`
- Slack **+0.246 ns（MET）**，Data Path Delay 9.650 ns
  （logic 3.931 ns / 40.7%，route 5.719 ns / 59.3%），**Logic Levels 8**（原 13）

即：**desparsifier → AXI 写握手链已退出关键路径，4-way 加速核成为新的关键路径，
但它满足 100 MHz 约束。** 这是健康的收敛状态——瓶颈回到真正做有用功的逻辑上，
且 route 占比从 74.2% 降到 59.3%，逻辑级数从 13 降到 8。

## 11.3 资源：几乎不变，判据仍全部通过

| 资源 | 4-way 默认策略 | 4-way 方案(c) | 门限 | 判定 |
| --- | --- | --- | --- | --- |
| Total LUTs | 15 499 | **15 483** | 17 600 | ✓ 88.0% |
| Logic LUTs | 14 820 | 14 804 | — | — |
| FFs | 16 908 | 16 907 | 35 200 | ✓ |
| RAMB36 | 44 | **44** | 60 | ✓ |
| RAMB18 | 2 | 2 | — | — |
| DSP | 3 | 3 | 80 | ✓ |

**未以资源换时序**（LUT 反而少了 16 个）。收益纯粹来自布局布线与 post-route phys_opt。

## 11.4 结论修订

§8 的三选一到此有明确答案：

- **(c) 成功，(b) 与 (a) 均不需要执行。** 无需 AXI Register Slice、无需改 `desparsification_dec` 的 RTL。
- **不需要降频**：100 MHz 达成且有 +0.246 ns 裕量。
- **不需要回退 2-way**：4-way 的 1.929x 顶层加速比得以保留。
- §4「既有 AXI 握手链是结构性弱点」的判断**依然成立且需留档**：
  2-way 基线只剩 +0.136 ns 就是证据。本次是靠实现策略把裕量赢了回来，
  **握手链本身没有被修复**。后续若再增加逻辑或提高频率目标，
  它仍会第一个失败——届时 (b)/(a) 的打拍方案仍是正解。
  建议把 `Performance_ExplorePostRoutePhysOpt` **固化进 `build.tcl`**，
  否则下次从零重建又会退回 `Vivado Implementation Defaults` 并复现 −0.252 ns。
  （此项需 main 决定是否改 `build.tcl`，我未擅自改动。）

## 11.5 交付口径（可用表述）

> 4-way 整机在 xc7z010-clg400 上**已达成 100 MHz 时序收敛**：
> WNS = **+0.246 ns**，TNS = 0，setup/hold/pulse-width 失败端点均为 0；
> 资源 LUT 15 483 ≤ 17 600、RAMB36 44 ≤ 60、DSP 3 ≤ 80。
> 该结果通过实现策略 `Performance_ExplorePostRoutePhysOpt` 达成，**无任何 RTL/BD 改动**。
> 前一次采用默认实现策略时 WNS = −0.252 ns（43 个失败端点，
> 集中于 `desparsification_dec` → AXI HP 写握手链，与 4-way 选优树无关）。

⚠ 仍需注意：**以上为整机 implementation 静态时序结论，不等于板级实测证据**
（同 §6 对 OOC 的告诫）。上板功能验证仍须单独进行。

## 11.6 产物位置

- 新比特流：`hw/build/dna_accel.runs/impl_1/top_bd_wrapper.bit`（01:04 生成，收敛版）
- 报告：`logs/vivado/recovery_20260909/physopt/{summary.log,timing.rpt,util.rpt,failing_endpoints_complete.tsv}`
- 旧的**未收敛** impl 产物已备份至 `hw/build/impl1_backup_wns_neg252/`（routed dcp + bit + runme.log，**不入库**）
- `hw/build/export_4way/` 仍是**旧的未收敛版本**，未被覆盖；如需导出收敛版应另行 export。

---

# 12. 策略固化与收敛版制品导出（2026-09-09 01:1x）

## 12.1 `hw/scripts/build.tcl`：固化实现策略

在 `launch_runs impl_1` 之前插入：

```tcl
set impl_strategy "Performance_ExplorePostRoutePhysOpt"
if {[info exists ::env(DNA_IMPL_STRATEGY)] && $::env(DNA_IMPL_STRATEGY) ne ""} {
  set impl_strategy $::env(DNA_IMPL_STRATEGY)
}
set_property strategy $impl_strategy [get_runs impl_1]
```

并附 22 行注释说明依据（WNS −0.252 → +0.246、43 端点归零、失败链与 4-way 无关、
以及「握手链未修复，只是赢回裕量」的未关闭项），避免后人当作随手参数改回默认。
保留 `DNA_IMPL_STRATEGY` 环境变量以便日后再做策略 A/B，不必改脚本。

**必要性**：不固化则从零重建退回默认策略、复现 WNS = −0.252 ns 不收敛，
已交付的收敛结果将不可复现（`docs/13` G7/G8 门禁）。

## 12.2 收敛版制品：`hw/build/export_4way_physopt/`

导出脚本 `export_physopt.tcl` 带三重硬校验，任一不满足即拒绝导出，
防止把未收敛比特流误当制品发出：

1. `impl_1 PROGRESS == 100%`
2. `impl_1 STRATEGY == Performance_ExplorePostRoutePhysOpt`
3. `WNS >= 0`

实际校验输出：`===> 校验通过 strategy=Performance_ExplorePostRoutePhysOpt WNS=0.246`

制品哈希（`SHA256SUMS`，`sha256sum -c` 全部 OK）：

```
7a9b367ea1679e736963a9791371e6757329dbe27ae356213fa53b7f34e23d89  top_bd_wrapper.bit
b05e4f57f41ebb7b8c826912707a2c440cbb466393cfa89c89768a3b06eefe66  dna_accel.xsa
85c838bfeb906eb7839835eec57aee5d41809bde724e506f7449c5ea43e62cc4  reports/summary.log
e22b03b0ade9413c4516b4d724ef923d428b76b4952cf29a08fa056b194fa8fe  reports/timing.rpt
5cfac50b43144c650a5836a9a72b4fb4c14f2e491e7e9af40491909f68051dd9  reports/util.rpt
```

**版本可鉴别性（重要，供板测方核对）**：

| 制品 | bit SHA256 前 8 位 | WNS | 可否上板作为时序合格证据 |
| --- | --- | --- | --- |
| `export_4way_physopt/`（本次，收敛） | `7a9b367e` | **+0.246 ns** | ✓ |
| `export_4way/`（旧，未收敛） | `b85770d7` | −0.252 ns | ✗ 等于超频运行 |
| `export/`（2-way 基线） | — | +0.136 ns | ✓（但为 2-way） |

`7a9b367e` 与 `hw/build/dna_accel.runs/impl_1/top_bd_wrapper.bit` **逐位相同**，
证明导出的确为方案 (c) 收敛版，非旧产物。
旧 `export_4way/` **未被触碰**（目录时间戳仍为 09-08 20:32），其报告仍是 §2~§5 的证据来源。

`reports/summary.log` 内已写入告诫：
**整机静态时序收敛 ≠ 板级实测证据，上板功能验证仍须单独进行。**
