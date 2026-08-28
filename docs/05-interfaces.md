# 05 · 接口规范（协议 / 寄存器 / 地址）

本文按**截至 2026-08-16 的实现现状**记录，来源是 `sw/app/echo.h`、`sw/app/echo.c`、`clients/python/first.py`
和三个 IP 的 RTL。历史文档 `docs/reference/legacy-tech-note.md` 里的寄存器表是「示例模板」，
与实现不符，不要参考。

---

## 1. TCP 协议（PC ⇄ 板）

默认 `192.168.1.10:7`（IP/MAC 硬编码在 `sw/app/main.c`，`app_net_config.h` 为空且未被包含）。

**包头 8 字节，大端：**

| 偏移 | 宽度 | 字段 | 值 |
| --- | --- | --- | --- |
| 0 | u16 | magic | `0xBEEF` |
| 2 | u8 | type | 见下表 |
| 3 | u8 | reserved | 0 |
| 4 | u32 | payload_len | 负载字节数 |

| type | 名称 | 方向 | 负载 |
| --- | --- | --- | --- |
| 0x05 | `PKT_CONFIG` | PC→板 | 44 B 任务描述（见 1.1 节；**必须在 WM/BATCH/POST 之前**） |
| 0x06 | `PKT_CAPS` | PC→板 | 空，查询板端能力 |
| 0x01 | `PKT_WM` | PC→板 | 打包水印：逻辑有效载荷 10,125 B；当前客户端按 8 B 对齐发送 10,128 B，PS 上限 10,240 B |
| 0x02 | `PKT_BATCH` | PC→板 | `u32 BE` 本批条数 + 条数 × 40 B 读段 |
| 0x03 | `PKT_POST` | PC→板 | 空，触发流水线 |
| 0x04 | `PKT_RESULT` | 板→PC | 8,100 B 码字 |
| 0x15 | `CONFIG_OK` | 板→PC | **带包头**，4 B 状态码（0=接受，非 0=拒绝码，见 1.2 节） |
| 0x16 | `CAPS_INFO` | 板→PC | **带包头**，24 B 能力描述（见 1.3 节） |
| 0x11 / 0x12 | `WM_OK` / `BATCH_OK` | 板→PC | **裸 1 字节，无包头** |
| 0xEE | `PKT_ERROR` | 板→PC | 裸 1 字节：包头级错误（magic/长度/类型未知/顺序非法） |

> ⚠️ ACK（0x11/0x12/0xEE）是裸字节而 RESULT/CONFIG_OK/CAPS_INFO 带包头，这种不对称已经固化在两端，改协议时要成对修改。

### 1.1 PKT_CONFIG（0x05，PC→板，44 B，2026-08-16 新增 · P3）

任务参数在发数据前显式声明（G1/G2 语义）。**强制**：未收到合法 CONFIG 前，
板端对 WM/BATCH/POST 一律回 `PKT_ERROR`（决策：无兼容模式）；
校验失败**严格拒绝**（决策），状态码经 `CONFIG_OK(0x15)` 非 0 值返回。

| payload 偏移 | 字段 | 类型 | 约束（v1） |
| --- | --- | --- | --- |
| 0 | `version` | u8 | =1 |
| 1 | `read_bps` | u8 | 必须等于比特流值 150（SE250 留给 P7） |
| 2 | `reserved` | u16 | 0 |
| 4 | `num_lc` | u32 | 必须等于比特流综合参数 50 |
| 8 | `stride` | u32 | 必须等于 807 |
| 12 | `symbols` | u32 | 水印符号数 L，须满足 `symbols = num_lc×stride + read_bps`（当前 40,500） |
| 16 | `total_reads` | u32 | 本任务条数（含补零尾批）：64 的倍数，≤ `max_reads` |
| 20 | `score_min` | u32 | ≤ 1023（比对分 10 bit）；0=不过滤 |
| 24 | `reserved` | u32 | 0 |
| 28..39 | `reserved` | 12 B | 0（版本化扩展区） |
| 40 | `crc32` | u32 | CRC-32/IEEE（zlib 兼容，多项式 0xEDB88320，初值/终值 0xFFFFFFFF），覆盖 payload 前 40 B |

数值一律大端（与包头一致）。校验通过后板端把值用于：
Voter 的 `TOTAL_READS`/`SCORE_MIN`、cache/DDR 范围（`ddr_layout`）、
Voter/Decoder 的 `OUT_BEATS = ceil(2×symbols/64)`（v1 即 1,266/1,013），
且 `POST` 时校验实际收到条数 = 声明条数。

### 1.2 CONFIG_OK 状态码（4 B，大端）

| 码 | 含义 |
| --- | --- |
| 0 | 接受 |
| 1 | 协议版本不支持 |
| 2 | read_bps 不被当前比特流支持 |
| 3 | 几何不匹配（num_lc/stride/symbols 与比特流不符） |
| 4 | symbols 违反契约 `num_lc×stride + read_bps` |
| 5 | total_reads 非法（0 / 非 64 倍数 / 超容量 / DDR 越界） |
| 6 | score_min > 1023 |
| 7 | CRC32 不符 |
| 8 | 重复 CONFIG（本连接已配置） |
| 9 | 顺序非法（已收到 WM/BATCH 后才发 CONFIG） |

### 1.3 PKT_CAPS（0x06）/ CAPS_INFO（0x16，24 B）

连接后任意时刻可查。如实反映**当前比特流**的能力（决策：第一版只支持 SE150）：

| payload 偏移 | 字段 | 类型 | 当前值 |
| --- | --- | --- | --- |
| 0 | `version` | u8 | 1 |
| 1 | `read_bps` | u8 | 150 |
| 2 | `reserved` | u16 | 0 |
| 4 | `num_lc` | u32 | 50 |
| 8 | `stride` | u32 | 807 |
| 12 | `max_symbols` | u32 | 40,500（水印 BRAM 几何） |
| 16 | `max_reads` | u32 | 107,968（容量内最大 64 对齐条数） |
| 20 | `features` | u32 | bit0=支持 SCORE_MIN 寄存器（=1），其余保留 |

## 2. 时序

```
PC: CAPS ─────────────► 板: CAPS_INFO（24 B，任意时刻可查）
PC: CONFIG ───────────► 板: 校验 ──► CONFIG_OK(0)（4 B）
PC: WM  ──────────────► 板: 存入 DDR 水印区 ──► ACK 0x11
PC: BATCH ×N ─────────► 板: 写 DDR 读段区   ──► ACK 0x12（每批一个）
PC: POST ─────────────► 板: 展开 50 个水印区域并预载 → Stage1 → Stage2 → PS XOR 水印 → Stage3
PC: ◄───────────────── 板: PKT_RESULT + 8,100 B
```

未 CONFIG 先发 WM/BATCH/POST → `PKT_ERROR`；声明条数与实际收到不符 → `PKT_ERROR`。
每个 `PKT_BATCH` 只负责写入一批读段并返回一个裸 `BATCH_OK`/`PKT_ERROR`；即使达到声明条数，
板端也不会隐式启动流水线，客户端仍须发送显式 `PKT_POST`。
包头声明的 `payload_len` 若超过接收缓冲可容纳的 `99,992` 字节，或接收缓存溢出，板端先回
`PKT_ERROR` 再清理回调并关闭连接，以便下一次连接恢复。

AXI-Lite 控制口遵循 AW/W 独立握手：DNA、Voter、Desparsifier 三个生产从机分别缓存地址
与数据通道，二者均完成后才提交一次寄存器写并返回 B 响应；上层不能假定 AWVALID/WVALID
必须同周期。DNA 正常读段入口的 `S_AXIS_DATA_TREADY` 仅在输入 FIFO 非满时有效，预载水印
模式例外地直接接收，不经过读段 FIFO。

当前 BD 将 DNA、Voter、Desparsifier 的 AXI-Lite、AXI 主口和 DMA 时钟统一接到
`clk_wiz_0/clk_out1`。这些接口在本版隐含同一时钟域；若后续拆分时钟，必须先设计 CDC
并新增跨域 Testbench，不能只改端口名。

## 3. IP 寄存器

### 3.1 DNA Accelerator Core — `0x43C0_0000`

| 偏移 | 位 | 含义 |
| --- | --- | --- |
| 0x00 | [0] | `start`（上升沿启动，PS 置 1 后保持） |
| 0x00 | [1] | `preload`（1=AXIS 数据写入水印 BRAM） |
| 0x00 | [2] | `soft_reset` |
| 0x04 | [5:0] | `wm_sel` —— 水印区域号 0..NUM_LC-1 |
| 0x08 / 0x0C | — | 未使用 |

> `wm_sel` 是预载 50 个区域的唯一入口。B1 修复后的 `echo.c:465-495` 对每个区域写入
> `reg1=wm_sel`、DMA 957 个 32-bit 符号、退出 preload 后再切换下一区域；水印展开逻辑已通过
> 47,850 符号主机单测。AXIS 时序与 BRAM 实际写入仍待顶层仿真或上板确认。

### 3.2 Differential Voter — `0x43C2_0000`

| 偏移 | 读/写 | 含义 |
| --- | --- | --- |
| 0x00 | W | [0]=`start_pulse`，[1]=`done_clr` |
| 0x00 | R | [0]=`idle`，[1]=`done` |
| 0x04 | RW | `IN_ADDR` 输入 DDR 基址 |
| 0x08 | RW | `IN_BEATS` 输入拍数（= 记录数 × 6；硬件实际按 `TOTAL_READS` 计数） |
| 0x0C | RW | `OUT_ADDR` 输出 DDR 基址 |
| 0x10 | RW | `OUT_BEATS` 输出拍数（81,000 bit → 1,266） |
| 0x14 | RW | `TOTAL_READS` **本次任务实际记录数**（含补零尾批；2026-08-16 起 PS 下发 `conn->total_reads_received`，不再用 108,000 宏） |
| 0x18 / 0x24 / 0x2C / 0x38 | R | 调试：状态计数 / 写计数 / 错误标志 / 最后 RRESP |
| 0x30 | RW | `SCORE_MIN` 比对分阈值（2026-08-16 新增，D1 方案B）：`score < SCORE_MIN` 的记录在解析后直接跳过、不投票，补零记录（score=0）随之丢弃。复位默认 0=不过滤。PS 固定写 `VOTER_SCORE_MIN=67`（与 `stage2_expect.hex` 的生成阈值 `int(0.45×150)` 严格一致）。注意实施计划原写 0x18，但 0x18 已被 DBG_STATE 占用 |

### 3.3 Desparsification Decoder — `0x43C1_0000`

| 偏移 | 含义 |
| --- | --- |
| 0x00 | `IN_ADDR` |
| 0x04 | `IN_BEATS`（1,266） |
| 0x08 | `OUT_ADDR` |
| 0x0C | `OUT_BEATS`（1,013） |
| 0x10 | `START`（写 1 启动） |
| 0x18 | `STATUS`：[0]=idle，[1]=done |

> ⚠️ `bd.tcl` 注释把 Voter 与 Decoder 的地址写反了；以 XSA 内 `design_1.hwh` 为准。

## 4. DDR 布局（`sw/app/echo.h`，按 108,000 条读段预留）

> **实物 DDR（2026-08-29 更正）**：目标 ZYNQ ECO(R6) 板为**单颗 16 bit
> `MT41J256M16HA-125`，总容量 512 MiB**（不是此前 PS7 配置里的 32 bit 双颗）。
> 总容量不变，故**下表地址布局无需改动**，最高用到约 294 MiB，远在容量内。
> 变化的只有 DDR 峰值带宽（约 4.3 GB/s → 约 2.1 GB/s），对本流水线无实质影响。
> 详见 `docs/16-board-zynq-eco-7010.md`。


> 2026-08-16 起，cache flush/invalidate 与 Voter 配置均按**本次任务实际条数**计算
> （`sw/app/ddr_layout.h`，主机可测，见 `tools/test_ddr_layout.c`）；下表尺寸是
> 预留容量上限，不是运行时用量。另注意 `TOTAL_READS=108000` 本身不是 64 的倍数
> （108000 = 64×1687+32），容量内最大的合法条数是 107,968。

| 区间 | 用途 | 大小 |
| --- | --- | --- |
| `0x1000_0000` | 原始打包水印 | `MAX_WATERMARK_SIZE = 10,240 B`；R0.83 逻辑数据 10,125 B，客户端传输 10,128 B |
| `0x1004_0000` | 水印区域展开区 | 50 × 957 × 4 B = 191,400 B；低 2 bit 为一个 DNA 符号 |
| `0x1010_0000` | 读段原始数据 | 108,000 × 40 B = 4.32 MB |
| `0x1060_0000` | Stage1 输出 | 108,000 × 48 B = 5.184 MB |
| `0x1100_0000` | Stage2 输出 | 1,266 × 8 B = 10,128 B |
| `0x1110_0000` | Stage3 输出 | 1,013 × 8 B = 8,104 B |
| `0x1180_0000` | DMA TX BD | 2,048 × 64 B |
| `0x1190_0000` | DMA RX BD | 1,024 × 64 B |

程序自身在 `0x0010_0000` 起（`sw/linker/lscript.ld`）。
Stage1 输出直接作为 Stage2 输入、Stage2 输出直接作为 Stage3 输入，没有中间重打包。

## 5. 一次运行的 PS 控制流（`echo.c`）

0. `process_post()` 入口校验（2026-08-16 起）：实际条数非零、为 64 的整数倍（C2）、
   经 `ddr_layout_validate()` 按实际条数确认读段区 / Stage1 输出区不越界（C3），
   任一不满足回 `PKT_ERROR` 且不启动流水线。
1. `PIPE_WM_PREP` / `PIPE_WM_TX` / `PIPE_WM_WAIT`：把原始位平面水印展开为 50 个重叠区域；逐区域写
   `reg1=wm_sel` → 置 `reg0=preload` → DMA 957 个 32-bit 符号 → 清 preload。
2. `PIPE_RX_PREP`：按**实际收到的条数**提交 S2MM BD（`total_reads × 48 B`）
3. `PIPE_TX_PREFILL` / `PIPE_START_IP`：预填一帧（64 条）→ 写 `reg0=0x01` 启动
4. `PIPE_TX_STREAM`：边回收 BD 边继续提交，直到 TX/RX 都完成
5. `PIPE_VOTER_*`：按实际条数 invalidate cache → 配置 Voter 寄存器
   （含 `SCORE_MIN=67`）→ 回读校验 → start → 轮询 done
6. `PIPE_DONE_STAGE2`：invalidate Voter 输出 → `apply_watermark_differential()` 对 10,125 B 做
   LSB-first 逐字节 XOR → flush 回 DDR；Stage2 输出已有黄金 RTL 判据背书
   （`run_sim.sh stage2`），整链端到端仍待上板。
7. `PIPE_DEC_*`：配置 Decoder → start → 轮询 done → 校验写入拍数
8. `send_result()`：invalidate → 通过 TCP 发 8,100 B
