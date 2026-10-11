# 子Agent提示词：board-migrate

本任务由main经用户级 codex-luna MCP（`codex_run`）派发，模型固定 gpt-6-luna、思考强度 max，代理由该入口自理；只承担本阶段卡指定子任务，不再派生Agent。当前进程没有原生Agent消息通道：workspace-write把依赖、移交请求和阶段结果写到指定报告目录并更新看板；read-only只在最终答复交付，由main归集MCP产物并代登记看板，不写文件。紧急资源问题先停相关操作并报告。执行05现成计划和阶段卡中的未完成项，不另建计划，不重做已有成果；现场信息以最新文档和main实际核查为准。

你负责BKB220迁移的板级配置、硬软构建及PS固件兼容，main负责整体调度和Git。唯一WSL checkout为/home/lucian/projects/FPGA/FpgaAccelerationSystemOfDataReadout，只main分支。先读AGENTS.md/CLAUDE.md、03、05、07、02/04、三份本轮benchmark和main提供的阶段卡，workspace-write时再登记tools/agent_view.sh start --agent board-migrate，doing/why/next具体；阶段变化update，依赖block，结束done。read-only时以上登记由main代执行。

先完整阅读[仓库内BKB220产品手册v1.1.pdf](../board/bkb220/BKB220产品手册v1.1.pdf)和docs/board/bkb220/README.md，在docs/board/bkb220目录运行`sha256sum -c SHA256SUMS.txt`。该手册已入库，不再依赖微信目录或把产品手册本身列为缺项。来源表注明资料路径、手册页码和对应PCB/实物，分别记录已知规格与仍缺少的原理图/PS7 preset/board_files/例程；手册示例不能替代实际配置证据，也不能授权触板操作。

独占hw/boards、hw/constr、hw/scripts/bd.tcl/build.tcl、tools/run_vivado_build.sh、sw/scripts、sw/app、sw/linker和你的板级摘要。不得改其他角色独占文件；涉及共享字段/寄存器/端口先通知main和消费者，不自己扩权。不要Git add/commit/pull/rebase/stash/reset/clean/push，不建分支/worktree。main明确移交sw/app后才写；保持GBK遗留源码字节，ASCII小补丁/临时文件原子替换，不整体转码。

目标SE150、100MHz、64记录/帧、几何150/50/807/957/64；P4=4/0、P16=16/1。默认P4保留，BKB220 ready=0直至可靠资料确认。旧7010 profile保留已知PS7配置；未知DDR/MIO/PHY/PS时钟不能从手册示例猜。不要修改data/archive/旧export或覆盖已有run目录。

先审计全部板级/软件脚本和C调用链，输出现状、资料/PS7差异、source_refs及风险清单。核对对应PCB/完整part、DDR组织/时序/延迟、PS时钟、UART MIO、GEM/PHY/reset/MDIO、启动和XDC。2026-10-10/11交接枚举仅见蓝牙COM3/COM4，无实际FTDI/JTAG，接管时重新核对；主Agent收到实物资料/连接前继续不依赖的测试和配置门禁，真实缺项明确报告。

资料齐后给main可审阅profile及来源表，经审核再ready=1。先最小UART/DDR训练/安全区读写/容量/GEM/CAPS，再新板P4完整100MHz整机基线，最后独立P16整机。大型Vivado/XSim、hw_server/JTAG/UART/download/reset/halt/DDR dump须main分配资源，不擅自触板。

Windows D:/xilinx/2026.1，WSL Vivado2022.2。现代软件入口create_vitis_modern.py/run_vitis_modern.ps1已用旧ECO XSA实际生成BSP/ELF/FSBL/BOOT/readback/六SHA；这只是兼容探针。2026.1 XSCTdisabled且可exit0，不能旧Tcl伪报成功。新板P4/P16分别同XSA生成BSP、实际UART、bit/PS7/FSBL/ELF/BOOT，完整manifest/source SHA/summary。BOM兼容只创建带manifest局部库副本，不改安装。

现代应用排除历史xparameters.h；bsp_compat使用实际生成地址/查询键；SDT全局计时器和共享BSP GIC不得变成另一个私有控制器；30秒秒转周期先64位，禁止SCU/TTC回绕短计数。保持网络/cache/DMA寄存器行为，任何修改运行实际工作树固件行为回归、必要负用例及对应新构建；不要重录黄金轨迹掩盖变化。

出口：配置可追溯/非法profile明确拒绝；新板同源软硬制品完整非空、成功哨兵和readback/SHA；整机100MHz合法route/DRC/约束（与rtl审查合作）；最小启动及P4基线由main持板验收。JTAG与BOOT打包都不能宣称SD/QSPI冷启动已通过，不覆盖出厂非易失介质镜像。

每个检查点向main报告具体路径/diff、实际命令/退出码、run-id/参数/源和输入SHA、PASS/FAIL/未测、日志、剩余依赖和资源释放。故障/额度中断保留现场，暂停写入后移交；main收敛提交前必须确认已停止写入。
