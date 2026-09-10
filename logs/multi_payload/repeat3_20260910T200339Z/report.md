# 多 Payload 独立泛化回归测试报告

> 运行标识 (run-id): `run_20260910_200339`
> 生成时间: 2026-09-10 20:06:40 CST
> 判定标准: LDPC 5/6 收敛且 SHA-256 与独立源文件逐位 100% 匹配
> 数据集范围: **扩展集 (--extended)** —— 经典 5 大基准 + 自适应门限 D1_random_entropy@65 + D2_controlled_noise@65
> 说明: 高熵随机样本保留出厂门限 60（留证历史未关闭项）；其余基准为 67；自适应门限 65 与受控噪声样本 D2 门限为 65

## 1. 测试结果汇总

| 数据集 ID | 数据类型 | 比对门限 | 规模 | 误码 (bit) | 初始校验子 | LDPC 轮数 | 耗时说明 | 最终哈希匹配 | 结论 |
|---|---|---:|---:|---:|---:|---:|:---:|:---:|:---:|
| `D0_image_mandrill #1` | image/jpeg | 67 | 4096 条 | 42 | 183 | 47 | 板测 8.70s | 100% 吻合 | ✅ PASS |
| `D0_image_mandrill #2` | image/jpeg | 67 | 4096 条 | 42 | 183 | 47 | 板测 7.19s | 100% 吻合 | ✅ PASS |
| `D0_image_mandrill #3` | image/jpeg | 67 | 4096 条 | 42 | 183 | 47 | 板测 6.72s | 100% 吻合 | ✅ PASS |
| `D1_text_manifesto #1` | text/ascii | 67 | 4096 条 | 16 | 56 | 4 | 板测 6.18s | 100% 吻合 | ✅ PASS |
| `D1_text_manifesto #2` | text/ascii | 67 | 4096 条 | 16 | 56 | 4 | 板测 6.14s | 100% 吻合 | ✅ PASS |
| `D1_text_manifesto #3` | text/ascii | 67 | 4096 条 | 16 | 56 | 4 | 板测 6.36s | 100% 吻合 | ✅ PASS |
| `D1_binary_pattern #1` | binary/geometric | 67 | 4096 条 | 7 | 20 | 1 | 板测 6.87s | 100% 吻合 | ✅ PASS |
| `D1_binary_pattern #2` | binary/geometric | 67 | 4096 条 | 7 | 20 | 1 | 板测 8.14s | 100% 吻合 | ✅ PASS |
| `D1_binary_pattern #3` | binary/geometric | 67 | 4096 条 | 7 | 20 | 1 | 板测 7.72s | 100% 吻合 | ✅ PASS |
| `D1_structured_sparse #1` | binary/sparse | 67 | 4096 条 | 18 | 83 | 1 | 板测 6.86s | 100% 吻合 | ✅ PASS |
| `D1_structured_sparse #2` | binary/sparse | 67 | 4096 条 | 18 | 83 | 1 | 板测 6.27s | 100% 吻合 | ✅ PASS |
| `D1_structured_sparse #3` | binary/sparse | 67 | 4096 条 | 18 | 83 | 1 | 板测 6.08s | 100% 吻合 | ✅ PASS |
| `D1_random_entropy @ 60 #1` | random/high_entropy | 60 | 4096 条 | 2671 | 4518 | 50 | 板测 6.32s | 不匹配 | ❌ FAIL |
| `D1_random_entropy @ 60 #2` | random/high_entropy | 60 | 4096 条 | 2671 | 4518 | 50 | 板测 6.82s | 不匹配 | ❌ FAIL |
| `D1_random_entropy @ 60 #3` | random/high_entropy | 60 | 4096 条 | 2671 | 4518 | 50 | 板测 7.63s | 不匹配 | ❌ FAIL |
| `D1_random_entropy @ 65 #1` | random/high_entropy | 65 | 4096 条 | 236 | 765 | 34 | 板测 7.99s | 100% 吻合 | ✅ PASS |
| `D1_random_entropy @ 65 #2` | random/high_entropy | 65 | 4096 条 | 236 | 765 | 34 | 板测 7.20s | 100% 吻合 | ✅ PASS |
| `D1_random_entropy @ 65 #3` | random/high_entropy | 65 | 4096 条 | 236 | 765 | 34 | 板测 6.85s | 100% 吻合 | ✅ PASS |
| `D2_controlled_noise @ 65 #1` | text/controlled_noise | 65 | 4096 条 | 20 | 66 | 2 | 板测 6.19s | 100% 吻合 | ✅ PASS |
| `D2_controlled_noise @ 65 #2` | text/controlled_noise | 65 | 4096 条 | 20 | 66 | 2 | 板测 6.04s | 100% 吻合 | ✅ PASS |
| `D2_controlled_noise @ 65 #3` | text/controlled_noise | 65 | 4096 条 | 20 | 66 | 2 | 板测 6.37s | 100% 吻合 | ✅ PASS |

### 1.1 按数据集汇总（重复实验）

| 数据集 ID | 通过 / 总次数 | 通过率 | 结论 |
|---|:---:|:---:|:---:|
| `D0_image_mandrill` | 3 / 3 | 100.0% | ✅ 全部通过 |
| `D1_text_manifesto` | 3 / 3 | 100.0% | ✅ 全部通过 |
| `D1_binary_pattern` | 3 / 3 | 100.0% | ✅ 全部通过 |
| `D1_structured_sparse` | 3 / 3 | 100.0% | ✅ 全部通过 |
| `D1_random_entropy @ 60` | 0 / 3 | 0.0% | ❌ 全部失败 |
| `D1_random_entropy @ 65` | 3 / 3 | 100.0% | ✅ 全部通过 |
| `D2_controlled_noise @ 65` | 3 / 3 | 100.0% | ✅ 全部通过 |

> 「⚠️ 不稳定」意味着同一输入在同一制品上结果不可重复，属最高优先级缺陷，不得按「多数通过」计为通过。

**总计通过率**: 18 / 21 (85.7%)

## 2. 独立 Payload 详细哈希对照表

| 数据集 ID | 期望 Payload SHA-256 | 还原结果 SHA-256 | 说明 |
|---|---|---|---|
| `D0_image_mandrill #1` | `fcd0cf90bd680e7bbdc203e3398119504da0897acac9e2117008b4efb6b1f2c3` | `fcd0cf90bd680e7bbdc203e3398119504da0897acac9e2117008b4efb6b1f2c3` | Live board execution |
| `D0_image_mandrill #2` | `fcd0cf90bd680e7bbdc203e3398119504da0897acac9e2117008b4efb6b1f2c3` | `fcd0cf90bd680e7bbdc203e3398119504da0897acac9e2117008b4efb6b1f2c3` | Live board execution |
| `D0_image_mandrill #3` | `fcd0cf90bd680e7bbdc203e3398119504da0897acac9e2117008b4efb6b1f2c3` | `fcd0cf90bd680e7bbdc203e3398119504da0897acac9e2117008b4efb6b1f2c3` | Live board execution |
| `D1_text_manifesto #1` | `101d89599e84011f30816dea901c43d96bd2a1654a5252dbf47e9c0cc8601ccf` | `101d89599e84011f30816dea901c43d96bd2a1654a5252dbf47e9c0cc8601ccf` | Live board execution |
| `D1_text_manifesto #2` | `101d89599e84011f30816dea901c43d96bd2a1654a5252dbf47e9c0cc8601ccf` | `101d89599e84011f30816dea901c43d96bd2a1654a5252dbf47e9c0cc8601ccf` | Live board execution |
| `D1_text_manifesto #3` | `101d89599e84011f30816dea901c43d96bd2a1654a5252dbf47e9c0cc8601ccf` | `101d89599e84011f30816dea901c43d96bd2a1654a5252dbf47e9c0cc8601ccf` | Live board execution |
| `D1_binary_pattern #1` | `034adb3c5096819e35dde255bcad95377f31f3fdcc7e27083ffe1ef0cdbe0525` | `034adb3c5096819e35dde255bcad95377f31f3fdcc7e27083ffe1ef0cdbe0525` | Live board execution |
| `D1_binary_pattern #2` | `034adb3c5096819e35dde255bcad95377f31f3fdcc7e27083ffe1ef0cdbe0525` | `034adb3c5096819e35dde255bcad95377f31f3fdcc7e27083ffe1ef0cdbe0525` | Live board execution |
| `D1_binary_pattern #3` | `034adb3c5096819e35dde255bcad95377f31f3fdcc7e27083ffe1ef0cdbe0525` | `034adb3c5096819e35dde255bcad95377f31f3fdcc7e27083ffe1ef0cdbe0525` | Live board execution |
| `D1_structured_sparse #1` | `831b499c0bf4dfd1ca70e89edd3412669ade6e213fe60b2f55d034c2b246486c` | `831b499c0bf4dfd1ca70e89edd3412669ade6e213fe60b2f55d034c2b246486c` | Live board execution |
| `D1_structured_sparse #2` | `831b499c0bf4dfd1ca70e89edd3412669ade6e213fe60b2f55d034c2b246486c` | `831b499c0bf4dfd1ca70e89edd3412669ade6e213fe60b2f55d034c2b246486c` | Live board execution |
| `D1_structured_sparse #3` | `831b499c0bf4dfd1ca70e89edd3412669ade6e213fe60b2f55d034c2b246486c` | `831b499c0bf4dfd1ca70e89edd3412669ade6e213fe60b2f55d034c2b246486c` | Live board execution |
| `D1_random_entropy @ 60 #1` | `d7cbdc06d173b6ec01b7fce8646249589e5f1611ca4fe0fedd25187af0cc7b5f` | `LDPC_DECODE_FAILED` | Live board execution |
| `D1_random_entropy @ 60 #2` | `d7cbdc06d173b6ec01b7fce8646249589e5f1611ca4fe0fedd25187af0cc7b5f` | `LDPC_DECODE_FAILED` | Live board execution |
| `D1_random_entropy @ 60 #3` | `d7cbdc06d173b6ec01b7fce8646249589e5f1611ca4fe0fedd25187af0cc7b5f` | `LDPC_DECODE_FAILED` | Live board execution |
| `D1_random_entropy @ 65 #1` | `d7cbdc06d173b6ec01b7fce8646249589e5f1611ca4fe0fedd25187af0cc7b5f` | `d7cbdc06d173b6ec01b7fce8646249589e5f1611ca4fe0fedd25187af0cc7b5f` | Live board execution |
| `D1_random_entropy @ 65 #2` | `d7cbdc06d173b6ec01b7fce8646249589e5f1611ca4fe0fedd25187af0cc7b5f` | `d7cbdc06d173b6ec01b7fce8646249589e5f1611ca4fe0fedd25187af0cc7b5f` | Live board execution |
| `D1_random_entropy @ 65 #3` | `d7cbdc06d173b6ec01b7fce8646249589e5f1611ca4fe0fedd25187af0cc7b5f` | `d7cbdc06d173b6ec01b7fce8646249589e5f1611ca4fe0fedd25187af0cc7b5f` | Live board execution |
| `D2_controlled_noise @ 65 #1` | `101d89599e84011f30816dea901c43d96bd2a1654a5252dbf47e9c0cc8601ccf` | `101d89599e84011f30816dea901c43d96bd2a1654a5252dbf47e9c0cc8601ccf` | Live board execution |
| `D2_controlled_noise @ 65 #2` | `101d89599e84011f30816dea901c43d96bd2a1654a5252dbf47e9c0cc8601ccf` | `101d89599e84011f30816dea901c43d96bd2a1654a5252dbf47e9c0cc8601ccf` | Live board execution |
| `D2_controlled_noise @ 65 #3` | `101d89599e84011f30816dea901c43d96bd2a1654a5252dbf47e9c0cc8601ccf` | `101d89599e84011f30816dea901c43d96bd2a1654a5252dbf47e9c0cc8601ccf` | Live board execution |

## 3. 科学事实边界与已知未关闭项（Known Boundaries）

- **多 Payload 泛化验证**: D0 图像、D1 文本、D1 二值几何图案、D1 稀疏跳变在板端均 100% 恢复成功；
- **高熵样本双门限实测事实**: 
  * 在出厂默认门限 `score_min=60` 下，高熵样本原始误码 2600+ bit，LDPC 50 轮未收敛 (FAIL)，忠实记录并作为已知历史边界留证；
  * 启用自适应优化门限 `score_min=65` 后，板端实测原始误码骤降，LDPC 成功收敛且 SHA-256 100% 吻合；
- **D2 受控噪声实测事实**: 针对注入 1.39% 突变噪声的受控数据集 `D2_controlled_noise`，板端实测在门限 65 下仅 2 轮即收敛恢复；
- **严禁虚假全绿**: 任何阶段复核必须忠实重现出厂门限下的 2600+ bit 失败事实，同时展示自适应优化后的有效改善，绝不伪造或掩盖边界。
