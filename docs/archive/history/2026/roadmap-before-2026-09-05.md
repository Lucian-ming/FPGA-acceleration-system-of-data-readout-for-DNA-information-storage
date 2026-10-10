# 04 · 开发方向与路线图

## 总原则：先建立「可验证」，再谈「加速」

> **2026-08-30 更新**：板端闭环验收（G3）已完成——第五次上板回传经 LDPC 译码后图片
> SHA-256 与判据逐位相同，四级 DDR 快照逐级比对全过。本节记录的是达成它所用的策略，
> 保留下来作为方法论；下一阶段的重点见 `docs/archive/history/2026/pre-bkb220-handoff-2026-10-10/status.md` 与本文末尾的排队项。
> 闭环只在「2,048 条源读段 / `--orient both` / `score_min 67` / SE150」这组参数下成立。

这个项目**曾经**最大的问题不是性能，而是尚未完成从板端 Stage1/Stage2/Stage3 到 LDPC 的闭环验收。
当时的整体策略是：

> 先用软件把每一级的正确输出算出来（黄金向量），
> 再让硬件逐级去对齐这些向量，每对齐一级就锁定一级。

`tools/golden_model.py` 已经把这条路的第一块砖铺好了：
`verify-code` 证明了算法链路成立，`simulate` 能从 FASTQ 直接产出各级的期望输出。

截至 2026-08-16：Stage1/2/3 三级 RTL 均有黄金回归；D1（方案B + SCORE_MIN）、
C1~C3 已落地并有离线判据；P5 纯 Python LDPC 在 Linux 完成黄金自检
（重建 JPEG 与原图逐字节相同）。**除上板本身外，P1/P2 的离线部分已全部完成**；
剩余主路径是「重新生成比特流 → 烧板 → 真实回传 → LDPC → 图片哈希」。

**强烈建议不要一上来就改 RTL。** 推荐的替换顺序是「软件全链 → 逐级换成硬件」，
每一步都有可回归的判据；否则六个缺陷叠加，改完也无法判断是否改对。

---

## P0 · 立刻可做（半天～1 天）

| 任务 | 判据 |
| --- | --- |
| 用 `golden_model.py simulate` 产出 R0.83 SE150 的全套黄金向量：Stage1 每条 (pos,score)、Stage2 的 81,000 bit、Stage3 的 64,800 bit | 四个文件落盘并记录 SHA-256 |
| ~~为 Voter 建文件型黄金 Testbench~~ ✅ 2026-08-16 完成：`tb_differential_voter.v` 接入 `run_sim.sh stage2`，并新产出 `stage2_in.hex` / `stage2_rtl_expect.hex`（板端语义：正反双向、不过滤分数） | 两轮 4,096 条记录投票 81,000 bit 逐位相同；ARLEN/WLAST/WSTRB/调试寄存器全查 |
| 删除 `gui_app.spec` 里的 `('dec_input.txt', '.')` | EXE 内不再携带任何正确答案 |
| 补 `clients/python/requirements.txt`（`numpy`、`Pillow`），并注明需要 Python ≥ 3.8 | 干净环境 `pip install -r` 后能跑 |
| 把 `five_to_four_decoder.v` 标注为废弃或直接按契约改对 | 不再有与契约矛盾的死代码 |

## P1 · 打通「真实结果」链路（核心，建议 2～3 周）

按依赖顺序修，每修一项都用对应的黄金向量回归。

0. ~~**D1 反向互补**~~ ✅ 2026-08-16 完成：方案B（双向发送 + Voter SCORE_MIN=67 过滤）。
   - RTL 判据：`run_sim.sh stage2` 三轮逐位通过（SCORE_MIN=67 两轮 + 0 一轮）；
   - 软件判据：方案B 语义 dec_input（88 bit 错误）经 `tools/ldpc_decode.py`
     译码后 info 0 错误，`decoded_image.jpg` 与 `Milk coronet.jpg` **逐字节相同**。

1. **B1 水印预载**（PS 首版已实现，待 AXIS/上板验证）
   - 决定预载数据格式：建议保持「1 符号/32-bit 拍」的现有硬件行为不变，
     改由 PS 把 40,500 个符号**展开成 50 个区域 × 957 个符号 = 47,850 拍**，
     每个区域前写一次 `reg1 = region_id`，分 50 次 DMA；
   - 或者改 RTL：一拍解析 16 个符号 + 由硬件自己按 `MUL957` 地址展开区域（吞吐更好，改动更大）；
   - `MAX_WATERMARK_SIZE=10,240` 与拒绝静默截断已经落地；需继续核实错误包语义和 DMA/BRAM 时序。
   - **判据**：读回水印 BRAM（或加一个 debug 寄存器）与黄金水印逐符号相同。

2. **B4 + B2 位序统一**（✅ 已完成 RTL 黄金回归）
   - 以 `docs/archive/history/2026/pre-bkb220-handoff-2026-10-10/data-contract.md` 为准，让 `first.py`、`srpe_batch`、`voter` 三方一致；
   - 建议统一到**位平面**布局，因为 Voter 与客户端已经是它，只需改 `srpe_batch` 的
     `cw_data` 取位方式和 `cw_acc` 的拼装方式。
   - **判据**：给 Stage1 喂黄金读段，输出的 `pos` 与软件模型逐条一致（允许极少数并列峰差异）。

3. **B3 水印差分**（PS 首版已实现，等待 Stage2 与整链判据）
   - `PIPE_DONE_STAGE2` 已调用 PS 软件 XOR（10,125 B），但它只能在获得 Voter 的 RTL/板端输出后验证；
   - 端到端跑通、拿到第一张正确图片之后，再决定是否把 XOR 下沉进 Voter。
   - **判据**：`decoded_image.jpg` 与 `Milk coronet.jpg` 的 SHA-256 相同。

4. **B5 + B6 Stage3**（✅ 已完成；B7/B8/B9 也已在同次控制层重写中解决）
   - `conv40_32` 改成用组内第一个 bit 作取反标志；
   - `in_pool` 改成 `in_pool | (RDATA << in_bits)`，并把插入与消费合并成一个
     互斥的赋值分支，消除同周期覆盖。
   - **判据**：喂黄金 81,000 bit，输出与 `codeword_R083.txt` 逐位相同。

5. **C1 + C2 条数**
   - Voter 改用 `conn->total_reads_received`；
   - 尾批不足 64 条时，由 PS 补零凑满一批，或给 `srpe_batch` 加一个「本批有效条数」寄存器。
   - **判据**：发 1,000 / 51,781 / 51,776 条都能正常结束且结果可解释。

## P2 · 任务配置化（水印长度、读段数运行时适配）

这是用户明确要的目标，但**必须排在 P1 之后**——在一条不正确的链路上做参数化只会放大问题。

设计要点：

- 协议增加一个 `PKT_CONFIG`（或扩展包头），携带**版本化的任务描述**：
  格式版本、水印格式（文本 bit / 32-bit 值）、水印有效位数 L、读段碱基数 READ_BPS、
  读段条数、各级期望输出长度；
- PS 校验这些值是否落在综合上限内（`NUM_LC_MAX`、`REF_LEN_MAX`、DDR 预算），
  超限返回明确错误码，**不得静默截断**；
- PL 侧把 `NUM_LC / STRIDE / REF_LEN / CODEBITS` 从 `parameter` 改成寄存器可配，
  并遵守 `docs/archive/history/2026/pre-bkb220-handoff-2026-10-10/data-contract.md` 第 7 节的约束
  （`NUM_LC*STRIDE = L - READ_BPS`，`REF_LEN = STRIDE + READ_BPS`）；
- `CODEBITS`（读段长度）会改变数据通路宽度，**无法完全运行时可变**；
  务实做法是综合时支持一组离散档位（如 150 / 250 bp），运行时选择档位并公开支持范围。

**判据**：同一比特流下，SE150 与「截取的短水印」两种任务都能给出正确结果；
超限任务返回可诊断错误而不是错误结果。

## P3 · 工程可复现（可与 P1 并行）

1. 从当前板导出**完整的** BD Tcl（含 PS7 全部 DDR/MIO/PHY 配置），消除 `design_1` 与 `top_bd` 的分裂；
2. `build.tcl` 改成以脚本自身位置推导仓库根，加 `set_property ip_repo_paths` + `update_ip_catalog`，
   并把 XDC 纳入构建流；
3. 提交一次完整成功的构建日志、XSA、BSP 配置和可下载的 ELF；
4. 补 LICENSE、第三方声明（Xilinx / lwIP）、`.gitignore`。

**判据**：干净机器上从仓库根执行两条命令即可得到 XSA 和 ELF。

## P4 · LDPC（建议先做软件，暂缓上板）

现状是「唯一实现是一个 Windows EXE，没有源码」，这既挡住了 Linux 复现，也挡住了上板。

**建议的第一步不是写 RTL，而是写一个 Python 参考译码器：**

1. 解析 `dvb_s2_r5_6.pchk` 与 `permutation64800`，转成可版本控制的稀疏图描述；
2. 用它实现 bit-flipping / min-sum 硬判决译码，和 EXE 的输出逐位比对
   （`dec_input.txt` → `decoded_bits.txt` 已有黄金对照）；
3. 这一步完成后，Linux 上就不再依赖 EXE，`ldpc_pipeline.py` 可以切换到原生实现。

只有拿到可审计的算法、定点位宽、迭代/早停策略和黄金向量之后，第 4 个 PL IP 才有意义。
届时还要评估：`ic_lite` 需从 4 个从端口扩到 5 个、`ic_hp` 需增主端口、
XC7Z010 的 BRAM 余量（Voter 已占约 810 kbit / 全片 2,160 kbit）。

---

## 反向互补问题的历史量化（已由方案 B 完成离线闭环）

当前实现是 `first.py --orient both` 双向发送，加 Voter `SCORE_MIN=67` 过滤；Stage2 黄金
回归和下游 LDPC 已通过，剩余的是随 G3 完成真实板端验收。以下保留修复前的量化依据。

用软件模型对 SE150 做的实测（`tools/golden_model.py`）：

| 测量 | 结果 |
| --- | --- |
| 读段按**正向**与真实编码序列比对，一致度 ≥140/150 的比例 | **50.7%** |
| 读段按**反向互补**比对，一致度 ≥140/150 的比例 | **48.0%** |
| **两个方向取更优**后，一致度 ≥140/150 的比例 | **98.8%**（平均 148.9/150） |

结论非常明确：**这批测序数据里约一半的读段是反向互补的**。`first.py` 现在默认发送
正向和反向互补两份读段；修复前 Stage1/Voter 尚未依据 `score` 排除错误方向，噪声会进入共识。
当前已通过 Voter 的 `SCORE_MIN=67` 在投票前过滤低分记录。

用全量 51,781 条读段跑软件模型，前后对比：

| 软件模型（191× 覆盖） | 共识误码率 | 码字误码率 | 能否译码 |
| --- | ---: | ---: | --- |
| 不处理反向互补（旧实现） | 1.33%（1,078 bit） | **2.33%**（1,507 bit） | ❌ 超过硬判决门限 |
| 处理反向互补（`--rc`，实测 25,615 条反向） | **0.0037%**（3 bit） | **0.014%**（9 bit） | ✅ 远在纠错能力内 |

**只这一件事就把误码率降低了 167 倍，整条算法链路随即闭合。**
（顺带证明读段质量很好：两方向取优后平均 148.9/150 ≈ 99.3%，问题不在测序数据。）

**这意味着：即使把其他实现缺陷全部修好，没有反向互补处理也拿不到正确图片。**
当时评估的做法如下；当前已经落地第 1 种的双向发送，并在 Voter 用分数阈值过滤：

1. **上位机做**（最省事，强烈建议先这样验证）：`first.py` 对每条读段同时准备正向和
   反向互补两份，或者由主机先做一次轻量比对来定向。代价是发送量翻倍或主机算力上升。
2. **PL 做**：`srpe_batch` 对每条读段同时算两个方向的相关峰并取更优。
   反向互补在 2-bit 编码下就是「符号值异或 1 后整体反序」，硬件代价不大，
   但要多一倍的相关运算或多一套位平面 BRAM。

另外两个已量化的算法改进点：

- **比对分的旧实现没有被利用。** 当前 Voter 已在解析拍用 `SCORE_MIN=67` 过滤；阈值 75
  会因丢覆盖而变差，不能随意改动 67 或脱离对应黄金向量。
- **水印相关的信噪比在 150 bp 下本来就紧张**：真实峰值约 75/150，
  而 40,351 个候选位置的噪声最大值约 59～62。SE250（250 bp）会显著改善这一点，
  这可能正是数据集同时提供 SE250 的原因——值得作为后续方案评估。

### 已实测的端到端闭环

整条链路（原始 FASTQ → 比对 → 投票 → 反稀疏化 → LDPC → JPEG）**已经在软件上跑通并验证**：

```bash
python3 tools/golden_model.py verify-code                  # 1 秒，证明算法契约
python3 tools/golden_model.py simulate --limit 60000       # 约 4 分钟，当前链路的天花板 → LDPC 失败
python3 tools/golden_model.py simulate --limit 60000 --rc  # 约 8 分钟，补上反向互补 → LDPC 成功
# 把产出的 dec_input.txt 交给 LDPC EXE（注意先看下面「运行 LDPC EXE 的前置条件」）
R5_6_LDPC_hard_decoder.exe dec_input.txt TestBitStream.txt image.jpg H
```

实测结果：`--rc` 版本输出 `Decoding successful!`，`image.jpg` 的 SHA-256 与
`Milk coronet.jpg` **完全相同**（`fcd0cf90...b6b1f2c3`）；不带 `--rc` 的版本
`Decoding failed!`，图片是错的。**所需读段数只要约 1,080 条（≈4× 覆盖）**，
详细曲线见 `docs/archive/history/2026/pre-bkb220-handoff-2026-10-10/status.md` D1。

因此后续所有 RTL 修复的目标非常明确：**让硬件复现这份软件结果**，
每一级都有可逐位比对的期望输出。

### 运行 LDPC EXE 的前置条件（踩过的坑）

`R5_6_LDPC_hard_decoder.exe` 是 MinGW 构建，依赖 `libstdc++-6.dll`、
`libgcc_s_seh-1.dll`、`libwinpthread-1.dll`。**缺 DLL 时它不报错、不输出、退出码还是 0**，
非常容易被误判成「输入数据不对」。这三个 DLL 只藏在历史 `gui_app.exe` 里，
已用 `tools/extract_ldpc_dlls.py` 提取到 `clients/python/resources/`。

✅ 已修复（2026-08-13）：`ldpc_pipeline.py` 会把 EXE + `.pchk` + `permutation64800`
和三个 DLL 一起拷进临时目录（缺失时警告并提示提取工具；运行后还有输出缺失检查兜底），
判据见 `docs/archive/history/2026/pre-bkb220-handoff-2026-10-10/status.md` A10。

WSL 下可直接调用 Windows EXE（binfmt 互操作），但工作目录必须放在
`/mnt/c/...` 等 Windows 可见路径上；放在 `\\wsl$` UNC 路径下会以错误码 53 失败。
