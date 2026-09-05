# DNA 存储读出 FPGA 加速系统

在 AMD/Xilinx Zynq-7000 上实现 DNA 信息存储读出：

```text
FASTQ → Stage1 水印滑窗比对 → Stage2 投票 → Stage3 反稀疏化 → LDPC → 原始文件
```

## 当前状态

截至 2026-09-05，SE150/SE250 均已完成真实板端 G3 闭环；SE250 全量 129,600 条记录和连续任务也已通过。当前未关闭重点是：

- Stage1 公平性能优化；
- 多 payload 泛化；
- 测序错误/覆盖度鲁棒性；
- 上位机性能与可维护性；
- 实测功耗和长期稳定性。

最终哈希判据、适用范围和未关闭问题见 [`docs/03-status.md`](docs/03-status.md)。

## 新会话阅读顺序

只需按 [`docs/README.md`](docs/README.md) 阅读 `docs/01`～`docs/12`；历史完整快照位于 `docs/archive/history/2026/`，不要默认扫描。

## 快速验证

```bash
bash tools/verify_repo_binding.sh --remote
python3 tools/golden_model.py verify-code
bash tools/run_sim.sh
bash tools/run_xsim.sh all
STAGE1_JOBS=3 bash tools/run_m2_full.sh
```

板端 G3：

```bash
bash tools/run_g3.sh --full --read-bps 250 --score-min 112 \
  --reads "data/R0.83_data/Sequencing data/DNA-40.5Kb-MC-SE250.fastq"
```

完整构建与上板顺序见 [`docs/09-board-build-and-acceptance.md`](docs/09-board-build-and-acceptance.md)。

## 目录

```text
docs/                 当前文档和历史归档
hw/                   Vivado、IP、RTL、仿真和约束
sw/                   Zynq PS 裸机/lwIP 固件
clients/python/       CLI、GUI、LDPC 和协议
tools/                黄金模型、构建、仿真、压测和板测工具
data/R0.83_data/      只读真实基准数据
archive/              历史提交资产，只读
```

## 开发门禁

- 只在 WSL 原生 checkout 的 `main` 开发；
- 开始前运行 `bash tools/verify_repo_binding.sh --remote`；
- 禁止修改 `data/R0.83_data/`；
- 不得用历史正确结果绕过 FPGA 生产路径；
- 改 RTL/固件后必须重建 `.bit/.xsa/.elf/BOOT.bin` 并更新哈希；
- 提交前显式指定路径，推送后确认 `main...origin/main = 0/0`；
- 新证据必须写入带时间戳目录和 `docs/` 摘要。

## 环境

- Vivado/Vitis 2022.2；
- 当前目标器件 `xc7z010clg400-1`，PL 100 MHz；
- 目标板为 ZYNQ ECO(R6)，DDR 配置见 `docs/09-board-build-and-acceptance.md`；
- 工具生成日志不得留在仓库根目录。
