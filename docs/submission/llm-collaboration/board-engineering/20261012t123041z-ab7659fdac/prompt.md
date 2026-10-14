> 脱敏副本，原件 `20261012T123041Z-ab7659fdac/{prompt.txt,answer.md}`。本机绝对路径、邮箱、凭据形模式及非白名单私网 IP 已替换；除脱敏与换行规范化外保留原文。

你是 board-migrate（看板名 board-migrate）。第三阶段任务：**BKB220 新板 P4/P16 整机 100MHz 构建与时序收敛**。前两阶段你已交付来源表、candidate PS7 profile 与 4 套 UART ps7_init，main 已复核并已实板跑通 DDR/UART（见 docs/board/bkb220/migration-source-table.md §9），不要重做。

先读 docs/agent-prompts/board-migrate.md、AGENTS.md、CLAUDE.md、docs/05-implementation-plan.md（F4/F5 行）、docs/07-board-build-and-acceptance.md（含 §3a 触板通道）、docs/board/bkb220/migration-source-table.md（尤其 §8/§9）。

【看板】workspace-write，自己 `tools/agent_view.sh start --agent board-migrate --doing ... --why ... --next ...`，长任务启动前先 update 说明在跑什么与预计时长，阶段 update，受阻 block，收工 done。
【禁止】任何 Git 写操作；不建分支/worktree；不派生子 Agent；**不触板**（JTAG/串口/下载/reset 全归 main）；不改 docs 根目录 01～09。不要运行 `tools/verify_repo_binding.sh`（main 的门禁，沙箱 git 目录只读必失败）。

============ main 已确认的现状 ============
- `hw/boards/bkb220.tcl` 的 `ready` **已由 main 置 1**（用户 2026-10-12 明确授权"先建 P4，ENET0 留到板测再验"）。profile 头部写明了已实测项与仍未证实项，**先读它**。
- `part_name` 必须与板配置的 `expected_part` 一致：`xc7z020clg400-2`。
- `tclsh hw/scripts/build.tcl board=bkb220 dry_run=1` 现在会走到「新板必须显式指定独立 build_dir」——说明守卫已放行，你**必须**显式传独立的 build_dir/export_dir/report_dir。
- 实板已证实：PS_CLK=33.333MHz、DDR3-1066(533.33MHz) 读写可用、PS UART=UART0/MIO14-15→FT4232H 通道 C、FCLK0 目标 100MHz。
- **ENET0/PHY 未通过**：GEM0 存在、寄存器可写、MDIO 完成标志（`NETWORK_STATUS[2]`）正常，但 PHY 0..31 全地址无应答；已知网线是板子直连主机 ASIC 网卡且链路 1Gbps Up（故 PHY 有电、未被复位保持）。当前 profile 里的 ENET0 = MIO16-27 + MDIO52/53 是**候选**，不是已证实值。

============ 本阶段任务 ============
用 **WSL Vivado 2022.2**（`VIVADO_ROOT=<本机路径>`，显式固定，不要用 Windows 26 做这一步）跑：

**A. P4 整机（必须完成）**
```
VIVADO_ROOT=<本机路径> bash tools/run_vivado_build.sh \
  board=bkb220 part_name=xc7z020clg400-2 clk_mhz=100 \
  stage1_p_ways=4 stage1_pipe_tree=0 \
  build_dir=<全新独立目录> export_dir=<全新独立目录> report_dir=<全新独立目录>
```
必须走到**完整 route**（不是 OOC、不是仅综合）。逐项报告：
- 是否 impl 完成、bit 与 XSA 是否生成、XSA 内 part 是否确为 xc7z020。
- **WNS / WHS / TNS / THS**，**失败端点是否为 0**，以及 100MHz 时钟是否被识别为 `clk_fpga_0` 且确为 100MHz（从时序报告读，不要从我们的配置反推）。
- DRC 违规、路由状态、以及资源占用（LUT/FF/DSP/BRAM 的 used 与 %）。
- 若有失败端点：给出**具体端点名、路径类型与 slack**，判断是真实关键路径还是约束缺失。**不要加无依据 false path、不要降频**来"修复"。
- 原始报告路径（时序摘要、DRC、utilization）+ 你的实际命令与退出码。

**B. P16 整机（必须完成，独立目录）**
同一条命令改为 `stage1_p_ways=16 stage1_pipe_tree=1`，**全新独立 build/export/report 目录**。同样报告上面每一项，并额外给出：P16 相对 P4 的 LUT/DSP/BRAM 增量与 WNS 变化。这是本次迁移的核心技术问题（P16 能否在真实器件上收敛 100MHz）。

**C. 不要做的事**
不要生成/覆盖旧 `hw/build/export/`；不要跑板测；不要做 Windows 2026.1 的构建（那是 F9，本轮明确不做）；不要改 RTL / `component.xml` / `hw/sim`（归 rtl-16way / verify-system）；不要为了让时序"过"而改约束或降频。

**D. 如果构建失败**
如实报告失败阶段与原始错误；区分 `tooling`（工具/脚本问题）与 `functional`（设计/配置问题）。失败时**保留全部日志与工程目录**，不要删除、不要重跑掩盖。若失败原因是 ENET0/PS7 配置，明确说明并给出你建议改什么、为什么。

============ 报告要求 ============
最终答复给出：① P4 与 P16 各自的完整命令、退出码、日志/报告路径；② 每项的 WNS/WHS/TNS/THS、失败端点数、DRC、资源占用、100MHz 确认；③ 明确区分 PASS / FAIL / 未测（例如"route 完成但 WHS<0"必须写成 FAIL 并给端点）；④ 与 rtl-16way 先验（P16 整机约 33.9k LUT / 64%）的对比；⑤ 下一步依赖。收工 `tools/agent_view.sh done --agent board-migrate`。