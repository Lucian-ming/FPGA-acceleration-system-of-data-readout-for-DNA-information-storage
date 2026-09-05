# 本机生成日志归档

`tools/run_vivado_build.sh` 会把 Vivado 的 `.log`/`.jou` 写入
`logs/vivado/<UTC 时间戳>-<PID>/`，避免生成文件散落在仓库根目录。

这些日志属于本机运行产物，按 `.gitignore` 忽略；可提交的构建结论、哈希和
验收证据应写入 `docs/` 或 `hw/build/export/SHA256SUMS`，不要把整份工具日志当作
发布制品。
