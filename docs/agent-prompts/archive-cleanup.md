# 归档整理任务（交给接手 agent 的完整提示词）

> 比赛已全部结束。本任务把散落在 Windows D 盘与桌面的项目材料收进 WSL 仓库，
> 去重、清理、重排目录、全面更新文档，然后冻结、打 tag、提交并推送。
> 你是本任务期间**唯一的 Git 写入者**；原主会话已停止写入。

## 0. 身份、工作目录与必读规则

- **工作目录（唯一的 checkout）**：`/home/lucian/projects/FPGA/FpgaAccelerationSystemOfDataReadout`
  - `.git` 是一个文件，指向同目录下的 `.git-data/`。不要动它，也不要 `git init` 或重新 clone。
  - 远端只有 `origin` =
    `https://github.com/Lucian-ming/FPGA-acceleration-system-of-data-readout-for-DNA-information-storage.git`，
    分支只用 `main`。
  - **该仓库目前是 PUBLIC**（`gh repo view` 实测）。推上去的东西任何人都看得到，隐私规则见 §5。
- **Windows 盘在 WSL 里的路径**：D 盘是 `/mnt/d/`，桌面是 `/mnt/e/桌面/`。
- **动手前先完整读两份文件**：仓库根目录的 `AGENTS.md`（开发规范、Git 门禁、常见陷阱）和
  `CLAUDE.md`（看板、子 Agent、提交规则）。两者与本提示词冲突时，以本提示词为准；
  本提示词没写到的，按这两份执行。
- **看板**：你的看板名固定为 `archive-cleanup`。
  - 动手前先 `tools/agent_view.sh start --agent archive-cleanup --doing ... --why ... --next ...`；
  - 换阶段时 `update`，等用户回答时 `block`（把问题写进 `--next`），收工 `done`；
  - 禁止手工编辑 `view.md`。
- **开工核验**：在仓库根目录跑
  - `bash tools/verify_repo_binding.sh --remote`，
  - `git status --short`，
  - `tools/agent_view.sh show`。

  看板上若有别的 agent 在跑，先停下问用户。
- **工作树里已有 4 个未提交改动，都是原主会话的正当改动**，审阅 diff 后作为你的第一个提交：
  - `tools/agent_view.sh` 与 `docs/submission/skill/ai-agent-collaboration/agent_view.sh`：`show` 改成纯读、不建目录；
  - `docs/submission/skill/fpga-timing-probe/readme.md`；
  - `docs/submission/submission-todo-2026-10-20.md`。
- **需要派子 Agent 时**：
  - 按 `CLAUDE.md` 走 `codex-luna` MCP，不用 Agent 工具；
  - 子 Agent 不做任何 Git 写操作，也不跑 `verify_repo_binding.sh`；
  - 单个子任务必须能在 60 分钟内完成；
  - 对 `/mnt/d`、`/mnt/e` 的复制与删除由你亲自做，不派出去。

## 1. 必须知道的事实（已核实，2026-11-02）

### 1.1 最终提交包

- **位置**：`/mnt/d/dna-readout-accelerator/`（约 240 MB，约 1251 个文件）。
- **它是权威最终版**：在这棵树上用 Vivado/Vitis 2026.1 从零重建，过程见包内 `build/reports/2026.1-rebuild.md`。
- **目录布局**：`src/` 是工作树根，`sim/ build/ board/ data/ report/ skill/` 在包根，另有根目录的 `readme.md` 与 `license`。
- **压缩包**：`/mnt/d/dna-readout-accelerator.rar`，RAR5，61,938,975 B，
  SHA-256 `ba315d4f22bdfeba1a61d219fde4e3aaf208876235b3246e8945ef852da17dbf`，顶层目录为 `dna-readout-accelerator\`。
- **硬件身份与实现数字**：
  - `FW_BUILD_ID=bfcd40dd3c435a19`；
  - LUT 36,731，FF 38,437，RAMB36 89 / RAMB18 2，DSP 6；
  - WNS +0.089 ns，WHS +0.030 ns，频率 100 MHz，器件 xc7z020clg400-2。

### 1.2 仓库源码落后于提交包

不要拿仓库覆盖提交包，方向相反。已知差异：

- IP 目录改名：`hw/ip/Dna_accelerator_core_1_0` 改成 `dna_accelerator_core_1_0`，VLNV 也小写了。
- HDL 文件改名：`*_v1_0.v` 改成 `*.v`，各 IP 的 `component.xml` 同步修改。
- `PACKAGED_VARIANTS.txt` 改成 `packaged_variants.txt`。
- `sw/app` 下新增 `xilinx.spec`，`README.txt` 改成 `readme.txt`，另有若干注释改动。
- 测试目录：仓库是 `tests/`，包内是 `sim/`。
- 重建时修掉的 6 处脚本路径问题，见 `2026.1-rebuild.md` §7。
- 文件数对比（仓库 → 包内）：
  - hw：65 → 34
  - sw：54 → 50
  - clients：24 → 21
  - tools：73 → 39
  - tests：207 → sim 163

  多出来的是开发期脚本与实验。

### 1.3 报告与海报

- **报告**：
  - 权威可编辑稿是 `/mnt/d/submitwork/report/design-report-2026.docx`（11-02 19:16，含用户手改的参考文献）；
  - 权威 PDF 是包内 `report/design-report-2026.pdf`（11-02 19:16）；
  - `submitwork/report/design-report-2026.{md,pdf}` 停在 18:33/18:34，不含用户在 Word 里的手改，属于**过期稿**。
- **海报**：
  - 可编辑稿是 `/mnt/d/submitwork/poster/dna-readout-poster-2026.pptx`（11-02 19:03）；
  - 包内 PDF 是 18:34 导出的，比 pptx 早，需要核对两者是否一致，只记录、不重导；
  - `dna-readout-poster-2026-final.pptx`（10-30）是过期稿。

### 1.4 演示视频与客户端

- **最终演示视频**：`/mnt/d/submitwork/video/提交视频/提交视频.mp4`（105 MB），封面 `提交视频-封面.jpg`。
  - 超过 GitHub 100 MB 单文件上限，**不能进 Git**。
  - 包内 `readme.md` §5 写的「4 分 09 秒」可能已经过期。用 Windows 侧 ffprobe 或任意可用工具实测时长后，写进仓库文档；不改包内 readme。
- **上位机 `gui_app.exe`**：以下三处 SHA-256 相同，前缀都是 `5624f589ca2a24f9`，只需留一份：
  - 包内 `src/clients/python/gui_app.exe`；
  - `submitwork/client-build/dist/`；
  - `E:\桌面\演示\`。

### 1.5 仓库本地状态

- **被忽略的大目录**（只在本地，不在 Git 里）：

  | 目录 | 大小 |
  | --- | --- |
  | `archive/` | 2.2 G |
  | `hw/build/` | 863 M（其中 xsim 304 M） |
  | `dna-readout-video/build/` | 919 M |
  | `data/test-sets/` | 717 M |
  | `logs/` | 184 M（只有 25 个小文件入库） |
  | `.Xil/` | 142 M |
  | `data/R0.83_data/` | 54 M |
  | `sw/workspace/` | 50 M |

- **`archive/` 里有什么**：
  - `submission_2025-11-07/`（221 M）是 **2025 年那次比赛的提交记录**，含承诺书、旧视频、旧海报；
  - `board-evidence-2026-10/`（2.0 G）是板端原始留证；
  - 另有 `old-video-pipeline-2026-10-27/` 和 `R0.83_data_source.rar`。
- **Git 历史**：468 个提交，`.git-data` 共 84 MB。仓库里有 139 条路径含大写或非 ASCII 字符。

## 2. 名词约定：「收进项目」分两种去处

- **入库（Git）**：会推到 PUBLIC 远端。只放源码、脚本、文档、小体积且可公开的成品
  （单文件 ≤ 10 MB，例外须在计划里逐个列出）。
- **本地归档（不入 Git）**：`archive/`，已被 `.gitignore` 忽略。放大文件、原始留证、
  不宜公开的材料，以及提交物原件。用户之后整体打包归档的就是这整个文件夹，
  所以本地归档同样要整洁，并配一份 `archive/readme.md` 加 `archive/SHA256SUMS`。

「用户说的删除之前的提交记录、换成最新的」按以下理解执行：

- **要做**：清掉旧的提交材料（2025 年那次比赛的 `archive/submission_2025-11-07/`、
  旧版平铺包 `D:\dna-accel-bkb220`、桌面上的旧包副本），换成 2026 最终提交物。
- **不做**：重写 Git 历史、`git push --force`。用户同时要求「保留开发记录」，
  所以 Git 历史一律保留。如果你认为用户其实指的是 Git 历史，放进 §4 的确认清单里问，
  得到明确答复前不动。

## 3. 来源清单与默认处置

动手前对每一项列出文件、大小与 SHA-256，处置可以在计划里调整，但要写明理由。

| 来源 | 内容 | 默认处置 |
| --- | --- | --- |
| `/mnt/d/dna-readout-accelerator/` | **最终提交包** | 作为仓库主体导入（见 §4 阶段 4）；Windows 原件**保留** |
| `/mnt/d/dna-readout-accelerator.rar` | 提交包压缩件 | 复制到 `archive/submission-2026/`，核对 SHA；Windows 原件**保留** |
| `/mnt/d/submitwork/report/` | `design-report-2026.docx`（权威可编辑稿） | 入库到可编辑稿目录 |
|  | `figures/v2/`、`evidence/*.tsv` | 入库 |
|  | `tools/build_report_docx_v2.py`、`tools/docx2pdf.ps1` | 入库（报告生成与 Office 实开导出脚本） |
|  | `design-report-2026.md/.pdf`（过期，缺用户 Word 手改） | md 作为「生成源文本」入库，并在 readme 注明它落后于 docx；pdf 删除（包内 PDF 是权威） |
|  | `design-report-2026_按模板修订版.docx`、`report-template.md`、`readme.md`、旧 `build_report_docx.py`、`tools/` 下的 `eq*.docx`、`poster-fix*.pdf`、`orig.pptx`、`bis` 等试验品、`~$*` 锁文件、`~WRL*.tmp` | 删除（先确认没有独有内容） |
|  | `参考*.docx/.pdf` | **原样**复制到本地归档，不入库，**不许修改内容** |
| `/mnt/d/submitwork/poster/` | `dna-readout-poster-2026.pptx`（权威） | 入库 |
|  | `check_layout.py`、`layout.md`、`CHANGES*.md` | 有价值的并入 readme 后删除，脚本可入库 |
|  | `dna-readout-poster-2026-final.pptx`（10-30 过期） | 删除 |
|  | `参考*` | 同上，原样进本地归档 |
| `/mnt/d/submitwork/video/提交视频/` | 最终演示视频 mp4（105 MB）+ 封面 | 本地归档 `archive/submission-2026/`；封面可入库 |
| `/mnt/d/submitwork/client-build/` | PyInstaller 的 `work/`、`dist/`、`build.log`、`check/` | 只把打包命令/版本写进客户端 readme；exe 与 `dist/` 是重复件，删除；其余删除 |
| `/mnt/d/dna-accel-bkb220/` | 2026-10-20 旧平铺包（293 MB），板测用的旧 ELF `e71554ac…` 出自这里 | 记下其 `build/artifact` 或 `export` 的哈希清单并写进文档，然后整目录列入删除候选 |
| `/mnt/e/桌面/演示/` | `gui_app.exe`（与包内同哈希）、3 组演示用例、`演示说明.txt`、`decoded_*` | 说明文字入库（客户端文档），用例与包内 `data/` 比对后去重；整个目录列入删除候选 |
| `/mnt/e/桌面/FPGA-DNA/dna-readout-accelerator/` | 提交包的旧副本（86 MB） | 与 D 盘最终包逐文件比对，没有独有内容就列入删除候选 |
| `/mnt/e/fpga-dna-bld` | **符号链接**，指向上一行那个目录 | 只删链接本身（`rm` 链接，不要跟进目标），列入删除候选 |
| `/mnt/e/桌面/FPGA-DNA/dna-accel-bkb220-submit/` | 更早的提交包副本（229 MB） | 比对后列入删除候选 |
| `/mnt/e/桌面/FPGA-DNA/review-2026-10-20/` | 10-20 报告评审稿 | 有独有结论的 md 并入 `docs/` 历史，其余列入删除候选 |
| `/mnt/e/桌面/FPGA-DNA/video-2026-10-30/` | 旧版讲解视频（34 MB）、旁白、分镜、截图 | 与 `dna-readout-video/` 比对去重；mp4 进本地归档或删除；文字稿入库 |
| `/mnt/e/桌面/FPGA-DNA/video-agent-prompt-2026-10-27.md`、`video-storyboard.md` | 视频阶段提示词与分镜 | 入库到 `docs/` 历史 |
| `/mnt/e/桌面/FPGA-DNA/CPU平台测试性能.docx` | **48 核服务器 CPU 基线数据**（报告性能对比的依据） | docx 进本地归档；把表格**照原文**转成 md 入库，不许改数字 |
| `/mnt/e/桌面/FPGA-DNA/好东西.pdf`、`DNA存储简介.pdf` | 来源不明的 PDF | 打开确认；第三方资料只进本地归档 |
| `/mnt/e/桌面/FPGA-DNA/*.jpg`、`图片1.jpg` | 照片 | 只进本地归档，**不入库**（可能拍到个人物品，见 §5） |
| `/mnt/e/桌面/比赛简介.txt` | 作品简介定稿 | 入库 |
| `/mnt/d/下载/…2026FPGA赛道选题指南-AMD.pdf` | 竞赛指南 | 与仓库 `docs/submission/competition-guide-2026-fpga-amd.pdf` 同哈希，不用再复制，也不删用户的下载文件 |
| `/tmp/photo12/`、`/tmp/refsearch/`、`/tmp/pkgfix-bak/`、`/tmp/rp/` | 换图、参考文献检索与包修正的临时脚本和备份 | 脚本（`clean.py`、`make_fig.py`、`swap.py`、`cr.py`、`doi.py`、`fmt.py`）入库到报告工具目录；**未打码的原始照片不入库**；备份文件删除。WSL 重启后 `/tmp` 会清空，这一项要先做 |
| `C:\Users\Lucian\AppData\Local\Temp\rpq\`（若存在） | Word/PowerPoint COM 导出脚本 | 与 `submitwork/report/tools/docx2pdf.ps1` 去重后入库 |

**不属于本项目，一律不碰**：

- `E:\桌面` 上的其他文件：快捷方式、`desktop.ini`、`常用.txt`、`xilinx/` 快捷方式目录、
  **`微电子学院24级本科新生分班名单.xls`**（含他人个人信息，绝不复制）。
- `D:\xilinx`、`D:\dev_tools`、`D:\tools`，以及 Windows 上的 Vivado/Vitis 安装目录。

## 4. 分阶段执行

### 阶段 1：盘点（只读，不改任何文件）

1. 对 §3 每个来源生成清单：相对路径、字节数、SHA-256，写到 `/tmp/archive-cleanup/inventory/`。
2. 跨来源找重复：同一哈希出现在多处的，列出「保留哪一份、删哪几份」。
3. 仓库内盘点：
   - `git ls-files` 中的过时文档、重复文档、只服务于开发期的一次性脚本；
   - 被忽略目录 `archive/`、`hw/build/`、`logs/`、`.Xil/`、`sw/workspace/`、`dna-readout-video/build/` 里的内容。
4. 比对仓库源码与提交包源码（§1.2），列出每一处差异，并判定以哪边为准。
   默认以**提交包为准**；仓库独有的开发期文件，有记录价值的保留，否则删除。

### 阶段 2：出计划并等用户确认（必须停下）

把计划写成 `/tmp/archive-cleanup/plan.md`，在对话里给用户看摘要，然后 `block` 看板等待。计划包括：

- **目标目录结构**（§4 阶段 4 的草案，可调整）；
- **四张表**：入库 / 本地归档 / 删除（WSL 内）/ 删除（Windows 侧），每行带大小与理由；
- **需要用户拍板的问题**，一次问清，不要一条一条追问：
  1. Windows 侧原件（D 盘、桌面）在复制核验之后删不删、删哪些。默认保留
     `D:\dna-readout-accelerator`、`.rar` 与 `D:\submitwork`，其余列为候选。
  2. 仓库是 PUBLIC：2025 年的提交材料（承诺书等）与本次视频要不要留在公开仓库外。默认不入库。
  3. 大文件策略（§6）选哪种。
  4. 2.0 G 的 `archive/board-evidence-2026-10/` 是否保留全部原始留证。默认保留，只做去重与压缩。
  5. 「删除之前的提交记录」是否指 Git 历史。默认不是，见 §2。

用户没确认之前，不许删除任何文件，不许做任何 Git 写操作。只有第 4 阶段之前的复制可以先做。

### 阶段 3：收集（复制 + 核验）

1. 按批准的计划，从 `/mnt/d`、`/mnt/e` 复制到仓库或 `archive/`。
   复制用 `cp -p` 或 `rsync -a`，**不用 `mv`**。
2. 每批复制后重新算 SHA-256，与阶段 1 的清单逐个比对，**全部相同**才算这一批完成。
   结果写进 `archive/SHA256SUMS`，以及仓库里的导入记录（见阶段 5）。
3. **Windows 侧的删除放到全部收尾、推送成功之后**。只删用户批准的那些；
   删前再核对一次哈希，删后列出已删路径。

### 阶段 4：重排仓库（以提交包为主体）

目标：**仓库主体就是最终提交包的那棵树**，外加开发记录。下面是建议结构，可在计划里调整：

```text
<repo>/
├── readme.md            # 由提交包 readme 改写：项目简介、复现、目录、最终数字、归档说明
├── license              # MIT
├── src/                 # = 提交包 src/（hw sw clients tools），以提交包版本为准
├── sim/  build/  board/  data/  skill/
│                        # = 提交包同名目录；data 中的大文件见 §6
├── report/              # 最终 PDF（报告、海报）+ 可编辑稿 docx/pptx + 生成工具 + 图源
├── docs/                # 开发记录：01–09 设计/状态/证据文档，history/（旧提示词、评审、计划），
│                        # submission/（合规说明、LLM 协作记录）
├── tools/  （若有）      # 仅仓库维护用：agent_view.sh、verify_repo_binding.sh、check_repo_hygiene.sh
├── AGENTS.md  CLAUDE.md # 保留，但改写为归档版（见阶段 5）
└── archive/             # 本地归档，被 .gitignore 忽略，不入库
```

要求：

- 用 `git mv` 迁移已跟踪文件，保住历史追溯。仓库里的 `hw/ sw/ clients/ tools/ tests/`
  迁到 `src/` 与 `sim/` 后，再用提交包版本覆盖，**以提交包内容为准**。
- **目录和文件名全部纯英文小写**，只用 `[a-z0-9._-]`。
  例外只有 `AGENTS.md`、`CLAUDE.md`：工具按这两个名字查找文件，不改名。
  确有理由保留的其他例外，在 readme 里列出。中文名文件（`参考*` 等）只进本地归档。
- 迁移后脚本必须照常能跑：`src/` 是脚本工作根，包内脚本已按此修正。
  仓库维护脚本（看板、绑定核验、卫生门禁）需要按新路径修正。
- **删除对象**：
  - 重复文档；
  - 已作废的开发期一次性实验脚本；
  - `tests/__pycache__`、`tests/stress_results` 这类运行产物；
  - `docs/archive/` 里已被新文档覆盖的版本；
  - 根目录残留的 `*.log`、`*.jou`；
  - 本地的 `.Xil/`、`sw/workspace/`。

  `hw/build/` 中的 Vivado 工程是可重建产物，用户批准后可以删；删之前把仍有引用的报告摘要搬进 `build/reports/` 或 `docs/`。
- **保留开发记录**：
  - Git 历史一律保留；
  - `docs/03-status.md`、`docs/09-evidence-ledger.md` 这类结论文档保留；
  - 删掉的大块内容，在 `docs/history/` 留一份「删了什么、为什么、去哪找」的索引。

### 阶段 5：全面更新文档

改完之后，每一份文档都必须与新结构和最终事实一致。重点：

1. **`readme.md`（根目录）**：
   - 项目一句话简介，取自 `比赛简介.txt`；
   - 最终数字，取自 §1.1，**只从源文件抄**，不从本提示词以外的地方凭记忆写；
   - 目录对照、复现步骤（以包内 readme 为底本）；
   - 提交物清单：哪些在 Git、哪些在本地归档、哪些在哪个 Release；
   - 「项目已结束、已冻结」的声明与冻结 tag 名。
2. **`docs/README.md`**：重写文档地图，删掉指向已删除文件的链接。
3. **`docs/03-status.md`**：改成最终状态，写明比赛已结束、最终版本、冻结日期（写实际执行冻结的那天）。
4. **新增 `docs/final-status.md`**（或并入 03，二选一，不要两份），内容包括：
   - 最终制品身份（FW_BUILD_ID、bit/XSA/ELF/BOOT 哈希，引自 `build/reports/2026.1-rebuild.md`）；
   - 板测依据，以及旧 ELF `e71554ac…` 与包内 ELF `ff5894b5…` 的关系；
   - **提交包的已知遗留问题**。照实记录，**不去修已提交的包**：
     1. 报告参考文献编号错位：用户新增的论文覆盖了原 [1]–[7]、[14]–[19]，正文引用指向了错误条目，原有 13 条文献丢失，新增论文在正文里没有被引用；
     2. 提交包只有报告 PDF，没有 docx；
     3. 海报页眉写的是「2026 Embedded Design Competition」，应为嵌入式芯片与系统设计竞赛；
     4. 报告缺少利用率百分比（LUT 69.0%、BRAM 64.3%）和「自主选题初级组」副标题；
     5. 包内 readme §5 的视频时长「4 分 09 秒」可能已过期，写入实测值；
     6. 包内 `board/run-logs/` 共 46 个文件，30 多个是 XC7Z010 时期的历史记录，其中 2 个提到 AGENTS.md；
     7. 包内 `build/reports/reference-original/` 是 v1.1 旧报告，含 `/home/lucian` 路径；
     8. 包内 `build/sw-repo/compat-manifest.json` 含 `/mnt/d/` 路径；
     9. PDF 作者元数据：报告为个人昵称，海报为 AMD 模板作者。
   - 仓库内的对应副本是否修正由你判断。修了的要注明「仓库版已修、提交包版未修」，两者不得混称。
5. **`AGENTS.md` / `CLAUDE.md`**：
   - 改写成**归档版**：开头写明项目已结束、仓库已冻结、后续只读；
   - 删掉已失效的并行开发流程（多 agent 派发、codex 通道、看板强制等可以压缩成一段「历史上怎么协作的」）；
   - 保留真正有用的工程知识（常见陷阱、判据设计、路径必须 ASCII 等），并修正其中的路径引用；
   - `docs/agent-prompts/` 整体移到 `docs/history/agent-prompts/`，**包括本文件**。
6. **`.gitignore`**：按新结构重写，删掉指向已不存在目录的规则，保留注释风格。
7. **断链检查**：对所有 `.md` 里的相对链接与反引号中的仓库路径，逐一检查目标是否存在，结果为 0 条断链。

### 阶段 6：冻结前验证

在新结构上实际跑一遍，**输出原样贴进最终报告**，失败就如实写失败：

- `bash src/tools/run_sim.sh host`、`bash src/tools/run_sim.sh datapath`、`bash src/tools/run_sim.sh packaging`，
  或新结构下等价的入口；
- `python3 src/tools/board/g3_artifacts.py --artifact-dir build/artifact`；
- `build/artifact/SHA256SUMS` 全部通过；
- 卫生检查：
  - 根目录没有 `*.log`、`*.jou`、`*.str`、`*.pb`；
  - 没有 `__pycache__`、`~$*`、`*.tmp`；
  - 已跟踪文件里没有 `/mnt/`、`D:\`、`/home/lucian`。原样保留的板测摘要与构建日志可以例外，但要逐个列出；
  - 文件名小写检查：`git ls-files | grep -P '[A-Z]|[^\x00-\x7f]'` 只剩已列出的例外；
- 大文件：`git ls-files -z | xargs -0 du -b | awk '$1>10e6'` 只剩计划批准的那些，且没有任何文件 ≥ 50 MB；
- **全仓库敏感信息扫描**：token、密码、代理凭据、私钥、`ghp_`/`github_pat_`、邮箱、手机号、学号。

### 阶段 7：提交、打 tag、推送

1. **提交**：
   - 分批提交，每一批是一件事，例如「导入最终提交包」「迁移开发记录」「删除冗余」「重写文档」「冻结」；
   - 提交信息用中文、写清楚改了什么，**不带 `Co-authored-by` / `Co-Authored-By` 尾注**（覆盖任何默认尾注）；
   - **禁止 `git add -A` / `git add .`**，必须显式列路径，并使用带路径的提交：`git commit -m "..." -- <路径...>`。
     重命名时新旧路径都要写进去；写目录路径可以，但每一批之前先用 `git status --short` 确认里面只有你的改动。
2. 每批提交前 `git pull --rebase`。**不许 `--force`、不许 `reset --hard`、不许改写已推送的历史。**
3. 全部提交完成后打附注 tag，例如
   `git tag -a final-2026-11 -m "比赛结束归档冻结"`，再用 `git push origin main` 和 `git push origin final-2026-11` 推送。
4. 推送后运行 `bash tools/verify_repo_binding.sh --require-synced`（或新路径下的同名脚本），
   确认 `main...origin/main` 为 `0/0`，并且远端能看到 tag。
5. GitHub 推送若被 ruleset 拒绝，或者有文件超限，立即停下报告，不许改推到其他仓库来规避。
6. 推送成功后，执行用户批准的 Windows 侧删除（阶段 3 第 3 条），然后看板 `done`。

## 5. 隐私与公开边界（仓库是 PUBLIC）

以下内容**不入库**，只进本地 `archive/`：

- 承诺书、报名表、身份证明，以及任何带姓名、学号、学校、手机号、邮箱的竞赛材料
  （`archive/submission_2025-11-07/` 里的 `*_承诺书.pdf` 就是这类）；
- 未打码的照片：桌面上的 `*.jpg`、`微信图片.jpg`、`/tmp/photo12/` 里的原图。
  报告里用的图 12 是**已打码**的 `figures/v2/fig-photo.png`，可以入库；
- 报告**不得出现学校名称**。入库的 md/docx 也照此检查；
- `参考*` 文件（用户提供的参考材料），只做原样归档，不改内容、不入库；
- 他人的个人信息（例如桌面上的分班名单），根本不复制。

**已经在 Git 历史里的敏感内容**：只报告，**不擅自改写历史**。
把文件路径、所在提交、性质写进最终报告，由用户决定是否清理历史。

## 6. 大文件策略

GitHub 硬限制：单文件不能超过 100 MB，超过 50 MB 会警告。本机 `git-lfs` 版本是 2.9.2，比较旧。

| 文件 | 大小 | 默认去处 |
| --- | --- | --- |
| 演示视频 `提交视频.mp4` | 105 MB | 本地归档；推荐作为 GitHub Release 附件上传（不超过 2 GB），需要用户同意 |
| 提交包 `.rar` | 59 MB | 本地归档；同上，可作为 Release 附件 |
| `gui_app.exe` | 30 MB | 不入库，写清 PyInstaller 打包方法（版本见客户端 readme）；或作为 Release 附件 |
| `data/r083-data/…se250.fastq` | 37 MB | 入库可以接受，但要列进计划；也可用 Release 附件 + 清单哈希代替 |
| `data/r083-data/…se150.fastq` | 19 MB | 同上 |
| 提交包 `data/` 合计 | 162 MB | 测试用例本身较小，可以入库；总增量要写进计划 |
| bit / XSA / ELF / BOOT.bin（`build/artifact/`） | 每个几 MB | 入库：它们是板测依据，`SHA256SUMS` 与 `manifest.json` 一起入库 |
| 报告 docx（6 MB）、PDF（2 MB）、海报 pptx（1.2 MB） | 小 | 入库 |
| `archive/board-evidence-2026-10/`（2.0 G）、`dna-readout-video/build/`（919 M）、`data/test-sets/`（717 M） | 大 | 不入库；本地归档，并在 `archive/readme.md` 说明内容与来源 |

选 LFS 还是 Release，由用户在阶段 2 拍板。在得到答复前，大于 10 MB 的文件一律不入库。
**不要**把已经推送过的大文件改用 LFS 重写历史。

## 7. 禁止事项汇总

1. `git add -A` / `git add .`，以及不带路径的 `git commit`。
2. 提交信息带 `Co-authored-by` / `Co-Authored-By`。
3. `git push --force`、`git reset --hard`、`git filter-repo` / `filter-branch`、删除远端分支或 tag、
   修改已推送的提交。
4. 在用户批准之前删除任何文件。Windows 侧原件在推送成功前一律不删。
5. 修改 `/mnt/d/dna-readout-accelerator/` 与 `.rar` 的内容。它们是已提交的冻结物，
   只能复制，不能改，也不能删。
6. 修改 `参考*` 文件内容；手工编辑 `view.md`；把 `view.md`、`.agent_view/` 加进 Git。
7. 凭记忆或从别的 agent 摘要里抄数字。所有数字都要从源文件读，并在文档里注明出处。
8. 使用 `pkill -f`（会误杀别的进程），以及使用 Windows 原生 hw_server（本机有蓝屏历史）。本任务不需要上板。
9. 未经同意重新跑 Vivado/Vitis 整机构建。本任务不需要，复用提交包里的报告与制品即可。
10. 把仓库改成私有或公开、改仓库设置、新建远端仓库。

## 8. 收工时给用户的最终报告（按此格式）

1. **结果**：最终提交 SHA、tag 名、`main...origin/main` 状态。
2. **结构**：新目录树，到第二层。
3. **数字**：入库文件数与总大小（前后对比）；本地 `archive/` 大小（前后对比）；删除了多少文件、释放多少空间。
4. **收集记录**：每个来源各复制了什么、复制到哪里、哈希核验是否全部通过。
5. **删除清单**：WSL 内与 Windows 侧分开列出，写明路径、大小与理由。
6. **验证输出**：阶段 6 每一项的命令与原样结果，失败如实写。
7. **遗留问题**：§1 与阶段 5 列的已知问题，加上你新发现的问题（包括历史中的敏感内容）。
8. **需要用户决定的事**：如果还有，一次列完。

报告写进 `docs/final-status.md` 的「归档记录」一节并提交；在对话里给出摘要即可，不要把全文贴两遍。
