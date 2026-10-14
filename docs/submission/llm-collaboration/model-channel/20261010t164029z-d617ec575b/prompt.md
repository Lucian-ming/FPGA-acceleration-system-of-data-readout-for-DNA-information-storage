> 脱敏副本，原件 `20261010T164029Z-d617ec575b/{prompt.txt,answer.md}`。本机绝对路径、邮箱、凭据形模式及非白名单私网 IP 已替换；除脱敏与换行规范化外保留原文。

你是本仓库一个临时子 agent，名字叫 codex-luna-smoke。严格按顺序做三件事，不要做别的：
(1) 在仓库根目录执行：tools/agent_view.sh start --agent codex-luna-smoke --doing '验证 codex-luna MCP 子agent与看板登记' --why '用户要求实测子agent承载通道' --next '读文档后登记 done'
(2) 只读地查看 AGENTS.md 中标题为「子 Agent 的承载通道与模型」那一节，回报该节当前写明的"可执行模型名"是什么（逐字引用）
(3) 在仓库根目录执行：tools/agent_view.sh done --agent codex-luna-smoke --doing '通道验证完成' --next '无'
严禁执行任何 git 命令（包括 status/diff），严禁改动 .agent_view/ 和 view.md 以外的任何文件。最后输出一行 JSON：{"agent":"codex-luna-smoke","doc_executable_model":"..."}