> 脱敏副本，原件 `20261014T030737Z-f566498c16/{prompt.txt,answer.md}`。本机绝对路径、邮箱、凭据形模式及非白名单私网 IP 已替换；除脱敏与换行规范化外保留原文。

## 结论

按本文列明的确定性 DSATUR 规则，L=1 得到 **29 色**；L=2 得到 **52 色**，不是背景中的 53 色。52 是这次贪心着色的结果，不是图的最小色数证明；L=2 的 W=43 只给出 43 色的下界。

在检验的低复杂度公式族中，没有找到能精确复现这份列色映射的公式。按映射建一张颜色表只需 **6 bit/列**：原始容量下界约 11 个 BRAM36，单副本可放进 92 块余量。但若每拍并行查询一批的 43 个列色，简单双读口 BRAM 方案约需 22 份表、合计 **242 块 BRAM36**。因此，**表的原始存储容量放得下；按 43 路并行查询实现时，放不下**。

## 着色结果与映射复现

图含 64,800 个列节点。冲突边来自同一批中共同出现的列对，跨批重复边去重。DSATUR 每轮按以下顺序选择节点：饱和度最高、静态度数最高、列号最小；为选中节点分配最小可用颜色。

| L | W 分布 | 着色数 | 无向冲突边数 | 节点度均值 | 单节点颜色数范围 | 列序颜色数组 SHA-256 |
|---|---|---:|---:|---:|---:|---|
| 1 | 21×1，22×10,799 | 29 | 2,494,779 | 77.00 | 2–2,823 | `3202f5824dd0cd46a2da90241774f9b63a659a0fd73ad11fb40edd507a8a5a02` |
| 2 | 42×1，43×5,399 | 52 | 4,870,398 | 150.32 | 5–2,096 | `cdae20f43ef529edfb65287ca724246a24b1196703a78ccda958b27458dd5f3d` |

哈希按列号 0..64,799 的颜色序列，以 little-endian int16 编码计算。下方命令会重建并验证着色，并把完整的 `列号,颜色` 映射打印到标准输出；这次没有把映射写入文件。

```python
python3 - <<'PY'
import hashlib, heapq
from pathlib import Path
import numpy as np

p = Path("clients/python/resources/dvb_s2_r5_6.pchk")
assert hashlib.sha256(p.read_bytes()).hexdigest() == \
    "9b33ea42f3334e5fbc2aa3cb4b76d968a184da591c9dcb0284a29b3964c407dc"

raw = np.fromfile(p, dtype="<i4")
segments, cur = [], []
for value in raw[3:]:
    if value < 0:
        segments.append(cur)
        cur = []
    else:
        cur.append(int(value))
segments.append(cur)
rows = [
    np.asarray([x - 1 for x in row if x > 0], dtype=np.int32)
    for row in segments[1:]
]
assert len(rows) == 10800 and sum(map(len, rows)) == 237599

N = 64800

def dsatur(L):
    batches = [
        np.unique(np.concatenate(rows[i:i + L]))
        for i in range(0, len(rows), L)
    ]
    W, counts = np.unique([len(b) for b in batches], return_counts=True)
    print("L/W:", L, dict(zip(map(int, W), map(int, counts))))

    chunks = []
    for b in batches:
        i, j = np.triu_indices(len(b), 1)
        u, v = b[i], b[j]
        chunks.extend((u.astype(np.int64) * N + v,
                       v.astype(np.int64) * N + u))
    keys = np.unique(np.concatenate(chunks))
    src = (keys // N).astype(np.int32)
    nbr = (keys % N).astype(np.int32)

    degree = np.bincount(src, minlength=N).astype(np.int32)
    ptr = np.empty(N + 1, dtype=np.int64)
    ptr[0] = 0
    np.cumsum(degree, out=ptr[1:])

    color = np.full(N, -1, dtype=np.int16)
    masks, saturation = [0] * N, [0] * N
    heap = [(0, -int(degree[v]), v) for v in range(N)]
    heapq.heapify(heap)

    while heap:
        neg_sat, neg_degree, v = heapq.heappop(heap)
        if color[v] >= 0:
            continue
        if neg_sat != -saturation[v] or neg_degree != -int(degree[v]):
            continue

        used, c = masks[v], 0
        while (used >> c) & 1:
            c += 1
        color[v] = c

        for w0 in nbr[ptr[v]:ptr[v + 1]]:
            w = int(w0)
            if color[w] < 0 and not ((masks[w] >> c) & 1):
                masks[w] |= 1 << c
                saturation[w] += 1
                heapq.heappush(
                    heap, (-saturation[w], -int(degree[w]), w)
                )

    assert all(len(np.unique(color[b])) == len(b) for b in batches)
    hist = np.bincount(color)
    digest = hashlib.sha256(color.astype("<i2").tobytes()).hexdigest()
    print("colors:", len(hist), "degree min/mean/max:",
          int(degree.min()), float(degree.mean()), int(degree.max()))
    print("class sizes:", hist.tolist())
    print("map SHA-256:", digest)
    print("column,color")
    for column, c in enumerate(color):
        print(f"{column},{int(c)}")

for L in (1, 2):
    dsatur(L)
PY
```

## 代数结构检验

以下公式检查只把 `(t,q,a)` 用于 54,000 个信息列；对 10,800 个校验列另检验了一维 `bank=(αr+δ) mod B`，也没有精确解。

| 形式 | 搜索范围与判据 | 结果 |
|---|---|---|
| 直接仿射 `(αt+βq+γa+δ) mod B` | 精确解要求 `B≥颜色数 C`。对 `B=C..2C−2`，原点和三个相邻点唯一确定四个参数，逐点检查全体信息列。对 `B≥2C−1`，相邻颜色差的取值范围小于 B，因此每个轴上的差必须恒定；实测不恒定。 | L1 `B=29..56`、L2 `B=52..102` 均无精确解；更大的 B 也被差分条件排除。B=53 在有限搜索内。 |
| 直接仿射的近似最好值 | 对指定代表模数，把全部 `α,β,γ,δ ∈ Z_B` 用四维相关计数穷举；这是近似匹配数，不影响上面的全 B 精确判定。 | L1：B=29、53 的最好值均为 2,278/54,000（4.2185%），公式为常数 22。L2：B=52、53 均为 1,212/54,000（2.2444%），公式为常数 42。 |
| 单个周期余数项 | 搜索 `αt+βq+γa+δ(x mod k)+ε`，周期项分别放在 t、q、a；k 遍历各维度的有效周期。有限 B 与直接仿射相同；更大的 B 用整数差分模式检查。 | 共 186 个 k；有限范围检查 L1 5,208 个、L2 9,486 个 `(B,k)` 组合。没有组合通过必要差分条件，候选公式数为 0；较大 B 的差分模式命中也为 0。 |
| 区间分段局部仿射 | 分别允许按 t、q 或 a 分段，最多细分到每个取值各自一段；对每个 B 检查每个单点切片能否由剩余维度的局部仿射式精确表示。任一切片失败，就不可能有包含该切片的仿射区间段。 | L1 的 150、12、30 个切片均为 0 个可表示；L2 也均为 0 个。有限 B 共检查 L1 5,376、L2 9,792 个切片–B 组合。 |
| 基地址 `x∈B_t` 单值映射 | 若颜色仅由 x 决定，同一 x 所关联列必须要求相同颜色。 | 600 个基地址项中有 472 个不同 x；**472/472 个 x 都要求多个颜色**，故单值 `g(x)` 不成立。 |
| 固定置换后取模 `π(列) mod B` | 置换后的模数桶大小必然均衡；允许颜色任意重标后，比较实际颜色类大小与均衡桶容量。 | L2 需要 44 桶各 1,246 项、8 桶各 1,247 项；L1 需要 15 桶各 2,234 项、14 桶各 2,235 项。两者都不能精确匹配。允许最佳颜色重标后的最大重合为 L2 59,819/64,800（92.3133%）、L1 58,058/64,800（89.5957%）。 |

切片检验覆盖“按一个坐标区间分段、每段使用局部仿射式”，包括把该坐标细分到单点；它不等价于穷举所有多维矩形分段。多个周期项、变量间交叉项或任意复杂的三维分段也没有穷举。因而结论是：**这份映射不符合上述低复杂度结构，需用查表或更复杂编码；不是对所有可能程序公式的数学不可能性证明。** 校验列的一维仿射式同样失败，但未把所有其它 parity 专用公式族逐一搜索。

## 查表规模与 BRAM36

| 映射 | 每项位宽 | 全表逻辑位数 | 仅按总位数的 BRAM36 下界 |
|---|---:|---:|---:|
| L2，52 色（53 色也相同位宽） | 6 bit | 64,800×6 = 388,800 bit | 11 块 |
| L1，29 色 | 5 bit | 64,800×5 = 324,000 bit | 9 块 |

按常见 BRAM36 配置估算，L2 每列一个 6-bit 字、用 x9/4,096 深度存储时需 `ceil(64,800/4,096)=16` 块；将 3 个颜色打包进 x18 字并使用双口时，21,600 个字深度需 `ceil(21,600/2,048)=11` 块。11 块是紧凑打包后的单副本估算，未计外围选择逻辑。

因此，单副本表与约 27 块 LLR 存储合计约 **38–43 块**，低于 92 块余量。若每拍并行查询 43 个列色，x18 双读口下需要 22 份完整表，即约 **242 块**；加上约 27 块 LLR 为约 269 块，超过 92 块。这个多端口数字基于“43 路同拍查询、每份表提供两路读”的 BRAM 复制假设；串行查询或把颜色预先编码进调度会改变资源与吞吐量，本次未实现验证。

**产出路径：**没有仓库文件；完整映射通过上面的命令打印。矩阵 SHA-256、冲突批次、着色合法性及映射哈希均已核对。未完成边界是任意复杂公式和多维分段的全局搜索；本次检验的四类映射形式及其搜索范围已在上表明确列出。
