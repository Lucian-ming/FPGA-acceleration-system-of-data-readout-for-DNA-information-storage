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
| `run_g3.sh` | **板级验收唯一入口**。烧录 → 下发任务 → LDPC → 比解码载荷 SHA → 四级 DDR 取证；默认 JPEG 仍按 EOI 截断，任意载荷用 `--input-bytes N --expect-sha SHA` 按元数据长度写裸字节。`xc7z020` 自动启用严格制品门禁并要求显式 `--artifact-dir`、`--ip`；WSL XSDB 用 `--xsdb /tools/.../xsdb --hw-server TCP:127.0.0.1:3132 --win-root /绝对路径` 本地执行，串口必须收到输出才可验收 PASS。`--allow-uart-skip` 仅供排错并写入摘要 |
| `run_sim.sh` | **RTL + 主机侧回归**。含 IP 打包门禁、三级 TB、行为轨迹判据、LDPC 自检、语法检查 |
| `test_client.sh` | 客户端统一检查入口：语法检查后运行 unittest discovery，并要求实际收集数不少于 25 |
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
| `repro_non_jpeg_decode_length.py` | 在外部 v2 数据包上用 54,000 bit 信息块复现旧 JPEG EOI 截断与 `input_bytes` 的长度差；只读外部数据并打印长度/SHA，不表示板端结果 |

## 板端诊断（`tools/board/`）

| 脚本 | 用途 |
| --- | --- |
| `g3_artifacts.py` | 完整制品目录、SHA、XSA内bit/器件/生产几何与manifest核验；只读预检，不将哈希自洽当作源码因果证明 |
| `g3_uart_cap.ps1` / `g3_uart_cap.py` | Windows COM 与 WSL `/dev/ttyUSBn` 串口采集器；端口必须显式传入，记录接收量，禁止默认 COM6 |
| `g3_xsdb.ps1` | Windows XSDB参数桥接，安装/留证路径含空格时分别传参，供G3调用 |
| `generate_stage1_fixture.py` | 独立NumPy逐符号枚举Stage1 oracle；生产LC50与显式LC6短测，定向807/末区域/补零/并列向量 |
| `g3_performance_matrix.py` | 同板P4/P16多规模≥3次性能矩阵；明确t_result/上传/LDPC/整轮边界，未采集硬件周期时null |
| `g3_upload_sweep.sh` | **读段上传段的多档 × 多次扫描**（`--no-post`，**只测上传、不触发流水线、不判正确性**）：4 档规模各 3 次，出耗时与吞吐。用来区分上传段是被「轮询周期/接收窗口」还是「停等」限速。**不烧录**——A/B 时换包由调用者负责。见 [上传段 benchmark](../docs/benchmarks/bkb220-p16-speed-a-upload.md) |
| `g3_soak.py` | **新板长稳（2h/8h）编排**：按**实际墙钟**循环跑 `run_g3.sh` 完整判据轮（全量输入、`--skip-boot`、唯一判据 SHA），逐轮写 TSV，每 N 轮插一次畸变包恢复探针。**不烧录**——调用方须先真烧录本包并把包 SHA 记进 `--tag`；`hardware_cycles`/`power_w` 恒 null，板端耗时是客户端打印值，不得反推。墙钟达标≠全部轮次通过：有失败轮仍继续跑（观察能否恢复），但最终 verdict 会红 |
| `g3_caps.py` / `g3_wait_ready.py` | 完整核对 CAPS 的 SE150 几何；探针要求显式 `--ip`。CAPS 不含 P_WAYS/PIPE_TREE，因此无法区分 P4/P16 |
| `g3_overhead_sweep.py` | 固定开销尺寸扫描与模型拟合。**必须 `post=True`**，`--no-post` 是「不发 POST 触发」，板子根本不算 |
| `g3_recovery_probe.py` / `g3_netfault_probe.py` | 畸变包 / 断网注入恢复探针 |
| `g3_config_guard_probe.py` | **配置/容量守卫故障注入**：手工拼 CONFIG 字节绕开客户端全部校验，直打固件守卫。2026-09-11 实测 **7/7 通过**：超容量/非 64 对齐/零条数均被 `rc=5` 拒绝，`read_bps=250` 被 `rc=2` 拒绝。⚠️ 注意 `PKT_CONFIG_OK` 只是应答，payload 里的 u32 **才是理由码，0 才是接受**——初版探针把拒绝当成接受，得出过错误结论 |
| `g3_runs_to_jsonl.py` | run 目录收敛成结构化 JSONL |
| `read_pipe_counters.tcl` | **不依赖串口**、用 XSDB 读固件内 poll 计数器；从本轮 ELF 的 `pipe_poll_steps` / `wm_poll_steps` / `pipe_state` 符号经 `arm-none-eabi-nm` 解析。`--addresses` 仅供显式排错，无旧地址兜底 |
| `arm_baseline.py` | **同片 ARM 纯软件 Stage1 基线**：编译 `sw/bench_arm/`（主机参考 + A9 裸机 NEON 版），XSDB 复位 PS、`dow -data` 读段进 DDR、运行并读回，与主机参考逐条比对后才报耗时。**会复位整板**，跑前确认板上没有其他任务。2026-09-22 实测 12.10 ms/记录（单核），见 `docs/benchmarks/measured_arm_baseline.md` |
| `bkb220_f3_bringup.sh` | **BKB220 F3 最小启动判据入口**（2026-10-12 新增）：真实 FT4232H/USB 前置检查 → 被动抓 `/dev/ttyUSB1/2/3` → `rst -system` + `source ps7_init.tcl` + `ps7_init`/`ps7_post_config` → 读回 DDR/UART/GEM/MIO/时钟寄存器 → 汇总哪个通道收到字节；PS7 初始化命令或寄存器读失败会失败退出；可选 `--ddr-window <基址>,<字节数>` 做指定窗口 walking-1 与固定 pattern 写读比对。**触板路径见 `docs/07` §3a 的工具链分工：开发在 WSL 2022.2；Windows 2026.1 只负责烧录。** 本脚本按 **WSL 路径**实现（`usbipd` 直通 + Linux 2022.2 hw_server），那是 F3 实际跑通的路径；若要归 Windows 烧录，则改用 COM10 + Windows XSDB。边界：`ps7_post_config` 退出 0 不等于 DDR PASS；指定窗口回环不等于全容量/温压验证；串口没字节不等于该通道不是 PS UART；JTAG 启动通过不证明 QSPI/SD 冷启动通过 |

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
| `profile_upload.py` | **读段上传段的三段拆分**：客户端预处理／本机回环停等对照／板端小包 RTT 探针（`--rtt-probe IP:PORT`）。用来判断"上传慢"到底出在客户端 CPU、协议停等还是板端收包速率；**不触板也能跑前两段**。见 `docs/benchmarks/bkb220-p16-speed-a-upload.md` |
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
| `build_sw_variant.sh` | **PS 编译宏 A/B 的完整变体包构建器**：复制一份已验收包 → 只在新包副本的 Makefile 里追加 `-D` 宏 → 重建应用 ELF → 重打 BOOT.bin → 写 manifest 派生字段 → 重签并自检 SHA256SUMS。**核验并拒绝**新包 bit 与参考包不同（本脚本不改硬件制品）。存在理由：`run_g3.sh` 禁止 `--elf` 指向包外文件，所以任何 PS 侧编译期改动的 A/B 都必须有自己的完整包。只证明新包自洽且与参考包同源，**不证明**它在板上通过 |
| `run_xsim.sh` / `run_m2_full.sh` / `run_m2_quick.sh` / `run_m3_bd.sh` | XSim 与多级串联仿真 |
| `test_ldpc_perm.sh` | **PS 侧位级置换的主机单元测试**（不需要板子）。重新生成并校验 `sw/app/ldpc_perm_table.c` → 用 gcc 编 `sw/app/ldpc_perm.c` + 生成的表 → 与 `native_ldpc.deinterleave` 在**板端真实回传样本**与随机/全 0/全 1/交替模式上**逐位比对**，含往返还原。存在理由：板上缺解交织只表现为「核不收敛」，信号弱、定位慢；置换是纯数据变换，可以在主机上被穷尽核验。**只证明 C 实现 == Python 参考，不证明板上正确**（那要 G3 + 串口出现 `converged=1`） |
| `gen_ldpc_perm_table.py` | 从 `clients/python/resources/permutation64800` 生成 `sw/app/ldpc_perm_table.c`（`inv` 表，语义 `natural[c] = rx[inv[c]]`，u16×64800 = 126.6 KiB）。生成前断言输入是排列，生成后断言逆变换正确且与 `deinterleave` 逐位一致。`--check` 只校验现有文件是否最新（**检入的门禁用法**：手改或源表变更会被抓出来） |
| `write_source_manifest.py` | 为制品包写/刷新 `reports/source_manifest.json`（`files`: 源码相对路径 → SHA256）并同步 `manifest.json` 的 `source_manifest.sha256`；`--resign` 会顺带重签并自检 SHA256SUMS。范围固定为「决定 bit 与 ELF 的源」。存在理由：**没有它，包里 bit/ELF 出自哪份源码就只剩人嘴说**；`g3_artifacts.py` 只校验这份清单的**格式**，查不出「清单与包内源码不一致」——`build_sw_variant.sh --sync-src` 以前正是这个隐患（已由本工具接入修掉） |
| `rebuild_software_package.py` | 从 `hw/build/` 下含 XSA 的硬件包生成独立软件验收包：用 Vitis 2022.2 XSCT 生成平台/BSP/FSBL，先 `platform generate` 物化 BSP 头，再设置并复核 `TCP_WND=32768`；仅在 XSCT `app create` 命中已知 socket 错误时，显式回落同安装树 ARM GCC 直编；随后生成 ELF/BOOT/readback/manifest/SHA256SUMS 并运行 G3 strict `--plan-only`。只读输入硬件包，不连板、不烧录。完整实测命令和环境边界见 [`docs/submission/reproduce-artifacts.md`](../docs/submission/reproduce-artifacts.md) |
| `prune_xsim.sh` | XSim 仿真历史生成物保留窗口与常态化修剪工具（docs/05 的清理条款，默认 keep 3 并归集日志） |
| `check_ip_packaging.sh` | IP 打包卫生门禁：hdl 内无 TB、同名模块只打包一个、引用文件存在、无孤儿、打包变体与清单一致、**打包的实现必须被回归覆盖**（已接入 `run_sim.sh`） |
| `check_repo_hygiene.sh` | 仓库卫生门禁：根目录残留、工具登记、文档编号、共享数据副本、`logs/` 的 `.gitignore` 覆盖（已接入 `run_sim.sh`） |


用户指定的开发顺序（2026-10-11）：先用WSL Vivado2022.2完成硬件开发，PS软件也以补齐后的WSL Vitis2022.2为主；Windows2026.1负责下载/调试。WSL Vitis2022.2已从现有Vivado维护入口补齐：Vivado2022.2、XSCT2022.2.0必需命令及ARM GCC11.2.0实际Cortex-A9 ARM32对象编译通过；`rebuild_software_package.py` 已从当日 BKB220 P16 XSA 实际重建软件包并通过 SHA 与 G3 plan-only 门禁。已有Windows2026.1旧ECO XSA软件兼容探针继续保留，但不替代22主线或新板验收。22主线稳定后，最后独立验证Windows2026.1完整硬件及软件开发链路，规则见07。

WSL22使用显式VIVADO_ROOT，启动器选择顺序为VIVADO→VIVADO_ROOT→PATH，显式根目录错误即拒绝，不默默切换工具版本。BKB220 P16 完整同 XSA 包已有 G3 记录，自动软件打包入口已从当日硬件包重建并通过只读制品门禁；留证见[制品复现说明](../docs/submission/reproduce-artifacts.md)和[任务报告](../logs/submission/vitis-chain.md)。`create_vitis.tcl` 的首次 `platform generate` 与第二次 BSP 生成已由新入口调用和校验；XSCT `app create` 的 socket 错误由同树 ARM GCC 明示回退。新重建包尚无板端 G3 证据。Windows26软件入口`create_vitis_modern.py/run_vitis_modern.ps1`用于最后26重建或明确辅助探针。2026.1 XSCT禁用且可能exit0；完整工具/同源门禁见[07](../docs/07-board-build-and-acceptance.md)。

Stage1生产P4/P16模块与真实包装接口：`bash tools/run_sim.sh stage1_production` 为LC6短测；`SIM_CASE_TIMEOUT=3600 bash tools/run_sim.sh stage1_production_full` 为LC50生产几何长测，日志和fixture保留在 `logs/iverilog/<run-id>/`。短测不替代生产几何或真板验收。

## C 单元测试（由 `run_sim.sh host` 调用）

`test_wm_expand.c`（PS 水印展开）、`test_ddr_layout.c`（DDR 分区校验）、
`test_task_config.c`（协议解析/CRC）、`align.c`（`bench_align.py` 的 C 对照实现）。

2026.1 本机 lwIP YAML 的 UTF-8 BOM 与 GBK 读取路径有实际兼容问题：先运行 `sw/scripts/prepare_vitis_compat_repo.py --vitis-root D:/xilinx/2026.1/Vitis --out-dir <新目录>`，再将目录填入现代构建 JSON 的 `embedded_sw_repo`。仅移除描述文件 BOM，保留原厂库源码 SHA 与 compat-manifest；不修改安装。完整命令和已测边界见 `docs/benchmarks/bkb220-toolchain-audit.md`。

性能矩阵可加 `--uart-log <外部持续追加的现有采集日志>`，记录本轮 Voter/Decoder 的原始硬件周期；不自动抢占串口。主机回归：`python3 -m unittest discover -s tests/host -p 'test_g3_*.py' -v`，涵盖制品/严格回退、CAPS 几何和网络探针显式 IP；这些替身测试不能替代板测。恢复、断网、配置守卫、性能矩阵和 overhead 探针均必须显式传实测 `--ip`。

Windows2026.1 正式 Stage1 XSim 输入由 tools/board/create_stage1_xsim_input.py 制作：先使用 generate_stage1_fixture.py --num-lc 50 生成oracle，再将生产RTL/TB/fixture复制为带14文件SHA的只读构建输入。`tools/run_stage1_xsim.ps1 -InputDir <带SHA的输入目录> -RunDir <新run目录>` 为Windows2026.1正式仿真入口；LC50模块/真实包装接口已通过，结果见 `docs/benchmarks/stage1-16way-ip-integration.md`。

## 新板执行前的旧平台风险（2026-10-10核对）

- 旧stress_test_suite.py/switch_export.sh已成对退出现用区并归档。新板长稳由main/verify围绕run_g3.sh --artifact-dir完整包、显式工具/目标/串口和现用故障探针编排；按实际运行时长判断2h/8h，保留逐轮证据，不自动切SE250或覆盖旧export。
- board/arm_baseline.py固定旧BSP/XSA/GCC/XSDB并复位整板；新板先适配，必须持板资源。
- run_multi_payload_regression.py的board模式及run_demo.sh主要发TCP任务，不下载/复位，仍须实际新板IP/固件/阈值确认；golden/check-dumps离线。
- run_robustness_scan.py的board_equivalent是软件模拟，不是新板证据；故障探针主动注入错误流量，不是只读健康检查。

完整命令、现状和失败分类见06/08，历史编号文档已归档，当前根文档收敛为9份。
