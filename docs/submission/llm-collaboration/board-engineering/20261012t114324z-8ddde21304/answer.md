> 脱敏副本，原件 `20261012T114324Z-8ddde21304/{prompt.txt,answer.md}`。本机绝对路径、邮箱、凭据形模式及非白名单私网 IP 已替换；除脱敏与换行规范化外保留原文。

已完成第二阶段，结果追加在 [migration-source-table.md §8](<仓库根目录>/docs/board/bkb220/migration-source-table.md:204)。`hw/boards/bkb220.tcl` 未修改，`ready=0` 保持不变。

**Vivado 2022.2 验证：**最终探测命令退出码为 0，四套 PS7 IP 的 `validate_ip` 与 `generate_target` 均为 `rc=0`。原始 `MT41K256M16TW-107` 被 PS7 catalog 拒绝；最接近的 `MT41K256M16 RE-125/RE-15E` 不是可直接替代的料号。使用 `Custom` 后，32-bit、1GB 配置及草案时序被接受并生成，但这不证明实物 DDR 训练或读写成功。`xc7z020clg400-2` 在库中；手册标示的工业级 -2 对应项未找到，现有工业级 CLG400 条目速度档不同。走线延迟和温度配置仍待确认。

四个 `ps7_init.tcl` 均已生成，SHA-256 已复核：

| 变体 | 生成路径 | SHA-256 |
|---|---|---|
| UART0 MIO14–15 | `hw/build/bkb220-ps7-probe/20261012T114440Z-board-migrate-r3/v1-uart0-mio14-15/ps7_init.tcl` | `2f80e045cb18d7c37d5144bf0a819cd8fd42d09a622fca164f2ef7b007b6c81f` |
| UART0 MIO46–47 | `hw/build/bkb220-ps7-probe/20261012T114440Z-board-migrate-r3/v2-uart0-mio46-47/ps7_init.tcl` | `4e401a4886ccade2e97de36de2a5bda80be792828fbb2de488bf8c9168f9e2d2` |
| UART1 MIO08–09 | `hw/build/bkb220-ps7-probe/20261012T114440Z-board-migrate-r3/v3-uart1-mio08-09/ps7_init.tcl` | `b06959ccdeb9f867933411bc45dc061e9d6c3eff48ff4bb2ee08e10c7685d16a` |
| UART1 MIO48–49 | `hw/build/bkb220-ps7-probe/20261012T114440Z-board-migrate-r3/v4-uart1-mio48-49/ps7_init.tcl` | `308390212b257f3263c1e6f5e84e22a57d5cce8454110939980e38be8b6e456e` |

ENET0 的 MIO16–27、MDIO MIO52–53 与 1000 Mbps 属性通过 Vivado 验证；PHY ID 和链路仍**待 main 上板用 MDIO 验证**。F3 的 XSDB 命令、三路串口监听、DDR 轮询判据和失败恢复步骤已写入 §8.6。由于 `ps7_init` 不提供可靠的 DDR PASS 返回值，也不在 UART 打印校准信息，main 还需准备 OCM hello ELF 来验证串口归属和 DDR scratch 读写。

本任务未操作板卡，未生成 bit/XSA，未运行综合或实现；最终构建日志与四套 `.tcl/.html/.xci` 留在上述独立 run 目录。根目录工具日志检查无残留。仍待完成：工业级器件与 DDR 板级参数确认、hello ELF、板上 DDR/UART 实测及 ENET0 MDIO 验证。
