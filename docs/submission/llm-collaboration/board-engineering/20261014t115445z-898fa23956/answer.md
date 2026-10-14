> 脱敏副本，原件 `20261014T115445Z-898fa23956/{prompt.txt,answer.md}`。本机绝对路径、邮箱、凭据形模式及非白名单私网 IP 已替换；除脱敏与换行规范化外保留原文。

已完成分析和可烧录变体，报告在 [report.md](<仓库根目录>/logs/ldpc-poll/report.md)。

结论是 **证据不足**：默认档回调差 155 次，乘以 200 µs 为 31 ms；全量档差 123 次，为 24.6 ms，均不足以解释约 70 ms。并且 LDPC 状态读取可在一次回调内推进最多 64 步，主循环之后才休眠；这段休眠与 PL 译码等待重叠，不能再叠加到译码耗时上。报告也保留了全量档板端差 +118 ms、主机 `t_result` 差约 +170 ms 的口径差异。

变体包：[manifest.json](<仓库根目录>/hw/build/bkb220-p16-k2-ldpc-poll0-20261014T115821Z-board-migrate/manifest.json)。`PIPE_RUN_SLEEP_US=0`；bit SHA 与参考包相同（`8f0da7bf…14d5001c`），ELF SHA 不同（参考 `6ec76fc5…e4f0cd4f`，变体 `72f519fd…44c159f8`）。2,966 项 SHA256SUMS 校验及 `xc7z020` 制品门禁均通过。

main 可用下面的命令烧录并跑全量测试：

```bash
bash tools/run_g3.sh --artifact-dir hw/build/bkb220-p16-k2-ldpc-poll0-20261014T115821Z-board-migrate --xsdb <本机路径> --device xc7z020 --strict-artifacts --uart-port COM10 --ip 192.168.1.10 --port 7 --win-root <本机路径> --score-min 67 --full --skip-dump
```

本任务未上板。A/B 实测仍待 main 执行；另外，构建脚本最终返回码为 1，但包已生成并独立校验通过，原因是脚本末尾未启用 `--lwip-opt` 时的可选打印条件成为最终 shell 状态。
