# 06 · 实施入口与开发门禁

本文是开发前的短版入口；旧版 550 行实施计划已归档至
`docs/archive/history/2026/06-implementation-plan-before-2026-09-05.md`。

## 开发顺序

1. 读 `01-architecture.md`、`02-data-contract.md`、`03-status.md`；
2. 涉及寄存器、DDR、TCP 时读 `05-interfaces.md`；
3. 仿真/接口改动读 `08-verification-plan.md`；
4. 板级构建/上板读 `09-board-build-and-acceptance.md`；
5. 性能、数据扩展和上位机改动读 `11-optimization-plan.md`、`12-stress-analysis.md`；
6. 先跑最小判据，再做长任务；
7. 改 RTL/固件后重建 bitstream、XSA、ELF、BOOT.bin 并更新哈希。

## 变更分类

| 分类 | 例子 | 最低判据 |
|---|---|---|
| 数据契约 | 位序、几何、5b4b | Python/PS/RTL 成对回归 |
| 接口 | AXIS、DMA、FIFO、寄存器 | 真实接口 TB + 故障注入 |
| 性能 | Stage1 展开、DMA 重叠 | 公平基准 + 板测分段计时 |
| 上位机 | 协议、LDPC、GUI | 主机单测 + 板端哈希 |
| 板级 | PS7、DDR、PHY | 最小工程 + G3 |

## 提交门禁

- 禁止修改 `data/R0.83_data/`；
- 不使用历史正确结果绕过 FPGA 生产路径；
- 不以仿真、综合或图片界面代替板端判据；
- 证据摘要写入 `docs/`，大型日志写入归档目录；
- Git 提交只包含本次明确路径。
