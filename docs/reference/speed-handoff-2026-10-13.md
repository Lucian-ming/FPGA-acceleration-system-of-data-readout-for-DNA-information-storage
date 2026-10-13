# speed 主线交棒文档（2026-10-13）

本文是 `speed` 主线（「在不改变结果正确性的前提下压缩时间消耗与资源占用」）的交接载体。
**接手者读完这一份就能继续，不需要问上一任。**

- **唯一判据（全程未变）**：板端回传经 LDPC 译码后的载荷 SHA-256 =
  `fcd0cf90bd680e7bbdc203e3398119504da0897acac9e2117008b4efb6b1f2c3`。
- **底稿**：[bkb220-p16-time-budget.md](../benchmarks/bkb220-p16-time-budget.md)（整轮墙钟分解、板端 PL/PS 分解、函数级预算）。
- **本线新增**：[bkb220-p16-speed-a-upload.md](../benchmarks/bkb220-p16-speed-a-upload.md)（A 组上传段的完整测量与结论）。
- 最后提交：`f9ebbd0`；`main...origin/main` = **0/0**。

---

## 1. 一句话结论

**全量档整轮墙钟 14.25 s → 10.18 s（同小时参考包对照，−28.6 %），唯一判据 SHA 逐位不变。**
省下的 4.07 s **全部来自读段上传段**（4.26 s → 0.20 s，≈21×）；
板端处理段（`t_result`）**一动没动**（同小时 9.34 → 9.33 s）。

**对 CPU 的倍率本轮没有改变**，要如实说：

| 板端口径 | 全量 | 每记录 | 对单核 C | 对 4 线程 C | 对 16 线程 C |
| --- | ---: | ---: | ---: | ---: | ---: |
| 仅板端处理（`t_result`，同小时） | 9.33 s | 0.0900 ms | 快 2.43× | 慢 1.14×（基本打平） | 慢 2.37× |
| **端到端**（上传+处理+LDPC） | **10.18 s** | **0.0982 ms** | 快 2.23× | 慢 1.24× | 慢 **2.58×** |

⚠️ **两边口径不同**：CPU 数只算比对内核；`t_result` 是端到端里的一段，端到端那行还含上传、水印、
DMA、Voter、协议与固定开销 —— 所以这个对照**偏向 CPU**，板端一旦打平，实际是赢的。
（底稿 §2.4 的「16 线程慢 2.14×」用的是今晨的 `t_result=8.68 s`；同小时口径见上表。）

---

## 2. 逐项改动表

| # | 改了什么 | 为什么能省时间 | 改前 → 改后（实测） | 判据 | 结果 |
| --- | --- | --- | --- | --- | --- |
| **A2** | **`sw/app/main.c`**：空闲主循环的 `usleep(1000)` 提成宏 `PIPE_IDLE_SLEEP_US`（**默认值不变**）；派生包用 **0** | BSP 是 `NO_SYS=1`，Xilinx `xemacpsif_input()` 的取包 `while(1)` **整个在 `#if !NO_SYS` 里** → 裸机下一次 `xemacif_input()` 只取一帧。上传时流水线未启动、走「空闲」支，吞吐 ≈ 1514 B ÷ 一圈耗时 | 上传段全量 **4.27 s → 0.19 s**（四档 × 3 次中位 ≈22×） | 全量 `--runs 3` SHA 逐位不变 + `--strict-artifacts` G3 PASS | ✅ **通过** |
| **A2'** | **BSP `lwipopts.h`**：`TCP_WND 2048 → 32768`（`tools/build_sw_variant.sh --lwip-opt`） | 窗口 2 KB 时发送方经常无帧可发；放大后发送端持续有帧在飞 | 单独只 **4.18 → 3.22 s（1.23×）**；与 A2 合起来才有 15.5× | 同上（两处一起验证） | ✅ 通过（**单独不足以解决问题，但缺它达不到 0.19 s**） |
| **工具** | **`tools/build_sw_variant.sh`** 新增 `--lwip-opt NAME=VALUE` 与 `--sync-src` | ① lwIP 开关烧在 `liblwip4.a` 里，应用侧 `-D` 盖不住，必须重建 BSP 库；而 BSP Makefile **没有头依赖跟踪**，不删 `.o` 会「成功但一个文件都没重编」→ 脚本重建后**校验库 SHA 确实变了**，静默无效即变红；② 改 `.c/.h` 时派生包必须从权威源 `sw/app` 重新同步 | — | 脚本自检 + bit/XSA/ps7_init/FSBL 与参考包逐字节相同 | ✅ |
| **工具** | **`tools/profile_upload.py`**（新） | 把上传段拆成「客户端预处理 / 本机回环停等对照 / 板端小包 RTT 探针」，前两段**不触板**即可跑 | — | 已登记进 `tools/README.md`（卫生门禁 PASS） | ✅ |

**改动面很小**：只有 1 处固件源码（且默认行为不变）、1 处 BSP 编译期开关、2 个工具。
**没有动任何 RTL，没有动协议语义，没有动 `run_g3.sh`。**

### 2.1 完整实测数据

四档 × 3 次上传扫描（`--no-post`，只跑上传段），**两包各烧一次板、背靠背测**：

| 源读段 | 负载 | 参考包（`WND=2048`，眠 1000 µs） | 新包（`WND=32768`，不休眠） | 加速 |
| ---: | ---: | ---: | ---: | ---: |
| 2,048 | 163,840 B | 0.17 / 0.17 / 0.17 s | 0.01 / 0.01 / 0.01 s | ≈17× |
| 8,192 | 655,360 B | 0.67 / 0.67 / 0.67 s | 0.04 / 0.03 / 0.04 s | ≈17× |
| 32,768 | 2,621,440 B | 2.70 / 2.70 / 2.69 s | 0.13 / 0.12 / 0.14 s | ≈21× |
| 全量 51,781 | 4,144,640 B | 4.27 / 4.26 / 4.26 s | 0.19 / 0.19 / 0.26 s | ≈22× |

参考包吞吐恒定 7.76～7.80 Mbps（**不随规模变化**，正是「一圈一帧」的特征）；新包 125～177 Mbps。

### 2.2 ⚠️ 一条必须继承的测量纪律：`t_result` 同一天内会漂移

**今晨**（六档矩阵）全量 `t_result` 中位 = **8.682 s**；**同一天傍晚**把参考包重新烧回板子重测 = **9.33 / 9.34 / 9.34 s**，
**+7.5%**。如果拿新包的 9.33 s 去比今晨的 8.68 s，会得出「**优化让处理段慢了 7.5%**」这个**假结论**。

→ **任何 A/B 都必须同小时重测参考包**，不能引用几小时前的数字。
（漂移的原因本轮**未定位**，只记录了现象；`t_result` 本身是客户端打印值，不是硬件周期计数。）

---

## 3. 失败与放弃的项（**留证保留，不删除**）

| 项 | 试了什么 | 为什么不成 | 留证 |
| --- | --- | --- | --- |
| **「逐批 ACK 停等是上传瓶颈」**（底稿 §5 第 2 项的猜测） | 只改 `--batch`：500 / 1000 / 2000（批次数 208 / 104 / 52） | **实测否掉**：批次数降到 1/4，上传耗时只降 6%（4.25 / 4.18 / 3.98 s）。吞吐被**每字节**的东西限住，不是停等 | `docs/benchmarks/bkb220-p16-speed-a-upload.md` §2.2 |
| **`batch=2500`** | 想再放大批 | **板端拒绝**：`process_batch` 的上限是 `tcp_recv_buffer[100000]`，客户端 `BrokenPipeError`。有效上限约 2,499 条/批 | 同上 |
| **`TCP_WND` 单独作为解** | `WND=32768`、其余不变 | **单独立不住**：只 1.23×（4.18 → 3.22 s）。真正的限速器是轮询周期，窗口只是第二重限制 | 同上 §3.1 |
| **归因点「仅去掉空闲休眠、`WND` 保持 2048」** | 包已造好（`bkb220-p16-idle0-wnd2048-20261013T090815Z`，ELF `785a140b…`） | **本轮未上板测**（时间预算）；按模型外推 `WND/RTT ≈ 2048 B ÷ ~0.4 ms ≈ 5 MB/s → 约 0.8 s`，即窗口那时才会真正成为瓶颈。**这是外推，不是实测**，留给接手者 | 包在仓库里，未测 |

**本轮没有任何"改坏了"的失败**：每一次上板 G3 都是 PASS，判据 SHA 全程逐位不变。

---

## 4. 未做项（判定不做 / 来不及做，附理由与建议）

| 项 | 现状 | 理由 | 建议 |
| --- | --- | --- | --- |
| **A3：上位机 LDPC 与下一轮重叠** | **未做** | 0.653 s，占新口径整轮 **6.4%**。要改的是 **`tools/run_g3.sh` 的逐轮循环**（把 `ldpc_decode.py` 放后台、与下一轮 `first.py` 并行，循环尾 join 后再比 SHA）。**动的是验收脚本本身**，改完必须重跑 ≥3 轮全量判据自证没改坏 —— 本轮预算不够把"改 + 自证"一起做完 | 值得做：改动小、逻辑清晰。注意 `run_g3.sh` 是所有验收的入口，改完必须自己先跑一遍完整 `--full --runs 3` |
| **C 组（PL）多碱基并行 K=2/K=4** | **只做了只读设计与探针方案，未实施、未探针** | 这是**结构性 RTL 改动**（参数化 `srpe_batch_pway` → 接顶层/`component.xml`/`PACKAGED_VARIANTS.txt` → OOC 探针 → 整机 route → 全量功能回归）。**改了不验的 RTL 不能进主线**，本轮时间不够 | **这是唯一能改变"对 CPU 倍率"的方向**，优先做。见 §6 |
| **上传段零拷贝** | 未做 | 剩余上限只有 0.19 s（4.14 MB ÷ 0.19 s ≈ 21.8 MB/s ≈ 千兆的 17%），再往下要动 `pbuf_copy_partial` + DDR `memcpy` 的零拷贝，收益低 | 不建议 |
| **提高 PL 时钟（100 → 106+ MHz）** | 未做 | WNS 仅 **+0.617 ns**、最差路径 84.5% 是布线，**不是免费加速**；任何时钟改动都要以 SHA 逐位不变为门禁 | 与 C 组一起评估，别单独做 |
| **`PIPE_IDLE_SLEEP_US=0` 的空闲功耗** | **未测** | 空闲时主循环满速自旋，功耗会升高；**本项目无功率计**，如实记未测。流水线阶段不受影响（仍按 `PIPE_RUN_SLEEP_US=200`） | 若有功率计，值得量一下；若无，接受现状 |
| **8 h 长稳** | 未做（2 h 已完成） | 不在本轮任务边界内 | 按 `docs/05` 的 D 项排期 |

---

## 5. 复现命令

```bash
# 造派生包（bit/XSA/ps7_init/FSBL 与参考包逐字节相同）
bash tools/build_sw_variant.sh \
  --ref hw/build/bkb220-p16-enet0-software-20261012T144141Z-board-migrate \
  --out hw/build/bkb220-p16-swwnd32k-idle0-<TS>-board-migrate \
  --lwip-opt TCP_WND=32768 --define PIPE_IDLE_SLEEP_US=0 --sync-src \
  --label "H-A1b: TCP_WND 32768 + 空闲不休眠 + sw/app 权威源同步"

# 烧录 + 全量判据 x3（板卡独占；Windows XSDB + COM10 路径）
bash tools/run_g3.sh --artifact-dir <新包> \
  --xsdb D:/xilinx/2026.1/Vitis/bin/xsdb.bat --device xc7z020 --strict-artifacts \
  --uart-port COM10 --ip 192.168.1.10 --port 7 --win-root D:/bkb220_board_speed \
  --full --runs 3

# 四档 x 3 次上传扫描（两包各烧一次背靠背；--no-post，不触发流水线）
bash tools/board/g3_upload_sweep.sh <tag>

# 纯上位机的两段（不触板）
python3 tools/profile_upload.py --loopback
python3 tools/profile_upload.py --rtt-probe 192.168.1.10:7 --rtt-samples 300
```

**留证路径**（`logs/` 与 `hw/build/` 不入库，文件保留）：

| 路径 | 内容 |
| --- | --- |
| `tools/board/g3_upload_sweep.sh`（已登记进 `tools/README.md`）；本轮原始表在 `logs/g3/speed-a-upload/sweep-{ref-wnd2048-idle1000,new-wnd32k-idle0}.tsv` | §2.1 四档 × 3 次原始表 |
| `logs/g3/speed-a-upload/full-idle0-runs3.out` / `full-ref-control-runs3.out` | 新包 / **同小时参考包**全量 `--runs 3`，均 G3 PASS |
| `logs/g3/speed-a-upload/{offline-b1000,rtt-probe-baseline}.json` | 离线三段拆分与板端 RTT 探针 |
| `D:\bkb220_board_speed\g3_runs\*` | 每轮 `first_run*.log` / `uart.log` / `artifact_selection.json` |
| `~/.local/state/codex-subagent/runs/20261013T085911Z-8abf8eed49/` | `stage1-multibase` 只读子 Agent 的 prompt/answer/日志 |

---

## 6. C 组（PL）的具体交接：这是下一步该做的事

**为什么是它**：板端处理 9.33 s 里 **PL 约 8.2 s（87.8%）**，PS 侧全部可归因工作只占 2.1% ——
**把 PS 侧清零也只到 7.77 s**。要缩短与 16 线程 CPU 的距离，只有 PL。

只读子 Agent `stage1-multibase` 已给出（**均为静态推导/外推，无 OOC、无综合、无板测**）：

- **现状**：`srpe_batch_pway.v` 的 `S_RUN` 每拍只推进**一个**碱基索引，并行比较
  **16 起点 × 64 记录 = 1024** 个匹配位；`score` 是寄存器数组（16×64×10 位）；Stage1 OOC 基线 26,867 LUT / 8 RAMB36。
- **K=2**：`S_RUN` 150 → 75 拍，每块 176 → 101 拍；整机外推 36k～40k LUT。
- **K=4**：`S_RUN` 150 → 38 拍，每块 176 → **64** 拍；整机外推 **40k～48k LUT**
  （上限 53,200，**高端只剩约 5.2k 余量**）；读段 BRAM 要按奇偶 bank 拆、水印要 4 bank。
  **全量估算 ≈ 3.91 s**；再与「7 拍选优排空」重叠 ≈ **3.60 s**（目标 3.70 s）。
- **真正的门槛是时序，不是 LUT**：现 WNS 仅 **+0.617 ns**，最差路径 84.5% 是布线。
- **预充/排空重叠**：`S_PREFILL 18` + `S_UPD1 5` + `S_UPD2 1` + `S_NEXT 1` 现在串行，
  可重叠**上限 7 拍**；K 路预充可再把 18 拍压到 ≈11（K=2）/ ≈7（K=4）拍。

**先做实现探针，不要直接上板。** 入口 `docs/submission/skill/fpga-timing-probe/ooc_probe.tcl`
（`SYNTH_IMPL=1` 会真的布局布线；**综合-only 的 WNS 不可作收敛判据**）：
先把 `BASES_PER_CYCLE` 参数化进 `srpe_batch_pway`，再对 K=2/K=4 各跑一次，
看 `util.rpt` / `util_hier.rpt` / `timing.rpt`。

**能变红的判据**：

| 阶段 | 判据 |
| --- | --- |
| OOC 探针 | WNS ≥ 0、WHS ≥ 0、TNS/THS = 0、失败端点 0、受约束时钟路径存在；Stage1 LUT ≤ 40,000；K=4 RAMB36 ≤ 12；DSP 增量 0 |
| 整机 | BKB220 `xc7z020clg400-2` 完整 route、`clk_fpga_0=100 MHz`、WNS/WHS ≥ 0、失败端点 0、DRC 0 errors；LUT ≤ 48,000 |
| 上板 | 生产几何回归覆盖 K=4 最后一组无效 lane / `STRIDE` 边界 / 选优并列；全量 103,616 条 ≥3 轮 SHA 逐位 = `fcd0cf90…b1f2c3`；端到端低于 **3.70 s** |

**纪律**：先写下判据再动手；**改了不验的 RTL 不进主线**；
新制品必须走 `tools/run_vivado_build.sh` 并重签 `SHA256SUMS`。

---

## 7. 当前状态（接手前必读）

| 项 | 状态 |
| --- | --- |
| 最后提交 | `f9ebbd0`；`main...origin/main` = **0/0** |
| Git 绑定门禁 | `tools/verify_repo_binding.sh --require-synced` **PASS** |
| 工作区 | **干净**，无未提交改动 |
| 卫生门禁 | `tools/check_repo_hygiene.sh` **PASS**（含 `sw/app` 与 workspace 副本一致） |
| 主机侧回归 | `tools/run_sim.sh host` **通过 6 项，失败 0 项** |
| 后台进程 | **无**板卡/长稳/EDA 任务；`iptables` 无注入规则 |
| 看板 | 无残留"进行中"条目 |
| **板子当前固件** | **冻结 P16 参考包** `bkb220-p16-enet0-software-20261012T144141Z-board-migrate`（ELF `595482d8…`）——本轮最后一次烧的就是它，**板子处于参考包状态** |
| 板卡在线 | `192.168.1.10:7` 可达；串口走 **Windows COM10**（WSL 侧无 `/dev/ttyUSB*`） |

**冻结参考包（不得就地修改）**：

- P16：`hw/build/bkb220-p16-enet0-software-20261012T144141Z-board-migrate`（ELF `595482d8…`，BOOT `afb296dd…`）
- P4：`hw/build/bkb220-p4-enet0-software-20261012T140800Z-board-migrate`

**本轮新建的实验包**（非冻结，可直接复用）：

| 包 | 内容 | ELF SHA-256（前 16） | 状态 |
| --- | --- | --- | --- |
| `bkb220-p16-swwnd32k-20261013T090000Z-board-migrate` | 仅 `TCP_WND=32768` | `8a3f4326f807bfc1` | 已上板测过，**不是推荐配置** |
| **`bkb220-p16-swwnd32k-idle0-20261013T090540Z-board-migrate`** | **`TCP_WND=32768` + `PIPE_IDLE_SLEEP_US=0` + `sw/app` 同步** | **`643056444dabe6b2`** | **推荐配置**，全量 `--runs 3` G3 PASS，四档 × 3 次已测 |
| `bkb220-p16-idle0-wnd2048-20261013T090815Z-board-migrate` | 仅 `PIPE_IDLE_SLEEP_US=0`（`WND` 保持 2048） | `785a140ba770826a` | **未测**，见 §3 的归因点 |

（另有两个更早的实验包 `bkb220-p16-prof-*` / `bkb220-p16-prof200-*` 与三个 `sw-throttle*` 包，
都是本线之前的工作，未改动。）

> **⚠️ 注意：推荐配置尚未"转正"。** `sw/app/main.c` 里的宏**默认值是 1000 µs（原行为）**，
> 只有派生包用 `-DPIPE_IDLE_SLEEP_US=0` 时才改变；`TCP_WND=32768` 也只在派生包的 BSP 里。
> **冻结参考包的源码与制品都没被动过。** 是否把这两项提升为新参考包（并重跑长稳/泛化），
> 由接手者或用户决定 —— 本轮只做到"验证通过、结论入库、**不覆盖已冻结制品**"。

---

## 8. 下一步建议（按优先级）

1. **把推荐配置转正**（小、明确）：用 `sw/app` 当前源码 + `TCP_WND=32768` 重建一份**完整** P16 包
   （走 `create_vitis.tcl` 正式流程，而不是 `build_sw_variant.sh` 的派生路径），把 `TCP_WND` 的改动
   **写进 `sw/scripts/create_vitis.tcl`**（现在只存在于派生包的 BSP 里），再跑一遍全量 + 泛化 + 2 h 长稳。
   *在此之前，不要拿派生包当发布制品。*
2. **A3（LDPC 重叠）**：改动小、收益 6.4%，见 §4。
3. **C 组 PL 的 OOC 探针**：见 §6 —— 这是唯一能改变"对 CPU 倍率"的方向。
4. **补测归因点**（§3）：`bkb220-p16-idle0-wnd2048-…` 那个包已造好，测一次就能把
   「窗口 vs 轮询」的贡献切成 2×2。
5. **别忘的纪律**：任何 A/B **同小时重测参考包**（§2.2）；底稿 §5 的第 1、2 项已关闭，
   **第 3 项仍开放**。
