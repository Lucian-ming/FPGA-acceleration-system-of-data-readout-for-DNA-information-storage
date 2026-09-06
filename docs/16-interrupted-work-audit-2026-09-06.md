# 16 · 中断任务清点与证据审计（2026-09-06）

## 清点结果

- `git status` 仅发现 `tools/run_robustness_scan.py` 三行未提交赋值；其逻辑会把
  “原始误码为 0”误当作恢复成功，已删除。未发现其他未提交或未跟踪半成品。
- `git worktree list` 只有主 checkout；没有孤儿 worktree、分支或运行中的 Vivado/XSim/
  压测进程。看板中的 `host-opt`、`stage1-arch` 属于中断状态，不能标记完成，已交由
  15 文档重新派工。
- `hw/build/export/SHA256SUMS` 五个制品均通过 `sha256sum -c`；这只证明文件完整，
  不证明其与当前 RTL 同源。

## 已复核的板测留证

使用 `run_check_saved_dumps` 逐一复核 `tests/datasets/*/board_output.bin`：

| 数据集 | dump SHA-256（原始文件） | LDPC/结果 |
|---|---|---|
| D0 image | `a737e816c6f7d2632946c9ce7e143a33f71dc9863cfe3abade9547964ac327a7` | 42 bit，47 轮，PASS |
| D1 text | `61b286084dcce63c5d97fec6ba46c77240ff573df82cbe086c87040f617d5c5a` | 16 bit，4 轮，PASS |
| D1 binary | `92e53c3320252d13d5dde3e66b0d26cfa27190afc835fb9909ea49a4489c910d` | 7 bit，1 轮，PASS |
| D1 sparse | `761c17106016ac8d3014f6193d512f7f2cee216ca8346f2ca7506e5411c0df9e` | 18 bit，1 轮，PASS |
| D1 random | `beb27aa682d99eff4b0c1eb44d8fb8d1e21e6e54730cf64af51bd8d0fa354b96` | 2671 bit，50 轮，FAIL |

随机高熵失败必须保留为当前边界；不能用其余四个 PASS 推导“多 payload 已完成”。
