# DNA 存储读出 FPGA 加速系统

系统在 Zynq-7000 上把测序 FASTQ 还原为文件：

```text
PC FASTQ/水印 → TCP → PS裸机/lwIP/AXI-DMA
→ PL Stage1滑窗比对 → PL Stage2投票
→ PS水印XOR → PL Stage3反稀疏化
→ TCP回传8100 B → PC LDPC → 原始文件及SHA-256
```

## 当前状态（2026-10-13）

BKB220 配置已为 `ready=1`。P4/P16 均完成 100 MHz 整机 route、bit/XSA 构建；P4 完成 G3，P16 完成 smoke、全量、连续/状态复位、故障探针、六档矩阵及 42 例 v2 数据集板端对照。正式 P16 上传配置包已构建并 G3 PASS，上传为 0.40 s；完整软件包可用，但 Vitis 自动化构建路径仍有需补齐的步骤，详见[转正记录](docs/benchmarks/bkb220-p16-upload-promotion.md)。

当前剩余项：v2 的 `score_min=67` 尚未在板上测；8 个 challenge 例仍按软件验证器一致地以 LDPC 不收敛告失败；新载荷四级逐级取证、8 h 长稳（2 h 已完成）、QSPI/SD 冷启动、UART 反向、实测功耗和 F9 独立复核未完成。P16 仍慢于 16 线程 CPU；Stage1 K2 已有 OOC 与整机 route 证据，相关后续工作仍在进行，不能据此写成 Stage1 优化已完成。详见[当前状态与证据边界](docs/03-status.md)。

## 许可

本项目作者原创部分采用 **MIT**（见 [LICENSE](LICENSE)）。仓库内的第三方素材（原始测序数据、厂商板级资料、参赛提交与历史资产、以及 Xilinx/AMD 工具生成的制品）**不适用** MIT，各自保留原条款——详见 LICENSE 末尾的适用范围说明，公开分享前请按各来源许可处理。

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
bash tools/check_repo_hygiene.sh
bash tools/check_ip_packaging.sh
python3 -m unittest discover -s tests/host -p 'test_g3_*.py' -v
bash tests/host/run_host_tests.sh --worktree
bash tools/run_sim.sh stage1_production
```

`check_repo_hygiene.sh` 检查根目录工具残留、工具登记、现用文档编号与归档去号、重复水印、`logs/` 忽略覆盖、文件行号引用、`sw/app/` 与 workspace 同名文件一致性、attic 登记、实验目录清单及已跟踪文件重复 SHA-256。`check_ip_packaging.sh` 检查 IP `hdl/` 内容、重复模块打包歧义、`component.xml` 引用和孤儿文件、打包变体清单、回归覆盖，并核对 Stage1 生产参数/源集/GUI/静态选择及 P-way 源码约束。细项以两个脚本为准，入口见[工具索引](tools/README.md)。

正式LC50长测：`SIM_CASE_TIMEOUT=3600 bash tools/run_sim.sh stage1_production_full`；Windows2026.1的可复现XSim入口见运行手册。LC6短测不能替代LC50。起点参赛脚本附件重复告警已收敛为唯一源引用，过程见[整理记录](docs/reference/workspace-cleanup-2026-10-10.md)；旧失败日志保留。

**工具链分工（2026-10-12 明确）：开发全部在 WSL 用 Vivado/Vitis 2022.2（RTL/BD/约束/综合/实现/时序/bit/XSA/BSP/ELF/FSBL/BOOT）；Windows 里的 2026.1 只负责烧录/下载/调试，烧的是 22 产出的制品。** 见 [07 §3a](docs/07-board-build-and-acceptance.md)。

用户指定的开发顺序（2026-10-11）：开发全部在 WSL 使用 Vivado/Vitis 2022.2，Windows 2026.1 只负责烧录、下载和调试。P16 完整同源包已有构建及 G3 证据；`create_vitis.tcl` 到完整包的自动化路径仍有手动补步，限制见转正记录。F9 的 Windows 2026.1 独立完整开发链复核仍待 22 主线后续阶段。

整机构建使用`VIVADO_ROOT=/tools/Xilinx/Vivado/2022.2 bash tools/run_vivado_build.sh ...`。P4/P16 独立目录的 bit/XSA 与板测记录见[07](docs/07-board-build-and-acceptance.md)及对应 benchmark；已通过的制品包与尚待完善的自动化构建链分别表述，不互相替代。

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
