# -*- coding: utf-8 -*-
"""S5 — Stage 3 反稀疏化：5 bit 一组，压成 4 bit。

上：输入码流按 5 bit 分组——码本只有重量 ≤ 2 的 16 个字，正好全部列出。
中：取一组放大——b0 扇出到四个异或门，另外四路是数据位 b1..b4。
右：同一组数据在 b0 = 0 与 b0 = 1 两种取值下的结果（两种都是合法码字）。
下：码本 → 长度 81,000 → 64,800 bit（8,100 B）→ 64 bit/拍的输出拍数。
"""
import math

from engine.gfx import (clamp, lerp, ramp, ease_out, pulse,
                        WEIGHT_BOLD, WEIGHT_NORMAL, WEIGHT_MEDIUM)
from scenes import common as C

TITLE = "三级：5 比特转 4 比特"

# ---------------------------------------------------------------- 顶部码流
STRIP_X, STRIP_Y = 112, 218
CELL_W, CELL_GAP = 16, 2
GROUP_W = 5 * CELL_W + 4 * CELL_GAP          # 88
GROUP_PITCH = 102

# 码本 = 全部汉明重量 ≤ 2 的 5-bit 字（docs/02-data-contract.md §4）
CODEBOOK = ["00000", "00001", "00010", "00011",
            "00100", "00101", "00110", "01000",
            "01001", "01010", "01100", "10000",
            "10001", "10010", "10100", "11000"]
N_GROUPS = len(CODEBOOK)
SEL = 14                                      # 10100：b0 = 1，数据 0100

# ---------------------------------------------------------------- 放大组
PANEL_X, PANEL_Y, PANEL_W, PANEL_H = 112, 292, 672, 420
B0_X, B0_Y, B0_W, B0_H = 150, 440, 76, 60     # b0 方框
BUS_X = 470                                   # b0 扇出竖线
DATA_X, DATA_W, DATA_H = 330, 60, 48
ROWS = [386, 460, 534, 608]                   # 四个门芯的竖直中心
GATE_CX, GATE_W = 590, 52
OUT_X, OUT_W, OUT_H = 640, 52, 44

DATA_BITS = ["0", "1", "0", "0"]              # 10100 的 b1..b4
OUT_BITS = {0: DATA_BITS,
            1: ["1" if b == "0" else "0" for b in DATA_BITS]}   # 1011
WIRE = {0: "0" + "".join(DATA_BITS),           # 00100
        1: "1" + "".join(DATA_BITS)}           # 10100

# ---------------------------------------------------------------- 右对照
CASE_Y, CASE_H = 292, 420
CASE_A_X, CASE_B_X, CASE_W = 800, 1312, 496

# ---------------------------------------------------------------- 底部带
BAND_Y0, BAND_Y1 = 760, 940


def strip(f, t, a, l0):
    if a <= 0:
        return
    f.text("输入码流 · 81,000 bit", STRIP_X, STRIP_Y - 34, 21, C.INK2,
           C.SANS, WEIGHT_MEDIUM, alpha=a * 0.95)
    # 右对齐说明挂在条带上沿之上：选中组的描边从 STRIP_Y-7 起，
    # 原来贴着 STRIP_Y-32 放会与框线压在同一条线上。
    f.text("81,000 ÷ 5 = 16,200 组 · 每组第 1 位是 b0 · 图中示出前 16 组",
           C.W - 112, STRIP_Y - 46, 19, C.INK3, align="right", alpha=a * 0.9)

    sel_k = ramp(t, l0 + 1.5, l0 + 2.1)
    for g in range(N_GROUPS):
        k = ramp(t, l0 + 0.07 * g, l0 + 0.07 * g + 0.3)
        if k <= 0:
            continue
        gx = STRIP_X + g * GROUP_PITCH
        is_sel = (g == SEL)
        bits = CODEBOOK[g]
        for i in range(5):
            cx = gx + i * (CELL_W + CELL_GAP)
            flag = (i == 0)
            f.rect(cx, STRIP_Y, CELL_W, 26,
                   C.S3C if flag else C.PANEL,
                   alpha=(0.16 if flag else 0.9) * k * a, r=3)
            f.rect_stroke(cx, STRIP_Y, CELL_W, 26,
                          C.S3C if flag else C.EDGE, lw=1.0, r=3,
                          alpha=(0.6 if flag else 0.7) * k * a)
            f.text(bits[i], cx + CELL_W / 2, STRIP_Y + 3, 15,
                   C.S3C if flag else C.INK2, C.MONO, WEIGHT_BOLD,
                   align="center", alpha=k * a)
        if is_sel and sel_k > 0:
            f.rect_stroke(gx - 7, STRIP_Y - 7, GROUP_W + 14, 40, C.S3C,
                          lw=2.0, r=3, alpha=sel_k * a)
            f.text("放大", gx + GROUP_W / 2, STRIP_Y + 34, 17, C.S3C,
                   align="center", alpha=sel_k * a * 0.95)


def xgate(f, cy, a, hot=0.0):
    """异或门：方框 + ⊕，左进两路、右出一路。"""
    x = GATE_CX - GATE_W / 2
    y = cy - GATE_W / 2
    f.rect(x, y, GATE_W, GATE_W, C.PANEL_HI, alpha=0.95 * a, r=3)
    f.rect_stroke(x, y, GATE_W, GATE_W, C.S3C, lw=1.5 + 1.2 * hot, r=3,
                  alpha=(0.42 + 0.58 * hot) * a)
    f.text("⊕", GATE_CX, cy, 26, C.S3C, C.MONO, WEIGHT_BOLD,
           align="center", anchor_mid=True, alpha=a)


def detail(f, t, a, l1, l2):
    """取一组放大：b0 扇出 + 四个数据位 + 四个异或门 + 输出。"""
    if a <= 0:
        return
    f.rect(PANEL_X, PANEL_Y, PANEL_W, PANEL_H, C.PANEL, alpha=0.9 * a, r=3)
    f.rect_stroke(PANEL_X, PANEL_Y, PANEL_W, PANEL_H, C.EDGE, lw=1.2, r=3)
    f.text("取出码字 %s 放大" % CODEBOOK[SEL], PANEL_X + 22, PANEL_Y + 16, 22,
           C.S3C, C.MONO, WEIGHT_MEDIUM, alpha=a)
    f.text("b0 = %s · 数据位 %s" % (CODEBOOK[SEL][0], "".join(DATA_BITS)),
           PANEL_X + PANEL_W - 22, PANEL_Y + 18, 18, C.INK3, align="right",
           alpha=a * 0.85)

    b0v = int(CODEBOOK[SEL][0])
    flash = pulse(t, l2 + 2.6, 0.8) * (1.0 if t >= l2 + 2.6 else 0.0)

    # ---- b0 方框
    f.rect(B0_X, B0_Y, B0_W, B0_H, C.S3C, alpha=(0.14 + 0.22 * flash) * a, r=3)
    f.rect_stroke(B0_X, B0_Y, B0_W, B0_H, C.S3C, lw=1.8 + 1.4 * flash, r=3,
                  alpha=a)
    f.text("%d" % b0v, B0_X + B0_W / 2, B0_Y + 8, 34, C.S3C, C.MONO,
           WEIGHT_BOLD, align="center", alpha=a)
    f.text("b0", B0_X + B0_W / 2, B0_Y - 26, 20, C.S3C, C.MONO,
           align="center", alpha=a * 0.9)
    f.text("翻转标志", B0_X + B0_W / 2, B0_Y + B0_H + 8, 17, C.INK3,
           align="center", alpha=a * 0.9)

    # ---- b0 到四门的扇出（竖线在数据线左侧，数据线跨过时打拱）
    f.line(B0_X + B0_W, B0_Y + B0_H / 2, BUS_X, B0_Y + B0_H / 2, C.S3C,
           2.6, alpha=0.9 * a)
    f.line(BUS_X, ROWS[0] + 12, BUS_X, ROWS[-1] + 12, C.S3C, 2.6,
           alpha=0.9 * a)
    f.circle(BUS_X, B0_Y + B0_H / 2, 3.4, C.S3C, alpha=0.9 * a)

    for i, cy in enumerate(ROWS):
        kin = ramp(t, l1 + 0.35 + 0.18 * i, l1 + 0.65 + 0.18 * i)
        if kin <= 0:
            continue
        dy = cy - 12
        # 数据位 b1..b4
        f.rect(DATA_X, dy - DATA_H / 2, DATA_W, DATA_H, C.PANEL_HI,
               alpha=0.95 * kin * a, r=6)
        f.rect_stroke(DATA_X, dy - DATA_H / 2, DATA_W, DATA_H, C.EDGE,
                      lw=1.2, r=6, alpha=kin * a)
        f.text(DATA_BITS[i], DATA_X + DATA_W / 2, dy - 14, 26, C.INK, C.MONO,
               WEIGHT_BOLD, align="center", alpha=kin * a)
        f.text("b%d" % (i + 1), DATA_X - 14, dy - 11, 19, C.INK3, C.MONO,
               align="right", alpha=kin * a * 0.95)

        # 数据线：从方框到门，跨过 b0 竖线处打拱
        hx = BUS_X
        f.line(DATA_X + DATA_W, dy, hx - 8, dy, C.INK2, 1.8, alpha=kin * a * 0.85)
        f.arc_stroke(hx, dy, 8, math.pi, 2 * math.pi, C.INK2, 1.8,
                     alpha=kin * a * 0.85)
        f.line(hx + 8, dy, GATE_CX - GATE_W / 2, dy, C.INK2, 1.8,
               alpha=kin * a * 0.85)

        # b0 支线
        f.line(BUS_X, cy + 12, GATE_CX - GATE_W / 2, cy + 12, C.S3C, 2.2,
               alpha=0.85 * kin * a)
        f.circle(BUS_X, cy + 12, 3.2, C.S3C, alpha=0.9 * kin * a)

        # 门与输出
        xgate(f, cy, kin * a, hot=flash)
        f.line(GATE_CX + GATE_W / 2, cy, OUT_X, cy, C.INK2, 1.8,
               alpha=kin * a * 0.85)
        ob = OUT_BITS[b0v][i]
        hot_c = C.S3C if b0v == 1 else C.OKC
        f.rect(OUT_X, cy - OUT_H / 2, OUT_W, OUT_H, hot_c,
               alpha=(0.10 + 0.30 * flash) * kin * a, r=6)
        f.rect_stroke(OUT_X, cy - OUT_H / 2, OUT_W, OUT_H,
                      hot_c if b0v == 1 else C.EDGE,
                      lw=1.2 + 1.2 * flash, r=6, alpha=kin * a)
        f.text(ob, OUT_X + OUT_W / 2, cy - 13, 24, C.INK, C.MONO,
               WEIGHT_BOLD, align="center", alpha=kin * a)

    # ---- 数据流动的小点（一句一动）
    if t > l1 + 0.8:
        for i, cy in enumerate(ROWS):
            p = ((t - (l1 + 0.8)) / 1.55 + 0.13 * i) % 1.0
            if p < 0.06 or p > 0.94:
                continue
            dy = cy - 12
            x = lerp(DATA_X + DATA_W + 6, GATE_CX - GATE_W / 2 - 6, p)
            f.circle(x, dy, 3.6, C.S3C, alpha=0.85 * a)

    f.text("rᵢ = bᵢ ⊕ b0（4 位逐位异或）", PANEL_X + 22, PANEL_Y + PANEL_H - 48,
           21, C.INK2, C.MONO, alpha=a * 0.95)
    C.principle_tag(f, PANEL_X, PANEL_Y + PANEL_H + 12,
                    "门级画法为原理示意；实际是 4 路组合逻辑并行异或",
                    alpha=a * 0.7)


def case_panel(f, x, y, w, h, a, b0v, accent, hot, note):
    if a <= 0:
        return
    f.rect(x, y, w, h, C.PANEL, alpha=(0.86 + 0.10 * hot) * a, r=3)
    f.rect_stroke(x, y, w, h, accent, lw=1.4 + 1.4 * hot, r=3,
                  alpha=(0.30 + 0.70 * hot) * a)
    f.text("b0 = %d" % b0v, x + 24, y + 18, 26, accent, C.MONO,
           WEIGHT_BOLD, alpha=a * (0.55 + 0.45 * hot))
    f.text(note, x + w - 24, y + 22, 20, C.INK2, align="right",
           alpha=a * (0.55 + 0.45 * hot))

    rows = [("码字 b0..b4", [c for c in WIRE[b0v]], C.INK2),
            ("数据 b1..b4", DATA_BITS, C.INK2),
            ("输出 r1..r4", OUT_BITS[b0v], accent if b0v else C.OKC)]
    for i, (lab, bits, col) in enumerate(rows):
        yy = y + 92 + i * 72
        f.text(lab, x + 24, yy + 8, 19, C.INK3, alpha=a * 0.95)
        C.bits_row(f, x + 214, yy, bits, cw=28, ch=38, gap=7, alpha=a,
                   size=22, colors={k: col for k in range(5)},
                   hl={0} if i == 0 else None, hl_c=C.S3C)
        if i < 2:
            f.line(x + 214, yy + 54, x + w - 24, yy + 54, C.EDGE, 1.0,
                   alpha=a * 0.45)

    eq = "rᵢ = bᵢ ⊕ 0 = bᵢ" if b0v == 0 else "rᵢ = bᵢ ⊕ 1 = ¬bᵢ"
    f.text(eq, x + 24, y + h - 48, 22, accent if b0v else C.OKC, C.MONO,
           alpha=a * 0.95)


def band_codebook(f, t, a, l0):
    """码本只有 16 个合法组——重量 ≤ 2。"""
    if a <= 0:
        return
    k = ramp(t, l0 + 1.0, l0 + 1.7)
    f.text("码本：只有汉明重量 ≤ 2 的 16 个 5-bit 字", 150, BAND_Y0 + 2, 22,
           C.INK2, C.SANS, WEIGHT_MEDIUM, alpha=k * a)

    kk = ramp(t, l0 + 1.5, l0 + 2.2)
    x0, y0 = 150, BAND_Y0 + 44
    cw, gap = 12, 3
    for g, bits in enumerate(CODEBOOK):
        gx = x0 + g * (5 * cw + 4 * gap + 16)
        sel = (g == SEL)
        for i, b in enumerate(bits):
            cx = gx + i * (cw + gap)
            f.rect(cx, y0, cw, 20, C.S3C if (sel and i == 0) else C.PANEL,
                   alpha=(0.20 if (sel and i == 0) else 0.9) * kk * a, r=2)
            f.rect_stroke(cx, y0, cw, 20, C.S3C if sel else C.EDGE, lw=1.0,
                          r=2, alpha=(0.9 if sel else 0.6) * kk * a)
            f.text(b, cx + cw / 2, y0 + 1, 13, C.S3C if sel else C.INK3,
                   C.MONO, align="center", alpha=kk * a)

    k3 = ramp(t, l0 + 2.4, l0 + 3.1)
    f.text("1 + 5 + 10 = 16", 150, BAND_Y0 + 92, 24, C.S3C, C.MONO,
           WEIGHT_BOLD, alpha=k3 * a)
    f.text("1 个 00000 ＋ 5 个重量 1 ＋ 10 个重量 2；重量 ≥ 3 的字不会出现在码流里",
           400, BAND_Y0 + 98, 19, C.INK3, alpha=k3 * a * 0.95)


def band_size(f, t, a, l3):
    """81,000 → 64,800 bit，以及 8,100 字节。"""
    if a <= 0:
        return
    f.text("数据量：压到原来的五分之四", 150, BAND_Y0 + 2, 22, C.INK2,
           C.SANS, WEIGHT_MEDIUM, alpha=a)

    k = ramp(t, l3 + 0.2, l3 + 0.85)
    C.bar(f, 400, BAND_Y0 + 50, 760 * k, 24, 1.0, C.INK2, alpha=0.55 * a)
    f.text("输入", 150, BAND_Y0 + 50, 20, C.INK3, alpha=a)
    f.text("81,000 bit", 400 + 772 * k + 4, BAND_Y0 + 50, 20, C.INK2,
           C.MONO, alpha=a)

    k2 = ramp(t, l3 + 0.95, l3 + 1.65)
    C.bar(f, 400, BAND_Y0 + 108, 608 * k2, 24, 1.0, C.S3C, alpha=0.9 * a)
    f.text("输出", 150, BAND_Y0 + 108, 20, C.INK3, alpha=a)
    f.text("64,800 bit", 400 + 620 * k2 + 4, BAND_Y0 + 108, 20, C.S3C,
           C.MONO, alpha=a)

    k3 = ramp(t, l3 + 1.75, l3 + 2.35)
    f.text("81,000 × 4/5 = 64,800 bit", 1360, BAND_Y0 + 44, 20, C.INK2,
           C.MONO, alpha=k3 * a * 0.95)
    f.text("64,800 ÷ 8 = ", 1360, BAND_Y0 + 84, 24, C.INK2, C.MONO,
           alpha=k3 * a)
    f.text("8,100", 1572, BAND_Y0 + 68, 44, C.S3C, C.MONO,
           WEIGHT_BOLD, alpha=k3 * a)
    f.text("B", 1712, BAND_Y0 + 88, 22, C.INK3, C.MONO,
           alpha=k3 * a)
    f.text("去稀后的码字长度", 1360, BAND_Y0 + 128, 19, C.INK3,
           alpha=k3 * a * 0.95)


def band_beats(f, t, a, l4):
    """64 bit 一拍输出，共 1,013 拍。"""
    if a <= 0:
        return
    f.text("硬件节奏：每拍 64 bit", 150, BAND_Y0 + 2, 22, C.INK2,
           C.SANS, WEIGHT_MEDIUM, alpha=a)

    k = ramp(t, l4 + 0.4, l4 + 1.0)
    f.text("1,013", 150, BAND_Y0 + 36, 72, C.S3C, C.MONO, WEIGHT_BOLD,
           alpha=k * a)
    f.text("拍", 150 + 226, BAND_Y0 + 66, 26, C.INK2, alpha=k * a)
    f.text("输出拍数（64 bit / 拍）", 150, BAND_Y0 + 124, 19, C.INK3,
           alpha=k * a * 0.95)

    k2 = ramp(t, l4 + 1.0, l4 + 1.7)
    f.text("64,800 ÷ 64 = 1,012.5", 760, BAND_Y0 + 40, 24, C.INK2, C.MONO,
           alpha=k2 * a)
    f.text("→ 1,013 拍，末拍只有 32 bit 有效", 760, BAND_Y0 + 80, 21,
           C.INK2, alpha=k2 * a * 0.95)
    k3 = ramp(t, l4 + 2.0, l4 + 2.6)
    f.text("输入侧按 64 bit/拍 计：81,000 ÷ 64 ≈ 1,266 拍（进 5 出 4）",
           760, BAND_Y0 + 126, 19, C.INK3, alpha=k3 * a * 0.9)


def draw(f, t, S):
    C.background(f, t)
    C.chapter(f, 5, "三级 · 解稀", C.S3C, t)
    C.footer(f, 5, 9, t)
    C.header(f, "每组 5 bit 取 4 bit，首位当翻转标志", t=t)

    l0, l1, l2 = [C.ls(S, i) for i in range(3)]

    a_strip = ramp(t, l0 + 0.1, l0 + 0.8) * (1.0 - 0.5 * ramp(t, l1 - 0.2,
                                                              l1 + 0.4))
    strip(f, t, a_strip, l0)

    a_det = ramp(t, l1 - 0.2, l1 + 0.4)
    detail(f, t, a_det, l1, l2)

    # 两个对照在讲五位合法模式那句时一起登场，随后依次点亮
    a_case = ramp(t, l1 + 1.1, l1 + 1.7)
    hot_a = ramp(t, l1 + 1.9, l1 + 2.4) * (1.0 - ramp(t, l1 + 3.0, l1 + 3.4))
    hot_b = ramp(t, l1 + 3.3, l1 + 3.7)
    case_panel(f, CASE_A_X, CASE_Y, CASE_W, CASE_H, a_case, 0, C.OKC, hot_a,
               "原样输出")
    case_panel(f, CASE_B_X, CASE_Y, CASE_W, CASE_H, a_case, 1, C.S3C, hot_b,
               "四位全部取反")

    a_c = ramp(t, l0 + 0.8, l0 + 1.4) * (1.0 - ramp(t, l1 - 0.30, l1 - 0.05))
    # 底部两块在同一 y 上放小标题（BAND_Y0 + 2）。只做交叉淡出时，退场的
    # 「码本…」会在 0.2~0.4 的透明度上和新标题「数据量…」叠在同一行，
    # 所以换块之前把 748..952 抹回纸底。
    C.paper_patch(f, t, 0, 748, C.W, 204, ramp(t, l1 - 0.30, l1 - 0.05))
    band_codebook(f, t, a_c, l0)
    # 两块共用同一批坐标：前一块必须在后一块入场前完全退干净，
    # 否则两个小标题会叠在同一行 y 上。
    # 全片压缩后底部只剩「码本」与「数据量」两块，拍数块并入片尾的性能段。
    a_s = ramp(t, l2 - 0.05, l2 + 0.45)
    band_size(f, t, a_s, l2)
