# v1.1 制品构建留证（2026-10-16）

本文只记录**构建**。**板端验收尚未进行**——G3 三层判据、v2 `score_min=67` 的 42 例、
8 h 长稳、SD 冷启动**都还没在 v1.1 上重跑**。**不得**把本文读成 v1.1 已验证。

## 1. 为什么会有 v1.1

用户 2026-10-16 拍板：允许改 `sw/app/` 与 `hw/ip/` 源码（注释 + 真缺陷），
**接受 v1.0 重定版为 v1.1 并重跑板测证据**。背景与判据见
[cleanup-swarm-2026-10-16.md](cleanup-swarm-2026-10-16.md)。

v1.0 包的 `source_manifest.json`（111 项）与改动后的源码**已分离**。
⚠️ **精确数字（2026-10-16 上板前审核时自查更正）**：与 v1.1 包（113 项）比较，共有路径中
**31 项哈希不同**（其中 **30 项是真实源码**、1 项是 `.pyc`），**1 项仅 v1.0 有**
（`hw/boards/zynq_eco_7010.tcl`，已被旧板剥离删除），**3 项仅 v1.1 有**（都是新增的 `.pyc`）。
> 更正说明：此前文档与提交信息里写的「26 项哈希不同」**有误**——那是转述一份子 Agent 报告时
> 未自行复核的结果。真值以本节为准。凡是"X 项不同"这类数字进文档前必须自己算一遍。

⇒ v1.0 的板端证据只对应当初那次构建的源码。

## 2. 构建输入

| 项 | 值 |
| --- | --- |
| 源码 | commit `e84c7aa`（`docs:` 计数更正那笔） |
| 板 / 器件 | `bkb220` / `xc7z020clg400-2` |
| 架构 | `C_STAGE1_P_WAYS=16`、`C_STAGE1_PIPE_TREE=1`、`STAGE1_CYCLE_COUNTERS=0` |
| 几何 | `READ_BPS=150`、`NUM_LC=50`、`STRIDE=807`、`REF_LEN=957`、`BATCH=64` |
| 工具 | Vivado / Vitis **2022.2**（指南推荐 2026.1） |
| 硬件入口 | `tools/run_vivado_build.sh` |
| 软件入口 | `tools/rebuild_software_package.py` |

## 3. 这是**第一次**从零跑完整机

`docs/submission/reproduce-artifacts.md` 此前明写：
「**硬件 Vivado 从零构建这一段尚未实测**」。本次补上了这一格。

**硬件成功判据（`reproduce-artifacts.md` 自己定的三条）全部满足：**

| 判据 | 结果 |
| --- | --- |
| `export/` 中 XSA / `top_bd_wrapper.bit` / `hardware_build_config.txt` 非空 | ✅ `1,405,040 B` / `4,045,674 B` / `393 B` |
| `reports/timing.rpt` 达 100 MHz 收敛 | ✅ `All user specified timing constraints are met.`（Setup 0 失败端点 WNS=**+0.411**；Hold 0 失败 WHS=**+0.021**；PW 0 失败） |
| 配置记录与 XSA 的 part / 版本 / HWH 几何 / P_WAYS / PIPE_TREE 一致 | ✅ 逐项比对见 §4 |

⚠️ **过程中的一个虚警，记下来免得下次误判**：physopt 阶段曾报
`Estimated Timing Summary | WNS=-0.333 | TNS=-8.993`（负值），路由中途还出现过
`WHS=-0.298 | THS=-1568.725`。**两者都是中间估算**，Post Routing 落到
`+0.411 / 0.000 / +0.021 / 0.000`。**不要拿中间值当结论。**

## 4. 配置一致性（判据 3 的逐项证据）

`hardware_build_config.txt` 与 XSA 内 `top_bd.hwh` 实测参数：

| 参数 | config 文件 | HWH 实测 |
| --- | --- | --- |
| `C_STAGE1_P_WAYS` | 16 | **16** |
| `C_STAGE1_PIPE_TREE` | 1 | **1** |
| `READ_BPS` / `NUM_LC` | 150 / 50 | **150 / 50** |
| `STRIDE` / `REF_LEN` / `BATCH` | 807 / 957 / 64 | **807 / 957 / 64** |

## 5. 设计未变——用资源报告证明，**不是**用 bit 哈希

| 项 | v1.0 | v1.1 |
| --- | --- | --- |
| 包 | `bkb220-v1.0-release-20261016T104902Z-board-migrate` | `bkb220-v1.1-release-20261016T122937Z` |
| bit SHA-256 | `81229e23…11e226` | `2ec76c7d…13d1aa` |

⚠️ **两个 bit 的哈希不同，但这不证明设计变了。** Vivado bitstream **不是字节可复现的**
（内含时间戳 / design ID），同一份设计两次构建哈希就会不同。

**能证明设计等价的是资源报告**：v1.0 与 v1.1 的 `reports/util.rpt` **只有文件头不同**
（日期、命令行、分隔线宽度），**整个资源层级逐行相同**：

```text
顶层:  Total LUTs 36289 | Logic LUTs 35610 | LUTRAMs 456 | SRLs 223
       FFs 37595 | RAMB36 89 | RAMB18 2 | DSP 6      （v1.0 == v1.1）
```

⇒ 与本波 RTL 改动**只是注释**（剥注释后逐字节相同）互为印证：
**注释级改动没有改变综合实现结果。**

## 6. 软件制品包

| 项 | 值 |
| --- | --- |
| 包 | `hw/build/bkb220-v1.1-release-20261016T122937Z` |
| `top_bd_wrapper.bit` | `2ec76c7dfbe3d92ef706d8f5a60f8062e1e714fcd424b6ca9c7cee7fc313d1aa` |
| `dna_lwip_app.elf`（裸） | `1ed635b808f325ff018aec1f0da0a84be83e4622dc4073d30f6277af7edd8c9a` |
| `dna_lwip_app.elf`（strip-debug） | `fa8b792e12f9f84c64efd26732fd1ac07c4e8c05c5e689c05f42ac40983e1e6c` |
| `fsbl.elf`（裸 / strip-debug） | `f76cdcf5…77af95` / `8711b14a…78db378` |
| `BOOT.bin` | `14d4b2d589b1437268c4bf133ca1aa14ed61a55ea277d4dc88b668b735892e77` |
| `dna_accel.xsa` | `8fb75a31404074c0a71aa69be8e8323473d4b4a676b573facda012284dd58979` |
| `SHA256SUMS` | **2977 条，`sha256sum -c` 全 OK** |
| 包内 `source_manifest.json` | **113 项，与当前源码逐条一致（0 不同、0 缺失）**，但**含 11 项 `__pycache__/*.pyc` 污染**，见下 |
| G3 制品门禁 | `run_g3.sh --strict-artifacts --plan-only` **PASS**（未连板、未烧录） |

⚠️ **plan-only 跑了两次，以第二次为准**：第一次（构建脚本内自动跑的那次）是在
`tools/run_g3.sh` **正被另一路改动**的过程中执行的——日志里那句
`载荷输出模式 : infer_payload 推断长度并以期望 SHA-256 仲裁` 就是那次并发改动。
虽然结论同为 PASS，但按项目纪律「**冻结工作树再比对**」，那次**不作数**。
**定稿后重跑**（`run=20261016T125033Z`，退出码 0）才是本文引用的依据。

⚠️ 判"是不是同一份代码"**必须用 strip-debug 后的逐字节比较或 `nm -S`**，不能裸比 ELF 的 SHA
（构建带 `-g`，调试信息里含构建路径）。

`dna_lwip_app.elf` 与 v1.0 **应当不同**且**确实不同**——本波对 `sw/app` 做了真实修复
（`proto.c` 的有符号溢出 UB、按契约收紧 `reserved` 校验、几何常量单一来源等），**不是注释级**。

## 7. 已知缺陷：`source_manifest.json` 混进了 `__pycache__/*.pyc`

v1.1 包的 `reports/source_manifest.json` **113 项里有 11 项是 `__pycache__/*.pyc`**
（v1.0 是 8 项，同样有）。根因：`tools/write_source_manifest.py` 用 `rglob("*")`
扫 `tools/board` 等目录，**没有排除 `__pycache__`**。

**为什么这是个真问题**（不只是难看）：

1. `.pyc` 是**编译字节码**，不是源码；
2. `__pycache__/` 被 `.gitignore` 忽略（第 52 / 108 行）⇒ **干净 clone 上这些文件不存在**
   ⇒ 这份"源码清单"在别的机器上**校验不过**，可复现性被破坏；
3. `.pyc` 内容**随 Python 版本与源文件 mtime 变**，所以它会**随机漂移**。

**对本次板测的影响：无。** bit/ELF 来自真实源码，多出的条目不影响它们。
**但不要**拿这份清单声称"制品↔源码关系已被完整固化"。修法见下（未做）。

## 8. 尚未做的（**不要读成已完成**）

- **板端 G3 三层判据**（架构 syndrome 全零 + 系统载荷 SHA）——未跑；
- **v2 `score_min=67` 的 42 例**——未在 v1.1 上重跑；
- **8 h 长稳**——未在 v1.1 上重跑；
- **SD 冷启动**——未在 v1.1 上重跑（且历史上就没抓到过 FSBL 启动日志）；
- **QSPI 冷启动**——从未做过；
- **功耗**——从未测（无仪器）；
- **SE250 profile**——另一 profile，本次未构建。

⇒ 上述任一项完成前，**v1.1 不得被宣布为已验收版本**。
