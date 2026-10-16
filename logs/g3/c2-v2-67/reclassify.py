#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""logs/g3/c2-v2-67/reclassify.py —— 从逐例 .out 重判 v2@67 的失败性质。

## 为什么不能直接用 run_all_67.sh 的 SUMMARY.tsv

那支脚本的 `failmode` 判据是**字符串匹配**（找"不收敛"字样），而 `run_g3.sh` 的输出里
这一情形写的是「主机译码退出码=1」，匹配不上 ⇒ 全部落进 `OTHER_SEE_LOG`，
**分类器失效但脚本照跑**。而脚本正在跑时**不能改**（改运行中的 bash 脚本会破坏执行）。

⇒ 权威结论由本脚本从 `.out` 原文离线重判；`run_g3.sh` 的完整输出就是证据，
不依赖那支脚本的分类。

## 判什么

本项的核心不是"通过率"，而是**失败是不是安全的**：

| 分类 | 判据 | 含义 |
| --- | --- | --- |
| `PASS` | 架构 PASS 且 系统 PASS | 端到端正确 |
| `SAFE_NOCONV` | **架构 FAIL**（syndrome 非零）且 **无载荷** | 板端明确"纠不动"，**不吐任何字节** ⇒ 安全失败 |
| `DANGER_WRONG_PAYLOAD` | **架构 PASS 但系统 FAIL** | 译出了**合法码字但载荷不是期望的那一份** ⇒ **静默错误输出，必须为 0** |
| `OTHER` | 其余 | 需要人看 |

⚠️ `SAFE_NOCONV` 与 `与 65 档的差异` 合起来看才有意义：65 档有 34 PASS / 8 FAIL。
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

OUT = Path(__file__).resolve().parent
DANGER_MARK = "板端码字合法但载荷不是期望的那一份"


def classify(text: str) -> dict:
    arch = sysv = ""
    m = re.findall(r"架构判据\s*:\s*(PASS|FAIL)", text)
    if m:
        arch = m[-1]
    m = re.findall(r"系统判据\s*:\s*(PASS|FAIL)", text)
    if m:
        sysv = m[-1]
    # 板端回传的载荷 SHA（系统判据行里的第一个 64 hex）
    m = re.findall(r"系统判据\s*:\s*PASS\s*—\s*SHA-256\s*([0-9a-f]{64})", text)
    judge = m[-1] if m else ""
    m = re.findall(r"期望\s*([0-9a-f]{64})", text)
    expect = m[-1] if m else ""
    no_payload = "SHA-256 无载荷" in text
    danger_mark = DANGER_MARK in text
    syn = ""
    m = re.findall(r"syndrome 非零行\s*(\d+)/(\d+)", text)
    if m:
        syn = f"{m[-1][0]}/{m[-1][1]}"
    m = re.findall(r"syndrome 全零\s*(\d+)/(\d+)", text)
    if m:
        syn = f"0/{m[-1][1]}"
    host_rc = ""
    m = re.findall(r"主机译码退出码=(\d+)", text)
    if m:
        host_rc = m[-1]

    if arch == "PASS" and sysv == "PASS":
        kind = "PASS"
    elif danger_mark or (arch == "PASS" and sysv == "FAIL"):
        kind = "DANGER_WRONG_PAYLOAD"
    elif arch == "FAIL" and no_payload:
        kind = "SAFE_NOCONV"
    else:
        kind = "OTHER"
    return dict(arch=arch, sys=sysv, kind=kind, judge=judge, expect=expect,
                match="YES" if (judge and judge == expect) else "NO",
                syn=syn, host_rc=host_rc, no_payload=no_payload)


def main() -> int:
    outs = sorted(OUT.glob("*.out"))
    if not outs:
        print("没有 .out，先跑 run_all_67.sh", file=sys.stderr)
        return 2
    rows = []
    for p in outs:
        t = p.read_text(errors="replace")
        r = classify(t)
        r["case"] = p.stem
        rows.append(r)

    tsv = OUT / "SUMMARY-classified.tsv"
    with tsv.open("w") as fh:
        fh.write("case\tarch\tsystem\tclass\tmatch\tsyndrome\thost_rc\tjudge_sha16\n")
        for r in rows:
            fh.write("\t".join([r["case"], r["arch"], r["sys"], r["kind"], r["match"],
                                r["syn"], r["host_rc"], r["judge"][:16]]) + "\n")

    from collections import Counter
    c = Counter(r["kind"] for r in rows)
    print(f"例数 {len(rows)}")
    for k in ("PASS", "SAFE_NOCONV", "DANGER_WRONG_PAYLOAD", "OTHER"):
        if c[k]:
            print(f"  {k:22s} {c[k]}")
    print()
    print(f"⚠️ DANGER_WRONG_PAYLOAD = {c['DANGER_WRONG_PAYLOAD']}"
          f"  ← **必须为 0**；不为 0 说明板端静默给出了错误字节，是真缺陷")
    if c["OTHER"]:
        print("\nOTHER 明细（需要人看）：")
        for r in rows:
            if r["kind"] == "OTHER":
                print(f"  {r['case']}  arch={r['arch']} sys={r['sys']} "
                      f"no_payload={r['no_payload']} syn={r['syn']} host_rc={r['host_rc']}")
    print(f"\n→ {tsv}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
