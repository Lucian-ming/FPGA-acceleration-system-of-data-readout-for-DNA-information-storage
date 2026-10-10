# D0 基准数据集清单（R0.83_data）

> `data/` 在 `.gitignore` 里（54 MB，且属实验原始数据），**不入库**。
> 但 clean checkout 因此拿不到 D0，`tools/run_g3.sh` / `tools/make_golden.py`
> 全部无法运行——这是 [13](../docs/05-implementation-plan.md) §5 最终验收表
> 「别人能否不用人工修路径独立跑通」的**硬阻塞**。
>
> 本清单给出逐文件 SHA-256，使接收方能验证自己拿到的副本与本项目一致。
> **本文件必须随数据变更同步刷新**：`bash data/MANIFEST.sh` 重新生成。

生成时间：2026-09-11T04:10:43Z

| 文件 | 大小 | SHA-256 |
| --- | ---: | --- |
| `R0.83_data/Sequencing data/DNA-40.5Kb-MC-SE150.fastq` | 19M | `f66503ae9f91ce8980876520e5c93330586cfd2870336cc834b2fab352a37691` |
| `R0.83_data/Sequencing data/DNA-40.5Kb-MC-SE250.fastq` | 36M | `dde178bc0df9e3c500641ff61ff29faca701c5087948d7268d1f5e88e3f05a80` |
| `R0.83_data/Source data/Encoded_codeword/codeword_R083.txt` | 64K | `767d194809f9d89f9ba66e9194f198fe472dd32448a69bfc6327b180e2a0d108` |
| `R0.83_data/Source data/Encoded_sequences/DNA-40.5Kb-MC (R=0.83).txt` | 40K | `96c416c258020091f8d11e2caa678625d7f79a5c5f25fb5d48d6d89aa04d1c8d` |
| `R0.83_data/Source data/Original data files/Milk coronet.jpg` | 8.0K | `fcd0cf90bd680e7bbdc203e3398119504da0897acac9e2117008b4efb6b1f2c3` |
| `R0.83_data/Source data/Original data files/source_bit.txt` | 56K | `0a2aa3b514b4b470c80a8affa64a5795dba34bbab134153c3d528c298c40e04f` |
| `R0.83_data/Source data/Watermark sequences/r0.83_watermark.txt` | 80K | `b7c842f30be1c49bb57b0161d7685a0a0761668b5d2bd0df024145ae7075d05f` |
| `R0.83_data/Source data/Watermark sequences/SequenceL81000NoPeriodOnly2ndFILE` | 320K | `de8c12b8ed8d10ee70eb2ba37809c58f58b658e969502cd80f883218251de272` |

## 用途对照

| 文件 | 被谁用 |
| --- | --- |
| `Sequencing data/DNA-40.5Kb-MC-SE150.fastq` | D0 主输入，`run_g3.sh` / `make_golden.py` / `bench_align.py` |
| `Sequencing data/DNA-40.5Kb-MC-SE250.fastq` | SE250 profile（**当前比特流仅支持 150 bp，无法端到端**） |
| `Source data/Watermark sequences/r0.83_watermark.txt` | 权威水印源；数据集里的规范化副本见 `tests/datasets/common/` |
| `Source data/Encoded_codeword/codeword_R083.txt` | 黄金码字，误码统计的参照 |
| `Source data/Original data files/Milk coronet.jpg` | 端到端唯一判据的目标图片（SHA-256 `fcd0cf90…f2c3`） |
| `Source data/Original data files/source_bit.txt` | 原始比特流 |
| `Source data/Encoded_sequences/…(R=0.83).txt` | 编码后参考序列 |
| `Source data/Watermark sequences/SequenceL81000NoPeriodOnly2ndFILE` | 水印原始来源文件 |

## 获取

> **2026-09-11 决策：D0 明确不入库、不随仓库分发。**
> 依据是体积（54 MB 进 Git 历史后极难移除）与权属未确认（数据非本项目产出）。
> 这是一条**有意的取舍**，不是遗漏——`docs/05` G7/G8 已据此改写为
> 「接收方须自备等价数据集」。

本数据集非本项目产出，**不随仓库分发**。
复现者需向项目维护者索取，或使用自己的等价数据集并相应重生成黄金向量
（`python3 tools/make_golden.py`）——注意后者会改变端到端判据哈希，
不能再与 `fcd0cf90…f2c3` 比对。

**权属与许可尚未确认**，见 `docs/03-status.md` P5 工程技术债。
