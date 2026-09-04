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
- Vivado/XSim 大型生成目录不提交，但不得自动删除；必须提交可复现入口、源文件/黄金数据 manifest、
  结果摘要和结论边界。若 GitHub ruleset 阻止直接推送，立即报告，不得改推其他仓库规避。
- **提交纪律**：禁止 `git add -A` / `git add .`，必须按文件显式 `git add <路径>`。
  多个会话并行时共用同一棵工作树，别人的半成品会和你的改动交错在 `git status` 里，
  `-A` 会把它一起提交出去（2026-08-31 就发生过一次）。提交前先 `git pull --rebase`，
  推完确认 `main...origin/main` 为 `0/0`。
- **但「显式 add」挡不住并行会话，必须用带路径的 commit**：
  **暂存区（索引）是整棵工作树共享的一份**，而 `git commit` 提交的是**索引的全部内容**，
  不是「你 add 的那些」。你 `git add` 之后、`git commit` 之前，索引会被别的会话改掉，
  两个方向都出过事（均为 2026-09-03/04 实况）：
  - **别人的文件混进你的提交**：`7747e9e` 把 `docs/22` 和 `docs/README.md` 卷进了一个
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

## 文档地图（改代码前先读）

| 文档 | 作用 |
| --- | --- |
| `docs/README.md` | 文档索引 |
| `docs/01-architecture.md` | 系统架构与算法模型 |
| `docs/02-data-contract.md` | **数据格式的唯一权威规范**（编码、位序、5b4b 码表） |
| `docs/03-status.md` | 现状与缺陷清单（含 `文件:行号` 证据） |
| `docs/04-roadmap.md` | 开发顺序与验收判据 |
| `docs/05-interfaces.md` | TCP 协议、寄存器、DDR 地址 |
| `docs/08-handoff-2026-08-10.md` | 历史快照（Stage1/Stage3 修复与复核） |
| `docs/09-handoff-2026-08-16.md` | **当前可交接基线**、已复跑判据和下一阻塞项 |
| `docs/12-main-handoff-2026-08-21.md` | **当前主分支交接**、Git 门禁、构建和上板步骤 |
| `docs/13-xsim-simulation-plan.md` | XSim 分层仿真计划、判据和留证规则 |
| `docs/14-next-steps-2026-08-29.md` | 历史快照：G3 闭环**前**的排序（已被 `docs/18` 取代） |
| `docs/15-m3-bd-simulation-2026-08-29.md` | **M3 实际 BD 集成仿真结果**与 BD-3 阻塞证据 |
| `docs/16-board-zynq-eco-7010.md` | **板级配置唯一权威**：ZYNQ ECO(R6) 实物参数、DDR 修正与上板顺序 |
| `docs/17-parallel-tasks-2026-08-29.md` | 并行任务简报：B21 的两条定位路径与会话互斥约定 |
| `docs/18-next-steps-2026-08-30.md` | **当前行动计划**：G3 闭环后的排队、适用范围与技术债 |
| `docs/19-parallel-sessions-2026-08-30.md` | 并行会话简报（**历史，已完结**）：分工/互斥的做法与提示词；§3 是一份「结论被实测推翻」的复盘 |
| `docs/21-parallel-plan-2026-08-31.md` | **当前并行推进计划**：四条线的冲突矩阵、板子令牌协议与五段提示词 |
| `docs/20-se250-study-2026-08-30.md` | **SE250 扩展评估**：几何推导、硬编码清单与分阶段方案（只调研，未改 RTL） |
| `docs/reference/` | 历史审计结果（数据集校验和、文件索引、缺口清单、提交归档），只读参考 |

改架构、协议或数据格式时**必须同步更新对应文档**；修好缺陷时在 `03-status.md` 里划掉并记录判据。

## 事实边界

- **G3 已于 2026-08-30 闭环。** 板端回传经 `tools/ldpc_decode.py` 译码后图片 SHA-256 =
  `fcd0cf90bd680e7bbdc203e3398119504da0897acac9e2117008b4efb6b1f2c3`，与判据逐位相同；
  板上四级 DDR 快照逐级比对全过（`tools/board_stage_check.py`）。
  **一条命令即可复现：`tools/run_g3.sh`**（单一 PASS/FAIL、非零退出码）。
- **闭环的适用范围（当日 6 轮上板实测，全部由 `run_g3.sh` 驱动，逐轮同一张图片哈希）**：
  SE150、`--orient both`、`score_min 67`，**规模 4,096 / 8,192 / 16,384 / 32,768 /
  103,616（全量 51,781 条源读段）条记录**，以及**同一次上电内连续两次任务**
  （两轮回传比特流逐位相同，不只是最终图片哈希相同）。
  二次任务这条要看清楚口径：**同参数两轮测不出「Voter 累加器没清零」**
  （票是有符号累加、输出按符号判决，`clip(x±1)` 对起始值单调 ⇒ 输出必然逐位相同，
  逐位相同恰是该缺陷的必然输出）。累加器复位是靠
  `run_g3.sh --runs 2 --first-run-score-min 0`（第一轮换阈值把累加器弄脏）
  在 2026-08-31 于板上补齐的，该判据自带鉴别力自证。详见 `docs/03-status.md` 同名小节。
  **尚未验证**：SE250、长时间连续运行、三轮以上或跨不同**规模**的连续任务
  （如先全量再 2,048 条）。不得据此声称「系统已全面正确」。
- **「同一次连接内跑两次任务」现有协议不支持**，且是设计如此不是缺陷：
  `conn->configured` 对重复 `PKT_CONFIG` 直接拒绝（拒绝码 8，`echo.c:1691`）。
  二次任务必须另开一条连接；硬件状态不随新连接复位，所以有价值的判据是
  「同一次上电内两条连接」，已由 `run_g3.sh --runs 2` 覆盖。
- **板端处理时长已量化**：`t = 28.90 s + 1.0012 ms/条 × 条数`（五档实测，R² = 1.00000，
  `tools/g3_timing_fit.py` 可复跑）。全量实测 132.67 s。
  **28.90 s 的固定开销是水印预载的约 100 个 poll 步**（`PIPE_WM_TX`/`PIPE_WM_WAIT`
  每区域各占一个 `tcp_poll` 周期，`echo.c:554-586`），与数据规模无关。
  docs/18 先前「全量必然超时 ≈800 s」的结论**已作废**，作废理由见 docs/18 P1 第 3 项：
  它把一个扣除法推断当成了实测。
- **判据纪律不变**：界面成功、图片生成、EXE 正常退出、仿真全绿都不能证明流水线正确。
  唯一判据始终是板端实际回传的数据经 LDPC 后与 R0.83 参考逐位/逐哈希相同。
  这条纪律在 G3 闭环后**更要守住**——2026-08-29 到 30 修掉的 7 个缺陷里，
  有 5 个（B23/B24/B25/B26/B27）在所有仿真里都是绿的，只有上板才暴露。
- **算法本身已被证明正确**：`python3 tools/golden_model.py verify-code` 会用黄金数据证明
  「编码序列 ⊕ 水印 → 5b4b → codeword_R083.txt」逐位成立。要做的是让 RTL 对齐这个模型。
- **历史演示存在「用正确结果直接生成图片」的通道。**
  `data/R0.83_data/` 与 `archive/submission_2025-11-07/演示文件/` 里的
  `result.txt`/`dec_input.txt`/`decoded_bits.txt`/`decoded_image.jpg`/`codeword_R083.txt`/
  `source_bit.txt`/`Milk coronet.jpg` **只能被测试代码读取做显式比较**，
  绝不可进入生产路径。`clients/python/gui_app.spec` 已移除 `dec_input.txt`；后续修改打包规则时
  必须保持这一点。
- 两份 XSA 字节相同（SHA-256 `79c64736...e6eb33`），是历史硬件快照，
  **不是**当前 Tcl 已被证明可再生的产物。
- **历史 XSA 是另一块板**：其 DDR 为 32 bit 双颗 `MT41J128M16`，而目标 ZYNQ ECO(R6)
  实物是单颗 16 bit `MT41J256M16HA-125`。板级配置的唯一权威是
  `docs/16-board-zynq-eco-7010.md` 与 `docs/board/zynq-eco-7010/`，
  **禁止**再据历史 XSA 回退 DDR 配置。
- `hw/build/export/` 中的制品已按 ECO 板的 16 bit DDR 配置、并含 B20/B23/B24/B25/B26/B27
  修复整套重建（2026-08-30），是 G3 闭环那一轮实际烧录的版本。
  改动 RTL 或固件后**必须整套重建并刷新 `SHA256SUMS`**，否则制品与源码不同源。
- `archive/submission_2025-11-07/..._重要代码.rar` 尚未解压（环境缺 RAR5 工具）；
  解压后必须先做来源/哈希差异审计再决定是否导入。
- **仿真喂黄金数据、板上走真实接口——差异就在这里。** 2026-08-29~30 修掉的 7 个缺陷里，
  B23/B24/B25/B26/B27 五个全部落在这条缝上：`run_m2_full.sh` 的 Stage1 只编译
  `srpe_batch.v` + `tb_srpe_batch.v`，直接抓引擎的 `res_din`，**完全绕开**
  `Dna_accelerator_core_v1_0.v` 的 AXIS 输入/输出级；`tb_srpe_batch` 也是把水印直接灌进 BRAM，
  不走 `preload_mode + S_AXIS` 的 DMA 预载通路。于是这些缺陷在所有仿真里都是绿的。
  **新增或修改任何跨 IP 接口（AXIS 握手、DMA、寄存器时序、FIFO 读延迟）时，
  判据必须建在真实接口上**，不能继续用 VIP 内存喂黄金数据糊过去。
  现有的接口级判据：`run_xsim.sh result_axis`（DNA 核 AXIS 出口）、
  `ingress_result`（入口采样）、`dec_restart`（Decoder 寄存器时序）、
  `vot_ddr`（Voter 的 AXI 读/写通路走类 DDR 从机 + 固件寄存器时序，含 3 档故障注入自检）。

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
  故障注入实测见 docs/20 §6「鉴别力实测」；`tools/make_golden.py` 已内置哨兵会红。
  **注意这条实测的适用范围**：它测的是**主机侧黄金模型**
  （`tools/make_golden.py`）——那里几何只喂水印区域展开，Stage1 直接在整条 `ref`
  上滑窗，所以下游整条链路与几何无关。**板上不是这样**：`wm_regions` 预载进
  BRAM 后就是 Stage1 实际比对的对象，几何错了板端结果**应当**会坏。
  也就是说，「板上跑出 `fcd0cf90…f2c3`」仍然是有意义的判据，
  不要据本条去掉它；本条只否掉一件事——**拿黄金向量那条链路上的图片哈希，
  去证明黄金向量用对了几何**。这两者差一个「范围」，正是上一条陷阱说的那种错法。
