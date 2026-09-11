# 可上板交付制品（ZYNQ ECO R6，16 bit DDR，4-way Stage1 + P7 周期计数器 + S-5 瘦身）

本目录是与当前 `main` 的 RTL / PS 固件匹配、且**按目标板 ZYNQ ECO(R6) 实物 DDR 配置**
重建的最小完整交付集。

## 2026-09-11 重建：4-way Stage1 + P7 周期计数器 + S-5 热清理

本次重建将 **4-way Stage1 比对加速核**、**P7 独立硬件周期计数器**（Voter 0x40~0x50、Decoder 0x14~0x24）与 **S-5 固件热清理**（清除 7 个模板文件）合并落地：

- **实现收敛**：`Performance_ExplorePostRoutePhysOpt` 下 **WNS = +0.167 ns @ 100 MHz**，0 failing endpoint，0 error / 0 critical warning；
- **资源利用**：Total LUTs 15,709 (89.2%)，FFs 17,198 (48.9%)，RAMB36 44 块，DSPs 3 块，安全适配 XC7Z010CLG400-1；
- **固件瘦身**：移除 7 个未引用的 Xilinx 模板源文件（1,292 行，占 20.3%），ELF 机器码完全同源且大小自洽；
- **仿真覆盖**：`tools/run_sim.sh` 16/16 全 PASS，TB 精确验证 Voter（2,853,481 周期，分项守恒等式成立）与 Decoder（2,053 周期）。

## 当前交付集

| 文件 | 用途 |
| --- | --- |
| `BOOT.bin` | 可烧录的 Zynq 启动镜像，分区顺序为 FSBL、bitstream、应用 ELF |
| `dna_accel.xsa` | 与当前 bitstream 同源的硬件平台（**16 bit DDR**） |
| `top_bd_wrapper.bit` | 独立 PL bitstream |
| `fsbl.elf` | 生成 `BOOT.bin` 使用的 FSBL，按新 XSA 重建 |
| `dna_lwip_app_b27.elf` | 与新 XSA、bitstream 匹配的应用固件（含 B21/B22/B27 固件修复） |
| `reports/` | 完整实现及四个关键 RTL 核的时序、资源报告 |
| `SHA256SUMS` | 上述文件的 SHA-256 清单 |

`hardware.xsa`（与根目录原 `design_2_wrapper.xsa` 逐字节相同）已于 2026-09-11 依据代码卫生 §5 第 2 条（逐字节重复）与第 3 条（已被 `dna_accel.xsa` 取代）从本目录及根目录删除。其 DDR 配置与本板不符（32 bit 双颗），历史可由 Git 取回（SHA-256 `79c64736b081720c9de37e608ab930b879be93c4609f55ad729c010b42e6eb33`）。

> 历史上按旧配置构建的 ELF（`dna_lwip_app_board_20260816.elf` 为 32 bit DDR 版、
> `dna_lwip_app_ddr16.elf` 为 B20 修复前版、`dna_lwip_app_b20.elf`、`dna_lwip_app_b25.elf`）
> 均已从本目录移除（Git 历史中仍可取回），以免误烧。
> 对应的 `dna_board_20260816.bif` 已于 2026-09-11 依据代码卫生 §5 第 3 条从 `sw/boot/` 删除（已被 `sw/boot/dna_board_b27.bif` 取代）；
> `dna_board_ddr16.bif` / `dna_board_b25.bif` 同样作废，
> **现用 `sw/boot/dna_board_b27.bif`**。

## 2026-08-30 重建：B26 + B27 修复，且**已上板闭环**

本次重建把两个 RTL 缺陷一起烤进同一颗 bit：

| 编号 | 缺陷 | IP / 流水级 |
| --- | --- | --- |
| B26 | 入口 FIFO 两级同步读、引擎晚一拍采样 → Stage1 结果整体错位一条读段 | `Dna_accelerator_core_v1_0.v` / Stage1 |
| B27 | AXI-Lite 写 START 寄存器时不看 `wdata[0]`，固件启动后 100 us 又写了一次 START=0，把跑到一半的任务重启；重启不取消已发出的 AXI 读突发，残留 R 拍被当成新任务输入流的开头，整条输入旋转 126 拍 | `desparsification_decoder_v1_0.v` / Stage3 |

两者在不同 IP、不同流水级，而每一级都有黄金向量可以单独归因，所以合并成一次综合。

- 实现收敛：**WNS +0.088 ns / WHS +0.016 ns**，0 failing endpoint，0 error / 0 critical warning。
- **第五次上板（2026-08-30）G3 闭环**：`first.py --limit 2048 --orient both --score-min 67`
  回传 8,100 B，经 `tools/ldpc_decode.py` 起始失败校验 332、5 轮收敛，
  重建 JPEG 的 SHA-256 = `fcd0cf90bd680e7bbdc203e3398119504da0897acac9e2117008b4efb6b1f2c3`，
  与判据逐位相同。
- 四级 DDR 只读留证（`tools/board_stage_check.py`）：展开水印 47,850/47,850、
  Stage1 码字 4,096/4,096（B26 错位消失）、Stage2⊕水印 误码 0/81,000、
  **Stage3 误码 0/64,800**（上一版是 49.47%）。
- 闭环范围仅限 SE150 / 2,048 条源读段 / `--orient both` / `SCORE_MIN=67` 这一组参数，
  SE250、全量 51,781 条、二次任务均未验证。详见 `docs/03-status.md`「第五次上板」一节。

## 本次重建的验证

- Vivado 综合 / 实现 0 error，100 MHz 收敛：**WNS +0.266 ns**
  （B20 修复前为 +0.145 ns，修复后反而更宽裕；拆分突发只增加了一个减法与一次比较）。
- 新 XSA 内 `PCW_UIPARAM_DDR_BUS_WIDTH = 16 Bit`、
  `PCW_UIPARAM_DDR_PARTNO = MT41J256M16 RE-125`、`DEVICE_CAPACITY = 4096 MBits`。
- **启动初始化代码已确认改变**：`ps7_init_gpl.c` 中 `reg_ddrc_data_bus_width`
  由 `0x0`（32 bit）变为 `0x1`（16 bit），即 `0XF8006000[3:2]` 由 `0x0` 变为 `0x1`；
  DDR 初始化数据段共 160 行差异。这证明修正确实传播到了 FSBL 的 DDR 初始化，
  而不只是停留在工程配置里。
- BD 地址图与修正前逐行一致，DDR 段仍为 `0x00000000 + 0x20000000`（512 MiB），
  因此 `sw/app/echo.h` 的 DDR 布局无需改动。

`bootgen` 会给出分区地址范围重叠的 WARNING（FSBL/bit/ELF 之间），
与本设计既有的分区布局有关，不是本次改动引入的。

## 本次还包含 RTL 缺陷 B20 的修复

`differential_voter_v1_0.v` 的 AXI 读突发原先固定 6 拍（`ARLEN=5`）、地址每条记录 +48 B，
会周期性跨越 4 KB 页边界，违反 AXI 规范 A3.4.1（4,096 条记录中 32 次）。
已改为跨页时拆成两笔突发。验证：`run_sim.sh` 11/11、`run_xsim.sh` 6/6、
M2 完整串联全链 PASS（图片哈希不变）、BD-3ext 的 Voter 与 Decoder 均逐位通过且零协议违规。
详见 `docs/15-m3-bd-simulation-2026-08-29.md` §6.6。

## 复核

```bash
cd hw/build/export
sha256sum -c SHA256SUMS

cd ../../..
/tools/Xilinx/Vitis/2022.2/bin/bootgen \
  -image sw/boot/dna_board_b25.bif \
  -arch zynq -o /tmp/BOOT-rebuilt.bin -w on
cmp /tmp/BOOT-rebuilt.bin hw/build/export/BOOT.bin
```

完整重建：

```bash
vivado -mode batch -source hw/scripts/build.tcl
xsct sw/scripts/create_vitis.tcl -tclargs \
    xsa=$PWD/hw/build/export/dna_accel.xsa ws=$PWD/sw/workspace \
    plat=dna_platform_b25 app=dna_lwip_app_b25
```

## 本轮（2026-08-29 晚）在此基础上的修复

这套制品比上一版多了四个已定位缺陷的修复，详见 `docs/03-status.md`：

| 编号 | 位置 | 内容 | 验证状态 |
| --- | --- | --- | --- |
| B21 | `sw/app/echo.c` | RX BD 按 48 B/记录滚动补投；`reclaim_some_bd` 的 BD 环回绕 | ✅ 板上 `RX: done=4096/4096` |
| B22 | `sw/app/echo.c` | Stage3 等待循环从不读 STATUS、超时≈69 小时 | ✅ 板上回传 8,100 B |
| B23/B24 | `Dna_accelerator_core_v1_0.v`、`s2mm_pack64.v` | AXIS 结果输出级 TDATA 比 TVALID 早一拍；packer 违反 AXI-Stream；结果 FIFO 被反复 pop | ✅ 板上每包 6 拍完整、码字 4,094/4,095 对上 |
| B25 | `Dna_accelerator_core_v1_0.v` | 水印预载写地址与数据不同拍，整条水印偏一个符号 | ✅ 板上 position 偏移归零，4,009/4,096 条整条逐位正确 |

实现结果：**WNS +0.017 ns**，0 failing endpoint，0 error。
（上一版 +0.266 ns；输出级重写后时序更紧但仍收敛。）

仿真回归：`run_sim.sh` 11/11、`run_xsim.sh all` **7/7**
（新增 `result_axis`，即 `hw/sim/dna/tb_dna_result_axis.v`，覆盖此前完全没有判据的
DNA 核 AXIS 结果输出级）。

## 边界

**构建成功不代表板端端到端正确。G3 仍未闭环。**

第四次上板逐级取证的结论（XSDB 只读 DDR 与黄金向量比对）：

| 级 | 与黄金比对 | 判定 |
| --- | --- | --- |
| 展开水印 | 47,850/47,850 字相同 | ✅ |
| Stage1 输出 | 4,009/4,096 条整条逐位相同（其余为 B26 的整体错位一条读段） | ✅（除 B26） |
| Stage2 输出 ⊕ 水印 | 与 `sparse_expect.hex` 1,265/1,266 字相同，比特误码 0.01% | ✅ |
| **Stage3 输出** | 与 `stage3_expect.hex` **0/1,013 字相同，比特误码 49.46%** | ❌ **B27** |

**当前主阻塞项是 B27**：Decoder 的输入几乎全对，输出却与正确答案完全不相关，
且已排除整体位移（±64 bit / ±16 B 全搜索最好仍 49.0%）。
在图片 SHA-256 等于目标值之前，不得声称端到端正确。

本次只保证制品与实物 DDR 配置一致。
DDR 板级走线延迟（`PCW_UIPARAM_DDR_BOARD_DELAY*`）仍是从历史板卡继承的 `0.25`，
ECO 资料未给出该参数——若上板 DDR 自检不过，优先怀疑此处（见 `docs/16` §5）。

最终验收仍是 FPGA 真实回传经 LDPC 后图片 SHA-256 等于
`fcd0cf90bd680e7bbdc203e3398119504da0897acac9e2117008b4efb6b1f2c3`。

首次上板顺序见 `docs/16-board-zynq-eco-7010.md` §6：**先用官方 LED 例程冒烟，
再下载本目录制品**；首次一律用 JTAG 模式（SW1 = `00`），不写 QSPI、不动 SD 卡。

## 只改 PS 固件时怎么重建 ELF（2026-09-03 实测可复现）

上面「完整重建」那一节的参数已经过期（`plat=dna_platform_b25`、`dna_board_b25.bif`
都是上一版的名字），且改一行 C 代码没必要重跑 `platform generate`。
现有 Vitis workspace 就能增量重建，**并且逐字节可复现**：

```bash
export PATH=/tools/Xilinx/Vitis/2022.2/gnu/aarch32/lin/gcc-arm-none-eabi/bin:$PATH
cp sw/app/echo.c sw/workspace/dna_lwip_app_b27/src/echo.c      # 按需同步改动的源文件
cd sw/workspace/dna_lwip_app_b27/Debug && make all
sha256sum dna_lwip_app_b27.elf
```

**先做这个自证再信重建结果**，但**别拿整个 ELF 的 SHA-256 当自证判据** ——
这里有个坑，2026-09-04 实测踩到了：

```bash
# 把未改动的源码（例如某个提交里的 sw/app/echo.c）放进 workspace 后重建
git show <某提交>:sw/app/echo.c > sw/workspace/dna_lwip_app_b27/src/echo.c
cd sw/workspace/dna_lwip_app_b27/Debug && rm -f src/echo.o && make all
sha256sum dna_lwip_app_b27.elf      # ← 很可能**不等于** 9006d0ca…，而这不代表出错了
```

**为什么**：编译用的是 `-g3`，DWARF 行号表里存着每条语句的行号。
`40ba34f` 给 `sw/app/echo.c` 加了 **24 行纯注释**（那次的提交说明写明「只改注释、不动数值」，
因为改数值要重建 ELF 并刷新 `SHA256SUMS`），但 `export/` 里的 ELF 从此没再重建过。
于是**行号整体挪了位，调试段变了，整个文件的 SHA-256 也就变了 —— 而机器码一个字节没动**。

所以正确的自证判据是**按段比对**，只看真正会被执行的部分：

```bash
OC=/tools/Xilinx/Vitis/2022.2/gnu/aarch32/lin/gcc-arm-none-eabi/bin/arm-none-eabi-objcopy
for s in .text .data .rodata; do
  $OC -O binary --only-section=$s hw/build/export/dna_lwip_app_b27.elf /tmp/ship$s.bin
  $OC -O binary --only-section=$s <你重建出来的>.elf                   /tmp/new$s.bin
  cmp /tmp/ship$s.bin /tmp/new$s.bin && echo "$s 相同"
done
```

2026-09-04 实测：用 `a2a8067^` 的 `sw/app/echo.c` 重建出 `53352d55…`（≠ `9006d0ca…`），
但 `.text`（115,360 B）、`.data`（3,148 B）、`.rodata`（14,607 B）**三段逐字节相同**。
结论是工具链、BSP、链接脚本仍是当初出这套制品时那一套，可以放心换制品。

**顺带钉住一个事实**：`hw/build/export/` 里的 ELF 与 `sw/app/echo.c` 自 `40ba34f`
起就不是逐字节同源的，**差异纯粹是注释行号，已按上面的方法证明机器码相同**——
不是「大概只是注释吧」的推测。下次谁再发现哈希对不上，不必重新怀疑一遍。

**没做这一步就换制品，等于拿一个没校准的秤称东西。**

`BOOT.bin` 里嵌着应用 ELF，所以换了 ELF 必须一起重生成（`.bif` 用 b27 那份，不是 b25）：

```bash
/tools/Xilinx/Vitis/2022.2/bin/bootgen \
  -image sw/boot/dna_board_b27.bif -arch zynq -o hw/build/export/BOOT.bin -w on
```

同样先自证：不改 ELF 直接跑上面这条，输出必须等于
`cabaf453015315ef2bab3b1947db43f6ecc62c1d51f46a8ed93691dff3fb7a92`（2026-09-03 实测成立）。
`bootgen` 这一侧没有上面那个行号坑：它的输入就是 ELF 文件本身，输入不变输出就不变。

最后刷新清单，否则 `tools/run_g3.sh` 的「制品同源性校验」会挡住你——**那是故意的**：

```bash
cd hw/build/export && sha256sum -c SHA256SUMS      # 先看哪几行变了
# 用新哈希替换 BOOT.bin / dna_lwip_app_b27.elf 两行，再复验
```

⚠️ **换制品的时机**：工作树是多个会话共享的，`run_g3.sh` 每次烧录前都按 `SHA256SUMS`
校验同源性。在自己的板上判据跑通之前就覆盖本目录，别的会话要么烧到一份没过判据的固件、
要么直接因哈希不符停机。所以顺序是：**先在 scratchpad 里备好新制品 → 拿到板子令牌 →
覆盖 + 刷新 `SHA256SUMS` → 跑 `run_g3.sh` → 通过后立刻提交**。
