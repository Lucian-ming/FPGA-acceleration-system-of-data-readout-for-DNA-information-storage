> 脱敏副本，原件 `20261012T144034Z-6f22579588/{prompt.txt,answer.md}`。本机绝对路径、邮箱、凭据形模式及非白名单私网 IP 已替换；除脱敏与换行规范化外保留原文。

## P16 硬件构建：PASS

构建命令退出码 **0**；输出在全新目录，旧 P16 包未覆盖：

```bash
VIVADO_ROOT=<本机路径> bash tools/run_vivado_build.sh \
  board=bkb220 part_name=xc7z020clg400-2 clk_mhz=100 \
  stage1_p_ways=16 stage1_pipe_tree=1 \
  build_dir=hw/build/bkb220-p16-enet0-100mhz-20261012T144141Z-board-migrate/build \
  export_dir=hw/build/bkb220-p16-enet0-100mhz-20261012T144141Z-board-migrate/export \
  report_dir=hw/build/bkb220-p16-enet0-100mhz-20261012T144141Z-board-migrate/reports
```

route 完成，失败网为 0。最终时序为 **WNS +0.617 ns / TNS 0，WHS +0.017 ns / THS 0**；setup、hold 失败端点均为 **0/86,415**。`clk_fpga_0` 为 **100.000 MHz**。DRC 为 **0 errors、75 warnings、3 advisories**。资源占用：LUT **33,987/53,200（63.89%）**、FF **36,067/106,400（33.90%）**、BRAM tile **45/140（32.14%）**、DSP **3/220（1.36%）**。

与修复前 P16 对照：WNS、WHS、失败端点、LUT 数和 DRC errors 均一致。实测结果符合 ENET0 修复只改变 PS7 配置的预期。报告见 [timing.rpt](<仓库根目录>/hw/build/bkb220-p16-enet0-100mhz-20261012T144141Z-board-migrate/reports/timing.rpt)、[util.rpt](<仓库根目录>/hw/build/bkb220-p16-enet0-100mhz-20261012T144141Z-board-migrate/reports/util.rpt) 和 [routed DRC report](<仓库根目录>/hw/build/bkb220-p16-enet0-100mhz-20261012T144141Z-board-migrate/build/dna_accel.runs/impl_1/top_bd_wrapper_drc_routed.rpt)。

## ENET0 MIO 自查：PASS

从新 XSA 提取的 [ps7_init.tcl](<仓库根目录>/hw/build/bkb220-p16-enet0-software-20261012T144141Z-board-migrate/export/ps7_init.tcl) 上执行 grep，退出码 **0**。以下为 grep 首组实际输出；初始化函数中有三组相同写入：

```text
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
```

## 同源软件包与板测移交

新软件包：[bkb220-p16-enet0-software-20261012T144141Z-board-migrate](<仓库根目录>/hw/build/bkb220-p16-enet0-software-20261012T144141Z-board-migrate)。BSP、FSBL 和应用 ELF 构建均退出 **0**；XSCT 的 `app create` 因本地 socket 权限拒绝而退出 **1**，随后用同一 P16 BSP、未修改的 `sw/app` 权威源和 ARM GCC 11.2.0 直接构建 ELF，退出 **0**。实际 lwIP 为安装树中的 `lwip211_v1_8`。Bootgen 创建 BOOT.bin 和 readback 均退出 **0**，readback 显示 FSBL、bit、应用三个 image。

`g3_artifacts.py` 预检 **PASS**，SHA256SUMS 全量校验 **PASS（2,949 项）**。XSA HWH 与 manifest 参数均确认 **`C_STAGE1_P_WAYS=16 / C_STAGE1_PIPE_TREE=1`**；这两个值可用于确认所选包是 P16（P4 为 4/0）。构建摘要见 [software_build_summary.md](<仓库根目录>/hw/build/bkb220-p16-enet0-software-20261012T144141Z-board-migrate/reports/software_build_summary.md)。

六制品 SHA-256：

| 制品 | SHA-256 |
|---|---|
| bit | `123c02b3f3d0156b7b60c935c9e48aa064a0ec2eac943361ccb656c7d8b6e6cf` |
| XSA | `d3afb1d5d3818bd0c8ab8db4a073cc2486e7284c8def787fe12f069fe78fb14a` |
| `ps7_init.tcl` | `2f80e045cb18d7c37d5144bf0a819cd8fd42d09a622fca164f2ef7b007b6c81f` |
| 应用 ELF | `595482d87aa5fcc1019376faf792b884875409a9908178342258a9a0e23b934c` |
| FSBL | `1f22062b9ce8e9e6898f110d02ee108a054ca455681eb66822b8a2e699e07bef` |
| BOOT.bin | `afb296dd87b0a1356c3547f24573ca61afc53fd3ba55020a7c4bdef2c844ddb5` |

供 main 使用：bit、`ps7_init.tcl`、应用 ELF 均在新软件包的 `export/` 下。**本任务未触板、未使用串口；P16 板端 G3、功能验收和冷启动均未测，不能据此宣称 P16 已通过验收。**
