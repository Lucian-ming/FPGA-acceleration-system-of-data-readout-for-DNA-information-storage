# Stage1 P4/P16 生产源集集成（2026-10-10）

正式 IP 默认保持 P4=4/0；显式 16/1 选择新 `srpe_batch_pway`，使用 SE150：READ_BPS=150、NUM_LC=50、STRIDE=807、REF_LEN=957、BATCH=64。原 P4 模块名为 `srpe_batch`，两个实现名称不同；不改变外部 AXI-Lite/AXIS 接口。非法参数组合在 RTL 展开时失败。

新增生产 `hdl/srpe_batch_pway.v` 来自已有 P14 候选，改变默认几何和注释，算法体等价由打包检查脚本核验。`component.xml` 的综合/仿真源集和参数、xgui、PACKAGED_VARIANTS、BD 构建参数及仿真入口已一致。移除的是 Stage1 component 中已失效的 bd_tcl 引用，历史 RTL 仍保留。

## 已完成验证

| 检查 | 实际结果 | 证据 |
|---|---|---|
| IP 文件/变体/七项参数/候选算法契约 | PASS | `tools/check_ip_packaging.sh`；各仿真 run 的 packaging.log |
| Vivado 2022.2 实际导入、生成 wrapper | P4 默认 4/0、set_property 16/1、SE150 七参数 PASS | `logs/vivado/stage1_ip_catalog_20261010_2110/` |
| 非法 16/0 | Vivado catalog 可保存；实际 RTL 展开明确拒绝 | 同目录日志；CLI 另有前置拒绝 |
| LC6 快速独立算法/接口 | 3 项 PASS、0 FAIL | `logs/iverilog/run_20261010_215955_167820_stage1_production/` |
| LC50 正式生产几何 | Windows2026.1 XSim 模块两轮+P4/P16接口两轮均PASS；Icarus模块两轮同周期PASS | `D:/Agent/outputs/bkb220-xsim26/run-20261010-a4/`；Icarus原run保留 |

LC6 独立 oracle 覆盖符号相等计数、首次 argmax、末组掩码、最后位置 807、正向/反向互补、37 个实际记录+27 个补零、并列/全零得分，以及复位后二次任务。两轮模块结果 P4=258875、P16=118813 周期；这是 LC6 的模块测试值。

包装接口测试实际实例化 P4 和 P16 生产核，覆盖 AW/W 分别到达、WSTRB、B 通道背压、FIFO 压力、64 条记录、随机输出停顿、TLAST/填充位、START 0→1→等待→0 和第二轮软复位。LC6 P4/P16 周期分别为 252147/112083。

正式长测命令：`SIM_CASE_TIMEOUT=3600 bash tools/run_sim.sh stage1_production_full`。fixture、编译命令、RTL SHA、日志保留；短测不替代 LC50、完整布线或板端正确性。

## 正式 LC50 完整结果

两轮独立 oracle 模块：P4=1680956、P16=513755周期，模块周期改善约3.27倍。正式包装接口：P4=1674229、P16=507032周期；P4/P16均完成两轮64条记录、寄存器时序、随机背压、TLAST/填充及软复位再任务。这个比例是模块/包装测试周期，不是整机或实际网络任务提速。

Windows2026.1 运行证据：`D:/Agent/outputs/bkb220-xsim26/run-20261010-a4/`，两个 case 的 `xsim.console.txt` 及 xvlog/xelab 日志、14文件source_manifest和runner副本保留。LC50模块用时约6分29秒，接口约4分53秒。

Icarus LC50模块亦通过且两轮周期与XSim相同。其重复接口长测在XSim完整通过后主动停止，`execution_end.json`说明原因；不声称Icarus LC50接口已通过。原日志目录不删除。

复现：先用 `generate_stage1_fixture.py --num-lc 50` 生成独立oracle，再以 `tools/board/create_stage1_xsim_input.py --fixtures-dir <oracle目录> --out-dir /mnt/d/<新输入目录>` 复制并核查14文件。Windows运行 `tools/run_stage1_xsim.ps1 -InputDir D:/<输入目录> -RunDir D:/<新run目录>`，固定使用TB默认正式LC50并检查两轮哨兵。旧Icarus入口仍可使用。

## 尚未完成

新板 PS7/XDC 资料未确认，未生成新板完整 bit/XSA。尚无 Windows2026.1 新板整机 route、WNS/WHS/DRC 或实际 P4/P16 同板测量。历史 OOC WNS 和约 3.30 倍模块周期改进仍仅作背景，约 8.6 秒仍是估算。

仓库卫生 10/11 项通过，失败项是提交起点已存在的两个同字节 `agent_view.sh`（工具和 submission 附件）；本轮不删除既有提交材料。IP 打包门禁通过与整库卫生全绿必须分开陈述。

2026-10-10整理收尾：上文卫生FAIL属于当时快照；起点重复agent_view.sh附件已改为引用tools唯一源码，原字节有备份/Git历史、旧失败证据保留。当前整理结果以工作区整理记录和最终卫生日志为准，未放宽门禁。

## 2026-10-11 文档引用清理的证据边界

本轮只修正正式顶层与P4核中的旧文档引用，HDL去注释后的词法标记与修改前完全相同；模块、参数、端口与算法未改。原XSim输入快照、14文件SHA和运行日志继续保留，源SHA指向当时编译的字节，不能直接声称与当前注释字节相同。本轮没有重新运行长仿真或重建发布包；当前字节变化及等价复核在logs/host/current-residue-20261011/documentation-integrity.json及对应备份verification.json留证。新板时序和真板门禁仍未通过。
