# 证据台账（Evidence Ledger）

> 2026-10-10：本台账保留历史结论及其适用范围，当前事实见03；原16中断审计全文在[合并归档](archive/history/2026/pre-bkb220-handoff-2026-10-10/interrupted-work-audit-2026-09-06.md)。原16的dump/哈希/复核命令仍随全文保留，不能把历史板结果当新板。

> **本文不叙述、不解释、不推销**，只做一件事：把每一条**可以对外说的话**
> 与它的**判据、证据路径、复现命令、边界**钉在一起。
>
> **编号约定**：现用文档一律带序号（本文为 `09`），归档文档一律**不带**序号
> （见 `docs/archive/history/2026/`）。这样从文件名就能看出一份文档是否还有效，
> 也不必再为「历史文档占了号」而跳号。
>
> **维护规则**
> 1. 结论变了就**改对应行**，不要新写一份叙述；失效的行标 ~~删除线~~ 并注明原因，不要删。
> 2. 每行必须能回答：**这句话凭什么？换台机器怎么重跑？它在什么范围内成立？**
> 3. 没有「证据路径」的行不许存在。没实测的东西写进 [08](08-performance-and-strategy.md)
>    的候选池，不写这里。
> 4. 最终状态以 [03](03-status.md) 为准；本文是它的**可复现索引**。

---

## 1. 正确性

| # | 可以说的话 | 判据 | 证据 | 复现 |
|---|---|---|---|---|
| C1 | SE150 真实测序数据端到端恢复原始图像，逐位一致 | 图片 SHA-256 `fcd0cf90…f2c3` | `g3_runs/20260910T*` 多轮 | `tools/run_g3.sh --limit 2048` |
| C2 | 四级中间结果逐字节吻合，不只是最终哈希对 | Stage1/Stage2⊕水印/Stage3 分别对黄金向量 | 同上，`board_stage_check.py` | 同上（脚本第 7/7 步） |
| C3 | 4-Way 与 2-Way 在生产几何下与**独立黄金模型**逐条一致 | 分数严格相等 + 位置属同分并列最大集，64/64 | `logs/iverilog/run_20260909_005333_*` | 见 `docs/benchmarks/stage1_4way_ip_integration.md` §6.3 |

> **C3 的坑**：`tests/golden/stage1_fwd_expect.txt` 里的位置在同分并列时由 FFT
> 浮点噪声决定（read 4 三个并列位置浮点值 `59.0 / 59.000000000000014 / 59.0`），
> **不能按单值比相等**，否则会把正确的 RTL 判成失败。并列集由
> `tools/make_stage1_tie_golden.py` 用整数精确滑窗生成。
>
> **G3 压测日志结构化**：多轮连续运行留证由 `tools/board/g3_runs_to_jsonl.py` 提取为逐轮机器可读的 JSONL（`tests/stress_results/*/continuous.jsonl`）。

---

## 2. 泛化与可重复

| # | 可以说的话 | 判据 | 证据 | 复现 |
|---|---|---|---|---|
| G1 | 6 类异构 payload 板端 100% 逐位恢复 | 各自独立源文件的 SHA-256 | `docs/benchmarks/measured_board_multi_payload.md` §3 | `tools/run_multi_payload_regression.py --mode check-dumps --extended` |
| G2 | **21 次板端运行，结果逐位可重复，零抖动** | 每数据集 3 次原始误码数完全相同 | `logs/multi_payload/repeat3_20260910T200339Z/` | `... --mode board --extended --repeat 3` |
| G3 | 高熵失败是**确定性算法边界**，非随机故障 | @60 稳定 0/3 失败、@65 稳定 3/3 通过 | 同 G2 | 同 G2 |
| G4 | **误接受率有定义且已测**：`score_min=67` 时干净数据 FAR **0.44%**、FRR 0% | 逐记录判真/诱饵/错位，FAR = 垃圾票占被接受记录的比例 | `docs/benchmarks/measured_g5_false_accept.md`、`logs/g5_matrix/run1/` | `python3 tools/g5_false_accept.py --dataset tests/datasets/D1_text_manifesto --limit 2048` |
| G5 | **替换错误不影响误接受率，插删才是主因** | sub 0→4% 时 FAR@67 恒 ~0.5%；ins=del 0.1% 时升到 8.9%，且成因由「诱饵」变为「真错位」 | 同上，7 个噪声点 × 3 种子 | `bash tools/run_g5_matrix.sh` |
| G6 | **阈值法在纯替换下的边界是 sub ≈ 4%** | 真记录最低分与诱饵最高分的间隔在 4% 处归零（+4.0 → ±0.0） | 同上 §3.1 | 同上 |

**G2 的具体数字**（这是比「6/7 通过」更强的证据）：

```text
D0 42/42/42   D1文本 16/16/16   D1几何 7/7/7   D1稀疏 09/09/09
D1高熵@60 2671/2671/2671   D1高熵@65 236/236/236   D2 20/20/20
```

**边界**：3 次重复只支撑「该制品、该输入下确定性可重复」，
**不能**外推为任意输入的可靠率；板端回传真实，但 LDPC 译码与哈希比对在主机侧。

---

## 3. 性能（口径最容易走样，逐条钉死）

| # | 可以说的话 | 数据 | 证据 |
|---|---|---|---|
| P1 | 板端耗时模型（当前固件，P13） | `T = 0.480 s + 0.2451 ms × N_records`，R²=0.9996；全量 SE150 中位 **25.69 s = 2,016 reads/s** | `docs/03` P13，`g3_runs/20260922T11*`、`20260922T12*`，18 点 |
| P1a | 每记录成本≈Stage1 PL 理论周期 | 实测斜率 0.2451 vs 4-way 理论 0.2436 ms/记录（差 0.6%）；去掉运行期休眠 `[PIPE] total` 逐毫秒不变 | `docs/03` P13 |
| P1c | **PL 比同片 ARM 快约 49x** | 单核 Cortex-A9（-O3 NEON）12.10 ms/记录 vs PL 0.2451 ms/记录；ARM 结果与主机参考 1,024/1,024 逐条一致 | `docs/benchmarks/measured_arm_baseline.md`，`arm_baseline/20260922T152202Z-n1024` |
| P1b | 较早的 P0 修复后模型（已被 P12/P13 取代） | `T = 1.505 s + 0.5656 ms × N_records`，R²=0.986 | `logs/overhead_sweep/`，7 档 × 3 次 |
| P2 | 修复前模型 | `T = 5.284 s + 0.5157 ms × N_records`，R²=0.996 | `logs/overhead_sweep/20260910T075540Z/` |
| P3 | 板端固定开销压缩 **3.5x** | 5.284 s → 1.505 s | 同上两行对比 |
| P4 | 演示规模端到端提速 **1.8x** | 2,048 源读段 7.315 s → 4.123 s | 同上 |
| P5 | 4-Way 顶层加速比（生产几何仿真） | 3,229,621 → 1,674,217 周期 = **1.929x** | `logs/iverilog/run_20260909_005333_*` |
| P6 | 4-Way 整机时序收敛 | WNS **+0.246 ns** @100 MHz，失败端点 0 | `logs/vivado/recovery_20260909/physopt/` |
| P7 | 独立硬件周期实测拆解非 Stage1 耗时 | 4096 记录下 Voter 29.627 ms (0.93%)、Decoder 0.022 ms (0.0007%)，总 PL 硬件执行不足 30 ms；非 Stage1 耗时 62.9% 的 99% 以上是 PS 侧 lwIP poll 空等 (2,777 ms) 与 Cache 维护 (396 ms) | `docs/benchmarks/measured_p7_cycle_counters.md`、`g3_runs/20260911T140559Z/` |

### ⛔ 不能说的话（每条都有实测支撑其为假）

| 说法 | 为什么不能说 |
|---|---|
| 「比 CPU 快 / 加速 N 倍」（不加限定） | 全量 SE150 **板端实测 2,016 reads/s**（P13）：只比**单核** C 快 1.48x，比 16 线程**慢 6.9x**。只能说「快于单核」且须同时给出多核对照。（旧的 0.77x、1,055 reads/s 是 P12 之前的外推，已作废） |
| 「优化 Voter / Decoder 硬件流水线能显著提升端到端性能」 | **板端硬件周期实测证伪**：4,096 条记录下 Voter 执行仅 29.6 ms (0.93%)，Decoder 仅 0.02 ms (0.0007%)，就算两核执行时间降为 0，端到端提速也不足 1%。瓶颈 99% 在 PS 侧 lwIP poll 空等与 Cache 维护，硬件并行化方向已彻底关闭 |
| 「固定开销优化提升了吞吐」 | 只对小规模成立。全量占比仅 9%，修复后全量 58.7 s → 60.1 s **略差** |
| 「纯硬件三级流水线」 | **Stage 2.5 跑在 ARM 上**（`apply_watermark_differential()`），见 `docs/01` |
| 「低功耗 / 能效优势」 | **功耗一个数字都没测**，无功率计 |
| 「误接受率低说明系统鲁棒」/「FAR 就是失败率」 | FAR 衡量的是**累加器污染程度**，不是任务成败：`D2_controlled_noise` 在板端 `score_min=65` 下 FAR **21.76%**，却 **3/3 逐位恢复** |
| 「score_min=67 是最优阈值」 | 67 = `int(0.45×150)`，是设计时选的比例**不是测出来的**。纯替换场景实测 τ=70 才给 FAR=0%；但插删场景抬阈值换不来干净 |
| 「8-way 还没做」 | 是**做不了**：4-way 已占 LUT 88.0%，8-way 外推 ~125% |
| 「WNS +2.197 ns 说明整机时序好」 | 那是**单模块 OOC**；同一设计整机默认策略下是 **−0.252 ns 不收敛** |

---

## 4. 工程与可复现

| # | 可以说的话 | 判据 | 证据 |
|---|---|---|---|
| E1 | 制品与源码**可证同源** | 符号级比对 + 分段比对 | `docs/archive/history/2026/pre-bkb220-handoff-2026-10-10/status.md` P0b（历史符号/分段同源复核） |
| E2 | 时序收敛可复现，非偶然 | impl 策略已固化进 `hw/scripts/build.tcl` | commit `1e4e746` |
| E3 | 异常连接可恢复 | 断网/半截包头/坏 magic/RST 注入后恢复恒 2.02 s | `tests/stress_results/g6_postfault_*/` |
| E4 | 判据有鉴别力，不是只会报 PASS | 故障注入会红；`wm_regions.hex` 几何哨兵 | `tools/make_golden.py` 内置哨兵 |
| E5 | 演示不依赖预生成结果 | 四幕现场出哈希，含一幕**预期红灯** | `tools/run_demo.sh`，2026-09-10 实跑 |

> **E1 的方法学（重要）**：**整文件 SHA-256 发现不了制品与源码不同源。**
> 2026-09-10 实测：出厂 `SHA256SUMS` 当时完全自洽，但那份 ELF **不含**源码里
> 已有的 B29/B30 修复（`arp_keepalive` 在 ELF 中出现 **0 次**）。
> 整文件哈希只证明「文件没被改动」，**不证明「文件由该源码构建」**。
> 有鉴别力的判据是：
> ```bash
> arm-none-eabi-nm <elf> | grep <源码里新增的函数名>      # 符号级
> arm-none-eabi-objcopy -O binary --only-section=.text ... # 分段比对
> ```

---

## 5. 已知失败与负结果（**必须保留，不得从统计里消失**）

| # | 失败项 | 现象 | 判定 | 证据 |
|---|---|---|---|---|
| F1 | 高熵 payload @ 出厂门限 60 | 原始误码 2,671 bit，LDPC 50 轮未收敛 | **已知边界**，稳定 0/3 复现；@65 可恢复 | `logs/multi_payload/repeat3_*/` |
| F2 | 8-way / 128×4 展开 | LUT 外推 ~125% | **资源证伪**，不再排期 | [08性能策略的旧分析边界](08-performance-and-strategy.md#2-旧分析的适用边界)，原7010资源报告在合并归档competition-strategy.md中 |
| F3 | 流式阶段批量推进（两次尝试） | `submitted=640 > ring free=512`，Stage1 挂死 ~30 s | **放弃**：剩余收益上限仅 1.11x | `g3_runs/20260910T113222Z`、`115133Z` 的 `uart.log` |

> **F3 的教训**：原设计「一帧一个 poll」不只是浪费，**它同时是 BD 环的节流机制**。
> 两次失败都用错了控制变量（第二次用 RX ring 余量，但 `ring free` 恒为 512，
> 门限从未触发）。正确的控制变量是**在飞帧数**或 DMA 完成中断。

---

## 6. 本轮（2026-09-10）新增的过程教训

这些不是结论，是**方法层面的坑**，写下来避免重复踩：

1. **留证通道断了 = 没有留证。** 固件早就打印了 `[PIPE] total %u poll steps`，
   注释还写着「下一个人就不必再靠分档拟合去反推常数项」——但 UART 没接，
   **这行字从未被读到**，于是同一个根因被用分档拟合重查了一遍。
   串口不通时应改用 XSDB 读内存符号（`tools/board/read_pipe_counters.tcl`）。
2. **不要在被测对象上做「顺手探测」。** 板端 lwIP 是单例 `g_conn`，
   一次 TCP 探测直接把正在进行的 G3 弄成 FAIL，浪费一轮板测。
3. **先确认工具语义再用。** `--no-post` 是「不发送 POST 触发命令」（板子根本不算），
   不是「不做 LDPC 译码」，导致首轮扫描全部作废。
4. **`pgrep -f` 会匹配到自己的命令串。** 等待循环因此永远不退出，
   误判「板卡忙」多轮。用 `ps -eo cmd | grep -v` 之类不自匹配的写法。
5. **代码里的警告要当警告读。** `stage1_dna.c` 的 `PIPE_WM_TX` 分支写着「原实现靠下一个 poll
   才回收，天然有 250 ms 余量」——这句话同时解释了开销**和**节流机制，
   只读出前半句就会拆掉后半句（F3）。

## 7. 2026-10-10 迁移准备证据

| 可以说的话 | 判据/原始证据 | 边界 |
|---|---|---|
| 正式LC50 P4/P16模块与真实包装通过 | [集成摘要](benchmarks/stage1-16way-ip-integration.md)；D:/Agent/outputs/bkb220-xsim26/run-20261010-a4两个case及14文件SHA；Icarus模块同周期 | 无新板route/G3；约3.27倍仅模块cycle |
| 47项主机门禁通过 | [主机摘要](benchmarks/bkb220-host-verification.md)；logs/host/g3-preflight-20261010/all_host_tests.txt | fixture/替身，不是板测 |
| 现代软件入口实际完整构建核验 | [工具摘要](benchmarks/bkb220-toolchain-audit.md)；D:/Agent/outputs/bkb220-vitis26/logs-a14/vitis.log与export-a14/software_build_config.json | 旧ECO XSA兼容探针，不是新板包 |
| 正式源/参数与实际catalog包装通过 | [集成摘要](benchmarks/stage1-16way-ip-integration.md)；logs/vivado/stage1_ip_catalog_20261010_2110 | 默认P4，BKB220 ready=0 |

Icarus重复接口已在XSim正式通过后停止，不称Icarus接口PASS。起点重复附件告警及唯一源引用修复记录保留，边界见[整理记录](reference/workspace-cleanup-2026-10-10.md)。全项目门禁与当前Agent任务见05/07。

2026-10-11 Agent承载通道补充：logs/agents/handoff-channel-20261011-a2/result.json、events.jsonl及final.md证明现有代理下gpt-5.6-luna/max的只读调用退出0、turn.completed与JSON哨兵通过；这是Agent运行环境证据，不是FPGA功能、时序或真板验收证据。用户目标gpt-6-luna 已由 2026-10-11 00:40 codex-luna MCP 的冒烟与真实派发实测可用（11.7s / 34.0s，均 completed/ok/exit0/turn_completed，更正提交25c3336）；b3c70b3 依据的旧 CLI 0.147.0 拒绝是客户端版本问题，不是账号权限。
