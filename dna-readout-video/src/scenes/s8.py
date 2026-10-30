# -*- coding: utf-8 -*-
"""S8 — 实测结果：时延、上传、正确性、长稳。

四条横条共用一条时间轴，靠条长直接比较；正确性用 42 个格子，26 绿 / 16 橙，
不靠颜色单独表达，格子下面同时写 PASS / SAFE_NOCONV。
长稳只呈现最终版制品的一次记录，不并列、不累加历史版本。
"""
import math

from engine.gfx import (clamp, lerp, ramp, ease_out, pulse,
                        WEIGHT_BOLD, WEIGHT_NORMAL, WEIGHT_MEDIUM)
from scenes import common as C

TITLE = "实测结果"

# ---------------------------------------------------------------- 性能面板
PF_X, PF_Y, PF_W, PF_H = 112, 190, 1120, 336
PF_LAB_X = 132
PF_BAR_X = 380
PF_BAR_MAX = 620.0          # px for the slowest run (26.5 s)
PF_TMAX = 26.5
PF_ROWS = [268, 324, 380, 436]
PF_BH = 26

# ---------------------------------------------------------------- 上传面板
UP_X, UP_Y, UP_W, UP_H = 1264, 190, 544, 336
UP_BAR_X = 1372
UP_BAR_MAX = 300.0
UP_TMAX = 4.27

# ---------------------------------------------------------------- 正确性
OK_X, OK_Y, OK_W, OK_H = 112, 548, 1696, 176
CELL_W, CELL_H, CELL_GAP = 30, 44, 7
CELL_X0, CELL_Y0 = 132, 600
N_PASS, N_SAFE = 26, 16

# ---------------------------------------------------------------- 长稳
LR_X, LR_Y, LR_W, LR_H = 112, 752, 1696, 148


def perf(f, t, a, l0, l1):
    """四路 / 十六路 / K=2 / 最终配置，同一坐标轴比长短。"""
    if a <= 0:
        return
    f.rect(PF_X, PF_Y, PF_W, PF_H, C.PANEL, alpha=0.92 * a, r=3)
    f.rect_stroke(PF_X, PF_Y, PF_W, PF_H, C.EDGE, lw=1.0, r=3, alpha=0.85 * a)
    f.text("板端结果段 t_result（中位数）", PF_X + 20, PF_Y + 16, 23, C.INK2,
           C.SANS, WEIGHT_MEDIUM, alpha=a)
    f.text("同一 6,624 B 载荷 · 不含上传与 LDPC · 越小越好", PF_X + PF_W - 20,
           PF_Y + 20, 19, C.INK3, align="right", alpha=a * 0.9)

    rows = [
        ("四路并行", "P4", "26.5", 26.5, C.INK3, "1.00×", l0 + 0.15),
        ("十六路并行", "P16", "8.95", 8.95, C.S1C, "2.97×", l0 + 0.55),
        ("十六路 · K=2", "K=2", "6.06", 6.06, C.S2C, "4.37×", l1 + 0.15),
        ("最终配置", "final", "5.1", 5.1, C.OKC, "5.2×", l1 + 0.55),
    ]
    for i, (lab, tag, val, sec, col, ratio, t_on) in enumerate(rows):
        k = ramp(t, t_on, t_on + 0.55)
        if k <= 0:
            continue
        y = PF_ROWS[i]
        f.text(lab, PF_LAB_X, y - 2, 21, C.INK2, C.SANS, alpha=k * a)
        f.text(tag, PF_LAB_X, y + 26, 17, C.INK3, C.MONO, alpha=k * a * 0.85)
        f.rect(PF_BAR_X, y, PF_BAR_MAX, PF_BH, "#E6DCC9", alpha=0.85 * a, r=2)
        w = PF_BAR_MAX * (sec / PF_TMAX) * ease_out(k)
        f.rect(PF_BAR_X, y, max(3.0, w), PF_BH, col, alpha=0.30 * a, r=5)
        f.rect(PF_BAR_X, y, max(3.0, w), 3, col, alpha=0.85 * k * a, r=2)
        f.text("%s s" % val, PF_BAR_X + w + 16, y + 1, 24, col, C.MONO,
               WEIGHT_BOLD, alpha=k * a)
        if i:
            f.text(ratio, PF_X + PF_W - 24, y + 6, 19, C.INK3,
                   C.MONO, align="right", alpha=k * a * 0.9)

    kf = ramp(t, l1 + 1.1, l1 + 1.7)
    if kf > 0:
        f.line(PF_X + 20, PF_Y + PF_H - 48, PF_X + PF_W - 20, PF_Y + PF_H - 48,
               C.EDGE, 1.0, alpha=0.7 * kf * a)
        f.text("相对四路并行的加速比，标在条右端", PF_X + 20, PF_Y + PF_H - 38,
               18, C.INK3, alpha=kf * a * 0.9)


def upload(f, t, a, l2):
    """上传段：4.27 s → 0.40 s。"""
    if a <= 0:
        return
    f.rect(UP_X, UP_Y, UP_W, UP_H, C.PANEL, alpha=0.92 * a, r=3)
    f.rect_stroke(UP_X, UP_Y, UP_W, UP_H, C.EDGE, lw=1.0, r=3, alpha=0.85 * a)
    f.text("上传段", UP_X + 20, UP_Y + 16, 23, C.INK2, C.SANS, WEIGHT_MEDIUM,
           alpha=a)
    f.text("读入记录 → 板卡", UP_X + UP_W - 20, UP_Y + 20, 18, C.INK3,
           align="right", alpha=a * 0.9)

    rows = [("原始", "4.27", 4.27, C.INK3, l2 + 0.2),
            ("优化后", "0.40", 0.40, C.OKC, l2 + 0.7)]
    for i, (lab, val, sec, col, t_on) in enumerate(rows):
        k = ramp(t, t_on, t_on + 0.6)
        if k <= 0:
            continue
        y = 268 + i * 58
        f.text(lab, UP_X + 20, y - 4, 20, C.INK2, C.SANS, alpha=k * a)
        f.rect(UP_BAR_X, y, UP_BAR_MAX, PF_BH, "#E6DCC9", alpha=0.85 * a, r=2)
        w = UP_BAR_MAX * (sec / UP_TMAX) * ease_out(k)
        f.rect(UP_BAR_X, y, max(3.0, w), PF_BH, col, alpha=0.30 * a, r=5)
        f.rect(UP_BAR_X, y, max(3.0, w), 3, col, alpha=0.85 * k * a, r=2)
        f.text("%s s" % val, UP_BAR_X + w + 12, y + 1, 22, col, C.MONO,
               WEIGHT_BOLD, alpha=k * a)

    kx = ramp(t, l2 + 1.3, l2 + 1.9)
    if kx > 0:
        f.line(UP_X + 20, 400, UP_X + UP_W - 20, 400, C.EDGE, 1.0,
               alpha=0.7 * kx * a)
        C.value_label(f, UP_X + 20, 416, "≈10.7", "×", 48, C.OKC, alpha=kx * a)
        f.text("上传段加速比", UP_X + 20, 476, 19, C.INK3, alpha=kx * a * 0.9)
        f.text("4.27 / 0.40", UP_X + UP_W - 20, 440, 21, C.INK3, C.MONO,
               align="right", alpha=kx * a * 0.85)


def correctness(f, t, a, l3):
    """42 个用例：26 PASS，16 安全拒收，0 静默错误。"""
    if a <= 0:
        return
    f.rect(OK_X, OK_Y, OK_W, OK_H, C.PANEL, alpha=0.92 * a, r=3)
    f.rect_stroke(OK_X, OK_Y, OK_W, OK_H, C.EDGE, lw=1.0, r=3, alpha=0.85 * a)
    f.text("正确性 · 42 个用例", OK_X + 20, OK_Y + 12, 23, C.INK2, C.SANS,
           WEIGHT_MEDIUM, alpha=a)
    f.text("每个用例只按判据落结果，允许拒收，不允许错认", OK_X + OK_W - 20,
           OK_Y + 16, 18, C.INK3, align="right", alpha=a * 0.9)

    x = CELL_X0
    for i in range(N_PASS + N_SAFE):
        k = ramp(t, l3 + 0.15 + 0.016 * i, l3 + 0.45 + 0.016 * i)
        if k <= 0:
            continue
        if i == N_PASS:
            x += 18
        safe = i >= N_PASS
        col = C.WARNC if safe else C.OKC
        y = CELL_Y0 + (1 - ease_out(k)) * 6
        f.rect(x, y, CELL_W, CELL_H, col, alpha=0.20 * k * a, r=3)
        f.rect_stroke(x, y, CELL_W, CELL_H, col, lw=1.0, r=3, alpha=0.60 * k * a)
        x += CELL_W + CELL_GAP

    ka = ramp(t, l3 + 0.9, l3 + 1.4)
    if ka > 0:
        f.text("26 PASS", CELL_X0, OK_Y + OK_H - 40, 21, C.OKC, C.MONO,
               WEIGHT_BOLD, alpha=ka * a)
        f.text("16 SAFE_NOCONV（安全拒收）", CELL_X0 + N_PASS * (CELL_W + CELL_GAP) + 18,
               OK_Y + OK_H - 40, 21, C.WARNC, C.SANS, alpha=ka * a)

    ke = ramp(t, l3 + 1.5, l3 + 2.1)
    if ke > 0:
        f.text("静默错误", OK_X + OK_W - 190, OK_Y + OK_H - 44, 21, C.INK3,
               C.SANS, align="right", alpha=ke * a)
        f.text("0", OK_X + OK_W - 40, OK_Y + OK_H - 56, 40, C.OKC, C.MONO,
               WEIGHT_BOLD, align="right", alpha=ke * a)


def longrun(f, t, a, l4):
    """最终版制品的连续运行记录。只呈现当前版，不并列历史版本。"""
    if a <= 0:
        return
    k = ramp(t, l4 + 0.2, l4 + 0.9)
    if k <= 0:
        return
    y = LR_Y + (1 - ease_out(k)) * 12
    col = C.OKC
    f.rect(LR_X, y, LR_W, LR_H, C.PANEL, alpha=0.92 * k * a, r=3)
    f.rect_stroke(LR_X, y, LR_W, LR_H, col, lw=1.0, r=3, alpha=0.38 * k * a)
    f.rect(LR_X, y, 4, LR_H, col, alpha=0.85 * k * a, r=2)
    f.text("连续运行", LR_X + 26, y + 18, 22, col, C.SANS, WEIGHT_MEDIUM,
           alpha=k * a)
    f.text("当前制品 · 单次不中断", LR_X + 26, y + 50, 19, C.INK3,
           alpha=k * a * 0.9)

    cols = [("2 小时", "连续时长", 0.0), ("262 轮", "完整轮次", 0.15),
            ("0", "失败次数", 0.30)]
    x0 = LR_X + 380
    step = 430
    for i, (val, lab, dly) in enumerate(cols):
        kk = ramp(t, l4 + 0.5 + dly, l4 + 1.1 + dly)
        if kk <= 0:
            continue
        cx = x0 + i * step
        f.line(cx - 60, y + 26, cx - 60, y + LR_H - 26, C.EDGE, 1.0,
               alpha=0.55 * kk * a)
        C.value_label(f, cx, y + 34, val, "", 46, col, alpha=kk * a)
        f.text(lab, cx, y + 100, 20, C.INK3, alpha=kk * a * 0.95)


def draw(f, t, S):
    C.background(f, t, C.OKC)
    C.chapter(f, 8, "实测结果", C.OKC, t)
    C.footer(f, 8, 9, t)
    C.header(f, "实测：从 26.5 秒到约 5.1 秒", t=t)

    l0, l1, l2 = [C.ls(S, i) for i in range(3)]

    # 第一句给计时口径，四行时延跨 l0→l1；第二句前半上传、后半写第二条时延；
    # 第三句同时给正确性与长稳（两块纵向分居，不抢位）。
    a_p = ramp(t, l0, l0 + 0.6)
    perf(f, t, a_p, l0, l1)

    a_u = ramp(t, l1 + 2.0, l1 + 2.5)
    upload(f, t, a_u, l1 + 1.9)

    a_c = ramp(t, l2 - 0.2, l2 + 0.4)
    correctness(f, t, a_c, l2)

    a_l = ramp(t, l2 + 2.1, l2 + 2.6)
    longrun(f, t, a_l, l2 + 2.2)
