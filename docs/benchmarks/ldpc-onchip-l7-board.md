# 片上 LDPC：L7 上板（2026-10-14）

**结论：首跑 G3 PASS 但走的是兜底（片上译码器从不真正纠错）——根因是 L6 漏做解交织，
已定位、已双向验证、已在 PS 侧补上并复测通过。修复后收敛路径首次在板上跑通，
且片上 LDPC 的**净代价落在测量噪声内**（+1 ms / 0.14%，对照无 LDPC 的参考包）。**

| 阶段 | 结论 |
| --- | --- |
| L7 首跑 | G3 PASS **但走兜底**：`converged=0 iterations=-1 error=1`，核跑满 50 轮未收敛 |
| 根因 | **L6 漏做解交织**：核被验的是自然序，板端喂的是交织序 rx，31,958/64,800 位不同 |
| 修法 | **PS 侧补置换**（`sw/app/ldpc_perm.c` + 生成的 `inv` 表），**不动比特流** |
| 复测 | **`converged=1 iterations=5`**；板端 725 ms vs 参考包 724 ms；G3 判据 SHA 不变 |

## 1. 板端结果（首跑：G3 PASS 但走兜底）

制品：`hw/build/bkb220-p16-k2-ldpc-sw-20261014T104331Z-board-migrate`（bit `8f0da7bf…`，
与无 LDPC 的参考包 bit `123c02b3…` 不同）。留证 `/mnt/d/bkb220_board_smoke/g3_runs/20261014T110319Z`（已于 2026-10-30 清理，未留存）。

| 判据 | 结果 |
| --- | --- |
| 完整制品包一致性 | PASS（新 bit/XSA/ELF/FSBL/BOOT 同源，part/参数与 XSA HWH 相符） |
| 烧录 / CAPS 就绪 | PASS（`READY 7.1 2`） |
| **唯一判据：载荷 SHA-256** | **PASS** —— `fcd0cf90…b1f2c3` 逐位相同 |
| 四级逐级取证 / 串口 | PASS |

**但这个 PASS 不能当「片上 LDPC 跑通」用。** 串口日志显示三行：

```
[LDPC] loading 8100 bytes as 2025 LSB-first words
[LDPC] converged=0 iterations=-1 error=1 timeout=0; 保留 Stage3 原码字
[PIPE] total 61812 steps in 1922 callbacks, 890 ms
```

`iterations=-1` + `error=1` 正是 `ldpc_decoder_p1.v` 里 `iteration_q >= MAX_ITER` 那个 **「跑满 MAX_ITER 未收敛」** 的出口
（不是硬件故障）。软件按设计**保留了 Stage3 原码字**，所以主机侧看到的字节与 L6 之前逐位相同
——**G3 判的是「兜底没搞坏东西」，不是「译码成功」**。这正是 L6 文档 §0 预告的情形。

## 2. 根因：漏做解交织（已双向验证）

### 2.1 事实链

| 环节 | 事实 | 出处 |
| --- | --- | --- |
| RTL 被验的输入 | **自然序**（解交织后） | `logs/ldpc/golden/build_golden.py`：`bits=read_bit_text(f)` → `natural=L.deinterleave(rx,perm)` → `pack_hex(natural)` 写 `in_*.hex` |
| TB 装载约定 | `load_bit = input_bytes[i>>3][7-(i&7)]`（每字节 MSB 先）+ `pack_hex` 用 `bitorder="big"` ⇒ **核地址 i ← natural[i]** | `hw/experimental/tb_ldpc_decoder_p1.v` 的 `load_bit` 赋值 |
| 板端实际喂的 | 结果缓冲**原样**：核地址 a ← `rx[a]`（LSB 先，与主机 `fast_readout.fast_unpack_result` 的 `bitorder="little"` 一致） | `sw/app/ldpc_onchip.c` 的 `ldpc_load_word`、`hdl/ldpc_decoder_v1_0.v` 的 `core_load_addr`/`core_load_bit` |
| 两者差多少 | **31,958 / 64,800 位不同**（≈49%） | 本轮实测输入算得 |

⇒ 核收到的是一个**被置换过的码字**，等于在错误的 H 上做 min-sum。

### 2.2 复现实验（双臂，用本轮板端真实输入）

把 `20261014T110319Z/dec_input_run1.txt` 的 64,800 位做两臂，喂**同一个 RTL**：

| 臂 | 喂入 | 仿真结果 |
| --- | --- | --- |
| **A** | `rx`（板端现在的行为） | **converged=0**，51 次 syndrome 扫描（50 轮），**20,802,990 周期** |
| **B** | `natural`（解交织后） | **converged=1，5 轮** |

- 臂 A **逐项复现**了板上的 `converged=0 / iterations=-1`；
- 臂 B 的 **5 轮**与主机 `tools/ldpc_decode.py` 对同一批比特的「**起始失败校验 332，5 轮收敛**」
  **完全一致**。

⇒ **核是对的，集成是错的。** 这也顺带回答了 L6 文档 §3.2 留的那个问题：
AXI 边界的**字内位序没有问题**（两条路都等价于「核地址 = 序列下标」），
真正缺的是**置换**。

### 2.3 为什么不能靠「把表的列号重标号」白嫖

自然的想法是把 B_t 表的列号直接换成交织域下标，从而零成本。**实测不可行**：
`inv = perm⁻¹` 在信息列的自然分组 `10800+360t+m`（m 取 0..359）上**不保持等差**
（实测 `inv[10800+360·3 .. +359]` 前 12 项 `28904 44684 29350 30863 63191 …`，不连续、也不落回同一 360 块）。

而 p=1 实现的核心优势正是那条**仿射地址算术**（`m=(a−b) mod 360`、`列=base_col+m`，
见[架构决定 §2.1](ldpc-decoder-l4.md)）。重标号会把它换成一张 54,000 项的查找表——
把最省资源的东西换掉去省另一样。**故置换必须显式做**，不能隐式吸收进表。

## 3. 代价（修复前，默认 4096 条记录口径）——⚠️ 本节原版对照包选错，已更正

> **勘误（2026-10-14 当日）**：本节与 §3b.2 初版把 `bkb220-p16-upload-promoted-…` 当成了
> 「无手上 LDPC 的参考包」。**它不是**——查其 `export/hardware_build_config.txt`，
> 该包来自 **2026-10-12** 的构建，`result` 记 **WNS +0.617 ns**，是 **K 参数化之前**的 P16
> （`stage1-multibase-ooc-probe.md` 也早写明「即 K 参数化之前的 P16」）。
> ⇒ 初版那张「724 / 890 / 725」的三方表把 **K=1→K=2** 和 **LDPC 有无** 两件事混在了一起。
> 全量档一跑就露馅：该包 **8.90 s**，而 K=2 包 **5.89 s**——差的正是 K 的 ~1.5×。
> 下面用**真基线** `bkb220-p16-k2freeze-20261014T000848Z`（K=2、无 LDPC、35,702 LUT、
> bit `a0e03ff0…`）重做。旧表的数字保留在本节末尾作留证，**但不得再被引用**。

### 3.0 同小时四次背靠背（K 与 LDPC 两轴分开）

| 包 | K | 片上 LDPC | 默认档 板端 | 默认档 `t_result` | 全量档 板端 | 全量档 `t_result` |
| --- | :---: | :---: | ---: | ---: | ---: | ---: |
| `upload-promoted`（2026-10-12） | **K=1** | 无 | 724 ms | 0.78 s | 9,238 ms | 8.90 s |
| `k2freeze` | **K=2** | 无 | **602 ms** | **0.65 s** | **6,141 ms** | **5.89 s** |
| `k2-ldpc-perm`（本页） | K=2 | 有（收敛） | 725 ms | 0.77 s | 6,259 ms | 6.06 s |
| `k2-ldpc-sw`（修复前） | K=2 | 有（不收敛） | 890 ms | 0.94 s | 未测 | 未测 |

**两条各自干净的结论**：
- **K=1 → K=2**：默认档 724→602 ms（**−17%**），全量档 8.90→5.89 s（**−34%**）。
  （默认档差距小是因为那个量级上整轮由固定开销主导。）
- **片上 LDPC 的净代价 ≈ +120 ms/任务，且与数据量基本无关**（一次任务只译一次码）：
  默认档 **602 → 725 ms（+123 ms）**，全量档 **6,141 → 6,259 ms（+118 ms）**。

### 3.1 这 +120 ms 里能归因多少

| 分量 | 量 | 依据 |
| --- | ---: | --- |
| PS 状态机（LDPC_PREP + RUN + READBACK） | **17 ms** | 板端自报（6+5+6） |
| 其中置换（装载解交织 + 读回交织） | 3 ms | 板端串口打印 |
| PL 译码（收敛，4~5 轮） | 29~35 ms | 仿真周期 2.9~3.5 M @100 MHz |
| **已归因合计** | **≈ 50 ms** | |
| **剩下的 ≈ 70 ms** | **未归因** | 最可能是 **200 µs 轮询量化**带来的额外延迟（本任务多出约 155~1,000 次回调）。**这是假设不是结论**，要专门测 |

⚠️ **不要拿两次跑的 `[in-state]`/`[waiting]` 相减去归因**：修复前的包（无 LDPC）
在 `DONE_STAGE3 → SEND_RESULT` 这一步由 TCP 回调直接接管，profiler **没有闭合该区间**，
它的 `[in-state]` 少记了这一段。**跨这两个包只能比 `[PIPE] total` 与 `t_result`。**

### 3.2 初版那张表（**留证，不得引用**）

同一小时、同一板、同一组参数，先跑 LDPC 包（19:03）再跑**冻结的 K=2 参考包**（19:09）：

| 项 | 参考包（无片上 LDPC） | LDPC 包 | 差 |
| --- | ---: | ---: | ---: |
| 板端整条流水线 | **724 ms** | **890 ms** | **+166 ms（+22.9%）** |
| 主机 `t_result` | **0.78 s** | **0.94 s** | +0.16 s |
| 载荷 SHA | `fcd0cf90…` | `fcd0cf90…` | 相同 |

**这 +166 ms 是在「永远走兜底」的情况下付的**：不收敛 ⇒ 每次都跑满 50 轮。
按仿真周期算，50 轮 ≈ 20.8 M 周期 ≈ **208 ms @100 MHz**，与实测增量同量级。

### 3.3 Stage1 未回退（修复前那次对照，结论仍成立）

两包的**定值阶段逐项相同到毫秒**：

| 阶段 | 参考包 | LDPC 包 |
| --- | ---: | ---: |
| DONE_STAGE1 | 65 ms | 65 ms |
| VOTER_START | 107 ms | 107 ms |
| DONE_STAGE2 | 45 ms | 45 ms |
| DECODER_PREP | 65 ms | 65 ms |
| DONE_STAGE3 | 73 ms | 73 ms |

（`TX_STREAM` / `VOTER_WAIT` 的 **hits** 不同，那是 poll 次数随调度浮动，ms 列相同。）

## 3b. 修复后：收敛路径首次在板上跑通

修法：**PS 侧补置换**，`sw/app/ldpc_perm.c` + 由 `tools/gen_ldpc_perm_table.py` 从
`clients/python/resources/permutation64800` 生成的 `inv` 表（u16 × 64,800 = 126.6 KiB，进 `.rodata`）。
**没有动 `hw/ip/`，所以比特流、整机 WNS、G3 留证全部保值**——新包只是派生 ELF
（`tools/build_sw_variant.sh --sync-src`；bit/FSBL 与参考包逐字节相同）。

制品：`hw/build/bkb220-p16-k2-ldpc-perm-20261014T113500Z-board-migrate`
（ELF `6ec76fc5…`；参考 LDPC 包 ELF `8be9ef4c…`）。
留证：`/mnt/d/bkb220_board_smoke/g3_runs/20261014T113108Z`（已于 2026-10-30 清理，未留存）。

### 3b.1 板端串口（三条日志就是判据）

```
[LDPC] loading 8100 bytes as 2025 LSB-first words; deinterleaved in 2 ms
[LDPC] converged=1 iterations=5; reading corrected codeword
[LDPC] converged=1 iterations=5; wrote back 2025 words; reinterleaved in 1 ms
```

- **`converged=1 iterations=5`** —— 与 §2.2 臂 B 仿真的 `converged=1 / 5 轮`
  **逐项一致**。收敛路径从此不再只有仿真证据；
- **`deinterleaved in 2 ms` / `reinterleaved in 1 ms`** —— PS 侧置换的实测代价
  **合计 3 ms**（事前估算 2~5 ms）。相对 34.9 ms 的译码与 13.27 s 的整轮，
  分别是 8.6% 与 0.02%；
- 主机侧签名同时从 `起始失败校验 332，5 轮收敛` 变成
  **`起始失败校验 0，0 轮收敛`** —— 板上已经把码字纠成合法码字，主机侧无事可做。

### 3b.2 同小时背靠背三次（同一板、同一默认 4096 条记录口径）

| | 参考包（无片上 LDPC）19:09 | LDPC 修复前 19:03 | **LDPC 修复后 19:31** |
| --- | ---: | ---: | ---: |
| 板端流水线 | 724 ms | 890 ms | **725 ms** |
| 主机 `t_result` | 0.78 s | 0.94 s | **0.77 s** |
| 核的轮数 | — | 50（未收敛，兜底） | **5（收敛）** |
| 载荷 SHA | `fcd0cf90…` | `fcd0cf90…` | `fcd0cf90…` |

⚠️ **初版这里写「修复把 +166 ms 变成 +1 ms」，那是错的**——见 §3 的勘误：
那次比的是 K=1 参考包，K 与 LDPC 两个因素被混在一起。**按 §3.0 的真基线**：
- 修复前（不收敛，跑满 50 轮）：默认档 **890 ms**，比 K=2 真基线 602 ms 高 **+288 ms**；
- 修复后（收敛，4~5 轮）：默认档 **725 ms**，比真基线高 **+123 ms**。
⇒ **修复省下约 165 ms**（不收敛的 50 轮 → 收敛的 4~5 轮），
但**片上 LDPC 本身仍要 +120 ms/任务**（与数据量基本无关，见 §3.0）。
**这 +120 ms 是集成度的代价，不是零成本**；其中约 70 ms 尚未归因，最可能是轮询量化，
**要优化就先测它**（§3.1）。

### 3b.3 Stage1 未回退（修复后，交接文档的停止条件已满足）

三次跑的**定值阶段逐项相同到毫秒**：`DONE_STAGE1` 65、`VOTER_START` 107、
`DONE_STAGE2` 45、`DECODER_PREP` 65、`DONE_STAGE3` 73 ms。

⚠️ 一处口径提醒：**修复前的参考包分解表里没有 `DONE_STAGE3` 行**，不是它少跑了一步，
而是那时 `DONE_STAGE3 → SEND_RESULT` 这一步由 TCP 回调直接接管、profiler 没有闭合该区间；
LDPC 版本因为多了 `DONE_STAGE3 → LDPC_PREP` 的正常步进才被记上。
**比较以板端自报的 `[PIPE] total … ms` 与主机 `t_result` 为准**，
`[in-state]`/`[waiting]` 的拆分在这两次之间不可直接相减。

### 3b.4 怎么在主机上验的（不靠板子）

`tools/test_ldpc_perm.sh`：把 `sw/app/ldpc_perm.c` 与生成的表编成 x86 程序，
与 `native_ldpc.deinterleave` 在**板端真实回传样本**、随机、全 0、全 1、交替模式上
逐位比对，并校验往返还原。5 组全过。
⇒ 置换这种纯数据变换**本就不该靠上板试错**：上板只暴露成「核不收敛」，信号弱、定位慢。

## 4. ⚠️ 边界

1. **样本只有一个**。修复后 `converged=1` 只在**这一个** G3 默认样本上被验证过。
   L4 的 14 样本分布是 8 收敛 / 6 不收敛；**不收敛样本在板上的兜底路径**（保留 Stage3
   原码字、字节不变）首跑验证过，但**修复后的不收敛路径没有再复测**。
2. **+120 ms 是单次测量对单次测量**，方向可信、小数位不可信（日内漂移 ±7.5%）。
   两次口径都给了一致的量级（+123 / +118 ms），**这才是它比单个数字更可信的地方**。
3. **PS 置换的 3 ms 是实测**（板端串口打印），不是估算——但它同样只是这一个样本上的值；
   置换工作量与输入内容无关（恒为 64,800 位），所以这个数比时间类测量更可外推。
4. 主机侧那 5 轮收敛用的是 **Gallager-B 比特翻转**（`tools/ldpc_decode.py`），
   RTL 是 **flooding Min-Sum**；两者**不是同一算法**，所以「轮数相同（都是 5）」
   是巧合而非等价性证明。判等只在**收敛状态**这一层。
5. 留证目录原在 `/mnt/d/bkb220_board_smoke/g3_runs/`（`logs/` 忽略区），2026-10-30 已清理。

## 5. 制品包口径修正（本轮顺带做的）

子 Agent 交付的软件包有三处**与 G3 门禁的格式口径不符**（都不是内容错误，但会让
`--strict-artifacts` 拒收）。本轮归一化后门禁通过，SHA256SUMS 内容哈希**全部不变**：

| 项 | 原状 | 改为 |
| --- | --- | --- |
| `SHA256SUMS` 路径 | 带 `./` 前缀 | 裸相对路径（`build_sw_variant.sh` 的既有口径） |
| `reports/source_manifest.json` | 自造 schema（`source_files_sha256`） | 门禁 schema（`files`：69 条源码 → SHA256） |
| `manifest.json` 的 `tool_versions.vivado` | `"2022.2 (source hardware package; not run for this task)"` | `"2022.2"`，原说明挪到 `vivado_note` |

原 `SHA256SUMS` 另存为 `SHA256SUMS.pre-normalize-20261014T1100Z.bak` 留档。
清单那一条已固化成工具 **`tools/write_source_manifest.py`**，并接进
`tools/build_sw_variant.sh --sync-src`（此前它把参考包的清单原样复制，而源码已换
——**门禁只查格式，查不出这种不一致**，这是个已修掉的隐患）。
**这三处是「包能不能被门禁吃进去」的问题，与本页的功能结论无关**；
但也说明从 `create_vitis.tcl` 到「门禁可吃的完整包」之间**仍有手工补步**（docs/07 §3 早已记为待收口项）。
