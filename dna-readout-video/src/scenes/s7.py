# -*- coding: utf-8 -*-
"""S7 — 客户端验收：上位机（PC）侧的两道硬判据。

上：判据一「板端校验子全零」与判据二「载荷 SHA-256 一致」并排。
中：8,100 B → 54,000 bit → 按 input_bytes 截断 → 载荷上限 6,750 B 的收窄链。
下：四级取证只用于失败定位（不改判据），以及最终判定 PASS / 拒绝。
"""
import math

from engine.gfx import (clamp, lerp, ramp, ease_out, pulse,
                        WEIGHT_BOLD, WEIGHT_NORMAL, WEIGHT_MEDIUM)
from scenes import common as C

TITLE = "客户端验收"

# ---------------------------------------------------------------- 两道判据
GATE_Y, GATE_H = 196, 250
GA_X, GA_W = 112, 820
GB_X, GB_W = 956, 852

NCOL, NROW = 27, 2
CELL_W, CELL_H, CELL_GAP = 24, 26, 4
GRID_X = GA_X + 26
GRID_Y = GATE_Y + 96

# ---------------------------------------------------------------- 收窄链
PATH_Y, PATH_H = 474, 148
PATH_X0, PATH_BW, PATH_GAP = 128, 368, 64

# ---------------------------------------------------------------- 底部
FOR_Y, FOR_H = 648, 132
VER_Y, VER_H = 800, 84

# R0.83 SE150 全量端到端载荷摘要（docs/01 §1、docs/09 记录值）
DIGEST = "fcd0cf90 … f2c3"


def gate_a(f, t, a, l1, l2):
    """判据一：客户端本地重算的 10,800 位校验子必须全零。"""
    if a <= 0:
        return
    f.rect(GA_X, GATE_Y, GA_W, GATE_H, C.PANEL, alpha=0.92 * a, r=3)
    f.rect_stroke(GA_X, GATE_Y, GA_W, GATE_H, C.OKC, lw=1.4, r=3, alpha=0.34 * a)
    f.rect(GA_X, GATE_Y, 4, GATE_H, C.OKC, alpha=0.85 * a, r=2)
    f.text("判据一 · 校验子全零", GA_X + 26, GATE_Y + 20, 24, C.OKC, C.SANS,
           WEIGHT_MEDIUM, alpha=a)
    f.text("本地重算 10,800 条校验式", GA_X + GA_W - 26, GATE_Y + 24, 19,
           C.INK3, align="right", alpha=a * 0.9)

    t0 = l1 + 0.25
    n = 0
    for r in range(NROW):
        for c in range(NCOL):
            k = ramp(t, t0 + 0.012 * (r * NCOL + c), t0 + 0.012 * (r * NCOL + c) + 0.30)
            if k <= 0:
                continue
            x = GRID_X + c * (CELL_W + CELL_GAP)
            y = GRID_Y + r * (CELL_H + 10)
            f.rect(x, y, CELL_W, CELL_H, C.OKC, alpha=0.12 * k * a, r=3)
            f.rect_stroke(x, y, CELL_W, CELL_H, C.OKC, lw=1.0, r=3,
                          alpha=0.42 * k * a)
            f.text("0", x + CELL_W / 2, y + 4, 15, C.OKC, C.MONO,
                   align="center", alpha=k * a)
            n += 1

    if n >= NCOL * NROW:
        k = ramp(t, l2 - 0.5, l2 + 0.2)
        if k > 0:
            f.text("每格 200 bit · 54 格 = 10,800 bit 全为 0",
                   GRID_X, GRID_Y + NROW * (CELL_H + 10) + 2, 18, C.INK3,
                   alpha=k * a * 0.95)

    kp = ramp(t, l2 - 0.2, l2 + 0.5)
    if kp > 0:
        f.text("PASS", GA_X + 26, GATE_Y + GATE_H - 60, 32, C.OKC, C.MONO,
               WEIGHT_BOLD, alpha=kp * a)
        f.text("syndrome = 0 / 10,800", GA_X + 148, GATE_Y + GATE_H - 50, 21,
               C.INK2, C.MONO, alpha=kp * a * 0.95)


def gate_b(f, t, a, l2, l3):
    """判据二：恢复出来的载荷 SHA-256 必须和原文一致。"""
    if a <= 0:
        return
    f.rect(GB_X, GATE_Y, GB_W, GATE_H, C.PANEL, alpha=0.92 * a, r=3)
    f.rect_stroke(GB_X, GATE_Y, GB_W, GATE_H, C.OKC, lw=1.4, r=3, alpha=0.34 * a)
    f.rect(GB_X, GATE_Y, 4, GATE_H, C.OKC, alpha=0.85 * a, r=2)
    f.text("判据二 · 载荷 SHA-256", GB_X + 26, GATE_Y + 20, 24, C.OKC, C.SANS,
           WEIGHT_MEDIUM, alpha=a)
    f.text("比的是整份载荷的 SHA-256 摘要", GB_X + GB_W - 26, GATE_Y + 24, 19,
           C.INK3, align="right", alpha=a * 0.9)

    rows = [("原文", C.INK2), ("恢复后", C.INK2)]
    for i, (lab, col) in enumerate(rows):
        k = ramp(t, l2 + 0.3 + 0.45 * i, l2 + 0.9 + 0.45 * i)
        if k <= 0:
            continue
        y = GATE_Y + 68 + i * 54
        f.text(lab, GB_X + 26, y + 6, 20, C.INK3, alpha=k * a)
        f.text("SHA-256", GB_X + 110, y + 6, 20, C.INK3, C.MONO,
               alpha=k * a * 0.9)
        f.rect(GB_X + 218, y - 2, 372, 38, C.PANEL_HI, alpha=0.95 * k * a, r=2)
        f.rect_stroke(GB_X + 218, y - 2, 372, 38, C.EDGE, lw=1.0, r=2,
                      alpha=0.8 * k * a)
        f.text(DIGEST, GB_X + 236, y + 6, 21, col, C.MONO,
               alpha=k * a * 0.95)

    ke = ramp(t, l2 + 1.3, l2 + 1.9)
    if ke > 0:
        f.text("=", GB_X + 612, GATE_Y + 84, 30, C.OKC, C.MONO, WEIGHT_BOLD,
               align="center", alpha=ke * a)
        f.text("相等", GB_X + 660, GATE_Y + 90, 21, C.OKC, C.SANS,
               alpha=ke * a)
        f.line(GB_X + 26, GATE_Y + 172, GB_X + GB_W - 26, GATE_Y + 172, C.EDGE,
               1.0, alpha=0.6 * ke * a)

    kp = ramp(t, l3 - 0.3, l3 + 0.4)
    if kp > 0:
        f.text("PASS", GB_X + 26, GATE_Y + GATE_H - 62, 34, C.OKC, C.MONO,
               WEIGHT_BOLD, alpha=kp * a)
        f.text("端到端载荷逐位相同（R0.83 SE150 全量）", GB_X + 150,
               GATE_Y + GATE_H - 50, 21, C.INK2, alpha=kp * a * 0.95)



def path_chain(f, t, a, l3):
    """8,100 B → 54,000 bit → input_bytes 截断 → ≤ 6,750 B。"""
    if a <= 0:
        return
    items = [
        ("8,100", "B", "板端回传的结果码字", C.INK),
        ("54,000", "bit", "解交织后取末段为信息位", C.INK),
        ("input_bytes", "", "按原文件长度截断", C.INK2),
        ("≤ 6,750", "B", "载荷上限 = 54,000 ÷ 8", C.S3C),
    ]
    for i, (v, u, lab, col) in enumerate(items):
        k = ramp(t, l3 + 0.15 + 0.30 * i, l3 + 0.55 + 0.30 * i)
        if k <= 0:
            continue
        x = PATH_X0 + i * (PATH_BW + PATH_GAP)
        y = PATH_Y + (1 - ease_out(k)) * 10
        f.rect(x, y, PATH_BW, PATH_H, C.PANEL, alpha=0.88 * k * a, r=3)
        f.rect_stroke(x, y, PATH_BW, PATH_H, C.EDGE, lw=1.2, r=3,
                      alpha=0.9 * k * a)
        f.text(v, x + 24, y + 34, 52 if len(v) < 6 else 40, col, C.MONO,
               WEIGHT_BOLD, alpha=k * a)
        if u:
            w = f.measure(v, 52 if len(v) < 6 else 40, C.MONO, WEIGHT_BOLD)[0]
            f.text(u, x + 26 + w, y + 62, 20, C.INK3, C.MONO, alpha=k * a)
        f.text(lab, x + 24, y + 108, 19, C.INK3, alpha=k * a * 0.95)
        if i < 3:
            kk = ramp(t, l3 + 0.45 + 0.30 * i, l3 + 0.75 + 0.30 * i)
            C.flow_arrow(f, x + PATH_BW + 8, PATH_Y + PATH_H / 2,
                         x + PATH_BW + PATH_GAP - 8, PATH_Y + PATH_H / 2,
                         C.INK3, kk, dur=0.4, lw=2.2)


def forensics(f, t, a, l4):
    """四级逐级比对：每轮板上运行都做，用来定位问题出在哪一级。"""
    if a <= 0:
        return
    f.text("四级逐级比对 · 每轮板上运行都做", 112, FOR_Y, 24, C.INK2, C.SANS,
           WEIGHT_MEDIUM, alpha=a)
    f.text("与黄金向量逐级对照，用来定位问题出在哪一级",
           1808, FOR_Y + 2, 19, C.INK3, align="right", alpha=a * 0.9)

    # 按数据流排序：Stage 1 → Stage 2 → Stage 2.5（PS 水印）→ Stage 3
    names = ["Stage 1 码字", "Stage 2 投票", "Stage 2.5 水印", "Stage 3 解稀"]
    cols = [C.S1C, C.S2C, C.INK3, C.S3C]
    x = 112
    for i, (nm, col) in enumerate(zip(names, cols)):
        k = ramp(t, l4 + 0.2 + 0.18 * i, l4 + 0.6 + 0.18 * i)
        if k <= 0:
            break
        y = FOR_Y + 44
        w = 404
        f.rect(x, y, w, FOR_H - 48, C.PANEL, alpha=0.85 * k * a, r=3)
        f.rect_stroke(x, y, w, FOR_H - 48, col, lw=1.0, r=3, alpha=0.40 * k * a)
        f.text("%d" % (i + 1), x + 20, y + 18, 22, col, C.MONO, WEIGHT_BOLD,
               alpha=k * a * 0.9)
        f.text(nm, x + 52, y + 17, 22, C.INK2, C.SANS, alpha=k * a)
        x += w + 32


def verdict(f, t, a, l4):
    """最终判定：两道都过才算交付。"""
    if a <= 0:
        return
    y = VER_Y
    f.rect(112, y, 796, VER_H, C.OKC, alpha=0.09 * a, r=3)
    f.rect_stroke(112, y, 796, VER_H, C.OKC, lw=1.2, r=3, alpha=0.45 * a)
    f.text("PASS", 140, y + 22, 32, C.OKC, C.MONO, WEIGHT_BOLD, alpha=a)
    f.text("两道都过 → 输出原始文件", 268, y + 30, 22, C.INK2, alpha=a * 0.95)

    f.rect(940, y, 868, VER_H, C.WARNC, alpha=0.09 * a, r=3)
    f.rect_stroke(940, y, 868, VER_H, C.WARNC, lw=1.2, r=3, alpha=0.45 * a)
    f.text("拒绝", 968, y + 22, 32, C.WARNC, C.SANS, WEIGHT_BOLD, alpha=a)
    f.text("任一不过 → 不出文件（不收敛记为 SAFE_NOCONV）", 1080, y + 30, 21,
           C.INK2, alpha=a * 0.95)


def draw(f, t, S):
    C.background(f, t, C.OKC)
    C.chapter(f, 7, "客户端验收", C.OKC, t)
    C.footer(f, 7, 9, t)
    C.header(f, "两道硬判据，都过了才交出文件", t=t)

    l0, l1, l2, l3, l4 = [C.ls(S, i) for i in range(5)]

    k = ramp(t, l0 + 0.1, l0 + 0.8)
    gate_a(f, t, k, l1, l2)
    gate_b(f, t, k, l2, l3)

    a_p = ramp(t, l3 - 0.35, l3 + 0.35)
    path_chain(f, t, a_p, l3)

    a_f = ramp(t, l4 - 0.3, l4 + 0.4)
    forensics(f, t, a_f, l4)
    verdict(f, t, ramp(t, l4 + 1.4, l4 + 2.2), l4)
