# report/evidence/

逐轮/逐例摘要表，由本机运行日志生成。生成时删除了 `run_dir` 等宿主机路径列，
其余字段原样保留；原始日志不随包提交。

| 文件 | 内容 | 来源 |
| --- | --- | --- |
| `board-runs.tsv` | 板测轮次索引（日期、run、制品、驱动、判据、结果） | 各轮 `summary.txt` 汇总 |
| `soak-8h.tsv` | v1.1 8 h 长稳逐轮（1736 行） | `soak.tsv`，删除 `run_dir` 列 |
| `multimedia-42.tsv` | 42 例逐例判据（arch / system / class / syndrome） | `SUMMARY-classified.tsv` |
| `soak-2h.tsv` | 2026.1 制品 2 h 长稳逐轮 | `soak.tsv`，删除 `run_dir` 列 |

列口径：

- `wall_s`：该轮开始时的累计墙钟秒数；
- `result_s`：客户端打印的结果耗时，**不得反推周期或功耗**；
- `judge_sha`：系统判据使用的载荷 SHA-256；
- `match`：`YES` 表示与期望 SHA 一致；
- `process_rc`：该轮 `run_g3.sh` 的退出码，`0` 为通过。
