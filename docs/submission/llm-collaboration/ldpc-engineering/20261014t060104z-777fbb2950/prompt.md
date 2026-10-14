> 脱敏副本，原件 `20261014T060104Z-777fbb2950/{prompt.txt,answer.md}`。本机绝对路径、邮箱、凭据形模式及非白名单私网 IP 已替换；除脱敏与换行规范化外保留原文。

任务（workspace-write，看板名 **ldpc-rtl-l4**）：实现 DVB-S2 R=5/6 LDPC 硬判决 flooding Min-Sum 译码器的 **RTL 原型**，并用仿真对**黄金集逐位验证**。

## 先读（务必回原文，不要只信我下面的转述）
- `clients/python/native_ldpc.py` 的 `hard_decode`（**第 59–118 行，这是唯一要复刻的语义**）与 `load_pchk`
- `docs/reference/ldpc-architecture-decision-2026-10-14.md`（架构：p=1 边串行）
- `hw/experimental/ldpc_row_engine_probe.v`（上一轮 OOC 探针，可参考其 BRAM 推断写法）
- `docs/benchmarks/ldpc-row-engine-ooc-probe.md`（该探针的结论与边界）

## 要交付
1. **`hw/experimental/ldpc_decoder_p1.v`** —— 译码器原型（**正确性优先，速度与面积先不管**）
2. **`hw/experimental/tb_ldpc_decoder_p1.v`** —— testbench
3. 更新 `hw/experimental/README.md` 的「当前内容」表，为新增文件各加一行（**表内描述不要用反引号**，门禁的表解析器会把反引号里的词当成文件名）

## 必须逐位复刻的语义（`hard_decode`）

```
llr0[c] = +3.0 if natural[c]==1 else -3.0         # Q1 定点下 → +6 / -6
llr = llr0
decoded = natural; if syndrome(decoded)==0: 返回 (decoded, 0 轮)     # 先做一次初始校验
for it in 1..50:
    for 每个校验行 r:
        magnitudes = |llr|(该行各列)   # 无效槽填 big
        signs      = sign(llr)(该行各列)   # 无效槽填 +1
        row_signs  = Π signs
        min1,min2  = 该行幅值的最小、次小
        first      = 该行幅值 == min1 的**第一个**（按槽序）
        每条边的消息 = row_signs * sign(该边) * (first ? min2 : min1)
    llr = llr0 + 按列求和(所有消息)      # 逐列累加
    decoded = (llr > 0)
    if syndrome(decoded)==0: 返回 (decoded, it 轮)
未收敛 → 报错
```

**四个必须小心的点（写错就会与黄金不符）**：
1. **`np.sign(0.0) == 0`**：某行只要有**任一 LLR 恰为 0**，`row_signs` 就是 0 ⇒ **该行所有消息全为 0**。RTL 里要显式检测"该行有零"，命中时整行跳过累加。**不要**把它当成 ±1 处理。
2. **min1 并列取"第一个"**：不是任意一个。RTL 要维护"最小幅值首次出现的槽序号"。
3. **`decoded = (llr > 0)` 是严格大于**，`llr==0` 判 0。
4. **初始校验**：输入本身若是合法码字，直接返回且**轮数为 0**。

## 定点（L1 已确立，照做）
- LLR 6 bit **饱和**有符号，范围 **[-32, 31]**；Q1 尺度：Δ=0.5，llr0 的 ±3.0 → **±6**。
- 消息幅值取自行内 LLR 的绝对值，故范围 [0,32]，**消息用 7 bit 有符号**（[-64,63]）承载。
- **只在"逐列聚合 `llr0 + Σ消息` 之后"做饱和**（这是 L1 验证过的语义），消息本身不饱和。
- 累加器宽度：每列最大度 13 ⇒ |Σ消息| ≤ 13×32 = 416，加 llr0 ⇒ ≤ 422 ⇒ **12 bit 有符号**足够，请用 12。
- **必须饱和，不能回绕**（L1：回绕版 0/14 全不收敛）。

## H 的访问（已给你现成数据，不要自己重算）
- 校验位列（前 10800 列）：行 0 连列 `{0}`；行 `r>0` 连列 `{r-1, r}`。
- 信息位列：列 `= 10800 + 360t + m`，行 `r` 与它相连当且仅当 `(r - x) mod 30 == 0` 且 `m = ((r - x) mod 10800)/30`，其中 `x ∈ B_t`。
- **B_t 已按 `x mod 30` 分好桶**（每桶恰好 20 项，共 600 项），便于每行只扫一桶：
  - `logs/ldpc/golden/bt_by_res.hex`：600 行，每行 6 位十六进制，值 = `(x<<8) | t`（x 是 14 bit 基地址，t 是组号 0..149）
  - `logs/ldpc/golden/bt_res_off.hex`：31 行，每行 3 位十六进制，第 `ρ` 桶的区间是 `[off[ρ], off[ρ+1])`
  - 每行 r 只需扫 `ρ = r mod 30` 那一桶。
  - 请用 `$readmemh` 在 testbench 里加载，或把表作为 `initial` 初值写进 ROM（**综合时要能推断成 BRAM**）。

## 黄金集（比对目标）
- `logs/ldpc/golden/summary.tsv`：每个样本的 `converged` 与 `iters`
- `logs/ldpc/golden/in_<tag>.hex`：输入硬比特，**64,800 bit 按 8 bit/字节打包**（大端，`np.packbits(bitorder="big")`），共 8100 字节
- `logs/ldpc/golden/out_<tag>.hex`：**期望的完整码字**，同样打包（仅收敛样本有）
- **8 个收敛样本的输出码字 SHA 全同（`53ba32145df35acd`）**，即都收敛到同一个合法码字。

## testbench 判据
从 `in_<tag>.hex` 载入比特（注意字节→比特的大端展开顺序要与 `np.packbits(bitorder="big")` 相反），跑完译码后：
1. **`converged` 必须与 summary.tsv 一致**；
2. **`iter_count` 必须与 summary.tsv 一致**；
3. **输出 64,800 bit 必须与 `out_<tag>.hex` 逐位相同**；
4. 打印 PASS/FAIL 与实测轮数。

## 你要实际跑的仿真
用 **iverilog**（项目 `tools/run_sim.sh` 也用它；本次直接调 `iverilog`/`vvp` 即可）。**至少跑完这两个样本**并在答复里给出原始输出：
- `013_se150_16384`（**4 轮**，最快）
- `008_se150_2048`（5 轮）
若还有余力，再跑 `006_se150_1312`（28 轮）。
（`vvp` 跑百万级周期是可以的；`013` 估计约数百万周期。）

## 硬约束
- **不要**改 `sw/`、`tools/`、`clients/`、`docs/` 的既有文件；**不要**动 `hw/ip/`（生产 IP 打包目录）。
- **不要**跑 Vivado 综合/实现（OOC 与 impl 由 main 跑，避免资源争用）。
- **不要**做 Git 写操作；**不要**运行 `tools/verify_repo_binding.sh`（沙箱内 git 只读，必然失败白跑）。
- 不碰板卡。
- 看板：`tools/agent_view.sh start/update/done --agent ldpc-rtl-l4 ...` 自行登记。

## 交付
1. 新增/改动文件清单；
2. **仿真的原始输出**（每个样本的 PASS/FAIL、实测轮数、比对结果）+ 你用的确切命令；
3. **明确区分**：哪些已验证（仿真的）、哪些没有（未综合、未上板、未测时序）；
4. **任何你无法与黄金对齐的地方**：如实报告，**不要为了让它 PASS 而放宽判据或改黄金**。如果真的对不上，把最小复现和你的分析写清楚——**失败证据比一个假 PASS 有价值得多**。
答复用中文。