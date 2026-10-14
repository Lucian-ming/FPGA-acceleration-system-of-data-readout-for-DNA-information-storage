> 脱敏副本，原件 `20261014T141026Z-cf7ff867aa/{prompt.txt,answer.md}`。本机绝对路径、邮箱、凭据形模式及非白名单私网 IP 已替换；除脱敏与换行规范化外保留原文。

板端验收因 WSL 串口不可用而停止。`pgrep -af "run_g3|g3_soak" | grep -v grep` 无输出；设备检查原始报错为：

```text
ls: cannot access '<本机路径>': No such file or directory
```

按要求没有启动 `run_g3.sh`，也没有切换到 Windows。新包 G3 轮和参考包同小时 A/B 均未执行，因此没有判据 SHA、日志、留证目录或性能测量值可报告。

检查结果和未完成项已写入 [board-verify-stage1.md](<仓库根目录>/logs/verify/board-verify-stage1.md)。
