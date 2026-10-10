# 09 · 板级配置、构建与验收

## 1. 唯一板级基线

目标板为 ZYNQ ECO(R6)，当前 DDR 为单颗 16 bit `MT41J256M16HA-125`；不得用历史 32 bit 双颗 XSA 回退配置。详细只读板卡资料位于 `docs/board/zynq-eco-7010/`。

## 2. 构建交付集

```text
hw/build/export/top_bd_wrapper.bit
hw/build/export/dna_accel.xsa
hw/build/export/dna_lwip_app_*.elf
hw/build/export/BOOT.bin
hw/build/export/SHA256SUMS
```

RTL 或固件变化后必须整套重建。BOOT.bin 必须包含 FSBL、bitstream 和 ELF，并用 Bootgen readback 与哈希核对。

## 3. 上板顺序

1. 绑定仓库并确认 `main...origin/main=0/0`；
2. 核验器件、PS7、DDR、MIO、时钟和 XDC；
3. Vivado 实现并检查 WNS/WHS、资源和错误；
4. XSCT/Vitis 重建 ELF；
5. Bootgen 打包并校验；
6. 烧录；
7. `CAPS` 就绪探针；
8. `run_g3.sh` 真实协议；
9. LDPC 解码、图片哈希、四级 DDR 取证；
10. 归档运行 ID 和摘要。

## 4. 验收边界

当前已闭环的是 SE150/SE250 指定 profile 和已记录规模。功耗、任意 payload、任意测序错误率和新开发板迁移，必须有独立证据后才能扩大结论。
