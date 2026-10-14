> 脱敏副本，原件 `20261014T000641Z-b6e116553d/{prompt.txt,answer.md}`。本机绝对路径、邮箱、凭据形模式及非白名单私网 IP 已替换；除脱敏与换行规范化外保留原文。

## 结论

- **L=2 能落进 92 块 BRAM36 余量。**按已找到的 53-bank 无冲突映射和真双端口配对估算：LLR 需 27 块；加 H 表 1 块、片上 permutation 32 块，共 **60/92**。permutation 留 DDR 时为 **28/92**。
- 上一轮的 **“L=4 需要 118–130 块，所以放不下”结论被推翻**：把一个逻辑 bank 折算成一块 BRAM36 过于保守。L=4 的已找到映射是 97 个逻辑 bank，按 BRAM 真双端口配对并考虑 bank 深度，LLR 状态估算为 49 块；加 H 和片上 permutation 是 **82/92**，permutation 留 DDR 是 **50/92**。
- 这是存储容量和读端口的估算，**不是完整译码器已能综合或布线的证明**。bank 到物理地址的转换、写回调度和控制逻辑尚未实现验证。

## 问题 1：L=2、L=3 的访问与调度

下表的线性映射在 64 个 `(A,C,D)` 组合中，按“先最小化单 bank 最坏请求数，再最小化全轮周期数”选择。周期数按每批串行调度计算：每批周期数是四个 bank 中请求最多者的请求数，重复地址按一次读并广播。

| L | W（首批 / 其余批） | 无冲突 bank 下界 | DSATUR 着色上界 | `column mod 4` 最坏占用 | 最佳四 bank 映射：最坏占用 `(A,C,D)` | 每轮周期数 |
|---:|---:|---:|---:|---:|---:|---:|
| 2 | 42 / 43 | 43 | 53 | 22 | 16 `(1,3,0)` | 70,743 |
| 3 | 63 / 64 | 64 | 76 | 34 | 23 `(1,0,1)` | 70,476 |

**下界**是每批最大 W；**着色上界**是有效的 DSATUR 贪心着色结果，不代表最小着色数。64 组线性映射穷举只证明所列值在该映射族中的最优结果，不证明所有映射中的最优结果。

L=2 的 BRAM 账本即使沿用“每 bank 一块”的旧折算也只有 `53 + 1 + 32 = 86` 块；按双端口配对估算为 60 块。因此片上 permutation 和 DDR 两种情形都能落入 92 块余量。完整译码器的 LUT 与时序仍未验证。

## 问题 2：BRAM 折算与 XC7Z020 资源估算

### 实际端口与容量

RAMB36E1 真双端口可在两个端口上独立寻址；x9 配置相当于 4096 个 9-bit 地址行。两组逻辑 bank 可放进同一块 BRAM36 的**不同地址区间**，但两组深度之和须不超过 4096。这样每块支持两个独立读地址，满足两个逻辑 bank 同拍各读一次。[AMD UG953：RAMB36E1](https://docs.amd.com/r/2025.2-English/ug953-vivado-7series-libraries/RAMB36E1?contentId=Nm2aVbtVbH5UQNZ3PFqKqw)

宽度打包的 `512×72` 是简单双端口模式：有一个读地址和一个写地址，72 表示一次地址返回的位宽，**不是 72 个独立读地址**。不同 bank 的请求地址不同，打成宽字并不能满足独立访问要求。[AMD UG953：RAMB36E1](https://docs.amd.com/r/2025.2-English/ug953-vivado-7series-libraries/RAMB36E1?contentId=Nm2aVbtVbH5UQNZ3PFqKqw)

因此，L=4 的 85 个独立读至少需要 `ceil(85/2)=43` 块真双端口 BRAM36；已找到的 97-bank 着色映射对应 49 块。端口数仍是硬约束，所以折算不会降到单纯按存储位数算出的约 16 块。

### 着色映射的 BRAM 账本

下表的着色上界是有效映射；配对数按每对 bank 深度和不超过 4096 行计算。资源仅包括 LLR 状态、H 表与 permutation：

| L | bank 下界 / 已找到的着色数 | 着色映射的 LLR BRAM36 | permutation 片上：加 H 与 permutation | permutation 留 DDR：加 H |
|---:|---:|---:|---:|---:|
| 1 | 22 / 29 | 25 | 58/92 | 26/92 |
| 2 | 43 / 53 | 27 | 60/92 | 28/92 |
| 4 | 85 / 97 | 49 | 82/92 | 50/92 |

L=1 没有简单地把 29 除以二：DSATUR 颜色类大小不均，只有 4 对能装入一块 4096 行的 BRAM，因此是 25 块。L=2 有 26 对、L=4 有 48 对可配，分别得到 27、49 块。这些数是**由颜色分布和 BRAM 端口/深度规则推算的存储估算**，不是 Vivado 推断结果。

按 8-bit LLR 计，状态共 518,400 bit；x9 BRAM 行格式需要 583,200 bit，容量下界为 `ceil(583200/36864)=16` 块。另有一个低 BRAM、低吞吐方案：采用四 bank 线性映射并按 bank 分拍调度，四个 bank 各约 16,200 个节点，每个 bank 分成四个深度段，总计 16 块状态 BRAM36。加 H 与片上 permutation 为 49 块；permutation 留 DDR 为 17 块。它能省 BRAM，但不会每拍完成整批请求；每轮周期数就是上表对应四 bank 调度所示的数量。

### LUTRAM 与位宽取舍

XC7Z020 的 64×1 单端口分布式 RAM 使用一个 LUT；64×1 双端口配置使用两个 LUT，且分布式 RAM 只能放在 SLICEM。深度超过 64 还需要额外的宽函数复用器。[AMD UG474：Distributed RAM](https://docs.amd.com/r/en-US/ug474_7Series_CLB/Distributed-RAM-SLICEM-Only)

- 把 64800×8 bit LLR 全放单读口 LUTRAM，存储位数下界为 **8100 LUT**；按多个 bank 分开取整，存储约为 8.1k–8.9k LUT，另外还要 bank 控制和复用逻辑。仅按给出的 17,498 LUT 余量看容量有空间，但 SLICEM 余量、时序和控制开销未验证。
- 若每个存储位需要第二个独立读地址，64×1 双端口 LUTRAM 的存储估算约 **16,200 LUT**，尚未计逻辑，已经接近 17,498 的余量。
- 降低 LLR 位宽可减少状态容量，也可能利用更深的 BRAM 配置；但不会增加每块 BRAM 的独立读地址数。增加逻辑 bank 数可减少冲突周期，却会增加所需端口与 BRAM 数。

高并行着色映射还需要把原始列地址转换成 bank 及 bank 内地址。仅存 L=4 的 7-bit bank 标签就需 453,600 bit，约 14 块 BRAM36 的**原始存储容量**；这还没包含 bank 内地址，也没有解决每拍大量并行查询所需的读端口。它可以被紧凑逻辑或预计算结构替代，但本轮没有实现验证。

所以，旧的 L=4 不可行结论被推翻：**LLR 数据和读端口的可信估算是 49 块状态 BRAM，连同片上 permutation 与 H 表为 82 块，低于 92 块。**这不足以宣称完整的一拍 85 地址设计已经装得下；地址转换及写回可能增加资源，仍须 RTL 与 route 验证。

## 复现命令

输入为 [`dvb_s2_r5_6.pchk`](<仓库根目录>/clients/python/resources/dvb_s2_r5_6.pchk)，本轮检查的 SHA-256 为 `9b33ea42f3334e5fbc2aa3cb4b76d968a184da591c9dcb0284a29b3964c407dc`。解析器是 [`native_ldpc.py`](<仓库根目录>/clients/python/native_ldpc.py)。

以下脚本复算批次 W、64 个线性映射的最优占用和周期数；在仓库根目录运行，不写文件：

```bash
python3 - <<'PY'
import sys
from collections import Counter
from pathlib import Path
import numpy as np

sys.path.insert(0, "clients/python")
from native_ldpc import load_pchk

rows = load_pchk(Path("clients/python/resources/dvb_s2_r5_6.pchk"))

for L in (1, 2, 3, 4):
    batches = [
        sorted(set(int(c) for row in rows[s:s+L] for c in row))
        for s in range(0, len(rows), L)
    ]
    print("W", L, dict(sorted(Counter(map(len, batches)).items())))

    direct = 0
    choices = []
    for A in range(4):
        for C in range(4):
            for D in range(4):
                occ = []
                for cols in batches:
                    c = np.asarray(cols, dtype=np.int64)
                    direct = max(direct, int(np.bincount(c % 4, minlength=4).max()))
                    d = c[c >= 10800] - 10800
                    p = c[c < 10800] % 4
                    bank = np.concatenate((
                        (A*(d//360) + C*((d%360)//30) + D*(d%30)) % 4,
                        p
                    ))
                    occ.append(int(np.bincount(bank, minlength=4).max()))
                choices.append((max(occ), sum(occ), A, C, D))
    print("column_mod4_max", direct, "best(max,cycles,A,C,D)", min(choices))
PY
```

DSATUR 上界及 BRAM 深度配对数量可用前述 `batches(L)` 生成访问集合，再按 DSATUR 为冲突集合着色。复算时用 64,800 个节点、按 `(-饱和度, -度, 节点编号)` 排序，遇到已着色批次中的 bank 颜色就禁止该颜色；最后断言每批颜色互异。对每个颜色类计数后，将类大小排序，用双指针最多配对满足 `size[i]+size[j]≤4096` 的颜色类；物理状态 BRAM 数为“颜色类数−配对数”。得到的颜色类数为 L=1/2/3/4 的 **29/53/76/97**，状态 BRAM 数为 **25/27/38/49**。

**验证结果与边界：**本轮只读 Python 分析与校验和检查完成；没有改仓库文件、执行 Git 写操作、运行 Vivado/XSim 或接触板卡。尚未验证的项目是 bank 地址转换的 LUT/BRAM 成本、LLR 写回和读改写调度、完整译码器的边消息存储、实际综合与 route。
