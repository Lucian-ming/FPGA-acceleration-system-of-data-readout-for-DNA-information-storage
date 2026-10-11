# 06 · 验证、压力与故障恢复

本文件合并原08验证与12压力分析；当前准备结果见03，阶段计划及命令在05，历史完整内容见[归档索引](archive/history/2026/pre-bkb220-handoff-2026-10-10/README.md)。

## 1. 验证层级与最低判据

| 层级 | 入口 | 能证明什么 |
|---|---|---|
| 数据/算法契约 | golden_model.py verify-code、make_golden.py及黄金SHA | 编码/位序/几何；wm_regions哨兵不能被最终图像哈希替代 |
| 主机门禁 | tests/host的G3与性能用例、tests/board | 参数/制品/串口/路径/统计正确，使用替身不能替代真板 |
| 固件行为 | tests/host/run_host_tests.sh --worktree及故障注入 | 实际C源码对外寄存器/DMA/cache/TCP轨迹；B27重新注入应红；不能重录黄金掩盖变化 |
| IP模块 | run_sim.sh各级与stage1_production/full | 正式源集功能，LC6短测与LC50正式分别标明 |
| 真实接口 | run_xsim.sh all、Stage1真实AXI包装TB | AW/W独立、WSTRB、AXIS背压/TLAST/FIFO、START0→1→0、顺序/拍数/补帧/重复/复位 |
| 三级和BD | run_m2_full.sh、run_m3_bd.sh | 三级串联、PS7控制/互连、DDR背压与复位；改相关接口才扩展到对应层 |
| 完整实现/软件 | WSL22主线route/Vitis/Bootgen；最后Windows26独立重建 | WNS/WHS、TNS/THS、DRC、合法约束/路由；实际BSP/ELF/FSBL/BOOT，不代表启动 |
| 真板G3 | run_g3.sh --artifact-dir完整包 | 下载、CAPS、真实任务、LDPC、图片SHA和四级DDR；唯一端到端验收 |

只编译、有波形、有GUI图片或退出0都不够。改数据契约需Python/PS/RTL对应回归；改接口需真实接口TB及负用例；改固件需工作树行为与新制品；改板级需最小启动和G3；性能修改需公平同输入板测。

## 2. 正式Stage1专项

SE150固定READ_BPS=150、NUM_LC=50、STRIDE=807、REF_LEN=957、BATCH=64；P4=4/0、P16=16/1。独立oracle直接逐符号枚举，校验最大score、首并列pos和cw，覆盖最后region、末组有效lane、正/反向、零分/全并列、37条有效+27补零、第二轮重跑。

模块及包装两个case必须记录LC50，两轮均PASS；LC6用于短排错。正式源集从component.xml/manifest贯通到TB/综合。Windows2026.1复现使用generate_stage1_fixture.py→create_stage1_xsim_input.py→run_stage1_xsim.ps1，14文件输入SHA；命令见05。[本轮正式结果](benchmarks/stage1-16way-ip-integration.md)不包含新板route/G3。

## 3. 新板正确性与压力顺序

1. 完整制品/器件/七参数/工具/源码SHA预检，唯一JTAG/实际PS UART；最小UART、DDR安全区、GEM、CAPS通过。
2. 新板P4、再P16：2048源读段smoke→全量至少3次→full/2048/full连续序列；最终D0 JPEG SHA必须相同。
3. 严格弄脏轮：低阈值/足量输入把累加器弄脏，再67干净轮；验证第二轮正确及各状态/cache重新初始化。不能用弱弄脏掩盖不重置。
4. CONFIG超容量/不对齐/零条数/不支持几何、畸变包、断网/断连、超时和恢复，拒绝码从CONFIG_OK载荷读取，0才接受；错误后正常任务必须恢复。
5. 旧stress_test_suite.py/switch_export.sh已成对原样归档至docs/archive/tools/2026/retired-20261011，不再作为现用入口。新板长稳以run_g3.sh --artifact-dir完整包、显式XSDB/device/实际PS串口和现用guard/recovery/netfault探针编排，保存逐轮证据，以实际墙钟时长验收2h/8h；禁止自动切SE250或覆盖旧export。 现用泛化和故障脚本按同一完整包与显式目标审计适配后运行。
6. 多payload至少5组、受控sub/ins/del×覆盖度×阈值×至少3种子；区分合成/真实、主机复算/板测、FAR/FRR与最终恢复率。D0没有真值位置，不能报告其FAR。

7. 22主线稳定后按05 F9及07独立验证Windows2026.1完整开发，冻结相同源/输入/参数，比较合法100MHz整机、实际接口/任务结果、G3/恢复/性能与长稳；不同工具产物不要求整文件SHA相等，各包自身仍需完整SHA与同源链。

## 4. 统计与失败分类

每轮记录board/profile/part、源码/输入/制品SHA、源读段和补帧记录数、阈值/方向、t_fastq/t_upload/t_result/t_ldpc/整轮、原始码字误差/syndrome/LDPC迭代/图片SHA、硬件周期、failure_class和run目录。至少区分pass、functional、communication、tooling、boundary_expected、fault_injection_expected。

真板性能用同板P4/P16六档各≥3次；中位数、min/max/标准差、固定开销+每记录斜率同时给出。小规模覆盖不足可以边界失败，但全量译码/SHA失败必须使功能门禁失败并保留，不能从fit/样本中悄悄删掉。原始UART周期来自唯一采集者且按本轮offset读取；未测Stage1周期/功耗为null，不以墙钟×100MHz冒充。

## 5. 证据与资源

每次运行全新run-id/目录，保存命令、退出码、参数、输入/source manifest、工具版本、原始日志与PASS/FAIL哨兵、摘要/边界。大产物留本地，必要小摘要入库。只同时一个大型EDA任务、一个板任务、一个串口采集进程；所有reset/halt/dump占板资源。长期测试停止时写INTERRUPTED，不包装成PASS。

已通过的检查在无相关变更时不无意义重跑；发生新修改、失败或未知担忧才扩展验证。起点卫生重复告警及处理过程继续记录，唯一源码SHA不变，不放宽门禁隐藏。
