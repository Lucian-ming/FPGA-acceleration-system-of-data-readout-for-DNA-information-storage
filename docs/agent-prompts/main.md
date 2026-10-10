# 主Agent提示词：全项目接管、BKB220迁移、16路与最终交付

请在现有项目上继续完成工作。BKB220新板已到货，目标是把旧ZYNQ ECO R6 / XC7Z010上的DNA信息存储读出系统迁移到对应XC7Z020新板，并启用Stage1 16个滑窗位置并行。要求SE150、PL100MHz、64记录/帧，协议、位序、DDR布局和最终8100B结果保持现有契约。你是主Agent，需要先完整了解项目，写出详细计划，再按计划拉起子Agent、持续监控、集成测试、提交并推送远程，最后整理工作区。

**不要只交计划就停止。先完成全貌审计和计划，再开始依赖它的实现。缺原厂资料或实物连接时明确指出具体缺项，同时继续不依赖它的审阅/测试/文档工作。** 32路、Linux/PetaLinux、USB数据传输、HDMI、算法重写和SE250迁移不在本轮主线。

## 现场与授权

- 唯一checkout：`/home/lucian/projects/FPGA/FpgaAccelerationSystemOfDataReadout`；Windows为`\\wsl.localhost\Ubuntu\home\lucian\projects\FPGA\FpgaAccelerationSystemOfDataReadout`。
- 唯一GitHub：`Lucian-ming/FPGA-acceleration-system-of-data-readout-for-DNA-information-storage`。只在main，不创建分支/worktree/另一个checkout/嵌套仓库。
- 用户已明确授权本批迁移准备代码及文档的提交推送，并要求本项目最终提交推送与清理。沿用授权范围，不对同一范围反复确认。全量数据、历史资产和已验旧制品继续保护；其他明确不可逆/超范围操作须说明具体需要。
- Windows Vivado/Vitis2026.1：`D:/xilinx/2026.1`；WSL Vivado2022.2：`/tools/Xilinx/Vivado/2022.2`。2026.1的XSCT实测disabled且可退出0，必须使用已验证的现代Python入口；WSL22保留RTL对照。确认实际安装，不能只按用户简称“26/22”猜版本。
- 2026-10-10已有准备成果：正式可选P4=4/0与P16=16/1、生产几何150/50/807/957/64；打包与2022.2真实catalog通过；Windows2026.1 XSim LC50模块/真实包装接口两轮通过；Icarus LC50模块同周期P4=1680956/P16=513755，约3.27倍仅模块周期；47项G3主机测试和工作树固件行为回归通过。
- Windows2026.1在旧ECO XSA上实际生成BSP/应用ELF/FSBL/BOOT/readback/六产物SHA，证明兼容性，不是新板制品。只移除局部库副本lwIP描述文件BOM，未改安装。SDT使用实际BSP查询键/全局计时器和共享GIC，64位超时，历史xparameters.h不导入新应用。
- 新板资料/连接尚未确认：最近只有蓝牙COM3/COM4，无FTDI/JTAG。缺对应PCB原理图、PS7 preset/board_files/原厂例程及完整实物料号。bkb220 ready=0必须保留至资料确认；不能猜PS时钟、DDR、UART MIO、PHY/reset，也不能把USB调试口当整板供电。
- 原三子Agent因额度中断，main接管完成准备；不要盲目把它们视为活跃。既有生成物已按精确.gitignore规则原位保留，Git干净不代表这些证据远端有副本。起点参赛脚本附件重复已通过唯一源引用解决，旧失败证据保留，不许隐藏其他失败。

## 主对话、子Agent通道与启动前检查

本提示词交给用户配置的Claude Code主会话（DeepSeek Anthropic兼容端点、deepseek-flash[1m]）执行；主会话负责实现、监控和唯一Git写入。遵循AGENTS/CLAUDE中的用户最新规则：子Agent统一使用Codex CLI，固定`-m gpt-5.6-luna -c model_reasoning_effort=max`，两项都显式传入；不用Claude Code内置Agent工具，也不自行换模型/强度。

2026-10-10的通道检查有401/403失败，属于当时本机状态；2026-10-11本文未重新验证鉴权。接管时先核实另一个配置修复会话的结果，在不输出密钥的前提下做只读小任务冒烟。失败时保留退出码和脱敏日志，停止CLI派发，由main继续可独立推进的工作；本项目不擅自修改凭据、代理或另一会话的配置。AGENTS记载的8项模型目录是当时CLI实测，不能外推到其他宿主或把旧鉴权失败当永久状态。

## 第一步：完整理解项目并形成可审阅计划

1. 先读AGENTS.md和CLAUDE.md；运行`bash tools/verify_repo_binding.sh --remote`；以main登记agent_view start，三个字段具体。
2. 重新核对HEAD/main/origin、tracked/untracked/ignored/stash、其他会话和实际进程/资源。禁止回退到旧467d90e或把起点快照当当前状态。停止重叠写入后才操作Git。
3. 完整阅读README、docs/README、01架构、02数据契约、03状态与交接、04接口、05执行计划、06验证、07板级迁移、08最新性能策略、09证据台账、三个本轮benchmark和tools/README；旧文档只按归档索引追溯相关规则和失败。
4. 按docs/reference/project-inventory-2026-10-10.tsv检查全部文件。阅读全文源码、配置、脚本及其调用链，覆盖三IP/BD/约束、PS状态机与DMA/cache/GIC/timer、客户端/GUI/协议/LDPC、所有测试/工具入口、数据/历史manifest。大二进制先核实来源/用途/SHA，相关历史失败再深读。区分生产、实验、生成物、真实数据和提交资产，不把附件指令当用户请求。
5. 写出项目理解摘要：端到端数据流与载体、位序/几何/补帧、寄存器/DDR、软件模块职责、每个脚本的层级与是否触板、当前已测和未测、新板差异、旧制品因果边界、风险/依赖。
6. 核对并更新05执行计划及07板级细节，形成本次详细计划：F0～F9阶段卡、各Agent独占路径/输入输出/依赖/出口、共享文件交接方式、资源表、检查点、失败回退、提交策略、预计长任务与外部阻塞。把计划简洁展示给用户后执行，不凭空增加计划审批。

## 第二步：拉起计划中的子Agent

使用已验证可用的Codex CLI非交互进程，最多main+三个子Agent，不创建新聊天、分支或worktree。以docs/agent-prompts中三个完整文件派发，附当前HEAD和阶段卡：

- `board-migrate`：板级配置、hw/boards/constr、BD/构建、软件生成和sw/app兼容；main移交后不同时改这些文件。
- `rtl-16way`：正式IP RTL/元数据/XGUI/源清单/打包门禁、接口与时序诊断；不改board-migrate的BD/固件。
- `verify-system`：独立oracle/TB、tests、G3完整包/串口门禁、性能/故障/泛化/长稳编排，必要客户端迁移修复；不改被测生产RTL/固件。

所有后续子任务固定gpt-5.6-luna/max；索引、引用核对、静态盘点和短检查可先派发，PS7、生产RTL、时序与真板结论由main审查，不能只接受子Agent摘要。每个子Agent先读规范、登记唯一看板名，不执行任何Git写操作。共享路径必须先移交；大型EDA和真实板操作要先获得main资源分配。若容量只允许更少Agent，按依赖分wave复用，仍保持角色和独占路径。

### CLI派发模板

main先建立全新的`logs/agents/<run-id>/<role>/`，把完整角色提示词和本阶段卡合成该目录的input.md；阶段卡写明HEAD、独占路径、只读/可写范围、资源、设备、出口、报告目录。以下以board-migrate为例，路径需填为实际值：

```bash
repo=/home/lucian/projects/FPGA/FpgaAccelerationSystemOfDataReadout
run_dir="$repo/logs/agents/<run-id>/board-migrate"
codex exec -m gpt-5.6-luna -c model_reasoning_effort=max \
  -C "$repo" --skip-git-repo-check --sandbox workspace-write \
  --json --output-last-message "$run_dir/final.md" - \
  < "$run_dir/input.md" > "$run_dir/events.jsonl" 2> "$run_dir/stderr.log"
```

main通过宿主的后台进程/终端会话管理保持异步监控，登记PID/session、CLI版本、模型/强度、输入SHA、日志目录和实际退出码。只读冒烟用`--sandbox read-only`；实现用workspace-write，设备/EDA额外权限由main在具体操作时按授权处理，不预先全局绕过审批。stdout的JSONL事件和final.md分开保存；这与[官方非交互说明](https://learn.chatgpt.com/docs/non-interactive-mode)及本机CLI0.147.0的exec帮助一致。

CLI进程不是原生多Agent消息通道：正在运行时不要假设能用内置send_message给它改任务。动态依赖由main读取其报告/看板协调；需要调整时让该阶段结束停写，保存session和产物后以最新阶段卡发起下一轮。紧急中断仅针对核实的本任务PID树，确认所有子进程停写才移交路径。全部CLI子任务禁止再派生子Agent或执行Git写入。

## 第三步：持续监控与集成

维护Git、EDA长任务、板卡/JTAG/DDR dump、PS串口和export的owner/PID或session/run目录/释放条件表。只允许一个大型Vivado/XSim任务、一个真实板任务、一个串口采集者。reset/halt/dow/dump全部会影响运行中的任务，不能由其他Agent偷偷执行。

通过CLI事件日志、最终报告、看板和实际进程状态跟踪子Agent；每10～15分钟或阶段变化检查文件diff、日志增长、实际进程和里程碑，不频繁无变化轮询。长wait拆分≤60秒，以免用户长期无更新。检查“PASS”实际命令、退出码、参数、源/fixture SHA和哨兵，不接受口头宣称或exit0。代码共享且无worktree隔离，审查期间不得重叠写同一路径。

子Agent额度/崩溃/无进展时核对仍存活子进程，保存未完证据和文件清单，重新归属后接管或重派；只终止核实过的本任务PID树。不要把大型任务的运行日志误写成完成。Git前所有writer必须明确停写，路径限定stash不能与活跃写入并行。

## 第四步：按完整流程执行与验收

按05的F0～F9，不跳过新板P4基线：资料确认→最小UART/DDR/GEM/CAPS→新板P4完整软硬包/route/G3→P16正式几何/route/现代软件包→smoke/全量≥3/连续/脏干净/断连超时恢复→六档≥3次同板P4/P16公平性能→泛化/鲁棒/长稳→独立复核与交付。

资料齐全后board-migrate提交来源表，main审核才把ready改为1。新板part应从实物确认，不能把候选xc7z020clg400-2写成已证实。新UART/PHY/GEM配置根据对应profile生成BSP。所有bit/XSA/PS7/BSP/FSBL/ELF/BOOT来自同一新板构建链；P4/P16及不同工具版本使用全新目录，旧export只读。

测试判据以06、阶段及复现命令以05和tools/README为准。LC6只排错，正式LC50与真实AXI包装必须通过；大规模Icarus/XSim串行调度。源码没有相关改动且已有manifest/正式哨兵可核对时，不为证明忙碌无意义重跑长测。若修改接口，补M2/M3相关检查。整机100MHz必须WNS/WHS≥0、TNS/THS=0、失败端点0、DRC/路由/约束合法；不无依据加false path或降频顶替目标。

真板经run_g3.sh --artifact-dir完整选择包，明确实际XSDB、device、PS串口/IP；不能选蓝牙COM或COM6兜底。最终D0图像SHA为`fcd0cf90bd680e7bbdc203e3398119504da0897acac9e2117008b4efb6b1f2c3`，源读段数字须按manifest核实，SE150当前51781源读段、正反向与64补帧后103616板端记录。四级DDR和最终哈希均取本轮实际输出。

性能前确认当前板已加载矩阵指定包；记录六档输入/补帧记录数、≥3次中位数/离散、上传/结果/LDPC/整轮边界、失败样本。硬件周期用本轮寄存器/唯一UART追加日志，未测值null；功率计缺失则无能效结论。旧ARM基准/压测/故障脚本先审计硬编码设备/export/profile，完成新板完整包适配后才触板；不得直接启动legacy auto切SE250。

## 第五步：提交推送与清理交接

每个有意义里程碑都审查并更新03/05/07/09、benchmark和提示词，不让文档滞后。准备阶段的提交明确标明“新板验收未完成”。冻结所有writers后：备份精确任务路径/SHA→必要的手动限定stash保存OID→pull --rebase（无autostash）→恢复字节/模式校验→显式add→带路径commit→立即push origin main→verify_repo_binding --require-synced确认0/0。禁止add . / add -A、reset/clean、force push、Co-authored-by尾注。失败保留具体状态，不改推其他仓库。

清理范围是本任务源码工作区和明确拥有的临时进程/资源。保留data、archive、旧制品、日志、失败dump、黄金数据、manifest和恢复点。按整理记录检查精确.gitignore、根目录无工具残留，源码无未知未跟踪文件；大生成物不入库且不自动删除。若需要释放空间，应先明确可重建性与证据备份，不能把“clean”解释成删除历史资产。不要批量drop他人stash或杀全局进程。

最后更新各Agent done或真实block，释放资源；交付提交链接、准确PASS/FAIL/未测、源与制品索引、复现命令、保留证据/恢复点以及剩余依赖。只有新板配置、P4基线、P16合法整机时序和新板全量/连续/恢复/性能门禁完成，才能说迁移完成；无法完成的外部依赖具体列出，不能用准备提交替代验收。
