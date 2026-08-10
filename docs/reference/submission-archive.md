> **归档说明**：本文是 2025-11-07 提交资产的清单与校验和（2026-08-05 整理），内容仍然有效。

# 历史提交资产清单

## 来源、复制与差异结论

来源为用户指定的 `E:\桌面\提交`，于 2026-08-05 复制。该目录中的子目录 `FPGA-acceleration-system-of-data-readout-for-DNA-information-storage/` 已与当前仓库逐文件比较：所有共有路径字节完全一致；当前目录额外包含 GitHub 根 `README.md`、根 XSA、R0.83 数据和本次整理文档。因此没有复制该源码子目录，以免形成嵌套的重复源码树。

其余 18 个文件共 231,602,980 字节已完整保留在 `archive/submission_2025-11-07/`。每个目标文件均以 `cmp` 与源文件逐字节核对一致。

## 演示文件是另一数据版本，且含黄金结果

| 演示资产 | 已核实的事实 | 开发用途 |
| --- | --- | --- |
| `演示文件/read.fastq` | 207,124 行 = **51,781 条** FASTQ 记录，序列长度均为 **150 bp**；与 `data/R0.83_data/Sequencing data/DNA-40.5Kb-MC-SE150.fastq` 完全相同。 | 保留为 R0.83 的 SE150 输入和协议回归样本。 |
| `演示文件/watermark.txt` | 81,001 字节，含 81,000 个文本 bit 和换行；SHA-256 为 `79c64ec4...2a87daed`，与 R0.83 文本水印不同。 | 必须独立于 R0.83 水印处理，不能以“同长度”推定同内容。 |
| `演示文件/result.txt`、`dec_input.txt` | 两者均为 64,800 字节，SHA-256 都为 `767d1948...e2a0d108`，且与 `data/R0.83_data/.../codeword_R083.txt` 完全相同。 | 这是正确 LDPC 输入/码字的黄金参考，不能被生产代码伪装成 FPGA 回传。 |
| `演示文件/decoded_bits.txt` | 54,000 字节、SHA-256 `0a2aa3b5...8c40e04f`，与 R0.83 `source_bit.txt` 完全相同。 | LDPC 信息位黄金参考。 |
| `演示文件/decoded_image.jpg` | 6,624 字节、SHA-256 `fcd0cf90...b6b1f2c3`，与 R0.83 `Milk coronet.jpg` 完全相同。 | 最终图像黄金参考。 |
| `演示文件/gui_app.exe` | 31,800,183 字节，Windows x86-64 GUI 可执行文件。 | 仅作历史行为/打包参考；可维护实现仍以 Python 源码为准。 |

用户已明确：当前真实 FPGA 流水线结果不正确，历史演示中存在直接使用正确结果生成图片的做法。由上述哈希关系可证实“正确码字、译码位和图像”确实作为演示文件存在。未来验收必须把它们作为 oracle 比较，而非运行时输入：

```text
允许：真实 FPGA 回传 -> LDPC -> 输出，与 result/decoded_bits/decoded_image 比对
禁止：result/dec_input -> LDPC 或图片，跳过真实 FPGA 回传
```

## 归档资产校验和

| 路径 | 大小（字节） | SHA-256 |
| --- | ---: | --- |
| `069a9fb033ef3d47642e6aee8818b9dc.jpg` | 231,107 | `4dd9a46272ad353e3f83dc0df4733d274ddd0208419c6a22b826145bc186ec77` |
| `309927374fc5eddde6b97e9cd998e577.png` | 38,536 | `c4b3bf9ff700363f0d04d03d187db7528fa96680b06e0553322c6fc1c140410b` |
| `35f83b5023b881ead7fc1621b3e611c7.jpg` | 212,665 | `3d9dffddd7bb8647eff3fd0d964bcb8b3297f25c22656a578e0a8d8b52243e46` |
| `5bcc86f5d3889be808822ea8fe0fe267.png` | 38,652 | `48cfc7c9ac5e3d8984286d4266824ff6544648a396a9cc3c3722ea96558d151c` |
| `DAN存储读出FPGA实现架构_49030_演示视频.mp4` | 172,929,104 | `6acef1059f79c1c189dd730f95abcf2fa2ba9f19e4cd970d20ab22fc69e217eb` |
| `DNA存储读出FPGA实现架构_49030_承诺书.pdf` | 203,316 | `2ec7a24741148e10d6508cc31abe60c0c006a1f2864af1ed4e276171c3e77c39` |
| `DNA存储读出FPGA实现架构_49030_技术文档.pdf` | 1,401,484 | `9242246624c4db143abb4503421d9bee7fd4177d87831d0e89858ed1a3ca8f41` |
| `DNA存储读出FPGA实现架构_49030_海报.pptx` | 1,618,432 | `f932cc5c99c13c9b1ed99b05cb440322918596d6d7294728598d2715371aeaaa` |
| `DNA存储读出FPGA实现架构_49030_重要代码.rar` | 1,209,267 | `5375d874787eb3418018d1532858a8d5adfe875e32f2153b8df494c9f70c2eec` |
| `图片1.jpg` | 27,611 | `0987b236e5ba684744aceccab009a9d04da21e31bad07054f98dccc9de44fc0d` |
| `微信图片.jpg` | 2,541,944 | `23894fb0edfc0cad1f667bdb36f392d50bbab1e37742b935dfe4fbb4b366fde8` |
| `演示文件/dec_input.txt` | 64,800 | `767d194809f9d89f9ba66e9194f198fe472dd32448a69bfc6327b180e2a0d108` |
| `演示文件/decoded_bits.txt` | 54,000 | `0a2aa3b514b4b470c80a8affa64a5795dba34bbab134153c3d528c298c40e04f` |
| `演示文件/decoded_image.jpg` | 6,624 | `fcd0cf90bd680e7bbdc203e3398119504da0897acac9e2117008b4efb6b1f2c3` |
| `演示文件/gui_app.exe` | 31,800,183 | `e4542d6ebeb3cea0107fde9e9aa2d0da84836eee5a0977bb1e676f4b6ec0372f` |
| `演示文件/read.fastq` | 19,079,454 | `f66503ae9f91ce8980876520e5c93330586cfd2870336cc834b2fab352a37691` |
| `演示文件/result.txt` | 64,800 | `767d194809f9d89f9ba66e9194f198fe472dd32448a69bfc6327b180e2a0d108` |
| `演示文件/watermark.txt` | 81,001 | `79c64ec4a573b4bf5931653e8d1afd8bd512be0ef6b5b0a3cebf04072a87daed` |

## 历史文档与压缩包的处理状态

- 已按 PDF 审阅流程提取并视觉检查 21 页技术文档的代表性页面。该文档记录的历史参数为 51,781 条、300-bit 读段和 81,000-bit 水印，且声称无错恢复；它与当前代码、R0.83 数据和用户确认的真实流水线故障存在冲突。因此它是设计意图和历史提交证据，不是当前正确性的证明或最新规格。
- `DNA存储读出FPGA实现架构_49030_重要代码.rar` 已原样归档。当前环境没有 `7z`、`unar`、`unrar` 或 `bsdtar`，不能可靠列出/解压 RAR5；从可读字符串可见其包含当前已有的 `clients/`、`hw/`、`sw/` 路径。待在 Windows 或具备 RAR5 工具的环境中解压后，应再对其全部内容进行 SHA-256 差异审计，特别检查是否含未提交的测试向量、工程文件或旧版 Python。
