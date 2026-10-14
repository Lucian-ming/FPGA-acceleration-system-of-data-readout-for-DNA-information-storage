> 脱敏副本，原件 `20261014T124212Z-ceadb329a0/{prompt.txt,answer.md}`。本机绝对路径、邮箱、凭据形模式及非白名单私网 IP 已替换；除脱敏与换行规范化外保留原文。

已完成测试、资源清单、打包 spec 和客户端文档更新。交付报告见[tests-docs-report.md](<仓库根目录>/logs/client/tests-docs-report.md)。

**验收结果**

- `bash tools/test_client.sh`：PASS，实际收集 **28 项**。
- `bash tools/check_repo_hygiene.sh`：PASS。
- 未纠对测试故障注入后按预期失败：`AssertionError: 332 != 333`，退出码 1；恢复断言后全套测试通过。
- 成功留证校验为 `0/10800`，载荷 SHA-256 与指定值一致；失败留证抛出 `BoardCodeRejected`，`failed_rows=332`。
- 8 个资源清单哈希均匹配；7 个二进制哈希未改变。根目录工具日志检查无残留。

本轮更新了[测试](<仓库根目录>/clients/python/tests/test_client_core.py)、[测试脚本](<仓库根目录><本机路径>)、[资源清单](<仓库根目录>/clients/python/resources/SOURCES.json)、[资源说明](<仓库根目录>/clients/python/resources/readme.txt)、[打包 spec](<仓库根目录>/clients/python/gui_app.spec)和[客户端 README](<仓库根目录>/clients/python/README.md)。

**未完成项**

Windows PyInstaller 打包未执行：当前环境没有 PyInstaller，且打包要求在 Windows 侧运行。因此没有生成或验收 exe；本轮也没有新跑板，测试使用的是已有留证。旧外部解码器 EXE 和三个 MinGW DLL 已从 spec 移出，但按要求保留在资源目录和清单中；`libc_ldpc.so` 仍由离线工具使用。未执行 Git 写操作，也未修改 `gui_app.py`、`first.py` 或核心译码管线。
