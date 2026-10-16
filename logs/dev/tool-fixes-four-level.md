# 四级取证工具修正记录

日期：2026-10-16

## 改动

- `tools/board_stage_check.py` 的 `load_baseline_dir()` 增加可选 `reads_sha256`。基准条目带此字段时必须精确匹配；精确 keyed 项优先于旧式条目。调用方提供读段 SHA 且该载荷/读长已经有 keyed 条目时，若没有精确匹配就返回未命中，不回退到宽泛旧项。仅含旧式条目的基准表仍按原载荷 SHA、读长和首匹配行为工作。
- 检查器增加可选 `--reads-sha256`，校验其为 64 位十六进制 SHA-256。未命中时，输出说明会指出本次读段 SHA 没有可用基准。
- `tools/run_g3.sh` 在四级检查前计算 `$READS_FILE` 的 SHA，并传给检查器；该值仍用于最终摘要，即使跳过 dump 也会记录。
- 新增 `record_stage_check_result()`：退出码 `0` 记 PASS，`3` 记 SKIP 并显式写“本轮四级未取证”，其余退出码记 FAIL。`1` 与其他非零仍设置整体失败标志。
- `tests/golden/board_stage_baselines.json` 未改动；D1/D2 的实际登记由 main 决定。

## 口径变更

这是 G3 验收口径变更：四级检查器退出码 `3` 代表没有适用黄金、无法取证，不再单独触发 G3 FAIL。它也不代表四级 PASS；G3 仍须满足架构与系统判据及其余既有步骤。退出码 `1` 及其他非零仍判步骤 FAIL。

## 离线验证

### 读段 SHA 查表

- 旧式兼容：对当前基准表的 5 组 `payload_sha256/read_bps`，用原首匹配规则计算的目录与新函数一致；不传读段 SHA 与传入读段 SHA 时均保持一致。
- 两个真实数据集的载荷 SHA 都是 `101d89599e84011f30816dea901c43d96bd2a1654a5252dbf47e9c0cc8601ccf`。真实读段文件 SHA 与临时 keyed 基准查表输出如下：

  ```text
  D1_text_manifesto: reads_sha256=7453803b55071eef7af7cc5a831f0fad23eebfe6b5ca63207057a553f316b07c
  D2_controlled_noise: reads_sha256=b621ec199d71785c7452b0655f295d5c21ad52ea1f433e0502d98de0519c8641
  判别命中 PASS：7453803b55071eef7af7cc5a831f0fad23eebfe6b5ca63207057a553f316b07c -> D1_text_manifesto_se150
  判别命中 PASS：b621ec199d71785c7452b0655f295d5c21ad52ea1f433e0502d98de0519c8641 -> D2_controlled_noise_se150
  不匹配 SHA PASS：仅有 keyed 项时返回 None
  混合条目 PASS：提供未知读段 SHA 时不回退旧式宽泛项；未提供时保留旧式项行为
  ```

- 比较了真实黄金文件：`stage2_in.hex`、`sparse_expect.hex`、`stage3_expect.hex` 均不同，`wm_regions.hex` 相同。

### 四级退出码

从 `D1_text_manifesto_se150` 黄金生成完整四级 dump；通过例返回 `0`。同一 dump 在没有登记适用基准时返回 `3`。将 `dump_stage2.bin` 每字节取反后，Stage2 与黄金不符并返回 `1`。随后直接运行从 `tools/run_g3.sh` 提取的实际映射函数：

```text
checker exit=0: 逐级取证 4/4 级全部通过
checker exit=3: 逐级取证 UNVERIFIED
checker exit=1: 逐级取证 3/4 级通过，最先出错的一级是 Stage2 输出 ⊕ 水印
checker_exit=0 => PASS FAILED=0
checker_exit=3 => SKIP FAILED=0 note=本轮四级未取证（退出码 3；UNVERIFIED 不判硬件 FAIL）
checker_exit=1 => FAIL FAILED=1
```

这验证了 `3` 不设置失败标志，真不符 `1` 仍设置失败标志。

### 历史留证复算

- `20261016T090819Z` 使用其 `summary.txt` 中的 `--expect-sha` 与 `--input-bytes 4096` 执行 `tools/run_g3.sh --offline-recheck`：架构 PASS、系统 PASS、三层裁决 PASS。
- 该目录的既有 `stage_check.log` 实际写的是 `UNVERIFIED`（四级都缺可用基准），而 `summary.txt` 将四级步骤记为 FAIL。这与“没有四级黄金时退出码 3 被 G3 当作 FAIL”的故障描述吻合；但留证内容不是“四级 4/4 PASS”。
- `20261016T090617Z` 按其摘要参数复算：架构 PASS，系统 FAIL（实测 SHA `638bc48a9cf30e151e43d47ac1de2ea3ad07fdc4f2265066a1ed10b751327bc9`，期望 SHA `034adb3c5096819e35dde255bcad95377f31f3fdcc7e27083ffe1ef0cdbe0525`）。因此即使四级未取证被改为 SKIP，这轮仍会因系统判据失败而保持 G3 FAIL。

### 仓库检查

```text
bash -n tools/run_g3.sh                         PASS
python3 -m py_compile tools/board_stage_check.py PASS
git diff --check                                PASS
bash tools/check_repo_hygiene.sh                仓库卫生检查 PASS
bash tools/check_ip_packaging.sh                IP 打包卫生检查 PASS
```

## 未确定事项

- 基准表尚未登记 D1/D2 keyed 项；查表验证用临时 JSON 指向仓库内真实黄金目录，未替 main 决定实际条目内容。
- 用户给出的 `20261016T090819Z` 描述称四级为 `4/4 PASS`，但现有 `stage_check.log` 显示四级 `UNVERIFIED`，`summary.txt` 记为 FAIL。三层 PASS 已由摘要和带正确参数的离线复算确认。此报告按留证文件记录该差异。
- 没有在板上重跑；硬件状态与线上实际调用仍以 main 后续验收为准。
