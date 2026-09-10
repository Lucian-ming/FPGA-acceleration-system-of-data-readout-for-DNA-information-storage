# tests/datasets/common/ —— 数据集共享文件

## watermark.txt

**所有 D1/D2 合成数据集共用同一份水印**，故收敛到此处一份，
不再在每个数据集目录下各存一份副本。

- SHA-256：`be9b7799dff00851263fcf53b2e3aafa4d28b27104f07c2c9adb96f9f156f7eb`
- 长度：81,000 bit（81,000 B 的 '0'/'1' ASCII）

### 为什么收敛

2026-09-10 卫生审计发现 6 个数据集目录各存一份 `watermark.txt`，
**内容逐字节完全相同**（`cmp` 逐一确认）。体积只是次要问题（81 KB × 6），
真正的风险是**分叉**：将来改水印要同步改 6 个文件，漏一个就是静默的数据不一致，
而各数据集的 `SHA256SUMS` 各自自洽，**发现不了这种不一致**。

### 它不是 `data/R0.83_data/` 里的那份

权威源是 `data/R0.83_data/Source data/Watermark sequences/r0.83_watermark.txt`
（SHA-256 `b7c842f3…`），本文件是 `tools/generate_payload_dataset.py`
把它规范化之后的形式，**两者哈希不同是预期的**，不要互相比对。

### 消费方

`tools/run_multi_payload_regression.py` 与 `tools/debug_high_entropy.py` 通过
`resolve_watermark(dataset_dir)` 解析：**数据集目录下若存在同名文件则优先用它**
（兼容历史数据集与外部投放），否则回落到本共享副本。
