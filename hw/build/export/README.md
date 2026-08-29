# 2026-08-29 可上板交付制品（ZYNQ ECO R6，16 bit DDR）

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
| `dna_lwip_app_ddr16.elf` | 与新 XSA、bitstream 匹配的应用固件 |
| `reports/` | 完整实现及四个关键 RTL 核的时序、资源报告 |
| `SHA256SUMS` | 上述文件的 SHA-256 清单 |

`hardware.xsa` 是仓库原有历史 XSA，只为保留历史而存在，**不属于本次可上板构建对**，
且其 DDR 配置与本板不符，禁止使用。

> 上一版按旧 DDR 配置构建的 `dna_lwip_app_board_20260816.elf` 已从本目录移除
> （Git 历史中仍可取回），以免误烧。对应的 `sw/boot/dna_board_20260816.bif` 同样作废，
> 现用 `sw/boot/dna_board_ddr16.bif`。

## 本次重建的验证

- Vivado 综合 / 实现 0 error，100 MHz 收敛：**WNS +0.145 ns**（与修正前一致，
  印证 PL 侧不受 DDR 配置影响）。
- 新 XSA 内 `PCW_UIPARAM_DDR_BUS_WIDTH = 16 Bit`、
  `PCW_UIPARAM_DDR_PARTNO = MT41J256M16 RE-125`、`DEVICE_CAPACITY = 4096 MBits`。
- **启动初始化代码已确认改变**：`ps7_init_gpl.c` 中 `reg_ddrc_data_bus_width`
  由 `0x0`（32 bit）变为 `0x1`（16 bit），即 `0XF8006000[3:2]` 由 `0x0` 变为 `0x1`；
  DDR 初始化数据段共 160 行差异。这证明修正确实传播到了 FSBL 的 DDR 初始化，
  而不只是停留在工程配置里。
- BD 地址图与修正前逐行一致，DDR 段仍为 `0x00000000 + 0x20000000`（512 MiB），
  因此 `sw/app/echo.h` 的 DDR 布局无需改动。

`bootgen` 会给出一条 `Partition top_bd_wrapper.bit.0 range is overlapped with
partition dna_lwip_app_ddr16.elf.0 memory range` 的 WARNING，与本设计既有的分区布局有关，
不是本次改动引入的。

## 复核

```bash
cd hw/build/export
sha256sum -c SHA256SUMS

cd ../../..
/tools/Xilinx/Vitis/2022.2/bin/bootgen \
  -image sw/boot/dna_board_ddr16.bif \
  -arch zynq -o /tmp/BOOT-rebuilt.bin -w on
cmp /tmp/BOOT-rebuilt.bin hw/build/export/BOOT.bin
```

完整重建：

```bash
vivado -mode batch -source hw/scripts/build.tcl
xsct sw/scripts/create_vitis.tcl -tclargs \
    xsa=$PWD/hw/build/export/dna_accel.xsa ws=$PWD/sw/workspace \
    plat=dna_platform_ddr16 app=dna_lwip_app_ddr16
```

## 边界

**构建成功不代表板端端到端正确。** 本次只保证制品与实物 DDR 配置一致。
DDR 板级走线延迟（`PCW_UIPARAM_DDR_BOARD_DELAY*`）仍是从历史板卡继承的 `0.25`，
ECO 资料未给出该参数——若上板 DDR 自检不过，优先怀疑此处（见 `docs/16` §5）。

最终验收仍是 FPGA 真实回传经 LDPC 后图片 SHA-256 等于
`fcd0cf90bd680e7bbdc203e3398119504da0897acac9e2117008b4efb6b1f2c3`。

首次上板顺序见 `docs/16-board-zynq-eco-7010.md` §6：**先用官方 LED 例程冒烟，
再下载本目录制品**；首次一律用 JTAG 模式（SW1 = `00`），不写 QSPI、不动 SD 卡。
