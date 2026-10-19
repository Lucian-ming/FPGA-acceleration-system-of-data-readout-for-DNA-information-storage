# 项目清理瘦身清单与执行记录（2026-10-16）

用户要求「给项目清理瘦身、减少历史包袱」——换了板子之后旧板信息与演示视频不该留在项目里，
过时的脚本工具该清就清。

**本文只出清单，不执行任何删除。**

## 0. 先看前提：本项目已经做过一轮系统清理，且立了规矩

`docs/reference/slimming-report-2026-09-11.md`（P9「slim」专项）已把工作树从 **1.8 GB 降到 807 MB**，
并留下了**机制**而不是一次性动作：

| 它留下的东西 | 现状 |
| --- | --- |
| 冷批次流程（S-1~S-4 + 热清理），门禁是「**不破坏同源性制品链**」 | 沿用 |
| `tools/check_repo_hygiene.sh` 扩到 11 项、`check_ip_packaging.sh` 14 项 | 今天仍全绿 |
| `tools/prune_xsim.sh`（XSim 历史生成物常态化修剪，保留最近 3 轮、日志归档） | `logs/xsim` 现仅 **27 MB** |
| `hw/experimental/` 收敛 + 门禁第 10 项**永久守护**它「README 内容表与目录 1:1」 | 见下 |
| `tools/attic/` + 门禁第 9 项守护「attic 下脚本必须在 `tools/README.md` 登记」 | 沿用 |

**⇒ 所以"过时的脚本工具"这件事基本已经做完了**：本次清点时 `tools/attic/` 下只有 `__pycache__`；
`hw/experimental/` 里都是**在用的**实验件（`srpe_batch_pway.v` 是 K 写死前的原件、
`srpe_batch_pway_dbuf_proto.v` 是今天的双缓冲原型、`tb_ldpc_decoder_p1.v` 是仿真台）。

**真正的缺口是两处体量**：`hw/build/*/build/` 与 `logs/iverilog`。下面只讲这两处 + 你点名的演示视频。

## 1. 硬约束：有些东西**明文不许删**

| 对象 | 依据 |
| --- | --- |
| `data/`、**`archive/`**、两份 XSA | `AGENTS.md`：「**不删除历史数据或构建产物**（`data/`、`archive/`、两份 XSA 只读）」 |
| `archive/` | `README.md`：「原始数据和历史提交资产，**只读保护**」 |
| `archive/submission_2025-11-07/`（228 MB） | P9 报告已记：「按用户指令与红线要求，**不删也不自行移动**，原地保留待用户拍板目标路径」 |
| `hw/experimental/` | 两个门禁依赖（冻结 SHA 契约 + 目录内容表 1:1 检查） |
| `hw/build/*/export/` | **发布制品本身**，板测与 G3 留证指向它。**动它等于毁证** |

⇒ **`archive/` 不列入可删项。** 它要动，得先改 `AGENTS.md` 与 `README.md` 里的只读声明，
那是另一个决定。

## 2. 建议清理项（未跟踪、可重建、无引用、非证据 —— 四项全满足）

| # | 对象 | 数量 | 体积 | 可重建依据 | 引用 |
| --- | --- | ---: | ---: | --- | --- |
| 1 | `hw/build/*/build/` | 18 个 | **4.98 G** | Vivado 工程目录；`hw/scripts/build.tcl` + `tools/run_vivado_build.sh` 从源码重建 | **无**（已 grep：`run_g3.sh`、`tools/board/*.py`、回归工具只读 `export/`） |
| 2 | `hw/build/*/workspace/*_platform/` | 30 个 | **~1.43 G** | Vitis platform/BSP，由 XSA 重建 | 无 |
| 3 | `logs/iverilog/*/` 下的仿真器可执行文件 | **83 个** | **432 M** | `iverilog` 编译产物 | 无（留证是 `.log`/`.txt`/`.hex`，另计约 12 M） |
| 4 | `（旧板 ZYNQ ECO 7010 资料，2026-10-16 已归档移出仓库）03_examples/tutorials/ECO_蜂鸣器上板演示.mp4` | 1 | **12.0 M** | 厂商教程视频 | 无（**你点名的那个演示视频**；本来就没被 git 跟踪） |
| 5 | `tools/attic/__pycache__/` | — | 40 K | Python 缓存 | 无 |

**小计 ≈ 6.85 GB。** 工作区从 **9.0 G → 约 2.1 G**。

### ⚠️ 同一批目录里**必须原地保留**的（防止误删）

- `hw/build/*/export/` —— 45 个目录、**186 个 `.bit`/`.elf`/`.bin`/`.xsa`**、0.40 G，**发布制品**；
- `hw/build/*/reports/` —— 47 个目录，`timing.rpt`/`util.rpt`/`summary.log`，**WNS/WHS 与 LUT 数字的证据源**；
- **`hw/build/*/workspace/dna_lwip_app/`** —— 每包 3.2 MB，**该包当初编译用的源码拷贝**；
  「发布包源码 == HEAD」这类出处核对靠的就是它。**只删 `*_platform/`，不删 `dna_lwip_app/`。**
- 各包的 `manifest.json` / `artifact_manifest.json` / `SHA256SUMS` —— 制品身份。

## 3. 建议：把第 3 项做成**工具**，而不是手写 `rm`

`logs/iverilog` 涨到 444 MB，根因是**项目改用 iverilog 做仿真后，没有对应的修剪工具**——
XSim 那条路有 `tools/prune_xsim.sh`（保留最近 N 轮、日志自动归集归档），iverilog 这条路是空的。

⇒ **建议照 `prune_xsim.sh` 的样子补一个 `tools/prune_iverilog.sh`**：默认保留最近 3 轮、
删除前把 `.log`/`.txt`/`.hex` 归集到 `logs/iverilog/archive/`。
**这与项目既有机制一致，也比一次性 `rm` 更耐久**——今天删了，下个月还会涨回来。

## 4. 明确**不建议**现在做的事

| 事项 | 为什么 |
| --- | --- |
| 删 `（旧板 ZYNQ ECO 7010 资料，2026-10-16 已归档移出仓库）`（旧板资料 20 MB） | 被 **17 个文件**引用，其中 `hw/boards/zynq_eco_7010.tcl`、`hw/scripts/bd.tcl`、`tools/board/g3_artifacts.py` 是**工具与板级 profile**，不是文档。删它要同步改 17 处，改错会直接影响 `run_g3.sh` 能否运行。**20 MB 换这个风险不值得。** 而且 `migration-source-table.md` 的价值正是"记录从哪块板迁过来的"——把旧板资料删干净会让那张表失去可核对的对象 |
| 删 `archive/`（228 MB） | 明文只读保护（见 §1） |
| 删 `hw/experimental/` | 门禁依赖，且里面的文件都在用 |
| 删 `docs/archive/` | 被 58 处引用 |

**关于"减少历史包袱"的目标**：如果指的是**交付物看起来干净**，那 §2 的四项**已经在 git 之外**
——它们本来就不进交付物。如果指的是**磁盘**，§2 省 6.85 GB。

## 5. 真要执行时的前置条件

1. **确认没有正在跑的构建/仿真**占用这些目录（当前板子空闲、无 Vivado 进程）；
2. 第 1、2 项**按目录名精确匹配**删除，**不要用宽泛通配**——
   `hw/build/` 里混着 `export/`、`reports/`、`dna_lwip_app/` 这些**不能碰**的东西：
   ```bash
   find hw/build -mindepth 2 -maxdepth 2 -type d -name build -prune -exec rm -rf {} +
   find hw/build -mindepth 3 -maxdepth 3 -type d -name '*_platform' -prune -exec rm -rf {} +
   ```

3. 删完**立刻跑两个门禁**确认没打中依赖；
4. 第 3 项**先写工具再跑**，不要手删；
5. 删完核对 `run_g3.sh --plan-only` 仍能选中制品（它依赖 `export/` 而不是 `build/`）。

## 6. 本文没做的事

- **没有删除任何文件**；
- 「可重建」是**依据"脚本与输入数据在库"判断的，没有实际跑一遍重建验证**；
- 没有评估 `logs/` 下其它子目录（`g5_matrix` 27 M、`d3_profile` 18 M、`vivado` 25 M 等）——
  它们都不是本次的体量大头。


---

# 执行记录（2026-10-16，用户批准后执行）

用户指示：「可清理的删掉；历史的发布制品也可以删掉；现在作为 1.0 正式版本发布；
旧版资料也能删；iverilog 做成工具或只保留 xsim」。

## 先备份（可逆性来自这里，不是来自"我小心"）

备份根：`D:\bkb220_cleanup_backup_20261016T104516Z\`（**655 MB**）

> ⚠️ **2026-10-19 更新**：该备份目录已按用户要求**删除**（用户确认这些历史备份不再需要）。
> 下表记录的是当时的备份与校验结论，**对应目录已不存在**。

| 子目录 | 内容 | 校验 |
| --- | --- | --- |
| `artifacts/` | **45 个历史包的 `export/`**（408 MB） | **296 个文件逐字节一致** |
| `board-docs/` | 旧板资料（20 MB，17 个文件） | README 逐字节一致 |
| `archive/` | 2025 年那份提交（228 MB，19 个文件） | 文件数一致 |

**只备份不可重建的东西**——可重建的 `build/`、`*_platform/`、仿真器二进制不占备份空间。

## 已执行

| 动作 | 结果 |
| --- | --- |
| 删 `hw/build/*/build/` + `workspace/*_platform/` + `logs/iverilog` 编译产物 + 演示视频 + `attic/__pycache__` | 释放 **6.80 GB**（8.71 G → 1.92 G） |
| 删 70 个历史制品包 + 可重建的 `dna_accel.{runs,gen,cache}` | `hw/build` 1.2 G → 421 M |
| `prune_xsim.sh --keep 3` | 311 M 未变（已在保留上限内） |
| 删旧板资料目录 `docs/board/zynq-eco-7010/` | 16 个跟踪文件、20 MB；**10 处活引用已同步修正** |
| 补 `.gitignore` 规则 `hw/build/bkb220-v*-*/` | v1.0 包此前未被忽略，会误提交 68 MB |
| 新建 v1.0 定版包并板端验证 | 见 [release-v1.0.md](release-v1.0.md) |
| 新建 `tools/prune_iverilog.sh` 并登记 | 门禁要求 `tools/*.sh` 必须登记，已补 |

**最终：工作区 8.71 G → 1.3 G。**

## ⚠️ 执行中弄坏又修好的一件事（必须记下来）

删 `workspace/*_platform/` 时**我误判了它的作用**：以为它只是"可由 XSA 重建的 BSP"，
**但它被制品的 `SHA256SUMS` 引用（2956 条 `workspace/` 条目）**，而 `g3_artifacts.py`
会逐条校验 ⇒ **29 个软件包当场全部过不了 `--strict-artifacts`**。

> **教训：说"可重建"之前，必须查它有没有被完整性清单/门禁引用。**
> 我当时的判据是"没有工具读 `build/`"——那只查了 `/build/`，**没查 `/workspace/`**。

**处置**：由于用户本就要删历史制品、只留一个，**改为重建唯一要留的那个**——
正是 v1.0 定版包（完整、自洽：`sha256sum -c` 2977 条全 OK、`g3_artifacts --strict-artifacts` PASS）。
坏掉的 29 个历史包随之删除，问题自然消解。
**v1.0 的 `workspace/` 完整保留**，不受影响。

## 明确**没有**做的事

- **`data/` 未动**——它是仍在用的构建输入（D0 的水印就来自 `data/R0.83_data/`），
  虽然旧板已换掉，但这份数据与新板无关、且仍被引用；
- **`archive/` 未删**（228 MB）——已备份，等用户明确；它受 `AGENTS.md` 与 `README.md` 只读保护，
  且 P9 报告记着"按用户指令与红线要求不删也不自行移动"；
- **旧板 profile 与构建系统分支未动（原记录已被后续提交 `ffc4b5d` 取代）**——原执行记录曾称 `hw/boards/zynq_eco_7010.tcl`、`hw/scripts/build.tcl` 中的 `zynq_eco_7010` 分支是 legacy 默认路径，并记载当时 dry-run 的两块板配置检查均为 `BUILD_CONFIG_PASS`；这些内容仅反映原记录写成时的状态。`ffc4b5d` 后，`hw/scripts/build.tcl` 默认 `board=bkb220`，`hw/boards/load_board.tcl` 按显式 board ID 加载现存 profile，旧板不再是构建默认值；
- **`docs/archive/history/**` 里指向旧板资料的引用未改**——那是历史快照，当时的路径就是那样；
- **`docs/submission/llm-collaboration/**` 一律未动**——逐字证据。
