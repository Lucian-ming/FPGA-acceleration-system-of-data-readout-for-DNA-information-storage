# 2026-10-11工具整理与开发路线

用户要求在板卡到货前减轻历史工具负担，优先WSL Vivado2022.2开发、Windows2026.1下载，最后复核2026.1开发链路。现有05计划继续执行，不另建计划。

## 工具整理

全仓文本依赖核对后，6个历史脚本原样退出现用tools区，归档及SHA见[历史工具源码](../archive/tools/2026/retired-20261011/README.md)。只有旧stress调用switch_export，两者成对归档；其余工具无现用可执行调用者，debug_vote_diff只在TB注释中提及，该注释已指向历史源码。

归档共81,616 B、1,771行源码，目的是收敛现用入口，不声称释放这部分磁盘空间。原始数据、旧制品、黄金、日志、失败dump和此前归档均保留。当前LDPC DLL仍在客户端resources中；没有重新提取或移动运行库。

保留g3_timing_fit与g3_overhead_sweep：前者离线拟合既有证据，后者主动测量，并非相同用途。保留bench_align的种子法反证、实际构建依赖collect_info、OOC复现synth_check，以及被打包门禁使用的实验srpe_batch_pway快照；local_correlator仍不满足退休条件。

新板长稳使用严格完整包G3与现用故障探针编排，不能调用旧profile自动切换。当前工具与完整流程见[工具索引](../../tools/README.md)及[05计划](../05-implementation-plan.md)。

## 验证记录

实际日志：logs/host/tools-cleanup-route-20261011/verification.json及同目录原始输出。启动器4项、G3主机47项、公平基准契约8项、工作树固件行为2项、IP打包及卫生11项全部通过；bash语法和diff空白检查通过。6份退役源码SHA/权限与原文件一致，TB去注释后词法内容不变；原20份文档归档、2份冻结资产SHA及产品手册SHA不变。135个当前/新归档Markdown本地链接有效，docs根编号保持01～09，Windows主提示词和05计划镜像一致；现用代码没有调用退役路径。

首次文档断言要求验证角色写出实际版本号而失败，已明确2022.2/2026.1后通过；记录在precheck-failure-1.txt，没有隐藏失败。没有触板、重建新板制品或宣称迁移完成。

## 开发与安装状态

主线为WSL Vivado/Vitis2022.2开发，Windows2026.1下载，最后在相同冻结HEAD/参数/输入下独立复核26完整开发链路；具体门禁在07和05 F9。启动器现按显式VIVADO→VIVADO_ROOT→PATH选择，显式根目录无效即拒绝，help无需已安装工具。

本机已实测Vivado2022.2可运行，Vitis_HLS2022.2目录存在；当时未找到用于PS开发的Vitis/XSCT。2026-10-11用户从已有Vivado维护入口手动开始补装，安装日志明确“Adding design tools/devices to Edition: Vitis Unified Software Platform”，目标/tools/Xilinx/Vitis/2022.2；界面总下载7.24GB。这是正在安装的快照，完成与否须重新核验实际Vitis/XSCT及原Vivado，不等同于完整软件构建通过。认证/用户账户数据不纳入项目。

官方2022.2的[增补入口说明](https://docs.amd.com/r/2022.2-English/ug973-vivado-release-notes-install-license/Adding-Additional-Tools-and-Devices)与[Vitis安装说明](https://docs.amd.com/r/2022.2-English/ug1400-vitis-embedded/Installing-the-Vitis-Software-Platform)分别说明修改现有安装及统一包的组件选择；本机实际补装状态以上述现场证据为准。


后续实测更新（2026-10-11）：维护安装器显示Install completed successfully。/tools/Xilinx/Vitis/2022.2已具备vitis/xsct/xsdb/settings64.sh；原Vivado v2022.2仍可启动，XSCT实际报告xsct 2022.2.0且setws/platform/domain/app/bsp/importsources六命令可用。SDK内GCC11.2.0（arm-xilinx-eabi）以cortex-a9/hard/vfpv3成功生成ARM32对象，ELF机器字段为ARM。最终报告及命令输出在D:/Agent/outputs/fpga-migration-handoff-20261010/vitis22-installation-verification-20261011-a2/；仅验证安装与基本工具能力，不是完整BSP/应用/FSBL/BOOT构建或真板验收。

首轮编译器实际--version退出0，但检查脚本误要求输出包含arm-none-eabi-gcc；实际厂商名为arm-xilinx-eabi-gcc.real。首次日志原样保留在不带-a2的同名目录；修正为实际目标架构与ARM对象编译后通过，没有修改安装内容。
