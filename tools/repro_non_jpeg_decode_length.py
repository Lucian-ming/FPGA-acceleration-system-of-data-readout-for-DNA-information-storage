#!/usr/bin/env python3
"""复现任意载荷被 JPEG EOI 规则错误截断/保留补零尾部的问题。"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parent.parent
CLIENT_DIR = REPO / "clients" / "python"
if str(CLIENT_DIR) not in sys.path:
    sys.path.insert(0, str(CLIENT_DIR))

from native_ldpc import K_INFO, bits_to_jpeg_bytes  # noqa: E402


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("dataset_root", type=Path, help="v2 外部数据包根目录")
    parser.add_argument("asset", nargs="?", default="numeric_signal", help="资产名（默认 numeric_signal）")
    args = parser.parse_args(argv)

    metadata_path = args.dataset_root / "encoded" / args.asset / "block000" / "encoding.json"
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    candidates = sorted((args.dataset_root / "payloads").glob(args.asset + ".*"))
    if len(candidates) != 1:
        raise SystemExit(f"期望 payloads/{args.asset}.* 恰有一个文件，找到 {len(candidates)} 个")
    payload = candidates[0].read_bytes()
    expected_bytes = int(metadata["input_bytes"])
    if len(payload) != expected_bytes:
        raise SystemExit(
            f"源载荷长度 {len(payload)} != encoding.json input_bytes {expected_bytes}；"
            "请选一个单块且长度相符的资产"
        )
    if len(payload) * 8 > K_INFO:
        raise SystemExit(f"源载荷 {len(payload)} B 超过 {K_INFO} bit 信息位容量")

    info = np.zeros(K_INFO, dtype=np.uint8)
    info[:len(payload) * 8] = np.unpackbits(np.frombuffer(payload, dtype=np.uint8))
    legacy = bits_to_jpeg_bytes(info)
    expected_sha = metadata["input_sha256"]
    legacy_sha = hashlib.sha256(legacy).hexdigest()
    reproduced = len(legacy) != expected_bytes or legacy_sha != expected_sha
    print(f"资产: {candidates[0].name}；信息位: {info.size} bit（回传信息字节 {info.size // 8} B）")
    print(f"encoding.json input_bytes: {expected_bytes} B")
    print(f"旧 bits_to_jpeg_bytes 输出: {len(legacy)} B")
    print(f"input_sha256: {expected_sha}")
    print(f"旧函数 SHA-256: {legacy_sha}")
    print(f"缺陷复现: {'是' if reproduced else '否'}")
    return 0 if reproduced else 1


if __name__ == "__main__":
    raise SystemExit(main())
