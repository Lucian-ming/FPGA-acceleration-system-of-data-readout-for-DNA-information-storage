# 14 · 并行 Agent 与 Git 生命周期（当前有效）

当前遵守 `AGENTS.md`：只在同一棵 `main` checkout 工作，禁止新建 branch/worktree/嵌套仓库。
旧版 worktree 流程暂不启用，因为它与现行 main-only 门禁冲突。
独立 worktree 本可隔离工作文件/索引，但不能自动隔离板卡、构建绝对路径和看板；
不能只改文档就宣称隔离机制可用。

## 并行协议

1. 主会话先运行 `bash tools/verify_repo_binding.sh --remote`，并登记 `agent_view.sh start`。
2. 子 Agent 只能修改互不重叠的文件；不得执行 Git 写操作（add/commit/pull/rebase/
   stash/reset/switch/clean/push），不得修改真实数据或共享构建输出。子任务的提交义务由
   main 收齐后统一履行；同文件任务必须串行。
3. 每个 Agent 必须用唯一看板名，结束返回路径、命令、结果和未决风险；中断只能标记“待重派”。
4. 主会话先暂停全部写入者，复核 diff/测试/索引，再按项目要求 `git pull --rebase`。
   如果存在不能安全处理的脏改动/暂存内容，停下协调，不以 autostash/reset 规避。
   显式 add 新文件，执行 `git commit -m "..." -- <paths>`，每次立即
   `git push origin main`，最后验证 `main...origin/main = 0/0`。
5. 本阶段保守限制同时最多一个 Vivado/XSim 长任务和一个板卡占用者；输出写入带 run-id 的 `hw/build/xsim/`
   或 `logs/`，根目录不得留生成日志。

## 回收

看板是状态工具，不是板卡或 Git 锁；主会话必须给每种独占资源明确持有人。
如果有不受本主会话监督的其他会话，先协调共同遵守单一 Git writer，不能假设本文自动强制互斥。

## 中断、孤儿项和收工门禁

中断修改先分类：已验证结论写入 `docs/`，脚本/manifest/失败样本保留，生成日志先归档，
没有保留价值的修改逐行删除并说明原因。无修改的任务 `done` 注明中断待重派，
不冒充实现完成。存在活跃进程时先核实归属，不能只凭看板过期就清理。

交接必须检查 `git status --short`、`git branch -a -vv`、`git worktree list --porcelain`、
根目录生成日志、看板和任务进程。main 外任何新增分支/worktree 都需报告负责人和处置，
不能无限期留下“以后再清理”。未提交工作必须转交具体负责人，否则不能宣布收口。

若未来用户批准 worktree，须先同步 `AGENTS.md`、仓库绑定脚本、构建输出和共享看板策略；
没有这一步不得创建。旧 worktree 回收必须逐项核验：
负责人确认、无活跃任务、无脏改动、成果已集成并推送、重要忽略文件已归档；
先 `git worktree remove <已核验路径>`，再 `git branch -d <已合并分支>`，
有远端分支时经核验后删除远端引用，再检查登记。任一步失败就记录阻塞，不强制清除。
`worktree prune` 不能替代文件/成果检查；禁止 `-D`、`--force` 或 `rm -rf` 静默抹证据。
