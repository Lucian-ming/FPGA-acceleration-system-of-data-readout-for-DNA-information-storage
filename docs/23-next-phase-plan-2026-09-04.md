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

4. **SE250 首次上板点亮 (S5) 与混用防呆验证彻底闭环（`se250-lighting` 2026-09-04 交付）**：
   - **整机构建**：Vivado 全量实现后 WNS 达 **+0.586 ns**，BRAM 降至 **47.5 块 (79.17%)**，LUT 11,850；
   - **首次上板**：4,096 条记录（2,048 条源读段）物理上板运行耗时仅 **12s**（网络/板端 11.35s，8,100 B），图片 SHA-256 逐位精准匹配 `fcd0cf90bd680e7bbdc203e3398119504da0897acac9e2117008b4efb6b1f2c3`；
   - **四级 DDR 取证**：4/4 级全部全绿（展开水印 52,750 符号、Stage1 72B 输出、Stage2 误码率 0.02%、Stage3 误码率 0.00%）；
   - **混用防呆双层硬闸门**：上位机探针检测阻断（`ValueError: 板端只支持 250bp`）与板端协议层坚决拒绝（`reply code=2`）均 100% 验证通过。

### 三大阶段路线图

```
┌────────────────────────────────────────────────────────────────────────────────────────┐
│                                   未来推进三阶段路线图                                  │
├────────────────────────────────────────────────────────────────────────────────────────┤
│ 【阶段一】近程攻坚：SE250 首次上板点亮 (S5) & 混用防呆验证 [已完成] & S6 SE150 回归      │
│ 【阶段一】近程攻坚：SE250 首次上板点亮 (S5) & 混用防呆验证 & S6 SE150 回归 [✅ 全面闭环] │
│   - [x] Vivado 全量整机构建 (生成 SE250 bitstream & XSA)                               │
│   - [x] 已解耦固件配置切换为 SE250 宏 (72B/条, 阈值 112)，编译新 ELF 与 BOOT.bin        │
│   - [x] 4,096 记录上板首次点亮 (唯一判据图片哈希 fcd0cf90...f2c3 & 四级取证)             │
│   - [x] 运行时混用防呆验证 (SE150 客户端下发配置连接 SE250 必须被拒绝码 2 拦下)          │
│   - [x] 阶段 S6：SE150 黄金基线回归复验 (已闭环，9s 出图，四级取证 4/4 全绿)           │
├────────────────────────────────────────────────────────────────────────────────────────┤
│ 【阶段二】中程突破：B29 网络挂起根治加固 & SE250 全量点亮 (S7) [✅ 全面闭环]              │
│   - [x] 植入 B29 网络保活与投递结算机制，根治长算力任务后结果挂起 (ARP刷新/投递结算)    │
│   - [x] SE250 DDR 布局上移调整 (按 docs/20 §5.3 突破 5.24MB 读段区限制)                   │
│   - [x] 修复 B30 Voter 1s 看门狗超时缺陷 (无进展看门狗 + 10s 全局上限 + 固件 ERROR 熔断)  │
│   - [x] SE250 全量 129,600 记录点亮闭环 (唯一判据图片哈希逐位吻合 & 四级 DDR 全绿)        │
├────────────────────────────────────────────────────────────────────────────────────────┤
│ 【阶段三】长效交付：技术债彻底清零与交付资产归档                                       │
│   - RTL 源码文件编码彻底标准化 (GBK → UTF-8，配置 .gitattributes 防乱码)              │
│   - 上位机 Python 客户端 (GUI/CLI) 双模式自适应与生产环境独立打包                      │
│   - 架构优化报告（MUX移位寄存器/LUTRAM解BRAM）学术素材与最终交接文档归档               │
└────────────────────────────────────────────────────────────────────────────────────────┘
```

---

## 1. 阶段一实施方案（当前核心攻坚）
## 1. 阶段一实施方案（✅ 100% 全面闭环）

阶段一的目标是完成 **SE250 在物理硬件上的首次端到端闭环**（即 `docs/20` 中的阶段 S5），并完成混用防呆与 SE150 回归。

### 1.1 步骤一：Vivado SE250 整机全量构建（✅ PASS）
- **执行**：运行 `vivado -mode batch -source hw/scripts/build.tcl`；
- **产物**：
  - `hw/build/export/top_bd_wrapper.bit`（SHA-256 `128a2fb6...`）
  - `hw/build/export/dna_accel.xsa`
  - `hw/build/reports/` 综合与实现时序利用率报告；
- **实测指标**：
  - 综合与实现无致命错误（errors = 0）；
  - WNS @ 100MHz = **+0.586 ns**（0 failing endpoints）；
  - BRAM Tile = **47.5 / 60 (79.17%)**（芯片余 12.5 块）；
  - Slice LUT = **11,850 / 17,600 (67.33%)**。

### 1.2 步骤二：已解耦固件的 SE250 常量切换与编译（✅ PASS）
得益于第二波刚刚完成的固件模块化拆分，固件参数修改被极大简化，已在解耦头文件与模块中按 `docs/20 §3.5` 切换为 SE250 宏：
- `READ_BASES_PER_READ`：`250U`
- `READ_SIZE_BYTES`：`64U`（对齐到 4 字节）
- `WM_STRIDE` / `WM_REF_LEN`：`805U` / `1055U`
- `DNA_ACC_RESULT_PACKED_BYTES`：`72U`
- `VOTER_INPUT_BYTES_PER_READ`：`72U`
- `VOTER_SCORE_MIN`：`112U`
- **编译与打包**：在 `sw/workspace/dna_lwip_app_b27/Debug` 编译通过，使用 `bootgen` 打包生成 SE250 版 `BOOT.bin`；
- **制品刷新**：`hw/build/export/SHA256SUMS` 16 项全通过。

### 1.3 步骤三：SE250 首次上板点亮实测（4,096 条记录）（✅ PASS）
- **规模**：源读段 2,048 条（`--orient both` $\to$ 4,096 条记录，每条 250 bp）；
- **执行**：
  ```bash
  bash tools/run_g3.sh --limit 2048 --read-bps 250 --score-min 112 --reads "data/R0.83_data/Sequencing data/DNA-40.5Kb-MC-SE250.fastq" --tag se250-s5-lighting
  ```
- **实测结果**：
  1. 板端回传经 `tools/ldpc_decode.py` 译码后图片 SHA-256 严格逐位匹配：
     `fcd0cf90bd680e7bbdc203e3398119504da0897acac9e2117008b4efb6b1f2c3`
  2. 板端处理与传输时长仅 **11.35s**（总耗时 12s），远低于 180s 上限；
  3. 四级 DDR 取证（`tools/board_stage_check.py`）**4/4 级全绿**：
     - 展开水印：52,750 / 52,750 字逐位相同（PASS）；
     - Stage1 输出：码字全等 4,096/4,096，分值全等 4,096/4,096（PASS）；
     - Stage2 输出 ⊕ 水印：整字相同 1,265/1,266，比特误码率 0.02%（PASS）；
     - Stage3 输出：整字相同 1,012/1,012，比特误码率 0.00%（PASS）；
  4. 留证目录：`/mnt/d/dna_board_smoke/g3_runs/20260904T122121Z-se250-s5-lighting`。

### 1.4 步骤四：运行时混用防呆验证（反向判据）（✅ PASS）
- **背景**：`AGENTS.md` 规定“SE150 与 SE250 绝不可混用”，这是两套完全不同的硬件几何常数。硬件与固件必须具备明确的安全闸门。
- **实测双层阻断**：
  - **上位机层**：客户端探针检测到板端返回 `read_bps=250`，触发 `ValueError: 板端只支持 250bp，本任务需要 150bp`，零配置零数据下发并中断；
  - **板端固件/硬件层**：直接向板端下发 `read_bps=150` 配置包，板端固件严格按规范返回拒绝码 2（`reply code=2: read_bps 不被支持`），拒绝启动流水线。
- **结论**：双层防呆安全闸门 100% 具备鉴别力，不可混用规范在运行时彻底闭环。

### 1.5 步骤五：阶段 S6 SE150 黄金回归
- **执行**：恢复归档的 SE150 制品与固件，执行标准 `bash tools/run_g3.sh --limit 2048 --tag se150-s6-regression`；
- **判据**：图片 SHA-256 依然为 `fcd0cf90…f2c3`，四级取证全绿，证明整套仓库保持双几何兼容与零回归。
### 1.5 步骤五：阶段 S6 SE150 黄金回归（✅ PASS）
- **背景**：硬件架构改造（移位寄存器）与固件解耦模块化必须证明对原 SE150 黄金基线零退化、零回归。
- **切换工具**：通过新建的 `tools/switch_export.sh se150` 一键切回 SE150 导出制品与头文件宏配置。
- **实测运行**：
  - 任务编号：`run 20260905T021433Z-se150-s6-regression`；
  - 执行命令：`bash tools/run_g3.sh --limit 2048 --read-bps 150 --score-min 67 --tag se150-s6-regression`；
  - CAPS 探针确认就绪：`read_bps=150, stride=807, max_reads=107968`；
  - 板端耗时：4,096 条记录总耗时仅 **9s**（数据运算 9.05s，回传 8,100 B），零性能退化；
  - 最终唯一判据：LDPC 5 轮收敛，图片 SHA-256 为：
    `fcd0cf90bd680e7bbdc203e3398119504da0897acac9e2117008b4efb6b1f2c3`（与黄金参考逐位全等！）；
  - 四级 DDR 取证 4/4 级全绿（展开水印全等、Stage1 码字分值全等、Stage2 误码率 0.03%、Stage3 误码率 0.00%）；
  - 留证归档：`docs/board/run-logs/20260905T021433Z-se150-s6-regression-summary.txt` 与 `run18-uart-se150-s6-regression-2026-09-05.log`。
- **结论**：阶段一所有五个步骤（S5 硬件构建、S5 固件解耦、S5 首次点亮、不可混用防呆、S6 黄金回归）**全部达成 100% PASS，阶段一圆满收官！**

---

## 2. 阶段二与阶段三实施方案

### 阶段二：B29 网络挂起根治与 SE250 全量推进（进行中）

#### 2.1 任务进展与实测闭环（2026-09-05 上板实测）

1. **SE250 全量 DDR 布局上移重排与 B29 根治加固（✅ 实施完成）**：
   - 依据 `docs/20 §5.3` 完成 `sw/app/echo.h` DDR 布局重排：`TOTAL_READS=129600`，`DDR_DNA_ACC_OUT_BASE=0x10900000`，`DDR_VOTER_OUT_BASE=0x11200000`，`DDR_DECODER_OUT_BASE=0x11300000`；读段区成功扩充至 8.38MB（余量 94KB），Stage1 区扩充至 9.43MB（余量 105KB）；
   - 固件与客户端完成同步：`clients/python/task_protocol.py` 扩充 `MAX_TOTAL_READS=129600`；
   - 植入 B29 网络保活机制（`arp_keepalive` 免费 ARP + 周期性 ARP 请求刷新），并在 `send_result` 后增加 `Delivery settled` 物理 ACK 等待确认。

2. **档位 1：4,096 记录点亮复验（✅ PASS）**：
   - 运行编号：`run 20260905T023113Z-se250-s7-layout-check`；
   - 耗时 13s（网络/板端 11.91s，8,100 B），图片 SHA-256 逐位吻合 `fcd0cf90bd680e7bbdc203e3398119504da0897acac9e2117008b4efb6b1f2c3`；四级 DDR 取证 4/4 级全绿！
   - 探针证实：`Delivery settled after 4 ms (unsent=0, unacked=0)`，投递确认完全生效。

3. **档位 2：32,768 记录压测点亮（✅ PASS）**：
   - 运行编号：`run 20260905T023216Z-se250-s7-32768`；
   - 耗时 63s（网络/板端 58.93s，8,100 B），图片 SHA-256 逐位吻合 `fcd0cf90bd680e7bbdc203e3398119504da0897acac9e2117008b4efb6b1f2c3`；四级 DDR 取证 4/4 级全绿！
   - 成功跨越 2MB 读段区边界，证明新 DDR 布局时序稳定。

4. **档位 3：全量 129,600 记录点亮 —— 撞上 RTL 硬件看门狗硬编码（⚠️ 定位完成，缺陷编号 B30）**：
   - 运行编号：`run 20260905T023406Z-se250-s7-full-129600`（全量 64,800 条源读段，8.3MB 读段区）；
   - **现场现象**：Stage1 完美完成，9.33 MB 数据全部写入 DDR `0x10900000`；但在 Stage2 Voter 时停止在 `Waiting for completion...`；
   - **XSDB 物理取证（决定性证据）**：
     直接读取板上 Voter 寄存器：`STATUS=0x00`, `DBG_ST=0x10 (16: S_ERROR)`, `ERR_FLAGS=0x01`（超时错误）；
   - **根因分析**：
     `hw/ip/differential_voter_1_0/hdl/differential_voter_v1_0.v:116` 写死了全局看门狗 `TIMEOUT_CYCLES = 32'd100000000;`（严格 1.000 秒）；
     且计数器只要离开 IDLE 就在处理全部记录期间一路累加不复位；
     全量 129,600 条记录硬件计算需 1.2~1.5 秒，在运行至第 1.000 秒的瞬间被超时硬编码强行斩杀进 `S_ERROR`；而固件轮询只等 `DONE` 未判 `ERROR` 导致假死挂起；
   - **修复方案**：
     ① RTL 将超时上限放大至 10 秒（$10^9$ 拍），并改为每处理完一条读段或写出一拍字即清零的“无进展看门狗”；
     ② 固件增加对 `S_ERROR` 的即时轮询与报错；
     ③ 启动 Vivado 全量整机构建更新 bitstream。

5. **档位 3 修复后终极闭环：全量 129,600 记录点亮（✅ 100% 全面闭环，B30/B29 根除）**：
   - **构建同源**：RTL 实施无进展看门狗（`no_progress_counter`）+ 10s 全局上限，AXI-Lite STATUS bit 2 暴露 `error_flag`；固件 `stage2_voter.c` 建立熔断保护；Vivado 批量构建收敛（WNS = +0.107 ns，WHS = +0.015 ns，0 错误），XSCT 重建 ELF 并使用 bootgen 打包全新 `BOOT.bin`；
   - **板级验证**：`run 20260905T045558Z-se250-s7-full-b30-fix`（全量 64,800 条源读段，129,600 条记录，8.3MB 读段区，`score_min=112`）；
   - **实测耗时**：232 秒（数据处理 217.47s），回传 8,100 字节结果即时完整送达；
   - **唯一判据**：LDPC 译码（5 轮收敛，54,000 bit），图片 SHA-256 = `fcd0cf90bd680e7bbdc203e3398119504da0897acac9e2117008b4efb6b1f2c3` 逐位完全吻合！
   - **四级 DDR 取证**：展开水印、Stage1、Stage2、Stage3 4/4 级全绿！
   - **结论**：阶段二 S7 全面闭环！B30 硬看门狗与 B29 网络挂死彻底根治！

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
