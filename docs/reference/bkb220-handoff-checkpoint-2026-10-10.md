# 2026-10-10 交接计划执行检查点

用户要求文档合并并保持连续编号、完整主子Agent提示词、实际执行可推进阶段、提交推送与工作区整理。当前根编号文档为01～09，原20份在pre-bkb220-handoff-2026-10-10目录归档，原/归档SHA和入口映射保留。

## 已实际执行

main安排三个gpt-6-luna只读助手：docs-audit核对合并/编号/引用，tools-audit核对脚本副作用和短检查，env-audit核对设备/资料/dry-run；main审查差异、修复引用语义、直接复核CIM设备和原始检查日志。

- F0/F1：正式生产源SHA与SE150五几何fixture内容SHA通过，P4/P16架构另在run-config留证；IP打包PASS，47项G3主机用例PASS。日志：logs/host/g3-preflight-20261010/handoff-final-host.txt。
- 文档：210个当前入口/提示词/本次归档链接核对，连续01～09；23个既有Python程序的文档修改经AST去文档并规范化引用后与HEAD程序一致，改动只影响说明/帮助引用；日志：同目录handoff-document-checks.json。
- F2只读门禁：bkb220 ready=0，dry_run明确拒绝且发生在create_project前；未生成新板工程或触板。
- 设备：主Agent与env助手均仅见蓝牙COM3/COM4，无FTDI/JTAG/PS USB串口，无物理以太网；未发现本任务后台EDA/JTAG/串口进程。资料只在指定目录一层/仓库文件名核对，BKB220匹配项是产品手册，不代表所有磁盘不存在其他资料。
- 旧stress的flash_mode/switch_export会覆盖旧export和头文件，ARM基准固定旧工具路径并整板复位；已写入工具索引和计划，未执行这些入口。
- sw/app文档引用修改后的生成源码副本已单向同步，修改前备份在logs/host/workspace-source-sync-20261010-final；旧BSP/ELF未重建。旧制品及原始数据继续保留。

## 剩余门禁

缺对应原厂PS7 preset/board_files/原理图、PCB与完整料号、实际供电/USB调试/网线连接。F3～F8的新板P4基线、P16合法100MHz整机时序、同XSA完整软件包、全量/连续/恢复与公平性能仍未测试。当前检查和既有LC50 XSim/A14兼容探针不替代新板验收。

任务起点的参赛agent_view.sh重复附件已核对为逐字节重复，随后收敛为引用tools唯一源码；原附件保留在Git历史和本轮备份，原失败日志保留，卫生门禁11项通过且未放宽。生成物原位保留并精确忽略，Git干净不代表大型证据远端有副本。

下一主Agent直接读docs/agent-prompts/main.md，按05计划和07板级文档继续。每个新里程碑更新事实/台账/制品manifest，main冻结writer后按路径commit立即push，并确认0/0。

最终复核：工作树固件2/2 PASS；旧发布五项SHA全部OK；重复附件收敛后仓库卫生11项PASS，门禁未放宽。最终日志在logs/host/g3-preflight-20261010/handoff-final-firmware.txt及handoff-final-hygiene.txt。

2026-10-11交接规则同步：保留用户安排的独立提交3ad6fbd（仅AGENTS/CLAUDE）；当前main/origin均含该提交。主提示词和05计划已改为Claude Code主控、Codex CLI子Agent、固定gpt-5.6-luna/max，补齐CLI输入/JSONL/退出码/阶段停写监控。鉴权在本FPGA任务中未重新验证，不修改另一配置会话的凭据或代理。另六个C源码/测试的旧编号引用已逐项审阅，只有注释/测试展示文本变化，纳入本轮文档整理。

2026-10-11提交前最后复核：47项G3主机用例、2项工作树固件行为回归、IP打包和11项仓库卫生检查再次通过，日志在logs/host/handoff-final-20261011。原20份归档与原文恢复点SHA、旧发布五项SHA及精确保留清单均核验通过。生成源码副本已一致，本次同步检查未再改动副本；未重建旧BSP/ELF。
