# 01 · 系统架构与算法模型

本文描述系统「应该是什么」。所有数值都已用 `data/R0.83_data/` 的黄金数据或 RTL 源码核对，
凡是推测都显式标注。与本文冲突的历史文档（`docs/reference/legacy-tech-note.md`、
2025-11 技术 PDF）以本文为准。

---

## 1. 这个项目在做什么

DNA 信息存储的**读出**（readout）环节：把测序仪产出的大量短读段（FASTQ）还原成原始文件。

编码侧（不在本仓库内）采用 **watermark（水印同步码）+ 稀疏码 + LDPC** 的经典组合：

```
原始文件 (Milk coronet.jpg, 6,624 B)
  └─ 54,000 bit 信息位            source_bit.txt
      └─ DVB-S2 LDPC R=5/6 编码 → 64,800 bit 码字      codeword_R083.txt
          └─ 4b→5b 稀疏化        → 81,000 bit 稀疏流
              └─ XOR 水印         → 81,000 bit
                  └─ 2 bit/碱基   → 40,500 nt DNA 序列  DNA-40.5Kb-MC (R=0.83).txt
                      └─ 合成/测序 → 51,781 条 x 150 bp  SE150.fastq
```

读出侧（本仓库）就是把这条链**倒过来走**。三个主计算核在 PL；在 Stage2 与 Stage3 间，
当前由 PS 做一次软件 XOR 作为过渡：

| 级 | 载体 | 输入 | 输出 | 作用 |
| --- | --- | --- | --- | --- |
| Stage 1 | `Dna_accelerator_core` (PL) | 读段 40 B/条 | 48 B/条 | 与水印滑窗相关，求每条读段的最佳起点 |
| Stage 2 | `differential_voter` (PL) | 48 B/条 | 81,000 bit | 按起点把读段投票叠加，重建共识序列 |
| Stage 2.5 | `apply_watermark_differential()` (PS) | 共识序列 + 水印 | 81,000 bit 稀疏流 | 逐字节 XOR；是 B3 的过渡实现 |
| Stage 3 | `desparsification_decoder` (PL) | 81,000 bit | 64,800 bit | 5b→4b 反稀疏化，还原 LDPC 码字 |
| Stage 4 | PC 端 EXE | 64,800 bit | 54,000 bit + JPEG | DVB-S2 R=5/6 LDPC 硬判决译码 |

> **实现边界**：B3 已由 `sw/app/echo.c` 接入 PS 状态机，不是 PL IP；Stage2 已有黄金
> 向量逐位判据，但 Stage2.5 的真实 DDR/cache 输入输出和整链仍待上板验收，不能由此宣称 G3 完成。

---

## 2. 物理拓扑

```
PC (Python GUI/CLI)
  │  TCP :7  自定义 0xBEEF 协议
ARM Cortex-A9 (裸机 + lwIP)  ── GEM0 ── PHY
  │  AXI-DMA (SG 模式, MM2S/S2MM)      GP0=控制  HP0=数据
  ├─ Stage1 DNA core     0x43C0_0000   AXIS 进 / AXIS 出（走 DMA）
  ├─ Stage3 Desparsifier 0x43C1_0000   AXI-Lite 控制 + AXI4 Master 自取 DDR
  └─ Stage2 Voter        0x43C2_0000   AXI-Lite 控制 + AXI4 Master 自取 DDR
DDR3 512MB：水印 / 读段 / 各级中间结果（地址表见 docs/05-interfaces.md）
```

地址来自 XSA 内 `design_1.hwh`，器件 `xc7z010clg400-1`，PL 100 MHz。
注意 `hw/scripts/bd.tcl` 注释里把 Stage2/Stage3 的地址写反了。

数据流不是链式直连，而是**每一级都经过 DDR 中转**，由 PS 逐级配置寄存器、启动、轮询 done：

```
PC → DDR(reads) → [DMA MM2S] → Stage1 → [DMA S2MM] → DDR(48B/read)
                                              ↓ Stage2 自己读 DDR
                                        DDR(81,000 bit)
                                              ↓ PS：共识 XOR 水印（B3，10,125 B）
                                        DDR(81,000 bit 稀疏流)
                                              ↓ Stage3 自己读 DDR
                                        DDR(64,800 bit) → PS → TCP → PC → LDPC → JPEG
```

---

## 3. Stage 1：水印滑窗相关（srpe_batch.v）

参考序列（=水印）被切成 `NUM_LC` 个互相重叠的区域，每个区域 `REF_LEN` 个符号，区域间距 `STRIDE`：

```
REF_LEN = STRIDE + READ_BPS
L       = (NUM_LC-1) * STRIDE + REF_LEN = NUM_LC * STRIDE + READ_BPS
```

R0.83 的实际取值完全吻合，说明这套几何是为该数据集量身定制的：

```
NUM_LC=50, STRIDE=807, REF_LEN=957, READ_BPS=150
→ L = 50*807 + 150 = 40,500 符号 = 81,000 bit   ✅ 与水印文件长度一致
→ 可搜索起点 0..40,350，恰好覆盖 150 bp 读段的全部合法位置
```

引擎每批处理 **BATCH=64** 条读段：把 64 条读段转置进「位平面 BRAM」
（`plane_lo/plane_hi`，各 150×64 bit），然后对每个候选起点并行地对 64 条读段计分，
逐位比对 2-bit 符号，取全局最高分及其位置。输出 326 bit：

```
res_din = { codeword[299:0], global_pos[15:0], score[9:0] }
global_pos = region * STRIDE + best_pos      // 0..40,350
```

**两个已实测的算法限制**：

- 引擎只按**正向**比对。SE150 里约一半读段是反向互补的，它们会被定位到随机位置
  （见 `docs/03-status.md` D1）。
- 用水印做参考时，正确位置的期望峰值只有约 75/150（因为读段与水印只在稀疏位为 0 处相同），
  而 40,351 个候选位置的噪声最大值约 59～62——信噪比在 150 bp 下相当紧张。
  SE250（250 bp）会显著改善这一点。

**关键推论（用于「水印长度自动适配」）**：给定水印长度 L 和读段长度 READ_BPS，
必须选一组 `NUM_LC * STRIDE = L - READ_BPS`，并令 `REF_LEN = STRIDE + READ_BPS`。
水印 BRAM 深度 = `NUM_LC * REF_LEN`（R0.83 为 47,850 × 2 bit ≈ 95.7 kbit）。
换成 SE250（READ_BPS=250）时 `L - READ_BPS = 40,250 = 50 × 805`，
即 `NUM_LC=50, STRIDE=805, REF_LEN=1055`，但同时要改 `CODEBITS=500`、
Stage1 输出打包宽度和 Stage2 的 `CODEWORD_BITS/UPPER_LAYER_BITS` —— **不是改一个常量的事**。

---

## 4. Stage 2：投票重建（differential_voter_v1_0.v）

每条读段的 300 bit 码字按「位平面」摊回长度 81,000 的投票数组：

```verilog
bit_idx < 150 :  addr = position + bit_idx                      // 高位平面
bit_idx >= 150:  addr = LAYER_SIZE + position + (bit_idx-150)   // 低位平面
```

BRAM 为 81,000 × signed 10 bit 累加器，读段 bit 为 1 则 +1，为 0 则 −1（饱和到 ±511）。
全部读段处理完后按 `vote > 0` 判决，得到 81,000 bit 共识码流，
按 64 bit 一拍、**拍内 LSB-first** 写回 DDR（1,266 拍 = 10,125 B，最后一拍只有 40 bit 有效）。

Voter IP 本身的“差分”只体现在 ±1 累加；它**不直接保存或异或水印**。
当前 PS 会在 `PIPE_DONE_STAGE2` 使 Voter 输出与原始打包水印逐字节 XOR，
再交给 Stage3；后续若下沉到 PL，必须以这份 LSB-first 行为为兼容基准。

---

## 5. Stage 3：反稀疏化（desparsification_decoder_v1_0.v）

综合进 IP 的是顶层里的 `conv40_32()` 函数（`five_to_four_decoder.v` 是**未被引用的死文件**；
其查找表已校正，但不参与当前综合）：

```verilog
grp = x[5k +: 5];
r[k] = grp[4:1] ^ {4{grp[0]}};          // 第一个 bit=取反标志
```

该规则与从黄金数据反解出的 16 项映射**完全等价**（证明见 `docs/02-data-contract.md`）。
每拍 64 bit 进、按 40 bit→32 bit 转换、64 bit 出，81,000 → 64,800 bit（1,013 拍 = 8,100 B）。

---

## 6. Stage 4：LDPC（PC 端）

`clients/python/resources/R5_6_LDPC_hard_decoder.exe`（Windows x86-64，无源码）
读取 `dec_input.txt`（64,800 个 '0'/'1' 字符）、`dvb_s2_r5_6.pchk`、`permutation64800`，
以硬判决模式输出 54,000 bit 和 JPEG。这是目前唯一的 LDPC 实现载体，也是可维护性上的最大风险。
