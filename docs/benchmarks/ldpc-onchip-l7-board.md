# 片上 LDPC：L7 上板（2026-10-14）

**结论一句话：G3 PASS，但走的是兜底路径——片上译码器这一版在板上从不真正纠错。
根因已定位并双向验证：L6 集成漏做了解交织。**

## 1. 板端结果

制品：`hw/build/bkb220-p16-k2-ldpc-sw-20261014T104331Z-board-migrate`（bit `8f0da7bf…`，
与无 LDPC 的参考包 bit `123c02b3…` 不同）。留证 `/mnt/d/bkb220_board_smoke/g3_runs/20261014T110319Z`。

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

## 3. 代价：同小时背靠背 A/B（默认 4096 条记录口径）

同一小时、同一板、同一组参数，先跑 LDPC 包（19:03）再跑**冻结的 K=2 参考包**（19:09）：

| 项 | 参考包（无片上 LDPC） | LDPC 包 | 差 |
| --- | ---: | ---: | ---: |
| 板端整条流水线 | **724 ms** | **890 ms** | **+166 ms（+22.9%）** |
| 主机 `t_result` | **0.78 s** | **0.94 s** | +0.16 s |
| 载荷 SHA | `fcd0cf90…` | `fcd0cf90…` | 相同 |

**这 +166 ms 是在「永远走兜底」的情况下付的**：不收敛 ⇒ 每次都跑满 50 轮。
按仿真周期算，50 轮 ≈ 20.8 M 周期 ≈ **208 ms @100 MHz**，与实测增量同量级。

### 3.1 Stage1 未回退（交接文档的停止条件）

两包的**定值阶段逐项相同到毫秒**：

| 阶段 | 参考包 | LDPC 包 |
| --- | ---: | ---: |
| DONE_STAGE1 | 65 ms | 65 ms |
| VOTER_START | 107 ms | 107 ms |
| DONE_STAGE2 | 45 ms | 45 ms |
| DECODER_PREP | 65 ms | 65 ms |
| DONE_STAGE3 | 73 ms | 73 ms |

（`TX_STREAM` / `VOTER_WAIT` 的 **hits** 不同，那是 poll 次数随调度浮动，ms 列相同。）

## 4. ⚠️ 边界

1. **这一版片上 LDPC 在板上是「纯兜底」**：没有一次真正纠错，因此
   **「收敛路径」在板端一次都没被验证过**（收敛时的读回、写回位序、与主机结果一致，
   全部只有仿真证据）。
2. 上述 **+166 ms 不可外推到修好之后**：修好后收敛样本只跑 4~5 轮（≈2 M 周期 ≈20 ms），
   代价会小一个量级——但**这是预测不是实测**。
3. 本轮只跑了**一个样本**（默认 G3 口径）。L4 的 14 样本分布（8 收敛 / 6 不收敛）本轮的
   分布未知。
4. 主机侧那 5 轮收敛用的是 **Gallager-B 比特翻转**（`tools/ldpc_decode.py`），
   RTL 是 **flooding Min-Sum**；两者**不是同一算法**，所以「轮数相同（都是 5）」
   是巧合而非等价性证明。判等只在**收敛状态**这一层。
5. 留证目录在 `/mnt/d/bkb220_board_smoke/g3_runs/`（`logs/` 忽略区）。

## 5. 制品包口径修正（本轮顺带做的）

子 Agent 交付的软件包有三处**与 G3 门禁的格式口径不符**（都不是内容错误，但会让
`--strict-artifacts` 拒收）。本轮归一化后门禁通过，SHA256SUMS 内容哈希**全部不变**：

| 项 | 原状 | 改为 |
| --- | --- | --- |
| `SHA256SUMS` 路径 | 带 `./` 前缀 | 裸相对路径（`build_sw_variant.sh` 的既有口径） |
| `reports/source_manifest.json` | 自造 schema（`source_files_sha256`） | 门禁 schema（`files`：69 条源码 → SHA256） |
| `manifest.json` 的 `tool_versions.vivado` | `"2022.2 (source hardware package; not run for this task)"` | `"2022.2"`，原说明挪到 `vivado_note` |

原 `SHA256SUMS` 另存为 `SHA256SUMS.pre-normalize-20261014T1100Z.bak` 留档。
**这三处是「包能不能被门禁吃进去」的问题，与本页的功能结论无关**；
但也说明从 `create_vitis.tcl` 到「门禁可吃的完整包」之间**仍有手工补步**（docs/07 §3 早已记为待收口项）。
