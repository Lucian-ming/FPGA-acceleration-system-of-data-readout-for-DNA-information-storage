> 脱敏副本，原件 `20261012T111652Z-40a8ed6c3d/{prompt.txt,answer.md}`。本机绝对路径、邮箱、凭据形模式及非白名单私网 IP 已替换；除脱敏与换行规范化外保留原文。

## 静态审计结论

已完整读取指定的角色提示词、指南、文档和 README，并静态审阅目标脚本及 G3 fixture。**未写文件、未执行测试、仿真或板端操作**；下述负用例结论来自实现和测试定义检查，不是本轮重新运行的结果。阶段卡报告的 47 项主机用例 PASS 是既有结果。

当前 F3/F4 仍是**未测**：新板的 JTAG 系列和 FT4232 串口枚举已由阶段卡确认，但 PS UART 对应 COM、板端实际 IP 和完整器件料号仍未确认；Windows 主机网卡收到字节数为 0。文档中的 `bkb220.tcl` 仍是 `ready=0`，PS7、DDR、MIO、PHY 配置尚未形成可验收的新板包。不能把当前状态写成新板 PASS。

### A. 旧板和旧环境硬编码

| 入口及符号 | 当前值 | 新板应使用 | 忘记传值的结果 |
|---|---|---|---|
| [`tools/run_g3.sh`](<<仓库根目录><本机路径>>)：`ARTIFACT_DIR`、`ARTIFACT_EXPLICIT` | 默认 `hw/build/export`；未显式指定时自动加 `--allow-legacy` | P4/P16 完整新包目录，必须有 manifest | **会静默选旧 ECO 包**。若同时给 `--device xc7z020`，会因旧 XSA 器件不符而明确失败；默认正常烧录时旧器件筛选预计也会在新板 JTAG 上失败。若加 `--skip-boot`，仍可能对网络上的另一个服务运行，包与实板关系无法证明。 |
| 同上：`XSDB_VALUE` | `<本机路径>` | 阶段卡确认的 `<本机路径>` | 旧路径不存在时明确报找不到 XSDB；若旧工具仍存在，脚本只检查文件存在，**不校验 XSDB 版本**。 |
| 同上：`JTAG_DEVICE`、`--device` | 环境变量/命令行默认空，随后从选定 XSA 推导 | `xc7z020` 目标前缀；XSA 的 manifest 必须记录经核实的完整器件料号 | 对正确的 020 包显式传 `xc7z010` 会在 `g3_artifacts.validate` **明确拒绝**。省略时按 XSA 推导。正常烧录筛选 010 也不会匹配 020；`--skip-boot` 则绕过物理目标筛选。当前 XSDB 筛选是系列前缀，不能验证 020 的完整封装/速度级。 |
| 同上：`UART_PORT`、`--uart-port` | 默认为空，尝试自动唯一选择 USB/FTDI COM | 由 main 确认的实际 PS UART；候选是 COM9/10/11，尚未映射到 PS | 新板有三个 FTDI 候选，省略端口会因不唯一而明确失败。COM3/COM4 蓝牙及未枚举 COM 会被拒绝；但**任何当前枚举到的 USB/FTDI COM 都可能被接受**，脚本不能识别是否真是 PS UART。错误 FTDI 通道若能打开，`run_g3.sh` 只看见 `CAPTURING` 就继续，且串口失败可记为 `SKIP`，整体 G3 仍可能 PASS。 |
| 同上：`BOARD_IP`、`BOARD_PORT` | `192.168.1.10:7` | main 实测确认的板端 IP；端口 7 与当前协议相同 | 无服务时 CAPS 会明确失败；若旧板或其他相同固件服务在 `.10`，**可能测到错误板而通过**。Windows 主机 `.100` 不是已确认的板端 IP。固件 `sw/app/main.c` 也静态配置为 `.10`；若新板要用其他 IP，仅传客户端 `--ip` 不够，固件也须重建。 |
| 同上：`READS_FILE`、`WM_FILE`、`EXPECT_SHA`、`READ_BPS`、`LIMIT`、`SCORE_MIN` | D0 SE150 FASTQ、水印、给定图片 SHA、150、2048、67；`ORIENT=both` | 当前 SE150 P4 基线可沿用 D0；换数据集须同步传 FASTQ、水印和预期 SHA | 当前 D0 路径缺失会明确失败；换数据却省略参数会继续使用 D0。其他数据若仍用 D0 SHA 通常会明确哈希失败。 |
| 同上：`WIN_ROOT_VALUE` | `<本机路径>` | 新板专用、独立的留证目录 | 会静默沿用旧留证根目录；运行子目录带时间戳，但证据仍混在旧目录体系。 |
| [`tools/board/g3_artifacts.py`](<<仓库根目录><本机路径>>)：`LEGACY_FILES`、`--artifact-dir` | 旧文件名对应 `zynq-eco-7010-legacy`；独立调用时 artifact-dir 是必填 | 新包 manifest 指定的完整五类制品及精确完整 part | 直接漏传 `--artifact-dir` 会被 argparse **明确拒绝**；但 `run_g3.sh` 包装层有上述 legacy 回退。新包下器件/几何/架构校验较强；源码 manifest 的源文件哈希只检查格式和清单自身哈希，**不与当前源码树比较**。 |
| `g3_wait_ready.py`、`g3_recovery_probe.py`、`g3_config_guard_probe.py` | 三者均默认 `--ip 192.168.1.10 --port 7` | 实测板端 IP；端口 7 | 无服务时失败；同协议旧板可能通过。它们都不携带 artifact/device/profile 身份。`g3_config_guard_probe.py` 的 `READ_BPS=150`、`NUM_LC=50`、`STRIDE=807`、`WM_BITS=81000` 与新板 SE150 几何一致，但不鉴别 P4/P16。 |
| `g3_netfault_probe.py` | 默认 `.10:7`、D0 FASTQ/水印、150 bp、`score_min=67`、`limit=16384` | 实测 IP 与经确认的输入；仍是 SE150 数据 | 省略 IP 会打到旧地址；若同协议旧板在线，恢复 CAPS 可能通过。没有 package/器件参数；`task_entered_transfer` 只记入 JSON，未参与 PASS 裁决，故注入任务未真正开始时仍有误报恢复 PASS 的风险。 |
| `g3_performance_matrix.py` | artifact-dir 和 out-dir 必填；默认 D0 输入、150/50/807/957、67、both、`.10:7`；六档各 3 次 | 新板完整包、实测 IP；P4/P16 均是该 SE150 几何 | artifact 缺失会明确报错；**IP 漏传会静默测 `.10`**。它验证所选包，但不读板上已加载器件/架构/CAPS，也不下载，所以错误选择活动 P4/P16 可能仍产生被错误归属的性能结果。 |
| `g3_overhead_sweep.py` | 默认 `.10:7`、D0 输入、150、67、both、64…4096 源读段；固定 `post=True` | 实测 IP；若用于新板证据，还需绑定完整包和活动 profile | IP 漏传会继续用 `.10`；脚本没有 artifact 或 P_WAYS 信息，只产时间数据，不能据此归属 P4/P16。 |
| [`tools/board/g3_uart_cap.ps1`](<<仓库根目录><本机路径>>)：`PortName` | 直接调用默认 `COM6`、115200 | 实际 PS UART，波特率按当前固件核实 | 直接漏传会用旧 COM6。`run_g3.sh` 会传入所选端口，但错误的现存 FTDI 通道仍可能打开。 |
| `g3_xsdb.ps1` | `XsdbPath` 和 `TclPath` 都是必填，无旧路径默认 | 显式传 2026.1 XSDB 路径和本轮 Tcl | 漏传或路径不存在会明确失败；只检查存在，不核验版本和目标。 |
| [`tools/board/read_pipe_counters.tcl`](<<仓库根目录><本机路径>>)：`mrd` 地址 | `0x0021a2a4`、`0x0021af00`、`0x0021a2a0`，注释明确来自旧 B27 ELF | 从本轮选中 ELF 重新解析符号地址 | **无迁移参数**；新 ELF 地址改变时可能静默读到无关内存。 |
| [`tools/board/arm_baseline.py`](<<仓库根目录><本机路径>>)：`BSP`、`XSA`、`XSDB_BAT`、`WIN_ROOT_*` | 旧 `dna_platform_b27` BSP、`hw/build/export/dna_accel.xsa`、旧 Vivado Lab 2022.2 XSDB、`<本机路径>`；另固定 `RB=150`、`L=40500` 和 DDR 测试地址 | 新板同 XSA 的 BSP/PS7 init、实际 XSDB、经核实的 DDR 地址与几何 | **没有新板覆盖参数**。若旧文件在，可能以旧 `ps7_init` 对当前板执行 `rst -system`，不能试跑；缺旧工具/文件则明确失败。 |
| `run_demo.sh`、`run_multi_payload_regression.py` | 默认 `.10:7`；`run_multi_payload_regression.py` 默认模式是 `golden`，其板测数据配置均为 SE150 | 板测时显式 `--ip`、`--port 7` 和 `--mode board`；数据仍与当前 SE150 契约相符 | 漏传 IP 可能测旧地址；忘记 `--mode board` 会安静运行软件黄金模型。两者都不绑定 artifact/device/P_WAYS。`run_multi_payload_regression.py` 仅有任一数据通过时即可返回 0；`run_demo.sh` 场景不符只打印差异，末尾没有失败退出。 |
| `run_robustness_scan.py`、`g5_false_accept.py`、`run_g5_matrix.sh` | 都是主机侧模型/数据；默认基于 SE150/D0 或 D1，不连接板卡。`run_robustness_scan.py` 默认 `board_equivalent`，票值截断 `[-128,127]` | 只作为主机模型结果；若要新板 G5，另需真实板端输入、Stage1 dump 和板测流程 | 它们不会因新板 IP 自动去新板，结果不能记作新板 PASS。`board_equivalent` 名称容易造成误读；当前 RTL `safe_vote_value` 是 10-bit `[-512,511]`，与扫描器默认 8-bit 截断不一致。`g5_false_accept.py` 文档声称提供 `--cross-check-dump`，实际参数解析中没有该选项。 |
| [`tools/run_cpu_benchmark.py`](<<仓库根目录><本机路径>>)：`parse_board_log`、`get_theoretical_estimates` | 历史板测固定标注 `ZYNQ XC7Z010 / FPGA 2-way`；理论项固定 1/2/8-way 与 100 MHz，8-way 标注 Z020 | 新板 P4/P16 应从本轮 manifest/矩阵记录读取器件、架构和时钟；纯 CPU 测量另列 | 未传 `--board-log` 时只是宿主机 CPU 测量。传入新板日志会继续标成旧 Z010/2-way，日志解析不全时还可能回退到 2048 源读段、4096 记录、8.60 秒。`--include-estimates` 不表示 P4/P16 实测。 |

**器件判定简答：** 使用正确的 020 artifact 并显式传 `--device xc7z010`，会被包校验拒绝；不传 device 则从 XSA 推导 `xc7z020`，正常 boot Tcl 也按该前缀选目标。旧 legacy 包搭配 020 板会在正常 boot 的目标筛选处失败。`--skip-boot` 会跳过 JTAG 身份筛选，之后只靠 IP/CAPS/结果，不能排除连到同几何的错误服务。

**串口判定简答：** Bluetooth COM3/COM4 和未枚举的任意 COM 不会被 `choose_uart` 接受。COM9/10/11 都是当前候选 USB/FTDI COM，显式给错一个仍可能通过端口枚举及串口打开检查；必须先确认哪一个接 PS UART。

## B. F3/F4 判据清单

完整包应由 WSL 2022.2 构建主线产生，下载/调试按阶段卡使用 Windows 2026.1 XSDB。以下命令是运行模板，尖括号项必须由 main/board 用实物资料和现场地址替换。

| 阶段 | 入口命令 | PASS 判据 | 失败分类 | 证据 | 鉴别力 |
|---|---|---|---|---|---|
| 新板 P4 构建与完整包 | `VIVADO_ROOT=<本机路径> bash tools/run_vivado_build.sh board=bkb220 part_name=<经核实完整料号> clk_mhz=100 stage1_p_ways=4 stage1_pipe_tree=0 build_dir=<唯一build> export_dir=<唯一export> report_dir=<唯一report>`，再由 board 以同 XSA 重建 PS 软件并生成 manifest/SHA | 完整料号、SE150 `150/50/807/957/64`、P4 `4/0`；整机 route 满足 WNS/WHS≥0、TNS/THS=0、失败端点 0，DRC/路由/约束合法；包内 XSA/HWH/独立 bit/PS7/ELF/FSBL/BOOT 和 manifest 一致 | 工具启动/生成失败为 `tooling`；时序、几何、器件或制品功能不符为 `functional`；资料未齐导致 profile 仍 `ready=0` 属 `boundary_expected` | 独立 build/export/report；构建摘要、时序/DRC 报告、`manifest.json`、`SHA256SUMS`、XSA 和同源软件包 | 对构建产物及 HWH 参数有较强鉴别力；仍不能证明物理板料号或板上已运行该包。 |
| 包与命令预检 | `python3 tools/board/g3_artifacts.py --artifact-dir <P4完整包> --device xc7z020 --read-bps 150`；再用 `run_g3.sh` 加 `--plan-only` | 包内 SHA、XSA 的 JSON/HWH part、P4 参数、完整制品和工具版本通过；XSDB 路径存在 | 包字段、校验和或工具路径问题是 `tooling`；目标器件/参数不符是 `functional` | 命令输出 JSON；完整包自身 manifest/SHA | 只检查静态文件；`--plan-only` 不连接 UART/JTAG/IP，不能证实实板身份、串口映射或网络。 |
| F3 唯一 JTAG、UART、DDR、GEM/CAPS 最小启动 | 当前没有独立 F3 最小启动/DDR 测试入口。可用的 CAPS 探针为 `python3 tools/board/g3_wait_ready.py --ip <实测板IP> --port 7 --deadline 90`，但须先由 main 完成启动；串口采集由 `run_g3.sh --uart-port <确认的PS COM>` 启动 | JTAG 仅一个目标且为 020 系列；UART 有可解释的板端启动/网络日志；DDR 安全区读写及容量检查通过；GEM 联通；CAPS 精确等于 `version=1, read_bps=150, num_lc=50, stride=807, max_symbols=40500, max_reads=129600, features bit0=1` | XSDB/串口工具错误为 `tooling`；无链路/CAPS 为 `communication`；DDR、CAPS 参数错误为 `functional`；profile 资料缺失是 `boundary_expected` | `uart.log`、XSDB/JTAG 输出、DDR 测试原始读写及摘要、CAPS 响应 | 目前 `g3_wait_ready.py` 只确认 CAPS 包格式/响应，不验证上表几何或器件。`tests/board/test_g3_wait_ready.py` 的假板以错误几何值也期望 READY，直接说明它不是几何判据。仓库没有独立 DDR 安全区检查证据入口。 |
| F4 P4 2048 smoke | `bash tools/run_g3.sh --artifact-dir <P4完整包> --xsdb <本机路径> --device xc7z020 --uart-port <实际PS COM> --ip <实测板IP> --win-root <独立留证根> --limit 2048 --read-bps 150 --score-min 67` | 默认 `both` 将 2048 源读段变为 4096 条板端记录；CAPS、任务、LDPC、图片 SHA `fcd0cf90bd680e7bbdc203e3398119504da0897acac9e2117008b4efb6b1f2c3` 和四级取证通过 | 无 CAPS/TCP 为 `communication`；错误固件/DDR/阶段结果/哈希为 `functional`；XSDB/串口启动异常为 `tooling`；D0 smoke 不应按已知边界放行 | G3 run 目录的 `artifact_selection.json`、`boot.out`、`wait_ready.out`、`first_run1.log`、`dec_input_run1.txt`、LDPC/JPEG、DDR dump、`stage_check.log`、`summary.txt` | 若默认实际 boot 且 IP 确是本板，数据端到端鉴别力较强。图片 SHA 不辨 P4/P16；错误 IP、`--skip-boot`、同几何旧板仍可能通过。UART 采集可 `SKIP`，G3 总体仍可能 PASS。 |
| F4 P4 全量 | 在 smoke 命令基础上改为 `--full --runs 3 --result-timeout 1800` | 三轮均完成，最终图片 SHA 相同；检查四级 DDR 和全量输入记录数 | 同上；全量 D0 SHA 或四级数据不符必须是 `functional` FAIL，不能归为边界 | 每轮 G3/LDPC/JPEG/D0 SHA、最后一轮 DDR dump、`summary.txt` | 对当前 D0 全链正确性有强鉴别力；运行摘要不记录 FASTQ/水印 SHA，也不证明板身份和 P4/P16 实际活动状态。 |
| 连续与状态复位 | `bash tools/run_g3.sh ... --runs 3 --run-limits full,2048,full --run-score-mins 0,67,67 --result-timeout 1800` | first dirty、后两轮判据；判据 SHA 正确，dirty 前后原始回传不同且状态无退化 | 恢复功能错为 `functional`；连接中断为 `communication`；脚本/XSDB 失效为 `tooling` | 三轮原始 bits、每轮日志/哈希、dirty 判据、连续耗时 | 比单轮强，但不能弥补错误 IP 或 P4/P16 活动包未核实。 |
| P4 性能基线（按 05/07 计划，正式矩阵归 F7） | `python3 tools/board/g3_performance_matrix.py --artifact-dir <已加载P4完整包> --out-dir <全新目录> --limits 128,512,2048,8192,32768,full --repeat 3 --ip <实测板IP>` | 每档至少 3 次；全量 D0 LDPC/SHA 正确；报告中位数、离散、斜率/截距 | 时间异常/全量哈希不符为 `functional`；无服务为 `communication`；输出目录/输入错误为 `tooling` | `plan.json`、`samples.jsonl`、client/LDPC 日志、`summary.json`，含输入 SHA | 输入 SHA 有记录，但矩阵不烧录、不核对活动包，也不查询 P_WAYS；若 main 未先确认加载 P4，可能把 P16/P4 数字标错。 |

**判据边界：** F3/F4 的 D0 任务预期不属于 `boundary_expected`。小样本泛化/噪声实验可按覆盖度报告边界；故障注入探针只有“确实注入、板端拒绝且随后恢复”才可归 `fault_injection_expected`，不能当普通 G3 PASS。

### C. 需要改代码 vs 只需运行期传参

**只需运行期传参（前提是新 profile、完整同 XSA 软件包和现场映射已验证）：**

- `run_g3.sh`：显式传 `--artifact-dir`、`--xsdb <本机路径>`、`--device xc7z020`、经确认的 `--uart-port`、实测 `--ip` 和新 `--win-root`。P4 用 SE150 默认数据时 `--read-bps 150 --score-min 67`；D0 输入和 SHA 可沿用。
- `g3_artifacts.py` 本身能接受符合格式、准确记录完整料号和参数的 020 包；无需因芯片系列从 010 换 020 而改解析器。
- 网络探针的 IP/输出目录，以及 `run_multi_payload_regression.py` 的 `--mode board --ip ... --port 7`。现有 D0/D1 输入都是 SE150；协议几何与 P4/P16 相同。
- 若 main 已确认 PS UART 的具体 FTDI 通道，`run_g3.sh --uart-port COMx` 可选对端口；但这不能用候选列表替代现场映射。

**若这些工具要承担新板验收证据，则需要代码/门禁调整：**

1. `run_g3.sh`：BKB220 路径应拒绝默认 legacy artifact 回退；运行摘要记录 FASTQ/水印 SHA；UART 捕获应检查实际启动/网络标记，关键验收不能把串口 `SKIP` 当作可接受 PASS。
2. `g3_wait_ready.py` 与公共网络探针：要求显式 IP，记录 artifact/profile 关联，并核对 CAPS 全部几何字段。现有 CAPS 没有 P_WAYS/PIPE_TREE，单靠 TCP 不能证明正在运行 P4 还是 P16；性能矩阵须有受控的已加载包证据或增加可查询的架构字段。
3. F3：新增独立最小启动判据，至少包含经板卡配置确认的 DDR 安全区读写、UART 内容、GEM/CAPS 精确几何。当前 `arm_baseline.py` 不可替代，它复位整板并使用旧 PS7 init。
4. `read_pipe_counters.tcl`：由本轮 ELF 符号动态解析地址，避免旧绝对地址静默误读。
5. `arm_baseline.py`：接受新板同源 XSA/BSP/PS7/XSDB/DDR 区域，并核实 part/profile 后才能复位和测量。
6. `g3_overhead_sweep.py`、`g3_performance_matrix.py` 和故障探针：写入实际目标、包 manifest SHA、P4/P16、输入 SHA；当前网络层不能自证其连到的 IP 就是刚由 XSDB 编程的器件。
7. `run_demo.sh`/`run_multi_payload_regression.py`：如用于验收，任一指定场景失败须非零退出；`run_demo.sh` 当前 mismatch 只打印，`run_multi_payload_regression.py` 有任一项通过时可返回 0。新增 artifact/profile 元数据才能把结果归到新板包。
8. `run_cpu_benchmark.py`：更新历史板测身份解析；避免把 BKB220 记为 XC7Z010/2-way，也避免用现有 1/2/8-way 理论表代替 P4/P16 新板数据。`g5_false_accept.py` 的 dump 交叉核对文档选项缺实现；真实板 FAR 仍需独立证据路径。`run_robustness_scan.py` 默认 8-bit 截断也应在任何硬件等价声明前修正或降低表述。

**几何/P_WAYS 方面的实际边界：** 新板目标仍是 SE150 `150/50/807/957/64`，所以旧脚本的 SE150 数据几何本身与新板目标一致；主要缺口是它们不记录或不验证实际 P4/P16。`g3_artifacts.py` 是列表中唯一显式检查 P4 `4/0` 与 P16 `16/1` 的入口。网络型工具、`run_demo.sh`、多 payload、overhead sweep 和 G5 脚本都不能靠输出区分 P4/P16；CPU benchmark 仍标旧 Z010/2-way。`tools/README.md` 把 overhead sweep 描述为新测量入口，而 05/07 将新板同板六档矩阵交给 `g3_performance_matrix.py`，应由 main 统一当前入口说明。

### D. G3 fixture 负用例现状与缺口

| 类别 | 当前校验/fixture | 新板相关缺口 |
|---|---|---|
| 错 part/目标 | `g3_artifacts.validate` 对 manifest part 与 XSA JSON/HWH、显式 `device` 与 XSA 检查；测试含 `test_wrong_target`、`test_part_manifest_mismatch`、`test_legacy_z020_refused`。020 正向 fixture 已用 `xc7z020clg400-2`。 | **显式错误 device 会拒绝**，但 `run_g3.sh` 无 artifact-dir 时 legacy 默认路径反而有 `test_plan_legacy_default` 验证为可通过。缺少“BKB220 验收模式必须拒绝 legacy 默认包”的负用例；也没把 `board_id=bkb220` 与经核实完整 part 绑定。 |
| 错几何 | XSA HWH 和 manifest 的七参数须一致，且 SE150/SE250 几何受限；`test_wrong_geometry_self_consistent` 证明 manifest/HWH 自洽的 LC6 也会被拒绝。 | 这是 host fixture 的包内几何校验，不证明烧录后的板子真的运行该包。 |
| 缺制品 | `bundle_path` 会拒绝不存在的文件；`test_missing_xsa` 确认 XSA 缺失会拒绝。manifest 缺必需制品键的校验在实现中存在。 | fixture 只实际覆盖缺 XSA；没有逐类覆盖缺 bit/ELF/FSBL/BOOT 或 manifest 缺 artifacts 键。 |
| SHA 不符 | `test_hash_failure`、`test_missing_hash_entry`、`test_embedded_bit_mismatch` 分别覆盖 ELF 校验失败、校验表缺项、独立 bit 与 XSA 内 bit 不同。 | 这些证明制品包内部哈希/一致性，不证明制品是由当前源码编译。 |
| manifest 缺字段 | 实现检查 `schema_version`、`artifacts`、`source_manifest`、`tool_versions`、`board_id`、参数；fixture 覆盖缺 P_WAYS、缺 Vitis 版本及若干 malformed manifest。 | 未直接覆盖缺 `schema_version`、`board_id`、`source_manifest.path/sha256`、`artifacts` 键等拒绝分支。 |
| 非法 P16/组合 | `test_wrong_architecture_self_consistent` 用 P16/0 组合并期望拒绝；实现只允许 P4/0 或 P16/1。 | 没有 P4/1 的专门负用例，也没有 P4/0 正向 fixture；当前 `test_valid` 正例是 P16/1。 |
| 源码与制品不同源 | 实现验证 source manifest 本身在 `SHA256SUMS` 内、字段是合法路径和 SHA 格式。 | 不把 `source_manifest.files` 的摘要与当前 checkout 比较，也不验证构建日志因果关系；源码到制品不同源仍可能包内自洽。 |

## 未完成项

- 本轮没有执行 fixture 测试或真实板测；上表“当前拒绝”是实现和 fixture 定义层面的静态核对。
- COM9/10/11 中哪个是 PS UART、实际 BKB220 board IP、完整 part 料号、PS7/DDR/GEM 配置仍需 main/board 现场确认。
- 仓库没有独立 F3 DDR 安全区读写与完整几何 CAPS 判据；需要由 main/board 补入口后才能声称 F3 完成。
- 未知 IP 不应从 Windows 主机 `.100` 推断；当前客户端默认 `.10` 与固件静态配置相符，但阶段卡所报 `ReceivedBytes=0` 不证明板端正在响应。
- 未检查或确认活动 P4/P16 包与各次性能/故障运行一致；TCP CAPS 不暴露 P_WAYS/PIPE_TREE。
