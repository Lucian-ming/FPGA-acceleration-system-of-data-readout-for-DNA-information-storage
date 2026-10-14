> 脱敏副本，原件 `20261014T141348Z-d86906b208/{prompt.txt,answer.md}`。本机绝对路径、邮箱、凭据形模式及非白名单私网 IP 已替换；除脱敏与换行规范化外保留原文。

你是本项目的**板端验收子 Agent**，工作目录 <仓库根目录>。
任务：把一份**新硬件包**烧到 BKB220 板子上并跑 G3 验收，同时做一次同小时 A/B。
（上一位做这件事的 agent 因 USB 设备掉出 WSL 而中止，**main 已经把设备接回来了**，通道现在是好的。）

【开始前的环境确认】
```bash
ls <本机路径>                      # 应有 ttyUSB0..3
ps -eo pid,cmd | grep -F "3132" | grep -v grep   # 应能看到 hw_server 在 3132
pgrep -af "run_g3|g3_soak" | grep -v grep        # 应无输出（板子空闲）
```
- main 刚验证过：JTAG 能看到 `xc7z020` 与 `ARM Cortex-A9 MPCore #0 (Running)`；**网络现在不通是正常的**
  ——`run_g3.sh` 会先 reset 系统并下载 bit/ELF，应用起来后才配 ENET0。
- **若 `<本机路径>` 又不见了**（FT4232H 从 WSL 掉出去），先试恢复：
  ```bash
  <本机路径> /c "usbipd attach --wsl --busid 5-2"
  ```
  然后重新 `ls <本机路径>`。**若这条也失败**（例如报 vsock/socket 错误），
  **立刻停下并把准确报错原文写进最终答复**，不要硬试、不要绕去 Windows 烧录路径——
  main 会接手。**"子 Agent 能不能独立完成板端验收"本身就是本次要回答的问题**，失败也是有价值的答案。
- **⛔ 不要用 `pkill -f hw_server` 之类的模式杀进程**：命令行里含同样的字符串会**把你自己杀掉**
  （main 今天踩过两次，退出码 144）。要杀就用 `ps` 查出 PID 再 `kill <pid>`。

【被测包（新硬件 = Stage1 优化版）】
`hw/build/bkb220-p16-k2-ldpc-prefillopt-sw-20261014T135534Z-board-migrate/`
（已过 `--strict-artifacts --plan-only` 门禁；包内 bit SHA `8d17d17e…`）

【参考包（同小时对照，Stage1 未优化）】
`hw/build/bkb220-p16-k2-ldpc-sw-20261014T104331Z-board-migrate/`

【怎么跑（main 今天实测可用的命令，照抄改包名）】
```bash
tools/run_g3.sh --artifact-dir <包> \
  --xsdb <本机路径> --hw-server TCP:127.0.0.1:3132 \
  --device xc7z020 --strict-artifacts --uart-port <本机路径> \
  --ip 192.168.1.10 --port 7 --win-root <本机路径> --skip-dump
```
（留证会落到 `<本机路径><时间戳>/`。跑一轮约 1 分钟。）

【要产出什么】

**1. 新包的 G3 判据轮**（**唯一判据**）：
- 必须 `######## G3 PASS ########`，且载荷 SHA-256 **逐位等于**
  `fcd0cf90bd680e7bbdc203e3398119504da0897acac9e2117008b4efb6b1f2c3`。
- **贴原文**：`summary.txt` 的判据行；`ldpc_run1.log` 全文；`uart.log` 里
  `[LDPC] loading … deinterleaved in … ms`、`[LDPC] converged=… iterations=…`、
  `[PIPE] total … ms`、以及 `[PIPE-BREAKDOWN]` 表。给出留证目录路径。

**2. 同小时 A/B**：紧接着（同一小时内、同一板、同参数）跑**参考包**，同样贴出
   `Result:` 行的 `t_result`、`[PIPE] total`、判据 SHA。
- ⚠️ `t_result` 有 ±7.5% 日内漂移，**跨小时不得相减**，所以必须背靠背。
- 给出两轮的 `t_result` / `[PIPE] total` 对照表，并说明这是**单次测量**、差值在什么量级。

**3. 判据纪律（重要）**
- **不许**把"界面成功/TCP 返回/四级取证全绿"当成 G3 通过；**只有那条 SHA 算数**。
- SHA 不符或 G3 FAIL ⇒ **不要重试掩盖**，原样保留留证并如实报告。
- 若 `converged=0`（板上没纠对），**那是失败**，如实报。

【看板】tools/agent_view.sh，`--agent board-verify-stage1`：开始前 update、完成时 done。不要手工编辑 view.md。

【产出】报告 `logs/verify/board-verify-stage1.md`（含上面要求贴的全部原文与路径）。

【硬性禁止】
- **不做任何 Git 写操作**；不要跑 tools/verify_repo_binding.sh。
- **不改任何源码/制品**（`hw/`、`sw/`、`clients/` 一个字节都不许动）；只读 + 烧录 + 跑脚本。
- **不要重跑 Vivado 综合/实现**（太慢且不在范围内）。
- 不碰 `clients/python/`（另有 agent 在做）。
- **不许同时跑两个 run_g3**；一轮跑完再跑下一轮。

【边界】你只交付"板端判据轮的实际结果 + 同小时 A/B 的实际数字"。**通过与否由 main 裁决。**