> 脱敏副本，原件 `20261012T111757Z-da68ff4265/{prompt.txt,answer.md}`。本机绝对路径、邮箱、凭据形模式及非白名单私网 IP 已替换；除脱敏与换行规范化外保留原文。

已完成 BKB220 板级来源表和候选 profile：

- [migration-source-table.md](<仓库根目录>/docs/board/bkb220/migration-source-table.md) 记录了手册页码、main 提供的现场实测、未确认项、入口守卫审计和 F3 最小启动步骤。
- [bkb220.tcl](<仓库根目录>/hw/boards/bkb220.tcl) 已补齐 profile 字段和候选 PS7 属性，`ready` 保持 `0`。

验证结果：

- 手册 SHA-256 校验通过：`BKB220产品手册v1.1.pdf: OK`，exit 0；已提取全部 30 页文本，并目视核对规格所在页。
- Tcl profile 结构检查通过：8 个字段齐全，29 对 PS7 属性无重复。
- `tclsh hw/scripts/build.tcl board=bkb220 dry_run=1` 按预期 exit 1，在 `dna_load_board` 的 `ready=0` 守卫处给出缺项说明；未进入 `file mkdir` 或 `create_project`。完整输出已写入报告。
- 仓库根目录未发现 `.log`、`.jou`、`.str` 或 `.pb` 文件。

报告区分了器件 `-107` 等级和手册所述 533.333 MHz DDR3-1066 候选运行点：Micron 资料将 `-107` 列为 1866 MT/s 等级；CL/CWL、tRCD、tRP、tRC、tRAS、tFAW 是按 DDR3-1066 器件时序表推导的草案，**不是板测或 Vivado 验证结果**。[Micron 料号页](https://www.micron.com/products/memory/dram-components/ddr3-sdram/part-catalog/part-detail/mt41k256m16tw-107-m-p) · [Micron 4Gb DDR3L 数据表](https://datasheet.lcsc.com/datasheet/pdf/5dffd7a5abc502f4a8d151b6c508c1b4.pdf?productCode=C2888412)

仍未完成：PS_CLK 频率、PS UART MIO、ENET0 PHY/MIO/MDIO/RGMII/复位、DDR 板级延迟与 DQS-to-CLK、厂商 preset/原理图及 Vivado 2022.2 catalog 验证。未运行 Vivado、未操作板卡/JTAG/串口。手册 p.16 的“1Gb”摘要与 p.9–10 两颗 4Gbit DDR 的 1GB 计算不一致，已列为待厂商确认项。

`board-migrate` 看板状态已登记为完成；没有执行 Git 写操作。
