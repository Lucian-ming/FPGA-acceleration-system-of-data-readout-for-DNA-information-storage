> 脱敏副本，原件 `20261014T143640Z-2e05efa58d/{prompt.txt,answer.md}`。本机绝对路径、邮箱、凭据形模式及非白名单私网 IP 已替换；除脱敏与换行规范化外保留原文。

你是本项目的客户端修复子 Agent，工作目录 <仓库根目录>。
任务：**修掉界面现代化改造引入的 3 个行为回归**（独立验收员查出来的，有报告为证）。

【背景】
另一个 agent 把界面做了现代化（`clients/python/gui_app.py` + `clients/python/ui_theme.py`，**未提交**）。
**独立验收结论是"不予验收"**，因为出现了 3 个行为回归。**你的任务只是修这 3 个，不要顺手做别的。**

【必读】`logs/verify/ui-verify-behavior.md`（验收员的原始报告，**这是你的问题清单**）；
`docs/agent-prompts/ui-modernize.md`（任务书，看清楚"行为一行都不许改"这条）。

【要修的 3 条（逐条修，逐条给证据）】

**1. ⚠️ 最严重：未触发 POST 时仍把五阶段标完成 + 顶部显示「板端纠对通过」**
   —— 这是**假成功**。本项目唯一的验收判据是"板端是否纠对"，**界面绝不能在不该显示成功时显示成功**。
   要求：只有**真正走完校验且 syndrome 全零**时才允许出现"通过"字样与绿色完成态；
   跳过 POST、中断、失败等一切其它路径都不得显示"通过"。**这是本次修复的重中之重。**

**2. 结束回调不再停止 LDPC 的不确定进度条**
   —— 任务结束后进度条还在转。要求：所有终态（成功/失败/取消/异常）都必须停住它。

**3. 自绘按钮保留了鼠标回调，但键盘触发行为与 ttk 按钮不等价**
   —— 可访问性退化。要求：键盘（Tab 聚焦 + Space/Enter 触发）行为与原来的 ttk 按钮一致。

【修法约束】
- **只做外观层的修复**：这 3 条都是"外观改造顺带碰坏了行为"，把行为改回来即可；
  **不要顺手重构、不要改配色/布局（那部分验收是过的或待定的）**。
- 允许改 `clients/python/gui_app.py` 与 `clients/python/ui_theme.py`。
- **不许改** `first.py`、`ldpc_pipeline.py`、`native_ldpc.py`、`tests/`、`resources/`、
  `gui_app.spec`、`README.md`（都被别的 agent 碰过或已冻结）。
  若你判断某条**必须**改 `first.py` 才能修好——**不要改**，写进报告让 main 决定。

【验收判据 —— 逐条给实际输出的证据】
- 3 条各自的**修复前/修复后行为证据**。你**不能截图**（沙箱起不了 Xvfb，验收员已经踩过），
  所以要用**可复现的代码级证据**：例如用模块桩驱动到"未触发 POST"这一态，
  断言顶部状态文案**不含**"通过"字样；驱动到成功态，断言**含**。
- `python3 -m py_compile clients/python/gui_app.py clients/python/ui_theme.py` 通过。
- `bash tools/test_client.sh` **PASS**，报告实际用例数。
- `bash tools/check_repo_hygiene.sh` **PASS**。
- **自证有牙齿**：对你写的每一条断言，**故意把修复退回**（临时改回坏行为），确认断言**变红**，再恢复。
  不红就说明你的断言没意义。
- 最后 `git status --short -- clients/python/` 只应包含 `gui_app.py` 与 `ui_theme.py`。

【看板】tools/agent_view.sh，`--agent ui-fix`：开始前 update、完成时 done。不要手工编辑 view.md。

【产出】报告 `logs/verify/ui-fix-report.md`（含 3 条的前后证据与自证变红记录）。

【硬性禁止】
- **不做任何 Git 写操作**；不要跑 tools/verify_repo_binding.sh。
- ⛔ **不要用 `pkill`/`killall` 按名字杀进程**——main 今天因为这个误杀了自己的子 Agent
  （命令行里嵌着 prompt 文本，正则会误匹配）。要杀就用 `ps` 查 PID 再 `kill <pid>`。
- 不碰板卡、不碰 `hw/`、`tools/`。
- 不许把"我看了觉得对"当成证据。

【边界】你只交付"3 个回归已修且有可复现证据"。**不代表**整体界面验收通过——那要 main 复核。