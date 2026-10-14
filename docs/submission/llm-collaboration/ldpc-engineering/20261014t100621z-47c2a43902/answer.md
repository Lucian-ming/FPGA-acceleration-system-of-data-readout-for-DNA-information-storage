> 脱敏副本，原件 `20261014T100621Z-47c2a43902/{prompt.txt,answer.md}`。本机绝对路径、邮箱、凭据形模式及非白名单私网 IP 已替换；除脱敏与换行规范化外保留原文。

已完成 LDPC 013 回归接入。TB 只增加黄金目录和 B_t ROM 路径注入；收敛状态与码字逐位比较判据未改。013 回归在默认 **600 秒**用例超时内 **24.5 秒**完成，结果为 4 轮收敛、64,800 位全匹配。

### 文件与黄金集

| 文件 | 变更 | 大小 |
| --- | --- | ---: |
| [tb_ldpc_decoder_p1.v](<仓库根目录>/hw/experimental/tb_ldpc_decoder_p1.v) | 修改：支持 `+GOLD_DIR` 和 ROM 参数覆盖 | 14,669 B |
| [run_sim.sh](<仓库根目录><本机路径>) | 修改：新增 `ldpc_decoder` 用例 | 15,110 B |
| [summary.tsv](<仓库根目录>/tests/golden/ldpc/summary.tsv) | 新增，内容与源文件一致 | 736 B |
| [in_013_se150_16384.hex](<仓库根目录>/tests/golden/ldpc/in_013_se150_16384.hex) | 新增，内容与源文件一致 | 16,200 B |
| [out_013_se150_16384.hex](<仓库根目录>/tests/golden/ldpc/out_013_se150_16384.hex) | 新增，内容与源文件一致 | 16,200 B |

黄金集共 **33,136 B（约 32.36 KiB）**。两个 hex 文件各含 8,100 字节向量的十六进制文本表示。B_t 表文件只引用、未修改：`bt_col_by_res.hex` 为 5,400 B，`bt_res_off.hex` 为 124 B。

SHA-256：

```text
ccb2fad536a424871d7b21cfe00ef7db2cffdf121085da982bdfd5375beb6db4  summary.tsv
9df1dead59ddcdea26368531e4bbd879d548d4041e4a6f04de846bb168ad7c91  in_013_se150_16384.hex
c987d5ae18b40411ccb307aa57cc0e1a0155daea48ec44e8c8068cfa07f966fe  out_013_se150_16384.hex
```

### 验证输出

以下为终端文字输出，去除了 ANSI 颜色控制序列。

`bash tools/run_sim.sh ldpc_decoder`（退出码 0）：

```text
仿真入口: ldpc_decoder；证据目录: logs/iverilog/run_20261014_180819_2_ldpc_decoder；每项超时: 600s

=== ldpc_decoder ===
  START sample=013_se150_16384 codeword_input=0 expected_converged=1 expected_iters=4
  PROGRESS sample=013_se150_16384 syndrome_pass=1 iteration_q=1 converged=0 done=0
  PROGRESS sample=013_se150_16384 syndrome_pass=2 iteration_q=2 converged=0 done=0
  PROGRESS sample=013_se150_16384 syndrome_pass=3 iteration_q=3 converged=0 done=0
  PROGRESS sample=013_se150_16384 syndrome_pass=4 iteration_q=4 converged=0 done=0
  PROGRESS sample=013_se150_16384 syndrome_pass=5 iteration_q=4 converged=1 done=1
  OUTPUT MATCH sample=013_se150_16384 compared_bits=64800 bit_mismatches=0
  CYCLES sample=013_se150_16384 total=2915672 row_setup=54000 row_pipeline=1295995 emit_pipeline=1241673 update_pipeline=259204 init_sum=64800 syndrome_state_cycles=0 other=0 syndrome_passes=5 syndrome_edges=1187995 rom_reads=1132200 llr_reads=1187995 llr_captures=1187995 emit_reads=1187687 emit_writes=1187687 update_reads=259200 update_writes=259200
  PASS sample=013_se150_16384 converged=1 expected_iters=4 actual_iters=4 bit_mismatches=0 compared_bits=64800

==================================================
通过 1 项，失败 0 项
==================================================
```

`bash tools/check_ip_packaging.sh`（退出码 0）：

```text
=== IP 打包卫生检查 ===
  ✓ IP hdl/ 目录内无 testbench
  ✓ IP hdl/ 目录内无非 HDL 文件
  ✓ Dna_accelerator_core_1_0: 模块 srpe_batch 有多个实现( srpe_batch.v srpe_batch_4way.v)，已明确打包 srpe_batch_4way.v
  ✓ desparsification_decoder_1_0: 模块名无冲突
  ✓ differential_voter_1_0: 模块名无冲突
  ✓ ldpc_decoder_1_0: 模块名无冲突
  ✓ Dna_accelerator_core_1_0: component.xml 引用的文件均存在
  ✓ desparsification_decoder_1_0: component.xml 引用的文件均存在
  ✓ differential_voter_1_0: component.xml 引用的文件均存在
  ✓ ldpc_decoder_1_0: component.xml 引用的文件均存在
  ✓ Dna_accelerator_core_1_0: hdl/ 无孤儿文件
  ✓ desparsification_decoder_1_0: hdl/ 无孤儿文件
  ✓ differential_voter_1_0: hdl/ 无孤儿文件
  ✓ ldpc_decoder_1_0: hdl/ 无孤儿文件
  ✓ 打包内容与 hw/ip/PACKAGED_VARIANTS.txt 一致
  ✓ Dna_accelerator_core_1_0: 打包的实现均被 tools/run_sim.sh 覆盖
  ✓ desparsification_decoder_1_0: 打包的实现均被 tools/run_sim.sh 覆盖
  ✓ differential_voter_1_0: 打包的实现均被 tools/run_sim.sh 覆盖
  ✓ ldpc_decoder_1_0: 打包的实现均被 tools/run_sim.sh 覆盖
    Stage1: P4=4/0, P16=16/1；六文件源集与参数对齐；生产源码 SHA 已冻结；K 写死为 2
  ✓ Stage1生产参数、静态选择、源集与迁移算法契约一致

######## IP 打包卫生检查 PASS ########
```

`bash tools/check_repo_hygiene.sh`（退出码 0）：

```text
=== 仓库卫生检查 ===
  ✓ 仓库根目录无残留
  ✓ tools/ 下所有脚本均已登记进 README
  ✓ docs/ 现用文档均带序号
  ✓ 归档文档均已去号
  ✓ 水印未出现重复副本
  ✓ logs/ 子目录均已被 .gitignore 覆盖（或已刻意入库）
  ✓ 现行文档/源码的「文件:行号」引用均可解析且在范围内
  ✓ sw/app/ 与 workspace 同名文件逐字节相同
  ✓ tools/attic/ 下脚本均已登记进 README（或 attic 目录为空）
  ✓ hw/experimental/README.md「当前内容」表与目录实际文件一致
  ✓ 仓库内无重复 SHA-256 已跟踪文件（A1 通用判据）

######## 仓库卫生检查 PASS ########
```

`bash tools/run_sim.sh host` 退出码为 0：6 项通过、0 项失败；其中 client_core 的 25 个测试通过。根目录残留检查的 `find` 命令无输出。

### 未完成项与边界

首次编译尝试退出码为 1：Icarus 默认 `-g2005` 不接受 TB 中已有的 `string` 声明。我在该用例加上 `-g2012` 后重跑通过；失败日志保留在 `logs/iverilog/run_20261014_180800_2_ldpc_decoder/`。成功日志位于 `logs/iverilog/run_20261014_180819_2_ldpc_decoder/`。

我没有执行 Git 写操作，因此三个黄金文件目前尚未暂存或提交，需由主会话审查后纳入 Git。当前 `git status` 还显示 `hw/ip/ldpc_decoder_1_0/` 为未跟踪目录，以及 `hw/ip/PACKAGED_VARIANTS.txt`、`hw/scripts/bd.tcl` 有修改；本任务没有修改这些路径，仿真和门禁是在当前工作树内容上通过的。未运行其他仿真项、Vivado 或板测。
