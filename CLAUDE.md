# CLAUDE.md

## 必读

**`AGENTS.md` 是本项目的开发规范，动手前必须完整读一遍**（语言约定、Git 绑定门禁、
文档地图、事实边界、开发前检查表、常见陷阱）。本文件只放对 Claude Code 生效的操作规则。

## 强制：每个 agent 都要写 view.md 看板

用户只看仓库根目录的 `view.md` 来了解各个 agent 在干什么。**主会话和每个子 agent
都必须**用 `tools/agent_view.sh` 登记自己的状态（脚本内部 `flock` 串行化，支持并发）：

```bash
tools/agent_view.sh start  --agent "<名字>" --doing "在做什么" --why "为了解决什么问题" --next "下一步可能干什么"
tools/agent_view.sh update --agent "<名字>" --doing "..." --next "..."   # 省略的字段沿用上次
tools/agent_view.sh block  --agent "<名字>" --doing "..." --why "..." --next "在等什么"
tools/agent_view.sh done   --agent "<名字>" --doing "..." --next "..."
tools/agent_view.sh show                                                # 查看当前看板
```

规则要点：

1. **拿到任务、动手之前**先 `start`；**交接之前**最后 `done`。
   `done` 之后条目会自动从「当前状态」摘除（**零残留**），完成记录留在「最近动态」里，
   所以正常收工**不需要**再手工 `clear`。看板上永远只剩还在跑的 agent。
   反之，「进行中/阻塞」超过 6 小时没更新会被自动标注「⚠️ 可能已中断」——
   看到就接手或 `done` 掉，别留着。
2. 主会话固定用 `--agent main`；子 agent 用任务短名（`voter-4kb`、`m3-bd-sim` …），
   并行时名字不得重复（同名会互相覆盖）。
3. 换子任务、结论变化、启动长任务（综合/实现/XSim 长跑）之前，都要 `update`；
   受阻立刻 `block`，并把「在等用户回答什么」写进 `--next`。
4. 三个字段都要写具体内容（带上关键文件名/脚本名），不要写「处理任务中」这类空话。
5. **派生子 agent 时**，必须在给它的 prompt 里指定 `--agent` 名字，
   并要求它按本节规则 `start` / `update` / `done`。承载通道见下一节。
6. **禁止手工编辑 `view.md`**：它由脚本生成，手改会被下一次刷新覆盖。
   `view.md` 与 `.agent_view/` 不进 Git；结论与判据仍要写进 `docs/` 并提交。

详细说明见 `AGENTS.md` 的「工作可见性：view.md 看板（强制）」一节。

## 子 Agent 一律用 codex 承载（覆盖 Claude Code 默认行为）

执行计划时**主对话就是本会话**：Claude Code 接 DeepSeek（`ANTHROPIC_MODEL=deepseek-flash[1m]`），
负责执行任务本身，并且是唯一 Git 写入者。

**派生任何子 agent 都不要用 Agent 工具**——Agent 工具的子会话跑在 `CLAUDE_CODE_SUBAGENT_MODEL`
上，拿不到用户指定的子 agent 模型。改为用 Bash 调 codex CLI 非交互模式：

```bash
codex exec -m gpt-5.6-luna -c model_reasoning_effort=max \
  -C <工作目录> --skip-git-repo-check "<子任务 prompt>"
```

模型固定 `gpt-5.6-luna`、思考强度固定 `max`，**两者都必须显式传**：codex 的默认 `model` 是
`gpt-6-astra`（不在其模型目录里），luna 的默认强度只有 `medium`。
给 codex 子 agent 的 prompt 里同样要写清它用哪个 `--agent` 名字、按上节规则登记看板、
**不执行任何 Git 写操作**。

通道自身的可用性、验证依据与当前阻塞项见 `AGENTS.md` 的
「子 Agent 的承载通道与模型」一节。

## Git 提交（覆盖 Claude Code 默认行为）

- 提交信息**禁止带 `Co-authored-by` / `Co-Authored-By` 尾注**。
- 禁止 `git add -A` / `git add .`：按文件显式 add，提交前 `git pull --rebase`，
  推完确认 `main...origin/main` 为 `0/0`。多会话并行时这条是硬要求。
- **提交时把路径写进 commit**：`git commit -m "..." -- <你的文件>`。
  `git commit` 提交的是索引全部内容，而**索引是整棵工作树共享的**：别人在你 add 与
  commit 之间 add 东西、或者跑 `git pull --rebase`（autostash 会重置索引），都会改掉它。
  两个方向都出过事——别人的文件混进你的提交（`7747e9e`），你的文件被踢出索引。
  带路径的 commit 不看索引、直接取这些路径的工作树内容，两边都堵住；
  「add 后复核索引」堵不住，复核与 commit 之间照样会被插入。

完整门禁见 `AGENTS.md` 的「Git 绑定与远程交付（最高优先级门禁）」一节。
