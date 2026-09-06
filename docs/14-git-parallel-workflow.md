# 14 · 并行 Agent 与 Git 生命周期（当前有效）

当前遵守 `AGENTS.md`：只在同一棵 `main` checkout 工作，禁止新建 branch/worktree/嵌套仓库。
旧版 worktree 创建、强制删除流程全部作废，原因是共享索引、构建目录和板卡会互相污染。

## 并行协议

1. 主会话先运行 `bash tools/verify_repo_binding.sh --remote`，并登记 `agent_view.sh start`。
2. 子 Agent 只能修改互不重叠的文件；不得切分支、rebase、push、修改真实数据或共享构建输出。
3. 每个 Agent 必须用唯一看板名，结束返回路径、命令、结果和未决风险；中断只能标记“待重派”。
4. 主会话统一检查、`git commit -m "..." -- <paths>`、`git push origin main`，最后验证
   `main...origin/main = 0/0`。
5. 同时最多一个 Vivado/XSim 长任务和一个板卡占用者；输出写入带 run-id 的 `hw/build/xsim/`
   或 `logs/`，根目录不得留生成日志。

## 回收

中断修改先分类：已验证结论写入 `docs/`，脚本/manifest/失败样本保留，明显临时文件先归档
再删除。没有修改的任务直接 `agent_view.sh done` 并注明中断。只有用户明确批准新的隔离
策略后才评估分支/worktree；回收前必须确认无未提交改动且证据已归档，禁止 `-D`、`--force`
或 `rm -rf` 静默抹除证据。
