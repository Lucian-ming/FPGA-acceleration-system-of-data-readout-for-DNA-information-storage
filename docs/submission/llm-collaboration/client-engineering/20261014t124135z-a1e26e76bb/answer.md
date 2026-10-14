> 脱敏副本，原件 `20261014T124135Z-a1e26e76bb/{prompt.txt,answer.md}`。本机绝对路径、邮箱、凭据形模式及非白名单私网 IP 已替换；除脱敏与换行规范化外保留原文。

已完成 GUI 与 CLI 改造，报告在 [gui-fpga-only-report.md](<仓库根目录>/logs/client/gui-fpga-only-report.md)。

- 修改了 [gui_app.py](<仓库根目录>/clients/python/gui_app.py) 和 [first.py](<仓库根目录>/clients/python/first.py)：移除主机译码入口，接入板端结果校验、失败红色状态、载荷字节数与媒体类型展示，并修正阶段提示、等待进度和耗时估算。
- 指定成功留证通过：0/10,800 行非零，载荷 6,624 字节，SHA-256 与预期一致。
- 指定未收敛留证判为失败：332/10,800 行非零，未生成载荷；失败界面分支检查通过。
- `py_compile`、`tools/test_client.sh`（28 项）和 `tools/check_repo_hygiene.sh` 均通过。

真实 GUI 窗口未能启动：Tkinter 可导入，但显示服务器 `:0` 无法连接；因此未验证实际窗口交互或系统默认程序打开。未连接 FPGA 做新的板端测试。本任务未执行 Git 写操作。
