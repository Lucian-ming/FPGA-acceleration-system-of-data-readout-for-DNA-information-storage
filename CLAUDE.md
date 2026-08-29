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
2. 主会话固定用 `--agent main`；子 agent 用任务短名（`voter-4kb`、`m3-bd-sim` …），
   并行时名字不得重复（同名会互相覆盖）。
3. 换子任务、结论变化、启动长任务（综合/实现/XSim 长跑）之前，都要 `update`；
   受阻立刻 `block`，并把「在等用户回答什么」写进 `--next`。
4. 三个字段都要写具体内容（带上关键文件名/脚本名），不要写「处理任务中」这类空话。
5. **用 Agent 工具派生子 agent 时**，必须在给它的 prompt 里指定 `--agent` 名字，
   并要求它按本节规则 `start` / `update` / `done`。
6. **禁止手工编辑 `view.md`**：它由脚本生成，手改会被下一次刷新覆盖。
   `view.md` 与 `.agent_view/` 不进 Git；结论与判据仍要写进 `docs/` 并提交。

详细说明见 `AGENTS.md` 的「工作可见性：view.md 看板（强制）」一节。
