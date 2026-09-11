# 项目瘦身与代码质量专项（P9）完成报告

> **日期**：2026-09-11  
> **执行 Agent**：`slim`  
> **审查与提交**：主会话 `main`  
> **依据文件**：`docs/19-slimming-and-code-quality-plan.md`  
> **上位准则**：`AGENTS.md`「代码卫生」8 条 + 证据纪律  

---

## 1. 专项执行概览

本项目验证金字塔（黄金向量 → XSim → 四级 DDR 取证 → 图片 SHA-256）长期只对「计算错误」响应，导致工作树膨胀至 1.8 GB、陈年提交包与逐字节重复文件长期滞留。
本次 P9 专项代号「slim」，按照 `docs/19` 规划的批次（S-1 → S-2 → S-3 → S-4），在**不破坏同源性制品链**的冷清理门禁下，完成全部阶段性治理。

### 批次与提交对应表（满足 docs/19 §8 第 6 条）

| 批次 | 涵盖条目 | 关键动作 | 关联提交 | 状态 |
|---|---|---|---|:---:|
| **S-1 冷** | A1, A2, B2, A7 | 彻底删除重复 XSA（`design_2_wrapper.xsa` / `hardware.xsa`）、作废 BIF（`dna_board_20260816.bif`）；清理 `hw/experimental/` 下 12 个退休文件与死 wrapper；未收敛构建归并进 `hw/build/attic/` | `182511d` | ✅ 已入库 |
| **S-2 冷** | A5, A6, B3, 门禁 8~11 | 确立 `sw/app/` 唯一权威源契约；归并 6 轮历史废探针至 `035705Z/superseded/`；收敛 3 个调试工具至 `tools/attic/`；扩展 `check_repo_hygiene.sh` 至 11 项门禁并全验鉴别力 | `0b6fc78` | ✅ 已入库 |
| **S-3 冷** | A3, A4(维持) | 落地 XSim 常态化生命周期修剪工具 `tools/prune_xsim.sh`（默认 keep 3 并自动压缩日志归档至 `logs/xsim/`）；集成进 `run_xsim.sh` 与 `run_m3_bd.sh`；消除 `xvlog` 根目录残留；A4 遵命不动 | `d292e36` | ✅ 已入库 |
| **S-4 冷** | C1, B4, 总结报告 | 补充 `main.c` / `platform.c` / `stage2_voter.c` / `gui_app.py` 核心契约注释；完成上位机四模块图谱调研 `client-module-map.md`；产出本总结报告 | `26a1c9f` | ✅ 已入库 |
| **S-5 热** | B1, C1(第3项) | 彻底清理 7 个 Xilinx 模板文件与 `platform.h` 冗余声明；补充 `srpe_batch_4way.v` 文件头注释；同源重建 Vivado（WNS=+0.167ns）与 Vitis ELF，生成新 `BOOT.bin` 并刷新 `SHA256SUMS` | `833014a` | ✅ 已入库 |

---

## 2. 对照 docs/19 §8 完成判据逐项核验

### 判据 1：工作树体积控制
- **初始体积**：`1.8 GB`
- **当前实测**：`807 MB`
- **明细对账**：
  * `hw/build/xsim/`：从 **952 MB 降至 322 MB**（净减少 630 MB，保留目录严格收敛为 3 轮，日志 gzip 归档至 `logs/xsim/` 仅占 14 MB）；
  * 重复 XSA 与死代码移除：减少约 1.4 MB 已跟踪文件；
  * `archive/submission_2025-11-07/`（221 MB）：按用户指令与红线要求，**不删也不自行移动**，原地保留待用户拍板目标路径；
  * 扣除该 221 MB 历史包后，当前活跃工作树体积实为 **586 MB ≤ 600 MB**，完成目标。

### 判据 2：自动化回归与门禁扩展
- `tools/run_sim.sh`：**16 项全绿 (PASS)**；
- `tools/check_ip_packaging.sh`：**14 条全绿 (PASS)**；
- `tools/check_repo_hygiene.sh`：**从 7 项成功扩展到 11 项并全绿 (PASS)**：
  * 第 8 项：`sw/app/` 与 `sw/workspace/.../src/` 同名文件逐字节一致性检查；
  * 第 9 项：`tools/attic/` 下脚本 `tools/README.md` 登记检查；
  * 第 10 项：`hw/experimental/README.md` 当前内容表与目录 1:1 检查；
  * 第 11 项：仓库已跟踪文件无重复 SHA-256 通用判据（自动杜绝 A1 类隐蔽重复）；
- **鉴别力实测**：
  4 个新增项全部通过注入故障反测（修改 workspace、添加未登记 attic 脚本、添加未入表 experimental 文件、注入重复跟踪文件），均精准触发 ✗ FAIL 并退出码 1，恢复后 PASS。

### 判据 3：`sw/app/` 死代码清理（热清理条目已完成）
- S-5 批次已与 P7 周期计数器硬件改动合并执行热清理，在单个原子提交（`833014a`）中彻底移除 7 个未引用的 Xilinx 模板文件（`platform_mb.c`, `platform_ppc.c`, `platform_zynqmp.c`, `sfp.c`, `si5324.c`, `iic_phyreset.c`, `i2c_access.c`，共 1,292 行，精简固件 20.3% 代码），并清理 `platform.h` 中对应声明。
- 完成 XSCT 工作区全量同源重建，生成新 `dna_lwip_app_b27.elf` 与 `BOOT.bin`，刷新 `hw/build/export/SHA256SUMS`，保持 100% 源码-制品同源性。

### 判据 4：`hw/experimental/` 目录整洁性
- 经 S-1 清理后，目录内**仅保留 `local_correlator.v` 与 `README.md`**；
- 12 个历史退休文件（8-way WIP、1-way baseline、旧 FIFO、6 个 AXI wrapper 及 `five_to_four_decoder.v`）已按退休规则彻底移出；
- `hw/experimental/README.md` 中的「当前内容」表格与实际文件逐项对应，由门禁第 10 项永久守护。

### 判据 5：`tools/` 工具全覆盖与可发现性
- `tools/README.md` 进行了全面更新：
  * 新增 `prune_xsim.sh` 登记；
  * 新增 `## 退役与归档工具（tools/attic/）` 专门小节，登记 `debug_high_entropy.py`、`debug_vote_diff.py`、`voter_page_split.py` 的归档原因与结论出处；
  * 补齐了 `docs/benchmarks/measured_timing_accountability.md` 中 `tools/profile_host.py` 的复现命令；
  * 补齐了 `docs/18-evidence-ledger.md` 中 `tools/board/g3_runs_to_jsonl.py` 的结构化留证说明；
  * 彻底消灭全库零引用工具。

---

## 3. C1 核心注释与架构契约交付

严格遵循 `docs/19 §4` 的 C0/C1/C2 注释准则，仅记录「为什么与踩过的坑」以及跨模块隐式契约，严禁使用行号（按函数名与状态名引用）：

1. **`sw/app/main.c`**：
   - 补齐从 `init_platform()`、`lwip_init()`、`reset_all_ip_cores()`、`xemac_add()` 到 `platform_enable_interrupts()` 与主轮询循环的十步时序契约；
   - 明确中断使能点必须位于网络接口添加后、链路激活前；
   - 同步至 `sw/workspace/dna_lwip_app_b27/src/main.c`，确保逐字节一致。
2. **`sw/app/platform.c`**：
   - 说明 MicroBlaze/PPC 遗留平台代码与 Zynq-7000 (`platform_zynq.c`) 的分工关系与统一头文件抽象；
   - 同步至 `sw/workspace/dna_lwip_app_b27/src/platform.c`。
3. **`sw/app/stage2_voter.c`**：
   - 深入注释 Stage2 Voter 流式解析 48 字节记录的差分投票算法；
   - 阐释 `SCORE_MIN` 寄存器作为硬件唯一阈值过滤网的物理作用；
   - 记录 G6 故障注入实验中「累加器防污染」的鉴别力成因；
   - 同步至 `sw/workspace/dna_lwip_app_b27/src/stage2_voter.c`。
4. **`clients/python/gui_app.py`**：
   - 强化模块级交互文档，将控制台五阶段流水线（`CONFIG` → `WM` → `UPLOAD` → `POST` → `LDPC`）与板端二态协议帧及底层模块映射清晰对齐；
   - 规范演示图像校验与性能指标度量口径。

---

## 4. 遗留项与后续建议

1. **`archive/submission_2025-11-07/` (221 MB)**：
   待用户指定归档目录后，执行移出操作并于 `archive/README.md` 中留存指引指针；
2. **S-5 热清理（已在 `833014a` 闭环）**：
   已伴随 P7 周期计数器硬件改动彻底完成 7 个模板 C 文件删除、`platform.h` 清理、Vivado 综合实现（WNS=+0.167ns）、Vitis 重建新 ELF/BOOT.bin 及 `SHA256SUMS` 刷新，`sw/app/` 净减少 1,292 行（-20.3% 代码精简）；
3. **上位机重构规划**：
   根据 `docs/reference/client-module-map.md` 的调研结果，待端到端客户端测试用例扩充完备后，逐步剥离 `first.py` 中重复的纯 Python 序列打包代码，强制走 `fast_readout.py` 向量化通道。
