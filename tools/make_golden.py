#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""生成各级黄金向量，供 RTL Testbench 与端到端回归使用。

输入只有 FASTQ 读段和水印；参考答案（codeword / source_bit / 原图）只在最后
用于交叉核对，不参与生成。

    python3 tools/make_golden.py --limit 2048 --outdir tests/golden

产出（`tests/golden/`）：
    reads.hex            每行 40 B 编码后的读段（LSB-first 打包），Stage1 激励
    watermark_sym.hex    40,500 个 2-bit 水印符号，每行一个
    wm_regions.hex       NUM_LC × REF_LEN 个符号，按区域展开，Stage1 预载用
    stage1_expect.txt    每条读段的 dir/pos/score
    stage2_expect.hex    Stage2 应输出的 81,000 bit 共识码流（64 bit/行，含分数过滤，D1 修后用）
    stage2_in.hex        Voter Testbench 激励：2n 条 Stage1 输出记录 × 6 个 64-bit 字
    stage2_rtl_expect.hex Voter 板端语义期望：全部记录投票（无分数过滤）的 81,000 bit
    sparse_expect.hex    共识 ⊕ 水印后的稀疏流（= Stage3 输入），64 bit/行
    stage3_expect.hex    Stage3 应输出的 64,800 bit 码字，64 bit/行
    dec_input.txt        交给 LDPC 的 0/1 文本
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

# Stage1 的滑窗几何（与 srpe_batch 的 parameter 一致）
NUM_LC, STRIDE, REF_LEN = 50, 807, 957


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
    ap.add_argument("--outdir", default=str(REPO / "tests" / "golden"))
    args = ap.parse_args(argv)

    out = Path(args.outdir)
    out.mkdir(parents=True, exist_ok=True)

    ref, wm_bits = rd.load_watermark(Path(args.watermark))
    L = ref.size
    R = rd.load_reads(Path(args.reads), args.limit)
    n, rb = R.shape
    thr = int(args.min_score * rb)
    print(f"参考 {L} nt   读段 {n} 条 × {rb} bp   阈值 {thr}")

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

    # ---- Stage2：投票 ----
    votes = np.zeros(2 * L, dtype=np.int32)
    used = 0
    for i, (d, p, s) in enumerate(res):
        if s < thr:
            continue
        a = R[i] if d == 0 else (R[i] ^ 1)[::-1]
        used += 1
        idx = np.arange(p, p + rb)
        np.add.at(votes, idx, ((a >> 1) & 1).astype(np.int32) * 2 - 1)
        np.add.at(votes, idx + L, (a & 1).astype(np.int32) * 2 - 1)
    consensus = (votes > 0).astype(np.uint8)
    write_hex(out / "stage2_expect.hex", pack_lsb_first(consensus), 16)
    print(f"  stage2_expect.hex    {2*L} bit，{used}/{n} 条参与投票")

    # ---- Stage2 RTL 语义向量（Voter Testbench 判据）----
    # 板端现行语义：上位机把每条读段「正向 + 反向互补」各发一份（first.py
    # orient="both"，交替顺序），Stage1 只做正向比对，Voter 的比对分目前
    # 不参与过滤（D2 未修）。因此 Voter 的输入是 2n 条记录、全部参与投票。
    # 记录格式 = Stage1 输出 48 B：bit[9:0]=score, bit[25:10]=pos,
    # bit[325:26]=codeword（位平面布局），LSB-first 装进 6 个 64-bit 字。
    rtl_records = []
    votes_rtl = np.zeros(2 * L, dtype=np.int64)
    for i, (pf, sf, pr, srr) in enumerate(both):
        for d, p, s, a in ((0, pf, sf, R[i]), (1, pr, srr, (R[i] ^ 1)[::-1])):
            planes = np.concatenate([(a >> 1) & 1, a & 1])
            v = int(s) | (int(p) << 10)
            for k in np.nonzero(planes)[0]:
                v |= 1 << (26 + int(k))
            for j in range(6):
                rtl_records.append((v >> (64 * j)) & 0xFFFF_FFFF_FFFF_FFFF)
            idx = np.arange(p, p + rb)
            np.add.at(votes_rtl, idx, ((a >> 1) & 1).astype(np.int64) * 2 - 1)
            np.add.at(votes_rtl, idx + L, (a & 1).astype(np.int64) * 2 - 1)
    # 与 RTL safe_vote_value 一致：每次 ±1 后钳位到 [-512, 511]。
    # 本数据量（约 15 票/位）远达不到钳位，这里只保证语义等价。
    votes_rtl = np.clip(votes_rtl, -512, 511)
    write_hex(out / "stage2_in.hex", rtl_records, 16)
    write_hex(out / "stage2_rtl_expect.hex",
              pack_lsb_first((votes_rtl > 0).astype(np.uint8)), 16)
    print(f"  stage2_in.hex        {2*n} 条记录 × 6 字（板端语义，不过滤分数）")
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
