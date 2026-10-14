> 脱敏副本，原件 `20261012T123041Z-ab7659fdac/{prompt.txt,answer.md}`。本机绝对路径、邮箱、凭据形模式及非白名单私网 IP 已替换；除脱敏与换行规范化外保留原文。

## 构建结果

P4、P16 均在 WSL Vivado 2022.2 完成整机综合、implementation、完整 route、bitstream 和 XSA 导出；两次脚本退出码均为 **0**。两套最终 STA 都满足 100 MHz setup/hold 判据。DRC 均为 **0 errors**，但有未清理的 warnings 和 advisories，见下表。

### P4：`4/0`

实际命令：

```bash
VIVADO_ROOT=<本机路径> bash tools/run_vivado_build.sh \
  board=bkb220 part_name=xc7z020clg400-2 clk_mhz=100 \
  stage1_p_ways=4 stage1_pipe_tree=0 \
  build_dir=<仓库根目录>/hw/build/bkb220-p4-100mhz-20261012T123158Z-board-migrate-p4/build \
  export_dir=<仓库根目录>/hw/build/bkb220-p4-100mhz-20261012T123158Z-board-migrate-p4/export \
  report_dir=<仓库根目录>/hw/build/bkb220-p4-100mhz-20261012T123158Z-board-migrate-p4/reports
```

退出码 **0**。原始日志在 [`vivado.log`](<仓库根目录>/logs/vivado/20261012T123158Z-342/vivado.log) 和同目录 `vivado.jou`。

### P16：`16/1`

实际命令：

```bash
VIVADO_ROOT=<本机路径> bash tools/run_vivado_build.sh \
  board=bkb220 part_name=xc7z020clg400-2 clk_mhz=100 \
  stage1_p_ways=16 stage1_pipe_tree=1 \
  build_dir=<仓库根目录>/hw/build/bkb220-p16-100mhz-20261012T123936Z-board-migrate-p16/build \
  export_dir=<仓库根目录>/hw/build/bkb220-p16-100mhz-20261012T123936Z-board-migrate-p16/export \
  report_dir=<仓库根目录>/hw/build/bkb220-p16-100mhz-20261012T123936Z-board-migrate-p16/reports
```

退出码 **0**。原始日志在 [`vivado.log`](<仓库根目录>/logs/vivado/20261012T123936Z-342/vivado.log) 和同目录 `vivado.jou`。

### 最终判据

| 判据 | P4 | P16 |
|---|---:|---:|
| Implementation / 完整 route | **PASS**；26,731/26,731 可布线 nets 完成，无 routing errors | **PASS**；49,404/49,404 完成，无 routing errors |
| WNS / TNS | +0.680 ns / 0 | +0.617 ns / 0 |
| WHS / THS | +0.036 ns / 0 | +0.017 ns / 0 |
| Setup / hold 失败端点 | 0 / 0 | 0 / 0 |
| 时钟报告 | `clk_fpga_0`，10.000 ns，100.000 MHz | `clk_fpga_0`，10.000 ns，100.000 MHz |
| Timing coverage | no clock、unconstrained endpoints、缺少 input/output delay 均为 0 | 同左，均为 0 |
| DRC | 0 errors、58 warnings、3 advisories；共 61 项报告项 | 0 errors、75 warnings、3 advisories；共 78 项报告项 |

两个设计的**构建、路由和时序目标均 PASS**；DRC 尚非 warning-free。两份报告都指出 20 项 `REQP-1839` 和 20 项 `REQP-1840` 异步复位 BRAM 控制警告，提示复位期间可能影响存储内容，且默认 STA 不分析该风险。P16 另有 16 项 `DPOR-1`，提示异步复位限制 DSP 输出寄存器映射。P16 还有 `RTSTAT-10` no-routable-load 警告，但 route status 报告的 routing errors 为 0。建议由 RTL/main 复核这些警告后再关闭 DRC 审查项。

两者最差 setup path 都是**正 slack、非失败路径**：P4 为 `desparsification_dec` 到 `differential_voter`，+0.680 ns；P16 为 Stage1 `pos_valid_reg[8]` 到选优树寄存器，+0.617 ns。

### 资源与 P16 对照

| 资源 | P4 | P16 | P16 相对 P4 |
|---|---:|---:|---:|
| LUT | 15,447 / 53,200（29.04%） | 33,987 / 53,200（63.89%） | +18,540 |
| FF | 16,910 / 106,400（15.89%） | 36,067 / 106,400（33.90%） | +19,157 |
| BRAM tile | 45 / 140（32.14%） | 45 / 140（32.14%） | 0 |
| DSP | 3 / 220（1.36%） | 3 / 220（1.36%） | 0 |
| WNS | +0.680 ns | +0.617 ns | −0.063 ns |
| WHS | +0.036 ns | +0.017 ns | −0.019 ns |

P16 的 33,987 LUT、63.89% 与 rtl-16way 的约 33.9k LUT / 64% 先验吻合，差 87 LUT。P16 在本次器件和 100 MHz 约束下有正 setup/hold 裕量并完成 route。

两份归档摘要包含命令、退出码、路径、STA、DRC、资源和结论边界：[P4 摘要](<仓库根目录>/hw/build/bkb220-p4-100mhz-20261012T123158Z-board-migrate-p4/reports/run_summary.md)、[P16 摘要](<仓库根目录>/hw/build/bkb220-p16-100mhz-20261012T123936Z-board-migrate-p16/reports/run_summary.md)。两套 XSA 均包含 bit；`sysdef.xml` 的 `PART` 均为 `xc7z020clg400-2`。

## 未完成项与后续依赖

- **未测**：板端下载/功能验收，以及 BSP、应用、FSBL、BOOT、readback 和完整软件 manifest。本轮按要求没有触板。
- ENET0/PHY 仍未通过；此次构建验证候选 profile 能生成并收敛，不证明 MIO/PHY 连线正确。来源表 §9 的 PHY 问题仍需原理图或受控探测定位。
- 工业级完整料号和 DDR 板级延迟仍未确认；XSA 只证明构建使用了指定的普通 `xc7z020clg400-2` catalog part。
- 下一步需复核 P16 DRC 警告，生成同 XSA 软件制品，再由 main 持板完成后续板端验收。根目录 Vivado 日志残留检查为空。
