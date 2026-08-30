# 2026-08-30 可上板交付制品（ZYNQ ECO R6，16 bit DDR + B20/B23/B24/B25/B26/B27 修复）

本目录是与当前 `main` 的 RTL / PS 固件匹配、且**按目标板 ZYNQ ECO(R6) 实物 DDR 配置**
重建的最小完整交付集。板级基准见 `docs/16-board-zynq-eco-7010.md`。

> **本次重建的原因**：2026-08-29 之前的制品是按 32 bit 双颗 `MT41J128M16` 的 DDR 配置
> 生成的，而实物 ECO 板只有一颗 16 bit 的 `MT41J256M16HA-125`。板卡硬件规格说明书明确写着
> 「配置 DDR3 必须是 16 位，默认配置 32 位，如果不更改不能运行」。
> 追溯发现：`bd.tcl` 的 DDR 参数源自只读历史快照 `design_2_wrapper.xsa`，
> 而该 XSA 自身就是 32 bit 双颗配置，**属于另一块板**。详见 `docs/16` §3。

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

`hardware.xsa` 是仓库原有历史 XSA，只为保留历史而存在，**不属于本次可上板构建对**，
且其 DDR 配置与本板不符，禁止使用。

> 历史上按旧配置构建的 ELF（`dna_lwip_app_board_20260816.elf` 为 32 bit DDR 版、
> `dna_lwip_app_ddr16.elf` 为 B20 修复前版、`dna_lwip_app_b20.elf`、`dna_lwip_app_b25.elf`）
> 均已从本目录移除（Git 历史中仍可取回），以免误烧。
> 对应的 `dna_board_20260816.bif` / `dna_board_ddr16.bif` / `dna_board_b25.bif` 同样作废，
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
