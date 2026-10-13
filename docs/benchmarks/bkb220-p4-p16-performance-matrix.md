# BKB220 同板 P4 / P16 六档性能矩阵（2026-10-13）

本文是 `docs/05-implementation-plan.md` §7 里 **P1-C1「同板 P4/P16 六档 ≥3 次性能矩阵」** 的正式口径。
它把此前「P16 比 P4 快」的苗头，变成**同一块 BKB220、同一 SE150 输入、同一客户端、逐个档位各 3 次**的可复现测量。

- 测量工具：`tools/board/g3_performance_matrix.py`（`--repeat 3 --limits 128,512,2048,8192,32768,full`）
- 原始留证：`logs/g3/c1-matrix/p4/`、`logs/g3/c1-matrix/p16/`（`plan.json` / `samples.jsonl` / `summary.json` / 每档每轮的 `*.client.log`、`*.bits.txt`、`*.ldpc.log`、`*.jpg`）
- 未入库说明：`logs/` 受 `.gitignore` 覆盖，留证在本地磁盘；本文抄录全部关键数值，命令可原地复现。

## 1. 被测身份（两轮各自独立的制品证据）

| | P4 矩阵 | P16 矩阵 |
| --- | --- | --- |
| 制品目录 | `hw/build/bkb220-p4-enet0-software-20261012T140800Z-board-migrate` | `hw/build/bkb220-p16-enet0-software-20261012T144141Z-board-migrate` |
| `C_STAGE1_P_WAYS` | 4 | 16 |
| `C_STAGE1_PIPE_TREE` | 0 | 1 |
| bit SHA256 | `6ea4c090b6bd0c1bb11f581d1c7f794ccb212aaeba190f0c491897f96a5103d2` | `123c02b3f3d0156b7b60c935c9e48aa064a0ec2eac943361ccb656c7d8b6e6cf` |
| ELF SHA256 | `37ca544ecd72db7d8667db487060918b590316d18d851064a47bd2b41ce83688` | `595482d87aa5fcc1019376faf792b884875409a9908178342258a9a0e23b934c` |
| XSA 工具版本 | 2022.2 | 2022.2 |
| part / device | `xc7z020clg400-2` / `xc7z020` | 同 |

两轮都是**独立烧录整包**（bit + FSBL + 应用 ELF 同源），不是「同一份 bit 换参数」。
P16 轮在矩阵开始前先跑一次 `tools/run_g3.sh --limit 128 --skip-dump` 确立板上身份，日志 `logs/g3/c1-matrix/p16-boot.out`。

固定输入（两轮相同，`plan.json` 记录 SHA256）：

- FASTQ `data/R0.83_data/Sequencing data/DNA-40.5Kb-MC-SE150.fastq` = `f66503ae9f91ce8980876520e5c93330586cfd2870336cc834b2fab352a37691`
- 水印 `data/R0.83_data/Source data/Watermark sequences/r0.83_watermark.txt` = `b7c842f30be1c49bb57b0161d7685a0a0761668b5d2bd0df024145ae7075d05f`

## 2. 六档结果（每档 3 次，取 `t_result` 中位数）

`source_reads` 是喂进去的源读段数；`records` 是客户端按 SE150 几何（READ_BPS=150、STRIDE=807、BATCH=64）**精确补帧后**的真实记录数。最高档 = 全量输入。

| 源读段 | 记录 | P4 中位 (s) | P16 中位 (s) | 加速比 | P4 stdev (ms) | P16 stdev (ms) |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 128 | 256 | 0.5194 | 0.4762 | 1.09× | 0.10 | 1.02 |
| 512 | 1024 | 0.7110 | 0.5250 | 1.35× | 0.13 | 10.98 |
| 2048 | 4096 | 1.4752 | 0.7400 | 1.99× | 0.29 | 14.05 |
| 8192 | 16384 | 4.5809 | 1.7623 | 2.60× | 0.53 | 7.35 |
| 32768 | 65536 | 16.9735 | 5.5921 | 3.04× | 8.36 | 160.20 |
| **51781（全量）** | **103616** | **26.5393** | **8.9486** | **2.97×** | 19.42 | 346.45 |

线性拟合 `T = a + b·N`（N = 记录数，只用各档中位数）：

| | 固定项 a (s) | 每条成本 b (ms/记录) | R² |
| --- | ---: | ---: | ---: |
| P4 | 0.4529 | **0.2519** | 0.9999993 |
| P16 | 0.4182 | **0.0814** | 0.9993922 |

## 3. 三条结论

1. **每条记录的处理成本降到 1/3.10**：0.2519 → 0.0814 ms/记录。这是 16 路并行滑窗在真实板上的直接收益，也是**唯一应当对外引用的加速口径**。
2. **固定开销几乎不变**（0.4529 → 0.4182 s，差 35 ms，约 7.6%）。它对应 PS 侧与记录数无关的那一段（启动握手、任务下发、DDR 搬运骨架、结果收尾）。**改 P_WAYS 不会动这一段**——这与 `docs/09` 的 P7 结论一致：整机瓶颈在 PS 侧，不在 PL。
3. **加速比随规模单调上升并趋于饱和**：1.09×（小档被固定开销淹没）→ 2.99×附近（摊薄完固定开销后趋近 b 的比值 3.10×）。所以**引用加速比必须同时给出档位**，只报一个「3×」是小档不成立、大档略欠的粗口径。

## 4. 必须一起写明的边界（否则数字会被误读）

- **`t_result` 口径**：POST 发送 → 8100 B 结果收齐，**不含**上传与 LDPC。它是「板端流水线吞吐」，不是端到端。
- **`round_wall` 口径**：`run_client` 开始 → LDPC 进程结束且图片 hash 完成，含输入处理/上传/结果/LDPC，**不含**烧录、四级 DDR 取证与轮间 settle。全量档实测：P4 31.27 s / P16 13.77 s。
- **`hardware_cycles` / `power_w` 为 `null`**：本轮没有接外部实时 UART 采集，`samples.jsonl` 里显式记 `UNMEASURED: 未提供外部实时UART日志`。**绝不能用 `t_result × 时钟频率` 反推周期数或功耗**——那是在编数据。
- **功能判据只在全量档成立**：`correctness_required=true` 仅出现在 51781 档，两轮 `hash_match=true`、`functional_status=PASS`，译码载荷 SHA256 = `fcd0cf90bd680e7bbdc203e3398119504da0897acac9e2117008b4efb6b1f2c3`。其余五档标 `NOT_REQUIRED_PARTIAL_INPUT`——**部分输入不构成完整码字，拿不到唯一判据**，这些档只是性能采样，不是正确性证据。
  - 附带观察（**不是判据**）：2048～32768 档的 `hash_match` 也已经是 `true`，说明部分输入下的 LDPC 仍然收敛到了同一个 8100 B 结果；这只说明流水线在小规模上没坏，**不替代全量档的功能门禁**。
- **CAPS 不能区分 P4/P16**：`g3_caps.py` 报的 `features=1`、`read_bps=150`、`num_lc=50` 等几何两轮完全一致，不含 `P_WAYS`/`PIPE_TREE`。**TCP 层无法证明板上跑的是哪一份**——身份只能靠「本轮烧的制品包 SHA + 该包 `artifact_selection.json` 里的参数」来立，这一点在两份 `plan.json` 里都记了。
- **`p16-boot.out` 末尾的 `G3 FAIL` 不是板卡故障**：那一步是 `--limit 128 --skip-dump`，部分输入的 LDPC 必然非零退出，唯一判据拿不到。该轮真正通过的是：完整制品一致性 PASS、烧录 PASS、CAPS `READY 6.1 1` PASS、串口收到 7744 字符 PASS。**读这个日志时不要把它当成硬件 FAIL。**
- **P16 全量档方差明显更大**（stdev 346 ms，三次 9.036 / 8.397 / 8.949 s；P4 同档 19 ms）。矩阵跑在与其他负载共享的 WSL/Windows 通道上，且 P16 单轮更短、更容易被调度抖动影响。**引用 P16 全量数时应同时给出三次原始值与中位数**，不要只截一个最小值。
- **与 `docs/05` §7 旧数字的差异**：§7 表里写的是「P16 全量 8.61 s vs P4 26.51 s（3.05×）」，那是更早一次单轮的结果。本文的正式口径是 **8.9486 vs 26.5393（2.97×，3 次中位数）**。两者同量级、结论不变；**对外引用以本文为准**，§7 已改为指向本文。

## 5. 复现

```bash
# P16（脚本内含启动步骤，先确立板上身份再跑矩阵）
bash logs/g3/c1-matrix/run_p16_matrix.sh

# P4（同样先烧 P4 包确立身份，再跑同一矩阵命令）
python3 tools/board/g3_performance_matrix.py \
  --artifact-dir hw/build/bkb220-p4-enet0-software-20261012T140800Z-board-migrate \
  --out-dir logs/g3/c1-matrix2/p4 \
  --ip 192.168.1.10 --port 7 --repeat 3 \
  --limits 128,512,2048,8192,32768,full
```

前置条件：板子已上电并接回（USB 直通 + 网线），`192.168.1.10:7` 可达，`--artifact-dir` 指向一个通过完整制品门禁的包。
烧录用 Windows 2026.1 XSDB（`D:/xilinx/2026.1/Vitis/bin/xsdb.bat`），矩阵本身**不烧录**，靠 `artifact-dir` 佐证身份。

## 6. 这条证据在比赛里的位置

对应评分表「性能与资源（20 分）」。它给出的是一条**可复现、同板、同输入、含边界声明**的性能口径：16 路把每条记录成本压到 1/3.10，固定开销不变，加速比随规模趋于 3.10×。
`docs/05` §7 的 P3 优化方向据此定为**PS 侧**（`docs/09` P7：4096 条记录下 Voter 29.6 ms / Decoder 0.022 ms，非 Stage1 耗时 99% 以上是 lwIP poll 空等 2777 ms 与 cache 维护 396 ms），而不是继续压 PL——后者已被板上周期实测证伪。
