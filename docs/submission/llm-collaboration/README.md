# LLM 协作记录归档

本目录归档项目竞赛材料中的 Codex 子 Agent 调用证据：脱敏后的完整提示词与回答副本、全量调用索引，以及从原始事件流核实的纠错摘录。它记录可查事实，不推断评分结果。

## 清点范围

- 快照时间：2026-10-14 14:59:11 UTC。
- 原始目录：`~/.local/state/codex-subagent/runs/<run-id>/`；本机路径前缀可忽略。
- 本次共清点 **87 个 runs 子目录**，表示调用次数（包含取消、重派、失败和冒烟任务），不是去重后的独立需求数。
- 每个调用的原始 JSONL 合计 **40,097,093 bytes（38.24 MiB）**；完整事件流没有复制进提交区。每条记录的原始文件大小见 [inventory.md](inventory.md) 和对应 `trace.md`。
- 原始 `prompt.txt` 非空：87/87；原始 `answer.md` 非空：82/87。没有回答的调用不补写答案。
- 有 `result.json` 的记录中，模型元数据分布：
- `gpt-6-luna`：84 次
- `待 result.json`：3 次

### 调用状态

- `cancelled`：6 次
- `completed`：76 次
- `failed`：1 次
- `result.json 尚未生成`：3 次
- `timed_out`：1 次

### 沙箱权限（读取 result.json）

- `read-only`：28 次
- `workspace-write`：56 次
- `元数据待生成`：3 次

没有 `result.json` 的 3 条记录，无法确认沙箱权限，未从 prompt 推断。

### 任务类型

- `board-engineering`（板迁移、G3 验收与制品构建）：18 次
- `client-engineering`（客户端行为、测试和 UI 工程）：8 次
- `ldpc-engineering`（LDPC 探针、RTL、回归与固件集成）：12 次
- `model-channel`（MCP/Codex 通道与运行时冒烟测试）：9 次
- `performance-analysis`（Stage/吞吐/周期/时序优化分析）：19 次
- `project-docs`（文档、技能包、协作材料与合规）：14 次
- `system-analysis`（系统数据通路与架构只读分析）：7 次

## 阅读顺序

1. 先看 [inventory.md](inventory.md)：列出每次调用的任务/用途、UTC 时间、权限模式、可核验的项目写入事件、运行状态和原始 JSONL 大小。每行可进入该调用目录。
2. 每个调用目录中的 `prompt.md` 与 `answer.md` 是原文脱敏副本；`trace.md` 记录原始日志来源、大小和 SHA-256。未选中的调用明确标注“没有核实到可提交的自我纠错链”，不据此声称发生过纠错。
3. 看 [self-correction.md](self-correction.md)：4 个经过事件级核验的“现象 → 定位 → 修正 → 复验”案例；每个案例都链接到对应 prompt、answer 和轨迹摘录。

## 脱敏范围

导出前扫描并替换了本机仓库/用户绝对路径、Windows 盘符路径、邮箱、常见凭据格式与赋值型密码/令牌、私钥块，以及白名单板卡地址 `192.168.1.10` 以外的私网 IPv4。仓库根目录用 `<仓库根目录>`，其它本机路径用 `<本机路径>`。**唯一保留的私网 IPv4 是项目文档确认的板卡 IP `192.168.1.10`。**脱敏副本保持原文结构，但敏感值不再逐字一致；原始留证只读保存在本机 runs 目录。

## 范围边界与缺口

- 归档内容是 codex-subagent 的原始 prompt/answer 副本及少量 JSONL 事件摘录；没有把 38+ MiB 的完整 JSONL 搬入 Git。需要复核完整过程时，按 `~/.local/state/codex-subagent/runs/<run-id>/run.jsonl` 回到本机原件。
- 快照中有 3 条记录尚无 `result.json`，并且 5 条没有非空 answer；这些被列入清单但没有伪造最终回答。
- 本档不含主会话 Claude Code 的完整交互转录，也不代替技能包、验证报告或评分承诺。若竞赛方要求主会话的逐轮原始 transcript，需要另行导出/确认来源。
- 本目录只整理材料，没有执行 Git 写操作；待主会话审阅后提交。
