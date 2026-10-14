> 脱敏副本，原件 `20261012T115059Z-93cae00e2a/{prompt.txt,answer.md}`。本机绝对路径、邮箱、凭据形模式及非白名单私网 IP 已替换；除脱敏与换行规范化外保留原文。

你是 verify-system（看板名 verify-system）。这是**第二阶段任务**。你第一阶段已交付一份很扎实的只读审计（main 已存档于 logs/agents/verify-system-20261012/audit-report.md），本阶段把其中「必须改代码」的项落地。

先读 docs/agent-prompts/verify-system.md（角色全文）、AGENTS.md、CLAUDE.md、docs/06-verification-plan.md、docs/07-board-build-and-acceptance.md（**特别是新增的 §3a「触板通道」**）、docs/03-status.md（**§1a/§1b**）、你上一轮的审计报告。

【看板】workspace-write，自己 `tools/agent_view.sh start --agent verify-system --doing ... --why ... --next ...`，阶段 update，受阻 block，收工 done。
【禁止】任何 Git 写操作；不建分支/worktree；不派生子 Agent；**不触板**（JTAG/串口/下载/reset/DDR dump 全归 main）；不改被测生产 RTL（hw/ip/**）与 sw/app、hw/boards、hw/scripts/bd.tcl|build.tcl（归 board-migrate）；不改 docs 根目录 01～09（归 main）。
【更正】不要运行 `tools/verify_repo_binding.sh`（main 的门禁，沙箱 git 目录只读，跑了必失败）。

============ main 已实测的现场（直接采信）============
- 新板 **xc7z020**（IDCODE `0x23727093`），板载 FT4232HL；JTAG 链 `Xilinx HW-Z1-ZCU104 FT4232H 15051A`。
- **触板只走 WSL**：`usbipd attach --wsl --busid 4-2` → `<本机路径>`=JTAG、`<本机路径>`=三串口 → Linux `<本机路径> -sTCP:127.0.0.1:3132` → `<本机路径>` 连 `TCP:127.0.0.1:3132`。
- **Windows 原生 hw_server 是已知蓝屏路径（两次 BugCheck 0x139，进程 hw_server.exe，栈 ftdibus+0xf4d4），用户已暂停**。所以 `run_g3.sh` 默认的 `XSDB_VALUE`、`g3_xsdb.ps1`、`g3_uart_cap.ps1` 这条 **Windows 侧**路线现在不可用；下载/调试改走 WSL 2022.2。
- main 已新建 `tools/board/bkb220_f3_bringup.sh`（F3 最小启动判据入口，补你上轮指出的缺口）——**该文件已由 main 写到你的独占路径下，现正式移交给你**：请审阅它、按需修改或扩展，不要另起一个重复入口。
- board-migrate 正在并行生成候选 ps7_init（4 个 UART MIO 变体）+ 校验 Vivado 2022.2 catalog，产物在 `hw/build/bkb220-ps7-probe/<run-id>/`。**不要碰那个目录。**

============ 本阶段任务 ============
按你上轮审计的 C 节「需要改代码」清单，做**最小必要适配**，重点是让工具在新板 + WSL 通道下**不会静默走旧值**。优先做这几项（其余可列为后续）：

1. **`tools/run_g3.sh` 的新板路径收紧**（最高优先级）：
   - 让「BKB220/新板验收」明确**拒绝 legacy 默认制品回退**（现在 `ARTIFACT_DIR` 默认 `hw/build/export` 且会自动 `--allow-legacy`）。给出一个显式开关或按 `--device xc7z020` 自动进入严格模式，并保证不给 `--artifact-dir` 时**明确失败**而不是静默选旧包。
   - 提供 **WSL 侧 XSDB/hw_server 入口**（因为 Windows 路线被暂停）：至少让 `--xsdb` 能指向 Linux xsdb 并可传 `TCP:127.0.0.1:3132`。注意 `run_g3.sh` 现在假定 xsdb 是 Windows 路径且经 `cmd.exe`/PowerShell 桥接，Linux 路径需要区分处理——请做成「显式传 Linux xsdb 时走本地直接调用」，不要让旧桥接逻辑把它当 Windows 路径。
   - 运行摘要记录 **FASTQ/水印输入 SHA**，不能只记图片 SHA。
   - **验收运行时串口采集失败不能记成可接受 PASS**：现在 UART 失败可 `SKIP` 而整体 G3 仍 PASS。请让「验收模式」下串口无输出/打不开成为明确失败（保留一个仅供排错用的放宽开关，且必须在摘要里标注）。
2. **`tools/board/g3_wait_ready.py` 与网络探针**：要求显式 `--ip`（不要静默落到 `192.168.1.10`），并**校验 CAPS 的全部几何字段**（version/read_bps/num_lc/stride/max_symbols/max_reads/features bit0），字段不符必须失败。请先读 `docs/04-interfaces.md` 核对字段与长度。同时指出：CAPS **不含 P_WAYS/PIPE_TREE**，所以 TCP 层无法区分板上跑的是 P4 还是 P16——在文档/输出里明确这个边界。
3. **`tools/board/read_pipe_counters.tcl`**：现在写死旧 B27 ELF 的绝对地址（`0x0021a2a4` 等）。改成从**本轮选中的 ELF**解析符号地址（可用 `arm-none-eabi-nm`，工具在 `<本机路径>`），并保留一个显式传地址的排错出口。地址解析不到时必须明确失败，不能回退旧地址。
4. **负用例**：新增/加强「新板验收模式下，缺 `--artifact-dir` 时必须拒绝 legacy 默认包」的 host 用例，放进现有 `tests/host` 的 G3 用例集。**你上轮指出的 `tools/board/g3_uart_cap.ps1` 默认 COM6、`g3_xsdb.ps1` 组合等其它项**，能做就做，做不完如实列为未完成。
5. **审阅并接手 `tools/board/bkb220_f3_bringup.sh`**：跑 `bash -n` 语法检查；确认它的判据边界陈述正确；如发现会误导的判据（例如把 `ps7_post_config` 退出 0 当成 DDR PASS）请修正。**你不需要真的触板**——判据逻辑用 dry-run/静态方式验证即可，把「未在真板验证」如实写进报告。

【硬约束】
- **不许为了全绿放宽任何现有门禁**。你上轮已确认 47 项 G3 主机用例、打包门禁（main 复跑 exit 0）、卫生 11 项（main 复跑 exit 0）是通过的，改完必须**回归**：跑 `python3 -m unittest discover -s tests/host -p 'test_g3_*.py' -v`、`bash tests/host/run_host_tests.sh --worktree`、`bash tools/check_ip_packaging.sh`、`bash tools/check_repo_hygiene.sh`，把实际命令与退出码写进报告。新增的负用例要**真的会红**（用反向验证证明）。
- 改 `tools/`、`tests/`、`hw/sim/` 是你的独占路径；不要顺手改生产 RTL 或固件。若你判断某项必须改被测对象，写进报告的 block 项交 main。
- 仓库根目录不得留 `*.log/*.jou/*.str/*.pb`；新工具/入口必须登记进 `tools/README.md`（你独占的文档范围是工具索引中与 tools/ 相关的条目）。

【交付】报告给出：① 每项改动的文件+函数/符号名+前后行为差异；② 回归命令与退出码；③ 新增负用例的**反向验证证据**（改坏后确实变红）；④ 明确区分 PASS/FAIL/未测，特别是「未在真板验证」的部分；⑤ 与 board-migrate / main 的接口假设（例如新板 G3 需要 main 传哪些参数）。收工 `tools/agent_view.sh done --agent verify-system`。