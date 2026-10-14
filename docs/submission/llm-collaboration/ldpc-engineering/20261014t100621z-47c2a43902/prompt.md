> 脱敏副本，原件 `20261014T100621Z-47c2a43902/{prompt.txt,answer.md}`。本机绝对路径、邮箱、凭据形模式及非白名单私网 IP 已替换；除脱敏与换行规范化外保留原文。

任务（workspace-write，看板名 **ldpc-regress**）：给 LDPC 译码器加**自包含、可复现**的回归用例，让 `tools/check_ip_packaging.sh` 通过。

## 为什么（先读）
`tools/check_ip_packaging.sh` 现在报：
```
✗ ldpc_decoder_1_0: 打包进比特流但**回归没覆盖**的文件： ldpc_decoder_p1.v ldpc_decoder_v1_0.v
```
即 `hw/ip/ldpc_decoder_1_0/` 的 HDL 会进比特流，但 `tools/run_sim.sh` 里没有覆盖它的用例。
**问题**：现有 testbench `hw/experimental/tb_ldpc_decoder_p1.v` 依赖 `logs/ldpc/golden/`（**被 gitignore 的忽略区**），
不能直接当回归用——回归用例必须**只依赖仓库内已跟踪的文件**。

## 你要做的
### (1) 把黄金样本固化进仓库
在 `tests/golden/ldpc/` 下建立**只依赖仓库内文件**的最小黄金集：
- 取自 `logs/ldpc/golden/`：`summary.tsv`、`in_013_se150_16384.hex`、`out_013_se150_16384.hex`
  （013 是 4 轮收敛的样本，最快；**如需再加一个不收敛样本也可以，但要注意仿真时长**）。
- 同时把译码器要的 B_t 表固化：`hw/ip/ldpc_decoder_1_0/data/bt_col_by_res.hex` 与 `bt_res_off.hex` **已在仓库内**，回归直接指向它们即可（不要再依赖 `logs/`）。
- **格式与内容必须与 logs 里现有的一致**（`in_*.hex`/`out_*.hex` 是 8,100 字节按 8 bit/字节打包的十六进制，**每字节 LSB 先**；
  这一点已在客户端代码核验过：`clients/python/fast_readout.py` 的 `fast_unpack_result` 用 `np.unpackbits(raw, bitorder="little")`）。

### (2) 让 testbench 不依赖 logs/
修改 `hw/experimental/tb_ldpc_decoder_p1.v`（**只改路径注入，不改判定逻辑**）：
- 支持 `+GOLD_DIR=<目录>` plusarg（默认保持现在的 `logs/ldpc/golden`，这样原有用法不变）；
- 黄金表的路径改成从该目录解析；
- B_t ROM 的路径：让 TB 实例化译码器时能通过 `define` 覆盖 `BT_ROM_FILE` / `BT_OFF_FILE`（或直接在 TB 里传参），
  回归时指向 `hw/ip/ldpc_decoder_1_0/data/`。
- ⚠️ **不要改判据**：收敛状态 + **码字逐位相同**；轮数只记录不判 FAIL（`docs/benchmarks/ldpc-decoder-l4.md` §1.1 已写明原因）。

### (3) 接进 `tools/run_sim.sh`
- 在文件顶部的用例白名单里加一个名字，例如 `ldpc_decoder`；
- 加一段 `if [ "$WHICH" = "all" ] || [ "$WHICH" = "ldpc_decoder" ]; then ... fi`，用 `run_case` 跑；
- `run_case` 的约定：iverilog 编译 + `vvp`，**输出里必须含 `PASS`** 且退出码 0；
- 用 `VVP_ARGS` 或在该用例里显式传 `+TAG=013_se150_16384 +GOLD_DIR=tests/golden/ldpc`（看现有写法怎么传 plusarg，保持一致）；
- **注意 013 要跑约 291 万周期**，请确认在默认 `CASE_TIMEOUT` 内跑得完；若不够，**如实说明**并给出建议（不要偷偷改全局超时影响别的用例）。

## 你要实际验证
1. `bash tools/run_sim.sh ldpc_decoder` **必须通过**，把原始输出贴进答复；
2. `bash tools/check_ip_packaging.sh` **必须 PASS**；
3. `bash tools/check_repo_hygiene.sh` **必须 PASS**；
4. **其余用例不要被破坏**：至少跑一次 `bash tools/run_sim.sh host`（或你判断最快的相关子集）确认没连带损坏，并报告结果。

## 硬约束
- **不要**改 `hw/ip/ldpc_decoder_1_0/` 里的 RTL 与 `hw/experimental/ldpc_decoder_p1.v` 的逻辑；
  只允许改 `hw/experimental/tb_ldpc_decoder_p1.v`、`tools/run_sim.sh`，并**新增** `tests/golden/ldpc/` 下的文件。
- 不要碰 `sw/`、`clients/`、`docs/`、其他 IP。
- **不做 Git 写操作**；**不要运行 `tools/verify_repo_binding.sh`**（沙箱内 git 只读，必然失败白跑）。
- 不跑 Vivado、不碰板卡。
- 看板自行登记：`tools/agent_view.sh start/update/done --agent ldpc-regress ...`

## 交付
1. 新增/改动文件清单与**每个文件的大小**（黄金集要固化进 Git，体积要说清楚）；
2. 三个门禁的**原始输出**；
3. `tests/golden/ldpc/` 的 SHA-256（便于以后追溯）；
4. 明确区分：哪些跑过、哪些没跑；失败或放弃的尝试也写。
答复用中文。