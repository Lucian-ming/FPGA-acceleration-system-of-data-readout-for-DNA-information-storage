# 代码质量复排清单（2026-10-14）

> 本文是源码与脚本的只读复排，供 main 复核并决定后续修复。**本轮未改任何代码、RTL、脚本或制品。**
> 没有运行测试、仿真、综合、route 或板测；问题判断来自当前源码、门禁入口和项目文档的静态核对。

## 1. 范围与结论口径

本轮优先复核 `clients/python/` 的新界面与客户端逻辑、`sw/app/`、生产 RTL 与 testbench、构建脚本和 `tools/`。未评判 `logs/`、`hw/build/`、`tests/datasets/`、`docs/archive/`、`docs/images/` 的内容，也未读取或更改 `data/R0.83_data/`。

“问题”只列出能说明具体后果的维护风险；代码长度、个人风格和抽象偏好本身不算缺陷。风险栏说明是否会碰到位级/包级 SHA、回归门禁、manifest 或证据台账。涉及已验证行为的项目不建议作为一般可读性重构。

## 2. 上一轮清单逐项复核

依据上一轮计划 `docs/archive/history/2026/pre-bkb220-handoff-2026-10-10/slimming-and-code-quality-plan.md` 与执行报告 `docs/reference/slimming-report-2026-09-11.md` 逐项复核。对用户明确排除的归档、日志与构建目录，沿用上一轮报告状态，不重新打开或评判其内容。

| 编号 | 状态 | 当前复核 |
|---|---|---|
| A1 重复 XSA | 已解决 | 上一轮报告记录已退休；`design_2_wrapper.xsa` 与 `hw/build/export/hardware.xsa` 当前均不在工作区。未检查其他 XSA 内容。 |
| A2 过期 BIF | 已解决 | `sw/boot/dna_board_20260816.bif` 当前不存在；上一轮报告记录由有效启动包取代。 |
| A3 XSim 目录生命周期 | 已解决 | 上一轮报告记录保留窗口已落实；`tools/prune_xsim.sh` 仍存在并登记在 `tools/README.md`。本轮没有检查或清理 `hw/build/`。 |
| A4 旧赛季提交包外移 | 仍在 | 上一轮报告记为等待用户指定目标路径。本轮按范围要求不检查、不移动 `archive/submission_2025-11-07/`。 |
| A5 Vitis workspace 同源检查 | 已解决 | 上一轮报告记录已将 `sw/app/` 与生成 workspace 的一致性检查接入 `tools/check_repo_hygiene.sh`；本轮未检查被排除的 workspace 制品。 |
| A6 历史探针留证归并 | 已解决 | 上一轮报告记录错误轮次已归并并保留说明。本轮未检查 `logs/` 或 `tests/stress_results/`。 |
| A7 非发布构建中间件归档 | 已解决 | 上一轮报告记录已按用途归并；`hw/build/` 属于本轮排除范围，未重新评判目录状态。 |
| B1 固件模板死文件 | 已解决 | 上一轮报告记录七个模板文件及对应声明已清理并重建软件包；当前 `sw/app/` 中不再有这些模板源文件。 |
| B2 `hw/experimental/` 退休 | 部分解决 | 上一轮列出的旧实现与 wrapper 已退休；当前目录新增的 `srpe_batch_pway.v`、`vivado_quick_sim.tcl`、LDPC 探针和 testbench 均在 `hw/experimental/README.md` 说明用途与保留理由，不能套用旧版“只剩 `local_correlator.v`”的目录目标。现状有文档说明，但每次新增实验文件仍需同步更新目录表和回归覆盖关系。 |
| B3 零引用工具整理 | 已解决 | 上一轮报告记录调试工具已迁入历史区；当前 `tools/README.md` 有现用工具索引、历史工具入口和新增脚本登记。 |
| B4 客户端模块图谱 | 部分解决 | `docs/reference/client-module-map.md` 已交付，但其模块规模和职责描述没有跟上 `gui_app.py`、`ui_theme.py`、`ldpc_pipeline.py` 的本轮架构变化；例如旧图谱仍把纯 Python 打包作为活跃双轨，而 `first.py` 当前相关入口已委托 `fast_readout.py`。文档存在但不再足以指导当前改造。 |
| C1 核心契约注释 | 已解决 | 上一轮报告记录已补充 `main.c`、`platform.c`、`stage2_voter.c`、`gui_app.py` 和打包版 Stage1 RTL 的背景说明；本轮没有发现需要为“注释数量”再做一轮普遍扩写的理由。 |
| C2 禁止纯格式 RTL 重排/批量改名 | 仍在 | 这不是待修代码，而是仍然有效的风险约束。当前 voter 流水、Stage1 BRAM 对齐、固件协议符号与历史留证都有行为或追溯依赖；不得把格式统一或改名包装成无风险清理。 |

## 3. 新一轮问题清单

严重度按可造成的错误判断、定位成本和改动影响排序。各条建议均需由 main 复核后安排，本报告不授权实现。

### 3.1 可开发性与验证信号

#### 高：客户端测试下限把跳过用例也计入覆盖数

- **位置**：`tools/test_client.sh::ACTUAL_TESTS`；`clients/python/tests/test_client_core.py::BoardLDPCVerificationTests`。
- **问题**：脚本从 unittest 的 `Ran N tests` 取总数并要求至少 28；unittest 的总数包含 `skipTest`。板端 LDPC 用例依赖 `/mnt/d/bkb220_board_smoke/` 的外部文件，不存在时会跳过，但脚本没有校验跳过数或必需用例是否执行。
- **后果**：在没有板端样本的普通开发环境里，关键的 syndrome 通过/拒绝判据可能未执行，入口仍可能以用例数达标显示测试通过。开发者会把“测试被收集”误读成“关键路径已覆盖”。
- **建议**：把必需的主机可复现样本放入受版本管理的测试夹具，或把外部板端用例显式分层；测试入口应分别报告通过、失败、跳过，并对必须执行的集合设独立下限。`tools/README.md` 当前写的客户端用例下限为 25，而脚本实际要求 28，也应由同一入口或生成方式维护。
- **改动风险**：不改 FPGA 位级 SHA 或固件 source manifest；会改变客户端门禁的通过条件，需核对 `tools/run_sim.sh host` 与 `tools/test_client.sh` 两个入口的职责，避免一处更新、另一处继续产生不同信号。若把测试夹具纳入仓库，要遵守数据集来源和授权边界。

#### 中：客户端配置解析分散，非法阈值会静默变成默认值

- **位置**：`clients/python/gui_app.py::start_processing`、`_load_parameter_preset`、`_on_geom_changed`、`_resolve_read_bps`、`_apply_recommended_score`。
- **问题**：几何与 `score_min` 的读取、默认值、预设加载和 UI 联动分布在多个回调中。`start_processing` 遇到非数字阈值时直接选默认值，没有将输入错误呈现给用户；界面输入与实际任务配置可能因此不一致。
- **后果**：用户以为任务使用了填写值，实际发送的却是默认 `score_min`。该阈值参与固件投票筛选，会改变有效读段和最终结果，排查时容易误判为板端或数据问题。
- **建议**：在启动任务前通过单一配置解析函数生成已验证的不可变配置对象；无效输入明确标错并阻止提交。预设、几何变化和推荐值回写应复用相同的合法范围与默认策略。
- **改动风险**：不会改 RTL SHA 或固件 source manifest，但会影响任务配置字节及板端判据。必须保持合法现有配置的协议字节不变，并补客户端配置边界回归；不能把默认值策略悄悄改成另一种投票语义。

#### 中：客户端测试有两个可漂移入口

- **位置**：`tools/test_client.sh`；`tools/run_sim.sh` 的 `host` 用例；`tools/README.md` 客户端入口说明。
- **问题**：客户端 unittest discovery 被两个脚本分别启动和统计，配置容易分叉；README 登记的用例数又与 `test_client.sh` 的实际下限不一致。
- **后果**：开发者可能从两个入口得到不同的覆盖口径，增加或跳过用例时只更新一处，导致 CI/本地门禁含义不一致。
- **建议**：确定一个负责 unittest discovery、跳过数和汇总格式的唯一脚本；`run_sim.sh host` 调用它，或通过共享参数/函数维护同一契约。同步修正文档下限。
- **改动风险**：只影响主机门禁和工具文档，不触碰 RTL/ELF SHA、硬件 manifest 或板端台账；要保留 `run_sim.sh` 现有完整回归顺序及日志路径规则。

#### 中：所谓批处理迭代器仍然先物化整项输入

- **位置**：`clients/python/fast_readout.py::fast_iter_read_batches`、`fast_iter_source_seqs`、`batch_seqs_to_records`；`clients/python/first.py::iter_read_batches`。
- **问题**：`fast_iter_read_batches` 在 `yield` 前构造完整序列列表、记录矩阵及原始/临时缓冲区。调用者拿到的虽然是迭代器，但首批网络帧要等全量输入解析和编码结束后才产生。
- **后果**：输入规模增长时启动延迟和峰值内存随整项任务增加；网络发送不能与解析流水并行，批处理接口名会让调用方误以为它具备流式背压。
- **建议**：后续可把解析、编码与批次生成改为有界块流水，明确缓存上限和首批输出时点；先记录现有载荷逐字节、帧填充、尾包及错误输入行为，再做实现。
- **改动风险**：不改变 FPGA/固件 SHA，但会影响线上 TCP 字节序列、帧对齐与已验证黄金输入。需客户端字节级回归及协议边界核验；若性能或行为结论写入台账，应更新相应证据记录。

### 3.2 解耦与扩展边界

#### 中：固件公共头文件、状态枚举与流水分派形成隐式耦合

- **位置**：`sw/app/echo.h`；`sw/app/pipeline.h` 的 `pipe_state_t`；`sw/app/echo.c::run_processing_pipeline`；`sw/app/stage3_decoder.h`。
- **问题**：`echo.h` 同时承载协议、几何、DDR/IP 寄存器、任务配置和连接结构；其他阶段通过头文件传递依赖取得公共类型。`run_processing_pipeline` 依赖状态枚举的连续数值区间来选择 Stage1/2/3/LDPC 阶段，新增状态若插入错误区段可能走错分派，但编译仍成功。
- **后果**：调整一个公共类型或状态集合会扩大重编译和审查范围；阶段归属规则没有在显式映射中表达，扩展状态时容易造成运行时错派。
- **建议**：后续固件维护窗口可将纯共享类型与协议常量拆到最小公共头文件，并用显式状态到阶段映射取代数值区间判断；保留现有 enum 数值、wire 协议和状态迁移语义。
- **改动风险**：会改 `sw/app/` 源码并触发软件源 manifest、ELF/BOOT 同源包及 SHA256SUMS 更新；必须走 Vitis 2022.2 重建、软件包核验和完整 G3。不能只靠主机编译通过宣称安全。

#### 中：Stage3 DDR beat 几何有重复权威值

- **位置**：`sw/app/echo.h` 的 `DECODER_INPUT_BEATS` / `DECODER_OUTPUT_BEATS`；`sw/app/stage3_decoder.c` 的本地 `#undef` 与重定义；`sw/app/reg_timing.c::decoder_configure_default`。
- **问题**：共享头文件已经定义输入/输出 beat 数，Stage3 实现又撤销并重算宏，寄存器初始化还保留同一几何的本地数值。几何变化时必须同步多处，且 `stage3_decoder.c` 的注释数字与表达式容易被独立修改。
- **后果**：DDR 读写长度、DMA beat 配置和缓存维护区间可能互相偏离，造成尾部数据截断、越界或读回不完整；编译器不会发现这些语义不一致。
- **建议**：先确定唯一权威几何表达式，再让寄存器设置、缓存维护和验证函数引用同一组常量；保留现有启动写序列与延时。
- **改动风险**：不改 FPGA RTL 位级 SHA，但固件源 manifest 和软件制品 SHA 必须刷新。该路径直接决定 DDR 访问边界，需主机几何检查、重建完整软件包和 G3 取证；不得只做文本替换。

#### 中：软件包封装与 SHA 封存逻辑有多份实现

- **位置**：`tools/rebuild_software_package.py::write_sums` / `verify_sums`；`tools/write_source_manifest.py`；`tools/build_sw_variant.sh` 的 manifest 与 checksum 更新流程。
- **问题**：几个构建入口都实现文件枚举、manifest 更新或 SHA256SUMS 重签；排除临时文件和选择封存范围的规则并不完全相同。当前入口的差异有各自用途，但共同逻辑重复，后续维护容易形成“包 A 接受、包 B 拒绝”的边界漂移。
- **后果**：同源包、变体包和软件重建包可能对同一文件采用不同封存范围；哈希自洽不再能说明不同构建入口遵守同一清单契约。
- **建议**：把清单范围、排除项、manifest 更新和封存校验提取成一个有明确参数的共享库/命令；构建器只提供输入包和变体元数据，不自行重写 SHA 规则。抽取前先列出三个流程的当前文件集合差异。
- **改动风险**：不会必然改变 bit 或 ELF，但会影响 `source_manifest.json`、`manifest.json`、SHA256SUMS、严格 G3 制品门禁以及构建脚本自己的 source hash。必须用各类现存包做正反向门禁验证并更新复现说明/台账；不应在此轮直接统一排除规则。

### 3.3 可读性与维护小项

#### 中：异步回调捕获已退出异常作用域的变量

- **位置**：`clients/python/gui_app.py::DNAAcceleratorApp._test_connection` 内部 `do_ping`。
- **问题**：异常分支把 `exc` 放进 `self.after` 延后执行的 lambda；Python 在 `except` 结束时清理异常变量，延后回调可能在执行时触发 `NameError`。
- **后果**：连接失败的 UI 日志可能丢失原始异常，甚至由 Tk 回调报告新的 NameError；连接状态更新仍可能显示失败，但用户拿不到诊断原因。
- **建议**：在安排回调前把异常文本保存到局部不可变字符串，或用默认参数绑定回调所需值；仅修复日志交付，不改连接状态机。
- **改动风险**：纯 UI 错误路径，不改 FPGA SHA、固件 manifest、任务协议或硬件台账；可用连接失败的客户端单测覆盖，不需要板卡。

#### 低：状态颜色仍有两处语义映射

- **位置**：`clients/python/ui_theme.py::STEP_PALETTE` / `RoundedStatusBanner.set_theme_mode`；`clients/python/gui_app.py::DNAAcceleratorApp._update_status`。
- **问题**：总体样式已集中在 `ui_theme.py`，没有发现跨文件的大面积重复样式；但 `STEP_PALETTE` 中重复写入部分 `COLOR_*` 已命名颜色值，步骤状态与总状态也分别映射语义到色彩。
- **后果**：主题色变更可能只改到一处，某种状态在步骤条和顶部状态横幅呈现不一致；这是局部维护成本，不足以支持重写 860 行主题模块。
- **建议**：保留主题模块和组件 API，只抽共享状态 token 或从已有 `COLOR_*` 引用调色板项；让 GUI 提供状态语义，不再次决定颜色。
- **改动风险**：无 FPGA SHA、source manifest、硬件门禁影响；需检查亮/暗主题及各状态显示，不应顺便调整布局或控件行为。

#### 低：testbench 手工复现说明指向错误的源码位置

- **位置**：`hw/sim/tb_srpe_batch_pway.v`；`hw/sim/ip_tb/tb_differential_voter.v`；实际入口 `tools/run_sim.sh`。
- **问题**：TB 注释/手工编译示例仍指向 experimental 旧副本或不存在于 IP `hdl/` 的 voter TB；正式回归入口实际从生产 IP 源码和 `hw/sim/ip_tb/` 编译。
- **后果**：维护者按注释单独复现时可能测到旧实现，或因找不到 TB 而失败；复现结果与回归所覆盖生产版本不一致。
- **建议**：更新说明为 `tools/run_sim.sh` 对应的实际入口和被编译的生产模块名，不改 TB 激励与 RTL。
- **改动风险**：只改注释不触碰判据或 manifest；但若改动 TB 本体，需保持 testbench 覆盖关系并跑对应回归，不能把 TB 注释修复混成 RTL 重排。

#### 低：仓库卫生门禁的工具发现范围没有覆盖 PowerShell

- **位置**：`tools/check_repo_hygiene.sh` 的工具登记扫描；`tools/README.md` 中的 `g3_uart_cap.ps1`、`g3_xsdb.ps1`。
- **问题**：登记检查覆盖根目录及部分子目录的 Python、Shell、Tcl 脚本，没有扫描 `.ps1`；现有 PowerShell 工具已登记，但新增遗漏不会由该门禁抓出。
- **后果**：Windows 辅助脚本可能逐渐成为 README 中不可见的入口，触犯“每个工具都可被发现”的既有规则而门禁仍绿。
- **建议**：在脚本后缀集合和路径范围中加入 `.ps1`，同时保留已登记工具的忽略/生成文件边界；给检查本身加一个未登记 PowerShell 文件的故障注入判据。
- **改动风险**：不影响硬件或软件 SHA；会改变 `check_repo_hygiene.sh` 和 `run_sim.sh` 门禁结果，修改脚本必须登记 `tools/README.md`。不需触碰台账，若门禁发现新遗漏则再补工具索引。

#### 低：`ldpc_pipeline.py` 留有未调用资源复制 helper

- **位置**：`clients/python/ldpc_pipeline.py::_copy_resource` 与 `shutil` 导入。
- **问题**：该文件当前职责为 syndrome 校验、解交织和提取，不再提供译码器资源回退；`_copy_resource` 没有调用者，唯一用途是 `shutil` 导入。
- **后果**：读者仍可能以为当前流程会复制/加载某个译码资源，模糊了“只校验”的模块边界；增加无用依赖也让打包排查多一条路径。
- **建议**：确认包内没有动态字符串调用或外部使用后，移除私有 helper 和导入；不要恢复旧的本地译码器回退。
- **改动风险**：不改位级 SHA、固件 source manifest 或硬件门禁；客户端模块若纳入发行包需重打包并执行对应主机检查。当前建议属于低收益清理，可与客户端回归更新合并。

## 4. 今日重点文件的专项判断

- **`gui_app.py` 与 `ui_theme.py`**：界面大部分通用控件和样式已移到主题模块，未见需要再拆目录的证据。可操作债务集中在配置校验职责分散、异步异常捕获和状态色彩 token 重复；不建议按文件行数做二次大拆分。
- **`ldpc_pipeline.py`**：改为纯校验路径符合当前架构边界。只剩未使用 helper；不应因“管线”命名而重新引入译码后端或自动回退。
- **`differential_voter_v1_0.v`**：`S_VOTE_PIPE`、`S_VOTE_DRAIN` 与 BRAM 延迟对齐关系需要按周期审查。项目证据记录已有模块级流水回归，但没有本轮或当前新包的板端验收。未发现值得冒险做纯可读性拆分的缺陷。
- **`srpe_batch_pway.v`**：`S_PREFILL`、`PREFILL_BODY` 及同步 BRAM tag/valid 对齐表达了当前 P-way 行为；其源文件受打包变体与哈希门禁约束。未发现单纯因写法需要重构的证据。
- **今日新增软件构建/manifest/客户端脚本**：`tools/README.md` 已登记相关入口。主要可维护性风险是软件包封存逻辑多处实现；当前没有证据表明脚本结果错误，不应先合并实现再补验证。

## 5. 应明确“动不得”的内容

这里的“动不得”指不得作为一般代码整洁任务改写；将来若有独立功能需求，仍需按对应的判据重新论证。

1. **Stage1 P-way 预充填与生产 RTL 的 BRAM 时序对齐**：不要为了统一状态机或抽象宏而重排。它关系到同步 RAM 延迟、tag/valid 地址对齐、生产 LC 几何行为；源码还受 `PACKAGED_VARIANTS.txt` 与 `tools/check_ip_packaging.sh` 哈希/覆盖门禁约束。任何功能变更需同源综合实现、回归及完整 G3，更新 manifest 和证据台账。
2. **Voter 流水的累加/饱和行为**：不要在代码质量清理中“纠正” `+511` 越界时的既有行为或改变流水周期。项目证据记录了文档边界与实现行为的差异；改变它是协议/算法语义决策，可能改变逐位结果和板端 SHA，必须单独定契约、重跑向量/仿真、实现与板测，并更新台账。
3. **固件寄存器写序列与延时**：`reg_timing.c` 的写 0 → 写 1 → 延时 → 写 0 等序列是固件与 IP 的交互判据。禁止为去重改成“等价”序列；改动会使 ELF/BOOT/source manifest 变化，需整包重建和 G3。
4. **生成的 `sw/app/ldpc_perm_table.c`**：不得手工格式化或重排表项。它由 `gen_ldpc_perm_table.py` 生成且有逐位置换检查；源表、生成器、产物必须保持同源，改动需重新生成并运行专用门禁。
5. **`ui_theme.py` 的模块化边界**：不要单因文件较长而永久拆散主题控件或重复建立样式系统。该文件当前承担共用控件和视觉 token 的明确职责；只修有证据的 token 重复与主题不一致。

## 6. 下一步修复顺序

### 先做：低风险、可离线验证

1. 修复 `_test_connection` 的异常文本绑定，保持连接状态不变。
2. 统一客户端 unittest 的唯一入口，分别统计跳过项与必需覆盖；同步 `tools/README.md` 下限说明。
3. 修正两个 testbench 的手工复现注释；扩展卫生门禁以发现 PowerShell 工具。
4. 更新 `client-module-map.md`，删去已过期的职责图；确认 `_copy_resource` 无外部/动态调用后再移除。
5. 仅做状态色彩 token 去重时，保持界面布局与状态行为不变。

### 需要主机回归后安排

6. 集中 GUI 配置解析与阈值校验；保持所有合法配置的协议字节与默认策略不变。
7. 讨论客户端真实流式生成；先固定逐帧黄金和峰值缓存边界，再实现有界流。
8. 设计软件包封存逻辑共享入口；先比对三种构建方式的 manifest/SHA 文件集合，再动构建器。

### 等软件或板卡维护窗口

9. 固件公共头文件、枚举分派和 Stage3 beat 几何整理，须先有当前包基线，随后在 WSL Vitis 2022.2 重建、刷新 `SHA256SUMS` 并走完整 G3；不应与纯冷清理混在一起。
10. Voter 与 P-way RTL 只在有明确功能缺陷或验收目标时改；先复核当前 source hash pin、`PACKAGED_VARIANTS.txt`、仿真覆盖和当前板测窗口，再完成综合实现及 G3。当前没有“为了可读性就重构”的收益证据。

## 7. 未完成项与复核限制

- 本轮未执行自动化测试，因此测试下限、skip 计数、门禁后缀范围等结论是静态代码审阅，不代表门禁已实际失败或通过。
- 本轮未运行 GUI 交互、客户端端到端、RTL 仿真、综合、route 或板测；新增问题的运行时影响仍需 main 在安排修复时验证。
- 当前板端状态与硬件证据以 `docs/03-status.md`、`docs/09-evidence-ledger.md` 为准。本报告不把模块仿真或哈希自洽提升为板端验收。
- 修复取舍和优先级最终由 main 复核；报告中的建议不代表已经授权实施。
