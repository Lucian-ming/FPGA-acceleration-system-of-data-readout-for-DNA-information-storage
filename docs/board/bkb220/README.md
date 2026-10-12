# BKB220 板级资料

- [BKB220产品手册v1.1.pdf](BKB220产品手册v1.1.pdf)：用户于2026-10-11提供的v1.1产品手册，按原文件字节复制，大小1,816,494 B。
- [BK_B220_SchDoc.pdf](BK_B220_SchDoc.pdf)：用户 2026-10-12 提供的 Altium 原理图（23 页 A4 横版），按原文件字节复制，大小 4,714,284 B。它补齐了此前缺的 F2 依据：PS_CLK 33.333MHz 晶振、**UART0 = MIO14/15**、**ENET0 为 RGMII**、**PHY = RTL8211E-VL**、**PHY 地址 = 1**、**PHY 复位 `PHYRSTB` 接 `PS_POR_B`（非 GPIO）**。逐条核对见[来源表 §10](migration-source-table.md)。
- [SHA256SUMS.txt](SHA256SUMS.txt)：原件与仓库副本的SHA-256校验值。

SHA-256：产品手册 `40b50e666ecab4ee83fbcfb1eea816a04a0989f73b001d9b9432e4778c8cd086`；原理图 `fb7947dfa762a58d7e6a178fc612d8ec48a1d05c677e60c357acc0697e8955a6`。在本目录运行 `sha256sum -c SHA256SUMS.txt` 可校验。

原理图入库后，此前「缺对应 PCB 原理图」的缺项**已关闭**；仍缺厂商 PS7 preset/board_files、原厂例程，以及**板卡实物与该版图修订是否一致（未核对）**。

板级迁移与资料缺项以[07板级配置与验收](../../07-board-build-and-acceptance.md)为准，完整流程沿用[05执行计划](../../05-implementation-plan.md)。原理图与手册都不能替代真板验收。
