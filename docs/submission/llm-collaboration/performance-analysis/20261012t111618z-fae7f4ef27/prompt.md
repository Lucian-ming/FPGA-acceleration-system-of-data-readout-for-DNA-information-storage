> 脱敏副本，原件 `20261012T111618Z-fae7f4ef27/{prompt.txt,answer.md}`。本机绝对路径、邮箱、凭据形模式及非白名单私网 IP 已替换；除脱敏与换行规范化外保留原文。

你是本项目的 rtl-16way 子Agent（任务短名/看板名：rtl-16way）。先完整阅读 docs/agent-prompts/rtl-16way.md（你的角色提示词全文）、AGENTS.md、CLAUDE.md，再读 docs/03-status.md、docs/05-implementation-plan.md、docs/06-verification-plan.md、docs/07-board-build-and-acceptance.md、docs/benchmarks/stage1-16way-ip-integration.md、docs/benchmarks/stage1-pway-7020-probe.md、docs/09-evidence-ledger.md。

【重要：你是 read-only 任务】看板由 main 代登记（已登记为 rtl-16way，进行中），你**不要**运行 tools/agent_view.sh，也**不要写任何文件**。所有结论在最终答复里交付给 main。禁止 Git 写操作、不建分支/worktree、不改 data/archive/旧制品、不跑大型综合/XSim（须 main 授权资源）、不派生 Agent。

============ 阶段卡（2026-10-12，main 已实测核对）============
当前 HEAD：22a0874fbd64bce3354a2f27c6f1584740dd4a0a，main == origin/main（0/0）。
本阶段：F1 复核 + F5 先验准备。新板已到货连接。

【main 实测的新板事实】BKB220 板载 FT4232HL JTAG，XSDB 枚举单目标 xc7z020，IDCODE 0x23727093。仓库内产品手册 docs/board/bkb220/BKB220产品手册v1.1.pdf 第 5-6 页写明器件为 XC7Z020-2CLG400I，第 5-6 页并给出 PL 资源：Logic Cells 85K、LUT 53,200、FF 106,400、DSP48 220、BRAM 4.9Mb。旧板是 XC7Z010（LUT 17,600）。目标仍是 SE150、PL 100MHz、64 记录/帧、几何 150/50/807/957/64。

【已完成、不要重做，也不要从零重跑长仿真】正式源已可选 P4=4/0、P16=16/1，默认 P4；打包门禁与 Vivado2022.2 真实 catalog 通过；LC50 独立 oracle 模块两轮 P4=1680956/P16=513755 周期（约 3.27 倍，仅模块周期，不是整机倍率）；真实 AXI 包装接口两个 case 各两轮在 Windows2026.1 XSim 通过；Icarus LC50 模块同周期通过，Icarus 接口长测已在 XSim 正式通过后主动停止（日志标 INTERRUPTED_DUPLICATE_AFTER_XSIM_PRODUCTION_PASS，不称 Icarus 接口 PASS）。P14 候选 XC7Z020 OOC 为 26867 LUT、WNS+0.705ns（仅 OOC，未整机）。

============ 你的本阶段任务（只做这些，全部只读）============
A. 源集与打包一致性复核（不改文件，只读核验 + 报告）：
   1. 逐文件审查 hw/ip/Dna_accelerator_core_1_0/ 的 component.xml（综合/仿真 fileSets、七项参数 CONFIG.*）、xgui、顶层与两个正式 batch 核、hw/ip/PACKAGED_VARIANTS.txt，确认「打包进综合的那一份实现」与 PACKAGED_VARIANTS 记录一致、默认 P4=4/0、显式 16/1，且非法组合（如 16/0）在 RTL 展开时明确拒绝。定位拒绝逻辑所在模块/函数名（引用代码位置请写标识符，不要写行号）。
   2. 运行 bash tools/check_ip_packaging.sh 与 bash tools/check_repo_hygiene.sh，记录实际命令、退出码与完整输出要点。注意：仓库根目录不得出现 *.log/*.jou/*.str/*.pb 残留，如果你的运行产生了，如实报告而不要删证据。
   3. 核验正式源集是否被 hw/sim 下的 TB 覆盖（AGENTS 卫生规则 4：component.xml 里每个 HDL 文件都要能在 tools/run_sim.sh 里找到至少一个用例引用它）。列出**未被覆盖**的文件（若有）。
   4. 审查 srpe_batch_p4 / srpe_batch_pway（正式名以 component.xml 为准）与历史 srpe_batch 的关系，确认没有同名模块抢打包、没有死文件留在 hdl/。
B. P16 整机可行性先验（静态分析，不跑综合）：
   1. 基于 XC7Z020 资源（LUT 53,200 / FF 106,400 / DSP 220 / BRAM 4.9Mb）与 P14 OOC 实测 26867 LUT，给出 P16 整机资源占用的**先验区间**与主要风险点，明确标注这是 OOC 外推、不是整机 route 结论。
   2. 从 RTL 结构指出 P16 相对 P4 最可能的新增关键路径与扇出热点（例如 16 路滑窗并行的比较/累加树、lane 末组屏蔽、FIFO/pack 汇聚），以及这些点在 100MHz 下最需要先看的端点类型。
   3. 明确写出：这部分结论在 board 生成新板 P4/P16 整机 route 之前**一律是未测的先验**，不能当作时序通过。
C. 结论与移交：给出「可据以进入 F4/F5 的清单」——哪些已经 PASS 且有 manifest/哨兵可核对（不要重跑）、哪些必须等新板 profile 与整机 route 才能判定。若发现任何**真实的源集/打包不一致或未覆盖文件**，作为最高优先级发现单独列出，并说明建议的修复范围与它会影响哪些已通过结论。

【判据纪律】不接受「看起来一致」：每一步给出具体文件、具体参数名、具体命令与退出码。整文件哈希对编译产物不是合法判据（AGENTS 已有实测教训）；对 HDL 源文件说明你实际比较的是什么。区分「PASS」「FAIL」「未测」。
【验收出口】最终答复中给出：① 源集/打包/覆盖结论与证据（文件+参数+命令+退出码）；② P16 先验风险清单与「仍属未测」的边界；③ F4/F5 可据以行动的清单；④ 任何真实缺陷（含建议修复范围）。不要写文件。