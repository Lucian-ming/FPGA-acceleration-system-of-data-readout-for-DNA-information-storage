# 载荷格式自动判定与两处长度缺口（2026-10-16）

用户要求：**「客户端最好能根据 LDPC 回复出来的数据自己决定恢复成什么格式的文件」**，
并要求收掉当日发现的两个缺口。本文记录判据、实现与**边界**。

## 1. 背景：v2 把可恢复的文件形式拓开了

原设计只恢复 **JPEG** 载荷。v2 数据集（42 例 = 21 资产 × baseline/challenge）把它拓到
**文本 / 数值信号 / 随机二进制 / 多种图像**。客户端此前是**半格式无关**：

- 给了 `input_bytes` ⇒ 按字节截断，**任意格式都对**；
- **没给** ⇒ 走 `bits_to_jpeg_bytes`，按 `rfind(b"\xff\xd9")` 找 JPEG 结尾
  —— 对非 JPEG 载荷**误截断**或**保留补零尾部**，且**不报错**。

## 2. 两个缺口（已收）

### 缺口 A（真 bug）：`run_g3.sh` 给 `first.py` 漏传长度

`run_g3.sh` 每轮其实产出**两份载荷成果**：

| 成果 | 谁写的 | 拿到长度? | 对非 JPEG |
| --- | --- | --- | --- |
| `decoded_runN.payload` | `g3_judge` | ✅（`JUDGE_ARGS` 有 `--input-bytes`） | 正确 |
| `decoded_payload.bin` | `first.py` 内部 `verify_board_result` | ❌（`FIRST_ARGS` 漏传） | **静默截错** |

⚠️ **v2 的「26 PASS / 16 SAFE_NOCONV / 0 危险」判定不受影响**——判据走的是 `g3_judge` 那份。
坏的是 `first.py` 写的**留证**。

**修法**：`FIRST_ARGS` 补 `--input-bytes`；两条路现在**同源同长度**。

### 缺口 B：留空时**静默**退回 JPEG 规则

`ldpc_pipeline` 的注释白纸黑字写着"不给按 JPEG EOI 截断"，GUI 的
`if not input_bytes_raw: input_bytes = None` 也没有任何提示。
⇒ 手工恢复非 JPEG 载荷时忘了填字节数，会**静默**拿到一个坏文件。

**修法**：留空改为走下面的**格式自动判定**，并在不确定时**显式告警**。

## 3. 新增：从板端解码结果自动判定格式

`clients/python/native_ldpc.py` 新增（**`bits_to_payload_bytes` 一字未改**，
v1/R0.83 判据依赖的 `input_bytes=None` → JPEG EOI 行为保持逐位不变）：

```python
@dataclass(frozen=True)
class PayloadGuess:
    data: bytes; media_type: str; extension: str; length_certain: bool; method: str

def infer_payload(bits: np.ndarray) -> PayloadGuess: ...
```

**识别 9 类**：JPEG / PNG / GIF / BMP / RIFF-WAVE / RIFF-AVI / PDF / ZIP / UTF-8 文本。

**🔴 核心设计——"长度能不能自己定出来"分两种，并且如实标注：**

| 类型 | `length_certain` | 依据 |
| --- | --- | --- |
| JPEG / PNG / GIF / BMP / RIFF / PDF / ZIP | **True** | 格式**自描述**：`FFD9` / `IEND` / 长度字段 / `%%EOF` / EOCD |
| UTF-8 文本 / 随机二进制 | **False** | 只能**去尾零**，**明确标记为推测** |

### 3.1 一条**信息论上无解**的边界（必须知道）

**载荷本身以零字节结尾时，去尾零必然多删**——没有外部长度就无法区分
"数据里的零"与"填充的零"。

**实测**：`b'ABC\x00\x00\x00'` → 被还原成 `b'ABC'`（多删 3 B），
**但 `length_certain` 如实为 `False`**。⇒ **不装准**是这个设计的第一原则。

### 3.2 所以 G3 那条路**不靠猜**：用 `--expect-sha` 精确仲裁

`run_g3.sh` 没给 `--input-bytes` 时：

1. 先按 `infer_payload` 的长度算 SHA-256，**命中即确认**；
2. 不中 ⇒ 在 `1..6750` 里**遍历长度求精确 SHA-256 命中**（6750 次哈希，成本可忽略）；
3. 🔴 **都不中 ⇒ 抛「载荷长度未验证」直接失败**，
   **明确拒绝回退到 JPEG 截断或整段载荷**（`ldpc_pipeline.py` 的报错原文如此）。

仲裁出的长度**同时喂给 `g3_judge`**，且 `run_g3.sh` 侧也是**失败关闭**：
`first.py` 成功但没写出 SHA 确认长度 ⇒ `step_bad` + 停止本轮判据。

## 4. 用户侧怎么用

| 场景 | 行为 |
| --- | --- |
| 不给字节数（默认） | **自动识别格式与长度**；不确定时**明确告知** |
| 给了字节数 | **精确截取**，逐位走原路径（行为未变） |
| GUI | 显示「识别格式 / 建议扩展名 / 长度是否确定 / 判定依据」；不确定时打 `[WARN] 载荷长度靠去尾零推测，可能不准` |
| 落盘文件名 | 用**推断出的扩展名**：`decoded_payload.jpg` / `.txt` / `.wav` / `.bin`…（不再固定 `.bin`，也不再用 `.jpg` 暗示格式） |

（GUI 的**开发模式/普通模式**分档见 §5。）

## 5. GUI：开发模式 / 普通模式

用户要求：**「将填写字节数等比较复杂的功能封到开发模式，平时不启用保留默认。」**

| | **普通模式（默认）** | 🔒 **开发模式** |
| --- | --- | --- |
| 显示 | IP/端口/测试连接、测序文件与输出目录、发送条数+全量、**发送 POST**、开始/停止、结果预览、日志 | 载荷字节数、分数阈值、几何规格、测序方向、传输批大小、跳过水印预载、参数预设保存/加载 |
| 生效值 | `geom_mode=auto`、`orient=both`、`batch=默认`、`score_min=default_score_min(read_bps)`、`skip_wm=False`、**`input_bytes=None`（自动识别）** | 完全沿用原有读取逻辑 |

**🔴 关键语义**：关模式时**强制取默认，不读隐藏控件里的残留值**——
由 `_effective_config_values()` **一处决定**，避免 `_refresh_estimate()` 与
`start_processing()` 两处漂移。

其他：开关本身**始终可见**、默认 `False`；隐藏用 `grid_remove()`/`grid()`、
`pack_forget()`/`pack(**opts)`（记住原选项，恢复不错位）；
预设文件新增 `dev_mode` 键，**旧预设缺该键时按 `False`**（`values.get("dev_mode", False)`）。
**若关模式后找不到某个控件，勾上「开发模式」即可。**

同时修掉一处**过期文案**：`载荷字节数` 右侧原写"留空按 JPEG EOI 截断"，
已改为"留空=客户端自动识别格式与长度（不确定时会提示）"。

## 5.1 顺带抓到的**第二条既有红判据**

`tests/host/test_g3_payload_decode.py` 的
`test_g3_plan_accepts_and_rejects_input_byte_count_without_board_access`
要求 `run_g3.sh --plan-only` **不给 `--artifact-dir`** 时返回 0 ——
但 `run_g3.sh` 早已改成 `--artifact-dir` **必需**（缺了 `FATAL` 退出 2）。

- **既有，非本波引入**：用 `git archive HEAD` 取干净快照复跑，**HEAD 上同样红**；
- 同一文件树里 `tests/host/test_g3_artifacts.py` 已有**相反的、正确的**断言
  `test_plan_without_artifact_dir_refused` ⇒ **两条自相矛盾**；
- **修法**：改成带一个**合成制品包夹具**（复用 `test_g3_artifacts.py` 的做法，
  **不依赖** `hw/build/` 下 gitignore 的真实包，否则 clean clone 跑不了），
  **四条断言一字未删**（`rc==0` + `原始字节截断（3862 B）`；`rc==2` + `1..6750`）。

现状：该文件 **11 项**、G3 Python 主机回归 **63 项**，**全绿**。

### ⚠️ 系统性发现（值得单独处理）

**Python 主机回归不在任何门禁里**。`tools/run_sim.sh` 只跑 C 那套
（`tests/host/run_host_tests.sh`）；README 里那条
`python3 -m unittest discover -s tests/host -p 'test_g3_*.py'` 是**手写步骤**。
⇒ 它烂了没人知道——**与 C 轨迹判据被链接错误掩盖两天是同一类病**。
建议纳入 `run_sim.sh host`，但那是**新增门禁**（收紧），未擅自做。

## 6. 边界（**不要读成"任意格式都能可靠恢复"**）

- `infer_payload` 只认**上面列的 9 类**；其他容器会落到"去尾零（不确定）"；
- 尾部零歧义**无法消除**（见 §3.1），只能靠 `--expect-sha` 仲裁或人工给长度；
- **GUI 单跑没有 SHA 仲裁**，不确定时只能"猜 + 告知"；
- 本次**没有上板**：板端 G3、v2@67 的 42 例、8 h 长稳都**未在 v1.1 上重跑**。
