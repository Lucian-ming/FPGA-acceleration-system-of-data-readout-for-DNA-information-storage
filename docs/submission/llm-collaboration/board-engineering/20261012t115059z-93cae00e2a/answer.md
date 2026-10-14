> 脱敏副本，原件 `20261012T115059Z-93cae00e2a/{prompt.txt,answer.md}`。本机绝对路径、邮箱、凭据形模式及非白名单私网 IP 已替换；除脱敏与换行规范化外保留原文。

阶段二实施已完成，详细改动、判据边界和未完成项见[实施报告](<<仓库根目录>/logs/agents/verify-system-20261012/implementation-report.md>)。

主要改动：`xc7z020` 验收要求显式制品目录和板端 IP；`run_g3.sh` 增加 WSL 本地 XSDB、hw_server URL 和 `<本机路径>` 采集路径。验收时串口打不开或没有输出会失败，输入摘要记录 FASTQ 与水印 SHA。CAPS 全字段校验已覆盖网络探针；流水线计数器改从本轮 ELF 解析符号地址。F3 脚本会将 PS7 初始化或寄存器读取失败判为失败，并明确限制 DDR 结论。

最终回归结果：

- `python3 -m unittest discover -s tests/host -p 'test_g3_*.py' -v`：退出码 0，53 项通过。
- `bash tests/host/run_host_tests.sh --worktree`：退出码 0。
- `bash tools/check_ip_packaging.sh`：退出码 0。
- `bash tools/check_repo_hygiene.sh`：退出码 0。

新板缺少 `--artifact-dir` 的负例，在临时移除严格门禁并恢复旧 fallback 后按预期变红。F3 脚本语法检查通过；本轮没有触板，未验证真实 XSDB 下载、UART 映射、DDR、CAPS 或 G3。板端 IP 和 `<本机路径>` 中的 PS UART 映射仍需 main 确认；`g3_netfault_probe.py` 的任务是否真正进入传输阶段也尚未纳入 PASS 裁决。

本轮未执行 Git 写操作；看板已登记完成。
