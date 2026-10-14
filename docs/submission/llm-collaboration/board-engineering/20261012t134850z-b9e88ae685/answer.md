> 脱敏副本，原件 `20261012T134850Z-b9e88ae685/{prompt.txt,answer.md}`。本机绝对路径、邮箱、凭据形模式及非白名单私网 IP 已替换；除脱敏与换行规范化外保留原文。

## 结论

**lwip220 的 Realtek 改动可能缓解 PHY 复位后的启动时序问题，但代码对照不足以证明它能修复 F4 的持续自协商超时。** 我没有修改安装树源码，也没有生成新软件包；以下是可核对的取证结果，不能视为修复完成。

## 源码对照

已阅读 [迁移来源表 §11](<<仓库根目录>/docs/board/bkb220/migration-source-table.md>) 和 [docs/07 §3a](<<仓库根目录>/docs/07-board-build-and-acceptance.md>)，并对照 [lwip211 源码](<<本机路径>>) 与 [lwip220 源码](<<本机路径>>)。

- **`Configure_Phy_Speed`：主要是重构。** 自协商分支仍是读改写 ANAR、GBCR，再设置 BMCR 的自协商使能与重启位；与 lwip211 的内联操作顺序和内容一致。
- **`Reset_Realtek_Phy`：多了 1 秒稳定延时。** 两版都会设置 BMCR 软复位并轮询复位位清零。lwip220 在此后 `sleep(1)`，这是最实质的行为差异；它可能缓解复位后立即访问 PHY 的时序问题，但不足以证明能解释持续约 30 秒的超时。
- **`Wait_Autoneg_Complete`：轮询主体基本相同。** 两版都是先读 BMSR，再每秒等待并重读 bit5；`>=` 与旧代码的 `== 30` 在正常计数中没有实质差异。lwip220 的默认超时是 **5 秒**，lwip211 当前是 **30 秒**，照搬默认值会缩短等待时间，可能更早失败。
- **`get_Realtek_phy_speed`：关键顺序没有改变。** 两版仍然是先配置并启动自协商，之后软复位，再等待 BMSR bit5。复位是否清掉此前配置或重启状态，两版都没有在复位后重新配置，因此这次移植本身不能消除该疑点。
- **依赖与调用点：** 目标函数所需的 `IEEE_*` 宏在 lwip211 头文件中已有；没有发现必须新增的头文件。lwip220 在本文件本地定义了 `PHY_SPEED_AUTONEG`、`PHY_AUTONEG_ENABLE` 和 `PHY_AUTONEG_TIMEOUT_DEFAULT`，lwip211 中没有这些定义；若移植须本地补定义或直接传值。`Configure_Phy_Speed` 还被 TI RGMII、TI SGMII、Marvell、ADI 自协商路径和固定速率路径调用。只移植 Realtek 路径时，不应因此改动这些其他路径。

**根因判断：** 代码事实是独立 MDIO 读取曾观察到 BMSR bit5 已置位；这证明 PHY 能报告自协商完成，但不能证明失败时驱动读取的是同一地址、同一时刻或成功的 MDIO 事务。当前差异没有改变 BMSR 轮询机制。更有价值的下一步是记录驱动实际选用的 PHY 地址，以及复位前后的 BMCR、ANAR、GBCR、BMSR 读写结果和 MDIO 返回状态；重点确认复位后自协商配置是否仍有效。**真正原因尚未由本次源码对照确定。**

## 补丁与制品状态

目标安装文件当前及复核后的 SHA-256 均为：

`2e05d7ae1ebe0094dab10742cc29868a1bef7b91a3a888f030ef96f4da68e7ad`

lwip220 对照文件 SHA-256：

`bb58d502d22544d34827c1262e15c2b5a6dc139c267dbb1ba29f110e8958b8d1`

本会话的 sandbox 只允许写项目目录和 `/tmp`，不允许写任务指定的 `<本机路径>` 安装树。因此：

- 未修改目标源码，**没有补丁 diff**。
- 未创建要求的 `.orig` 备份；目标文件保持原样，当前无需回滚。若后续由有权限的会话修改，应先在原目录备份为 `xemacpsif_physpeed.c.orig`；回滚时用该备份恢复目标文件。
- 未生成独立 BSP、应用 ELF、FSBL、BOOT.bin、readback、SHA 清单或 manifest，也未运行新包的 `g3_artifacts.py` 预检。
- [现有 F4 包](<<仓库根目录>/hw/build/bkb220-p4-software-20261012T130201Z-board-migrate-f4/>)使用的 P4 XSA 与 P4 基线 XSA SHA 相同：`5e1a966a9dfd45887292a5cfccc720cadb6f47181cc989b31995bb334dad98bc`。这只是输入基线核对，不能替代新软件包。
- `sw/app` 未修改；未运行 host tests。没有触板，也没有板测结论。
- 遵照本轮指令，未运行 `tools/verify_repo_binding.sh`；因此 AGENTS.md 所列开发前绑定门禁没有本轮核验结果。

## 给 main 的板测判据与下一手

补丁构建并烧录后，UART 中 `Waiting for PHY to complete autonegotiation.` 后应出现 **`autonegotiation complete`**，并继续打印 PHY 地址与协商速率；若仍超时，移植后的等待函数应打印 **`Auto negotiation timeout`**，而不是旧实现的 `Auto negotiation error`。lwip220 默认超时为 5 秒；若移植时保留 lwip211 的 30 秒等待，则失败行会在约 30 秒后出现。

若超时，下一步在同一轮启动中记录实际 `phy_addr`，并采集复位前后 BMCR、ANAR、GBCR 与 BMSR 的值及 MDIO 读写返回状态；特别检查复位是否清除了广告或自协商配置。若出现 `autonegotiation complete` 但网络仍不通，再检查协商速率状态和 RGMII 延迟配置。不要仅凭 TCP server 启动日志判定 GEM 链路已通。

| 检查项 | 状态 |
|---|---|
| 指定资料与源码对照 | PASS |
| 安装树补丁及 `.orig` | 未完成：sandbox 不允许写 `/tools` |
| 新 BSP 包与 `g3_artifacts.py` 预检 | 未完成：没有新包 |
| 板测 | 未测 |
| `sw/app` 变更 | 无 |

看板条目已按要求以 `board-migrate` 完成登记并收工。
