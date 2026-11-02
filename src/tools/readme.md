# tools/ 工具索引

本目录只保留**复现与验收要用**的脚本；开发期的一次性实验脚本已从提交包中移除。
所有脚本以 `src/` 为工程根，可直接用相对路径运行。

## 仿真与验证

| 脚本 | 用途 |
| --- | --- |
| `tools/run_sim.sh` | Icarus Verilog 仿真总入口（RTL 回归、打包门禁、卫生门禁、主机测试） |
| `tools/check_ip_packaging.sh` | 校验 IP 封装的文件集合、VLNV 契约与生产 P-way 源码冻结 SHA |
| `tools/board_stage_check.py` | 四级逐级取证检查器（水印 / Stage1 / Stage2 / Stage3） |
| `tools/golden_model.py` | DNA 读出流水线的纯软件黄金参考模型 |
| `tools/readout.py` | 纯软件读出参考实现：滑窗相关 → 大数投票 → 差分 → 反稀疏化 |
| `tools/ldpc_decode.py` | 纯 Python DVB-S2 R=5/6 硬判决 Min-Sum 译码器（`verify` 自检随主机回归运行） |
| `tools/make_golden.py` | 由 `data/r083-data` 生成 `sim/golden/` 黄金向量 |
| `tools/make_stage1_tie_golden.py` | 生成 Stage1 比对「同分并列位置集」黄金向量 |
| `tools/vote_range.py` | 实测 Voter 累加器运行中极值，验证 10 bit 位宽是否足够 |
| `tools/test_ddr_layout.c` | DDR 镜像布局自检（随主机回归编译） |
| `tools/test_task_config.c` | 任务配置下发/拒绝路径自检（随主机回归编译） |
| `tools/test_wm_expand.c` | 水印展开自检（随主机回归编译） |

## 构建与打包

| 脚本 | 用途 |
| --- | --- |
| `tools/make_artifact_package.py` | 把 Vivado/Vitis 输出组装成 `run_g3.sh` 可用的完整制品包 |
| `tools/write_source_manifest.py` | 生成源码清单（相对路径 + SHA-256） |

## 板端验收

| 脚本 | 用途 |
| --- | --- |
| `tools/run_g3.sh` | **一键板端验收入口**：制品校验 → 烧录 → CAPS → 三层判据 → 四级取证 |
| `tools/board/g3_artifacts.py` | G3 制品包静态门禁（默认只读核验，`--stage` 才复制到新 run 目录） |
| `tools/board/g3_judge.py` | 复算 G3 的架构、系统与诊断判据 |
| `tools/board/g3_caps.py` | CAPS 几何验收规则 |
| `tools/board/g3_soak.py` | 长稳编排（按实际墙钟时长循环跑完整判据轮 + 恢复探针） |
| `tools/board/g3_recovery_probe.py` | 板端「断连 / 畸变包」恢复能力探针 |
| `tools/board/g3_config_guard_probe.py` | 板端配置/容量守卫的故障注入探针 |
| `tools/board/g3_netfault_probe.py` | 板端「任务中途断网 / 上位机崩溃」恢复探针 |
| `tools/board/g3_wait_ready.py` | 板端应用层就绪探针 |
| `tools/board/g3_boot.tcl.in` | 烧录用 XSDB Tcl 模板（由 `run_g3.sh` 渲染） |
| `tools/board/g3_dump.tcl.in` | DDR 导出用 XSDB Tcl 模板（由 `run_g3.sh` 渲染） |
| `tools/board/g3_xsdb.ps1` | Windows 侧 XSDB 桥接 |
| `tools/board/g3_uart_cap.ps1` | Windows 侧串口实录（端口须显式指定） |
| `tools/board/g3_uart_cap.py` | WSL 本地 USB-UART 只读采集器 |
| `tools/board/read_fw_build_id.tcl` | 从所选 ELF 解出 `fw_build_id` 地址并逐字节读回板上构建身份 |
| `tools/board/read_pipe_counters.tcl` | XSDB 只读本轮固件 ELF 中的 pipeline poll 计数器 |
| `tools/board/bkb220_f3_bringup.sh` | BKB220 F3 最小启动（UART / DDR）判据入口 |
| `tools/board/generate_stage1_fixture.py` | 独立生产 Stage1 oracle（逐符号滑窗评分） |
| `tools/board/create_stage1_xsim_input.py` | 把生产 RTL/TB 与 LC50 oracle 复制成带 SHA 的 XSim 输入 |

## 性能测量

| 脚本 | 用途 |
| --- | --- |
| `tools/board/g3_performance_matrix.py` | P4/P16 同板性能矩阵 |
| `tools/board/g3_upload_sweep.sh` | 读段上传段多档 × 多次扫描 |
| `tools/board/g3_overhead_sweep.py` | 板端固定开销尺寸扫描与模型重拟合 |
| `tools/board/g3_runs_to_jsonl.py` | 把 `run_g3.sh` 留证目录收敛成结构化 JSONL |

## 说明

- 原始逐轮/逐例日志不随包提交；结论与统计见 `report/design-report-2026.pdf`。
- 需要留证目录的参数（如 `run_g3.sh --win-root`）必须显式传入，脚本不提供外部默认路径。
- `bin/python3` 是 Git Bash 下的 Python 选择垫片，避免 Windows 商店占位符。
