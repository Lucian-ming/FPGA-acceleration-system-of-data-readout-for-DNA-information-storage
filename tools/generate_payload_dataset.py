#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""D1 多 Payload 独立数据集生成器。

依据 docs/26 §3.2 设计：
    从全新、独立的原始 Payload 开始，执行正向全流程编码：
        Source Payload (54,000 bit)
        --> DVB-S2 R=5/6 LDPC 编码 (64,800 bit)
        --> 4b -> 5b 稀疏化映射 (81,000 bit)
        --> 水印异或叠加 (81,000 bit)
        --> 双位平面合成 DNA 参考序列 (40,500 nt)
        --> 模拟测序 (In-silico Sequencing) 生成 FASTQ 读段集
    生成后立即执行逆向解码自测（Oracle 闭环检验），
    并输出规范的 manifest.json 与 SHA256SUMS。

产出目录：tests/datasets/<dataset_id>/
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import numpy as np

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "clients" / "python"))

from clients.python.native_ldpc import (
    load_pchk,
    load_permutation,
    deinterleave,
    hard_decode,
    M_ROWS,
    N_BITS,
    K_INFO,
    PARITY_COLS,
)
from tools.golden_model import DESPARSIFY_TABLE, desparsify

# 碱基与数值映射
VAL2BASE = {0: "A", 1: "T", 2: "G", 3: "C"}
BASE2VAL = {"A": 0, "T": 1, "G": 2, "C": 3, "N": 0}
RC_MAP = str.maketrans("ATGCatgc", "TACGtacg")

# 4b -> 5b 稀疏化正向码表 (由 DESPARSIFY_TABLE 1-to-1 逆向导出)
SPARSIFY_MAP = {
    val4: [(code5 >> (4 - k)) & 1 for k in range(5)]
    for code5, val4 in DESPARSIFY_TABLE.items()
}

import c_ldpc

BASES = ["A", "C", "G", "T"]
OTHER_BASES = {
    "A": ["C", "G", "T"],
    "C": ["A", "G", "T"],
    "G": ["A", "C", "T"],
    "T": ["A", "C", "G"],
    "N": ["A", "C", "G", "T"],
}


def mutate_read_sequence(
    seq: str,
    qual: str,
    sub_rate: float,
    ins_rate: float,
    del_rate: float,
    rng: np.random.Generator,
    fixed_len: bool = True,
) -> tuple[str, str, int, int, int]:
    """对单条读段注入替换 (sub)、缺失 (del)、插入 (ins) 错误，并做定长适配（docs/15 §8）。"""
    orig_len = len(seq)
    seq_chars = list(seq)
    qual_chars = list(qual)

    n_sub = 0
    n_del = 0
    n_ins = 0

    # 1. 替换 (Substitution)
    if sub_rate > 0.0:
        sub_mask = rng.random(len(seq_chars)) < sub_rate
        for idx in np.where(sub_mask)[0]:
            orig = seq_chars[idx].upper()
            candidates = OTHER_BASES.get(orig, BASES)
            seq_chars[idx] = candidates[rng.integers(0, len(candidates))]
            n_sub += 1

    # 2. 缺失 (Deletion)
    if del_rate > 0.0 and len(seq_chars) > 1:
        del_mask = rng.random(len(seq_chars)) < del_rate
        keep_indices = [i for i, d in enumerate(del_mask) if not d]
        n_del += len(seq_chars) - len(keep_indices)
        if keep_indices:
            seq_chars = [seq_chars[i] for i in keep_indices]
            qual_chars = [qual_chars[i] for i in keep_indices]

    # 3. 插入 (Insertion)
    if ins_rate > 0.0:
        ins_mask = rng.random(len(seq_chars)) < ins_rate
        new_seq = []
        new_qual = []
        for idx in range(len(seq_chars)):
            new_seq.append(seq_chars[idx])
            new_qual.append(qual_chars[idx])
            if ins_mask[idx]:
                new_seq.append(BASES[rng.integers(0, 4)])
                new_qual.append("!")
                n_ins += 1
        seq_chars = new_seq
        qual_chars = new_qual

    # 4. 定长适配 (命名：插删加定长适配 fixed_len_adaptation)
    if fixed_len:
        if len(seq_chars) > orig_len:
            seq_chars = seq_chars[:orig_len]
            qual_chars = qual_chars[:orig_len]
        elif len(seq_chars) < orig_len:
            pad_len = orig_len - len(seq_chars)
            for _ in range(pad_len):
                seq_chars.append(BASES[rng.integers(0, 4)])
                qual_chars.append("!")

    return "".join(seq_chars), "".join(qual_chars), n_sub, n_del, n_ins


def sha256_bytes(data: bytes) -> str:
    """计算字节串 SHA-256。"""
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    """计算文件 SHA-256。"""
    h = hashlib.sha256()
    with path.open("rb") as f:
        while chunk := f.read(65536):
            h.update(chunk)
    return h.hexdigest()


def bytes_to_bits(data: bytes, target_len: int = K_INFO) -> np.ndarray:
    """将字节数据转为 0/1 位数组；若不足 target_len 则右侧补 0，超长则报错。"""
    bits = np.unpackbits(np.frombuffer(data, dtype=np.uint8))
    if bits.size > target_len:
        raise ValueError(f"Payload 尺寸 {bits.size} bit 超过最大容量 {target_len} bit ({target_len//8} 字节)")
    if bits.size < target_len:
        padded = np.zeros(target_len, dtype=np.uint8)
        padded[:bits.size] = bits
        return padded
    return bits.astype(np.uint8)


def bits_to_bytes(bits: np.ndarray) -> bytes:
    """位数组转字节串（每 8 bit 一字节，高位在前）。"""
    padding = (-bits.size) % 8
    if padding:
        bits = np.concatenate([bits, np.zeros(padding, dtype=np.uint8)])
    return np.packbits(bits).tobytes()


def encode_ldpc_dvb_s2(info_bits: np.ndarray, pchk_path: Path, perm_path: Path) -> tuple[np.ndarray, np.ndarray]:
    """DVB-S2 R=5/6 LDPC 编码。
    
    返回: (natural_codeword, interleaved_codeword)
    """
    if info_bits.size != K_INFO:
        raise ValueError(f"info_bits 长度应为 {K_INFO}，实得 {info_bits.size}")
    
    rows = load_pchk(pchk_path)
    permutation = load_permutation(perm_path)

    natural = np.zeros(N_BITS, dtype=np.uint8)
    natural[PARITY_COLS:] = info_bits

    # 利用 DVB-S2 双对角 (Staircase) 特性递推校验位:
    # row 0: p_0 = sum(data_cols) mod 2
    # row i: p_i = p_{i-1} ^ (sum(data_cols) mod 2)
    p_prev = 0
    for i, row in enumerate(rows):
        data_cols = [c for c in row if c >= PARITY_COLS]
        s_i = int(np.sum(natural[data_cols])) & 1
        p_i = s_i if i == 0 else (p_prev ^ s_i)
        natural[i] = p_i
        p_prev = p_i

    # 交织为传输码字: tx = natural[permutation]
    interleaved = natural[permutation].astype(np.uint8)
    return natural, interleaved


def sparsify_4b5b(codeword: np.ndarray) -> np.ndarray:
    """64,800 bit LDPC 码字 -> 81,000 bit 稀疏流 (4b -> 5b)。"""
    if codeword.size % 4 != 0:
        raise ValueError("码字长度不是 4 的倍数")
    
    nibbles = codeword.reshape(-1, 4) @ np.array([8, 4, 2, 1], dtype=np.uint8)
    sparse_stream = np.array([SPARSIFY_MAP[v] for v in nibbles], dtype=np.uint8).reshape(-1)
    return sparse_stream


def planes_to_dna_sequence(encoded_bits: np.ndarray) -> str:
    """81,000 bit 双位平面 -> 40,500 nt DNA 序列。"""
    if encoded_bits.size != 81000:
        raise ValueError(f"编码比特流长度应为 81000，实得 {encoded_bits.size}")
    
    half = 40500
    hi = encoded_bits[:half]
    lo = encoded_bits[half:]
    symbols = (hi << 1) | lo
    return "".join(VAL2BASE[s] for s in symbols)


def reverse_complement(seq: str) -> str:
    """计算 DNA 序列反向互补。"""
    return seq.translate(RC_MAP)[::-1]


def simulate_sequencing_reads(
    ref_seq: str,
    read_len: int = 150,
    reads_count: int = 4096,
    orient: str = "both",
    seed: int = 42,
    qual_char: str = "F",
    min_coverage_tile: bool = True,
    tile_step: int = 50,
    sub_rate: float = 0.0,
    ins_rate: float = 0.0,
    del_rate: float = 0.0,
    return_stats: bool = False,
) -> Any:
    """从参考序列生成测序读段（FASTQ 4行格式），支持 D2 受控噪声注入。"""
    rng = np.random.default_rng(seed)
    ref_len = len(ref_seq)
    max_start = ref_len - read_len
    if max_start <= 0:
        raise ValueError(f"参考序列长度 {ref_len} 必须大于读长 {read_len}")

    if min_coverage_tile and reads_count >= 1000:
        # 1. 平铺保底读段（确保全长 0 盲区，消除高熵数据因泊松随机抽样导致的零覆盖空洞）
        tiled_starts = list(range(0, max_start + 1, tile_step))
        if tiled_starts[-1] != max_start:
            tiled_starts.append(max_start)
        remaining = max(0, reads_count - len(tiled_starts))
        random_starts = rng.integers(0, max_start + 1, size=remaining).tolist()
        all_starts = tiled_starts + random_starts
        # 打乱顺序以保持测序真实性
        rng.shuffle(all_starts)
        start_positions = all_starts[:reads_count]
    else:
        # 纯随机采样
        start_positions = rng.integers(0, max_start + 1, size=reads_count).tolist()

    qual = qual_char * read_len
    records = []
    tot_sub = 0
    tot_del = 0
    tot_ins = 0
    has_noise = (sub_rate > 0.0 or ins_rate > 0.0 or del_rate > 0.0)

    for i, pos in enumerate(start_positions):
        sub_seq = ref_seq[pos : pos + read_len]
        if orient == "both":
            is_rc = bool(rng.integers(0, 2))
        elif orient == "rc":
            is_rc = True
        else:
            is_rc = False

        direction = "rc" if is_rc else "fwd"
        read_seq = reverse_complement(sub_seq) if is_rc else sub_seq
        current_qual = qual

        if has_noise:
            read_seq, current_qual, n_s, n_d, n_i = mutate_read_sequence(
                read_seq, current_qual, sub_rate, ins_rate, del_rate, rng, fixed_len=True
            )
            tot_sub += n_s
            tot_del += n_d
            tot_ins += n_i

        header = f"@read_{i:06d}_pos_{pos:05d}_orient_{direction} 1:N:0:ATTACTCG+AGCGAATG"
        records.append((header, read_seq, "+", current_qual))

    if return_stats:
        total_bases = reads_count * read_len
        noise_stats = {
            "target_sub_rate": sub_rate,
            "target_ins_rate": ins_rate,
            "target_del_rate": del_rate,
            "actual_substitutions": tot_sub,
            "actual_deletions": tot_del,
            "actual_insertions": tot_ins,
            "effective_mutation_rate": round((tot_sub + tot_del + tot_ins) / max(1, total_bases), 6),
            "length_adaptation": "插删加定长适配 (fixed_len_adaptation)",
        }
        return records, noise_stats

    return records



def verify_readout_pipeline(
    ref_dna_seq: str,
    wm_bits: np.ndarray,
    read_records: list[tuple[str, str, str, str]],
    expected_cw: np.ndarray,
    pchk_path: Path,
    perm_path: Path,
    score_min: Optional[int] = None,
    read_len: int = 150,
) -> dict[str, Any]:
    """对生成的数据集读段执行全流程软件读出验证 (Stage 1~4 端到端闭环)。"""
    L = len(ref_dna_seq)
    half = L
    ref_sym = ((wm_bits[:half] << 1) | wm_bits[half:]).astype(np.uint8)

    if score_min is None:
        score_min = 67 if read_len == 150 else 112

    seqs = [r[1] for r in read_records]
    R = np.array([[BASE2VAL[c] for c in s] for s in seqs], dtype=np.uint8)

    c_lib_path = REPO_ROOT / "tools" / "libalign_fast.so"
    align_pos = []
    align_score = []
    records_arr = []

    if c_lib_path.exists():
        import ctypes
        lib = ctypes.CDLL(str(c_lib_path))
        lib.align_reads_fast.argtypes = [
            ctypes.POINTER(ctypes.c_uint8), ctypes.c_int,
            ctypes.POINTER(ctypes.c_uint8), ctypes.c_int, ctypes.c_int,
            ctypes.c_int,
            ctypes.POINTER(ctypes.c_int), ctypes.POINTER(ctypes.c_int), ctypes.POINTER(ctypes.c_int),
        ]
        lib.align_reads_fast.restype = None

        rec_fwd = R
        rec_rc = np.array([[(BASE2VAL[c] ^ 1) for c in s[::-1]] for s in seqs], dtype=np.uint8)
        ref_ptr = np.ascontiguousarray(ref_sym, dtype=np.uint8).ctypes.data_as(ctypes.POINTER(ctypes.c_uint8))

        for rec_group in [rec_fwd, rec_rc]:
            n_grp = len(rec_group)
            reads_ptr = np.ascontiguousarray(rec_group, dtype=np.uint8).ctypes.data_as(ctypes.POINTER(ctypes.c_uint8))
            out_d = np.empty(n_grp, dtype=np.int32)
            out_p = np.empty(n_grp, dtype=np.int32)
            out_s = np.empty(n_grp, dtype=np.int32)
            lib.align_reads_fast(
                ref_ptr, L, reads_ptr, n_grp, read_len, 8,
                out_d.ctypes.data_as(ctypes.POINTER(ctypes.c_int)),
                out_p.ctypes.data_as(ctypes.POINTER(ctypes.c_int)),
                out_s.ctypes.data_as(ctypes.POINTER(ctypes.c_int))
            )
            for j in range(n_grp):
                records_arr.append(rec_group[j])
                align_pos.append(out_p[j])
                align_score.append(out_s[j])
    else:
        n_pad = L + read_len
        size = 1 << (n_pad - 1).bit_length()
        spec = [np.fft.rfft((ref_sym == s).astype(np.float64), size) for s in range(4)]
        maxpos = L - read_len

        def _align_single(a: np.ndarray) -> tuple[int, int]:
            sc = np.zeros(size)
            for s in range(4):
                sc += np.fft.irfft(spec[s] * np.fft.rfft((a == s).astype(np.float64)[::-1], size), size)
            v = sc[read_len - 1 : read_len + maxpos]
            p = int(np.argmax(v))
            return p, int(round(v[p]))

        for i in range(len(seqs)):
            pf, sf = _align_single(R[i])
            pr, sr = _align_single((R[i] ^ 1)[::-1])
            records_arr.append(R[i]); align_pos.append(pf); align_score.append(sf)
            records_arr.append((R[i] ^ 1)[::-1]); align_pos.append(pr); align_score.append(sr)

    votes = np.zeros(2 * L, dtype=np.int32)
    used = 0
    for j in range(len(records_arr)):
        s = align_score[j]
        if s >= score_min:
            used += 1
            p = align_pos[j]
            a = records_arr[j]
            idx = np.arange(p, p + read_len)
            for tgt, bit in ((idx, (a >> 1) & 1), (idx + L, a & 1)):
                votes[tgt] = np.clip(votes[tgt] + (bit.astype(np.int32) * 2 - 1), -512, 511)

    consensus = (votes > 0).astype(np.uint8)
    sparse = consensus ^ wm_bits
    dec_input = desparsify(sparse)
    raw_errs = int(np.sum(dec_input != expected_cw))

    info_bits, init_syn, iters = c_ldpc.decode_bits_c(
        dec_input, pchk_path, perm_path, max_iter=50, raise_on_error=False
    )
    converged = (info_bits is not None)
    rec_sha = hashlib.sha256(np.packbits(info_bits[:54000]).tobytes()).hexdigest() if converged else "LDPC_FAILED"

    return {
        "score_min": score_min,
        "used_records": used,
        "total_records": len(records_arr),
        "raw_bit_errors": raw_errs,
        "initial_syndromes": init_syn,
        "ldpc_iterations": iters,
        "ldpc_converged": converged,
        "recovered_sha256": rec_sha,
    }


def generate_dataset(
    dataset_id: str,
    payload_data: bytes,
    payload_type: str,
    output_dir: Path,
    read_len: int = 150,
    reads_count: int = 4096,
    orient: str = "both",
    seed: int = 42,
    watermark_path: Optional[Path] = None,
    pchk_path: Optional[Path] = None,
    perm_path: Optional[Path] = None,
    tier: Optional[str] = None,
    base_dataset: Optional[str] = None,
    sub_rate: float = 0.0,
    ins_rate: float = 0.0,
    del_rate: float = 0.0,
    verify_readout: bool = True,
    score_min: Optional[int] = None,
) -> dict:
    """生成完整的数据集套件，执行闭环自证，并生成 manifest.json 与校验和。"""
    output_dir.mkdir(parents=True, exist_ok=True)

    if tier is None:
        tier = "D2" if (sub_rate > 0.0 or ins_rate > 0.0 or del_rate > 0.0) else "D1"

    if pchk_path is None:
        pchk_path = REPO_ROOT / "clients" / "python" / "resources" / "dvb_s2_r5_6.pchk"
    if perm_path is None:
        perm_path = REPO_ROOT / "clients" / "python" / "resources" / "permutation64800"
    if watermark_path is None:
        watermark_path = REPO_ROOT / "data" / "R0.83_data" / "Source data" / "Watermark sequences" / "r0.83_watermark.txt"

    print(f"=== 正在生成数据集: {dataset_id} ({tier}) ===")
    print(f"  Payload 类型: {payload_type}, 原始大小: {len(payload_data)} 字节")
    print(f"  测序参数: read_len={read_len}, reads_count={reads_count}, orient={orient}, seed={seed}")
    if tier == "D2":
        print(f"  D2 受控噪声: sub={sub_rate}, ins={ins_rate}, del={del_rate}, 基底={base_dataset}")

    # 1. 原始 Payload 处理
    raw_payload_file = output_dir / "source_payload.bin"
    raw_payload_file.write_bytes(payload_data)
    payload_sha = sha256_bytes(payload_data)

    info_bits = bytes_to_bits(payload_data, target_len=K_INFO)

    # 2. DVB-S2 LDPC 编码
    natural_cw, interleaved_cw = encode_ldpc_dvb_s2(info_bits, pchk_path, perm_path)
    codeword_str = "".join(str(b) for b in interleaved_cw)
    codeword_file = output_dir / "codeword.txt"
    codeword_file.write_text(codeword_str, encoding="utf-8")
    codeword_sha = sha256_bytes(codeword_str.encode("ascii"))

    # 3. 4b -> 5b 稀疏化
    sparse_stream = sparsify_4b5b(interleaved_cw)

    # 4. 水印加载与异或叠加
    wm_text = watermark_path.read_text(encoding="utf-8", errors="ignore")
    wm_bits = np.frombuffer(
        "".join(ch for ch in wm_text if ch in "01").encode("ascii"), dtype=np.uint8
    ) - ord("0")
    if wm_bits.size != 81000:
        raise ValueError(f"水印比特长度应为 81000，实得 {wm_bits.size}")
    # 水印已收敛到 tests/datasets/common/watermark.txt 一份（2026-09-10）：
    # 所有 D1/D2 合成数据集共用同一份，此前每个数据集各存一份逐字节相同的副本，
    # 将来改水印时漏改其中一份就是静默的数据不一致，而各数据集 SHA256SUMS
    # 各自自洽、发现不了。详见 tests/datasets/common/README.md。
    common_dir = output_dir.parent / "common"
    common_dir.mkdir(parents=True, exist_ok=True)
    watermark_file = common_dir / "watermark.txt"
    wm_norm = "".join(str(b) for b in wm_bits)
    if watermark_file.exists():
        # 已存在就必须逐字节一致，否则说明这次生成用的水印与既有数据集不同源，
        # 直接失败——静默覆盖会让已有数据集的 manifest 记录的哈希失效。
        if watermark_file.read_text(encoding="utf-8") != wm_norm:
            raise ValueError(
                f"{watermark_file} 已存在且内容不同：本次生成使用的水印与既有共享副本"
                f"不一致。若确要更换水印，须同时重生成全部数据集并刷新各自 manifest。"
            )
    else:
        watermark_file.write_text(wm_norm, encoding="utf-8")
    watermark_sha = sha256_file(watermark_file)

    encoded_bits = sparse_stream ^ wm_bits

    # 5. 双位平面合成 DNA 序列
    ref_dna_seq = planes_to_dna_sequence(encoded_bits)
    ref_seq_file = output_dir / "reference_sequence.txt"
    ref_seq_file.write_text(ref_dna_seq, encoding="utf-8")
    ref_seq_sha = sha256_file(ref_seq_file)

    # 6. 模拟测序生成 FASTQ (支持 D2 受控噪声注入)
    read_records, noise_stats = simulate_sequencing_reads(
        ref_dna_seq,
        read_len=read_len,
        reads_count=reads_count,
        orient=orient,
        seed=seed,
        sub_rate=sub_rate,
        ins_rate=ins_rate,
        del_rate=del_rate,
        return_stats=True,
    )
    fastq_file = output_dir / f"reads_se{read_len}.fastq"
    with fastq_file.open("w", encoding="utf-8") as f:
        for r in read_records:
            f.write(f"{r[0]}\n{r[1]}\n{r[2]}\n{r[3]}\n")
    reads_sha = sha256_file(fastq_file)

    # 7. 闭环自证 (Oracle Verification)
    print("  执行 Oracle 闭环验证...")
    # (a) 反稀疏化逆运算自测
    rec_cw = desparsify(sparse_stream)
    if not np.array_equal(rec_cw, interleaved_cw):
        raise RuntimeError("Oracle 失败: 反稀疏化与原码字不符！")

    # (b) LDPC 译码逆运算自测
    perm = load_permutation(perm_path)
    natural_decoded = deinterleave(interleaved_cw, perm)
    pchk_rows = load_pchk(pchk_path)
    clean_cw, syn_fail, iters = hard_decode(natural_decoded, pchk_rows, max_iter=20)
    decoded_info = clean_cw[PARITY_COLS:]
    if syn_fail != 0 or iters != 0:
        raise RuntimeError(f"Oracle 失败: 原始无错码字解出 {syn_fail} 失败校验, {iters} 轮迭代！")
    if not np.array_equal(decoded_info, info_bits):
        raise RuntimeError("Oracle 失败: 解码信息位与输入 Payload 不符！")

    recovered_bytes = bits_to_bytes(decoded_info)[:len(payload_data)]
    if recovered_bytes != payload_data:
        raise RuntimeError("Oracle 失败: 解出字节流与原始字节流不符！")
    print("  [PASS] Oracle 闭环验证 100% 逐位吻合 (0 错误，0 迭代，完全闭环)！")

    # (c) 全流程软件读出自检 (Stage 1~4 端到端闭环验证)
    readout_stats = None
    if verify_readout:
        print("  执行全流程软件读出自验 (Stage 1~4 端到端)...")
        readout_stats = verify_readout_pipeline(
            ref_dna_seq, wm_bits, read_records, interleaved_cw,
            pchk_path, perm_path, score_min=score_min, read_len=read_len,
        )
        readout_stats["matches_source"] = (readout_stats["recovered_sha256"] == payload_sha)
        print(f"  [READOUT VERIFY] 误码: {readout_stats['raw_bit_errors']}, "
              f"LDPC迭代: {readout_stats['ldpc_iterations']}, "
              f"收敛闭环: {readout_stats['ldpc_converged'] and readout_stats['matches_source']}")

    # 8. 生成 manifest.json
    now_utc = datetime.now(timezone.utc).isoformat()
    prov = {
        "tier": tier,
        "description": (
            "受控噪声注入数据集（明确基底 + 精确替换/插入/删除率控制与定长适配）"
            if tier == "D2"
            else "独立合成 Payload 数据集，完全重新全流程编码与模拟测序，杜绝数据单一性质疑"
        ),
        "generator": "tools/generate_payload_dataset.py",
    }
    if base_dataset:
        prov["base_dataset"] = base_dataset
    if tier == "D2":
        prov["noise_model"] = noise_stats

    manifest = {
        "dataset_id": dataset_id,
        "created_at_utc": now_utc,
        "provenance": prov,
        "payload": {
            "type": payload_type,
            "original_bytes": len(payload_data),
            "info_bits": K_INFO,
            "sha256": payload_sha,
            "source_file": raw_payload_file.name,
        },
        "ldpc": {
            "standard": "DVB-S2",
            "rate": "5/6",
            "n_bits": N_BITS,
            "k_info": K_INFO,
            "codeword_sha256": codeword_sha,
            "codeword_file": codeword_file.name,
        },
        "watermark": {
            "length_bits": 81000,
            "sha256": watermark_sha,
            "watermark_file": watermark_file.name,
        },
        "reference_dna": {
            "length_nt": len(ref_dna_seq),
            "sha256": ref_seq_sha,
            "reference_file": ref_seq_file.name,
        },
        "sequencing": {
            "read_len": read_len,
            "reads_count": reads_count,
            "orient": orient,
            "seed": seed,
            "fastq_file": fastq_file.name,
            "fastq_sha256": reads_sha,
        },
        "oracle_verified": True,
    }
    if readout_stats is not None:
        manifest["readout_verification"] = readout_stats

    manifest_file = output_dir / "manifest.json"
    manifest_file.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    # 9. 生成 SHA256SUMS
    sha_lines = []
    for p in sorted(output_dir.iterdir()):
        if p.is_file() and p.name != "SHA256SUMS":
            sha_lines.append(f"{sha256_file(p)}  {p.name}")
    (output_dir / "SHA256SUMS").write_text("\n".join(sha_lines) + "\n", encoding="utf-8")

    print(f"  [PASS] 数据集生成完毕并归档至: {output_dir}")
    return manifest


def make_standard_suite(base_dir: Path, reads_count: int = 4096):
    """生成 docs/26 §3.2 指定的首批 4 套代表性 Payload 数据集。"""
    print("\n=======================================================")
    print(" 启动生成首批 4 套全新独立 D1 Payload 数据集")
    print("=======================================================")

    # 数据集 1: 高低熵文本（宣誓/说明文本，6000 字节 UTF-8 文本）
    text_content = (
        "FPGA Acceleration System of Data Readout for DNA Information Storage.\n"
        "Autonomous track design for AMD Open Hardware Competition 2026.\n"
        "Key Innovations:\n"
        "1. Real-time sequence alignment and de-watermarking on FPGA logic.\n"
        "2. Multi-position sliding window pipeline with massive bit-plane parallelism.\n"
        "3. High-throughput differential voter and 5b4b desparsification architecture.\n"
        "4. Energy efficiency exceeding multi-core CPU by 18x.\n"
    )
    # 重复扩充至约 5,000 字节
    text_payload = (text_content * 15)[:5000].encode("utf-8")
    generate_dataset(
        dataset_id="D1_text_manifesto",
        payload_data=text_payload,
        payload_type="text",
        output_dir=base_dir / "D1_text_manifesto",
        reads_count=reads_count,
        seed=101,
    )

    # 数据集 2: 高熵伪随机数（密码学高熵测试，6,750 字节满载）
    rng = np.random.default_rng(20260905)
    random_payload = rng.bytes(6750)
    generate_dataset(
        dataset_id="D1_random_entropy",
        payload_data=random_payload,
        payload_type="random",
        output_dir=base_dir / "D1_random_entropy",
        reads_count=reads_count,
        seed=202,
    )

    # 数据集 3: 二进制图形/图标数据（合成 64x64 单色位图/图标，约 4,096 字节）
    img_data = bytearray(4096)
    for i in range(64):
        for j in range(64):
            # 同心圆图案
            r = int(np.hypot(i - 32, j - 32))
            if (r % 8) < 4:
                img_data[(i * 64 + j) // 8] |= (1 << (7 - ((i * 64 + j) % 8)))
    generate_dataset(
        dataset_id="D1_binary_pattern",
        payload_data=bytes(img_data),
        payload_type="binary_pattern",
        output_dir=base_dir / "D1_binary_pattern",
        reads_count=reads_count,
        seed=303,
    )

    # 数据集 4: 稀疏极低熵边界数据（结构化稀疏序列，测试全链路极端边界与最小跳变）
    sparse_payload = bytearray(6750)
    for k in range(0, 6750, 64):
        sparse_payload[k] = 0xAA if (k % 128 == 0) else 0x55
    generate_dataset(
        dataset_id="D1_structured_sparse",
        payload_data=bytes(sparse_payload),
        payload_type="structured_sparse",
        output_dir=base_dir / "D1_structured_sparse",
        reads_count=reads_count,
        seed=404,
    )

    print("\n=======================================================")
    print(" 首批 4 套全新独立 D1 Payload 数据集全部成功生成并验证闭环！")
    print("=======================================================\n")


def main():
    parser = argparse.ArgumentParser(description="D1 多 Payload 独立数据集生成器")
    parser.add_argument("--suite", action="store_true", help="生成标准 4 套评估数据集")
    parser.add_argument("--dataset-id", type=str, default="D1_custom", help="自定义数据集 ID")
    parser.add_argument("--payload-file", type=Path, help="自定义源 Payload 文件路径")
    parser.add_argument("--payload-type", type=str, default="custom", help="Payload 类型描述")
    parser.add_argument("--output-dir", type=Path, help="输出目录 (默认 tests/datasets/<dataset_id>)")
    parser.add_argument("--read-len", type=int, default=150, choices=[150, 250], help="测序读长 (bp)")
    parser.add_argument("--reads-count", type=int, default=4096, help="生成测序读段数")
    parser.add_argument("--orient", type=str, default="both", choices=["both", "fwd", "rc"], help="读段方向")
    parser.add_argument("--seed", type=int, default=42, help="随机数种子")
    parser.add_argument("--tier", type=str, choices=["D1", "D2"], default=None, help="数据集层级 (D1/D2)")
    parser.add_argument("--base-dataset", type=str, default=None, help="D2 衍生基底数据集 ID")
    parser.add_argument("--sub-rate", type=float, default=0.0, help="替换错误率 (Substitution)")
    parser.add_argument("--ins-rate", type=float, default=0.0, help="插入错误率 (Insertion)")
    parser.add_argument("--del-rate", type=float, default=0.0, help="缺失错误率 (Deletion)")
    parser.add_argument("--score-min", type=int, default=None, help="读出验证的比对门限")
    parser.add_argument("--no-readout-verify", action="store_true", help="跳过读出验证")

    args = parser.parse_args()

    base_dir = REPO_ROOT / "tests" / "datasets"
    if args.suite:
        make_standard_suite(base_dir, reads_count=args.reads_count)
        return

    if not args.payload_file:
        if args.payload_type == "random":
            rng = np.random.default_rng(args.seed)
            payload_data = rng.bytes(6750)
        else:
            print("错误: 必须指定 --suite 生成全套数据集，或提供 --payload-file 指定自定义数据（或 --payload-type random）", file=sys.stderr)
            parser.print_help()
            sys.exit(1)
    else:
        payload_data = args.payload_file.read_bytes()

    out_dir = args.output_dir or (base_dir / args.dataset_id)
    generate_dataset(
        dataset_id=args.dataset_id,
        payload_data=payload_data,
        payload_type=args.payload_type,
        output_dir=out_dir,
        read_len=args.read_len,
        reads_count=args.reads_count,
        orient=args.orient,
        seed=args.seed,
        tier=args.tier,
        base_dataset=args.base_dataset,
        sub_rate=args.sub_rate,
        ins_rate=args.ins_rate,
        del_rate=args.del_rate,
        verify_readout=(not args.no_readout_verify),
        score_min=args.score_min,
    )


if __name__ == "__main__":
    main()
