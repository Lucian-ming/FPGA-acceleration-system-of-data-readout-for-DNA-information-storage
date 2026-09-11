# 19 · 项目瘦身与代码质量计划

> **建立日期**：2026-09-11（`035401d` 之后）
> **性质**：可执行的清理计划，**不是**优化方向讨论。方向见 [17](17-competition-strategy.md)。
> **执行者**：由主会话 main 统一调度或派发专职子 agent（执行报告见 [slimming-report-2026-09-11.md](reference/slimming-report-2026-09-11.md)）。
> **上位规则**：[AGENTS.md](../AGENTS.md)「代码卫生」八条 + `hw/experimental/README.md` 退休三条。
> 本文只做两件事：**把那些规则落到具体文件上**，并**给每一项配一条会红的判据**。

---

## 0. 为什么现在做，以及这件事的危险在哪

本项目的验证金字塔（黄金向量 → XSim → 四级 DDR 取证 → 图片 SHA-256）
**只对错误答案响应**。仓库里 1.8 GB 磁盘、221 MB 陈年提交包、一份逐字节重复的 XSA、
七个 Xilinx 模板残留 C 文件，**没有一个会让判据变红**。它们不会让项目算错，
只会让接手的人算错——`bench_align.py` 已经让项目付过一次代价
（零引用 → 结论不存在 → `docs/17` 把被它推翻的方向列为第一优先级）。

**但清理本身是这个项目里风险最高的一类操作**，原因只有一条：

> **本项目的核心资产是「制品与源码同源」这条判据**，它由
> `hw/build/export/SHA256SUMS` 与 `tools/run_g3.sh:329` 的校验共同守住。
> **任何改动固件源码的清理，都会让已发布的 ELF 失去同源性**，
> 而 `docs/03-status.md` §P0b 记着这个坑已经踩过一次：
> `928e156` 提交了一份与源码不同源的 ELF，**整文件 SHA 校验对此完全失明**。

因此本计划把所有条目按「是否触碰同源链」分成两类，**两类的判据完全不同**：

| 类别 | 触碰什么 | 清理后必须做什么 |
|---|---|---|
| **冷清理** | 磁盘、未跟踪目录、文档、零引用脚本、非综合 RTL | `tools/check_repo_hygiene.sh` + `tools/check_ip_packaging.sh` + `tools/run_sim.sh` |
| **热清理** | `sw/app/**`、`hw/ip/*/hdl/**`、`clients/python/**` | **必须重新构建 → 重新烧录 → 重跑 G3 → 更新 SHA256SUMS**，缺一项就不许提交 |

**热清理没有 Vivado/Vitis 就不能做。** 没有条件重建时，
**只允许标注不允许删除**——留 `@deprecated` 注释与本文条目号，等有构建窗口再删。

---

## 1. 盘点（2026-09-11 实测）

```text
工作树总体积        1.8 GB
已跟踪文件          463 个 / 36.9 MB     <- 真正的仓库只有这么大
未跟踪占用          ~1.76 GB             <- 97.9% 是构建产物与历史包
```

| 目录 | 磁盘 | 已跟踪 | 说明 |
|---|---:|---:|---|
| `hw/build/` | 1.2 GB | 9.4 MB | `xsim/` 单独占 952 MB；只有 `export/` 21 项入库 |
| `archive/submission_2025-11-07/` | 221 MB | **0** | 2025 年赛季提交包，含 173 MB 演示视频 |
| `sw/workspace/` | 77 MB | **0** | Vitis 工作区，由 `create_vitis.tcl` 生成 |
| `tests/` | 61 MB | 13.1 MB | `stress_results/` 48 MB |
| `data/R0.83_data/` | 54 MB | **0** | D0 真实数据集，**已决策不入库** |
| `logs/` | 34 MB | 0.5 MB | `d3_profile/` 18 MB |
| `docs/` | 21 MB | 8.7 MB | 含 5.5 MB 板卡 PDF/图片 |

**结论：Git 仓库本身（36.9 MB）没有肥胖问题，肥胖全在工作树。**
因此瘦身的第一优先级**不是 `git rm`，而是把不入库的大件移出工作树或明确其生命周期**。

---

## 2. A 部分 · 磁盘与工作树瘦身

每项都给出**依据**与**可回滚性**。凡未标「可删」的，一律先问 main。

### A1 · 逐字节重复的历史 XSA（可删，依据：退休规则第 2 条）

```text
design_2_wrapper.xsa              sha256 79c64736…e6eb33   692 KB  【已跟踪】
hw/build/export/hardware.xsa      sha256 79c64736…e6eb33   692 KB  【已跟踪】
                                  ^^^^^^^^^^^^^^^^^^^^^^ 逐字节相同
```

- 两份**同一文件**，`hw/build/export/README.md` 写明 `hardware.xsa`
  「DDR 配置与本板不符，**禁止使用**」，且**不在 `export/SHA256SUMS` 五项之内**；
- 唯一的历史价值是「`bd.tcl` 的 DDR 参数来自它」这条追溯链，
  该结论已固化在 `hw/build/export/README.md` 与 `docs/reference/repo-structure.md`。

**动作**：`git rm design_2_wrapper.xsa hw/build/export/hardware.xsa`，
在提交说明里写明「依据 AGENTS.md 代码卫生 §5 第 2 条（逐字节重复）+ 第 3 条（已被 `dna_accel.xsa` 取代）」，
并在 `docs/reference/repo-structure.md` 补一行「已于 2026-09-xx 删除，SHA-256 `79c647…e6eb33`，
可由 `git show <commit>^:design_2_wrapper.xsa` 取回」。

> **必须同时做**：`hw/build/export/README.md` 里关于 `hardware.xsa` 的那段要改写成
> 「已删除」，否则留下一条指向不存在文件的说明——**这正是本次要消灭的那类缺陷**。

### A2 · 作废的 BIF（可删，依据：退休规则第 3 条）

`sw/boot/dna_board_20260816.bif` —— `export/README.md` 已写明「同样作废，
现用 `sw/boot/dna_board_b27.bif`」。删除并在 README 对应段落标注。

### A3 · `hw/build/xsim/`（952 MB，不入库，需要生命周期规则）

`m3/` 789 MB + `m2_full/` 91 MB + 二十余个时间戳目录。
这些是 XSim 的一次性产物，**结论已经进了 `docs/` 与 `logs/`**。

**动作**：不要手工 `rm -rf`。给 `tools/run_xsim.sh` / `tools/run_m3_bd.sh` 加一条
**保留窗口**（默认保留最近 3 个时间戳目录，`--keep N` 可调，`--no-prune` 关闭），
删除前把每个目录的 `summary`/`*.log` 归并进 `logs/xsim/`。
**一次性清理与常态化规则必须同时落地**，只做前者三周后原样长回来。

### A4 · `archive/submission_2025-11-07/`（221 MB，未跟踪）

2025 赛季的提交包，含 173 MB 演示视频。**不是本赛季制品**，但有历史价值。

**动作**：**不删**。移出仓库工作树到用户指定的外部位置，
在 `archive/README.md`（新建）里留一行指针记录「移到哪、原 SHA-256、为什么移」。
**移动前必须让用户确认目标路径**——这是唯一一条需要用户拍板的条目。

### A5 · `sw/workspace/`（77 MB，未跟踪，生成物）

`sw/scripts/create_vitis.tcl:144` 是 `importsources -path sw/app`——
**`sw/app/` 是权威源，`sw/workspace/` 是它的生成副本**，当前 37 个文件逐字节相同。

**风险不在体积，在方向**：`tools/switch_export.sh:67` 会把 `sw/app/echo.h`
单向拷进 workspace，说明实践中存在「直接改 workspace」的路径。
**一旦有人改了 workspace 又重跑 `create_vitis.tcl`，改动被无声覆盖。**

**动作**（这是 A 部分里价值最高的一条，因为它不是体积问题而是正确性问题）：

1. 在 `tools/check_repo_hygiene.sh` 增加检查：
   `sw/workspace/dna_lwip_app_b27/src/` 下与 `sw/app/` 同名的文件必须逐字节相同，
   不同则 FAIL 并打印 `diff --stat`；workspace 不存在则跳过（不是所有机器都有 Vitis）；
2. 在 `sw/app/README.txt` 开头写明单向关系与「禁止编辑 workspace」；
3. 不删除 workspace（重建要花 Vitis 时间）。

### A6 · `logs/`、`tests/stress_results/`（82 MB，运行留证）

**这些是证据，AGENTS.md「不得静默删除证据」直接适用，一个都不许删。**
但当前有 **9 个未跟踪目录**（`g6_config_guard_*` 七个、`g6_continuous_*`、`g6_postfault_*`），
其中 `g6_config_guard_*` 的前六个是探针写错的三个版本留下的废轮次
（见 `docs/03-status.md` 与 `g3_config_guard_probe.py` 文件头）。

**动作**：不删，但**收敛**——把六个废轮次归并进
`tests/stress_results/g6_config_guard_20260911T035705Z/superseded/`，
并在该目录写一个 `README.md` 说明「前六轮为探针 v1–v3 的错误结果，
保留是为了佐证 `docs/03-status.md` 记载的三次误判，不得用作判据」。

### A7 · `hw/build/export_4way/`、`export_4way_physopt/`、`impl1_backup_wns_neg252/`（22 MB）

`measured_4way_board.md` §5.4 已写明 `export_4way_physopt/` **不是发布基线**。
三者都未跟踪。

**动作**：`export_4way_physopt/` 保留（G3 已用它跑过，是活证据）；
`export_4way/`（WNS 为负的那版）与 `impl1_backup_wns_neg252/` 归并为一个
`hw/build/attic/20260910-4way-wns-neg/`，附一行 README 说明是时序不收敛的中间版本。

---

## 3. B 部分 · 死代码清除

### B1 · `sw/app/` 的 Xilinx 模板残留（**热清理**，7 个文件 1,292 行）

| 文件 | 行数 | 判据 |
|---|---:|---|
| `platform_mb.c` | 93 | MicroBlaze 平台，本项目是 Zynq-7010 |
| `platform_ppc.c` | 84 | PowerPC 平台 |
| `platform_zynqmp.c` | 199 | ZynqMP（UltraScale+），本项目是 Zynq-7000 |
| `sfp.c` | 192 | SFP 光模块，板上没有 |
| `si5324.c` | 187 | Si5324 时钟芯片，板上没有 |
| `iic_phyreset.c` | 117 | 该板 PHY 复位不走 IIC |
| `i2c_access.c` | 420 | 同上，全库零调用 |

**已核实**：`sw/app/*.c` 中**没有任何一处**引用 `sfp` / `si5324` / `IicPhyReset` / `i2c`；
`platform.c` 用 `#if __MICROBLAZE__ || __PPC__` 把自己的大半内容编译掉，
说明这一整组文件是 lwIP echo 模板原样带进来的。

**这是本计划里单笔收益最大的一项**：1,292 行占 `sw/app/` 全部 6,356 行的 **20.3%**，
接手的人每次通读固件都要先判断这七个文件是不是活的。

**但它是热清理**，必须整套走完：

```text
1. git rm 七个文件（+ 如果 platform_mb/ppc/zynqmp 被 platform.h 声明，一并清理声明）
2. 重跑 sw/scripts/create_vitis.tcl 重建 workspace
3. Vitis 重新编译 -> 新 ELF
4. 重新生成 BOOT.bin（sw/boot/dna_board_b27.bif）
5. 烧录 -> tools/run_g3.sh 完整跑一轮，判据：图片 SHA-256 = fcd0cf90…f2c3
6. 更新 hw/build/export/SHA256SUMS 与 export/README.md
7. 同一个 commit 里同时包含「源码删除」与「新制品」，不得分两次提交
```

**第 7 条是硬要求**：`928e156` 的教训就是源码与制品分两次提交，
中间那个 commit 的仓库状态「源码是新的、制品是旧的」，
而整文件 SHA 校验对此**完全失明**。

> **没有 Vitis 构建窗口时**：只在七个文件头部加
> `/* @deprecated 计划删除，见 docs/19 §B1。零引用已核实（2026-09-11）。*/`，
> **不要删**。带着一份不同源的 ELF 比带着 1,292 行死代码危险得多。

### B2 · `hw/experimental/`（**冷清理**，13 个文件）

`hw/experimental/README.md` 自己写了「每次卫生审计都应当清一次」。本次逐项判：

| 文件 | 退休规则 | 处置 |
|---|---|---|
| `srpe_batch_8way_wip.v` | **第 1 条成立**：方向已被资源证伪，结论在 `docs/17` §2.1，且 `measured_4way_board.md` §4 又补了「即使放得下端到端上限也只有 1.35x」 | **可删** |
| `srpe_batch_1way_baseline.v` | 第 3 条成立：被 `srpe_batch.v`(2-way) / `srpe_batch_4way.v` 取代，后者受 `run_sim.sh` 覆盖 | **可删** |
| `srpe.v` / `fifo.v` / `fifo_sync_sdpram.v` | 第 3 条成立：被 `_b64` 版取代 | **可删** |
| `local_correlator.v` | 零引用，但**不满足任何一条**——没有实测证伪它，也没有文件取代它 | **保留**，在 README 里补一行「保留原因：不满足退休三条中任何一条」 |
| `unused_axi_wrappers/`（7 个） | 第 3 条成立：AXI 逻辑已内联进各 IP 顶层；`five_to_four_decoder.v` 更是 AGENTS.md 白纸黑字的死文件 | **可删** |

> ### ⚠️ 删之前先看 `tools/run_sim.sh`——本条是 2026-09-11 回归实跑发现的
>
> `tools/run_sim.sh:207` 有一行：
>
> ```bash
> check five_to_four_decoder_dead "hw/experimental/unused_axi_wrappers/five_to_four_decoder.v"
> ```
>
> **`hw/experimental/` 下的文件不是全都没人引用**——这一个被回归的语法检查带着跑。
> 直接 `git rm` 它会让 `run_sim.sh` 立刻失败。正确顺序是**先删 `run_sim.sh` 里那一行，
> 再删文件，然后重跑回归**，两个改动放同一个提交。
>
> 更一般的规则：**删 `hw/experimental/` 下任何文件之前，先 `grep -n "<文件名>" tools/run_sim.sh
> tools/run_xsim.sh tools/run_m2_full.sh tools/run_m3_bd.sh hw/ip/*/component.xml`。**
> 本项目已经因为「移了 6 个 TB 却没重跑回归」把 `run_sim.sh` 弄坏过一次。

**删除必须在 commit message 里逐个写明依据第几条**（AGENTS.md §5 明文要求）。
删完把 `hw/experimental/README.md` 的「当前内容」表改写成实际剩余项——
**表与目录不一致本身就是一个新的卫生缺陷**。

### B3 · 零引用工具（**冷清理**，需要逐个判，不是一律删）

`bench_align.py` 的教训说明「零引用 ≠ 该删」，正确处置是**让它可被发现**。
扫描结果（除自身与 `tools/README.md` 外的提及次数）：

| 脚本 | 提及 | 判断 |
|---|---:|---|
| `tools/board/g3_runs_to_jsonl.py` | 0 | 264 行，G3 运行结果转 JSONL。**不删**，在 `docs/18-evidence-ledger.md` 的复现命令里接上，或并入 `run_g3.sh` |
| `tools/profile_host.py` | 0 | 608 行，**它产出的正是 `measured_timing_accountability.md` §4 那张上位机资源表**。零引用纯属失误——**必须在该报告里补上复现命令** |
| `tools/voter_page_split.py` | 1 | 109 行，查清是否仍被 `run_m2_full.sh` 链路使用；否则移 `tools/attic/` |
| `tools/debug_vote_diff.py`、`debug_high_entropy.py` | 2 | 调试脚本，结论已进文档。移 `tools/attic/` 并在 README 标注 |

**规则**：`tools/` 下一律**不 `git rm`**，只在「已确认其结论已被文档吸收」后
`git mv` 到 `tools/attic/`，并在 `tools/README.md` 单列一节。
`check_repo_hygiene.sh` 的登记检查要同时覆盖 `tools/attic/`。

### B4 · `clients/python/first.py`（**热清理**，758 行）

被 77 处提及，其中多数是文档与历史日志。需要查清它与
`fast_readout.py`(260) / `task_protocol.py`(214) 的职责重叠——
`fast_readout.py` 自己就 import 了 `first`。

**动作**：**本轮只做调查，不改代码**。产出一份
`docs/reference/client-module-map.md`，画清四个模块（`first` / `fast_readout` /
`protocol` / `task_protocol`）的调用方向与各自唯一职责，
标出重复实现的函数。**改造留到下一轮**——上位机现在是唯一能跑通全链路的入口，
在没有独立回归的情况下重构它，风险远大于收益（`clients/python/tests/test_client_core.py`
是目前唯一的客户端测试）。

---

## 4. C 部分 · 注释与可读性

### C0 · 先说清楚标准，不然会得到一堆噪声

本项目的注释**已经是资产**，不是负担——`stage1_dna.c` 的 `PIPE_WM_TX` 分支里那句注释
让我在 P0 修复时少烧一整轮板子；`echo.c` 里记着 v1 失败数字的那段注释
直接防止了同一个错误被重犯；`g3_config_guard_probe.py` 的文件头保存了
三个错误版本作为反例。**这个项目的注释风格是「记录为什么与踩过的坑」，
不是「说明这行在做什么」。**

因此 C 部分的标准是：

| 要加 | 不要加 |
|---|---|
| 这个常量为什么是这个值、谁定的、改了会撞到什么 | `i++; // i 加一` |
| 这段代码修的是哪个编号的缺陷，失败时的现象是什么 | 把函数名翻译成中文 |
| 「这里看起来可以优化，试过 N 次失败，原因是……」 | 无依据的「TODO 优化」 |
| 跨文件的隐式契约（谁先于谁执行、谁持有什么锁） | 重复类型声明已表达的信息 |

**任何一条新注释都必须是可核验的事实。**
写不出依据的就不要写——本项目已经因为「推算被当成实测」（0.470 ms / 81%）
付过一次代价，注释里塞进一个想当然的数字是同一类事故。

### C1 · 优先补注释的文件（按「接手者最先读到 + 当前注释密度最低」排序）

1. `sw/app/main.c`(304)、`platform.c`(190) —— 启动顺序与 lwIP 初始化契约；
2. `sw/app/stage2_voter.c`(458) —— 投票语义与 `score_min` 的作用点，
   G6 的「弄脏轮」鉴别力就建立在这里的累加器行为上；
3. `hw/ip/Dna_accelerator_core_1_0/hdl/srpe_batch_4way.v` ——
   **这是打包进比特流的那份实现**，必须在文件头写明它与 `srpe_batch.v`(2-way) 的
   关系、`PACKAGED_VARIANTS.txt` 的约束，以及「改这个文件必须重跑
   `check_ip_packaging.sh`」；
4. `clients/python/gui_app.py`(954) —— 最长的单文件，且是演示入口。

### C2 · 禁止的「可读性改造」

- **禁止对已通过判据的 RTL 做纯格式化重排**。RTL 的任何改动都要重新综合与实现，
  而实现结果有随机性（4-way 的 WNS 从 -0.252 ns 到 +0.246 ns 花了一轮定位）。
  **注释可以加，代码排版不要动。**
- **禁止在本轮引入新抽象**（提取基类、拆分模块、改目录结构）。
  本计划的目标是「删掉不用的 + 说清在用的」，**不是重构**。
- **禁止批量替换命名**。`sw/app` 与 `hw/ip` 的命名跨越了 RTL/固件/文档/日志四层，
  改一个名字会让所有历史日志失去可搜索性。

---

## 5. 红线

1. **`logs/`、`tests/stress_results/`、`tests/datasets/`、`data/` 下一个字节都不许删。**
   归并、加 README、加 `superseded/` 子目录可以，删除不行。
2. **`data/R0.83_data/` 不进仓库**（用户已决策），也不许因为"瘦身"把它移走——
   它是 D0 的唯一本地副本。
3. **不许为了让判据变绿而修改判据。** 发现 `check_*.sh` 报了新问题，
   要么修问题，要么在文档里写明为什么这一条不适用，**不许放宽检查**。
4. **不许一次提交跨越冷/热两类。** 冷清理与热清理分开提交，
   热清理的源码与制品必须在同一个提交里。
5. **不许 `git add -A`。** 每次 `git commit -m "..." -- <显式路径>`。
6. **删除任何文件前先 `grep -rIn` 全库确认引用**，并把命令与结果贴进提交说明或 PR 描述。

---

## 6. 执行顺序与每批的出口判据

| 批次 | 内容 | 出口判据 |
|---|---|---|
| **S-1 冷** | A1、A2、B2（RTL 退休）、A7（归并） | `run_sim.sh` **16 项全绿**（含两个 check 脚本）；`check_ip_packaging.sh` 14 条断言全绿。基线：2026-09-11 实跑 16/16、7/7、14/14 |
| **S-2 冷** | A5（workspace 一致性检查）、A6（废轮次归并）、B3（工具收敛） | `check_repo_hygiene.sh` 由 7 项扩到 9 项后 PASS |
| **S-3 冷** | A3（xsim 保留窗口）、A4（旧提交包外移，**需用户确认路径**） | `du -sh .` 降到 ≤ 600 MB；`run_xsim.sh --keep 3` 实跑一次验证不误删 |
| **S-4 冷** | C1 注释（仅 `.c`/`.py`，不含 RTL）、B4 调查报告 | `run_sim.sh` 全绿；新增 `docs/reference/client-module-map.md` |
| **S-5 热** | B1（七个模板文件）+ C1 第 3 项（RTL 文件头注释） | **重建 → 烧录 → G3 PASS（SHA `fcd0cf90…f2c3`）→ SHA256SUMS 更新**，单次提交 |

**S-1 到 S-4 可以在没有板子、没有 Vivado 的情况下全部完成。**
**S-5 必须等一个完整的构建 + 板卡窗口**，不得拆开做一半。

---

## 7. 本计划要新增的可执行判据（AGENTS.md 代码卫生 §1）

只写进文档的约定等于没有。

### 7.1 第 7 条已由 main 落地，当作模板照抄

写这份计划时顺手核对了文档里引用的每个路径与行号，结果发现：

- `sw/app/echo.c` 的注释里写着 `stage1_dna.c:178`，而那一行在 WM 批量化补进注释后
  **早已不是被引用的内容**（真正的位置是 `PIPE_WM_TX` 分支）。
  这条错误引用**从源码注释扩散进了 5 份文档，全程没有任何判据变红**；
- `docs/05-interfaces.md` 指着 `echo.c:465-495`，那段代码早就拆到 `stage1_dna.c`，
  而 `echo.c` 现在只有 740 行；
- `docs/benchmarks/stage1-candidate-audit.md` 有 4 处指向已被删除的 `srpe_batch_2way.v`。

全部已修，并落成 `check_repo_hygiene.sh` 的**第 7 项**（2026-09-11，已验鉴别力：
注入越界与悬空引用各一条，两条都能被抓出并给出出处文件，退出码 1）。

**这一条同时说明了这类检查的边界，写检查之前先想清楚**：

| 能查 | 查不了 |
|---|---|
| 文件不存在（悬空） | **文件还在、行号也在范围内，但内容已经挪走** |
| 行号超出文件总行数（越界） | ——`:178` 那个就是这种，检查抓不到 |

**写这类检查会遇到的一个坑（我当场踩了）**：文档里作为**反面示例**写的
「文件名 + 冒号 + 行号」会被当成真引用抓出来。不要为此给检查加豁免机制——
**改文案比加豁免便宜**，而豁免机制一旦存在就会被滥用来绕过检查。
另外：**改完文档要重跑检查再提交**，我就是漏了这一步才提交出一次 FAIL 状态。

所以判据之外还要有纪律：**现行文档与新写的注释一律按标识符引用**
（函数名 / 状态名 / 模块名），不要写行号。
**过期的引用比没有引用更糟**——它会把人导向错误的位置，还显得言之凿凿。
`docs/archive/` 整个排除在检查外：归档文档引用的是写作当时的行号，那是正确的历史记录。

### 7.2 以下四条由清理 agent 补齐

```text
8  sw/app/ 与 sw/workspace/.../src/ 同名文件必须逐字节相同（workspace 不存在则跳过）
9  tools/attic/ 下的脚本也必须登记进 tools/README.md
10 hw/experimental/README.md 的「当前内容」表必须与目录实际文件一一对应
11 仓库内不得存在两份 SHA-256 相同的已跟踪文件（A1 那类重复的通用判据）
```

第 11 条是本次最值得沉淀的一条：**它能自动发现所有 A1 类缺陷**，
而 A1 这种缺陷靠人读目录发现不了——两份文件相隔两级目录，名字还不一样。

---

## 8. 完成判据

1. `du -sh .` ≤ 600 MB（当前 1.8 GB），且减少量逐项对得上本文条目；
2. `tools/run_sim.sh` 全绿（基线 16/16），卫生检查**从 7 项扩到 11 项**且全 PASS；
3. `sw/app/` 行数从 6,356 降到 ~5,064（−20.3%），且**同一提交内**制品已更新、G3 已 PASS；
4. `hw/experimental/` 只剩 `local_correlator.v` + README，且 README 表与目录一致；
5. `tools/README.md` 覆盖 `tools/` 与 `tools/attic/` 全部脚本，零引用脚本要么被文档接上、
   要么进 attic；
6. 本文每一条 A/B/C 编号都能在某个 commit message 里被搜到——
   **没有对应提交的条目视为未执行**，不许在完成报告里含糊带过。

---

## 9. 附录 · 未跟踪项基线（2026-09-11，`269388d` 之后）

提示词要求清理 agent「事后能解释每一个未跟踪项」。这里给出真值，
**不在本表里的新增未跟踪项，都要么是你产生的、要么是别人动了仓库**，两种都要查清。

| 未跟踪路径 | 体积 | 为什么在这里 | 处置 |
|---|---:|---|---|
| `hw/build/export_4way_physopt/` | 3.2 M | 4-way 的 WNS +0.246 ns 收敛版，G3 实际用它跑过 | **保留**（活证据） |
| `hw/build/export_4way/` | 3.2 M | 4-way 时序不收敛的中间版本 | A7：并入 `hw/build/attic/` |
| `hw/build/impl1_backup_wns_neg252/` | 16 M | WNS −0.252 ns 的实现备份 | A7：并入 `hw/build/attic/` |
| `logs/multi_payload/repeat3_*/dumps/` | 1.4 M | 21 次重复实验的板端 dump | **保留**，是 G4 的留证 |
| `logs/vivado/recovery_20260909/failing_*.{tsv,rpt}` | 2.4 M | 时序定位的失败端点清单 | **保留**，是 §P6 的留证 |
| `tests/stress_results/g6_config_guard_2026091?T03{4221,4311,4405,4454,4525,4644}Z/` | 6 × 8 K | **探针 v1–v3 的错误轮次**（见 `g3_config_guard_probe.py` 文件头记录的三次误判） | A6：并入 `…035705Z/superseded/` 并写 README |
| `tests/stress_results/g6_config_guard_*035705Z/` | 8 K | v4 的正确结果（7/7） | **保留** |
| `tests/stress_results/g6_continuous_*/`、`g6_postfault_*/` | 60 K + 168 K | G6 连续任务与注入后判据轮 | **保留**，是 G6 的留证 |
| `logs/g5_matrix/` | 27 M | G5 误接受率矩阵：`summary.tsv` 与每点 JSON 是结论，`mut_*/` 是可由 seed 复现的加噪输入 | **保留**；`mut_*/` 可按 A3 的保留窗口规则回收 |
| `sw/workspace/` | 77 M | Vitis 工作区，`create_vitis.tcl` 的生成物 | A5：加一致性检查，**不删** |
| `archive/submission_2025-11-07/` | 221 M | 2025 赛季提交包 | A4：**等用户给路径**后移出工作树 |
| `data/R0.83_data/` | 54 M | D0 真实数据集 | **不入库、不移动**（用户已决策） |
| `hw/build/{xsim,dna_accel.*}/` | ~1.1 G | Vivado / XSim 生成物 | A3：给保留窗口，不手工 `rm -rf` |

> 核对命令：`git status --porcelain | grep '^??'`
> 体积：`git status --porcelain | grep '^??' | sed 's/^?? //' | xargs -I{} du -sh {}`
