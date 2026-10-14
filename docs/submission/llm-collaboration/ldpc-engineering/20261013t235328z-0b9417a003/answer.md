> 脱敏副本，原件 `20261013T235328Z-0b9417a003/{prompt.txt,answer.md}`。本机绝对路径、邮箱、凭据形模式及非白名单私网 IP 已替换；除脱敏与换行规范化外保留原文。

## 结论

**产出路径：本次最终答复；未写入或修改仓库文件。** 分析输入为 [`dvb_s2_r5_6.pchk`](<仓库根目录>/clients/python/resources/dvb_s2_r5_6.pchk)，SHA-256 为 `9b33ea42f3334e5fbc2aa3cb4b76d968a184da591c9dcb0284a29b3964c407dc`。

以下结果按**连续校验行分组**计算：L=4 时批次为 0–3、4–7……；L=22 时批次从 0 开始，最后一批有 20 行。相同变量在同拍被多行读取时，按一次物理读并向各 lane 广播计算。结论只覆盖 LLR 读地址；并行写回、更新顺序和逐边消息存储未建模。

穷举 `.pchk` 得到：30 个 `r mod 30` 类各有 20 个信息基地址；因此每行有 20 条信息边，校验边是双对角结构。行 `r=30k+a` 的信息变量列可由各基地址 `x=30s+a ∈ B_t` 生成：

```text
c = 10800 + 360t + ((k-s) mod 360)
```

同一信息列的邻接校验行具有相同的 `r mod 30`。一拍处理的连续行数最多为 22，小于 30，所以同拍的信息地址不重复；重复地址来自相邻行共享的校验变量。

令 `W` 表示一拍内去重后的 LLR 地址数。完整批次中，起始行为 0 时 `W=20L+L`，其他批次为 `W=20L+(L+1)`。逐行验证结果：

| 并行度 L | 每拍唯一地址数 W | 已证明的 bank 下界 | 静态着色启发式上界 |
|---:|---:|---:|---:|
| 1 | 第 0 行 21，其余 22 | 22 | 29 |
| 4 | 第 0 批 84，其余 85 | 85 | 97 |
| 22 | 第 0 批 462；489 批为 463；末批 421 | 463 | 476 |

下界来自每批地址集合必须使用互不相同的 bank。上界是对真实变量地址冲突超图找到的有效着色：L=1、4 用 DSATUR 贪心，L=22 用按关联批次数排序的 first-fit。**这些是上下界，不是精确最小值；精确染色数未能定论。**

## Bank 映射实测

| L | `column mod 4` 最坏单 bank 请求数 | QC 线性映射搜索的最好结果 | 搜索到的 `(A,C,D)` |
|---:|---:|---:|---:|
| 1 | 14 | 11 | (1,0,2) |
| 4 | 43 | 30 | (1,3,0) |
| 22 | 206 | 128 | (1,0,0) |

QC 搜索采用信息列坐标 `t, q=floor(m/30), a=m mod 30`，测试了全部 64 个映射：

```text
bank = (A*t + C*q + D*a) mod 4
校验列 bank = column mod 4
```

线性映射结果只对这 64 种映射、以及上述校验列映射成立，不是所有 QC 映射的最优值。原先 `column mod 4` 的单行最坏冲突数 14 也复现了。

**600 个基地址着色尝试：**按 `x mod 30` 分组后得到 30 个 `K20`，每组可用 20 个局部颜色着色。但颜色取决于当前边的基地址。逐项检查发现，54,000 个信息变量列都需要 3 个或 13 个不同的基地址颜色。因而这种按边着色不能直接用作变量存储的静态 bank 映射。

**最小 bank 数仍未精确求出。**实际变量地址图着色给出了表中的有效静态映射上界；在下界颜色数处的贪心失败不能证明不可着色。

## 不复制与复制下界

若使用 4 个单端口 bank、每份 LLR 全量复制 `p` 份，总读端口数为 `4p`。仅从地址数可得：

| L | `p ≥ ceil(max(W)/4)` | 32 块 BRAM36/份对应的容量下界 |
|---:|---:|---:|
| 1 | 6 | 192 |
| 4 | 22 | 704 |
| 22 | 116 | 3,712 |

这些是端口总量下界。对已测试的 QC 四 bank 映射，最坏 bank 占用分别为 11、30、128；对应足够的复制数，因此 L=4 的测试映射需要 30 份，而 `p=22` 是否可达未验证。

不复制 LLR 在抽象 bank 模型下**可以做到无冲突**：表中的 29、97、476 个 bank 是找到的构造性上界。按题设每个逻辑 bank 使用一个单端口 BRAM36，并计入 H 表 1 块和上片 permutation 32 块：

- L=4：bank 下界 85，故至少 `85+1+32=118` 块；已找到的 97-bank 映射为 130 块。两者都超过 92 块余量。
- L=22：下界已是 `463+1+32=496` 块。
- 四 bank 复制的 L=4 下界是 `704+1+32=737` 块。

因此，**四 bank 复制方案明确超出余量**。单份 LLR 的 bank 数与 BRAM36 的实际端口/容量映射尚未综合验证；若不把 permutation 放上片，L=4 的单端口 BRAM 估算范围为 86–98 块，是否能落入 92 块余量仍无法定论。BRAM 双端口或 LUTRAM 的映射没有评估。

## 分拍调度

对 L=4 的一批，85 个唯一地址由四个共享 bank 服务至少需要 `ceil(85/4)=22` 拍。单独处理一行的 22 条边则至少需要 `ceil(22/4)=6` 拍。这里按**四个共享端口服务四行**计算，所以一批四行是至少 22 拍。

使用上表的最佳 QC 四 bank 映射 `(1,3,0)`，每批拍数等于四个 bank 中请求数的最大值。实测：

- 最坏批次 30 拍；
- 2,700 批共 **66,435 拍/轮**，相对每批一拍的 2,700 拍基线为 **24.61 倍**；
- 45 轮共 **2,989,575 拍**；基线是 121,500 拍。

22 倍是地址总数给出的理想下界；24.61 倍是这组静态映射的实际调度结果，不是所有映射下的最优值。`column mod 4` 的对应结果为每轮 97,380 拍、最坏批次 43 拍，即 36.07 倍。

## 复现命令

以下命令从仓库内解析器读取 `.pchk`，复算每拍地址数、4-bank 映射结果和着色上界；不写仓库文件：

```bash
python3 - <<'PY'
import sys, heapq
from collections import Counter
from pathlib import Path
import numpy as np

sys.path.insert(0, "clients/python")
from native_ldpc import load_pchk

rows = load_pchk(Path("clients/python/resources/dvb_s2_r5_6.pchk"))
N = 64800

def batches(L):
    return [
        sorted(set(int(c) for row in rows[s:s+L] for c in row))
        for s in range(0, len(rows), L)
    ]

for L in (1, 4, 22):
    bs = batches(L)
    sizes = Counter(map(len, bs))
    print("W", L, dict(sorted(sizes.items())))

    parts = []
    direct = 0
    for cols in bs:
        c = np.asarray(cols, dtype=np.int64)
        direct = max(direct, int(np.bincount(c % 4, minlength=4).max()))
        d = c[c >= 10800] - 10800
        p = c[c < 10800] % 4
        parts.append((d // 360, (d % 360) // 30, d % 30, p))
    best = (10**9, None)
    for A in range(4):
        for C in range(4):
            for D in range(4):
                occ = []
                for t, q, a, p in parts:
                    b = np.concatenate(((A*t + C*q + D*a) % 4, p))
                    occ.append(int(np.bincount(b, minlength=4).max()))
                if max(occ) < best[0]:
                    best = (max(occ), (A, C, D), sum(occ))
    print("4-bank", L, "column_mod4=", direct,
          "best_QC_linear(max,coeff,sum_cycles)=", best)

def incidence(bs):
    inc = [[] for _ in range(N)]
    for b, vs in enumerate(bs):
        for v in vs:
            inc[v].append(b)
    return inc

# DSATUR 贪心：L=1、4
for L, limit in ((1, 30), (4, 98)):
    bs = batches(L)
    inc = incidence(bs)
    deg = [sum(len(bs[b])-1 for b in x) for x in inc]
    blocked = [0]*N
    sat = [0]*N
    ver = [0]*N
    colors = [-1]*N
    used = [0]*len(bs)
    heap = [(0, -deg[v], v, 0) for v in range(N)]
    heapq.heapify(heap)
    assigned = 0
    while heap:
        sn, dn, v, version = heapq.heappop(heap)
        if colors[v] >= 0 or version != ver[v] or -sn != sat[v]:
            continue
        forbidden = blocked[v]
        color = (((forbidden + 1) & ~forbidden).bit_length() - 1)
        assert color < limit
        colors[v] = color
        assigned += 1
        bit = 1 << color
        for b in inc[v]:
            if used[b] & bit:
                continue
            used[b] |= bit
            for u in bs[b]:
                if colors[u] < 0 and not (blocked[u] & bit):
                    blocked[u] |= bit
                    sat[u] += 1
                    ver[u] += 1
                    heapq.heappush(
                        heap, (-sat[u], -deg[u], u, ver[u])
                    )
    assert assigned == N
    assert all(len({colors[v] for v in x}) == len(x) for x in bs)
    print("DSATUR", L, max(colors) + 1)

# first-fit，按关联批次数降序：L=22
L = 22
bs = batches(L)
inc = incidence(bs)
used = [0]*len(bs)
colors = [-1]*N
order = sorted(range(N), key=lambda v: (-len(inc[v]), v))
for v in order:
    forbidden = 0
    for b in inc[v]:
        forbidden |= used[b]
    color = (((forbidden + 1) & ~forbidden).bit_length() - 1)
    colors[v] = color
    bit = 1 << color
    for b in inc[v]:
        used[b] |= bit
assert all(len({colors[v] for v in x}) == len(x) for x in bs)
print("first-fit", L, max(colors) + 1)
PY
```

复现确认：矩阵 10,800 行，度为 21 的行 1 个、度为 22 的行 10,799 个；上述脚本应得到 W 分布和着色上界表中的数值。

## 未完成项与结论边界

精确最小染色数、四 bank 的最小复制数、非线性 bank 映射、BRAM 双端口/宽深度规划、写回冲突与真实 RTL 时序均未定论；未运行 Vivado、XSim 或板级验证。
