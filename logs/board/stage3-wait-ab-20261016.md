# Stage3 DONE 固定 50 ms → 有界墙钟轮询 IDLE：上板 A/B（2026-10-16）

执行人：main。**同一块板、同一 bit、背靠背交替**，唯一变量是 PS 固件里
`PIPE_DONE_STAGE3` 的那段等待。

## 1. 结论

| 轮 | 固件 | `[PIPE] total` | steps / callbacks | 串口字节 | G3 三层 |
| --- | --- | ---: | --- | ---: | --- |
| A  | 发布包（无条件 `usleep(50ms)`） | 5148 ms | 79621 / 24237 | 275 | PASS |
| A2 | 同上 | 5148 ms | 79621 / 24237 | 275 | PASS |
| A3 | 同上 | 5149 ms | 79621 / 24237 | 275 | PASS |
| B  | 变体（有界轮询 IDLE） | 5098 ms | 79621 / 24237 | 275 | PASS |
| B2 | 同上 | 5099 ms | 79621 / 24237 | 275 | PASS |

**净收益 −49 ~ −50 ms（−0.95% ~ −0.97%）**；基线自身抖动 ±1 ms，两档之间**没有重叠**。
`steps`/`callbacks`/串口字节数**逐字不变** —— 改的只是"等多久"，不是"做了什么"。

G3 三层判据：**架构判据 5/5 PASS**（板端 syndrome 全零 0/10800）、
**系统判据 5/5 PASS**（SHA-256 `fcd0cf90…` 命中，来源=板端合法码字直接提取）。
留证：`/mnt/d/bkb220_board_smoke/g3_runs/{20261015T235349Z, 20261016T000031Z, 20261016T000106Z, 20261015T235921Z, 20261016T000018Z}`。

## 2. 制品

| | bit | ELF（裸） | ELF（strip-debug） |
| --- | --- | --- | --- |
| A 发布包 | `81229e23…` | `a48900c1…` | `5efeb4f5aa4d0685af0f5069e5e68358aa3c362bc2101df58b18868cb59e601d` |
| B 推广包 | `81229e23…` | `383fb2cd…` | `b967585fd3197f7545db2d9ab347d2fcf41d97f9356967fa2df18afe093356cd` |

- A = `hw/build/bkb220-p16-k2-ldpc-release-default-graded-20261015T141803Z-board-migrate`
- B = `hw/build/bkb220-p16-k2-ldpc-release-stage3poll-20261016T000308Z-board-migrate`

**bit 逐字节相同**（`81229e23…`），A/B 只差固件。
上板测量用的中间包 `hw/build/bkb220-p16-k2-ldpc-stage3wait-repro2-20261015T235739Z`
与推广包 B **strip 后逐字节相同**（同为 `b967585f…`、852 个符号尺寸全同）⇒ 那次 5098 ms
的测量对推广包同样成立。

⚠️ 裸 ELF SHA 不同**不代表代码不同**：构建带 `-g`，调试信息里含构建路径。
判定必须用 **strip-debug 后逐字节**或**符号表尺寸**，不能裸比 SHA。

## 3. 构建出处（为什么这一次比较是有效的）

早先的教训（`freeze-tree-before-comparison-build`）是"比较构建前必须冻结树"。
本次先把"发布包到底由哪份源码建出来"钉死，再谈差异：

1. **发布包内自带它编译用的源码拷贝**。`workspace/dna_lwip_app/src/` 的 39 个 `.c/.h`
   与 `HEAD:sw/app/` **逐字节全部相同**（0 个不同）；`stage3_decoder.c` 的
   `HEAD` 版本哈希 = `e81fd93e…` = 发布包内那一份。⇒ **发布包源码 = HEAD**。
2. **HEAD-only 重建**（`rebuild_software_package.py`，无 ② 改动）产出的 ELF
   strip 后 = `5efeb4f5…`，**与发布候选完全相同**，`.text` 同为 254522。⇒ 构建在**代码层面可复现**。
3. **HEAD + ② 重建**与发布包的差异**只有一个符号**：`pipeline_step_stage3`
   `0x4f0`（1264 B）→ `0x540`（1344 B），**+0x50 = 80 字节**，与 `.text` 差值
   254522 → 254602 **完全吻合**；其余 851 个符号尺寸全同。

⇒ 两边制品在**代码层面**的差异**恰好且只有** ② 这一处，A/B 干净。

## 4. ⚠️ 本次犯的一个错（已纠正，记下来）

为做 HEAD 复现构建，我执行了
`git checkout -- sw/app/stage3_decoder.c sw/workspace/dna_lwip_app_b27/src/stage3_decoder.c`。
**第二个路径不被 git 跟踪**，git 因此整体报错并**什么都没有回退**——但我当时只在
`git status` 里看到 ` M sw/app/stage3_decoder.c`，误以为"已回退"（那一行被我自己的
提示语"以上为空即干净"掩盖了）。

后果：头两次所谓"复现构建"其实**都带着 ② 的改动**，是**变体包**而非 HEAD 包。
**是符号表对比（只差 `pipeline_step_stage3` 一个符号）把它暴露出来的**，不是我看输出看出来的。

教训：`git checkout -- <paths>` 里只要有一个路径非法，**整条命令不做任何事**；
回退后必须**用内容本身核验**（哈希 / `git status` 真的为空），不能靠"我执行过了"。

## 5. 固件改动本身（②）

- 改前：`write_reg32(START,0); write_reg32(IN_BEATS,0); write_reg32(OUT_BEATS,0);` 之后
  **无条件 `usleep(50000)`**，再读一次 `STATUS`，非 IDLE 时走原 dummy-run 恢复路径。
- 改后：**按墙钟**最多等 50 ms，每 1 ms 读一次 `STATUS.IDLE`；IDLE 置位即继续；
  直到截止点仍未置位则再采样一次并**照原路径**继续。**不是按轮询次数超时**
  （`docs/03` P13 有教训）。
- 顺手移除 `DONE_STAGE3` 里对 `(DEC_OUT_ADDR, DEC_OUT_BEATS*8)` 的**重复**缓存失效：
  `validate_decoder_written_beats()` 入口第一行就是对**同一范围**的同一失效，
  中间无写入。已核验函数体。
- 红线未动：`START` 后 100 µs 采样等待、B27「START 只写一次 1」、`PIPE_RUN_SLEEP_US`。

**安全性论证（我方独立核验 RTL，不是照抄子 Agent）**：
`hw/ip/desparsification_decoder_1_0/hdl/desparsification_decoder_v1_0.v`
- `STATUS = {30'd0, done, idle}` ⇒ **bit0 = idle**，与固件打印的 `& 0x01` 一致；
- `idle_s <= ~b2`，其中 `{b2,b1} <= {b1, busy}` ⇒ IDLE = `busy` 打两拍取反；
- `busy` **只在** `(wr_state == WR_RESP) && M00_AXI_BVALID && (w_left == 0)`（最后一笔 B 响应）清除；
- 同一模块里项目**自己**的"能否重启"判据是
  `core_active_m = busy | (rd_state == RD_ADDR) | (rd_state == RD_DATA)`，
  其注释写明：**"RD_DONE 时所有读突发都已收完，busy=0 时最后一个 B 也已回来，此时重启才是安全的"**。
  `DONE_STAGE3` 发生在 DONE 之后（已过 RD_DONE）⇒ **IDLE 正是 RTL 自己认可的可推进条件**，
  与 B27 的既有推理同源。

### 边界（不要把这条读成"IDLE 是万能的"）
- `STATUS.IDLE` 只反映**写引擎** `busy`，**不是**对所有内部子状态的汇总；
  `core_active_m` 那个更全的信号**没有**接到 STATUS 寄存器上，固件读不到。
- 本改动**依赖** `DONE_STAGE3` 已经确认输出完成；它不被解释成通用复位或任何情况下的清零证明。
- 实测覆盖的是**单次任务**的 5 轮；**连续多任务**下 Decoder 的 IDLE/恢复可靠性，
  由多载荷回归与 8 h 长稳覆盖（另见相应留证）。

## 6. 本次未证明什么

- 没有测**功耗**、没有测**周期计数器**（`hardware_cycles` 仍为空）；
  `[PIPE] total` 是板端应用打印值，**不得反推周期或功耗**。
- 收益是**同板同小时**的差值；换板、换 bit、换时钟配置都不适用。
- 没有跑 LC50 双缓冲相关任何东西（那是另一条线）。
