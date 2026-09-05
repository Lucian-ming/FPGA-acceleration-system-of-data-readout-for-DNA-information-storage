# 25 · FPGA DNA 数据读出系统主产品规划

> **版本**：v1.0，2026-09-05
> **定位**：面向当前 `main` checkout 的系统架构审视、近期缺陷整改方案、产品化路线和并行 Agent 任务书。
> **唯一验收真理**：板端真实回传经 `tools/ldpc_decode.py` 译码后，重建图片
> SHA-256 必须为
> `fcd0cf90bd680e7bbdc203e3398119504da0897acac9e2117008b4efb6b1f2c3`，
> 并且四级 DDR 快照逐级通过。界面、仿真、`tcp_write` 入队计数和“看起来完成”
> 均不能替代这一判据。

## 0. 规划基线与证据边界

本规划以 `docs/01-architecture.md`、`docs/02-data-contract.md`、
`docs/03-status.md`、`docs/05-interfaces.md`、`docs/16-board-zynq-eco-7010.md`、
`docs/18-next-steps-2026-08-30.md`、`docs/20-se250-study-2026-08-30.md` 和
`docs/23-next-phase-plan-2026-09-04.md` 为事实来源，并核对了
`hw/ip/`、`sw/app/`、`clients/python/`、`tools/run_g3.sh` 和接口级仿真入口。

当前 checkout 的物理平台是 ZYNQ ECO R6，器件 `xc7z010clg400-1`，单颗
16-bit `MT41J256M16HA-125` DDR3。历史 XSA 的 32-bit 双颗 DDR 配置不是本产品
的配置来源。任何 RTL/固件改动都必须重新生成同源 `bit/XSA/ELF/BOOT.bin`，
刷新 `hw/build/export/SHA256SUMS`，再做板级回归。

## 1. 系统全貌与已验证基线

### 1.1 端到端数据生命周期

```text
FASTQ（SE150 或 SE250）
  -> 上位机按正向/反向互补展开，按位平面 + 字节内 LSB-first 打包
  -> TCP CAPS / CONFIG / WM / BATCH* / POST
  -> PS lwIP RAW API 将水印、读段写入 DDR
  -> Stage1 DNA 比对（AXIS DMA -> Dna_accelerator_core/srpe_batch）
       输入：每条 2*READ_BPS bit；输出：score + position + codeword
  -> Stage2 差分投票（Voter AXI master 从 DDR 读 Stage1 输出）
       过滤 score_min；按 position 将每个 codeword bit 以 +/-1 饱和累加
       输出：81,000 bit 共识流，64-bit 拍、拍内 LSB-first
  -> PS Stage2.5：共识流 XOR 原始水印
  -> Stage3 5b4b 反稀疏化（81,000 -> 64,800 bit）
  -> PS 通过 TCP 返回包头 + 8,100 B
  -> 上位机 LDPC 硬判决译码
  -> 54,000 bit 信息位 -> Milk coronet.jpg -> SHA-256 判据
```

三个 PL 计算级均通过 DDR 中转，不是 PL 内部直连。Stage1 走 AXI-Stream 和
AXI DMA；Stage2/Stage3 通过 AXI-Lite 配置并以 AXI4 master 访问 DDR。该拓扑使
AXI 握手、FIFO 同步读延迟、缓存维护、BD 回收和 lwIP 事件泵都属于功能契约，
不能只用内部数组喂黄金数据来证明。

### 1.2 两套几何与共同码流

`L=40,500` nt、`81,000` watermark bit、`64,800` LDPC codeword bit 在两套几何
中不变；几何必须满足 `NUM_LC*STRIDE=L-READ_BPS` 和
`REF_LEN=STRIDE+READ_BPS`。

| 项 | SE150 基线 | SE250 演进 |
| --- | ---: | ---: |
| FASTQ 源读段 | 51,781 | 64,800 |
| 板端记录（正反向展开并补齐） | 103,616（全量） | 129,600（全量） |
| `READ_BPS` | 150 | 250 |
| `NUM_LC / STRIDE / REF_LEN` | 50 / 807 / 957 | 50 / 805 / 1,055 |
| Stage1 AXIS 输入 | 40 B/条 | 64 B/条 |
| Stage1 结果 | 48 B/条、6×64-bit | 72 B/条、9×64-bit |
| 推荐 `score_min` | 67 | 112 |
| Stage2/Stage3 输出 | 81,000 -> 64,800 bit | 相同 |

SE150 的水印、位序、5b4b 表和 LDPC 等式以 `docs/02-data-contract.md` 为唯一
规范。SE250 主机黄金向量隔离在 `tests/golden/se250/`；两个几何最终都输出同一
图片哈希，因此不能用图片哈希区分几何，必须同时检查 CAPS、几何 manifest、制品
哈希和四级 DDR 快照。

### 1.3 已验证事实

| 范围 | 证据与状态 |
| --- | --- |
| SE150 G3 | 4,096、8,192、16,384、32,768、103,616 条记录板级闭环，图片哈希逐位匹配；四级 DDR 取证通过。 |
| SE150 性能 | 水印预载批量化后 `t = 4.93 s + 0.9396 ms/条 × N`，四档拟合 `R²=1.00000`；固定开销由约 28.90 s 降至 4.93 s。 |
| SE150 状态复位 | 三轮跨规模连续任务已闭环；使用弄脏轮 `score_min=0` 后再以 67 判定，证明 Voter 累加器清零。 |
| SE250 基础 | S1~S4 的参数化、资源/时序和接口仿真已通过；整机 S5 首次点亮 4,096 条，S7 布局复验 32,768 条，均得到目标图片哈希、四级 DDR 全绿。 |
| SE250 当前边界 | 全量 129,600 条在 Stage1 完成后于 Stage2 命中 B30；尚不能声称 SE250 全量闭环。 |
| B29 状态 | 已有 ARP 保活、发送重试计数、`tcp_sndbuf` 和 `Delivery settled` 探针；中小规模通过，但全量长计算后的物理投递仍需重新验证。 |
| B30 状态 | 现场已锁定 Voter 全局 1.000 s 看门狗导致 `S_ERROR`；工作树已有 10 s/状态清零半成品，但必须按真实进展握手重构并整机验证。 |

## 2. 当前不足与深层技术债

### 2.1 几何与硬编码割裂

SE150/SE250 的 `READ_BPS`、AXIS 拍数、结果宽度、FIFO 深度、Voter 拆包、
水印乘法、DDR 基址、`TOTAL_READS`、主机默认值分散在 RTL parameter、
IP-XACT、`echo.h`、协议模块、Python 客户端和黄金脚本中。现有
`PKT_CONFIG/PKT_CAPS` 是严格校验闸门，不是运行时重配置：一份已综合 bitstream
仍只服务其编译几何。

风险不是“改一个宏漏一处”这么简单。SE250 曾暴露 72 B 记录的 4 KB 跨页首点、
3-bit burst 截断、526-bit 结果打包等耦合问题；错误几何还可能在最终图片哈希上
被 LDPC 隐藏。因此必须由一个版本化 geometry manifest 驱动主机、PS、RTL 参数和
黄金向量，并让 `CAPS` 返回 manifest/hash。

### 2.2 RTL 保护机制仍按“时间”而不是“进展”

`differential_voter_v1_0.v` 曾在离开 `S_IDLE` 后连续累计
`TIMEOUT_CYCLES=100,000,000`，不区分正在处理记录、等待 DDR 返回和真正无进展。
129,600 条 SE250 记录约 1.2~1.5 s 即触发 B30。当前将常数改为 10 s 只能缓解
规模，不能解决“某个 AXI 握手永久不来”时的诊断和恢复语义。

还存在三个产品化缺口：

1. 错误状态和错误码没有成为稳定寄存器契约；固件容易只等 DONE。
2. 已接受的 AXI burst 必须完整完成，但错误路径、复位路径和下游背压路径缺少
   统一的“停止发起新事务、排空已接受事务、报告原因”状态机。
3. 计数器、地址、页边界和最后一拍有效位虽然有接口测试，却未形成跨几何参数的
   自动属性检查。

### 2.3 lwIP RAW API 的长计算脆弱性

固件在 `sw/app/main.c` 中运行裸循环、输入泵和定时器；流水线推进依赖
`tcp_poll` 回调，每次回调只推进一个或少量状态。长计算期间若没有稳定、单一的
网络事件泵，ARP 表项、TCP 重传定时器、发送窗口和 PHY 驱动的节奏会脱钩。

B29 已证明最危险的语义差异：`send_result()` 打印的 `sent` 只是
`tcp_write()` 成功入队字节数，不是对端收到的字节数。全量任务现场出现
Stage3 DDR 完整、`sent=8100`、连接仍 ESTABLISHED，但客户端连包头都收不到。
现有探针能定位范围，却还没有一次“全量长计算 + 物理投递确认”的闭环证据。

### 2.4 XC7Z010 资源和时序裕量偏薄

SE150 历史实现曾达到约 90% BRAM、96% Slice；SE250 经过移位寄存器和 FIFO
紧缩后整机约 47.5/60 BRAM（79.17%）、11,850 LUT、实现 WNS +0.586 ns。
这已足够当前功能，但新增错误遥测、双通道、SE300 或更深缓存都可能触发布线
拥塞和时序回退。资源门禁应同时看 BRAM、Slice、LUT、WNS/WHS、拥塞和功耗，
不能只看“综合通过”。

### 2.5 接口级仿真覆盖仍需制度化

B23~B27 曾在内部黄金向量仿真中全部通过，只有真实 AXI DMA、AXIS、FIFO 延迟、
固件寄存器写序列和板端 DDR 才暴露。当前已有 `result_axis`、`ingress_result`、
`dec_restart`、`vot_ddr`、`bd3b` 等资产，但它们仍需成为每次几何/RTL变更的强制
门禁，并且每个判据必须带能失败的故障注入。

### 2.6 其他工业化债务

- `hw/ip/` 部分 Verilog 为 GBK；检索和修改必须转码，长期应迁移 UTF-8 并固定
  `.gitattributes`，迁移前后做字节和综合回归。
- LDPC Windows EXE 仍是黑盒依赖；Python 译码器可用于 Linux 判据，但产品需定义
  版本、许可证、性能和跨平台发布策略。
- ACK 有裸字节与带包头两种格式；协议版本、能力 manifest、错误码和重试语义尚未
  形成正式兼容矩阵。
- `data/R0.83_data/`、历史 XSA、历史演示文件和生产路径之间的隔离主要靠纪律，
  需用 manifest、路径白名单和 CI 哨兵自动阻断“正确结果直出图片”的旁路。
- 当前构建、烧录、板级取证依赖 Windows/WSL 混合环境；缺少可审计的工具版本、
  SBOM、许可证清单和发布签名。

## 3. 近期致命问题的根治方案

### 3.1 B30：Voter 无进展保护看门狗

**目标语义**：正在进行合法的 AXI 读、投票或 AXI 写时不因任务规模超时；只有在
硬件处于活动状态且一段时间没有任何可证明的进展，才转入可诊断的 `S_ERROR`。

**RTL 设计**：

1. 保留一个 10 s 级“任务绝对上限”作为最后防线，但由参数或寄存器表达，明确
   100 MHz 假设；达到上限时产生 `ERR_TIMEOUT_GLOBAL`。
2. 新增 `progress_event`，仅由真实握手/提交产生：
   `ARVALID&&ARREADY`、`RVALID&&RREADY`、一条记录解析完成、一个投票位写入、
   `AWVALID&&AWREADY`、`WVALID&&WREADY`、`BVALID&&BREADY` 均可作为进展事件。
   单纯状态切换、`VALID` 拉高、计数器自增不能算进展。
3. `no_progress_counter` 在活动状态且 `progress_event=0` 时累加；在任一进展
   事件时清零。计数器饱和而不是回绕。等待 DDR 刷新/背压时可以停留，但必须在
   无进展预算耗尽后报告 `ERR_TIMEOUT_STALL`。
4. `S_ERROR` 必须锁存错误码、停止发起新 burst、等待已接受事务按 AXI 规则完成，
   再拉起 `error` 状态；不能通过 `DONE` 伪装成功，也不能让固件靠写 START=0
   猜测状态。
5. AXI-Lite status 至少固定 `IDLE/DONE/ERROR` 三个位，新增 `ERR_FLAGS`、
   `DBG_STATE`、读/写拍计数和最后 `RRESP/BRESP` 的清除语义；错误码在新任务
   START 或显式 CLEAR 前保持，便于 JTAG/串口事后取证。

**固件防御**（`sw/app/stage2_voter.c`）：

- `PIPE_VOTER_WAIT` 每次读 STATUS，同时读 `DBG_STATE` 和 `ERR_FLAGS`；
  `ERROR` 位、`DBG_STATE==S_ERROR` 或 `ERR_FLAGS!=0` 立即打印输入地址、任务条数、
  已读/已写拍数和最后响应，转 `PIPE_FAIL`，禁止继续 Stage2.5/Stage3。
- 轮询超时按 `total_reads`、几何和最近进展时间计算，不能再用“数万次轮询约几小时”
  的不可解释常数；超时日志必须包含最后进展时间戳。
- 对每个任务开始前清除旧错误和 DONE；错误后只允许显式 reset/retry，不自动把坏结果
  送给 LDPC。

**判据矩阵**：

| 场景 | 预期 |
| --- | --- |
| SE150 4,096 / 全量、SE250 4,096 / 32,768 | 图片哈希目标值，四级 DDR 全绿 |
| SE250 全量 129,600 | 不进入 `S_ERROR`，完成并通过目标哈希、四级 DDR、BD 计数 |
| 从机长延迟但持续 R/W 握手 | 不超时，输出逐位正确 |
| 强制无 `RVALID` 或无 `BVALID` | 在无进展预算内进入 `S_ERROR`，错误码可读，固件快速失败 |
| 错误后再次任务 | 清除旧错误、无旧 burst 残留，判据轮仍通过 |

### 3.2 B29：长计算期间保活与物理投递确认

**网络事件泵**：

1. 在 PS 主循环建立唯一 `eth_pump(now)`，在同一上下文调用
   `xemacif_input()`、`sys_check_timeouts()` 和必要的 lwIP 定时器；删除重复、互相
   不同步的定时器驱动，避免 RAW API 被多个时基同时推进。
2. Stage1/Stage2/Stage3 等待循环每 25~50 ms 让出一次 `eth_pump`，每次记录
   `last_pump_ms`、收到/发送/重传计数和硬件进展。不得在中断里调用 RAW API。
3. ARP 刷新限速：任务开始、长计算期间按秒级节奏单播请求，按几十秒级节奏
   gratuitous ARP；禁止每个 poll 无条件广播，避免保活自身造成拥塞。

**结果投递状态机**：

- 把 `enqueued_bytes`、`unsent_bytes`、`unacked_bytes`、`acked_bytes` 分开记录。
- 结果包头和 8,100 B 正文入队后持续 `tcp_output()` + `eth_pump()`，直到
  `unsent==NULL && unacked==NULL`，或者到达明确的投递超时。
- “settled”不是 `tcp_sndbuf()==TCP_SND_BUF`；发送窗口可能承载其他控制包。
  物理确认应由 lwIP ACK 回调累计，至少核对结果包覆盖的序号区间。
- 到达投递超时必须回报 `PKT_ERROR`/关闭连接并留下计数器，不能打印
  `Complete` 后静默返回；主机端应区分“未入队、未上线、部分 ACK、完整 ACK”。
- 长任务期间若 PCB 已关闭或进入错误状态，停止硬件后续阶段，避免把结果写入已失效
 连接；必要时由新连接重试，但必须明确任务是否可重放。

**B29 通过条件**：SE250 全量和“全量弄脏轮 -> 判据轮”各至少一次冷启动运行，
客户端实际收到完整包头和 8,100 B，`acked_bytes` 等于结果长度，图片哈希与四级
DDR 均通过；重复三次无 0-byte 结果和无未解释重传增长。

## 4. 从当前状态到工业级成品的路线图

### 阶段一：B30 闭环、SE250 全量与连续压测（近期致命问题清零）

**入口**：SE250 4,096/32,768 已通过；B30 现场证据完整；B29 探针已在工作树。
**工作包**：

1. `hw-timing` 完成无进展看门狗、错误寄存器和 AXI 故障注入；
2. `net-firmware` 完成 Voter ERROR 熔断、统一 `eth_pump`、结果 ACK 统计；
3. 重新 Vivado/Vitis/Bootgen 全套构建，校验同源 manifest；
4. `board-verify` 独占板卡执行 SE250 全量 129,600；
5. 在同一次上电中执行至少三轮：弄脏轮、跨规模判据轮、同参数重复轮；再做一次
   全量作为前置轮的连续任务。

**退出门禁**：

- `run_g3.sh --full --read-bps 250 --score-min 112` 返回单一 PASS；
- 图片 SHA-256 目标值，四级 DDR 4/4 全绿；
- TX/RX BD 计数、跨页拆分、Voter 读/写拍数与 manifest 一致；
- B30 故障注入能红、真实长任务不误报；
- B29 物理 ACK 完整，连续三轮无挂死、无性能退化；
- `tools/verify_repo_binding.sh --require-synced` 显示 `0/0`。

### 阶段二：双几何动态自适应与架构产品化

当前 `PKT_CONFIG` 已有 `read_bps/num_lc/stride/symbols/total_reads/score_min/CRC`，
但硬件几何仍是综合期常量。本阶段先做架构决策门：

1. **方案 A（优先评估）**：一个最大 250 bp bitstream，AXIS 使用 64 B 固定帧，
   以 `valid_bits/read_bps`、运行时 stride/ref_len、结果有效位掩码支持 150 bp；
   需要重新评估 BRAM、时序和 FIFO 深度，不能只改协议。
2. **方案 B（保守交付）**：SE150/SE250 保持两套已签名 bitstream，但共用一个
   支持 CAPS/manifest、自动选择制品、拒绝混用的固件和上位机发布包；这是先产品化
   再追求单镜像的可交付路径。

两种方案都必须：

- geometry manifest 带版本、数据集 ID、读长、位序、码长、默认阈值、DDR 预算和
  SHA-256；PS/主机/黄金脚本从同一 manifest 生成；
- CAPS 返回能力集合而不是单个 `read_bps`，CONFIG 返回明确拒绝码；
- 每次任务把 manifest/hash 写入 UART、结果日志和板级 summary；
- 每次 RTL 变化先跑 SE150 回归，再跑 SE250；黄金目录和 export 制品双套隔离。

**退出门禁**：两种几何均能冷启动闭环；错误几何在零数据下被拒绝；单镜像方案只有
在资源、时序、AXI 帧格式和两套板级哈希都通过后才可宣称完成。

### 阶段三：工业级长稳与抗扰

建立 24 小时自动运行器，覆盖：

- 任务规模、阈值和几何组合随机化；
- TCP 丢包、乱序/重传、ARP 老化、网线拔插、客户端重连；
- AXI 从机延迟、R/B 通道长停顿、单拍背压和故障注入；
- Stage1/2/3 watchdog、错误寄存器、软件重置、整板复位和幂等重试；
- DDR cache flush/invalidate、BD 环回、内存哨兵和输出哈希；
- 温度、电源、时钟/DDR 训练和 24 h 资源泄漏统计。

**工业门槛**：24 h 内零未解释任务失败、零数据静默截断、零错误后假 PASS；
任何注入都能在规定时间内进入可诊断状态；恢复后下一任务必须重新通过目标哈希和
四级 DDR，不允许沿用旧结果。

### 阶段四：跨平台上位机、遥测与一键交付

- CLI 与 GUI 共用一个协议/任务库；自动识别 FASTQ 读长并与 CAPS 双向协商；
- 展示连接、CONFIG、DMA、三阶段状态、进度、发送 ACK、错误码和最终哈希；
- Windows/Linux 打包，LDPC 实现明确选择和版本锁定，不把黄金 `result.txt` 等
  正确答案打进生产路径；
- CI 生成黄金向量、主机行为轨迹、RTL/XSim、固件 ELF、bit/XSA/BOOT.bin、
  SHA256SUMS、许可证清单和 SBOM；发布包附工具链版本与板级验收 summary；
- 生产模式默认禁止调试读 DDR，审计模式才允许导出四级快照。

## 5. 并行体系、互斥矩阵与板卡令牌

### 5.1 资源互斥矩阵

| Agent | 独占写目录 | 只读目录 | 严禁触碰 | 板卡/制品令牌 |
| --- | --- | --- | --- | --- |
| `hw-timing` | `hw/ip/`、`hw/sim/`、`hw/scripts/` | `docs/03`、`docs/20`、`tests/golden/` | `sw/app/`、`clients/python/`、`data/R0.83_data/` | 不占板；需要 `EXPORT_LOCK` 才能刷新 `hw/build/export/` |
| `net-firmware` | `sw/app/`、`sw/scripts/`、`tests/host/`（仅固件行为） | `hw/`、协议文档 | `hw/ip/`、`data/R0.83_data/` | 不占板；不得覆盖硬件 Agent 的 export |
| `board-verify` | `docs/board/run-logs/`、`tools/board/`、验收摘要 | 已签名制品、全部源码 | `hw/ip/`、`sw/app/`、`data/R0.83_data/` | 独占 `BOARD_TOKEN`；只读烧录输入 |
| `host-integration` | `clients/python/`、`tools/` 主机工具、主机测试 | 协议/黄金 manifest | `hw/`、`sw/app/`、`data/R0.83_data/`（只读） | 不占板；不改 `tests/golden/` 根目录 |
| `release-integrator` | `docs/` 交接、`hw/build/export/` 发布制品 | 四条线的提交与证据 | 未授权源码目录 | 独占 `EXPORT_LOCK`，负责带路径提交/推送 |

共享规则：

1. 所有 Agent 开工、阶段切换、阻塞和收工都必须使用
   `tools/agent_view.sh`；不得手改 `view.md`。
2. 只在 `main` 工作；禁止 `git add -A`/`git add .`，提交必须是
   `git commit -m "..." -- <路径>`，不得带 `Co-authored-by`。
3. `.git-data/index` 是共享资源；提交前由 `release-integrator` 协调暂停其它
   Agent 的 `add/commit/pull --rebase`，提交后立即 `git push origin main` 并核对
   `main...origin/main=0/0`。
4. `data/R0.83_data/` 只读。板卡一次只能有一个持有者；持有者在 view 看板明确
   `【持有 BOARD_TOKEN】`，运行、取证、释放后才能交给下一人。
5. 任何 RTL/固件变化都必须刷新同源 export；未完成板级判据时不得把“仿真 PASS”
   写成产品完成。

### 5.2 开箱即用子 Agent 提示词矩阵

以下模板可直接复制。每个 Agent 都必须先执行绑定门禁和 `agent_view start`，
并在结束时提交证据或明确阻塞原因。

#### `hw-timing`：硬件与时序专家

```text
你是 hw-timing，负责 B30 Voter RTL 无进展看门狗与接口级验证。
仓库：/home/lucian/projects/FPGA/FpgaAccelerationSystemOfDataReadout
先读 AGENTS.md、docs/03-status.md(B29/B30)、docs/20-se250-study-2026-08-30.md、
docs/25-master-product-plan.md；执行 bash tools/verify_repo_binding.sh --remote。
开工登记：
tools/agent_view.sh start --agent hw-timing --doing "审阅并重构 Voter 无进展看门狗" \
  --why "修复 SE250 全量 1 秒误杀并建立可诊断错误状态" \
  --next "运行 vot_ddr 故障注入，再做 Vivado OOC/整机构建"

只允许写 hw/ip、hw/sim、hw/scripts；不得改 sw/app、clients/python、data。
目标：
1. 在 GBK 文件上先判编码，采用安全转码->临时文件->os.replace 方式修改；
2. 用真实 AR/R/B/AW/W 握手定义 progress_event；无进展计时器只在活动且无握手时累加；
3. 保留 10 s 全局上限，但锁存 ERR_FLAGS、DBG_STATE=S_ERROR，停止新事务并遵守已接收 burst；
4. 固定 STATUS 的 IDLE/DONE/ERROR 位和错误清除语义，不能靠 DONE 假装成功；
5. 为 SE150/SE250 及无 RVALID/无 BVALID/背压场景添加逐位判据和故障注入。
验证：bash tools/run_xsim.sh vot_ddr；bash tools/run_xsim.sh all；
Vivado OOC/整机报告须记录 WNS/WHS、BRAM、LUT、错误数和产物 SHA256。
不要自行占用开发板，不要覆盖他人的 hw/build/export；完成后把构建交给
release-integrator。带路径提交并 push，最后：
tools/agent_view.sh done --agent hw-timing --doing "B30 RTL与仿真证据已交接" \
  --next "等待 release-integrator 刷新同源制品"
```

#### `net-firmware`：固件与网络专家

```text
你是 net-firmware，负责 B29 网络保活、Delivery Settled 和 B30 固件熔断。
先读 AGENTS.md、docs/05-interfaces.md、docs/22-ps-refactor-plan.md、
docs/03-status.md(B29/B30)、docs/25-master-product-plan.md；
执行 verify_repo_binding --remote，并用 agent_view.sh start --agent net-firmware 登记。
只允许写 sw/app、sw/scripts、tests/host；不改 hw/ip、clients/python、data。

必须完成：
1. 在 stage2_voter.c 轮询 STATUS、DBG_STATE、ERR_FLAGS；ERROR/S_ERROR 立即
   PIPE_FAIL，打印任务参数、读写拍数、最后 RRESP/BRESP 和进展时间；
2. 建立单一 eth_pump：主循环上下文执行输入、lwIP timeouts 和限速 ARP 刷新；
   Stage1/2/3 等待每 25~50 ms 服务一次，不能在 ISR 调 RAW API；
3. send_result 分离 enqueued/unsent/unacked/acked，有限重试并报告真实投递超时；
4. 保持寄存器写序列、缓存维护和行为轨迹不变；补主机故障注入；
5. 编译 ELF/BOOT.bin 但不覆盖未锁定的 export，写出 manifest/哈希候选。
验证：bash tests/host/run_host_tests.sh --worktree；
bash tests/host/run_host_tests.sh --selftest；必要时 make/XSCT 构建。
只提交你拥有的路径，禁止 Co-authored-by；板级运行须另行取得 BOARD_TOKEN。
```

#### `board-verify`：物理板级验证专家

```text
你是 board-verify，唯一持有 BOARD_TOKEN，负责 B30 修复后的 SE250 全量验收。
先读 AGENTS.md、docs/16-board-zynq-eco-7010.md、docs/23-next-phase-plan-2026-09-04.md、
docs/25-master-product-plan.md；执行 verify_repo_binding --remote；
登记：
tools/agent_view.sh start --agent board-verify --doing "核验签名制品并准备 SE250 全量板测" \
  --why "验证 B30/B29 修复是否达到真实物理闭环" \
  --next "确认制品哈希后独占板卡运行 run_g3"

只读使用 release-integrator 提供的 bit/XSA/ELF/BOOT.bin/SHA256SUMS；不得改 RTL、
sw/app 或 data。先确认 CAPS/geometry manifest 与板端一致，再执行：
bash tools/run_g3.sh --full --read-bps 250 --score-min 112 \
  --reads "data/R0.83_data/Sequencing data/DNA-40.5Kb-MC-SE250.fastq" \
  --tag se250-s7-full
判据必须同时满足：目标图片 SHA256、四级 DDR 4/4、Stage1/2/3 拍数、
TX/RX BD 计数、B30 无错误、B29 结果包头和 8100 B 全部物理 ACK。
随后同一次上电做三轮（弄脏轮->跨规模判据轮->重复轮）和全量前置轮。
所有 UART/socket/XSDB/dump/summary 写 docs/board/run-logs；结论以 PASS/FAIL
和证据路径表达，不把仿真当板级通过。释放板卡后：
tools/agent_view.sh done --agent board-verify --doing "板级证据已归档并释放 BOARD_TOKEN" \
  --next "等待 release-integrator 更新状态与推送"
```

#### `host-integration`：上位机与集成专家

```text
你是 host-integration，负责双几何客户端、协议遥测和发布集成。
先读 AGENTS.md、docs/02-data-contract.md、docs/05-interfaces.md、
docs/20-se250-study-2026-08-30.md、docs/25-master-product-plan.md；
执行 verify_repo_binding --remote 和 agent_view start --agent host-integration。
只允许写 clients/python、tools/主机工具、主机测试；data 与 tests/golden 根目录只读。

任务：
1. 从 FASTQ 读长和 CAPS manifest 选择 SE150/SE250；几何不匹配必须在 WM/BATCH
   前失败，错误码可读，不能静默截断/补齐；
2. 为 PKT_CONFIG、ACK、RESULT、Delivery Settled、错误/重试和版本兼容建立状态机；
3. CLI/GUI 共用协议库，显示硬件进展与物理 ACK，不把 tcp_write 入队当完成；
4. 加 mock/server 故障测试：错序、CRC、超长、丢包、重连、部分结果、错误码；
5. 生成发布 manifest、工具版本、LDPC 依赖、SBOM；确保生产包不含任何黄金答案旁路。
验证：主机单测、黄金模型、协议 mock 回归；不要宣称板级 PASS。
用带路径 commit 并 push，收工登记 agent_view done。
```

## 6. 最终交付判定

只有同时满足以下条件，项目才可称为工业级最终成品：

1. SE150 与 SE250 均在目标 ECO R6 实物上通过唯一图片哈希和四级 DDR 判据；
2. B29/B30 在正常、长稳和故障注入下均进入可诊断、可恢复状态；
3. 单一 manifest、版本化协议和签名制品能阻断几何混用与黄金旁路；
4. 24 h 抗扰运行无未解释失败，恢复后的下一任务重新通过完整判据；
5. 主机、固件、RTL、构建、板测证据和许可证/SBOM 可在干净环境复现；
6. Git `main` 与 `origin/main` 同步，交接文档、看板和发布包不留未说明的本地状态。
