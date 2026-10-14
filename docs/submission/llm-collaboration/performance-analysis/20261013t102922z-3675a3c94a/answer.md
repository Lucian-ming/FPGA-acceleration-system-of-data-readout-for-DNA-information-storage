> 脱敏副本，原件 `20261013T102922Z-3675a3c94a/{prompt.txt,answer.md}`。本机绝对路径、邮箱、凭据形模式及非白名单私网 IP 已替换；除脱敏与换行规范化外保留原文。

## 交付

- RTL 参数化已完成：[srpe_batch_pway.v](<仓库根目录>/hw/ip/Dna_accelerator_core_1_0/hdl/srpe_batch_pway.v)
- 探针报告：[stage1-multibase-ooc-probe.md](<仓库根目录>/docs/benchmarks/stage1-multibase-ooc-probe.md)
- 原始 Vivado 报告保存在 `logs/vivado/`：K1 在 `20261013T1834CST_stage1_multibase`；最终扁平地址 bank RTL 的 K2、K4 在 `20261013T1900CST_stage1_multibase_flataddr`。

## OOC 结果

拍数为静态推导；其余表中数据来自 Vivado 2022.2 的 OOC 综合、布局布线报告（100 MHz，`SYNTH_IMPL=1`）。

| K | 每块拍数 | LUT | FF | RAMB36 / RAMB18 | DSP | WNS / WHS (ns) | setup / hold 失败端点 |
|---:|---:|---:|---:|---:|---:|---:|---:|
| 1 | 176 | 27,522 | 25,872 | 8 / 0 | 3 | +0.735 / +0.069 | 0 / 0 |
| 2 | 101 | 28,708 | 26,509 | 12 / 0 | 4 | +0.300 / +0.078 | 0 / 0 |
| 4 | 64 | 41,342 | 26,499 | 20 / 0 | 7 | +0.185 / +0.084 | 0 / 0 |

K1 相对给定基线 26,867 LUT 高 2.44%，低于 20% 停止线，因此继续了 K2、K4。K4 **作为 OOC 单模块可装入 XC7Z020**：占 77.71% LUT、14.29% BRAM tile；该 OOC 模块在 100 MHz **收敛**，但 setup 余量只有 0.185 ns。整机能否装入并收敛，仍需集成后实现确认。

## 验证边界与未完成项

未运行仿真、未触板；功能等价性尚未验证。WNS/WHS 是 OOC 时钟约束下的模块内部时序结果，不能替代整机接口约束与时序 signoff。整机集成和板测未完成。

工作树仅有上述 RTL 与报告两项变更，根目录无 Vivado 日志残留；未执行任何 Git 写操作。
