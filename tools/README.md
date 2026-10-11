# tools/ 工具索引

冻结说明：make_golden.py及tests/golden/se250/GEOMETRY.txt中的旧`docs/20`是生成时的历史引用，指向[SE250研究原文](../docs/archive/history/2026/se250-study-2026-08-30.md)。本轮保持生成器与黄金元数据字节不变，不为修引用重录黄金；当前契约查02/04，验证查06。


当前完整流程、资源与Agent任务见[05执行计划](../docs/05-implementation-plan.md)；新板配置/同源制品见[07](../docs/07-board-build-and-acceptance.md)。

> **为什么需要这份索引**：2026-09-10 卫生审计发现 `tools/` 下有 **7 个脚本零引用**
> ——不在任何文档、脚本或 CI 里出现。其中 `bench_align.py` 里存着「**精确种子法为何
> 在本任务中失效**」的实测反证，而 `docs/08` 因为看不到它，把种子索引列成了第一优先级
> 的长期方向（已于同日撤回，见 `docs/08` 的已证伪方向）。
>
> **一个无人可见的脚本，等于它得出的结论不存在。** 新增工具必须登记到本表。
>
> 本文件此前是 0 字节空文件。

---

## 一键入口（最常用）

| 脚本 | 用途 |
| --- | --- |
| `run_g3.sh` | **板级验收唯一入口**。烧录 → 下发任务 → LDPC → 比图片哈希 → 四级 DDR 取证。`--artifact-dir` 成套选择bit/XSA/PS7/ELF与manifest；拒绝仅覆盖不同bit/ELF的混用，新板必须严格制品门禁 |
| `run_sim.sh` | **RTL + 主机侧回归**。含 IP 打包门禁、三级 TB、行为轨迹判据、LDPC 自检、语法检查 |
| `run_demo.sh` | 答辩现场演示：现场换 payload + 故障红灯，四幕哈希均当场产生 |
| `verify_repo_binding.sh` | Git 绑定门禁，动手前必跑 |
| `agent_view.sh` | 多 agent 看板；**禁止手工编辑 `view.md`** |

## 黄金向量与参考模型

| 脚本 | 用途 |
| --- | --- |
| `make_golden.py` | 生成各级黄金向量。**不带参数调用必须逐字节复现已冻结的 SE150** |
| `make_stage1_tie_golden.py` | Stage1 同分并列位置集。`stage1_fwd_expect.txt` 的位置在并列时由 FFT 浮点噪声决定，**不能按单值比相等** |
| `golden_model.py` / `readout.py` | 纯软件参考实现（滑窗相关 → 投票 → 反稀疏化） |
| `ldpc_decode.py` | 纯 Python DVB-S2 R=5/6 硬判决译码器 |

## 板端诊断（`tools/board/`）

| 脚本 | 用途 |
| --- | --- |
| `g3_artifacts.py` | 完整制品目录、SHA、XSA内bit/器件/生产几何与manifest核验；只读预检，不将哈希自洽当作源码因果证明 |
| `g3_uart_cap.ps1` | run_g3调用的PS串口采集内部依赖；唯一采集者，实际端口不得用蓝牙/固定COM兜底 |
| `g3_xsdb.ps1` | Windows XSDB参数桥接，安装/留证路径含空格时分别传参，供G3调用 |
| `generate_stage1_fixture.py` | 独立NumPy逐符号枚举Stage1 oracle；生产LC50与显式LC6短测，定向807/末区域/补零/并列向量 |
| `g3_performance_matrix.py` | 同板P4/P16多规模≥3次性能矩阵；明确t_result/上传/LDPC/整轮边界，未采集硬件周期时null |
| `g3_wait_ready.py` | 应用层就绪探针（CAPS 握手） |
| `g3_overhead_sweep.py` | 固定开销尺寸扫描与模型拟合。**必须 `post=True`**，`--no-post` 是「不发 POST 触发」，板子根本不算 |
| `g3_recovery_probe.py` / `g3_netfault_probe.py` | 畸变包 / 断网注入恢复探针 |
| `g3_config_guard_probe.py` | **配置/容量守卫故障注入**：手工拼 CONFIG 字节绕开客户端全部校验，直打固件守卫。2026-09-11 实测 **7/7 通过**：超容量/非 64 对齐/零条数均被 `rc=5` 拒绝，`read_bps=250` 被 `rc=2` 拒绝。⚠️ 注意 `PKT_CONFIG_OK` 只是应答，payload 里的 u32 **才是理由码，0 才是接受**——初版探针把拒绝当成接受，得出过错误结论 |
| `g3_runs_to_jsonl.py` | run 目录收敛成结构化 JSONL |
| `read_pipe_counters.tcl` | **不依赖串口**、用 XSDB 读固件内 poll 计数器。串口没接时固件的 `xil_printf` 插桩等于不存在 |
| `arm_baseline.py` | **同片 ARM 纯软件 Stage1 基线**：编译 `sw/bench_arm/`（主机参考 + A9 裸机 NEON 版），XSDB 复位 PS、`dow -data` 读段进 DDR、运行并读回，与主机参考逐条比对后才报耗时。**会复位整板**，跑前确认板上没有其他任务。2026-09-22 实测 12.10 ms/记录（单核），见 `docs/benchmarks/measured_arm_baseline.md` |

## 数据集与鲁棒性

| 脚本 | 用途 |
| --- | --- |
| `generate_payload_dataset.py` | D1 多 payload 独立数据集生成 |
| `mutate_reads.py` | D2 受控噪声 / D3 经验轮廓加噪 |
| `extract_error_profile.py` | D3 真实测序经验误差轮廓提取 |
| `run_multi_payload_regression.py` | 多 payload 泛化回归。`--repeat N` 做重复实验（写独立目录，**不覆盖已提交留证 dump**） |
| `run_robustness_scan.py` | G5 抗噪边界扫描（错误率/覆盖度 → **恢复成功率**） |
| `g5_false_accept.py` | G5「**误接受率**」的定义与测量：逐记录判定真/诱饵/错位，扫 `score_min` 出 FAR/FRR 曲线。**定义写在文件头，先读那里** |
| `run_g5_matrix.sh` | 驱动上者跑 G5 受控误差矩阵（替换率 × 插删率 × 3 种子），产出 `summary.tsv` |

## 性能与基准

| 脚本 | 用途 |
| --- | --- |
| `run_cpu_benchmark.py` | CPU vs FPGA 公平基准，MEASURED/HISTORICAL/ESTIMATED 三级分型 |
| `profile_host.py` | 上位机瓶颈剖析与端到端拆解 |
| `g3_timing_fit.py` | 从 `run_g3.sh` 的留证目录拟合「固定开销 + 每条成本」。**与 `board/g3_overhead_sweep.py` 功能重叠**：前者事后拟合既有留证，后者主动扫描并控制档位与重复次数；新测量用后者，回溯历史用前者 |
| `bench_align.py` | Stage1 的 CPU 侧基准，**并含「精确种子法为何失效」的实证**：读段与水印在最佳位置最长连续精确匹配仅 5~7 nt，16-mer 命中概率 ≈ 1.5e-05。**任何基于精确种子的索引在本任务中不可用**（见 `docs/08` 的已证伪方向）。⚠️ 会在**当前工作目录**写出 `ref.bin` / `reads.bin`，跑完记得清理 |

## 单点调试（按需，不进回归）

| 脚本 | 用途 |
| --- | --- |
| `vote_range.py` | 投票累加器运行中极值实测（回答是否会饱和溢出） |
| `board_stage_check.py` | 四级 DDR 取证比对（由 `run_g3.sh` 调用） |
| `m2_chain.py` / `m3_mem.py` | M2/M3 仿真辅助 |

## 已退出现用区的历史工具

2026-10-11将以下6个脚本原样移入[历史源码索引](../docs/archive/tools/2026/retired-20261011/README.md)，SHA与文件权限保留。归档脚本不是现用入口，相对路径保留原布局，不能直接从归档目录执行；需要追溯时按整理记录审阅原版本。现用独立黄金、G3/故障探针、CPU基准、打包和构建工具继续保留。

| 历史脚本 | 退役原因 |
|---|---|
| [extract_ldpc_dlls.py](../docs/archive/tools/2026/retired-20261011/extract_ldpc_dlls.py) | 历史gui_app.exe的一次性DLL提取；当前客户端运行库已保留，无现用调用者。 |
| [debug_vote_diff.py](../docs/archive/tools/2026/retired-20261011/debug_vote_diff.py) | 已退役的BRAM票值定位脚本；保留TB的dump能力和历史源码，非现用验收入口。 |
| [debug_high_entropy.py](../docs/archive/tools/2026/retired-20261011/debug_high_entropy.py) | 已退役的高熵失败诊断；结论和原始失败证据保留在entropy_and_d2_validation等文档中。 |
| [voter_page_split.py](../docs/archive/tools/2026/retired-20261011/voter_page_split.py) | 已退役的B20跨4KB页参考表；结论已进入SE250历史研究和正式接口实现。 |
| [stress_test_suite.py](../docs/archive/tools/2026/retired-20261011/stress_test_suite.py) | 旧板压测依赖硬编码旧制品/目标，auto切SE250；新板改用严格完整包G3及故障探针编排。 |
| [switch_export.sh](../docs/archive/tools/2026/retired-20261011/switch_export.sh) | 只被旧压测调用，覆盖旧export/BSP头；与调用者一同退出现用区，新板每个profile使用独立成套包。 |

## 构建与制品

| 脚本 | 用途 |
| --- | --- |
| `run_vivado_build.sh` | Vivado 整机构建（日志不落仓库根）；显式board/part_name/独立build与export目录，未验证BKB220配置拒绝构建 |
| `run_xsim.sh` / `run_m2_full.sh` / `run_m2_quick.sh` / `run_m3_bd.sh` | XSim 与多级串联仿真 |
| `prune_xsim.sh` | XSim 仿真历史生成物保留窗口与常态化修剪工具（docs/05 的清理条款，默认 keep 3 并归集日志） |
| `check_ip_packaging.sh` | IP 打包卫生门禁：hdl 内无 TB、同名模块只打包一个、引用文件存在、无孤儿、打包变体与清单一致、**打包的实现必须被回归覆盖**（已接入 `run_sim.sh`） |
| `check_repo_hygiene.sh` | 仓库卫生门禁：根目录残留、工具登记、文档编号、共享数据副本、`logs/` 的 `.gitignore` 覆盖（已接入 `run_sim.sh`） |


用户指定的开发顺序（2026-10-11）：先用WSL Vivado2022.2完成硬件开发，PS软件也以补齐后的WSL Vitis2022.2为主；Windows2026.1负责下载/调试。WSL Vitis2022.2已从现有Vivado维护入口补齐：Vivado2022.2、XSCT2022.2.0必需命令及ARM GCC11.2.0实际Cortex-A9 ARM32对象编译通过；完整同XSA软件包仍待迁移阶段重建验证。已有Windows2026.1旧ECO XSA软件兼容探针继续保留，但不替代22主线或新板验收。22主线稳定后，最后独立验证Windows2026.1完整硬件及软件开发链路，规则见07。

WSL22使用显式VIVADO_ROOT，启动器选择顺序为VIVADO→VIVADO_ROOT→PATH，显式根目录错误即拒绝，不默默切换工具版本。Vitis22的实际XSCT能力已核验，`sw/scripts/create_vitis.tcl`是应用构建起点，完整FSBL/BOOT/readback/manifest须另补齐并实测；Windows26软件入口`create_vitis_modern.py/run_vitis_modern.ps1`用于最后26重建或明确辅助探针。2026.1 XSCT禁用且可能exit0；完整工具/同源门禁见[07](../docs/07-board-build-and-acceptance.md)。

Stage1生产P4/P16模块与真实包装接口：`bash tools/run_sim.sh stage1_production` 为LC6短测；`SIM_CASE_TIMEOUT=3600 bash tools/run_sim.sh stage1_production_full` 为LC50生产几何长测，日志和fixture保留在 `logs/iverilog/<run-id>/`。短测不替代生产几何或真板验收。

## C 单元测试（由 `run_sim.sh host` 调用）

`test_wm_expand.c`（PS 水印展开）、`test_ddr_layout.c`（DDR 分区校验）、
`test_task_config.c`（协议解析/CRC）、`align.c`（`bench_align.py` 的 C 对照实现）。

2026.1 本机 lwIP YAML 的 UTF-8 BOM 与 GBK 读取路径有实际兼容问题：先运行 `sw/scripts/prepare_vitis_compat_repo.py --vitis-root D:/xilinx/2026.1/Vitis --out-dir <新目录>`，再将目录填入现代构建 JSON 的 `embedded_sw_repo`。仅移除描述文件 BOM，保留原厂库源码 SHA 与 compat-manifest；不修改安装。完整命令和已测边界见 `docs/benchmarks/bkb220-toolchain-audit.md`。

性能矩阵可加 `--uart-log <外部持续追加的现有采集日志>`，记录本轮 Voter/Decoder 的原始硬件周期；不自动抢占串口。主机回归：`python3 -m unittest discover -s tests/host -p 'test_g3_*.py' -v`，涵盖 `test_g3_artifacts.py` 和 `test_g3_performance_matrix.py`；这些替身测试不能替代板测。

Windows2026.1 正式 Stage1 XSim 输入由 tools/board/create_stage1_xsim_input.py 制作：先使用 generate_stage1_fixture.py --num-lc 50 生成oracle，再将生产RTL/TB/fixture复制为带14文件SHA的只读构建输入。`tools/run_stage1_xsim.ps1 -InputDir <带SHA的输入目录> -RunDir <新run目录>` 为Windows2026.1正式仿真入口；LC50模块/真实包装接口已通过，结果见 `docs/benchmarks/stage1-16way-ip-integration.md`。

## 新板执行前的旧平台风险（2026-10-10核对）

- 旧stress_test_suite.py/switch_export.sh已成对退出现用区并归档。新板长稳由main/verify围绕run_g3.sh --artifact-dir完整包、显式工具/目标/串口和现用故障探针编排；按实际运行时长判断2h/8h，保留逐轮证据，不自动切SE250或覆盖旧export。
- board/arm_baseline.py固定旧BSP/XSA/GCC/XSDB并复位整板；新板先适配，必须持板资源。
- run_multi_payload_regression.py的board模式及run_demo.sh主要发TCP任务，不下载/复位，仍须实际新板IP/固件/阈值确认；golden/check-dumps离线。
- run_robustness_scan.py的board_equivalent是软件模拟，不是新板证据；故障探针主动注入错误流量，不是只读健康检查。

完整命令、现状和失败分类见06/08，历史编号文档已归档，当前根文档收敛为9份。
