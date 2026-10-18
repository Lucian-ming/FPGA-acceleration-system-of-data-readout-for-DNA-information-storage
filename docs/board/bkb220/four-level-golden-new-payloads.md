# 新载荷的四级逐级取证黄金向量（2026-10-16）

## 0. 这篇解决什么

`docs/03` 长期挂着一条欠账：「四级逐级取证对新载荷不适用（`board_stage_check.py` 仍写死 R0.83 黄金向量）」。
后果是 §16.6 写明的边界：**新载荷只能采信端到端判据**，中间三级（水印展开 / Stage1 / Stage2 / Stage3）
在板端拿不到逐级证据。

本文记录：为仓库内 5 个新载荷生成四级黄金向量、**用项目自己的译码器验证**、
并在**真板上完成一次试点**，证明这条链路成立；同时记下**过程中发现的 3 条硬规则**与**一个工具层阻塞**。

## 1. 先说结论

- **5 份黄金向量已生成并逐个验证**（每个都译回各自的期望载荷 SHA）。
- **板端试点（`D1_binary_pattern`）：四级 4/4 PASS，三层判据 PASS。** ⇒ 黄金与真板端逐位吻合。
- **发现 3 条必须遵守的规则**（见 §3）——违反任何一条都会得到"看起来像板端出错"的假结果。
- **1 个阻塞**：`D1_text_manifesto` 与 `D2_controlled_noise` **载荷 SHA 相同**，
  而基准表只按「载荷 SHA + read_bps」查目录 ⇒ **表达不了这个区别**，见 §5。

## 2. 怎么做的

### 2.1 载荷身份：D0 就是 R0.83

先确认要覆盖哪些载荷。`D0_image_mandrill` 的期望 SHA 就是 `fcd0cf90…` ——**D0 即 R0.83**，
它的黄金向量已经在 `tests/golden/`（`golden_dir: "."`）。**不需要新生成。**

需要新生成的是 5 个：`D1_text_manifesto`、`D1_binary_pattern`、`D1_structured_sparse`、
`D1_random_entropy`、`D2_controlled_noise`。

### 2.2 生成

```
python3 tools/make_golden.py \
  --reads tests/datasets/<载荷>/reads_se150.fastq \
  --watermark tests/datasets/common/watermark.txt \
  --limit 4096 --min-score <见 §3.2> --jobs 8 \
  --outdir tests/golden/<载荷>_se150
```

每份耗时 <1 分钟，产出 15 个文件；四级检查器只需要其中 4 个：
`wm_regions.hex`、`stage2_in.hex`、`sparse_expect.hex`、`stage3_expect.hex`。

### 2.3 **验证配方**（这一步不能省）

生成完**必须验证这份黄金对应的是哪个载荷**。做法是利用 `make_golden.py` 同时写出的
`dec_input.txt`（期望的板端输出码字）：

```
python3 tools/ldpc_decode.py decode <golden>/dec_input.txt --payload /tmp/x.bin --input-bytes <N>
sha256sum /tmp/x.bin        # 应等于该载荷的期望 SHA
```

⚠️ **这个配方本身要先做对照实验**：拿它去还原 **R0.83** 的黄金（`tests/golden/dec_input.txt`），
必须得到已知的 `fcd0cf90…`。**对照不通过就不要相信后面任何结论。**

⚠️ 我自己在这里**连续错了两次**：手工推导「码字前 N 字节」以及「`codeword[PARITY_COLS:]` + 自定
字节序」都不对——`dec_input.txt` 是**含噪接收比特**（R0.83 起始失败校验 332，5 轮收敛），
不是干净码字。**别自己发明提取方式，直接用项目译码器。**

## 3. 三条硬规则（违反会得到假结果）

### 3.1 黄金的 `--limit` 必须与板端任务的 `--limit` 相同

`stage2_expect` / `stage3_expect` 是**跨记录投票**的结果，记录数变了结果就变。
（`stage2_in` 只在 Stage1，逐记录独立，但为了整体一致，两边必须同值。）

### 3.2 黄金的 `--min-score` 必须映射到与板端 `--score-min` **相同的整数门限**

`--min-score` 是比例，`0.45 × 150 = 67.5 → 67`；**要 65 得用 `0.435`**。
第一批我全用了 `0.45`，结果 `D1_random_entropy` / `D2_controlled_noise` 的黄金在 67 下生成，
**译码不收敛**（残余失败校验 832 / 123）——而这两个载荷的期望 SHA 本来就取自 **65** 档。
改用 `0.435` 重生后两个都收敛且 SHA 全对。

### 3.3 非 JPEG 载荷的板端运行**必须传 `--input-bytes`**

`run_g3.sh` 默认走 `载荷输出模式 : JPEG EOI 截断`。对二进制/WAV/文本载荷，这会用 JPEG 的
`FF D9` 规则截长度 ⇒ **系统判据必然 FAIL**。

我这次第一遍就是这么栽的：**架构判据 PASS、四级 4/4 PASS，系统判据却 FAIL**
（板端码字载荷 SHA `638bc48a…` ≠ 期望 `034adb3c…`）。
补上 `--input-bytes 4096` 后同一个板端状态立刻 **三层全 PASS**。
⇒ **看到"四级过、系统不过"时，先怀疑载荷提取方式，不要先怀疑板子。**

## 4. 板端试点（`D1_binary_pattern`）

```
bash tools/run_g3.sh --artifact-dir <推广包> --strict-artifacts \
  --reads tests/datasets/D1_binary_pattern/reads_se150.fastq \
  --watermark tests/datasets/common/watermark.txt \
  --expect-sha 034adb3c5096819e35dde255bcad95377f31f3fdcc7e27083ffe1ef0cdbe0525 \
  --input-bytes 4096 --score-min 67 --limit 4096 \
  --xsdb /tools/Xilinx/Vitis/2022.2/bin/xsdb --hw-server TCP:127.0.0.1:3132 ...
```

留证 `g3_runs/20261016T090819Z`。**三层判据：架构 PASS（syndrome 0/10800）、系统 PASS、裁决 PASS。**

四级逐级（`--golden-dir` 显式指定）：

| 级 | 结果 |
| --- | --- |
| 展开水印 @0x10040000 | **47850/47850 字逐位相同** |
| Stage1 输出 @0x10600000 | 整条 48 B 相同 **4007/4096**；**码字 4096/4096、score 4096/4096**；position 差值 89 条（多为并列被打破，已知非致命） |
| Stage2 输出 @0x11000000 | 整字 **1265/1266**，比特误码 0.01% |
| Stage3 输出 @0x11100000 | 整字 **1010/1012**，比特误码 0.01% |

**4/4 级全部通过。**

⚠️ 注意 Stage2/Stage3 那 0.01% 的残差：四级检查器**容忍**它（判 PASS），
但**系统判据（载荷 SHA）不容忍**——§3.3 那次 FAIL 正是这个量级的差异造成的。

## 5. ⚠️ 阻塞：`D1_text_manifesto` 与 `D2_controlled_noise` 载荷 SHA 相同

| | 载荷 SHA | `wm_regions` | `stage2_in` | `sparse_expect` | `stage3_expect` |
| --- | --- | --- | --- | --- | --- |
| `D1_text_manifesto` | `101d8959…` | 相同 | **不同** | **不同** | **不同** |
| `D2_controlled_noise` | `101d8959…` | 相同 | | | |

两者是**同一个载荷在不同噪声下的两次任务**，所以载荷 SHA 相同；
但**读段不同**（`reads_se150.fastq` 的 SHA 分别是 `7453803b…` / `b621ec19…`），
所以中间三级黄金**不同**。

而 `tools/board_stage_check.py::load_baseline_dir()` **只按「`payload_sha256` + `read_bps`」匹配、
且返回第一个命中项** ⇒ 无法区分这两者。

**处置：两份黄金都生成并验证了，但 `D1_text_manifesto` 也【不登记】**——
因为一旦登记，`D2` 的 dump 会被拿去比 `D1_text` 的黄金，产生**假 FAIL**。
`UNVERIFIED`（未取证）比"假 FAIL"诚实。**两份的 `golden_dir` 都已备好，等工具改了随时可登记。**

**建议的修法**（未实施）：给基准条目加一个可选的 `reads_sha256` 判别字段
（有则必须匹配），并让 `run_g3.sh` 把 `--reads-file` 一并传给检查器
（它本来就有 `$READS_FILE`）。**向后兼容**：没有该字段的条目行为不变。

## 6. 已登记 / 未登记

已登记进 `tests/golden/board_stage_baselines.json`（`read_bps=150`）：

| 载荷 | golden_dir | 门限 |
| --- | --- | --- |
| `D1_binary_pattern` | `d1_binary_pattern_se150` | 67 |
| `D1_structured_sparse` | `d1_structured_sparse_se150` | 67 |
| `D1_random_entropy` | `d1_random_entropy_se150` | 65 |

**未登记**：`D1_text_manifesto`、`D2_controlled_noise`（§5 的撞车）。
两者的黄金目录 `tests/golden/{D1_text_manifesto,D2_controlled_noise}_se150` 已生成并验证。

⚠️ **登记的含义**：这些载荷从此在 `board_stage_check.py` 里**从 `UNVERIFIED` 变成会被实际裁决**。
前提是板端运行遵守 §3 的三条规则（尤其 `--limit` 必须与生成时一致）。

## 7. 顺带暴露：那条"工具尾巴"的活实例

试点第一遍（`g3_runs/20261016T090617Z`）里，**架构 PASS、系统 FAIL 是载荷提取方式造成的**；
但第二遍（`20261016T090819Z`）**三层判据全 PASS、四级 4/4 PASS**，脚本末尾仍打印
**`######## G3 FAIL ########`** —— 因为四级检查在 `run_g3.sh` 内报 `UNVERIFIED`（未登记基准）⇒
退出码 3 ⇒ 被当作通用 FAIL。

**这正是 `docs/03`「工具尾巴」描述的未决问题，现在有了活实例。**
它**不是**本次引入的；但"登记基准"会让一部分载荷不再触发它。
**改这个映射等于改验收口径，仍须专门定夺，本文不抢先改。**

## 8. 本页没证明什么

- **只对 `D1_binary_pattern` 做了板端试点**；另外 4 份黄金只有**离线**验证（译码回期望 SHA），
  **没有**各自的板端四级取证。
- 黄金是**用软件模型**生成的（`make_golden.py`），它本身不是独立参考实现；
  "与板端一致"只说明两者同源且逐位吻合，**不证明**模型算法在真实测序误差下的正确性。
- 数据仍是 **in-silico 模拟测序**。
- 未做：登记后的**完整回归**（确保登记没有把别的载荷判红）。

---

# 9. 2026-10-18：登记阻塞解除，**5 个载荷的板端四级取证全部完成**

## 9.1 §5 的阻塞是怎么解除的

§5 建议的修法已经落地：

- `tools/board_stage_check.py::load_baseline_dir()` 支持可选字段 **`reads_sha256`**
  （条目有该字段时**必须精确匹配**；没有该字段的条目不提供回退）；
- `tools/run_g3.sh` 已在取 dump 时把本次 FASTQ 的 SHA-256 作为 `--reads-sha256` 传给检查器
  （`READS_SHA="$(sha256sum "$READS_FILE")"`）。

⇒ `D1_text_manifesto` 与 `D2_controlled_noise` 载荷 SHA 相同的问题**不再阻碍登记**。

## 9.2 本次新登记的两条

`tests/golden/board_stage_baselines.json`（`read_bps=150`）：

| 载荷 | golden_dir | `score_min` | `reads_sha256` |
| --- | --- | ---: | --- |
| `D1_text_manifesto` | `d1_text_manifesto_se150` | 67 | `7453803b55071eef7af7cc5a831f0fad23eebfe6b5ca63207057a553f316b07c` |
| `D2_controlled_noise` | `d2_controlled_noise_se150` | 65 | `b621ec199d71785c7452b0655f295d5c21ad52ea1f433e0502d98de0519c8641` |

两份载荷 SHA 都是 `101d8959…`（同一载荷、不同噪声），靠 `reads_sha256` 区分。
`tests/golden/SHA256SUMS` 中 `board_stage_baselines.json` 一行已同步刷新。

## 9.3 离线验证（先验，不能省）

按 §2.3 的配方，用项目自己的译码器把每份黄金的 `dec_input.txt` 译回载荷并比对 SHA：

| 黄金目录 | `--input-bytes` | 结果 |
| --- | ---: | --- |
| `d1_binary_pattern_se150` | 4096 | ✅ SHA 相符 |
| `d1_structured_sparse_se150` | 6750 | ✅ |
| `d1_random_entropy_se150` | 6750 | ✅ |
| `d1_text_manifesto_se150` | 5000 | ✅ |
| `d2_controlled_noise_se150` | 5000 | ✅ |

## 9.4 板端结果：**5/5 载荷三层判据 PASS + 四级 4/4 PASS**（全部 v1.1 制品）

统一口径：`--limit 4096`、`--skip-boot`、制品 `hw/build/bkb220-v1.1-release-20261016T134556Z-fwid`
（`fw_build_id db5705fb4d0bc003`）。`--input-bytes` 取该载荷的真实字节数。

| 载荷 | 留证 run | 架构判据 | 系统判据 | 水印字 | Stage1 整条 48B | Stage3 整字 |
| --- | --- | --- | --- | ---: | ---: | ---: |
| `D1_binary_pattern` | `g3_runs/20261018T023524Z` | `0/10800` PASS | PASS | 47850/47850 | 4007/4096（码字 4096/4096、score 4096/4096） | 1010/1012（0.01%） |
| `D1_structured_sparse` | `g3_runs/20261018T023408Z` | `0/10800` PASS | PASS | 47850/47850 | 4025/4096（码字/score 均 4096/4096） | 1010/1012（0.02%） |
| `D1_random_entropy` | `g3_runs/20261018T023419Z` | `0/10800` PASS | PASS | 47850/47850 | 4008/4096（码字/score 均 4096/4096） | 996/1012（**0.36%**） |
| `D1_text_manifesto` | `g3_runs/20261018T023312Z` | `0/10800` PASS | PASS | 47850/47850 | 4014/4096（码字/score 均 4096/4096） | 1010/1012（0.02%） |
| `D2_controlled_noise` | `g3_runs/20261018T023430Z` | `0/10800` PASS | PASS | 47850/47850 | 4012/4096（码字/score 均 4096/4096） | 1009/1012（0.02%） |

- **Stage2 输出 ⊕ 水印**：五场均为 **1265/1266，比特误码 0.01%**。
- **四级逐级取证：5/5 场次均为「4/4 级全部通过」**。
- 每场的逐级原始数字在各 run 目录的 `stage_check.log`；完整命令在 `summary.txt` 与 `uart.log` 同目录。

## 9.5 关键验证点：`reads_sha256` **真的生效了**

`D1_text_manifesto` 与 `D2_controlled_noise` 的载荷 SHA 相同，如果判别没生效，
两场必然至少有一场被判红。实际两场 `stage_check.log` 分别写着：

```text
黄金向量：…/tests/golden/d1_text_manifesto_se150 （读段 SHA=7453803b…）
黄金向量：…/tests/golden/d2_controlled_noise_se150 （读段 SHA=b621ec19…）
```

⇒ 登记不是"看起来对"，而是**按读段身份真正区分开了**。
`D1_binary_pattern` 的 `matches` 也是按同一机制选中 `d1_binary_pattern_se150`。

## 9.6 边界（**不要读成"新载荷算法在真实测序下已验证"**）

- 数据仍是 **in-silico 模拟测序**；
- 黄金由 `make_golden.py`（软件模型）生成，**不是独立参考实现**；
  "与板端一致"只说明两者同源且逐位吻合；
- `D1_random_entropy` 的 Stage3 比特误码 **0.36%**（比其他载荷高一个量级），
  四级检查器仍判 PASS —— **硬判据是系统判据（载荷 SHA），不是逐级比对**；
- **`--limit` 必须与黄金生成时一致（本次均为 4096 源读段）**，换 `--limit` 必须重生成黄金（§3.1）；
- 非 JPEG 载荷必须传 `--input-bytes`（§3.3），本次四个都传了。

## 9.7 改动清单

| 文件 | 改动 |
| --- | --- |
| `tests/golden/board_stage_baselines.json` | 新增 `D1_text_manifesto`、`D2_controlled_noise` 两条（带 `reads_sha256`） |
| `tests/golden/SHA256SUMS` | 刷新 `board_stage_baselines.json` 的 SHA-256 行 |
| 本文件 | 新增第 9 节 |
