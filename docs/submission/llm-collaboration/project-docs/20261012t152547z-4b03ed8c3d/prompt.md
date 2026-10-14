> 脱敏副本，原件 `20261012T152547Z-4b03ed8c3d/{prompt.txt,answer.md}`。本机绝对路径、邮箱、凭据形模式及非白名单私网 IP 已替换；除脱敏与换行规范化外保留原文。

你是子 Agent，看板名 **phase-summary**。任务：**整理现阶段成果的阶段总结**（不是最终报告）。上一轮你因误把仓库绑定门禁当自己的前置而阻塞退出（那是主会话漏写提醒，已写进 AGENTS.md，不怪你），现在已更正，请继续。

**【必须先读】不要运行 `tools/verify_repo_binding.sh`（含 `--remote`/`--require-synced`）。** 那是 **main 的门禁**，main 已代跑留证（见 `docs/03-status.md`）。codex 沙箱把 git 目录（本仓库 gitdir 是 `.git-data`）挂成**只读**，脚本写 `FETCH_HEAD` 必报 `Read-only file system` —— **沙箱特性，不是仓库故障**。`AGENTS.md`「子 Agent 的承载通道与模型」一节有同样说明。

【看板】workspace-write，动手前 `tools/agent_view.sh start --agent phase-summary --doing "..." --why "..." --next "..."`，收工 `done`。
【禁止】Git 写操作；不派生子 Agent；**只写一个文件：`docs/reference/phase-summary-2026-10-12.md`**（别碰 `docs/submission/` 下的东西，那归另两个 agent）；不改 docs 根 01～09。

**重要**：这**不是**最终报告 —— 用户明确说最终报告要等「全面优化完成、停止修改之后」再写。你写的是**阶段性整理**：把"现在到哪儿了、凭什么这么说、还没做什么"讲清楚，供后续写报告时取材。

**素材（都可查证，不要凭印象）**：
- `docs/03-status.md`（§1a/§1b/§1c/§1d 与阶段进度表）
- `docs/board/bkb220/migration-source-table.md` §9～§15
- `docs/benchmarks/bkb220-p4-p16-100mhz-build.md`
- `docs/05-implementation-plan.md`（F0～F9、G0～G8、以及新增 §7 按比赛评分表重排的计划）

**结构**：
1. **一句话现状**。
2. **已完成（附判据与证据路径）**：F0～F5；F4 整机 G3（图片 SHA `fcd0cf90bd680e7bbdc203e3398119504da0897acac9e2117008b4efb6b1f2c3`）；A 五项（全量三轮/连续+状态复位/配置守卫 7-7/断连畸变 30-30/中途断网 3-3）；B1 P16 重建；B2 P16 上板（smoke/全量三轮/连续+状态复位）。每条写**判据是什么、证据在哪个目录**。
3. **关键数字**：P4/P16 整机 WNS/WHS/失败端点/LUT；同板 P4 vs P16 的 `t_result`（smoke 1.45s vs 0.75s；全量 26.51s vs 8.61s，约 3.05×）。**口径必须写明**：`t_result` 不含上传与 LDPC、不是整轮，正式口径待 C1 六档矩阵。
4. **踩过的坑与纠正**（简版，细节指向来源表 §12/§13）：MDIO 完成标志/MDEN、lwip220 假阻塞、**探针配置 ≠ 制品配置**、CRLF 假 FAIL。
5. **仍未做 / 单列**：C1 矩阵、C2 泛化、D 长稳；QSPI/SD 冷启动、UART 反方向、DDR 板级延迟、工业级料号；**功耗缺仪器**；SE250 另 profile；合规缺口（**仓库根无 LICENSE**、主线用 2022.2 而比赛硬要求 2026.1/2025.2、LLM 交互记录需整理、决赛一页英文海报未做）。
6. **下一步**：指向 `docs/05` §7 的 P1～P7。

**纪律**：只写你核证过的；引用代码位置写**函数名/符号名**不写行号；未测的一律写"未测"，**不要把准备成果或估算写成实测**。

最终答复给出：文件路径、写到什么程度、哪些没做完。