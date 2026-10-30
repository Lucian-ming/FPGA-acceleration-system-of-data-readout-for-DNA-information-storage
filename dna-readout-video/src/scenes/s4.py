# -*- coding: utf-8 -*-
"""S4 — Stage 2 差分投票。

上：81,000 bit 拆成两层、每层 40,500 个位置。
中：一个位置一个 10 bit 有符号累加器，命中 +1、未命中 −1，饱和在 −512..+511。
下：四段并置——整轮只清一次、判决 vote>0、score_min 入口门禁、按字节异或水印。
"""
import math

from engine.gfx import (Frame, clamp, lerp, ramp, ease_out, ease_in_out,
                        WEIGHT_BOLD, WEIGHT_NORMAL, WEIGHT_MEDIUM, mix)
from scenes import common as C

TITLE = "二级：差分投票"

# 顶部两条层带
LAY_X0, LAY_X1 = 300, 1620
LAY_A, LAY_B = 226, 268
LAY_H = 24

# 中区：一个位置上的累加器演示（6 条读出 × 6 个位置）
GX, GY = 300, 372
CW, CH = 58, 38
RGAP_Y = 44
COLS = 6
ROWS = 6
VOTES = [  # rows: read index; cols: position
    [+1, +1, -1, +1, +1, -1],
    [+1, -1, +1, +1, -1, +1],
    [-1, +1, +1, -1, +1, +1],
    [+1, +1, -1, +1, -1, -1],
    [+1, -1, +1, -1, +1, +1],
    [-1, -1, +1, +1, -1, +1],
]
TOTAL = [sum(VOTES[r][c] for r in range(ROWS)) for c in range(COLS)]

# 右侧饱和数轴
AXB_X, AXB_W = 960, 58
AXB_Y0, AXB_Y1 = 330, 700
SAT_MIN, SAT_MAX = -512, 511

T_GAUGE_NOTE = 92.0

# 底部条带共用区间
BAND_Y0, BAND_Y1 = 760, 940


def axb_y(v):
    return AXB_Y0 + (AXB_Y1 - AXB_Y0) * (SAT_MAX - v) / float(SAT_MAX - SAT_MIN)


def layer_bars(f, a):
    if a <= 0:
        return
    for y, lab, col, lab_long in ((LAY_A, "层 A", C.S2C, "高位平面 · 40,500 bit"),
                                  (LAY_B, "层 B", C.S2C, "低位平面 · 40,500 bit")):
        f.text(lab, 150, y + 2, 20, col, C.SANS, WEIGHT_MEDIUM, alpha=a)
        f.rect(LAY_X0, y, LAY_X1 - LAY_X0, LAY_H, "#DDD2BE", r=2, alpha=a)
        x = LAY_X0
        while x < LAY_X1:
            f.line(x, y + 3, x, y + LAY_H - 3, col, 1.0, alpha=0.30 * a)
            x += 5.0
        f.rect_stroke(LAY_X0, y, LAY_X1 - LAY_X0, LAY_H, col, 1.2, r=2,
                      alpha=0.55 * a)
        f.text(lab_long, LAY_X1 + 20, y + 2, 20, C.INK3, alpha=a * 0.9)
    f.text("81,000 bit = 2 × 40,500（位平面，不是两份拷贝）", 150, LAY_A - 32,
           22, C.INK2, alpha=a * 0.95)


def plane_detail(f, a):
    """每个碱基 2 bit，全部高位连成层 A，全部低位连成层 B。"""
    if a <= 0:
        return
    bases = ["A", "T", "C", "G", "A", "C"]
    hi = ["0", "0", "1", "1", "0", "1"]
    lo = ["0", "1", "1", "0", "0", "1"]
    y = 336
    cx0, cw = 330, 74
    f.text("每个碱基 2 bit", 150, y, 20, C.INK2, alpha=a * 0.95)
    f.text("碱基", 150, y + 44, 17, C.INK3, alpha=a * 0.85)
    f.text("高位", 150, y + 92, 17, C.S2C, alpha=a * 0.9)
    f.text("低位", 150, y + 140, 17, C.S2C, alpha=a * 0.9)
    for i, b in enumerate(bases):
        cx = cx0 + i * cw
        col = C.BASE_C.get(b, C.INK2)
        f.rect(cx, y + 36, cw - 18, 34, col, alpha=0.12 * a, r=5)
        f.text(b, cx + (cw - 18) / 2, y + 40, 22, col, C.MONO, WEIGHT_BOLD,
               align="center", alpha=a)
        for j, row in enumerate((hi, lo)):
            yy = y + 84 + j * 48
            f.rect(cx, yy, cw - 18, 32, C.S2C, alpha=0.10 * a, r=5)
            f.text(row[i], cx + (cw - 18) / 2, yy + 4, 20, C.S2C, C.MONO,
                   align="center", alpha=a)
    f.text("高位连成一串 → 层 A", 330, y + 196, 19, C.S2C, alpha=a * 0.95)
    f.text("低位连成一串 → 层 B", 330, y + 226, 19, C.S2C, alpha=a * 0.95)
    f.text("码表：A 00 · T 01 · G 10 · C 11", 150, y + 268, 17, C.INK3,
           alpha=a * 0.85)
    # 右侧：从一条读出到两个平面
    kx = 1090
    f.text("一条 150 bp 的读出", kx, y - 2, 20, C.INK2, alpha=a * 0.95)
    f.text("= 300 bit 码字", kx, y + 30, 20, C.INK2, alpha=a * 0.95)
    f.text("高 150 bit 落到层 A 的对应位置，", kx, y + 84, 19, C.INK3,
           alpha=a * 0.9)
    f.text("低 150 bit 落到层 B 的同一位置。", kx, y + 114, 19, C.INK3,
           alpha=a * 0.9)
    f.text("两条读出可能落在完全不同位置，", kx, y + 168, 19, C.INK3,
           alpha=a * 0.9)
    f.text("所以累加器要覆盖 81,000 个位置。", kx, y + 198, 19, C.INK3,
           alpha=a * 0.9)


def gauge(f, t, a, value, show_sat=False):
    if a <= 0:
        return
    f.rect(AXB_X, AXB_Y0, AXB_W, AXB_Y1 - AXB_Y0, "#EDE5D6", r=3, alpha=a)
    f.rect_stroke(AXB_X, AXB_Y0, AXB_W, AXB_Y1 - AXB_Y0, C.EDGE, 1.2, r=3,
                  alpha=a)
    # 0 线（判决边界）
    y0 = axb_y(0)
    f.line(AXB_X - 14, y0, AXB_X + AXB_W + 14, y0, C.INK2, 1.4,
           alpha=0.65 * a, dash=[6, 5])
    # 填充：从 0 到当前值
    yv = axb_y(value)
    top, h = min(y0, yv), abs(yv - y0)
    col = C.S2C if value > 0 else (C.WARNC if value < 0 else C.INK3)
    if h > 0.5:
        f.rect(AXB_X + 4, top, AXB_W - 8, h, col, alpha=0.55 * a, r=3)
    # 刻度（只画在右侧，左侧留给数值气泡）
    for v, lab in ((SAT_MAX, "+511"), (0, "0"), (SAT_MIN, "−512")):
        y = axb_y(v)
        f.line(AXB_X + AXB_W, y, AXB_X + AXB_W + 8, y, C.INK3, 1.0, alpha=a)
        f.text(lab, AXB_X + AXB_W + 16, y - 11, 20, C.INK2, C.MONO, alpha=a)
    # 指针 + 数值（放在左侧，避免与刻度标签打架）
    f.fill_poly([(AXB_X - 4, yv), (AXB_X - 16, yv - 8), (AXB_X - 16, yv + 8)],
                col, alpha=a)
    f.text("当前累加值", AXB_X - 30, AXB_Y0 - 26, 18, C.INK3,
           align="right", alpha=a * 0.9)
    f.text("%+d" % int(round(value)), AXB_X - 30, AXB_Y0 - 6, 34,
           col, C.MONO, WEIGHT_BOLD, align="right", alpha=a)
    f.text("10 bit 有符号", AXB_X + AXB_W / 2, AXB_Y1 + 20, 18, C.INK3,
           align="center", alpha=a * 0.9)
    if show_sat:
        f.text("越界停在边界", AXB_X + AXB_W / 2, AXB_Y1 + 46, 18, C.WARNC,
               C.SANS, align="center", alpha=a * 0.95)
        for v in (SAT_MAX, SAT_MIN):
            y = axb_y(v)
            f.rect(AXB_X + 4, y - (6 if v > 0 else 0), AXB_W - 8, 6, C.WARNC,
                   alpha=0.5 * a, r=2)
    # 右侧说明：为什么用差分
    kn = ramp(t, T_GAUGE_NOTE, T_GAUGE_NOTE + 0.8)
    if kn > 0:
        f.text("为什么是差分", 1200, AXB_Y0 + 4, 22, C.INK2, C.SANS,
               WEIGHT_MEDIUM, alpha=kn)
        lines = ["命中记 +1，未命中记 −1，", "投的是净票数，不是绝对数。",
                 "相反的票值求和后相互抵消，", "真实信号在多数读出里保持同号。"]
        for i, s in enumerate(lines):
            f.text(s, 1200, AXB_Y0 + 52 + i * 34, 21, C.INK3, alpha=kn * 0.95)
        f.text("得分 ≥ 67 的读段才进入投票", 1200, AXB_Y0 + 210, 19, C.S2C,
               alpha=kn * 0.9)


def vote_grid(f, a, row_a, total_a, dec_a):
    """6×6 的 ±1 表 + 合计行 + 判决行。"""
    if a <= 0:
        return
    f.text("一个位置一个累加器", GX, GY - 58, 24, C.INK2, alpha=a)
    f.text("每行是一条读出的贡献", GX + 250, GY - 57, 18, C.INK3,
           alpha=a * 0.85)
    for c in range(COLS):
        f.text("位 %d" % (c + 1), GX + c * CW + CW / 2, GY - 26, 16, C.INK3,
               C.MONO, align="center", alpha=a * 0.8)
    for r in range(ROWS):
        ka = ramp(row_a, r * 0.09, r * 0.09 + 0.35)
        if ka <= 0:
            continue
        y = GY + r * RGAP_Y
        f.text("读出 %d" % (r + 1), GX - 96, y + 7, 18, C.INK3, C.MONO,
               alpha=a * ka * 0.9)
        for c in range(COLS):
            v = VOTES[r][c]
            col = C.S2C if v > 0 else C.WARNC
            f.rect(GX + c * CW, y, CW - 6, CH, col, alpha=0.12 * a * ka, r=4)
            f.text("%+d" % v, GX + c * CW + (CW - 6) / 2, y + 5, 21, col,
                   C.MONO, WEIGHT_BOLD, align="center", alpha=a * ka)
    if total_a > 0:
        y = GY + ROWS * RGAP_Y + 4
        f.line(GX - 8, y - 10, GX + COLS * CW + 4, y - 10, C.EDGE, 1.2,
               alpha=a * total_a * 0.8)
        f.text("合计", GX - 96, y + 7, 18, C.INK2, C.SANS, alpha=a * total_a)
        for c in range(COLS):
            v = TOTAL[c]
            col = C.S2C if v > 0 else (C.WARNC if v < 0 else C.INK2)
            f.rect(GX + c * CW, y, CW - 6, CH, col, alpha=0.16 * a * total_a,
                   r=4)
            f.rect_stroke(GX + c * CW, y, CW - 6, CH, col, 1.0, r=4,
                          alpha=0.5 * a * total_a)
            f.text("%+d" % v, GX + c * CW + (CW - 6) / 2, y + 5, 21, col,
                   C.MONO, WEIGHT_BOLD, align="center", alpha=a * total_a)
        if dec_a > 0:
            y2 = y + RGAP_Y
            f.text("判决", GX - 96, y2 + 7, 18, C.INK2, C.SANS, alpha=a * dec_a)
            for c in range(COLS):
                bit = "1" if TOTAL[c] > 0 else "0"
                col = C.OKC if bit == "1" else C.INK3
                f.rect(GX + c * CW, y2, CW - 6, CH, col, alpha=0.14 * a * dec_a,
                       r=4)
                f.text(bit, GX + c * CW + (CW - 6) / 2, y2 + 4, 24, col,
                       C.MONO, WEIGHT_BOLD, align="center", alpha=a * dec_a)


def band_batches(f, t, a, l3):
    """整轮任务只清一次，批间不清零，全部收完才判决。"""
    if a <= 0:
        return
    x0, x1 = 150, 1770
    f.text("一条任务 = 103,616 条读出记录", x0, BAND_Y0 + 2, 22, C.INK2, alpha=a)
    f.text("按批进入，批间不清零", x1, BAND_Y0 + 2, 19, C.INK3, align="right",
           alpha=a * 0.9)
    y = 866
    f.line(x0, y, x1, y, C.EDGE, 1.4, alpha=a * 0.8)
    # 清零时刻
    f.rect(x0 - 3, y - 15, 6, 30, C.S2C, alpha=a, r=2)
    f.text("任务开始：清零 ×1", x0 + 16, y - 46, 19, C.S2C, alpha=a)
    # 批次方块
    n = 14
    for i in range(n):
        k = ramp(t, l3 + 0.15 + 0.055 * i, l3 + 0.35 + 0.055 * i)
        if k <= 0:
            continue
        bx = x0 + 26 + i * ((x1 - x0 - 52) / float(n))
        f.rect(bx, y - 13, 28, 26, C.S2C, alpha=0.22 * k * a, r=3)
        f.rect_stroke(bx, y - 13, 28, 26, C.S2C, 1.0, r=3, alpha=0.55 * k * a)
    kend = ramp(t, l3 + 1.05, l3 + 1.35)
    if kend > 0:
        f.line(x1, y, x1, y + 24, C.OKC, 1.4, alpha=kend * a)
        f.text("全部收完，才轮到判决", x1, y + 34, 19, C.OKC, align="right",
               alpha=kend * a)
        f.text("整条任务只清零这一次", x0 + 16, y + 34, 18, C.INK3,
               alpha=kend * a * 0.9)


def band_decision(f, t, a, l4):
    if a <= 0:
        return
    k = ramp(t, l4 + 0.1, l4 + 0.6)
    y = BAND_Y0 + 34
    f.text("每个位置单独判决", 150, y, 22, C.INK2, alpha=a)
    y += 46
    f.text("vote > 0", 150, y, 38, C.OKC, C.MONO, WEIGHT_BOLD, alpha=a * k)
    f.text("→ 1", 380, y, 38, C.OKC, C.MONO, WEIGHT_BOLD, alpha=a * k)
    f.text("否则 vote ≤ 0", 640, y, 38, C.INK2, C.MONO, WEIGHT_BOLD,
           alpha=a * k)
    f.text("→ 0", 960, y, 38, C.INK2, C.MONO, WEIGHT_BOLD, alpha=a * k)
    f.text("不看幅度，只看符号；正好为 0 也归 0", 150, y + 72, 20, C.INK3,
           alpha=a * k * 0.9)


def band_score(f, t, a, l5):
    if a <= 0:
        return
    k = ramp(t, l5 + 0.1, l5 + 0.7)
    f.text("入口门禁：得分低于 67 的读段不进入投票", 150, BAND_Y0 + 2, 22,
           C.INK2, alpha=a)
    x0, x1 = 150, 1600
    s_lo, s_hi = 55, 82

    def sx(sv):
        return x0 + (x1 - x0) * (sv - s_lo) / float(s_hi - s_lo)

    y = 880
    f.rect(x0, y - 46, sx(67) - x0, 30, C.WARNC, alpha=0.10 * k * a, r=3)
    f.text("score < 67：入口丢弃，不产生任何一票", x0, 806, 18, C.WARNC,
           alpha=a * k * 0.95)
    f.text("score_min = 67", sx(67) + 14, 806, 19, C.WARNC, alpha=a * k)
    f.line(x0, y, x1, y, C.EDGE, 1.4, alpha=a * k)
    for sv in (55, 60, 67, 75, 82):
        f.line(sx(sv), y - 6, sx(sv), y + 6, C.INK3, 1.0, alpha=a * k * 0.8)
        f.text(str(sv), sx(sv), y + 12, 16, C.INK3, C.MONO, align="center",
               alpha=a * k * 0.8)
    f.line(sx(67), y - 46, sx(67), y + 22, C.WARNC, 1.6, alpha=k * a,
           dash=[6, 4])
    f.text("SE150 默认值；高熵场景用 65", x1, y + 40, 17, C.INK3,
           align="right", alpha=a * k * 0.85)
    pts = [(59, C.WARNC), (61, C.WARNC), (65, C.WARNC), (74, C.OKC),
           (76, C.OKC), (61, C.WARNC), (78, C.OKC), (60, C.WARNC)]
    for i, (sv, col) in enumerate(pts):
        kk = ramp(t, l5 + 0.7 + 0.09 * i, l5 + 0.95 + 0.09 * i)
        if kk <= 0:
            continue
        f.circle(sx(sv) + (i % 3 - 1) * 5, y - 20, 6, col, alpha=kk * a)


def band_wm(f, t, a, l6):
    if a <= 0:
        return
    k = ramp(t, l6 + 0.1, l6 + 0.7)
    f.text("投票结果按字节异或水印，交给第三级", 150, BAND_Y0 + 2, 22, C.INK2,
           alpha=a)
    f.text("PS · 板载 ARM 裸机做这一级（Stage2.5）", 1400, BAND_Y0 + 4, 18,
           C.INK3, align="right", alpha=a * 0.85)
    f.text("字节内 LSB 优先：bit0 → bit7", 1770, BAND_Y0 + 2, 19, C.INK3,
           align="right", alpha=a * 0.9)
    rows = [("共识字节", "1 0 1 1 0 0 1 0", C.S2C),
            ("水印字节", "0 1 1 0 1 0 0 1", C.S1C),
            ("异或结果", "1 1 0 1 1 0 1 1", C.OKC)]
    y0 = BAND_Y0 + 56
    for ri, (lab, bits, col) in enumerate(rows):
        kk = ramp(t, l6 + 0.55 + 0.45 * ri, l6 + 0.85 + 0.45 * ri)
        if kk <= 0:
            continue
        yy = y0 + ri * 50
        f.text(lab, 150, yy + 4, 20, C.INK3, alpha=kk * a)
        for i, b in enumerate(bits.split()):
            f.text(b, 360 + i * 32, yy, 24, col, C.MONO, WEIGHT_BOLD,
                   alpha=kk * a)
    kk = ramp(t, l6 + 1.9, l6 + 2.3)
    if kk > 0:
        f.text("⊕", 320, y0 + 26, 30, C.INK2, C.MONO, align="center",
               alpha=kk * a)
        f.text("= 第三级的输入", 640, y0 + 104, 20, C.INK2, alpha=kk * a)


def draw(f, t, S):
    C.background(f, t)
    C.chapter(f, 4, "二级 · 差分投票", C.S2C, t)
    C.footer(f, 4, 9, t)
    C.header(f, "同一位的多条读出，加在一起投票", t=t)

    l0, l1, l2, l3, l4, l5, l6 = [C.ls(S, i) for i in range(7)]

    layer_bars(f, ramp(t, l1 - 0.2, l1 + 0.7))
    plane_detail(f, ramp(t, l1 + 0.6, l1 + 1.3)
                 * (1 - ramp(t, l2 - 1.0, l2 - 0.4)))

    a_grid = ramp(t, l2 - 0.1, l2 + 0.6)
    row_a = t - (l2 + 0.6)
    total_a = ramp(t, l2 + 3.4, l2 + 4.0)
    dec_a = ramp(t, l4 - 0.2, l4 + 0.5)
    vote_grid(f, a_grid, row_a, total_a, dec_a)

    # 右侧数轴：随 l2 里的演示值变化
    ga = ramp(t, l2 + 0.5, l2 + 1.2)
    val = 0.0
    if t > l2 + 1.0:
        seg = clamp((t - (l2 + 1.0)) / max(0.5, C.ld(S, 2) - 1.2))
        val = -600 + 1200 * seg          # 先撞下界再回到上界，展示饱和
        val = max(SAT_MIN, min(SAT_MAX, val))
    gauge(f, t, ga, val, show_sat=ga > 0.5)

    # 底部条带逐段切换
    a_b = ramp(t, l3 - 0.2, l3 + 0.5) * (1 - ramp(t, l4 - 0.3, l4 + 0.3))
    band_batches(f, t, a_b, l3)
    a_d = ramp(t, l4 - 0.3, l4 + 0.4) * (1 - ramp(t, l5 - 0.3, l5 + 0.3))
    band_decision(f, t, a_d, l4)
    a_s = ramp(t, l5 - 0.2, l5 + 0.5) * (1 - ramp(t, l6 - 0.3, l6 + 0.3))
    band_score(f, t, a_s, l5)
    a_w = ramp(t, l6 - 0.2, l6 + 0.5)
    band_wm(f, t, a_w, l6)
