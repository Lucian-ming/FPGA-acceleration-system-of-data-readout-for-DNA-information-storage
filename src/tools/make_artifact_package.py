#!/usr/bin/env python3
"""把 Vivado/Vitis 2026.1 的构建输出组装成 run_g3.sh 可用的完整制品包。

产物结构：
  <out>/export/top_bd_wrapper.bit, dna_accel.xsa, ps7_init.tcl,
                 dna_lwip_app.elf, fsbl.elf, BOOT.bin, hardware_build_config.txt
  <out>/manifest.json     —— 身份、参数、工具版本、固件构建 ID
  <out>/SHA256SUMS        —— export/ 下全部文件的校验和

用法：
  python3 src/tools/make_artifact_package.py \
      --hw-export build/vivado/export \
      --sw-export build/software-export \
      --app-src src/sw/app \
      --out build/artifact \
      --package-name bkb220-release
"""
from __future__ import annotations

import argparse
import datetime as _dt
import hashlib
import json
import shutil
import sys
from pathlib import Path

FILES = [
    "top_bd_wrapper.bit",
    "dna_accel.xsa",
    "ps7_init.tcl",
    "dna_lwip_app.elf",
    "fsbl.elf",
    "BOOT.bin",
    "hardware_build_config.txt",
]


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def compute_fw_build_id(app_src: Path) -> str:
    """与软件构建流程一致：按相对路径排序，对 .c/.h 路径与内容做 SHA-256。"""
    files = sorted(
        (p for p in app_src.rglob("*") if p.is_file() and p.suffix in {".c", ".h"}),
        key=lambda p: p.relative_to(app_src).as_posix(),
    )
    if not files:
        raise SystemExit(f"应用源码目录没有 .c/.h：{app_src}")
    digest = hashlib.sha256()
    for p in files:
        digest.update(p.relative_to(app_src).as_posix().encode("utf-8"))
        digest.update(p.read_bytes())
    return digest.hexdigest()[:16]


def parse_config(path: Path) -> dict[str, str]:
    data: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        data[key.strip()] = value.strip()
    return data


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--hw-export", type=Path, required=True, help="Vivado 的 export 目录")
    ap.add_argument("--sw-export", type=Path, required=True, help="Vitis 的 software-export 目录")
    ap.add_argument("--app-src", type=Path, required=True, help="应用源码目录（算 fw_build_id）")
    ap.add_argument("--out", type=Path, required=True, help="输出制品包目录（必须不存在）")
    ap.add_argument("--package-name", default="bkb220-release")
    args = ap.parse_args(argv)

    if args.out.exists() and any(args.out.iterdir()):
        raise SystemExit(f"输出目录已存在且非空：{args.out}")
    export = args.out / "export"
    export.mkdir(parents=True, exist_ok=True)

    sources = {name: (args.sw_export / name) for name in FILES}
    sources["top_bd_wrapper.bit"] = args.hw_export / "top_bd_wrapper.bit"
    sources["dna_accel.xsa"] = args.hw_export / "dna_accel.xsa"
    sources["hardware_build_config.txt"] = args.hw_export / "hardware_build_config.txt"
    missing = [str(p) for p in sources.values() if not p.is_file()]
    if missing:
        raise SystemExit("缺少构建产物：\n  " + "\n  ".join(missing))

    for name, src in sources.items():
        shutil.copy2(src, export / name)

    cfg = parse_config(export / "hardware_build_config.txt")
    fw_build_id = compute_fw_build_id(args.app_src)

    manifest = {
        "schema_version": 1,
        "package_name": args.package_name,
        "created_utc": _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "fw_build_id": fw_build_id,
        "board_id": cfg.get("board_id", "bkb220"),
        "part": cfg.get("part", "xc7z020clg400-2"),
        "parameters": {
            "READ_BPS": int(cfg.get("READ_BPS", 150)),
            "NUM_LC": int(cfg.get("NUM_LC", 50)),
            "STRIDE": int(cfg.get("STRIDE", 807)),
            "REF_LEN": int(cfg.get("REF_LEN", 957)),
            "BATCH": int(cfg.get("BATCH", 64)),
            "C_STAGE1_P_WAYS": int(cfg.get("C_STAGE1_P_WAYS", 16)),
            "C_STAGE1_PIPE_TREE": int(cfg.get("C_STAGE1_PIPE_TREE", 1)),
        },
        "artifacts": {
            "bit": "export/top_bd_wrapper.bit",
            "xsa": "export/dna_accel.xsa",
            "ps7_init": "export/ps7_init.tcl",
            "elf": "export/dna_lwip_app.elf",
            "fsbl": "export/fsbl.elf",
            "boot": "export/BOOT.bin",
        },
        "tool_versions": {
            "vivado": cfg.get("tool_version", "2026.1"),
            "vitis": "2026.1",
            "build_method": "Vivado/Vitis 2026.1 on Windows; no WSL dependency",
        },
    }
    (args.out / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")

    # SHA256SUMS 必须覆盖 manifest.json 自身（制品门禁要求），随后由
    # write_source_manifest.py --resign 追加 source_manifest.json。
    lines = [f"{sha256(export / name)}  export/{name}" for name in sorted(FILES)]
    lines.append(f"{sha256(args.out / 'manifest.json')}  manifest.json")
    lines.sort(key=lambda line: line.split("  ", 1)[1])
    (args.out / "SHA256SUMS").write_text("\n".join(lines) + "\n", encoding="utf-8")

    print(f"ARTIFACT_DIR {args.out}")
    print(f"FW_BUILD_ID {fw_build_id}")
    for line in lines:
        print("  " + line)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
