> 脱敏副本，原件 `20261014T052214Z-5d11259cd5/{prompt.txt,answer.md}`。本机绝对路径、邮箱、凭据形模式及非白名单私网 IP 已替换；除脱敏与换行规范化外保留原文。

### 交付

- 新增 [ldpc_row_engine_probe.v](<仓库根目录>/hw/experimental/ldpc_row_engine_probe.v:4)：含 `ldpc_h_addr_gen` 和参数化 p=1 行引擎；累加器写回有可观察输出，避免综合器删除数据通路。
- 更新 [hw/experimental/README.md](<仓库根目录>/hw/experimental/README.md:15) 当前内容表。

### 最终 OOC 综合结果

Vivado 2022.2，`xc7z020clg400-2`，100 MHz：综合成功，退出码 0，0 errors、0 critical warnings；约束报告显示 timing constraints met。

- LUT：**495**（479 logic、16 memory）
- FF：**234**
- BRAM：**32 RAMB36E1 + 1 RAMB18E1**（32.5 个 Block RAM Tile）
- DSP：**0**
- 综合后 WNS：**+0.601 ns**；WHS：**+0.035 ns**

最终报告目录：`logs/vivado/ldpc-probe/synth_ldpc_row_engine_probe_ldpc_row_engine/`。资源见 [util.rpt](<仓库根目录>/logs/vivado/ldpc-probe/synth_ldpc_row_engine_probe_ldpc_row_engine/util.rpt)，时序见 [timing.rpt](<仓库根目录>/logs/vivado/ldpc-probe/synth_ldpc_row_engine_probe_ldpc_row_engine/timing.rpt)。

ROM 使用 `(* rom_style = "block" *)` 和仅用于 ROM 初始化的确定性 `initial` 循环，内容为 `(i*137+593) mod 10800`；源码注明该内容**不是实际 B_t**。综合日志报告 `ROMs := 1`，最终网表含 1 个 RAMB18E1；两块大存储分别映射为 12 和 20 个 RAMB36E1。

首轮综合曾因 RAM 写回不可观察而优化掉数据通路；增加写回输出后重跑，以上数字来自最终版本。参数可覆盖，但本次只综合默认参数。**未跑 impl/route，因此没有布线后 WNS；未跑 XSim 或板测。** 根目录 Vivado 日志残留检查无输出，`git diff --check` 通过；没有执行 Git 写操作。
