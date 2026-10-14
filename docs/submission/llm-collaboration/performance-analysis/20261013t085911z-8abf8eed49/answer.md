> 脱敏副本，原件 `20261013T085911Z-8abf8eed49/{prompt.txt,answer.md}`。本机绝对路径、邮箱、凭据形模式及非白名单私网 IP 已替换；除脱敏与换行规范化外保留原文。

以下是只读静态分析结论。**本次没有修改或创建文件，也没有运行 Vivado、XSim 或板测。** 周期来自 RTL 静态推导；当前 P16 数字来自仓库报告；K=2/4 的资源和速度均为外推估算。

## 1. 当前数据通路

[PACKAGED_VARIANTS.txt](<仓库根目录>/hw/ip/PACKAGED_VARIANTS.txt) 与 [component.xml](<仓库根目录>/hw/ip/Dna_accelerator_core_1_0/component.xml) 都列有 `srpe_batch_4way.v` 和 `srpe_batch_pway.v`。实际激活哪个核由 [Dna_accelerator_core_v1_0.v](<仓库根目录>/hw/ip/Dna_accelerator_core_1_0/hdl/Dna_accelerator_core_v1_0.v) 的 generate 分支决定：`C_STAGE1_P_WAYS=4/C_STAGE1_PIPE_TREE=0` 选 4-way；`16/1` 选 `srpe_batch_pway`。组件默认值是 `4/0`；本轮 P16 构建记录的是 `16/1`。

在 [srpe_batch_pway.v](<仓库根目录>/hw/ip/Dna_accelerator_core_1_0/hdl/srpe_batch_pway.v) 中：

- `plane_lo` 和 `plane_hi` 是读段的两个位平面，每行 64 bit，行数为 `READ_BPS=150`。`a_addr` / `a_lo_q` / `a_hi_q` 用于比对读口；`b_addr` / `b_lo_q` / `b_hi_q` 用于装载和输出读改写。`S_RUN` 每拍取一个碱基索引，得到该索引下 64 条读段的两个位平面。
- 水印由 `wm_bram` 存储，地址是 `lc_idx * REF_LEN + wm_rd_offset`。`wm_rd_addr_q`、`wm_sym_q` 形成同步读流水；`wm_win[p]` 保存 `pos_base+p` 对应的候选水印符号。
- `match_mask[p][t]` 对位置 `p`、读段 `t` 做符号比较。P16 时每拍并行比较 **16 个候选起点 × 64 条读段，共 1,024 个匹配位**。
- `score[p][t]` 是寄存器数组，不是 BRAM；它有 `16×64×10=10,240` 个计分位。`best_sc`、`best_pos`、`best_region` 也都是寄存器。分数冻结后由 `gen_tree` 逐级选优。
- P16 OOC 基线报告为 8 个 RAMB36。按 RTL 几何和 64-bit 读口推算，其中水印约 4 个 RAMB36、两个读段平面合计约 4 个；报告只确认了总数，没有逐数组列出分摊，**4+4 是结构推算，须由新候选的层次利用率报告复核**。

## 2. K=2、K=4 的改动点

建议维持 16 个候选位置和 64 条记录的并行度，把 `S_RUN` 的时间维度改为每拍处理 K 个碱基索引。

| 项目 | K=2 | K=4 |
|---|---|---|
| 比较器 | 每拍 2 组 `16×64` 比较；相对现状新增 1,024 个 2-bit 符号比较单元 | 每拍 4 组 `16×64` 比较；相对现状新增 3,072 个 |
| 计分 | 优先保留每个 `score[p][t]` 一个累加器，每拍加两路匹配位的 popcount | 同一计分方案，每拍加四路匹配位的 popcount |
| 读段 BRAM | `a` 口读索引 j，`b` 口在 `S_RUN` 读 j+1；`b_we_*` 保持关闭。两个同步读口已存在 | 将 `plane_lo/hi` 按索引奇偶拆成两组；每组两端口各读一个索引，每拍合计取 j…j+3 |
| 水印 BRAM | 每拍需要两个水印符号读结果；把现有写口改为写入期写、运行期读，或按奇偶 bank 读 | 每拍需要四个水印符号；可用四个模 4 bank 各读一个，或两个奇偶 bank 各使用双读口 |
| 窗口 | 将 `wm_win` 扩成长度 `P_WAYS+K−1=17` 的滑窗，每拍移动 2 格并补入 2 个符号 | 滑窗长度 19，每拍移动 4 格并补入 4 个符号 |
| 控制 | `run_cnt` 改为分组计数；150 可整除 2，共 75 个 `S_RUN` 拍 | 38 个 `S_RUN` 拍；最后一组仅索引 148、149 有效，需屏蔽另外两路 |
| 选优 | 若共享计分器，16-way 选优树不变 | 若共享计分器，16-way 选优树不变 |

共享计分器方案在每拍把 K 路匹配位相加后更新 `score[p][t]`。这是新增计分器最少的方案。更利于保持原有计分路径的备选方案，是给每个 `(p,t)` 设置 K 个分组计数器，最后在 `S_UPD1` 前求和；代价是寄存器更多、末端归约更复杂。

## 3. 资源估算

当前 P16 整机布线报告为 33,987 LUT、36,067 FF、45 个 BRAM tile、3 个 DSP；LUT 余量为 19,213。[P16 构建摘要](<仓库根目录>/docs/benchmarks/bkb220-p4-p16-100mhz-build.md) 另记录 P16 的 WNS/WHS 与资源基线。P16 Stage1 的历史 OOC 基线是 26,867 LUT、25,829 FF、8 RAMB36；OOC 与当前整机的测量边界不同，不能直接相加当成实测。

以下是**共享计分器设计的外推估算**，不是综合结果：

| 配置 | LUT 增量估算 | 整机 LUT 粗估 | FF 增量估算 | Stage1 BRAM36 预期 | DSP 增量 |
|---|---:|---:|---:|---:|---:|
| K=2 | +2k～6k | 36k～40k | +0.2k～1k | 约 8；若水印端口推断复制，最多约 12 | 0 |
| K=4 | +6k～14k | 40k～48k | +0.5k～2k | 奇偶 bank 方案约 12；复制式读口可能更多 | 0 |

估算依据是每增加一路匹配面需增加 `16×64=1,024` 个符号比较与 popcount 逻辑；共享 `score` 和选优树避免按 K 复制整套计分与选优。P8 到 P16 的 OOC 报告增加了 12,435 LUT，但那同时增加了候选位置的计分器和选优树，不能直接按 K 倍套用。

如果把每路匹配、计分和选优都整套复制，P8→P16 的增量外推会得到 K=2 增加约 25k LUT、K=4 增加约 75k LUT；两者都会越过 XC7Z020 的 LUT 容量。实现应共享选优树和计分结构，或先单独评估分路计数方案。分路计数会相对当前全机 FF 增加约 4,096（K=2）或 14,336（K=4），这是按计数位宽推导的值。Stage1 当前无 DSP 运算需求，预计 DSP 增量为 0。

K=4 不因静态资源估算而必然不可行：奇偶读段 bank 方案预计多 4 个 RAMB36，LUT 粗估上限约 48k，仍在 53,200 之下；但高端估算只剩约 5.2k LUT 裕量，布线及时序可能成为门槛。**需要 OOC 探针确认。**

## 4. 100 MHz 时序风险

当前 P16 整机在 100 MHz 的 WNS/WHS 是 **+0.617/+0.017 ns**，失败端点为 0。最差路径从 `pos_valid_reg` 到选优树寄存节点，数据路径约 84.5% 是布线延迟。[当前 P16 timing 报告](<仓库根目录>/hw/build/bkb220-p16-enet0-100mhz-20261012T144141Z-board-migrate/reports/timing.rpt)

K=2/4 最可能出现的新关键路径：

1. `a_lo_q/a_hi_q` 与水印窗口比较后，经 K 路 popcount、`score` 加法，落到 `score[p][t]`。
2. K=4 bank 地址与水印多读口控制产生的高扇出和布线延迟。
3. 若用分路计数，最终 K 路计数求和进入 `gen_tree` 的路径。

探针需检查 `WNS/WHS`、TNS/THS 和失败端点数，并阅读最差路径的起止寄存器、逻辑级数、数据延迟与 net delay；重点关注 `a_addr`、`b_addr`、水印 bank 地址、`match_mask`、popcount、`score` 和 `pos_valid` 的扇出。当前仅有 0.617 ns setup 余量，K=4 尤其不能仅凭 LUT 预算判定通过。

## 5. OOC 探针步骤和命令

已读 [OOC 流程说明](<仓库根目录>/docs/submission/skill/fpga-timing-probe/readme.md)、[ooc_probe.tcl](<仓库根目录>/docs/submission/skill/fpga-timing-probe/ooc_probe.tcl) 和 [run_vivado_build.sh](<仓库根目录><本机路径>)。OOC 脚本在 `SYNTH_IMPL=1` 时会执行布局、物理优化和布线；布线后 WNS 或 WHS 为负、或找不到时序路径时以非零退出。综合-only 的 WNS 不可作收敛判据。

先在 RTL 为 `srpe_batch_pway` 增加参数（例如 `BASES_PER_CYCLE`），然后分别对 K=2、4 执行以下命令。命令是待 RTL 参数加入后的探针模板：

```bash
RUN_ID="stage1-k2-$(date -u +%Y%m%dT%H%M%SZ)-$$"
VIVADO=<本机路径>
mkdir -p "logs/vivado/$RUN_ID"
"$VIVADO" -version

SYNTH_PART=xc7z020clg400-2 \
SYNTH_IMPL=1 \
SYNTH_TAG="$RUN_ID" \
SYNTH_OUT_ROOT="logs/vivado/$RUN_ID/reports" \
SYNTH_GENERICS="P_WAYS=16 PIPE_TREE=1 BASES_PER_CYCLE=2 READ_BPS=150 REF_LEN=957 STRIDE=807 NUM_LC=50 BATCH=64" \
  "$VIVADO" -mode batch \
    -log "logs/vivado/$RUN_ID/vivado.log" \
    -journal "logs/vivado/$RUN_ID/vivado.jou" \
    -source docs/submission/skill/fpga-timing-probe/ooc_probe.tcl \
    -tclargs srpe_batch_pway 100 hw/ip/Dna_accelerator_core_1_0/hdl/srpe_batch_pway.v
```

K=4 使用独立 `RUN_ID` 并将参数改成 `BASES_PER_CYCLE=4`。查看 `util.rpt`、`util_hier.rpt`、`timing.rpt`，确认真实 BRAM 推断和最差路径。OOC 通过后，将该参数接入顶层、`component.xml`、`hw/scripts/build.tcl` 和制品 manifest，再用 WSL Vivado 2022.2 的 `tools/run_vivado_build.sh` 对 BKB220 完整 route。该脚本目前没有 K 参数；需先在构建 Tcl 中增加，例如 `stage1_bases_per_cycle=2`，随后按现有 `board=bkb220 part_name=xc7z020clg400-2 clk_mhz=100` 流程生成整机报告。

## 6. 可失败的验收判据

**OOC 阶段：**

- 使用 XC7Z020、100 MHz、`SYNTH_IMPL=1` 并完成 route；Vivado 2022.2。
- WNS≥0、WHS≥0、TNS/THS=0、setup/hold 失败端点均为 0，且存在受约束时钟路径。
- 建议 Stage1 OOC LUT≤40,000；当前非 Stage1 约 7.1k LUT，按此预算仍给整机留出约 6k LUT 空间。K=4 奇偶 bank 目标为 Stage1 RAMB36≤12，DSP 增量为 0。
- 任一项失败即不进入整机和板测；OOC 通过只代表模块级候选通过。

**整机和上板阶段：**

- BKB220 `xc7z020clg400-2` 完整 route，`clk_fpga_0=100 MHz`，WNS/WHS≥0、失败端点 0、DRC errors=0、无未约束时钟；建议整机 LUT≤48,000。
- 用新制品身份和 SHA 记录 bit/XSA/软件包；在生产几何下执行回归，覆盖 K=4 最后一组无效 lane、STRIDE 边界、选优并列规则，并逐条对比 P16 基线的 pos/score/结果记录。
- 板端全量 103,616 条记录至少连续三轮，经 LDPC 解码后图片 SHA 每轮均须等于 `fcd0cf90bd680e7bbdc203e3398119504da0897acac9e2117008b4efb6b1f2c3`；连续任务和状态复位也须通过。
- 性能须在与 8.95 s 基线相同的计时边界下低于 **3.70 s**。功能 SHA 与性能门槛分别判定，任一失败即不通过。

## 7. 预充填和选优排空能否重叠

静态周期分解是 `S_LAUNCH` 1 拍、`S_PREFILL` 18 拍、`S_RUN` 150 拍、`S_UPD1` 5 拍、`S_UPD2` 1 拍、`S_NEXT` 1 拍，共 176 拍。18+7 拍占 14.2%。这些数来自 P16 RTL 状态机和给定的 176 拍模型。

当前 FSM 串行执行，不能自然重叠。改成并行控制后，可以在前一块 `S_UPD1/S_UPD2/S_NEXT` 的 7 拍期间预充下一块的水印窗口，最多省 7 拍；预充所需的其余 11 拍仍留在关键路径上。实现需保留当前块的 `score`、`pos_valid`、`pos_base`、`lc_idx` 直到选优完成，并分开维护下一块地址和预充计数器。

若 K 路水印读口同时用于预充，可把初始窗口装载改成每拍读 K 个符号。按当前约两拍水印读延迟静态估算，预充下限约为 `ceil((P_WAYS+K−1)/K)+2`：K=2 约 11 拍，K=4 约 7 拍。这是待 RTL 验证的排程估算。

| 方案 | K=2 块拍数 | K=4 块拍数 | 相对 176 拍 |
|---|---:|---:|---:|
| 保留 18 拍预充、无重叠 | 101 | 64 | 1.74× / 2.75× |
| 保留 18 拍预充、重叠 7 拍选优 | 94 | 57 | 1.87× / 3.09× |
| K 路预充至 11/7 拍并重叠 7 拍 | 87 | 46 | 2.02× / 3.83× |

这些周期与加速比是静态外推，不是板测。按 [P16 时间预算](<仓库根目录>/docs/benchmarks/bkb220-p16-time-budget.md) 的 PL 7.77 s、PS 1.08 s 分解外推，K=4 保留 64 拍时全量约 3.91 s，略高于 3.70 s；若能省掉 7 拍，约 3.60 s。该分解本身是模型推导，结果须由同口径上板测量确认。

## 8. 判断与未验证项

- **K=2**：读段可复用现有双端口，预计资源可控；按周期模型单独提速不足以达到 3.70 s 目标。
- **K=4**：用共享计分器和奇偶 bank 时，静态资源估算仍有落地空间；其 timing、BRAM 推断和布线余量均**未验证/需要探针**。在给定目标下，K=4 需要进一步降低预充开销或与选优排空重叠。
- 尚未实现 K=2/4 RTL，也未完成 OOC、功能回归、整机 route 或板测。水印 BRAM 的精确读口映射、K=4 多读口实现及预充排程都需由候选 RTL 的 Vivado 报告确认。

**交付路径：最终答复正文**；本次没有文件产物。
