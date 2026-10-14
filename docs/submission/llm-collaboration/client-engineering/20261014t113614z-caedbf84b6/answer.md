> 脱敏副本，原件 `20261014T113614Z-caedbf84b6/{prompt.txt,answer.md}`。本机绝对路径、邮箱、凭据形模式及非白名单私网 IP 已替换；除脱敏与换行规范化外保留原文。

P0 已完成。`unittest.main()` 已移到测试文件末尾，直接运行和 discovery 都收集并通过 25 个用例；统一入口会先检查 8 个 Python 文件语法，再运行 discovery 并核对用例数下限 25。

**验收结果**

- 直接运行：25 tests，OK，退出码 0。
- unittest discovery：25 tests，OK，退出码 0。
- `bash tools/test_client.sh`：语法检查通过，实际收集 25 个用例，PASS，退出码 0。
- 故障注入：临时必失败断言使入口报红，`FAILED (failures=1)`，退出码 1；测试文件已逐字节恢复。
- `bash tools/check_repo_hygiene.sh`：PASS，退出码 0。
- `bash tools/check_ip_packaging.sh`：PASS，退出码 0。

**产出**

- [test_client_core.py](<仓库根目录>/clients/python/tests/test_client_core.py)
- [test_client.sh](<仓库根目录><本机路径>)
- [tools/README.md](<仓库根目录><本机路径>)：仅新增一行脚本登记
- [p0-report.md](<仓库根目录>/logs/client/p0-report.md)：记录改动和各项实测输出

本轮未做 P1/P2/P3、板端验证或客户端功能完备性验证；未执行 Git 写操作。
