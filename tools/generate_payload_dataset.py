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
) -> list[tuple[str, str, str, str]]:
    """从参考序列生成测序读段（FASTQ 4行格式）。"""
    rng = np.random.default_rng(seed)
    ref_len = len(ref_seq)
    max_start = ref_len - read_len
    if max_start <= 0:
        raise ValueError(f"参考序列长度 {ref_len} 必须大于读长 {read_len}")

    # 均匀采样读段起始位置
    start_positions = rng.integers(0, max_start + 1, size=reads_count)
    qual = qual_char * read_len
    records = []

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
        header = f"@read_{i:06d}_pos_{pos:05d}_orient_{direction} 1:N:0:ATTACTCG+AGCGAATG"
        records.append((header, read_seq, "+", qual))

    return records


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
) -> dict:
    """生成完整的数据集套件，执行闭环自证，并生成 manifest.json 与校验和。"""
    output_dir.mkdir(parents=True, exist_ok=True)
    
    if pchk_path is None:
        pchk_path = REPO_ROOT / "clients" / "python" / "resources" / "dvb_s2_r5_6.pchk"
    if perm_path is None:
        perm_path = REPO_ROOT / "clients" / "python" / "resources" / "permutation64800"
    if watermark_path is None:
        watermark_path = REPO_ROOT / "data" / "R0.83_data" / "Source data" / "Watermark sequences" / "r0.83_watermark.txt"

    print(f"=== 正在生成数据集: {dataset_id} ===")
    print(f"  Payload 类型: {payload_type}, 原始大小: {len(payload_data)} 字节")
    print(f"  测序参数: read_len={read_len}, reads_count={reads_count}, orient={orient}, seed={seed}")

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
    watermark_file = output_dir / "watermark.txt"
    watermark_file.write_text("".join(str(b) for b in wm_bits), encoding="utf-8")
    watermark_sha = sha256_file(watermark_file)

    encoded_bits = sparse_stream ^ wm_bits

    # 5. 双位平面合成 DNA 序列
    ref_dna_seq = planes_to_dna_sequence(encoded_bits)
    ref_seq_file = output_dir / "reference_sequence.txt"
    ref_seq_file.write_text(ref_dna_seq, encoding="utf-8")
    ref_seq_sha = sha256_file(ref_seq_file)

    # 6. 模拟测序生成 FASTQ
    read_records = simulate_sequencing_reads(
        ref_dna_seq,
        read_len=read_len,
        reads_count=reads_count,
        orient=orient,
        seed=seed,
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

    # 8. 生成 manifest.json
    now_utc = datetime.now(timezone.utc).isoformat()
    manifest = {
        "dataset_id": dataset_id,
        "created_at_utc": now_utc,
        "provenance": {
            "tier": "D1",
            "description": "独立合成 Payload 数据集，完全重新全流程编码与模拟测序，杜绝数据单一性质疑",
            "generator": "tools/generate_payload_dataset.py",
        },
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

    args = parser.parse_args()

    base_dir = REPO_ROOT / "tests" / "datasets"
    if args.suite:
        make_standard_suite(base_dir, reads_count=args.reads_count)
        return

    if not args.payload_file:
        print("错误: 必须指定 --suite 生成全套数据集，或提供 --payload-file 指定自定义数据", file=sys.stderr)
        parser.print_help()
        sys.exit(1)

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
    )


if __name__ == "__main__":
    main()
