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
| BD-3 | 数据面：Voter/Decoder 主口 → ic_hp → HP0 → DDR | **未通过（阻塞）** |

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
