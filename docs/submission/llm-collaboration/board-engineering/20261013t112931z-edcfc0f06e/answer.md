> 脱敏副本，原件 `20261013T112931Z-edcfc0f06e/{prompt.txt,answer.md}`。本机绝对路径、邮箱、凭据形模式及非白名单私网 IP 已替换；除脱敏与换行规范化外保留原文。

仓库处于 `main...origin/main`，HEAD 正是 `9bd2b9d`；源码默认 `PIPE_IDLE_FETCH_N=16U`。冻结包记录显示上次 XSCT 建完 BSP 后，`app build` 遇到 socket denial 并改用 ARM GCC。接下来我会在新包独立 workspace 中正式跑 Tcl，保留完整日志；若同一编译环节失败，再按冻结包记录走直接 GCC，并核验 BSP 库是否因此确实重编。
