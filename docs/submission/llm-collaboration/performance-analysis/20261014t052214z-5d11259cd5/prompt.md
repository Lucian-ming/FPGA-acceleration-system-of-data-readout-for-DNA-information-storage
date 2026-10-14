> 脱敏副本，原件 `20261014T052214Z-5d11259cd5/{prompt.txt,answer.md}`。本机绝对路径、邮箱、凭据形模式及非白名单私网 IP 已替换；除脱敏与换行规范化外保留原文。

任务（workspace-write，看板名 **ldpc-probe-rtl**）：写一个**可综合的 RTL 探针**，用于 OOC 综合拿 LUT/BRAM/时序的真实数字。**这是探针，不是完整译码器。**

【背景】
要把 DVB-S2 R=5/6 LDPC 硬判决 flooding Min-Sum 译码器集成到 XC7Z020（PL 100 MHz）。
架构已定为 **p=1 边串行**（见 `docs/reference/ldpc-architecture-decision-2026-10-14.md`，**先读它**）。
本步目的：在写完整译码器**之前**，先验证这类结构在 100 MHz 能否收敛、资源是否可接受。
（K=2 整机现只剩 WNS +0.313 ns，时序是最可能失败的一关。）

【要交付什么】
**新文件 `hw/experimental/ldpc_row_engine_probe.v`**（放 experimental 是因为它不该被 IP 打包/进生产综合），含两个模块：

### (A) `ldpc_h_addr_gen` —— 地址转换
给出行号 `r` 与边序号，输出该边连接的信息/校验列地址 `addr` 与 `valid`。规则见架构决定文与交接文 §4.2：
- 校验位部分（前 10800 列）是双对角累加器：第 0 行连列 `{0}`，第 `r>0` 行连列 `{r-1, r}`；
- 信息部分：组 `t`（0..149）、组内位置 `m`（0..359），列为 `10800 + 360t + m`，连接的校验行为 `(x + 30m) mod 10800`，`x ∈ B_t`；`B_t` 共 600 个基地址。
- 紧凑表用 **600 项 × 14 bit 的 ROM**。**ROM 初值不要让它被综合折叠掉**：请用 `(* rom_style = "block" *instance* 或 "block" *)` 并写入一个**确定性的非平凡内容**（例如 `(i*40503+7) mod 10800` 之类），并在注释里写明"探针内容非真实 B_t，仅为避免被折叠"。
- 地址计算必须是**可综合的组合/时序逻辑**，不要用仿真专用构造。

### (B) `ldpc_row_engine_probe` —— 行引擎（p=1，每拍一条边）
参数：`N=64800`、`MAXDEG=22`、`LLR_W=6`、`ACC_W=10`、`AW=17`。
内部两块**推断出来的 simple dual-port BRAM**：`llr_mem[N]`（`LLR_W` 位）、`acc_mem[N]`（`ACC_W` 位）。
建议 FSM：
1. **GATHER**：接受 `deg` 个边地址（每拍一个，来自 (A)），读 `llr_mem[addr]`，更新 最小/次小幅值与总符号积，并把 `(addr, llr)` 存进**行缓存**（最多 `MAXDEG` 项寄存器）。
2. **EMIT**：对缓存里每条边，算外出消息（幅值 = 该边 `abs` 等于 min1 时取 min2，否则取 min1；符号 = 总符号积 xor 该边符号），然后 **读 `acc_mem[addr]` → 加 → 饱和 → 写回**。
3. 结束脉冲 `done`。
- 加法用**饱和**（这是 L1 结论：饱和必需，回绕版完全不收敛），不要回绕。
- 输入端口至少要有：`clk`、`rst`、`start`、`deg`、以及边地址输入与 `done` 输出。

【硬性要求】
1. **可综合**：不能有 `initial`、`#delay`、`$display` 之类仿真构造（ROM 初值请用 `$readmemh` 之外的合法方式，例如 generate + case，或 `initial` 只用于 ROM 初值——若用 `initial` 给 ROM 赋初值，请确认 Vivado 综合接受并在答复里说明）。
2. **大存储器必须推断成 BRAM**，不能落在分布式 RAM。读写模式要符合 BRAM 推断模板。
3. **参数化**：`MAXDEG`、`LLR_W`、`ACC_W` 要能通过 `-generic` 覆盖，便于多档摸底。
4. **更新 `hw/experimental/README.md` 的「当前内容」表**，按该表现有格式加一行（这是仓库卫生门禁检查项，不加会红）。

【你要实际做的验证】
用仓库现成流程跑**一次 OOC 综合**（不跑 impl，impl 由 main 跑）：
```
SYNTH_PART=xc7z020clg400-2 SYNTH_TAG=ldpc_row_engine SYNTH_OUT_ROOT=logs/vivado/ldpc-probe \
  <本机路径> -mode batch \
  -source docs/submission/skill/fpga-timing-probe/ooc_probe.tcl \
  -tclargs ldpc_row_engine_probe 100 hw/experimental/ldpc_row_engine_probe.v
```
（`-tclargs` 里可以再加更多 `.v`；若你想拆成两个文件也可以，但要说明。）
拿到：**是否综合通过、LUT/FF/BRAM/DSP、综合后 WNS**，并把**报告目录路径**写进答复。

【硬约束】
- **不要**改 `sw/`、`tools/`、`docs/` 里的既有文件；只新增 `hw/experimental/ldpc_row_engine_probe.v` 并更新 `hw/experimental/README.md` 那一行表。
- **不要**跑 impl / route（那一步由 main 做，为了资源独占）。
- **不要**做 Git 写操作；**不要**运行 `tools/verify_repo_binding.sh`（沙箱内 git 只读，必然失败白跑）。
- 不碰板卡、不跑 XSim。
- 看板：用 `tools/agent_view.sh start/update/done --agent ldpc-probe-rtl ...` 自行登记（workspace-write 由你登记）。

【交付】
1. 新增/改动文件清单；
2. **OOC 综合的原始数字**（LUT/FF/BRAM/DSP、综合后 WNS、是否通过）与报告目录路径；
3. **明确声明哪些数字是综合结果、哪些是你没做的**（例如"未跑 impl、无布线后 WNS"）；
4. 你为"避免 ROM 被折叠"所采用的具体做法，以及它在综合日志里的体现。
答复用中文。