#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""为一份制品包写/刷新 reports/source_manifest.json，并让 SHA256SUMS 重新自洽。

为什么要有它
------------
`tools/board/g3_artifacts.py` 要求制品包里的 `manifest.json` 指向一份
**source_manifest**，其 `files` 必须是「源码相对路径 -> SHA256」的非空字典。
这份清单是「制品包 ↔ 源码」因果链唯一的机器可读凭据——没有它，包里那
bit/ELF 到底出自哪份源码就只剩人嘴说。

以前变体包（`tools/build_sw_variant.sh`）是**直接把参考包的 source_manifest 复制过来**，
而 `--sync-src` 又确实换掉了源码 ⇒ **清单与包内源码不一致**，而且门禁查不出来
（它只校验格式，不校验清单里的路径是否真的被重新构建过）。
本工具负责生成正确的那一份，并把它接进重签流程。

范围（固定，不随包变）
----------------------
只收**决定这份 bit 与这份 ELF 的源**：
  sw/app/*.{c,h}（排除生成的 xparameters.h）、sw/linker、sw/scripts、
  hw/ip/**、hw/boards、hw/constr、hw/scripts、tools/run_vivado_build.sh、
  tools/rebuild_software_package.py、tools/board
`hw/build/`、`logs/`、`tests/` 等测试与留证区**不进清单**——它们不是制品来源。

用法
----
    python3 tools/write_source_manifest.py --package hw/build/<某包>
    python3 tools/write_source_manifest.py --package hw/build/<某包> --resign

`--resign` 会在写完清单后重签 SHA256SUMS 并自检；不传则只改文件，由调用方自己重签。
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent

# 排除项：这些是构建产物或平台生成物，不是「源」
EXCLUDE_NAMES = {"xparameters.h"}
EXCLUDE_DIR_NAMES = {"__pycache__"}
EXCLUDE_SUFFIXES = {".pyc", ".pyo"}


def collect(repo: Path) -> list[str]:
    """返回清单要覆盖的、当前实际存在的源码相对路径（已排序、去重）。"""
    paths: set[str] = set()

    def add(p: Path) -> None:
        if not p.is_file():
            return
        rel = p.relative_to(repo)
        if (p.name in EXCLUDE_NAMES
                or any(part in EXCLUDE_DIR_NAMES for part in rel.parts)
                or p.suffix.lower() in EXCLUDE_SUFFIXES):
            return
        paths.add(rel.as_posix())

    for p in sorted((repo / "sw" / "app").glob("*.c")) + sorted((repo / "sw" / "app").glob("*.h")):
        add(p)
    for sub in ("sw/linker", "sw/scripts", "hw/ip", "hw/boards", "hw/constr", "hw/scripts"):
        for p in (repo / sub).rglob("*"):
            add(p)
    add(repo / "tools" / "run_vivado_build.sh")
    add(repo / "tools" / "rebuild_software_package.py")
    for p in (repo / "tools" / "board").rglob("*"):
        add(p)
    return sorted(paths)


def sha256(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--package", required=True, help="制品包目录（含 manifest.json）")
    ap.add_argument("--scope", default=None, help="覆盖默认 scope 描述")
    ap.add_argument("--resign", action="store_true", help="写完后重签 SHA256SUMS 并自检")
    args = ap.parse_args()

    pkg = (REPO / args.package).resolve() if not Path(args.package).is_absolute() else Path(args.package)
    if not (pkg / "manifest.json").is_file():
        print(f"不是制品包（缺 manifest.json）：{pkg}", file=sys.stderr)
        return 1

    files = collect(REPO)
    if not files:
        print("收集到的源码为空，拒绝写出空清单", file=sys.stderr)
        return 1

    # 逐项自检：必须是可放进包里的相对路径，且 SHA 合法
    table = {}
    for rel in files:
        if rel.startswith("/") or ".." in Path(rel).parts or "\\" in rel or ":" in rel:
            print(f"非法源码相对路径：{rel}", file=sys.stderr)
            return 1
        table[rel] = sha256(REPO / rel)

    scope = args.scope or (
        "BKB220 P16 SE150 源码快照（片上 LDPC：AXI 包装 IP + PS 侧驱动与位级置换）。"
        "只收决定 bit 与 ELF 的源；sw/app 是权威源，构建期复制进包内 workspace。"
        "hw/experimental 等仅仿真件不入清单。"
    )
    sm_path = pkg / "reports" / "source_manifest.json"
    sm_path.parent.mkdir(parents=True, exist_ok=True)
    sm_path.write_text(json.dumps(
        {"schema_version": 1, "scope": scope,
         "excluded_files": ["sw/app/xparameters.h"], "files": table},
        ensure_ascii=False, indent=1) + "\n")

    # manifest.json 里记的 source_manifest.sha256 要跟着变，否则门禁会判「缺被覆盖的 source_manifest」
    manifest_path = pkg / "manifest.json"
    manifest = json.loads(manifest_path.read_text())
    manifest.setdefault("source_manifest", {})
    manifest["source_manifest"]["path"] = "reports/source_manifest.json"
    manifest["source_manifest"]["sha256"] = sha256(sm_path)
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=1) + "\n")

    print(f"已写 {sm_path.relative_to(REPO)}：{len(table)} 条源码")
    print(f"  source_manifest.sha256 = {manifest['source_manifest']['sha256'][:16]}…")

    if args.resign:
        sums = pkg / "SHA256SUMS"
        listing = subprocess.run(
            ["find", ".", "-type", "f", "!", "-name", "SHA256SUMS",
             "!", "-name", "SHA256SUMS.pre-normalize-*", "-printf", "%P\n"],
            cwd=pkg, capture_output=True, text=True, check=True).stdout
        names = sorted(n for n in listing.split("\n") if n)
        lines = []
        for n in names:
            lines.append(f"{sha256(pkg / n)}  {n}")
        sums.write_text("\n".join(lines) + "\n")
        chk = subprocess.run(["sha256sum", "-c", "SHA256SUMS"], cwd=pkg,
                             capture_output=True, text=True)
        ok = sum(1 for l in chk.stdout.splitlines() if l.endswith("OK"))
        if chk.returncode != 0 or ok != len(names):
            print(f"SHA256SUMS 自检失败：{ok}/{len(names)}", file=sys.stderr)
            return 1
        print(f"  SHA256SUMS 已重签并自检：{ok}/{len(names)} OK")

    # 最后再核一遍：门禁要的那几个字段确实在
    sm = json.loads(sm_path.read_text())
    assert re.fullmatch(r"[0-9a-f]{64}", manifest["source_manifest"]["sha256"])
    assert isinstance(sm.get("files"), dict) and sm["files"]
    print("  门禁字段自检：files 非空 ✓  manifest.source_manifest.sha256 合法 ✓")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
