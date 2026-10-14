> 脱敏副本，原件 `20261013T235255Z-f14dd13b6e/{prompt.txt,answer.md}`。本机绝对路径、邮箱、凭据形模式及非白名单私网 IP 已替换；除脱敏与换行规范化外保留原文。

## 结论

**实测：采用饱和更新时，8 位和 6 位都能复现本次样本中 double 译码器成功的完整码字。**共测 14 个回传文件、12 个不同输入：double、8 位和 6 位都在 14 个文件中成功 8 个，在去重后的输入中成功 6 个。8 个成功文件的 64,800 位码字与 Python double 结果逐位相同；成功率差为 **0 个百分点**。

**回绕不适用：**8 位和 6 位回绕版在这 14 个输入上都没有收敛，连 double 成功的样本也未通过 syndrome。未观察到回绕版收敛到另一个合法码字。

本结论使用 Q1 量化：LLR 步长 `Δ=0.5`，double 的 `±3.0` 精确映射为整数 `±6`。6 位是本次验证中通过的最低测试位宽；**5 位及以下未测**。量化尺度会改变结果：例如 6 位改用 Q2（`Δ=0.25`）后，一个 double 成功输入不收敛，另一个 double 失败输入收敛到合法码字；该码字的信息位恰与 `source_bit.txt` 一致。因此，“6 位够用”必须连同缩放和饱和范围一起限定。

## 现有译码算法

- `native_ldpc.hard_decode` 和 `c_ldpc_accel.c::ldpc_decode` 都是 **flooding Min-Sum**：一轮中各校验节点基于当前 LLR 计算消息，累加到新 LLR 后再进入下一轮。不是 layered，也不是 sum-product。[Python 实现](<<仓库根目录>/clients/python/native_ldpc.py:59>)、[C 实现](<<仓库根目录>/clients/python/c_ldpc_accel.c:231>)
- **无归一化因子、无偏移因子**：直接使用第一、第二小幅值。
- 接收硬比特映射为 `1→+3.0`、`0→−3.0`；硬判决是 `LLR > 0` 判 1，否则判 0。每轮检查 syndrome，全为 0 即停止；没有 CRC 终止条件。[Python LLR、判决和早停](<<仓库根目录>/clients/python/native_ldpc.py:72>)、[C LLR、判决和早停](<<仓库根目录>/clients/python/c_ldpc_accel.c:199>)
- 最大 50 轮。Python 默认 `max_iter=50`；C 的 `max_iter<=0` 时也回落到 50。
- 管线 `backend="auto"` 在 C 动态库可用时选 C，否则选 Python。[管线选择逻辑](<<仓库根目录>/clients/python/ldpc_pipeline.py:204>)

## 输入、尺度与结果

使用了长稳报告中的 14 个 `dec_run_*.txt`，每个都是 64,800 字节的 0/1 回传流；报告记录了板端耗时、LDPC 状态和图像哈希。[测试报告](<<仓库根目录>/tests/stress_results/stress_20260905T204254/summary.md:10>)。其中 6/7 和 8/11 的文件内容分别重复，故 14 个文件对应 12 个独立 SHA-256 输入；**没有另造向量**。

定点模拟在每轮变量节点聚合 `LLR0 + Σ消息` 后执行 W 位饱和或二进制补码回绕，硬判决和 syndrome 早停保持原逻辑。Q1 下 `±3→±6`，`Δ=0.5`：W8 范围为 `[-128,127]`，W6 为 `[-32,31]`。

| 输入文件 | 原始输入 SHA-256 |
|---|---|
| `001_se150_1024` | `51f5823fc4c63cf050fc2ab11a3e45545960d717de0ed1546c5e236aa43c4394` |
| `002_se150_1088` | `d84d978f3afa05ad25c2c9149181e70f4f4e0c467d2e942e7a8d19f81371042a` |
| `003_se150_1152` | `4a7c4e8aba3e929514772e7354035cd099b2697732e9cd25472fb7deb3a7ce36` |
| `004_se150_1216` | `a9c1c39a5194a6fc707cb06688fcd1eac930fc99f9109d014d662385cf1e3df0` |
| `005_se150_1280` | `973780a06409d71e30a453cf5fc3680abf5057c5453ff8ec50b2d42689cc9678` |
| `006/007_se150_1312` | `b257e41512d439d6a48d20fd71a858a2e14d7d4ee12c19f4e7a4acd4bba026e2` |
| `008/011_se150_2048` | `874d814bcc7a9415c46cba561d719afa874db45862f4c560e82be7c2c07bb1c8` |
| `009_se150_4096` | `a737e816c6f7d2632946c9ce7e143a33f71dc9863cfe3abade9547964ac327a7` |
| `010_se150_2048` | `65786c175d90fcc746537b6848669d779c8aa3dafb10596d3b29b05fed4dc198` |
| `012_se150_8192` | `696c2ead2ab3a265e419939d8013738ab596729f932c1f834c5ef3bf692e8353` |
| `013_se150_16384` | `d1844257ee65035238978dbab1d5ce0bc11d6f765568c892cc883c0d8f902df5` |
| `014_se150_4096` | `7c14d0213c0a15bd9ed9c2c6873f7fdd323cef8d10170829ae906b54a8e97e01` |

Q1 的逐样本结果如下。`D/W8/W6` 列是 double、8 位饱和、6 位饱和的收敛轮数；`F50` 表示 50 轮后未收敛。

| 样本 | Double | W8 饱和 | W6 饱和 | 收敛码字比较 |
|---|---:|---:|---:|---|
| 001–005、010 | F50 | F50 | F50 | 两种饱和版均未产生合法码字 |
| 006/007 | 28 | 46 | 25 | 完整码字相同 |
| 008/011 | 5 | 5 | 5 | 完整码字相同 |
| 009 | 47 | 10 | 5 | 完整码字相同 |
| 012 | 47 | 10 | 5 | 完整码字相同 |
| 013 | 4 | 4 | 4 | 完整码字相同 |
| 014 | 46 | 21 | 15 | 完整码字相同 |

汇总：double、W8 饱和、W6 饱和均为 **8/14 文件、6/12 唯一输入**；W8 和 W6 的成功输出与 double 的完整码字差异均为 **0 bit**。W8、W6 回绕版均为 **0/14**，double 原本成功的输入也都在 50 轮后仍有失败校验。

Q2 的尺度敏感性检查中，W6 饱和版有 **7/14** 文件收敛：`004` 在 double 不收敛时收敛到合法码字，且输出信息位与 `source_bit.txt` 的差异为 0；`006/007` 则从 double 的 28 轮成功变为 50 轮未收敛。该检查说明饱和范围会改变结果，不能只报位宽。

## 复现命令

从仓库根目录运行以下只读脚本。默认 `AMP=6` 是 Q1 主结果；把 `LDPC_FIXED_LLR_AMP=6` 改成 `12` 可复测上面的 Q2 尺度检查。脚本逐项打印输入 SHA、双精度参考结果、各定点模式的收敛轮数及 syndrome，并核对成功时的完整码字。

```bash
LDPC_FIXED_LLR_AMP=6 python3 - <<'PY'
from pathlib import Path
import hashlib
import os
import sys
import numpy as np

sys.path.insert(0, str(Path("clients/python").resolve()))
import native_ldpc
from c_ldpc import decode_bits_c

res = Path("clients/python/resources")
pchk = res / "dvb_s2_r5_6.pchk"
perm_path = res / "permutation64800"
rows = native_ldpc.load_pchk(pchk)
perm = native_ldpc.load_permutation(perm_path)
M, N = 10800, 64800
D = max(map(len, rows))
matrix = np.zeros((M, D), dtype=np.int64)
valid = np.zeros((M, D), dtype=bool)
for r, cols in enumerate(rows):
    matrix[r, :len(cols)] = cols
    valid[r, :len(cols)] = True
edges = matrix.ravel()
AMP = int(os.environ.get("LDPC_FIXED_LLR_AMP", "6"))

def syndrome(bits):
    x = bits[matrix].copy()
    x[~valid] = 0
    return int(np.count_nonzero(x.sum(axis=1) & 1))

def fixed_decode(natural, width, overflow):
    lo, hi = -(1 << (width - 1)), (1 << (width - 1)) - 1
    llr0 = np.where(natural == 1, AMP, -AMP).astype(np.int64)
    llr = llr0.copy()
    for iteration in range(1, 51):
        mags = np.abs(llr)[matrix]
        mags[~valid] = 1 << 60
        signs = np.sign(llr)[matrix]
        signs[~valid] = 1
        row_signs = np.prod(signs, axis=1)
        sorted_mags = np.sort(mags, axis=1)
        min1, min2 = sorted_mags[:, 0], sorted_mags[:, 1]
        equal = mags == min1[:, None]
        prior = np.zeros_like(equal, dtype=np.int8)
        prior[:, 1:] = np.cumsum(equal.astype(np.int8), axis=1)[:, :-1]
        first_min = equal & (prior == 0)
        msg = row_signs[:, None] * signs * np.where(
            first_min, min2[:, None], min1[:, None]
        )
        msg[~valid] = 0
        raw = llr0 + np.bincount(
            edges, weights=msg.ravel(), minlength=N
        ).astype(np.int64)
        if overflow == "sat":
            llr = np.clip(raw, lo, hi)
        else:
            llr = ((raw - lo) % (1 << width)) + lo
        decoded = (llr > 0).astype(np.uint8)
        failed = syndrome(decoded)
        if failed == 0:
            return decoded, iteration, 0
    return decoded, 50, failed

files = sorted(Path("tests/stress_results/stress_20260905T204254")
               .glob("dec_run_*.txt"))
counts = {k: 0 for k in
          ("double", "8sat", "8wrap", "6sat", "6wrap", "8same", "6same")}
unique = {}

for path in files:
    raw = path.read_bytes()
    assert len(raw) == N and set(raw) <= {ord("0"), ord("1")}
    sha = hashlib.sha256(raw).hexdigest()
    rx = np.frombuffer(raw, dtype=np.uint8) - ord("0")
    natural = native_ldpc.deinterleave(rx, perm)

    try:
        double_cw, d_init, d_iter = native_ldpc.hard_decode(natural, rows)
        double_ok = True
    except RuntimeError:
        double_cw, double_ok = None, False

    c_info, c_init, c_iter = decode_bits_c(
        rx, pchk, perm_path, raise_on_error=False
    )
    assert double_ok == (c_info is not None)
    if double_ok:
        assert (d_init, d_iter) == (c_init, c_iter)
        assert np.array_equal(double_cw[10800:], c_info)

    counts["double"] += int(double_ok)
    row = [path.name, sha, f"double={'PASS' if double_ok else 'FAIL'}"]
    u = unique.setdefault(sha, {})
    u["double"] = double_ok

    for width in (8, 6):
        for mode in ("sat", "wrap"):
            cw, iters, failed = fixed_decode(natural, width, mode)
            ok = failed == 0
            key = f"{width}{mode}"
            counts[key] += int(ok)
            same = ok and double_ok and np.array_equal(cw, double_cw)
            if same:
                counts[f"{width}same"] += 1
            u[key] = ok
            status = ("same-full-codeword" if same else
                      "valid-vs-double-fail" if ok and not double_ok else
                      "different-valid" if ok else "no-converge")
            row.append(f"W{width}-{mode}={iters}it/synd{failed}/{status}")
            if AMP == 12 and path.name == "dec_run_004_se150_1216.txt" \
                    and width == 6 and mode == "sat" and ok:
                src = Path("data/R0.83_data/Source data/Original data files/source_bit.txt")
                source = np.frombuffer(src.read_bytes(), dtype=np.uint8) - ord("0")
                print("Q2 run004 info-bit diff:",
                      int(np.count_nonzero(cw[10800:] != source)))
    print(" | ".join(row), flush=True)

print("run-counts:", counts)
print("unique-SHA-count:", len(unique))
print("unique-SHA successes:",
      {k: sum(bool(v.get(k)) for v in unique.values())
       for k in ("double", "8sat", "8wrap", "6sat", "6wrap")})
PY
```

资源 SHA-256：`dvb_s2_r5_6.pchk`=`9b33ea42f3334e5fbc2aa3cb4b76d968a184da591c9dcb0284a29b3964c407dc`；`permutation64800`=`42f751c6d95c782ccaa3171aacf354435f77bc4186e433f52e89827995416742`；本次加载的 `libc_ldpc.so`=`ce92dcc1026cb4e36b9dd9092c703e428f9ab59e4a4037ca4051e85688cb67a6`。

## 未验证边界与产出

这是 2026-09-05 SE150 测试活动中的 12 个唯一输入，不覆盖所有噪声分布、数据集或软输入 LLR。低于 6 位、FPGA RTL/综合、按每条边逐次饱和的更新次序均未验证；本结论只针对这里实测的硬比特输入、Q1 缩放和“变量节点聚合后饱和”语义。

未修改仓库文件。沙箱将 `/tmp` 也挂为只读；尝试写临时文件返回 `EROFS`，因此没有可交付的 `/tmp` 脚本文件。定点实现通过内联 Python 执行，完整复现代码已列在上面。
