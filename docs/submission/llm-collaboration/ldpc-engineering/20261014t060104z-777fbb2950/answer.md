> 脱敏副本，原件 `20261014T060104Z-777fbb2950/{prompt.txt,answer.md}`。本机绝对路径、邮箱、凭据形模式及非白名单私网 IP 已替换；除脱敏与换行规范化外保留原文。

## 交付文件

- 新增 [ldpc_decoder_p1.v](<仓库根目录>/hw/experimental/ldpc_decoder_p1.v)：p=1 flooding Min-Sum 原型，使用真实转置桶表；LLR 为 Q1 6-bit 饱和，逐列聚合使用 12-bit 累加。
- 新增 [tb_ldpc_decoder_p1.v](<仓库根目录>/hw/experimental/tb_ldpc_decoder_p1.v)：从 summary.tsv 读取期望状态和轮数，比较完整码字；支持黄金码字回灌，检查合法输入是否 0 轮返回。
- 更新 [README.md](<仓库根目录>/hw/experimental/README.md#L16)：登记两个新文件和当前验证边界。

未执行 Git 写操作。工作区变更仅有上述三个文件；`git diff --check` 通过，仓库根目录没有 `.log/.jou/.str/.pb` 残留。

## 仿真结果

编译命令：

```bash
iverilog -g2012 -Wall -s tb_ldpc_decoder_p1 -o <本机路径> hw/experimental/ldpc_decoder_p1.v hw/experimental/tb_ldpc_decoder_p1.v
```

编译通过，无警告。最终版本的原始仿真输出：

**013：PASS**

```text
START sample=013_se150_16384 codeword_input=0 expected_converged=1 expected_iters=4
OUTPUT MATCH sample=013_se150_16384 compared_bits=64800 bit_mismatches=0
PASS sample=013_se150_16384 converged=1 iter_count=4 bit_mismatches=0 compared_bits=64800
```

**008：PASS**

```text
START sample=008_se150_2048 codeword_input=0 expected_converged=1 expected_iters=5
OUTPUT MATCH sample=008_se150_2048 compared_bits=64800 bit_mismatches=0
PASS sample=008_se150_2048 converged=1 iter_count=5 bit_mismatches=0 compared_bits=64800
```

**合法码字回灌：PASS，验证初始综合检查返回 0 轮**

```text
START sample=013_se150_16384 codeword_input=1 expected_converged=1 expected_iters=0
OUTPUT MATCH sample=013_se150_16384 compared_bits=64800 bit_mismatches=0
PASS sample=013_se150_16384 converged=1 iter_count=0 bit_mismatches=0 compared_bits=64800
```

**006：严格轮数判据 FAIL，码字逐位相同**

```text
START sample=006_se150_1312 codeword_input=0 expected_converged=1 expected_iters=28
FAIL sample=006_se150_1312 status expected=(conv:1,iters:28) actual=(conv:1,iters:25,error:0)
OUTPUT MATCH sample=006_se150_1312 compared_bits=64800 bit_mismatches=0
FAIL sample=006_se150_1312 converged=1 iter_count=25 status_mismatch=1 bit_mismatches=0
FATAL: hw/experimental/tb_ldpc_decoder_p1.v:213:
       Time: 645747746000 Scope: tb_ldpc_decoder_p1
```

**006 的差异没有通过放宽判据处理。** summary.tsv 的 28 轮来自浮点 `hard_decode`；规定的 Q1 6-bit 饱和实现第 25 轮收敛，输出与黄金码字完全相同。仓库既有 [L1 定点审计](<仓库根目录>/logs/audit/ldpc-fixedpoint.md)也记录了该样本 W6 饱和为 25 轮、码字与 double 相同。也就是说，当前“必须按 L1 饱和”和“轮数必须等于浮点黄金”对 006 不兼容。

独立核对了转置桶生成的邻接：10,800 行、237,599 条边均与 pchk 邻接集合一致。

## 未完成与验证边界

已验证：Icarus 编译；013、008 的收敛状态、轮数与 64,800 位输出；合法码字 0 轮返回；006 的码字一致性及轮数差异。

未验证：Vivado 综合与 BRAM 推断、OOC/整机时序、板端行为。006 的轮数差异仍未解决；没有修改黄金数据或放宽 testbench 判据。
