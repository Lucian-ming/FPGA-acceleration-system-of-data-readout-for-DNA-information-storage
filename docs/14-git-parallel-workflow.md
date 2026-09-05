# 14 · 并行 Agent 的 Git 分支与 worktree 规范

> 本规范解决一个具体问题：并行开发结束后，不能留下无人负责的分支、worktree、构建目录或未推送提交。

## 1. 总原则

1. `main` 是唯一交付分支，任何时候必须可构建、可追溯；
2. 并行源码任务使用 **独立 branch + 独立 worktree**；
3. 只创建 branch、不创建 worktree，不能算隔离；
4. 没有明确并行任务时禁止创建 worktree；
5. agent 结束前必须完成提交、推送、合并或明确交接；
6. 合并完成后立即回收 branch 和 worktree，不允许“以后再清理”；
7. 未合并的 worktree 不得强制删除，必须先由负责人决定保留、转交或废弃。

## 2. 命名与目录

### 2.1 分支名

```text
agent/<短任务名>
```

示例：

```text
agent/stage1-4way
agent/stress-metrics
agent/payload-generalization
agent/host-optimization
```

禁止使用 `tmp/*`、`test/*`、无负责人姓名的随机分支。

### 2.2 worktree 目录

统一放在主 checkout 同级目录：

```text
/home/lucian/projects/FPGA-worktrees/<短任务名>/
```

禁止在项目仓库内部创建嵌套 clone 或 `.git`。每个 worktree 只能对应一个 active agent 和一个 branch。

## 3. 创建流程

创建前必须确认：

```bash
bash tools/verify_repo_binding.sh --remote
git status --short
git worktree list
```

创建：

```bash
name=stage1-4way
branch=agent/$name
path=/home/lucian/projects/FPGA-worktrees/$name

git fetch origin
git switch main
git pull --rebase origin main
git switch -c "$branch"
git push -u origin "$branch"
git worktree add "$path" "$branch"
```

实际协作时推荐由主 checkout 创建：

```bash
git worktree add -b agent/stage1-4way \
  /home/lucian/projects/FPGA-worktrees/stage1-4way origin/main
```

创建后必须登记：

```text
任务名
agent 名
branch
worktree 绝对路径
创建时间
负责人
预计结束时间
状态：active
```

登记可写入本机忽略文件 `.agent_worktrees/registry.tsv`，但最终交接必须用命令输出复核，不能只相信登记文件。

## 4. agent 工作规则

每个 agent 必须：

1. 在自己的 worktree 中工作；
2. 开工时更新 `tools/agent_view.sh start`；
3. 禁止切换到其他 agent 的 branch；
4. 禁止在自己的 branch 上运行会改写其他 worktree 的清理命令；
5. 提交时显式指定路径；
6. 提交前检查 `git diff --cached` 和 `git status`；
7. 只推送自己的 branch；
8. 完工时给出提交 SHA、测试命令和未解决问题；
9. 不得把构建缓存、临时日志和大文件塞进提交。

推荐提交：

```bash
git add <明确路径>
git commit -m "..." -- <明确路径>
git push origin agent/<短任务名>
```

## 5. 集成流程

集成者只能在主 checkout 或专用 `integration` worktree 操作：

```bash
git switch main
git pull --rebase origin main
git fetch origin agent/<短任务名>
git log --oneline main..origin/agent/<短任务名>
git diff --stat main...origin/agent/<短任务名>
git merge --no-ff origin/agent/<短任务名>
```

合并前必须确认：

- branch 只包含该任务；
- 没有混入其他 agent 文件；
- 无未提交工作树修改；
- 测试、构建和文档判据明确；
- 合并冲突已人工审查。

合并后必须执行项目相关回归，再推送：

```bash
git push origin main
bash tools/verify_repo_binding.sh --require-synced
```

## 6. 强制回收流程

合并成功后，**同一个交接回合内必须回收**：

```bash
branch=agent/stage1-4way
path=/home/lucian/projects/FPGA-worktrees/stage1-4way

# 1. 确认已合并
 git branch --merged main | grep -Fx "$branch"

# 2. 确认远端 main 已同步
git fetch --prune origin
git diff --exit-code main origin/main

# 3. 确认 worktree 无未提交修改
git -C "$path" status --short

# 4. 删除远端分支
git push origin --delete "$branch"

# 5. 删除本地分支
git branch -d "$branch"

# 6. 删除 worktree
git worktree remove "$path"

# 7. 清理失效登记
git worktree prune
```

任何一步失败都必须停止回收并记录原因，禁止使用 `-D`、`--force` 或 `rm -rf` 静默抹掉证据。

## 7. 未完成任务的处理

agent 被中断、额度耗尽或任务延期时，不能留下模糊状态。负责人必须三选一：

### 保留

写明负责人、下一步、截止时间；worktree 状态保留为 `paused`，最长 48 小时。

### 转交

新 agent 接管原 branch 和 worktree，并更新登记与 `view.md`。

### 废弃

确认没有需要保留的修改后：

```bash
git -C <worktree> status --short
git log --oneline main..<branch>
git branch -D <branch>
git push origin --delete <branch>
git worktree remove <worktree>
git worktree prune
```

废弃前必须把重要结论写入 `docs/`，不能只存在 worktree 里。

## 8. 每日/每轮收口检查

主 checkout 每次交接前必须执行：

```bash
git worktree list --porcelain
git branch -a -vv
git fsck --no-reflogs --unreachable 2>/dev/null | head -50
find /home/lucian/projects/FPGA-worktrees -mindepth 1 -maxdepth 1 -type d -print 2>/dev/null
```

检查规则：

- `main` 之外的 branch 必须有正在运行的任务；
- 每个 worktree 必须能映射到一个 branch 和负责人；
- 已合并 branch 不得继续存在；
- `paused` 超过 48 小时必须转交或废弃；
- 空目录、失效 worktree 必须 `git worktree prune` 后删除；
- 发现孤儿项时，交接不能标记为完成。

## 9. 本项目的推荐协作模式

| 任务 | 模式 |
|---|---|
| 单文件文档小改 | `main` 直接提交 |
| RTL/PS/上位机并行 | branch + 独立 worktree |
| Vivado/XSim 构建 | 专用 worktree，禁止与源码 agent 共用 |
| 板卡操作 | 单独持有板卡令牌，独占 worktree |
| 最终回归/发版 | `main` 或 integration worktree |

**完成的定义不是“代码写完”，而是“branch、worktree、构建临时目录和 view 状态都已收口”。**
