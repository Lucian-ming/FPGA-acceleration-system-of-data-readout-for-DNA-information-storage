> 脱敏副本，原件 `20261012T131141Z-39a08a710a/{prompt.txt,answer.md}`。本机绝对路径、邮箱、凭据形模式及非白名单私网 IP 已替换；除脱敏与换行规范化外保留原文。

P4 同源软件包已完成静态构建，产物在：

`<仓库根目录>/hw/build/bkb220-p4-software-20261012T130201Z-board-migrate-f4/`

详细命令、状态、六制品 SHA-256 和 main 的板测交接清单见[软件构建摘要](<<仓库根目录>/hw/build/bkb220-p4-software-20261012T130201Z-board-migrate-f4/reports/software_build_summary.md>)。

**验证结果：** BSP、应用 ELF、FSBL 检查、Bootgen 生成和 readback 均退出 0；readback 读到 FSBL、PL bit、应用 ELF 三个镜像。最终 `SHA256SUMS` 的 23 项全部通过，G3 只读预检退出 0，接受 `xc7z020clg400-2` 和 P4 参数。`artifact_manifest.json` 已生成；由于当前 G3 工具实际读取 `manifest.json`，包内同时提供了内容相同、均有 SHA 覆盖的 `manifest.json`。应用构建哨兵为：

```text
APP_BUILD_PASS source=sw/app BSP=generated-from-P4-XSA lwip=lwip211_v1_8
```

**实际 lwIP：** Vitis 2022.2 选中 `lwip211_v1_8`（上游 2.1.1）；2026.1 的 `lwip220` 属于另一条 F9 路径（2.2.0）。版本差异已记录，不作为本次失败理由。

**未完成项：** XSCT 在 `app create` 阶段因本地 socket 被拒绝而整体退出 1。应用 ELF 随后用 Vitis 2022.2 自带 GCC，针对该 XSA 生成的 BSP 直接编译，状态 0；因此制品齐全，但 XSCT 管理的应用工程本身未生成。Bootgen 还报告两条分区地址重叠 warning，已保留在日志。板端 G3、启动和冷启动均未测。

`sw/app` 与 `sw/linker` 未修改；编译快照排除了历史 `xparameters.h`，并确认依赖的是实际 BSP 生成的头文件。已有 `host-tests.log` 记录工作树行为测试通过，本轮未因源码未改而重跑。

main 板测请使用 `export/top_bd_wrapper.bit`、`export/ps7_init.tcl` 和 `export/dna_lwip_app.elf`；UART 为 `<本机路径>`。G3 首轮参数：`--artifact-dir <包根> --xsdb <本机路径> --hw-server TCP:127.0.0.1:3132 --device xc7z020 --strict-artifacts --uart-port <本机路径> --ip 192.168.1.10 --port 7 --limit 2048`。预期关键打印包括 `DNA Accelerator Complete Pipeline`、`[INIT] DNA Accelerator ready`、`Board IP: 192.168.1.10` 和 `*** Waiting for connections ***`；完整清单见摘要。
