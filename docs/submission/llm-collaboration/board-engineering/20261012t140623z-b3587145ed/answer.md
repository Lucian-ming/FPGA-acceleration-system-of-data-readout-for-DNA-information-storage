> 脱敏副本，原件 `20261012T140623Z-b3587145ed/{prompt.txt,answer.md}`。本机绝对路径、邮箱、凭据形模式及非白名单私网 IP 已替换；除脱敏与换行规范化外保留原文。

## P4 硬件重建：PASS

完整命令退出码 **0**，route、bitstream 与 XSA 均已生成：

```bash
VIVADO_ROOT=<本机路径> bash tools/run_vivado_build.sh \
  board=bkb220 part_name=xc7z020clg400-2 clk_mhz=100 \
  stage1_p_ways=4 stage1_pipe_tree=0 \
  build_dir=hw/build/bkb220-p4-enet0-rebuild-20261012T140800Z-board-migrate/build \
  export_dir=hw/build/bkb220-p4-enet0-rebuild-20261012T140800Z-board-migrate/export \
  report_dir=hw/build/bkb220-p4-enet0-rebuild-20261012T140800Z-board-migrate/reports
```

实测 post-route：WNS **+0.680 ns**、WHS **+0.036 ns**、TNS/THS 均为 **0**，setup/hold 失败端点均为 **0**；`clk_fpga_0` 为 **100.000 MHz**。资源为 15,447 LUT、16,910 FF、44 RAMB36、2 RAMB18、3 DSP。DRC 为 **0 errors、58 warnings、3 advisories**；警告详情保留在构建日志中。

[硬件构建摘要](<<仓库根目录>/hw/build/bkb220-p4-enet0-rebuild-20261012T140800Z-board-migrate/reports/hardware_build_summary.md>)

## PS7 ENET0 MIO 核心门禁：PASS

`export/ps7_init.tcl` 从新 XSA 解出，并与 Vivado 生成源逐字节一致。以下为该文件 `grep -n` 的实际命中：

```text
126:proc ps7_mio_init_data_3_0 {} {
151:    mask_write 0XF8000740 0x00003FFF 0x00001202
152:    mask_write 0XF8000744 0x00003FFF 0x00001202
153:    mask_write 0XF8000748 0x00003FFF 0x00001202
154:    mask_write 0XF800074C 0x00003FFF 0x00001202
155:    mask_write 0XF8000750 0x00003FFF 0x00001202
156:    mask_write 0XF8000754 0x00003FFF 0x00001202
157:    mask_write 0XF8000758 0x00003FFF 0x00001203
158:    mask_write 0XF800075C 0x00003FFF 0x00001203
159:    mask_write 0XF8000760 0x00003FFF 0x00001203
160:    mask_write 0XF8000764 0x00003FFF 0x00001203
161:    mask_write 0XF8000768 0x00003FFF 0x00001203
162:    mask_write 0XF800076C 0x00003FFF 0x00001203
181:    mask_write 0XF80007D0 0x00003FFF 0x00001280
182:    mask_write 0XF80007D4 0x00003FFF 0x00001280
726:            ps7_mio_init_data_3_0
```

MIO16–27 的 12 个寄存器均有配置；MIO52/53 两行写入值均为 `0x1280`。

## 同源软件包：PASS

软件包目录：`hw/build/bkb220-p4-enet0-software-20261012T140800Z-board-migrate/`。BSP 为 Vitis 2022.2 standalone，安装树实际提供并选用 `lwip211_v1_8`（lwIP 2.1.1）。

XSCT 的平台/BSP/FSBL生成成功，但 `app create` 因 `Socket create error. Operation not permitted` 退出 **1**。随后使用该 XSA 生成的 BSP、Vitis ARM GCC 11.2.0 和权威 `sw/app` 快照直接构建应用 ELF，退出 **0**，日志含 `APP_BUILD_PASS`。BSP、FSBL make、BOOT.bin 生成与 Bootgen readback 均退出 **0**。BOOT.bin 有两条 partition 地址范围重叠 warning，已保留在日志中。

最终 `sha256sum -c SHA256SUMS`：**59 项全 OK**。`g3_artifacts.py` 预检退出 **0**，识别为 `bkb220 / xc7z020clg400-2 / P4 4/0 / legacy=false`，七项生产参数匹配。

| 制品 | SHA-256 |
|---|---|
| `export/top_bd_wrapper.bit` | `6ea4c090b6bd0c1bb11f581d1c7f794ccb212aaeba190f0c491897f96a5103d2` |
| `export/dna_accel.xsa` | `ed73b6f440ef8594dd28b4d192b520e0c7357076064de767398f7870aeea913b` |
| `export/ps7_init.tcl` | `2f80e045cb18d7c37d5144bf0a819cd8fd42d09a622fca164f2ef7b007b6c81f` |
| `export/dna_lwip_app.elf` | `37ca544ecd72db7d8667db487060918b590316d18d851064a47bd2b41ce83688` |
| `export/fsbl.elf` | `6c03cff4945aa052f50b877ae11904971aaaae561f522ea20789083ba5db9b7d` |
| `export/BOOT.bin` | `3e9f75fd236300a24a3aab889832cd9d2e0a76c4cd1289337e69b18f2799a0df` |

[软件构建摘要](<<仓库根目录>/hw/build/bkb220-p4-enet0-software-20261012T140800Z-board-migrate/reports/software_build_summary.md>)

## main 板测移交

bit、PS7 初始化与应用 ELF 位于新软件包的 `export/` 目录；G3 使用该包作为 `--artifact-dir`。UART 判据是日志出现 **`autonegotiation complete`**，并且不再出现 **`Auto negotiation error`**。

若仍失败，先确认实际下载/执行的是新包的 `ps7_init.tcl`，再检查 MIO52/53 生效情况及驱动 `detect_phy` 是否识别 PHY、最终使用的 PHY 地址；随后读取 PHY 状态寄存器核对协商状态。

**本轮未触板，F4 G3 与 PHY 自协商修复均未测，不能宣称板端已修好。** 未修改 `sw/app` 或 docs 根目录 01～09；工作树保持 `main...origin/main`，仓库根无 Vivado 日志残留。
