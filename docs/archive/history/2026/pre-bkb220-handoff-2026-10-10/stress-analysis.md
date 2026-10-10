# 12 · 自动化压测与统计口径

## 当前资产

压测脚本：`tools/stress_test_suite.py`。已有报告：`tests/stress_results/stress_20260905T143122/summary.md`，共 737 轮；排除边界探索和故障注入后，SE150 有效任务 700/700、SE250 有效任务 13/13 通过。

这证明长稳性和最低可恢复规模的基础，不证明多 payload 泛化，也不单独定位性能瓶颈。

## 必须补齐的字段

```text
failure_class
dataset_id
payload_sha256
watermark_sha256
fastq_read_s
upload_s
dma_in_s
stage1_s
stage2_s
stage3_s
download_s
ldpc_s
```

## 失败分类

`pass`、`functional`、`communication`、`tooling`、`boundary_expected`、`fault_injection_expected`。边界探索和 `dirty_proof` 不能混入产品成功率；脚本字段错误属于 tooling，必须单独修复。

## 下一步

1. 修复统计接口；
2. 增加失败分类和阶段计时；
3. 跑 10～20 轮 smoke；
4. 生成 CPU/FPGA 公平基准；
5. 接入多 payload；
6. 接入错误/覆盖度矩阵；
7. 输出恢复成功率、耗时和错误边界曲线。

旧报告和完整分析保留在 `docs/archive/history/2026/stress-analysis-2026-09-05.md`。
