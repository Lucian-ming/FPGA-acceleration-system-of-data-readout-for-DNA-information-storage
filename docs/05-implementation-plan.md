# 05 · 全项目执行计划与多Agent运行手册

更新时间：2026-10-11。本文把项目地图、文档/脚本入口、从当前准备成果到新板交付的完整流程、子Agent分工和监控收敛放在同一入口。用户已明确授权本批代码与文档提交推送，并要求整理工作区。详细任务提示词在[agent-prompts/](agent-prompts/README.md)。

## 1. 全项目地图与事实优先级

唯一checkout：`/home/lucian/projects/FPGA/FpgaAccelerationSystemOfDataReadout`，Windows访问为`\\wsl.localhost\Ubuntu\home\lucian\projects\FPGA\FpgaAccelerationSystemOfDataReadout`。唯一远端：`Lucian-ming/FPGA-acceleration-system-of-data-readout-for-DNA-information-storage`，只在main开发，主Agent是唯一Git写入者。

项目的编码侧不在本仓库：54000 bit信息→64800 bit LDPC→81000 bit稀疏流→水印XOR→40500 nt。读出侧包含PC FASTQ处理、协议、PS控制/DDR/cache/DMA、三段PL、PS Stage2.5 XOR、PC LDPC与图像哈希。它包含多种载体，不能把全部计算都称为PL。

| 组件 | 权威入口与应理解的内容 | 接手风险 |
|---|---|---|
| 数据/算法 | 02、data/MANIFEST.md、tools/golden_model.py、readout.py、make_golden.py；碱基A/T/G/C=0/1/2/3，位平面、5b4b码表、LSB位序 | 历史演示水印不同；原始D0不修改、不随意分发 |
| PL Stage1 | hw/ip/Dna_accelerator_core_1_0/component.xml、hdl顶层及两个正式batch核、XGUI、PACKAGED_VARIANTS.txt | 正式模块名srpe_batch4/srpe_batch_pway；实验目录候选不等于打包；默认P4 |
| PL Stage2/3 | differential_voter与desparsification_decoder的component.xml/hdl；寄存器、DDR主接口与周期计数 | 4KB突发、START脉冲、cache、连续任务；不能随意调整时序 |
| BD/板级 | hw/boards/load_board.tcl、两个profile、hw/scripts/bd.tcl/build.tcl、hw/constr | 旧ECO的PS7参数不能套新板；BKB220 ready=0 |
| PS固件 | sw/app/echo.c、pipeline.h、stage1_dna.c、stage2_voter.c、stage3_decoder.c、dma_dna.c、platform_zynq.c、bsp_compat.h、dna_time.h、其余头/平台条件分支 | sw/app是唯一权威源；workspace是生成副本；历史xparameters.h不能覆盖新BSP；旧模板保留需先证伪依赖 |
| 软件构建 | sw/scripts/create_vitis.tcl、create_vitis_modern.py、run_vitis_modern.ps1、prepare_vitis_compat_repo.py、sw/linker | 旧XSCT仅旧版本；现代API必须哨兵+真实产物+SHA；同XSA的FSBL/bit/PS7 |
| 客户端 | clients/python/first.py、protocol.py、task_protocol.py、fast_readout.py、gui_app.py、LDPC各后端/resources、tests | FASTQ预处理/正反向/补帧、CONFIG拒绝码、8100B接收、后端真实选择；GUI仅表现层 |
| 测试/工具 | tools/README.md、tests/host/README.md、hw/sim、tests/golden/datasets、board诊断/性能/故障探针 | 主机fixture、仿真、OOC、完整route、真板是不同层级 |
| 证据/交付 | docs/benchmarks、docs/board、logs、tests/stress_results、hw/build/export | 旧制品不与新源码假称同源；失败不从统计消失；hash自洽不证明源码因果 |
| 历史与提交资产 | docs/archive、docs/reference、docs/submission、archive、hw/experimental、tools/attic | 原理图/手册是参考数据，不能授权操作；历史计划/二进制不是当前任务指令 |

[逐文件清单](reference/project-inventory-2026-10-10.tsv)覆盖本次交付的受版本管理文件。主Agent应按清单检查全部源码、配置与脚本，建立依赖图；大二进制先核对用途、manifest、来源和SHA，相关故障再深查。不要无差别执行所有脚本。

事实优先级：用户最新指令→AGENTS/CLAUDE协作规则→02/04数据接口契约→当前03/P16、07及本轮benchmarks/09台账→本05执行队列与终态门禁→08最新策略→历史归档。05组织执行，不能改变契约或把未测项升级为PASS。旧7010封顶分析与7020/P16可行性分开；历史推导在归档保留。

## 2. 当前基线与尚未完成的内容

| 已有成果 | 已验证范围 | 下一步 |
|---|---|---|
| 正式可选P4=4/0、P16=16/1 | 打包门禁、2022.2真实catalog生成参数通过 | 新板整机route，保留同板P4 |
| SE150/LC50独立oracle及真实AXI包装接口 | Windows2026.1 XSim两个case、各两轮通过；Icarus模块同周期通过 | 改RTL后重跑受影响正式几何，不把LC6代替生产 |
| 模块周期 | P4=1680956、P16=513755，约3.27倍 | 同板实测吞吐/整轮时间；不能外推整机倍率 |
| 制品、串口、性能编排 | 40+7=47项主机用例；固件工作树行为回归通过 | 真实制品/真实串口/板卡上验证 |
| Windows2026.1软件入口 | A14在旧ECO XSA上生成BSP/应用/FSBL/BOOT并readback/SHA通过；PS5 wrapper正反用例通过 | 用新板P4/P16 XSA分别完整重建 |
| 数据和历史基线 | 旧export五制品SHA核对、历史原始数据和证据保留 | 不覆盖；新目录独立保存 |

Icarus LC50接口重复长测在XSim正式接口已通过后主动停止，日志标记INTERRUPTED_DUPLICATE_AFTER_XSIM_PRODUCTION_PASS；不是Icarus接口PASS。旧BSP下13个C文件编译通过，但临时旧链接探针因Newlib/VFP ABI失败，不能称旧工具链完整重建。起点参赛agent_view.sh重复附件已改为引用tools唯一源码解决，旧失败日志及附件Git历史保留，未放宽门禁。

硬件阻塞：当前只读枚举只有蓝牙COM3/COM4，没有FTDI/JTAG；缺对应PCB原理图、PS7 preset/board_files/原厂例程及实物完整料号。Windows Vivado/Vitis为2026.1，WSL Vivado为2022.2。手册的存在不能消除PS7配置依赖。资料未齐之前BKB220保持ready=0；不能猜DDR/MIO/PHY/时钟、复位未知设备或把USB调试误当整板供电。

## 3. 全流程计划与出口门禁

| 阶段 | 工作、负责者和输入 | 交付与出口门禁 |
|---|---|---|
| F0 接管与全貌冻结 | main读取清单及当前文档，核对仓库/HEAD/脏文件/工具/设备；三Agent各审计负责区域 | 现场摘要、依赖图、逐文件归属、最新执行计划、资源表；先写计划再改代码 |
| F1 已有成果确认 | main对照07和三个benchmark；子Agent复核源集、API/制品、测试边界 | 必要短检查通过；已有长测来源可验证，不无故重跑；已知失败和阻塞有记录 |
| F2 新板配置落实 | board收集实物/原厂PS7及原理图；main给实际供电/USB/网线明确要求；verify核对工具目标 | PCB/完整part/DDR时序、PS时钟、UART MIO、GEM/PHY/reset、启动配置、XDC及source_refs表；获得可靠配置后才ready=1 |
| F3 新板最小启动 | board准备最小同XSA软硬包；main持板卡锁运行；verify协助留证 | 唯一JTAG目标、实际PS串口、UART、DDR训练/安全区读写、容量、GEM链路、CAPS；失败先定位单项，不直接跑全系统 |
| F4 新板P4基线 | board完整生成SE150/P4/100MHz整机和现代软件包；rtl审查路由；main/verify执行板测 | route/DRC/约束合格；完整manifest通过；2048源读段、全量、四级DDR、最终SHA通过；冻结P4制品/输入/性能基线 |
| F5 P16整机候选 | rtl审查正式P16依赖和关键路径，board按同板profile生成独立目录；改动按层级回归 | 150/50/807/957/64及16/1贯通；LC50真实接口PASS；WNS/WHS≥0、TNS/THS=0、失败端点0、DRC和路由合法、100MHz；完整新XSA软硬包 |
| F6 P16正确性与工程回归 | main持板卡/串口，verify编排；先smoke再全量，再连续和故障恢复 | 全量≥3次哈希相同；full→2048→full及脏轮→干净轮通过；配置拒绝/断连/超时→正常任务恢复；不只靠一次下载PASS |
| F7 性能与泛化复核 | verify同板P4/P16六档≥3次矩阵；board提供合法完整包；main审核公平口径 | 128/512/2048/8192/32768/full输入一致、补帧记录数明确；中位数/离散程度/斜率/截距；全量LDPC和SHA必须PASS；至少5独立payload复核与受控噪声边界，旧结果注明旧板 |
| F8 长稳与剩余终态门禁 | verify逐项重核本计划的G0～G8；main安排可用设备 | 建议先2小时新板连续观察，稳定后8小时长稳；异常分类/恢复证据；有功率计才测闲置/任务功率与能耗；无仪器写未测。SE250另制品/另几何，本次16路SE150不能冒充支持 |
| F9 独立复核与最终交付 | main冻结代码和制品；verify独立重跑复现入口；所有Agent交接后停止写入 | 完整BKB220/P16新板验收摘要、源码/参数/版本/制品/SHA链、可复现命令、限制、03/05/07/09更新、提示词同步；按路径commit后立即push、0/0、源码工作区干净 |

F2缺资料不会阻塞F0/F1、测试和文档准备；F3～F8真板部分按依赖等待。当前已完成的是F1的一批准备检查和本轮整理交付，F2～F8不因写好脚本而关闭。若P16无法合法100MHz，保留失败报告并从实际路径修改或回到已验P4，不用无依据false path或降低频率宣布目标达成。

原迁移计划S2～S4对应F2～F8的新板核心门禁，S5对应F9。原13的G4/G5/G6历史成果要在新板候选上复核相关接口与正确性；G7独立复现仍受D0数据分发边界约束；G8材料制作只按用户需要进行。32路、Linux/PetaLinux、USB数据传输、HDMI、算法重写不纳入本轮。

### 总项目G0～G8终态门禁（保留原13门禁，当前进度重新核对）

| 门禁 | 在新交付中的判据 |
|---|---|
| G0 冻结与基线 | 源码/输入/板/profile/工具/制品可追溯；本轮SE150，SE250单列 |
| G1 统计可靠 | 时间边界/失败分类/重复数/分母一致，原始数据可重算 |
| G2 客户端/传输 | 协议/LDPC/结果完整，性能优化有公平测量，未引入断连/错误码回归 |
| G3 Stage1 | P4同板基线、P16正式功能/接口/整机100MHz/新板G3与性能，不以OOC替代 |
| G4 泛化 | 至少5独立payload，源文件哈希和恢复判据；旧板数据与新板复核分开 |
| G5 鲁棒 | sub/ins/del/覆盖度/阈值曲线、FAR/FRR定义、种子与失败，明确主机/板测范围 |
| G6 工程/功耗 | 冷启动项目单列、全量/连续/脏干净/故障恢复/长稳；有仪器才给功耗 |
| G7 冻结/独立复现 | 同源制品/脚本/manifest、独立复查；D0数据分发边界如实保留 |
| G8 报告/演示/交付 | 最新事实、限制、复现与提交同步；正式材料和发布按用户需要 |

既有负结果可关闭某个优化方向，不能替代产品正确性；旧候选池仅作追溯，不并行开展被证伪方向。

## 4. 子Agent分工、并发与监控

最多main+三子Agent同时运行；后续交接按用户在3ad6fbd确定的通道：主会话为Claude Code/DeepSeek（deepseek-flash[1m]），子Agent经用户级 codex-luna MCP 非交互进程（`codex_run`/`codex_status`）派发，固定 gpt-6-luna 与 model_reasoning_effort=max，不用Claude内置Agent工具，不自行换模型/强度、不再派生子Agent，不新建聊天/分支/worktree。各角色完整输入由角色提示词+最新阶段卡组成，启动模板在[main提示词](agent-prompts/main.md#cli派发模板)。

main已于2026-10-11从WSL登录环境通过只读通道冒烟：经host-proxy http://127.0.0.1:17897，gpt-5.6-luna/max，退出0、turn.completed及JSON哨兵；日志在logs/agents/handoff-channel-20261011-a2。用户安排的通道更新已独立提交为b3c70b3。接管先核对实际CLI路径/版本、代理监听和冒烟；gpt-6-luna 的可用性已由 2026-10-11 00:40 的 codex-luna MCP 实测确认可用（客户端 0.162.0-alpha.17.2），旧的「此CLI/账号组合不支持」结论作废（更正提交25c3336）；不凭缓存或别的宿主能力判断。凭据/代理服务由配置会话管理，本FPGA任务不擅改配置或关闭其服务。失败时main接管可推进项，不假称派发成功。原三实现子Agent额度中断后main已接管；本次gpt-6-luna原生审计助手是后来模型规则生效前的实际历史记录，未来派发统一使用上述CLI规则。

| 角色/看板名 | 独占文件 | 输入、输出、依赖 |
|---|---|---|
| main | README、docs根目录/索引/证据/交接、agent-prompts、.gitignore；唯一Git写入 | 全项目理解报告、阶段计划、派发/监控/审查、资源调度、真板操作、远程交付 |
| board-migrate | hw/boards、hw/constr、hw/scripts/bd.tcl/build.tcl、tools/run_vivado_build.sh、sw/scripts、sw/app、sw/linker；独占板级摘要 | 当前板级入口/旧ECO配置、原厂资料；输出可审计profile、同XSA完整制品、SDT/旧BSP兼容和软件测试报告 |
| rtl-16way | 三IP的相关RTL/component.xml/XGUI及PACKAGED_VARIANTS.txt、tools/check_ip_packaging.sh；独占RTL摘要 | 正式P4/P16代码和独立TB接口；输出源集一致性、参数、修复及综合/时序诊断。大型任务须main授权资源 |
| verify-system | hw/sim、tests、tools/board、run_sim.sh/run_xsim.sh/run_m2*/run_m3*、run_g3.sh、性能/泛化/故障/压测入口；clients/python仅必要迁移测试修复；独占验证摘要 | 生产参数/寄存器契约、板级完整包；输出独立判据、负用例、板测和矩阵报告，明确测试层级 |

按wave派发：F0/F1三Agent可并行审计；F2期间board整理资料、rtl评估源/时序风险、verify准备矩阵与故障脚本；F3/F4主要board/main执行，另两人静态审阅；F5只允许一个综合/XSim长任务；F6～F8只有一位板卡操作者，其他人分析已完成run；F9全部停止写入后main收敛。

共享文件修改必须先向main申请具体移交；main记录旧owner、新owner、路径和停止写入确认。board持有sw/app后main不同时改固件。RTL参数/模块端口/几何变更先通知verify和board，先更新契约再消费，不能各取一套名字。

资源表至少记录`resource/owner/purpose/PID或session/开始时间/run目录/释放条件`。资源包括Git、Vivado/XSim大型任务、真实板卡/JTAG、PS串口、下载/DDR dump、发布export。Git恒归main；同一时刻最多一个大型EDA任务、一个真实板任务、一个串口采集进程。下载、reset、halt、dump会影响正在运行的任务，都需要板卡资源。

main的监控循环：派发时附角色完整提示词、独占路径、阶段卡及检查点；每个检查点读取CLI events.jsonl/final.md、看板和diff，核对日志增长/PID/退出码/哨兵与资源表；宿主支持事件等待时使用事件等待，避免忙轮询。非交互CLI不提供原生Agent消息工具，改任务需阶段停写后重新附卡派发。每10～15分钟或阶段变化核查进度，不能仅靠Agent说“正在跑”。长工具等待分段≤60秒，持续向用户说明新结果或阻塞。

发现Agent退出、额度限制或长期无日志增长：核对实际子进程/文件写入者，停止重叠派发，保存证据，移交未完成项；必要时由main接管。只终止本任务核实过的PID树，不杀全局同名进程。Git操作前要求全部writer停写并确认，不能以看板状态替代实际检查。

每个Agent以tools/agent_view.sh登记start/update/block/done，三个字段具体；禁止手改view.md。退出交接提供路径/diff、实际命令和退出码、参数/输入SHA/run-id、PASS/FAIL/未测、失败证据、资源释放和下一依赖。

## 5. 验证入口与判据的鉴别力

| 层级 | 入口 | 判据和边界 |
|---|---|---|
| 仓库/打包/卫生 | verify_repo_binding.sh、check_ip_packaging.sh、check_repo_hygiene.sh | 正确远端main；正式源集一致。重复附件通过唯一源引用解决，旧失败日志保留，门禁未放宽 |
| 算法契约 | `python3 tools/golden_model.py verify-code` | 使用本地只读D0，数据/编码模型正确，不代表真板 |
| 固件行为 | `bash tests/host/run_host_tests.sh --worktree` | 真实工作树C源码的寄存器/DMA/cache/TCP轨迹；默认HEAD测试不能替代未提交工作树 |
| 主机门禁 | `python3 -m unittest discover -s tests/host -p 'test_g3_*.py' -v` | 缺manifest/错part/错几何/SHA/版本、串口歧义、矩阵失败保留等负用例 |
| Stage1短/正式 | run_sim.sh stage1_production / stage1_production_full、run_stage1_xsim.ps1 | LC6排错；LC50生产；独立oracle+P4/P16两轮、末组/并列/补帧/反向、AXI真实包装 |
| 三级/BD | run_xsim.sh all、run_m2_full.sh、run_m3_bd.sh | 源码修改涉及接口时跑受影响层级；黄金几何/当前源集一致 |
| 构建 | run_vivado_build.sh、现代Vitis入口 | 完整route/DRC/约束，实际XSA/BSP/ELF/FSBL/BOOT，成功哨兵+六制品SHA |
| 制品选择 | `python3 tools/board/g3_artifacts.py --artifact-dir <完整包>` | XSA内bit/part/HWH七参数、源码manifest、工具版本、SHA一致 |
| 真板唯一入口 | `bash tools/run_g3.sh --artifact-dir <完整包> ...` | 实际下载/任务/LDPC/最终SHA/四级DDR；禁止旧bit与新ELF混用 |
| 性能 | tools/board/g3_performance_matrix.py、run_cpu_benchmark.py、arm_baseline.py | 前者不自动烧录，先确认已加载同一包；ARM工具会复位整板，当前硬件假设先审计 |
| 泛化/故障/长稳 | run_multi_payload_regression.py、run_robustness_scan.py、g5_false_accept.py、run_g5_matrix.sh、board的guard/recovery/netfault、stress_test_suite.py | 先审计旧脚本的硬编码export/设备/几何，使其消费完整新板包后才运行；禁止直接用legacy自动切SE250 |

任何新修复必须有能失败的判据：错误part、缺制品、非法P16组合应明确拒绝；已知START故障注入应变红；完整输入译码/图片失败必须保留并使功能门禁失败。小规模覆盖不足的译码失败不冒充整机故障，也不算完整正确性PASS。禁止为了全绿重录黄金轨迹或改成比较实现本身。

正式XSim复现（RUN_ID自行选未使用值，输出目录必须全新）：

```bash
python3 tools/board/generate_stage1_fixture.py --num-lc 50 --out-dir logs/iverilog/<RUN_ID>/fixtures
python3 tools/board/create_stage1_xsim_input.py --fixtures-dir logs/iverilog/<RUN_ID>/fixtures --out-dir /mnt/d/Agent/outputs/bkb220-xsim26/<RUN_ID>-input
```

Windows PowerShell用权威脚本或带SHA的脚本快照：

```powershell
& '\\wsl.localhost\Ubuntu\home\lucian\projects\FPGA\FpgaAccelerationSystemOfDataReadout\tools\run_stage1_xsim.ps1' -InputDir 'D:\Agent\outputs\bkb220-xsim26\<RUN_ID>-input' -RunDir 'D:\Agent\outputs\bkb220-xsim26\<RUN_ID>-run'
```

软件JSON必填`repo_root/workspace/xsa/export_dir/uart/board_id/part/bootgen`，可选`embedded_sw_repo`。uart来自实际BSP/profile，不能照抄旧UART1。BOM兼容脚本仅创建库副本，不修改安装。软件wrapper参数为`-Config/-Vitis/-LogDir/-Script`，完整命令及A14证据见[工具核查](benchmarks/bkb220-toolchain-audit.md)。

新板资料确认后才运行以下模板；尖括号都是待填值，不能照字面执行：

```bash
VIVADO_ROOT=/tools/Xilinx/Vivado/2022.2 bash tools/run_vivado_build.sh board=bkb220 part_name=<实物确认part> clk_mhz=100 stage1_p_ways=16 stage1_pipe_tree=1 build_dir=<独立目录> export_dir=<独立制品目录> report_dir=<独立报告目录>
bash tools/run_g3.sh --artifact-dir <完整制品目录> --xsdb D:/xilinx/2026.1/Vitis/bin/xsdb.bat --device xc7z020 --uart-port <实际PS串口> --ip <实际板IP> --limit 2048 --read-bps 150 --score-min 67
bash tools/run_g3.sh --artifact-dir <完整制品目录> --xsdb D:/xilinx/2026.1/Vitis/bin/xsdb.bat --device xc7z020 --uart-port <实际PS串口> --ip <实际板IP> --full --runs 3 --result-timeout 1800
python3 tools/board/g3_performance_matrix.py --artifact-dir <已加载完整制品目录> --out-dir <新矩阵目录> --limits 128,512,2048,8192,32768,full --repeat 3 --ip <实际板IP>
```

构建模板展示已存在的WSL入口；正式选择Windows2026.1或WSL2022.2需记录硬软版本组合，不暗示新板最终路线已验证。矩阵需先加载相应P4/P16包；UART周期采集复用唯一追加日志，Stage1未测周期和功耗保持null，不能墙钟×时钟代替硬件计数。

旧平台脚本的已复核风险：stress_test_suite.py的flash_mode会调用switch_export.sh覆盖旧export和固件/BSP头，再不带artifact-dir烧录；auto会切SE250。ARM基准固定旧BSP/XSA/GCC/XSDB并rst -system，必须适配后再用。多payload/run_demo主要是TCP任务，不下载或复位；run_robustness_scan的board_equivalent为软件模拟。不能将名称当作板测证据。

## 6. 提交、推送、工作区整理与完成定义

每个可验证里程碑由main统一交付：停写确认→核对所有diff/索引/未跟踪文件→备份精确任务路径及SHA→必要时手动限定路径stash并保存OID→pull --rebase（禁止autostash）→恢复并验证SHA/模式→精确add与带路径commit→立即push origin main→require-synced=0/0。若实际失败，保存状态并报告，不force push、不reset/clean掩盖。

提交说明写清问题、变化、测试及未测边界；准备提交不能称为新板迁移完成。大EDA生成目录不提交；可复现源码/入口、参数、fixture/source manifest、必要小证据、结果摘要必须交付。每次迭代更新03/05/07/09和相关benchmark，避免文档互相矛盾。

本轮工作区整理按[整理记录](reference/workspace-cleanup-2026-10-10.md)：原位保留历史生成物与证据，仅用精确.gitignore规则防止误提交；没有删除数据/旧制品、没有释放其磁盘空间。最终Git status应无源码改动或未知未跟踪文件。ignored不等于已备份到GitHub，目录归档与hash清单仍须保留。未来确需释放空间按本文件清理条款先保留日志/manifest和用户认可的范围，不盲删生成目录，不移动活证据导致路径断裂。

收工前确认没有本任务仍运行的EDA/下载/串口进程；只关闭本任务明确持有的资源，其他用户进程不动。恢复点stash在确认新提交与远端同步后按OID核对是否仍需保留，不能批量drop他人stash。用agent_view.sh对已结束角色done；真实外部阻塞写block或交接，不挂“正在测试”假状态。

可宣布“迁移完成”的最小条件：确认过的新板配置、P4新板基线、P16合法100MHz完整route、同XSA完整软件包、全量/连续/恢复新板G3和同板公平性能、源码制品证据可追溯。功耗/SE250/D0分发/材料未完成单独列项。当前整理交付可以完成，硬件迁移仍按上述门禁继续。

### 清理分类与不可省略的门禁

- 冷整理（文档/生成目录/非综合死源）先证明引用/用途，归档或改精确忽略，复查打包/卫生/相关回归；保存失败和活证据，不把运行证据当死源码。
- 热整理（sw/app、综合RTL、客户端生产逻辑）即使结果看起来相同，也必须重建对应整套制品→真实G3→刷新SHA/source manifest；无工具/板卡窗口只记录deprecated/待办，不假报通过或删除仍用实现。
- sw/app唯一权威，workspace同名源应一致，禁止改生成副本；黄金共享common，不能复制到各数据集。
- 工具必须登记，综合hdl不得含TB/孤儿，同名变体打包唯一且回归覆盖。零引用不是自动可删：依AGENTS退休条件，先保留Git历史与结论，确认已证伪/逐字节重复/已替代才处置。
- archive/submission历史包不删除；若将来移出项目，先明确并得到用户认可目标路径，保存SHA和指针；本次未移动。任何空间修剪先归集日志/manifest，保留窗口必须可审计，不手工盲rm。
- main在Git前冻结全部writers、核实真实进程，恢复时核对文件SHA/模式与stash OID；只终止自己核实的PID树，不清他人改动或恢复点。

### 本轮按计划执行的检查点（2026-10-10）

主Agent按用户要求使用三个低等级gpt-6-luna子Agent完成docs-audit、tools-audit、env-audit两轮短任务，分别核对文档映射/提示词、脚本副作用/打包/47主机用例、实际设备/资料/配置门禁。main复查引用与差异、直接重复只读CIM设备核查并查看测试原始日志；子Agent不做Git写入。

F0/F1审计与准备检查已执行：正式源SHA、fixture几何/内容、打包与47主机用例PASS。F2只做只读资料/设备与dry-run核查：bkb220 ready=0在create_project前拒绝，未创建工程；当前只有蓝牙COM，无FTDI/JTAG、无物理网口/对应原厂preset。资料搜索仅指定目录一层关键词及仓库文件名，不构成全磁盘不存在资料的证明。F3～F8真板依赖仍未关闭。

后续资料/连接到位且CLI冒烟通过后，由main经 codex-luna MCP 固定 gpt-6-luna/max 按角色提示词派发board-migrate/rtl-16way/verify-system；当前审计助手已停写。索引、静态盘点和短检查可优先派发；生产RTL、时序、PS7及真板结论必须main审查，不仅依据子Agent的摘要。
