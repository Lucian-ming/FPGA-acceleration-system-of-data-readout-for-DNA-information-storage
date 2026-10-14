# 已核实的自我纠错案例

以下 4 例逐条核对了原始 `run.jsonl` 的事件顺序、提示词和最终回答。每例分清问题、定位、改动、复验证据与仍未完成项。事件编号是 JSONL 的零基行号。原始来源前缀 `~/.local/state/codex-subagent/runs/` 是本机路径。

## LDPC 回归：修正 Icarus 语言标准

**现象**：首次 `bash tools/run_sim.sh ldpc_decoder` 退出 1，Icarus 在 TB 的 `string` 声明处报语法错误。**定位**：Agent 先怀疑路径宏；查实际编译命令后看到 `iverilog -g2005`，再把根因修正为仿真语言标准不匹配。**改动**：该用例加入 `-g2012`。**复验**：同一入口退出 0；黄金向量 64,800 位 `bit_mismatches=0`、1/1 PASS；IP 打包和卫生门禁也 PASS。

原始调用 `20261014T100621Z-47c2a43902` 的 JSONL 为 144,614 bytes。

- [提示词原文（脱敏副本）](ldpc-engineering/20261014t100621z-47c2a43902/prompt.md)
- [回答原文（脱敏副本）](ldpc-engineering/20261014t100621z-47c2a43902/answer.md)
- [原始事件摘录、大小和 SHA-256](ldpc-engineering/20261014t100621z-47c2a43902/trace.md)

## G3 主机回归：调整 mock 与沙箱测试方式

**现象**：首轮 G3 unittest discovery 退出 1，53 项中 4 项错误。**定位**：输出显示性能矩阵 mock 漏传新必需的 `--ip`；CAPS 输出用例则试图在沙箱中监听本机 socket。**改动**：mock 显式传测试 IP；CAPS 用例改成进程内 fake socket/CAPS。**复验**：同一 discovery 重跑 53 项全过；最终答复记录 host、IP packaging、repo hygiene 均退出 0。未触板，结论限于主机回归。

原始调用 `20261012T115059Z-93cae00e2a` 的 JSONL 为 528,422 bytes。

- [提示词原文（脱敏副本）](board-engineering/20261012t115059z-93cae00e2a/prompt.md)
- [回答原文（脱敏副本）](board-engineering/20261012t115059z-93cae00e2a/answer.md)
- [原始事件摘录、大小和 SHA-256](board-engineering/20261012t115059z-93cae00e2a/trace.md)

## 客户端等价测试：避免同一路径自比

**现象**：实现检查发现 `first.iter_read_batches()` 直接委托给 `fast_readout`，比较两个批处理 API 会变成同一路径自比，漏掉真实分叉。**定位**：事件消息指出委托关系与假阳性风险。**改动**：采用 `first.iter_reads()` 逐读路径构造线上字节，再与快路径逐字节比较。**复验**：统一入口 31 项通过、1 项 external 显式 skip；native 与 c_accel 的 54,000 位载荷 SHA 一致。故障注入能令测试失败并报告偏移 4。Windows PE external 尚未在 Linux/WSL 验证。

原始调用 `20261014T114756Z-c57e5fd839` 的 JSONL 为 186,947 bytes。

- [提示词原文（脱敏副本）](client-engineering/20261014t114756z-c57e5fd839/prompt.md)
- [回答原文（脱敏副本）](client-engineering/20261014t114756z-c57e5fd839/answer.md)
- [原始事件摘录、大小和 SHA-256](client-engineering/20261014t114756z-c57e5fd839/trace.md)

## 软件构建：XSCT 通道失败后的可审计后备

**现象**：XSCT 在 `getsdkchan` 报 `Socket create error. Operation not permitted`，`app create` 退出 1。**定位**：平台、BSP、FSBL 已生成，失败被限定在 SDK socket 通道。**改动**：保留 XSCT 失败日志，改用同一 Vitis 2022.2 安装树的 ARM GCC，基于新生成 BSP 编译应用，再执行 Bootgen/readback 和清单检查。**证明与边界**：记录有 `APP_BUILD_PASS`、Bootgen/readback 成功和 SHA256SUMS 2,958/2,958 匹配；但 repo hygiene 仍因两份已跟踪 LDPC HDL 重复而失败，且没有板端验收。

原始调用 `20261014T103825Z-36c2ae3be6` 的 JSONL 为 522,776 bytes。

- [提示词原文（脱敏副本）](ldpc-engineering/20261014t103825z-36c2ae3be6/prompt.md)
- [回答原文（脱敏副本）](ldpc-engineering/20261014t103825z-36c2ae3be6/answer.md)
- [原始事件摘录、大小和 SHA-256](ldpc-engineering/20261014t103825z-36c2ae3be6/trace.md)

## 不作为案例的记录

其余调用在本轮不声称存在自我纠错：有些是只读分析或一次通过，有些虽出现错误但没有完整的“定位、改动、复验”闭环，还有些只有未完成的 prompt。它们的 prompt/answer 状态和原始 JSONL 大小仍逐条列在 [inventory.md](inventory.md)。
