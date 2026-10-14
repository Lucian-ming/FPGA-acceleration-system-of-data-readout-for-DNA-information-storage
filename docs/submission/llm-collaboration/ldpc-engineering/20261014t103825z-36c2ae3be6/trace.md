# 运行轨迹

原始留证：`~/.local/state/codex-subagent/runs/20261014T103825Z-36c2ae3be6/run.jsonl`（522776 bytes；SHA-256 `d39c2f73ecee3c012b4f7d3a4524cd357887a51682965e17005da4d2bc980ad8`）。该路径是本机状态目录，读者可忽略本机前缀。事件编号为 JSONL 的零基行号。

## 自我纠错摘录（已核实；存在未完成门禁）

- **现象**：XSCT 2022.2 的 fresh-workspace 创建阶段退出 1；日志在 `getsdkchan` 报 `Socket create error. Operation not permitted`。
- **定位**：平台、BSP 和 FSBL 已生成；失败点是 `app create` 的本机 socket 通道。事件 127 将错误限定到该步骤，而不是把 launcher 的退出状态当成软件构建通过。
- **修正**：保留 XSCT 失败日志，改用同一 Vitis 2022.2 安装树的 ARM GCC，基于本轮生成的 BSP include/lib 编译应用，然后继续 Bootgen/readback 和清单核验。
- **证明与边界**：回答和事件记录包含 `APP_BUILD_PASS`、Bootgen/readback 成功及 SHA256SUMS 2,958/2,958 匹配；但 `check_repo_hygiene.sh` 仍因两份已跟踪 LDPC HDL 完全重复而失败。这证明构建后备路径完成，不代表整套门禁全绿，也没有板端验证。

**原始事件摘录**

```text
[124] XSCT create_vitis.tcl exit=1（输出重定向到保留日志）
[126] Socket create error. Operation not permitted
      (procedure "getsdkchan" line 93)
[127] 正式流程已把新 BSP 与 FSBL 生成出来，并成功应用 `TCP_WND=32768`；但 XSCT 的 `app create` 在 `getsdkchan` 阶段被本机 `Socket create error. Operation not permitted` 阻断，与参考软件包记录的限制一致。我会保留这次失败日志，按参考包的已用做法，用新 BSP 的 include/lib 和 Vitis 2022.2 ARM GCC 直接编译应用；不会使用 `build_sw_variant.sh`。
[145] hw/build/bkb220-p16-k2-ldpc-sw-20261014T104331Z-board-migrate/logs/app-build.log:212:APP_BUILD_PASS source=sw/app BSP=generated-from-k2-ldpc-XSA lwip=lwip211_v1_8
[197/205] exit=0 checked=2958 ok=2958 failed=0
[172] exit=1，repo hygiene 存在重复 HDL 项；详见最终回答边界。
```
