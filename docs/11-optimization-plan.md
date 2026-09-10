# 11 · 性能、通用性与上位机优化计划

> 当前执行与并发依赖见 [15](15-resume-and-parallel-plan.md)。本文件保留方向与原则，
> 不以估算代替性能/功耗实测，不根据过期资源报告排除候选。

## 1. 执行顺序

```text
T0 分段计时与公平基准
→ P0 拆解 4.25 s 板端固定开销        ← 2026-09-10 新增，最高优先级
→ H 上位机/传输优化
→ 双缓冲/DDR 往返削减
→ 多 payload 泛化（重复 ≥3 次）
→ 错误鲁棒性矩阵
```

> 2026-09-10 按 [17](17-competition-strategy.md) 删除两项：
> 「T2 Stage1 候选比较（含 8-way）」与「8 倍展开或更大 batch」。
> 4-way 已实测 88.0% LUT 占用，8-way 外推约 125%，在 XC7Z010 上放不下；
> 且即使放得下，端到端仍受 4.25 s 固定开销支配（Amdahl），收益远小于 P0。

没有 T0 分段计时，不将 RTL 性能候选合入生产。数据、模型核验和 RTL 只读分析可以并行，
不是等所有性能工作结束才开始多 payload。

## 2. Stage1 目标与架构展开

当前设计在读段维度并行、碱基维度部分串行。
**展开序列止于 64×4，已于 2026-09-09 收口**：64×4 整机实测 1.929x、
LUT 15,483/17,600 (88.0%)、RAMB36 44/60、WNS +0.246 ns（策略
`Performance_ExplorePostRoutePhysOpt`，已固化进 `hw/scripts/build.tcl`）。
**64×8 不再评估**：按实测 ~1,634 LUT/路外推需约 22,000 LUT，超出器件 25%。
详见 [17](17-competition-strategy.md) §2.1。

### 2.1 资源报告纠偏

`hw/build/export/reports/implementation-utilization.rpt` 的日期是 2026-08-30、
状态 Fully Placed，不能与 9 月时序报告拼成当前 2-way 的资源定论。

9 月 6 日 `hw/build/export/reports/util.rpt` 的 Routed 顶层为：

| 资源 | 报告值 |
|---|---:|
| Total LUTs | 12,232 |
| FFs | 14,830 |
| RAMB36 / RAMB18 | 44 / 2 |
| BRAM Tile 等效量 | 45 |
| DSP | 3 |

`timing.rpt` 报告 WNS +0.136 ns、WHS +0.007 ns；这是报告本身的观察值，
仍需补齐源码 commit、实现配置和已装载制品关联。当前表没有 Slice 总数，
不能用旧报告的 96.68% 补齐。

撤回“2-way 是 7010 极限”“新板无缝迁移”。

**2026-09-10 更新（以实测替换当时的待定状态）**：
- “4-way 必然超限”**已被证伪** —— 4-way 实测可落地，88.0% LUT、正 WNS；
- “8-way 保留候选”**已关闭** —— 按实测增量外推约 125% LUT，放不下；
- batch 调整、访存复用、频率提升**仍是候选**，但按 [17](17-competition-strategy.md) §1，
  它们同样受 4.25 s 固定开销封顶，须排在 P0 之后。

更大芯片资源只是条件之一，DDR/MIO/PHY/时钟/XDC 未知的新板不能直接迁移。

## 3. 数据不足的处理

保持 `data/R0.83_data/` 只读。用 `tools/generate_payload_dataset.py` 生成 D1 多 payload，用 `tools/mutate_reads.py` 生成 D2 错误/覆盖度数据；每个实验保存 manifest、输入/输出哈希、随机种子和最终判据。D0 真实、D1/D2 合成、D3 外部数据必须分开报告。

## 4. 上位机

拆分 FASTQ 读取、几何检查、协议会话、结果接收、LDPC 和验证报告；用 profiler 找热点；优化缓冲复用、流式读写、C LDPC 和结果并行处理。Python 保留为参考实现，C/原生扩展必须逐位对照并通过断连、超时、错误协议测试。

## 5. 成功定义

> 按 [17](17-competition-strategy.md) §1：**“性能”不再定义为超过对照 CPU**。
> 在 XC7Z010 上这已被自有实测数据证明不可能（固定开销 4.25 s 本身就大于
> 多核 CPU 跑完全量的 3.70 s）。性能成功 = 真实浪费被消除且可复现。

- 性能：同输入同正确性下，分段和端到端耗时下降；
- 通用性：至少 5 个 payload；
- 鲁棒性：覆盖度、substitution、insertion、deletion 曲线；
- 工程性：长稳、断连恢复、资源/时序/功耗有证据。
