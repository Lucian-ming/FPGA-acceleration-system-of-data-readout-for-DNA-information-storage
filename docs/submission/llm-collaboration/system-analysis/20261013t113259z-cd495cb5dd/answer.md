> 脱敏副本，原件 `20261013T113259Z-cd495cb5dd/{prompt.txt,answer.md}`。本机绝对路径、邮箱、凭据形模式及非白名单私网 IP 已替换；除脱敏与换行规范化外保留原文。

## 交付

- 新包：[manifest.json](<仓库根目录>/hw/build/bkb220-p16-upload-promoted-20261013T113400Z-board-migrate/manifest.json)、[SHA256SUMS](<仓库根目录>/hw/build/bkb220-p16-upload-promoted-20261013T113400Z-board-migrate/SHA256SUMS)
- 构建与板测记录：[bkb220-p16-upload-promotion.md](<仓库根目录>/docs/benchmarks/bkb220-p16-upload-promotion.md)
- 构建摘要：[software_build_summary.md](<仓库根目录>/hw/build/bkb220-p16-upload-promoted-20261013T113400Z-board-migrate/reports/software_build_summary.md)

## 核验结果

- **两处改动确实进入新包：** BSP 的 `TCP_WND` 为 `32768`；显式清理并重编后的 `liblwip4.a` SHA 为 `1cc4d99e…14c32d1c`，冻结包对应 SHA 为 `ce1944be…0c45e6ff`。应用源码与 `sw/app/main.c` 逐字节相同，默认 `PIPE_IDLE_FETCH_N` 为 `16U`，ARM GCC 构建通过。
- bit、XSA、ps7_init、FSBL 与冻结包的 SHA 逐项相同，且 `cmp` 四项均通过。完整包 SHA 自检 **2966 项全 OK**；G3 制品静态门禁报告 P16/SE150 参数正确。
- XSCT 正式流程生成了平台/BSP；`app create` 遇到已知 socket 错误后，按实际记录改用 ARM GCC Makefile 构建应用。Bootgen 创建及 readback 均通过，具体路径和退出码已写入报告。

## 上板结论与未完成项

- **G3 板端判据没有 PASS，也没有 FAIL：本轮未运行到设备访问。** `cmd.exe` 创建 Windows 留证目录时遇到 `UtilBindVsockAnyPort:307: socket failed 1`；G3 因留证目录不可见，在 XSDB 前置检查处退出 2。
- 因未获得板端载荷和客户端上传日志，**本轮不能确认判据 SHA，也不能声称上传耗时降到约 0.2 秒**。
- 泛化和长稳未运行。报告文档留在当前分支工作树，未执行 Git 写操作。
