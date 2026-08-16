# 🧬 DNA 存储读出 FPGA 加速系统

在 **Xilinx Zynq-7000 (xc7z010clg400-1)** 上实现 DNA 信息存储的读出流水线：
把测序读段（FASTQ）还原成原始文件。

```
PC ──TCP──► ARM(裸机+lwIP) ──DMA──► ①水印比对 ──► ②投票重建 ──► ③反稀疏化 ──► PC ──► ④LDPC ──► 图片
                                    PL 加速                                        PC 端
```

---

## ⚠️ 项目状态（截至 2026-08-10）

**流程能跑通，结果还不正确。** 请在动手前先读 [`docs/03-status.md`](docs/03-status.md)。

- ✅ **算法链路已在软件上端到端跑通并验证**：原始 FASTQ → 比对 → 投票 → 反稀疏化 → LDPC
  → 还原出的 JPEG 与 `Milk coronet.jpg` 的 SHA-256 完全相同。
- ✅ **反向互补板端取舍已完成（方案B，离线判据闭环）**：Voter 新增 `SCORE_MIN`(0x30)
  阈值过滤，`first.py` 双向发送 + 分数阈值丢弃错误方向；码字误码率 2.33% → 0.14%，
  LDPC 可解。上板验收待做。
- ✅ 已完成并有离线判据：PS 水印区域展开（B1 主机单测）、读段位序/位平面（B2/B4）、
  Stage1 三处同步读流水线修复（B10/B11/B12）、Stage3 数据通路与 AXI 控制层（B5--B9）、
  **Stage2 投票核（B13--B16/C4，2026-08-16 黄金 Testbench 逐位通过）**。
  PS 端水印 XOR（B3）已在 `PIPE_DONE_STAGE2` 实际调用；其输入（Stage2 输出）已有黄金向量背书。
- ✅ C1~C4 完成：PS 按实际条数配置 Voter、DDR 布局主机单测、协议层 64 倍数校验、
  二次任务清零累加器；修改后的 Voter 重新综合在 100 MHz 收敛（WNS +2.48 ns），
  ELF 已用 xsct 重建。
- ✅ P3 任务配置化（离线部分）：PKT_CONFIG/PKT_CAPS 协议 + 严格校验 + 上位机自动
  推导几何与 `--dry-run`；SCORE_MIN/条数现在是运行时下发而非编译期常量。
- ⚠️ 板级构建一键复现（A3）和板上端到端验证未完成（P3 的板端握手联调也待上板）。
- ✅ LDPC 有纯 Python 参考实现（`tools/ldpc_decode.py`，Linux 可跑）：黄金自检
  88 bit 错误 5 轮收敛、重建 JPEG 与原图逐字节相同（Windows EXE 保留给 GUI）。

历史演示中存在「直接用已知正确结果生成图片」的通道。
`data/` 与 `archive/` 里的参考结果**只能作为离线比对的 oracle**，
任何情况下都不得进入生产路径。

---

## 📁 目录结构

```
├─ docs/                 文档（先看 docs/README.md 索引）
├─ tools/golden_model.py 黄金参考模型 / 验收基准
├─ hw/                   PL 工程
│  ├─ ip/                三个自研 IP（RTL + IP-XACT 封装）
│  ├─ constr/            约束（当前为空）
│  └─ scripts/           Vivado 构建 Tcl
├─ sw/                   PS 裸机软件
│  ├─ app/               lwIP + 三级流水线调度（echo.c/echo.h 是核心）
│  ├─ linker/            链接脚本
│  └─ scripts/           XSCT 构建脚本
├─ clients/python/       上位机 CLI(first.py) / GUI(gui_app.py) / LDPC 封装
├─ data/R0.83_data/      R0.83 数据集（输入 + 黄金参考，只读）
└─ archive/              历史提交资产与原始数据包（只读）
```

## 🚀 快速开始

### 验证算法契约（不需要板子，1 秒）

```bash
python3 tools/golden_model.py verify-code
```

### 软件复现整条流水线（不需要板子，全量约 4 分钟）

```bash
python3 tools/golden_model.py simulate --limit 60000 --rc --progress 10000
```

会打印每一级与黄金数据的符合率，并产出可喂给 LDPC 的 `dec_input.txt`。
去掉 `--rc` 就能复现「当前实现的天花板」：码字误码率 2.33%，无法译码；
加上 `--rc` 则降到 0.014%，可以完全纠正。

### 上位机（需要板子）

```bash
cd clients/python
python first.py --ip 192.168.1.10 --port 7 \
    --watermark "../../data/R0.83_data/Source data/Watermark sequences/r0.83_watermark.txt" \
    --reads "../../data/R0.83_data/Sequencing data/DNA-40.5Kb-MC-SE150.fastq" \
    --output dec_input.txt
python gui_app.py          # 图形界面，跑完自动调用 LDPC 解码器
```

需要 Python ≥ 3.8（`first.py` 已移除 `dataclass(slots=True)` 限制）。
LDPC 解码器 `resources/R5_6_LDPC_hard_decoder.exe` 只有 Windows 版本。

### 硬件与固件构建

```bash
vivado -mode batch -source hw/scripts/build.tcl     # ⚠️ 当前脚本依赖当前工作目录，见 docs/03-status.md A2
xsct sw/scripts/create_vitis.tcl
```

`design_2_wrapper.xsa`（与 `hw/build/export/hardware.xsa` 字节相同）是**历史硬件快照**，
含可用的 bitstream，但尚未被证明能由当前 Tcl 重新生成。

## 🔧 环境

- Vivado / Vitis 2022.2
- 器件 `xc7z010clg400-1`，PL 100 MHz，GP0 + HP0，GEM0，UART1
- 板端静态 IP `192.168.1.10:7`（硬编码于 `sw/app/main.c`）

## 📚 下一步

详细实施计划见 [`docs/06-implementation-plan.md`](docs/06-implementation-plan.md)，
方向性说明见 [`docs/04-roadmap.md`](docs/04-roadmap.md)。一句话版本：
**除上板本身外，全部离线任务已于 2026-08-16 完成**（D1/D2 方案B、C1~C4、
A2/A6/A8/A9、P5 纯 Python LDPC、P3 任务配置化）。下一步只有一条主路径：
用修复后的 RTL 重新生成比特流（历史 XSA 里的 Voter 是 B13~B16 修复之前的版本，
**直接烧旧比特流必错**）→ 烧板 → 2,048 条读段双向发送 → 真实回传 →
`python3 tools/ldpc_decode.py decode` → 图片 SHA-256 必须等于 `fcd0cf90...b6b1f2c3`。
之后是 P3 任务配置化与 A7 LICENSE（需选择许可证类型）。
调试期只需要传 2,048 条读段（80 KB），不必传全部 51,781 条。
