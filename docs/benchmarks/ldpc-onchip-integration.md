# 片上 LDPC：L6 集成（硬件 IP + PS 侧流程，2026-10-14）

L6 的目标是把已验的 p=1 译码器**接进整机数据通路**，并且**不动任何既有判据**。
结论：**硬件侧整机 route 通过（WNS +0.334 ns），软件侧可构建、可自检**；
**未上板**——L7 是唯一能判定「板上真的跑通」的一步。

## 0. 集成方式：为什么它能不扰动判据

结果缓冲里那 8,100 B 就是 **64,800 bit 的 LDPC 码字估计**（1 bit/bit）。
主机侧后续流程（`clients/python/ldpc_pipeline.py`）拿它去做 LDPC 重建。
片上译码器现在插在 Stage3 与 `PIPE_SEND_RESULT` 之间，**就地写回同一个缓冲**：

| 情形 | 板端行为 | 主机看到 |
| --- | --- | --- |
| 收敛 | 写回纠正后的码字 | 合法码字，主机 LDPC 立即收敛 ⇒ 同一载荷 |
| 不收敛 / 报错 / 超时 | **一个字节都不动** | 与今天**逐位相同** |

⇒ 协议、结果长度（8,100 B）、主机流程、**G3 判据 SHA 的验收方式**全部不变。
不收敛路径保持原样这一条是刻意的：新增模块**不得**让原本通过的行为变差。

## 1. 硬件侧

- IP：`hw/ip/ldpc_decoder_1_0/`（`component.xml` + `hdl/` + `xgui/` + `data/`），基地址 **0x43C30000**。
  - `hdl/ldpc_decoder_p1.v` 是**唯一权威副本**（原 `hw/experimental/` 下那份已删除，见 commit `ce4811e`）；
  - `hdl/ldpc_decoder_v1_0.v` 为 AXI4-Lite 包装；`data/` 为该 IP 自带的 B_t 表。
- BD：`hw/scripts/bd.tcl` 的 `ic_lite` 由 4 端口扩到 5，新增 `ldpc_decoder_0`，
  `assign_bd_address -offset 0x43C30000 -range 0x10000 -force`；
  既有四个地址（0x40400000 / 0x43C00000 / 0x43C10000 / 0x43C20000）未动。

寄存器（软件按此实现，见 `sw/app/ldpc_onchip.h` 与 IP 的 `xgui`）：

| 偏移 | 名称 | 说明 |
| --- | --- | --- |
| 0x00 | CONTROL | bit0 启动，bit1 复位（单次脉冲，同时清 sticky done） |
| 0x04 | STATUS | bit0 busy，bit1 done，bit2 converged，bit3 error，bit4 loading，bit5 readback，[15:8] 有符号迭代轮数 |
| 0x08 / 0x0C | LOAD_ADDR / LOAD_DATA | 装载字地址与数据；**写数据寄存器的响应在硬件完成该字后返回** |
| 0x10 / 0x14 | RESULT_ADDR / RESULT_DATA | 读回字地址与数据；**读数据寄存器触发硬件同步读回** |

### 1.1 位序（本层最容易被静默写错的一处）

结果缓冲是**每字节 LSB 先**——核验自 `clients/python/fast_readout.py` 的
`fast_unpack_result` 用 `np.unpackbits(raw, bitorder="little")`。
包装器按同一路序在字的**同一 bit 位置**进出：

```
码字 bit k  ⇔  字 (k/32) 的 bit (k%32)
```

⚠️ `native_ldpc.py` 的 `bits_to_bytes` 是 **MSB 先**，那是**载荷输出**那条路，两条路不能混。
⇒ 8,100 B = 2,025 个完整 32 位字，无余字节。

### 1.2 整机时序与资源（**布线后**，`SYNTH_IMPL=1`）

| 项 | 值 |
| --- | ---: |
| **整机 WNS** | **+0.334 ns**（0 个 setup 失败端点 / 92,521） |
| WHS | +0.036 ns（0 个 hold 失败端点） |
| WPWS | +3.000 ns（0 个） |
| 整机 LUT | 36,600（LUTRAM 456、SRL 223） |
| 整机 FF | 37,606 |
| 整机 RAMB36 | 89（另 RAMB18 ×2） |
| 整机 DSP | 6 |
| — 其中 `ldpc_decoder_0` | **855 LUT / 789 FF / 41 RAMB36 / 1 DSP** |

留证：`hw/build/bkb220-p16-k2-ldpc-20261014T102111Z-board-migrate/reports/{timing,util}.rpt`
（`Design State: Physopt postRoute`）。

**并入代价**：整机 WNS 由 K=2 冻结版的 +0.313 ns 变到 **+0.334 ns**（同为正，
差异在布线噪声量级内）。这与 L4 OOC 的 +0.444 ns 不是一回事——
**OOC 余量不等于整机余量**，这里报的是整机 route 后的数字。

⚠️ 但仍有一条**未经实测的假设**：BD 里那个 100 MHz 时钟域现在是 100 MHz 约束下的
单域设计，LDPC IP 与其时钟/复位（`clk_wiz_0/clk_out1` 与 `rst_ps/peripheral_aresetn`）
同域——这一条由本次 route 覆盖；**跨域不存在**，因为本 IP 没有独立时钟。

## 2. 软件侧

新增 [src/sw/app/ldpc_onchip.c](../../src/sw/app/ldpc_onchip.c)（201 行）与 `.h`；
`pipeline.h` 加三个状态 `PIPE_LDPC_PREP / _RUN / _READBACK`；
`stage3_decoder.c` 的收尾由 `PIPE_SEND_RESULT` 改指向 `PIPE_LDPC_PREP`；
`echo.c` 的完成判定随之由 `PIPE_DONE_STAGE3` 改为 `PIPE_SEND_RESULT`
（三条 LDPC 出口**都**落在 `PIPE_SEND_RESULT`，无死路）。

- **装载**：`Xil_DCacheInvalidateRange` → 按 32 字/步推入 2,025 字 → 发 START；
- **轮询**：非阻塞，`done && 无 busy/loading/readback && converged && !error` 才进读回；
- **读回**：32 字/步，读完 `Xil_DCacheFlushRange` 再进 `PIPE_SEND_RESULT`；
- **兜底**：`error`、`done && !converged`、或 120 s 超时 ⇒ 保留 Stage3 原码字，
  打印 `[LDPC] converged=0 …保留 Stage3 原码字` 后照常进 `PIPE_SEND_RESULT`；
- BSP 宏 `XPAR_LDPC_DECODER_0_BASEADDR` 在**新 XSA 的 BSP 里实际生成**（= 0x43C30000），
  源码里有 `#error` 守卫，宏缺失时**编译期**就失败，不会静默跑错地址。

### 2.1 构建与自检（**不等于上板通过**）

软件包：`hw/build/bkb220-p16-k2-ldpc-sw-20261014T104331Z-board-migrate/`。

- XSCT 2022.2 由**新 XSA** 生成平台 / BSP / FSBL；`TCP_WND=32768` 回读确认；
- `BOOT.bin` 由 Bootgen 生成，readback 含 FSBL + bit + 应用 ELF；
- **`SHA256SUMS` 自检 2,958/2,958 通过**；`sw/app` 与 workspace 同名文件逐字节相同。

两处必须一起说的偏差：

1. **`app create` 没走通**：XSCT 在 SDK channel 阶段返回
   `Socket create error. Operation not permitted`（本机限制，参考软件包也记录过同一现象）。
   应用改用**同一安装树的 ARM GCC 11.2.0** 直接编译并链接新 BSP 的 `libxil.a` / `liblwip4.a`，
   结果 `APP_BUILD_PASS`。⇒ **产物是同一工具链的**，但 Vitis 托管式 app 工程那条路**没有**在本包内验证。
2. **`create_vitis.tcl` 改了一处**：新空 workspace 首次运行时 `lwipopts.h` 还不存在，
   改为先 `platform generate` 物化 BSP 头文件、再设 `TCP_WND` 并重新生成。
   这是脚本在新 workspace 下的**必需**步骤，不是可选项。

## 3. ⚠️ 边界（引用本页时必须一起说）

1. **未上板。** 编译通过、包自检通过、整机 route 通过——**都不代表 LDPC 在板上跑通**。
   唯一判定在 L7。
2. **AXI 边界上的位序没有被仿真覆盖。** L4 仿真是**核**级（`tb_ldpc_decoder_p1.v` 直接喂比特），
   `ldpc_decoder_v1_0.v` 这层包装器**没有 testbench**。字节序（PS 侧小端拼字）与
   位序（字内 LSB 先）在**边界上**是否真的对齐，只有 G3 回传能判。
   ⇒ 若 L7 的 SHA 不符，**第一优先怀疑这里**，而不是算法。
3. **迭代轮数在板上没有独立计数手段**，只能读 STATUS[15:8]；L4 的周期数是仿真数，
   不是板端数。
4. **不收敛时板端行为故意与今天相同**，所以那 8 个 challenge 例**不会因此变好**
   （它们本来就是硬判决不收敛）。本模块的价值是集成度与「让主机侧少做一遍」，
   **不是**把失败的例子救回来。
5. 软件包是在**去重之前**构建的，其 `reports/check_repo_hygiene.log` 记的重复件
   （`hw/experimental/ldpc_decoder_p1.v`）**现已由 commit `ce4811e` 修掉**；
   该日志是**历史留证**，不代表当前工作树状态。

## 4. L7 上板判读（按此顺序，先看日志再看 SHA）

1. UART 是否出现 `[LDPC] loading 8100 bytes as 2025 LSB-first words`
   与终态 `[LDPC] converged=… iterations=…`；
2. 若**没有**终态日志，读 STATUS（0x43C30004）按位判断卡在哪：
   bit0/4/5 说明还在装/算/读回，bit3 是 error，bit2=1 但没进读回说明是轮询条件不满足；
3. 若报了收敛但主机载荷 SHA **不符**：优先逐字节比对 8,100 B 读回缓冲与
   LSB-first 位序（§1.1），**不要**先去怀疑译码算法；
4. 若**未收敛**：输出应保持 Stage3 原结果 ⇒ 主机行为应与 L6 之前**逐位相同**；
5. **回归判据**：G3 载荷 SHA 仍须是
   `fcd0cf90bd680e7bbdc203e3398119504da0897acac9e2117008b4efb6b1f2c3`；
   同时 K=2 板端数值要复测，确认 Stage1 未回退（交接文档的停止条件）。
