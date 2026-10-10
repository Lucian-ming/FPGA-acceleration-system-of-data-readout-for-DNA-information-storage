# 16 · 中断任务清点与证据审计（2026-09-06）

## 清点结果

- 接管时 HEAD 为 `fffbd8d9e27aecfea546035cdc290e4cbfab7641`，`main` 与远端同步。
- `git status` 仅发现 `tools/run_robustness_scan.py` 三行未提交赋值：
  `info_bytes = np.packbits(info_bits[:54000]).tobytes()`、其 SHA 计算，以及
  `recovered = (raw_errs == 0 or rec_sha256 == GOLDEN_IMAGE_SHA256)`。
  随后原有 JPEG 还原与哈希判定立即覆盖这些结果，故目前只是无效重复赋值；
  若将来误用 OR 判据又会放宽恢复标准。仅删除这三行，文件恢复已提交内容，无行为改动。
  未发现其他未提交或未跟踪半成品。
- `git worktree list` 只有主 checkout；没有孤儿 worktree、分支或运行中的 Vivado/XSim/
  压测进程。Git 的特殊 `.git-data` 展示不代表额外 worktree，不做“修复”。
  看板中的 `host-opt`、`stage1-arch` 停在准备实现，本轮未找到对应的新改动，
  按用户确认的中断状态回收并在文档 15 重新派工，不能声称实现完成。
- `hw/build/export/SHA256SUMS` 五个制品均通过 `sha256sum -c`；这只证明文件完整，
  不证明其与当前 RTL 同源。

## 已复核的板测留证

使用 `run_check_saved_dumps` 逐一复核 `tests/datasets/*/board_output.bin`；
五份各 64,800 B，另检查了全文件字节合法性。没有重新接板，不能证明旧耗时或装载版本：

| 数据集 | dump SHA-256（原始文件） | LDPC/结果 |
|---|---|---|
| D0 image | `a737e816c6f7d2632946c9ce7e143a33f71dc9863cfe3abade9547964ac327a7` | 42 bit，47 轮，PASS |
| D1 text | `61b286084dcce63c5d97fec6ba46c77240ff573df82cbe086c87040f617d5c5a` | 16 bit，4 轮，PASS |
| D1 binary | `92e53c3320252d13d5dde3e66b0d26cfa27190afc835fb9909ea49a4489c910d` | 7 bit，1 轮，PASS |
| D1 sparse | `761c17106016ac8d3014f6193d512f7f2cee216ca8346f2ca7506e5411c0df9e` | 18 bit，1 轮，PASS |
| D1 random | `beb27aa682d99eff4b0c1eb44d8fb8d1e21e6e54730cf64af51bd8d0fa354b96` | 2671 bit，50 轮，FAIL |

随机高熵失败必须保留为当前边界；不能用其余四个 PASS 推导“多 payload 已完成”。

## 留用与纠偏清单

| 留存物 | 判断/处置 |
|---|---|
| `tools/generate_payload_dataset.py`、`tests/datasets/` | 有价值：独立 payload、manifest、失败回传全部保留，真实数据不动 |
| `tools/run_multi_payload_regression.py` | 有价值：可重译码；模式区分、严格输入检查和生成报告待 W1-B 修正 |
| `tools/run_robustness_scan.py`、`tools/align_fast.c` | 有价值的软件探索；方向/饱和语义不等价于板端，不能用于 G5 验收 |
| `tools/run_cpu_benchmark.py` | CPU 入口保留；FPGA 与功耗常量冒充实测的问题列入 W1-A |
| `hw/ip/Dna_accelerator_core_1_0/hdl/srpe_batch*` | 1/2/4/8-way 候选与 WIP 保留；有文件不等于已被 IP/生产顶层引用 |
| 资源/性能/鲁棒性报告 | 删除无证据结论，保留原表与明确边界；旧全文可从 Git 历史追溯 |
| `hw/build/export`、历史 XSA/日志 | 只核验、不删除；完整性和源码同源性分开 |

没有发现足以安全删除的大型残留目录；不为“看起来干净”删除构建证据。
本轮根目录 `.log/.jou/.str/.pb` 扫描无输出。Python 语法检查通过，
未重跑全部 robustness 扫描、XSim、Vivado 或真实板级验收。

## 复核入口（无板卡、不覆盖 Markdown）

```bash
PYTHONPATH=tools:clients/python python3 - <<'PY'
from pathlib import Path
from run_multi_payload_regression import MultiPayloadRegression
r = MultiPayloadRegression()
for c in r.get_dataset_configs():
    raw = (Path("tests/datasets") / c["id"] / "board_output.bin").read_bytes()
    assert len(raw) == 8100 or (
        len(raw) == 64800 and (set(raw) <= set(b"01") or set(raw) <= {0, 1})
    )
    result = r.run_check_saved_dumps(c)
    assert result is not None
    print(c["id"], result.passed, result.recovered_sha256)
PY
```

制品完整性：在 `hw/build/export/` 执行 `sha256sum -c SHA256SUMS`，五项 OK。
本轮只读子 Agent 因远程门禁 TLS 失败未开展审计；上述结果由已通过门禁的主会话复核，
不是独立双人审计。
