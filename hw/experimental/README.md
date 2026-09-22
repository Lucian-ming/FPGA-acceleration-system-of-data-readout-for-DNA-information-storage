# hw/experimental/ —— 退出打包目录的 RTL

这里放**不会被综合**的 RTL：实验变体、半成品、已证伪方向、被取代的旧实现。
它们从 `hw/ip/*/hdl/` 移出，是因为**IP 打包目录的内容决定综合工具看到什么**，
把这些留在那里迟早被误打包（本项目已发生过：五个文件同时定义 `module srpe_batch`，
改 `component.xml` 一行就静默换掉整个微架构，且**不报错**）。

## 当前内容

| 文件 | 为什么在这里 | 保留原因 |
| --- | --- | --- |
| `local_correlator.v` | 全库零引用。4-way 是扁平实现，不实例化任何子模块 | **保留**：不满足退休三条中任何一条（无实测证伪，亦无直接替代文件覆盖其微结构） |
| `srpe_batch_pway.v` | 参数化 P 路 Stage1（由生产 4-way 机械推广），XC7Z020 迁移候选，**未打包** | **保留**：7020 摸底的被测对象；由 tools/run_sim.sh 的 stage1_pway 用例覆盖，结论见 docs/benchmarks/stage1-pway-7020-probe.md |

## 历史退休记录（2026-09-11，docs/19 §B2）

以下文件已于 2026-09-11 依据 AGENTS.md 代码卫生 §5 退休删除，历史可从 Git 取回：

| 文件 | 退休规则 | 依据 |
| --- | --- | --- |
| `srpe_batch_8way_wip.v` | 第 1 条成立 | 方向已被资源证伪，结论在 `docs/17` §2.1 与 `docs/benchmarks/measured_4way_board.md` §4 |
| `srpe_batch_1way_baseline.v` | 第 3 条成立 | 被 `srpe_batch.v` (2-way) / `srpe_batch_4way.v` 取代，受 `tools/run_sim.sh` 覆盖 |
| `srpe.v` | 第 3 条成立 | 被 `srpe_batch.v` / `srpe_batch_4way.v` 取代 |
| `fifo.v` | 第 3 条成立 | 被 `fifo_sync_sdpram_b64.v` 取代 |
| `fifo_sync_sdpram.v` | 第 3 条成立 | 被 `fifo_sync_sdpram_b64.v` 取代 |
| `unused_axi_wrappers/`（7 个） | 第 3 条成立 | AXI 逻辑已内联进各 IP 顶层；`five_to_four_decoder.v` 为死文件，功能由 `desparsification_decoder_v1_0.v` / `desparsify_datapath.v` 覆盖 |

## 退休规则（AGENTS.md「代码卫生」§5）

移到这里**本身就保留了证据**——Git 历史在，随时可以取回。
「不得静默删除证据」指的是**运行留证与实验数据**，不是死代码。

满足以下**任一条**即可真正 `git rm`，并在提交说明里写明依据哪一条：

1. 该方向已被实测证伪，且结论已写进 `docs/`（如 8-way 的资源证伪）；
2. 与仓库内另一文件逐字节相同（`cmp` 确认）；
3. 其功能已被另一个**受回归覆盖**的文件完全取代。

反过来，**不满足任何一条就不要删**——它可能还藏着没被记录的结论。
`tools/bench_align.py` 是前车之鉴：它守着「精确种子法为何失效」的实证，
却因零引用而事实上不存在，导致 `docs/17` 把被它推翻的方向列为第一优先级。

## 不要做的事

- 不要把这里的文件加进任何 `component.xml`；
- 不要在这里放 testbench（TB 去 `hw/sim/` 或 `hw/sim/ip_tb/`）；
- 不要把这里当草稿箱长期堆放——**每次卫生审计都应当清一次**。
