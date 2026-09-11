# tools/ 工具索引

> **为什么需要这份索引**：2026-09-10 卫生审计发现 `tools/` 下有 **7 个脚本零引用**
> ——不在任何文档、脚本或 CI 里出现。其中 `bench_align.py` 里存着「**精确种子法为何
> 在本任务中失效**」的实测反证，而 `docs/17` 因为看不到它，把种子索引列成了第一优先级
> 的长期方向（已于同日撤回，见 `docs/17` §5.1）。
>
> **一个无人可见的脚本，等于它得出的结论不存在。** 新增工具必须登记到本表。
>
> 本文件此前是 0 字节空文件。

---

## 一键入口（最常用）

| 脚本 | 用途 |
| --- | --- |
| `run_g3.sh` | **板级验收唯一入口**。烧录 → 下发任务 → LDPC → 比图片哈希 → 四级 DDR 取证。`--elf` 可换固件做对照实验（会降级同源性判据并打告警） |
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
| `g3_wait_ready.py` | 应用层就绪探针（CAPS 握手） |
| `g3_overhead_sweep.py` | 固定开销尺寸扫描与模型拟合。**必须 `post=True`**，`--no-post` 是「不发 POST 触发」，板子根本不算 |
| `g3_recovery_probe.py` / `g3_netfault_probe.py` | 畸变包 / 断网注入恢复探针 |
| `g3_config_guard_probe.py` | **配置/容量守卫故障注入**：手工拼 CONFIG 字节绕开客户端全部校验，直打固件守卫。2026-09-11 实测 **7/7 通过**：超容量/非 64 对齐/零条数均被 `rc=5` 拒绝，`read_bps=250` 被 `rc=2` 拒绝。⚠️ 注意 `PKT_CONFIG_OK` 只是应答，payload 里的 u32 **才是理由码，0 才是接受**——初版探针把拒绝当成接受，得出过错误结论 |
| `g3_runs_to_jsonl.py` | run 目录收敛成结构化 JSONL |
| `read_pipe_counters.tcl` | **不依赖串口**、用 XSDB 读固件内 poll 计数器。串口没接时固件的 `xil_printf` 插桩等于不存在 |

## 数据集与鲁棒性

| 脚本 | 用途 |
| --- | --- |
| `generate_payload_dataset.py` | D1 多 payload 独立数据集生成 |
| `mutate_reads.py` | D2 受控噪声 / D3 经验轮廓加噪 |
| `extract_error_profile.py` | D3 真实测序经验误差轮廓提取 |
| `run_multi_payload_regression.py` | 多 payload 泛化回归。`--repeat N` 做重复实验（写独立目录，**不覆盖已提交留证 dump**） |
| `run_robustness_scan.py` | G5 抗噪边界扫描 |
| `stress_test_suite.py` | 长时压测 |

## 性能与基准

| 脚本 | 用途 |
| --- | --- |
| `run_cpu_benchmark.py` | CPU vs FPGA 公平基准，MEASURED/HISTORICAL/ESTIMATED 三级分型 |
| `profile_host.py` | 上位机瓶颈剖析与端到端拆解 |
| `g3_timing_fit.py` | 从 `run_g3.sh` 的留证目录拟合「固定开销 + 每条成本」。**与 `board/g3_overhead_sweep.py` 功能重叠**：前者事后拟合既有留证，后者主动扫描并控制档位与重复次数；新测量用后者，回溯历史用前者 |
| `bench_align.py` | Stage1 的 CPU 侧基准，**并含「精确种子法为何失效」的实证**：读段与水印在最佳位置最长连续精确匹配仅 5~7 nt，16-mer 命中概率 ≈ 1.5e-05。**任何基于精确种子的索引在本任务中不可用**（见 `docs/17` §5.1）。⚠️ 会在**当前工作目录**写出 `ref.bin` / `reads.bin`，跑完记得清理 |

## 单点调试（按需，不进回归）

| 脚本 | 用途 |
| --- | --- |
| `debug_high_entropy.py` | 高熵样本失败五级分级诊断 |
| `debug_vote_diff.py` | 重算板端语义票值，与 TB 的 `dut.bram` 转储 diff |
| `vote_range.py` | 投票累加器运行中极值实测（回答是否会饱和溢出） |
| `voter_page_split.py` | Voter 读突发 4 KB 跨页拆分参考表（B20） |
| `board_stage_check.py` | 四级 DDR 取证比对（由 `run_g3.sh` 调用） |
| `m2_chain.py` / `m3_mem.py` | M2/M3 仿真辅助 |
| `extract_ldpc_dlls.py` | 从历史 `gui_app.exe` 提取 LDPC 缺失的 MinGW DLL（一次性历史工具） |

## 构建与制品

| 脚本 | 用途 |
| --- | --- |
| `run_vivado_build.sh` | Vivado 整机构建（日志不落仓库根） |
| `run_xsim.sh` / `run_m2_full.sh` / `run_m2_quick.sh` / `run_m3_bd.sh` | XSim 与多级串联仿真 |
| `switch_export.sh` | 切换 `hw/build/export/` 制品组 |
| `check_ip_packaging.sh` | IP 打包卫生门禁：hdl 内无 TB、同名模块只打包一个、引用文件存在、无孤儿、打包变体与清单一致、**打包的实现必须被回归覆盖**（已接入 `run_sim.sh`） |
| `check_repo_hygiene.sh` | 仓库卫生门禁：根目录残留、工具登记、文档编号、共享数据副本、`logs/` 的 `.gitignore` 覆盖（已接入 `run_sim.sh`） |

## C 单元测试（由 `run_sim.sh host` 调用）

`test_wm_expand.c`（PS 水印展开）、`test_ddr_layout.c`（DDR 分区校验）、
`test_task_config.c`（协议解析/CRC）、`align.c`（`bench_align.py` 的 C 对照实现）。
