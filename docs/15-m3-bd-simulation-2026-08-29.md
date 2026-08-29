# 15 · M3：实际 Block Design 集成仿真（2026-08-29）

本文记录 M3 的实施结果。技术计划见 `docs/13-xsim-simulation-plan.md` §7，
排序理由见 `docs/14-next-steps-2026-08-29.md`。

---

## 1. 一句话结论

**BD-1 与 BD-2 已关闭；BD-3 未关闭，被 Xilinx PS7 VIP 的 HP0（AFI）从机读通路挡住。
因此 M3 整体仍是「未完成」，更不允许据此关闭 G3。**

| 步骤 | 内容 | 结果 |
| --- | --- | --- |
| BD-1 | 实际 BD 重建 / 静态检查 / elaboration | **PASS** |
| BD-2 | 控制面：GP0 → ic_lite → 四个从机 | **PASS**（71 项检查 0 失败） |
| BD-3 | 数据面（生产 BD，端点为实际 PS7 HP0） | **未通过**：被 PS7 VIP 的 HP0 读通路挡住 |
| BD-3ext | 数据面（仿真专用端点，HP0 换成 AXI VIP 内存） | **Decoder 逐位通过；Voter 暴露真实 RTL 缺陷 B20** |

> ### 🔴 M3 的最大产出：发现 Voter 违反 AXI 4KB 边界规则（缺陷 B20）
>
> 换上可用的内存端点后，Xilinx AXI 协议检查器立刻抓到：
>
> ```
> Warning: ARADDR=0x10600ff0, ARID=0x2, ARLEN=0x05, ARSIZE=0b011
> Fatal: AXI4_ERRM_ARADDR_BOUNDARY: A burst must not cross a 4kbyte boundary.
>         Spec: section A3.4.1.
> ```
>
> 这是**真实的 RTL 协议违规**，不是仿真模型问题，详见 §6。

本机证据目录：`hw/build/xsim/m3/20260828T171531Z/`（`bash tools/run_m3_bd.sh all`）。
该目录在 `.gitignore` 中，**不随 Git 分发**，换 checkout 必须本机重跑。

---

## 2. 交付物

| 文件 | 作用 |
| --- | --- |
| `hw/scripts/m3_bd_sim.tcl` | 从 `hw/scripts/bd.tcl` 在一次性目录重建实际 BD、做静态检查、生成 simulation target、编译并 elaborate。**不触碰** `hw/build/dna_accel.xpr` |
| `hw/sim/m3/tb_m3_bd2_ctrl.v` | BD-2 控制面 Testbench |
| `hw/sim/m3/tb_m3_bd3_dpath.v` | BD-3 数据面 Testbench（plusarg 选择 voter/decoder、内存镜像、HP0 延迟档；`+vipdebug=1` 打开 VIP 与 HP0 AR/R 探针） |
| `tools/m3_mem.py` | 黄金 64 bit 向量 ⇄ PS7 VIP DDR 的 32 bit 字镜像格式互转与逐位比较 |
| `tools/run_m3_bd.sh` | M3 统一入口：`bash tools/run_m3_bd.sh [all\|bd1\|bd2\|bd3]` |

DUT 始终是 `bd.tcl` 生成的**实际** `top_bd_wrapper`：真实 PS7（仿真时为
`processing_system7_vip`）、实际 `axi_interconnect`（ic_lite / ic_hp）、实际 AXI DMA
和三个自研 IP，不是简化模型。

---

## 3. BD-1：静态与 elaboration —— PASS

从干净目录重建 BD 并 elaborate `top_bd_wrapper`，自动核对：

- **地址图与 `sw/app/xparameters.h` 逐项一致**：
  DNA `0x43C0_0000`、Decoder `0x43C1_0000`、Voter `0x43C2_0000`、AXI DMA `0x40400000`；
  DMA 的 MM2S/S2MM/SG 与 Voter/Decoder 的 M00_AXI 全部映射到
  `SEG_ps_0_HP0_DDR_LOWOCM` offset `0x00000000` range `0x20000000`（512 MB），
  覆盖 `docs/05-interfaces.md` §4 的全部 DDR 区间。
  > 顺带澄清 `docs/05-interfaces.md` §3.3 的一处历史存疑：那里提醒「`bd.tcl` 注释把
  > Voter 与 Decoder 的地址写反」。本次核查发现当前 `bd.tcl` 里并没有会写反地址的注释，
  > 且 `assign_bd_address` 生成的实际地址与 `xparameters.h` 完全一致，
  > 该提醒可视为已经不再适用。
- **未连接接口只有 `/ps_0/S_AXI_HP0_FIFO_CTRL`**（PS7 可选边带，非数据通路）。
- **三个自研 IP 均在 BD 中且未被锁定**，无待升级 IP。
- **elaborate 无黑盒、无缺失模块**。全部 51 条 warning 都落在 Xilinx 自带 IP 的仿真模型内
  （PS7 VIP、fifo_generator、protocol converter）或可选未连接端口，本项目 RTL 无一条。

---

## 4. BD-2：控制面 —— PASS

主设备是 **PS7 VIP 的 M_AXI_GP0**（不是通用 AXI VIP），经实际 `ic_lite` 打到四个实际从机。
71 项检查、0 失败：

1. **复位初值**：Voter `0x00` 与 Decoder `0x18` 读回 `idle=1, done=0`。
2. **AXI DMA 地址译码**：`MM2S_DMASR` 读回 `0x00010009`，复位后 `Halted=1` 符合预期。
3. **Voter 六个寄存器写/读回逐位一致**：`IN_ADDR/IN_BEATS/OUT_ADDR/OUT_BEATS/TOTAL_READS/SCORE_MIN`
   （含 `SCORE_MIN=67`，对应 `echo.c` 的回读校验语义）。
4. **Decoder 四个寄存器写/读回逐位一致**。
5. **DNA `wm_sel` 写/读回**覆盖 0/10/20/30/40/49 六个区域号。
6. **从机隔离**：三个 IP 基址只差 `0x0001_0000`，用「写 Voter 后回读 Decoder 与 DNA 不变」
   和反向用例证明 `ic_lite` 没有地址混叠。
7. **无效地址**：读未映射的 `0x43C3_0000` 返回 `RRESP=11`（DECERR），既不是静默 OKAY 也没挂死。
8. **错误响应之后总线仍可用**：紧接着读 Voter `SCORE_MIN` 仍得 67。

### BD-2 的边界

- PS7 VIP **不是**真实 ARM：不覆盖 cache 维护、lwIP、PHY、SG 描述符管理和实际 ELF。
- 本用例只驱动控制面，不搬运业务数据。
- 「AW/W 独立到达」这一条：BD 层的实际 Interconnect 会自然产生 AW/W 偏斜，但本用例
  无法逐拍构造该时序；该判据仍由 IP 级黄金 TB（`tb_dna_axil` 等，Icarus 与 XSim 双通过）背书。

---

## 5. BD-3：数据面 —— 未通过（阻塞在 PS7 VIP 的 HP0 从机）

### 5.1 已经打通的部分

- DDR 镜像预载成功（VIP 自报 `DDR Memory is pre-loaded with ... bytes`）；
- 经 GP0 配置 Voter/Decoder 全部寄存器并回读校验成功；
- 写 start 后两个 IP 都真的动起来并发出 AXI4 读请求；
- 请求确实经实际 `ic_hp` 到达 PS7 的 `S_AXI_HP0`，AR 握手完成。

### 5.2 卡在哪

**HP0 从机接受了 AR，却一拍 RDATA 都不返回**，最终由 Xilinx AXI VIP 的前向进展看门狗终止：

```
Fatal: [slv_rd_driver] ... forward_progress_watchdog :
  Forward progress timeout triggered. There are pending AR commands (1),
  however, a corresponding RDATA+RLAST has not occured in (50000) cycles.
```

HP0 AR 通道探针抓到的实际事务完全合法：

| 发起者 | ARADDR | ARLEN | ARSIZE | ARBURST | ARID | 结果 |
| --- | --- | --- | --- | --- | --- | --- |
| Voter | `0x10600000` | 5（6 拍 = 48 B） | 3（8 B） | 01 INCR | 010 | 无 R 拍 |
| Decoder | `0x11000000` 起，每次 +0x80，共 8 笔 | 15（16 拍 = 128 B） | 3 | 01 INCR | 011 | 无 R 拍 |

两者都是对齐的 INCR 突发、不跨 4 KB 边界、落在已映射且已预载的地址上。

### 5.3 为什么判断是仿真模型限制，而不是设计缺陷

逐条排除：

| 假设 | 排除依据 |
| --- | --- |
| 突发跨 4 KB 边界 | 用 `total_reads=80`（数学上不可能跨界）复跑，**仍在同一时刻卡死**；且 Voter 首笔就是 48 B 对齐突发 |
| 未命中的地址范围 | HP0 段为 `0x00000000+512MB`；VIP 的 AFI 从机默认 `BASEADDR=0x00000000 / HIGHADDR=0xFFFFFFFF`；VIP 的 DDR 数组为 1 GB；同地址的预载由 VIP 自己确认成功 |
| DDR 容量不足（怀疑 VIP 只建模 256 MB，而项目缓冲区都在 `0x1000_0000` 以上） | 用 `+s2_addr=01000000 +s3_addr=01100000` 把整级搬到 16 MB 处复跑，**同样卡死**，与地址高低无关 |
| 超出未完成读事务上限 | Voter 的 FSM 一次只发 **1 笔**读突发，同样卡死；不需要触及 VIP 的 `max_rd_outstanding_transactions = 8` |
| 某一档从机延迟的问题 | `BEST_CASE(0)`、`AVG_CASE(1)`、`WORST_CASE(2)` 三档**全部**卡死 |
| 某个 IP 自身的问题 | Voter 与 Decoder 两个独立 IP、不同突发长度/ID/CACHE，症状一致 |
| HP0 未使能或时钟/复位没接 | `C_USE_S_AXI_HP0(1)`，日志自报 `S_AXI_HP0 : Port is ENABLED`；`S_AXI_HP0_ACLK` 已接 `clk_wiz_0/clk_out1`；PS7 无 `S_AXI_HP0_ARESETN` 引脚，该复位由 VIP 内部生成；同一时钟域的 GP0 全程正常 |

打开 VIP 内部调试（`set_debug_level_info(1)`，覆盖 `ddrc.ddr_read_ports` 与
`icm.ssw.ddr_hp01.ddr_hp_rd`）后，**DDR 读端口没有任何日志**——请求根本没走到 VIP 的
DDR 读通路。VIP 的读响应进程停在
`wait(arvalid_flag[rresp_time_cnt[...]] == 1)` 上。

结论：证据都指向 **Vivado 2022.2 的 `processing_system7_vip` HP/AFI 从机读通路在本配置下不返回数据**。
真实硬件上 HP0 接的是实际 DDR 控制器，其读发起能力本就按 8 笔设计，
**因此不能据此说 BD 或 RTL 有缺陷；但同样不能声称数据面已验证。**

> **明确不做的事**：不会为了绕开仿真模型的问题去改生产 BD（例如压低 Interconnect 的
> 未完成事务数或改 `RDISSUECAP`）。那是拿真实硬件配置迁就模型，属于为变绿而放宽判据。

### 5.4 下一步可选路径（按推荐顺序）

1. **换掉仿真里的内存端点**：保留实际 BD 与三个自研 IP，只在**仿真专用**的 harness 里
   把 `ic_hp` 的 M00 接到 Xilinx AXI VIP 从机或一个简单 AXI4 内存模型，替代 PS7 的 HP0。
   报告必须写明「这不是实际 PS7 的 AFI 通路」。
2. 换 Vivado 版本复跑同一用例，确认是否为 2022.2 特有行为。
3. 若最终无法在合理成本内让 HP0 从机工作，就按 `docs/13` §7.2 的既定退路：
   保留 actual-BD 的 elaboration 与控制面结论，把数据面的 BD 级验证标为未覆盖，
   并在 G3 上板时重点采集 Voter/Decoder 的 AXI 读写证据。

无论走哪条，**M2 已经证明三级算法链本身逐位正确**（`docs/13` 的 M2 完整串联记录），
BD-3 缺的是「同一条链在实际 BD 连接下」的事务级证据。

---

## 6. 复跑方法

```bash
bash tools/verify_repo_binding.sh --remote     # 强制门禁
bash tools/run_m3_bd.sh all                    # BD-1 + BD-2 + BD-3
bash tools/run_m3_bd.sh bd2                    # 只跑控制面
```

证据落在 `hw/build/xsim/m3/<RUN_ID>/`，含 `summary.txt`（HEAD、工具版本、黄金向量与
Testbench 的 SHA-256）、`bd_address.txt`、`bd_unconnected.txt`、`bd_ip_status.txt`
和各用例日志。**该目录在 `.gitignore` 中，不随 Git 分发**；换 checkout 必须本机重跑。

由于 BD-3 未通过，`run_m3_bd.sh all` 目前会以非 0 退出——这是如实反映
「M3 未完成」，不是脚本缺陷。

---

## 7. 边界声明（不得越过）

- M3 未完成，**不允许**据此关闭 G3。
- 即使 BD-3 将来通过，普通 XSim 仍不能证明 lwIP、真实 PHY、真实 DDR 电气行为、
  ARM cache 维护和 SG DMA 描述符管理正确。
- 最终判据不变：真实板端回传经 LDPC 后重建 JPEG 的 SHA-256 等于
  `fcd0cf90bd680e7bbdc203e3398119504da0897acac9e2117008b4efb6b1f2c3`。

---

## 6. BD-3ext：换掉仿真内存端点后的结果（含缺陷 B20）

### 6.1 做法

`hw/scripts/bd_sim_mem.tcl` 在生产 `bd.tcl` 的基础上只做**一处**替换：
断开 `ic_hp/M00_AXI -> ps_0/S_AXI_HP0`，改接 `axi_vip(SLAVE)` 内存模型，
并把五个主设备（DMA MM2S/S2MM/SG、Voter、Decoder）按**完全相同的真实地址**
（`0x00000000 + 512 MiB`）重新映射。控制面仍走实际 PS7 VIP 的 GP0 → 实际 `ic_lite`。

生成结果核对：控制面地址与生产 BD 逐行一致
（DNA `0x43C00000` / Decoder `0x43C10000` / Voter `0x43C20000` / DMA `0x40400000`），
0 error。Testbench 为 `hw/sim/m3/tb_m3_bd3_extmem.sv`，入口
`bash tools/run_m3_bd.sh bd3ext`。

> **结论边界**：内存端点是 AXI VIP，**不是实际 PS7 的 AFI/DDR 控制器**。
> 本路径能证明「三个自研 IP 经实际 Interconnect 在真实地址上正确读写内存」，
> **不能**证明 PS7 AFI 本身的行为。

### 6.2 Decoder：逐位通过

Decoder 经实际 `ic_hp` 在真实地址读写，`done` 正常，全程 0 条协议违规；
输出 1013 拍 / 64,832 bit 与 `tests/golden/stage3_expect.hex` **逐位相同**。

（Testbench 在启动前把输出区清零，因此 DUT 用 `WSTRB` 有意不写的末拍填充字节
读回为 0，与黄金向量一致；若 DUT 漏写也会立刻暴露成 0，而不会被残留数据掩盖。）

### 6.3 Voter：暴露缺陷 B20 —— 读突发跨越 4 KB 边界

**现象**（`hw/build/xsim/m3/` 下 bd3ext 的 Voter 日志）：

```
Warning: ARADDR=0x10600ff0, ARID=0x2, ARLEN=0x05, ARSIZE=0b011
Fatal: AXI4_ERRM_ARADDR_BOUNDARY: A burst must not cross a 4kbyte boundary.
```

**成因**（`hw/ip/differential_voter_1_0/hdl/differential_voter_v1_0.v`）：

- 第 675 行 `assign M00_AXI_ARLEN = 8'd5;` —— 固定 6 拍；
- `ARSIZE = 3`（8 B/拍），即每次读突发固定 **48 B**；
- 第 512 行 `read_addr <= read_addr + (WORDS_PER_READ * 8);` —— 每条记录 **+48 B**；
- **全程没有 4 KB 边界处理**。

因为 4096 不是 48 的整数倍（4096 / 48 = 85.33），地址每前进一段就会出现
「突发起点距页尾不足 48 B」的情况，此时该突发跨页，违反 AXI 规范 A3.4.1。

**量化**（`BASE=0x10600000`，步长 48 B，突发 48 B）：

| 项 | 值 |
| --- | --- |
| 4096 条记录中跨界的突发数 | **32** |
| 首次跨界 | 记录 **85**，地址 `0x10600ff0`（与仿真器报告完全一致） |
| 周期 | 每 256 条记录 2 次（`i ≡ 85, 170 (mod 256)`） |

**未受影响的通路**（均为 128 B 突发、4 KB 对齐基址，跨界数为 0）：
Decoder 的读、Voter 的写、Decoder 的写。**缺陷只在 Voter 的读路径**。

### 6.4 为什么以前没被发现

Stage2 的既有黄金 Testbench（`tb_differential_voter.v`，Icarus 与 XSim 双通过、
M2 完整串联也通过）使用的是**自带的简易 AXI 从机内存模型**，它不检查 4 KB 规则，
给什么地址和长度就返回什么数据。而实际 AXI Interconnect / PS7 AFI 没有义务这样宽容。

这正是 M3「实际 BD 集成仿真」存在的意义：它覆盖的恰好是 IP 级黄金 TB 看不到、
又最难在板上定位的一类错误。

> ⚠️ 需要澄清一处本轮调查中的弯路：在 BD-3（生产 BD）阶段曾用 `total_reads=80`
> 试图证伪 4 KB 假设，当时"仍然卡死"于是把该假设排除。**那次排除是无效的**——
> 因为 PS7 VIP 的 HP0 通路在更早的位置就已经卡死，根本没跑到记录 85，
> 故障被完全掩盖。教训：在一个已知损坏的平台上做的排除性实验不能作为证据。

### 6.5 B20 的影响与修复选项（**待用户决定，尚未实施**）

**影响**：AXI 规范下，跨 4 KB 的突发行为未定义。实际 Interconnect / AFI 可能返回
错误数据、错位数据或挂死。这极可能是一个**真实的 G3 阻塞项**，且在板上表现为
「偶发错数据 / 卡死」，极难定位。

| 方案 | 做法 | 优点 | 代价 |
| --- | --- | --- | --- |
| **A. 拆分突发**（推荐） | 在 `S_READ_SETUP` 判断是否跨页；跨页则拆成两笔突发（到页尾 + 余下） | 性能几乎不变，语义最干净 | 需要改读 FSM 并新增状态，改动量中等 |
| B. 退化为单拍读 | `ARLEN=0`，每条记录发 6 笔单拍读 | 改动最小、绝对安全 | AR 事务数 ×6（约 +2.5~5 ms/任务），相对 Stage1 耗时可忽略 |
| C. 记录对齐到 64 B | 把每条记录的 DDR 步长由 48 B 改为 64 B | 突发永不跨页 | **改动数据契约**，PS/DMA/`echo.h`/黄金向量都要跟着改，影响面最大 |

无论选哪个，改完都必须重跑：Icarus 11/11、XSim 6/6、M2 完整串联、
BD-3ext、以及 Vivado 综合/时序，并**重建 A 阶段的全套上板制品**。

---

## 7. 当前 M3 状态汇总

| 步骤 | 状态 |
| --- | --- |
| BD-1 | ✅ 通过 |
| BD-2 | ✅ 通过（71 项检查 0 失败） |
| BD-3（实际 PS7 HP0 端点） | ⛔ 被 Vivado 2022.2 PS7 VIP 的 HP0 读通路挡住，非设计问题 |
| BD-3ext Decoder（仿真端点） | ✅ 逐位通过 |
| BD-3ext Voter（仿真端点） | ❌ 暴露缺陷 **B20**（AXI 4 KB 跨界），待修 |
| M4 | 未开始 |

**M3 仍未完成**，且现在多了一个必须先修的 RTL 缺陷。不得据此关闭 G3。
