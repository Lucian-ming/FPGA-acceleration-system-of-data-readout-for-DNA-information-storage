# 2026-08-16 可上板交付制品

本目录保存与 `refactor/three-end-audit-20260816` 当前 RTL/PS 固件匹配的最小完整交付集。
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
