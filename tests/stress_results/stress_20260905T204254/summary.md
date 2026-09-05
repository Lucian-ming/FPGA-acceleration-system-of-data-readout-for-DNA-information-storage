# 标准化长稳与分段基准测试报告

- **更新时间**：2026-09-05 20:45:55
- **产品长稳通过率 (排除预期边界与弄脏)**：**8 / 8 (100.0%)**
- **总运行轮次 (含科学探索)**：14 轮 (PASS: 8)
- **SE150 最低可恢复源读段数 ($N_{min}$)**：**1312** 条
- **SE250 最低可恢复源读段数 ($N_{min}$)**：**探索中** 条
- **计划运行时间**：0.1 小时

## 最近 20 轮执行记录（含端到端分段耗时）

| 轮次 | 规格 | 标签 | 类别 | 读段数 | 板耗 | 上传 | LDPC | 总耗时 | 初始校验子 | 迭代 | 状态 | 图像 SHA-256 |
| :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| 1 | SE150 | explore | boundary_expected | 1024 | 6.95s | 0.19s | 151.7ms | 7.34s | 2906 | 50 | ❌ boundary_expected | - |
| 2 | SE150 | explore | boundary_expected | 1088 | 6.99s | 0.22s | 114.1ms | 8.23s | 2356 | 50 | ❌ boundary_expected | - |
| 3 | SE150 | explore | boundary_expected | 1152 | 7.18s | 0.22s | 122.2ms | 7.58s | 1887 | 50 | ❌ boundary_expected | - |
| 4 | SE150 | explore | boundary_expected | 1216 | 7.41s | 0.20s | 110.9ms | 7.78s | 1659 | 50 | ❌ boundary_expected | - |
| 5 | SE150 | explore | boundary_expected | 1280 | 7.40s | 0.22s | 142.2ms | 7.82s | 1203 | 50 | ❌ boundary_expected | - |
| 6 | SE150 | explore | pass | 1312 | 7.49s | 0.28s | 62.9ms | 8.74s | 1131 | 28 | ✅ PASS | `fcd0cf90...` |
| 7 | SE150 | n_min_stress | pass | 1312 | 7.67s | 0.24s | 76.6ms | 8.04s | 1131 | 28 | ✅ PASS | `fcd0cf90...` |
| 8 | SE150 | std_2k | pass | 2048 | 9.15s | 0.38s | 12.3ms | 9.61s | 332 | 5 | ✅ PASS | `fcd0cf90...` |
| 9 | SE150 | med_4k | pass | 4096 | 12.98s | 0.69s | 104.5ms | 14.69s | 183 | 47 | ✅ PASS | `fcd0cf90...` |
| 10 | SE150 | dirty_proof | fault_injection_expected | 2048 | 8.88s | 0.35s | 125.2ms | 9.41s | 5317 | 50 | ❌ fault_injection_expected | - |
| 11 | SE150 | clean_check | pass | 2048 | 9.00s | 0.34s | 15.0ms | 9.41s | 332 | 5 | ✅ PASS | `fcd0cf90...` |
| 12 | SE150 | large_8k | pass | 8192 | 20.90s | 1.34s | 113.5ms | 23.28s | 189 | 47 | ✅ PASS | `fcd0cf90...` |
| 13 | SE150 | xl_16k | pass | 16384 | 36.78s | 2.63s | 14.0ms | 40.33s | 50 | 4 | ✅ PASS | `fcd0cf90...` |
| 14 | SE150 | tight_thresh | pass | 4096 | 13.01s | 0.90s | 107.5ms | 14.92s | 760 | 46 | ✅ PASS | `fcd0cf90...` |
