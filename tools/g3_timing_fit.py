#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把 tools/run_g3.sh 各轮留证里的 result 耗时拟合成「固定开销 + 每条成本」。

为什么需要它
------------
`first.py` 的 `stats.t_result` 是「发完 POST 到收完结果」的**全部板端时间**，
而板端在这段时间里一个字节都不发，所以它同时也是上位机超时值的下界。
换规模时要回答的问题是：这个数里多少是与条数无关的固定开销、多少随条数线性涨。
分档跑几轮再最小二乘拟合，是直接给出答案的最省事办法——
比在 UART 日志里靠扣除法推断可靠得多（扣除法推断出来的东西容易被当成实测引用）。

用法
----
    python3 tools/g3_timing_fit.py /mnt/d/dna_board_smoke/g3_runs/*/

判据纪律
--------
本工具只做**性能**的量化，与 G3 的功能判据无关。
G3 是否通过永远只看图片 SHA-256（见 AGENTS.md「事实边界」）。
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

RE_RECORDS = re.compile(r"^源读段/记录\s*:\s*\d+\s*/\s*(\d+)", re.M)
RE_RESULT = re.compile(r"Result:\s*\d+\s*bytes,\s*([0-9.]+)s")


def collect(run_dir: Path) -> tuple[int, float] | None:
    summary = run_dir / "summary.txt"
    if not summary.is_file():
        return None
    m = RE_RECORDS.search(summary.read_text(encoding="utf-8", errors="replace"))
    if not m:
        return None
    records = int(m.group(1))

    # 只取第一轮：二次任务那轮要单独看，混进拟合会把状态复位的开销算成规模效应。
    log = run_dir / "first_run1.log"
    if not log.is_file():
        return None
    r = RE_RESULT.search(log.read_text(encoding="utf-8", errors="replace"))
    if not r:
        return None
    return records, float(r.group(1))


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print(__doc__)
        return 2

    points: list[tuple[int, float]] = []
    for d in sorted(argv[1:]):
        got = collect(Path(d))
        if got:
            points.append(got)

    # 同一档跑过多轮时取最早的一条，避免同一 x 重复加权。
    dedup: dict[int, float] = {}
    for rec, t in points:
        dedup.setdefault(rec, t)
    points = sorted(dedup.items())

    if len(points) < 2:
        print(f"至少需要两个不同规模的数据点，当前只有 {len(points)} 个", file=sys.stderr)
        for rec, t in points:
            print(f"  {rec:>7,} 条 → {t:.2f} s", file=sys.stderr)
        return 1

    print(f"{'记录数':>10}  {'result 耗时':>12}  {'每条':>10}")
    for rec, t in points:
        print(f"{rec:>10,}  {t:>10.2f} s  {t / rec * 1000:>8.3f} ms")

    n = len(points)
    sx = sum(r for r, _ in points)
    sy = sum(t for _, t in points)
    sxx = sum(r * r for r, _ in points)
    sxy = sum(r * t for r, t in points)
    denom = n * sxx - sx * sx
    slope = (n * sxy - sx * sy) / denom
    intercept = (sy - slope * sx) / n

    # 判定系数：线性拟合到底有多贴。若明显小于 1，说明不是线性，别拿它外推。
    mean = sy / n
    ss_tot = sum((t - mean) ** 2 for _, t in points)
    ss_res = sum((t - (intercept + slope * r)) ** 2 for r, t in points)
    r2 = 1.0 - ss_res / ss_tot if ss_tot > 0 else float("nan")

    print()
    print(f"最小二乘拟合： t = {intercept:.2f} s + {slope * 1000:.4f} ms/条 × 条数")
    print(f"  固定开销（截距）: {intercept:.2f} s")
    print(f"  每条成本（斜率）: {slope * 1000:.4f} ms")
    print(f"  R^2             : {r2:.5f}")

    print()
    print("外推（仅当 R^2 接近 1 时才可引用）：")
    for rec in (32_768, 51_781 * 2, 103_552):
        print(f"  {rec:>7,} 条 → {intercept + slope * rec:>7.1f} s")

    full = intercept + slope * 103_552
    print()
    print(f"全量 103,552 条预测 {full:.1f} s，对 first.py 默认 180 s 超时而言："
          f"{'会撞穿' if full > 180 else '不会撞穿'}")
    print("注意：预测不是实测。真正的判据是拿全量实跑一轮，看图片 SHA-256。")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
