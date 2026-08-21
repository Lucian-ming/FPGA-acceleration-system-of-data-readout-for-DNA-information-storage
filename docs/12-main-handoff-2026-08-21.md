# 12 · 主分支最终开发交接（2026-08-21）

本文面向下一位实际接手开发的人。目标是让接手者在不依赖口头背景的情况下，能够判断
当前代码能证明什么、不能证明什么，复跑离线判据，找到三端入口，并安全地完成首次上板验收。

## 1. 三十秒结论

- 当前开发基线是 `main`。`refactor/three-end-audit-20260816@ce41269` 的 14 个审查提交已在
  2026-08-21 经核查后用 `git merge --ff-only` 纳入主分支；无额外价值的审查分支随后已在
  本地和 GitHub 删除，后续只在 `main` 开发。
- 离线算法、Stage1/Stage2/Stage3 黄金 RTL、PS/主机单测、Python LDPC、完整 Vivado/Vitis
  构建和 Bootgen 制品复现均已通过。
- **项目仍未完成 G3 板端端到端验收。** 构建成功、GUI 成功、TCP 返回结果、生成图片或程序
  正常退出，都不能证明结果正确。
- 唯一最终判据：开发板真实回传的 64,800 bit 经 LDPC 后，重建 JPEG SHA-256 必须等于
  `fcd0cf90bd680e7bbdc203e3398119504da0897acac9e2117008b4efb6b1f2c3`。
- 上板必须使用 `hw/build/export/BOOT.bin`。两份历史 XSA 对应旧 Voter，不能作为当前实现。

## 2. Git 与工作区状态

### 2.0 接手前强制 Git 门禁

本项目只允许直接使用 `/home/lucian/projects/FPGA/FpgaAccelerationSystemOfDataReadout`，并绑定：

```text
https://github.com/Lucian-ming/FPGA-acceleration-system-of-data-readout-for-DNA-information-storage.git
```

禁止 `git init`、另行 clone 后另建项目或在本目录中创建嵌套仓库。任何 Agent 开始工作前必须运行：

```bash
cd /home/lucian/projects/FPGA/FpgaAccelerationSystemOfDataReadout
bash tools/verify_repo_binding.sh --remote
```

未通过绝对路径、`main`、`origin/main`、指定远端及 fetch/push 权限检查时，必须立即停止，且不得转去
其他项目。所有有意义修改都必须提交并立即 `git push origin main`；交接前必须运行
`bash tools/verify_repo_binding.sh --require-synced`，确认本地没有未推送提交。大型 Vivado/XSim 生成
目录继续只保存在本机，但可复现脚本、manifest、摘要和交接结论必须提交远端。

私有仓库接手者还必须满足以下条件：

1. 接受 GitHub 仓库邀请；仓库设置中应从 `Pending Invite` 变为已加入的 collaborator。
2. 账号至少具有 `Write` 权限，并使用 SSH key、HTTPS PAT/Git Credential Manager 或
   `gh auth login` 完成 GitHub 身份认证；GitHub 账号密码不能直接用于 Git push。
3. 配置 `git user.name` 和 `git user.email`，然后在现有项目目录运行门禁。禁止为验证权限而
   新建仓库或新 clone。
4. 若仓库 ruleset/branch protection 禁止直接推送 `main`，即使已有 `Write` 权限也不能直接推送；
   仓库所有者必须赋予 bypass 或调整规则，使本项目要求的 `git push origin main` 可以执行。
5. 第一次工作前必须看到 `git fetch origin` 和 `git push --dry-run origin HEAD:main` 成功；每次
   提交后实际推送，交接前确认 `main...origin/main` 为 `0 0`。

### 2.1 分支关系

合并前基线为：

| 引用 | 提交 | 含义 |
| --- | --- | --- |
| 原 `main` | `81986bc` | Stage2、D1/D2、C1~C4、P3/P5 离线基线 |
| 审查分支 | `ce41269` | 在原 main 上增加 R1~R5 三端修复、构建制品和交接记录 |

2026-08-21 合并使用 `--ff-only`，没有生成合并提交，也没有改写历史。审查分支确认没有未合并
价值后已在本地和 GitHub 删除；历史提交仍可从 `main` 追溯。当前只保留 `main` 与
`origin/main`，不得从旧审查提交另建长期分支。

接手后先执行：

```bash
git switch main
git fetch --prune origin
git status --short --branch
git log -5 --oneline --decorate
git rev-list --left-right --count main...origin/main
```

正常结果应为工作树无修改、`main...origin/main` 左右提交数 `0 0`。

### 2.2 “未提交更新”的处理结论

合并前在旧 `main` 上看到的未跟踪项是 `hw/build/dna_accel.*` 和 `hw/build/reports/`。
它们是 Vivado 构建工程、runs 和报告，不是源码修改。处理方式是把准确规则补入 `.gitignore`，
而不是删除本地构建证据或把约 157 MiB 工具缓存整体提交。

当前以下内容只保留在本机并被忽略：

| 路径 | 约占空间 | 处理原则 |
| --- | ---: | --- |
| `data/` | 54 MiB | R0.83 输入与黄金数据，只读；未经用户同意禁止修改、覆盖或删除 |
| `archive/` | 228 MiB | 历史提交资产，只读；RAR5 内容未完成来源审计 |
| `sw/workspace/` | 145 MiB | Vitis 平台、BSP、ELF 中间目录；独立交付 ELF 已进入 `export/` |
| `hw/build/dna_accel.*`、`hw/build/reports/` | 约 157 MiB | Vivado 工程/runs/本地报告；关键制品和精选报告已进入 `export/` |
| `.Xil/`、`*.jou`、`*.log`、`__pycache__/` | 临时状态 | 不提交；不要误判成源码变化 |

本次检查没有发现需要丢弃的源码或文档修改，因此没有执行 `git clean`、`rm` 或其他删除操作。

## 3. 当前验证矩阵

2026-08-21 现场复跑记录：

| 基线 | 命令 | 结果 |
| --- | --- | --- |
| 原 `main@81986bc` | `bash tools/run_sim.sh` | 8 项通过、0 项失败 |
| 审查分支 `ce41269` | `bash tools/run_sim.sh` | 11 项通过、0 项失败 |
| 审查分支 `ce41269` | `python3 tools/golden_model.py verify-code` | 反稀疏化与参考码字逐位一致 |
| 合并后 `main` | `(cd hw/build/export && sha256sum -c SHA256SUMS)` | 16 项制品/报告全部 OK |
| 合并后 `main` | Bootgen 重建后 `cmp` | 与交付 `BOOT.bin` 逐字节一致 |

审查分支的 11 项包括：

```text
desparsify_datapath / desparsifier_axi / srpe_batch
dna_ingress / dna_axil / differential_voter
wm_expand / ddr_layout / task_config / client_core / ldpc_decode
+ 三个生产顶层和 five_to_four_decoder 的语法检查
```

关键结果：

- Stage1：64 条读段分数不符 0、码字不符 0；2 条同分并列峰在允许范围。
- Stage2：`SCORE_MIN=67` 连续两轮和 `SCORE_MIN=0` 一轮，均为 1,266 拍/81,000 bit 逐位一致。
- Stage3：1,013 拍/64,800 bit 与黄金向量逐位一致，并覆盖随机背压和 AXI 边界。
- LDPC：88 bit 输入错误在 5 轮收敛，信息位错误归零，重建 JPEG 与原图逐字节相同。
- 完整实现：100 MHz，WNS `+0.145 ns`、WHS `+0.018 ns`，0 路由错误；报告在
  `hw/build/export/reports/`。

这些都是离线、仿真或构建证据，**不是 G3 板端证据**。

## 4. 系统数据流

```text
SE150 FASTQ
  -> PC first.py：每条生成正向和反向互补，位平面/LSB-first 打包
  -> TCP 0xBEEF 协议，192.168.1.10:7
  -> PS 裸机 lwIP：CONFIG/CAPS/WM/BATCH/POST、DDR/DMA 调度
  -> Stage1 PL：水印滑窗相关，40 B/read -> 48 B/read(position, score, codeword)
  -> Stage2 PL：按位置投票，SCORE_MIN=67 过滤 -> 81,000 bit 共识
  -> Stage2.5 PS：共识 XOR 水印 -> 81,000 bit 稀疏流
  -> Stage3 PL：5b->4b 反稀疏化 -> 64,800 bit LDPC 码字
  -> TCP 回传 8,100 B
  -> PC native_ldpc.py / tools/ldpc_decode.py -> 54,000 bit -> JPEG
```

三个 PL 核不直接串接，均经 DDR 中转，由 PS 状态机逐级配置、启动和轮询。Stage2.5 XOR
目前在 PS 软件中，不在 PL。任何性能重构都必须先保持这条功能链和黄金向量一致。

## 5. 固定数据契约

`docs/02-data-contract.md` 是唯一权威。当前比特流只支持 R0.83 SE150：

| 参数 | 当前值 | 约束/用途 |
| --- | ---: | --- |
| 水印/共识长度 | 40,500 nt / 81,000 bit | 两个位平面 |
| `READ_BPS` | 150 bp | 现有比特流不支持 SE250 |
| `NUM_LC/STRIDE/REF_LEN` | 50 / 807 / 957 | `NUM_LC*STRIDE=L-READ_BPS` |
| Stage1 输入/输出 | 40 B / 48 B 每条 | 输出含 300 bit 码字、pos、score |
| `SCORE_MIN` | 67，寄存器偏移 `0x30` | 与黄金向量 `int(0.45*150)` 一致 |
| Stage2 输出 | 81,000 bit / 1,266 拍 | 最后一拍仅 40 bit 有效 |
| Stage3 输出 | 64,800 bit / 1,013 拍 | TCP 实际回传 8,100 B |
| 最大合法记录数 | 107,968 | 必须非零且为 64 的倍数 |

三端统一使用位平面布局和字节内 LSB-first。禁止单独修改 Python、PS 或 RTL 中任意一端的
打包规则；格式变化必须先更新 `docs/02-data-contract.md`，再成对修改并重生成黄金向量。

SE250 不是换一个常量：它需要 250 bp、500 bit 码字、63 B 输入、72 B Stage1 输出，以及
`50/805/1055` 几何和更宽 RTL 数据通路。当前 CAPS 必须如实只报告 SE150。

## 6. 三端代码入口

| 范围 | 主要入口 | 修改前必读 |
| --- | --- | --- |
| 数据契约/算法 | `docs/02-data-contract.md`、`tools/golden_model.py` | `docs/01-architecture.md` |
| 上位机任务编排 | `clients/python/first.py` | `task_protocol.py`、`protocol.py` |
| 上位机 LDPC | `clients/python/native_ldpc.py`、`ldpc_pipeline.py` | `tools/ldpc_decode.py` |
| PS 协议和流水线 | `sw/app/echo.c`、`echo.h` | `task_config.h`、`ddr_layout.h`、`wm_expand.h` |
| Stage1 | `hw/ip/Dna_accelerator_core_1_0/hdl/srpe_batch.v` | Stage1/ingress/AXI-Lite TB |
| Stage2 | `hw/ip/differential_voter_1_0/hdl/differential_voter_v1_0.v` | `tb_differential_voter.v` |
| Stage3 | `hw/ip/desparsification_decoder_1_0/hdl/` | `tb_desparsifier.v` |
| BD/约束/构建 | `hw/scripts/bd.tcl`、`build.tcl`、`hw/constr/top.xdc` | `collect_info.tcl` |
| 固件构建 | `sw/scripts/create_vitis.tcl` | `sw/linker/lscript.ld` |

`srpe.v`、Voter 的旧 M00/S00 模板和 `five_to_four_decoder.v` 已标为遗留/废弃，不在当前
生产数据路径。不要因为文件名看起来像“主模块”就接回顶层。

## 7. TCP、寄存器与 DDR

协议顺序是：CAPS 查询 -> CONFIG -> WM -> BATCH x N -> POST -> RESULT。未 CONFIG 就发送
WM/BATCH/POST、声明条数与实收不一致、非 64 倍数或越界任务，都必须返回 `PKT_ERROR`。

IP 基址：

| IP | 基址 |
| --- | --- |
| DNA Accelerator | `0x43C0_0000` |
| Desparsifier | `0x43C1_0000` |
| Voter | `0x43C2_0000` |

DDR 关键区：水印 `0x1000_0000`，展开水印 `0x1004_0000`，读段 `0x1010_0000`，Stage1
输出 `0x1060_0000`，Stage2 输出 `0x1100_0000`，Stage3 输出 `0x1110_0000`。实际 cache
flush/invalidate 和 Voter 条数必须使用任务实收条数，不能恢复固定 `TOTAL_READS=108000`。

完整包格式、错误码、寄存器偏移、DDR 区间和状态机顺序只看 `docs/05-interfaces.md`。

## 8. 离线复跑

环境：Python >= 3.8、Icarus Verilog、NumPy、Pillow；硬件重建使用 Vivado/Vitis 2022.2。

```bash
python3 -m pip install -r clients/python/requirements.txt
python3 tools/golden_model.py verify-code
bash tools/run_sim.sh
python3 tools/ldpc_decode.py verify
```

只调单级时可用：

```bash
bash tools/run_sim.sh stage1
bash tools/run_sim.sh stage2
bash tools/run_sim.sh axi
bash tools/run_sim.sh ingress
bash tools/run_sim.sh dna_axil
bash tools/run_sim.sh host
```

不要把 `tb_dna_quick.v` 编译通过当功能判据；权威判据是 `run_sim.sh` 收编的黄金 Testbench。

## 9. 构建和交付制品

当前最小完整交付集在 `hw/build/export/`：

| 文件 | SHA-256 |
| --- | --- |
| `BOOT.bin` | `5b7f9840cff67fc36a1c5cdcefb56a8c7581956460c4d97cab724dff8d92b711` |
| `dna_accel.xsa` | `aed6f74ab5f2ef5fcd5998ddd575834e9dd68d8d4f3fbdb76065da0f87df92cf` |
| `top_bd_wrapper.bit` | `c3a365a02b76daff29e52acd694c2457f25cd3a44f553f169baf45f9a3f7d25f` |
| `dna_lwip_app_board_20260816.elf` | `fd88dce5909f522a7255ca6ae1fe114539dcefa0a2e5bef0b6ca94a00a4cfef4` |
| `fsbl.elf` | `6575e43f96a1a1d95e954590a4a7c7987d20f18f77f448f7a9067b19dcb78cb0` |

先验哈希：

```bash
(cd hw/build/export && sha256sum -c SHA256SUMS)
```

重新构建：

```bash
vivado -mode batch -source hw/scripts/build.tcl
xsct sw/scripts/create_vitis.tcl -tclargs \
  xsa="$PWD/hw/build/export/dna_accel.xsa"
```

从已跟踪组件验证 BOOT 可复现：

```bash
/tools/Xilinx/Vitis/2022.2/bin/bootgen \
  -image sw/boot/dna_board_20260816.bif \
  -arch zynq -o /tmp/BOOT-rebuilt.bin -w on
cmp /tmp/BOOT-rebuilt.bin hw/build/export/BOOT.bin
```

Bootgen 会报告 Zynq bitstream 分区地址范围重叠 warning；已读回确认分区类型正确且镜像可复现，
不要仅凭该 warning 覆盖或丢弃现有交付件。

## 10. 首次上板验收步骤

1. 校验并使用 `hw/build/export/BOOT.bin` 启动板卡；通过 UART 记录 FSBL、网络初始化和 TCP
   server 启动日志。板端静态地址为 `192.168.1.10/24`，网关 `192.168.1.1`，TCP 端口 7。
2. 主机设置同网段地址，先用 `--dry-run` 核对任务几何、记录数和 CONFIG CRC，不连接板端：

```bash
python3 clients/python/first.py \
  --watermark "data/R0.83_data/Source data/Watermark sequences/r0.83_watermark.txt" \
  --reads "data/R0.83_data/Sequencing data/DNA-40.5Kb-MC-SE150.fastq" \
  --limit 2048 --orient both --score-min 67 --dry-run
```

3. 去掉 `--dry-run`，显式指定输出，执行 2,048 条原始读段的双向测试。双向后是 4,096 条
   Stage1/Stage2 记录，满足 64 倍数约束：

```bash
python3 clients/python/first.py \
  --ip 192.168.1.10 --port 7 \
  --watermark "data/R0.83_data/Source data/Watermark sequences/r0.83_watermark.txt" \
  --reads "data/R0.83_data/Sequencing data/DNA-40.5Kb-MC-SE150.fastq" \
  --limit 2048 --orient both --score-min 67 \
  --output /tmp/fpga-dec-input.txt
```

4. 译码并生成图片：

```bash
python3 tools/ldpc_decode.py decode /tmp/fpga-dec-input.txt \
  -o /tmp/fpga-decoded-bits.txt --image /tmp/fpga-decoded.jpg
sha256sum /tmp/fpga-decoded.jpg
```

5. 只有哈希严格等于
   `fcd0cf90bd680e7bbdc203e3398119504da0897acac9e2117008b4efb6b1f2c3` 才关闭 G3。
6. 保存本次输入文件哈希、CONFIG/CAPS 内容、读段数、每级 DDR 中间输出、UART/TCP 日志、
   回传 bitstream、LDPC 迭代结果和最终图片哈希，回填 `docs/03-status.md`。

禁止从 `data/R0.83_data/` 或 `archive/` 复制 `dec_input.txt`、`decoded_bits.txt`、结果图片或
`codeword_R083.txt` 进入生产路径。黄金文件只能在测试代码中作为显式比较对象。

## 11. 尚未完成与优先级

### P0：G3 板端端到端验收

当前唯一阻塞主路径。重点观察：

- CAPS/CONFIG/WM/BATCH/POST 应答顺序和错误恢复。
- PS cache flush/invalidate 后 DDR 对 PL/CPU 的可见性。
- 水印区域切换时 `wm_waddr` 是否从 0 开始，50 次 DMA/preload 时序是否正确。
- Stage1 TX/RX BD 实际完成数、Stage2/Stage3 写拍数和末拍有效字节。
- 二次任务是否真正清零 Voter 累加器。

### P1：验收后工程事项

- A7 LICENSE 和第三方声明：需要用户确认代码权属及许可证类型。
- P7 Stage1 架构改造：当前搜索吞吐低，若追求 100 倍级加速需评估 XC7Z020 或更大器件。
- PL 几何参数化/SE250：只能在 SE150 G3 闭环后推进，不能与首次验收混在一起。
- PS `echo.c` 仍较大；跨文件拆分会改变 Vitis 导入和全局状态边界，应另开小批次回归。

## 12. 风险和禁止事项

- 不得宣称“当前代码已经端到端正确”；G3 尚无真实板端证据。
- 不得修改、重命名或覆盖 `data/R0.83_data/`；`archive/` 和历史 XSA 保持只读。
- 不得把 `TOTAL_READS`、`NUM_LC`、`STRIDE`、`REF_LEN` 当互不相关的固定常量。
- 不得把历史 `hardware.xsa`/`design_2_wrapper.xsa` 用作当前 RTL 的构建证据。
- 不得把 GUI、EXE 退出码、图片存在或仿真编译通过当正确性判据。
- 不得在当前项目目录中再套一层 clone/repository；直接使用此 checkout。
- 不得把本项目复制或 clone 成平行项目继续开发；其他 Agent 必须绑定并直接推送上述 GitHub 仓库。
- 不得留下仅本地提交；每次提交都必须推送 `origin/main` 并核对 `main...origin/main`。
- 不得为清理工作区删除 `data/`、`archive/`、`sw/workspace/` 或 Vivado 构建结果。
- Git 清理前先看 `git status` 和 `.gitignore`；生成目录被忽略是预期状态，不是未提交代码。

## 13. 建议的接手顺序

1. 阅读 `docs/02-data-contract.md`、`docs/03-status.md`、本文和 `docs/05-interfaces.md`。
2. 复跑 `verify-code`、`run_sim.sh`、LDPC verify 和制品 SHA-256，建立本机可信基线。
3. 不改代码，先完成一次 2,048 条读段的板端协议联调，采集每一级证据。
4. 根据第一处实际不一致定位到 PC、PS、Stage1、Stage2、Stage2.5 或 Stage3；一次只替换一级，
   用对应黄金向量锁定边界。
5. G3 哈希闭环后回填状态文档并提交；之后再讨论性能、SE250、LDPC 上板或代码重构。

遇到冲突时，事实优先级是：真实文件/哈希和现场复跑结果 > `docs/02-data-contract.md`/
`docs/05-interfaces.md` 当前规范 > 本交接 > 历史快照和旧技术说明。
