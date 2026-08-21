# 11 · GitHub 两分支同步与交接（2026-08-21）

## 结论

本次同步覆盖两个本地开发分支：

| 分支 | GitHub 状态 | 定位 |
| --- | --- | --- |
| `main` | 已推送至 `81986bc` | 2026-08-16 离线任务完成基线，包含 Stage2 黄金 TB、D1/D2、C1~C4、P3、P5 |
| `refactor/three-end-audit-20260816` | 本交接提交推送后与远端同名分支对齐 | 当前完整可上板基线，包含三端审查修复、可复现构建和独立启动制品 |

两个分支不是相互冲突的两套历史：`main@81986bc` 是审查分支的祖先。审查分支包含
`main` 的全部内容，并在其上增加 R1~R5 审查修复、构建制品和本交接记录。上板与后续开发
应从 `refactor/three-end-audit-20260816` 继续；`main` 保留为较小、稳定的离线基线。

## 本次实际上传

### `main` 补推的 3 个提交

```text
be51e10 feat(stage2): Voter 黄金 Testbench 与 B13~B16/C4 五缺陷修复
758597f feat: 完成除上板外全部离线任务（D1/D2、C1~C4、A2/A6/A8/A9、P5）
81986bc feat(p3): 任务配置化——PKT_CONFIG/PKT_CAPS 运行时下发（离线部分）
```

推送范围为 `276391c..81986bc`，推送后 `main...origin/main` 左右提交数为 `0 0`。

### 审查分支新增交付提交

`d759e8c build(hw): 补齐可上板独立制品与验证报告` 新增约 4 MiB 的最小完整交付集：

| 文件 | 字节数 | SHA-256 |
| --- | ---: | --- |
| `hw/build/export/BOOT.bin` | 2,319,112 | `5b7f9840cff67fc36a1c5cdcefb56a8c7581956460c4d97cab724dff8d92b711` |
| `hw/build/export/dna_accel.xsa` | 680,134 | `aed6f74ab5f2ef5fcd5998ddd575834e9dd68d8d4f3fbdb76065da0f87df92cf` |
| `hw/build/export/top_bd_wrapper.bit` | 2,083,850 | `c3a365a02b76daff29e52acd694c2457f25cd3a44f553f169baf45f9a3f7d25f` |
| `hw/build/export/dna_lwip_app_board_20260816.elf` | 943,824 | `fd88dce5909f522a7255ca6ae1fe114539dcefa0a2e5bef0b6ca94a00a4cfef4` |
| `hw/build/export/fsbl.elf` | 228,672 | `6575e43f96a1a1d95e954590a4a7c7987d20f18f77f448f7a9067b19dcb78cb0` |

同时上传 `hw/build/export/reports/` 中完整实现及四个关键 RTL 核的时序/资源报告
（合计 1,021,883 B），以及 `SHA256SUMS` 和使用说明。BIF 已改为只引用这些受 Git 跟踪的
独立组件，不再依赖被忽略的 `sw/workspace/` 或 `hw/build/dna_accel.runs/`。

## 没有上传的本地内容

以下内容继续按 `.gitignore` 和项目红线排除，不属于遗漏：

| 本地内容 | 规模 | 原因 |
| --- | ---: | --- |
| `data/` | 54 MiB | R0.83 只读数据；未经同意不得修改或覆盖，来源和哈希已记录在 `docs/reference/` |
| `archive/` | 228 MiB | 历史归档只读；RAR5 尚待来源/哈希审计，不导入生产代码 |
| `sw/workspace/` | 145 MiB | Vitis 平台、缓存和同一 ELF/bitstream 的重复副本；必要独立制品已转存到 `export/` |
| Vivado 工程缓存和 runs | 约 157 MiB | 可由 Tcl 重建；上传会造成大量工具生成噪声，关键 bitstream/XSA/报告已上传 |
| `.git-data/`、`.Xil/`、日志、Python cache | 本机状态 | Git 元数据或临时文件，不是项目交付内容 |

仓库原有两份历史 XSA 保持原样；`hardware.xsa`/`design_2_wrapper.xsa` 不是当前可上板构建证据。

## 本次验证

```bash
# 上传前先刷新远端，确认没有未知分叉
git fetch --prune origin

# 两分支包含关系：输出应为 0，说明 main 是审查分支祖先
git rev-list --count refactor/three-end-audit-20260816..main

# 制品逐文件哈希
(cd hw/build/export && sha256sum -c SHA256SUMS)

# 从受 Git 跟踪的三个启动组件重建，并与交付镜像逐字节比较
/tools/Xilinx/Vitis/2022.2/bin/bootgen \
  -image sw/boot/dna_board_20260816.bif \
  -arch zynq -o /tmp/BOOT-rebuilt-20260821.bin -w on
cmp /tmp/BOOT-rebuilt-20260821.bin hw/build/export/BOOT.bin

# 推送后两个分支都必须输出 0 0
git rev-list --left-right --count main...origin/main
git rev-list --left-right --count \
  refactor/three-end-audit-20260816...origin/refactor/three-end-audit-20260816
```

本次只整理和同步 Git/交付制品，没有修改 RTL、PS 或上位机逻辑，因此未重复执行耗时的
全量仿真与 Vivado 实现。最近一次代码判据仍是 2026-08-16 的 `bash tools/run_sim.sh`：
11 项通过、0 项失败；完整实现报告显示 100 MHz 下 WNS `+0.145 ns`、WHS `+0.018 ns`。

## 接手后的唯一主路径

1. 检出 `refactor/three-end-audit-20260816`，先执行 `sha256sum -c SHA256SUMS`。
2. 使用 `hw/build/export/BOOT.bin` 启动开发板，不得改用两份历史 XSA 对应的旧 bitstream。
3. 用 `clients/python/first.py` 完成 CAPS/CONFIG/WM/BATCH/POST 联调并保存真实 FPGA 回传。
4. 对真实回传执行 `tools/ldpc_decode.py decode`；只有重建图片 SHA-256 等于
   `fcd0cf90bd680e7b...b6b1f2c3`，才可关闭 G3 并宣称端到端正确。

GitHub 同步、构建成功、GUI 成功或 BOOT.bin 可生成都不能替代第 4 步的板端验收。
