# FPGA DNA 读出加速系统 (dna-readout-accelerator)

> **项目状态**：比赛已全部结束，本项目源码与文档全面归档并冻结。  
> **归档冻结标签**：`final-2026-11` | **主分支**：`main` | **开源协议**：MIT License

---

## 1. 项目简介

针对 DNA 信息存储规模性应用过程中读出计算密集瓶颈，本作品在 Xilinx Zynq-7000（XC7Z020）上构建从测序读段到原始载荷的完整硬件加速流水线：**滑窗比对（Stage 1）、差分投票（Stage 2）、反稀疏化（Stage 3）与片上 LDPC 纠错（Stage 4）固化于 FPGA**，以 16 路并行与流水选优树把核心处理压到 9 秒以内，吞吐较 48 核服务器参考实现提升约两个数量级。40 余类载荷零静默错误，连续长稳数百轮无失败；板端硬件校验与载荷哈希双重闭环，为规模化 DNA 读出提供可落地方案，并沉淀出可复用技能包。

---

## 2. 最终实现与硬件身份

本项目交付物基于 Vivado / Vitis 2026.1 从零重建并通过完整板测验收，核心硬件指标如下（数据源自 `build/reports/2026.1-rebuild.md`、`timing.rpt` 与 `util.rpt`）：

| 指标项 | 最终实测数值 | 依据与状态 |
| :--- | :--- | :--- |
| **目标器件** | Xilinx Zynq-7000 `xc7z020clg400-2` (BKB220) | 100 MHz 生产主频 |
| **固件身份标识** | `FW_BUILD_ID = bfcd40dd3c435a19` | 源码内容哈希，板测/报告逐字符一致 |
| **时序性能** | **Setup WNS: +0.089 ns** (0 failing endpoints)<br>**Hold WHS: +0.030 ns** (0 failing endpoints) | 严格收敛 (`All timing constraints met`) |
| **LUT 资源** | **36,731**（Logic 36,018 / LUTRAM 502 / SRL 211） | 占比 69.04% |
| **触发器 (FF)** | **38,437** | 占比 36.13% |
| **块存储 (BRAM)** | **RAMB36: 89 块 / RAMB18: 2 块** | 算力与片上缓存平衡 |
| **DSP 单元** | **6** | 满足低功耗低开销设计 |

---

## 3. 仓库目录结构

本仓库以权威提交包为主体组织，以 `src/` 为源码工作根，同时保留完整的科研演进历史与运维门禁：

```text
.
├── readme.md                       # 本项目总览、指标、复现指引与归档说明
├── license                         # MIT 开源许可证
├── AGENTS.md / CLAUDE.md           # 协作规范与历史经验总结（归档版）
├── src/                            # 【核心代码】以提交包为准，源码工作根
│   ├── hw/                         # 自研 IP（dna_accelerator_core 等）、约束与板级脚本
│   ├── sw/                         # PS 裸机固件（lwIP 协议栈、DMA 状态机、app 源码）
│   ├── clients/                    # 上位机客户端 Python 源码与 GUI 实现
│   └── tools/                      # 核心构建、自检、封包与仿真驱动脚本
├── sim/                            # 【仿真体系】（163 个验证资产）
│   ├── rtl/                        # RTL 级 testbench 与 IP 级仿真（25 个）
│   ├── golden/                     # 117 个黄金向量（SE150 / SE250 / LDPC 逐位一致）
│   └── host/                       # 21 个 PS 固件逻辑与行为级回归测试
├── build/                          # 【构建与制品】
│   ├── artifact/                   # 最终上板制品（bit, xsa, elf, boot.bin, manifest, sha256sums）
│   ├── reports/                    # 2026.1 从零重建记录、时序报告与资源报告
│   └── configs/                    # build.config、vitis.config.json 等复现配置
├── board/                          # 【板测证据】提交包 32 个实测日志（含 G3 判据与长稳留证）
├── data/                           # 【测试数据集】基准数据与 42 例完整多媒体测试集（约 108 MB）
├── skill/                          # 【技能资产】竞赛沉淀的 8 个可复用工程技能包
├── report/                         # 【赛事报告与海报】
│   ├── design-report-2026.docx     # 权威可编辑底稿（5.98 MB，含手改 7 篇文献与脱敏实物图）
│   ├── design-report-2026.pdf      # 权威交付 PDF（2.24 MB，28 页）
│   ├── poster/                     # 权威海报底稿（pptx）与矢量 PDF
│   ├── figures/v2/                 # 15 张正式插图
│   └── tools/                      # 10 个报告构建、COM 导出、图片脱敏与文献抓取工具
├── docs/                           # 【设计与科研档案】
│   ├── 01-overview.md ~ 09-evidence-ledger.md # 核心技术架构、状态与证据台账
│   ├── 10-final-status.md             # 归档总结、最终制品身份、事实表与审计记录
│   ├── 11-project-summary.md          # 206 字作品定稿简介
│   └── history/                    # 科研演进历史：ARM 裸机基线、48 核 CPU 基线、硬件探索原型
└── tools/                          # 【仓库运维门禁】agent_view.sh、verify_repo_binding.sh 等
```

---

## 4. 提交物与分发策略

| 交付形态 | 内容物 | 存放位置与说明 |
| :--- | :--- | :--- |
| **Git 仓库**<br>*(Public)* | 全部源码、仿真套件、复现配置、制品固件（bit/xsa/elf/boot）、42 组测试向量、权威设计报告、海报与历史文档 | 随仓库全量跟踪，单文件严格控制在 ≤ 10 MB |
| **GitHub Release 附件**<br>*(推荐挂载)* | 1. 提交包压缩原件 `dna-readout-accelerator.rar`（59.1 MB）<br>2. 最终演示视频 `提交视频.mp4`（104.3 MB）<br>3. 上位机独立可执行文件 `gui_app.exe`（29.1 MB） | 大于 50 MB 或独立可执行二进制，不入 Git 树，通过 Release 附件提供下载 |
| **本地完备归档**<br>*(.gitignore)* | 原始留证（11,288 个板测日志）、全量第三方参考文献、涉密材料（已签字授权书扫描件、未脱敏照片） | 严格隔离在本地 `archive/`，不公开分发 |

> **演示视频时长重要纠偏说明**：  
> 实测最终演示视频（`archive/submission-2026/提交视频.mp4`）参数为：1920×1080 (1080p)，H.264，30 fps，内嵌中文字幕，**精确时长为 2 分 49 秒 71（169.7 秒）**。此前提交包草稿中记载的“4 分 09 秒”系早期过期预估口径，特此勘误。

---

## 5. 快速复现指引

### 5.1 纯软件仿真与主机回归（无需硬件）

直接使用标准开发环境（GCC / Icarus Verilog / Python 3.8+）：

```bash
# 1. 运行 PS 固件协议与流水线行为级主机回归（直接编译 src/sw/app/echo.c）
bash src/tools/run_sim.sh host

# 2. 运行硬件数据通路 RTL 仿真（64,800 位与黄金向量逐位一致）
bash src/tools/run_sim.sh datapath

# 3. 运行生产 IP 打包与一致性门禁检查
bash src/tools/run_sim.sh packaging
```

### 5.2 从零构建硬件与固件（需 Vivado / Vitis 2026.1）

1. **硬件工程构建（输出 bit / XSA）**：
   ```bat
   set VIVADO_BAT=<Vivado安装目录>\bin\vivado.bat
   cd build
   run_build.bat
   ```
2. **软件工程构建（输出 ELF / BOOT.bin）**：
   ```bat
   set XILINX_VITIS=<Vitis安装目录>
   powershell -ExecutionPolicy Bypass -File src\sw\scripts\run_vitis_modern.ps1 -Config build\vitis.config.json
   ```
3. **制品组装与自检**：
   ```bat
   python src\tools\make_artifact_package.py --hw-export build\vivado\export --sw-export build\software-export --app-src src\sw\app --out build\artifact-rebuilt --package-name bkb220-release
   cd src && python tools\write_source_manifest.py --package ..\build\artifact-rebuilt --resign
   ```

### 5.3 板端实测验收（连接 BKB220 开发板）

启动 `hw_server` 后，通过网口及串口执行全自动板级验收：

```bash
cd src/tools
bash run_g3.sh --artifact-dir ../build/artifact \
  --xsdb "<Vitis安装目录>/bin/xsdb.bat" --hw-server TCP:127.0.0.1:3121 \
  --device xc7z020 --uart-port COM10 --ip 192.168.1.10 --port 7 \
  --win-root D:/evidence-tmp
```

---

## 6. 许可与合规说明

本项目原创源码、脚本、文档遵循 **MIT License**（详见 `license`）。第三方组件、测试读段、AMD IP 与参考文献使用遵守各自原有协议，详见 `docs/09-evidence-ledger.md`。
