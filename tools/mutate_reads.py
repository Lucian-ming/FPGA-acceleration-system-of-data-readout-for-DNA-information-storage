#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""D2 受控测序错误注入工具。

依据 docs/26 §3.3 设计：
    以标准 FASTQ 文件及对应的 manifest 为输入，在保留随机可复现性的前提下，
    注入受控的替换 (substitution)、插入 (insertion)、缺失 (deletion) 与覆盖度抽样扰动。
    输出独立新目录，严禁覆盖或污染原数据文件。

典型应用：
    1. 评估 Stage1 容错窗口与门限曲线 (score_min vs sub_rate)；
    2. 评估 LDPC 纠错极限与信噪比门限 (BER vs SNR)；
    3. 构建多维鲁棒性压力测试矩阵。
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

BASES = np.array(["A", "C", "G", "T"])
OTHER_BASES = {
    "A": ["C", "G", "T"],
    "C": ["A", "G", "T"],
    "G": ["A", "C", "T"],
    "T": ["A", "C", "G"],
    "N": ["A", "C", "G", "T"],
}


def sha256_file(path: Path) -> str:
    """计算文件 SHA-256。"""
    h = hashlib.sha256()
    with path.open("rb") as f:
        while chunk := f.read(65536):
            h.update(chunk)
    return h.hexdigest()


def parse_fastq(path: Path):
    """逐条读取 FASTQ 文件，生成 (header, seq, plus, qual)。"""
    with path.open("r", encoding="utf-8", errors="ignore") as f:
        while True:
            header = f.readline()
            if not header:
                break
            seq = f.readline()
            plus = f.readline()
            qual = f.readline()
            if not seq or not plus or not qual:
                break
            yield header.rstrip("\r\n"), seq.rstrip("\r\n"), plus.rstrip("\r\n"), qual.rstrip("\r\n")


def mutate_sequence(
    seq: str,
    qual: str,
    sub_rate: float,
    ins_rate: float,
    del_rate: float,
    rng: np.random.Generator,
    fixed_len: bool = True,
) -> tuple[str, str, int, int, int]:
    """对单条读段注入 substitution, insertion, deletion 错误。"""
    orig_len = len(seq)
    seq_chars = list(seq)
    qual_chars = list(qual)
    
    n_sub = 0
    n_ins = 0
    n_del = 0

    # 1. Substitution (替换)
    if sub_rate > 0.0:
        sub_mask = rng.random(len(seq_chars)) < sub_rate
        for idx in np.where(sub_mask)[0]:
            orig = seq_chars[idx].upper()
            candidates = OTHER_BASES.get(orig, ["A", "C", "G", "T"])
            seq_chars[idx] = candidates[rng.integers(0, len(candidates))]
            n_sub += 1

    # 2. Deletion (缺失)
    if del_rate > 0.0 and len(seq_chars) > 1:
        del_mask = rng.random(len(seq_chars)) < del_rate
        keep_indices = [i for i, d in enumerate(del_mask) if not d]
        n_del += len(seq_chars) - len(keep_indices)
        if keep_indices:
            seq_chars = [seq_chars[i] for i in keep_indices]
            qual_chars = [qual_chars[i] for i in keep_indices]

    # 3. Insertion (插入)
    if ins_rate > 0.0:
        ins_mask = rng.random(len(seq_chars)) < ins_rate
        new_seq = []
        new_qual = []
        for idx in range(len(seq_chars)):
            new_seq.append(seq_chars[idx])
            new_qual.append(qual_chars[idx])
            if ins_mask[idx]:
                new_seq.append(BASES[rng.integers(0, 4)])
                new_qual.append("!")  # 插入位给予最低质量分
                n_ins += 1
        seq_chars = new_seq
        qual_chars = new_qual

    # 4. 保持硬件读长约束 (如果 fixed_len 为真)
    if fixed_len:
        if len(seq_chars) > orig_len:
            # 截断超长部分
            seq_chars = seq_chars[:orig_len]
            qual_chars = qual_chars[:orig_len]
        elif len(seq_chars) < orig_len:
            # 右侧补齐随机碱基与低质量分
            missing = orig_len - len(seq_chars)
            pad_bases = rng.choice(BASES, size=missing).tolist()
            seq_chars.extend(pad_bases)
            qual_chars.extend(["!"] * missing)

    return "".join(seq_chars), "".join(qual_chars), n_sub, n_ins, n_del


def mutate_dataset(
    input_fastq: Path,
    output_dir: Path,
    sub_rate: float = 0.0,
    ins_rate: float = 0.0,
    del_rate: float = 0.0,
    coverage: float = 1.0,
    seed: int = 42,
    fixed_len: bool = True,
    manifest_in: Path | None = None,
) -> dict:
    """对 FASTQ 注入错误并生成独立的变异数据集目录与检验和。"""
    output_dir.mkdir(parents=True, exist_ok=True)
    rng = np.random.default_rng(seed)

    in_sha = sha256_file(input_fastq)
    out_fastq = output_dir / f"mutated_{input_fastq.name}"

    total_in = 0
    total_out = 0
    sum_sub = 0
    sum_ins = 0
    sum_del = 0

    print(f"=== 正在注入错误 ===")
    print(f"  输入文件: {input_fastq}")
    print(f"  扰动参数: sub={sub_rate:.3%}, ins={ins_rate:.3%}, del={del_rate:.3%}, coverage={coverage:.2f}, seed={seed}")

    with out_fastq.open("w", encoding="utf-8") as out_f:
        for header, seq, plus, qual in parse_fastq(input_fastq):
            total_in += 1
            # 覆盖度下采样
            if coverage < 1.0 and rng.random() > coverage:
                continue

            mut_seq, mut_qual, n_s, n_i, n_d = mutate_sequence(
                seq, qual, sub_rate, ins_rate, del_rate, rng, fixed_len=fixed_len
            )
            out_f.write(f"{header}\n{mut_seq}\n{plus}\n{mut_qual}\n")
            total_out += 1
            sum_sub += n_s
            sum_ins += n_i
            sum_del += n_d

    out_sha = sha256_file(out_fastq)

    # 生成元数据报告
    now_utc = datetime.now(timezone.utc).isoformat()
    meta = {
        "created_at_utc": now_utc,
        "tier": "D2",
        "description": "受控错误注入与下采样测序数据集",
        "input": {
            "file": input_fastq.name,
            "sha256": in_sha,
            "total_reads": total_in,
        },
        "mutation_parameters": {
            "sub_rate": sub_rate,
            "ins_rate": ins_rate,
            "del_rate": del_rate,
            "coverage": coverage,
            "seed": seed,
            "fixed_len": fixed_len,
        },
        "output": {
            "file": out_fastq.name,
            "sha256": out_sha,
            "total_reads": total_out,
            "total_substitutions": sum_sub,
            "total_insertions": sum_ins,
            "total_deletions": sum_del,
            "actual_sub_rate": (sum_sub / (total_out * len(seq))) if total_out else 0.0,
        },
    }

    if manifest_in and manifest_in.is_file():
        try:
            orig_man = json.loads(manifest_in.read_text(encoding="utf-8"))
            meta["parent_manifest"] = orig_man
        except Exception:
            pass

    meta_file = output_dir / "mutation_manifest.json"
    meta_file.write_text(json.dumps(meta, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    # 生成校验和
    sha_lines = [
        f"{out_sha}  {out_fastq.name}",
        f"{sha256_file(meta_file)}  {meta_file.name}",
    ]
    (output_dir / "SHA256SUMS").write_text("\n".join(sha_lines) + "\n", encoding="utf-8")

    print(f"  [PASS] 错误注入完成:")
    print(f"    读段数: {total_in} -> {total_out}")
    print(f"    总错误: sub={sum_sub}, ins={sum_ins}, del={sum_del}")
    print(f"    归档至: {output_dir}")
    return meta


def main():
    parser = argparse.ArgumentParser(description="D2 受控测序错误注入工具")
    parser.add_argument("--input-fastq", type=Path, required=True, help="输入源 FASTQ 文件")
    parser.add_argument("--output-dir", type=Path, required=True, help="输出目录 (严禁覆盖输入目录)")
    parser.add_argument("--manifest", type=Path, help="源数据集 manifest.json 路径 (可选)")
    parser.add_argument("--sub-rate", type=float, default=0.0, help="替换错误率 (例: 0.01 表示 1%%)")
    parser.add_argument("--ins-rate", type=float, default=0.0, help="插入错误率 (例: 0.001 表示 0.1%%)")
    parser.add_argument("--del-rate", type=float, default=0.0, help="缺失错误率 (例: 0.001 表示 0.1%%)")
    parser.add_argument("--coverage", type=float, default=1.0, help="保留读段比例 (例: 0.5 表示采样 50%%)")
    parser.add_argument("--seed", type=int, default=42, help="随机数种子 (保证可复现)")
    parser.add_argument("--variable-len", action="store_true", help="允许输出变长读段 (默认强制对齐固定硬件读长)")

    args = parser.parse_args()

    if not args.input_fastq.is_file():
        print(f"错误: 找不到输入 FASTQ 文件: {args.input_fastq}", file=sys.stderr)
        sys.exit(1)

    if args.output_dir.resolve() == args.input_fastq.parent.resolve():
        print("错误: 输出目录不能与输入目录相同 (门禁要求严禁覆盖原数据)！", file=sys.stderr)
        sys.exit(1)

    mutate_dataset(
        input_fastq=args.input_fastq,
        output_dir=args.output_dir,
        sub_rate=args.sub_rate,
        ins_rate=args.ins_rate,
        del_rate=args.del_rate,
        coverage=args.coverage,
        seed=args.seed,
        fixed_len=not args.variable_len,
        manifest_in=args.manifest,
    )


if __name__ == "__main__":
    main()

