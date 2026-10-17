# D0 基准数据集清单（R0.83_data）

> `data/` 在 `.gitignore` 里（D0 约 54 MB + `test-sets/` 约 717 MB，且属实验原始数据），**不入库**。
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

---

## 测试集与生成源（`data/test-sets/`，2026-10-17 并入）

> 这三份原先放在 `E:\桌面`。2026-10-17 按**逐文件 SHA-256** 校验通过后并入本项目，
> **桌面原件（含冗余压缩包 `dna-multimedia-simulation-v2-20261013.zip`）已删除**。
> `data/` 不入库，本清单只登记身份；数据本身仍须自行保存。

| 目录 | 文件数 | 体积 | 逐文件清单 SHA-256 |
| --- | ---: | ---: | --- |
| `DNA测试集_20261014/` | 147 | 108 MB | `66f489c8965b1c6cdb2760c3661a644cc93c75424dfd94a146b89068a4898156` |
| `dna-multimedia-simulation-v2-20261013/` | 613 | 591 MB | `dc9efa6396f6e98b922ecf29a2ecf3e15fb46a637cc34484960b0e48ea94152e` |
| `scientific-image-datasets-20261012/` | 184 | 19 MB | `8e993d8353fb04c2661ecc7d457bbc3cd8d5ab12ea7cce7f6bea64f62a7ee9d2` |
| **合计** | **944** | **717 MB** | 见下方 `SHA256SUMS` |

**本地逐文件清单**：`data/test-sets/SHA256SUMS`（944 行）。

```bash
cd data/test-sets && sha256sum -c SHA256SUMS     # 应全部 OK
```

该清单自身的 SHA-256：`2cb9b1e8057fbe68cf4b383661daf9aa2cea3e47650f7a71bb1225de112396b3`

### 各目录是什么

| 目录 | 用途 |
| --- | --- |
| `DNA测试集_20261014/` | **42 例成品测试集**（21 个资产 × {baseline, challenge}）。每例含 `read.fastq`、`watermark.txt`、`期望结果.txt`（该例期望载荷 SHA-256 与软件侧结果）、`参考输出.jpg`；顶层 `00_索引.tsv` 汇总。**客户端手动全流程测试与板端 v2 42 例都用它。** |
| `dna-multimedia-simulation-v2-20261013/` | 生成上述测试集的**仿真源包**：`datasets/`、`payloads/`、`encoded/` 及 provenance/清单。是成品集的**来源与可复现依据**。 |
| `scientific-image-datasets-20261012/` | 源图像与生成工具（19 MB），重新生成数据时的起点。 |

### ⚠️ 读这套数据时要带上的两条边界

1. `00_索引.tsv` 里的「期望载荷 SHA256 / 软件侧结果」是 **`score_min=65`** 口径。
   板端 v2 42 例用的是 **`score_min=67`**，两者**不能直接混用**；
   板端逐例结论见 [`docs/board/bkb220/v2-42cases-v1.1-2026-10-16.md`](../docs/board/bkb220/v2-42cases-v1.1-2026-10-16.md)。
2. `期望结果.txt` 只覆盖**该例**；`参考输出.jpg` 是软件侧译码结果，供肉眼比对，
   不是硬件黄金向量。

### 与 `tests/datasets/` 的关系

`tests/datasets/`（D0/D1/D2，9.5 MB）是**入库**的小型主机测试集，用途不同；
本节的 42 例是**板端/客户端验收**用的大数据集，体积大且不入库。两者不要互相替代。
