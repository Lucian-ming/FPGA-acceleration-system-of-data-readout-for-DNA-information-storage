# DNA 存储读出 FPGA 加速系统

系统在 Zynq-7000 上把测序 FASTQ 还原为文件：

```text
PC FASTQ/水印 → TCP → PS裸机/lwIP/AXI-DMA
→ PL Stage1滑窗比对 → PL Stage2投票
→ PS水印XOR → PL Stage3反稀疏化
→ TCP回传8100 B → PC LDPC → 原始文件及SHA-256
```

## 当前状态（2026-10-11）

旧板 ZYNQ ECO R6 / XC7Z010 的 SE150 生产链路有历史真板闭环。当前任务是迁移到 BKB220 / XC7Z020，并启用 Stage1 16 个滑窗位置并行，PL 100 MHz、64记录/帧、协议及结果格式保持现有契约。交接快照中的新板完整料号、PS7/DDR/MIO/PHY资料与实际连接尚未确认，配置保持 `ready=0`；接管时重新核对实际资料与设备，不把旧枚举当当前现场。

迁移准备已完成：正式可选P4/P16源集及参数、完整制品门禁、现代软件构建入口、独立oracle和AXI包装测试。正式LC50模块/包装接口在 Windows2026.1 XSim通过；47项G3主机用例和工作树固件行为回归通过；Windows2026.1使用旧ECO XSA实际完成BSP/ELF/FSBL/BOOT/readback/SHA核验。

这些结果证明准备代码的相关检查通过。尚无新板bit/XSA、整机时序和新板G3结果。P4/P16模块周期约改善3.27倍，不能当作整机加速比。SE250、32路、能效和泛化结论分别需要对应制品和实测。

## 接手入口

1. 读 [AGENTS.md](AGENTS.md)、[CLAUDE.md](CLAUDE.md)，核验唯一WSL checkout与远程绑定。
2. 读 [完整运行手册](docs/05-implementation-plan.md)，了解项目全貌、所有入口、分阶段计划、资源及交付规则。
3. 主Agent直接使用 [主提示词](docs/agent-prompts/main.md)，接管现成05计划，从尚未完成阶段继续，按最新文档经codex-luna MCP派发gpt-6-luna/max并监控；无需重写计划。
4. 板级任务先阅读并校验[已入库的BKB220 v1.1产品手册](docs/board/bkb220/README.md)，再按[07板级迁移文档](docs/07-board-build-and-acceptance.md)核对配置来源；[03状态](docs/03-status.md)与[09证据台账](docs/09-evidence-ledger.md)限定可对外使用的结论。
5. 其余阅读顺序见 [文档索引](docs/README.md)。历史资料保留供追溯。

## 验证与构建

在 `/home/lucian/projects/FPGA/FpgaAccelerationSystemOfDataReadout` 中运行：

```bash
bash tools/verify_repo_binding.sh --remote
bash tools/check_ip_packaging.sh
python3 -m unittest discover -s tests/host -p 'test_g3_*.py' -v
bash tests/host/run_host_tests.sh --worktree
bash tools/run_sim.sh stage1_production
```

正式LC50长测：`SIM_CASE_TIMEOUT=3600 bash tools/run_sim.sh stage1_production_full`；Windows2026.1的可复现XSim入口见运行手册。LC6短测不能替代LC50。起点参赛脚本附件重复告警已收敛为唯一源引用，过程见[整理记录](docs/reference/workspace-cleanup-2026-10-10.md)；旧失败日志保留。

**工具链分工（2026-10-12 明确）：开发全部在 WSL 用 Vivado/Vitis 2022.2（RTL/BD/约束/综合/实现/时序/bit/XSA/BSP/ELF/FSBL/BOOT）；Windows 里的 2026.1 只负责烧录/下载/调试，烧的是 22 产出的制品。** 见 [07 §3a](docs/07-board-build-and-acceptance.md)。

用户指定的开发顺序（2026-10-11）：先用WSL Vivado2022.2完成硬件开发，PS软件也以补齐后的WSL Vitis2022.2为主；Windows2026.1负责下载/调试。WSL Vitis2022.2已从现有Vivado维护入口补齐：Vivado2022.2、XSCT2022.2.0必需命令及ARM GCC11.2.0实际Cortex-A9 ARM32对象编译通过；完整同XSA软件包仍待迁移阶段重建验证。已有Windows2026.1旧ECO XSA软件兼容探针继续保留，但不替代22主线或新板验收。22主线稳定后，最后独立验证Windows2026.1完整硬件及软件开发链路，规则见07。

整机构建使用`VIVADO_ROOT=/tools/Xilinx/Vivado/2022.2 bash tools/run_vivado_build.sh ...`。BKB220资料门禁通过后，独立P4/P16目录生成同XSA完整硬软包，经g3_artifacts.py和run_g3.sh --artifact-dir验收；22软件包补齐及最后26现代Python路线见[07](docs/07-board-build-and-acceptance.md)。

## 目录与保护范围

| 目录 | 职责 |
|---|---|
| `hw/boards/`、`hw/scripts/`、`hw/constr/` | 板级profile、BD/构建和约束 |
| `hw/ip/`、`hw/sim/`、`hw/experimental/` | 正式三个IP、TB、实验候选；打包源以component.xml/manifest为准 |
| `sw/app/`、`sw/linker/`、`sw/scripts/` | PS固件权威源码、链接布局、软件生成 |
| `clients/python/` | TCP客户端、GUI、协议、LDPC后端 |
| `tools/`、`tests/` | 参考模型、仿真、构建、板测、性能/故障/泛化回归 |
| `docs/` | 当前规范、事实、计划、提示词、历史资料及摘要 |
| `data/`、`archive/` | 原始数据和历史提交资产，只读保护 |
| `hw/build/`、`sw/workspace/`、`logs/` | 制品、生成物和运行证据；保留旧基线，新运行不覆盖 |

2026-10-10起点的职责清单见[项目清单](docs/reference/project-inventory-2026-10-10.tsv)；后续布局以当前Git文件清单和[工具整理记录](docs/reference/tool-cleanup-2026-10-11.md)为准。现用脚本用法见[工具索引](tools/README.md)。

仅此WSL原生checkout、仅main；主Agent统一Git写入，每次按路径提交后立即推送。数据、旧发布制品和失败证据不删除；生成目录的精确忽略规则不代表远程已包含这些文件。交付前确认main/origin为0/0、源码工作区干净、所有剩余门禁真实可追溯。
