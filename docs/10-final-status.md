# 最终状态与归档总表 (Final Status & Evidence Ledger)

> **发布日期**：2026-11-02  
> **项目状态**：比赛已全部结束，全库归档冻结于标签 `final-2026-11`。  
> **开源协议**：MIT License

---

## 1. 最终制品身份与硬件凭证

本项目交付制品于 2026-10-30 在自包含提交树上基于 Vivado / Vitis 2026.1 从零完成硬件综合实现与软件构建，并通过完整板测闭环。

### 1.1 核心固件身份标识
- **固件构建唯一哈希**：`FW_BUILD_ID = bfcd40dd3c435a19`
- **生成依据**：由 `src/tools/write_source_manifest.py` 遍历 `src/sw/app/` 下全部 `.c` 与 `.h` 文件内容及相对路径计算生成，板端运行时通过串口打印输出，并回读校验一致。

### 1.2 权威制品校验和（引自 `build/reports/2026.1-rebuild.md`）

制品文件存放在 `build/artifact/`：

| 文件名称 | SHA-256 校验和 | 规格与说明 |
| :--- | :--- | :--- |
| `top_bd_wrapper.bit` | `5c3fcc1a9a4c3c0c5dbc04b56bb3707e2248f581bbfdc8a73a36aa538eae1a20` | FPGA 比特流 (4,045,769 B) |
| `dna_accel.xsa` | `465d619a47492247b72e7945a2311c57722da7a3f7a678171948b0425f7100c1` | 硬件导出元数据包 (1,422,869 B) |
| `dna_lwip_app.elf` | `ff5894b548d78f4be7a004360dfd68a0eb44398491bd57e852680f451024ffc3` | PS 裸机应用执行体 (1,234,324 B) |
| `fsbl.elf` | `7836590a0085fb86d02ce03da56fc9689cacbc6b1ef017c81008fb12a155fbcc` | 第一阶段引导加载程序 (583,708 B) |
| `BOOT.bin` | `8ff205dc7bd0a8d84e74528dbf76738389c20b7859997a636c49036dc5fedce1` | SD/QSPI 启动镜像 (4,491,604 B) |

### 1.3 最终硬件指标
- **器件型号**：Xilinx Zynq-7000 `xc7z020clg400-2`
- **运行主频**：100 MHz（时钟约束周期 10.000 ns）
- **时序收敛**：
  - Setup WNS: **+0.089 ns** (0 failing endpoints)
  - Hold WHS: **+0.030 ns** (0 failing endpoints)
  - 判定：`All user specified timing constraints are met.`
- **资源利用率**：
  - Total LUTs: **36,731**（Logic 36,018 / LUTRAM 502 / SRL 211，利用率 69.04%）
  - Flip-Flops: **38,437**（利用率 36.13%）
  - Block RAM: **89 块 RAMB36E1 / 2 块 RAMB18E1**（利用率 64.64%）
  - DSP48E1: **6**（利用率 2.73%）

---

## 2. 板测依据合法性与旧 ELF 哈希论证

### 2.1 为什么旧 ELF (`e71554ac...`) 是最终制品的合法板测依据
在 `board/run-logs/` 中留存的 G3 验收与 2 小时长稳实测记录使用的是 2026-10-20 构建的 ELF（SHA-256: `e71554ac...`，1,231,712 B），而最终构建的 ELF 哈希为 `ff5894b5...`（1,234,324 B）。两者的机器码与功能**完全等价**，具有充分的法律与技术依据：

1. **源码绝对同源**：两次构建的 `FW_BUILD_ID` 均为 `bfcd40dd3c435a19`，逐字符一致；
2. **符号表与反汇编 100% 对齐**：
   - 提取符号表比对，1,006 个函数与数据符号名称、尺寸完全相同；
   - 对两版 ELF 反汇编屏蔽绝对内存地址常量后，代码逻辑汇编指令实现 **0 行差异**；
3. **哈希微变根因**：
   - ELF 内部包含调试符号（DWARF）与驱动断言宏（`__FILE__`）。旧包构建于 `D:\dna-accel-bkb220`，新包构建于 `D:\dna-readout-accelerator`；
   - 因构建目录绝对路径字符串长度差异，导致 `.rodata` 中断言路径常量变长，后续数据段对齐偏移，进而引起机器码中引用该字面量的绝对地址发生重定位；
   - `.rodata` 在对齐路径字符串后逐字节相同；`.data` 段中仅有的 257 个变动字全部是指向代码段的函数指针或重定位地址。
4. **结论**：本项目的硬件判定依据严格基于 `FW_BUILD_ID` 与时序/资源实测数据，`board/run-logs/` 的实测留证为当前交付制品的合法、有效证据。

---

## 3. 阶段 1 全量盘点与审计结论总览

在归档清理过程中，对所有相关物理源进行了只读盘点与深度审计：

1. **跨来源精确去重**：
   - 验证了上位机 `gui_app.exe` 在三处位置（包内、PyInstaller dist、桌面演示）SHA-256 均为 `5624f589...`，保留源码与打包配置，Windows 冗余副本在 Phase 6 后清理；
   - 桌面旧副本 `FPGA-DNA/dna-readout-accelerator`（86 MB, 753 文件）经穿透检索，除 2 个崩溃日志外，其余 751 个文件在其他归档区 100% 存在，无独有技术资产；
   - 桌面演示包中 3 组测试用例与包内 `data/` 逐字节一致，`演示说明.txt` 已提炼至 `docs/history/demo-notes.md`；
2. **2.0 GB 板测原始留证优化（方案 A）**：
   - 审计发现 `soak-2h-evidence/g3_runs/` 下 263 轮次目录重复存放了 262 份 bit/xsa/elf 二进制（浪费 1.67 GB）；
   - 执行 Linux 原生硬链接（Hardlink）零损耗去重后，目录结构与文件可读性 100% 保持，体积从 1,913 MB 锐减至 183 MB，瞬间节省 1.73 GB 存储；
3. **隐私隔离红线**：
   - 发现 `桌面/FPGA-DNA/好东西.pdf` 为含有队员签名的承诺书扫描件，连同 2025 年承诺书公章原件、未脱敏人像原图，已全部彻底移出公开代码树，严格隔离于本地 `archive/submission-privacy/`。

---

## 4. 归档记录与处置总账 (Archive Ledger)

### 4.1 Git 入库资产
- 核心代码：`src/hw/` (34)、`src/sw/` (50)、`src/clients/` (21)、`src/tools/` (39)；
- 仿真体系：`sim/rtl/` (25)、`sim/golden/` (117)、`sim/host/` (21)；
- 构建制品：`build/artifact/`、`build/reports/`、`build/configs/`；
- 板测留证：`board/run-logs/` (32 个小写日志)；
- 数据用例：`data/` (42 组多媒体测试用例，约 108 MB)；
- 赛事文档：`report/design-report-2026.docx` (5.98 MB 权威底稿)、`report/design-report-2026.pdf` (2.24 MB)、`report/poster/`、`report/figures/v2/`、`report/tools/` (10 个打捞工具)；
- 历史档案：`docs/history/bench-arm/`、`docs/history/bench-cpu-server/`、`docs/history/experimental-hw/`、`docs/history/milestones/`、`docs/history/experiments/`。

### 4.2 本地完备归档 (`archive/`，不公开)
- 提交物压缩包：`archive/submission-2026/dna-readout-accelerator.rar` (59.1 MB，SHA-256: `ba315d4f...`)；
- 最终演示视频：`archive/submission-2026/提交视频.mp4` (104.3 MB，SHA-256: `fb0b4e02...`，实测时长 2分49秒71)；
- 上位机免装二进制：`archive/submission-2026/gui_app.exe` (29.1 MB)；
- 原始压测数据：`archive/board-evidence-2026-10/` (已硬链接去重至 183 MB)；
- 涉密隔离区：`archive/submission-privacy/` (手写签字授权书、公章扫描件、生活人像)；
- 参考文献库：`archive/references/` (参考论文、48核CPU测试原件 docx、DNA存储综述)。

### 4.3 释放存储收益
- WSL 内部清理：安全清理视频中间帧缓存（916 MB）、Vivado 崩溃缓存（141 MB）、冗余测试集（714 MB）、中间综合工程（700 MB）等，共释放空间 **约 2.8 GB**；
- 板测留证硬链接去重：释放空间 **约 1.73 GB**；
- Windows 侧清理（Phase 6 后执行）：清理旧平铺包、桌面冗余副本、PyInstaller 缓存等，释放空间 **约 1.2 GB**。
