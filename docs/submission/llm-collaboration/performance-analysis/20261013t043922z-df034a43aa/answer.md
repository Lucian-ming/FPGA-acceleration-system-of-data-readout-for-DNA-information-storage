> 脱敏副本，原件 `20261013T043922Z-df034a43aa/{prompt.txt,answer.md}`。本机绝对路径、邮箱、凭据形模式及非白名单私网 IP 已替换；除脱敏与换行规范化外保留原文。

## 代码位置与当前判读

| 瓶颈 | 代码位置 | 判读 |
|---|---|---|
| lwIP poll 空等 | [sw/app/echo.c:279](<仓库根目录>/sw/app/echo.c:279)、[sw/app/echo.c:304](<仓库根目录>/sw/app/echo.c:304)、[sw/app/echo.c:439](<仓库根目录>/sw/app/echo.c:439) | 旧路径用 `tcp_poll()` 回调推进流水线；源码注释记载旧实现每次回调只走一步。当前主循环在 [sw/app/main.c:304](<仓库根目录>/sw/app/main.c:304) 每轮调用 `echo_pipeline_poll()`，它又直接调用 `poll_callback()`，因此源码已有主动推进路径。P7 的 2777 ms 不能直接当作当前源码仍可省下的时间；本轮没有核验冻结 ELF 与当前源码的对应关系。 |
| 仍存在的 PS 轮询间隔 | [sw/app/main.c:28](<仓库根目录>/sw/app/main.c:28)、[sw/app/main.c:329](<仓库根目录>/sw/app/main.c:329) | 流水线运行时默认每轮 `usleep(200)`。另外主循环先调用一次 `xemacif_input()`，而 `echo_pipeline_poll()` 调用的回调也会经 [sw/app/echo.c:281](<仓库根目录>/sw/app/echo.c:281) 再次调用 `keep_tcp_alive()`。 |
| Cache 维护 | [sw/app/bd_ring.c:121](<仓库根目录>/sw/app/bd_ring.c:121)、[sw/app/stage1_dna.c:236](<仓库根目录>/sw/app/stage1_dna.c:236)、[sw/app/stage1_dna.c:414](<仓库根目录>/sw/app/stage1_dna.c:414)、[sw/app/stage2_voter.c:102](<仓库根目录>/sw/app/stage2_voter.c:102) | Stage1 RX 每条记录一个 BD；4096 条会提交 4096 个 RX BD。[sw/app/bd_ring.c:129](<仓库根目录>/sw/app/bd_ring.c:129) 对每个 BD 单独调用一次 `Xil_DCacheFlushRange()`。数据缓冲的范围已按实际任务条数计算：4096 × 48 B = 196,608 B；Stage1 完成后还全量 flush，Stage2 准备时又全量 invalidate 同一输入区。 |
| 分包与 ACK 往返 | [clients/python/first.py:457](<仓库根目录>/clients/python/first.py:457)、[clients/python/first.py:462](<仓库根目录>/clients/python/first.py:462)、[sw/app/echo.c:219](<仓库根目录>/sw/app/echo.c:219) | 客户端每发一个 `PKT_BATCH` 就同步等一个 ACK；板端每个完整批次处理后返回 ACK。这个往返计入 `t_batches`，不会计入 POST 之后的 `t_result`。 |
| 结果接收与 LDPC | [clients/python/first.py:648](<仓库根目录>/clients/python/first.py:648)、[clients/python/first.py:484](<仓库根目录>/clients/python/first.py:484)、[clients/python/gui_app.py:718](<仓库根目录>/clients/python/gui_app.py:718)、[clients/python/gui_app.py:731](<仓库根目录>/clients/python/gui_app.py:731) | `t_result` 包住完整的 `recv_result()`；该函数收完 8100 B 后还会展开成文本并写文件。[gui_app.py]( <仓库根目录>/clients/python/gui_app.py:718) 在 `run_client()` 返回后才启动 LDPC。 |

## 候选优化

| 代码位置 | 改什么、为什么能省时间 | 预期量级 | 风险 | 失败判据与验证命令 | 对冻结制品包的影响 |
|---|---|---|---|---|---|
| [sw/app/bd_ring.c:121](<仓库根目录>/sw/app/bd_ring.c:121)、[sw/app/dma_dna.c:57](<仓库根目录>/sw/app/dma_dna.c:57)、[sw/app/dma_dna.h:18](<仓库根目录>/sw/app/dma_dna.h:18) | **合并连续 BD 的 cache flush 范围。** 保持 BD 初始化和提交顺序不变；遍历环时把相邻地址合为一个范围，遇到环尾分成两段。每条记录仍保留一个 BD，只减少 cache API 调用。 | 4096 条对应 4096 次逐 BD flush。若每次 RX 提交都是 512 个连续 BD，8 次提交理论上最多约 16 个范围调用；实际提交次数取决于回收节奏。毫秒收益不确定，但针对的是实测的 cache 瓶颈。 | 环尾处理错误会漏刷或刷到环外地址，硬件可能读取旧 BD；B21 已有过环回相关缺陷。 | 新增范围规划的 host 单测，断言每次提交覆盖的 BD 地址集合与提交集合完全相同、范围不越界且环回最多拆成两段；失败时测试退出非零。随后跑下方 4096 条板端命令，要求结果与黄金文件 `cmp` 一致。 | 属于 PS 固件改动。按项目规则生成**新的同步制品包**，重建 Vitis 2022.2 ELF、配套 bit/XSA 和 SHA256SUMS；不能覆盖冻结包。 |
| [sw/app/stage1_dna.c:236](<仓库根目录>/sw/app/stage1_dna.c:236)、[sw/app/stage1_dna.c:414](<仓库根目录>/sw/app/stage1_dna.c:414)、[sw/app/stage2_voter.c:102](<仓库根目录>/sw/app/stage2_voter.c:102)、[sw/app/echo.h:114](<仓库根目录>/sw/app/echo.h:114) | **按 DDR 所有权合并或删除重复的全量 cache 操作。** `DDR_VOTER_IN_BASE` 与 Stage1 输出是同一地址。审查后可考虑保留 DMA 写入前的全量 invalidate，删除 Stage1 DMA 完成后的全量 flush，以及 Stage2 开始前重复的全量 invalidate；CPU 观察数据所需的 invalidate 仍要保留。 | 4096 条下两次候选全量操作各覆盖 196,608 B。它们属于给定的 396 ms cache 总量的一部分；单独能省多少目前不确定，不能把 396 ms 全算到这两处。当前范围是实际任务大小，并非按最大容量误刷。 | 若 CPU 曾写入这些 cache line，或 Stage1 的 DMA/Stage2 的 AXI Master 路径与预期不同，删操作会造成脏数据覆盖或硬件读到旧数据。 | 增加按操作名记录字节数和耗时的诊断；4096 条运行时确认候选的两次全量操作确已消失、DMA 前保护仍在，并运行下方命令要求结果 `cmp` 通过。若 cache 总耗时或 `t_result` 中位数未下降，则该优化未证明有效。 | PS 固件改动；重建 ELF、匹配 bit/XSA 与 SHA256SUMS，另存新包。 |
| [sw/app/main.c:304](<仓库根目录>/sw/app/main.c:304)、[sw/app/main.c:329](<仓库根目录>/sw/app/main.c:329)、[sw/app/echo.c:281](<仓库根目录>/sw/app/echo.c:281)、[sw/app/echo.c:411](<仓库根目录>/sw/app/echo.c:411) | **量测后再调运行期节拍并拆开网络输入与状态推进。** 评估 200 µs 睡眠是否拖慢 DMA BD 回收；避免主循环已经 `xemacif_input()` 后，直接状态推进又重复调用输入处理。只有确认 DMA IRQ 已连到 PS、并且能维持 lwIP 服务后，才评估中断唤醒。 | 每次主循环睡眠上限为 200 µs；总收益取决于活动循环次数，当前没有计数依据。P7 的 2777 ms 是旧 poll 路径实测，不能拿来推算本项收益。 | 去掉睡眠会增加 CPU 占用；改变回调结构可能影响 lwIP 服务。IRQ 路由未从本次阅读范围确认。 | 用相同 4096 条输入重复运行至少 5 次，比较 UART `[PIPE-BREAKDOWN] [waiting]` 和客户端 `Result: 8100 bytes, ...` 的中位数；要求等待时间下降、端到端结果哈希一致，否则判失败。 | PS 固件改动，需生成新的完整同步制品包。若 IRQ 需要更改 BD/XSA 连接，也须更新硬件制品。 |
| [clients/python/first.py:462](<仓库根目录>/clients/python/first.py:462)、[clients/python/first.py:465](<仓库根目录>/clients/python/first.py:465)、[sw/app/echo.c:219](<仓库根目录>/sw/app/echo.c:219) | **给上传 ACK 加有界窗口。** 客户端先发 W 个完整批次，再依序收 W 个现有 ACK 字节；板端线上协议和每批 ACK 保持不变。这样用后续批次发送隐藏一部分等待时间。 | 当前 B 个批次大致有 B 次串行 ACK 等待；窗口 W 后约为 `ceil(B/W)` 轮等待。可省时上限约为 `(B - ceil(B/W)) × 实测 RTT`，实际取决于批次数和网络。收益落在 `t_batches` / 总时长，不会改变 POST 后的 `t_result` 指标。 | 必须限制窗口字节数，避免压满板端 TCP 接收缓存；按 ACK 顺序归属批次，任何 `PKT_ERROR` 都必须使任务失败。 | 增加延迟 ACK 的本地客户端测试，令测试失败条件为 ACK 数量不符、错误 ACK 未报错或窗口模式耗时仍等于逐批停等；运行 `cd clients/python && python -m unittest discover -s tests -p 'test_client_core.py'`。再用下方板端命令验证黄金结果。 | 仅客户端改动不重建 ELF、bit/XSA；若交付打包 GUI/客户端，需要生成新的主机端包。冻结板端包保持原样。 |
| [clients/python/gui_app.py:716](<仓库根目录>/clients/python/gui_app.py:716)、[clients/python/gui_app.py:731](<仓库根目录>/clients/python/gui_app.py:731)、[clients/python/ldpc_pipeline.py:68](<仓库根目录>/clients/python/ldpc_pipeline.py:68)、[sw/app/echo.c:728](<仓库根目录>/sw/app/echo.c:728) | **让第 n 轮 LDPC 与第 n+1 轮板端任务并行。** 当前 GUI 顺序等待 `run_client()` 完成才做 LDPC；可以把结果交给独立译码队列，并在上一轮网络会话关闭后启动下一轮。结果传输本身仍须完成后才能开始该结果的 LDPC；单板同时只能处理一轮。 | 连续任务吞吐理论上最多隐藏 `min(LDPC 耗时, 下一轮板端任务耗时)`；CPU 争用会降低实际收益。不会降低单轮 `t_result`，主要降低多轮总墙钟时间。 | 固件使用全局 `g_conn`，`accept_callback()` 会重置连接状态；需要确保上一轮结果 ACK 已收敛且旧连接退役后再接受下一轮。每轮结果、译码输出也必须使用独立目录，避免覆盖。 | 新增两轮调度测试，失败条件为译码与下一轮没有时间重叠、输出目录冲突或任一结果哈希不符；运行 `python -m unittest discover -s clients/python/tests -p 'test_run_scheduler.py'`。板端验证时再要求两轮结果分别匹配黄金文件。 | 仅主机端调度改动，不重建 ELF、bit/XSA；若 GUI 作为可执行包发布，需重新打包 GUI。 |

4096 条板端回归命令可固定为同一输入、同一批大小和同一 score 阈值：

```bash
cd clients/python
python first.py --ip 192.168.1.10 --port 7 \
  --watermark "$WM" --reads "$READS" \
  --total-reads 2048 --orient both --batch "$BATCH" \
  --output "$OUT" --result-timeout 180
test "$(wc -c < "$OUT")" -eq 64800 && cmp "$OUT" "$GOLDEN"
```

这里 2048 条源读段以 `both` 方向发送，形成 4096 条板端记录。`cmp` 对不上或长度不为 64800 字节即失败。P4/P16 计时比较还需使用各自冻结基线的相同配置；不要用上传 ACK 优化后的 `t_batches` 变化解释 `t_result`。

## 不建议做

- **继续提速 PL 时钟或重写 Voter/Decoder。** 给定板测中 Stage2 与 Stage3 合计不足 30 ms，瓶颈证据集中在 PS 等待与 cache 操作，PL 提速性价比低。
- **全局关闭 D-cache，或把 AXI HP 当作硬件缓存一致性通道。** 本次查看的 PS 源码没有证明 DDR 映射属性或实际 AXI 端口具备一致性。未确认端口和内存属性前，直接删 cache 操作会破坏 DMA/CPU 数据正确性；非缓存映射或 ACP 路径应另做独立硬件实验。
- **取消批次 ACK、无界并发发包或让同一连接直接跑下一任务。** 当前 ACK 是批次处理成功反馈；板端还校验声明与实际记录数，TCP 缓冲和全局连接状态也有边界。应先做有界窗口和错误 ACK 回归。
- **取消 `send_result()` 的未确认数据等待，或缩短超时来“省时”。** [sw/app/echo.c:728](<仓库根目录>/sw/app/echo.c:728) 在确认 `unsent/unacked` 清空后才报告交付成功；绕开此判据会带来结果未完整送达的风险。
- **减少读段方向、改变 score_min、改 64 条帧对齐或结果长度。** 这些会改变数据语义或唯一比对条件，不能用于优化既定 P4/P16 基准。
- **直接套用历史 P7 轮询收益作为当前源码预测。** 当前源码已有主循环直接推进流水线的路径；板上实测 2777 ms 是否对应冻结 ELF 的旧路径，需先核对制品来源。

## 本次执行情况

只读查看了源码并核对上述行号；未改写文件、未做 Git 写操作、未运行测试或板卡任务。交付路径仅为本答复；所有验证判据均为后续候选变更的验收建议，尚未执行。
