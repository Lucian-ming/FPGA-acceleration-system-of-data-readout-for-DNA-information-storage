> 脱敏副本，原件 `20261014T115445Z-898fa23956/{prompt.txt,answer.md}`。本机绝对路径、邮箱、凭据形模式及非白名单私网 IP 已替换；除脱敏与换行规范化外保留原文。

你是本项目的子 Agent，工作目录 <仓库根目录>。你的任务是**归因一个还没解释清楚的 ~70 ms**，并给出一份可以直接上板跑的复现配方。

【必读】AGENTS.md（规范）；docs/benchmarks/ldpc-onchip-l7-board.md §3.1；docs/benchmarks/bkb220-p16-full-flow-compression.md §2C。

【要回答的问题】
片上 LDPC 的实测净代价是 **≈ +120 ms/任务**（与数据量基本无关：默认档 +123 ms、全量档 +118 ms）。
其中**只有 ≈50 ms 能归因**：
  - PS 状态机 LDPC_PREP + LDPC_RUN + LDPC_READBACK = **17 ms**（板端自报 6+5+6）
  - 其中置换（装载解交织 2 ms + 读回交织 1 ms）= **3 ms**（板端串口打印）
  - PL 译码（收敛 4~5 轮）≈ **29~35 ms**（仿真周期 2.9~3.5 M @100 MHz）
**剩下 ≈70 ms 没有归因。** 当前的**假设**是：主循环的 `PIPE_RUN_SLEEP_US`（出厂 200 µs）轮询量化——
LDPC 步骤多出约 155~1,000 次回调，每次最多 200 µs。**这是假设，不是结论，你要证实或否证它。**

【做法】
1. 先用**已有留证**做定量分析，不要一上来就改代码：
   - 留证目录 `<本机路径>` 下这几轮可直接用：
     - `20261014T114158Z` K=2 无 LDPC 默认档（板端 602 ms，1016 callbacks）
     - `20261014T113108Z` K=2 + LDPC 默认档（725 ms，1171 callbacks）
     - `20261014T114053Z` K=2 无 LDPC 全量档（6,141 ms，27263 callbacks）
     - `20261014T113737Z` K=2 + LDPC 全量档（6,259 ms，27386 callbacks）
   - 每个目录里有 `uart.log`（含 `[PIPE-BREAKDOWN]` 与 `[PIPE] total … steps in N callbacks`）与 `first_run1.log`。
   - 算清楚：**回调次数差**能否解释 **板端毫秒差**？给出算式与数字。
   - ⚠️ **一个已知陷阱**：无 LDPC 的包在 `DONE_STAGE3 → SEND_RESULT` 这一步由 TCP 回调直接接管，profiler **没有闭合该区间**，所以它的 `[in-state]` **少记了这一段**。**跨这两个包不能减 `[in-state]`/`[waiting]`**，只能比 `[PIPE] total` 与 `t_result`。别踩这条。
2. 读 `sw/app/main.c`、`sw/app/echo.c`、`sw/app/ldpc_onchip.c`，说明 `PIPE_RUN_SLEEP_US` 到底在什么条件下休眠、LDPC 的轮询循环是不是每次都走休眠。
3. 若分析支持该假设，给出**一个最小、可逆**的验证方案：应改哪个文件/哪个宏、改成什么、预期看到什么数字变化。**可以直接把变体包构建出来**（用 `tools/build_sw_variant.sh --ref <某包> --out <新包> --define <宏=值>`，或必要时改 `ldpc_onchip.c` 后用 `--sync-src`）。
   ⚠️ **板子只能 main 跑**（你在沙箱里跑不了 Windows 二进制、也不该开 hw_server）。你的交付是「**main 可以直接烧的包 + 一条命令 + 预期判据**」。

【验收判据】
- 报告里给出：回调差 → 毫秒差 的算式与结论，**明确写「假设成立 / 不成立 / 证据不足」**三者之一。
- 若给出变体包，报告里写清包路径、**与参考包的 bit SHA 应逐字节相同**（本变体不应改硬件）、ELF SHA 不同、以及 `run_g3.sh` 的完整命令行。
- 任何数字都要标来源（哪个留证文件、哪一行）；**不要写没有出处的数**。

【看板】tools/agent_view.sh，`--agent ldpc-poll`：开始前 update、完成时 done。不要手工编辑 view.md。

【产出】报告 `logs/client/../ldpc-poll-report.md` → 实际路径用 `logs/ldpc-poll/report.md`。变体包（若构建）放 `hw/build/`。

【硬性禁止】
- **不做任何 Git 写操作**；不要跑 tools/verify_repo_binding.sh（子 Agent 沙箱里跑不了）。
- **不碰板卡**：不开 hw_server、不烧录、不跑 run_g3.sh、不占用 <本机路径>
- **不改 `hw/ip/**`**（本任务不该动硬件）；不改 `clients/python/native_ldpc.py`。
- 不许把「假设」写成「结论」。

【边界】你只做归因与配方；**实测由 main 执行**，在你报告之前那 +70 ms 仍然是未归因的。