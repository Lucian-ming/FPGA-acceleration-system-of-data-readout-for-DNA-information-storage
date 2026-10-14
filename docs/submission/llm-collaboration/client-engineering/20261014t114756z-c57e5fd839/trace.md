# 运行轨迹

原始留证：`~/.local/state/codex-subagent/runs/20261014T114756Z-c57e5fd839/run.jsonl`（186947 bytes；SHA-256 `69f180c6e1f3e0800819fc476f08a27ea38f975cc76bc61994e31674b7678280`）。该路径是本机状态目录，读者可忽略本机前缀。事件编号为 JSONL 的零基行号。

## 自我纠错摘录（已核实）

- **现象**：设计逐字节回归时发现 `first.iter_read_batches()` 会直接委托给 `fast_readout`；比较这两个批处理 API 会变成同一路径自比，不能发现分叉。
- **定位**：事件 45 的分析消息记录了代码关系与风险，并指出需要从另一条独立读取路径构造线上字节。
- **修正**：使用 `first.iter_reads()` 逐读路径作为参考，再与 `fast_readout.fast_iter_read_batches()` 输出比较。
- **复验**：回答原文报告 31 项通过、1 项显式 skip；native 与 c_accel 的 54,000 位载荷 SHA-256 一致。external Windows PE 在 Linux/WSL 未执行，报告明确保留该未完成项。故障注入时读出测试按预期失败，报告首个不符偏移 4。

**原始事件摘录**

```text
[45] 当前实现里 `first.iter_read_batches()` 直接委托给 `fast_readout`，直接对比这两个批处理 API 会形成同函数自比。我会用 `first.iter_reads()` 生成逐读记录，再按线协议封装成 batch，与 `fast_readout.fast_iter_read_batches()` 的完整线上字节比较，这样能覆盖方向处理、向量化打包、头部和补零。另会核实外部 EXE 在当前运行环境是否可执行。
Ran 31 tests in 1.303s
OK (skipped=1)
SKIP: LDPC backend=external：当前宿主为 linux，resources 中是 Windows PE EXE；该执行环境不能直接启动此 EXE
```

核对用载荷 SHA-256（取自最终回答）：`0a2aa3b514b4b470c80a8affa64a5795dba34bbab134153c3d528c298c40e04f`。
