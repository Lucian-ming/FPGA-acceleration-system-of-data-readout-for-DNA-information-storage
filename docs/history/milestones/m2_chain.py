#!/usr/bin/env python3
"""Small, auditable checkpoint model for the quick three-stage regression.

The script never supplies a DUT checkpoint.  It only derives the software
scoreboard from the actual Stage1/Stage2 files emitted by the preceding RTL
simulation, then performs the PS-equivalent byte/bit-plane XOR.
"""
from __future__ import annotations

import argparse
import re
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
BATCH = 64


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


def packed_record(words: list[int], record: int) -> int:
    base = record * WORDS_PER_RECORD
    return sum(words[base + j] << (64 * j) for j in range(WORDS_PER_RECORD))


def codeword_to_symbols(codeword: int) -> np.ndarray:
    hi = np.array([(codeword >> i) & 1 for i in range(CODEWORD_BITS // 2)], dtype=np.uint8)
    lo = np.array([
        (codeword >> (CODEWORD_BITS // 2 + i)) & 1
        for i in range(CODEWORD_BITS // 2)
    ], dtype=np.uint8)
    return (hi << 1) | lo


def symbols_to_codeword(symbols: np.ndarray) -> int:
    if symbols.size != CODEWORD_BITS // 2:
        raise ValueError(f"read has {symbols.size} symbols, expected {CODEWORD_BITS // 2}")
    value = 0
    for i, symbol in enumerate(symbols):
        value |= int((symbol >> 1) & 1) << i
        value |= int(symbol & 1) << (CODEWORD_BITS // 2 + i)
    return value


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
        if position + CODEWORD_BITS // 2 > LAYER_SIZE:
            raise ValueError(f"Stage1 record {offset // WORDS_PER_RECORD} position {position} is out of range")
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


def cmd_prepare_stage1(args: argparse.Namespace) -> int:
    """Build forward/RC Stage1 stimuli independently from committed read codewords.

    stage2_in.hex is used only as the scoreboard for position/score/codeword.  The
    reverse-complement input is derived here from reads_cw.hex and is checked
    against the codeword field in that scoreboard before any simulation starts.
    """
    read_codewords = read_words(Path(args.reads_cw))
    if args.original_records:
        read_codewords = read_codewords[:args.original_records]
    if not read_codewords:
        raise ValueError("no Stage1 input codewords")

    golden_words = read_words(Path(args.stage2_golden))
    expected_records = len(read_codewords) * 2
    if len(golden_words) != expected_records * WORDS_PER_RECORD:
        raise ValueError(
            f"Stage1 scoreboard has {len(golden_words)} words, expected "
            f"{expected_records * WORDS_PER_RECORD}"
        )

    stimuli: list[int] = []
    expected: list[tuple[int, int]] = []
    for original, forward_cw in enumerate(read_codewords):
        forward = codeword_to_symbols(forward_cw)
        reverse = (forward ^ 1)[::-1]
        for direction, symbols in enumerate((forward, reverse)):
            record = 2 * original + direction
            stimulus = symbols_to_codeword(symbols)
            golden = packed_record(golden_words, record)
            golden_score = golden & 0x3FF
            golden_position = (golden >> 10) & 0xFFFF
            golden_codeword = (golden >> 26) & ((1 << CODEWORD_BITS) - 1)
            if stimulus != golden_codeword:
                raise ValueError(
                    f"derived codeword differs from Stage1 scoreboard at record {record}"
                )
            stimuli.append(stimulus)
            expected.append((golden_position, golden_score))

    if len(stimuli) % BATCH:
        raise ValueError(f"Stage1 stimulus count {len(stimuli)} is not a multiple of {BATCH}")

    reads_out = Path(args.reads_out)
    expect_out = Path(args.expect_out)
    reads_out.parent.mkdir(parents=True, exist_ok=True)
    expect_out.parent.mkdir(parents=True, exist_ok=True)
    reads_out.write_text(
        "\n".join(f"{value:075x}" for value in stimuli) + "\n", encoding="ascii"
    )
    expect_out.write_text(
        "# idx pos score\n"
        + "\n".join(f"{i} {position} {score}" for i, (position, score) in enumerate(expected))
        + "\n",
        encoding="ascii",
    )

    batch_dir = Path(args.batch_dir)
    batch_dir.mkdir(parents=True, exist_ok=True)
    for batch, start in enumerate(range(0, len(stimuli), BATCH)):
        (batch_dir / f"reads_{batch:03d}.hex").write_text(
            "\n".join(f"{value:075x}" for value in stimuli[start:start + BATCH]) + "\n",
            encoding="ascii",
        )
        (batch_dir / f"expect_{batch:03d}.txt").write_text(
            "# idx pos score\n"
            + "\n".join(
                f"{i} {position} {score}"
                for i, (position, score) in enumerate(expected[start:start + BATCH])
            )
            + "\n",
            encoding="ascii",
        )

    print(
        f"[M2 MODEL] prepared {len(read_codewords)} original reads -> "
        f"{len(stimuli)} forward/RC Stage1 records in {len(stimuli) // BATCH} batches"
    )
    return 0


def cmd_combine_stage1(args: argparse.Namespace) -> int:
    input_dir = Path(args.input_dir)
    paths = sorted(input_dir.glob("actual_*.hex"))
    if len(paths) != args.batches:
        raise ValueError(f"found {len(paths)} Stage1 batches, expected {args.batches}")
    words: list[int] = []
    for path in paths:
        part = read_words(path)
        if len(part) != BATCH * WORDS_PER_RECORD:
            raise ValueError(f"{path} has {len(part)} words, expected {BATCH * WORDS_PER_RECORD}")
        words.extend(part)
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text("\n".join(f"{value:016x}" for value in words) + "\n", encoding="ascii")
    print(f"[M2 MODEL] combined {len(paths)} batches -> {len(words) // WORDS_PER_RECORD} Stage1 records")
    return 0


def cmd_flip(args: argparse.Namespace) -> int:
    words = read_words(Path(args.input))
    if args.bit < 0 or args.bit >= len(words) * 64:
        raise ValueError(f"fault bit {args.bit} outside {len(words) * 64} stored bits")
    words[args.bit // 64] ^= 1 << (args.bit % 64)
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text("\n".join(f"{value:016x}" for value in words) + "\n", encoding="ascii")
    print(f"[M2 MODEL] flipped bit {args.bit} in {args.input}")
    return 0


def cmd_to_bittext(args: argparse.Namespace) -> int:
    words = read_words(Path(args.input))
    if len(words) * 64 < args.bits:
        raise ValueError(f"input stores {len(words) * 64} bits, expected at least {args.bits}")
    text = "".join(
        "01"[(words[index // 64] >> (index % 64)) & 1]
        for index in range(args.bits)
    )
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(text, encoding="ascii")
    print(f"[M2 MODEL] wrote {args.bits} LSB-first bits to {output}")
    return 0


def cmd_summarize_stage1(args: argparse.Namespace) -> int:
    paths = sorted(Path(args.input_dir).glob("stage1_run_*/xsim.log"))
    if len(paths) != args.batches:
        raise ValueError(f"found {len(paths)} Stage1 logs, expected {args.batches}")
    pattern = re.compile(
        r"分数不符\s+(\d+)\s+条\s+/\s+码字不符\s+(\d+)\s+条\s+/\s+并列峰\s+(\d+)\s+条"
    )
    score_errors = codeword_errors = ties = 0
    for path in paths:
        matches = pattern.findall(path.read_text(encoding="utf-8", errors="replace"))
        if len(matches) != 1:
            raise ValueError(f"{path} has {len(matches)} Stage1 summary lines, expected 1")
        score, codeword, tied = (int(value) for value in matches[0])
        score_errors += score
        codeword_errors += codeword
        ties += tied
    allowed_ties = args.records * args.max_percent // 100
    print(
        f"[M2 MODEL] Stage1 aggregate: score_errors={score_errors}, "
        f"codeword_errors={codeword_errors}, ties={ties}/{args.records}, "
        f"allowed={allowed_ties} ({args.max_percent}%)"
    )
    if score_errors or codeword_errors or ties > allowed_ties:
        raise ValueError("Stage1 aggregate scoreboard failed")
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
    p = sub.add_parser("prepare-stage1")
    p.add_argument("--reads-cw", required=True)
    p.add_argument("--stage2-golden", required=True)
    p.add_argument("--reads-out", required=True)
    p.add_argument("--expect-out", required=True)
    p.add_argument("--batch-dir", required=True)
    p.add_argument("--original-records", type=int, default=0)
    p.set_defaults(func=cmd_prepare_stage1)
    p = sub.add_parser("combine-stage1")
    p.add_argument("--input-dir", required=True)
    p.add_argument("--output", required=True)
    p.add_argument("--batches", type=int, required=True)
    p.set_defaults(func=cmd_combine_stage1)
    p = sub.add_parser("flip")
    p.add_argument("--input", required=True)
    p.add_argument("--output", required=True)
    p.add_argument("--bit", type=int, required=True)
    p.set_defaults(func=cmd_flip)
    p = sub.add_parser("to-bittext")
    p.add_argument("--input", required=True)
    p.add_argument("--output", required=True)
    p.add_argument("--bits", type=int, required=True)
    p.set_defaults(func=cmd_to_bittext)
    p = sub.add_parser("summarize-stage1")
    p.add_argument("--input-dir", required=True)
    p.add_argument("--batches", type=int, required=True)
    p.add_argument("--records", type=int, required=True)
    p.add_argument("--max-percent", type=int, default=5)
    p.set_defaults(func=cmd_summarize_stage1)
    args = ap.parse_args()
    try:
        return args.func(args)
    except (OSError, ValueError) as exc:
        print(f"[M2 MODEL] FAIL: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
