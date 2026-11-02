#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""D3 真实测序经验误差轮廓提取器（Empirical Error Profile Extractor）。

依据 `docs/reference/d3-wetlab-survey.md` §5.1「方案 A：基于经验错误轮廓的物理噪声
驱动流水线」设计。本工具处于流水线的第 3 环：

    外部真实 FASTQ --> 比对 --> [本工具] --> empirical_profile.json --> mutate_reads.py

【边界声明（对应调研报告 §1.2 与 §6.1）】
    本工具只做「边界 B：真实物理测序噪声分布提取」。
    外部数据集的碱基流**不会**、也**不可能**进入本系统 Stage1~Stage4 的数据通路
    （无水印、外码体制异构）。本工具的唯一产物是**统计轮廓**，用于驱动本系统
    自有 Payload 的受控加噪。任何汇报都不得表述为「跑通了外部数据」。

【输入形态（三选一）】
  1. `--bam <aln.bam|aln.sam>`   已比对结果。BAM 走原生 BGZF 解析（不依赖 pysam）；
                                 参考碱基优先取 `--reference`，缺省回落到 MD tag。
  2. `--fastq <r.fq> --reference <ref>`
                                 无比对结果时，用内置 k-mer 种子 + 带状 DP 比对器
                                 现场比对（不依赖 minimap2）。
  3. `--parametric-prior <name>` 不含任何实测成分的**先验参数模型**，仅用于本仓库
                                 无法存放 GB 级外部 FASTQ 时的占位与自检。
                                 产物 JSON 内会打上 `NOT_MEASURED` 标记，
                                 严禁当作真实湿实验测量结果汇报。

【输出】`empirical_profile.json`（schema: d3-empirical-error-profile v1），含：
  * 4x4xC 碱基转移概率张量  P(B_obs | B_ref, c)
  * 每 Cycle 插入/缺失速率  R_ins(c), R_del(c)
  * 质量值条件分布          P(Q | match, c) 与 P(Q | mismatch, c)
  * 覆盖度变异系数          CV = sigma_D / mu_D 与 dropout 比例
  * Illumina 末端翘尾拟合   P_err(c) ≈ P0 + alpha * exp(beta * c)   （调研报告 §3.2 A）

碱基顺序在整个 JSON 中固定为生信惯例 **A, C, G, T**（注意：与本仓库 RTL 侧
`BASE2VAL = {A:0, T:1, G:2, C:3}` 的 2-bit 编码顺序不同，两者不得混用）。
"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import re
import struct
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Iterator, List, Optional, Sequence, Tuple

import numpy as np

SCHEMA_NAME = "d3-empirical-error-profile"
SCHEMA_VERSION = 1
TOOL_VERSION = "1.0.0"

# 生信惯例碱基顺序（本文件与 empirical_profile.json 全程使用）
BASES = "ACGT"
B2I = {"A": 0, "C": 1, "G": 2, "T": 3}
COMPLEMENT = str.maketrans("ACGTNacgtn", "TGCANtgcan")

# BAM 4-bit 编码表：=ACMGRSVTWYHKDBN
BAM_SEQ_DECODE = "=ACMGRSVTWYHKDBN"
BAM_CIGAR_OPS = "MIDNSHP=X"

MAX_Q = 60  # Phred 上限（含）


# --------------------------------------------------------------------------
# 基础工具
# --------------------------------------------------------------------------
def sha256_file(path: Path) -> str:
    """计算文件 SHA-256（与仓库其它工具口径一致）。"""
    h = hashlib.sha256()
    with path.open("rb") as f:
        while True:
            chunk = f.read(1 << 16)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


def revcomp(seq: str) -> str:
    """反向互补。"""
    return seq.translate(COMPLEMENT)[::-1]


def load_reference(path: Path) -> "Dict[str, str]":
    """读入参考序列。

    同时支持两种形态：
      * FASTA（以 '>' 开头，可多条序列，例如外部 Oligo 设计集合）；
      * 裸序列文本（本仓库 `reference_sequence.txt` 那种 40,500 nt 单行）。
    """
    text = path.read_text(encoding="utf-8", errors="ignore")
    refs: "Dict[str, str]" = {}
    if text.lstrip().startswith(">"):
        name = None
        buf: "List[str]" = []
        for line in text.splitlines():
            if line.startswith(">"):
                if name is not None:
                    refs[name] = "".join(buf).upper()
                name = line[1:].strip().split()[0] if line[1:].strip() else "ref"
                buf = []
            else:
                buf.append(line.strip())
        if name is not None:
            refs[name] = "".join(buf).upper()
    else:
        seq = "".join(text.split()).upper()
        if seq:
            refs[path.stem] = seq
    if not refs:
        raise ValueError("参考序列为空：%s" % path)
    return refs


def parse_fastq(path: Path) -> "Iterator[Tuple[str, str, str]]":
    """逐条读取 FASTQ，产出 (header, seq, qual)。支持 .gz。"""
    opener = gzip.open if path.suffix == ".gz" else open
    with opener(str(path), "rt", encoding="utf-8", errors="ignore") as f:  # type: ignore[operator]
        while True:
            header = f.readline()
            if not header:
                break
            seq = f.readline()
            plus = f.readline()
            qual = f.readline()
            if not seq or not plus or not qual:
                break
            yield header.rstrip("\r\n"), seq.strip().upper(), qual.rstrip("\r\n")


def phred_of(qual: str) -> "np.ndarray":
    """Phred+33 质量串 -> 整数数组。"""
    return np.frombuffer(qual.encode("ascii", errors="replace"), dtype=np.uint8).astype(np.int16) - 33


# --------------------------------------------------------------------------
# BAM / SAM 读取（原生实现，不依赖 pysam / samtools）
# --------------------------------------------------------------------------
class AlignedRecord(object):
    """一条比对记录的最小充分表示（cycle 语义已归一化）。

    注意 `seq` / `qual` 始终是**测序仪原始读出方向**（即 index 0 == cycle 1）。
    BAM/SAM 中反向链读段的 SEQ 是参考正向存储的，读入时会被转回读出方向，
    参考片段同步取反向互补，这样 cycle 依赖统计才不会被整体镜像。
    """

    __slots__ = ("qname", "flag", "ref_name", "pos", "cigar", "seq", "qual", "md")

    def __init__(self, qname, flag, ref_name, pos, cigar, seq, qual, md):
        self.qname = qname
        self.flag = flag
        self.ref_name = ref_name
        self.pos = pos  # 0-based 参考起点
        self.cigar = cigar  # List[(op_char, length)]，参考正向
        self.seq = seq  # 参考正向
        self.qual = qual  # 参考正向，整数数组
        self.md = md  # MD tag 字符串或 None

    @property
    def is_unmapped(self) -> bool:
        return bool(self.flag & 0x4)

    @property
    def is_reverse(self) -> bool:
        return bool(self.flag & 0x10)

    @property
    def is_secondary_or_supp(self) -> bool:
        return bool(self.flag & 0x100) or bool(self.flag & 0x800)


def parse_cigar_str(cigar: str) -> "List[Tuple[str, int]]":
    """'100M2I48M' -> [('M',100),('I',2),('M',48)]"""
    if cigar == "*" or not cigar:
        return []
    return [(m[1], int(m[0])) for m in re.findall(r"(\d+)([MIDNSHP=X])", cigar)]


def _read_bgzf_all(path: Path) -> bytes:
    """把 BGZF/BAM 全量解压到内存。

    BGZF 是「多成员 gzip」，Python 的 gzip 模块本身就会顺序解出全部成员，
    因此无需自建 BGZF 解块逻辑，也就不需要 pysam。
    """
    with gzip.open(str(path), "rb") as f:
        return f.read()


def iter_bam(path: Path) -> "Iterator[AlignedRecord]":
    """原生解析 BAM（BGZF 容器 + BAM 二进制记录）。"""
    blob = _read_bgzf_all(path)
    if blob[:4] != b"BAM\x01":
        raise ValueError("不是合法 BAM：magic != 'BAM\\1' (%s)" % path)
    off = 4
    (l_text,) = struct.unpack_from("<i", blob, off)
    off += 4 + l_text
    (n_ref,) = struct.unpack_from("<i", blob, off)
    off += 4
    ref_names: "List[str]" = []
    for _ in range(n_ref):
        (l_name,) = struct.unpack_from("<i", blob, off)
        off += 4
        ref_names.append(blob[off:off + l_name - 1].decode("ascii", "replace"))
        off += l_name + 4  # 跳过 l_ref
    n = len(blob)
    while off < n:
        (block_size,) = struct.unpack_from("<i", blob, off)
        off += 4
        end = off + block_size
        (ref_id, pos, l_read_name, mapq, _bin, n_cigar_op, flag, l_seq,
         _n_ref_id, _n_pos, _tlen) = struct.unpack_from("<iiBBHHHiiii", blob, off)
        p = off + 32
        qname = blob[p:p + l_read_name - 1].decode("ascii", "replace")
        p += l_read_name
        cigar: "List[Tuple[str, int]]" = []
        for _ in range(n_cigar_op):
            (packed,) = struct.unpack_from("<I", blob, p)
            p += 4
            cigar.append((BAM_CIGAR_OPS[packed & 0xF], packed >> 4))
        nseq_bytes = (l_seq + 1) // 2
        raw_seq = blob[p:p + nseq_bytes]
        p += nseq_bytes
        chars = []
        for i in range(l_seq):
            b = raw_seq[i >> 1]
            chars.append(BAM_SEQ_DECODE[(b >> 4) if (i & 1) == 0 else (b & 0xF)])
        seq = "".join(chars)
        qual_raw = blob[p:p + l_seq]
        p += l_seq
        qual = np.frombuffer(qual_raw, dtype=np.uint8).astype(np.int16)
        if qual.size and int(qual[0]) == 0xFF:  # 质量缺失
            qual = np.full(l_seq, -1, dtype=np.int16)
        md = _bam_tag_md(blob, p, end)
        off = end
        yield AlignedRecord(
            qname, flag,
            ref_names[ref_id] if 0 <= ref_id < len(ref_names) else "*",
            pos, cigar, seq, qual, md,
        )


def _bam_tag_md(blob: bytes, p: int, end: int) -> "Optional[str]":
    """在 BAM 记录的 tag 区里找 MD tag（其余 tag 按长度跳过）。"""
    while p + 3 <= end:
        tag = blob[p:p + 2].decode("ascii", "replace")
        val_type = chr(blob[p + 2])
        p += 3
        if val_type in "AcC":
            val = blob[p:p + 1]
            p += 1
        elif val_type in "sS":
            val = blob[p:p + 2]
            p += 2
        elif val_type in "iIf":
            val = blob[p:p + 4]
            p += 4
        elif val_type in "ZH":
            e = blob.index(b"\x00", p)
            val = blob[p:e]
            p = e + 1
            if tag == "MD":
                return val.decode("ascii", "replace")
        elif val_type == "B":
            sub = chr(blob[p])
            (cnt,) = struct.unpack_from("<i", blob, p + 1)
            width = {"c": 1, "C": 1, "s": 2, "S": 2, "i": 4, "I": 4, "f": 4}.get(sub, 1)
            p += 5 + cnt * width
        else:
            break
    return None


def iter_sam(path: Path) -> "Iterator[AlignedRecord]":
    """解析 SAM 文本（便于 `samtools view -h` 管道产物，或手工构造小样例）。"""
    opener = gzip.open if path.suffix == ".gz" else open
    with opener(str(path), "rt", encoding="utf-8", errors="ignore") as f:  # type: ignore[operator]
        for line in f:
            if not line or line.startswith("@"):
                continue
            fields = line.rstrip("\n").split("\t")
            if len(fields) < 11:
                continue
            flag = int(fields[1])
            seq = fields[9].upper()
            qual_s = fields[10]
            if qual_s == "*":
                qual = np.full(len(seq), -1, dtype=np.int16)
            else:
                qual = phred_of(qual_s)
            md = None
            for tag in fields[11:]:
                if tag.startswith("MD:Z:"):
                    md = tag[5:]
                    break
            yield AlignedRecord(
                fields[0], flag, fields[2], int(fields[3]) - 1,
                parse_cigar_str(fields[5]), seq, qual, md,
            )


def open_alignments(path: Path) -> "Iterator[AlignedRecord]":
    """按文件魔数自动区分 BAM(BGZF) 与 SAM 文本。"""
    with path.open("rb") as f:
        magic = f.read(2)
    if magic == b"\x1f\x8b":
        head = _read_bgzf_all(path)[:4]
        if head == b"BAM\x01":
            return iter_bam(path)
        return iter_sam(path)  # gzip 压缩的 SAM
    return iter_sam(path)


def md_to_ref_bases(md: str, read_bases_on_ref: str) -> "Optional[str]":
    """由 MD tag + 读段的 M 段碱基还原参考碱基串（长度等于 M 段总长）。"""
    out: "List[str]" = []
    i = 0  # 读段 M 段游标
    for token in re.finditer(r"(\d+)|(\^[A-Za-z]+)|([A-Za-z])", md):
        num, dele, mism = token.group(1), token.group(2), token.group(3)
        if num is not None:
            k = int(num)
            out.append(read_bases_on_ref[i:i + k])
            i += k
        elif dele is not None:
            continue  # 缺失碱基不占读段位置，插删速率由 CIGAR 统计
        else:
            out.append(mism.upper())
            i += 1
    ref = "".join(out)
    return ref if len(ref) == len(read_bases_on_ref) else None


# --------------------------------------------------------------------------
# 内置比对器：k-mer 种子 + 对角线投票 + 带状 DP（替代 minimap2）
# --------------------------------------------------------------------------
class KmerIndex(object):
    """参考序列的 k-mer 位置索引（仅正向链；读段方向由调用方枚举）。"""

    def __init__(self, refs: "Dict[str, str]", k: int = 14, max_hits: int = 64):
        self.k = k
        self.max_hits = max_hits
        self.refs = refs
        self.index: "Dict[str, List[Tuple[str, int]]]" = {}
        for name, seq in refs.items():
            for i in range(0, len(seq) - k + 1):
                kmer = seq[i:i + k]
                if "N" in kmer:
                    continue
                bucket = self.index.setdefault(kmer, [])
                if len(bucket) <= max_hits:
                    bucket.append((name, i))

    def seed_diagonals(self, read: str, n_seeds: int = 16) -> "Counter":
        """对读段撒种子，投票 (ref_name, diagonal=ref_pos-read_pos)。"""
        votes: "Counter" = Counter()
        L = len(read)
        if L < self.k:
            return votes
        step = max(1, (L - self.k) // max(1, n_seeds - 1)) if n_seeds > 1 else L
        for rp in range(0, L - self.k + 1, step):
            bucket = self.index.get(read[rp:rp + self.k])
            if not bucket or len(bucket) > self.max_hits:
                continue
            for name, ip in bucket:
                votes[(name, ip - rp)] += 1
        return votes


def banded_align(read: str, window: str, offset: int, band: int,
                 match: int = 1, mismatch: int = -2, gap: int = -3
                 ) -> "Tuple[int, List[Tuple[str, int]], int]":
    """带状比对：读段全长参与，参考窗口两端自由。

    `offset` 是「读段第 0 个碱基在 window 中的预期位置」（由种子投票的对角线给出），
    带宽 `band` 即允许的最大净插删漂移。返回 (score, cigar, ref_start_in_window)，
    cigar 只含 M/I/D，且 ref_start 让调用方能把 CIGAR 锚回参考坐标。

    打分默认 match=+1 / mismatch=-2 / gap=-3：Illumina 替换远多于插删，
    故意让 gap 比 mismatch 更贵，避免把一次替换误判成「插入 + 缺失」。
    """
    n, m = len(read), len(window)
    NEG = -(1 << 28)
    # 第 0 行：读段尚未消耗，参考起点在 [offset-band, offset+band] 内任意位置都免费
    prev = [NEG] * (m + 1)
    for j in range(max(0, offset - band), min(m, offset + band) + 1):
        prev[j] = 0
    trace: "List[bytes]" = []
    for i in range(1, n + 1):
        cur = [NEG] * (m + 1)
        row = bytearray(m + 1)
        lo = max(0, i + offset - band)
        hi = min(m, i + offset + band)
        for j in range(lo, hi + 1):
            best, op = NEG, 1
            if j >= 1 and prev[j - 1] > NEG:
                best = prev[j - 1] + (match if read[i - 1] == window[j - 1] else mismatch)
                op = 0
            if prev[j] > NEG and prev[j] + gap > best:   # 读段消耗、参考不消耗 -> 插入
                best, op = prev[j] + gap, 1
            if j >= 1 and cur[j - 1] > NEG and cur[j - 1] + gap > best:  # 缺失
                best, op = cur[j - 1] + gap, 2
            cur[j] = best
            row[j] = op
        trace.append(bytes(row))
        prev = cur
    # 末行取最优（参考右端自由）
    j_best, s_best = -1, NEG
    for j in range(m + 1):
        if prev[j] > s_best:
            s_best, j_best = prev[j], j
    if j_best < 0:
        return NEG, [], 0
    # 回溯：i 归零时的 j 即参考起点
    ops: "List[str]" = []
    i, j = n, j_best
    while i > 0:
        op = trace[i - 1][j]
        if op == 0:
            ops.append("M")
            i -= 1
            j -= 1
        elif op == 1:
            ops.append("I")
            i -= 1
        else:
            ops.append("D")
            j -= 1
        if j < 0:
            j = 0
    ops.reverse()
    cigar: "List[Tuple[str, int]]" = []
    for op in ops:
        if cigar and cigar[-1][0] == op:
            cigar[-1] = (op, cigar[-1][1] + 1)
        else:
            cigar.append((op, 1))
    return s_best, cigar, j


def ungapped_score(probe: str, ref_seq: str, diag: int) -> "Tuple[int, int, int]":
    """无缺口比对的 (匹配数, 比较位点数, 起点)。用于挑方向与快速通道。"""
    lo = max(0, diag)
    seg = ref_seq[lo:lo + len(probe)]
    if not seg:
        return 0, 0, lo
    off = lo - diag  # diag<0 时读段左端悬空
    same = sum(1 for a, b in zip(probe[off:off + len(seg)], seg) if a == b)
    return same, len(seg), lo


class BuiltinAligner(object):
    """FASTQ + 参考 -> 比对记录（cycle 方向已归一化）。

    流程：k-mer 种子投票定对角线 -> 无缺口快速评分选链方向 ->
    （必要时）带状 DP 还原插删 -> 一致率门禁。
    """

    def __init__(self, refs: "Dict[str, str]", k: int = 14, band: int = 8,
                 min_identity: float = 0.70, allow_indel: bool = True,
                 ungapped_shortcut: float = 1.0):
        self.refs = refs
        self.index = KmerIndex(refs, k=k)
        self.band = band
        self.min_identity = min_identity
        self.allow_indel = allow_indel
        # 无缺口一致率高于该阈值时跳过 DP（默认 1.0 = 只有完全无错读段才跳过）
        self.ungapped_shortcut = ungapped_shortcut
        self.stats = Counter()

    def align(self, seq: str, qual: "np.ndarray") -> "Optional[AlignedRecord]":
        """返回读出方向的比对记录；无法可信定位时返回 None。"""
        cand = None  # (ungapped_identity, votes, name, diag, is_rc)
        for is_rc in (False, True):
            # 索引只建了参考正向：负链读段先取 RC 才能命中
            probe = revcomp(seq) if is_rc else seq
            votes = self.index.seed_diagonals(probe)
            if not votes:
                continue
            for (name, diag), v in votes.most_common(3):
                same, total, _lo = ungapped_score(probe, self.refs[name], diag)
                if total < len(probe) // 2:
                    continue
                ident = same / total
                if cand is None or (ident, v) > (cand[0], cand[1]):
                    cand = (ident, v, name, diag, is_rc)
        if cand is None:
            self.stats["no_seed"] += 1
            return None
        ung_ident, _v, name, diag, is_rc = cand
        probe = revcomp(seq) if is_rc else seq
        probe_qual = qual[::-1] if is_rc else qual
        ref_seq = self.refs[name]

        if (not self.allow_indel) or ung_ident >= self.ungapped_shortcut:
            same, total, lo = ungapped_score(probe, ref_seq, diag)
            ident = (same / total) if total else 0.0
            cigar = [("M", total)]
            ref_start = lo
            self.stats["ungapped"] += 1
        else:
            lo = max(0, diag - self.band)
            hi = min(len(ref_seq), diag + len(probe) + self.band)
            window = ref_seq[lo:hi]
            if len(window) < len(probe) // 2:
                self.stats["short_window"] += 1
                return None
            _score, cigar, rs = banded_align(probe, window, diag - lo, self.band)
            if not cigar:
                self.stats["dp_failed"] += 1
                return None
            ref_start = lo + rs
            ident = self._identity(probe, ref_seq, ref_start, cigar)
            self.stats["banded_dp"] += 1

        if ident < self.min_identity:
            self.stats["low_identity"] += 1
            return None
        self.stats["aligned"] += 1
        return AlignedRecord("builtin", 16 if is_rc else 0, name, ref_start,
                             cigar, probe, probe_qual, None)

    @staticmethod
    def _identity(probe: str, ref_seq: str, ref_start: int,
                  cigar: "List[Tuple[str, int]]") -> float:
        """按 CIGAR 沿参考真实坐标算一致率（插删各计一个不匹配位点）。"""
        qi, ri = 0, ref_start
        same = total = 0
        for op, ln in cigar:
            if op == "M":
                for t in range(ln):
                    if qi + t < len(probe) and ri + t < len(ref_seq):
                        total += 1
                        if probe[qi + t] == ref_seq[ri + t]:
                            same += 1
                qi += ln
                ri += ln
            elif op == "I":
                qi += ln
                total += ln
            else:
                ri += ln
                total += ln
        return (same / total) if total else 0.0


# --------------------------------------------------------------------------
# 统计累加器
# --------------------------------------------------------------------------
class ProfileAccumulator(object):
    """按 Cycle 累加替换 / 插删 / 质量值 / 覆盖度。"""

    def __init__(self, read_length: int, q_bin: int = 2, max_q: int = MAX_Q):
        self.C = read_length
        self.q_bin = q_bin
        self.n_qbin = (max_q // q_bin) + 1
        self.max_q = max_q
        self.sub_counts = np.zeros((self.C, 4, 4), dtype=np.int64)
        self.ins_counts = np.zeros(self.C, dtype=np.int64)
        self.del_counts = np.zeros(self.C, dtype=np.int64)
        self.cycle_obs = np.zeros(self.C, dtype=np.int64)  # 每 cycle 的 M 位点数
        self.q_match = np.zeros((self.C, self.n_qbin), dtype=np.int64)
        self.q_mismatch = np.zeros((self.C, self.n_qbin), dtype=np.int64)
        self.q_match_sum = np.zeros(self.C, dtype=np.float64)
        self.q_match_sq = np.zeros(self.C, dtype=np.float64)
        self.q_mism_sum = np.zeros(self.C, dtype=np.float64)
        self.q_mism_sq = np.zeros(self.C, dtype=np.float64)
        self.n_reads = 0
        self.n_aligned_reads = 0
        self.depth: "Dict[str, np.ndarray]" = {}
        self.read_len_hist: "Counter" = Counter()
        self.skipped_long = 0

    def ensure_depth(self, refs: "Dict[str, str]") -> None:
        for name, seq in refs.items():
            self.depth[name] = np.zeros(len(seq), dtype=np.int32)

    def add_alignment(self, rec: AlignedRecord, ref_seq: "Optional[str]") -> bool:
        """把一条比对记录拆成 cycle 事件并累加。

        `rec` 必须是**参考正向**形态（BAM 原样）；本函数负责按 FLAG 0x10
        转回测序读出方向，保证 cycle 0 是真实的第 1 个测序循环。
        """
        self.n_reads += 1
        if rec.is_unmapped or not rec.cigar:
            return False
        seq, qual = rec.seq, rec.qual
        # 逐 CIGAR 走出「读段位点 -> 参考碱基」的配对（先在参考正向坐标系里做）
        events: "List[Tuple[str, int, str, str, int]]" = []  # (op, read_idx, ref_b, obs_b, q)
        qi = 0
        rp = rec.pos
        md_ref = None
        if ref_seq is None and rec.md:
            m_bases = []
            tqi = 0
            for op, ln in rec.cigar:
                if op in "M=X":
                    m_bases.append(seq[tqi:tqi + ln])
                    tqi += ln
                elif op in "IS":
                    tqi += ln
            md_ref = md_to_ref_bases(rec.md, "".join(m_bases))
            if md_ref is None:
                return False
        md_cursor = 0
        for op, ln in rec.cigar:
            if op in "M=X":
                for t in range(ln):
                    if qi + t >= len(seq):
                        break
                    obs = seq[qi + t]
                    if ref_seq is not None:
                        idx = rp + t
                        ref_b = ref_seq[idx] if 0 <= idx < len(ref_seq) else "N"
                    else:
                        ref_b = md_ref[md_cursor + t] if md_cursor + t < len(md_ref) else "N"
                    q = int(qual[qi + t]) if qi + t < len(qual) else -1
                    events.append(("M", qi + t, ref_b, obs, q))
                qi += ln
                rp += ln
                md_cursor += ln
            elif op == "I":
                for t in range(ln):
                    q = int(qual[qi + t]) if qi + t < len(qual) else -1
                    events.append(("I", qi + t, "-", seq[qi + t] if qi + t < len(seq) else "N", q))
                qi += ln
            elif op in "DN":
                events.append(("D", qi, "-", "-", -1))
                rp += ln
            elif op == "S":
                qi += ln
            elif op == "H" or op == "P":
                continue
        if not events:
            return False
        read_len = len(seq)
        self.read_len_hist[read_len] += 1
        # 方向归一化：负链读段在 BAM 里是参考正向存储，cycle 顺序需要翻回来
        if rec.is_reverse:
            events = [
                (op, read_len - 1 - ri, _comp(rb), _comp(ob), q)
                for (op, ri, rb, ob, q) in events
            ]
        if read_len > self.C:
            self.skipped_long += 1
        for op, ri, ref_b, obs_b, q in events:
            c = ri
            if c < 0 or c >= self.C:
                continue
            if op == "M":
                self.cycle_obs[c] += 1
                ir, io = B2I.get(ref_b, -1), B2I.get(obs_b, -1)
                if ir >= 0 and io >= 0:
                    self.sub_counts[c, ir, io] += 1
                    if 0 <= q <= self.max_q:
                        b = q // self.q_bin
                        if ir == io:
                            self.q_match[c, b] += 1
                            self.q_match_sum[c] += q
                            self.q_match_sq[c] += q * q
                        else:
                            self.q_mismatch[c, b] += 1
                            self.q_mism_sum[c] += q
                            self.q_mism_sq[c] += q * q
            elif op == "I":
                self.ins_counts[c] += 1
            elif op == "D":
                self.del_counts[c] += 1
        # 覆盖度
        if rec.ref_name in self.depth:
            d = self.depth[rec.ref_name]
            start, end = rec.pos, rec.pos
            for op, ln in rec.cigar:
                if op in "M=XDN":
                    end += ln
            start = max(0, min(start, len(d)))
            end = max(0, min(end, len(d)))
            if end > start:
                d[start:end] += 1
        self.n_aligned_reads += 1
        return True


def _comp(b: str) -> str:
    return {"A": "T", "C": "G", "G": "C", "T": "A", "-": "-"}.get(b, "N")


# --------------------------------------------------------------------------
# 末端翘尾模型拟合： P_err(c) = P0 + alpha * exp(beta * c)
# --------------------------------------------------------------------------
def fit_tail_rise(err_rate: "np.ndarray", weights: "Optional[np.ndarray]" = None) -> dict:
    """对 Illumina 3' 端翘尾做 P0 + alpha*exp(beta*c) 拟合（调研报告 §3.2 A）。

    beta 用网格搜索，(P0, alpha) 在给定 beta 下退化为线性最小二乘，
    因此无需 scipy。为避免 exp(beta*150) 溢出，内部用
    exp(beta*(c - C)) 作基函数，再换算回文档中的 alpha。
    """
    C = len(err_rate)
    c = np.arange(1, C + 1, dtype=np.float64)
    y = np.asarray(err_rate, dtype=np.float64)
    w = np.ones(C) if weights is None else np.asarray(weights, dtype=np.float64)
    ok = np.isfinite(y) & (w > 0)
    if ok.sum() < 4:
        return {"fitted": False, "reason": "有效 cycle 数不足"}
    cw, yw, ww = c[ok], y[ok], np.sqrt(w[ok])
    best = None
    for beta in np.concatenate([np.linspace(0.002, 0.05, 120), np.linspace(0.05, 0.5, 90)]):
        basis = np.exp(beta * (cw - C))
        A = np.vstack([np.ones_like(cw), basis]).T * ww[:, None]
        try:
            coef, *_ = np.linalg.lstsq(A, yw * ww, rcond=None)
        except np.linalg.LinAlgError:
            continue
        p0, a_tail = float(coef[0]), float(coef[1])
        if p0 < 0.0:  # 基线不能为负：钳到 0 后只解 alpha
            p0 = 0.0
            denom = float(np.sum((basis * ww) ** 2))
            a_tail = float(np.sum(basis * ww * yw * ww) / denom) if denom > 0 else 0.0
        pred = p0 + a_tail * basis
        rmse = float(np.sqrt(np.mean((pred - yw) ** 2)))
        if best is None or rmse < best[0]:
            best = (rmse, p0, a_tail, float(beta))
    if best is None:
        return {"fitted": False, "reason": "拟合失败"}
    rmse, p0, a_tail, beta = best
    pred = p0 + a_tail * np.exp(beta * (cw - C))
    ss_res = float(np.sum((yw - pred) ** 2))
    ss_tot = float(np.sum((yw - yw.mean()) ** 2))
    with np.errstate(over="ignore", under="ignore"):
        alpha_doc = float(a_tail * np.exp(-beta * C))
    return {
        "fitted": True,
        "form": "P_err(c) = P0 + alpha * exp(beta * c),  c 从 1 计数",
        "P0": p0,
        "alpha": alpha_doc,
        "beta": beta,
        "alpha_at_last_cycle": a_tail,
        "stable_form": "P_err(c) = P0 + alpha_at_last_cycle * exp(beta * (c - C))",
        "rmse": rmse,
        "r2": (1.0 - ss_res / ss_tot) if ss_tot > 0 else 0.0,
    }


# --------------------------------------------------------------------------
# 轮廓组装
# --------------------------------------------------------------------------
def rate_preserving_matrix(counts: "np.ndarray", pseudocount: float,
                           rate_pseudocount: float = 0.0,
                           fallback: "Optional[np.ndarray]" = None,
                           dir_prior: "Optional[np.ndarray]" = None) -> "np.ndarray":
    """把替换计数整理成转移概率矩阵，且**不改变实测碱基错误率**。

    Laplace 伪计数只作用在「已经发生替换之后、错成哪一个碱基」的 3 选 1 方向分布上；
    「错 / 不错」的二分严格取原始计数比值（除非显式给了 rate_pseudocount）。
    这样 `cycles/error_rate`、`aggregate/ti_tv_ratio` 与本矩阵三者自洽，
    加噪端 `mutate_reads.py --profile-from` 采样出的错误率与轮廓自报值一致。

    `dir_prior`（4x4，行内非对角归一）给出方向伪计数的**分摊比例**：
    低覆盖 cycle 的方向分布向它收缩，而不是向均匀分布收缩。替换方向偏好来自化学
    （转换 A<->G / C<->T 天然多于颠换），基本不随 cycle 变化，因此聚合方向分布
    是比均匀分布好得多的先验。向均匀收缩会把 Ti/Tv 往 0.5 拽——实测在
    2.43 次替换/cycle/ref-base 的早期 cycle 上，把 Ti/Tv 从 2.04 稀释到 1.73（缺陷 D3-2）。

    背景（缺陷 D3-1，见 logs/d3_profile/*/findings.md §B）：
    早先对整个 4x4 张量统一加伪计数（`counts + pc` 后按行归一），等价于给每一行
    注入 `3*pc/(n+4*pc)` 的**常数错误地板**。n=1500 时地板 0.109%，把早期 cycle
    的实测 0.165% 抬到 0.277%（+67.8%），全程 +15.7%，并把 Ti/Tv 从 2.04
    稀释到 1.69——轮廓文件对外宣称的 error_rate 与它实际驱动出的加噪结果不一致。
    """
    counts = np.asarray(counts, dtype=np.float64)
    flat = counts.reshape(-1, 4, 4)
    out = np.zeros_like(flat)
    ident = np.eye(4)
    for k in range(flat.shape[0]):
        for i in range(4):
            row = flat[k, i]
            n = float(row.sum())
            off = row.copy()
            off[i] = 0.0
            e = float(off.sum())
            if n <= 0.0:
                # 该 cycle 该 ref base 零观测：回退到汇总行，没有汇总则回退成恒等（不注错）
                out[k, i] = fallback[i] if fallback is not None else ident[i]
                continue
            p_err = (e + 3.0 * rate_pseudocount) / (n + 4.0 * rate_pseudocount)
            # 方向伪计数总量恒为 3*pseudocount，按 dir_prior 分摊（缺省才退化成均匀）
            if dir_prior is not None:
                pseudo = 3.0 * pseudocount * dir_prior[i]
            else:
                pseudo = pseudocount * (1.0 - ident[i])
            w = off + pseudo
            w[i] = 0.0
            s = float(w.sum())
            direction = (w / s) if s > 0 else (1.0 - ident[i]) / 3.0
            out[k, i] = direction * p_err
            out[k, i, i] = 1.0 - p_err
    return out.reshape(counts.shape)


def build_profile(acc: ProfileAccumulator, provenance: dict,
                  pseudocount: float = 0.5, keep_q_hist: bool = True,
                  rate_pseudocount: float = 0.0) -> dict:
    """把累加器里的原始计数整理成 empirical_profile.json 结构。"""
    C = acc.C
    counts = acc.sub_counts.astype(np.float64)
    # 保率平滑（缺陷 D3-1 修复）：伪计数只平滑替换方向，不注入错误率地板。
    # 先算汇总行，低覆盖 cycle 的零观测行回退到它。
    agg_counts = counts.sum(axis=0)
    agg_matrix = rate_preserving_matrix(agg_counts[None, :, :], pseudocount,
                                        rate_pseudocount)[0]
    # 聚合方向分布（行内非对角归一）作为逐 cycle 方向平滑的先验，避免低覆盖 cycle
    # 的方向偏好被拉向均匀（缺陷 D3-2）
    _dir = agg_counts.copy()
    np.fill_diagonal(_dir, 0.0)
    _rs = _dir.sum(axis=1, keepdims=True)
    dir_prior = np.where(_rs > 0, _dir / np.maximum(_rs, 1e-12),
                         (1.0 - np.eye(4)) / 3.0)
    matrix = rate_preserving_matrix(counts, pseudocount, rate_pseudocount,
                                    fallback=agg_matrix, dir_prior=dir_prior)

    obs = acc.cycle_obs.astype(np.float64)
    diag = np.array([[counts[c, b, b] for b in range(4)] for c in range(C)]).sum(axis=1)
    with np.errstate(divide="ignore", invalid="ignore"):
        err_rate = np.where(obs > 0, (obs - diag) / np.maximum(obs, 1), np.nan)
        ins_rate = np.where(obs > 0, acc.ins_counts / np.maximum(obs, 1), np.nan)
        del_rate = np.where(obs > 0, acc.del_counts / np.maximum(obs, 1), np.nan)
        q_m_mean = np.where(acc.q_match.sum(axis=1) > 0,
                            acc.q_match_sum / np.maximum(acc.q_match.sum(axis=1), 1), np.nan)
        q_x_mean = np.where(acc.q_mismatch.sum(axis=1) > 0,
                            acc.q_mism_sum / np.maximum(acc.q_mismatch.sum(axis=1), 1), np.nan)
        q_m_var = np.where(acc.q_match.sum(axis=1) > 0,
                           acc.q_match_sq / np.maximum(acc.q_match.sum(axis=1), 1) - q_m_mean ** 2, np.nan)
        q_x_var = np.where(acc.q_mismatch.sum(axis=1) > 0,
                           acc.q_mism_sq / np.maximum(acc.q_mismatch.sum(axis=1), 1) - q_x_mean ** 2, np.nan)

    total_obs = float(obs.sum())
    total_err = float(agg_counts.sum() - np.trace(agg_counts))
    # 转换 (transition: A<->G, C<->T) vs 颠换 (transversion)
    ti_pairs = [("A", "G"), ("G", "A"), ("C", "T"), ("T", "C")]
    ti = sum(agg_counts[B2I[a], B2I[b]] for a, b in ti_pairs)
    tv = total_err - ti

    # --- 自洽性自检（缺陷 D3-1 的常驻回归哨兵）---
    # 加噪端只读 substitution_matrix，所以必须证明它蕴含的错误率/Ti-Tv 与本文件
    # 自报的 error_rate / ti_tv_ratio 一致；否则轮廓宣称的和实际注入的是两回事。
    eye4 = np.eye(4, dtype=bool)
    m_err = matrix.copy()
    m_err[:, eye4] = 0.0
    row_obs = counts.sum(axis=2)                       # (C,4) 每 cycle 每 ref base 观测数
    tot_row = float(row_obs.sum())
    measured_rate = (total_err / total_obs) if total_obs > 0 else 0.0
    matrix_rate = (float((m_err.sum(axis=2) * row_obs).sum() / tot_row)
                   if tot_row > 0 else 0.0)
    rate_infl = ((matrix_rate - measured_rate) / measured_rate) if measured_rate > 0 else 0.0
    # Ti/Tv 必须用【逐 cycle】矩阵算：加噪采样读的是它，而聚合矩阵计数大、
    # 几乎不受平滑影响，用聚合矩阵自检会漏掉逐 cycle 方向分布被拉平的问题（缺陷 D3-2）。
    cyc_exp = np.einsum("cij,ci->ij", matrix, row_obs)
    np.fill_diagonal(cyc_exp, 0.0)
    ti_m = sum(cyc_exp[B2I[a], B2I[b]] for a, b in ti_pairs)
    tv_m = float(cyc_exp.sum() - ti_m)
    matrix_titv = (float(ti_m) / tv_m) if tv_m > 0 else None
    measured_titv = (float(ti) / tv) if tv > 0 else None
    titv_infl = (abs(matrix_titv - measured_titv) / measured_titv
                 if (matrix_titv is not None and measured_titv) else 0.0)
    self_check = {
        "measured_sub_rate": measured_rate,
        "matrix_implied_sub_rate": matrix_rate,
        "sub_rate_inflation": rate_infl,
        "measured_ti_tv": measured_titv,
        "matrix_implied_ti_tv": matrix_titv,
        "ti_tv_rel_dev": titv_infl,
        "tolerance": 0.02,
        "consistent": bool(abs(rate_infl) <= 0.02 and titv_infl <= 0.02),
        "note": ("substitution_matrix 蕴含的错误率与 Ti/Tv 必须与本文件自报的 "
                 "error_rate / ti_tv_ratio 一致（容差 2%），否则 mutate_reads.py "
                 "实际注入的噪声与轮廓宣称的不是同一个东西。"),
    }

    fit = fit_tail_rise(err_rate, weights=obs)

    # 覆盖度统计
    cov = {}
    if acc.depth:
        all_depth = np.concatenate([d.astype(np.float64) for d in acc.depth.values()])
        mu = float(all_depth.mean()) if all_depth.size else 0.0
        sd = float(all_depth.std()) if all_depth.size else 0.0
        cov = {
            "positions": int(all_depth.size),
            "mean_depth": mu,
            "std_depth": sd,
            "cv": (sd / mu) if mu > 0 else None,
            "dropout_fraction": float((all_depth == 0).mean()) if all_depth.size else None,
            "note": "CV = sigma_D / mu_D，逐参考位点深度统计；调研报告 §3.2 B 的过离散判据",
        }

    def _r(a, nd=8):
        """np -> 纯 Python，并把 NaN 转成 null（JSON 不接受 NaN）。"""
        arr = np.asarray(a, dtype=np.float64)
        return [None if not np.isfinite(v) else round(float(v), nd) for v in arr.ravel().tolist()]

    profile = {
        "schema": SCHEMA_NAME,
        "schema_version": SCHEMA_VERSION,
        "tool": "tools/extract_error_profile.py",
        "tool_version": TOOL_VERSION,
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "provenance": provenance,
        "bases": list(BASES),
        "base_order_note": "本 JSON 全程使用生信惯例 A,C,G,T；与仓库 RTL 侧 A,T,G,C 的 2-bit 编码不同，不得混用",
        "read_length": C,
        "counts": {
            "reads_seen": acc.n_reads,
            "reads_aligned": acc.n_aligned_reads,
            "aligned_bases": int(total_obs),
            "substitutions": int(total_err),
            "insertions": int(acc.ins_counts.sum()),
            "deletions": int(acc.del_counts.sum()),
            "reads_longer_than_profile": acc.skipped_long,
            "read_length_hist": {str(k): v for k, v in sorted(acc.read_len_hist.items())},
        },
        "aggregate": {
            "substitution_matrix": [[round(float(x), 8) for x in row] for row in agg_matrix],
            "substitution_counts": [[int(x) for x in row] for row in agg_counts],
            "sub_rate": (total_err / total_obs) if total_obs > 0 else 0.0,
            "ins_rate": (float(acc.ins_counts.sum()) / total_obs) if total_obs > 0 else 0.0,
            "del_rate": (float(acc.del_counts.sum()) / total_obs) if total_obs > 0 else 0.0,
            "ti_tv_ratio": (float(ti) / tv) if tv > 0 else None,
            "mean_q": float(np.nansum(acc.q_match_sum + acc.q_mism_sum) /
                            max(1.0, float((acc.q_match.sum() + acc.q_mismatch.sum())))),
        },
        "cycles": {
            "substitution_matrix": [
                [[round(float(x), 8) for x in row] for row in matrix[c]] for c in range(C)
            ],
            "substitution_counts": [
                [[int(x) for x in row] for row in acc.sub_counts[c]] for c in range(C)
            ],
            "observations": [int(x) for x in obs],
            "error_rate": _r(err_rate),
            "ins_rate": _r(ins_rate),
            "del_rate": _r(del_rate),
            "q_match_mean": _r(q_m_mean, 4),
            "q_match_std": _r(np.sqrt(np.clip(q_m_var, 0, None)), 4),
            "q_mismatch_mean": _r(q_x_mean, 4),
            "q_mismatch_std": _r(np.sqrt(np.clip(q_x_var, 0, None)), 4),
        },
        "quality_model": {
            "encoding": "Phred+33",
            "q_bin": acc.q_bin,
            "n_bins": acc.n_qbin,
            "bin_centers": [int(b * acc.q_bin + acc.q_bin // 2) for b in range(acc.n_qbin)],
            "has_hist": bool(keep_q_hist),
        },
        "tail_rise_fit": fit,
        "coverage": cov,
        "smoothing": {
            "mode": "rate_preserving",
            "pseudocount": pseudocount,
            "rate_pseudocount": rate_pseudocount,
            "note": ("Laplace 伪计数只平滑「已发生替换后错成哪个碱基」的 3 选 1 方向分布，"
                     "不平滑「错/不错」的二分，因此不会注入错误率地板（缺陷 D3-1 修复）。"
                     "rate_pseudocount>0 才会额外平滑错误率，默认 0 即完全忠实于实测计数。"),
            "self_check": self_check,
        },
    }
    if keep_q_hist:
        profile["quality_model"]["hist_match"] = [[int(x) for x in row] for row in acc.q_match]
        profile["quality_model"]["hist_mismatch"] = [[int(x) for x in row] for row in acc.q_mismatch]
    return profile


# --------------------------------------------------------------------------
# 先验参数模型（无实测成分，仅占位/自检用）
# --------------------------------------------------------------------------
PARAMETRIC_PRIORS = {
    # 参数取自调研报告 §3.2 的**定性**描述（Illumina 替换主导 + 3' 翘尾 + InDel 极罕见），
    # 不是任何一次实测的拟合结果。
    #   ti_weight    : 转换 (A<->G, C<->T) 相对于普通颠换的权重
    #   tv_boost     : 调研报告点名的 A->C 与 G->T 颠换的额外权重
    # 注意这两个是「单一替换方向」的相对权重，与汇总口径 Ti/Tv 不是同一个数，
    # 汇总 Ti/Tv 由 build_profile 从计数反算后写进 aggregate.ti_tv_ratio。
    "illumina_pe150": {
        "read_length": 150, "p0": 0.0008, "alpha_last": 0.010, "beta": 0.035,
        "ins_rate": 2.0e-5, "del_rate": 3.0e-5, "q_top": 38.0, "q_bottom": 22.0,
        "ti_weight": 4.5, "tv_boost": 1.6,
        "desc": "Illumina HiSeq/MiSeq PE150 定性先验：替换主导 + 3' 端翘尾，汇总 Ti/Tv≈2.0",
    },
    "mgi_t7_pe150": {
        "read_length": 150, "p0": 0.0004, "alpha_last": 0.0035, "beta": 0.030,
        "ins_rate": 1.0e-5, "del_rate": 1.5e-5, "q_top": 39.0, "q_bottom": 28.0,
        "ti_weight": 4.0, "tv_boost": 1.3,
        "desc": "MGI DNBSEQ-T7 PE150 定性先验：RCA 无指数放大，替换率更低、更平坦",
    },
}


def prior_weight(ref_base: str, obs_base: str, ti_weight: float, tv_boost: float) -> float:
    """单个替换方向 ref->obs 的相对权重（先验模型专用）。"""
    if ref_base == obs_base:
        return 0.0
    if (ref_base, obs_base) in {("A", "G"), ("G", "A"), ("C", "T"), ("T", "C")}:
        return ti_weight          # 转换 (transition)
    if (ref_base, obs_base) in {("A", "C"), ("G", "T")}:
        return tv_boost           # 调研报告 §3.2 点名偏多的两种颠换
    return 1.0                    # 其余颠换 (transversion)


def build_parametric_prior(name: str, read_length: "Optional[int]" = None,
                           q_bin: int = 2) -> dict:
    """构造**不含任何实测成分**的先验轮廓（JSON 里会打 NOT_MEASURED 标记）。"""
    if name not in PARAMETRIC_PRIORS:
        raise ValueError("未知先验模型 '%s'，可选：%s" % (name, ", ".join(PARAMETRIC_PRIORS)))
    p = dict(PARAMETRIC_PRIORS[name])
    C = int(read_length or p["read_length"])
    acc = ProfileAccumulator(C, q_bin=q_bin)
    c = np.arange(1, C + 1, dtype=np.float64)
    err = p["p0"] + p["alpha_last"] * np.exp(p["beta"] * (c - C))
    # 用一个足够大的「虚拟观测数」把解析速率写成计数，保证下游口径与实测路径完全一致
    N = 2_000_000
    for ci in range(C):
        e = float(err[ci])
        acc.cycle_obs[ci] = N
        for br in range(4):
            n_ref = N // 4
            n_err = e * n_ref
            wts = [prior_weight(BASES[br], BASES[bo], p["ti_weight"], p["tv_boost"])
                   for bo in range(4)]
            s = sum(wts)
            acc.sub_counts[ci, br, br] = int(round(n_ref - n_err))
            for bo in range(4):
                if bo != br:
                    acc.sub_counts[ci, br, bo] = int(round(n_err * wts[bo] / s))
        acc.ins_counts[ci] = int(round(p["ins_rate"] * N))
        acc.del_counts[ci] = int(round(p["del_rate"] * N))
        # 质量值：match 走 q_top->q_bottom 线性衰减，mismatch 整体低 8 dB 左右
        qm = p["q_top"] - (p["q_top"] - p["q_bottom"]) * (ci / max(1, C - 1))
        qx = max(2.0, qm - 9.0)
        for mean, hist, ssum, ssq, weight in (
            (qm, acc.q_match, acc.q_match_sum, acc.q_match_sq, N * (1.0 - e)),
            (qx, acc.q_mismatch, acc.q_mism_sum, acc.q_mism_sq, N * e),
        ):
            sigma = 3.0
            qs = np.arange(0, MAX_Q + 1)
            pdf = np.exp(-0.5 * ((qs - mean) / sigma) ** 2)
            pdf /= pdf.sum()
            cnt = np.round(pdf * weight).astype(np.int64)
            for q, n in zip(qs, cnt):
                if n:
                    hist[ci, q // q_bin] += n
                    ssum[ci] += float(q) * n
                    ssq[ci] += float(q) * float(q) * n
    acc.n_reads = acc.n_aligned_reads = N // C
    acc.read_len_hist[C] = acc.n_reads
    provenance = {
        "mode": "parametric_prior",
        "measured": False,
        "WARNING": "NOT_MEASURED —— 本轮廓由解析式先验生成，不含任何真实湿实验测序数据。"
                   "严禁在论文/结题材料中表述为实测经验轮廓；正式结论必须用 --bam 或 "
                   "--fastq/--reference 从真实外部数据集重新提取。",
        "prior_name": name,
        "prior_params": {k: v for k, v in p.items() if k != "desc"},
        "description": p["desc"],
        "reference_doc": "docs/reference/d3-wetlab-survey.md §3.2",
    }
    return build_profile(acc, provenance)


# --------------------------------------------------------------------------
# 主流程
# --------------------------------------------------------------------------
def extract_from_alignments(aln_path: Path, reference: "Optional[Path]",
                            read_length: "Optional[int]", q_bin: int,
                            max_reads: int, keep_q_hist: bool,
                            pseudocount: float,
                            rate_pseudocount: float = 0.0) -> dict:
    """从 BAM/SAM 提取轮廓。"""
    refs = load_reference(reference) if reference else {}
    # 先扫一遍确定读长（若未显式给出）
    if read_length is None:
        lens = Counter()
        for i, rec in enumerate(open_alignments(aln_path)):
            if rec.is_unmapped:
                continue
            lens[len(rec.seq)] += 1
            if i > 20000:
                break
        if not lens:
            raise ValueError("没有可用的已比对读段：%s" % aln_path)
        read_length = max(lens)
    acc = ProfileAccumulator(read_length, q_bin=q_bin)
    acc.ensure_depth(refs)
    used = 0
    for rec in open_alignments(aln_path):
        if max_reads and used >= max_reads:
            break
        if rec.is_unmapped or rec.is_secondary_or_supp:
            acc.n_reads += 1
            continue
        ref_seq = refs.get(rec.ref_name) if refs else None
        if ref_seq is None and not rec.md:
            acc.n_reads += 1
            continue
        if acc.add_alignment(rec, ref_seq):
            used += 1
    provenance = {
        "mode": "bam" if aln_path.suffix.lower() == ".bam" else "sam",
        "measured": True,
        "alignment_file": str(aln_path),
        "alignment_sha256": sha256_file(aln_path),
        "reference_file": str(reference) if reference else None,
        "reference_sha256": sha256_file(reference) if reference else None,
        "reference_source": "reference fasta" if refs else "MD tag",
        "boundary_note": "仅提取统计轮廓；外部读段碱基流不进入本系统 Stage1~4 数据通路"
                         "（docs/reference/d3-wetlab-survey.md §1.2 边界 A/B）",
    }
    return build_profile(acc, provenance, pseudocount=pseudocount, keep_q_hist=keep_q_hist,
                         rate_pseudocount=rate_pseudocount)


def extract_from_fastq(fastq: Path, reference: Path, read_length: "Optional[int]",
                       q_bin: int, max_reads: int, kmer: int, band: int,
                       min_identity: float, allow_indel: bool,
                       keep_q_hist: bool, pseudocount: float,
                       rate_pseudocount: float = 0.0,
                       ungapped_shortcut: float = 1.0) -> dict:
    """从 FASTQ + 参考提取轮廓（内置比对器）。"""
    refs = load_reference(reference)
    aligner = BuiltinAligner(refs, k=kmer, band=band, min_identity=min_identity,
                             allow_indel=allow_indel, ungapped_shortcut=ungapped_shortcut)
    if read_length is None:
        lens = Counter()
        for i, (_h, s, _q) in enumerate(parse_fastq(fastq)):
            lens[len(s)] += 1
            if i > 5000:
                break
        if not lens:
            raise ValueError("FASTQ 为空：%s" % fastq)
        read_length = max(lens)
    acc = ProfileAccumulator(read_length, q_bin=q_bin)
    acc.ensure_depth(refs)
    used = 0
    for _h, seq, qual in parse_fastq(fastq):
        if max_reads and used >= max_reads:
            break
        rec = aligner.align(seq, phred_of(qual))
        if rec is None:
            acc.n_reads += 1   # 未能可信定位：只计入总数，不进任何统计
            continue
        if acc.add_alignment(rec, refs.get(rec.ref_name)):
            used += 1
    provenance = {
        "mode": "fastq_align",
        "measured": True,
        "fastq_file": str(fastq),
        "fastq_sha256": sha256_file(fastq),
        "reference_file": str(reference),
        "reference_sha256": sha256_file(reference),
        "aligner": "builtin kmer-seed + banded-DP (k=%d, band=%d, min_identity=%.2f)"
                   % (kmer, band, min_identity),
        "aligner_stats": dict(aligner.stats),
        "boundary_note": "仅提取统计轮廓；外部读段碱基流不进入本系统 Stage1~4 数据通路"
                         "（docs/reference/d3-wetlab-survey.md §1.2 边界 A/B）",
    }
    return build_profile(acc, provenance, pseudocount=pseudocount, keep_q_hist=keep_q_hist,
                         rate_pseudocount=rate_pseudocount)


def print_summary(profile: dict) -> None:
    """终端摘要（便于人工快速核对，不替代 JSON）。"""
    cnt = profile["counts"]
    agg = profile["aggregate"]
    fit = profile.get("tail_rise_fit", {})
    prov = profile["provenance"]
    print("=== D3 经验误差轮廓提取完成 ===")
    print("  来源模式  : %s (measured=%s)" % (prov.get("mode"), prov.get("measured")))
    if prov.get("WARNING"):
        print("  ⚠ 警告    : %s" % prov["WARNING"])
    print("  读长      : %d cycle" % profile["read_length"])
    print("  读段      : 见到 %d，已比对 %d" % (cnt["reads_seen"], cnt["reads_aligned"]))
    print("  碱基      : %d 个已比对位点" % cnt["aligned_bases"])
    print("  替换      : %d (%.4f%%)" % (cnt["substitutions"], agg["sub_rate"] * 100))
    print("  插入/缺失 : %d / %d (%.5f%% / %.5f%%)"
          % (cnt["insertions"], cnt["deletions"], agg["ins_rate"] * 100, agg["del_rate"] * 100))
    if agg.get("ti_tv_ratio") is not None:
        print("  Ti/Tv     : %.3f" % agg["ti_tv_ratio"])
    er = [x for x in profile["cycles"]["error_rate"] if x is not None]
    if er:
        head = np.mean(er[:min(30, len(er))])
        tail = np.mean(er[-min(30, len(er)):])
        print("  末端翘尾  : 前30 cycle %.4f%% -> 后30 cycle %.4f%%  (放大 %.2fx)"
              % (head * 100, tail * 100, (tail / head) if head > 0 else float("nan")))
    if fit.get("fitted"):
        print("  拟合      : P0=%.3e, alpha=%.3e, beta=%.4f, R^2=%.4f"
              % (fit["P0"], fit["alpha"], fit["beta"], fit["r2"]))
    sc = (profile.get("smoothing") or {}).get("self_check") or {}
    if sc:
        if sc.get("consistent"):
            print("  自洽性    : [OK] 矩阵蕴含替换率 %.4f%% vs 实测 %.4f%% (偏差 %+.2f%%)，"
                  "Ti/Tv 偏差 %.2f%%"
                  % (sc["matrix_implied_sub_rate"] * 100, sc["measured_sub_rate"] * 100,
                     sc["sub_rate_inflation"] * 100, sc["ti_tv_rel_dev"] * 100))
        else:
            print("  ⚠ 自洽性  : [FAIL] 平滑使矩阵蕴含替换率 %.4f%% 偏离实测 %.4f%% 达 %+.2f%%"
                  "（Ti/Tv 偏差 %.2f%%）——加噪端实际注入的噪声与本轮廓自报值不一致，"
                  "请检查 --rate-pseudocount"
                  % (sc["matrix_implied_sub_rate"] * 100, sc["measured_sub_rate"] * 100,
                     sc["sub_rate_inflation"] * 100, sc["ti_tv_rel_dev"] * 100))
    cov = profile.get("coverage") or {}
    if cov.get("cv") is not None:
        print("  覆盖度    : mean=%.2f, CV=%.4f, dropout=%.4f"
              % (cov["mean_depth"], cov["cv"], cov["dropout_fraction"]))


def main() -> int:
    ap = argparse.ArgumentParser(
        description="D3 真实测序经验误差轮廓提取器（BAM / FASTQ+Reference -> empirical_profile.json）",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""示例：
  # 1) 已有比对结果（BAM 原生解析，参考碱基取自 MD tag 或 --reference）
  tools/extract_error_profile.py --bam ext.bam --reference oligos.fa -o data/profiles/illumina_pe150.json

  # 2) 只有 FASTQ + 参考（内置比对器，无需 minimap2）
  tools/extract_error_profile.py --fastq ext.fq --reference ref.txt -o profile.json

  # 3) 先验占位模型（不含实测成分，JSON 内带 NOT_MEASURED 标记）
  tools/extract_error_profile.py --parametric-prior illumina_pe150 -o prior.json
""")
    src = ap.add_mutually_exclusive_group(required=True)
    src.add_argument("--bam", type=Path, help="已比对的 BAM 或 SAM 文件")
    src.add_argument("--fastq", type=Path, help="外部 FASTQ（需配合 --reference）")
    src.add_argument("--parametric-prior", type=str, choices=sorted(PARAMETRIC_PRIORS),
                     help="生成不含实测成分的先验轮廓（仅占位/自检）")
    ap.add_argument("--reference", type=Path, help="参考序列（FASTA 或裸序列文本）")
    ap.add_argument("-o", "--output", type=Path, required=True, help="输出 empirical_profile.json")
    ap.add_argument("--read-length", type=int, default=None, help="Cycle 数（默认自动探测）")
    ap.add_argument("--max-reads", type=int, default=0, help="最多统计多少条已比对读段（0=全部）")
    ap.add_argument("--q-bin", type=int, default=2, help="质量值直方图分箱宽度（默认 2）")
    ap.add_argument("--no-q-hist", action="store_true", help="不写出逐 cycle 质量直方图（仅留均值/方差）")
    ap.add_argument("--pseudocount", type=float, default=0.5,
                    help="替换【方向】分布的 Laplace 平滑系数（不影响错误率）")
    ap.add_argument("--rate-pseudocount", type=float, default=0.0,
                    help="额外平滑【错误率】本身的伪计数；默认 0=忠实实测。"
                         "设为非 0 会给每个 cycle 注入 3*pc/(n+4*pc) 的错误率地板（缺陷 D3-1）")
    ap.add_argument("--kmer", type=int, default=14, help="内置比对器种子长度")
    ap.add_argument("--band", type=int, default=8, help="内置比对器 DP 带宽（即最大可容忍净插删）")
    ap.add_argument("--min-identity", type=float, default=0.70, help="内置比对器可信度门禁")
    ap.add_argument("--no-indel", action="store_true", help="内置比对器只做无缺口比对（更快，只统计替换）")
    ap.add_argument("--ungapped-shortcut", type=float, default=1.0,
                    help="无缺口一致率高于该值时跳过带状 DP（默认 1.0，即只跳过全对读段）")
    args = ap.parse_args()

    if args.fastq and not args.reference:
        print("错误：--fastq 模式必须同时给出 --reference", file=sys.stderr)
        return 2
    for p in (args.bam, args.fastq, args.reference):
        if p is not None and not Path(p).is_file():
            print("错误：找不到输入文件 %s" % p, file=sys.stderr)
            return 2

    if args.parametric_prior:
        profile = build_parametric_prior(args.parametric_prior, args.read_length, args.q_bin)
    elif args.bam:
        profile = extract_from_alignments(args.bam, args.reference, args.read_length,
                                          args.q_bin, args.max_reads, not args.no_q_hist,
                                          args.pseudocount,
                                          rate_pseudocount=args.rate_pseudocount)
    else:
        profile = extract_from_fastq(args.fastq, args.reference, args.read_length,
                                     args.q_bin, args.max_reads, args.kmer, args.band,
                                     args.min_identity, not args.no_indel,
                                     not args.no_q_hist, args.pseudocount,
                                     rate_pseudocount=args.rate_pseudocount,
                                     ungapped_shortcut=args.ungapped_shortcut)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(profile, indent=1, ensure_ascii=False) + "\n",
                           encoding="utf-8")
    print_summary(profile)
    print("  输出      : %s (sha256=%s)" % (args.output, sha256_file(args.output)[:16] + "..."))
    if profile["counts"]["reads_aligned"] == 0 and profile["provenance"].get("measured"):
        print("警告：没有任何读段被成功比对，轮廓无统计意义！", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
