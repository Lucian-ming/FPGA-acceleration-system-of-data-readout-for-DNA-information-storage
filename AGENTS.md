# FPGA DNA 数据读出项目：AI / 开发协作指南

## 语言与范围

- 与用户沟通、代码注释、新增文档默认使用中文。
- 不重构无关代码，不删除历史数据或构建产物（`data/`、`archive/`、两份 XSA 只读）。
- 未经用户同意，不修改、重命名或覆盖 `data/R0.83_data/` 中的任何文件。

## Git 绑定与远程交付（最高优先级门禁）

- 开发必须位于用户指定的 **WSL 原生文件系统 checkout**；路径可随机器或用户授权的新 clone 变化，
  但唯一允许的 GitHub 仓库是
  `Lucian-ming/FPGA-acceleration-system-of-data-readout-for-DNA-information-storage`。
- 禁止 `git init` 另建仓库，禁止在项目内创建嵌套仓库，禁止在同一任务中同时修改多个 checkout。
  只有用户明确要求新建独立 WSL 文件夹时才允许重新 clone；拉取或接手后仍必须绑定上述 GitHub
  仓库。绑定核验未通过前，禁止进行仿真或开发。
- 开始工作必须在仓库根目录运行 `bash tools/verify_repo_binding.sh --remote`。该命令必须确认脚本所属 checkout、
  `main`、`origin/main`、指定远端以及当前 GitHub 身份的 fetch/push 权限；任一项失败立即停止。
- 只允许在 `main` 开发。所有有意义的源码、脚本、测试摘要和交接文档必须提交，并在每次提交后执行
  `git push origin main`；禁止留下仅存在本地的提交。交接前运行
  `bash tools/verify_repo_binding.sh --require-synced`，结果必须显示 `main...origin/main` 为 `0/0`。
- **本轮并行执行约束**：主会话是唯一 Git 写入者，子 Agent 不 add/commit/pull/rebase/stash/
  reset/switch/clean/push；子任务交付由 main 审查后统一提交、立即推送。main 操作 Git 前须
  暂停写入并核对其他会话，不能在活跃子任务中触发 autostash。路径限定 commit 仍然必须使用。
  当前不创建分支/worktree，独占路径、资源和中断回收按 `docs/14-git-parallel-workflow.md`。
- Vivado/XSim 大型生成目录不提交，但不得自动删除；必须提交可复现入口、源文件/黄金数据 manifest、
  结果摘要和结论边界。若 GitHub ruleset 阻止直接推送，立即报告，不得改推其他仓库规避。
- 工具生成的 `*.log`、`*.jou`、`*.str`、`*.pb` 不得留在仓库根目录；Vivado 使用
  `tools/run_vivado_build.sh`，XSim/仿真脚本必须把日志写入对应的
  `hw/build/xsim/<run-id>/` 或 `logs/<tool>/<run-id>/`。交接前必须执行
  `find . -maxdepth 1 -type f \( -name '*.log' -o -name '*.jou' -o -name '*.str' -o -name '*.pb' \)`
  并确认无输出；发现残留时先归档到带时间戳目录，不得静默删除证据。
- **提交纪律**：禁止 `git add -A` / `git add .`，必须按文件显式 `git add <路径>`。
  多个会话并行时共用同一棵工作树，别人的半成品会和你的改动交错在 `git status` 里，
  `-A` 会把它一起提交出去（2026-08-31 就发生过一次）。提交前先 `git pull --rebase`，
  推完确认 `main...origin/main` 为 `0/0`。
- **但「显式 add」挡不住并行会话，必须用带路径的 commit**：
  **暂存区（索引）是整棵工作树共享的一份**，而 `git commit` 提交的是**索引的全部内容**，
  不是「你 add 的那些」。你 `git add` 之后、`git commit` 之前，索引会被别的会话改掉，
  两个方向都出过事（均为 2026-09-03/04 实况）：
  - **别人的文件混进你的提交**：`7747e9e` 把 `docs/archive/history/2026/ps-refactor-plan.md` 和 `docs/README.md` 卷进了一个
    纯 RTL 提交。当事会话确实只 add 了三个 RTL 文件、提交前也复核过 `git status`。
  - **你自己的文件被踢出索引**：另一会话 add 完之后，`git diff --cached` 里多出了两个
    从没 add 过的 `tests/host/golden/*`，而自己的 `tools/run_g3.sh` 反而掉了出去。
    元凶多半不是别人的 `add`，而是别人跑了 **`git pull --rebase`——autostash 会重置索引**。
  所以「add 之后再复核一次索引」堵不住：复核与 commit 之间同样会被 rebase 插入。
  **正确写法是把路径写进 commit**：

  ```bash
  git commit -m "..." -- sw/app/echo.c      # 只提交这些路径
  ```

  实测（GNU git，2026-09-04）两个方向都成立：索引里有别人的 `theirs.txt`、自己的
  `mine.txt` **完全没 add** 时，`git commit -m .. -- mine.txt` 仍然只产生
  1 file changed 且内容是工作树里的新版，`theirs.txt` 原封不动留在索引里；
  换成不带路径的 `git commit` 则是 2 files changed。也就是说带路径的 commit
  **不看索引、直接取这些路径的工作树内容**，`git add` 那一步甚至可以省掉。
  多路径并列写在 `--` 后面。
- 提交信息只描述本次改动，**禁止附带 `Co-authored-by` / `Co-Authored-By` 尾注**；
  这一条覆盖 Claude Code 的默认行为，因此也写在 `CLAUDE.md` 里。

## 工作可见性：view.md 看板（强制）

用户只看仓库根目录的 `view.md`，就应当知道**每个 agent 此刻在干什么**。因此所有 agent
（主会话与任何子 agent、并行 agent）都必须实时登记自己的工作状态。

- **唯一写入方式**是 `tools/agent_view.sh`（内部用 `flock` 串行化，支持多 agent 并发）。
  **禁止**手工编辑 `view.md`：它是自动生成的，手改会被下一次刷新覆盖。
- 三个字段必须都填，且写人话、写具体（不要写「处理任务」这种废话）：
  - `--doing` 在做什么（当前这一步的具体动作，含关键文件/脚本名）
  - `--why` 为了解决什么问题（哪个缺陷/哪条判据/用户的哪个诉求）
  - `--next` 下一步可能干什么（做完这步的下一动作，或在等什么）

```bash
# 开工（每个 agent 拿到任务后、动手前的第一件事）
tools/agent_view.sh start  --agent "<agent 名>" --doing "..." --why "..." --next "..."
# 阶段切换 / 有新发现（省略的字段沿用上一次的值）
tools/agent_view.sh update --agent "<agent 名>" --doing "..." --next "..."
# 卡住（等用户决策、缺工具、复现失败）
tools/agent_view.sh block  --agent "<agent 名>" --doing "..." --why "..." --next "..."
# 收工（交接前的最后一件事）
tools/agent_view.sh done   --agent "<agent 名>" --doing "..." --next "..."
```

- **`--agent` 名字规则**：主会话固定用 `main`；子 agent 用「任务短名」，如 `voter-4kb`、
  `m3-bd-sim`、`ldpc-golden`。同名会互相覆盖，并行时务必取不同名字。
- **更新时机**（宁多勿少，但不要每条命令都刷）：
  1. 开工时 `start`；
  2. 换到另一个子任务、或结论发生变化时 `update`；
  3. 长任务（综合、实现、XSim 长跑）**启动前**先 `update` 说明在跑什么、预计等多久；
  4. 受阻立刻 `block`，把「在等用户回答什么」写进 `--next`；
  5. 结束时 `done`。
- **派生子 agent 时**，必须在给子 agent 的 prompt 里明确写上：它要用哪个 `--agent` 名字，
  并要求它按本节规则 `start` / `update` / `done`。
- **`done` 之后条目会自动从「当前状态」摘除（零残留）**，不需要再手工 `clear`。
  完成这件事本身仍然留痕——它出现在 view.md 的「最近动态」里；
  结论、判据和证据以 `docs/` 为准。所以看板上永远只剩「还在跑的 agent」，
  不会出现「任务早就做完了、条目还挂着」的情况。
- 反过来，**「进行中/阻塞」但超过 6 小时没更新的条目会被自动标注
  「⚠️ 可能已中断」**（会话被杀或额度中断的典型残留）。看到这个标记要么接手，
  要么 `done` 掉它，不要视而不见。阈值可用 `AGENT_VIEW_STALE_HOURS` 调整。
- `view.md` 与 `.agent_view/` 是本机实时看板，已在 `.gitignore` 中忽略，**不进 Git**。
  它不替代交接文档：结论、判据和证据仍然要写进 `docs/` 下对应文档并提交。

## 代码卫生（与证据纪律同级，2026-09-11 新增）

### 为什么要单列这一节

本文其余规则保护的都是**结论**——不得把估算写成实测、不得静默删除证据、
路径限定提交、失败也算产出。**没有一条保护「仓库状态」**。
系统精确地优化了它所度量的东西，于是出现了「一流的证据纪律 + 三流的代码卫生」：

- 五个文件同时定义 `module srpe_batch`，改 `component.xml` 一行就静默换掉微架构，
  **不报错**；
- 回归跑的是 `srpe_batch.v`(2-way)，而打包进比特流的是 `srpe_batch_4way.v`，
  **回归验证的实现与综合出来的实现不是同一个**；
- `bench_align.py` 存着「精确种子法为何失效」的实测反证，却零引用、不在任何文档里，
  导致 `docs/17` 把被它推翻的方向列为第一优先级长期方向。

**共同点：这些缺陷都不产生错误答案，所以整套验证金字塔对它们失明。**

还有一层更隐蔽的原因：**保护证据的规则同时也在保护垃圾**。
「不得静默删除证据」「保留失败实验」用在证据上完全正确，推广到源文件就变成
「什么都不删」——`five_to_four_decoder.v` 被 AGENTS.md 白纸黑字记为死文件，
依然留了一个月。**清理必须要删东西，而规范没有给删除留出口。**
本节就是那个出口。

### 硬规则

1. **卫生问题必须是会红的判据，不是「记得注意」。**
   新发现一类卫生缺陷，先问「能不能写成脚本检查」；能就写进
   `tools/check_ip_packaging.sh`（或同类门禁）并接入 `tools/run_sim.sh`。
   只写进文档的约定，等于没有。

2. **IP 打包目录（`hw/ip/*/hdl/`）只放会被综合的文件。**
   testbench 放 `hw/sim/`（顶层）或 `hw/sim/ip_tb/`（IP 级）；
   实验/半成品/已证伪变体放 `hw/experimental/`；零引用文件不得留在 `hdl/`。

3. **同名模块的多个实现允许共存，但 `component.xml` 必须恰好打包其中一个**，
   且打包内容必须与受版本管理的 `hw/ip/PACKAGED_VARIANTS.txt` 一致。
   换微架构必须在 Git 里留下一处可见的 diff，不能藏在一行文件名里。

4. **被打包的实现必须被回归覆盖。**
   `component.xml` 里列的每个 HDL 文件，都要能在 `tools/run_sim.sh` 里找到
   至少一个用例引用它。测了不会进比特流的那份实现，等于没测。

5. **删除的出口**：确认零引用后，源文件先 `git mv` 到 `hw/experimental/`
   或 `docs/archive/`，**保留 Git 历史即等于保留证据**——
   「不得静默删除证据」指的是**运行留证与实验数据**，不是死代码。
   `hw/experimental/` 下的文件满足以下任一条即可真正删除：
   - 该方向已被实测证伪且结论已写进 `docs/`（如 8-way 的资源证伪）；
   - 与仓库内另一文件逐字节相同（`cmp` 确认）；
   - 其功能已被另一个受回归覆盖的文件完全取代。
   删除必须在提交说明里写明依据的是哪一条。

6. **每个工具都要可被发现。** 新增 `tools/` 下的脚本必须登记进
   `tools/README.md`。**一个无人可见的脚本，等于它得出的结论不存在**——
   这不是比喻，`bench_align.py` 已经让项目付过一次代价。

7. **共享状态没有主人时，由 main 负责。**
   「只写自己独占的路径」防住了并行踩踏，副作用是公共目录整洁无人认领。
   main 在收敛子任务时必须一并检查：根目录残留、`.gitignore` 覆盖、
   新增日志目录、散落文档、零引用文件。

8. **同一份数据不得存多份副本。** 必须共享时收敛到单一来源
   （如 `tests/datasets/common/`），消费方用解析函数回落。
   多份副本各自的校验和都自洽，**发现不了彼此不一致**。

9. **引用代码位置用标识符，不用行号**（2026-09-11 新增）。
   现行文档与新写的注释里，指代码位置要写函数名 / 状态名 / 模块名
   （`stage1_dna.c` 的 `PIPE_WM_TX` 分支），不要写 `stage1_dna.c:178`。
   **行号引用会静默过期**：`echo.c` 的注释里那条 `stage1_dna.c:178` 在别处补了几行注释后
   就指向了错误的内容，并从源码扩散进 5 份文档，**全程没有任何判据变红**。
   `tools/check_repo_hygiene.sh` 第 7 项能抓住悬空与越界，
   但**抓不住「文件还在、行号也在范围内、内容却挪走了」那一种**——那只能靠本条纪律。
   `docs/archive/` 不受本条约束：归档引用的是写作当时的行号，是正确的历史记录。

## 文档编号约定

**现用文档一律带序号**（`docs/01-…` ~ `docs/18-…`），**归档文档一律不带序号**
（`docs/archive/history/2026/` 下全部为纯名字）。这样从文件名就能一眼看出
一份文档是否还有效，也不必因为「历史文档占了号」而给新文档跳号。

文档退役时：`git mv docs/NN-foo.md docs/archive/history/2026/foo.md`，
并更新指向它的引用。归档内容只用于追溯，不能覆盖当前状态。

## 文档地图（改代码前先读）

| 文档 | 作用 |
| --- | --- |
| `docs/README.md` | 精简文档索引与阅读顺序 |
| `docs/01-architecture.md` | 系统架构与算法模型 |
| `docs/02-data-contract.md` | 数据格式唯一权威规范 |
| `docs/03-status.md` | 当前闭环状态、未关闭问题与证据边界 |
| `docs/04-roadmap.md` | 总体开发顺序与验收判据 |
| `docs/05-interfaces.md` | TCP、寄存器、DMA、DDR 地址 |
| `docs/06-implementation-plan.md` | 开发前检查、变更分类与提交门禁 |
| `docs/07-performance.md` | CPU/FPGA 性能基线与瓶颈 |
| `docs/08-verification-plan.md` | 仿真、接口、BD 与 G3 验证层级 |
| `docs/09-board-build-and-acceptance.md` | 板级配置、构建与上板验收 |
| `docs/10-current-handoff.md` | 当前接手顺序与主线 |
| `docs/11-optimization-plan.md` | Stage1、数据、鲁棒性与上位机优化 |
| `docs/12-stress-analysis.md` | 自动压测统计口径与后续改造 |
| `docs/13-final-delivery-roadmap.md` | 从当前状态到最终交付的总收口计划与硬门禁 |
| `docs/14-git-parallel-workflow.md` | 当前共享 main 的并行与回收规范（禁止 worktree） |
| `docs/15-resume-and-parallel-plan.md` | 中断恢复与全流程并行计划 |
| `docs/16-interrupted-work-audit-2026-09-06.md` | 本轮遗留物清点与 dump 复核 |
| `docs/archive/history/2026/` | 历史交接、旧计划和旧状态全文，只用于追溯 |
| `docs/reference/` | 数据集与历史审计参考 |

改架构、协议或数据格式时**必须同步更新对应文档**；修好缺陷时在 `03-status.md` 里划掉并记录判据。

## 事实边界

当前有效事实只看 `docs/03-status.md`，不要从历史文档推断现状：

- G3 已闭环：SE150/SE250 均有真实板端回传、LDPC 图片哈希和四级 DDR 证据；
- SE250 全量 129,600 条记录与连续任务已闭环；
- 当前板级唯一配置见 `docs/09-board-build-and-acceptance.md` 与 `docs/board/zynq-eco-7010/`；
- 当前性能模型是板测事实，不等于 FPGA 已击败优化 CPU；公平基准和 Stage1 展开仍是下一阶段；
- 多 payload 泛化、错误鲁棒性曲线、实测功耗和新板迁移没有证据前不得宣称完成；
- 历史完整证据保留在 `docs/archive/history/2026/`，归档内容不能覆盖当前状态；
- `data/R0.83_data/` 和历史演示结果只可由测试代码显式比较，不能进入生产路径；
- RTL/固件变化后必须重建整套制品并刷新 `SHA256SUMS`；
- 仿真喂黄金数据不等于真实接口正确，跨 IP 接口改动必须有 AXIS/DMA/DDR/寄存器判据；
- 最终正确性判据仍是板端实际回传经 LDPC 后与参考逐位/逐哈希一致。

## 开发前检查表

1. 确认数据版本、文件 SHA-256、输入格式和参数；不同版本绝不共用未说明的常量。
2. 改数据格式前先读 `docs/02-data-contract.md`；三方（Python / PS / RTL）成对修改。
3. 涉及硬件：先核对 PS7/DDR/MIO/PHY、XDC、时钟、IP Catalog、地址图和 XSA 同源性。
4. 涉及 DMA/DDR：重算所有 buffer 区间、cache flush/invalidate、对齐和上限。
5. 涉及 LDPC/图片：禁止绕过 FPGA 结果；提交输入、每级中间输出、最终 bitstream、图片哈希和自动比对。
6. 改 Tcl 时保持现有的脚本定位和本地 IP repository 注册方式，不得重新引入对调用者 `pwd` 的依赖。

## 常见陷阱

- 不要把 `MAX_WATERMARK_SIZE`、`TOTAL_READS`、`NUM_LC`、`REF_LEN` 当成唯一常量；
  它们之间存在约束 `NUM_LC*STRIDE = L - READ_BPS`、`REF_LEN = STRIDE + READ_BPS`。
- 不要把 `tb_dna_quick.v` 编译通过当成功能正确：它的 AXI-Lite `AWVALID`/`WVALID` 恒为 0，
  控制寄存器从未被真正写入。
- **控制寄存器的写序列本身就是被测对象。** 只在 TB 里写一次 `START=1` 不构成判据——
  B27 就是这么漏掉的：`tb_desparsifier` 连**综合后网表**都 PASS，说明既不是 RTL
  也不是综合的问题，而是真实固件那串「写 0 → 写 1 → 100 us 后再写 0」的时序从未被回放过，
  而该 IP 对 `START` 写任何值都会启动。TB 必须按固件的原样顺序回放寄存器写，
  参见 `hw/sim/dec/tb_dec_ddr_restart.v`。
- **同步 FIFO 的读延迟要按实现数，不要按注释数。** `fifo_sync_sdpram_b64` 是两级同步读
  （`raddr_q <= rptr; dout <= mem[raddr_q]`），pop 之后 `dout` 要 3 拍才稳定。
  B24 和 B26 都是照注释里的「1 拍」去采样才出的错，一个丢记录、一个整体错位一条读段。
- 不要把 `apply_bd_automation` 的默认 PS7 配置或历史 XSA 当作新板配置来源；当前约束必须以
  `hw/constr/top.xdc` 和可复现 Tcl 构建的现场结果为准。
- 不要把 `five_to_four_decoder.v` 接回生产数据通路：它是未被顶层引用的死文件；查找表已按契约
  校正，但权威实现与 RTL 判据仍是 `desparsification_decoder_v1_0.v` / `desparsify_datapath.v`。
- **GBK 编码的 RTL 文件：搜中文必须先转码，`grep` 的空结果不能当「没有」。**
  `hw/ip/` 下 `differential_voter_v1_0.v`、`Dna_accelerator_core_v1_0.v` 等是 GBK。
  你的模式是 UTF-8 字节、文件里是 GBK 字节，两串字节根本不同，所以**中文模式恒为零命中**
  （GNU grep 3.4 实测：`grep 累加器` → 0，`iconv -f GBK -t UTF-8 | grep` → 3；
  `rg` 同样无匹配）。跨全库复查中文（例如「这处解释还有几份副本」）必须逐文件判编码、
  GBK 的先 `iconv` 再搜。**搜 ASCII 标识符不受影响**，无需任何特殊开关
  （实测 `grep -c safe_vote_value` → 6，exit 0）。
- **⚠️ 但先确认你手里的 `grep` 是什么**：Claude Code 会注入一个同名 shell 函数
  （内部走 `ugrep -I`，`-I` = 跳过二进制）。这些 GBK 文件第 3 行就有非法 UTF-8 字节，
  于是**整个文件被判成二进制并静默跳过**——连 GNU grep 那句 `Binary file … matches`
  都不打，exit=1、stdout 空，看起来和「确实没有这个标识符」一模一样，
  **连 ASCII 标识符都搜不到**。`type grep` 看是不是函数，`/bin/grep` 可绕开。
  本条曾让人差点得出「peer 说的标识符根本不存在」，也曾让本文档写错一版
  （错写成「一律加 `-a`」——`-a` 只改二进制判定、不转码，对中文加不加都是 0）。
  教训与「范围划错了没人提醒你」同类：**工具被换掉了也没有任何东西会提醒你**。
- 改写这类 GBK 文件仍按老规矩：先 encode 成 bytes → 写临时文件 → `os.replace`，
  绝不能 `open(p,'wb').write(s.encode(...))`（编码抛异常时文件已被截断为 0 字节）。
- **「整文件 SHA-256」是不是合法判据，取决于该产物里有没有环境相关的元数据**——
  两个方向今天各踩到一次，别把其中一条当通则：
  - **编译产物：不能用整文件哈希。** ELF 用 `-g3` 编译，DWARF 行号表存着每条语句的
    行号，源码里加几行**纯注释**就会让调试段变、整文件 SHA 变，而机器码一个字节没动
    （`40ba34f` 给 `echo.c` 加了 24 行注释，`export/` 的 ELF 从此没重建过，
    于是 `9006d0ca…` 对不上重建结果）。正确判据是 `objcopy --only-section` 按
    `.text`/`.data`/`.rodata` 逐段比对，见 `hw/build/export/README.md`。
    Vivado 的报告与 checkpoint 同理（带时间戳、路径、工具版本），要比就比网表。
  - **黄金向量：整文件哈希恰恰是正确判据。** 它们是纯函数产物、不含时间戳，
    `tests/golden/**/SHA256SUMS` 就是靠这个守住的——`make_golden.py` 改成逐票饱和后
    （`b9a3b86`），SE150 15 个 + SE250 16 个文件逐字节不变，正是用它证明的。
  判断方法：问「同样的输入、换个时间或换台机器重跑，这个文件会不会变？」
  会变就说明它带环境元数据，得挑语义载体比；不会变就直接比整文件。
- SE150（51,781 × 150 bp）与 SE250（64,800 × 250 bp）不可混用；
  现有比特流只支持 150 bp。**「几何用错了」这件事在图片哈希上测不出来**：把
  「几何写死成 SE150 的 807/957」这个缺陷注回去，15 个产物里 14 个逐字节不变，
  `dec_input` 照样译出 `fcd0cf90…f2c3`、与 `codeword_R083.txt` 的误码照样
  36/64,800。**唯一有鉴别力的是 `wm_regions.hex`**：SE250 应为 52,750 行 /
  `bf8795dd…`，一旦等于 SE150 的 `f352853912338cd0…` 就是该缺陷的特征签名。
  故障注入实测见 docs/archive/history/2026/se250-study-2026-08-30.md §6「鉴别力实测」；`tools/make_golden.py` 已内置哨兵会红。
  **注意这条实测的适用范围**：它测的是**主机侧黄金模型**
  （`tools/make_golden.py`）——那里几何只喂水印区域展开，Stage1 直接在整条 `ref`
  上滑窗，所以下游整条链路与几何无关。**板上不是这样**：`wm_regions` 预载进
  BRAM 后就是 Stage1 实际比对的对象，几何错了板端结果**应当**会坏。
  也就是说，「板上跑出 `fcd0cf90…f2c3`」仍然是有意义的判据，
  不要据本条去掉它；本条只否掉一件事——**拿黄金向量那条链路上的图片哈希，
  去证明黄金向量用对了几何**。这两者差一个「范围」，正是上一条陷阱说的那种错法。
- **Git 索引被意外截断为 0 字节时的特征与一键修复**：
  多 Agent 并行或频繁提交/rebase 发生写竞争或被中断时，`.git-data/index` 可能被截断为 0 字节。
  症状是任何 Git 命令与 VS Code 轮询立即稳定报 `fatal: .../index: index file smaller than expected`，
  且弹窗关掉又会反复弹出。
  **一键修复**：`rm -f .git-data/index && git reset`（从当前 HEAD 树瞬间重建完整索引）。
  **IDE 防扰**：在 `.vscode/settings.json` 中配置 `"git.showError": false`。
- **WSL 下调用 Windows 命令（`cmd.exe` / `powershell.exe` / `xsdb.bat`）必须重定向 stdin**：
  在非交互式子 shell 或后台任务中执行 Windows 原生进程时，必须显式重定向输入：
  `< /dev/null`（例如 `cmd.exe /c "..." < /dev/null`）。若缺少重定向，
  Windows 进程会无限期挂起等待 stdin EOF，导致调用者卡死。
