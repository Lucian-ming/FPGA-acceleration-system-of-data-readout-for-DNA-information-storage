# 23 · 未来三阶段行动计划与 SE250 点亮实施方案（2026-09-04）

本文规划项目在第一波与第二波并行任务全面闭环后的**后续三个推进阶段**，给出详细步骤、判据门禁、资源互斥矩阵与执行子 Agent 的提示词。

---

## 0. 一页结论与起点事实

### 起点事实（2026-09-04 晚最新状态）
1. **G3 SE150 端到端已彻底闭环并多次验证**：
   - 图片 SHA-256 稳定匹配 `fcd0cf90bd680e7bbdc203e3398119504da0897acac9e2117008b4efb6b1f2c3`；
   - 水印预载优化完成，固定开销从 28.90s 压降至 **4.93s**（全量耗时从 133s 降至 102s）；
   - 三轮跨规模连续任务（8,192 脏轮 → 4,096 → 4,096）与连续运行无退化全部闭环；
2. **PS 固件解耦彻底完成（`ps-refactor` S1~S6 全部交付）**：
   - 单体 `echo.c` 从 2,335 行大幅精简解耦至 **578 行**，拆出 8 个内聚模块，消除了 25 个全局静态变量的隐式耦合；
   - 植入了 B29 诊断加固探针（发送重试计数、`tcp_sndbuf` 监测、物理 ACK 追踪）；
   - 主机侧 816 行行为轨迹 100% 逐行完全一致（Zero Regression）；
   - 物理硬件连续双轮上板（弄脏轮 `score_min=0` → 判据轮 `score_min=67`）全绿通过，四级 DDR 4/4 级全绿！
3. **SE250 硬件基础与接口仿真全过（`se250-hw` S1~S4 全部交付）**：
   - **阶段 S1**：移位寄存器改造彻底消灭了 Top 1~5 300:1 MUX 关键路径，WNS 提升至 +0.568ns，BRAM 压降至 83.33%；
   - **阶段 S2**：黄金向量 `tests/golden/se250/` 就绪（16 个文件，含反向 G1 鉴别力哨兵）；
   - **阶段 S3**：Gate A OOC 综合评估三门槛全面超额达标（BRAM 45/52 块，WNS +1.356ns，LUT 7,773 / 12,000），**彻底确认现有 XC7Z010 芯片资源充足，无需更换芯片**；
   - **阶段 S4**：XSim 接口级仿真套件 13/13 项全过，精准自证了 72B 记录下第 56 条记录（8+1 拍）的 4KB 跨页拆分点（B20 特别判据）。

### 三大阶段路线图

```
┌────────────────────────────────────────────────────────────────────────────────────────┐
│                                   未来推进三阶段路线图                                  │
├────────────────────────────────────────────────────────────────────────────────────────┤
│ 【阶段一】近程攻坚：SE250 首次上板点亮 (S5) & 混用防呆验证 & S6 SE150 回归             │
│   - Vivado 全量整机构建 (生成 SE250 bitstream & XSA)                                  │
│   - 已解耦固件配置切换为 SE250 宏 (72B/条, 阈值 112)，编译新 ELF 与 BOOT.bin           │
│   - 4,096 记录上板首次点亮 (唯一判据图片哈希 fcd0cf90...f2c3 & 四级取证)                │
│   - 运行时混用防呆验证 (SE150 客户端下发配置连接 SE250 必须被拒绝码 2 拦下)             │
│   - 阶段 S6：SE150 黄金基线回归复验                                                   │
├────────────────────────────────────────────────────────────────────────────────────────┤
│ 【阶段二】中程突破：B29 网络挂起根治加固 & SE250 全量点亮 (S7)                         │
│   - 利用新植入的 B29 探针，根治大算力任务后 TCP 物理未上线问题 (心跳包/发送队列优化) │
│   - SE250 DDR 布局上移调整 (按 docs/20 §5.3 突破 5.24MB 读段区限制)                   │
│   - 运行 SE250 全量 129,600 条记录，拟合 SE250 处理时长模型                           │
│   - 闭环全量规模作为前置轮次的多轮连续任务                                            │
├────────────────────────────────────────────────────────────────────────────────────────┤
│ 【阶段三】长效交付：技术债彻底清零与交付资产归档                                       │
│   - RTL 源码文件编码彻底标准化 (GBK → UTF-8，配置 .gitattributes 防乱码)              │
│   - 上位机 Python 客户端 (GUI/CLI) 双模式自适应与生产环境独立打包                      │
│   - 架构优化报告（MUX移位寄存器/LUTRAM解BRAM）学术素材与最终交接文档归档               │
└────────────────────────────────────────────────────────────────────────────────────────┘
```

---

## 1. 阶段一实施方案（当前核心攻坚）

阶段一的目标是完成 **SE250 在物理硬件上的首次端到端闭环**（即 `docs/20` 中的阶段 S5），并完成混用防呆与 SE150 回归。

### 1.1 步骤一：Vivado SE250 整机全量构建
- **执行**：运行 `vivado -mode batch -source hw/scripts/build.tcl`；
- **产物**：
  - `hw/build/export/top_bd_wrapper.bit`（SE250 新比特流）
  - `hw/build/export/dna_accel.xsa`（SE250 新硬件包）
  - `hw/build/reports/` 综合与实现时序利用率报告；
- **判据**：
  - 综合与实现无致命错误（errors = 0）；
  - WNS @ 100MHz $\ge 0$（预期 $\ge +0.3\text{ ns}$）；
  - BRAM Tile $\le 52$（预期约 45.0 块）；
  - 归档 SE250 比特流与报告。

### 1.2 步骤二：已解耦固件的 SE250 常量切换与编译
得益于第二波刚刚完成的固件模块化拆分，固件参数修改被极大简化，仅需在已解耦的头文件中按 `docs/20 §3.5` 修改宏定义：
- `READ_BASES_PER_READ`：`150U` $\to$ `250U`
- `READ_SIZE_BYTES`：`40U` $\to$ `64U`（对齐到 4 字节）
- `WM_STRIDE` / `WM_REF_LEN`：`807U` / `957U` $\to$ `805U` / `1055U`
- `DNA_ACC_RESULT_PACKED_BYTES`：`48U` $\to$ `72U`
- `VOTER_INPUT_BYTES_PER_READ`：`48U` $\to$ `72U`
- `VOTER_SCORE_MIN`：`67U` $\to$ `112U`（默认值，实际经 `PKT_CONFIG` 下发）
- **编译**：在 `sw/workspace/dna_lwip_app_b27/Debug` 执行 `make clean && make all`；
- **打包**：使用 `bootgen` 结合 SE250 的 `fsbl.elf`、`top_bd_wrapper.bit`、`dna_lwip_app_b27.elf` 生成 SE250 版 `BOOT.bin`；
- **刷新**：同步更新 `hw/build/export/` 与 `SHA256SUMS`。

### 1.3 步骤三：SE250 首次上板点亮实测（4,096 条记录）
- **规模**：源读段 2,048 条（`--orient both` $\to$ 4,096 条记录，每条 250 bp）；
- **执行**：
  ```bash
  bash tools/run_g3.sh --limit 2048 --read-bps 250 --score-min 112 --reads "data/R0.83_data/Sequencing data/DNA-40.5Kb-MC-SE250.fastq" --tag se250-s5-lighting
  ```
- **正向硬判据（全部必须满足）**：
  1. 板端回传经 `tools/ldpc_decode.py` 译码后图片 SHA-256 必须严格等于：
     `fcd0cf90bd680e7bbdc203e3398119504da0897acac9e2117008b4efb6b1f2c3`
  2. 回传原始比特流与 `tests/golden/se250/dec_input.txt` 差异为 0/64,800；
  3. 四级 DDR 取证（`tools/board_stage_check.py`）4/4 级全绿（展开水印 52,750 符号、Stage1 输出、Stage2 误码率 $\le 0.05\%$、Stage3 误码率 $0.00\%$）；
  4. 板端处理时长 $t_{\text{result}} < 180\text{ s}$（预估约 8~15s）。

### 1.4 步骤四：运行时混用防呆验证（反向判据，必须能失败）
- **背景**：`AGENTS.md` 规定“SE150 与 SE250 绝不可混用”，这是两套完全不同的硬件几何常数。硬件与固件必须具备明确的安全闸门。
- **验证动作**：
  - 在板端烧录 SE250 比特流与固件后，上位机强制使用 SE150 参数（`read_bps=150`）发起任务下发；
  - **判定标准**：板端**必须坚决拒绝**该任务，返回 `PKT_CONFIG` 拒绝码 2（`task_config.h:113`：`read_bps mismatch`），上位机报错退出且不得启动数据传输；
  - 故障注入自证成立：反向证明防呆逻辑有效。

### 1.5 步骤五：阶段 S6 SE150 黄金回归
- **执行**：恢复归档的 SE150 制品与固件，执行标准 `bash tools/run_g3.sh --limit 2048 --tag se150-s6-regression`；
- **判据**：图片 SHA-256 依然为 `fcd0cf90…f2c3`，四级取证全绿，证明整套仓库保持双几何兼容与零回归。

---

## 2. 阶段二与阶段三实施方案

### 阶段二：B29 网络挂起根治与 SE250 全量推进
1. **B29 根除加固**：
   - 在上板全量长任务（>100s 或弄脏轮数分钟）时，观察 `ps-refactor` 植入的探针日志（`retries`, `sndbuf_zero_cnt`, `sndbuf_avail`）；
   - 若为 lwIP 缓冲区耗尽导致丢包未重发，在 `pipeline` 中增加定期 `keep_tcp_alive` 或发送心跳数据帧；若为 Windows 客户端连接超时，在客户端增加保活探针；
   - 彻底闭环“全量规模弄脏轮作为前置的多轮连续任务”。
2. **SE250 全量规模推进（阶段 S7）**：
   - 目标：全量 64,800 条源读段（129,600 条记录 × 250 bp）；
   - 按 `docs/20 §5.3` 执行 DDR 基址上移（`DDR_DNA_ACC_OUT_BASE 0x10900000`，`DDR_VOTER_OUT_BASE 0x11200000` 等），扩充读段区至 8.38MB；
   - 验证 TX BD 环容纳 2,025 帧、RX BD 环回绕 127 次无丢包；
   - 上板拟合 SE250 的时长数学模型（预测 $t \approx 5\text{s} + 1.5\text{ms/条} \times N$）。

### 阶段三：长效工程化交付
1. **源码编码标准化**：
   - 将 `hw/ip/` 下历史 GBK 编码文件批量转为 UTF-8；
   - 配置 `.gitattributes`（`*.v text eol=lf working-tree-encoding=UTF-8`）；
2. **交付打包与上位机自适应**：
   - 上位机自动读取 FASTQ 头行检测读长（150 bp 或 250 bp），自适应配置 `read_bps` 与 `score_min`；
   - 独立打包发布，确保生产环境彻底隔离历史黄金测试数据；
3. **技术资产与学术总结归档**：
   - 总结输出 FPGA 架构优化论文/报告章节（移位寄存器时序重构、LUTRAM 替代 BRAM、零拷贝流水线）。

---

## 3. 资源约束与纪律约定

1. **Git 提交纪律**：
   - 严禁 `git add -A` / `git add .`；
   - 每次提交必须指定具体路径：`git commit -m "..." -- <paths>`；
   - 提交前必须 `git pull --rebase`，推送到 `origin/main`；
   - 保持 `tools/verify_repo_binding.sh --require-synced` 在 `0/0`。
2. **板卡令牌管理**：
   - 当前板卡处于空闲状态；
   - 阶段一中，整机构建与固件编译阶段不需要板子；只有在上板首次点亮（步骤 1.3/1.4/1.5）时才独占板卡。

---

## 4. 阶段一子 Agent 提示词（直接可用）

### Agent：`se250-lighting`（SE250 首次上板点亮）

```
你接手 FPGA DNA 项目的「SE250 首次上板点亮与防呆验证」任务（agent 名称：se250-lighting）。仓库在 /home/lucian/projects/FPGA/FpgaAccelerationSystemOfDataReadout。
动手前按顺序读完：AGENTS.md、CLAUDE.md、docs/23-next-phase-plan-2026-09-04.md 全文（你的核心任务书）、docs/20-se250-study-2026-08-30.md（§3.5 固件宏与 §6 阶段 S5/S6）。
然后在 view.md 上以 --agent se250-lighting 登记（使用 tools/agent_view.sh start --agent se250-lighting --doing "..." --why "..." --next "..."）。

【前情资产与现状】
1. SE250 硬件已通过 Gate A OOC 综合（BRAM 45 块，WNS +1.356ns）与 XSim 13/13 接口仿真，代码在 hw/ip/。
2. PS 固件已解耦重构完成（echo.c 578 行，8 大模块），单测与行为轨迹全绿，代码在 sw/app/。
3. tests/golden/se250/ 黄金向量已完备，反向哨兵已生效。
4. 当前开发板（ZYNQ ECO R6）处于完全空闲状态，主会话 main 已为你授权板卡使用权！

【你的任务与执行步骤】
第一步：Vivado SE250 整机全量构建（阶段 S5 硬件）
1. 在 view.md 上 update：正在运行 Vivado 整机构建（hw/scripts/build.tcl），预计耗时 30~50 分钟。
2. 执行构建：vivado -mode batch -source hw/scripts/build.tcl。
3. 检查 reports/ 下的 timing 与 util 报告，确认 WNS >= 0 且 BRAM/LUT 达标。
4. 产物确认：hw/build/export/ 包含新生成的 top_bd_wrapper.bit 与 dna_accel.xsa。

第二步：固件切换 SE250 参数并编译（阶段 S5 固件）
1. 按照 docs/20 §3.5 修改 sw/app/echo.h 中的相关宏定义为 SE250 规格：
   - READ_BASES_PER_READ 250U
   - READ_SIZE_BYTES 64U
   - WM_STRIDE 805U, WM_REF_LEN 1055U
   - DNA_ACC_RESULT_PACKED_BYTES 72U, VOTER_INPUT_BYTES_PER_READ 72U
   - VOTER_SCORE_MIN 112U
2. 在 sw/workspace/dna_lwip_app_b27/Debug 执行 make clean && make all，生成新 ELF。
3. 拷贝新 ELF 到 hw/build/export/dna_lwip_app_b27.elf。
4. 使用 bootgen -image sw/boot/dna_board_b27.bif -arch zynq -o hw/build/export/BOOT.bin -w on 生成新 BOOT.bin。
5. 刷新 hw/build/export/SHA256SUMS，并用 sha256sum -c SHA256SUMS 复核。

第三步：SE250 首次上板点亮实测（4,096 条记录）
1. 在 view.md 上 update：【持有板子】执行 SE250 4,096 条记录首次点亮。
2. 运行上板命令：
   bash tools/run_g3.sh --limit 2048 --read-bps 250 --score-min 112 \
     --reads "data/R0.83_data/Sequencing data/DNA-40.5Kb-MC-SE250.fastq" \
     --tag se250-s5-lighting
3. 判定正向判据：
   - 最终图片 SHA-256 必须严格匹配 fcd0cf90bd680e7bbdc203e3398119504da0897acac9e2117008b4efb6b1f2c3！
   - 四级 DDR 取证 4/4 级全绿！

第四步：运行时混用防呆验证（反向判据）
1. 用 SE150 参数（--read-bps 150）尝试连接板端：
   验证必须被板端拒绝（拒绝码 2: read_bps 不符），客户端报错退出且无任何数据下发。
2. 证明混用闸门有效。

第五步：留证、归档与交付
1. 将实测数据、WNS、资源利用率及板上耗时写入 docs/20 §6 阶段 S5 和 docs/23。
2. 留证日志归档在 docs/board/run-logs/。
3. 遵守 Git 纪律：带路径提交 git commit -m "..." -- <paths>，推送到 origin/main。
4. 运行 tools/agent_view.sh done --agent se250-lighting ... 释放板卡。
```
