> 脱敏副本，原件 `20261014T114834Z-2000d09787/{prompt.txt,answer.md}`。本机绝对路径、邮箱、凭据形模式及非白名单私网 IP 已替换；除脱敏与换行规范化外保留原文。

你是本项目的客户端子 Agent 之一，工作目录 <仓库根目录>。用户的目标是：**把上位机客户端做完备修改，并打包成 Windows exe**。你是这份交付里负责「资源/后端/文档/GUI」的那一半，另一位子 Agent 在做 P1（测试），**不要碰测试文件与 tools/**。

【必读】先完整读 docs/agent-prompts/client.md（规划：缺口 G1~G6、工作项 P0~P3、明确不做清单）。

【本轮范围：P2 + P3】
P2-1 —— `clients/python/resources/` 的**同源清单与载入前校验**。
  现状：libc_ldpc.so（Linux 预编译）与 R5_6_LDPC_hard_decoder.exe + 三个 MinGW DLL 都入库了，但仓库对**制品包**有严格 SHA/manifest 门禁，对客户端这两份二进制**没有**：没有任何机制证明 libc_ldpc.so 出自当前的 c_ldpc_accel.c。
  要求：新增 `clients/python/resources/SOURCES.json`（逐项记：文件名、SHA256、上游源文件、构建命令、平台）与可选的 SHA256SUMS；`c_ldpc.py` 在载入动态库**之前**校验哈希，不符就**报错而不是继续**。`build_c_accel.sh` 重编后刷新清单。
  ⚠️ **不要修改或删除 resources 下任何既有的二进制文件**——只加清单与校验。先把每个文件的现有 SHA256 原样记录下来（它们就是现状基线）。

P2-2 —— Windows 侧 C 加速**缺失**这件事必须**显式**，不许静默降级。
  事实：`c_ldpc.py` 的候选名里有 `c_ldpc.dll`，但 resources 里**没有** Windows 版 C 加速库 ⇒ Windows 上 auto 会静默退到纯 Python（慢一个量级），用户看不出原因。
  要求：二选一——(a) 在 `c_ldpc.py` 里对「Windows 下 C 加速不可用」给出**可见警告**（走 logging/warning，GUI 与 CLI 都能看到），并在返回的 backend 名字里体现；或 (b) 给出可复现的 `c_ldpc.dll` 构建方法并在 `build_c_accel.sh` 里支持。**选 (a) 更稳**（交叉编译 MinGW DLL 在本环境未验证）。无论选哪个，都要在报告里说明选了什么、为什么。

P3-1 —— `clients/python/README.md` **使用说明**（现在没有面向使用者的文档，docs/02/04 是协议契约不是说明书）。
  必须覆盖：GUI 与 CLI 怎么起、依赖怎么装、三个后端（native/c_accel/external）分别是什么与怎么选、常见失败长什么样（连不上板子、CONFIG 被拒码、结果超时、LDPC 不收敛）、数据集与阈值口径（read_bps/score_min）、以及**打包 exe 的方法**。
  ⚠️ 写之前先实际跑一遍 CLI 的 `--dry-run` 与 GUI 的启动路径，**按实测写，不要照抄源码注释**。

P3-2 —— GUI 的实际短板：**先列后改**。
  先在报告里写清「你实测/读码确认**真缺**的是哪几条」，再动手。已知候选（**要逐条核实，不要全盘接受**）：多轮/批量数据集跑、结果历史与对比、失败样本归档、参数预设存读。
  ⚠️ 不要重写 GUI 框架、不换 tkinter。**改动必须有可复现的操作步骤与判据**；不确定的宁可不动，写进报告留给 main。

【exe 打包】只做你这一半：把 `clients/python/gui_app.spec` 审一遍并修正明显问题。
  ⚠️ **已知问题**：datas 里打包了 `resources/libc_ldpc.so`（Linux 库），而 Windows exe 需要的是 `c_ldpc.dll`。**实际打包由 main 在 Windows 侧执行，你不要跑 pyinstaller**（你在 Linux 沙箱里跑出来的是 Linux 二进制，没用）。你只负责改 spec 与写清打包步骤。

【验收判据 —— 逐条给实际输出】
- `bash tools/check_repo_hygiene.sh` → PASS。
- `bash tools/test_client.sh` → PASS（若它因你改动而红，说明你破坏了 P1 的范围，立刻修）。
- `python3 -c "import c_ldpc"` 级别的导入与校验路径自测：**故意改坏清单里的一个哈希**，确认载入会**报错**（自证校验有效），然后恢复。
- 报告里逐条列出：做了什么、没做什么、哪几条是「核实后确认缺失」、哪几条是「核实后其实不缺」。

【看板】用 tools/agent_view.sh 自行维护，`--agent client-pkg`：
  开始前 update --agent client-pkg --doing "..." --next "..."
  完成时 done --agent client-pkg --doing "..." --next "..."
  不要手工编辑 view.md。

【产出】
- 增：`clients/python/resources/SOURCES.json`
- 改：`clients/python/c_ldpc.py`、`clients/python/build_c_accel.sh`、`clients/python/gui_app.spec`、`clients/python/README.md`（新建）
- 可能改：`clients/python/gui_app.py`（仅 P3-2 里你核实确实缺的项）
- 报告：`logs/client/p2p3-report.md`

【硬性禁止】
- **不做任何 Git 写操作**（add/commit/push/rebase），Git 由 main 负责。不要跑 tools/verify_repo_binding.sh（子 Agent 沙箱里跑不了）。
- **不改 `clients/python/resources/` 下的既有二进制文件**（只加清单）。
- 不改 `clients/python/native_ldpc.py`（L4 黄金的参考实现，改它等于改判据）。
- 不改 `clients/python/tests/`、`tools/`（那是另一位子 Agent 的范围）。
- 不碰 `hw/`、`tools/run_g3.sh`、`tools/board/`。
- 不跑 pyinstaller（打包由 main 在 Windows 做）。

【边界】你只交付「客户端资源可核验、后端可用性显式、有使用文档、GUI 已知短板有据可依」。**不代表**客户端已上板验证，也不代表 exe 已产出。