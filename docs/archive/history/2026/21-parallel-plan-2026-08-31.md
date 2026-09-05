# 21 · 并行推进计划（2026-08-31）

本文安排四条工作线并行推进：**风险验证、水印预载优化、SE250 扩展、PS 代码拆分解耦**，
并给出可直接粘贴的会话提示词。

排队与判据以 `docs/18` 为准，事实状态以 `docs/03-status.md` 为准，
SE250 的技术细节以 `docs/20` 为准。本文只解决「怎么并行、谁先拿资源、谁不许碰什么」。

---

## 0. 一页结论

**可以同时开 5 个会话**，但并行不是把四件事同时扔出去——
真正稀缺的资源只有两个，整个安排就是围着它们转的：

| 稀缺资源 | 谁要 | 结果 |
| --- | --- | --- |
| **开发板**（一次只能一个会话碰） | 风险验证、水印预载、SE250-S1 复验、拆分复验 | 排队，令牌由 `main` 发放 |
| **`sw/app/echo.c` 的写权** | 水印预载、SE250-S2 主机侧、PS 拆分 | 每一波只给一个会话 |

第一波五个会话**互相零冲突**，因为把「PS 拆分」拆成了两半：
第一波只做**让拆分变得可验证**的安全网（不碰 `echo.c`），第二波才动刀。
这不是凑数——2,206 行的文件重构如果没有「行为等价」判据，
出了问题只能靠上板试，那正是 B22/B27 两个缺陷的产生方式。

```
第一波（现在就能开，5 个并行）
  ①  risk-verify     板子(先) · 不改源码 · 只加 run_g3.sh 的一个开关
  ②  wm-preload      echo.c 写权 · 板子(次) · 收掉 28.9 s 固定开销
  ③  se250-rtl       RTL + 综合 · 板子(末) · docs/20 阶段 S1
  ④  se250-golden    黄金向量 + 主机侧 · 不碰板子/RTL/echo.c · docs/20 阶段 S2
  ⑤  ps-refactor-net 拆分安全网 · 只读 echo.c，不写

第二波（等 ② 落地并释放 echo.c 写权）
  ⑥  ps-refactor     按 ⑤ 的设计与判据真正动刀
```

**板子令牌顺序：① → ② → ③。** 见 §3。

---

## 1. 起点事实（2026-08-31）

- HEAD 与 `origin/main` 同步，`bash tools/verify_repo_binding.sh --remote` PASS。
- **端到端判据始终只有一个**：板端回传经 `tools/ldpc_decode.py` 译码后的图片
  SHA-256 = `fcd0cf90bd680e7bbdc203e3398119504da0897acac9e2117008b4efb6b1f2c3`。
- 已闭环边界：全量 103,616 条（132.67 s）、同一次上电内两次任务（含 Voter 累加器复位）、
  `tools/run_g3.sh` 一键复现、`run_xsim.sh all` 13/13、M2 全链、M3 BD-2/BD-3ext/BD-3b。
- 板端时长模型：**`t = 28.90 s + 1.0012 ms/条`**（五档实测，R² = 1.00000）。
  那 28.9 s 的常数项**基本全是水印预载**——50 个区域 × 2 个流水线状态 ≈ 100 个 poll 步，
  每步 250~500 ms。**4,096 条那档 87% 的时间花在这里，且与数据规模无关。**
- **仍未验证**（`AGENTS.md` 事实边界）：跨不同**规模**的连续任务、三轮以上、
  长时间连续运行、SE250。

---

## 2. 四条线的真实冲突

这张表是本文的核心，排波次全靠它。**开工前每个会话都要看自己那一行的「不许碰」。**

| 线 | 板子 | `echo.c` | RTL | 综合 | 黄金向量 | 主要文件 |
| --- | --- | --- | --- | --- | --- | --- |
| ① 风险验证 | **要（先）** | 不碰 | 不碰 | 否 | 不碰 | `tools/run_g3.sh`、`docs/03` |
| ② 水印预载 | **要（次）** | **写** | 不碰 | 否 | 不碰 | `sw/app/echo.c` |
| ③ SE250-S1 | 要（末） | 不碰 | **写** | **要** | 不碰 | `differential_voter_v1_0.v`、`srpe_batch.v` |
| ④ SE250-S2 | 不碰 | 不碰 | 不碰 | 否 | **新建 se250/** | `tools/make_golden.py`、`clients/python/` |
| ⑤ 拆分安全网 | 不碰 | **只读** | 不碰 | 否 | 不碰 | `tests/host/`、`docs/22` |
| ⑥ 拆分执行（二波） | 要 | **大改** | 不碰 | 否 | 不碰 | `sw/app/echo.c`、新建 `sw/app/pipeline_*.c` |

**三条硬规矩**：

1. **`echo.c` 写权每波只有一个会话**。第一波是 ②。⑤ 只读不写，④ 只动主机侧。
2. **`tools/run_g3.sh` 第一波归 ①**。③⑤⑥ 要改它必须先跟 ① 或 `main` 打招呼。
3. **`tests/golden/` 现有文件一个字节都不许改**。④ 只能**新建** `tests/golden/se250/`。
   SE150 的 `tests/golden/SHA256SUMS` 必须逐字节不变——它是所有其它判据的地基。

---

## 3. 板子令牌协议

板子（ZYNQ ECO R6 + JTAG 210251A08870 + COM6）**一次只能一个会话碰**。
碰它的动作包括：`tools/run_g3.sh`（不带 `--skip-boot` 时）、任何 `xsdb`、任何串口占用。

**顺序写死：① risk-verify → ② wm-preload → ③ se250-rtl。**

1. **申请**：`SendMessage` 给主会话（`main`），说明要跑什么、预计多久。
2. **确认后**才动手，并立刻 `tools/agent_view.sh update --agent <你> --doing "【持有板子】…"`。
3. **释放**：跑完立刻 `update` 去掉「【持有板子】」，并 `SendMessage` 告知 `main`。
4. **没拿到明确答复前，一律不碰板子。** 看板上同时出现两个「【持有板子】」是事故。

`main` 负责仲裁与转交。任何会话如果长时间占着板子不放，`main` 会来问。

---

## 4. 五段提示词（第一波，可直接粘贴）

每段都是**冷启动**提示词，假设新会话对本项目一无所知。

---

### ① `risk-verify` —— 把三条未验风险验掉

```
你接手 FPGA DNA 项目的「剩余风险验证」。仓库在
/home/lucian/projects/FPGA/FpgaAccelerationSystemOfDataReadout

动手前按顺序读完：AGENTS.md（开发规范、事实边界、常见陷阱）、CLAUDE.md、
docs/21-parallel-plan-2026-08-31.md（本次并行安排，尤其 §2 冲突表和 §3 板子令牌）、
docs/03-status.md 的「二次任务 / 状态复位」一节、docs/18 P1 第 4 项。
然后跑 bash tools/verify_repo_binding.sh --remote，不 PASS 就停下来问。

在 view.md 上用 tools/agent_view.sh 以 --agent risk-verify 登记（规则见 CLAUDE.md）。

【你的任务】AGENTS.md 事实边界里列了三条「仍未验证」，把它们验掉：

1. 跨不同规模的连续任务：先跑全量（103,616 条），紧接着在同一次上电内跑 2,048 条，
   第二轮必须仍得 fcd0cf90…f2c3。这是三条里最值得测的——DDR 里还留着上一轮更长的
   中间结果，而这条路径从没走过。
   注意 tools/run_g3.sh 目前没有「每轮不同条数」的开关（只有 --first-run-score-min），
   需要你加一个 --first-run-limit 之类的开关。run_g3.sh 第一波归你，可以改。
2. 三轮以上连续任务：--runs 3 或更多，每轮换 score_min（理由见下）。
3. 长时间连续运行：连续跑若干轮并观察是否退化（lwIP 连接资源、DDR 状态）。
   轮数你自己定，说明理由。

【判据纪律，这是本项目的核心规矩】
- 唯一最终判据是图片 SHA-256 = fcd0cf90bd680e7bbdc203e3398119504da0897acac9e2117008b4efb6b1f2c3。
  界面成功、TCP 有返回、四级取证全绿都不算通过。
- 每条判据都必须「能失败」。跑之前先问自己：如果缺陷真的存在，这条判据会变红吗？
  如果答案是否，这条判据没有信息量，通过了也不能写进结论。
- 特别注意：连续任务如果每轮用同一份输入，「Voter 累加器没清零」是结构性不可观测的
  （票的更新 x <- clip(x±1) 对起始值单调不减，符号判决三种情况全不变，
  所以输出逐位相同 —— 逐位相同恰是该缺陷的必然输出，不是它不存在的证据）。
  完整推导见 docs/03-status.md 的盲区小节。所以多轮测试**每轮必须换 score_min**，
  并且要像 run_g3.sh 现在那样做「鉴别力自证」：两轮 pre-LDPC 原始回传必须不同，
  相同即 FAIL。

【互斥】板子归你先用（令牌顺序 ① → ② → ③，见 docs/21 §3），跑完立刻释放并告知主会话。
不要改 sw/app/echo.c（第一波归 wm-preload 会话）、不要改任何 RTL、
不要动 tests/golden/ 下任何现有文件。

【交付】结论写进 docs/03-status.md 并更新 AGENTS.md 的「仍未验证」列表；
留证（summary + UART 实录）放 docs/board/run-logs/。
按文件显式 git add（禁止 git add -A，工作树里可能有别的会话的改动）、
提交前 git pull --rebase、推到 origin/main。
```

---

### ② `wm-preload` —— 收掉 28.9 s 的固定开销

```
你接手 FPGA DNA 项目的「水印预载性能优化」。仓库在
/home/lucian/projects/FPGA/FpgaAccelerationSystemOfDataReadout

动手前按顺序读完：AGENTS.md、CLAUDE.md、docs/21-parallel-plan-2026-08-31.md（尤其
§2 冲突表与 §3 板子令牌）、docs/18 P2 第 6 项「性能」与 P1 第 3 项的时长模型。
然后跑 bash tools/verify_repo_binding.sh --remote。
在 view.md 上以 --agent wm-preload 登记。

【问题】板端处理时长实测 t = 28.90 s + 1.0012 ms/条（五档，R² = 1.00000）。
那 28.9 s 的常数项基本全是水印预载：sw/app/echo.c 的 PIPE_WM_TX ↔ PIPE_WM_WAIT
按区域循环，50 个区域各占两个 poll 步 ≈ 100 步，而 poll 间隔是 250~500 ms
（两个互不清零的驱动源叠加，见 docs/18 §「poll 间隔」）。
这两个状态实际只做「提交一次 DMA + 回收一次 BD」，却各等一个 poll 周期。
4,096 条那档 87% 的时间花在这里，而且与数据规模无关——任何规模都白等。

【任务】把它收掉。预期 4,096 档 33 s → ~5 s，全量 133 s → ~105 s。

【关键约束，别踩】poll_callback 是 lwIP 的回调，长时间不返回会饿死 TCP 处理。
不要写成「一个 poll 里把 50 个区域全做完」。稳妥做法是每次 poll 走固定若干区域
（比如 8 或 16），把步数从 100 降到十几，并说明你为什么选这个数。
如果你想改成别的结构，先说清楚它为什么不会阻塞 lwIP。

【判据】
- 唯一最终判据：bash tools/run_g3.sh 退出码 0，图片 SHA-256 仍等于
  fcd0cf90bd680e7bbdc203e3398119504da0897acac9e2117008b4efb6b1f2c3。
- 性能判据：改前改后各跑至少两档（如 4,096 与 32,768），用 tools/g3_timing_fit.py
  重新拟合，常数项必须显著下降。**只报一个数不算**——要给出改前改后的对照。
- 回归：bash tools/run_xsim.sh all 必须仍是 13/13。
- 别忘了重建 ELF 后 hw/build/export/ 的 SHA256SUMS 要同步更新，否则 run_g3.sh
  的「制品同源性校验」会挡住你——那是故意的，不要绕过它。

【互斥】第一波只有你有 sw/app/echo.c 的写权。板子令牌顺序是
① risk-verify → ② 你 → ③ se250-rtl，跑板子前先 SendMessage 问主会话要令牌。
不要改 RTL、不要改 tools/run_g3.sh（第一波归 risk-verify）、
不要动 tests/golden/ 下任何现有文件。

【交付】结论写进 docs/18 P2 第 6 项与 docs/03-status.md 的时长模型一节，
把新的拟合式和对照数据一起写上。按文件显式 git add、git pull --rebase、推 origin/main。
```

---

### ③ `se250-rtl` —— docs/20 的阶段 S1（在 SE150 参数下先改时序）

```
你接手 FPGA DNA 项目 SE250 扩展的「阶段 S1」。仓库在
/home/lucian/projects/FPGA/FpgaAccelerationSystemOfDataReadout

动手前按顺序读完：AGENTS.md、CLAUDE.md、docs/21-parallel-plan-2026-08-31.md（尤其
§2 冲突表与 §3 板子令牌）、docs/20-se250-study-2026-08-30.md 全文（这是你的任务书，
§4 讲时序、§6 讲分阶段方案，你做的是阶段 S1）、docs/13 的仿真判据纪律。
然后跑 bash tools/verify_repo_binding.sh --remote。
在 view.md 上以 --agent se250-rtl 登记。

【任务】按 docs/20 §4.3 把两处「宽度正比于 CODEBITS 的顺序扫描多路选择器」
改成移位寄存器：differential_voter_v1_0.v:521 的 current_codeword[bit_in_codeword]
（300 选 1，9 级逻辑，走线占 66.5%，全设计 Top-4 关键路径同源于此）与
srpe_batch.v:305/308 的 cw_data[row_i]（Top-5 第 5 名）；u_in_fifo 深度 1024→256。

【为什么现在做、且仍用 SE150 参数】因为这样判据是现成的：现有黄金向量、
run_xsim.sh、run_g3.sh 都能直接当判据用。等换了几何再改，就是两个变量同时动，
出问题分不清是改造错了还是几何错了。docs/20 §6 阶段 S1 把这条写清楚了。

【判据（全部必须过，缺一条都不算完成）】
① bash tools/run_xsim.sh all 13/13 PASS；
② bash tools/run_m2_full.sh 全链 PASS；
③ bash tools/run_m3_bd.sh bd2 / bd3ext / bd3b 全过；
④ 重建后 WNS 显著改善（目标 ≥ +1.5 ns，现在是 +0.088 ns，那条路径应当整条消失）；
⑤ 上板 bash tools/run_g3.sh 仍得 fcd0cf90…f2c3。
黄金向量零重生成——这正是本阶段的价值。
失败退路：改造无效或引入回归就回滚，并把结论写进 docs/20，不要硬凑。

【两个必踩的坑，先看】
- hw/ip/ 下的 RTL 是 GBK 编码。搜中文必须先 iconv -f GBK 再搜，
  UTF-8 模式对这些文件恒为零命中；改写必须「先 encode 成 bytes → 写临时文件 →
  os.replace」，绝不能 open(p,'wb').write(s.encode(...))（编码抛异常时文件已被截断）。
  另外用这个手法改可执行脚本会丢权限位，记得 chmod +x。详见 AGENTS.md 常见陷阱。
- 仿真全绿不等于板上正确。B23~B27 五个缺陷在所有仿真里都是绿的，只有上板才暴露，
  全都落在「仿真喂黄金数据、板上走真实接口」这条缝里。所以判据 ⑤ 不可省。

【互斥】板子令牌顺序 ① risk-verify → ② wm-preload → ③ 你，轮到你时主会话会通知；
要用之前先 SendMessage 申请。不要改 sw/app/echo.c、不要改 tools/run_g3.sh、
不要动 tests/golden/ 下任何现有文件。综合是长任务，启动前先在 view.md update。

【交付】结论与实测数字（WNS、资源占用、各判据结果）写进 docs/20 §6 阶段 S1，
并更新 docs/18。按文件显式 git add、git pull --rebase、推 origin/main。
```

---

### ④ `se250-golden` —— docs/20 的阶段 S2（黄金向量与主机侧，完全不碰硬件）

```
你接手 FPGA DNA 项目 SE250 扩展的「阶段 S2」。仓库在
/home/lucian/projects/FPGA/FpgaAccelerationSystemOfDataReadout

动手前按顺序读完：AGENTS.md、CLAUDE.md、docs/21-parallel-plan-2026-08-31.md（尤其
§2 冲突表）、docs/20-se250-study-2026-08-30.md 全文（这是你的任务书，
§1 几何、§3 硬编码清单、§5 DDR 布局、§6 阶段 S2）、docs/02 的数据契约。
然后跑 bash tools/verify_repo_binding.sh --remote。
在 view.md 上以 --agent se250-golden 登记。

【任务】按 docs/20 阶段 S2 生成 SE250 的黄金向量与主机侧支持：
几何 NUM_LC=50 / STRIDE=805 / REF_LEN=1055，数据 64,800 条 × 250 bp，参考链 L 仍是 40,500。
产物放 tests/golden/se250/，**不许改 tests/golden/ 下任何现有文件**——
SE150 的 tests/golden/SHA256SUMS 必须逐字节不变，它是其它所有判据的地基。

【判据】
① wm_regions.hex 必须是 50×1055 = 52,750 行，且**不能**等于 SE150 那份的
   f352853912338cd0…。撞上就是特征签名：说明 tools/make_golden.py:43 那组写死的
   NUM_LC, STRIDE, REF_LEN = 50, 807, 957 没被改到，脚本压根没用新几何——
   它不会报错，只会静默给出错的水印区域。
② dec_input.txt 经 tools/ldpc_decode.py 得 fcd0cf90…f2c3（docs/20 §2 已预演通过）。
③ 与 codeword_R083.txt 的交叉核对误码 ≈ 36/64,800。

【一个反直觉但重要的事实，先知道】SE150 和 SE250 产出**同一个图片哈希**
（docs/20 §2 已实跑证明）。所以「不可混用」这条**不能靠哈希守**——
判据必须连同「用的哪套几何、哪套向量」一起记录，否则你会拿一个通过的哈希
去证明一件它证明不了的事。这是本项目反复吃过亏的地方。

【互斥】你这条线完全不碰板子、不碰 RTL、不碰 sw/app/echo.c，与其它四个会话零冲突。
主要动 tools/make_golden.py、clients/python/ 与新建的 tests/golden/se250/。

【交付】结论写进 docs/20 §6 阶段 S2。按文件显式 git add、git pull --rebase、推 origin/main。
```

---

### ⑤ `ps-refactor-net` —— 给 PS 代码拆分先搭安全网（第一波不动 echo.c）

```
你接手 FPGA DNA 项目「PS 固件拆分解耦」的准备阶段。仓库在
/home/lucian/projects/FPGA/FpgaAccelerationSystemOfDataReadout

动手前按顺序读完：AGENTS.md、CLAUDE.md、docs/21-parallel-plan-2026-08-31.md（尤其
§2 冲突表）、docs/18「技术债」第 1 条、docs/03-status.md 的缺陷编年
（B21/B22/B27 三条都源自 sw/app/echo.c）。
然后跑 bash tools/verify_repo_binding.sh --remote。
在 view.md 上以 --agent ps-refactor-net 登记。

【背景】sw/app/echo.c 已经 2,206 行、37 个函数，把 TCP 协议、流水线状态机、
DMA/BD 管理、寄存器时序、缓存维护全塞在一起。B22（Stage3 等待逻辑三处错误，
注释声称读 STATUS 但代码从没读过）和 B27（对 START 寄存器写任何值都会启动，
固件却写了 11 次、其中 9 次是 0）两个缺陷都直接源自这个文件的随意性。

【本波你的任务：不是拆，是让拆变得可验证】
2,206 行的重构如果没有「行为等价」判据，出了问题只能靠上板试——
那正是 B22/B27 的产生方式。所以第一波交付两样东西：

1. **主机侧可跑的单元测试**：把 echo.c 里**纯逻辑**的部分（协议头解析 parse_header、
   DDR 布局计算 ddr_layout_*、批次/对齐计算、状态机的状态转移判定等）
   在主机上用现有的 tests/host 风格跑起来，覆盖边界条件。
   这些函数不依赖 Xilinx 头文件，可以直接编译测试。
2. **拆分设计与模块边界**，写进新建的 docs/22-ps-refactor-plan.md：
   建议的模块划分（如 pipeline_stage1/2/3、bd_ring、reg_timing、proto）、
   每个模块的对外接口、拆分顺序（哪一块先拆风险最低）、
   以及每一步拆完之后用什么判据证明「行为没变」。

【硬约束】**本波你只能读 sw/app/echo.c，不能写它。** 第一波的 echo.c 写权归
wm-preload 会话（它在改水印预载）。你的产物是 tests/ 下的新文件和 docs/22。
第二波你才动刀，那时 wm-preload 已经落地，你从新的 HEAD 开始。

【设计时必须尊重的既有约束，别当成可以清理的历史包袱】
- poll_callback 每 250~500 ms 才走一次，且 run_processing_pipeline() 每次只推进
  一个状态。这个节奏是 lwIP 决定的，不是随意写的。
- 寄存器写序列本身就是被测对象（B27 的教训）：「写 0 → 写 1 → usleep → 写 0」
  这类顺序不能在重构中被「整理」掉，仿真判据 tb_dec_ddr_restart / vot_ddr
  正是在回放它。
- 缓存维护（invalidate / flush）的位置与范围是正确性的一部分，不是样板代码。

【交付】docs/22-ps-refactor-plan.md + 主机侧测试。按文件显式 git add、
git pull --rebase、推 origin/main。做完在 view.md 上 done，等第二波。
```

---

## 5. 共同规则（每个会话都适用）

这一节是前面几轮踩出来的，**不是形式主义**——括号里是它咬过谁。

**Git**

- 按文件显式 `git add`，**禁止 `git add -A`**：工作树是共享的，别的会话的半成品就在旁边
  （上一轮两个 agent 的改动在同一棵树里交错，差点互相提交）。
- 提交前 `git pull --rebase`；别的会话有未提交改动时 rebase 会被挡住，
  先把自己的提交做掉再拉。
- 所有修改必须 push 到 `origin/main`。只允许 `Lucian-ming/FPGA-acceleration-system-of-data-readout-for-DNA-information-storage`，
  不许 `git init`、不许嵌套仓库、只在 `main` 上开发。

**看板**

- 拿到任务先 `start`，交接前 `done`（`done` 会自动摘除条目，零残留）。
- 换子任务、结论变化、启动长任务（综合 / XSim 长跑 / 上板）之前都要 `update`。
- 受阻立刻 `block`，并把「在等什么」写进 `--next`。
- **禁止手工编辑 `view.md`。**

**判据纪律**

- 唯一最终判据是那个图片 SHA-256。仿真全绿、界面成功、TCP 有返回都不算。
- **每条判据都必须能失败**。加判据时顺手做一次故障注入自证：把缺陷人为造出来，
  判据必须变红。一条不会失败的判据，通过了也没有信息量。
- 报告要区分**直接测量**和**推断**。这一轮有两个结论被推翻，都是因为
  扣除法推断进了表格之后被下一个人当实测引用（详见 `docs/19` §3 的复盘）。
- 结论写不写进 `docs/` 决定它会不会被下一个人白重做一遍。

**这轮踩过、还会再咬人的坑**

| 坑 | 症状 | 办法 |
| --- | --- | --- |
| GBK 编码的 RTL | 搜中文恒零命中；`grep` 空结果 ≠ 没有 | 先 `iconv -f GBK` 再搜 |
| 同上，写侧 | 文件被截断为 0 字节 / 注释变 U+FFFD | encode → 临时文件 → `os.replace` |
| 临时文件 + `os.replace` | 脚本可执行位丢失，下一个人拿到 Permission denied | 改完 `chmod +x` |
| 拿注释当实现 | 三处「poll 约 500 ms」全错，据此算的超时差一倍 | 数值要么实测、要么从代码推 |
| 长仿真被打断 | 会话结束 / OOM 杀掉，几十分钟白跑 | 每完成一个子判据就往 summary 追加一行 |
| 只在成功路径上报 | 判据脚本自己的假红/假绿 | 完成性兜底要单独计数，别复用结果数组 |

---

## 6. 第二波（`ps-refactor`，等 ② 落地后再开）

前置条件：`wm-preload` 已提交并释放 `echo.c` 写权；`ps-refactor-net` 的
`docs/22` 与主机侧测试已入库。届时提示词按 `docs/22` 定的拆分顺序现写，
核心判据仍是两条：**主机侧测试全过** + **上板 `run_g3.sh` 仍得 `fcd0cf90…f2c3`**。

拆分是纯重构，**不允许顺手改行为**。想改行为就单独开一笔提交，
否则一旦上板出问题，分不清是拆错了还是改错了。
