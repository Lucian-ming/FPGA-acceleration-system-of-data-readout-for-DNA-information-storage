# 17 · 并行任务简报：定位 B21（Stage1 板上硬卡死）

本文供**两个并行会话**冷启动使用。两条路径互相独立、可同时进行，
但**只有任务 B 允许碰开发板**（见 §0 的互斥约定）。

结论与判据仍要写回 `docs/` 并提交；`view.md` 只是实时看板，不进 Git。

---

## 0. 两个会话的共同前置（每个会话都要先做）

```bash
cd /home/lucian/projects/FPGA/FpgaAccelerationSystemOfDataReadout
bash tools/verify_repo_binding.sh --remote     # 强制门禁，未通过禁止任何开发
```

**看板登记（强制，见 `CLAUDE.md`）**：

| 会话 | `--agent` 名字 |
| --- | --- |
| 任务 A（BD-3b 仿真复现） | `bd3b-sim` |
| 任务 B（板上诊断） | `board-diag` |

```bash
tools/agent_view.sh start --agent "<上表名字>" \
  --doing "..." --why "定位 B21" --next "..."
```

### 互斥约定（重要）

- **只有任务 B 可以操作开发板**（JTAG 烧录、XSDB、串口 COM6、Vivado Lab）。
  任务 A **禁止**碰板子与 `D:\dna_board_smoke\`，否则会打断对方的现场。
- 两个会话都可能跑 Vivado/XSim；机器只有 8 核，**避免同时启动两个大型综合**。
  长任务启动前先 `tools/agent_view.sh update` 说明在跑什么，另一方看板上能看到。
- 都要提交到 `main` 并 `git push`；提交前 `git pull --rebase` 避免冲突，
  **不要用 `git add -A`**（会扫进对方的临时文件），按文件显式 `git add`。

---

## 1. 背景：已经确认成立的事实

首次上板（2026-08-29）已实测通过，**这些不要重复验证**：

| 环节 | 状态 |
| --- | --- |
| DDR（16 bit 修正后）训练 + 11 地址 × 4 图案读写自检 | ✅ |
| 三个 IP 复位（Voter/Decoder `IDLE=1,DONE=0`） | ✅ |
| 千兆链路 1000 Mbps、`Board IP 192.168.1.10`、TCP:7 | ✅ |
| CAPS/CONFIG 握手（`L=40500, reads=4096, score_min=67`） | ✅ |
| 水印下发 10,128 B → 展开 50 区域 × 957 符号 = 191,400 B | ✅ |
| 读段下发 4,096 条 / 163,840 B | ✅ |
| 仿真侧：Icarus 11/11、XSim 6/6、M2 完整串联、BD-1、BD-2、BD-3ext | ✅ |

**缺陷 B21**（详见 `docs/03-status.md` 同名条目）：板端打印到
`[STAGE1] IP core START` 后再无输出，客户端 180 s 超时。XSDB 只读取证：

- RX BD 环 Cmplt = **13 / 1024**（首个未完成 = 13）
- TX BD 环 Cmplt = **69 / 2048**（首个未完成 = 69）
- 所有 BD 的 DecErr/SlvErr/IntErr = **0**
- RX BD 样本 `0x8c000030` = Cmplt + RXSOF + RXEOF + 48 B（一条完整记录）
- TX BD 样本 `0x80000ef4` = Cmplt + 3828 B（= 957×4，水印预载）
- 隔时复测数值完全不变 → **硬卡死**，非总线错误

推断：TX 的 69 个中前 50 个是水印预载，其余 19 帧（每帧 64 条 × 40 B）
约 1,216 条读段已进入 DNA 核，而核只吐出 13 条结果即停止。

**根因缺口**：`AXI DMA MM2S → DNA S_AXIS` 与 `DNA M_AXIS → AXI DMA S2MM`
这条链**从未在 BD 级仿真过**（`docs/13` §7.2 的 BD-3 第 1、2 项未实施）；
BD-3ext 只覆盖了 Voter 与 Decoder。IP 级 `tb_dna_ingress` 只测了 FIFO 背压，
没有真实 DMA、没有 50 次水印预载的区域切换时序。

### 三个优先怀疑方向

1. 水印预载 50 次区域切换时 `wm_waddr` 是否每次从 0 开始，
   `preload` 位与 DMA 的时序配合；
2. DNA ingress FIFO 满背压后能否恢复；
3. `start` 与 `preload` 位的先后与清除时机。

---

## 2. 任务 A —— BD-3b：在实际 BD 仿真里复现 Stage1 卡死

`--agent bd3b-sim`。**不碰板子。**

### 目标

把 `AXI DMA ↔ DNA` 这条唯一未被 BD 级覆盖的链补上，并在仿真中**复现 B21**。
复现出来才算找到根因；改完要能证明同一用例从 FAIL 变 PASS。

### 已有的可复用基础（不要重造）

| 资产 | 说明 |
| --- | --- |
| `hw/scripts/m3_bd_sim.tcl` | 生成实际 BD 工程；`bd_script_sel=sim_mem` 用仿真专用内存端点 |
| `hw/scripts/bd_sim_mem.tcl` | 把 PS7 的 HP0 换成 AXI VIP 内存模型（**必须用它**，理由见下） |
| `hw/sim/m3/tb_m3_bd3_extmem.sv` | SV TB 范例：PS7 VIP 驱动 GP0 控制面 + AXI VIP 后门读写内存 |
| `tools/run_m3_bd.sh` | 统一入口，已有 `bd3ext` 分支可照着加 `bd3b` |
| `tools/m3_mem.py` | 黄金 64bit 向量 ⇄ VIP 32bit 字镜像互转与逐位比较 |

> **必须用 `bd_sim_mem.tcl` 的原因**：Vivado 2022.2 的 `processing_system7_vip`
> 的 HP0/AFI 从机读通路在本配置下接受 AR 后不返回任何 RDATA
> （已逐条排除设计侧因素，见 `docs/15` §5）。用生产 BD 会卡在这个模型缺陷上，
> 而不是卡在真正的问题上。

### 建议做法

1. 新增 `hw/sim/m3/tb_m3_bd3b_dma.sv`，DUT 仍是 `bd_sim_mem.tcl` 生成的 BD。
2. 由 PS7 VIP 的 GP0 配置 **AXI DMA（SG 模式）**：
   在 VIP 内存里按 `sw/app/echo.c` 的方式构造 TX/RX BD 链
   （TX BD @ `0x11800000`、RX BD @ `0x11900000`，每个 64 B；
   `0x00 NXTDESC / 0x08 BUFADDR / 0x18 CONTROL / 0x1C STATUS`；
   TX 需置 `TXSOF|TXEOF`），再写 `CURDESC`/`RS`/`TAILDESC` 启动。
   寄存器：MM2S `0x40400000`，S2MM `0x40400030`。
3. **先复现水印预载**：50 次「写 `wm_sel` → 置 `preload` → DMA 957 × 4 B → 清 `preload`」，
   每次都检查 `wm_waddr` 行为。这是 1 号怀疑点。
4. 再送读段：至少 3 帧 × 64 条，观察 DNA 核吐出的结果条数是否等于送入条数。
   **判据是「送入 N 条 → 收到 N 条 48 B 记录」**，不是「跑完没报错」。
5. 若复现出「产出若干条后停止」，用波形定位停在哪个握手
   （`S_AXIS_DATA_TREADY`、`M_AXIS_RESULT_TVALID`、FIFO 满信号、`wm_waddr`）。

### 判据纪律

沿用 `docs/13` §十：编译通过、跑完、有波形都不算 PASS；每个用例要有显式 PASS/FAIL、
非零失败退出码、超时保护、逐位比较。**不得为了变绿放宽判据或屏蔽 X/Z。**

### 交付

- `tools/run_m3_bd.sh bd3b` 可一键复跑；
- 结论写进 `docs/15-m3-bd-simulation-2026-08-29.md` 新增一节；
- 若定位到 RTL 缺陷，按 B20 的方式在 `docs/03-status.md` 立条目（编号 B22 起）。

---

## 3. 任务 B —— 板上诊断：缩小 Stage1 卡死范围

`--agent board-diag`。**独占开发板。**

### 环境（已验证可用，直接照抄）

- Windows 侧 **Vivado Lab 2022.2**：`D:\dev_tools\Vivado_Lab\2022.2\bin\`
  （`vivado_lab.bat` / `xsdb.bat`）。
  **WSL 里的 Vivado 连不上 Windows 的 hw_server**（TCP 探测会误报成功，
  实际协议握手失败），必须在 Windows 侧跑批处理。
- 工作目录 `D:\dna_board_smoke\`（制品、Tcl 脚本都放这里）。
- JTAG：Digilent cable `210251A08870`，器件 `xc7z010_1`。
- 串口：**CH340 = COM6**，115200。`Win32_SerialPort` 查不到它，
  要用 `Win32_PnPEntity` 按 `Name -match 'COM\d+'` 找。
  抓取脚本 `D:\dna_board_smoke\uart_cap.ps1`（PowerShell SerialPort，写 `uart.log`）。
  **一次只能有一个抓取进程占用 COM6**，否则报「访问被拒绝」。
- 主机网卡已配 `192.168.1.100/24`（ASIX USB 千兆网卡，InterfaceIndex 47），
  板子 `192.168.1.10`，WSL 可直连。
  恢复 DHCP：`Set-NetIPInterface -InterfaceAlias "以太网 2" -Dhcp Enabled`。

### 两个已知的踩坑（别再踩）

1. **`mrd -value` 返回十进制**，不是十六进制。比较前必须
   `format %08x`，否则会把正确的读回值误判成 DDR 故障。
2. **XSDB 默认禁止访问 PL 地址**（`0x4000_0000+`），报
   "PL AXI slave ports access is not allowed"。原因是 Vivado Lab 无 HSI、
   `loadhw` 用不了。`memmap -addr ... -flags 3` 本轮**未能生效**，
   这是任务 B 需要解决的第一个问题（否则读不到 DMA/DNA 寄存器）。
   备选：DDR 里的 BD 环可以直接读（本轮就是这么取证的）。

### 建议做法

1. **先解决 PL 寄存器可读性**：或让 `memmap` 生效，或改用
   完整版 Vivado（WSL 内）+ Windows `hw_server` 的其它连法，
   或在固件里加寄存器 dump（见第 3 步）。
2. **保留现场取证**：`sw/app/echo.c` 已有 `dump_dma_regs()`，
   但卡死路径没触发它。可在 `PIPE_TX_STREAM` 加一个「N 次无进展就 dump」的兜底，
   把 MM2S/S2MM 的 `DMACR/DMASR/CURDESC/TAILDESC` 和 DNA 的 `reg0/reg1` 打出来。
3. **二分缩小**：用 `first.py --limit` 把读段数降到 64 / 128 / 256，
   看卡死是否与条数相关；再用 `--skip-watermark` 对照，
   判断是否与 50 次水印预载有关（这是 1 号怀疑点最快的验证）。
4. 每次改固件后按 `hw/build/export/README.md` 的流程重建 ELF 并记录哈希。

### 判据纪律

**板端「看起来跑通了」不算数**：最终判据仍是真实回传 8,100 B 经 LDPC 后
图片 SHA-256 等于 `fcd0cf90bd680e7bbdc203e3398119504da0897acac9e2117008b4efb6b1f2c3`。
中间阶段的结论要写明是「缩小了范围」还是「定位了根因」。

### 交付

- 诊断过程与结论写进 `docs/03-status.md` 的 B21 条目；
- 固件若有改动，同步更新 `hw/build/export/` 与其 `README.md`、`SHA256SUMS`。

---

## 4. 两条路径如何汇合

- 任务 A 在仿真里复现并定位根因 → 出补丁；
- 任务 B 在板上缩小范围 → 验证 A 的补丁是否真的解决问题。

**任一方定位到根因后**，都必须走完整回归：
`run_sim.sh` 11/11 → `run_xsim.sh all` 6/6 → `run_m2_full.sh` 全链 →
`run_m3_bd.sh bd2/bd3ext`（以及新增的 `bd3b`）→ Vivado 综合时序 →
重建 `hw/build/export/` 全套制品 → 再上板。

**G3 未闭环前，任何人不得声称端到端正确。**
