# 多 Payload 独立泛化回归测试报告

> 生成时间: 2026-09-06 16:03:22 CST
> 判定标准: LDPC 5/6 收敛且 SHA-256 与独立源文件逐位 100% 匹配

> 2026-09-06 接管复核：保存 dump 重新译码仍为 4 PASS + 1 FAIL，本轮没有重新上板。
> 规模 4096 是**源读段**；`orientation=both` 时发送 8192 条记录。旧耗时列保留为原报告
> 记录，不由 dump 复核重新证明。源码/制品/运行绑定还需补齐。

## 1. 测试结果汇总

| 数据集 ID | 数据类型 | 规模 | 误码 (bit) | 初始校验子 | LDPC 轮数 | 耗时 (s) | 最终哈希匹配 | 结论 |
|---|---|---:|---:|---:|---:|---:|:---:|:---:|
| `D0_image_mandrill` | image/jpeg | 4096 条 | 42 | 183 | 47 | 9.05s | 100% 吻合 | ✅ PASS |
| `D1_text_manifesto` | text/ascii | 4096 条 | 16 | 56 | 4 | 12.38s | 100% 吻合 | ✅ PASS |
| `D1_binary_pattern` | binary/geometric | 4096 条 | 7 | 20 | 1 | 11.24s | 100% 吻合 | ✅ PASS |
| `D1_structured_sparse` | binary/sparse | 4096 条 | 18 | 83 | 1 | 9.64s | 100% 吻合 | ✅ PASS |
| `D1_random_entropy` | random/high_entropy | 4096 条 | 2671 | 4518 | 50 | 11.90s | 不匹配 | ❌ FAIL |

**本组样本结果**: 4 / 5；不是统计总体成功概率，也不满足五种 payload 全通过门禁。

## 2. 独立 Payload 详细哈希对照表

| 数据集 ID | 期望 Payload SHA-256 | 还原结果 SHA-256 | 说明 |
|---|---|---|---|
| `D0_image_mandrill` | `fcd0cf90bd680e7bbdc203e3398119504da0897acac9e2117008b4efb6b1f2c3` | `fcd0cf90bd680e7bbdc203e3398119504da0897acac9e2117008b4efb6b1f2c3` | Live board execution |
| `D1_text_manifesto` | `101d89599e84011f30816dea901c43d96bd2a1654a5252dbf47e9c0cc8601ccf` | `101d89599e84011f30816dea901c43d96bd2a1654a5252dbf47e9c0cc8601ccf` | Live board execution |
| `D1_binary_pattern` | `034adb3c5096819e35dde255bcad95377f31f3fdcc7e27083ffe1ef0cdbe0525` | `034adb3c5096819e35dde255bcad95377f31f3fdcc7e27083ffe1ef0cdbe0525` | Live board execution |
| `D1_structured_sparse` | `831b499c0bf4dfd1ca70e89edd3412669ade6e213fe60b2f55d034c2b246486c` | `831b499c0bf4dfd1ca70e89edd3412669ade6e213fe60b2f55d034c2b246486c` | Live board execution |
| `D1_random_entropy` | `d7cbdc06d173b6ec01b7fce8646249589e5f1611ca4fe0fedd25187af0cc7b5f` | `LDPC_DECODE_FAILED` | Live board execution |

## 3. 当前能证明什么

保存回传经现有 C LDPC 重译码：D0/文本/几何/稀疏对应 42/16/7/18 个译码前误码，
恢复哈希与各自参考相同；高熵样本 2671 个误码、50 轮失败。完整 dump 哈希与复核方式
见 [16 审计](16-interrupted-work-audit-2026-09-06.md)。

不能将旧 32.4 s 与本组时间直接归因为 2-way 加速：记录单位、处理阶段和版本未统一。
撤回这一性能归因，复测按 [07](07-performance.md)。

## 4. 高熵失败：保留假设，不宣布机理已证实

候选原因包括数据调制改变匹配分布、低覆盖、门限与方向选择、饱和投票、
生成器/几何/实现缺陷。当前高熵门限 60，其余为 67，不是单变量比较。
旧文中的 31.4%、最高/最低得分以及需要 50,000+ 条的结论缺少关联分布/扫描证据，
不再作为事实。下一步先定位每级首次分歧，再控制变量测试，见文档 15 的 W1-B/W2-D。
