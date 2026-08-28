# 2026-08-16 交付制品

> ## ⛔ 2026-08-29：本目录制品**不能烧录到目标 ZYNQ ECO(R6) 开发板**
>
> 这些制品是按 **32 bit 双颗 `MT41J128M16`** 的 DDR 配置生成的，而实物 ECO 板只有
> **一颗 16 bit 的 `MT41J256M16HA-125`**。板卡硬件规格说明书明确写着「配置 DDR3 必须是
> 16 位，默认配置 32 位，如果不更改不能运行」——烧上去 DDR 训练会失败，ARM 起不来，
> 连串口输出都不会有。
>
> 根因：`bd.tcl` 的 DDR 参数源自只读历史快照 `design_2_wrapper.xsa`，而该 XSA 自身
> 就是 32 bit 双颗配置，**属于另一块板**。详见 `docs/16-board-zynq-eco-7010.md` §3。
>
> `hw/scripts/bd.tcl` 已于 2026-08-29 修正为 16 bit + `MT41J256M16 RE-125`，
> 但**本目录尚未按新配置重建**。在重建并更新本文件之前，下面的说明只反映历史构建，
> 不代表可上板状态。PL 侧（RTL、三个 IP、时序结论）不受该修正影响。


本目录保存与 2026-08-21 主分支当前 RTL/PS 固件匹配的最小完整交付集。该实现最初在
`refactor/three-end-audit-20260816` 完成审查，核查通过后已快进纳入 `main`。
Vivado/Vitis 缓存和重复平台目录不纳入 Git；这里的独立启动组件来自同一次构建，且按
`sw/boot/dna_board_20260816.bif` 重新执行 Bootgen 后可逐字节复现 `BOOT.bin`。

## 当前交付集

| 文件 | 用途 |
| --- | --- |
| `BOOT.bin` | 可直接烧录的 Zynq 启动镜像，分区顺序为 FSBL、bitstream、应用 ELF |
| `dna_accel.xsa` | 与当前 bitstream 同源的硬件平台 |
| `top_bd_wrapper.bit` | 独立 PL bitstream |
| `fsbl.elf` | 生成 `BOOT.bin` 使用的 FSBL；保留原 basename 以复现分区头 |
| `dna_lwip_app_board_20260816.elf` | 与 XSA、bitstream 匹配的应用固件 |
| `reports/` | 完整实现及四个关键 RTL 核的时序、资源报告 |
| `SHA256SUMS` | 上述文件的 SHA-256 清单 |

`hardware.xsa` 是仓库原有历史 XSA，只为保留历史而存在，不属于本次可上板构建对。
构建成功不代表板端端到端正确；最终验收仍是 FPGA 真实回传经 LDPC 后图片 SHA-256
等于 `fcd0cf90bd680e7b...b6b1f2c3`。

## 复核

```bash
cd hw/build/export
sha256sum -c SHA256SUMS

cd ../../..
/tools/Xilinx/Vitis/2022.2/bin/bootgen \
  -image sw/boot/dna_board_20260816.bif \
  -arch zynq -o /tmp/BOOT-rebuilt.bin -w on
cmp /tmp/BOOT-rebuilt.bin hw/build/export/BOOT.bin
```
