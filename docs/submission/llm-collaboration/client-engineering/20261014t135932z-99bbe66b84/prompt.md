> 脱敏副本，原件 `20261014T135932Z-99bbe66b84/{prompt.txt,answer.md}`。本机绝对路径、邮箱、凭据形模式及非白名单私网 IP 已替换；除脱敏与换行规范化外保留原文。

你是本项目的**独立验收子 Agent（客户端「行为是否被改坏」方向）**，工作目录 <仓库根目录>。

【背景】
另一个 agent（不是你，也不是 main）刚把上位机界面做了"现代化改造"，改了
`clients/python/gui_app.py`（+572/−169）并新增 `clients/python/ui_theme.py`（795 行）。
**它的任务约束是「只做外观、行为一行都不许改」**——你要独立验收这一条。
**不许采信任何 agent 的报告或截图；你的结论只能来自你自己读的代码与跑出来的输出。**

另一位验收员负责"视觉/可用性"那一半，**你不要重复做外观评价**，你只做**行为等价性**。

【必读】`docs/agent-prompts/ui-modernize.md`（那是给它的任务书，写明允许做什么、不许做什么）；
`AGENTS.md`（事实边界）。

【本轮要回答的问题】

**1. 行为有没有被改坏？（核心）**
- 用 `git diff clients/python/gui_app.py` 逐块读，判断每一处改动是**纯外观**，还是**碰到了逻辑**。
- 逻辑面至少要覆盖（逐项给结论 + 证据）：
  - `verify_board_result` 的调用与参数（含 `input_bytes` 从哪里来）；
  - `BoardCodeRejected` 的处理分支（**必须走失败**，不许退回任何主机侧译码、不许"尽力显示"）；
  - 五段步进 token 与 `first.py` 的 `set_stage` 是否仍然对齐（有没有把断言删掉）；
  - 参数预设的存读、`--dry-run` 路径、日志内容；
  - 文件选择/输出目录/停止按钮等交互回调有没有被改语义。
- **明确列出**：哪些改动是纯外观、哪些"外观改动顺带碰了逻辑"、哪些逻辑**看代码没被碰**。

**2. 独立跑起来验（环境已装 tkinter 8.6 + xvfb-run）**
- `python3 -m py_compile clients/python/gui_app.py`；
- `cd clients/python && timeout 12 xvfb-run -a --server-args="-screen 0 1400x950x24" python3 gui_app.py` ⇒ **不抛异常**；
- `bash tools/test_client.sh` ⇒ PASS，报告实际收集用例数；
- `bash tools/check_repo_hygiene.sh` ⇒ ？

**3. 【main 提出的两个疑点，要你裁定】**
main 看了交付的截图（`logs/ui-modernize/after_screenshot_success.png` 等），看到两处可疑，
**但截图是用桩数据截的，所以不能断定**。请**读真实代码**裁定"是真 bug 还是桩的假数据"：
- **(a)** 成功态截图里「**端到端总耗时(E2E): 95945.71 s**」（≈26.6 小时，荒谬）；失败态截图里同一字段却是 2.35 s。
  查 `gui_app.py` 里这个 E2E 计时是怎么算的、起点终点各是什么、**有没有真实的量纲/时基错误**。
- **(b)** 截图里写「**54 条校验行全零**」，而日志写「0 / 54 / 54」。真实的校验行总数是
  **10,800**（`load_pchk` 的行数）。查这个 54 从哪来、界面显示的是不是 `BoardVerifyResult.total_rows`。
  ⚠️ 这一条尤其重要：**如果把验收判据的强度显示错了（10800 说成 54），那是在弱化本项目的唯一判据**，
  属于必须修的问题；但如果只是桩数据，也要明确说"不是 bug"。
- 对 (a)(b) 各自给出：**是 bug / 不是 bug / 无法判定**，并给出支持判断的代码位置与推理。

【验收判据 —— 逐条给实际输出】
- 行为等价性：逐项结论 + `git diff` 的对应片段（贴关键行）。
- 三条命令的实际输出。
- (a)(b) 的裁定与依据。
- **明确写"你在本环境验不了什么"**（例如真实板端交互、Windows 下的字体/DPI）。

【看板】tools/agent_view.sh，`--agent ui-verify-behavior`：开始前 update、完成时 done。不要手工编辑 view.md。

【产出】报告 `logs/verify/ui-verify-behavior.md`。

【硬性禁止】
- **不做任何 Git 写操作**（不许 commit/checkout/stash/restore，也不许 `git checkout -- ` 改回文件）；
  不要跑 tools/verify_repo_binding.sh。**不要修改任何文件**——你只验收。
- 不碰板卡；不碰 `hw/`、`tools/`、`clients/python/tests/`、`clients/python/resources/`。
- 不碰另一位验收员的方向（视觉/可用性）。
- 不许把别人的报告或截图当证据。

【边界】你只回答"这次现代化有没有改坏行为"，以及那两个疑点的裁定。**不代表**外观好坏（另有专人）。