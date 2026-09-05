# 08 · 仿真与验证计划

## 1. 判据层级

1. **算法层**：`tools/golden_model.py verify-code`、`tests/golden/`；
2. **IP 层**：`tools/run_sim.sh`、`tools/run_xsim.sh`；
3. **真实接口层**：AXIS ingress/result、DMA、Decoder restart、Voter DDR；
4. **BD 层**：地址图、控制面、AXI 读写和故障注入；
5. **板级 G3**：`tools/run_g3.sh` + LDPC + 图片 SHA-256 + 四级 DDR 取证。

编译通过、有波形或 GUI 显示成功都不是功能判据。接口改动必须走真实 AXIS/寄存器/DDR 语义，不能只用黄金内存喂 DUT。

## 2. 常用入口

```text
tools/run_sim.sh
tools/run_xsim.sh all
tools/run_m2_full.sh
tools/run_m3_bd.sh bd2
tools/run_m3_bd.sh bd3ext
tools/run_g3.sh ...
```

## 3. 证据要求

每次运行保存命令、工具版本、输入 manifest、日志路径、结果摘要和故障注入结果。XSim/Vivado 日志进入带 run-id 的构建目录，不进入仓库根目录。

## 4. 历史细节

旧版分层仿真计划、M3 BD 结果和各阶段历史快照位于 `docs/archive/history/2026/`，仅用于追溯，不作为当前状态入口。
