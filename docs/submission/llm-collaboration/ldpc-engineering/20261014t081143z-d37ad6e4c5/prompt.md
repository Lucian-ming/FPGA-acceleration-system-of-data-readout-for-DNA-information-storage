> 脱敏副本，原件 `20261014T081143Z-d37ad6e4c5/{prompt.txt,answer.md}`。本机绝对路径、邮箱、凭据形模式及非白名单私网 IP 已替换；除脱敏与换行规范化外保留原文。

任务（workspace-write，看板名 **ldpc-speed1**）：压缩 p=1 LDPC 译码器的**内层循环周期数**。目标：总周期数降到约 1/3，**功能必须与现在完全一致**。

## 已知（先读这些）
- 译码器 `hw/experimental/ldpc_decoder_p1.v`（p=1 边串行 flooding Min-Sum，功能已对黄金）
- testbench `hw/experimental/tb_ldpc_decoder_p1.v`（**已含总周期与分阶段周期计数**，用法 `vvp <out> +TAG=<样本>`）
- `docs/benchmarks/ldpc-decoder-l4.md`（功能判据与边界）
- 黄金集 `logs/ldpc/golden/summary.tsv`（14 样本，8 收敛 / 6 不收敛）
- 上一轮周期实测：`logs/ldpc/sim14-20261014-rerun/{results.tsv,phase-summary.txt}`

## 实测到的低效（**这是本轮的靶子**）
全量 14 例累计 978,534,050 周期的分布：syndrome 38.70%、GATHER 18.89%、桶/地址生成 18.46%、EMIT 16.22%、逐列处理 7.73%。

换算成"每次访问一条边"：
- **行扫描阶段（桶+GATHER+EMIT）= 6.3 周期/边**（以 013 为例：每轮 2.78M 周期 / 237,599 边）
- **syndrome ≈ 100 周期/行**（10800 行/轮），而它只是对该行 22 列做一次 XOR —— **水分最大**
- 逐列更新 3.3 周期/列

一个紧致的边串行引擎应做到 **2~3 周期/边**。所以**内层有 3~4 倍空间**。

## 你要做的
**在不变更架构的前提下**（仍是 p=1、边串行、同样的算法与访存语义），压缩周期。方向供参考，具体由你判断：
- 桶 ROM 扫描目前约 2.4 周期/项 —— 能否流水成 1 项/周期；
- GATHER 每条边约 2.2 周期、EMIT 约 1.9 周期 —— 同步读 + 寄存器的气泡能否用流水线填掉；
- **syndrome 那 ~100 周期/行**：它和行扫描走的是同一批行列关系，为什么这么贵？**先诊断清楚再说怎么改**。可能的方向是把它与行扫描融合（行扫描时顺便按行 XOR 当前 decoded 位），但**注意收敛判定的时点必须与参考语义等价**（见下）。
- FSM 状态数、每状态的固定开销、以及 `sum_mem` 读改写之间的空拍。

## 硬性约束（判据，**先读再动手**）
1. **功能必须逐位不变**。验收：14 个样本全部跑，与上一轮 `logs/ldpc/sim14-20261014-rerun/results.tsv` 逐项对比——
   - 8 个收敛样本：**码字 64,800 位逐位相同**；
   - 6 个不收敛样本：仍报未收敛；
   - **实测轮数也要与上一轮相同**（上一轮实测轮数是本版的行为基线；注意它本来就与浮点黄金不同，那不是缺陷）。
2. **若你打算把 syndrome 融进行扫描**：必须保证**检测时点与返回的码字和轮数与现在完全一致**。参考语义是「每轮更新后用新 decoded 查 syndrome，为 0 就返回该 decoded 与该轮数」。融合若导致多跑一轮或早停一轮，**都算不通过**。
3. **不许放宽判据、不许改黄金数据、不许为通过而改 testbench 的判定逻辑**（可以加计数与日志）。
4. 每改一版都要**重跑仿真**并记录周期数；**失败证据保留**。
5. **时序不能崩**：改完请跑一次 **OOC 综合**（`SYNTH_IMPL=0`，只要综合，**不要跑布局布线**——impl 由 main 跑以独占资源），确认没有新的组合长路径迹象，并报告综合后 WNS（**注明这是综合后、不是布线后**）。
   命令参考：
   ```
   SYNTH_PART=xc7z020clg400-2 SYNTH_TAG=ldpc_speed1 SYNTH_OUT_ROOT=logs/vivado/ldpc-speed \
     <本机路径> -mode batch \
     -journal logs/vivado/ldpc-speed1.jou -log logs/vivado/ldpc-speed1.log \
     -source docs/submission/skill/fpga-timing-probe/ooc_probe.tcl \
     -tclargs ldpc_decoder_p1 100 hw/experimental/ldpc_decoder_p1.v
   ```
   ⚠️ `logs/vivado/` 本身**不被 gitignore**（只忽略其子目录），所以 journal/log 要放进 `logs/vivado/<子目录>/`。

## 硬约束
- 只改 `hw/experimental/ldpc_decoder_p1.v` 与 `hw/experimental/tb_ldpc_decoder_p1.v`；**不要**碰 `sw/`、`tools/`、`clients/`、`docs/`、`hw/ip/`。
- **不做 Git 写操作**；**不要运行 `tools/verify_repo_binding.sh`**（沙箱内 git 只读，必然失败白跑）。
- 不碰板卡。
- 看板自行登记：`tools/agent_view.sh start/update/done --agent ldpc-speed1 ...`

## 交付
1. 你诊断出的**具体低效点**（每条：在哪个状态/哪几拍、为什么空转）；
2. 逐项改动与**每项的周期收益**；
3. **14 个样本的前后对照表**：轮数、码字是否逐位相同、**总周期数**、**分阶段周期**；
4. **总周期改善倍数**（加权与单样本都给）；
5. 综合后的资源与 WNS（注明是综合后）；
6. 明确区分实测与未做；失败或放弃的尝试也要写。
答复用中文。