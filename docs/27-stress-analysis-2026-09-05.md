# 27 · 自动化压测分析与后续改造要求（2026-09-05）

## 1. 结论

现有压测套件 `tools/stress_test_suite.py` 和留证目录
`tests/stress_results/` **有较高价值**，但证据类型必须分开：

- 它已经能够证明多尺度、跨规格、连续任务的板端稳定性；
- 它已经能够探索最低可恢复读段数，适合作为方向 B 的基础；
- 它目前不能单独证明 Stage1、DMA、DDR、网络或 LDPC 谁是耗时瓶颈；
- 它目前不能证明换 payload 后的通用性；
- 探索失败、故障注入失败、通信/脚本失败不能与功能失败混成一个通过率。

## 2. 当前压测证据

主报告：`tests/stress_results/stress_20260905T143122/summary.md`

| 指标 | 结果 |
|---|---:|
| 总轮次 | 737 |
| 总成功 | 720 |
| 表面通过率 | 97.7% |
| SE150 | 716 轮 / 704 成功 |
| SE250 | 21 轮 / 16 成功 |
| SE150 最低可恢复读段数 | 约 1312 |
| SE250 最低可恢复读段数 | 约 1216 |

失败主要集中在边界探索：

- SE250：768、896、1024、1152、1184 条未收敛；
- SE150：384～1280 条的若干探索点未收敛；
- `dirty_proof` 失败属于故意降低阈值后的弄脏轮，不应计作产品功能失败。

排除 `explore`、`binary` 和 `dirty_proof` 后，当前报告中的有效长稳任务为：

| 模式 | 有效轮次 | 通过 |
|---|---:|---:|
| SE150 | 700 | 700 |
| SE250 | 13 | 13 |

正确表述应为：

> 压测套件完成 737 轮，其中包含预期边界失败和故障注入；在排除这两类实验后，SE150 有效长稳任务 700/700 通过，SE250 有效长稳任务 13/13 通过。

禁止直接把 97.7% 写成“系统成功率”，因为分母混合了不同实验目的。

## 3. 压测失败分类门禁

`TestRecord` 和 `summary.md` 必须显式增加 `failure_class`：

```text
pass
functional
communication
tooling
boundary_expected
fault_injection_expected
```

分类规则：

| 类别 | 例子 | 是否计入产品失败 |
|---|---|---|
| `pass` | LDPC 收敛且图片哈希一致 | 否 |
| `functional` | 板端错误、原始 bit 错误异常、哈希不匹配 | 是 |
| `communication` | TCP 断连、结果超时、板端未响应 | 是 |
| `tooling` | 字段不存在、日志解析异常、结果文件未生成 | 否，但必须修复 |
| `boundary_expected` | 低覆盖度导致 LDPC 不收敛 | 否，作为边界数据 |
| `fault_injection_expected` | `dirty_proof` 弄脏轮不收敛 | 否，必须记录鉴别力 |

早期留证 `stress_20260905T142952` 出现：

```text
'NetStats' object has no attribute 'phase_seconds'
```

这属于 `tooling`，不是 FPGA 功能失败。修复统计接口后，必须重新跑一个短 smoke，确认结果 JSON 不再出现该异常。

## 4. 对方向 A/B 的改造要求

### 4.1 方向 A：多 payload

当前 SE150/SE250 压测仍主要使用同一个 R0.83 payload，因此不能证明内容泛化。压测套件应增加：

```text
dataset_id
payload_sha256
watermark_sha256
read_bps
read_count
score_min
```

第一批至少使用 4 个新生成 payload，所有 payload 从编码端重新生成，不能复制历史最终结果。每个 payload 至少跑：

- 2048、4096、16384、full 四档；
- SE150 或 SE250 对应 profile；
- 一次冷启动；
- 一次连续两轮；
- 最终图片哈希与四级中间结果检查。

### 4.2 方向 B：错误/覆盖度矩阵

新增 mutation manifest，保持原始 `data/R0.83_data/` 不变。每个实验保存：

```text
input_sha256
output_sha256
seed
sub_rate
ins_rate
del_rate
coverage
score_min
raw_bit_errors
initial_syndromes
ldpc_iters
image_sha256
failure_class
```

第一批矩阵：

- substitution：0%、0.5%、1%、2%；
- insertion/deletion：0%、0.1%、0.5%；
- coverage：0.5×、1×、2×；
- 每个点 3 个随机种子。

最终输出两类曲线：

```text
覆盖度 -> 恢复成功率
错误率 -> 恢复成功率
```

## 5. 对时间优化的改造要求

当前压测只记录总耗时和 `board_result_time`，不足以定位瓶颈。下一版 `TestRecord` 必须增加：

```text
fastq_read_s
upload_s
dma_in_s
stage1_s
stage2_s
stage3_s
download_s
ldpc_s
```

每轮输出分段 JSON，并按记录数拟合：

```text
总耗时 = 固定开销 + 记录数 × 斜率
Stage1耗时 = 固定开销 + 记录数 × 斜率
```

在此之前，不得用压测总耗时判断 RTL 优化收益。

## 6. 近期执行顺序

1. 修复 `NetStats.phase_seconds` 类统计接口不一致问题；
2. 增加 `failure_class`；
3. 增加阶段级计时字段；
4. 运行 10～20 轮 smoke，确认 JSON/Markdown 统计正确；
5. 执行 docs/26 的 T0 公平基准；
6. 再进入 Stage1 4 倍展开；
7. 最后把多 payload 和 mutation 矩阵接入长稳压测。

## 7. 证据边界

本报告中的 737 轮来自已有留证，不代表新代码已经重新执行。任何修改 `stress_test_suite.py`、上位机协议或 RTL 后，必须生成新的带时间戳运行目录，不能沿用旧目录宣称新版本通过。
