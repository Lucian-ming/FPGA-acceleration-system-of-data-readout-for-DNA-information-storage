#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""tests/test_empirical_noise_profile.py —— D3 经验误差轮廓「提取 -> 加噪 -> 重提取」闭环测试套件

被测对象：`tools/extract_error_profile.py`（轮廓提取）与 `tools/mutate_reads.py --profile-from`
（轮廓驱动加噪）。依据 docs/reference/d3-wetlab-survey.md §5.1 与 docs/13 §7.3 的 R9 判据。

本套件刻意**不满足于「跑得通」**。真实测序数据没有真值可比，所以这里合成一份
**误差轮廓已知**的数据集（3' 端指数翘尾 + 转换/颠换不等概 + Q 随 cycle 衰减），
再要求两个工具把它还原出来：

1. 测试级 1（提取还原度）：从合成 FASTQ 还原逐 cycle 替换率、4x4 方向矩阵、Ti/Tv、
   翘尾指数 beta 与 Q 模型，逐项对真值设阈；
2. 测试级 2（轮廓自洽性）：`substitution_matrix` 蕴含的替换率与 Ti/Tv 必须与同一份 JSON
   自报的 `error_rate` / `ti_tv_ratio` 一致——加噪端只读前者，两者不等就意味着
   「轮廓宣称的噪声」与「实际注入的噪声」不是同一个东西；
3. 测试级 3（往返闭环）：干净读段经轮廓加噪后重新提取，替换率与 Ti/Tv 必须回到源轮廓；
4. 测试级 4（**鉴别力故障注入**）：把两个已修缺陷分别注回去，断言判据**确实变红**。
   没有这一级，前三级只能证明「跑得通」，不能证明「用错了会被发现」；
5. 测试级 5（实际操作数与定长适配）：manifest 必须报告**实际发生**的替换/插入/缺失次数
   与逐 cycle 台账，而不是只回显名义参数；定长输出必须如实命名为「插删加定长适配」；
6. 测试级 6（先验轮廓的事实边界）：`--parametric-prior` 产物必须带 NOT_MEASURED 标记，
   且该标记必须传染给用它加噪的数据集 manifest。

【已修缺陷，本套件是其常驻回归哨兵】
  * D3-1：Laplace 伪计数原先施加于整个 4x4 张量，等价于给每行注入
    `3*pc/(n+4*pc)` 的常数错误率地板（n=1500 时 0.109%），使加噪实际替换率比轮廓
    自报值高 14.9%（前 30 cycle 高 71.3%）。判据量：`smoothing.self_check.sub_rate_inflation`。
  * D3-2：方向伪计数向**均匀分布**收缩（均匀方向 Ti/Tv=0.5），在早期低覆盖 cycle
    （每 ref base 仅 ~2.4 次替换事件 vs 伪计数 1.5）把 Ti/Tv 从 2.04 稀释到 1.73。
    判据量：`smoothing.self_check.ti_tv_rel_dev`（必须用**逐 cycle**矩阵计算，
    用聚合矩阵算会完全看不见）。
"""

from __future__ import annotations

import importlib.util
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import numpy as np

REPO_ROOT = Path(__file__).resolve().parent.parent
TOOLS_DIR = REPO_ROOT / "tools"
EXTRACTOR = TOOLS_DIR / "extract_error_profile.py"
MUTATOR = TOOLS_DIR / "mutate_reads.py"

BASES = "ACGT"
B2I = {b: i for i, b in enumerate(BASES)}
TRANSITION = {"A": "G", "G": "A", "C": "T", "T": "C"}
TI_PAIRS = [("A", "G"), ("G", "A"), ("C", "T"), ("T", "C")]

# --- 合成数据的真值参数（测试断言全部以此为基准）---
N_REF, READ_LEN, N_READS, SEED = 40, 120, 6000, 20260909
TRUTH_P0, TRUTH_ALPHA_LAST, TRUTH_BETA = 0.0015, 0.030, 0.045
TRUTH_TI_WEIGHT = 4.0            # 转换权重 4 : 两种颠换各 1 -> 真值 Ti/Tv = 4/2 = 2.0
TRUTH_TI_TV = TRUTH_TI_WEIGHT / 2.0
Q_TOP, Q_DROP, Q_MISMATCH_GAP = 38.0, 8.0, 10.0


def _load_extractor():
    """以模块方式载入提取器，供测试级 4 直接调用内部函数做故障注入。"""
    spec = importlib.util.spec_from_file_location("eep", EXTRACTOR)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def truth_sub_rate(L: int = READ_LEN) -> "np.ndarray":
    """真值逐 cycle 替换率：P(c) = P0 + alpha_last * exp(beta * (c - L))，c 从 1 计。"""
    c = np.arange(1, L + 1)
    return TRUTH_P0 + TRUTH_ALPHA_LAST * np.exp(TRUTH_BETA * (c - L))


def truth_direction_matrix() -> "np.ndarray":
    """真值方向矩阵：给定发生替换后，错成哪个碱基的 3 选 1 分布。"""
    m = np.zeros((4, 4))
    for i, b in enumerate(BASES):
        w = np.zeros(4)
        for j, o in enumerate(BASES):
            if o != b:
                w[j] = TRUTH_TI_WEIGHT if o == TRANSITION[b] else 1.0
        m[i] = w / w.sum()
    return m


def synth_dataset(out_dir: Path) -> dict:
    """生成误差轮廓已知的合成数据集：ref.fa / clean.fq（无错）/ noisy.fq（按真值加噪）。"""
    rng = np.random.default_rng(SEED)
    out_dir.mkdir(parents=True, exist_ok=True)
    refs = ["".join(rng.choice(list(BASES), size=READ_LEN)) for _ in range(N_REF)]
    (out_dir / "ref.fa").write_text(
        "".join(f">oligo_{i:03d}\n{s}\n" for i, s in enumerate(refs)))

    p = truth_sub_rate()
    dmat = truth_direction_matrix()
    q_match = Q_TOP - Q_DROP * (np.arange(READ_LEN) / (READ_LEN - 1))
    q_mis = q_match - Q_MISMATCH_GAP

    n_sub = 0
    with (out_dir / "clean.fq").open("w") as fc, (out_dir / "noisy.fq").open("w") as fn:
        for r in range(N_READS):
            ri = int(rng.integers(0, N_REF))
            ref = refs[ri]
            fc.write("@read%d_ref%d\n%s\n+\n%s\n" % (r, ri, ref, chr(33 + 38) * len(ref)))
            seq, quals = [], []
            for c, b in enumerate(ref):
                if rng.random() < p[c]:
                    nb = BASES[int(rng.choice(4, p=dmat[B2I[b]]))]
                    n_sub += 1
                    q = int(round(rng.normal(q_mis[c], 3.0)))
                else:
                    nb, q = b, int(round(rng.normal(q_match[c], 3.0)))
                seq.append(nb)
                quals.append(min(60, max(2, q)))
            fn.write("@read%d_ref%d\n%s\n+\n%s\n"
                     % (r, ri, "".join(seq), "".join(chr(33 + q) for q in quals)))
    return {"n_sub": n_sub, "sub_rate_mean": float(p.mean())}


def run_extractor(fastq: Path, ref: Path, out: Path, *extra) -> dict:
    cmd = [sys.executable, str(EXTRACTOR), "--fastq", str(fastq),
           "--reference", str(ref), "-o", str(out), *extra]
    cp = subprocess.run(cmd, capture_output=True, text=True)
    if cp.returncode != 0:
        raise AssertionError("提取器失败 rc=%d\n%s\n%s" % (cp.returncode, cp.stdout, cp.stderr))
    return json.loads(out.read_text())


def run_mutator(fastq: Path, out_dir: Path, profile: Path, *extra,
                want_stderr: bool = False):
    cmd = [sys.executable, str(MUTATOR), "--input-fastq", str(fastq),
           "--output-dir", str(out_dir), "--profile-from", str(profile), *extra]
    cp = subprocess.run(cmd, capture_output=True, text=True)
    if cp.returncode != 0:
        raise AssertionError("加噪器失败 rc=%d\n%s\n%s" % (cp.returncode, cp.stdout, cp.stderr))
    man = json.loads((out_dir / "mutation_manifest.json").read_text())
    return (man, cp.stderr) if want_stderr else man


def cycle_rates(profile: dict) -> "np.ndarray":
    return np.array([x if x is not None else np.nan
                     for x in profile["cycles"]["error_rate"]], dtype=float)


def binned(a: "np.ndarray", w: int = 10) -> "np.ndarray":
    n = len(a) // w
    return a[:n * w].reshape(n, w).mean(axis=1)


def direction_of(matrix4x4) -> "np.ndarray":
    """把 4x4 转移矩阵的每行非对角部分重新归一，得到纯方向分布。"""
    m = np.asarray(matrix4x4, dtype=float)
    out = np.zeros((4, 4))
    for i in range(4):
        off = m[i].copy()
        off[i] = 0.0
        s = off.sum()
        out[i] = off / s if s > 0 else off
    return out


def titv_of_cycle_matrix(profile: dict) -> float:
    """按加噪端真正读的【逐 cycle】矩阵算 Ti/Tv（用聚合矩阵算会看不见 D3-2）。"""
    m = np.array(profile["cycles"]["substitution_matrix"], dtype=float)
    obs = np.array(profile["cycles"]["substitution_counts"], dtype=float).sum(axis=2)
    exp = np.einsum("cij,ci->ij", m, obs)
    np.fill_diagonal(exp, 0.0)
    ti = sum(exp[B2I[a], B2I[b]] for a, b in TI_PAIRS)
    return float(ti / (exp.sum() - ti))


class EmpiricalNoiseProfileTest(unittest.TestCase):
    """D3 经验轮廓提取/加噪闭环。合成数据与三次工具调用在 setUpClass 里只做一次。"""

    @classmethod
    def setUpClass(cls):
        cls.tmp = Path(tempfile.mkdtemp(prefix="d3_profile_test_"))
        cls.truth = synth_dataset(cls.tmp / "synth")
        s = cls.tmp / "synth"
        # 1) 从带真值噪声的读段提取轮廓
        cls.profile = run_extractor(s / "noisy.fq", s / "ref.fa", cls.tmp / "profile.json")
        # 2) 用该轮廓给干净读段加噪
        cls.manifest = run_mutator(s / "clean.fq", cls.tmp / "rt", cls.tmp / "profile.json",
                                   "--seed", "1")
        # 3) 从加噪结果重新提取，构成闭环
        cls.reprofile = run_extractor(cls.tmp / "rt" / "mutated_clean.fq", s / "ref.fa",
                                      cls.tmp / "reprofile.json")

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    # ---------------- 测试级 1：提取还原度 ----------------
    def test_l1_cycle_rate_shape_recovered(self):
        """逐 cycle 替换率形状（3' 翘尾）必须被还原。"""
        t = binned(truth_sub_rate())
        e = binned(cycle_rates(self.profile))
        r = float(np.corrcoef(t, e)[0, 1])
        self.assertGreaterEqual(r, 0.99, "逐 cycle 替换率与真值相关性只有 %.5f" % r)
        rel = float(np.max(np.abs(t - e) / t))
        self.assertLess(rel, 0.35, "某个 cycle 分箱替换率相对真值偏差 %.1f%%" % (rel * 100))

    def test_l1_substitution_events_recalled(self):
        """替换事件总数召回率必须接近 1（这是提取器有没有漏比对的硬指标）。"""
        recall = self.profile["counts"]["substitutions"] / self.truth["n_sub"]
        self.assertGreater(recall, 0.97, "替换召回仅 %.4f" % recall)
        self.assertLess(recall, 1.03, "替换数虚高 %.4f，疑似把插删错位误计为替换" % recall)

    def test_l1_direction_matrix_and_titv(self):
        """4x4 方向矩阵与 Ti/Tv 必须还原真值（转换 : 颠换 = 4 : 1+1）。"""
        rec = direction_of(self.profile["aggregate"]["substitution_matrix"])
        err = float(np.max(np.abs(rec - truth_direction_matrix())))
        self.assertLess(err, 0.05, "方向矩阵最大绝对误差 %.4f" % err)
        titv = self.profile["aggregate"]["ti_tv_ratio"]
        self.assertAlmostEqual(titv, TRUTH_TI_TV, delta=0.20,
                               msg="Ti/Tv 还原为 %.4f，真值 %.2f" % (titv, TRUTH_TI_TV))

    def test_l1_tail_rise_and_quality_model(self):
        """翘尾指数 beta 与 Q 模型（match/mismatch 分离）必须还原。"""
        fit = self.profile["tail_rise_fit"]
        self.assertTrue(fit.get("fitted"))
        self.assertAlmostEqual(fit["beta"], TRUTH_BETA, delta=0.010,
                               msg="翘尾 beta=%.5f，真值 %.3f" % (fit["beta"], TRUTH_BETA))
        self.assertGreater(fit["r2"], 0.90)
        qm = np.array([x for x in self.profile["cycles"]["q_match_mean"] if x is not None])
        qx = np.array([x for x in self.profile["cycles"]["q_mismatch_mean"] if x is not None])
        truth_qm = Q_TOP - Q_DROP * (np.arange(READ_LEN) / (READ_LEN - 1))
        self.assertLess(float(np.max(np.abs(qm - truth_qm[:len(qm)]))), 1.0,
                        "Q(match) 逐 cycle 均值偏离真值超过 1 phred")
        gap = float(np.mean(qm[:len(qx)] - qx))
        self.assertAlmostEqual(gap, Q_MISMATCH_GAP, delta=1.0,
                               msg="match/mismatch 质量差 %.3f，真值 %.1f" % (gap, Q_MISMATCH_GAP))

    # ---------------- 测试级 2：轮廓自洽性 ----------------
    def test_l2_self_check_present_and_passing(self):
        """轮廓必须自带自洽性自检，且必须通过。"""
        sc = self.profile["smoothing"]["self_check"]
        self.assertTrue(sc["consistent"],
                        "轮廓自检未通过：率偏差 %+.2f%%，Ti/Tv 偏差 %.2f%%"
                        % (sc["sub_rate_inflation"] * 100, sc["ti_tv_rel_dev"] * 100))
        self.assertLessEqual(abs(sc["sub_rate_inflation"]), 0.02)
        self.assertLessEqual(sc["ti_tv_rel_dev"], 0.02)

    def test_l2_matrix_implies_reported_rate(self):
        """【D3-1 判据量】加噪端只读 substitution_matrix，它蕴含的替换率必须等于自报 error_rate。"""
        sc = self.profile["smoothing"]["self_check"]
        self.assertAlmostEqual(sc["matrix_implied_sub_rate"], sc["measured_sub_rate"],
                               delta=sc["measured_sub_rate"] * 0.02,
                               msg="矩阵蕴含率 %.6f 与实测率 %.6f 不一致（Laplace 平滑注入了错误率地板）"
                                   % (sc["matrix_implied_sub_rate"], sc["measured_sub_rate"]))

    def test_l2_cycle_matrix_preserves_titv(self):
        """【D3-2 判据量】逐 cycle 矩阵蕴含的 Ti/Tv 必须等于实测 Ti/Tv。"""
        got = titv_of_cycle_matrix(self.profile)
        want = self.profile["aggregate"]["ti_tv_ratio"]
        self.assertLess(abs(got - want) / want, 0.02,
                        "逐 cycle 矩阵 Ti/Tv=%.4f 偏离实测 %.4f（方向伪计数把偏好拉向均匀）"
                        % (got, want))

    def test_l2_inconsistent_profile_warns_downstream(self):
        """自检不通过的轮廓被拿去加噪时，必须在 stderr 与 manifest 里都留下警告。

        否则一份被平滑污染的轮廓可以静默地生产出「看起来很正经」的派生数据集。
        """
        bad_profile = self.tmp / "warn_profile.json"
        run_extractor(self.tmp / "synth" / "noisy.fq", self.tmp / "synth" / "ref.fa",
                      bad_profile, "--rate-pseudocount", "0.5")
        man, err = run_mutator(self.tmp / "synth" / "clean.fq", self.tmp / "warn_out",
                               bad_profile, "--seed", "5", want_stderr=True)
        self.assertIn("自检未通过", err, "加噪器没有对不自洽的轮廓告警")
        ep = man["empirical_profile"]
        self.assertIn("profile_self_check_warning", ep,
                      "manifest 未记录轮廓不自洽的警告")
        self.assertFalse(ep["profile_self_check"]["consistent"])
        # 反面：自洽的轮廓不得误报
        self.assertNotIn("profile_self_check_warning", self.manifest["empirical_profile"],
                         "自洽轮廓被误判为不自洽（假阳性）")
        self.assertTrue(self.manifest["empirical_profile"]["profile_self_check"]["consistent"])

    # ---------------- 测试级 3：往返闭环 ----------------
    def test_l3_round_trip_rate_closes(self):
        """干净读段按轮廓加噪后重提取，替换率必须回到源轮廓。"""
        src = self.profile["aggregate"]["sub_rate"]
        rt = self.reprofile["aggregate"]["sub_rate"]
        self.assertLess(abs(rt - src) / src, 0.05,
                        "往返替换率 %.6f vs 源轮廓 %.6f，偏差 %.2f%%"
                        % (rt, src, abs(rt - src) / src * 100))

    def test_l3_round_trip_titv_closes(self):
        """往返后 Ti/Tv 必须守住——这是方向分布有没有被平滑破坏的直接证据。"""
        src = self.profile["aggregate"]["ti_tv_ratio"]
        rt = self.reprofile["aggregate"]["ti_tv_ratio"]
        self.assertLess(abs(rt - src) / src, 0.06,
                        "往返 Ti/Tv %.4f vs 源轮廓 %.4f，偏差 %.2f%%"
                        % (rt, src, abs(rt - src) / src * 100))

    def test_l3_round_trip_tail_shape_closes(self):
        """往返后逐 cycle 形状（翘尾）必须守住。"""
        a, b = binned(cycle_rates(self.profile)), binned(cycle_rates(self.reprofile))
        r = float(np.corrcoef(a, b)[0, 1])
        self.assertGreaterEqual(r, 0.99, "往返逐 cycle 相关性只有 %.5f" % r)

    # ---------------- 测试级 4：鉴别力故障注入 ----------------
    def test_l4_fault_injection_rate_floor_is_caught(self):
        """把缺陷 D3-1 注回去（--rate-pseudocount 0.5），自检必须变红。

        没有这一级，测试级 2 只能证明「当前实现恰好一致」，不能证明判据有鉴别力。
        """
        out = self.tmp / "fault_d3_1.json"
        bad = run_extractor(self.tmp / "synth" / "noisy.fq", self.tmp / "synth" / "ref.fa",
                            out, "--rate-pseudocount", "0.5")
        sc = bad["smoothing"]["self_check"]
        self.assertFalse(sc["consistent"], "注入错误率地板后自检竟然仍判 PASS —— 判据无鉴别力")
        self.assertGreater(sc["sub_rate_inflation"], 0.10,
                           "错误率地板只抬高了 %.2f%%，鉴别力不足" % (sc["sub_rate_inflation"] * 100))
        # 而修复版在同一份数据上必须是绿的（证明红/绿不是恒定的）
        self.assertTrue(self.profile["smoothing"]["self_check"]["consistent"])

    def test_l4_fault_injection_uniform_direction_prior_is_caught(self):
        """把缺陷 D3-2 注回去（方向先验退回均匀），Ti/Tv 判据必须变红。"""
        eep = _load_extractor()
        counts = np.array(self.profile["cycles"]["substitution_counts"], dtype=float)
        obs = counts.sum(axis=2)
        agg = counts.sum(axis=0)
        d = agg.copy()
        np.fill_diagonal(d, 0.0)
        dir_prior = d / d.sum(axis=1, keepdims=True)
        measured = self.profile["aggregate"]["ti_tv_ratio"]

        def titv(m):
            exp = np.einsum("cij,ci->ij", m, obs)
            np.fill_diagonal(exp, 0.0)
            ti = sum(exp[B2I[a], B2I[b]] for a, b in TI_PAIRS)
            return float(ti / (exp.sum() - ti))

        good = titv(eep.rate_preserving_matrix(counts, 0.5, 0.0, dir_prior=dir_prior))
        bad = titv(eep.rate_preserving_matrix(counts, 0.5, 0.0, dir_prior=None))
        self.assertLess(abs(good - measured) / measured, 0.02,
                        "修复版方向先验下 Ti/Tv 偏差 %.2f%%" % (abs(good - measured) / measured * 100))
        self.assertGreater(abs(bad - measured) / measured, 0.10,
                           "均匀方向先验只让 Ti/Tv 偏了 %.2f%%，鉴别力不足"
                           % (abs(bad - measured) / measured * 100))

    # ---------------- 测试级 5：实际操作数与定长适配 ----------------
    def test_l5_manifest_reports_actual_operation_counts(self):
        """manifest 必须报告实际发生的操作数与实测率，而不是只回显名义参数。"""
        out = self.manifest["output"]
        for key in ("total_substitutions", "total_insertions", "total_deletions",
                    "total_bases", "actual_sub_rate", "actual_ins_rate", "actual_del_rate"):
            self.assertIn(key, out, "manifest 缺少实际操作数字段 %s" % key)
        self.assertGreater(out["total_substitutions"], 0)
        # 经验轮廓模式下名义速率参数必须为 null，避免被误读成实际注入率
        self.assertIsNone(self.manifest["mutation_parameters"]["sub_rate"])
        self.assertEqual(self.manifest["mutation_parameters"]["mode"], "empirical_profile")
        # 实测率必须与实际计数自洽
        self.assertAlmostEqual(out["actual_sub_rate"],
                               out["total_substitutions"] / out["total_bases"], places=9)

    def test_l5_realized_cycle_ledger_matches_expectation(self):
        """逐 cycle 台账必须存在，且与轮廓的期望值对得上（含前/后 30 cycle 分段）。"""
        rc = self.manifest["realized_cycle_stats"]
        ep = self.manifest["empirical_profile"]
        self.assertEqual(len(rc["sub_rate_per_cycle"]), READ_LEN)
        for key in ("sub_rate_first30", "sub_rate_last30", "q_mean_per_cycle", "note"):
            self.assertIn(key, rc, "逐 cycle 台账缺少字段 %s" % key)
        self.assertLess(abs(rc["sub_rate_last30"] - ep["expected_sub_rate_last30"])
                        / ep["expected_sub_rate_last30"], 0.10)
        # 翘尾必须真的在输出数据里出现，而不是只在轮廓 JSON 里
        self.assertGreater(rc["sub_rate_last30"], rc["sub_rate_first30"] * 3,
                           "加噪结果没有体现 3' 端翘尾")

    def test_l5_fixed_length_adaptation_is_named_not_claimed_as_variable(self):
        """定长输出必须如实标记 fixed_len，且所有读段长度与输入一致（插删加定长适配）。"""
        self.assertTrue(self.manifest["mutation_parameters"]["fixed_len"],
                        "默认应为定长适配模式")
        lens = set()
        with (self.tmp / "rt" / "mutated_clean.fq").open() as f:
            for i, line in enumerate(f):
                if i % 4 == 1:
                    lens.add(len(line.strip()))
        self.assertEqual(lens, {READ_LEN},
                         "定长适配下出现了非 %d nt 的读段：%s" % (READ_LEN, sorted(lens)))

    # ---------------- 测试级 6：先验轮廓的事实边界 ----------------
    def test_l6_parametric_prior_is_marked_not_measured_and_taints_manifest(self):
        """先验轮廓必须自带 NOT_MEASURED 标记，且该标记必须传染给下游数据集。"""
        prior = self.tmp / "prior.json"
        cp = subprocess.run([sys.executable, str(EXTRACTOR), "--parametric-prior",
                             "illumina_pe150", "-o", str(prior)],
                            capture_output=True, text=True)
        self.assertEqual(cp.returncode, 0, cp.stderr)
        pj = json.loads(prior.read_text())
        self.assertFalse(pj["provenance"]["measured"])
        self.assertIn("NOT_MEASURED", pj["provenance"]["WARNING"])
        man = run_mutator(self.tmp / "synth" / "clean.fq", self.tmp / "prior_out", prior,
                          "--seed", "3")
        ep = man["empirical_profile"]
        self.assertFalse(ep["measured"])
        self.assertIn("WARNING", ep,
                      "用 NOT_MEASURED 先验加噪的数据集 manifest 未继承警告，"
                      "可能被误当成真实经验噪声数据集")


if __name__ == "__main__":
    unittest.main(verbosity=2)
