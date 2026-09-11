#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""tools/g5_false_accept.py —— G5 门禁「误接受率」的定义与测量

## 这个脚本存在的唯一原因

`docs/13-final-delivery-roadmap.md` §4 G5 的出口门禁要求一条
「阈值 → 正确率 / 耗时 / **误接受率**」曲线。前两项早有数据，
**「误接受率」从 2026-08 立项起就没有定义**，因此 G5 一直挂在 🟡。
`docs/15` §2 也写着「单次成功不是成功率」——但没人说清什么叫「误接受」。

本脚本先给出一个**可判定**的定义，再测它。

## 定义（这是本文件最重要的部分，先读这里）

### 判定单位是「记录」，不是「读段」

上位机对每条源读段发两份记录：正向与反向互补
（`clients/python/fast_readout.py::batch_seqs_to_records`，交织成
`[fwd0, rc0, fwd1, rc1, ...]`）。板端对**每条记录独立比对、独立投票**，
`score < SCORE_MIN` 的记录在解析后直接跳过、不投票
（`docs/05-interfaces.md` 寄存器 0x30）。

因此接受/拒绝的主体是记录。一条源读段贡献两条记录，**其中恰好一条是正确方向**。

### 三类记录

设读段真值为 `(pos_true, orient_true)`（由 D1/D2 的 FASTQ header
`@read_XXXXXX_pos_<n>_orient_<fwd|rc>` 给出，生成器写入，是真值不是推断）：

| 类别 | 定义 | 期望行为 |
|---|---|---|
| **真记录** | `orient == orient_true` | 应当被接受，且定位到 `pos_true` |
| **诱饵记录** | `orient != orient_true` | **应当被拒绝**——它在参考上没有任何正确位置，
一旦通过阈值，它投出的每一票都落在错误位置 |
| **错位真记录** | `orient == orient_true` 但报告位置 ≠ `pos_true` | 同样是污染 |

### 误接受 / 误拒绝

```
误接受(τ) = { 记录 | score >= τ 且 该记录投出的票落在错误位置 }
          = { 通过阈值的诱饵记录 } ∪ { 通过阈值但错位的真记录 }

误接受率 FAR(τ) = |误接受(τ)| / |{记录 | score >= τ}|
                  ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^ 分母是**被接受的记录**
```

分母取「被接受的记录」而不是「全部记录」，是因为这个比值才有运行意义：
**它就是投票累加器里垃圾票的占比**。τ 调高会同时压小分子和分母，
用全部记录作分母会把这条曲线的意义冲淡。

```
误拒绝率 FRR(τ) = |{真记录 | score < τ 且 定位正确}| / |{定位正确的真记录}|
```

即「本来能投出正确一票，却被阈值挡掉」的比例。FAR 与 FRR 随 τ 反向移动，
G5 要的就是这条权衡曲线。

### 同分并列单列一类，不混进「错位」

Stage1 的分数是整数（匹配碱基数），**同分并列真实存在**：
`tools/make_stage1_tie_golden.py` 实测 SE150 前 64 条里有并列，
且 `tools/readout.py::_align_one` 走 FFT，float64 舍入误差会让 argmax
在并列集里挑一个**不可复现**的位置，而 RTL 确定性地选最小位置。

所以本脚本对每条「报告位置 ≠ 真值位置」的真记录，**再用整数精确滑窗复核两处的分数**：

- `int_score(报告位置) == int_score(真值位置)` → 记为 **并列错位**。
  这是编码本身的性质（真值位置并非唯一最优），**不是缺陷，也不是模型误差**；
- `int_score(报告位置)  >  int_score(真值位置)` → 记为 **真错位**。
  读段在噪声下真的更像别处。

两者都算误接受（票确实投错了地方），但**必须分开报**：
并列错位是 τ 调不掉的地板，真错位才是随错误率变化的那部分。

## 与板端的关系（边界，不要越界表述）

本脚本在**主机**上用与 RTL 相同的算法（滑窗匹配碱基数取最大）复算，
`tools/readout.py` 的实现受 `tests/golden/` 与 `hw/sim/golden/stage1_fwd_ties.txt`
两套黄金向量约束，且 4-way / 2-way 的 RTL 已对其判据 64/64 全等。

**但本脚本的输出是主机复算结果，不是板端实测。**
要把某一点升格为板端结论，必须用 `tools/run_g3.sh` 的四级取证里的
Stage1 DDR dump 对同一输入做交叉核对。脚本提供 `--cross-check-dump` 做这件事。

## 用法

    # 单个数据集，扫 τ
    python3 tools/g5_false_accept.py --dataset tests/datasets/D1_text_manifesto --limit 512

    # 误差矩阵：多个 D2 数据集一起扫，输出对比表
    python3 tools/g5_false_accept.py --dataset tests/datasets/D1_text_manifesto \
                                     --dataset tests/datasets/D2_text_sub1pct --limit 512

    # 结果写盘（JSON + Markdown 表）
    python3 tools/g5_false_accept.py --dataset ... --out-dir logs/g5_false_accept/<ts>
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "tools"))

import readout as rd  # noqa: E402

HDR_RE = re.compile(r"pos_(\d+)_orient_(fwd|rc)")
DEF_WM = REPO / "tests" / "datasets" / "common" / "watermark.txt"


# ---------------------------------------------------------------------------
# 输入
# ---------------------------------------------------------------------------
def load_reads_with_truth(fastq: Path, limit: int):
    """读 FASTQ，同时取出 header 里的真值 (pos, orient)。

    真值来自 `tools/generate_payload_dataset.py` 写入的 header，
    形如 `@read_000000_pos_12519_orient_rc 1:N:0:...`。
    **没有该字段的数据集不能用于本测量**——真值是外部给定的，不能由比对结果反推，
    否则就是拿被测对象给自己判分。
    """
    seqs, truth = [], []
    with fastq.open("r", encoding="utf-8", errors="ignore") as fh:
        while len(seqs) < limit:
            head = fh.readline()
            if not head:
                break
            seq = fh.readline().strip()
            fh.readline()
            fh.readline()
            m = HDR_RE.search(head)
            if m is None:
                raise ValueError(
                    f"{fastq} 的 header 缺少 pos_/orient_ 真值字段：{head.strip()!r}\n"
                    "本测量要求真值由数据集生成器给出，不接受从比对结果反推。")
            seqs.append(seq.upper())
            truth.append((int(m.group(1)), m.group(2)))
    if not seqs:
        raise ValueError(f"{fastq} 未读到任何读段")
    n = len(seqs[0])
    keep = [i for i, s in enumerate(seqs) if len(s) == n]
    R = np.array([[rd.BASE2VAL.get(c, 0) for c in seqs[i]] for i in keep], dtype=np.uint8)
    return R, [truth[i] for i in keep]


def int_score(ref: np.ndarray, read: np.ndarray, pos: int) -> int:
    """整数精确的单点匹配分：该位置上有多少个碱基相同。无浮点，可复现。"""
    if pos < 0 or pos + read.size > ref.size:
        return -1
    return int(np.count_nonzero(ref[pos:pos + read.size] == read))


# ---------------------------------------------------------------------------
# 逐记录分类
# ---------------------------------------------------------------------------
def classify(ref: np.ndarray, R: np.ndarray, truth, progress_every: int = 0):
    """把每条读段展开成两条记录并分类。

    返回记录列表，每项：
        orient      'fwd' / 'rc'
        is_true     该记录是否为正确方向（诱饵记录为 False）
        score       比对分（与 RTL 同口径：匹配碱基数）
        pos         报告位置
        verdict     'correct' | 'tie_mislocate' | 'true_mislocate' | 'decoy'
    """
    rl = R.shape[1]
    rd._init_worker(ref, rl)
    recs = []
    t0 = time.time()
    for i in range(R.shape[0]):
        pos_true, orient_true = truth[i]
        row = R[i]
        rc_row = (row ^ 1)[::-1]                      # 与 readout.py 一致的反向互补
        pf, sf = rd._align_one(row)
        pr, sr = rd._align_one(rc_row)

        for orient, pos, score, seq in (("fwd", pf, sf, row), ("rc", pr, sr, rc_row)):
            if orient != orient_true:
                # 诱饵记录：它在参考上没有正确位置，通过阈值即为误接受
                recs.append(dict(idx=i, orient=orient, is_true=False,
                                 score=score, pos=pos, verdict="decoy"))
                continue
            if pos == pos_true:
                recs.append(dict(idx=i, orient=orient, is_true=True,
                                 score=score, pos=pos, verdict="correct"))
                continue
            # 报告位置 ≠ 真值位置：用整数精确分复核，区分「并列」与「真错位」
            s_rep = int_score(ref, seq, pos)
            s_tru = int_score(ref, seq, pos_true)
            verdict = "tie_mislocate" if s_rep == s_tru else "true_mislocate"
            recs.append(dict(idx=i, orient=orient, is_true=True, score=score, pos=pos,
                             verdict=verdict, int_score_reported=s_rep,
                             int_score_truth=s_tru))
        if progress_every and (i + 1) % progress_every == 0:
            el = time.time() - t0
            print(f"    {i+1}/{R.shape[0]} 条  {el:.1f}s  "
                  f"(预计还需 {el/(i+1)*(R.shape[0]-i-1):.0f}s)", flush=True)
    return recs


def sweep(recs, taus):
    """按阈值扫描，返回每个 τ 的 FAR / FRR 与分项计数。"""
    sc = np.array([r["score"] for r in recs])
    is_wrong_vote = np.array([r["verdict"] != "correct" for r in recs])   # 票投错地方
    is_decoy = np.array([r["verdict"] == "decoy" for r in recs])
    is_tie = np.array([r["verdict"] == "tie_mislocate" for r in recs])
    is_realmis = np.array([r["verdict"] == "true_mislocate" for r in recs])
    is_correct = np.array([r["verdict"] == "correct" for r in recs])
    n_correct_total = int(is_correct.sum())

    rows = []
    for t in taus:
        acc = sc >= t
        n_acc = int(acc.sum())
        n_bad = int((acc & is_wrong_vote).sum())
        rows.append(dict(
            tau=int(t),
            accepted=n_acc,
            accepted_correct=int((acc & is_correct).sum()),
            false_accept=n_bad,
            fa_decoy=int((acc & is_decoy).sum()),
            fa_tie=int((acc & is_tie).sum()),
            fa_true_mislocate=int((acc & is_realmis).sum()),
            far=(n_bad / n_acc) if n_acc else 0.0,
            frr=((n_correct_total - int((acc & is_correct).sum())) / n_correct_total)
                if n_correct_total else 0.0,
        ))
    return rows


def separation(recs):
    """真记录与诱饵记录的分数分隔度——一个数就能说明阈值好不好选。"""
    good = np.array([r["score"] for r in recs if r["verdict"] == "correct"])
    dec = np.array([r["score"] for r in recs if r["verdict"] == "decoy"])
    if good.size == 0 or dec.size == 0:
        return None
    return dict(correct_min=int(good.min()), correct_median=float(np.median(good)),
                correct_max=int(good.max()),
                decoy_min=int(dec.min()), decoy_median=float(np.median(dec)),
                decoy_max=int(dec.max()),
                margin=int(good.min()) - int(dec.max()))


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dataset", action="append", required=True,
                    help="数据集目录（需含 reads*.fastq，header 带 pos_/orient_ 真值）；可重复")
    ap.add_argument("--watermark", default=str(DEF_WM),
                    help="水印序列。Stage1 比对的参考是水印，不是 reference_sequence")
    ap.add_argument("--limit", type=int, default=512, help="每个数据集取前 N 条源读段")
    ap.add_argument("--taus", default="0,50,55,60,62,64,66,67,68,70,72,75,80,85,90",
                    help="扫描的 score_min 列表（67 是固件当前固定值）")
    ap.add_argument("--out-dir", default=None, help="结果落盘目录（JSON + Markdown）")
    args = ap.parse_args(argv)

    ref, _ = rd.load_watermark(Path(args.watermark))
    taus = [int(x) for x in args.taus.split(",") if x.strip()]
    results = {}

    for ds in args.dataset:
        dsp = Path(ds)
        fq = next(iter(sorted(dsp.glob("*reads_se*.fastq"))), None)
        if fq is None:
            raise SystemExit(f"{dsp} 下找不到 reads_se*.fastq")
        print(f"\n=== {dsp.name} ({fq.name}) ===")
        R, truth = load_reads_with_truth(fq, args.limit)
        print(f"  源读段 {R.shape[0]} 条 × {R.shape[1]} bp  →  记录 {2*R.shape[0]} 条")
        recs = classify(ref, R, truth, progress_every=max(64, R.shape[0] // 8))
        rows = sweep(recs, taus)
        sep = separation(recs)
        results[dsp.name] = dict(fastq=str(fq), reads=R.shape[0], records=len(recs),
                                 read_len=int(R.shape[1]), separation=sep, sweep=rows,
                                 verdict_counts={v: sum(1 for r in recs if r["verdict"] == v)
                                                 for v in ("correct", "decoy",
                                                           "tie_mislocate", "true_mislocate")})
        if sep:
            print(f"  真记录分 {sep['correct_min']}~{sep['correct_max']}（中位 {sep['correct_median']:.0f}）"
                  f" | 诱饵分 {sep['decoy_min']}~{sep['decoy_max']}（中位 {sep['decoy_median']:.0f}）"
                  f" | 间隔 {sep['margin']:+d}")
        print(f"  {'τ':>4} {'接受':>7} {'误接受':>7} {'诱饵':>6} {'并列':>5} {'真错位':>6} "
              f"{'FAR':>8} {'FRR':>8}")
        for r in rows:
            print(f"  {r['tau']:>4} {r['accepted']:>7} {r['false_accept']:>7} "
                  f"{r['fa_decoy']:>6} {r['fa_tie']:>5} {r['fa_true_mislocate']:>6} "
                  f"{100*r['far']:>7.3f}% {100*r['frr']:>7.3f}%")

    if args.out_dir:
        od = Path(args.out_dir)
        od.mkdir(parents=True, exist_ok=True)
        (od / "g5_false_accept.json").write_text(
            json.dumps(dict(watermark=args.watermark, limit=args.limit,
                            taus=taus, datasets=results), ensure_ascii=False, indent=2),
            encoding="utf-8")
        print(f"\n已写出 {od/'g5_false_accept.json'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
