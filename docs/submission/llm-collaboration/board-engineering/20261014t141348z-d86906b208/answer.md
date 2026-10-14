> 脱敏副本，原件 `20261014T141348Z-d86906b208/{prompt.txt,answer.md}`。本机绝对路径、邮箱、凭据形模式及非白名单私网 IP 已替换；除脱敏与换行规范化外保留原文。

已按要求停止板端操作。WSL 中未发现 `<本机路径>`；指定恢复命令返回以下原文，退出码为 1：

```text
<3>WSL (341 - ) ERROR: UtilBindVsockAnyPort:307: socket failed 1
```

报告已写入 [board-verify-stage1.md](<仓库根目录>/logs/verify/board-verify-stage1.md)。看板任务已标记为阻塞。

新包和参考包的 `run_g3.sh` 均未启动，因此没有 G3 判据、留证目录或 A/B 计时数据；`hw_server` 和板子空闲状态也未确认。硬件包未修改。需要 main 恢复串口后接手验收。
