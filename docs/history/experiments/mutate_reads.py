#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""D2 受控测序错误注入工具 / D3 真实物理经验轮廓加噪引擎。

【两种模式】
  * **D2 均匀受控模式**（`--sub-rate/--ins-rate/--del-rate`，原有行为，逐位独立同分布）：
    用于扫门限曲线，参数可解析、可复算。
  * **D3 经验轮廓模式**（`--profile-from empirical_profile.json`，本次新增）：
    按 `tools/extract_error_profile.py` 提取的真实测序经验轮廓逐 Cycle 注入
    物理偏差——Illumina 3' 末端翘尾、4x4 碱基替换方向偏好（转换/颠换不等概）、
    Cycle 依赖的 InDel 速率，以及与 match/mismatch 相关的 Q-score 衰减。
    该模式下均匀速率参数被忽略，误差强度只由轮廓与 `--profile-scale` 决定。

依据 docs/06-verification-plan.md的受控噪声矩阵 与 docs/reference/d3-wetlab-survey.md §5.1 设计：
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
import math
import os
import sys
from bisect import bisect_right
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


PROFILE_BASES = "ACGT"          # 经验轮廓 JSON 的碱基顺序（生信惯例，与 RTL 侧 ATGC 不同）
PROFILE_B2I = {"A": 0, "C": 1, "G": 2, "T": 3}
Q_MIN, Q_MAX = 0, 60


class EmpiricalProfile(object):
    """`empirical_profile.json` 的加噪侧运行时表示。

    职责：
      1. 校验 schema，把 null（无观测 cycle）回填为汇总值；
      2. 按 `--profile-scale` 缩放误差强度（对角线重新归一，概率守恒）；
      3. 提供逐 Cycle 的替换采样、InDel 判定与 Q-score 采样。
    """

    def __init__(self, path: Path, scale: float = 1.0, cycle_map: str = "clamp"):
        self.path = Path(path)
        self.sha256 = sha256_file(self.path)
        raw = json.loads(self.path.read_text(encoding="utf-8"))
        if raw.get("schema") != "d3-empirical-error-profile":
            raise ValueError("不是经验误差轮廓文件（schema=%r），"
                             "请用 tools/extract_error_profile.py 生成" % raw.get("schema"))
        if list(raw.get("bases", [])) != list(PROFILE_BASES):
            raise ValueError("轮廓碱基顺序必须是 A,C,G,T，实为 %r" % (raw.get("bases"),))
        self.raw = raw
        self.scale = float(scale)
        self.cycle_map = cycle_map
        self.C = int(raw["read_length"])
        self.provenance = raw.get("provenance", {})
        self.measured = bool(self.provenance.get("measured", False))

        cyc = raw["cycles"]
        agg = raw["aggregate"]
        matrix = np.asarray(cyc["substitution_matrix"], dtype=np.float64)  # (C,4,4)
        if matrix.shape != (self.C, 4, 4):
            raise ValueError("转移张量形状应为 (%d,4,4)，实为 %s" % (self.C, matrix.shape))
        # 逐 cycle 行归一（提取器已做 Laplace 平滑，这里只兜底）
        matrix = matrix / matrix.sum(axis=2, keepdims=True)
        if self.scale != 1.0:
            matrix = self._scale_matrix(matrix, self.scale)
        self.matrix = matrix
        self.cum = np.cumsum(matrix, axis=2)
        # 逐碱基采样是热路径：4 元素上的 np.searchsorted 开销远大于纯 Python 比较，
        # 这里把累积分布落成嵌套 list，实测整体加速约 6x。
        self.cum_list = [[list(map(float, self.cum[c, r])) for r in range(4)]
                         for c in range(self.C)]

        self.ins_rate = self._fill(cyc.get("ins_rate"), float(agg.get("ins_rate", 0.0)))
        self.del_rate = self._fill(cyc.get("del_rate"), float(agg.get("del_rate", 0.0)))
        if self.scale != 1.0:
            self.ins_rate = np.clip(self.ins_rate * self.scale, 0.0, 0.5)
            self.del_rate = np.clip(self.del_rate * self.scale, 0.0, 0.5)

        # 质量值：优先用逐 cycle 直方图采样，缺省回落到截断高斯
        qm = raw.get("quality_model", {})
        self.q_bin = int(qm.get("q_bin", 1))
        self.q_centers = np.asarray(qm.get("bin_centers", []), dtype=np.float64)
        self.q_hist_match = self._cum_hist(qm.get("hist_match"))
        self.q_hist_mismatch = self._cum_hist(qm.get("hist_mismatch"))
        self.q_match_mean = self._fill(cyc.get("q_match_mean"), 35.0)
        self.q_match_std = self._fill(cyc.get("q_match_std"), 2.0)
        self.q_mismatch_mean = self._fill(cyc.get("q_mismatch_mean"), 20.0)
        self.q_mismatch_std = self._fill(cyc.get("q_mismatch_std"), 4.0)

    # -- 构造辅助 --------------------------------------------------------
    @staticmethod
    def _fill(values, default: float) -> "np.ndarray":
        """把 JSON 里的 null（该 cycle 无观测）回填成汇总缺省值。"""
        if not values:
            return np.array([default], dtype=np.float64)
        return np.array([default if v is None else float(v) for v in values], dtype=np.float64)

    @staticmethod
    def _cum_hist(hist):
        """逐 cycle 直方图 -> 累积分布（嵌套 list，供 bisect 采样）。

        全零行（该 cycle 没有该类事件）标 False，采样时回落到截断高斯。
        """
        if not hist:
            return None
        arr = np.asarray(hist, dtype=np.float64)
        tot = arr.sum(axis=1, keepdims=True)
        ok = [bool(t) for t in (tot[:, 0] > 0)]
        safe = np.where(tot > 0, tot, 1.0)
        cum = np.cumsum(arr / safe, axis=1)
        return [list(map(float, row)) for row in cum], ok

    @staticmethod
    def _scale_matrix(matrix: "np.ndarray", scale: float) -> "np.ndarray":
        """按 `scale` 缩放非对角（错误）概率，对角线补回，保持逐行和为 1。

        当 scale 大到错误概率之和超过 1 时按比例封顶（对角线归零），
        因此 `--profile-scale` 是「误差倍率」，不是无界外推。
        """
        out = matrix.copy()
        eye = np.eye(4, dtype=bool)
        for c in range(out.shape[0]):
            row = out[c]
            err = row.copy()
            err[eye] = 0.0
            err *= scale
            s = err.sum(axis=1, keepdims=True)
            too_big = (s > 1.0).ravel()
            if too_big.any():
                err[too_big] = err[too_big] / s[too_big]
                s = err.sum(axis=1, keepdims=True)
            new = err
            new[eye] = (1.0 - s).ravel()
            out[c] = new
        return out

    # -- 运行期接口 ------------------------------------------------------
    def cycle_index(self, c: int, read_len: int) -> int:
        """把输出读段位置映射到轮廓 cycle。"""
        if c < self.C:
            return c
        if self.cycle_map == "stretch" and read_len > 1:
            return min(self.C - 1, int(c * self.C / read_len))
        return self.C - 1        # clamp：超出部分沿用末 cycle（最差质量），偏保守

    def sample_base(self, ref_base: str, c: int, u: float) -> str:
        """按 P(B_obs | B_ref, c) 采样观测碱基。"""
        ir = PROFILE_B2I.get(ref_base)
        if ir is None:                     # N 或非法字符：等概率四选一，不计入替换
            return PROFILE_BASES[min(3, int(u * 4))]
        row = self.cum_list[c][ir]
        if u < row[0]:
            return "A"
        if u < row[1]:
            return "C"
        if u < row[2]:
            return "G"
        return "T"

    def rate_at(self, arr: "np.ndarray", c: int) -> float:
        return float(arr[c if c < len(arr) else -1])

    def sample_q(self, c: int, is_mismatch: bool, u1: float, u2: float) -> int:
        """按 P(Q | match/mismatch, c) 采样 Phred 质量值。"""
        pack = self.q_hist_mismatch if is_mismatch else self.q_hist_match
        if pack is not None:
            cum, ok = pack
            ci = c if c < len(cum) else len(cum) - 1
            if ok[ci]:
                row = cum[ci]
                b = min(bisect_right(row, u1), len(row) - 1)
                center = float(self.q_centers[b]) if b < len(self.q_centers) else b * self.q_bin
                # 在分箱内均匀展开，避免输出质量值只落在箱心
                jitter = (u2 - 0.5) * self.q_bin
                return min(Q_MAX, max(Q_MIN, int(round(center + jitter))))
        mean = self.rate_at(self.q_mismatch_mean if is_mismatch else self.q_match_mean, c)
        std = self.rate_at(self.q_mismatch_std if is_mismatch else self.q_match_std, c)
        # 用 Box-Muller 把两个均匀数变成正态，保证与调用方共用同一条随机流
        u1 = min(max(u1, 1e-12), 1.0 - 1e-12)
        z = math.sqrt(-2.0 * math.log(u1)) * math.cos(2.0 * math.pi * u2)
        return min(Q_MAX, max(Q_MIN, int(round(mean + z * max(std, 0.5)))))

    def summary(self) -> dict:
        """写进 mutation_manifest.json 的轮廓溯源信息。"""
        eye = np.eye(4, dtype=bool)
        err = self.matrix.copy()
        err[:, eye] = 0.0
        per_cycle_err = err.sum(axis=2).mean(axis=1)
        info = {
            "profile_file": str(self.path),
            "profile_sha256": self.sha256,
            "profile_schema_version": self.raw.get("schema_version"),
            "profile_created_at_utc": self.raw.get("created_at_utc"),
            "source_mode": self.provenance.get("mode"),
            "measured": self.measured,
            "read_length": self.C,
            "profile_scale": self.scale,
            "cycle_map": self.cycle_map,
            "expected_sub_rate": float(per_cycle_err.mean()),
            "expected_sub_rate_first30": float(per_cycle_err[:30].mean()),
            "expected_sub_rate_last30": float(per_cycle_err[-30:].mean()),
            "expected_ins_rate": float(self.ins_rate.mean()),
            "expected_del_rate": float(self.del_rate.mean()),
        }
        # 轮廓的自洽性自检（extract_error_profile.py 写入）：加噪端只读 substitution_matrix，
        # 该字段说明矩阵蕴含的错误率/Ti-Tv 是否与轮廓自报的 error_rate/ti_tv_ratio 一致。
        sc = (self.raw.get("smoothing") or {}).get("self_check")
        if sc is not None:
            info["profile_self_check"] = sc
            if not sc.get("consistent", True):
                info["profile_self_check_warning"] = (
                    "源轮廓自检未通过（替换率偏差 %+.2f%%、Ti/Tv 偏差 %.2f%%）："
                    "本数据集实际注入的噪声与该轮廓自报的 error_rate / ti_tv_ratio 不一致。"
                    % (sc.get("sub_rate_inflation", 0.0) * 100,
                       sc.get("ti_tv_rel_dev", 0.0) * 100))
        else:
            info["profile_self_check"] = None
            info["profile_self_check_warning"] = (
                "源轮廓没有 smoothing.self_check 字段（由旧版 extract_error_profile.py 生成）："
                "无法确认它蕴含的错误率与自报值一致，建议用当前版本重新提取。")
        if not self.measured:
            info["WARNING"] = (
                "本次加噪使用的是 NOT_MEASURED 先验轮廓（provenance.mode=%s），"
                "不含真实湿实验测序成分，衍生数据集不得表述为「真实经验噪声」。"
                % self.provenance.get("mode"))
        if self.provenance.get("WARNING"):
            info["profile_warning"] = self.provenance["WARNING"]
        return info


def mutate_sequence_profile(
    seq: str,
    profile: EmpiricalProfile,
    rng: np.random.Generator,
    fixed_len: bool = True,
) -> "tuple[str, str, int, int, int, dict]":
    """按经验轮廓逐 Cycle 加噪（替代均匀模型）。

    与 D2 均匀模式的关键区别：**cycle 语义定义在输出读段位置上**。
    测序仪的第 c 个循环产出读段第 c 个碱基，插入会把后续模板碱基整体后推、
    缺失会把模板碱基跳过——因此定长适配不是事后截断/补齐，而是
    「读满 orig_len 个循环就停机」，与真实仪器行为一致。

    第 6 个返回值是逐 cycle 台账 `events`，由加噪过程**当场记账**：
    插删一旦发生，输出位置与模板位置就永久错位，事后逐位比对
    `mut_seq[k] != seq[k]` 会把错位整段误计成替换（实测能把 0.27% 抬到 0.4%），
    因此逐 cycle 判据只能取这里的台账。
    """
    orig_len = len(seq)
    target = orig_len if fixed_len else None
    out_bases: "list[str]" = []
    out_mismatch: "list[bool]" = []
    # 台账：sub_cycles/obs_cycles 只记「有模板碱基参与」的循环（排除插入与补齐）
    ev_sub: "list[int]" = []
    ev_obs: "list[int]" = []
    ev_ins: "list[int]" = []
    ev_del: "list[int]" = []
    n_sub = n_ins = n_del = 0

    # 预抽随机数：读段级批量抽取比逐碱基调用快得多，且顺序固定 -> 可复现
    budget = orig_len * 2 + 16
    pool = rng.random(budget * 4).tolist()
    u_del = pool[0:budget]
    u_sub = pool[budget:2 * budget]
    u_ins = pool[2 * budget:3 * budget]
    u_base = pool[3 * budget:4 * budget]

    i = 0   # 模板游标
    c = 0   # 输出循环号
    while i < len(seq):
        if target is not None and c >= target:
            break
        if c >= budget - 2:
            break
        ci = profile.cycle_index(c, orig_len)
        # 1) 缺失：该模板碱基没被读到，循环号不推进
        if u_del[i % budget] < profile.rate_at(profile.del_rate, ci):
            i += 1
            n_del += 1
            ev_del.append(c)
            continue
        # 2) 替换：按 P(B_obs | B_ref, cycle) 采样
        ref_b = seq[i].upper()
        obs = profile.sample_base(ref_b, ci, u_sub[c])
        ev_obs.append(c)
        if obs != ref_b:
            n_sub += 1
            ev_sub.append(c)
        out_bases.append(obs)
        out_mismatch.append(obs != ref_b)
        i += 1
        c += 1
        # 3) 插入：多读出一个碱基，占掉下一个循环
        if c < budget and (target is None or c < target) and \
                u_ins[c] < profile.rate_at(profile.ins_rate, profile.cycle_index(c, orig_len)):
            out_bases.append(BASES[int(u_base[c] * 4) & 3])
            out_mismatch.append(True)     # 插入碱基在参考上无对应，按错误位点给质量
            n_ins += 1
            ev_ins.append(c)
            c += 1

    # 模板提前耗尽（净缺失过多）时补齐：真实仪器仍会跑满循环数
    if target is not None and len(out_bases) < target:
        pad = target - len(out_bases)
        u_pad = rng.random(pad)
        for t in range(pad):
            out_bases.append(BASES[int(u_pad[t] * 4) & 3])
            out_mismatch.append(True)

    n_out = len(out_bases)
    u_q1 = rng.random(n_out).tolist()
    u_q2 = rng.random(n_out).tolist()
    quals = "".join(
        chr(33 + profile.sample_q(profile.cycle_index(k, orig_len), out_mismatch[k],
                                  u_q1[k], u_q2[k]))
        for k in range(n_out)
    )
    events = {
        "sub_cycles": ev_sub,
        "obs_cycles": ev_obs,
        "ins_cycles": ev_ins,
        "del_cycles": ev_del,
        "q": [ord(ch) - 33 for ch in quals],
        "mismatch": out_mismatch,
    }
    return "".join(out_bases), quals, n_sub, n_ins, n_del, events


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
    profile: "EmpiricalProfile | None" = None,
) -> dict:
    """对 FASTQ 注入错误并生成独立的变异数据集目录与检验和。

    `profile` 非空时进入 D3 经验轮廓模式，均匀速率参数被忽略。
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    rng = np.random.default_rng(seed)

    in_sha = sha256_file(input_fastq)
    out_fastq = output_dir / f"mutated_{input_fastq.name}"

    total_in = 0
    total_out = 0
    total_bases = 0
    sum_sub = 0
    sum_ins = 0
    sum_del = 0
    # 逐 cycle 实测统计：用于事后核对「注出来的」与「轮廓声称的」是否一致
    cyc_len = profile.C if profile is not None else 0
    cyc_sub = np.zeros(max(cyc_len, 1), dtype=np.int64)
    cyc_obs = np.zeros(max(cyc_len, 1), dtype=np.int64)
    q_sum = np.zeros(max(cyc_len, 1), dtype=np.float64)
    q_obs = np.zeros(max(cyc_len, 1), dtype=np.int64)

    print(f"=== 正在注入错误 ===")
    print(f"  输入文件: {input_fastq}")
    if profile is not None:
        prov = profile.provenance
        print(f"  加噪模式: D3 经验轮廓 ({profile.path.name}, mode={prov.get('mode')}, "
              f"measured={profile.measured}, scale={profile.scale:g})")
        if not profile.measured:
            print("  ⚠ 警告  : 该轮廓为 NOT_MEASURED 先验模型，产物不得表述为真实经验噪声数据集")
        print(f"  预期替换: 全程 {profile.summary()['expected_sub_rate']:.4%}, "
              f"前30cycle {profile.summary()['expected_sub_rate_first30']:.4%}, "
              f"后30cycle {profile.summary()['expected_sub_rate_last30']:.4%}")
        print(f"  下采样  : coverage={coverage:.2f}, seed={seed}")
    else:
        print(f"  扰动参数: sub={sub_rate:.3%}, ins={ins_rate:.3%}, del={del_rate:.3%}, coverage={coverage:.2f}, seed={seed}")

    with out_fastq.open("w", encoding="utf-8") as out_f:
        for header, seq, plus, qual in parse_fastq(input_fastq):
            total_in += 1
            # 覆盖度下采样
            if coverage < 1.0 and rng.random() > coverage:
                continue

            if profile is not None:
                mut_seq, mut_qual, n_s, n_i, n_d, ev = mutate_sequence_profile(
                    seq, profile, rng, fixed_len=fixed_len
                )
                # 逐 cycle 复核：只认加噪过程当场记的账（插删会让位置错位）
                for k in ev["obs_cycles"]:
                    if k < cyc_len:
                        cyc_obs[k] += 1
                for k in ev["sub_cycles"]:
                    if k < cyc_len:
                        cyc_sub[k] += 1
                for k, qv in enumerate(ev["q"]):
                    if k < cyc_len:
                        q_obs[k] += 1
                        q_sum[k] += qv
            else:
                mut_seq, mut_qual, n_s, n_i, n_d = mutate_sequence(
                    seq, qual, sub_rate, ins_rate, del_rate, rng, fixed_len=fixed_len
                )
            out_f.write(f"{header}\n{mut_seq}\n{plus}\n{mut_qual}\n")
            total_out += 1
            total_bases += len(seq)
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
            "mode": "empirical_profile" if profile is not None else "uniform_controlled",
            "sub_rate": None if profile is not None else sub_rate,
            "ins_rate": None if profile is not None else ins_rate,
            "del_rate": None if profile is not None else del_rate,
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
            "total_bases": total_bases,
            "actual_sub_rate": (sum_sub / total_bases) if total_bases else 0.0,
            "actual_ins_rate": (sum_ins / total_bases) if total_bases else 0.0,
            "actual_del_rate": (sum_del / total_bases) if total_bases else 0.0,
        },
    }

    if profile is not None:
        meta["tier"] = "D3"
        meta["description"] = "真实测序经验误差轮廓驱动的物理加噪数据集"
        meta["empirical_profile"] = profile.summary()
        with np.errstate(divide="ignore", invalid="ignore"):
            realized = np.where(cyc_obs > 0, cyc_sub / np.maximum(cyc_obs, 1), np.nan)
            q_mean = np.where(q_obs > 0, q_sum / np.maximum(q_obs, 1), np.nan)
        meta["realized_cycle_stats"] = {
            "note": "逐 cycle 实际替换率，由加噪过程当场记账（不是事后逐位比对，"
                    "后者会把插删造成的错位误计为替换）。可直接与 "
                    "empirical_profile.expected_* 对拍。",
            "sub_rate_first30": float(np.nanmean(realized[:30])) if cyc_len else None,
            "sub_rate_last30": float(np.nanmean(realized[-30:])) if cyc_len else None,
            "sub_rate_per_cycle": [None if not np.isfinite(v) else round(float(v), 8)
                                   for v in realized] if cyc_len else [],
            "q_mean_per_cycle": [None if not np.isfinite(v) else round(float(v), 4)
                                 for v in q_mean] if cyc_len else [],
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
    if profile is not None and total_bases:
        rs = meta["realized_cycle_stats"]
        print(f"    实测率: sub={sum_sub / total_bases:.4%}, "
              f"前30cycle={rs['sub_rate_first30']:.4%}, 后30cycle={rs['sub_rate_last30']:.4%}")
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
    parser.add_argument("--profile-from", type=Path, default=None,
                        help="D3 经验轮廓 JSON (tools/extract_error_profile.py 产物)；"
                             "给定后忽略 --sub-rate/--ins-rate/--del-rate")
    parser.add_argument("--profile-scale", type=float, default=1.0,
                        help="经验轮廓误差倍率 (G5 鲁棒性扫描用，1.0=原样)")
    parser.add_argument("--cycle-map", choices=["clamp", "stretch"], default="clamp",
                        help="读长与轮廓 cycle 数不一致时的映射方式 (默认 clamp)")

    args = parser.parse_args()

    if not args.input_fastq.is_file():
        print(f"错误: 找不到输入 FASTQ 文件: {args.input_fastq}", file=sys.stderr)
        sys.exit(1)

    if args.output_dir.resolve() == args.input_fastq.parent.resolve():
        print("错误: 输出目录不能与输入目录相同 (门禁要求严禁覆盖原数据)！", file=sys.stderr)
        sys.exit(1)

    profile = None
    if args.profile_from is not None:
        if not args.profile_from.is_file():
            print(f"错误: 找不到经验轮廓文件: {args.profile_from}", file=sys.stderr)
            sys.exit(1)
        if args.profile_scale <= 0:
            print("错误: --profile-scale 必须为正数", file=sys.stderr)
            sys.exit(1)
        try:
            profile = EmpiricalProfile(args.profile_from, scale=args.profile_scale,
                                       cycle_map=args.cycle_map)
        except (ValueError, KeyError) as exc:
            print(f"错误: 经验轮廓无法加载: {exc}", file=sys.stderr)
            sys.exit(1)
        if any(r > 0 for r in (args.sub_rate, args.ins_rate, args.del_rate)):
            print("提示: --profile-from 模式下均匀速率参数被忽略（误差由轮廓决定）",
                  file=sys.stderr)
        _sc = (profile.raw.get("smoothing") or {}).get("self_check")
        if _sc is None:
            print("警告: 该轮廓没有 smoothing.self_check 字段（旧版提取器产物），"
                  "无法确认它蕴含的错误率与自报的 error_rate 一致；建议重新提取。",
                  file=sys.stderr)
        elif not _sc.get("consistent", True):
            print("警告: 该轮廓自检未通过——矩阵蕴含替换率偏离自报值 %+.2f%%、"
                  "Ti/Tv 偏离 %.2f%%。本次实际注入的噪声与轮廓宣称的不是同一个东西。"
                  % (_sc.get("sub_rate_inflation", 0.0) * 100,
                     _sc.get("ti_tv_rel_dev", 0.0) * 100), file=sys.stderr)

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
        profile=profile,
    )


if __name__ == "__main__":
    main()

