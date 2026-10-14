> 脱敏副本，原件 `20261014T124212Z-ceadb329a0/{prompt.txt,answer.md}`。本机绝对路径、邮箱、凭据形模式及非白名单私网 IP 已替换；除脱敏与换行规范化外保留原文。

你是本项目的客户端子 Agent，工作目录 <仓库根目录>。你负责**测试、资源清单、打包 spec 与文档**这一半；另一位子 Agent 在改 `gui_app.py` 与 `first.py`，**不要碰这两个文件**。

【背景 —— 用户刚下的架构决定】
**LDPC 译码全部由 FPGA 片上完成，PC 端彻底不做译码；PC 若还需要"再译一次"就说明板端没纠对，那是失败，不允许 PC 兜底。**

核心已由 main 改完（`clients/python/ldpc_pipeline.py` 已重写，**不要改它**）。接口：
```python
from ldpc_pipeline import verify_board_result, BoardVerifyResult, BoardCodeRejected
res = verify_board_result(result_bits_path, output_dir, input_bytes=None, log=None) -> BoardVerifyResult
# BoardVerifyResult: result_path, dec_input_path, decoded_bits_path, payload_path,
#                    payload_bytes, failed_rows, total_rows；属性 .verified
# 板端没纠对 => 抛 BoardCodeRejected(failed_rows, total_rows)  （这是失败判据）
```
旧的 `run_ldpc_decoder` / `LDPCResult` / `SUPPORTED_BACKENDS` **已不存在**。
`native_ldpc.hard_decode` **仍然存在**（离线工具与数据集生成在用），**不要删**。

【本轮范围：四件事】

**1. `clients/python/tests/test_client_core.py` —— 把测"多后端"的用例换成测新架构**
- 删掉针对 `c_accel` / `external` / 后端分派 / `LDPCResult.backend` 的用例（它们测的东西已经不存在了）。
- 新增用例，**至少覆盖**：
  a) **板端已纠对 → 通过**：用真实留证
     `<本机路径>`，
     断言载荷 SHA == `fcd0cf90bd680e7bbdc203e3398119504da0897acac9e2117008b4efb6b1f2c3`。
  b) **板端未纠对 → 必须失败**：用 `<本机路径>`，
     断言抛 `BoardCodeRejected`，且 `failed_rows == 332`。
     **这是本轮最重要的新判据**——"不允许兜底"必须有一条会红的测试钉住。
  c) **`input_bytes` 路径**：给定字节数时按字节截断（非图像载荷必需）；
     留空时沿用 JPEG EOI 截断。
  d) 若留证目录不可见（换机器），这些用例要**显式 skip 并打印原因**，不许静默通过。
- ⚠️ 留证在 `<本机路径>`（Windows D 盘挂载），**若不存在就 skip**，不要把绝对路径写死成硬依赖。

**2. `clients/python/resources/` 的清单与说明**
- `SOURCES.json`：现在多了几个**客户端已不再使用**的条目。逐个标明每项现在**还有谁在用**
  （例如 `libc_ldpc.so` 仍被 `c_ldpc.py` 用，而 `c_ldpc.py` 被 4 个 `tools/*.py` import；
  `R5_6_LDPC_hard_decoder.exe` 与三个 MinGW DLL 已经没有客户端调用点了）。
  **只加标注与结论，不要删文件、不要删条目、不要改任何二进制的哈希值。**
- `resources/readme.txt`：同步说明"客户端运行时不再需要这些"，但离线工具仍在用。

**3. `clients/python/gui_app.spec`**
- 已不再需要打包 `R5_6_LDPC_hard_decoder.exe` 与三个 MinGW DLL（外部译码后端已删除）。
  **但先别急着删**：确认 `gui_app.py` 里确实没有任何地方再引用它们（另一位子 Agent 正在改它，
  你可以读、不要写）。**若无法确认，就保留并在报告里写明为何保留。**
- `dvb_s2_r5_6.pchk` 与 `permutation64800` **必须保留**——新的校验路径要用。

**4. `clients/python/README.md`**
- 把「三个后端怎么选」整节**删掉**，改写成新架构：
  **板端做 LDPC，PC 只做校验与载荷提取**；校验不过就是失败，没有兜底。
- 补：**载荷字节数**参数（非图像载荷必需）、**媒体类型**（图像/音频/视频/文本/二进制）的处理差异。
- 补：**打包 exe 的方法**（PyInstaller，Windows 侧执行）。
- ⚠️ **按实测写，不要照抄源码注释**。能跑的命令先跑一遍再写进去。

【验收判据 —— 逐条给实际输出】
- `bash tools/test_client.sh` PASS，并报告**实际收集到的用例数**；同步更新脚本里的下限常量并在注释里写明这个数怎么来的。
- 新增的「未纠对必须失败」用例**注入一次必失败**时会红（自证有牙齿），把变红输出记进报告后恢复。
- `bash tools/check_repo_hygiene.sh` PASS。
- 报告里逐条写：做了什么、**没做什么**、哪几条是"核实后确认可以删但本轮没删"、以及理由。

【看板】tools/agent_view.sh，`--agent client-tests-docs`：开始前 update、完成时 done。不要手工编辑 view.md。

【产出】改：`clients/python/tests/test_client_core.py`、`tools/test_client.sh`、`clients/python/resources/SOURCES.json`、
`clients/python/resources/readme.txt`、`clients/python/gui_app.spec`、`clients/python/README.md`；
报告 `logs/client/tests-docs-report.md`。

【硬性禁止】
- **不做任何 Git 写操作**；不要跑 tools/verify_repo_binding.sh（子 Agent 沙箱里跑不了）。
- **不改 `clients/python/ldpc_pipeline.py`、`gui_app.py`、`first.py`、`native_ldpc.py`**。
- **不删任何文件**（删不删由 main 决定：`c_ldpc.py` 还有 4 个 tools 在 import）。
- **不改 `resources/` 下任何二进制的字节**。
- 不碰 `hw/`、`tools/`（除 `tools/test_client.sh` 外不做改动）。
- 不许静默跳过任何用例。

【边界】你只交付「测试钉住新架构、清单与文档与新架构一致」。**不代表** exe 已重打、也不代表板端已验证。