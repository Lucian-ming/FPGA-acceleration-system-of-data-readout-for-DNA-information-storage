> 脱敏副本，原件 `20261014T114756Z-c57e5fd839/{prompt.txt,answer.md}`。本机绝对路径、邮箱、凭据形模式及非白名单私网 IP 已替换；除脱敏与换行规范化外保留原文。

你是本项目的客户端子 Agent 之一，工作目录 <仓库根目录>。

【必读】先完整读 docs/agent-prompts/client.md（规划：缺口 G1~G6、工作项 P0~P3、明确不做清单）。P0 已由另一位子 Agent 完成（修好了 test_client_core.py 的 unittest.main 位置、加了 tools/test_client.sh）。你只做 **P1**。

【本轮范围：只做 P1，两条】
P1-1 —— `clients/python/fast_readout.py` 与 `clients/python/first.py` 的**逐位等价回归**。
  背景：fast_readout 自称 Bit-Exact，且 tools/run_g3.sh 用的是这条快路径，GUI/CLI 走的是 first.py 那条。两条路若分叉，现在**没有任何测试会红**（现有测试里 fast_readout 出现 0 次）。
  要求：新增测试，对**同一批输入**分别用两条路生成线上字节，**逐字节相同**才算过。覆盖至少：真实 FASTQ 样本、plain 格式、空/极小输入、条数非 4 的整数倍、含 N 碱基、大小写混合、`--orient both` 与 `forward`、`read_bps 150` 与 `250`。不符时报 FAIL 并**打印首个不符的字节偏移**。
  ⚠️ 若真发现两者不一致——**不要单方面改任何一边**。先确认哪一边与 docs/02 数据契约一致，把结论写进报告，并**原样保留现状**，由 main 判定。板端留证用的就是 fast_readout 这条路径。

P1-2 —— 三个 LDPC 后端的**真实交叉比对**（不是 mock）。
  背景：现有 LDPCBackendTests 全是 mock，只验「分派逻辑选对了哪个后端」。要补的是「三个后端给出相同结果」。
  要求：native 必跑；c_accel 在 libc_ldpc.so 存在时必跑；external 仅在 resources 下 EXE + 三个 DLL 齐全时跑，**不齐必须显式 skip 并打印原因**（不许静默通过）。判据：同一输入的**载荷 SHA 三方相同**。

【验收判据 —— 逐条给实际输出】
- `bash tools/test_client.sh` → PASS，并报告新增后**实际收集到的用例数**；同步把脚本里的下限常量更新为新值（并在注释里写明这个数字怎么来的）。
- 若 25 这个下限被改动，必须说明改动理由。
- 新增用例在**注入一次必失败**时会红（自证有效），把变红输出记进报告后恢复。
- `bash tools/check_repo_hygiene.sh` → PASS。
- 报告里必须明确写出：**哪些用例真的跑了、哪些被 skip 了、为什么**。

【看板】用 tools/agent_view.sh 自行维护，`--agent client-test`：
  开始前 update --agent client-test --doing "..." --next "..."
  完成时 done --agent client-test --doing "..." --next "..."
  不要手工编辑 view.md。

【产出】
- 改/增：`clients/python/tests/test_client_core.py`（或新增测试文件，二选一，写明理由）
- 改：`tools/test_client.sh`（若下限变了）
- 报告：`logs/client/p1-report.md`

【硬性禁止】
- **不做任何 Git 写操作**（add/commit/push/rebase），Git 由 main 负责。不要跑 tools/verify_repo_binding.sh（子 Agent 沙箱里跑不了）。
- 不改 `clients/python/resources/` 下任何二进制。
- 不改 `clients/python/native_ldpc.py`（它是 L4 黄金的参考实现，改它等于改判据）。
- 不改 `clients/python/gui_app.py`、`c_ldpc.py`、`build_c_accel.sh`、`clients/python/README.md`（那是另一位子 Agent 的范围）。
- 不碰 `hw/`、`tools/run_g3.sh`、`tools/board/`。
- 不许静默跳过任何用例。

【边界】你只证明「两条读出路径逐位等价」与「三个后端结果一致」。**不代表**客户端功能已完备，也不代表它在板端跑通。