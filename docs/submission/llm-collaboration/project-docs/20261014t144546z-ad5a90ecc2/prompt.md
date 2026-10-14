> 脱敏副本，原件 `20261014T144546Z-ad5a90ecc2/{prompt.txt,answer.md}`。本机绝对路径、邮箱、凭据形模式及非白名单私网 IP 已替换；除脱敏与换行规范化外保留原文。

你是本项目的子 Agent，工作目录 <仓库根目录>。
任务：**把「从源码到可验收制品包」这条链收成一个可复现的入口**（现在是半手工的）。

【为什么这是高优先】
竞赛评分里「**文档与可复现**」占 15，且硬要求写明 Vivado 版本是 2026.1/2025.2，
本项目用 **2022.2**，**须说明并保证可复现**。而今天这条链**又踩了两次**：
1. `sw/scripts/create_vitis.tcl` 在新 workspace 下必须**先 `platform generate` 物化 BSP 头**
   再设 `TCP_WND` 重新生成（已有补步，但要知道的人才知道）；
2. XSCT 的 **`app create` 报 `Socket create error. Operation not permitted`**（本机限制），
   只能改用**同一安装树的 ARM GCC** 直接编译并链接新 BSP。
⇒ 这两步现在**只在人的脑子里**，换个环境或换个人就复现不出来。

【必读】
- `docs/07-board-build-and-acceptance.md` §3（工具链与同源制品、§3a 分工）
- `tools/run_vivado_build.sh`（整机构建入口，**已有**）
- `sw/scripts/create_vitis.tcl`（软件包生成，**有待收口**）
- `tools/write_source_manifest.py`（制品包清单工具，**已有**）
- 今天最新的完整包：`hw/build/bkb220-p16-k2-ldpc-prefillopt-sw-20261014T135534Z-board-migrate/`
  （它的 `manifest.json` / `SHA256SUMS` / `reports/source_manifest.json` 就是标准格式）
- 与它对应的硬件包：`hw/build/bkb220-p16-k2-ldpc-prefillopt-20261014T124533Z-board-migrate/`

【本轮要交付什么】

1. **把这条链写成一条可执行入口**（新脚本，放 `tools/`）：
   从**硬件包目录**（含 XSA）→ 生成完整软件包（FSBL/BSP/ELF/BOOT/ps1_init/manifest/SHA256SUMS/source_manifest）
   → 自动跑 `tools/run_g3.sh --plan-only` 做制品门禁自检。
   - 脚本要**自己处理**上面两个已知坑（BSP 头物化顺序、`app create` 失败时回落 ARM GCC 直编），
     并把回落**显式打印出来**（不许静默）。
   - 参数：`--hw-package <硬件包>`、`--out <新包目录>`、可选 `--label`。
   - **失败要非零退出**，不要 exit 0。

2. **写一份可复现说明**：`docs/submission/reproduce-artifacts.md`（**纯英文小写路径**）
   - 从零到「一个可被 `--strict-artifacts` 接受、能上板跑 G3 的完整包」的**完整命令序列**。
   - 明确写清 **Vivado/Vitis 2022.2**、为什么用它（竞赛允许，但需说明并保证可复现）。
   - 写清每一步的**成功判据**（不是"命令没报错"，而是"产物存在且 SHA 自检通过"）。
   - 写清**已知偏差**：`app create` 的 socket 错误及其回落路径。
   - **按实测写**：你实际跑通一遍再写，不要照抄源码注释。

3. **实际验证**：用你的新脚本，**从今天那个硬件包重建一份软件包**，证明它是可用的：
   - 产物齐全；`sha256sum -c SHA256SUMS` 全 OK；
   - `run_g3.sh --plan-only --strict-artifacts` **通过**（**只做只读门禁校验，不连板、不烧录**）；
   - 与今天那份手工包对照：`manifest.json` 的关键字段、包内 bit 的 SHA 应一致。
   ⚠️ 重建要放**新目录**，**不要覆盖** `hw/build/bkb220-p16-k2-ldpc-prefillopt-sw-20261014T135534Z-board-migrate/`。

【验收判据 —— 逐条给实际输出】
- 新脚本路径 + `--help` 输出 + 一次**真实完整运行**的日志。
- 重建包的门禁 `--plan-only` 输出（应通过）、`sha256sum -c` 计数。
- 与手工包的对照结果。
- **证明脚本对已知坑真的有效**：至少演示"`app create` 失败会回落并显式打印"这条路径
  （真让它失败一次，或用一个可控的方式触发该分支），把输出贴出来。
- 说明文档里每条命令**你自己跑过**（跑过的标 ✔，没跑过的标"未实测"）。

【看板】tools/agent_view.sh，`--agent vitis-chain`：开始前 update、完成时 done。不要手工编辑 view.md。

【产出】`tools/` 下新脚本 + `docs/submission/reproduce-artifacts.md` + 报告 `logs/submission/vitis-chain.md`
+ 重建出的新包（放 `hw/build/` 新目录）。

【硬性禁止】
- **不做任何 Git 写操作**；不要跑 tools/verify_repo_binding.sh。
- **不改 `sw/app/**`**（权威源）、**不改 `hw/ip/**`**、**不改 `hw/scripts/bd.tcl`**、
  **不改已有制品包**（只读 + 新建）。
- **不碰板卡**（不开 hw_server、不烧录、不跑真 G3；只允许 `--plan-only`）。
- 不碰 `clients/python/`（别的 agent 在改）。
- ⛔ **不要用 `pkill`/`killall` 按名字杀进程**；要杀用 `ps` 查 PID 再 kill。
- 不许假装跑过。

【边界】你交付"一条能用的复现入口 + 一份实测的复现说明"。**不代表**它在别的机器上一定能跑（要注明环境依赖）。