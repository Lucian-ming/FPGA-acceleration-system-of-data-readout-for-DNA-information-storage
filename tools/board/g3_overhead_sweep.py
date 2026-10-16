#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""tools/board/g3_overhead_sweep.py —— 板端固定开销尺寸扫描与模型重拟合

## 为什么需要它

`docs/benchmarks/measured_cpu_vs_fpga.md` §3.3 的板端模型

    T_board = 4.25 s + 0.58 ms x N_records

其常数项在 2,048 源读段任务里占 **63%** 的时间，却是用
**只有 3 个大规模点**（4,096 / 8,192 / 16,384 条记录）外推出来的。
用三个大点去外推 x=0 处的截距，杠杆臂极长：这三点本身的抖动
（实测 min/max 相差 0.4~3.0 s）会被放大成常数项的巨大不确定度。
换句话说，**4.25 s 这个数字的误差棒从来没有被给出过**。

而 `docs/08-performance-and-strategy.md` §3 已经证明该常数项的既有解释
（TCP 握手 + DMA 启动 + Voter 初始化）在数量级上不成立：
可解释部分约 14 万周期，而 4.25 s @100MHz = 4.25 亿周期，差约 3,000 倍。

本工具做**零固件改动**的第一步：在小规模端（64~4,096 条源读段）密集采样，
把截距真正测出来而不是外推出来，并给出置信区间。

## 判据边界

- 本工具**只测时间，不判正确性**。小规模（如 64 条读段）覆盖度不足，
  LDPC 必然不收敛，这是预期行为，**不得据此报告任何正确性结论**。
  正确性判据仍然只有 `tools/run_g3.sh` 的图片 SHA-256。
- 本工具**必须** `post=True`。`--no-post` 的语义是「不发送 POST 触发命令」，
  板子根本不会开始计算，`t_result` 恒为 0（2026-09-10 实测踩过这个坑，
  第一轮扫描全部作废）。而 `run_client` 本身**不做 LDPC 译码**
  （那是独立的 `tools/ldpc_decode.py`），所以 `post=True` 拿到的正是
  「板端计算 + 回传」，天然不含主机译码耗时。
- 每个规模重复多次取中位数；单次结果不进模型。

## 用法

    tools/board/g3_overhead_sweep.py                    # 默认扫描，板子须已在运行
    tools/board/g3_overhead_sweep.py --repeat 5
    tools/board/g3_overhead_sweep.py --limits 64,128,256,512,1024,2048,4096

**前提**：板子已烧录并在跑（先用 `tools/run_g3.sh` 或 `--skip-boot`），
且**没有其他进程在占用板卡**——板端 lwIP 是单例 `g_conn`，
并发连接会破坏正在进行的任务。
"""

from __future__ import annotations

import argparse
import json
import math
import statistics
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent.parent
CLIENTS_PY = REPO / "clients" / "python"
if str(CLIENTS_PY) not in sys.path:
    sys.path.insert(0, str(CLIENTS_PY))

from first import ClientConfig, run_client  # noqa: E402
from g3_caps import CAPS_ARCHITECTURE_BOUNDARY, query_board_caps  # noqa: E402

DEF_READS = REPO / "data/R0.83_data/Sequencing data/DNA-40.5Kb-MC-SE150.fastq"
DEF_WM = REPO / "data/R0.83_data/Source data/Watermark sequences/r0.83_watermark.txt"


def one_run(ip: str, port: int, limit: int, out_path: Path, timeout: float):
    """跑一次任务，返回各阶段耗时。不做 LDPC 译码。"""
    cfg = ClientConfig(
        ip=ip, port=port,
        watermark=DEF_WM, reads=DEF_READS,
        out=out_path,
        send_limit=limit, read_bps=150, score_min=67,
        orient="both", post=True, result_timeout=timeout,
    )
    t0 = time.perf_counter()
    stats = run_client(cfg)
    wall = time.perf_counter() - t0
    return {
        "limit_source_reads": limit,
        "records": limit * 2,
        "t_wm": getattr(stats, "t_wm", None),
        "t_batches": getattr(stats, "t_batches", None),
        "t_result": getattr(stats, "t_result", None),
        "t_total": getattr(stats, "t_total", None),
        "wall": wall,
    }


def fit_line(xs, ys):
    """最小二乘拟合 y = a + b*x，返回 (a, b, r2)。"""
    n = len(xs)
    mx, my = sum(xs) / n, sum(ys) / n
    sxx = sum((x - mx) ** 2 for x in xs)
    sxy = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    b = sxy / sxx
    a = my - b * mx
    ss_tot = sum((y - my) ** 2 for y in ys)
    ss_res = sum((y - (a + b * x)) ** 2 for x, y in zip(xs, ys))
    r2 = 1.0 - ss_res / ss_tot if ss_tot > 0 else float("nan")
    return a, b, r2


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--ip", required=True, help="必须显式指定本轮实测板端 IP")
    ap.add_argument("--port", type=int, default=7)
    ap.add_argument("--limits", default="64,128,256,512,1024,2048,4096",
                    help="源读段数序列（逗号分隔）")
    ap.add_argument("--repeat", type=int, default=3, help="每档重复次数，取中位数")
    ap.add_argument("--timeout", type=float, default=300.0)
    ap.add_argument("--out-dir", default=None)
    args = ap.parse_args(argv)

    limits = [int(x) for x in args.limits.split(",") if x.strip()]
    if args.repeat < 1:
        ap.error("--repeat 必须至少为 1")
    if args.timeout <= 0:
        ap.error("--timeout 必须大于 0")
    if len(limits) < 2 or any(limit <= 0 for limit in limits) or len(set(limits)) != len(limits):
        ap.error("--limits 必须包含至少两个互不重复的正整数档位")

    caps = query_board_caps(args.ip, args.port)

    run_id = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
    out_dir = Path(args.out_dir) if args.out_dir else REPO / "logs" / "overhead_sweep" / run_id
    out_dir.mkdir(parents=True, exist_ok=True)

    print(f"=== 板端固定开销尺寸扫描 run={run_id} ===")
    print(f"    目标 {args.ip}:{args.port}   档位 {limits}   每档 {args.repeat} 次")
    print(f"    CAPS 全字段匹配：{caps}; {CAPS_ARCHITECTURE_BOUNDARY}")
    print(f"    留证 {out_dir}")
    print("    注意：本工具只测时间，不判正确性；小规模覆盖度不足，LDPC 必然不收敛。\n")

    rows = []
    all_tiers_complete = True
    for lim in limits:
        samples = []
        failures = []
        for k in range(args.repeat):
            try:
                r = one_run(args.ip, args.port, lim,
                            out_dir / f"dec_{lim}_{k}.txt", args.timeout)
                for field in ("t_wm", "t_batches", "t_result", "t_total", "wall"):
                    value = r[field]
                    if value is None or not math.isfinite(float(value)):
                        raise ValueError(f"{field} 不是有限数值: {value!r}")
            except Exception as e:
                message = f"第 {k+1} 次失败: {e}"
                failures.append(message)
                print(f"  [{lim:>5} 条] {message}")
                continue
            samples.append(r)
            print(f"  [{lim:>5} 条 / {lim*2:>5} 记录] 第 {k+1} 次: "
                  f"水印 {r['t_wm']:.3f}s  读段 {r['t_batches']:.3f}s  "
                  f"结果 {r['t_result']:.3f}s  总 {r['t_total']:.3f}s")
            time.sleep(1.0)   # 让板端连接彻底回收，避免单例 g_conn 抢占
        if len(samples) != args.repeat:
            all_tiers_complete = False
            row = {
                "limit_source_reads": lim,
                "records": lim * 2,
                "status": "INCOMPLETE",
                "expected_n": args.repeat,
                "n": len(samples),
                "failures": failures,
            }
            rows.append(row)
            print(f"  -> 样本不足：要求 {args.repeat} 次，只有 {len(samples)} 次；此档不入模型\n")
            continue
        med = {k: statistics.median([s[k] for s in samples])
               for k in ("t_wm", "t_batches", "t_result", "t_total", "wall")}
        med["limit_source_reads"] = lim
        med["records"] = lim * 2
        med["status"] = "COMPLETE"
        med["expected_n"] = args.repeat
        med["n"] = len(samples)
        med["t_result_all"] = [s["t_result"] for s in samples]
        rows.append(med)
        print(f"  -> 中位数 结果阶段 {med['t_result']:.3f}s  总 {med['t_total']:.3f}s\n")

    (out_dir / "sweep.json").write_text(
        json.dumps(rows, indent=2, ensure_ascii=False), encoding="utf-8")

    if all_tiers_complete and len(rows) >= 2:
        xs = [r["records"] for r in rows]
        ys = [r["t_result"] for r in rows]
        a, b, r2 = fit_line(xs, ys)
        print("=" * 64)
        print("按「结果阶段」(t_result = 板端计算 + 回传) 重新拟合：")
        print(f"    T = {a:.3f} s + {b*1000:.4f} ms x N_records      R^2 = {r2:.5f}")
        print(f"    既有文档模型：T = 4.25 s + 0.58 ms x N_records")
        print(f"    截距差异: {a - 4.25:+.3f} s")
        print("=" * 64)
        # 只用大点重拟合，复现文档模型的杠杆问题
        big = [r for r in rows if r["records"] >= 4096]
        if len(big) >= 2:
            a2, b2, _ = fit_line([r["records"] for r in big], [r["t_result"] for r in big])
            print(f"仅用 N>=4096 的点拟合（模拟原文档做法）："
                  f"T = {a2:.3f} s + {b2*1000:.4f} ms x N")
            print(f"    与全档拟合的截距差 {a2 - a:+.3f} s "
                  f"—— 差得越多，说明原模型的常数项越不可信")
        (out_dir / "fit.txt").write_text(
            f"all_points  a={a:.6f} b_ms={b*1000:.6f} r2={r2:.6f}\n", encoding="utf-8")
    else:
        (out_dir / "fit.txt").write_text(
            f"no_model status=INCOMPLETE expected_samples_per_tier={args.repeat}\n",
            encoding="utf-8",
        )

    print(f"\n结果已保存: {out_dir}/sweep.json")
    if not all_tiers_complete:
        print("[FAIL] 至少一档未达到 --repeat 样本数；未拟合模型。")
        return 1
    print("[PASS] 所有档位均取得完整样本。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
