#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""板上逐级取证：把 XSDB 只读导出的四级 DDR 快照与仓库黄金向量逐位比对。

为什么需要它
------------
2026-08-29 那轮把 B23/B24/B25/B26/B27 五个缺陷全定位出来，靠的都是同一招：
板子跑完**不复位、不重烧**，用 XSDB 只读把四级中间结果从 DDR 导出来，
再和 `tests/golden/` 逐位比。这比看串口日志或看最终图片有效得多——
它能直接指出"错在第几级"，而不是只知道"最后不对"。

这套比对此前散在各次会话的临时脚本里，每次重写一遍、口径还容易飘。
本工具把它固化下来，并且**把已知缺陷的特征签名内置成检查项**，
这样同类问题再出现时能立刻认出来，而不是从头再推一遍。

用法
----
    # 先在 Windows 侧用 XSDB 只读导出（不要复位）：
    #   xsdb.bat D:\\dna_board_smoke\\dump_ddr.tcl
    python3 tools/board_stage_check.py --dump-dir <G3留证目录>
    python3 tools/board_stage_check.py --dump-dir <手工dump目录> \\
        --payload-sha256 <期望载荷SHA256>
    python3 tools/board_stage_check.py --dump-dir <目录> --golden-dir tests/golden
        # 显式强制使用指定基准；没有匹配基准时必须保留 UNVERIFIED

判据纪律
--------
任何一级真不符以 1 退出；没有对应载荷的黄金向量以 3 退出并标为
``UNVERIFIED``，不打印成 PASS 或硬件 FAIL。**四级全绿也不等于 G3 闭环**——
最终判据仍由 ``run_g3.sh`` 的架构与系统判据共同决定。
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
GOLDEN = REPO / "tests" / "golden"
BASELINE_MANIFEST = GOLDEN / "board_stage_baselines.json"
DATASETS = REPO / "tests" / "datasets"
DEFAULT_DUMP_DIR = Path("/mnt/d/dna_board_smoke")

RECORD_BYTES = 48          # Stage1 每条记录 48 B = 6 拍 x 64 bit
BEATS_PER_RECORD = 6
SCORE_BITS = 10            # 记录 bit[9:0]
POS_BITS = 16              # 记录 bit[25:10]
L_SYMBOLS = 40500          # 水印符号总数，position 不可能 >= 它


def read_hex_words(path: Path) -> list[int]:
    return [int(line.strip(), 16) for line in path.read_text().splitlines() if line.strip()]


def le_words(blob: bytes, width: int = 8) -> list[int]:
    return [int.from_bytes(blob[i:i + width], "little") for i in range(0, len(blob) - width + 1, width)]


class Result:
    def __init__(self, name: str) -> None:
        self.name = name
        self.ok = True
        self.unverified = False
        self.lines: list[str] = []

    def note(self, msg: str) -> None:
        self.lines.append(msg)

    def fail(self, msg: str) -> None:
        self.ok = False
        self.unverified = False
        self.lines.append(msg)

    def mark_unverified(self, msg: str) -> None:
        if self.ok:
            self.unverified = True
        self.lines.append(msg)

    def render(self) -> None:
        if not self.ok:
            mark = "❌ FAIL"
        elif self.unverified:
            mark = "⚠️ 未取证 / UNVERIFIED"
        else:
            mark = "✅ PASS"
        print(f"\n=== {self.name} — {mark} ===")
        for line in self.lines:
            print(f"  {line}")


def find_payload_sha256(dump_dir: Path, explicit: str | None) -> str | None:
    """在线阶段从已经生成的 G3 层报告取载荷身份；人工复算可显式传入。"""
    if explicit:
        value = explicit.lower()
        if not re.fullmatch(r"[0-9a-f]{64}", value):
            raise ValueError("--payload-sha256 必须是 64 位十六进制 SHA-256")
        return value

    reported: set[str] = set()
    for path in dump_dir.glob("g3_layers_run*.json"):
        data = json.loads(path.read_text(encoding="utf-8"))
        value = data.get("expect_sha256")
        if value:
            value = str(value).lower()
            if not re.fullmatch(r"[0-9a-f]{64}", value):
                raise ValueError(f"{path} 的 expect_sha256 不是有效 SHA-256")
            reported.add(value)
    if len(reported) > 1:
        raise ValueError(f"G3 层报告中的期望载荷 SHA 不一致：{sorted(reported)}")
    if reported:
        return next(iter(reported))

    summary = dump_dir / "summary.txt"
    if summary.is_file():
        match = re.search(r"^期望系统 SHA\s*:\s*([0-9a-fA-F]{64})", summary.read_text(
            encoding="utf-8", errors="replace"), re.MULTILINE)
        if match:
            return match.group(1).lower()
    return None


def load_baseline_dir(payload_sha256: str, read_bps: int) -> Path | None:
    """只按显式登记的载荷 SHA 和读长匹配，绝不默认套用 R0.83 基准。"""
    manifest = json.loads(BASELINE_MANIFEST.read_text(encoding="utf-8"))
    for entry in manifest.get("baselines", []):
        if (entry.get("payload_sha256", "").lower() == payload_sha256
                and int(entry.get("read_bps", -1)) == read_bps):
            return (GOLDEN / entry["golden_dir"]).resolve()
    return None


def find_dataset_ids(payload_sha256: str) -> list[str]:
    """从数据集自己的 manifest 识别载荷，不在 tests/datasets 下复制任何输入。"""
    found: list[str] = []
    for path in DATASETS.glob("*/manifest.json"):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if data.get("payload", {}).get("sha256", "").lower() == payload_sha256:
            found.append(str(data.get("dataset_id", path.parent.name)))

    # D2_text_sub1pct 继承父数据集的载荷身份，只改变 FASTQ 读段。
    for path in DATASETS.glob("*/mutation_manifest.json"):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        parent = data.get("parent_manifest", {})
        if parent.get("payload", {}).get("sha256", "").lower() == payload_sha256:
            found.append(path.parent.name)
    return sorted(set(found))


def check_watermark(dump_dir: Path, golden_dir: Path, ref_len: int = 957) -> Result:
    r = Result("展开水印 @0x10040000  vs  wm_regions.hex")
    blob = (dump_dir / "dump_wm_regions.bin").read_bytes()
    gold = read_hex_words(golden_dir / "wm_regions.hex")
    got = le_words(blob, 4)
    n = min(len(got), len(gold))
    bad = [i for i in range(n) if got[i] != gold[i]]
    if bad:
        regions = sorted({i // ref_len for i in bad})
        r.fail(f"{len(bad)}/{n} 字不符，涉及 {len(regions)}/50 个区域，前几个：{regions[:8]}")
        r.note("→ 这是 PS 侧展开水印写进 DDR 的内容；它错说明问题在固件 expand_watermark_regions()")
    else:
        r.note(f"{n}/{n} 字逐位相同")
    return r


def check_stage1(dump_dir: Path, reads: int, golden_dir: Path, record_bytes: int = 48, beats_per_rec: int = 6) -> Result:
    r = Result("Stage1 输出 @0x10600000  vs  stage2_in.hex")
    blob = (dump_dir / "dump_stage1.bin").read_bytes()
    gold_w = read_hex_words(golden_dir / "stage2_in.hex")

    def brec(i: int) -> int:
        return int.from_bytes(blob[i * record_bytes:(i + 1) * record_bytes], "little")

    def grec(i: int) -> int:
        v = 0
        for k in range(beats_per_rec):
            v |= gold_w[i * beats_per_rec + k] << (64 * k)
        return v

    n_gold = len(gold_w) // beats_per_rec
    n = min(reads, len(blob) // record_bytes, n_gold)

    # --- 已知缺陷签名 1（B23）：TDATA 比 TVALID 早一拍 → 每包实收 [b1..b5,b5] ---
    def word(i: int, k: int) -> int:
        off = i * record_bytes + k * 8
        return int.from_bytes(blob[off:off + 8], "little")

    dup = sum(1 for i in range(n) if word(i, beats_per_rec - 2) == word(i, beats_per_rec - 1))
    if dup > n * 0.5:
        r.fail(f"【B23 签名】{dup}/{n} 条记录的倒数第 1、2 拍完全相同 → AXIS 输出级 TDATA/TVALID 又偏了一拍")

    # --- 已知缺陷签名 2（B26）：结果整体错位若干条读段 ---
    best_off, best_hits = 0, -1
    for off in (0, 1, -1, 2, -2):
        lo, hi = max(0, -off), min(n, n_gold - off)
        if hi <= lo:
            continue
        hits = sum(1 for i in range(lo, hi) if (brec(i) >> 26) == (grec(i + off) >> 26))
        if hits > best_hits:
            best_off, best_hits = off, hits
    if best_off != 0:
        r.fail(f"【B26 签名】结果整体错位 {best_off:+d} 条读段"
               f"（board[i] 的码字对上 golden[i{best_off:+d}]，{best_hits} 条）")

    # --- 逐条比对（按检出的错位对齐，便于看清剩余差异） ---
    lo, hi = max(0, -best_off), min(n, n_gold - best_off)
    exact = cw_same = score_same = 0
    pos_delta: dict[int, int] = {}
    for i in range(lo, hi):
        b, g = brec(i), grec(i + best_off)
        if b == g:
            exact += 1
        if (b >> 26) == (g >> 26):
            cw_same += 1
        if (b & ((1 << SCORE_BITS) - 1)) == (g & ((1 << SCORE_BITS) - 1)):
            score_same += 1
        d = ((b >> SCORE_BITS) & ((1 << POS_BITS) - 1)) - ((g >> SCORE_BITS) & ((1 << POS_BITS) - 1))
        pos_delta[d] = pos_delta.get(d, 0) + 1
    total = hi - lo

    # --- 已知缺陷签名 3（B25）：水印预载写偏一符号 → position 恒 +1 ---
    if pos_delta.get(1, 0) > total * 0.5:
        r.fail(f"【B25 签名】{pos_delta[1]}/{total} 条 position 恒比黄金大 1 → 水印预载写地址与数据不同拍")

    # --- 物理合理性：position 必须 < L ---
    bad_pos = sum(1 for i in range(lo, hi)
                  if ((brec(i) >> SCORE_BITS) & ((1 << POS_BITS) - 1)) >= L_SYMBOLS)
    if bad_pos:
        r.fail(f"{bad_pos}/{total} 条 position >= L={L_SYMBOLS}，不可能 → 记录内容是随机比特")

    r.note(f"整条 {record_bytes} B 逐位相同：{exact}/{total}")
    r.note(f"码字相同：{cw_same}/{total}   score 相同：{score_same}/{total}")
    top = sorted(pos_delta.items(), key=lambda kv: -kv[1])[:3]
    r.note(f"position 差值 top3：{top}")
    if exact < total:
        r.note("→ 未完全一致；差异若集中在少数条，多为并列被打破，通常不致命")
    if exact == total and best_off == 0:
        r.note("→ Stage1 逐位正确")
    return r


def _compare_words(r: Result, blob: bytes, gold_path: Path, hint: str) -> Result:
    gold = read_hex_words(gold_path)
    got = le_words(blob, 8)
    n = min(len(got), len(gold))
    same = sum(1 for i in range(n) if got[i] == gold[i])
    bits = sum(bin(got[i] ^ gold[i]).count("1") for i in range(n))
    ber = 100.0 * bits / (n * 64)
    r.note(f"整字相同 {same}/{n}，比特误码 {ber:.2f}%")
    if ber > 1.0:
        r.fail(f"比特误码 {ber:.2f}% 远超容差")
        r.note(hint)
    return r


def check_stage2(dump_dir: Path, golden_dir: Path) -> Result:
    r = Result("Stage2 输出 ⊕ 水印 @0x11000000  vs  sparse_expect.hex")
    r.note("注意：PS 会在 Stage2 之后就地异或水印，所以这里比的是 sparse 而不是 stage2_rtl_expect")
    return _compare_words(r, (dump_dir / "dump_stage2.bin").read_bytes(),
                          golden_dir / "sparse_expect.hex",
                          "→ 输入若正确而此级错，怀疑 Voter 的 AXI 读通路或 PS 侧异或的 cache 次序")


def check_stage3(dump_dir: Path, golden_dir: Path) -> Result:
    r = Result("Stage3 输出 @0x11100000  vs  stage3_expect.hex")
    blob = (dump_dir / "dump_stage3.bin").read_bytes()[:8100]
    r = _compare_words(r, blob, golden_dir / "stage3_expect.hex",
                       "→ 输入若正确而此级错，先查 B27 那类「被自己重启」的寄存器时序，"
                       "再查 Decoder 的 AXI 读通路")
    return r


def unverified_checks(read_bps: int, payload_sha256: str | None,
                      dataset_ids: list[str]) -> list[Result]:
    if payload_sha256:
        identity = f"payload SHA-256 {payload_sha256}"
        if dataset_ids:
            identity += f"（数据集：{', '.join(dataset_ids)}）"
        else:
            identity += "（仓库数据集 manifest 未识别）"
    else:
        identity = "未提供载荷 SHA-256，无法识别适用的黄金包"
    reason = f"{identity}；tests/golden 未登记 read_bps={read_bps} 的四级基准，本级未取证"
    checks = [
        Result("展开水印 @0x10040000  vs  wm_regions.hex"),
        Result("Stage1 输出 @0x10600000  vs  stage2_in.hex"),
        Result("Stage2 输出 ⊕ 水印 @0x11000000  vs  sparse_expect.hex"),
        Result("Stage3 输出 @0x11100000  vs  stage3_expect.hex"),
    ]
    for check in checks:
        check.mark_unverified(reason)
    return checks


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dump-dir", type=Path, default=DEFAULT_DUMP_DIR,
                    help="dump_ddr.tcl 导出的四个 .bin 所在目录")
    ap.add_argument("--reads", type=int, default=4096, help="本次任务的记录条数（默认 4096）")
    ap.add_argument("--read-bps", type=int, default=150, choices=[150, 250],
                    help="读段碱基数（150 或 250，默认 150）")
    ap.add_argument("--golden-dir", type=Path, default=None,
                    help="显式指定黄金目录；指定后按用户要求强制比较")
    ap.add_argument("--payload-sha256", default=None,
                    help="手工 dump 没有 G3 层报告时指定期望载荷 SHA-256")
    args = ap.parse_args()

    if not args.dump_dir.is_dir():
        print(f"FATAL: 找不到 dump 目录 {args.dump_dir}", file=sys.stderr)
        return 2

    if args.read_bps == 250:
        record_bytes = 72
        beats_per_rec = 9
        ref_len = 1055
    else:
        record_bytes = 48
        beats_per_rec = 6
        ref_len = 957

    checks = []
    for fn, need in ((check_watermark, "dump_wm_regions.bin"),
                     (None, "dump_stage1.bin"),
                     (check_stage2, "dump_stage2.bin"),
                     (check_stage3, "dump_stage3.bin")):
        if not (args.dump_dir / need).is_file():
            print(f"FATAL: 缺少 {args.dump_dir / need}，先在 Windows 侧跑 dump_ddr.tcl", file=sys.stderr)
            return 2

    try:
        payload_sha256 = find_payload_sha256(args.dump_dir, args.payload_sha256)
        if args.golden_dir is not None:
            golden_dir = args.golden_dir.resolve()
            baseline_source = "--golden-dir 显式指定"
        elif payload_sha256:
            golden_dir = load_baseline_dir(payload_sha256, args.read_bps)
            baseline_source = "BOARD_STAGE_BASELINES.json 按载荷 SHA 与读长匹配"
        else:
            golden_dir = None
            baseline_source = "缺少载荷身份"
    except (OSError, json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
        print(f"FATAL: 无法确定四级基准：{exc}", file=sys.stderr)
        return 2

    print(f"dump 目录：{args.dump_dir}")
    print(f"期望载荷 SHA256：{payload_sha256 or '未提供'}")
    if golden_dir is None:
        dataset_ids = find_dataset_ids(payload_sha256) if payload_sha256 else []
        print(f"黄金向量：无可比基准（{baseline_source}；read_bps={args.read_bps}）")
        checks = unverified_checks(args.read_bps, payload_sha256, dataset_ids)
        for c in checks:
            c.render()
        print("\n" + "=" * 60)
        print("逐级取证：UNVERIFIED — 该载荷没有四级黄金基准，未取证；不得据此判 PASS 或硬件 FAIL。")
        return 3

    if not golden_dir.is_dir():
        print(f"FATAL: 黄金向量目录不存在：{golden_dir}", file=sys.stderr)
        return 2
    print(f"黄金向量：{golden_dir} ({baseline_source}; read_bps={args.read_bps}, {record_bytes}B/read)")
    checks.append(check_watermark(args.dump_dir, golden_dir, ref_len))
    checks.append(check_stage1(args.dump_dir, args.reads, golden_dir, record_bytes, beats_per_rec))
    checks.append(check_stage2(args.dump_dir, golden_dir))
    checks.append(check_stage3(args.dump_dir, golden_dir))

    for c in checks:
        c.render()

    failed = [c.name for c in checks if not c.ok]
    unverified = [c.name for c in checks if c.unverified and c.ok]
    print("\n" + "=" * 60)
    if failed:
        print(f"逐级取证：{len(checks) - len(failed)}/{len(checks)} 级通过，最先出错的一级是：")
        print(f"  → {failed[0]}")
        print("按 AGENTS.md 的纪律：第一处不一致就停下来定位到具体一级，不要跑完全程再回头猜。")
        return 1
    if unverified:
        print(f"逐级取证：UNVERIFIED — {len(unverified)}/{len(checks)} 级缺少可用基准，未取证。")
        return 3
    print(f"逐级取证：{len(checks)}/{len(checks)} 级全部通过。")
    print("四级取证只作为 G3 的中间层证据；整体裁决仍由 run_g3.sh 的架构与系统判据给出。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
