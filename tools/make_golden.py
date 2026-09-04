#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""生成各级黄金向量，供 RTL Testbench 与端到端回归使用。

输入只有 FASTQ 读段和水印；参考答案（codeword / source_bit / 原图）只在最后
用于交叉核对，不参与生成。

    # SE150（默认，产出与已冻结的 tests/golden/ 逐字节相同）
    python3 tools/make_golden.py --limit 2048 --outdir tests/golden
    # SE250（几何由 --reads 的读段长度自动反解，务必带 --manifest）
    python3 tools/make_golden.py --limit 2048 --manifest \
        --reads "data/R0.83_data/Sequencing data/DNA-40.5Kb-MC-SE250.fastq" \
        --outdir tests/golden/se250

几何不再写死：STRIDE / REF_LEN 由 `L`、读段长度和 `--num-lc` 按数据契约反解
（见 `derive_geometry()`）。SE150 → 807/957，SE250 → 805/1055。

产出（`tests/golden/`）：
    reads.hex            每行 ceil(2*READ_BPS/8) B 编码后的读段（LSB-first 打包），Stage1 激励
    watermark_sym.hex    40,500 个 2-bit 水印符号，每行一个
    wm_regions.hex       NUM_LC × REF_LEN 个符号，按区域展开，Stage1 预载用
    stage1_expect.txt    每条读段的 dir/pos/score
    stage2_expect.hex    Stage2 应输出的 81,000 bit 共识（64 bit/行，方案B：逐记录过阈值）
    stage2_in.hex        Voter Testbench 激励：2n 条 Stage1 输出记录 × ceil(RESULT_W/64) 个 64-bit 字
    stage2_rtl_expect.hex Voter 板端语义期望：全部记录投票（无分数过滤）的 81,000 bit
    sparse_expect.hex    共识 ⊕ 水印后的稀疏流（= Stage3 输入），64 bit/行
    stage3_expect.hex    Stage3 应输出的 64,800 bit 码字，64 bit/行
    dec_input.txt        交给 LDPC 的 0/1 文本
    GEOMETRY.txt         本批向量用的几何/数据集/阈值（仅 --manifest 时写出）
    SHA256SUMS           全部产物的校验和
"""

from __future__ import annotations

import argparse
import hashlib
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import readout as rd  # noqa: E402

REPO = Path(__file__).resolve().parent.parent
DATA = REPO / "data" / "R0.83_data"
DEF_READS = DATA / "Sequencing data" / "DNA-40.5Kb-MC-SE150.fastq"
DEF_WM = DATA / "Source data" / "Watermark sequences" / "r0.83_watermark.txt"
DEF_CODEWORD = DATA / "Source data" / "Encoded_codeword" / "codeword_R083.txt"

# Stage1 的滑窗几何：只有 NUM_LC 是自由参数，另外两个由数据契约反解。
# srpe_batch.v:51 的 REGION_W=6 与 :34 的 bram_sel[5:0] 限死 NUM_LC <= 64。
DEF_NUM_LC = 50

# 已冻结的 SE150 基线：wm_regions.hex 的 SHA-256。用来识别 docs/20 §3.7 G1 那个坑。
SE150_WM_REGIONS_SHA = \
    "f352853912338cd0e0a1787445a341a0a74897948c048328903b2723bbdf7f5e"


def derive_geometry(L: int, read_bps: int, num_lc: int) -> tuple:
    """由数据契约的两条约束反解滑窗几何，不写死任何一档的数字。

        (C1) NUM_LC * STRIDE = L - READ_BPS
        (C2) REF_LEN         = STRIDE + READ_BPS

    SE150（L=40500, rb=150, num_lc=50）→ STRIDE=807, REF_LEN=957；
    SE250（L=40500, rb=250, num_lc=50）→ STRIDE=805, REF_LEN=1055。

    这两行以前是写死的 `NUM_LC, STRIDE, REF_LEN = 50, 807, 957`。换数据集时脚本
    **不会报错**，只会静默按 SE150 的几何展开水印区域，`wm_regions.hex` 于是和
    SE150 一模一样（SHA-256 f352853912338cd0…）——docs/20 §3.7 G1 记录了这个坑。
    """
    if not 1 <= num_lc <= 64:
        raise SystemExit(f"NUM_LC={num_lc} 必须在 1..64（srpe_batch.v:51 REGION_W=6）")
    span = L - read_bps
    if span <= 0 or span % num_lc:
        raise SystemExit(
            f"几何不成立：L={L}, READ_BPS={read_bps}, NUM_LC={num_lc}；"
            f"(L-READ_BPS)={span} 不是 NUM_LC 的整数倍，"
            f"违反 NUM_LC*STRIDE = L-READ_BPS"
        )
    stride = span // num_lc
    return stride, stride + read_bps


def pack_lsb_first(bits: np.ndarray, width: int = 64) -> list:
    """码流按 LSB-first 装进定宽字：第 k 位码流 → 第 k/width 个字的第 k%width 位。"""
    pad = (-bits.size) % width
    b = np.concatenate([bits, np.zeros(pad, dtype=np.uint8)])
    w = b.reshape(-1, width)
    weights = (1 << np.arange(width, dtype=object))
    return [int((w[i].astype(object) * weights).sum()) for i in range(w.shape[0])]


def write_hex(path: Path, words, digits: int):
    path.write_text("\n".join(f"{v:0{digits}x}" for v in words) + "\n", encoding="utf-8")


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--reads", default=str(DEF_READS))
    ap.add_argument("--watermark", default=str(DEF_WM))
    ap.add_argument("--codeword", default=str(DEF_CODEWORD), help="仅用于交叉核对")
    ap.add_argument("--limit", type=int, default=2048)
    ap.add_argument("--min-score", type=float, default=0.45)
    ap.add_argument("--jobs", type=int, default=8)
    ap.add_argument("--num-lc", type=int, default=DEF_NUM_LC,
                    help=f"水印区域数（默认 {DEF_NUM_LC}，受 REGION_W=6 限制 <= 64）；"
                         "STRIDE 与 REF_LEN 由它和读段长度反解")
    ap.add_argument("--manifest", action="store_true",
                    help="额外写出 GEOMETRY.txt 记录本批向量的几何/数据集/阈值。"
                         "默认关闭，好让不带参数的调用逐字节复现已冻结的 SE150"
                         "tests/golden/SHA256SUMS；新建向量目录（如 se250）一律要加")
    ap.add_argument("--outdir", default=str(REPO / "tests" / "golden"))
    args = ap.parse_args(argv)

    out = Path(args.outdir)
    out.mkdir(parents=True, exist_ok=True)

    ref, wm_bits = rd.load_watermark(Path(args.watermark))
    L = ref.size
    R = rd.load_reads(Path(args.reads), args.limit)
    n, rb = R.shape
    thr = int(args.min_score * rb)
    NUM_LC = args.num_lc
    STRIDE, REF_LEN = derive_geometry(L, rb, NUM_LC)
    # 一条 Stage1 记录：score(10) + pos(16) + 码字(2*rb)，LSB-first 装进 64 bit 字。
    # 与 srpe_batch.v:47-48 的 CODEBITS / RESULT_W 同源。
    result_w = 2 * rb + 26
    words_per_read = (result_w + 63) // 64
    print(f"参考 {L} nt   读段 {n} 条 × {rb} bp   阈值 {thr}")
    print(f"几何 NUM_LC={NUM_LC} STRIDE={STRIDE} REF_LEN={REF_LEN}   "
          f"CODEBITS={2*rb} RESULT_W={result_w} 每记录 {words_per_read} 个 64 bit 字")

    # ---- 读段编码：位平面 + 字节内 LSB-first ----
    per_read_bytes = (2 * rb + 7) // 8
    lines = []
    for i in range(n):
        planes = np.concatenate([(R[i] >> 1) & 1, R[i] & 1])
        words = pack_lsb_first(planes, 8)
        lines.append("".join(f"{v:02x}" for v in words))
    (out / "reads.hex").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"  reads.hex            {n} 行 × {per_read_bytes} B")

    # ---- 水印符号与区域展开 ----
    write_hex(out / "watermark_sym.hex", ref.tolist(), 1)
    regions = []
    for lc in range(NUM_LC):
        base = lc * STRIDE
        for row in range(REF_LEN):
            idx = base + row
            regions.append(int(ref[idx]) if idx < L else 0)
    write_hex(out / "wm_regions.hex", regions, 1)
    # 上位机实际会发送的打包水印（码流顺序 + 字节内 LSB-first），
    # 供 tools/test_wm_expand.c 单元测试 PS 侧的展开逻辑
    (out / "watermark_packed.bin").write_bytes(
        bytes(pack_lsb_first(wm_bits, 8)))
    print(f"  wm_regions.hex       {NUM_LC}×{REF_LEN} = {len(regions)} 个符号")

    # docs/20 §3.7 G1 的哨兵。旧代码把几何写死成 50/807/957，换数据集时**不报错**，
    # 只是静默按 SE150 展开水印区域。故障注入实测（本文件的参数化提交）表明：
    # 那个缺陷下 15 个产物里有 14 个逐字节相同，dec_input 照样译出 fcd0cf90…f2c3、
    # 码字误码照样是 36/64,800 —— 只有 wm_regions.hex 变。所以这条哨兵是唯一
    # 抓得住它的判据，放在这里尽早失败，不要先摊一地错产物。
    if rb != 150 and hashlib.sha256(
            (out / "wm_regions.hex").read_bytes()).hexdigest() == SE150_WM_REGIONS_SHA:
        raise SystemExit(
            f"wm_regions.hex 撞上 SE150 的 {SE150_WM_REGIONS_SHA[:16]}…，"
            f"但读段是 {rb} bp —— 几何没生效，产物不可用（docs/20 §3.7 G1）")

    # ---- Stage1：正反两个方向都算，RTL 判据用正向，投票用胜者 ----
    if args.jobs > 1:
        import multiprocessing as mp
        with mp.Pool(args.jobs, initializer=rd._init_worker, initargs=(ref, rb)) as pool:
            both = pool.map(rd._align_both, list(R), chunksize=8)
    else:
        rd._init_worker(ref, rb)
        both = [rd._align_both(R[i]) for i in range(n)]
    res = [(0, pf, sf) if sf >= sr else (1, prr, sr) for (pf, sf, prr, sr) in both]

    (out / "stage1_expect.txt").write_text(
        "# idx dir pos score   （dir=0 正向 / 1 反向互补，取分高者）\n" + "\n".join(
            f"{i} {d} {p} {s}" for i, (d, p, s) in enumerate(res)) + "\n", encoding="utf-8")
    # RTL 的 srpe_batch 只做正向，故单列一份正向期望作为 Testbench 判据
    (out / "stage1_fwd_expect.txt").write_text(
        "# idx pos score   （仅正向，srpe_batch 的判据）\n" + "\n".join(
            f"{i} {pf} {sf}" for i, (pf, sf, _, _) in enumerate(both)) + "\n", encoding="utf-8")
    print(f"  stage1_expect.txt    {n} 条，平均分 {np.mean([r[2] for r in res]):.1f}/{rb}")
    print(f"  stage1_fwd_expect.txt {n} 条正向，平均分 {np.mean([b[1] for b in both]):.1f}/{rb}")

    # 每条读段的 300-bit 码字（位平面布局，bit k 即码流第 k 位），供 srpe_batch TB
    cw_lines = []
    for i in range(n):
        planes = np.concatenate([(R[i] >> 1) & 1, R[i] & 1])
        v = 0
        for k in range(planes.size):
            if planes[k]:
                v |= (1 << k)
        cw_lines.append(f"{v:0{(2*rb+3)//4}x}")
    (out / "reads_cw.hex").write_text("\n".join(cw_lines) + "\n", encoding="utf-8")
    print(f"  reads_cw.hex         {n} 行 × {2*rb} bit")

    # ---- Stage2：投票（方案 B，与板端 RTL 的 SCORE_MIN 语义一致）----
    # 板端（D1 方案 B）：上位机把每条读段正向、反向互补各发一份，Voter 对
    # 每条记录【独立】按分数过滤（score >= thr 才投票）。与
    # `golden_model.py simulate --rc` 的「每对择优一条」语义仅在双方向都
    # 过阈的读段上不同（本数据集 2,048 条中有 10 条）；两种语义的码字误码
    # 相当（88 与 86 / 64,800），都远低于 LDPC 硬判决可解边界。
    votes = np.zeros(2 * L, dtype=np.int32)
    used = 0
    for i, (pf, sf, pr, sr_) in enumerate(both):
        for p, s, a in ((pf, sf, R[i]), (pr, sr_, (R[i] ^ 1)[::-1])):
            if s < thr:
                continue
            used += 1
            # 同下面 votes_rtl：按 RTL safe_vote_value 逐票钳位。这一份是
            # tb_vot_ddr_bitexact 在「固件时序 + SCORE_MIN」档的期望输出
            # （stage2_expect.hex），也是 sparse/stage3/dec_input 整条下游的源头，
            # 所以它同样必须是 RTL 语义而不是理想无限精度累加。
            # 实测（tools/vote_range.py）：SE150 全量 score_min=67 峰值 277，
            # 碰不到钳位；但 SE250 全量 score_min=112 峰值达 517，钳位会生效
            # 41 次——那时这一份若还用自由累加就不再是 RTL 期望。
            idx = np.arange(p, p + rb)
            for tgt, bit in ((idx, (a >> 1) & 1), (idx + L, a & 1)):
                votes[tgt] = np.clip(
                    votes[tgt] + (bit.astype(np.int32) * 2 - 1), -512, 511)
    consensus = (votes > 0).astype(np.uint8)
    write_hex(out / "stage2_expect.hex", pack_lsb_first(consensus), 16)
    print(f"  stage2_expect.hex    {2*L} bit（方案B：逐记录过阈值），{used}/{2*n} 条记录参与投票")

    # ---- Stage2 RTL 语义向量（Voter Testbench 判据）----
    # 板端现行语义：上位机把每条读段「正向 + 反向互补」各发一份（first.py
    # orient="both"，交替顺序），Stage1 只做正向比对，Voter 的比对分目前
    # 不参与过滤（D2 未修）。因此 Voter 的输入是 2n 条记录、全部参与投票。
    # 记录格式 = Stage1 输出 words_per_read*8 B（SE150 48 B / SE250 72 B）：
    # bit[9:0]=score, bit[25:10]=pos, bit[RESULT_W-1:26]=codeword（位平面布局），
    # LSB-first 装进 words_per_read 个 64-bit 字。字数写死成 6 的话，SE250 的
    # 526 bit 记录会被静默截断成 384 bit。
    rtl_records = []
    votes_rtl = np.zeros(2 * L, dtype=np.int64)
    for i, (pf, sf, pr, srr) in enumerate(both):
        for d, p, s, a in ((0, pf, sf, R[i]), (1, pr, srr, (R[i] ^ 1)[::-1])):
            planes = np.concatenate([(a >> 1) & 1, a & 1])
            v = int(s) | (int(p) << 10)
            for k in np.nonzero(planes)[0]:
                v |= 1 << (26 + int(k))
            for j in range(words_per_read):
                rtl_records.append((v >> (64 * j)) & 0xFFFF_FFFF_FFFF_FFFF)
            # 与 RTL safe_vote_value（differential_voter_v1_0.v:319-326）一致：
            # **每收一票就钳位**，不是最后钳一次。一条记录内 idx 各不相同
            # （p..p+rb-1 互异，两个平面又分处 idx 与 idx+L），所以这里向量化的
            # 一次更新与逐票更新严格等价。
            #
            # 原实现是全程自由累加、最后 np.clip 一次，注释却写「每次 ±1 后钳位」。
            # 两者只在**从不饱和**时才等价：自由累加到 +600 再回落 200 得 400，
            # 逐票饱和是 511 再回落 200 得 311。tools/vote_range.py 实测：
            # 2,048 条那档峰值仅 28/50，确实碰不到钳位（所以既有向量不受影响）；
            # 但全量 SE250（400×/位）运行中峰值达 ±517，钳位真的会生效。
            # 也就是说旧写法的正确性是**依赖规模的巧合**，不是构造上的等价。
            idx = np.arange(p, p + rb)
            for tgt, bit in ((idx, (a >> 1) & 1), (idx + L, a & 1)):
                votes_rtl[tgt] = np.clip(
                    votes_rtl[tgt] + (bit.astype(np.int64) * 2 - 1), -512, 511)
    write_hex(out / "stage2_in.hex", rtl_records, 16)
    write_hex(out / "stage2_rtl_expect.hex",
              pack_lsb_first((votes_rtl > 0).astype(np.uint8)), 16)
    print(f"  stage2_in.hex        {2*n} 条记录 × {words_per_read} 字"
          f"（板端语义，不过滤分数）")
    print(f"  stage2_rtl_expect.hex {2*L} bit，全部记录参与投票")

    # ---- 差分 + Stage3 ----
    sparse = consensus ^ wm_bits
    write_hex(out / "sparse_expect.hex", pack_lsb_first(sparse), 16)
    codeword = rd.desparsify(sparse)
    write_hex(out / "stage3_expect.hex", pack_lsb_first(codeword), 16)
    (out / "dec_input.txt").write_text("".join("01"[b] for b in codeword), encoding="utf-8")
    print(f"  stage3_expect.hex    {codeword.size} bit = {codeword.size//8} B")

    # ---- 交叉核对（只读参考答案，不参与生成）----
    ref_cw = np.frombuffer(
        "".join(c for c in Path(args.codeword).read_text() if c in "01").encode(),
        dtype=np.uint8) - ord("0")
    err = int((codeword != ref_cw).sum())
    print(f"\n交叉核对：与 codeword_R083.txt 相差 {err}/{ref_cw.size} bit "
          f"({err/ref_cw.size:.5f})")

    # ---- 纯函数向量：直接用真值稀疏流，Stage3 的输出必须逐位等于参考码字 ----
    # 这一组不含任何读段噪声，是 Stage3 最干净的判据。
    seq_bits = None
    seq_path = DATA / "Source data" / "Encoded_sequences" / "DNA-40.5Kb-MC (R=0.83).txt"
    if seq_path.exists():
        txt = "".join(c for c in seq_path.read_text() if c in "ACGT")
        sym = np.array([rd.BASE2VAL[c] for c in txt], dtype=np.uint8)
        seq_bits = np.concatenate([(sym >> 1) & 1, sym & 1])
        true_sparse = seq_bits ^ wm_bits
        write_hex(out / "sparse_ideal.hex", pack_lsb_first(true_sparse), 16)
        write_hex(out / "stage3_ideal_expect.hex", pack_lsb_first(ref_cw), 16)
        assert (rd.desparsify(true_sparse) == ref_cw).all(), "理想向量自检失败"
        print("  sparse_ideal.hex / stage3_ideal_expect.hex  （无噪声纯函数向量，自检通过）")

    # ---- 几何清单 ----
    # SE150 与 SE250 最终产出【同一个】图片 SHA-256 fcd0cf90…f2c3（docs/20 §2 实跑
    # 证明），所以哈希本身分不出这批向量用的是哪套几何。判据必须连同「哪套几何、
    # 哪份数据、哪个阈值」一起记录，否则会拿一个通过的哈希去证明它证不了的事。
    if args.manifest:
        def rel(path):
            path = Path(path).resolve()
            try:
                return str(path.relative_to(REPO))
            except ValueError:
                return str(path)

        def digest(path):
            h = hashlib.sha256()
            with open(path, "rb") as fh:
                for chunk in iter(lambda: fh.read(1 << 20), b""):
                    h.update(chunk)
            return h.hexdigest()

        (out / "GEOMETRY.txt").write_text(
            "# 本批黄金向量的几何与来源（tools/make_golden.py --manifest 生成）\n"
            "#\n"
            "# 为什么需要这份文件：SE150 与 SE250 产出同一个图片 SHA-256\n"
            "# fcd0cf90…f2c3（docs/20 §2），哈希分不出用的是哪套几何。引用本目录的\n"
            "# 任何判据时，必须连同下面这些字段一起记录。\n"
            "# 内容只由输入决定（不含时间戳），重跑同一条命令应逐字节相同。\n"
            "\n"
            f"read_bps        = {rb}\n"
            f"num_lc          = {NUM_LC}\n"
            f"stride          = {STRIDE}\n"
            f"ref_len         = {REF_LEN}\n"
            f"L               = {L}\n"
            f"codebits        = {2 * rb}\n"
            f"result_w        = {result_w}\n"
            f"words_per_read  = {words_per_read}\n"
            f"record_bytes    = {words_per_read * 8}\n"
            f"read_wire_bytes = {((2 * rb + 31) // 32) * 4}\n"
            f"per_read_bytes  = {per_read_bytes}\n"
            f"wm_regions_rows = {NUM_LC * REF_LEN}\n"
            "\n"
            f"source_reads    = {n}\n"
            f"records         = {2 * n}\n"
            f"min_score_ratio = {args.min_score}\n"
            f"score_min       = {thr}\n"
            f"voted_records   = {used}/{2 * n}\n"
            f"codeword_err    = {err}/{ref_cw.size}\n"
            "\n"
            f"reads_file      = {rel(args.reads)}\n"
            f"reads_sha256    = {digest(args.reads)}\n"
            f"watermark_file  = {rel(args.watermark)}\n"
            f"watermark_sha256= {digest(args.watermark)}\n"
            f"codeword_file   = {rel(args.codeword)}\n"
            f"codeword_sha256 = {digest(args.codeword)}\n",
            encoding="utf-8")
        print(f"  GEOMETRY.txt         几何/数据集/阈值清单")
    elif rb != 150:
        print(f"\n⚠️  读段是 {rb} bp 却没加 --manifest：这批向量没有留下几何记录，"
              f"\n    而 SE150/SE250 的图片哈希相同、分不出来。新建向量目录请加 --manifest。")

    # ---- 校验和 ----
    sums = []
    for f in sorted(out.iterdir()):
        if f.name == "SHA256SUMS" or f.is_dir():
            continue
        sums.append(f"{hashlib.sha256(f.read_bytes()).hexdigest()}  {f.name}")
    (out / "SHA256SUMS").write_text("\n".join(sums) + "\n", encoding="utf-8")
    print(f"\n已写出 {len(sums)} 个文件到 {out}，校验和见 SHA256SUMS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
