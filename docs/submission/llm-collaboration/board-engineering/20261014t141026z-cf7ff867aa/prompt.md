> 脱敏副本，原件 `20261014T141026Z-cf7ff867aa/{prompt.txt,answer.md}`。本机绝对路径、邮箱、凭据形模式及非白名单私网 IP 已替换；除脱敏与换行规范化外保留原文。

你是本项目的**板端验收子 Agent**，工作目录 <仓库根目录>。
任务：把一份**新硬件包**烧到 BKB220 板子上并跑 G3 验收，同时做一次同小时 A/B。

【这块板子现在归你独占】开始前先确认没有别人在占：
```bash
pgrep -af "run_g3|g3_soak" | grep -v grep    # 应无输出
ls <本机路径>                              # 应有 ttyUSB1/2/3
```
**同一时刻只允许你一个 agent 用板子。** 若发现别人在跑，停下并报告，不要抢。

【被测包（新硬件 = Stage1 优化版）】
`hw/build/bkb220-p16-k2-ldpc-prefillopt-sw-20261014T135534Z-board-migrate/`
（已过 `--strict-artifacts --plan-only` 门禁；包内 bit SHA `8d17d17e…`）

【参考包（同小时对照，K=2 无 Stage1 优化）】
`hw/build/bkb220-p16-k2-ldpc-sw-20261014T104331Z-board-migrate/`
（就是"加了解交织、但 Stage1 未优化"那一版）

【怎么跑（main 今天实测可用的完整命令，照抄改包名即可）】
```bash
# 1) 确认 hw_server 在 3132（没有就起一个）
pgrep -af "hw_server.*3132" || nohup <本机路径> -sTCP:127.0.0.1:3132 ><本机路径> 2>&1 &

# 2) 跑判据轮
tools/run_g3.sh --artifact-dir <包> \
  --xsdb <本机路径> --hw-server TCP:127.0.0.1:3132 \
  --device xc7z020 --strict-artifacts --uart-port <本机路径> \
  --ip 192.168.1.10 --port 7 --win-root <本机路径> --skip-dump
```
⚠️ 这是 **WSL 本地路径**（Linux xsdb + WSL 串口 + hw_server），不走 Windows。
**如果你发现这条路在你这里跑不通**（权限、设备、socket 之类），**不要硬试、不要绕去 Windows**——
**立刻停下，把准确报错原文写进最终答复**，main 会接手。**这本身就是本次任务要回答的问题之一。**

【要产出什么】

**1. 新包的 G3 判据轮**（这是**唯一判据**）：
- 必须 **`######## G3 PASS ########`**，且载荷 SHA-256 **逐位等于**
  `fcd0cf90bd680e7bbdc203e3398119504da0897acac9e2117008b4efb6b1f2c3`。
- **贴出**：`summary.txt` 的判据行、`ldpc_run1.log` 全文、以及 `uart.log` 里这几行的原文：
  `[LDPC] loading … deinterleaved in … ms`、`[LDPC] converged=… iterations=…`、
  `[PIPE] total … ms`、`[PIPE-BREAKDOWN]` 表。
- **贴出留证目录路径**。

**2. 同小时 A/B**：紧接着（同一小时内、同一板、同参数）把**参考包**也跑一遍，同样贴出
   `Result:` 行的 `t_result`、`[PIPE] total`、判据 SHA。
- ⚠️ 纪律：`t_result` 有 ±7.5% 的日内漂移，**跨小时的数字不得相减**；这两轮必须是背靠背。
- 给出两轮的 `t_result` 与 `[PIPE] total` 对照表，**并明确说明这是单次测量、差值在什么量级**。

**3. 判据纪律（重要）**
- **不许**把"界面成功""TCP 返回""四级取证全绿"当成 G3 通过；**只有那条 SHA 算数**。
- 如果 SHA 不符或 G3 FAIL，**不要重试掩盖**，原样保留留证并报告。
- 若 `converged=0`（板上没纠对），**那是失败**，如实报。

【看板】tools/agent_view.sh，`--agent board-verify-stage1`：开始前 update、完成时 done。不要手工编辑 view.md。

【产出】报告 `logs/verify/board-verify-stage1.md`（含上面要求贴的全部原文与路径）。

【硬性禁止】
- **不做任何 Git 写操作**；不要跑 tools/verify_repo_binding.sh。
- **不改任何源码/制品**（`hw/`、`sw/`、`clients/` 一个字节都不许动）；只读 + 烧录 + 跑脚本。
- **不要重跑 Vivado 综合/实现**（太慢，且不在本次范围）。
- 不要碰 `clients/python/`（另有 agent 在做）。
- **不许同时跑两个 run_g3**；一轮跑完再跑下一轮。

【边界】你只交付"板端判据轮的实际结果 + 同小时 A/B 的实际数字"。
**通过与否由 main 裁决**，你只提供原始证据。