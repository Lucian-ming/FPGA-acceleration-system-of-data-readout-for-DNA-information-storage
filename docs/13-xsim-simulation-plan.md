# 13 · XSim 高质量仿真接手提示与执行计划

本文用于直接交给后续 Agent，指导其在 `main` 分支建立可复现、可判定、可留证的
Vivado/XSim 验证体系。目标不是把现有 Icarus 命令机械地换成 XSim，而是按风险递增的顺序：

1. 用 XSim 复跑三个 IP 的既有黄金 Testbench；
2. 建立三级 PL 流水线的直接集成仿真；
3. 建立实际 Vivado Block Design 的集成仿真；
4. 对关键路径做综合后/实现后定向仿真；
5. 保留可审计证据，并明确哪些结论仍必须上板才能得到。

> **交接状态（2026-08-21）：** 本文最初是待执行计划。本次交接只完成计划、Git 约束和远端同步，
> 未实施 M0～M4，未新增 XSim Testbench/运行器，也未产生可据此宣称通过的 XSim 结果。
> 接手者必须先通过下述 Git 绑定门禁，然后从 M0.1 开始逐项执行；不得把计划文本当验证证据。

> **M1 实施记录（2026-08-22）：** 已在 `main@3515b19c8e83a3fe470d799e4fc5b98ede0b8d42`
> 通过 Vivado Simulator 2022.2 复跑 6 个既有黄金 Testbench：Stage3 数据通路、Stage3 AXI、
> DNA ingress、DNA AXI-Lite、Stage1 `srpe_batch`、Stage2 `differential_voter`，结果为 **6/6 PASS**。
> 每例均完成 xvlog → xelab → xsim，显式 PASS 比较通过，日志无 FATAL/ERROR/FAIL。统一入口为
> `tools/run_xsim.sh`，本次证据目录为 `hw/build/xsim/20260821T165313Z/`。随后复跑仍为 6/6 PASS。

> **M2 快速串联记录（2026-08-22，提交 `e4a895f`）：** `tools/run_m2_quick.sh` 完成
> `Stage1 实际输出 → Stage2 实际 AXI 读/写 → 独立 PS 等价 XOR → Stage3 实际 AXI 读/写`，
> 三个 checkpoint 均逐位比较通过。用例使用前 64 条黄金读段；Stage2 为满足既有固定容量 TB，
> 将其余记录填为 score=0 的显式无效记录，`SCORE_MIN=67` 下不参与投票。Stage2 期望、XOR
> 期望和 Stage3 期望均由 `tools/m2_chain.py` 从实际上一级输出/水印独立推导，未将
> `stage2_expect.hex` 或 `stage3_expect.hex` 注入级间数据。证据目录为
> `hw/build/xsim/m2_quick/20260821T171854Z/`，日志和 checkpoint SHA-256 已写入其
> `summary.txt`。M2 完整 2,048 条真实串联、故障注入、M3/M4 与 G3 仍未完成。

> **M0 实施记录（2026-08-22）：** 在同一 checkout 中，Icarus 11.0 的 6 个 RTL/AXI 功能用例、
> 3 个 PS 侧 C 单测和 4 个生产顶层语法检查通过；上位机 `client_core` 与 LDPC 自检未能执行，
> 原因是按项目约定不入 Git 的 `data/R0.83_data/` 当前未挂载，属于输入环境缺口而非 RTL 失败。

---

## 一、可直接交给后续 Agent 的执行提示

```text
你正在处理 FPGA DNA 数据读出项目：
/home/lucian/projects/FPGA/FpgaAccelerationSystemOfDataReadout

目标：在 main 分支建立完整、高质量、自动判定的 Vivado 2022.2 / XSim 仿真体系。
严格按照 docs/13-xsim-simulation-plan.md 的阶段顺序实施，不要只给建议或停在方案层面。

强制要求：

1. 开始前完整阅读 AGENTS.md、docs/README.md、docs/01-architecture.md、
   docs/02-data-contract.md、docs/03-status.md、docs/05-interfaces.md、
   docs/09-handoff-2026-08-16.md、docs/10-three-end-audit-2026-08-16.md 和本文。
2. 唯一允许的开发目录是 /home/lucian/projects/FPGA/FpgaAccelerationSystemOfDataReadout；禁止
   git init、另行 clone、另建平行项目或嵌套仓库。开始前必须运行
   bash tools/verify_repo_binding.sh --remote；绑定未通过前禁止仿真、开发或处理其他项目。
3. 只能在 main 分支工作，origin 必须绑定指定的 Lucian-ming 私有仓库。工作区可能已有用户修改，
   必须保留，禁止 reset、checkout 覆盖、clean 或删除构建产物。所有有意义修改必须提交并执行
   git push origin main；禁止仅本地提交。结束前以 --require-synced 验证 main 与 origin/main 为 0/0。
4. data/R0.83_data/、archive/ 和两份历史 XSA 只读。禁止修改、覆盖、重命名或用其参考结果
   驱动生产路径。黄金结果只能进入 Testbench 的显式 scoreboard。
5. 先复跑并记录现有 Icarus 11/11 和黄金模型基线，再开始 XSim。任何 XSim 修复不得破坏
   Icarus 结果；若改 RTL，必须同时复跑相关 Icarus、XSim 和 Vivado 综合/时序。
6. 不得把“编译成功”“仿真跑到结束”“出现波形”“收到非零数据”当 PASS。
   每个功能用例必须有显式 PASS/FAIL、非零失败退出码、超时、逐拍/逐位黄金比较。
7. 先做三个 IP 的独立 XSim，再做三级直接集成，再做实际 Block Design；不要一开始就把
   PS7、DMA、DDR、三个 IP 和软件全部塞进一个难以定位的仿真。
8. 三级直接集成仿真的唯一业务输入是 FASTQ 派生的读段和水印。Stage1 实际输出必须成为
   Stage2 输入，Stage2 实际输出必须经 Testbench 中等价于 PS 的 XOR 行为后成为 Stage3 输入。
   禁止用 stage2_expect.hex 或 stage3_expect.hex 替换级间真实输出；这些文件只允许比较。
9. Vivado/XSim 工具已安装在 /tools/Xilinx/Vivado/2022.2/bin。脚本不得依赖调用者当前目录，
   必须从脚本位置或仓库根目录推导绝对路径。所有命令使用 batch 模式，适合无人值守复跑。
10. 普通 XSim 不能证明 lwIP、真实 PHY、真实 DDR、ARM cache 和板级电气行为正确。
    即使全部 XSim 通过，也不得关闭 G3；最终判据仍是实际板端 8,100 B 回传经 LDPC 后图片
    SHA-256 等于 fcd0cf90bd680e7bbdc203e3398119504da0897acac9e2117008b4efb6b1f2c3。

先提交一份很短的执行状态说明，然后持续实施、验证和留档。遇到失败先保存日志和最小复现，
判断是 DUT、Testbench、XSim 语义、路径还是生成 IP 模型问题，再做最小修复。不要为了变绿
放宽黄金判据、屏蔽 X/Z、删除断言或把 ERROR 改成 WARNING。
```

---

## 二、当前事实边界

### 2.1 已有基础

- 当前生产器件：`xc7z010clg400-1`，PL 目标时钟 100 MHz。
- Vivado、`xvlog`、`xelab`、`xsim` 位于 `/tools/Xilinx/Vivado/2022.2/bin/`。
- `bash tools/run_sim.sh` 已使用 Icarus 覆盖 Stage1、Stage2、Stage3、DNA ingress、
  DNA AXI-Lite、PS 纯计算逻辑、上位机单测、LDPC 和语法检查。
- 三个核心 IP 已有黄金 Testbench：

| 阶段 | DUT/Testbench | 既有核心判据 |
| --- | --- | --- |
| Stage1 | `srpe_batch.v` / `tb_srpe_batch.v` | 64 条读段的 `score/position/codeword` |
| Stage2 | `differential_voter_v1_0.v` / `tb_differential_voter.v` | 4,096 条记录、三轮、81,000 bit、AXI 协议 |
| Stage3 数据通路 | `desparsify_datapath.v` / `tb_desparsify_datapath.v` | 随机背压、64,800 bit |
| Stage3 整核 | `desparsification_decoder_v1_0.v` / `tb_desparsifier.v` | AXI-Lite + AXI4 内存模型、64,800 bit |

- `tests/golden/` 已有受版本管理的激励和期望结果；权威生成器是
  `tools/make_golden.py`，算法/位序权威是 `docs/02-data-contract.md`。
- Vivado 已能生成实际 BD、bitstream、XSA 和匹配 ELF，完整实现已在 100 MHz 收敛。

### 2.2 当前缺口

- 没有统一、可回归的 XSim 运行器、结果摘要和日志归档。
- Vivado 工程中的 `sim_1` 没有完整 Testbench。
- `vivado_quick_sim.tcl` 是旧的 Stage1 冒烟脚本，不是黄金回归：源文件不完整、运行时间不足、
  输入不是生产向量、失败不 `$fatal`，不得作为验收入口。
- 尚无 Stage1 实际输出串入 Stage2、再经水印 XOR 串入 Stage3 的同一仿真闭环。
- 尚无实际 `top_bd` 下 AXI DMA、Interconnect、三个自研 IP 的事务级集成证据。
- 尚无板端 G3 证据。

### 2.3 概念边界

- XDC 是引脚/时序约束，不是仿真激励。行为仿真的关键缺口是顶层 Testbench、BFM、内存模型、
  scoreboard 和自动判据。
- 单独用 XSim 复跑现有 RTL Testbench，主要价值是交叉验证模拟器语义和 Xilinx 工具兼容性。
- 真正新增的验证价值来自三级集成、实际 BD 连接、Xilinx IP 模型及综合后/实现后定向检查。
- PS 软件单元测试和 XSim PL 仿真不能代替真实 ARM + cache + DMA + lwIP 板端联调。

---

## 三、总体分层与退出条件

| 里程碑 | 内容 | 退出条件 | 可以宣称什么 |
| --- | --- | --- | --- |
| M0 | 基线固化 | 黄金哈希、Icarus、工具版本全部留档 | 当前基线可复现 |
| M1 | 三个 IP 独立 XSim | 所有既有黄金 TB 在 XSim 自动 PASS | 三个 IP 在 Icarus/XSim 语义下结果一致 |
| M2 | 三级直接集成 XSim | 真实级间数据流 + 每级 checkpoint 逐位 PASS | PL 算法流水线及 PS XOR 等价行为闭环 |
| M3 | 实际 Block Design XSim | BD 生成/编译/elaborate + 关键 AXI 事务 PASS | Vivado BD 连接和模型下集成正确 |
| M4 | 综合后/实现后定向仿真 | 关键控制/接口短用例 PASS，STA 仍通过 | 综合网表/关键时序路径未暴露新问题 |
| G3 | 真实开发板 | 真实回传经 LDPC 得到目标图片哈希 | 才能宣称板端端到端正确 |

任何里程碑失败，都必须停在该层定位，不得跳到下一层掩盖问题。

---

## 四、M0：固化基线

### 4.1 Git 与工作区

首先运行强制门禁并保存输出：

```bash
bash tools/verify_repo_binding.sh --remote
git status --short --branch --untracked-files=all
git rev-parse HEAD
git log -8 --oneline --decorate
git branch -vv
```

要求：

- Git 根目录、`main`、`origin/main`、指定 GitHub URL 和当前身份的 fetch/push 权限必须全部通过。
- 当前分支必须是 `main`；若不是，且工作区不干净，不得擅自切换，先报告并停止。
- 禁止创建新仓库、新 clone 或嵌套仓库；此 checkout 是唯一开发目录。
- 不清理已有未跟踪 Vivado 目录，它们可能是用户保留的构建证据。
- 记录开始时的全部修改，结束时区分“开始前已有”和“本轮新增”。

### 4.2 工具版本

```bash
/tools/Xilinx/Vivado/2022.2/bin/vivado -version
/tools/Xilinx/Vivado/2022.2/bin/xvlog --version
/tools/Xilinx/Vivado/2022.2/bin/xelab --version
/tools/Xilinx/Vivado/2022.2/bin/xsim --version
iverilog -V
python3 --version
```

若 Xilinx 工具因 X11、权限或临时目录失败，先确认是否为环境问题；不要修改 RTL 来规避工具启动失败。

### 4.3 黄金数据完整性

```bash
(cd tests/golden && sha256sum -c SHA256SUMS)
python3 tools/golden_model.py verify-code
```

不要直接覆盖 `tests/golden/`。如需确认生成器可重复，输出到临时目录并比较：

```bash
golden_tmp=$(mktemp -d /tmp/dna-golden-verify.XXXXXX)
python3 tools/make_golden.py --limit 2048 --outdir "$golden_tmp"
diff -qr tests/golden "$golden_tmp"
```

若因说明文件或清单产生预期差异，应逐文件解释，不能直接接受整个目录不同。

### 4.4 Icarus 基线

```bash
bash tools/run_sim.sh
```

要求保留完整输出、退出码、开始/结束时间。预期为 `通过 11 项，失败 0 项`。若基线失败，
先定位基线，不开始 XSim 开发。

---

## 五、M1：三个 IP 分别进行 XSim 黄金仿真

### 5.1 建议目录和脚本边界

建议新增以下可维护文件，具体名称可以遵循仓库现状微调：

```text
tools/run_xsim.sh                  # 单一用户入口、选择 case/all、汇总 PASS/FAIL
hw/sim/xsim/run_ip_case.tcl        # 创建临时工程或调用 XSim 的通用 Tcl
hw/sim/xsim/cases.tcl              # case → 源文件/Testbench/顶层/运行方式映射
hw/build/xsim/                     # 所有生成工程、日志、WDB；不得散落源码目录
```

实现要求：

- 从脚本自身位置计算仓库根目录，不依赖 `pwd`。
- 每个 case 使用独立构建目录，避免 `xsim.dir`、快照和日志互相污染。
- 默认 batch/headless；不调用 GUI，不依赖人工查看波形。
- Testbench 应使用 `$finish` 正常结束，不用固定 `run 100us` 猜测是否完成。
- 每例必须有超时；超时算 FAIL。
- 只有同时满足以下条件才计为 PASS：编译成功、elaborate 成功、XSim 退出码为 0、
  日志包含该用例唯一 PASS 标志、日志不含 `FATAL`/明确失败标志。
- 汇总脚本最终以失败用例数作为进程退出码。
- 不要把普通 Xilinx IP informational warning 一刀切成失败；应维护明确白名单，任何新 warning 需审查。

### 5.2 Stage1 XSim

至少运行三例：

1. `stage1_core`：`srpe_batch.v + tb_srpe_batch.v`
   - 预载 50 × 957 个黄金水印符号；
   - 输入前 64 条黄金读段；
   - `score` 必须逐条一致；
   - `codeword` 必须逐位一致；
   - `position` 只允许黄金模型已经确认的同分并列峰，必须计数且不超过既有 5% 上限；
   - X/Z 出现在有效输出中必须失败。
2. `stage1_ingress`：生产 DNA 顶层 + `tb_dna_ingress.v`
   - 检查每条 10 个 32-bit AXIS 拍的组装；
   - FIFO 满时 `TREADY` 必须施加背压；
   - 接收计数与真实 FIFO 写入一致；
   - 100,000 周期 partial-batch 超时边界必须覆盖。
3. `stage1_axil`：AXI-Lite 控制从机 + `tb_dna_axil.v`
   - AW→W、W→AW 和同拍三种次序；
   - `WSTRB`；
   - 每次写只产生一次响应；
   - 不允许只编译不运行。

`tb_dna_quick.v` 可以保留为人工波形冒烟测试，但不得计入 M1 验收数量。

### 5.3 Stage2 XSim

运行 `differential_voter_v1_0.v + tb_differential_voter.v`，保留既有三轮语义：

- 第 1 轮 `SCORE_MIN=67`，与 `stage2_expect.hex` 的 81,000 bit 逐位相同；
- 第 2 轮相同配置再次运行，证明累加器已清零；
- 第 3 轮 `SCORE_MIN=0`，与 `stage2_rtl_expect.hex` 逐位相同；
- 每条输入严格 6 个 64-bit 拍，检查 `ARLEN=5`；
- 每笔输出写为单拍，检查 `WLAST`；
- 共 1,266 拍，末拍仅低 40 bit 有效且 `WSTRB=0x1F`；
- `DONE/IDLE`、错误寄存器、首写地址和写拍数均符合现有判据；
- AXI 内存模型至少覆盖零延迟响应和受控背压两组配置，避免只在理想从机下通过。

若 XSim 与 Icarus 出现差异，优先检查非阻塞赋值竞争、未初始化寄存器、`$readmemh` 工作目录、
Verilog-2005/SystemVerilog 模式和 X/Z 传播；不得直接放宽黄金比较。

### 5.4 Stage3 XSim

至少运行两例：

1. `stage3_datapath`
   - 81,000 bit `sparse_ideal.hex` 输入；
   - 随机输入/输出背压；
   - 1,013 拍、64,800 bit 与 `stage3_ideal_expect.hex` 逐位相同；
   - 末拍有效位掩码正确。
2. `stage3_axi`
   - AXI-Lite 完成真实寄存器配置和启动；
   - AXI4 从机覆盖 B 零延迟、只允许一个未完成地址及受控背压；
   - 所有输出地址被写且只有有效地址被写；
   - `DONE/IDLE` 和拍数正确；
   - 64,800 bit 逐位相同。

### 5.5 M1 完成判据

建议用户入口最终表现为：

```bash
bash tools/run_xsim.sh all
```

摘要至少包含：case、compile、elaborate、simulate、golden compare、耗时和结论。随后再次运行：

```bash
bash tools/run_sim.sh
```

只有 Icarus 和 XSim 都通过，才能关闭 M1。

---

## 六、M2：三级 PL 直接集成仿真

### 6.1 为什么先做直接集成

直接集成层不引入 PS7、lwIP 和真实 DMA IP，而用可控 BFM/内存模型准确复现它们对三个 IP 的
可观察行为。这样可以先回答最核心的问题：三个已验证 IP 串起来后，位序、长度、地址、尾拍和
启动顺序是否仍然正确。失败时也能明确定位到某一级边界。

### 6.2 建议结构

新增独立 Testbench，例如：

```text
hw/sim/tb/tb_pipeline_3stage.v
hw/sim/tb/axi_memory_model.v
hw/sim/tb/axi_lite_bfm.v
hw/sim/xsim/run_pipeline.tcl
```

Testbench 应实例化当前生产 RTL，而不是复制其算法：

```text
黄金水印 + FASTQ 派生读段
  -> DNA 顶层真实水印预载和 AXIS 输入
  -> Stage1 实际 AXIS 输出
  -> 模拟 DDR Stage1 区
  -> Stage2 AXI Master 实际读取/写回
  -> Testbench 执行与 PS 完全等价的逐字节水印 XOR
  -> Stage3 AXI Master 实际读取/写回
  -> 8,100 B / 64,800 bit 最终结果
```

### 6.3 真实性红线

- Stage1 输入只能来自读段向量；Stage1 结果必须捕获自 DUT 输出。
- `stage1_expect` 只做 checkpoint 比较，不得写入模拟 DDR 代替 DUT 输出。
- `stage2_expect.hex` 只做 Stage2 checkpoint 比较，不得作为 Stage3 的数据源。
- Stage3 输入必须来自 Stage2 实际输出与本次水印的 XOR。
- `stage3_expect.hex`/`dec_input.txt` 只能比较最终结果。
- Testbench 内的 PS XOR 行为必须独立、简单、可审计：按码流顺序和字节内 LSB-first 对
  10,125 B 逐字节异或；不得调用或复制黄金反稀疏化算法。
- 每一级数据应计算 SHA-256 或导出文件后由外部脚本计算，以便和软件黄金结果交叉核对。

### 6.4 两档用例

为了兼顾调试速度和完整性，建立两档：

#### 快速串联回归

- 使用 64 或 128 条原始读段，并按上位机生产语义生成正向+反向互补记录；
- 对应黄金向量必须生成到 `/tmp` 或独立测试目录，不覆盖受版本管理的 2,048 条向量；
- Stage1 至少跑完整的 64-record batch；
- Stage2、PS XOR、Stage3 必须真实串联；
- 每一级与相同读段子集的软件期望逐位比较；
- 该用例不要求 LDPC 成功，因为低覆盖率可能不足以恢复图片。

#### 完整串联回归

- 使用前 2,048 条原始读段，双方向共 4,096 条 Stage1 记录；
- 必须真实跑完所有 Stage1 batch，不能注入 `stage2_in.hex` 冒充串联；
- Stage2 使用 `SCORE_MIN=67`；
- 最终 64,800 bit 应与 2,048 条方案 B 的 `dec_input.txt` 一致；
- 调用 `tools/ldpc_decode.py decode` 后重建图片必须得到目标 SHA-256。

完整用例可能需要数亿 RTL 周期，必须先测量单 batch 耗时并设置合理的长时限。不得因运行慢而
悄悄把完整用例降级为 checkpoint 注入。可以把它标为 `full`/nightly，但交接前至少成功跑完一次。

### 6.5 级间 checkpoint

每次串联运行至少输出以下证据：

| Checkpoint | 逻辑长度 | 比较内容 |
| --- | ---: | --- |
| 水印区域 BRAM | 50 × 957 × 2 bit | 每区域逐符号相同，区域切换地址归零正确 |
| Stage1 | N × 48 B | score/position/codeword/padding/记录顺序 |
| Stage2 | 81,000 bit | 阈值语义、末拍 40 bit、第二层地址偏移 |
| PS XOR 后 | 81,000 bit | 与本次水印逐位 XOR 后的稀疏流 |
| Stage3 | 64,800 bit / 8,100 B | 逐位、字节内 LSB-first、末拍有效位 |
| LDPC | 54,000 bit + JPEG | syndrome、迭代数、图片 SHA-256 |

### 6.6 M2 完成判据

- 快速串联用例可在日常回归中稳定复跑；
- 完整 2,048 条串联至少成功一次并保存完整日志；
- 每级 checkpoint 均逐位通过；
- 故障注入有效：主动翻转一个级间 bit 时，对应 checkpoint 必须失败，证明 scoreboard 不是假绿；
- 移走一个必需向量或破坏配置时，脚本必须非零退出；
- M1 的单 IP 和 Icarus 回归仍全部通过。

---

## 七、M3：实际 Vivado Block Design 集成仿真

### 7.1 构建原则

- 从 `hw/scripts/build.tcl` / `hw/scripts/bd.tcl` 新建可复现工程，不把现存 `hw/build/dna_accel.xpr`
  当唯一来源。
- 注册本地 IP repository，刷新 IP Catalog，检查三个自研 IP 版本和 simulation fileSet。
- `validate_bd_design`、生成 wrapper 和 `generate_target simulation` 必须自动完成。
- 仿真工程必须使用实际地址图、100 MHz 时钟、复位网络、GP0/HP0、AXI DMA、Interconnect 和
  当前三个自研 IP。
- 先做编译/elaboration smoke，再做事务用例，不要同时调所有问题。

### 7.2 分三步推进

#### BD-1：静态和 elaboration 检查

- 重新生成 `top_bd`；
- 验证地址段无冲突、接口无未连接、时钟/复位连接正确；
- 所有 Xilinx IP 和自研 IP simulation model 可编译；
- `top_bd_wrapper` 可 elaborate；
- 禁止把 black-box warning 当作成功，关键数据通路不得为 stub。

#### BD-2：控制面事务

使用 PS7 BFM、Xilinx AXI VIP 或专用仿真 harness 驱动实际 AXI-Lite 路径，至少验证：

- GP0 经 Interconnect 到 DNA/Voter/Decoder/DMA 的地址译码；
- 三个 IP 的寄存器写/读回；
- AW/W 独立到达仍能正确完成；
- 无效地址返回符合设计预期；
- 启动、done、idle 和复位顺序。

不要凭空假定 PS7 BFM API。先检查 Vivado 2022.2 生成的 PS7 simulation model 和本机示例，记录
选用的模型、库和限制。若实际 PS7 模型无法在合理成本下驱动 GP0，应保留 actual-BD elaboration
测试，并建立一个仅在仿真中用 AXI VIP 替代 PS 主设备的等价 harness；报告必须明确它不是实际 PS7。

#### BD-3：数据面事务

逐步加入：

1. AXI DMA MM2S -> Stage1 S_AXIS；
2. Stage1 M_AXIS -> AXI DMA S2MM；
3. Stage2/Stage3 AXI Master -> Interconnect -> DDR/内存模型；
4. 真实地址、突发长度、`TLAST/WLAST/WSTRB`、背压、响应码；
5. 最小批次端到端数据搬运。

至少测试零延迟和带背压两种内存行为。检查所有访问均落在 `docs/05-interfaces.md` / `echo.h`
约定区间，越界、未对齐、错误响应或悬挂事务必须失败。

### 7.3 PS 软件边界

普通 XSim 的 BD 仿真不等于运行真实 `echo.c`、lwIP 和 ARM cache。若使用纯 BFM 驱动寄存器：

- 可以证明 BD 和 PL 事务连接；
- 不能证明 SG DMA 描述符管理、`Xil_DCacheFlushRange/InvalidateRange`、TCP 重传、PHY 或 ELF 正确。

不要为了声称“PS 已仿真”而写一个与 `echo.c` 无关的理想控制序列。BFM 序列应逐项映射到
`echo.c` 的状态机，并在报告中列出映射和未覆盖代码。

### 7.4 M3 完成判据

- 新建工程可从干净生成目录复现；
- actual BD 编译/elaborate 无关键 black box；
- 控制面地址、寄存器、复位用例通过；
- 数据面 DMA/AXI 最小闭环通过并与 M2 快速用例结果一致；
- 所有生成物、日志、用时和模型限制留档；
- 报告明确未运行或未覆盖的 PS/lwIP/cache 行为。

---

## 八、M4：综合后与实现后定向仿真

这一层不是全量 RTL 黄金回归的替代品。Stage1 全量用例在门级/时序仿真中成本过高，应只选择
高风险、短周期场景：

1. 三个 AXI-Lite 从机的 AW/W 独立握手和复位释放；
2. DNA ingress 的 AXIS 背压与数据保持；
3. Stage2/Stage3 的末拍 `WSTRB/WLAST`；
4. done/idle 脉冲、清零和连续两次任务；
5. 必要时对跨模块复位和时钟启动做实现后 SDF 仿真。

顺序：

- 先综合后功能仿真；
- 再只对最关键短用例做实现后时序仿真；
- 静态时序分析仍是时序收敛的主判据，检查 WNS/WHS、未约束路径和 CDC；
- 若网表仿真与 RTL 不一致，保存网表、SDF、seed、完整日志和最小波形窗口。

M4 通过也不能替代上板 G3。

---

## 九、日志、波形与证据规范

### 9.1 每次运行必须记录

- Git HEAD、分支、工作区状态；
- Vivado/XSim/Icarus/Python 版本；
- Testbench 顶层、DUT 源文件清单及其 SHA-256；
- 黄金输入/期望文件 SHA-256；
- 完整命令、开始/结束时间、耗时、退出码；
- 编译、elaborate、simulate 分阶段结果；
- 比较的总拍数/bit 数、错误数、首个错误位置；
- seed、超时值、背压配置；
- PASS/FAIL 摘要。

### 9.2 建议生成目录

```text
hw/build/xsim/<HEAD>/<timestamp>/<case>/
  command.txt
  manifest.sha256
  xvlog.log
  xelab.log
  xsim.log
  result.json
  result.tsv
  waves.wdb              # 失败必留；成功可按代表性用例保留
  checkpoint/            # 三级集成的逐级输出
```

大型生成目录默认不提交 Git且不得自动删除；可复现脚本、源文件/黄金数据 manifest、结果摘要和
交接报告必须纳入版本管理。每次有意义提交后必须立即推送 `origin/main`。

### 9.3 波形策略

- 默认只记录关键接口和状态，避免 `log_all_signals` 导致巨大 WDB；
- 失败时保存错误点前后有限窗口；
- Stage2 大 BRAM 不默认全量入波形，使用文件 dump + Python diff；
- 波形是定位证据，不是 PASS 判据。

---

## 十、防止假绿的强制检查

每个 Testbench 至少做一次 mutation/fault-injection 自检：

- 翻转一个期望 bit，测试必须失败；
- 删除或截短输入文件，测试必须失败；
- 破坏 AXI `WLAST` 或地址，协议断言必须失败；
- 缩短超时，脚本必须报告 timeout 并非零退出；
- 引入 X/Z 到有效输出，scoreboard 必须失败；
- XSim 返回 0 但日志含 DUT `FATAL` 时，总运行器仍必须失败。

禁止以下假绿模式：

- 只检查输出非零；
- 只检查发送数等于接收数；
- 只看 GUI 波形；
- 固定运行一段时间后无条件打印“Simulation Complete”；
- 捕获异常后继续返回 0；
- 用黄金中间结果覆盖 DUT 中间结果；
- 忽略末拍无效位之外的任意 mismatch；
- 把所有 X 当 0；
- 为了通过而调宽并列峰、误码或 timeout 容限。

---

## 十一、失败定位顺序

1. 确认路径和黄金文件 SHA-256，特别是 `$readmemh` 的工作目录。
2. 确认 XSim 编译语言模式和顶层，避免把 Verilog-2005/SystemVerilog 混用问题误判成 DUT bug。
3. 对比同一 TB 的 Icarus 输出，定位模拟器语义差异。
4. 检查复位、初值、X/Z 传播和 Testbench/DUT 时钟沿竞争。
5. 检查 AXI BFM 是否合规，特别是 VALID 不依赖 READY、AW/W 可独立、响应保持到握手。
6. 从第一个失败 checkpoint 反查，不要从最终 LDPC 结果猜问题。
7. 先验证 Testbench mutation 能抓住错误，再修改 DUT。
8. 若确认为 RTL bug，做最小修复，同步更新 `docs/03-status.md`，复跑该层及所有低层回归。

任何时候都不得用历史 XSA/bitstream 来解释当前 RTL 的仿真结果。

---

## 十二、最终交接报告模板

完成工作后按以下结构报告，不要只写“仿真通过”：

```text
基线
- branch / HEAD：
- 开始前工作区：
- Vivado/XSim 版本：
- 黄金向量清单 SHA-256：

M0 Icarus/黄金模型
- 命令：
- 结果和耗时：

M1 单 IP XSim
- Stage1 core/ingress/AXI-Lite：
- Stage2 三轮/协议：
- Stage3 datapath/AXI：
- Icarus 复跑：

M2 三级直接集成
- 输入读段数和方向：
- 水印预载 checkpoint：
- Stage1 checkpoint：
- Stage2 checkpoint：
- XOR checkpoint：
- Stage3 checkpoint：
- LDPC/图片哈希：
- fault-injection 结果：

M3 Block Design
- 工程再生：
- actual BD elaboration：
- 控制面：
- 数据面：
- 使用的 PS7/VIP/DDR 模型：
- 未覆盖项：

M4 网表/时序
- 用例：
- 结果：
- STA WNS/WHS/未约束路径：

证据
- 日志目录：
- manifest：
- 失败波形：
- 生成文件大小和 SHA-256：

工作区
- 本轮修改文件：
- 本轮生成文件：
- 未提交状态：

结论边界
- 可以确认：
- 仍不能确认：
- G3 是否完成：必须保持“未完成”，除非有真实板端回传和目标图片哈希证据。
```

---

## 十三、建议的实际执行顺序

严格按以下顺序推进，每一步通过后再进入下一步：

```text
M0.1  工作区/HEAD/工具/黄金哈希
M0.2  golden_model verify-code
M0.3  Icarus 全量 11/11

M1.1  XSim Stage3 datapath      # 最快，先验证运行框架
M1.2  XSim Stage3 AXI
M1.3  XSim Stage1 AXI-Lite
M1.4  XSim Stage1 ingress
M1.5  XSim Stage1 core          # 约 620 万周期
M1.6  XSim Stage2               # 三轮、约 1,100 万周期
M1.7  Icarus 全量复跑

M2.1  三级 Testbench 编译/elaborate
M2.2  快速子集真实串联
M2.3  checkpoint fault-injection
M2.4  2,048 条完整真实串联
M2.5  LDPC + 图片哈希

M3.1  从 Tcl 重建 actual BD
M3.2  actual BD compile/elaborate
M3.3  AXI-Lite 控制面
M3.4  DMA/DDR 数据面最小闭环
M3.5  与 M2 快速用例交叉比较

M4.1  综合后关键短用例
M4.2  实现后关键短用例
M4.3  STA/CDC/约束复核

最终：整理日志、哈希、耗时、覆盖与未覆盖项；提交所有有意义修改并推送 origin/main，
      运行 tools/verify_repo_binding.sh --require-synced 确认本地/远端 0/0 后才能交接。
```

执行质量的核心不是“XSim 跑过”，而是每一层都能回答：输入来自哪里、真实经过了哪些 DUT、
比较了多少 bit、失败能否被故障注入证明、日志能否由另一台机器复现，以及结论没有跨越上板边界。
