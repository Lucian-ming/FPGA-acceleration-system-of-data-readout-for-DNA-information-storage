> 脱敏副本，原件 `20261013T123941Z-4e02cebabd/{prompt.txt,answer.md}`。本机绝对路径、邮箱、凭据形模式及非白名单私网 IP 已替换；除脱敏与换行规范化外保留原文。

## 1. 仓库记录的要求

下表整理的是仓库对比赛要求的转述；未找到随仓库保存的正式评分表原件，因此具体评审口径只能按仓库现有记录说明。

| 要求 | 仓库写明的内容 | 仓库未定义的验收细节 |
|---|---|---|
| **大模型协作与技能包：15 分** | [docs/05-implementation-plan.md](<仓库根目录>/docs/05-implementation-plan.md) §7 将其列为 15 分；要求提交提示词、回答、自我纠错轨迹，并整理为可提交记录。 [docs/submission/ai-collaboration/readme.md](<仓库根目录>/docs/submission/ai-collaboration/readme.md) 也这样描述。 | 要交多少组、能否节选、提示词和回答是否必须逐字、记录需采用什么格式，**仓库未定义**。 |
| **技能包** | [docs/05-implementation-plan.md](<仓库根目录>/docs/05-implementation-plan.md) §7 要求 `skill/README.md`、补充新板和 16 路内容、入口说明怎么用。[docs/submission/skill/readme.md](<仓库根目录>/docs/submission/skill/readme.md) 规定每包写适用场景、使用方法、失效条件、已验证效果和来源，并将整个目录复制为提交包的 `skill/`。 | README 手册式技能是否满足比赛对 skill 的正式格式、是否要求机器可加载文件，**仓库未定义**。§7 写的 `README.md` 与全小写命名要求也有大小写冲突。 |
| **文件和目录命名** | [docs/05-implementation-plan.md](<仓库根目录>/docs/05-implementation-plan.md) §7 要求纯英文小写，并要求报告说明保留原名的理由。 | 规则覆盖整个 Git 仓库还是仅提交包、哪些例外会被评审接受，**仓库未定义**。 |
| **开源许可** | §7 要求 MIT 或 Apache-2.0，并确认 GitHub 仓库为 public。[README.md](<仓库根目录>/README.md)「许可」说明项目原创部分采用 MIT，第三方数据、板级资料及工具生成物不适用该许可。 | public 状态要用什么证据确认、如何随比赛包提交许可文本，**仓库未定义**。 |
| **工具版本与复现** | §7 的硬要求是 Vivado 2026.1 或 2025.2；使用其他版本须写明版本并保证可复现，不能只写“未做”。[AGENTS.md](<仓库根目录>/AGENTS.md)「工具链分工」和 README「验证与构建」规定当前主线在 WSL 使用 Vivado/Vitis 2022.2，Windows 2026.1 只负责下载、调试，22 主线是发布线。若缺指定软件包，按实际可用版本构建并注明差异。 | 最低复现证据要包含哪些命令、manifest、制品或报告，**仓库未定义**。 |
| **协作模型与留证** | AGENTS「子 Agent 的承载通道与模型」规定经 codex-luna 使用 gpt-6-luna/max，成功须同时满足 `completed / ok=true / exit_code=0 / turn_completed=true`；原始 MCP 记录保存到仓库外的 `prompt.txt`、`answer.md`、`result.json`、`run.jsonl`。 | 哪些任务需要入比赛协作记录、失败任务是否纳入、留证保存多久，**仓库未定义**。 |

[docs/05-implementation-plan.md](<仓库根目录>/docs/05-implementation-plan.md) §7 还把通用 PYNQ Skill 记为“单独加分”机会项；目前项目是裸机，未记录该项具体分值或验收口径。

## 2. 现状盘点

### 技能包

`docs/submission/skill/` 下有 **8 个技能包**：

1. `board-bringup-debug`：开发板 USB、JTAG、串口、网口和 PHY 分层排障。
2. `fpga-timing-probe`：单模块 OOC 资源及时序摸底。
3. `bottleneck-attribution`：用分段计时和对照实验定位 PS/PL 瓶颈。
4. `accel-vs-cpu-baseline`：建立 CPU 与 FPGA 基线并约束加速比口径。
5. `board-stage-evidence`：逐级取证并用故障注入检查判据鉴别力。
6. `ip-packaging-hygiene`：检查综合打包实现与回归覆盖是否一致。
7. `ai-agent-collaboration`：多 Agent 看板与 Git 提交隔离方法。
8. `claims-ledger`：区分可说、不可说、实测、估算和未测结论。

入口 [skill/readme.md](<仓库根目录>/docs/submission/skill/readme.md) 说明提交时复制整个目录，并提供适用对象、主题、附件索引；**8 个包的 README 都有“使用方法”章节**，因此作为人工操作手册，基本回答了怎么用。它不是自动加载的技能格式，正式格式是否另有要求仓库未定义。

仍有两个可打包性缺口，[skill/audit.md](<仓库根目录>/docs/submission/skill/audit.md) 已指出：

- `ai-agent-collaboration` 依赖唯一源码 `tools/agent_view.sh`，单独复制 `skill/` 后脚本不随包提供。
- `accel-vs-cpu-baseline` 缺少主机逐字段比较器；现有 XSDB 模板不能独自判定结果是否一致。

### 提示词与回答素材

- [docs/agent-prompts/](<仓库根目录>/docs/agent-prompts/) 有 **5 份实际提示词**：`main.md`、`board-migrate.md`、`rtl-16way.md`、`verify-system.md`、`speed.md`，另有 `readme.md` 索引。`ai-collaboration/prompts.md` 是摘要，不是逐字提示词；它没有列出索引中的 `speed.md`，需要同步。
- `logs/agents/` 当前有 19 个文件：**1 个 `prompt.txt`、0 个精确命名的 `answer.md`**，另有两个名称含 `answer` 的阶段交付文件及其他报告。这些是任务材料和结果摘要，不构成系统化的提示词/回答配对。
- 主机外部目录 `~/.local/state/codex-subagent/runs/` 当前有 **46 个任务目录**：43 组同时有 `prompt.txt` 和 `answer.md`；其中 **38 组**满足四项成功状态，另 4 组取消、1 组超时；还有 3 组只有 prompt。完整材料在本机、仓库外，不能直接视为已提交材料。[agent-usage.md](<仓库根目录>/docs/submission/ai-collaboration/agent-usage.md) 已明确此边界。

### 自我纠错素材

已有提交摘要 [self-correction.md](<仓库根目录>/docs/submission/ai-collaboration/self-correction.md)，列了四条真实纠错；另外还有可引用的测量与算法反证：

- **MDIO 读错完成寄存器、漏开 MDEN**：把探测器自身错误归因成板卡问题，改为核对 NETWORK_STATUS[2] 和 NETWORK_CONTROL bit 4 后读到 PHY。见 `self-correction.md`「MDIO 无应答」及 [migration-source-table.md](<仓库根目录>/docs/board/bkb220/migration-source-table.md) §9.5、§9.6。
- **lwip220 假阻塞**：把 Vitis 2022.2 不提供的 lwip220 写成必需项；核对安装树后改用实际可用的 lwip211。见 `self-correction.md`「假阻塞」、来源表 §12.5 和 [07-board-build-and-acceptance.md](<仓库根目录>/docs/07-board-build-and-acceptance.md) §3a。
- **探针配置不等于制品配置**：独立 ps7_init 探针能读到 PHY，不代表实际 P4 包带有对应 MIO 配置；核对制品后发现缺项并重建。见 `self-correction.md`「探针配置不等于制品配置」、来源表 §12.1–§12.4。
- **CRLF 导致判据误报**：串口内容存在，但行尾正则把输出判为空；归一化行尾后修正。见 `self-correction.md`「CRLF」及来源表 §13.1。
- **跨小时 A/B 把结论做反**：旧 `t_result` 为 8.682 秒，同小时参考重测为 9.34 秒；跨时段比较会误称新包变慢 7.5%。见 [bkb220-p16-speed-a-upload.md](<仓库根目录>/docs/benchmarks/bkb220-p16-speed-a-upload.md) §5、[09-evidence-ledger.md](<仓库根目录>/docs/09-evidence-ledger.md) P8b。
- **提前终止的收益被实测否掉**：真实样本中 40,800 个 64-lane 块全部跑满 150 拍，提前退出 0 次。见 [08-performance-and-strategy.md](<仓库根目录>/docs/08-performance-and-strategy.md) §2.1；相关子任务的原始 prompt/answer 在本机任务目录 `20261013T104103Z-2fa27a1842`。
- **精确种子索引方向被实测推翻**：256 条读段的水印最长精确匹配中位 5 nt、最大 7 nt，远短于约 16 nt 的选择性种子。见 [competition-strategy.md](<仓库根目录>/docs/archive/history/2026/pre-bkb220-handoff-2026-10-10/competition-strategy.md) §5.1 和 `tools/bench_align.py::seed_feasibility`。

因此，“错误假设—反证—改正”素材充足；不足在于现有四条是整理摘要，没有把对应的真实 prompt、回答和 job_id 配成可提交记录。

## 3. 缺口清单：按分值/成本比排序

| 顺序 | 要求 | 现状 | 缺什么 | 具体补法（产出文件） | 分值/成本 |
|---|---|---|---|---|---|
| 1 | LLM 协作记录 | 有提示词目录、四条纠错摘要；本机有 38 组完整成功记录 | 提交目录里没有一组可复核的 prompt/answer/job 状态配对；raw 只在本机 | 新建 `docs/submission/ai-collaboration/interactions.md`，选 4–5 个代表任务，逐项列 job_id、模型/状态、prompt 与 answer 摘要或明确标注的摘录、反证和修正，并链接仓库证据。至少覆盖 MDIO、lwIP、探针/制品差异、跨小时或提前终止 | **15 分合项中的核心，材料已在手，低成本** |
| 2 | Vivado 版本与可复现 | README/AGENTS/07 已记录 2022.2 与 2026.1 分工及构建入口；当前发布线仍以 2022.2 为准 | [docs/03-status.md](<仓库根目录>/docs/03-status.md) §1e 仍记版本说明待处理；提交目录缺统一说明。2022.2 与比赛版本要求的差异需解释 | 新建 `docs/submission/tool-versions/readme.md`，列实际 Vivado/Vitis/XSDB、Windows 下载端版本、Vitis 实际 lwIP 版本，附可复现命令、manifest/制品标识及 22/26 分工；若不以 2026.1/2025.2 构建，明确给出复现保证 | **文档与可复现 15 分 + 硬性版本项；低成本** |
| 3 | MIT/Apache 与 public | 根 `LICENSE` 已是 MIT，README 说明原创与第三方材料的许可边界 | §7 仍写“没有 LICENSE”；仓库内未找到 GitHub public 状态证明 | 更正 [docs/05-implementation-plan.md](<仓库根目录>/docs/05-implementation-plan.md) §7 的过期状态；新建 `docs/submission/open-source.md` 记录仓库公开状态、核查日期和许可范围。若比赛包包含许可文件，另提供全小写 `license.md` | 分值未注明；核查和文档成本极低 |
| 4 | 技能包可单独使用 | 8 包都已有使用章节，并补了 BKB220/P16 内容 | AI 协作包缺少随包脚本；CPU 基线缺逐字段比较器 | 新建 `docs/submission/skill/package-manifest.md`，写明打包附件。打包时从唯一源码 `tools/agent_view.sh` 取件；在结果格式核实后补 `docs/submission/skill/accel-vs-cpu-baseline/compare_results.py` | 属于同一 15 分项；脚本/格式核实成本中低 |
| 5 | 命名合规 | 目标提交目录当前扫描未发现违规名 | `skill/audit.md` 仍称 `readme.md`、`audit.md` 大小写违规；规则适用范围和保留名例外未闭环 | 更正 `docs/submission/skill/audit.md` 的命名结论；新建 `docs/submission/naming-audit.md`，定义最终包范围并解释根级保留名 | 分值未注明；成本低 |
| 6 | PYNQ 技能包加分项 | 当前是裸机，没有 PYNQ 包 | 是否值得投入及具体加分值未定义 | 若确认比赛材料仍可追加，再建 `docs/submission/skill/pynq/readme.md`，提供适用于该设计的 PYNQ 迁移/复现步骤；否则在报告中标作未采用机会项 | 加分值未注明；非硬门槛 |

## 4. 命名合规

对 `docs/submission/**` 和 `docs/agent-prompts/**` 的当前文件、目录逐段检查，**发现 0 个不合规名称**：前者 16 个文件、10 个目录；后者 6 个文件、无子目录。技能附件 `baremetal_baseline.tcl.in`、`ooc_probe.tcl` 也都是小写。

不过有两处文档不一致：

- [docs/05-implementation-plan.md](<仓库根目录>/docs/05-implementation-plan.md) §7 用大写 `skill/README.md` 指技能入口，同时要求全小写；当前的 `skill/readme.md` 符合小写规则，提交包应沿用实际小写名。
- [docs/submission/skill/audit.md](<仓库根目录>/docs/submission/skill/audit.md)「缺口清单」仍称 `readme.md` 和 `audit.md` 违规，和当前文件名相矛盾；其中 `tools/readme.md` 的大小写引用也与实际 `tools/README.md` 不一致。

保留名的理由应分范围看：

- `AGENTS.md`、`CLAUDE.md` 是仓库级 Agent 指令文件。若它们不是比赛包内容，保留原名有充分的工具兼容理由；若纳入严格小写的比赛包，仓库未定义评审是否接受该例外。
- `LICENSE` 的大写名称符合项目所称的 GitHub 识别惯例，但这只能解释仓库根文件名，**不能证明竞赛命名规则认可该例外**。若许可文件进入严格小写的比赛包，应随包提供小写名版本，或明确该包不含仓库根元数据。
- `docs/archive/**` 中确有路径与 SHA 绑定的材料，例如 `docs/archive/tools/2026/retired-20261011/SHA256SUMS.txt` 和 `pre-bkb220-handoff-2026-10-10/snapshot-manifest.json`；这些历史路径不改是合理的证据保护做法。但现有资料只能证明部分归档受此类 manifest 保护，不能证明整个 `docs/archive/**` 每个文件都在路径 SHA 清单中。若归档不进入比赛包，保留历史原名合理；适用范围仍应在命名说明中写清。
- 若提交的是**整个仓库**，目前的目标目录检查不足以证明全仓合规；根 `README.md`、`tools/README.md` 等也为大写名称。比赛包究竟是否包含它们，仓库未定义。

## 5. 开源自检

根目录 **有 `LICENSE`，内容是 MIT License**。README 将 MIT 范围限定为本项目原创源码、脚本、测试和文档，并明确排除第三方数据、厂商资料与 AMD/Xilinx 工具派生产物。

因此，[docs/05-implementation-plan.md](<仓库根目录>/docs/05-implementation-plan.md) §7 “仓库根没有 LICENSE、需新建”的状态已经过期；[docs/03-status.md](<仓库根目录>/docs/03-status.md) 的后续状态表也记录了 MIT 已入库。**许可证文件已补，GitHub 是否 public 在仓库材料中未找到当前证明。**

**产出与验证：**交付物是本答复，没有创建或修改文件。完成了只读文件盘点、名称扫描和子任务素材计数；未运行测试、Vivado/XSim 或板卡操作。仍未闭环的是提交目录中的 prompt/answer 配对记录、Vivado 版本说明与复现保证、GitHub public 状态证据，以及命名审计的过期结论。
