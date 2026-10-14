> 脱敏副本，原件 `20261014T114756Z-c57e5fd839/{prompt.txt,answer.md}`。本机绝对路径、邮箱、凭据形模式及非白名单私网 IP 已替换；除脱敏与换行规范化外保留原文。

P1 已完成，未执行任何 Git 写操作。

- 在 [test_client_core.py](<仓库根目录>/clients/python/tests/test_client_core.py) 增加读出逐字节比较和 LDPC 后端交叉测试。真实 FASTQ、plain、空/单条输入，150/250 bp、N、大小写及 `both`/`forward` 均通过；差异会报告首个线上字节偏移。测试发现 `first.iter_read_batches()` 当前委托给 `fast_readout`，所以比较使用 `first.iter_reads()` 的逐读路径，避免同函数自比。
- [test_client.sh](<仓库根目录><本机路径>) 的用例下限从 25 调到 31：原有 25 个基线用例，加 3 个读出用例和 3 个 LDPC 判据。
- `bash tools/test_client.sh`：**PASS，实际收集 31 个用例，下限 31，跳过 1 个**。native 与 c_accel 的 54,000 位载荷 SHA-256 均为 `0a2aa3b514b4b470c80a8affa64a5795dba34bbab134153c3d528c298c40e04f`。
- external 资源齐全，但 Windows PE EXE 在当前 Linux/WSL 环境无法启动，测试明确打印原因并 skip；因此**external 三方比对尚未完成**。
- 故障注入使读出用例按预期变红，报告首个差异偏移为 4。`bash tools/check_repo_hygiene.sh`：**PASS**。

完整记录见 [p1-report.md](<仓库根目录>/logs/client/p1-report.md)。
