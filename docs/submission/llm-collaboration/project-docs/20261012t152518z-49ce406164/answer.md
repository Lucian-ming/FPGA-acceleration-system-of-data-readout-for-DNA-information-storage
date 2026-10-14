> 脱敏副本，原件 `20261012T152518Z-49ce406164/{prompt.txt,answer.md}`。本机绝对路径、邮箱、凭据形模式及非白名单私网 IP 已替换；除脱敏与换行规范化外保留原文。

已完成 8 个技能包审阅，并新增 [AUDIT.md](<仓库根目录>/docs/submission/skill/AUDIT.md)。

修改包括技能入口、全部 8 个包的 README，以及 [ooc_probe.tcl](<仓库根目录>/docs/submission/skill/fpga-timing-probe/ooc_probe.tcl) 和 [baremetal_baseline.tcl.in](<仓库根目录>/docs/submission/skill/accel-vs-cpu-baseline/baremetal_baseline.tcl.in)。其中重点补充了 BKB220 的 ENET0/MDIO 排查步骤、P16 板测证据边界，以及 OOC 时序和基线模板的失败判据。

逐包结论：

- **board-bringup-debug**：补齐 PS 初始化、正式制品 MIO 核验、MDIO 位定义和 PHY 检查流程。
- **fpga-timing-probe**：更新到 BKB220 的 `xc7z020clg400-2`；路由后 setup/hold 失败会非零退出。资源预算仍需项目自行设定。
- **bottleneck-attribution**：补充 P4/P16 全量 `t_result` 对照及口径边界；通用噪声阈值仍未定义。
- **accel-vs-cpu-baseline**：将 XC7Z010 的 ARM 数据标为历史；模板现会对超时或板端错误状态失败，但没有主机逐字段比较器。
- **board-stage-evidence**：区分主机黄金模型和板上几何判据，补充 P16 全量与脏轮/干净轮证据。
- **ip-packaging-hygiene**：补充 P4/P16 manifest 身份核对，修正不准确的时间跨度。
- **ai-agent-collaboration**：明确看板脚本只有仓库内唯一源码，单独复制技能目录时脚本不会随包提供。
- **claims-ledger**：补充 P16 可说与不可说的示例，并区分已提交摘要和仓库外原始日志。

验证方面，指定事实来源和旧内容标识已核对；技能正文未发现 SE250 或旧 `export/` 路径。`git diff --check` 和空白检查通过。未运行测试、Vivado、XSDB 或板卡操作，因此脚本改动尚未在工具中执行；没有进行 Git 写操作。

**剩余缺口**：独立技能包缺少可直接运行的看板脚本；裸机模板缺逐字段比较器；OOC 资源预算和性能测量噪声阈值仍需明确；P16 剩余故障探针与六档性能矩阵仍待完成。命名扫描发现 8 个包 README 和入口 `README.md` 使用大写文件名，指定产出的 `AUDIT.md` 也含大写；我没有改名，已在审计中列出供 main 处理。
