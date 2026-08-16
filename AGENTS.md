# FPGA DNA 数据读出项目：AI / 开发协作指南

## 语言与范围

- 与用户沟通、代码注释、新增文档默认使用中文。
- 不重构无关代码，不删除历史数据或构建产物（`data/`、`archive/`、两份 XSA 只读）。
- 未经用户同意，不修改、重命名或覆盖 `data/R0.83_data/` 中的任何文件。

## 文档地图（改代码前先读）

| 文档 | 作用 |
| --- | --- |
| `docs/README.md` | 文档索引 |
| `docs/01-architecture.md` | 系统架构与算法模型 |
| `docs/02-data-contract.md` | **数据格式的唯一权威规范**（编码、位序、5b4b 码表） |
| `docs/03-status.md` | 现状与缺陷清单（含 `文件:行号` 证据） |
| `docs/04-roadmap.md` | 开发顺序与验收判据 |
| `docs/05-interfaces.md` | TCP 协议、寄存器、DDR 地址 |
| `docs/08-handoff-2026-08-10.md` | 历史快照（Stage1/Stage3 修复与复核） |
| `docs/09-handoff-2026-08-16.md` | **当前可交接基线**、已复跑判据和下一阻塞项 |
| `docs/reference/` | 历史审计结果（数据集校验和、文件索引、缺口清单、提交归档），只读参考 |

改架构、协议或数据格式时**必须同步更新对应文档**；修好缺陷时在 `03-status.md` 里划掉并记录判据。

## 事实边界

- **当前代码不能产生正确的端到端结果。** 界面成功、图片生成、EXE 正常退出都不能证明流水线正确。
  唯一判据是：板端实际回传的数据经 LDPC 后与 R0.83 参考逐位/逐哈希相同。
- **算法本身已被证明正确**：`python3 tools/golden_model.py verify-code` 会用黄金数据证明
  「编码序列 ⊕ 水印 → 5b4b → codeword_R083.txt」逐位成立。要做的是让 RTL 对齐这个模型。
- **历史演示存在「用正确结果直接生成图片」的通道。**
  `data/R0.83_data/` 与 `archive/submission_2025-11-07/演示文件/` 里的
  `result.txt`/`dec_input.txt`/`decoded_bits.txt`/`decoded_image.jpg`/`codeword_R083.txt`/
  `source_bit.txt`/`Milk coronet.jpg` **只能被测试代码读取做显式比较**，
  绝不可进入生产路径。`clients/python/gui_app.spec` 已移除 `dec_input.txt`；后续修改打包规则时
  必须保持这一点。
- 两份 XSA 字节相同（SHA-256 `79c64736...e6eb33`），是历史硬件快照，
  **不是**当前 Tcl 已被证明可再生的产物。
- `archive/submission_2025-11-07/..._重要代码.rar` 尚未解压（环境缺 RAR5 工具）；
  解压后必须先做来源/哈希差异审计再决定是否导入。

## 开发前检查表

1. 确认数据版本、文件 SHA-256、输入格式和参数；不同版本绝不共用未说明的常量。
2. 改数据格式前先读 `docs/02-data-contract.md`；三方（Python / PS / RTL）成对修改。
3. 涉及硬件：先核对 PS7/DDR/MIO/PHY、XDC、时钟、IP Catalog、地址图和 XSA 同源性。
4. 涉及 DMA/DDR：重算所有 buffer 区间、cache flush/invalidate、对齐和上限。
5. 涉及 LDPC/图片：禁止绕过 FPGA 结果；提交输入、每级中间输出、最终 bitstream、图片哈希和自动比对。
6. 改 Tcl 前先修它以 `pwd` 推导路径、不注册本地 IP 仓库的问题。

## 常见陷阱

- 不要把 `MAX_WATERMARK_SIZE`、`TOTAL_READS`、`NUM_LC`、`REF_LEN` 当成唯一常量；
  它们之间存在约束 `NUM_LC*STRIDE = L - READ_BPS`、`REF_LEN = STRIDE + READ_BPS`。
- 不要把 `tb_dna_quick.v` 编译通过当成功能正确：它的 AXI-Lite `AWVALID`/`WVALID` 恒为 0，
  控制寄存器从未被真正写入。
- 不要把空的 `hw/constr/top.xdc`、`apply_bd_automation` 的默认 PS7 配置或历史 XSA
  当作新板的约束/配置来源。
- 不要把 `five_to_four_decoder.v` 接回生产数据通路：它是未被顶层引用的死文件；查找表已按契约
  校正，但权威实现与 RTL 判据仍是 `desparsification_decoder_v1_0.v` / `desparsify_datapath.v`。
- SE150（51,781 × 150 bp）与 SE250（64,800 × 250 bp）不可混用；
  现有比特流只支持 150 bp。
