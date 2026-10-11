# BKB220 迁移主机验证与真板待测边界（2026-10-10）

当前主机侧 47 项测试通过：`test_g3_artifacts.py` 40 项、`test_g3_performance_matrix.py` 7 项。没有连接新板，这些测试使用显式合成制品或客户端替身，不是 G3 真板结果。

## G3 制品与下载入口

`tools/board/g3_artifacts.py` 核查五件产物 bit/XSA/ELF/FSBL/BOOT、manifest/source_manifest 及 SHA256SUMS；核对 XSA 实际 part、内置 bit、生产几何和 P4/0 或 P16/1。拒绝 LC6 假生产包、7010/P16、跨器件、缺文件、篡改哈希、单独 bit/ELF 覆盖和已有 run 目录。新板无 manifest 不自动回退旧包。

`tools/run_g3.sh` 接受明确 artifact-dir、XSDB、device、win-root、PS USB COM；PS7 初始化只能取自所选 XSA。FT4232HL 多串口必须人工确定 PS 通道，禁止蓝牙和 COM6 猜测。XSDB 使用 PowerShell 参数桥接，目标器件在复位之前核对。

测试证据：`logs/host/g3-preflight-20261010/test_g3_artifacts.txt`；带空格路径的 XSDB 桥接测试见 `xsdb_bridge_fixture.txt`。该桥接测试只验证命令参数和退出码传递；不接 JTAG。

## 性能矩阵

`tools/board/g3_performance_matrix.py` 默认源读段 128/512/2048/8192/32768/全量，各至少 3 次。实际记录数按双向并补至 64 计算，拟合实际记录数；区分上传、POST 到 8100B 回传的 t_result、LDPC 和整轮时间。全量 LDPC/参考图片哈希失败的样本不进入成功拟合，小样本标注功能判据不适用，不能算完整正确性通过。

`--uart-log <持续追加的现有采集文件>` 可读取本轮 Stage2/3 原始寄存器周期。按本轮起始字节位置解析，拒绝重复任务日志混用；Stage1 周期尚未由此脚本采集，为 null。缺 UART 时如实标注未采集；不把墙钟乘时钟伪造成硬件周期。串口由外部唯一采集者持有。无功率计时功率为 null。

七项编排测试核对 ClientConfig 实际调用、LDPC CLI、精确补帧、当前轮 UART、重复周期拒绝、全量哈希失败排除和无效时间/同补帧档位拒绝。证据：`logs/host/g3-preflight-20261010/test_g3_performance_matrix.txt`。

## 真板仍需完成

按 [迁移计划](../05-implementation-plan.md) 的 S2～S4：新板 P4 基线、P16 完整时序、匹配 XSA 的 BSP/FSBL/应用/BOOT、真实 TCP/CAPS、全量至少 3 次、逐级 DDR、低阈值弄脏→正式判据、非法配置/断连恢复及同板六档性能。

最终判据仍为真实回传经 LDPC 后的 JPEG SHA-256：`fcd0cf90bd680e7bbdc203e3398119504da0897acac9e2117008b4efb6b1f2c3`。串口可用、TCP 有返回、四级中间检查或主机合成测试均不能单独替代该判据。

2026-10-10整理收尾：上文卫生FAIL属于当时快照；起点重复agent_view.sh附件已改为引用tools唯一源码，原字节有备份/Git历史、旧失败证据保留。当前整理结果以工作区整理记录和最终卫生日志为准，未放宽门禁。
