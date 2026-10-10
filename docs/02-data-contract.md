# 02 · 数据契约（编码、位序、码表）

> 本文是**唯一权威**的数据格式规范。软件、PS 固件、RTL 三方必须以本文为准；
> 任何一方要改格式，先改本文再改代码。
> 全部结论由 `tools/golden_model.py` 用 `data/R0.83_data/` 可复现验证：
> `python3 tools/golden_model.py verify-code` 必须打印 `PASS`。

---

## 1. 碱基 ↔ 2 bit

| 碱基 | bit(高,低) | 值 |
| --- | --- | --- |
| A | 0,0 | 0 |
| T | 0,1 | 1 |
| G | 1,0 | 2 |
| C | 1,1 | 3 |
| N | 按 A 处理 | 0 |

与 `clients/python/first.py` 的 `BASE2BITS` 一致。

## 2. 序列 ↔ 位平面码流（**位平面，不是交织**）

长度 L 个碱基的序列展开成 2L bit 时，采用位平面布局：

```
bit[0     .. L-1  ] = 每个碱基的高位   （plane 0 / upper layer）
bit[L     .. 2L-1 ] = 每个碱基的低位   （plane 1 / lower layer）
```

L=40,500 时即 81,000 bit。`differential_voter_v1_0.v` 的 `calc_layer_position()`
（`bit_idx<150` → `position+bit_idx`，否则 `LAYER_SIZE+position+bit_idx-150`）就是这个布局；
`first.py` 的 `seq_to_read_bytes()`（`out_bits[idx]` / `out_bits[READ_BPS+idx]`；
2026-09-03 由 `seq_to_40B()` 改名并按 `read_bps` 参数化）也是这个布局。

`srpe_batch.v` 已在 B2/B4 修复中统一为同一布局：`cw_data[i]` 进入高位平面，
`cw_data[READ_BPS+i]` 进入低位平面；输出也按相同顺序回传。该约定已由
`bash tools/run_sim.sh stage1` 用 64 条黄金读段验证，禁止恢复为交织布局。

## 3. 水印与差分

水印文件 `r0.83_watermark.txt` 的 81,000 bit 采用**同一位平面布局**，
即水印符号 i 的高位是 `wm[i]`、低位是 `wm[40500+i]`。

```
稀疏流 = 编码序列位平面码流  XOR  水印码流         （逐位）
```

`SequenceL81000NoPeriodOnly2ndFILE`（81,000 个小端 32-bit 的 0/1）与文本水印
**内容完全相同**，可互换使用（已验证）。

## 4. 稀疏码本与 5b→4b 反稀疏化

稀疏流的每 5 bit 是一个码字，码本恰好是**全部汉明重量 ≤ 2 的 16 个 5-bit 字**
（1 + 5 + 10 = 16）。在 R0.83 数据上这 16 个值全部出现且没有第 08 个值出现。

反稀疏化规则（**用码流顺序表述，与端序无关**）：

```
设一组的 5 个 bit 按码流顺序为 b0 b1 b2 b3 b4
则输出 4 bit 按码流顺序为      b1^b0, b2^b0, b3^b0, b4^b0
即：第一个 bit 是取反标志，后 4 bit 是数据
```

等价查找表（左为 b0..b4，右为输出的 4 bit，均按码流顺序）：

| 输入 | 输出 | 输入 | 输出 |
| --- | --- | --- | --- |
| 00000 | 0000 | 01001 | 1001 |
| 00001 | 0001 | 01010 | 1010 |
| 00010 | 0010 | 01100 | 1100 |
| 00011 | 0011 | 10000 | 1111 |
| 00100 | 0100 | 10001 | 1110 |
| 00101 | 0101 | 10010 | 1101 |
| 00110 | 0110 | 10100 | 1011 |
| 01000 | 1000 | 11000 | 0111 |

`desparsification_decoder_v1_0.v` 的 `conv40_32()` 已在 B5 修复为
`grp[4:1] ^ {4{grp[0]}}`，与上述规则一致，并已通过随机背压 RTL 回归。
`five_to_four_decoder.v` 是未被综合引用的死文件；其表也已校正，但不得把它当作生产实现依据。

## 5. 已验证的端到端等式

```
desparsify( plane_bits(DNA-40.5Kb-MC (R=0.83).txt)  XOR  r0.83_watermark.txt )
    == codeword_R083.txt            （64,800 bit 逐位相同，已验证 PASS）
```

再经 `R5_6_LDPC_hard_decoder.exe`（DVB-S2 R=5/6 硬判决）应得到
`source_bit.txt`（54,000 bit）和 `Milk coronet.jpg`。

## 6. 传输/存储位序（当前实现，供对齐用）

| 环节 | 约定 |
| --- | --- |
| PC→板 读段 | 300 bit 位平面码流，**每字节 LSB-first** 打包成 40 B |
| PC→板 水印 | 81,000 bit，每字节 LSB-first；逻辑数据 10,125 B，当前传输按 8 字节对齐为 10,128 B |
| Stage1 输出 | 48 B/条 = `{padding, codeword[299:0], pos[15:0], score[9:0]}`，u64 小端 |
| Stage2 输出 | 81,000 bit，64 bit/拍，**拍内 LSB-first**，1,266 拍（末拍 40 bit 有效） |
| Stage3 输出 | 64,800 bit，同样 64 bit/拍 LSB-first，1,013 拍 = 8,100 B |
| 板→PC 结果 | 8,100 B 原样回传；`first.py` 按**每字节 LSB-first** 展开成 64,800 个字符 |

所有当前生产比特流均采用「码流顺序 + 字节内 LSB-first」。Stage1 AXIS 装配的
`in_buf[k]` 因而直接对应码流 bit k，PS 可逐字节 XOR 水印；任何一方更改此约定都必须
重新生成黄金向量并更新本表。

## 7. 换数据集时必须一起改的量

| 量 | R0.83 SE150 | 依赖关系 |
| --- | --- | --- |
| 水印/参考长度 L | 40,500 nt = 81,000 bit | 决定 Voter `TOTAL_BITS`/`LAYER_SIZE`、BRAM 深度 |
| 读段长度 READ_BPS | 150 bp | 决定 `CODEBITS=2*READ_BPS`、每条字节数 |
| 每条字节数（线上） | 40 B | `ceil(2*READ_BPS/8)` **再向上对齐到 4 B**（AXIS 是 32 bit，`Dna_accelerator_core_v1_0.v:16`）：38 → **40**。只按 `ceil(2*READ_BPS/8)` 算会少一拍 |
| Stage1 结果宽度 | 326 bit → 48 B | `2*READ_BPS + 16 + 10` |
| NUM_LC / STRIDE / REF_LEN | 50 / 807 / 957 | `NUM_LC*STRIDE = L - READ_BPS`，`REF_LEN = STRIDE + READ_BPS` |
| 读段条数 | 51,781 | 决定 DDR 预算、DMA 长度、Voter `total_reads` |
| 码字长度 | 64,800 bit | `L*2*4/5`，必须等于 LDPC 码长 |

SE250（64,800 条 × 250 bp）需要 `NUM_LC=50, STRIDE=805, REF_LEN=1055, CODEBITS=500`，
每条**线上 64 B**（有效 63 B + 1 B 对齐补零，同上一行的对齐规则），
Stage1 结果 526 bit → 72 B。**现有比特流不支持 SE250。**
主机侧与黄金向量已按这套几何落地（`tests/golden/se250/`的GEOMETRY/SHA清单，生成入口为tools/make_golden.py；几何鉴别力见AGENTS及06验证文档）；
RTL / 固件仍是 SE150。
