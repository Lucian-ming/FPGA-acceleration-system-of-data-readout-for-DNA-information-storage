# 多 Payload 独立泛化回归测试报告

> 生成时间: 2026-09-06 14:00:18 CST
> 判定标准: LDPC 5/6 收敛且 SHA-256 与独立源文件逐位 100% 匹配

## 1. 测试结果汇总

| 数据集 ID | 数据类型 | 规模 | 误码 (bit) | 初始校验子 | LDPC 轮数 | 耗时 (s) | 最终哈希匹配 | 结论 |
|---|---|---:|---:|---:|---:|---:|:---:|:---:|
| `D1_text_manifesto` | text/ascii | 4096 条 | 16 | 56 | 4 | 0.02s | 100% 吻合 | ✅ PASS |
| `D1_binary_pattern` | binary/geometric | 4096 条 | 7 | 20 | 1 | 0.01s | 100% 吻合 | ✅ PASS |
| `D1_structured_sparse` | binary/sparse | 4096 条 | 18 | 83 | 1 | 0.01s | 100% 吻合 | ✅ PASS |

**总计通过率**: 3 / 3 (100.0%)

## 2. 独立 Payload 详细哈希对照表

| 数据集 ID | 期望 Payload SHA-256 | 还原结果 SHA-256 | 说明 |
|---|---|---|---|
| `D1_text_manifesto` | `101d89599e84011f30816dea901c43d96bd2a1654a5252dbf47e9c0cc8601ccf` | `101d89599e84011f30816dea901c43d96bd2a1654a5252dbf47e9c0cc8601ccf` | Physical board output verification |
| `D1_binary_pattern` | `034adb3c5096819e35dde255bcad95377f31f3fdcc7e27083ffe1ef0cdbe0525` | `034adb3c5096819e35dde255bcad95377f31f3fdcc7e27083ffe1ef0cdbe0525` | Physical board output verification |
| `D1_structured_sparse` | `831b499c0bf4dfd1ca70e89edd3412669ade6e213fe60b2f55d034c2b246486c` | `831b499c0bf4dfd1ca70e89edd3412669ade6e213fe60b2f55d034c2b246486c` | Physical board output verification |
