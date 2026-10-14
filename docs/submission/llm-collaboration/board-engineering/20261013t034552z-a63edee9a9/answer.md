> 脱敏副本，原件 `20261013T034552Z-a63edee9a9/{prompt.txt,answer.md}`。本机绝对路径、邮箱、凭据形模式及非白名单私网 IP 已替换；除脱敏与换行规范化外保留原文。

## 交付

已增加按 `input_bytes` 写出任意原始载荷的路径。新增 CLI 出口选用 `--payload`，与 `--image` 分开：`--image` 和旧 JPEG EOI 行为保持不变；`--payload` 必须搭配 `--input-bytes N`，不查找 `FF D9`。

改动涉及 [native_ldpc.py](<仓库根目录>/clients/python/native_ldpc.py)（`bits_to_payload_bytes`、`bits_to_jpeg_bytes`）、[ldpc_decode.py](<仓库根目录><本机路径>)、[run_g3.sh](<仓库根目录><本机路径>)、[test_g3_payload_decode.py](<仓库根目录>/tests/host/test_g3_payload_decode.py)，以及已登记新脚本的 [tools/README.md](<仓库根目录><本机路径>)。新增的 [repro_non_jpeg_decode_length.py](<仓库根目录><本机路径>) 用于复现长度问题。

## 复现与反向验证

用外部 v2 包的 `numeric_signal.csv` 构造了 54,000 bit 信息块（6,750 B，含零填充），调用旧 `bits_to_jpeg_bytes` 得到：

- `encoding.json input_bytes`：**3,862 B**
- 旧函数输出：**6,750 B**
- 期望 SHA-256：`ced298c4a2f882fa1406d843d96adf70f1a1bbf50a9f97b28f37fda8e255dd98`
- 旧函数 SHA-256：`69a9dedee82811f0629b6446fafacf85d8b58a893485d93128ce572b25cf9bb5`

用 v2 包已有的软件恢复块对照：其 `validation.json` 标记 `software_only=true`、`ldpc_converged=true`、`hash_equal=true`。新通路设 N=3862 时输出 3,862 B，SHA 与 `input_sha256` 相同；故意设 N=3863 时 SHA 变为 `318c1d62dd4e4a9a77c5347378a18b6983ad19b194467aeb56e50957ae1202a8`，与期望不同。这是软件对照，**不是板端结论**。

`input_bytes` 必须为正整数且不超过 6,750；CLI、转换函数和 G3 参数入口均拒绝越界值。

## 回归结果

以下命令均退出 **0**：

- `python3 -m unittest discover -s tests/host -p 'test_g3_*.py'`：59 项通过。
- `bash tests/host/run_host_tests.sh --worktree`
- `bash tools/check_ip_packaging.sh`
- `bash tools/check_repo_hygiene.sh`
- `python3 tools/ldpc_decode.py verify`

R0.83 自检改动前后输出相同：332 个起始失败校验、5 轮收敛、改写 91 bit、JPEG 6,624 B、SHA 前缀 `fcd0cf90bd680e7b`，均 PASS。`bash -n tools/run_g3.sh && git diff --check` 也退出 0；仓库根目录工具日志扫描无输出。

## 传参示例与未完成项

main 持板后可按资产元数据传入长度和 SHA，例如：

```bash
tools/run_g3.sh \
  --reads <本机路径> \
  --watermark <本机路径> \
  --full \
  --input-bytes 3862 \
  --expect-sha ced298c4a2f882fa1406d843d96adf70f1a1bbf50a9f97b28f37fda8e255dd98 \
  --tag numeric-signal
```

**状态：代码与指定离线回归 PASS；板端验证未测。** 按任务要求未触板、未运行仓库绑定门禁、未执行 Git 写操作；外部 v2 包未修改。交付文件留在工作树供 main 审查提交。看板 `verify-system` 已登记完成。
