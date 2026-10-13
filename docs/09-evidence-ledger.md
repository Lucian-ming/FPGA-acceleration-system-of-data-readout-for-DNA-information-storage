# 证据台账（Evidence Ledger）

> 2026-10-10：本台账保留历史结论及其适用范围，当前事实见03；原16中断审计全文在[合并归档](archive/history/2026/pre-bkb220-handoff-2026-10-10/interrupted-work-audit-2026-09-06.md)。原16的dump/哈希/复核命令仍随全文保留，不能把历史板结果当新板。

> **本文不叙述、不解释、不推销**，只做一件事：把每一条**可以对外说的话**
> 与它的**判据、证据路径、复现命令、边界**钉在一起。
>
> **编号约定**：现用文档一律带序号（本文为 `09`），归档文档一律**不带**序号
> （见 `docs/archive/history/2026/`）。这样从文件名就能看出一份文档是否还有效，
> 也不必再为「历史文档占了号」而跳号。
>
> **维护规则**
> 1. 结论变了就**改对应行**，不要新写一份叙述；失效的行标 ~~删除线~~ 并注明原因，不要删。
> 2. 每行必须能回答：**这句话凭什么？换台机器怎么重跑？它在什么范围内成立？**
> 3. 没有「证据路径」的行不许存在。没实测的东西写进 [08](08-performance-and-strategy.md)
>    的候选池，不写这里。
> 4. 最终状态以 [03](03-status.md) 为准；本文是它的**可复现索引**。

---

## 1. 正确性

| # | 可以说的话 | 判据 | 证据 | 复现 |
|---|---|---|---|---|
| C1 | SE150 真实测序数据端到端恢复原始图像，逐位一致 | 图片 SHA-256 `fcd0cf90…f2c3` | `g3_runs/20260910T*` 多轮 | `tools/run_g3.sh --limit 2048` |
| C2 | 四级中间结果逐字节吻合，不只是最终哈希对 | Stage1/Stage2⊕水印/Stage3 分别对黄金向量 | 同上，`board_stage_check.py` | 同上（脚本第 7/7 步） |
| C3 | 4-Way 与 2-Way 在生产几何下与**独立黄金模型**逐条一致 | 分数严格相等 + 位置属同分并列最大集，64/64 | `logs/iverilog/run_20260909_005333_*` | 见 `docs/benchmarks/stage1_4way_ip_integration.md` §6.3 |

> **C3 的坑**：`tests/golden/stage1_fwd_expect.txt` 里的位置在同分并列时由 FFT
> 浮点噪声决定（read 4 三个并列位置浮点值 `59.0 / 59.000000000000014 / 59.0`），
> **不能按单值比相等**，否则会把正确的 RTL 判成失败。并列集由
> `tools/make_stage1_tie_golden.py` 用整数精确滑窗生成。
>
> **G3 压测日志结构化**：多轮连续运行留证由 `tools/board/g3_runs_to_jsonl.py` 提取为逐轮机器可读的 JSONL（`tests/stress_results/*/continuous.jsonl`）。

---

## 2. 泛化与可重复

| # | 可以说的话 | 判据 | 证据 | 复现 |
|---|---|---|---|---|
| G1 | 6 类异构 payload 板端 100% 逐位恢复 | 各自独立源文件的 SHA-256 | `docs/benchmarks/measured_board_multi_payload.md` §3 | `tools/run_multi_payload_regression.py --mode check-dumps --extended` |
| G2 | **21 次板端运行，结果逐位可重复，零抖动** | 每数据集 3 次原始误码数完全相同 | `logs/multi_payload/repeat3_20260910T200339Z/` | `... --mode board --extended --repeat 3` |
| G3 | 高熵失败是**确定性算法边界**，非随机故障 | @60 稳定 0/3 失败、@65 稳定 3/3 通过 | 同 G2 | 同 G2 |
| G4 | **误接受率有定义且已测**：`score_min=67` 时干净数据 FAR **0.44%**、FRR 0% | 逐记录判真/诱饵/错位，FAR = 垃圾票占被接受记录的比例 | `docs/benchmarks/measured_g5_false_accept.md`、`logs/g5_matrix/run1/` | `python3 tools/g5_false_accept.py --dataset tests/datasets/D1_text_manifesto --limit 2048` |
| G5 | **替换错误不影响误接受率，插删才是主因** | sub 0→4% 时 FAR@67 恒 ~0.5%；ins=del 0.1% 时升到 8.9%，且成因由「诱饵」变为「真错位」 | 同上，7 个噪声点 × 3 种子 | `bash tools/run_g5_matrix.sh` |
| G6 | **阈值法在纯替换下的边界是 sub ≈ 4%** | 真记录最低分与诱饵最高分的间隔在 4% 处归零（+4.0 → ±0.0） | 同上 §3.1 | 同上 |

**G2 的具体数字**（这是比「6/7 通过」更强的证据）：

```text
D0 42/42/42   D1文本 16/16/16   D1几何 7/7/7   D1稀疏 09/09/09
D1高熵@60 2671/2671/2671   D1高熵@65 236/236/236   D2 20/20/20
```

**边界**：3 次重复只支撑「该制品、该输入下确定性可重复」，
**不能**外推为任意输入的可靠率；板端回传真实，但 LDPC 译码与哈希比对在主机侧。

---

## 3. 性能（口径最容易走样，逐条钉死）

| # | 可以说的话 | 数据 | 证据 |
|---|---|---|---|
| P1 | 板端耗时模型（当前固件，P13） | `T = 0.480 s + 0.2451 ms × N_records`，R²=0.9996；全量 SE150 中位 **25.69 s = 2,016 reads/s** | `docs/03` P13，`g3_runs/20260922T11*`、`20260922T12*`，18 点 |
| P1a | 每记录成本≈Stage1 PL 理论周期 | 实测斜率 0.2451 vs 4-way 理论 0.2436 ms/记录（差 0.6%）；去掉运行期休眠 `[PIPE] total` 逐毫秒不变 | `docs/03` P13 |
| P1c | **PL 比同片 ARM 快约 49x** | 单核 Cortex-A9（-O3 NEON）12.10 ms/记录 vs PL 0.2451 ms/记录；ARM 结果与主机参考 1,024/1,024 逐条一致 | `docs/benchmarks/measured_arm_baseline.md`，`arm_baseline/20260922T152202Z-n1024` |
| P1b | 较早的 P0 修复后模型（已被 P12/P13 取代） | `T = 1.505 s + 0.5656 ms × N_records`，R²=0.986 | `logs/overhead_sweep/`，7 档 × 3 次 |
| P2 | 修复前模型 | `T = 5.284 s + 0.5157 ms × N_records`，R²=0.996 | `logs/overhead_sweep/20260910T075540Z/` |
| P3 | 板端固定开销压缩 **3.5x** | 5.284 s → 1.505 s | 同上两行对比 |
| P4 | 演示规模端到端提速 **1.8x** | 2,048 源读段 7.315 s → 4.123 s | 同上 |
| P5 | 4-Way 顶层加速比（生产几何仿真） | 3,229,621 → 1,674,217 周期 = **1.929x** | `logs/iverilog/run_20260909_005333_*` |
| P6 | 4-Way 整机时序收敛 | WNS **+0.246 ns** @100 MHz，失败端点 0 | `logs/vivado/recovery_20260909/physopt/` |
| P7 | 独立硬件周期实测拆解非 Stage1 耗时 | 4096 记录下 Voter 29.627 ms (0.93%)、Decoder 0.022 ms (0.0007%)，总 PL 硬件执行不足 30 ms；非 Stage1 耗时 62.9% 的 99% 以上是 PS 侧 lwIP poll 空等 (2,777 ms) 与 Cache 维护 (396 ms) | `docs/benchmarks/measured_p7_cycle_counters.md`、`g3_runs/20260911T140559Z/` |

### ⛔ 不能说的话（每条都有实测支撑其为假）

| 说法 | 为什么不能说 |
|---|---|
| 「比 CPU 快 / 加速 N 倍」（不加限定） | 全量 SE150 **板端实测 2,016 reads/s**（P13）：只比**单核** C 快 1.48x，比 16 线程**慢 6.9x**。只能说「快于单核」且须同时给出多核对照。（旧的 0.77x、1,055 reads/s 是 P12 之前的外推，已作废） |
| 「优化 Voter / Decoder 硬件流水线能显著提升端到端性能」 | **板端硬件周期实测证伪**：4,096 条记录下 Voter 执行仅 29.6 ms (0.93%)，Decoder 仅 0.02 ms (0.0007%)，就算两核执行时间降为 0，端到端提速也不足 1%。瓶颈 99% 在 PS 侧 lwIP poll 空等与 Cache 维护，硬件并行化方向已彻底关闭 |
| 「固定开销优化提升了吞吐」 | 只对小规模成立。全量占比仅 9%，修复后全量 58.7 s → 60.1 s **略差** |
| 「纯硬件三级流水线」 | **Stage 2.5 跑在 ARM 上**（`apply_watermark_differential()`），见 `docs/01` |
| 「低功耗 / 能效优势」 | **功耗一个数字都没测**，无功率计 |
| 「误接受率低说明系统鲁棒」/「FAR 就是失败率」 | FAR 衡量的是**累加器污染程度**，不是任务成败：`D2_controlled_noise` 在板端 `score_min=65` 下 FAR **21.76%**，却 **3/3 逐位恢复** |
| 「score_min=67 是最优阈值」 | 67 = `int(0.45×150)`，是设计时选的比例**不是测出来的**。纯替换场景实测 τ=70 才给 FAR=0%；但插删场景抬阈值换不来干净 |
| 「8-way 还没做」 | 是**做不了**：4-way 已占 LUT 88.0%，8-way 外推 ~125% |
| 「WNS +2.197 ns 说明整机时序好」 | 那是**单模块 OOC**；同一设计整机默认策略下是 **−0.252 ns 不收敛** |

---

## 4. 工程与可复现

| # | 可以说的话 | 判据 | 证据 |
|---|---|---|---|
| E1 | 制品与源码**可证同源** | 符号级比对 + 分段比对 | `docs/archive/history/2026/pre-bkb220-handoff-2026-10-10/status.md` P0b（历史符号/分段同源复核） |
| E2 | 时序收敛可复现，非偶然 | impl 策略已固化进 `hw/scripts/build.tcl` | commit `1e4e746` |
| E3 | 异常连接可恢复 | 断网/半截包头/坏 magic/RST 注入后恢复恒 2.02 s | `tests/stress_results/g6_postfault_*/` |
| E4 | 判据有鉴别力，不是只会报 PASS | 故障注入会红；`wm_regions.hex` 几何哨兵 | `tools/make_golden.py` 内置哨兵 |
| E5 | 演示不依赖预生成结果 | 四幕现场出哈希，含一幕**预期红灯** | `tools/run_demo.sh`，2026-09-10 实跑 |

> **E1 的方法学（重要）**：**整文件 SHA-256 发现不了制品与源码不同源。**
> 2026-09-10 实测：出厂 `SHA256SUMS` 当时完全自洽，但那份 ELF **不含**源码里
> 已有的 B29/B30 修复（`arp_keepalive` 在 ELF 中出现 **0 次**）。
> 整文件哈希只证明「文件没被改动」，**不证明「文件由该源码构建」**。
> 有鉴别力的判据是：
> ```bash
> arm-none-eabi-nm <elf> | grep <源码里新增的函数名>      # 符号级
> arm-none-eabi-objcopy -O binary --only-section=.text ... # 分段比对
> ```

---

## 5. 已知失败与负结果（**必须保留，不得从统计里消失**）

| # | 失败项 | 现象 | 判定 | 证据 |
|---|---|---|---|---|
| F1 | 高熵 payload @ 出厂门限 60 | 原始误码 2,671 bit，LDPC 50 轮未收敛 | **已知边界**，稳定 0/3 复现；@65 可恢复 | `logs/multi_payload/repeat3_*/` |
| F2 | 8-way / 128×4 展开 | LUT 外推 ~125% | **资源证伪**，不再排期 | [08性能策略的旧分析边界](08-performance-and-strategy.md#2-旧分析的适用边界)，原7010资源报告在合并归档competition-strategy.md中 |
| F3 | 流式阶段批量推进（两次尝试） | `submitted=640 > ring free=512`，Stage1 挂死 ~30 s | **放弃**：剩余收益上限仅 1.11x | `g3_runs/20260910T113222Z`、`115133Z` 的 `uart.log` |

> **F3 的教训**：原设计「一帧一个 poll」不只是浪费，**它同时是 BD 环的节流机制**。
> 两次失败都用错了控制变量（第二次用 RX ring 余量，但 `ring free` 恒为 512，
> 门限从未触发）。正确的控制变量是**在飞帧数**或 DMA 完成中断。

---

## 6. 本轮（2026-09-10）新增的过程教训

这些不是结论，是**方法层面的坑**，写下来避免重复踩：

1. **留证通道断了 = 没有留证。** 固件早就打印了 `[PIPE] total %u poll steps`，
   注释还写着「下一个人就不必再靠分档拟合去反推常数项」——但 UART 没接，
   **这行字从未被读到**，于是同一个根因被用分档拟合重查了一遍。
   串口不通时应改用 XSDB 读内存符号（`tools/board/read_pipe_counters.tcl`）。
2. **不要在被测对象上做「顺手探测」。** 板端 lwIP 是单例 `g_conn`，
   一次 TCP 探测直接把正在进行的 G3 弄成 FAIL，浪费一轮板测。
3. **先确认工具语义再用。** `--no-post` 是「不发送 POST 触发命令」（板子根本不算），
   不是「不做 LDPC 译码」，导致首轮扫描全部作废。
4. **`pgrep -f` 会匹配到自己的命令串。** 等待循环因此永远不退出，
   误判「板卡忙」多轮。用 `ps -eo cmd | grep -v` 之类不自匹配的写法。
5. **代码里的警告要当警告读。** `stage1_dna.c` 的 `PIPE_WM_TX` 分支写着「原实现靠下一个 poll
   才回收，天然有 250 ms 余量」——这句话同时解释了开销**和**节流机制，
   只读出前半句就会拆掉后半句（F3）。

## 7. 2026-10-10/11 迁移准备证据

| 可以说的话 | 判据/原始证据 | 边界 |
|---|---|---|
| 正式LC50 P4/P16模块与真实包装通过 | [集成摘要](benchmarks/stage1-16way-ip-integration.md)；D:/Agent/outputs/bkb220-xsim26/run-20261010-a4两个case及14文件SHA；Icarus模块同周期 | 无新板route/G3；约3.27倍仅模块cycle |
| 47项主机门禁通过 | [主机摘要](benchmarks/bkb220-host-verification.md)；logs/host/g3-preflight-20261010/all_host_tests.txt | fixture/替身，不是板测 |
| 现代软件入口实际完整构建核验 | [工具摘要](benchmarks/bkb220-toolchain-audit.md)；D:/Agent/outputs/bkb220-vitis26/logs-a14/vitis.log与export-a14/software_build_config.json | 旧ECO XSA兼容探针，不是新板包 |
| 正式源/参数与实际catalog包装通过 | [集成摘要](benchmarks/stage1-16way-ip-integration.md)；logs/vivado/stage1_ip_catalog_20261010_2110 | 默认P4，BKB220 ready=0 |
| 2026-10-11用户提供的BKB220 v1.1产品手册已随仓库收录，副本与原件字节一致 | [资料索引](board/bkb220/README.md)、[PDF](board/bkb220/BKB220产品手册v1.1.pdf)及[SHA256SUMS](board/bkb220/SHA256SUMS.txt)；SHA `40b50e66…c8cd086`；在docs/board/bkb220运行`sha256sum -c SHA256SUMS.txt` | 只证明所收录文档一致；不证明实物型号、PS7配置或新板验收；缺项见03/07 |
| 6个历史工具原样退役、22主开发/26下载/最后26复核顺序已同步 | [整理记录](reference/tool-cleanup-2026-10-11.md)；logs/host/tools-cleanup-route-20261011：启动器4/G3主机47/公平基准8/固件2/打包/卫生11 PASS；归档源码SHA/权限、135个链接与Windows镜像核验 | 主机/工具/文档验证及Vitis22安装后能力核验通过；无新板构建/下载/验收 |
| WSL Vitis2022.2补装成功，实际XSCT与ARM编译器可用 | D:/Agent/outputs/fpga-migration-handoff-20261010/vitis22-installation-verification-20261011-a2/verification.json：Vivado2022.2、XSCT2022.2.0六命令、GCC11.2.0、Cortex-A9 ARM32对象编译全部PASS | 仅工具安装与能力验证；没有生成新BSP/应用/FSBL/BOOT或触板，完整软件链继续按05/07验证 |

Icarus重复接口已在XSim正式通过后停止，不称Icarus接口PASS。起点重复附件告警及唯一源引用修复记录保留，边界见[整理记录](reference/workspace-cleanup-2026-10-10.md)。全项目门禁与当前Agent任务见05/07。

## 8. 2026-10-12 接管与新板现场实测

| 可以说的话 | 判据/原始证据 | 边界 |
|---|---|---|
| BKB220 已到货并连接，器件经 JTAG 证实为 **xc7z020**（IDCODE `0x23727093`），单目标链 | 2026-10-12 main 实测：JTAG 链 `Xilinx HW-Z1-ZCU104 FT4232H 15051A` → `arm_dap (4ba00477)` → `xc7z020`；原始输出 `logs/jtag/20261012T112212Z-bkb220-wsl-jtag/probe3.txt`（`logs/` 被 .gitignore 覆盖） | 只证明 JTAG 上识别到的器件与 IDCODE；**不证明**完整料号/温度等级/PCB 修订，也不证明任何 PS7/DDR/MIO 配置 |
| PS 处于干净的 JTAG 待机态，`BOOT_MODE=0`，DDR PLL 掉电、FCLK0 关闭、GEM 与两个 UART 均未启用 | 同一目录 `state_read.txt` 的寄存器读数 | 读数反映 BootROM 状态，不代表板级设计；不能据此推断 PS UART 的 MIO |
| **PS_CLK = 33.333 MHz** | `IO_PLL_CTRL` FBDIV=26 → IO PLL 433.33 MHz，且 BootROM 正常执行 | **推导 + 寄存器证据**，非厂商书面确认；ps7_init 实跑训练后应复核 |
| **分工：开发在 WSL 用 2022.2；Windows 2026.1 只负责烧录**（用户 2026-10-12 明确） | [03 §1b](03-status.md)、[07 §3a](07-board-build-and-acceptance.md)；22 主线构建证据见 P4/P16 benchmark | 这是**工具链约定**，不是功能/时序结论。F9 仍按计划用 26 做完整开发链独立复核 |
| Windows 主机两次蓝屏（**用户 2026-10-12 确认已解决**） | 用户 2026-10-12 诊断：两次 BugCheck `0x139`/参数1=`0xA`，进程均 `hw_server.exe`，栈均 `ftdibus+0xf4d4`；修复记录在 `D:\Agent\outputs\ftdi-repair-20261012\`。用户随后统一 FTDI 驱动到 `2.12.36.20`、确认 USB 供电即可，并确认 Windows 26 可用于烧录；另有一条**已验证可用的回退路径**：WSL `usbipd` 直通 + Linux 2022.2 hw_server（F3 即如此完成） | 用户已于同日自行处置并确认风险解决，故 Windows 26 按正常烧录路径使用。**但具体修复项未入仓**：这是环境所有者的判断，不是本项目独立复现的结论。原始证据保留在仓库外；若再出现同类异常，有已验证的 WSL 22 路径可用 |
| P4/P16 正式源集与打包一致、无未覆盖文件；打包与卫生门禁 PASS | main 复跑 `bash tools/check_ip_packaging.sh`（exit 0）、`bash tools/check_repo_hygiene.sh`（exit 0，11 项） | 子 Agent 只读沙箱内报的 packaging FAIL 是沙箱无法建临时输入所致，非真实缺陷；已由 main 复跑否定 |
| 候选 BKB220 PS7 profile 的 `ready=0` 守卫有效 | `tclsh hw/scripts/build.tcl board=bkb220 dry_run=1` → exit 1，在 `dna_load_board` 的 ready 守卫处失败，未进入 `file_create`/`create_project`，未建目录 | 只证明守卫与 Tcl 结构；**不证明** PS7 属性被 Vivado 2022.2 catalog 接受 |
| 候选 PS7 属性经 Vivado 2022.2 逐条验证；`MT41K256M16TW-107` 被 catalog 拒绝 | [来源表 §8](board/bkb220/migration-source-table.md)；原始日志与逐属性 TSV 在 `hw/build/bkb220-ps7-probe/20261012T114440Z-board-migrate-r3/`（该目录已被 .gitignore 精确覆盖，不入库也不自动删除） | 属性被接受只说明属性名/取值合法，**不证明**与实物 PCB 接线一致；DDR 改用 `Custom` 后仍属推导参数 |
| **BKB220 新板 DDR 训练可用** | `ps7_init`/`ps7_post_config` RC=0；`0x10000000` 起 1024 字写入后逐字回读 **0/1024 不符**；原始输出 `logs/bringup/20261012T120117Z-bkb220-f3-v1/f3.out`（`logs/` 已忽略） | 证明该配置下 DDR 可读写；**不等于**板级延迟/DQS-to-CLK 已确认或已优化，也不等于 QSPI/SD 冷启动或整机 G3 通过 |
| **BKB220 PS UART 归属已实测确定：UART0 / MIO14-15 → FT4232H 通道 C（`/dev/ttyUSB2`）115200 8N1** | 经 JTAG 直接写 UART0 TX FIFO，三路串口同时被动抓取：`/dev/ttyUSB2` 收到 `BKB220-UART0-1..8` 共 128 B 且 ASCII 完全正确，另两路 0 B；证据同上一行目录 | 只证明 PS→PC 方向；**反向（PC→PS）未测**。ASCII 正确即证明 115200 波特率正确 |
| BKB220 PS 时钟：PS_CLK 33.333 MHz、DDR PLL 533.33 MHz(DDR3-1066)、FCLK0 100 MHz | 回读 `0xF8000104/0x0108/0x0170`：DDR PLL FBDIV=32、IO PLL FBDIV=30 且 FCLK0 分频 5、`0xF800010C`(=PLL_STATUS)=0x3F 三 PLL 全 lock | 由寄存器回读与 PLL 公式推出，非频率计实测 |
| **BKB220 ENET0 配置在真板可用：PHY = Realtek RTL8211E，1000BASE-T 全双工 link up** | 经 JTAG 用 MDIO 读 PHY：reg2/3 = `0x001C`/`0xC915`（OUI `0x001CC9`，model 0x11 rev5 → RTL8211E）、reg1 BMSR `0x7969`（link up）、reg6 ANER `0x000F`、reg10 `0x78FF`（1000BASE-T 全双工）；证据 `logs/bringup/20261012T120117Z-bkb220-f3-v1/phy_dump.out`。网线经用户确认为板子直连主机 ASIX 网卡，其 1 Gbps 与本项互证 | 证明 RGMII MIO16-27 + MDIO MIO52-53 这组 PS7 属性在真板可用、PHY 型号与链路状态。**不证明** TCP/CAPS 或整条 G3 通过（那要固件） |
| ~~BKB220 ENET0/PHY 未通过~~（作废） | 早前记「MDIO 全地址无应答」并推测需原理图，**该结论错误且已作废**：实为 main 读错完成标志（应读 `NETWORK_STATUS[2]`，不是 `PHY_MAINT`）且漏写 MDEN（`NETWORK_CONTROL` bit4 = `0x10`）。改对后 PHY 正常应答，见上一行 | 保留此条是为了留下「把自造 bug 误判成硬件缺项」的方法教训：寄存器级探测应先对照厂商驱动头文件核位定义 |
| **BKB220 P4 与 P16 整机在真实器件上完成完整 route 且 100MHz 时序全通过** | [benchmark](benchmarks/bkb220-p4-p16-100mhz-build.md)；原始报告 `<P4\|P16>/reports/timing.rpt`、`util.rpt`、`impl_1/*drc_routed.rpt`（main 亲自复核计数）。P4 WNS+0.680/WHS+0.036/失败端点 0/51,506；P16 WNS+0.617/WHS+0.017/失败端点 0/86,415；两者 `Design State=Physopt postRoute`、`Device=xc7z020clg400-2`、DRC 0 errors、`clk_fpga_0`=100.000MHz | 仅**构建与静态时序**。不证明板端下载/启动/功能/G3 通过，也不是性能倍率。两设计各有 20 项 `REQP-1839/1840`（异步复位 BRAM）与 P16 的 16 项 `DPOR-1` 警告未清理，须在 F6 状态复位板测专门核对 |
| P16 整机资源 33,987 LUT（63.89%），与 rtl-16way 先验 33.9k/64% 吻合 | 同上 `util.rpt` | 先验被实测印证；旧板 XC7Z010 仅 17,600 LUT，这是 P16 在旧板不可行的直接原因 |
| **BKB220 新板 F4 整机 G3 通过：板端回传经 LDPC 重建的 JPEG SHA-256 与判据逐位相同** | [来源表 §13](board/bkb220/migration-source-table.md)；留证 `D:\bkb220_board_smoke\g3_runs\20261012T142924Z\`（`uart.log` 含 `autonegotiation complete`）；包 `hw/build/bkb220-p4-enet0-software-20261012T140800Z-board-migrate/`，`SHA256SUMS` 59 项 OK、`g3_artifacts.py` 预检 exit 0。7 步全 PASS | **2048 源读段（4096 板端记录）smoke 档**；全量≥3 次、连续/脏干净、断连恢复、性能矩阵、泛化/长稳**均未做**。板上是 **P4**，**P16 未上板**。不等于迁移完成 |
| 判据侧 bug：`run_g3.sh` 因 `uart_cap.out` 的 **CRLF** 把"收到 7781 字符"误判成"没有可确认的输出" | 实测：首轮 G3 除串口外全 PASS，串口那步误报 FAIL；加 `tr -d '\r'` 归一化后复跑全绿，`run_g3.sh` 内已注释说明原因 | 该文件由 Windows 侧脚本写、行尾 CRLF，`$` 锚点被 `\r` 顶掉。**这会把 PASS 稳定报成 FAIL、污染每次验收结论**，已修并回归（53 项主机用例 PASS） |
| 新板脚本适配完成一轮，门禁未放宽 | `python3 -m unittest discover -s tests/host -p 'test_g3_*.py'` 53 项 PASS；`tests/host/run_host_tests.sh --worktree`、`check_ip_packaging.sh`、`check_repo_hygiene.sh` 均 exit 0；新板缺 `--artifact-dir` 的负例在临时移除严格门禁后按预期变红 | 主机/工具层验证；本轮**未触板**跑过 G3，也不代表新板 CAPS/G3 通过 |
| **BKB220 同板 P4/P16 六档性能矩阵（各档 3 次）**：每条记录成本 **0.2519→0.0814 ms（3.10×）**；固定开销 0.4529→0.4182 s 基本不变；全量档 **26.5393 s → 8.9486 s（2.97×）** | [benchmark](benchmarks/bkb220-p4-p16-performance-matrix.md)；原始留证 `logs/g3/c1-matrix/{p4,p16}/{plan.json,samples.jsonl,summary.json,*client.log}`（`logs/` 已忽略）。两轮分别是 P4 `…p4-enet0-software-20261012T140800Z…`、P16 `…p16-enet0-software-20261012T144141Z…` 的独立整包烧录，`plan.json` 记 bit/ELF/XSA SHA、`P_WAYS`/`PIPE_TREE`、输入 FASTQ 与水印 SHA | **性能采样**，只有全量档 `correctness_required=true`（两轮 SHA 均 `fcd0cf90…b1f2c3` PASS）；其余五档 `NOT_REQUIRED_PARTIAL_INPUT`，部分输入不构成完整码字。`hardware_cycles`/`power_w` 为 `null`（未接外部 UART 采集），**不得用墙钟×时钟冒充**。CAPS 不含 `P_WAYS`/`PIPE_TREE`，**TCP 层无法区分板上是 P4 还是 P16**，身份只由本轮烧录的制品包立。P16 全量档方差明显大于 P4（stdev 346 ms vs 19 ms），引用须给三次原始值 |
| P16 矩阵前的板上身份确立步骤，`run_g3.sh --limit 128 --skip-dump` 末尾报 `G3 FAIL` | 同留证目录 `p16-boot.out`：完整制品一致性 PASS、烧录 PASS、CAPS `READY 6.1 1` PASS、串口 7744 字符 PASS、四级取证 SKIP；唯一 FAIL 是部分输入的 LDPC 步骤（无唯一判据） | **该 `G3 FAIL` 不是硬件故障**，是 `--limit 128` 部分输入 + 唯一判据不可得的必然结果。引用此日志时必须同时说明，否则会被读成板卡失败 |
| **C2 泛化：v2 challenge 集全量上板，板端判定与软件验证器 42/42 完全一致** | [来源表 §18](board/bkb220/migration-source-table.md)；留证 `logs/g3/c2-v2-challenge/SUMMARY.tsv` + 逐例 `<asset>-<class>.out`，板侧 `D:\bkb220_board_smoke\g3_runs\20261013T04*Z\`。42 例 = 21 资产 × baseline/challenge，各用**该资产自己的水印**、**全量输入**（8192 源读段 → 16384 板端记录）、`score_min=65`、P4 包；5 类非 JPEG 载荷走新的 `--input-bytes` 裸字节通路。结果：baseline 21/21 过，challenge 13 过 / 8 失败，**与软件的 13/8 同一批** | 8 个失败例的失败模式全部是 **LDPC 硬判决 50 轮不收敛**（残余失败校验 279~5192），**不是译出错误字节**——失败必须保留，不得降难度后宣布泛化通过。板端与软件一致只说明**两者同算法同判据**，不证明真实测序误差下的恢复率。本轮 `--skip-dump`（四级取证对新载荷仍不适用）；**P16 对本套数据未测**；数据是 in-silico 模拟，非湿实验 |
| **P16 跑同一套 v2 42 例：板端 P4 / 板端 P16 / 软件三方逐例一致，且 34 个成功例上 P4 与 P16 判据 SHA 逐例相同** | [来源表 §18.5](board/bkb220/migration-source-table.md)；留证 `logs/g3/c2-v2-p16/SUMMARY.tsv` + 逐例 `<asset>-<class>.out`，P16 包 `hw/build/bkb220-p16-enet0-software-20261012T144141Z-board-migrate`。三方一致 **42/42**，不一致 0 例；P16 轮 0 例烧录/就绪失败 | 证明 P16 在这套数据上与 P4 **位对位等价**、不是近似实现。**不证明** P16 在 R0.83 以外的其他几何（如 SE250）等价；也未测 `score_min=67` |
| **真载荷性能交叉验证：42 例真实任务的 P4/P16 中位耗时与 C1 矩阵 16384 记录档吻合** | [来源表 §18.6](board/bkb220/migration-source-table.md)。同一轮扫描的客户端打印值：P4 中位 4.470 s、P16 中位 1.720 s，逐例加速比中位 **2.57×**（范围 1.58~3.11×）；42 例中 36~37 例记录数正是 16384，C1 矩阵该档独立测得 4.5809 s / 1.7623 s（2.60×） | 该耗时是**客户端打印值**，与矩阵 `t_result` 同口径（POST→8100B 收齐，不含上传与 LDPC），**不是 `hardware_cycles`**；本轮无周期与功耗采集。逐例倍率差异主要来自记录数与调度抖动，不得据此断言"某类载荷更快" |
| **B2 收口：三个故障探针在 P16 包上全部通过，且折腾完判据轮仍逐位正确** | [benchmark](benchmarks/bkb220-p16-fault-probes.md)；留证 `logs/g3/b2-probes/`（`config_guard.jsonl`、`recovery-p16-cycles3.jsonl`、`netfault.jsonl`、`judgement-after-probes.out`）。配置/容量守卫 **7/7**（含「恰好等于上限必须被接受」的反例，越界在写发生前被拒）；畸变包/断连 **30/30**（10 类 × 3 遍，恢复 2.01~4.50 s，恒 1 次尝试）；中途断网 + SIGKILL **3/3**（2.02~2.03 s），`iptables` 无残留。随后同一 P16 实例跑全量 `score_min=67` 判据轮：`fcd0cf90…b1f2c3` **逐位相同** | 探针证明的是**协议/连接层**恢复与守卫**拒绝行为**；数据通路正确性只由那轮判据轮承担，两者不可互替。`power_w` 全为 `null`（无功率计）。**长稳 2h/8h 仍未做**——短时故障恢复不等于长时稳定。`score_min=67` 因此项在 **R0.83** 全量档被顺带验过，但 **v2 数据集仍未在 67 下测** |
| **外部 v2 数据包的哈希清单与「旧包未被改动」声明，经 main 独立复核成立** | [来源表 §18.7](board/bkb220/migration-source-table.md)。`sha256sum -c` 对 v2 包 **612/612 OK**（exit 0）；对 v1 旧包 183 条逐字节比对 **183/183 相同**、不同 0、缺失 0 | 只证明该外部包**自身完整、且 v1 未被 v2 生成过程改动**；**不证明**包内 FASTQ 的生物学真实性（仍是 in-silico 模拟），也不证明其噪声模型正确。⚠️ 复核时 `SHA256SUMS` 是 CRLF 行尾，不归一化会把 612 条全报成 `FAILED open or read`——与 `run_g3.sh` 那条 UART 判据 bug 同源，跨 Windows/Linux 的哈希清单校验必须先怀疑行尾 |
| **冻结的 P4/P16 制品包与当前工作树源码逐字节一致** | main 2026-10-13 用各包 `reports/source_manifest.json` 逐条 SHA 比对：60 条源条目中 **59 条相同、0 条不同、1 条缺失**（缺失项即 manifest 的 `excluded_files`：`sw/app/xparameters.h`）。故本轮测得的每条记录成本（P4 0.2519 ms / P16 0.0814 ms）**就是**当前 `sw/app/` 这份源码跑出来的 | 只证明「制品包 ↔ 工作树源码」的对应关系；**不证明**该源码与更早历史留证（如 2026-09-11 的 P7）出自同一版本——恰恰相反，见下一行 |
| **P7 的「lwIP poll 空等 2,777 ms」评测于 2026-09-11，早于 P12-B 事件驱动改造，已不代表当前固件** | `docs/benchmarks/measured_p7_cycle_counters.md:3` 记评测日期 2026-09-11、留证 `g3_runs/20260911T140559Z/`，正文第 110 行把「固件状态机改造为事件/中断驱动」列为**待做建议**；当前源码 `sw/app/main.c:326` 已是 `/* 3) 主动推进流水线 (P12-B 事件驱动，消除 poll 白等) */` + `echo_pipeline_poll()`，`docs/03` P13 行亦记「主循环事件推进/cache 优化保留」 | 该 2,777 ms **不能**再当作当前固件可回收的时间。P3 的起步实验改为 `sw/app/main.c:28-30` 的 `PIPE_RUN_SLEEP_US`（默认 `200U`，源码注释称「每条记录的斜率由这一行决定」，并提供 `-DPIPE_RUN_SLEEP_US=N` 覆盖开关）的 A/B；**但 `docs/03` P13 明记「不能盲删 200us 节流」**（Voter/Decoder 曾按 poll 次数误超时，后改 30 s 墙钟超时），A/B 必须复验唯一判据 SHA、30 s 超时路径与多轮轮间行为 |

2026-10-11 Agent承载通道补充：logs/agents/handoff-channel-20261011-a2/result.json、events.jsonl及final.md证明现有代理下gpt-5.6-luna/max的只读调用退出0、turn.completed与JSON哨兵通过；这是Agent运行环境证据，不是FPGA功能、时序或真板验收证据。用户目标gpt-6-luna 已由 2026-10-11 00:40 codex-luna MCP 的冒烟与真实派发实测可用（11.7s / 34.0s，均 completed/ok/exit0/turn_completed，更正提交25c3336）；b3c70b3 依据的旧 CLI 0.147.0 拒绝是客户端版本问题，不是账号权限。

2026-10-11文档/引用残留清理：logs/host/current-residue-20261011/documentation-integrity.json记录全仓当前引用和连续01～09校验；对应备份verification.json记录Python AST（除文档/帮助引用）、C/HDL词法标记及Shell非注释行不变，ECO PS7参数仅来源文档路径变化。固件2项、G3主机47项、基准契约8项、IP打包和卫生通过；基准首次缺PYTHONPATH的失败保留，正确命令见tests/host/README.md。源码副本单向同步前有备份，原BSP/ELF未重建。此记录不扩张新板功能/时序/性能结论。
