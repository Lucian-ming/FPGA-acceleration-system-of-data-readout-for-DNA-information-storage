# v2 挑战集 42 例 —— v1.1 逐例留证（2026-10-16）

**为什么有这份文件**：上板前审核指出，26/16/0 这些数字的**原始逐例日志在 `logs/` 与 `/mnt/d/`，
两者都被 `.gitignore` 忽略**，提交材料若只留文档摘要，审阅者无法复核逐例。
本文件把逐例结果**收进 Git**（原始 `.out` 仍在上述两处，不进 Git）。

**制品**：`hw/build/bkb220-v1.1-release-20261016T134556Z-fwid`
bit `2ec76c7d…13d1aa`、ELF `7f2f6862…c6d27e28`、`fw_build_id` `db5705fb4d0bc003`。

**运行**：`ARTIFACT=<上包> OUTDIR=logs/g3/c2-v2-67-v1.1 bash logs/g3/c2-v2-67/run_all_67.sh`
（脚本退出码 **1** = 有失败例，这是加固后的正确行为）。

**结果**：**26 PASS / 16 安全不收敛 / 0 危险**；与 v1.0 **逐例 verdict 全同**（42 例 0 例不同）。
16 个失败的形态**逐一核过**：全部是「架构判据 FAIL + syndrome 非零 + 无载荷」的**安全不收敛**；
**没有一例**是「架构判据 PASS 但系统判据 FAIL」——那才是"静默给出错误字节"的危险形态。

**42 例的固件身份核对：42/42 PASS**（每例都在复核板上跑的是不是本包）。

⚠️ 表里的 `judge SHA` 是**系统判据**取到的载荷 SHA（仅 PASS 例有）。baseline 与 challenge
共用同一资产 ⇒ **载荷相同、期望 SHA 相同**，差别在畸变后的读段难度。

| 例 | 类别 | 类型 | 载荷字节 | verdict | judge SHA(前16) | v1.0 同例 | 失败形态 |
| --- | --- | --- | ---: | --- | --- | --- | --- |
| `bark-baseline` | bark | baseline | 6738 | **PASS** | `90bc6ca5376bcb65` | PASS | — |
| `bark-challenge` | bark | challenge | 6738 | **PASS** | `90bc6ca5376bcb65` | PASS | — |
| `beach_sand-baseline` | beach_sand | baseline | 6705 | **PASS** | `edf0180d337571c9` | PASS | — |
| `beach_sand-challenge` | beach_sand | challenge | 6705 | **FAIL** | `—` | FAIL | 安全不收敛 syndrome 2350/10800 |
| `blue_sky-baseline` | blue_sky | baseline | 3920 | **PASS** | `cc5b1768e3e53b51` | PASS | — |
| `blue_sky-challenge` | blue_sky | challenge | 3920 | **PASS** | `cc5b1768e3e53b51` | PASS | — |
| `brick_wall-baseline` | brick_wall | baseline | 6730 | **PASS** | `336d99b0dd03b842` | PASS | — |
| `brick_wall-challenge` | brick_wall | challenge | 6730 | **PASS** | `336d99b0dd03b842` | PASS | — |
| `chirping_birds-baseline` | chirping_birds | baseline | 6750 | **FAIL** | `—` | FAIL | 安全不收敛 syndrome 1286/10800 |
| `chirping_birds-challenge` | chirping_birds | challenge | 6750 | **FAIL** | `—` | FAIL | 安全不收敛 syndrome 2262/10800 |
| `fishing_boat-baseline` | fishing_boat | baseline | 6750 | **PASS** | `5566c30ca8ebfaa7` | PASS | — |
| `fishing_boat-challenge` | fishing_boat | challenge | 6750 | **PASS** | `5566c30ca8ebfaa7` | PASS | — |
| `grass-baseline` | grass | baseline | 6615 | **PASS** | `841056802a674b10` | PASS | — |
| `grass-challenge` | grass | challenge | 6615 | **FAIL** | `—` | FAIL | 安全不收敛 syndrome 1816/10800 |
| `jellybeans-baseline` | jellybeans | baseline | 6725 | **PASS** | `650fc2224140741f` | PASS | — |
| `jellybeans-challenge` | jellybeans | challenge | 6725 | **PASS** | `650fc2224140741f` | PASS | — |
| `mandrill-baseline` | mandrill | baseline | 6734 | **PASS** | `8182f8e9f8135c6a` | PASS | — |
| `mandrill-challenge` | mandrill | challenge | 6734 | **FAIL** | `—` | FAIL | 安全不收敛 syndrome 2395/10800 |
| `moon-baseline` | moon | baseline | 6714 | **PASS** | `7db24feeca6126f0` | PASS | — |
| `moon-challenge` | moon | challenge | 6714 | **FAIL** | `—` | FAIL | 安全不收敛 syndrome 4622/10800 |
| `numeric_signal-baseline` | numeric_signal | baseline | 3862 | **PASS** | `ced298c4a2f882fa` | PASS | — |
| `numeric_signal-challenge` | numeric_signal | challenge | 3862 | **PASS** | `ced298c4a2f882fa` | PASS | — |
| `peppers-baseline` | peppers | baseline | 6742 | **FAIL** | `—` | FAIL | 安全不收敛 syndrome 2055/10800 |
| `peppers-challenge` | peppers | challenge | 6742 | **FAIL** | `—` | FAIL | 安全不收敛 syndrome 2057/10800 |
| `rain-baseline` | rain | baseline | 6750 | **FAIL** | `—` | FAIL | 安全不收敛 syndrome 1184/10800 |
| `rain-challenge` | rain | challenge | 6750 | **FAIL** | `—` | FAIL | 安全不收敛 syndrome 1943/10800 |
| `random_binary-baseline` | random_binary | baseline | 6000 | **PASS** | `9bc24dc3239381f2` | PASS | — |
| `random_binary-challenge` | random_binary | challenge | 6000 | **PASS** | `9bc24dc3239381f2` | PASS | — |
| `sailboat-baseline` | sailboat | baseline | 6746 | **PASS** | `455d9b612385ce65` | PASS | — |
| `sailboat-challenge` | sailboat | challenge | 6746 | **PASS** | `455d9b612385ce65` | PASS | — |
| `sea_waves-baseline` | sea_waves | baseline | 6750 | **FAIL** | `—` | FAIL | 安全不收敛 syndrome 1552/10800 |
| `sea_waves-challenge` | sea_waves | challenge | 6750 | **FAIL** | `—` | FAIL | 安全不收敛 syndrome 4733/10800 |
| `stream_bridge-baseline` | stream_bridge | baseline | 6701 | **PASS** | `1e028f88f7766445` | PASS | — |
| `stream_bridge-challenge` | stream_bridge | challenge | 6701 | **PASS** | `1e028f88f7766445` | PASS | — |
| `tree-baseline` | tree | baseline | 6750 | **PASS** | `c50a22ee0d6e4362` | PASS | — |
| `tree-challenge` | tree | challenge | 6750 | **FAIL** | `—` | FAIL | 安全不收敛 syndrome 4959/10800 |
| `utf8_text-baseline` | utf8_text | baseline | 3300 | **PASS** | `07707eee39b6c39c` | PASS | — |
| `utf8_text-challenge` | utf8_text | challenge | 3300 | **FAIL** | `—` | FAIL | 安全不收敛 syndrome 2510/10800 |
| `water_drops-baseline` | water_drops | baseline | 6750 | **FAIL** | `—` | FAIL | 安全不收敛 syndrome 1315/10800 |
| `water_drops-challenge` | water_drops | challenge | 6750 | **FAIL** | `—` | FAIL | 安全不收敛 syndrome 5460/10800 |
| `waterfall-baseline` | waterfall | baseline | 4161 | **PASS** | `46d2e7e9f0159c20` | PASS | — |
| `waterfall-challenge` | waterfall | challenge | 4161 | **PASS** | `46d2e7e9f0159c20` | PASS | — |

## 与 v1.0 的关系

**本表不主张 v1.1 优于 v1.0**——它证明的是**逐例一致**：换了制品之后，
42 例的通过与失败**一例不差**。v1.1 相对 v1.0 的实质变化在 PS 软件
（`proto.c` 的有符号溢出修复与 reserved 收紧、网络配置头接入、几何常量去重等），
PL 是同一份设计（两份 `util.rpt` 除文件头外逐行相同）。

**边界**：本表**不含**每例的原始 `run_g3.sh` 输出、串口日志与四级 dump 明细——
那些在 `logs/g3/c2-v2-67-v1.1/`（不进 Git）。
