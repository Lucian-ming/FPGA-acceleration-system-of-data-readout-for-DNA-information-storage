#!/usr/bin/env python3
"""Small, auditable checkpoint model for the quick three-stage regression.

The script never supplies a DUT checkpoint.  It only derives the software
scoreboard from the actual Stage1/Stage2 files emitted by the preceding RTL
simulation, then performs the PS-equivalent byte/bit-plane XOR.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "tools"))
from golden_model import desparsify  # noqa: E402

LAYER_SIZE = 40500
TOTAL_BITS = 2 * LAYER_SIZE
CODEWORD_BITS = 300
WORDS_PER_RECORD = 6
OUT_BEATS = (TOTAL_BITS + 63) // 64


def read_words(path: Path) -> list[int]:
    vals = []
    for token in path.read_text(encoding="ascii").split():
        vals.append(int(token, 16))
    return vals


def write_words(path: Path, bits: np.ndarray) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    out = []
    for start in range(0, bits.size, 64):
        value = 0
        for bit, b in enumerate(bits[start : start + 64]):
            value |= int(b) << bit
        out.append(f"{value:016x}")
    path.write_text("\n".join(out) + "\n", encoding="ascii")


def watermark_bits(path: Path) -> np.ndarray:
    symbols = [int(x, 16) & 3 for x in path.read_text(encoding="ascii").split()]
    if len(symbols) != LAYER_SIZE:
        raise ValueError(f"watermark has {len(symbols)} symbols, expected {LAYER_SIZE}")
    hi = np.array([(s >> 1) & 1 for s in symbols], dtype=np.uint8)
    lo = np.array([s & 1 for s in symbols], dtype=np.uint8)
    return np.concatenate([hi, lo])


def consensus_from_stage1(path: Path, score_min: int) -> np.ndarray:
    words = read_words(path)
    if len(words) == 0 or len(words) % WORDS_PER_RECORD:
        raise ValueError(f"Stage1 checkpoint has {len(words)} words, not a positive multiple of 6")
    votes = np.zeros(TOTAL_BITS, dtype=np.int32)
    used = 0
    for offset in range(0, len(words), WORDS_PER_RECORD):
        value = sum(words[offset + j] << (64 * j) for j in range(WORDS_PER_RECORD))
        score = value & 0x3FF
        position = (value >> 10) & 0xFFFF
        codeword = (value >> 26) & ((1 << CODEWORD_BITS) - 1)
        if score < score_min:
            continue
        used += 1
        for i in range(CODEWORD_BITS // 2):
            votes[position + i] += 1 if ((codeword >> i) & 1) else -1
            votes[LAYER_SIZE + position + i] += 1 if ((codeword >> (CODEWORD_BITS // 2 + i)) & 1) else -1
    print(f"[M2 MODEL] Stage1 records={len(words)//WORDS_PER_RECORD}, score_min={score_min}, used={used}")
    return (votes > 0).astype(np.uint8)


def cmd_stage2(args: argparse.Namespace) -> int:
    consensus = consensus_from_stage1(Path(args.stage1), args.score_min)
    write_words(Path(args.stage2_expect), consensus)
    wm = watermark_bits(Path(args.watermark))
    sparse = consensus ^ wm
    write_words(Path(args.sparse_expect), sparse)
    codeword = desparsify(sparse)
    write_words(Path(args.stage3_expect), codeword)
    print(f"[M2 MODEL] Stage2={consensus.size} bit, XOR={sparse.size} bit, Stage3={codeword.size} bit")
    return 0


def cmd_xor(args: argparse.Namespace) -> int:
    words = read_words(Path(args.stage2))
    if len(words) != OUT_BEATS:
        raise ValueError(f"Stage2 checkpoint has {len(words)} beats, expected {OUT_BEATS}")
    bits = np.zeros(TOTAL_BITS, dtype=np.uint8)
    for j, value in enumerate(words):
        for bit in range(64):
            index = j * 64 + bit
            if index < TOTAL_BITS:
                bits[index] = (value >> bit) & 1
    sparse = bits ^ watermark_bits(Path(args.watermark))
    write_words(Path(args.sparse), sparse)
    print(f"[M2 MODEL] PS XOR produced {sparse.size} bit / {OUT_BEATS} beats")
    return 0


def cmd_pad(args: argparse.Namespace) -> int:
    words = read_words(Path(args.input))
    if len(words) % WORDS_PER_RECORD:
        raise ValueError("Stage1 checkpoint is not record-aligned")
    current = len(words) // WORDS_PER_RECORD
    if current > args.records:
        raise ValueError(f"checkpoint has {current} records, cannot pad to {args.records}")
    words = words + [0] * ((args.records - current) * WORDS_PER_RECORD)
    Path(args.output).parent.mkdir(parents=True, exist_ok=True)
    Path(args.output).write_text("\n".join(f"{v:016x}" for v in words) + "\n", encoding="ascii")
    print(f"[M2 MODEL] padded Stage1 {current} -> {args.records} records")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("stage2")
    p.add_argument("--stage1", required=True)
    p.add_argument("--watermark", required=True)
    p.add_argument("--stage2-expect", required=True)
    p.add_argument("--sparse-expect", required=True)
    p.add_argument("--stage3-expect", required=True)
    p.add_argument("--score-min", type=int, default=67)
    p.set_defaults(func=cmd_stage2)
    p = sub.add_parser("xor")
    p.add_argument("--stage2", required=True)
    p.add_argument("--watermark", required=True)
    p.add_argument("--sparse", required=True)
    p.set_defaults(func=cmd_xor)
    p = sub.add_parser("pad")
    p.add_argument("--input", required=True)
    p.add_argument("--output", required=True)
    p.add_argument("--records", type=int, required=True)
    p.set_defaults(func=cmd_pad)
    args = ap.parse_args()
    try:
        return args.func(args)
    except (OSError, ValueError) as exc:
        print(f"[M2 MODEL] FAIL: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
