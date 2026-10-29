# -*- coding: utf-8 -*-
"""S3 — Stage 1 滑窗比对。

三层同轴：上=参考串总览（候选起点 0..40,350），中=参考链与读出链逐位对齐，
下=得分曲线。后两句把中景区换成「16 窗口 + 选路树」与「64 条一批 → 输出记录」。
得分曲线形状为原理示意；噪声 59–62、峰值典型值 ≈75 取自项目报告。
"""
import math

from engine.gfx import (Frame, clamp, lerp, ramp, ramp_lin, ease_out,
                        ease_in_out, pulse, WEIGHT_BOLD, WEIGHT_NORMAL,
                        WEIGHT_MEDIUM, mix)
from scenes import common as C

TITLE = "一级：滑窗比对"

BAR_X, BAR_W = 112, 1696
BAR_LAB_Y = 250
BAR_Y, BAR_H = 288, 20

Z_X, Z_W = 214, 1594        # 左侧 112..206 留给行标签
SHOWN = 64
CW = Z_W / float(SHOWN)

REF_Y, LH = 380, 34          # 参考链骨架顶边
MARK_Y = 424                 # 逐位结果行
READ_Y = 470                 # 读出链骨架顶边
LAB_Y = 540                  # 图例行

AX_Y, AX_H = 610, 240        # 得分曲线绘图区
TOTAL_OFF = 40351
SCORE_MAX = 150

MISMATCH = {11, 27, 43, 58}  # 示意：读出里读错的位


def off_to_x(off):
    return BAR_X + BAR_W * (off / float(TOTAL_OFF))


def score_to_y(s):
    return AX_Y + AX_H - AX_H * (s / float(SCORE_MAX))


def score_profile():
    """原理示意曲线：噪声底 59–62，真实起点附近一个典型值约 75 的峰。"""
    n = 1500
    pts = []
    for i in range(n):
        u = i / float(n - 1)
        base = 60.3 + 1.1 * math.sin(i * 1.7) + 0.55 * math.sin(i * 4.3 + 0.7)
        d = (u - 0.52) * TOTAL_OFF
        peak = 14.6 * math.exp(-(d * d) / (2 * 520.0 ** 2))
        peak += 2.0 * math.exp(-((d - 760) ** 2) / (2 * 560.0 ** 2))
        pts.append((u, min(SCORE_MAX, base + peak)))
    return pts


PROFILE = score_profile()


# ------------------------------------------------------------------ 构件
def overview(f, a, cursor_off=None):
    if a <= 0:
        return
    f.text("参考串（含水印）", BAR_X, BAR_LAB_Y, 21, C.INK2, alpha=a)
    f.text("40,500 符号 = 81,000 bit", BAR_X + 196, BAR_LAB_Y, 21, C.INK3,
           C.MONO, alpha=a * 0.9)
    f.text("候选起点 0 .. 40,350（40,351 个）", BAR_X + BAR_W, BAR_LAB_Y, 21,
           C.INK3, align="right", alpha=a * 0.9)
    f.rect(BAR_X, BAR_Y, BAR_W, BAR_H, "#16212A", r=3, alpha=a)
    x = BAR_X
    while x < BAR_X + BAR_W:
        f.line(x, BAR_Y + 3, x, BAR_Y + BAR_H - 3, "#2C4150", 1.0, alpha=0.55 * a)
        x += 4.0
    f.rect_stroke(BAR_X, BAR_Y, BAR_W, BAR_H, "#33454F", lw=1.0, r=3, alpha=a)
    for k in range(5):
        off = TOTAL_OFF * k / 4.0
        x = off_to_x(off)
        f.line(x, BAR_Y + BAR_H, x, BAR_Y + BAR_H + 6, "#3C4E5A", 1.0, alpha=a)
        f.text("{:,}".format(int(round(off))), x, BAR_Y + BAR_H + 11, 16,
               C.INK3, C.MONO, align="center", alpha=a * 0.85)
    if cursor_off is not None:
        x = off_to_x(cursor_off)
        f.rect(x - 1.5, BAR_Y - 7, 3, BAR_H + 14, C.S1C, alpha=a, r=2)
        f.fill_poly([(x, BAR_Y - 17), (x - 7, BAR_Y - 7), (x + 7, BAR_Y - 7)],
                    C.S1C, alpha=0.95 * a)


def strand(f, x, y, seq, cw, h, alpha=1.0, size=15, letters_below=False,
           label_col="#5E8CA6", dim=1.0, hi=None):
    """一条链：上下两条骨架 + 竖线 + 碱基字母。hi=(起, 止) 为窗口内不下沉的列。"""
    n = len(seq)
    x1 = x + n * cw
    f.line(x - 4, y, x1 + 4, y, label_col, 3.0, alpha=0.45 * alpha)
    f.line(x - 4, y + h, x1 + 4, y + h, label_col, 3.0, alpha=0.45 * alpha)
    ly = y + h + 6 if letters_below else y - size - 8
    for i, b in enumerate(seq):
        cx = x + i * cw + cw / 2
        ba = alpha
        if hi and not (hi[0] <= i < hi[1]):
            ba = alpha * dim
        f.line(cx, y + 2, cx, y + h - 2, "#4A6474", 1.2, alpha=0.40 * alpha)
        f.text(b, cx, ly, size, C.BASE_C.get(b, C.INK2), C.MONO, WEIGHT_BOLD,
               align="center", alpha=ba)


def score_layer(f, a, drawn=1.0, cursor_u=None):
    if a <= 0:
        return
    AX_X, AX_W = BAR_X, BAR_W
    # 合一行并贴着绘图区上沿：上面 LAB_Y 那行放的是 +1/+0 图例，
    # 原来是两行右对齐轴注，正好被图例的右端压住。
    f.text("纵轴 得分 / 150　横轴 候选起点 →", AX_X + AX_W, AX_Y - 26, 15,
           C.INK3, align="right", alpha=a * 0.9)

    for s in (0, 50, 75, 100, 150):
        y = score_to_y(s)
        f.line(AX_X, y, AX_X + AX_W, y, "#1D2830", 1.0,
               alpha=a * (0.85 if s in (0, 150) else 0.5))
        f.text(str(s), AX_X - 12, y - 10, 16, C.INK3, C.MONO,
               align="right", alpha=a * 0.8)

    y1, y2 = score_to_y(62.0), score_to_y(59.0)
    f.rect(AX_X, y1, AX_W, y2 - y1, C.WARNC, alpha=0.13 * a)
    f.text("噪声段 59–62", AX_X + 10, y1 + 5, 16, C.WARNC, alpha=a * 0.95)
    y75 = score_to_y(75.0)
    f.line(AX_X, y75, AX_X + AX_W, y75, C.S1C, 1.0, alpha=0.45 * a, dash=[6, 6])
    f.text("峰值典型值 ≈ 75", AX_X + 10, y75 - 22, 16, C.S1C, alpha=a * 0.95)

    n = int((len(PROFILE) - 1) * clamp(drawn))
    if n > 1:
        pts = [(BAR_X + BAR_W * PROFILE[i][0], score_to_y(PROFILE[i][1]))
               for i in range(n + 1)]
        area = pts + [(pts[-1][0], AX_Y + AX_H), (pts[0][0], AX_Y + AX_H)]
        f.fill_poly(area, C.S1C, alpha=0.055 * a)
        f.polyline(pts, C.S1C, 2.0, alpha=0.95 * a)
    if cursor_u is not None and 0 <= cursor_u <= 1:
        x = BAR_X + BAR_W * cursor_u
        i = min(len(PROFILE) - 1, int(cursor_u * (len(PROFILE) - 1)))
        sc = PROFILE[i][1]
        y = score_to_y(sc)
        f.line(x, AX_Y - 6, x, AX_Y + AX_H, C.S1C, 1.0, alpha=0.30 * a)
        f.circle(x, y, 5.5, C.S1C, alpha=a, stroke=C.BG, lw=2.0)
        # 读数始终收在绘图区内，并垫一层底色：否则光标滑到最右时数字会压在
        # 右边框和 75 虚线上
        txt = "%.0f" % sc
        tw = f.measure(txt, 24, C.MONO, WEIGHT_BOLD)[0]
        if x + 12 + tw <= AX_X + AX_W - 6:
            lx = x + 12
        else:
            lx = max(AX_X + 6, x - 12 - tw)
        ly = y - 34 if y - 34 >= AX_Y + 2 else y + 16
        f.rect(lx - 7, ly - 4, tw + 14, 34, C.BG, alpha=0.80 * a, r=6)
        f.text(txt, lx, ly, 24, C.S1C, C.MONO, WEIGHT_BOLD, alpha=a)


# ------------------------------------------------------------------ 主绘制
def draw(f, t, S):
    C.background(f, t)
    C.chapter(f, 3, "一级 · 滑窗比对", C.S1C, t)
    C.footer(f, 3, 9, t)
    C.header(f, "先定位：读出落在参考串的哪一段", t=t)

    l0, l1, l2, l3, l4, l5, l6, l7 = [C.ls(S, i) for i in range(8)]

    # ---------- 第一句：一句话点题
    k_tag = ramp(t, 0.0, 0.5) * (1 - ramp(t, l2 - 0.2, l2 + 0.5))
    if k_tag > 0:
        f.text("STAGE 1", 112, 196, 28, C.S1C, C.MONO, WEIGHT_BOLD, alpha=k_tag)
        f.text("固定参考串，让读出逐位滑过并打分", 236, 200, 24, C.INK2,
               alpha=k_tag)

    # ---------- 第二句：总览条
    a_bar = ramp(t, l1 - 0.2, l1 + 0.8)
    cursor_off = None
    if l3 <= t < l6:
        u = ease_in_out(clamp((t - l3 - 0.15) / max(0.2, C.ld(S, 3) - 1.0)))
        cursor_off = u * TOTAL_OFF
    overview(f, a_bar, cursor_off)

    refseq = C.base_seq(SHOWN, 21)
    readseq = list(refseq)
    for i in MISMATCH:
        readseq[i] = {"A": "G", "T": "C", "C": "A", "G": "T"}[refseq[i]]
    readseq = "".join(readseq)

    band_dim = 1.0 - 0.88 * ramp(t, l6 - 0.3, l6 + 0.3)
    zoom_a = ramp(t, l2 - 0.1, l2 + 0.6) * band_dim

    # ---------- 第三句：螺旋解开成参考链
    unwrap = ramp(t, l2 + 0.5, l3 + 1.4)
    if zoom_a > 0.01 and unwrap < 0.999:
        C.helix(f, Z_X + Z_W / 2, REF_Y + LH / 2, Z_W, t,
                phase=t * 0.6, bases=refseq, alpha=zoom_a * (1 - unwrap),
                rad=22, period=210, pitch=10, rung_alpha=0.6)

    a_ref = ramp(t, l2 + 0.9, l3 + 1.2) * band_dim
    if a_ref > 0.01:
        strand(f, Z_X, REF_Y, refseq, CW, LH, alpha=a_ref, size=15)
        f.text("参考链", 112, REF_Y + 4, 17, C.INK3, alpha=a_ref)
        f.text("64 位局部", 112, REF_Y + 23, 12, C.INK3, alpha=a_ref * 0.8)

    # ---------- 第四句：读出链 + 逐位比对
    a_read = ramp(t, l3 + 0.6, l4 + 0.9) * band_dim
    win = None
    if t >= l3 + 0.4:
        cu = clamp((t - l3 - 0.4) / max(0.2, C.ld(S, 3) - 1.0))
        w0 = int(cu * (SHOWN - 18))
        win = (w0, w0 + 18)
    if a_read > 0.01:
        if win:
            wy0, wy1 = REF_Y - 30, READ_Y + LH + 26
            wx, ww = Z_X + win[0] * CW, (win[1] - win[0]) * CW
            k = ramp(t, l4 - 0.4, l4 + 0.4)
            if k > 0:
                f.rect(wx, wy0, ww, wy1 - wy0, C.S1C, alpha=0.09 * k * a_read,
                       r=6)
                f.rect_stroke(wx, wy0, ww, wy1 - wy0, C.S1C, 1.4, r=6,
                              alpha=0.55 * k * a_read)
        strand(f, Z_X, READ_Y, readseq, CW, LH, alpha=a_read, size=15,
               letters_below=True, label_col="#7FB4D8")
        f.text("读出链", 112, READ_Y + 4, 17, C.INK3, alpha=a_read)
        f.text("300 bit", 112, READ_Y + 23, 12, C.INK3, alpha=a_read * 0.8)

        mk = ramp(t, l4, l4 + 0.6)
        if mk > 0 and win:
            for i in range(win[0], win[1]):
                cx = Z_X + i * CW + CW / 2
                hit = i not in MISMATCH
                f.text("+1" if hit else "+0", cx, MARK_Y - 4, 14,
                       C.OKC if hit else C.WARNC, C.MONO, WEIGHT_BOLD,
                       align="center", alpha=mk * a_read * (0.75 if hit else 1.0))
        f.text("比对窗口沿候选起点滑动，窗口内逐位计分", Z_X, LAB_Y + 4, 16,
               C.INK3, alpha=a_read * 0.9 * ramp(t, l4, l4 + 0.6))
        if mk > 0:
            w1 = f.measure("+1 命中", 16)[0] + 22
            C.chip(f, Z_X + Z_W - w1 - 124, LAB_Y - 2, "+1 命中", C.OKC, 16,
                   9, 4, alpha=mk * a_read, fill_alpha=0.10)
            C.chip(f, Z_X + Z_W - 114, LAB_Y - 2, "+0 未命中", C.WARNC, 16,
                   9, 4, alpha=mk * a_read, fill_alpha=0.10)

    # ---------- 第五句：得分曲线
    a_ax = ramp(t, l3 + 0.7, l3 + 1.6)
    dim = 1.0 - 0.55 * ramp(t, l6, l6 + 0.7)
    if a_ax > 0:
        drawn = clamp((t - (l3 + 0.9)) / max(0.2, (l6 + 0.3) - (l3 + 0.9)))
        cu = None
        if l3 <= t < l6:
            cu = clamp((t - l3 - 0.15) / max(0.2, C.ld(S, 3) - 1.0))
        score_layer(f, a_ax * dim, drawn, cu)
        if dim > 0.5:
            C.principle_tag(f, BAR_X, AX_Y + AX_H + 12,
                            "曲线为原理示意；59–62 与 ≈75 为项目典型值",
                            alpha=a_ax * (dim - 0.5) * 2 * 0.85)

    # ---------- 第六句：16 窗口 + 选路树
    a_tree = ramp(t, l6, l6 + 0.8) * (1 - ramp(t, l7 - 0.4, l7 + 0.2))
    if a_tree > 0.01:
        draw_selector(f, t, a_tree, l6)

    # ---------- 第七句：64 条一批 → 输出
    a_batch = ramp(t, l7 + 0.1, l7 + 1.0)
    if a_batch > 0.01:
        draw_output(f, t, a_batch, l7)


def draw_selector(f, t, a, l6):
    f.rect(0, 352, C.W, 250, C.BG, alpha=0.92 * a)
    f.text("16 个滑窗并行扫描，选路树每拍折半：16 → 8 → 4 → 2 → 1",
           Z_X, 366, 22, C.INK2, alpha=a)
    f.text("每条读出 → 300 bit 码字 + 16 bit 位置 + 10 bit 得分",
           Z_X + Z_W, 366, 17, C.INK3, align="right",
           alpha=a * ramp(t, l6 + 2.2, l6 + 2.8) * 0.95)

    n = 16
    bw, bh, top = 62, 58, 402
    gap = 16.0
    sc = [58, 61, 60, 74, 62, 59, 61, 60, 63, 59, 60, 61, 58, 62, 60, 59]
    for i in range(n):
        k = ramp(t, l6 + 0.25 + 0.025 * i, l6 + 0.55 + 0.025 * i)
        if k <= 0:
            continue
        x = Z_X + (i % 8) * (bw + gap)
        y = top + (i // 8) * (bh + 10)
        best = i == 3
        f.rect(x, y, bw, bh, C.S1C if best else C.PANEL_HI,
               alpha=(0.30 if best else 0.95) * k * a, r=5)
        f.rect_stroke(x, y, bw, bh, C.S1C if best else C.EDGE, lw=1.3, r=5,
                      alpha=a * k * (0.9 if best else 0.7))
        f.text("W%d" % i, x + bw / 2, y + 5, 15, C.INK2, C.MONO,
               align="center", alpha=a * k * 0.85)
        f.text(str(sc[i]), x + bw / 2, y + 26, 20, C.S1C if best else C.INK3,
               C.MONO, WEIGHT_BOLD, align="center", alpha=a * k)
    f.text("每窗一个得分（示意值）", Z_X, top + 2 * bh + 24, 15, C.INK3,
           alpha=a * ramp(t, l6 + 0.9, l6 + 1.4) * 0.85)

    # ---- 折半选路：每列条数减半，条高一致，靠密度读数
    levels = [16, 8, 4, 2, 1]
    fx = Z_X + 8 * (bw + gap) + 66
    mid = top + bh + 5
    for li, cnt in enumerate(levels):
        k = ramp(t, l6 + 0.9 + 0.26 * li, l6 + 1.2 + 0.26 * li)
        if k <= 0:
            continue
        bx = fx + li * 86
        bar_h, step = 6.0, 8.0
        total = cnt * step
        y0 = mid - total / 2.0
        for j in range(cnt):
            yy = y0 + j * step
            f.rect(bx, yy, 56, bar_h, C.S1C, alpha=0.30 * k * a, r=2)
            f.rect_stroke(bx, yy, 56, bar_h, C.S1C, 1.0, r=2, alpha=0.60 * k * a)
        f.text(str(cnt), bx + 28, mid + 62, 18, C.INK3, C.MONO, WEIGHT_BOLD,
               align="center", alpha=k * a * 0.9)
        if li < len(levels) - 1:
            f.text("›", bx + 64, mid - 9, 20, C.INK3, align="center",
                   alpha=k * a * 0.7)
    f.text("逐级流水，每拍只比一对", fx, mid + 92, 15, C.INK3,
           alpha=a * ramp(t, l6 + 2.0, l6 + 2.6) * 0.85)


def draw_output(f, t, a, l7):
    f.rect(0, 352, C.W, 250, C.BG, alpha=0.92 * a)
    f.text("每批 64 条读出", Z_X, 366, 22, C.INK2, alpha=a)
    for i in range(64):
        k = ramp(t, l7 + 0.3 + 0.012 * i, l7 + 0.45 + 0.012 * i)
        if k <= 0:
            continue
        cx = Z_X + 20 + (i % 32) * 30
        cy = 404 + (i // 32) * 34
        f.rect(cx, cy, 25, 27, C.S1C, alpha=0.16 * k * a, r=3)
        f.rect_stroke(cx, cy, 25, 27, C.S1C, 1.0, r=3, alpha=0.5 * k * a)
        f.text(str(i + 1), cx + 12, cy + 6, 12, C.INK3, C.MONO, align="center",
               alpha=k * a * 0.75)

    ox = Z_X + 20 + 32 * 30 + 56
    items = [("300", "bit 码字", C.S3C, 0.0), ("16", "bit 位置", C.OKC, 0.3),
             ("10", "bit 得分", C.S1C, 0.6)]
    xx = ox
    for val, lab, col, d in items:
        k = ramp(t, l7 + 1.3 + d, l7 + 1.7 + d)
        if k <= 0:
            continue
        w = f.measure(val, 30, C.MONO, WEIGHT_BOLD)[0]
        f.rect(xx, 404, w + 24, 54, col, alpha=0.10 * k * a, r=6)
        f.rect_stroke(xx, 404, w + 24, 54, col, 1.3, r=6, alpha=0.6 * k * a)
        f.text(val, xx + 12, 412, 30, col, C.MONO, WEIGHT_BOLD, alpha=k * a)
        f.text(lab, xx, 466, 16, C.INK3, alpha=k * a * 0.95)
        xx += w + 50
