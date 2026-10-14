> 脱敏副本，原件 `20261014T114834Z-2000d09787/{prompt.txt,answer.md}`。本机绝对路径、邮箱、凭据形模式及非白名单私网 IP 已替换；除脱敏与换行规范化外保留原文。

## 已交付

- 新增 [SOURCES.json](<仓库根目录>/clients/python/resources/SOURCES.json)，记录 8 项资源的哈希、来源、构建命令和平台；原有资源文件哈希均与基线一致。
- [c_ldpc.py](<仓库根目录>/clients/python/c_ldpc.py) 在动态库载入前校验 SHA-256；[ldpc_pipeline.py](<仓库根目录>/clients/python/ldpc_pipeline.py) 让 Windows 缺少 C DLL 时显示警告，并标明实际后端为 `native (Windows c_accel unavailable)`。选择了方案 (a)，未做未经验证的 Windows DLL 构建。
- [build_c_accel.sh](<仓库根目录>/clients/python/build_c_accel.sh) 重建后会刷新清单哈希和平台字段；已在隔离的 `/tmp` 副本验证。
- [gui_app.spec](<仓库根目录>/clients/python/gui_app.spec) 不再打包 Linux `.so`，并按 spec 所在目录定位资源；[README.md](<仓库根目录>/clients/python/README.md) 补齐使用、诊断和 Windows 打包说明，命令格式参考了 [PyInstaller 官方文档](https://pyinstaller.org/en/stable/usage.html)。
- GUI 四项候选均经读码确认缺失。本轮增加了 JSON 参数预设存取；多轮/批量运行、结果历史与对比、失败样本归档仍未实现。具体依据和预设操作判据见[交付报告](<仓库根目录>/logs/client/p2p3-report.md)。

## 验收结果

- `bash tools/check_repo_hygiene.sh`：PASS。
- `bash tools/test_client.sh`：PASS，31 项运行、1 项跳过；跳过项是 Linux 环境无法运行 Windows PE external 后端。native 与 c_accel 的译码 SHA 一致。
- 清单哈希故意改为全零后，动态库在 `ctypes.CDLL` 前被拒载；恢复清单后复验通过。
- CLI dry-run：exit 0；输出 SE150、40 B、`total_reads=128`、`score_min=67`，未连接板端。
- GUI 启动：当前环境缺少 `tkinter`，实际启动 exit 1；参数预设逻辑用模块桩完成往返与非法 JSON 检查，但真实 GUI 交互仍待验证。

未修改现有资源二进制，未执行 Git 写操作，也未运行 PyInstaller。Windows GUI 交互、exe 打包与启动、Windows external 后端运行及板端验证尚未完成。
