> 脱敏副本，原件 `20261014T135456Z-e5e8dff608/{prompt.txt,answer.md}`。本机绝对路径、邮箱、凭据形模式及非白名单私网 IP 已替换；除脱敏与换行规范化外保留原文。

软件制品包已生成，位于：

`<仓库根目录>/hw/build/bkb220-p16-k2-ldpc-prefillopt-sw-20261014T135534Z-board-migrate/`

[manifest.json](<仓库根目录>/hw/build/bkb220-p16-k2-ldpc-prefillopt-sw-20261014T135534Z-board-migrate/manifest.json) 和 [构建验收报告](<仓库根目录>/logs/package/prefillopt-sw-package.md) 已写好。

- `run_g3.sh --strict-artifacts --plan-only` 退出码 **0**，门禁接受制品包。当前脚本要求绝对路径 WSL XSDB 提供 `G3_HW_SERVER_URL`，我通过环境变量提供了地址；plan-only 未连接它，也未创建 run 目录。
- `sha256sum -c SHA256SUMS`：**2969/2969 OK**。
- 新 BSP 的 `XPAR_LDPC_DECODER_0_BASEADDR` 为 **`0x43C30000`**；Bootgen readback 确认 `BOOT.bin` 含 FSBL、bit 和应用 ELF 三个 image。
- 包内 bit 与硬件包 bit 的 SHA-256 一致：`8d17d17e…f3f38898`。
- XSCT 平台、BSP 和 FSBL 生成成功；`app create` 因 `Socket create error. Operation not permitted` 退出 1。随后按要求使用同一安装树的 ARM GCC 编译并链接新 BSP，得到 `APP_BUILD_PASS`。

**未完成项：**没有上板；Stage1 板端判据与回传一致性仍待 main 验收。本次未做 Git 写操作。
