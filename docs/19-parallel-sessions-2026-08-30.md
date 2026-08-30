# 19 · 并行会话简报（2026-08-30，G3 闭环之后）

本文供**多个并行会话冷启动**使用：先说清楚「离真正做完还差什么」，
再给三段可直接粘贴的会话提示词与互斥约定。

排队与判据以 `docs/18-next-steps-2026-08-30.md` 为准，事实状态以 `docs/03-status.md` 为准。
本文只解决「怎么把剩下的活并行分出去」。

---

## 1. 现在在哪

**G3 已闭环**（2026-08-30 第五次上板）：板端回传经 LDPC 译码后图片 SHA-256 =
`fcd0cf90bd680e7bbdc203e3398119504da0897acac9e2117008b4efb6b1f2c3`，与判据逐位相同。

但闭环**只在一组参数下成立**：2,048 条源读段（`--orient both` → 4,096 条记录）、
`score_min 67`、SE150、单次任务。

---

## 2. 离「做完」还差什么

以本机实测的单次循环成本估算（不是拍脑袋）：

| 动作 | 实测耗时 |
| --- | --- |
| Vivado 全量重建（综合+实现+bit+XSA） | ≈ 10 min |
| `xsct` 重建 ELF | 1–2 min |
| 上板一轮（烧录 + `first.py` + dump DDR） | ≈ 5 min |
| `run_xsim.sh all` | 5–8 min |
| `run_sim.sh` | ≈ 5 min |
| `run_m2_full.sh` | ≈ 30 min |
| DNA 核单次 `xelab` | 5 min 以上（单线程，加核帮不上忙） |

剩余环节：

| 环节 | 内容 | 估时 | 不确定性 |
| --- | --- | --- | --- |
| **A** | `tools/run_g3.sh` 一键复现 | 1–2 h | 低 |
| **B** | 分档测量 + 超时改造（见 §3 的坑） | 1–2 h | 低 |
| **C** | 全量数据集跑通（103,552 条记录） | 1–2 h | 中 |
| **D** | 二次任务 / 状态复位 | 1–3 h | **高** |
| **E** | 项目整理、文档收口、清理构建垃圾 | ≈ 1 h | 低 |

**合计半天到一天，D 是不确定性的主要来源**——那块至今零证据，
如果状态复位真的有问题，可能牵出 RTL 改动，就要再加一轮综合（10 min）+ 上板（5 min）。

C 的中等风险来自规模效应：RX BD 环回绕从 3 次变成 **101 次**、TX 从 64 帧变成 1,618 帧，
以及 `srpe_batch` 的 partial batch idle timeout 路径在最后一批的行为。

之后是可选项，不在「做完」的关键路径上：SE250 几何参数化（数天，要改 RTL 重新综合）、
性能优化（瓶颈至今没量化过，必须先测量）。

---

## 3. 一个必须先知道的坑（否则 C 会白跑一轮）

**全量数据集有撞穿上位机 180 s 超时的风险，而且这个风险至今没有被测量过。**
板端固件与 RTL 不用改、容量也够
（103,552 条 ≤ 上限 `TASK_MAX_READS` 107,968；Stage1 输出 4.74 MB ≤ 预算 4.94 MB），
**但上位机必须改**：

`clients/python/protocol.py` 的 `recv_exact` 用 `sock.settimeout(timeout)`，
`first.py:629` 传 180 s；而板端从收到 `PKT_POST` 到 `send_result()` 之间
**一个字节都不发**（`echo.c` 的 `poll_callback` 只在 `PROC_DONE` 才发结果）。
所以 180 s 不是「两次进度打印的间隔」，而是**整条流水线处理时长的上限**。

实测 4,096 条记录的 result 阶段 32.4 s，但**这 32.4 s 的内部拆分至今没测过**，
全量会不会超时完全取决于拆分：随条数线性增长的部分占大头就必然超时，
与条数无关的常数项占大头则可能只增加几秒。两种可能都存在，别先入为主。

注意别误读客户端那两个计时：`t_result` 是「发完 POST 到收完结果」的**全部板端时间**
（水印预载 + Stage1 + Stage2 + Stage3 + 回传），`读段 0.35s` 是**上传耗时**，
两个都不是某一级的处理时间。

**不要一上来就跑全量**——先分档测量（4,096 → 8,192 → 16,384）做线性拟合，
截距是常数项、斜率是每条成本，再决定怎么改。撞上超时会分不清是超时还是流水线真挂了。

---

## 4. 三个会话的分工

**开发板是唯一的硬串行点，只能一个会话独占。** 真正能并行的是不碰板子的工作。

| 会话 | `--agent` 名字 | 板子 | 主要改动范围 | 冲突风险 |
| --- | --- | --- | --- | --- |
| 1 | `g3-scale` | **独占** | `sw/app/`、`clients/python/`、`tools/run_g3.sh` | — |
| 2 | `voter-ddr` | 禁止 | `hw/sim/`、`tools/run_m3_bd.sh` | 低 |
| 3 | `se250-study` | 禁止 | 只产出 `docs/` | 无 |

### 共同前置（每个会话都要做）

```bash
cd /home/lucian/projects/FPGA/FpgaAccelerationSystemOfDataReadout
bash tools/verify_repo_binding.sh --remote     # 强制门禁，未通过禁止任何开发
tools/agent_view.sh start --agent "<上表名字>" --doing "..." --why "..." --next "..."
```

### 互斥约定

- **只有 `g3-scale` 可以碰开发板**（JTAG / XSDB / COM6 / `D:\dna_board_smoke\`）。
- **`se250-study` 这一轮不许改任何 RTL**：`g3-scale` 可能重建 ELF，
  `voter-ddr` 在跑仿真，一改 RTL 就会污染他们的构建。这个坑本项目已经踩过一次
  （两个会话共享工作区，未提交的 RTL 被另一方烤进了 bitstream）。
- 三方都会改 `docs/03-status.md`，**提交前务必 `git pull --rebase`**，
  不要用 `git add -A`，按文件显式 `add`。
- 机器 16 线程，避免同时启动两个大型综合；长任务启动前先 `agent_view.sh update`。

---

## 5. 会话提示词（可直接粘贴）

### 5.1 会话 1 —— `g3-scale`（独占开发板）

```
接手 FPGA DNA 项目 /home/lucian/projects/FPGA/FpgaAccelerationSystemOfDataReadout。
先完整读 AGENTS.md、CLAUDE.md，再读 docs/19-parallel-sessions-2026-08-30.md（本简报）、
docs/18-next-steps-2026-08-30.md（排队与判据）和 docs/03-status.md 的「第五次上板」一节。
动手前跑 bash tools/verify_repo_binding.sh --remote 过门禁。
view.md 登记名用 g3-scale。

【你独占开发板】另有 voter-ddr、se250-study 两个会话并行，它们都不碰板子。

背景：G3 已闭环，但只在「2048 条源读段 / --orient both / score_min 67 / SE150 / 单次任务」
这一组参数下成立。你的任务是把边界推到能交付的程度。按顺序：

1.【P0】把 G3 做成一条命令可复现：写 tools/run_g3.sh，串起
   uart_cap.ps1 → boot tcl → first.py → ldpc_decode.py → sha256sum → board_stage_check.py，
   给出单一 PASS/FAIL 和非零退出码。判据能被一条命令复现才算真的钉住——
   否则下一个人还要重新摸索，而这轮的经验是摸索本身就会引入错误。
   先用当前这组参数跑通它、复现出同一个哈希，作为工具自身的判据。

2.【P1】分档测量并解决超时。**先读本简报 §3**：板端处理期间一个字节都不发，
   所以 first.py:629 的 180 s 是整条流水线的时长上限，不是打印间隔。
   用 --limit 4096 → 8192 → 16384 分档测，拟合「固定开销 + 每条耗时」，
   再决定是把 timeout 调大，还是给板端加心跳/进度包
   （后者要动协议，但顺带给长任务可观测的进度，以后换规模不用重调超时）。

3.【P1】全量数据集。51781 x2 对齐 64 = 103,552 条记录 ≤ 上限 107,968；
   Stage1 输出 4.74 MB ≤ 预算 4.94 MB，所以板端固件与 RTL 不用改。
   判据仍是同一张图片 SHA-256 = fcd0cf90bd680e7bbdc203e3398119504da0897acac9e2117008b4efb6b1f2c3。
   规模效应要盯：RX BD 环回绕 3 次 → 101 次、TX 64 帧 → 1618 帧、
   srpe_batch 的 partial batch idle timeout 在最后一批的行为。
   若要改固件，只重建 ELF，不要重建 bitstream（RTL 没动）。

4.【P1】二次任务 / 状态复位。同一次连接内连续跑两次任务，
   判据是**两次都拿到同一张图片哈希**。docs/12 §11 早就列了
   「二次任务是否真正清零 Voter 累加器」，至今零证据。天然雷区：
   B27 的 START 语义、B21 的 BD 环指针、Voter 累加器、Stage3 的 done 清除时机，
   任何一个没复位干净都会在第二次翻车。

5. 顺带量化性能：现在 4096 条约 33 s，瓶颈至今没测过。
   流水线由 lwIP tcp_poll 驱动、间隔 500 ms，水印预载 50 个区域要走 100 次 poll
   是明显嫌疑。**先测量再优化**，不要在没有数据的情况下动 Stage1 架构。

板上环境（已验证，照抄别重摸）：Windows 侧 D:\dev_tools\Vivado_Lab\2022.2\bin\ 的
vivado_lab.bat / xsdb.bat，从 WSL 用 cmd.exe /c 调用；工作目录 D:\dna_board_smoke\；
JTAG Digilent 210251A08870，器件 xc7z010_1；串口 CH340=COM6@115200
（要用 Win32_PnPEntity 才查得到，一次只能一个进程占用）；
主机 192.168.1.100/24，板子 192.168.1.10，WSL 可直连 TCP:7。
烧录用 boot2.tcl 或 boot_b27.tcl，只读 DDR 取证用 dump_ddr.tcl。
制品在 hw/build/export/，bif 是 sw/boot/dna_board_b27.bif。
历次上板的 dump 备份在 D:\dna_board_smoke\run4_dumps\，别覆盖。
两个坑：mrd -value 返回十进制（比较前先 format %08x）；
XSDB 默认禁止访问 PL 地址（0x4000_0000+），所以只读 DDR 里的中间结果取证。

判据纪律：仿真全绿、界面成功、TCP 返回结果都不算数，唯一判据是图片 SHA-256。
本轮 7 个缺陷里有 5 个在所有仿真里都是绿的，只有上板才暴露。
每次上板后跑 python3 tools/board_stage_check.py 做四级取证，
它内置了 B23/B25/B26 的特征签名，同类问题回归能立刻认出来。
结论写进 docs/03-status.md 与 docs/18；改动 RTL 或固件后必须整套重建
hw/build/export/ 并刷新 SHA256SUMS。
提交前 git pull --rebase，不要用 git add -A，按文件显式 add，push 到 origin/main。
```

### 5.2 会话 2 —— `voter-ddr`（纯仿真）

```
接手 FPGA DNA 项目 /home/lucian/projects/FPGA/FpgaAccelerationSystemOfDataReadout。
先完整读 AGENTS.md、CLAUDE.md，再读 docs/19-parallel-sessions-2026-08-30.md（本简报）、
docs/18-next-steps-2026-08-30.md 的 §5「接口判据现状」，
以及 docs/13-xsim-simulation-plan.md 的 §7.2 与 §十（判据纪律）。
动手前跑 bash tools/verify_repo_binding.sh --remote 过门禁。
view.md 登记名用 voter-ddr。

【硬约束】你禁止碰开发板：不许 JTAG、XSDB、串口 COM6、不许动 D:\dna_board_smoke\。
板子由 g3-scale 独占。你只跑仿真。启动长任务前先 agent_view.sh update 说明在跑什么。

背景：2026-08-29~30 修掉的 7 个缺陷里，B23/B24/B25/B26/B27 五个**在所有仿真里都是绿的**，
全部落在同一条缝上：仿真喂黄金数据、板上走真实 DMA/DDR/寄存器接口。
这轮已补出四条接口判据（run_xsim.sh 的 result_axis / ingress_result / dec_restart、
run_m3_bd.sh 的 bd3b）。**还剩最后一个已知缺口，就是你的任务**：

  Voter（differential_voter_v1_0）的 AXI 读通路至今没有走过真实 DDR。
  M3 的 BD-3ext 虽然逐位通过，但喂它的是 AXI VIP 内存模型，
  不是「PS 用 CPU 写 DDR → Voter 用 AXI 主口读 DDR」这条板上真实通路。
  B27 的教训正是：Decoder 喂 VIP 内存连综合后网表都 PASS，板上照样错。

任务：
1. 给 Voter 补一条真实 DDR 级判据。直接照搬 hw/sim/dec/tb_dec_ddr_restart.v ——
   它已有「类 DDR 时序从机 + 回放固件原样寄存器写序列 + 已接受的读突发不因主机复位而取消」
   的完整骨架，是最省事的参考。hw/sim/dna/tb_dna_result_axis.v 则演示了
   「用真实 DUT、force 内部信号注入黄金记录、逐拍比对、随机背压」的写法。
2. 判据必须逐位，不是「跑完没报错」：输入用 tests/golden/stage2_in.hex（4096 条 48B 记录），
   输出比 tests/golden/stage2_rtl_expect.hex（异或水印**之前**的 Voter 原始输出；
   注意 sparse_expect.hex 是异或之后的，别比错）。
3. **必须做故障注入自检**：像 b26 在 bd3b 里那样，force 一条线制造已知缺陷，
   证明这条判据真的会 FAIL，否则你无法证明它有鉴别力。
   run_m3_bd.sh 里有 judge_inject_log 的写法可参考
   （注入档不能用通用 judge_log，因为日志里本来就有 FAIL 行）。
4. 接进 tools/run_m3_bd.sh 或 tools/run_xsim.sh，一键可复跑。

三个已知的坑，别再踩：
- **XSim 2022.2 的 $fatal 既不终止仿真也不让 xsim 非零退出**，会一路跑到看门狗。
  失败路径必须显式 $finish，并用 if/else 保证失败时绝不打印 PASS。
  但注意：若 $fatal 是单语句 if 的 body，补进去的 $finish 会变成无条件执行、
  仿真 0 fs 就退出还 exit=0 —— 必须包 begin/end。
- **XSim 2022.2 打印 SystemVerilog string 里的非 ASCII 会变乱码**（%s / %0s 都一样），
  TB 里的 label 一律传 ASCII。
- hw/ip 下部分 RTL（尤其 Dna_accelerator_core_v1_0.v）是 **GBK 编码**，
  用 UTF-8 直接读写会把注释写成不可逆的 U+FFFD（已发生过一次，只能从 HEAD 重打补丁）。
  必须按字节安全方式读写（latin-1 或 surrogateescape 往返），
  且 open(p,'wb') 会在参数求值前就截断文件，先写临时文件再 os.replace。
- TB 里的 forever 驱动要有上限：tb_m3_bd3_extmem.sv 的 forever send_*ready
  无限排队撞了 VIP 的 500 上限，日志刷到 16 GB 被 OOM 杀。

判据纪律见 docs/13 §十：编译通过、跑完、有波形都不算 PASS；每个用例要有显式 PASS/FAIL、
非零失败退出码、超时保护、逐位比较。不得为了变绿放宽判据或屏蔽 X/Z。
结论写进 docs/03-status.md 并更新 docs/18 §5 的判据现状表。
提交前 git pull --rebase，不要用 git add -A，按文件显式 add，push 到 origin/main。
```

### 5.3 会话 3 —— `se250-study`（纯分析，零冲突，可选）

```
接手 FPGA DNA 项目 /home/lucian/projects/FPGA/FpgaAccelerationSystemOfDataReadout。
先完整读 AGENTS.md、CLAUDE.md，再读 docs/02-data-contract.md（数据格式唯一权威）
和 docs/18-next-steps-2026-08-30.md 的 P2 第 5 项。
动手前跑 bash tools/verify_repo_binding.sh --remote 过门禁。
view.md 登记名用 se250-study。

【硬约束】这一轮你**只做调研和方案设计，产出只进 docs/**。
不许改 hw/ip 下任何 RTL、不许改 sw/app、不许重建 bitstream、不许碰开发板。
原因：g3-scale 独占板子并可能重建 ELF，voter-ddr 在跑仿真，
你一动 RTL 就会污染他们的构建——这个坑本项目已经踩过一次。

任务：评估把流水线从 SE150 扩展到 SE250 需要什么。

现状：现有比特流只支持 150 bp。AGENTS.md 明确「SE150（51,781 x 150 bp）与
SE250（64,800 x 250 bp）不可混用」，且 SE250 必须等 G3 闭环后才允许推进
——这个前置条件现在满足了。

几何约束（AGENTS.md「常见陷阱」，务必先吃透，别把它们当独立常量）：
    NUM_LC * STRIDE = L - READ_BPS
    REF_LEN = STRIDE + READ_BPS
当前 SE150 取值：READ_BPS=150, NUM_LC=50, STRIDE=807, REF_LEN=957, L=40500。

请回答并写进 docs/20-se250-study-2026-08-30.md：
1. SE250 的几何参数应该取多少？给出推导过程并验证满足上面两条约束。
   数据在 data/R0.83_data/Sequencing data/DNA-40.5Kb-MC-SE250.fastq
   （只读，禁止修改 data/R0.83_data/ 下任何文件）。
2. 哪些地方是硬编码的、必须改？至少覆盖：
   hw/ip/Dna_accelerator_core_1_0/hdl/ 下的 parameter 与位宽、
   sw/app/echo.h 的几何常量与 DDR 布局、clients/python/task_protocol.py 的下发参数、
   tests/golden/ 的黄金向量需不需要重新生成。
3. 资源与时序能不能扛住？当前实现 WNS 只有 +0.088 ns（xc7z010clg400-1，已经很紧），
   报告在 hw/build/export/reports/。READ_BPS 从 150 到 250 会让相关器阵列、
   记录宽度（CODEBITS = READ_BPS*2）、结果 FIFO 都变宽，
   请估算并给出「是否需要换更大器件（如 XC7Z020）」的判断依据。
4. DDR 布局够不够？现在 Stage1 输出区按 108000x48B=4.94MB 预算，
   SE250 的记录更宽、条数也不同，重算一遍所有区间是否还放得下。
5. 给出分阶段实施方案与每阶段判据，明确哪些必须重新生成黄金向量、哪些可以复用。
   **特别注意**：AGENTS.md 要求 SE250 不得与首次验收混在一起，
   所以方案必须保证 SE150 的判据（图片 SHA-256
   fcd0cf90bd680e7bbdc203e3398119504da0897acac9e2117008b4efb6b1f2c3）
   在改造后仍然成立，并说明怎么保证。

产出是一份可执行的方案，不是可行性空谈：每条结论都要给出出处
（文件:行号、报告数值、或推导过程）。拿不准的地方明确写「未验证」，不要猜。
提交前 git pull --rebase，只 add docs/ 下你新建的文件，push 到 origin/main。
```

---

## 6. 汇合点

- `g3-scale` 跑通全量与二次任务 → G3 的适用范围从「一组参数」扩到「可交付」，
  同步更新 `AGENTS.md` 事实边界里的「尚未验证」清单。
- `voter-ddr` 补完最后一条接口判据 → `docs/18` §5 的「仍未覆盖」只剩
  「二次任务的寄存器时序」与「长时间连续运行」，而这两条由 `g3-scale` 在板上覆盖。
- `se250-study` 出方案 → 由用户决定是否立项，**不要自行开工改 RTL**。

**任何一方改动 RTL 或固件后，都必须整套重建 `hw/build/export/` 并刷新 `SHA256SUMS`，
否则制品与源码不同源。** 最终判据始终是板端真实回传经 LDPC 后的图片 SHA-256。
