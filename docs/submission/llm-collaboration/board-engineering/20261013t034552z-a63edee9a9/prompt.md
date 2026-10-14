> 脱敏副本，原件 `20261013T034552Z-a63edee9a9/{prompt.txt,answer.md}`。本机绝对路径、邮箱、凭据形模式及非白名单私网 IP 已替换；除脱敏与换行规范化外保留原文。

你是 verify-system（看板名 verify-system）。任务：**给解码链加一条"按显式 input_bytes 截断"的通路**，让非 JPEG 载荷（WAV/MP4/文本/CSV/二进制）也能走板端 G3 判据。

**【必须先读】不要运行 `tools/verify_repo_binding.sh`**（含 `--remote`/`--require-synced`）。那是 main 的门禁、main 已代跑留证；codex 沙箱把 git 目录（本仓库 gitdir 是 `.git-data`）挂成只读，脚本写 `FETCH_HEAD` 必报 `Read-only file system`——**沙箱特性，不是仓库故障**。`AGENTS.md` 的「子 Agent 的承载通道与模型」一节有同样说明。

【看板】workspace-write，先 `tools/agent_view.sh start --agent verify-system --doing "..." --why "..." --next "..."`，收工 `done`。
【禁止】Git 写操作；不派生 Agent；**不触板**（板卡归 main，正在跑任务）；不改 `hw/boards`、`hw/scripts/bd.tcl|build.tcl`、`sw/app`（归 board-migrate）；不改 docs 根 01～09（归 main）。

============ 问题（main 已定位）============
`clients/python/native_ldpc.py` 的 `bits_to_jpeg_bytes(bits)` 用 **`data.rfind(b"\xff\xd9")`（JPEG EOI）截断**。这对 JPEG 载荷是对的（v1 全是 JPEG，所以能过），但对**非 JPEG** 载荷：
- 载荷里恰好含 `FF D9` → 截错；
- 不含 → 返回**带尾部零填充的全长** → SHA 对不上。
**两种情况都不可能等于真实文件长度。**

新测试集 `<本机路径>`（WSL `<本机路径>`）的 21 个资产里 **9 个是非 JPEG**（4 WAV、2 MP4、utf8_text.txt、numeric_signal.csv、random_binary.bin）。该包 README 明确要求：**"只应去掉外部 metadata 指定的尾部零填充；不能对 WAV/MP4/二进制套用 JPEG 的 FF D9 截断规则"**。每个 `encoded/<asset>/block000/encoding.json` 里有 `input_bytes`（真实文件长度）与 `input_sha256`。

============ 你要做的 ============
1. **先复现问题**（这是判据要有鉴别力的前提）：用 v2 的一个非 JPEG 资产，构造出"板端会回传的那 8100 B 对应的 54000 bit"，用**现有的** `bits_to_jpeg_bytes` 走一遍，证明它**得不到** `input_bytes` 长度的正确字节（把实际长度与期望长度都打出来）。可以写一个独立小脚本放在 `tools/` 下（记得登记进 `tools/README.md`），**不要改生产脚本只为做这个演示**。
2. **加显式截断通路**（最小改动）：
   - 给 `clients/python/native_ldpc.py` 的相关函数（或新增一个）加 **`input_bytes` 参数**：给定 N 时**取前 N 字节**，**不做** `FF D9` 查找；`input_bytes` 为 None 时**保持现有 JPEG 行为不变**（不能破坏 v1/R0.83 的既有判据）。
   - 给 `tools/ldpc_decode.py` 加对应的命令行参数（例如 `--input-bytes N`），并在 `--image` 输出之外支持写出**任意载荷**（现在是 `--image`，语义是 JPEG；请**新增**一个不叫 image 的出口或让 `--image` 在给了 input_bytes 时也按裸字节写，但要说清你选了哪种、为什么）。
   - 给 `tools/run_g3.sh` 加透传参数（例如 `--input-bytes N`），使 main 能在板测时传入。
   - **校验**：N 必须为正且 ≤ 6750（当前 54000 bit / 8 的信息位上限），越界要明确报错而不是静默截断。
3. **回归**：跑 `python3 -m unittest discover -s tests/host -p 'test_g3_*.py'`、`bash tests/host/run_host_tests.sh --worktree`、`bash tools/check_ip_packaging.sh`、`bash tools/check_repo_hygiene.sh`，实际命令与退出码写进报告。**不得放宽任何现有门禁**；v1/R0.83 的既有路径行为必须不变（请给出证据，例如同一条 R0.83 输入在改动前后得到同一输出）。
4. **反向验证**：证明新通路**真的会红/真的有用**——例如把 `input_bytes` 故意设成错值，应当得到不同 SHA；设成正确值时应当与 `input_sha256` 相符（用 v2 的 `blind_recover.py` 或该包自带的软件恢复结果作为对照，**注意那是软件对照，不是板端结论**）。

【纪律】只写你核证过的；引用代码位置写**函数名/符号名**不写行号；**不触板**，因此**不得声称任何板端结论**；不要把外部包（`<本机路径>`）的东西说成已入库。

【报告】① 复现问题的实际输出（长度对比）；② 改动清单（文件+函数名+前后行为）；③ 回归命令与退出码；④ 反向验证证据；⑤ 给 main 的板测参数样例（怎么传 input_bytes）；⑥ PASS/FAIL/未测。收工 `tools/agent_view.sh done --agent verify-system`。