#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""实测 Voter 投票累加器的运行中极值，回答「10 bit 够不够」。

`differential_voter_v1_0.v:319-326` 的 `safe_vote_value` 是一个**逐票饱和**的
10 bit 有符号累加器：每收一票就 `clip(x±1, -512, 511)`。docs/20 §3.2 据一个
**估算**的位级同意率 0.72 推出「全量 SE250 运行中上界 ≈ 282 < 511，不用加宽」，
并把它标成**未验证**。本脚本把那个数直接量出来。

顺带回答第二个问题：`tools/make_golden.py` 生成 `stage2_rtl_expect.hex` 时用的是
**最后一次性** `np.clip(votes, -512, 511)`，注释却写「每次 ±1 后钳位」。两者只在
**从不饱和**时才等价（自由累加到 +600 再回落 200 = 400；逐票饱和则是 511 再回落
200 = 311，符号判决都可能因此不同）。所以「会不会饱和」同时决定了黄金向量在该
规模下还算不算数。

用法：
    python3 tools/vote_range.py --reads <fastq> [--limit N] [--jobs J]
    python3 tools/vote_range.py --selftest      # 自证：能不能测出饱和

判据纪律：先跑 --selftest。如果探测器根本报不出饱和，那么「没饱和」这个结论
没有信息量——它可能只是说明工具瞎了。
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import readout as rd  # noqa: E402

REPO = Path(__file__).resolve().parent.parent
DATA = REPO / "data" / "R0.83_data"
DEF_WM = DATA / "Source data" / "Watermark sequences" / "r0.83_watermark.txt"

VOTE_MAX, VOTE_MIN = 511, -512      # safe_vote_value 的钳位边界


class Accum:
    """一路投票累加器：同时维护「逐票饱和」与「自由累加」两种语义。"""

    def __init__(self, size: int, name: str):
        self.name = name
        self.sat = np.zeros(size, dtype=np.int32)    # 逐票饱和（= RTL）
        self.free = np.zeros(size, dtype=np.int32)   # 自由累加（= make_golden 现状）
        self.records = 0
        self.sat_hits = 0                            # 真正被钳位截住的票数
        self.hi = self.lo = 0                        # 饱和累加器的**运行中**极值
        self.free_hi = self.free_lo = 0              # 自由累加器的运行中极值

    def apply(self, idx: np.ndarray, delta: np.ndarray) -> None:
        """一条记录内各 bit 位置互不重复，所以向量化 == 逐票。

        极值必须在这里取。原先在每条源读段之后对全数组取一次 max 是**末值**
        不是运行中峰值——峰值涨上去又落回来就漏掉了（自证第一版就是这么红的）。
        这里取的是每次更新后那批位置的极值，与逐票语义严格等价，且只扫 |idx|。
        """
        new_free = self.free[idx] + delta
        self.free[idx] = new_free
        self.free_hi = max(self.free_hi, int(new_free.max()))
        self.free_lo = min(self.free_lo, int(new_free.min()))

        raw = self.sat[idx] + delta
        clipped = np.clip(raw, VOTE_MIN, VOTE_MAX)
        self.sat_hits += int((raw != clipped).sum())
        self.sat[idx] = clipped
        self.hi = max(self.hi, int(clipped.max()))
        self.lo = min(self.lo, int(clipped.min()))

    def report(self) -> dict:
        free_clipped = np.clip(self.free, VOTE_MIN, VOTE_MAX)
        disagree = int(((self.sat > 0) != (free_clipped > 0)).sum())
        return {
            "name": self.name,
            "records": self.records,
            "running_max": self.hi,
            "running_min": self.lo,
            "peak_abs": max(self.hi, -self.lo),
            "headroom_to_511": VOTE_MAX - max(self.hi, -self.lo),
            "saturation_events": self.sat_hits,
            "free_peak_max": self.free_hi,
            "free_peak_min": self.free_lo,
            "free_final_max": int(self.free.max()),
            "consensus_bits_differing": disagree,
        }


def replay(both, R, L, rb, thr, log=None, checkpoint=0):
    """按板端到达顺序回放投票：每条源读段先正向、后反向互补（first.py orient=both）。"""
    filt = Accum(2 * L, f"SCORE_MIN={thr}（板端默认）")
    allr = Accum(2 * L, "SCORE_MIN=0（不过滤，票最多）")

    for i, (pf, sf, pr, sr) in enumerate(both):
        for p, s, a in ((pf, sf, R[i]), (pr, sr, (R[i] ^ 1)[::-1])):
            idx = np.arange(p, p + rb)
            d_hi = ((a >> 1) & 1).astype(np.int32) * 2 - 1
            d_lo = (a & 1).astype(np.int32) * 2 - 1
            allr.apply(idx, d_hi)
            allr.apply(idx + L, d_lo)
            allr.records += 1
            if s >= thr:
                filt.apply(idx, d_hi)
                filt.apply(idx + L, d_lo)
                filt.records += 1
        if checkpoint and log and (i + 1) % checkpoint == 0:
            # 长跑随时可能被限额打断：每个检查点就落盘一行，前面的不白跑。
            with open(log, "a", encoding="utf-8") as fh:
                fh.write(json.dumps({"reads_done": i + 1,
                                     "filtered": filt.report(),
                                     "all": allr.report()},
                                    ensure_ascii=False) + "\n")
    return filt, allr


def cmd_selftest() -> int:
    """自证：人为造一个必然饱和的场景，探测器必须报出来，且两种语义必须分家。

    不做这一步的话，「没饱和」和「工具坏了」长得一模一样。
    """
    print("[selftest] 造一个 600 票同向 + 200 票反向的位，逐票饱和必然与自由累加分家")
    acc = Accum(1, "selftest")
    one = np.array([0])
    for _ in range(600):
        acc.apply(one, np.array([1], dtype=np.int32))
    for _ in range(200):
        acc.apply(one, np.array([-1], dtype=np.int32))
    rep = acc.report()
    ok = True
    # 自由累加 600-200 = 400；逐票饱和 511 之后回落 200 = 311。
    if rep["free_peak_max"] != 600:
        print(f"  ✗ 自由累加运行中峰值应为 600，实得 {rep['free_peak_max']}"); ok = False
    if rep["free_final_max"] != 400:
        print(f"  ✗ 自由累加终值应为 400，实得 {rep['free_final_max']}"); ok = False
    if acc.sat[0] != 311:
        print(f"  ✗ 逐票饱和终值应为 311，实得 {int(acc.sat[0])}"); ok = False
    if rep["saturation_events"] != 89:      # 第 512..600 票被截住
        print(f"  ✗ 饱和次数应为 89，实得 {rep['saturation_events']}"); ok = False
    if rep["running_max"] != 511:
        print(f"  ✗ 运行中最大值应被钳在 511，实得 {rep['running_max']}"); ok = False
    print("  ✓ 探测器能测出饱和，且两种语义确实不同" if ok else "  ✗ 自证失败")

    print("[selftest] 反向对照：票数远低于钳位时，两种语义必须完全一致")
    acc2 = Accum(1, "selftest-low")
    for _ in range(30):
        acc2.apply(one, np.array([1], dtype=np.int32))
    r2 = acc2.report()
    if r2["saturation_events"] or r2["consensus_bits_differing"]:
        print("  ✗ 低票数下不该有饱和，也不该分家"); ok = False
    else:
        print("  ✓ 低票数下两种语义等价（这正是 make_golden 现状能成立的前提）")
    return 0 if ok else 1


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--reads")
    ap.add_argument("--watermark", default=str(DEF_WM))
    ap.add_argument("--limit", type=int, default=10 ** 9)
    ap.add_argument("--min-score", type=float, default=0.45)
    ap.add_argument("--jobs", type=int, default=6)
    ap.add_argument("--checkpoint", type=int, default=2048,
                    help="每处理多少条源读段往 --log 追加一行中间结果（0 = 不写）")
    ap.add_argument("--log", help="中间结果落盘路径（长跑被打断时不白跑）")
    ap.add_argument("--json", help="最终结果写成 JSON")
    ap.add_argument("--verify-golden", metavar="DIR",
                    help="用该黄金向量目录交叉核对：本脚本回放出的共识必须与 "
                         "stage2_expect.hex（过阈）和 stage2_rtl_expect.hex（不过阈）"
                         "逐位相同。不先过这一条，后面量出来的极值只是另一份"
                         "未经验证的实现说了算")
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args(argv)

    if args.selftest:
        return cmd_selftest()
    if not args.reads:
        ap.error("需要 --reads（或用 --selftest）")

    ref, _ = rd.load_watermark(Path(args.watermark))
    L = ref.size
    R = rd.load_reads(Path(args.reads), args.limit)
    n, rb = R.shape
    thr = int(args.min_score * rb)
    cov = n * rb / L
    print(f"参考 {L} nt   读段 {n} 条 × {rb} bp   阈值 {thr}   "
          f"单向覆盖度 {cov:.1f}×/位")

    if args.jobs > 1:
        import multiprocessing as mp
        with mp.Pool(args.jobs, initializer=rd._init_worker, initargs=(ref, rb)) as pool:
            both = pool.map(rd._align_both, list(R), chunksize=8)
    else:
        rd._init_worker(ref, rb)
        both = [rd._align_both(R[i]) for i in range(n)]
    print(f"比对完成，开始按板端到达顺序回放 {2*n} 条记录")

    filt, allr = replay(both, R, L, rb, thr, log=args.log, checkpoint=args.checkpoint)

    out = {"reads": n, "read_bps": rb, "L": L, "score_min": thr,
           "coverage_per_bit": round(cov, 2),
           "vote_clip": [VOTE_MIN, VOTE_MAX],
           "results": [filt.report(), allr.report()]}
    print()
    for rep in out["results"]:
        print(f"--- {rep['name']} ---")
        print(f"  参与投票记录        {rep['records']}")
        print(f"  运行中极值          {rep['running_min']} .. {rep['running_max']}"
              f"（绝对值峰 {rep['peak_abs']}）")
        print(f"  距 ±511/512 的余量  {rep['headroom_to_511']}")
        print(f"  实际被钳住的票数    {rep['saturation_events']}")
        print(f"  自由累加运行中极值  {rep['free_peak_min']} .. {rep['free_peak_max']}"
              f"（终值 max {rep['free_final_max']}）")
        print(f"  两种语义的共识差异  {rep['consensus_bits_differing']} bit / {2*L}")
    if args.verify_golden:
        gd = Path(args.verify_golden)
        ok = True
        for acc, fname in ((filt, "stage2_expect.hex"), (allr, "stage2_rtl_expect.hex")):
            words = [int(x, 16) for x in (gd / fname).read_text().split()]
            want = np.zeros(len(words) * 64, dtype=np.uint8)
            for w, v in enumerate(words):
                for b in range(64):
                    want[w * 64 + b] = (v >> b) & 1
            got = (acc.sat > 0).astype(np.uint8)
            diff = int((got != want[:got.size]).sum())
            print(f"  交叉核对 {fname:24s} 差异 {diff} bit / {got.size}"
                  f"  {'✅' if diff == 0 else '❌'}")
            ok = ok and diff == 0
        out["verify_golden"] = {"dir": str(gd), "match": ok}
        if not ok:
            print("❌ 回放语义与黄金向量不一致，本次极值不可采信")
            return 1

    if args.json:
        Path(args.json).write_text(json.dumps(out, ensure_ascii=False, indent=2),
                                   encoding="utf-8")
        print(f"\n已写出 {args.json}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
