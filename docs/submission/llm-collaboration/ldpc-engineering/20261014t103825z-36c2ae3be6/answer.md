> 脱敏副本，原件 `20261014T103825Z-36c2ae3be6/{prompt.txt,answer.md}`。本机绝对路径、邮箱、凭据形模式及非白名单私网 IP 已替换；除脱敏与换行规范化外保留原文。

### 改动与产物

- 新增 [ldpc_onchip.c](<仓库根目录>/sw/app/ldpc_onchip.c) 和 [ldpc_onchip.h](<仓库根目录>/sw/app/ldpc_onchip.h)：按 LSB-first 装载 2,025 个字，非阻塞轮询 DONE；收敛后读回并 flush，未收敛、报错或超时时保留原 Stage3 结果。
- 修改 [pipeline.h](<仓库根目录>/sw/app/pipeline.h)、[echo.c](<仓库根目录>/sw/app/echo.c)、[stage3_decoder.c](<仓库根目录>/sw/app/stage3_decoder.c)，并同步对应文件到 `sw/workspace/dna_lwip_app_b27/src/`。原发送状态和 8,100 B 结果长度不变。
- 修改 [create_vitis.tcl](<仓库根目录>/sw/scripts/create_vitis.tcl)：首次生成 BSP 后再设置 `TCP_WND` 并重新生成，以支持全新 workspace。
- 软件包位于 `hw/build/bkb220-p16-k2-ldpc-sw-20261014T104331Z-board-migrate/`；入口清单见 [manifest.json](<仓库根目录>/hw/build/bkb220-p16-k2-ldpc-sw-20261014T104331Z-board-migrate/manifest.json)，摘要见 [software_build_summary.md](<仓库根目录>/hw/build/bkb220-p16-k2-ldpc-sw-20261014T104331Z-board-migrate/reports/software_build_summary.md)。

  任务描述中的硬件包没有 `export/dna_accel.xsa`；实际唯一 XSA 是 `export/bkb220_p16_k2_ldpc.xsa`。我从该文件构建，并在新软件包中以 `export/dna_accel.xsa` 交付。

### 验证结果与未完成项

- 新 BSP 的 [xparameters.h](<仓库根目录>/hw/build/bkb220-p16-k2-ldpc-sw-20261014T104331Z-board-migrate/workspace/bkb220_p16_k2_ldpc_platform/ps7_cortexa9_0/standalone_domain/bsp/ps7_cortexa9_0/include/xparameters.h) 确认宏为 `XPAR_LDPC_DECODER_0_BASEADDR`，值为 `0x43C30000`。
- BSP、FSBL 已由新 XSA 的 XSCT 平台生成；应用用 Vitis 2022.2 ARM GCC 11.2.0 编译，结果为 `APP_BUILD_PASS`。Bootgen 生成成功，readback 包含 FSBL、bit 和应用 ELF。
- [SHA256SUMS](<仓库根目录>/hw/build/bkb220-p16-k2-ldpc-sw-20261014T104331Z-board-migrate/SHA256SUMS) 自检通过：2,958/2,958 文件匹配。`sw/app` 与 workspace 同名文件逐字节检查通过。
- **XSCT 应用创建未完成**：`create_vitis.tcl` 生成平台/BSP/FSBL 后，`app create` 因 `Socket create error. Operation not permitted` 退出 1；应用随后直接用同一安装树的 GCC、链接新 BSP 构建。两次 XSCT 运行日志都保留在软件包 `logs/`。
- **仓库卫生门禁未通过**：[check_repo_hygiene.log](<仓库根目录>/hw/build/bkb220-p16-k2-ldpc-sw-20261014T104331Z-board-migrate/reports/check_repo_hygiene.log) 记录唯一失败项：`hw/experimental/ldpc_decoder_p1.v` 与 `hw/ip/ldpc_decoder_1_0/hdl/ldpc_decoder_p1.v` 是相同 SHA 的重复文件。任务禁止修改这两个目录，因此未处理该既有问题。
- 未运行 Vivado、仿真或板卡验收；因此编译和软件包自检通过不代表 LDPC 已在板端运行通过。

### 上板优先判读

最先核对 UART 是否依次出现收敛日志和 `wrote back 2025 words`。若没有终态日志，检查状态寄存器 `0x43C30004`：bit 0–5 分别是 busy、done、converged、error、loading、readback，`[15:8]` 是有符号迭代轮数。若显示收敛但主机结果 SHA 不符，优先逐字节核对 8,100 B 读回结果与 LSB-first 位序；若未收敛，输出应保持 Stage3 原结果。
