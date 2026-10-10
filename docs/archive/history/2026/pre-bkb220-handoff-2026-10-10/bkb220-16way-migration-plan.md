# 20 · BKB220 迁移与 16 路实施计划

状态：2026-10-10 启动；先发布本计划，再开始实现。范围是 BKB220 的 XC7Z020 版本、SE150、PL 100 MHz、Stage1 16 个滑窗位置并行，帧大小仍为 64 记录。

## 当前执行进度（2026-10-10）

计划和索引已按用户授权提交并推送：`c4d7ad4`。用户已进一步明确授权提交并推送迁移准备源码与验证文档；main正在按路径限定完成本阶段提交。既有未跟踪生成目录、旧制品与真实数据均保留。

| 工作 | 当前结果 | 证据/入口 |
|---|---|---|
| 可选生产 P4/P16 与 IP 参数/源集 | 已落地；打包和 Vivado2022.2 真实 catalog 检查 PASS | [集成摘要](../../../../benchmarks/stage1-16way-ip-integration.md) |
| 独立算法及真实 AXI 包装接口 | LC6 三项 PASS；LC50 模块及真实包装接口均在 Windows2026.1 XSim PASS，Icarus LC50模块同周期 PASS | 上述摘要中的 run-id 和 Windows XSim 证据 |
| G3 制品、路径、串口和性能编排 | 40+7=47 项主机测试 PASS | [主机验证摘要](../../../../benchmarks/bkb220-host-verification.md) |
| Windows2026.1 完整软件入口 | 旧 ECO XSA 兼容探针 A14：BSP/应用/FSBL/BOOT/readback/六制品 SHA PASS；PS5 wrapper 三项 fixture PASS | [板级与工具核查](../../../../benchmarks/bkb220-toolchain-audit.md) |
| BKB220 PS7/XDC、P4 基线、P16 整机与板测 | 等待实物连接和对应厂商资料；ready=0 明确拒绝构建 | S2～S4 仍未关闭 |

三子 Agent 完成各自准备工作后因运行额度不足中断，main 已接管尚未完成的审查、测试和文档，并独占 `sw/app/` 的 SDT 兼容修改。分工表仍记录原归属；现在没有子 Agent 写入。新头文件只选择实际 BSP 的地址/查询/计时定义，旧 xparameters 快照保留但不再导入应用构建。30 秒超时采用 64 位秒到周期换算。完整软件探针只是兼容性验证，不能作为新板结果。

## 1. 已确认现状和依赖

- 唯一 checkout `/home/lucian/projects/FPGA/FpgaAccelerationSystemOfDataReadout`，指定 GitHub 仓库，main/origin 0/0；起点 `467d90e`。没有 tracked 脏改动，既有未跟踪生成目录和证据不处理。
- 生产打包仍为4路。P16候选在 `hw/experimental/srpe_batch_pway.v`，历史生产几何功能等价、2022.2 OOC 布线 WNS +0.705ns；尚无整机或新板实测。
- 当前发布制品 SHA256SUMS 五项 OK，保留旧 export 和历史 XSA。
- Windows Vivado 2026.1 在 `D:/xilinx/2026.1`，WSL Vivado 2022.2 在 `/tools/Xilinx/Vivado/2022.2`。Windows Vitis xsct/xsdb 入口存在，尚未完成实际软件构建验证；旧 G3 的2022.2 XSDB路径已不存在。
- 最新 Windows 只读枚举没有FTDI/JTAG/USB串口，只有蓝牙COM3/COM4；没有板用物理以太网适配器，hw_server/xsdb/vivado均未运行。用户已被请求连接电源、USB调试口、网线并提供厂商资料路径。
- 原微信临时PDF路径已失效，但已在 E:/WeChatRecord/xwechat_files/wxid_ferqcd0b3stq22_d21b/msg/file/2026-10/BKB220产品手册v1.1.pdf 找到完整持久副本并交板级Agent复核。手册仍不能替代原理图/preset；新板完整料号、PCB版本、PS时钟、DDR/preset、UART MIO、PHY等必须依据完整对应资料和实物确认。

未得到可靠资料前，不猜 PS7 参数、不复位或下载到未知板。此依赖不阻塞通用构建入口、P16生产集成、测试和G3制品选择适配。

## 2. 工具链决策

先验证Windows 2026.1的 XSCT/XSDB/Bootgen、ARM工具链、器件和许可，并检查现有WSL软件构建环境。WSL2022.2保留RTL/OOC对照。

最终生产构建必须能从指定源码和新板配置完整生成bit/XSA/PS7初始化/BSP/FSBL/应用ELF/BOOT及manifest。若2022.2的软件环境不足，验证2026.1整套重建路线；跨版本XSA/BSP或下载组合必须有明确最小实测与官方依据，不默认兼容。不同工具版本、P4/P16使用独立生成目录。源码权威只在WSL，Windows快照只作为带源manifest的构建输入，不另建Git仓库，不手工改副本。


### 2026-10-10 工具探针修正

Windows 2026.1 `xsct.bat` 已实测提示 XSCT disabled，退出码仍为0；不能再用旧 `create_vitis.tcl` 当成可用现代软件构建入口。现代 `vitis -s <python_script>` 已执行 Python/API 探针，ARM GCC 13.4可运行，本机lwIP为220；完整platform/BSP/FSBL/应用产物仍需实际生成核验。旧BSP为2022配置，不得直接冒充新板BSP。优先验证Windows2026.1完整硬软路线，WSL2022.2保留RTL/OOC对照；任何旧XSA导入探针只验证对应版本组合，不代表新板验收。软件脚本成功必须同时检查哨兵和产物，不能仅看进程退出0。

## 3. Agent、文件与资源归属

| Agent/看板名 | 工作 | 独占修改范围 | 输出与依赖 |
|---|---|---|---|
| main | 审计、计划、接口约定、资源调度、审查集成、正式构建/板测、Git和最终交付 | 本计划、docs根目录状态/交接/索引、tools/README.md；未另派的共享文件 | 阶段门禁、版本选择、提交/推送；等待板卡资料/连接 |
| bkb220_board | 工具盘点、厂商资料、新板差异表；适配隔离构建目录/显式配置和软件生成入口 | hw/scripts/bd.tcl、build.tcl、hw/constr/、新board配置目录、tools/run_vivado_build.sh、sw/scripts/；暂不改sw/app | 工具证据和板级差异；资料确认后才能落实新PS7和BSP |
| rtl_16way | 将P16候选纳入正式可选生产路径，保留P4基线，贯通参数、IP打包和源清单 | Stage1相关hw/ip/Dna_accelerator_core_1_0/、候选迁移、hw/ip/PACKAGED_VARIANTS.txt、tools/check_ip_packaging.sh、tools/run_sim.sh | P4/P16可明确选择的生产源集；与测试Agent交换端口和参数 |
| verify_bench | 独立P16生产几何/接口TB，G3完整制品配置和工具/目标参数，测量与恢复判据 | hw/sim/、tests/测试源码、tools/run_g3.sh、tools/board/、tools/board_stage_check.py、必要独占测试摘要 | TB/测试结果、可参数化G3；等待RTL参数和板级制品 |

共享接口初定为 `C_STAGE1_P_WAYS` 和 `C_STAGE1_PIPE_TREE`，默认4/0；新板P16配置16/1。RTL Agent先确认现有IP参数约定，再通知其他Agent。若已有更适合的参数名，由main统一裁决，不可各自选一套。不要直接将全局默认改16导致7010旧板或P4新板基线无法重建。

每个子Agent开工用本表唯一看板名start，阶段切换update、依赖阻塞block、交付done；不执行Git写操作或另派未经计划的Agent。新增文件也登记归属。子Agent给出具体路径、变更、命令、PASS/FAIL、证据与未决事项。sw/app若必须改，先由main明确移交，不与工具/BSP任务混抢。

资源：main是唯一Git写入者；同时最多一个Vivado/XSim长任务和一个板卡持有人。子Agent未获资源锁只能做静态审计、代码或短测试；正式综合、生产几何长测、hw_server/JTAG/UART和DDR dump由main排队授权。复位/下载/只读halt均需板卡锁。不同run保留独立日志和manifest。

## 4. 执行顺序和通过判据

### S0 · 审计与计划（本阶段）

仓库绑定、源码状态、工具/USB/网络/资料审计；发布计划与分工，登记看板，再派发互不冲突任务。计划和索引已本地保存；用户已明确授权仅这两份文件提交并推送，主Agent在全部写入者冻结后执行。预计约20～40分钟，取决于厂商资料是否可用。

### S1 · 并行准备

三Agent分别盘点工具与可复现配置、实现可选P16源集、编写独立TB与G3适配。目标是：没有完整新板配置时构建能明确失败，不静默用ECO参数；G3能选择一套bit/XSA/ELF/PS7及其哈希，不只覆盖bit/ELF；P4/P16与几何明确、仿真和综合读取同一实现。

快速验证：shell/Python语法、配置拒绝与制品manifest负用例、IP打包、P4默认路径和P16短TB。生产长测排队后运行，不能把NUM_LC=6当生产通过。预计1～3小时，实际随工具或接口缺陷调整。

### S2 · 新板最小bring-up与P4基线（依赖资料/连接）

确认XC7Z020完整料号、PCB、对应原理图/preset，登记PS/DDR/MIO/PHY/时钟/复位/启动和来源。验证FTDI各接口及真实PS串口、JTAG唯一目标、实际物理网口与IP。

生成匹配新板的最小工程和软件，验证UART、DDR训练/容量/安全测试区读写、PS GEM和CAPS。再构建新板SE150/P4/100MHz整机，跑2048源读段及全量闭环、四级DDR取证，保存独立P4完整制品和同板基线。资料缺失时该阶段等待，其他任务继续。首次bring-up可能数小时，不承诺固定完成时间。

### S3 · P16生产和完整实现（依赖S1、S2）

显式 `P_WAYS=16 PIPE_TREE=1 READ_BPS=150 NUM_LC=50 STRIDE=807 REF_LEN=957 BATCH=64`。生产候选的250/805/1055默认值不能泄漏。

模块TB：与确定性P4逐位等价、黄金score/cw和并列pos、STRIDE包含最后位置、末组有效掩码、零分、补帧、正反向、复位/再运行及周期。接口TB：AW/W独立握手、写使能、FIFO满空/读延迟、随机背压、TLAST/顺序/拍数、固件START写0→1→0、重复任务；跨BD改动按M2/M3验证。

包装/卫生门禁和全回归通过后，完整route检查WNS/WHS非负、TNS/THS=0、失败端点0、DRC/路由/约束合法。保留100MHz，失败按真实关键路径修，不用无依据false path或降频冒充完成。Decoder→HP握手链若再次成为瓶颈，由main重新分配修改与回归。

同一次新板XSA生成BSP/FSBL/应用/BOOT，检查XSA内bit与独立bit、PS7/地址/linker/UART/PHY及Bootgen组成，记录源清单/版本/参数/哈希。预计长仿真和实现1～数小时，以实际进程报告为准。

### S4 · 真板正确性、恢复和性能（依赖S3与连接）

| 验证 | 通过判据 |
|---|---|
| 冒烟与2048源读段 | TCP/CAPS真实就绪，原始8100B回传及LDPC后的指定参考文件哈希正确 |
| 全量SE150≥3次 | 每次实际103616记录完整执行，最终SHA为fcd0cf90bd680e7bbdc203e3398119504da0897acac9e2117008b4efb6b1f2c3；发布制品本身亦通过 |
| 逐级DDR | 展开水印、Stage1 score/pos/cw、Voter/XOR、Decoder均按既有规则检查；注明Stage1实际dump上限，不宣称全量逐条对比 |
| 连续跨规模 | 全量低阈值弄脏轮→正式阈值判据轮；原始回传真有差异，合法轮哈希正确；仅同阈值重复不作为复位证明 |
| 配置/断连恢复 | 非法几何/容量被拒绝，断连/中止后接合法任务仍通过；DMA/DDR边界不越界 |
| 性能 | 源读段128/512/2048/8192/32768/全量，各≥3次；记录实际补帧N_records、上传/t_result/硬件周期/LDPC/整轮时间，拟合a+bN并给波动 |

P4/P16同板同频同工具链对照为主；旧P13 25.69s模型作有范围限定的参考。约8.6s和3.30倍均为估算/历史模块周期，不作为必须凑出的测量答案。无功率计则功耗UNMEASURED，不阻塞本轮迁移。

S4预计测量数十分钟起，故障定位另计。需要用户物理连接的等待时间不计为计算进度。

### S5 · 交付

保留旧板与新板P4/P16制品，登记工具链、完整器件、PCB、PS7/DDR/MIO/PHY、源码manifest和可复现构建/下载/测试入口。提交源码、脚本、摘要和文档，保留失败证据与未测边界。BOOT打包不等于已测SD/QSPI冷启动；本轮先完成JTAG闭环，非易失介质出厂镜像不默认覆盖。

## 5. 提交、回退与阻塞管理

main每次提交前暂停所有写入者，检查diff/索引/进程，按规范安全pull/rebase，路径限定commit并立即push；不autostash、不reset、不clean、不混入历史未跟踪文件。代码/参数有改动就重建对应全套制品，不混用不同XSA的ps7_init。旧export与历史证据只读；失败的新run保留，退回已验证P4配置而非覆盖旧证据。

每阶段交付命令、run-id、manifest、PASS/FAIL/未执行和原因。主看板更新真实进度；物理阻塞明确等待用户哪项资料/连接，同时推进不依赖它的任务。所有子任务停止后才做Git写入。最终核验main/origin0/0、根目录无工具生成日志、看板和资源已释放。

最终只有在S2～S4真板门禁实际通过后才可宣布“新板16路迁移完成”。目前只是计划与可独立推进的软件/RTL准备阶段。
