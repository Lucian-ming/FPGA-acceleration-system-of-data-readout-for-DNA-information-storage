# DNA 加速器核心 4-Way 顶层 IP 集成、端到端接口仿真与加速比验证报告

> **报告版本**: 1.0.0  
> **编制日期**: 2026-09-07  
> **责任专员**: `stage1-ip-pack` (4-way IP 顶层集成与仿真包装专员 / 由 main 接管闭环)  
> **前序基准**: `docs/benchmarks/stage1-candidate-audit.md` (资源证伪)、`docs/benchmarks/stage1-4way-timing-closure.md` (OOC 时序闭环)  
> **核心交付**: `hw/ip/Dna_accelerator_core_1_0/hdl/Dna_accelerator_core_4way.v`、`hw/sim/tb_accelerator_core_4way.v`  

---

## 1. 任务背景与核心工程目标

在前期 W2 阶段的工作中，团队成功修复了 4-way 滑窗比对核的边界缺陷（`<= STRIDE` 替换 `< STRIDE`），引入了两拍流水化 4 选 1 选优树，并在 Vivado OOC（Out-of-Context）综合实现中达成了 100 MHz 下 **WNS = +2.197 ns** 的正时序裕量（8 块 RAMB36，8,673 LUT，占用率 49.3%）。

本任务的目标是将 4-way 比对微架构向上合入完整的加速器顶层 IP 核（`Dna_accelerator_core`），穿透验证：
1. **AXI-Lite 控制总线**：启动（START）、预载（PRELOAD）、复位（RESET）及区域选择（WM_SEL）寄存器控制时序；
2. **S_AXIS_DATA 输入流**：40-byte 测序读段包经输入 FIFO（256 深度）解包缓冲，两拍读延迟下的握手可靠性；
3. **M_AXIS_RESULT 输出流**：选优结果打包为 6 拍 × 64-bit DMA 流，在极端随机背压（Backpressure）下的防丢拍与防悬挂能力；
4. **端到端 2-Way vs 4-Way 逐位等价性**：在顶层总线级对全量 64 条读段进行逐拍比对，验证分数、位置、码字 100% 逐位一致；
5. **周期级实际加速比度量**：量化顶层整机包含数据入队、预载、计算与流式回传的全流程加速比。

---

## 2. 顶层 IP 架构集成设计 (`Dna_accelerator_core_4way.v`)

顶层 IP 核 `Dna_accelerator_core_4way` 保持与现有 Vivado Block Design 中 2-Way 核心 100% 引脚兼容，可作为 Drop-in 替代：

```
                    ┌───────────────────────────────────────────────────────────┐
                    │              Dna_accelerator_core_4way (Top IP)           │
                    │                                                           │
S_AXI_LITE ────────►│  ┌───────────────────────┐                                │
 (4B Registers)     │  │ S_AXI_LITE_CTRL 模块   │─── reg0_start, reg1_wm_sel ──┐│
                    │  └───────────────────────┘                               ││
                    │                                                           ││
S_AXIS_DATA ───────►│  ┌───────────────────────┐                                ││
 (32-bit Stream)    │  │  fifo_sync_sdpram_b64 │─── 2-cycle read pipeline ────┐││
                    │  │  (256-depth BRAM FIFO)│                              │││
                    │  └───────────────────────┘                              │││
                    │                                                         ▼▼▼
                    │  ┌────────────────────────────────────────────────────────┐
                    │  │              srpe_batch_4way 比对引擎                   │
                    │  │  • 4 组移位寄存器 + 4 组独立局部相关器 (local_correlator) │
                    │  │  • 2 拍流水化 4选1 选优树 (Tournament Tree)             │
                    │  │  • 双位平面 BRAM (150bp x 64 reads)                    │
                    │  └────────────────────────────────────────────────────────┘
                    │                                │
                    │                                │ valid / score / pos / codeword
                    │                                ▼
                    │  ┌────────────────────────────────────────────────────────┐
                    │  │   s2mm_pack64 打包引擎                                  │
                    │  │   • 326-bit 结果打包为 6 拍 x 64-bit AXI-Stream 数据拍    │
                    │  └────────────────────────────────────────────────────────┘
                    │                                │
M_AXIS_RESULT ◄─────┴────────────────────────────────┴───────────────────────────┘
 (64-bit to DMA)
```

### 关键接口时序契约与防陷阱设计：
- **FIFO 读延迟穿透**：`fifo_sync_sdpram_b64` 具有两级同步读（`raddr_q <= rptr; dout <= mem[raddr_q]`），从 `fifo_rd_en` 有效到 `fifo_dout` 稳定需要整整 3 拍。顶层状态机严格适配两拍握手，消除 B24/B26 曾发生的读段错位隐患。
- **背压解耦机制**：`s2mm_pack64` 内部包含发送移位与跨时钟打拍寄存器。当下游 DMA 因总线争用拉低 `M_AXIS_TREADY` 时，核心暂停流水线输出推进，保持数据有效，彻底杜绝数据丢失。

---

## 3. 顶层双核同构激励仿真实验 (`tb_accelerator_core_4way.v`)

为确保证据具备绝对公信力，测试平台将 2-Way Baseline 核心与 4-Way Pipelined 核心并联例化，在完全相同的激励下进行周期级同构验证。

### 3.1 仿真测试配置
- **参考区域数 (NUM_LC)**: 6
- **滑动跨度 (STRIDE)**: 807
- **测试批次规模 (BATCH)**: 64 条读段（填满一个完整硬件批次）
- **读长 (READ_BPS)**: 150 bp
- **水印符号规模**: 6 × 957 = 5,742 符号
- **系统时钟**: 100 MHz (周期 10.0 ns)
- **背压注入模式**: 启用 M_AXIS_RESULT 随机背压（50% 概率随机拉低 TREADY，模拟实际 Zynq HP0/DDR 拥塞）

### 3.2 仿真执行输出与判据核验

执行命令（**必须在仓库根目录运行**：TB 用相对路径读 `tests/golden/*`，
在别处运行会以 `FATAL: 无法打开 tests/golden/reads_cw.hex` 退出；
按 `AGENTS.md` 的日志纪律，仿真输出落 `logs/iverilog/<run-id>/`，不留在仓库根）：
```bash
RUNID="run_$(date +%Y%m%d_%H%M%S)_4way_top_lc6"; mkdir -p "logs/iverilog/$RUNID"
iverilog -g2012 -DSRPE_BATCH_4WAY_MODNAME=srpe_batch_4way -o "logs/iverilog/$RUNID/sim_core_4way" \
  -I hw/ip/Dna_accelerator_core_1_0/hdl \
  hw/ip/Dna_accelerator_core_1_0/hdl/local_correlator.v \
  hw/ip/Dna_accelerator_core_1_0/hdl/fifo_sync_sdpram_b64.v \
  hw/ip/Dna_accelerator_core_1_0/hdl/s2mm_pack64.v \
  hw/ip/Dna_accelerator_core_1_0/hdl/srpe_batch.v \
  hw/ip/Dna_accelerator_core_1_0/hdl/srpe_batch_4way.v \
  hw/ip/Dna_accelerator_core_1_0/hdl/Dna_accelerator_core_v1_0_S_AXI_LITE_CTRL.v \
  hw/ip/Dna_accelerator_core_1_0/hdl/Dna_accelerator_core_v1_0.v \
  hw/ip/Dna_accelerator_core_1_0/hdl/Dna_accelerator_core_4way.v \
  hw/sim/tb_accelerator_core_4way.v \
  && vvp "logs/iverilog/$RUNID/sim_core_4way" 2>&1 | tee "logs/iverilog/$RUNID/sim.log"
```

实测输出日志：
```text
================================================================
[TB 4-WAY TOP] 启动 DNA 加速器顶层核 4-Way vs 2-Way 端到端自检
[TB 4-WAY TOP] 配置: NUM_LC=6, STRIDE=807, BATCH=64, READ_BPS=150
================================================================
[TB 4-WAY TOP] 黄金数据载入完成: 64 条读段码字, 5742 个水印符号
[TB 4-WAY TOP] 阶段 1: 预载水印数据...
[TB 4-WAY TOP] 水印预载完成: 6 区域 x 957 符号 @119235000
[TB 4-WAY TOP] 阶段 2: 流式发送 40B 读段...
[TB 4-WAY TOP] 全部 64 条读段送入完成 @132745000
[TB 4-WAY TOP] 阶段 3: AXI-Lite 启动计算核心...
[TB 4-WAY TOP] 启用 M_AXIS_RESULT 随机背压注入 (模拟 DMA 拥塞)
[TB 4-WAY TOP] 进度 @cyc 100000: 2W完成 0/64, 4W完成 0/64
[TB 4-WAY TOP] 进度 @cyc 200000: 2W完成 0/64, 4W完成 0/64
[TB 4-WAY TOP] 进度 @cyc 300000: 2W完成 0/64, 4W完成 64/64
[TB 4-WAY TOP] 进度 @cyc 400000: 2W完成 0/64, 4W完成 64/64
================================================================
[TB 4-WAY TOP] 顶层吞吐与周期度量结果:
  - 2-Way 顶层总耗时: 438785 周期 (约 438.8k 周期)
  - 4-Way 顶层总耗时: 252139 周期 (约 252.1k 周期)
  - 顶层加速比 (2W / 4W): 1.740x (周期缩减 42.54%)
  - 背压握手状态: 零丢拍，零数据挂起
================================================================
[TB 4-WAY TOP] 顶层 4-Way vs 2-Way 输出等价性检验:
  - 收到记录条数: 2-Way=64, 4-Way=64, 期望=64
  - 2-Way 码字回传错误: 0 / 64 (B26 判据)
  - 4-Way 码字回传错误: 0 / 64 (B26 判据)
  - 4-Way vs 2-Way 分数一致率: 64 / 64 (差异: 0)
  - 4-Way vs 2-Way 位置一致率: 64 / 64 (差异: 0)
  - 4-Way vs 2-Way 码字一致率: 64 / 64 (差异: 0)
================================================================
[TB 4-WAY TOP] PASS: 顶层 4-Way 与 2-Way 100% 逐位全等，加速比 1.740x！
================================================================
```

---

## 4. 性能与加速比定量分析

| 指标项 | 2-Way 基线顶层核心 | 4-Way 流水化顶层核心 | 收益与变化幅度 | 判定与意义 |
|:---|:---:|:---:|:---:|:---|
| **顶层计算周期数 (Cycles)** | 438,785 | 252,139 | **缩减 186,646 周期 (-42.54%)** | 包含水印装入、读段装入与流式回传 |
| **纯核心比对加速比** | 1.000x (基线) | 1.929x | **提速 92.9%** | 接近理论极限 2.0x (双倍位置步进) |
| **顶层端到端整机加速比** | 1.000x (基线) | **1.740x** | **提速 74.0%** | 计入非比对开销后的真实系统提速 |
| **随机背压丢拍率** | 0 拍 (0.0%) | 0 拍 (0.0%) | 100% 无损 | 证明 AXI-Stream 打包逻辑抗背压鲁棒 |
| **最大匹配得分一致率** | 64 / 64 (100%) | 64 / 64 (100%) | 0 差异 | 逐位一致 |
| **最佳位置索引一致率** | 64 / 64 (100%) | 64 / 64 (100%) | 0 差异 | 逐位一致 |
| **回传码字逐位一致率** | 64 / 64 (100%) | 64 / 64 (100%) | 0 差异 | 逐位一致 |

---

## 5. Vivado IP 封装与替换 Checklist

为后续将 4-Way 核心合入 Vivado Block Design，提供明确的工程实施步骤：

- [x] **RTL 文件完备性**：`hw/ip/Dna_accelerator_core_1_0/hdl/Dna_accelerator_core_4way.v` 与 `srpe_batch_4way.v` 均已就绪并完成仿真；
- [x] **接口兼容性**：S_AXI_LITE、S_AXIS_DATA、M_AXIS_RESULT 信号线名称、位宽、时钟域与 2-Way 100% 一致；
- [x] **单模块 OOC 时序**：OOC 综合实测 WNS = +2.197 ns @ 100MHz；
      ⚠️ **这是 srpe 比对核单模块的 Out-of-Context 结果，不蕴含整机收敛**，
      整机 implementation 的实测见 §6.3；
- [x] **资源边界**：RAMB36 保持为 8 块，LUT 占用 8,673，完全符合 XC7Z010 芯片硬资源约束；
- [ ] **Vivado IP 重新打包**：在 Vivado IP Packager 中更新 `component.xml`，将顶层实体指定为 `Dna_accelerator_core_4way` 或更新 `srpe_batch.v` 符号链接；
- [ ] **顶层 Block Design 重新导出**：执行 `tools/run_vivado_build.sh` 启动整机综合实现与 bitstream 生成。

---

## 6. 2026-09-09 复核补充（main 接管后重跑，修正三处口径）

本节是 main 会话对 §1～§5 的独立复核结果。§1～§5 的数字本身可复现（我逐条重跑确认），
但有三处口径必须修正，否则会误导读者。

### 6.1 §3～§4 的 1.740x 是 `NUM_LC=6` 玩具配置，生产几何实测为 1.929x

顶层核 `Dna_accelerator_core_4way.v` 的默认参数是 `NUM_LC=50`（见该文件 26 行），
`tests/golden/wm_regions.hex` 也恰好是 50 × 957 = 47,850 个符号 —— **50 区域才是生产几何**。
而 §3.1 的仿真配置写的是 `NUM_LC=6`，只有生产几何的 1/8 比对工作量，
固定开销（47,850 符号水印预载 + 64 条读段装入）占比被严重放大，压低了整机加速比。

用 `-DCFG_NUM_LC=50` 重跑同一个 TB（run-id `run_20260908_202106_4way_top_lc50`）：

| 指标 | NUM_LC=6（原报告） | **NUM_LC=50（生产几何）** |
|---|---:|---:|
| 2-Way 顶层总周期 | 438,785 | 3,229,621 |
| 4-Way 顶层总周期 | 252,139 | 1,674,217 |
| **顶层整机加速比** | 1.740x | **1.929x** |
| 周期缩减 | 42.54% | 48.16% |

**结论：4-way 在生产几何下的顶层加速比是 1.929x，与纯比对核加速比 1.929x 完全重合。**
原因是比对工作量放大 8.33 倍后，固定开销被摊薄到可忽略。
也就是说 §4 表格里「顶层 1.740x 低于核心 1.929x」这个差距是玩具配置的产物，
**生产配置下并不存在**。这对 4-way 是更有利、也更准确的结论。

### 6.2 原 TB 载入了黄金模型却从不比较；补上后暴露出黄金向量本身的判据缺陷

原 `tb_accelerator_core_4way.v` 把 `tests/golden/stage1_fwd_expect.txt` 读进
`exp_score` / `exp_pos` 两个数组后**从未做过任何比较**（`has_golden_exp` 只被赋值、
never used），并且解析方式有三处错误：未跳过 `#` 注释头、按两列读取实为三列的
`idx pos score`、且把 pos 当成 score。也就是说它看起来有黄金判据，实际是死代码 ——
原报告「100% 逐位一致」的真实含义只是 **4-Way 与 2-Way 自洽**，两核同时错成一样是抓不出来的。

补上真实比对后（`NUM_LC=50`），出现 **2/64 条位置与黄金文件不符，且 2-Way 与 4-Way 同时不符**，
分数则 64/64 全对。逐条追查后确认 **这不是 RTL 缺陷，是黄金向量的位置判据本身不可用**：

`tools/readout.py::_align_one` 用 FFT 做互相关得到 float64 数组，再 `np.argmax`。
同分并列时，各并列位置的浮点值并不严格相等，argmax 取的是「浮点值最大」而非「位置最小」：

```text
read  4  整数精确并列位置 [17193, 17954, 32993]，整数分数均为 59
         FFT 浮点值        59.0 / 59.000000000000014 / 59.0   -> argmax 选中 17954（中间）
read 30  整数精确并列位置 [2621, 32735, 37642]，整数分数均为 59
         FFT 浮点值        59.0 / 59.0 / 59.00000000000001    -> argmax 选中 37642（末位）
```

黄金文件里这两条的位置由 1e-14 量级的舍入误差决定。RTL（2-way 与 4-way 一致）确定性地
选最小位置，于是差异恰好 2 条。前 64 条读段中共有 **9 条（14.1%）存在同分并列**，
其余 7 条恰好 argmax 也落在最小位置上，所以没暴露。

### 6.3 修正后的判据与交付口径

新增 `tools/make_stage1_tie_golden.py`，用**整数精确滑窗**（不走 FFT，无浮点）算出
每条读段在 RTL 搜索空间内的同分并列集，写入 `hw/sim/golden/stage1_fwd_ties.txt`。
TB 判据改为：

1. **分数**必须与整数精确最大分**严格相等**（无并列问题，硬判据）；
2. **位置**必须**属于同分并列最大集**，而不是等于黄金文件里那一个单值。

> 为什么不写进 `tests/golden/`：`tools/make_golden.py` 结尾会把该目录下**所有**文件
> 重算进 `SHA256SUMS`，新增文件会破坏「不带参数调用即逐字节复现已冻结 SE150」这条判据。

复现命令（须在仓库根目录运行）：

```bash
python3 tools/make_stage1_tie_golden.py          # 生成并列集黄金向量
RUNID="run_$(date +%Y%m%d_%H%M%S)_4way_top_lc50"; mkdir -p "logs/iverilog/$RUNID"
iverilog -g2012 -DSRPE_BATCH_4WAY_MODNAME=srpe_batch_4way -DCFG_NUM_LC=50 \
  -o "logs/iverilog/$RUNID/sim" -I hw/ip/Dna_accelerator_core_1_0/hdl \
  hw/ip/Dna_accelerator_core_1_0/hdl/{local_correlator,fifo_sync_sdpram_b64,s2mm_pack64,srpe_batch,srpe_batch_4way,Dna_accelerator_core_v1_0_S_AXI_LITE_CTRL,Dna_accelerator_core_v1_0,Dna_accelerator_core_4way}.v \
  hw/sim/tb_accelerator_core_4way.v \
  && vvp "logs/iverilog/$RUNID/sim" 2>&1 | tee "logs/iverilog/$RUNID/sim.log"
```

`NUM_LC` 小于 50 时 TB 会明确打印「非生产几何，未做黄金模型比对，本次结论仅为
4-Way 与 2-Way 自洽」，不再让读者把自洽误读成正确性。

### 6.4 尚未关闭：整机时序未收敛

§5 checklist 的最后两项仍未打勾。并行会话 `vivado-4way-build` 已完成整机构建并做了路径级定位，
结论分两层：

**（a）整机 100 MHz 未收敛，WNS = -0.252 ns**（估算上限约 97.5 MHz）。
这与 §5 的 OOC WNS = +2.197 ns 不矛盾 —— 前者是含 PS7/AXI 互联/DMA 的整机布线结果，
后者只是比对核单模块。**本例即为「OOC 正裕量不蕴含整机收敛」的直接反证**
（模块级 +2.197 ns，整机 −0.252 ns），归为 `AGENTS.md`「不得把仿真/综合当板级证据」同类错误。
在整机时序收敛前不得宣称「4-way 整机构建通过」；基于该比特流的任何板测结果等于超频运行，
**不能作为时序合格的证据**。

**（b）但瓶颈不在 4-way 加速核。** 该会话打开 routed DCP，用
`-max_paths 5000 -nworst 1` 保证**每个失败端点至少一条**，完整覆盖 43/43 个失败端点：

```text
ENDPOINTS_FOUND    43
COMPLETE_VERDICT   endpoints=43   accelerator=4   other=39
端点分布  ic_hp/s04_couplers(upsizer) 30 · axi_dma_0(SG engine) 9 · differential_voter_0 4
slack 范围  -0.252 ～ -0.003 ns
```

> ⚠️ 该目录早期的 `verdict.txt` 里写的是 `touching_accelerator: 0`，那是
> **被 200 条上限截断的查询产物，不可引用**；以上面的完整枚举为准。

那 4 条「accelerator」端点经逐条核对是正则误捕：落在
`differential_voter_0/inst/{debug_write_count,total_write_count}_reg[*]/CE`，
即**调试/统计计数器的时钟使能**，不是 4-way 选优树，slack −0.003 ns（43 个里最轻），
源点同样是 desparsifier，属同一条握手链的末梢负载。
**`Dna_accelerator_core` / `srpe_batch` 在全部 43 个失败端点中出现 0 次。**

失败集的源寄存器高度收敛：全部 43 个端点**共享同一个源寄存器**
`desparsification_dec_0/inst/u_dp/in_bits_reg[3]/C`（早期截断查询看到的
`in_bits_reg[3,4,6,7]` 是同一簇），终点集中在 `ic_hp/s04_couplers/auto_us`（upsizer）
与 `axi_dma_0/GEN_SG_ENGINE`；形态是典型的 AXI `WVALID→WREADY` 未打拍组合回路，
13 级逻辑、route 占 74.2%。**这意味着在该寄存器→`M00_AXI_WVALID` 的组合段上打一拍，
理论上可一次性消除整个违例集合**，不必逐条修补。

**这是既有瓶颈，不是 4-way 造成的**：2-way 基线的最差路径终点是同一个
`.../M_AXI_WDATA_I_reg[56]/CE`，slack 仅 **+0.136 ns（1.4% 周期）**。
4-way 只是把这仅存的裕量吃掉（9.510→9.897 ns，+0.387，与 WNS 差 −0.388 吻合；
其中 logic +0.276、逻辑级数 11→13，route 仅 +0.111）。
反证：2-way 基线第 6~9 差的路径源点还是 `u_srpe_batch/pos_base_reg[6]`，
到了 4-way，加速核已经掉出最差路径榜。

资源两条判据均通过：LUT 12,232→**15,499** ≤ 17,600（69.5%→88.1%）；
**RAMB36 44→44 ≤ 60（4-way 未增 BRAM）**；FF 14,830→16,908；DSP 3 不变。
`report_design_analysis -congestion` 显示 placer/router 均无 level>5 拥塞窗口，
**故「88% LUT → 拥塞 → 时序恶化」的推测不成立**，回归来自路径起点被推远、逻辑级数 +2。

**因此「回退 2-way」是治错病** —— 它会白丢 1.929x 加速比且不触及病灶。
而且要修的 `desparsification_dec` 是**既有 IP**，不是 4-way 新增逻辑，与「瓶颈是既有的」自洽。
处理方向按代价从低到高：impl 策略 `Performance_ExplorePostRoutePhysOpt`（零 RTL 改动，
只差 0.252 ns，最快证伪）→ `ic_hp` S04 口开 AXI Register Slice（BD 属性，+1 拍）→
最后才考虑把 `desparsification_dec` 的 `M00_AXI_WVALID` 寄存输出。
注意若 impl 策略失败，**不得解释为「拥塞太严重」**（拥塞已被证伪），应直接转入打拍方案。

原始证据与复现命令见 `logs/vivado/recovery_20260909/findings.md`。
