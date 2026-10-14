> 脱敏副本，原件 `20261014T135932Z-99bbe66b84/{prompt.txt,answer.md}`。本机绝对路径、邮箱、凭据形模式及非白名单私网 IP 已替换；除脱敏与换行规范化外保留原文。

验收报告已写入 [ui-verify-behavior.md](<仓库根目录>/logs/verify/ui-verify-behavior.md)。

核心 syndrome 校验与 `BoardCodeRejected` 失败路径仍然严格执行，没有 PC 侧译码兜底。但改造存在状态表达回归：未触发 POST 时仍会把五阶段标完成、顶部显示“板端纠对通过”；结束回调也不再停止 LDPC 不确定进度条。自绘按钮保留了鼠标回调，但键盘触发行为与 ttk 按钮不等价。

- **(a) E2E：不是正常运行路径的计时 bug。** 起点和终点都用 `time.perf_counter()`，单位是秒；若桩直接调用完成回调、没先设置起点，才会显示接近单调时钟读数的大值。
- **(b) 54 行：不是生产 GUI 的计数 bug。** 界面直接显示结果对象的 `total_rows`，生产校验器以 `len(rows)` 填入；按任务提供的真实矩阵行数应显示 10,800。

检查结果：`py_compile` 通过；`test_client.sh` 通过，实际收集并运行 **28 个用例**；`check_repo_hygiene.sh` 通过。指定的 GUI 启动命令因沙箱内 Xvfb 无法监听 `<本机路径>` 而退出，未能验证界面进入主循环。真实板端交互和 Windows 字体/DPI 效果也未验。
