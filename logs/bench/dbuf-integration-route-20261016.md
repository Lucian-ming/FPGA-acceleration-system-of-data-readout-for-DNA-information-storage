# 双缓冲原型的整机 route 评估：**装不下，place_design 硬失败**（2026-10-16）

执行人：main。用途：回答 `logs/dev/dbuf-proto-lc50-result.md` 里那句
「真正的闸门是时序」——结果是**连布局都进不去**，时序根本轮不到讨论。

## 1. 怎么做的（两路独立证据）

### 1.1 整机 route（真判据）

把 `hw/experimental/srpe_batch_pway_dbuf_proto.v` 的**体**并入 IP 源位
`hw/ip/Dna_accelerator_core_1_0/hdl/srpe_batch_pway.v`，**只换 module 名**为
`` `SRPE_BATCH_PWAY_MODNAME ``（生产 IP 本来就有的换名口），其余 RTL **一行未改**
（已用 `cmp` 核验 module 之后 719 行逐字节相同）。构建参数与发布候选**完全相同**：

```
board=bkb220 part_name=xc7z020clg400-2 clk_mhz=100 \
stage1_p_ways=16 stage1_pipe_tree=1 jobs=8
```

包：`hw/build/bkb220-p16-k2-ldpc-dbufexp-20261016T023113Z-board-migrate`（**已 gitignore**）。

**结果**：`opt_design` 后 DRC 报 2 个 Error，`place_design` **拒绝运行**：

```
ERROR: [Vivado_Tcl 4-23] Error(s) found during DRC. Placer not run.
FATAL: run impl_1 failed: status='place_design ERROR'
```

DRC `UTLZ-1` 两条：

| 规则 | 需要 | 可用 | 超出 |
| --- | ---: | ---: | ---: |
| UTLZ-1#1 LUT as Logic | **62,588** | 53,200 | +9,388（+17.6%） |
| UTLZ-1#2 Slice LUTs | **63,352** | 53,200 | +10,152（+19.1%） |

对照发布候选整机 **36,282 LUT** ⇒ 这个版本多要 **+27,070（+74.6%）**。

### 1.2 模块级受控 OOC 综合（找原因）

`hw/scripts/synth_check.tcl`，**同脚本、同器件、同参数**，只差 RTL：

```
SYNTH_PART=xc7z020clg400-2 SYNTH_GENERICS="P_WAYS=16 PIPE_TREE=1" \
  vivado -mode batch -source hw/scripts/synth_check.tcl -tclargs <top> 100 <file>
```

| （OOC，xc7z020clg400-2，P_WAYS=16/PIPE_TREE=1） | 生产核 | 双缓冲原型 | 差 |
| --- | ---: | ---: | ---: |
| Slice LUTs | 28,461（53.50%） | **54,413（102.28%）** | **+25,952（+91%）** |
| Slice Registers | 26,516（24.92%） | **68,741（64.61%）** | +42,225（+159%） |
| F7 Muxes | 288 | **9,830** | +9,542 |
| F8 Muxes | 142 | **4,156** | +4,014 |
| RAMB36 | 12 | 4 | −8 |
| DSP48E1 | 4 | 5 | +1 |

**原型模块单独一个就占 102.28% LUT —— 满器件都放不下它自己。**

两路数字**互相印证**：`54,413（核）+ (36,282 − 28,461)（系统其余 ≈ 7,821) ≈ 62,234`
，与整机 DRC 的 63,352 同量级（差额来自 opt_design 的解共享）。⇒ 不是构建配置问题。

## 2. 它为什么这么大（读数字，不猜）

- **F7/F8 宽 mux 从 288/142 涨到 9,830/4,156**（36× / 29×）。这类资源是**宽组合选择**的
  标志；在流水化设计里宽选择本该被打拍。原型的双 bank 读写路径与拆开的装载/发放引擎
  铺了大量无寄存的宽 mux。
- **寄存器 +159%**：`[*_mem [0:1][...]]` 双 bank 只是 BRAM，代价很小（见下），
  真正翻倍的是**控制/地址/元数据状态**（原型 `diff` 出 `ld_state`/`em_state`/`load_busy`/
  `pos_cnt`/`bit_sel`/`cw_idx`/`emit_idx`/`row_i`/`bank_state`/`bank_batch` 等一整套）。
- **RAMB36 反而 12 → 4**：双 bank 位平面本身只值约 1 个 RAMB36（9,600 → 19,200 bit），
  说明**代价不在存储器**——这一条推翻了"双缓冲很便宜"的直觉。

⚠️ 结论**只针对这个原型实现**：它是照**语义正确**写的（LC6/LC50 逐条等价、带背压），
**从未按面积写**。**不能**由它推出"双缓冲这个想法不可能"。

## 3. 要在这颗器件上走通，门槛在哪

发布候选整机 36,282 / 53,200 ≈ **68%**，系统里非 Stage1 核的部分约 **7,821 LUT**
⇒ 新核必须 **≤ 53,200 − 7,821 ≈ 45,379**，再扣 opt_design 增长与布线余量，
工程上大概要 **≤ 42,000**。即：要从 54,413 砍掉 **约 12,400（−23%）**，
相对生产核的增量从 **+91% 压到约 +45%**。

**没有任何证据表明做得到**，也没试过。

## 4. 一条**未验证的猜想**（写下来是为了下次不从头想）

`logs/dev/stage1-overlap-study.md` 的源码事实：`S_RUN` 用位平面 **Port A**，
装载与发放都用 **Port B** ⇒ 装载与发放**本来就争端口、必须互串**。
真需要的也许只是：

1. 第二块位平面（**≈1 个 RAMB36**）+ bank 选择；
2. 一个小的调度仲裁，让装载/发放在扫描窗口内串行插入；

而**不是**复制两套寻址引擎 + 一套双 bank 宽 mux。若如此，增量可能落在几千 LUT 量级、
**装得下**。但这是**猜想，未做任何实现或综合验证**，不得当作结论引用。

## 5. 本页没证明什么

- **没有**拿到 WNS/WHS：布局没跑起来，**时序仍未知**。
- **没有**板测、**没有** bitstream、**没有**功耗。
- 外推的 **731 ms** 收益（`logs/dev/dbuf-proto-lc50-result.md`）本身仍然成立且已实测，
  只是**当前实现拿不到**。

## 6. 处置

- 生产核 `hw/ip/.../srpe_batch_pway.v` 已从备份还原，SHA `54104a96…`
  与 `tools/check_ip_packaging.sh` 的 pin **三处一致**；工作树干净；
  `check_ip_packaging.sh` / `check_repo_hygiene.sh` 均 PASS。
- 实验包只落在 `hw/build/`（已 gitignore），**未污染任何生产件或 Git**。
