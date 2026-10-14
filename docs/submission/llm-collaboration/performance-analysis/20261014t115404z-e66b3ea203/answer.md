> 脱敏副本，原件 `20261014T115404Z-e66b3ea203/{prompt.txt,answer.md}`。本机绝对路径、邮箱、凭据形模式及非白名单私网 IP 已替换；除脱敏与换行规范化外保留原文。

## 结论：K=3 当前实现因时序失败，不建议进入整机集成

OOC 布局布线完成，资源容量够用：28,429 LUT、26,559 FF、15 RAMB36、9 DSP。但 100 MHz 下 **WNS −15.244 ns，16,115 个 setup 失败端点**；hold 通过，WHS +0.078 ns。最差路径经过水印 bank 读地址逻辑，终点是 `wm_rd_addr_q`。失败项是时序，不是资源容量。

位平面与 bank 深度的静态核对未发现对齐冲突：读段每 bank 50 个地址，水印每 bank 15,950 个地址，150 个碱基正好分为 50 组。K=3 的 6-bit 分组不会改变 LSB-first 的传输格式，也不需要额外重打包；**这不是功能仿真证明**。

## 产出与验证

- 新基准文档：[stage1-k3-feasibility.md](<仓库根目录>/docs/benchmarks/stage1-k3-feasibility.md)，含 K=2/3/4 OOC 对照及结论边界。
- 运行报告：[report.md](<仓库根目录>/logs/vivado/k3-probe/report.md)。
- 原始数据：[util.rpt](<仓库根目录>/logs/vivado/k3-probe/reports/synth_srpe_batch_pway_K3/util.rpt)、[timing.rpt](<仓库根目录>/logs/vivado/k3-probe/reports/synth_srpe_batch_pway_K3/timing.rpt)。
- route 已完成且没有未布通网络；Vivado 退出码为 2，原因是探针按负 WNS 判定时序失败。生产 RTL 探针前后 SHA-256 一致，没有修改 `hw/ip/**`。

**未做**功能仿真、整机综合/实现或板测。本结果是 OOC 单模块证据，不能证明整机资源、时序或板上功能。根目录日志残留检查无输出；未执行 Git 写操作。
