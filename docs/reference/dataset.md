> **归档说明**：本文是 R0.83 数据集的清单与校验和（2026-08-05），内容仍然有效。
> 数据集与算法的**已验证**对应关系（编码序列 ⊕ 水印 → 5b4b → 码字）见 `docs/archive/history/2026/pre-bkb220-handoff-2026-10-10/data-contract.md`。

# R0.83 数据集清单与使用约定

## 来源和完整性

本目录于 2026-08-05 从用户指定的 `E:\文档\R0.83_data\R0.83_data` 及其后提供的 `R0.83_data.rar` 完整复制到仓库的 `data/R0.83_data/`。共 8 个文件、56,486,685 字节；下表 SHA-256 已与源目录/压缩包逐一比对一致。原始 RAR5 包也保留为 `archive/R0.83_data_source.rar`（6,894,183 字节，SHA-256 `7ed2e5ae978b742892ed79e51b3d4c34efb751ef5f530a774352d1fb60480894`）。导入时用户明确说明：数据版本之间的水印大小、读段数可能不同，不能把任何历史常量当成通用协议。

| 仓库路径 | 大小（字节） | SHA-256 | 已核实格式/用途 |
| --- | ---: | --- | --- |
| `data/R0.83_data/Sequencing data/DNA-40.5Kb-MC-SE150.fastq` | 19,079,454 | `f66503ae9f91ce8980876520e5c93330586cfd2870336cc834b2fab352a37691` | FASTQ，207,124 行 = 51,781 条读段，每条序列 150 bp；与历史演示 `read.fastq` 完全相同。 |
| `data/R0.83_data/Sequencing data/DNA-40.5Kb-MC-SE250.fastq` | 36,836,306 | `dde178bc0df9e3c500641ff61ff29faca701c5087948d7268d1f5e88e3f05a80` | FASTQ，259,200 行 = 64,800 条读段，每条序列 250 bp。 |
| `data/R0.83_data/Source data/Encoded_codeword/codeword_R083.txt` | 64,800 | `767d194809f9d89f9ba66e9194f198fe472dd32448a69bfc6327b180e2a0d108` | 无换行的纯 `0/1` 文本，共 64,800 bit。 |
| `data/R0.83_data/Source data/Encoded_sequences/DNA-40.5Kb-MC (R=0.83).txt` | 40,500 | `96c416c258020091f8d11e2caa678625d7f79a5c5f25fb5d48d6d89aa04d1c8d` | 无换行的纯 A/C/G/T 文本，共 40,500 nt。 |
| `data/R0.83_data/Source data/Original data files/Milk coronet.jpg` | 6,624 | `fcd0cf90bd680e7bbdc203e3398119504da0897acac9e2117008b4efb6b1f2c3` | 240×302 JPEG 原图参考。 |
| `data/R0.83_data/Source data/Original data files/source_bit.txt` | 54,000 | `0a2aa3b514b4b470c80a8affa64a5795dba34bbab134153c3d528c298c40e04f` | 无换行的纯 `0/1` 文本，共 54,000 信息 bit。 |
| `data/R0.83_data/Source data/Watermark sequences/SequenceL81000NoPeriodOnly2ndFILE` | 324,000 | `de8c12b8ed8d10ee70eb2ba37809c58f58b658e969502cd80f883218251de272` | 81,000 个 little-endian 32-bit 值，值域仅为 0/1。 |
| `data/R0.83_data/Source data/Watermark sequences/r0.83_watermark.txt` | 81,001 | `b7c842f30be1c49bb57b0161d7685a0a0761668b5d2bd0df024145ae7075d05f` | 纯 `0/1` 文本，有效长度 81,000 bit，末尾含一个换行。 |

## 已知关系与不可假设的关系

- `source_bit.txt` 的 54,000 bit 与 DVB-S2 R=5/6 的 64,800-bit 码字长度在数学上匹配；`codeword_R083.txt` 也恰为 64,800 bit。这是强相关线索，但在没有 LDPC 源码/黄金测试脚本前，仍不得假定具体位序、缩短/填充方式和交织顺序。
- R0.83 包同时含两种读段长度：SE150 为 51,781 条×150 bp，SE250 为 64,800 条×250 bp。40,500 nt 正好等于 162×250，可能与 SE250 版本相关，但在没有数据准备器/黄金链路前，不能把此算术关系当成已证实映射。
- 现有 `clients/python/first.py` 的 `seq_to_40B()` 会把每条序列截断/补齐到 **150 bp**；因此它与 SE150 的长度一致，却会截断 SE250。必须让任务配置显式声明 `read_bases` 和编码规则，不能由文件名或默认常量隐式决定。
- 文本水印和 32-bit 水印文件都含 81,000 个逻辑位/值，但二者的逐位对应关系尚未验证；它们必须视为两个独立的输入格式，不能通过“长度相同”推定内容相同。
- 当前 DNA RTL 默认水印存储几何为 `NUM_LC=50`、`REF_LEN=957`、每符号 2 bit，即容量 95,700 bit；与 R0.83 文本水印的 81,000 bit 不可直接等同。需要明确“文件 bit → 区域/符号/BRAM”的转换器和运行时配置约束。

## 后续程序应遵守的数据契约

1. 上位机在发送前解析输入格式，报告 `watermark_format`、有效逻辑位数、字节数、DNA 序列长度、FASTQ 检测条数和请求发送条数；原始文件不应被就地修改。
2. 协议需传递经验证的任务元数据，而不只发送裸水印/批数据：至少包括格式版本、有效水印长度、读段数量、每条编码长度和期望阶段输出长度/编码版本。
3. 板端必须校验这些元数据是否落在已综合资源上限内；超限应返回明确错误，不得用固定 `TOTAL_READS` 或静默截断填充继续运行。
4. `Milk coronet.jpg`、`source_bit.txt` 和 `codeword_R083.txt` 仅用于离线黄金比对；真实运行链路必须从 FPGA 实际回传数据进入 LDPC，再生成图片。不得在生产路径用参考结果替代板端结果。
5. 新增数据版本时，新建版本目录和清单，保留 SHA-256、参数、生成方法和期望结果；不要覆盖 R0.83 文件。
