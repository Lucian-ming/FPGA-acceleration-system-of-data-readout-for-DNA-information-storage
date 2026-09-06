# 03 · 当前状态与未关闭问题

> 更新：2026-09-06。本文只保留有效结论；中断清点见 [16 审计](16-interrupted-work-audit-2026-09-06.md)，当前执行见 [15 并行计划](15-resume-and-parallel-plan.md)。历史结论必须绑定旧配置。

## 1. 当前结论

- **G3 已闭环**：SE150 与 SE250 均在目标 Zynq ECO(R6) 板上完成真实 TCP → PL → DDR → LDPC → 图片哈希闭环。
- **SE250 全量已闭环**：129,600 条记录、64,800 条源读段，板端结果 8,100 B，图片 SHA-256 为
  `fcd0cf90bd680e7bbdc203e3398119504da0897acac9e2117008b4efb6b1f2c3`。
- **连续任务已闭环**：跨规模、三轮连续、全量双轮弄脏自证和 SE250 四轮多尺度压测均有留证。
- **制品完整性已复核**：9 月 6 日 `hw/build/export/SHA256SUMS` 五项通过；同目录的 8 月旧报告与 9 月 routed 报告不可混用。文件哈希通过不单独证明源码、制品、板端运行同源。
- **版本边界**：上述 SE250 全量与连续任务是历史配置留证，不自动覆盖 9 月 6 日的 SE150 2-way 制品。本轮未重新上板、未重建。
- **多 payload 部分通过**：保存的五份 dump 重译码得到 D0 + 三种 D1 通过、高熵 D1 失败；不是五种独立 payload 全通过。
- **算法边界**：当前系统不是任意 DNA 编码器；正式支持范围由 manifest、读长 profile、几何参数和阈值共同限定。

## 2. 关键实测指标

| 项目 | 历史板测证据（不能直接套用新 2-way） |
|---|---|
| SE150 | 4,096～103,616 条记录多档板级闭环 |
| SE250 | 4,096～129,600 条记录多档板级闭环 |
| SE250 全量 | 约 217.47 s 板端计算，最终哈希一致，四级 DDR 4/4 通过 |
| 连续全量两轮 | 弄脏轮→判据轮，原始回传相差 24,839/64,800 bit，判据轮哈希一致 |
| 时长模型 | `t = 4.93 s + 0.9396 ms × 记录数`，当前为板测模型，不是理论上限 |
| 自动压测 | 737 轮留证；排除边界探索/故障注入后，SE150 700/700、SE250 13/13 有效任务通过 |

详细原始摘要位于 `docs/board/run-logs/` 和外部板测留证目录；压测分类见
`docs/12-stress-analysis.md`。

## 3. 尚未关闭的问题

### P1 · Stage1 吞吐

W1-A 已重构 `tools/run_cpu_benchmark.py` 并通过单测（commit `f7c898d`）：建立 MEASURED / HISTORICAL / ESTIMATED 严格三级分型，功耗标记未测，彻底清除虚假 FPGA 常量与未实测能效比。
W2-R 已完成 4-way 边界缺陷修复（`<= STRIDE`）与两拍流水化时序闭环（commit `5af3fa3`，详见 `docs/benchmarks/stage1-4way-timing-closure.md`）：全量 50 区域仿真相对 2-way 提速 1.929x 且 100% 逐位一致，Vivado OOC 实测 WNS @ 100MHz 达 **+2.197 ns**，RAMB36 保持为 8 块，LUT 仅占用 8,673（49.3%），证明 4-way 具备在 7010 芯片上的落地可行性。
W3-A 现场物理板卡实测（commit `f0d6af0`，详见 `docs/benchmarks/measured_cpu_vs_fpga.md`）：真实物理板卡 2-way 100MHz 在 2,048/4,096/8,192 源读段 × 3 轮实测（9/9 轮哈希全 PASS）中，纯计算吞吐为 304～591 reads/s（拟合模型：$T \approx 4.25\text{s} + 0.58\text{ms} \times N_{\text{records}}$）；同期宿主 CPU (i5-13500H) C 优化单核吞吐为 1,364.9 reads/s，16 线程达 14,003.1 reads/s。**实测定论：现行 100MHz 2-way FPGA 纯计算吞吐尚未击败优化多核 CPU，严禁宣称加速优势；无外置功率计前功耗统一标记 UNMEASURED / N/A**。

### P2 · 多 payload 泛化

W1-B 已重构 `tools/run_multi_payload_regression.py` 并通过单测（commit `73168c1`）：全量 64,800 字节合法性校验，8,100 字节固定 LSB-first 位序；复核磁盘 5 份 dump 保持已知 4 PASS + 1 FAIL 事实边界。
W2-D 已通过五级分级诊断（commit `5797a17`，`tools/debug_high_entropy.py`）定位高熵失败根因：彻底排除生成器缺陷与反稀疏化扩散，证实主因为高熵序列下水印伪互相关（期望 70.9 vs 伪相关 63.2）与门限（60）不适配，导致 82.1% 伪读段误入并稀释投票；在门限 65 下原始误码骤降至 236 bit 且 LDPC 成功收敛。
W4-D 多 Seed 验证与首个 D2 数据集交付（commit `f0d6af0`，详见 `docs/benchmarks/entropy_and_d2_validation.md`）：跨 5 个独立随机种子（Seed 101～105）全面证实门限 65 下达成 100% 收敛（5/5 PASS，误码均值仅 179.4 bit，下降 92.3%），排除随机偶发；正式交付首个 D2 受控噪声数据集 `tests/datasets/D2_controlled_noise/`（有效突变率 1.3918%，4,096 源读段，端到端 2 轮收敛恢复，SHA256SUMS 6 项全 OK）。

### P3 · 错误鲁棒性曲线

W1-B 已重构 `tools/run_robustness_scan.py` 并建立“板端等价模式”（both 双向独立过门限、逐票饱和截断 [-128, 127]；commit `73168c1`）。原最佳方向软件模式已隔离并标注不可作为硬件 G5 验收。
W4-R 硬件等价模式鲁棒性实测报告（commit `f0d6af0`，详见 `docs/benchmarks/measured_robustness_analysis.md`）：完成跨替换、缺失、插入三种噪声维度的硬件等价抗噪边界扫描。

### P4 · 上位机性能与可维护性

W2-H 已完成上位机 FASTQ 向量化解析与位平面打包无损优化（commit `2743beb`，`clients/python/fast_readout.py`）：全量 51,781 条读段批次打包耗时由 3.38s 降至 0.11s（加速 30.4x，吞吐达 46.5 万 reads/s），全链路主机侧处理占比压缩至 0.13%，消除了流水线停顿瓶颈；单测 25/25 与性能回归 7/7 全绿通过，100% 逐位一致。

### P5 · 工程技术债

包括功耗实测、断连恢复、长期温度运行、许可证/权属确认、文档引用清理和新板迁移风险。没有实测的数据不得写成已完成指标。

## 4. 证据纪律

1. 构建、仿真、包装和历史 XSA 都不能代替板端 G3。
2. 最终图片哈希是端到端判据；中间级别必须同时记录适用范围。
3. 修改 RTL/固件后必须重新构建整套制品并刷新 `SHA256SUMS`。
4. 新运行必须生成新的带时间戳留证目录，不得把旧运行 ID 当成新版本证据。
5. 任何“更快/更省电/更通用”的结论必须给出同口径基线、输入哈希、重复次数和失败样本。

## 5. 历史索引

- 缺陷根因与完整时间线：`docs/archive/history/2026/03-status-before-2026-09-05.md`。
- M3/XSim 细节：`docs/08-verification-plan.md` 与 archive 中对应快照。
- 板卡唯一配置：`docs/09-board-build-and-acceptance.md`。
