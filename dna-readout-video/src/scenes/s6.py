# -*- coding: utf-8 -*-
"""S6 — 四级：LDPC 纠错（DVB-S2 R=5/6，硬判决 Flooding Min-Sum）。

上：64,800 bit 码字条，按 5/6 切成 54,000 信息位 + 10,800 校验位。
中（第 1–2 句）：5 : 1 的分组比例示意，补足上部留白。
左：小 Tanner 图——6 个变量节点（圆）、4 个校验节点（方），每轮双向传消息。
右：迭代计数 + 每轮校验子条柱（可波动，不单调）→ 收敛门 0 / 10,800。
下：四段说明——参数 / 一轮做什么 / 硬比特不做软量化 / 不收敛走 SAFE_NOCONV。
末：宁可拒绝，也不交出没收敛的结果。

校验子条柱与分组图都只是原理示意，不是实测序列 / 实际校验矩阵。
"""
import math

from engine.gfx import (clamp, lerp, ramp, ease_out, pulse,
                        WEIGHT_BOLD, WEIGHT_NORMAL, WEIGHT_MEDIUM)
from scenes import common as C

TITLE = "四级：LDPC 纠错"

# ---------------------------------------------------------------- 码字条
CW_X, CW_Y, CW_W, CW_H = 112, 212, 1696, 46
INFO_W = CW_W * 54000.0 / 64800.0             # 1413.3
PAR_X = CW_X + INFO_W                          # 1525.3

# ---------------------------------------------------------------- 比例条
STRIP_Y, STRIP_H = 404, 74
STRIP_CW, STRIP_GAP, STRIP_GGAP = 41, 4, 18
STRIP_GROUPS = 6

# ---------------------------------------------------------------- 左：Tanner
TG_X, TG_Y, TG_W, TG_H = 112, 300, 700, 372
VXS = [166, 274, 382, 490, 598, 706]           # 6 个变量节点圆心 x
VY, VR = 392, 23
CXS = [220, 382, 544, 706]                     # 4 个校验节点中心 x
CY_, CS = 576, 20
V_LAB = ["v0", "v1", "v2", "v3", "v4", "v5"]
C_LAB = ["c0", "c1", "c2", "c3"]
EDGES = [(0, 0), (1, 0), (1, 1), (2, 1), (3, 1),
         (3, 2), (4, 2), (5, 2), (5, 3)]
PULSE_EDGES = [(0, 0), (1, 1), (2, 1), (3, 2), (4, 2), (5, 3)]   # ≤ 6 条消息
ROUND_SEC = 2.4                                # 一轮消息往返

# ---------------------------------------------------------------- 右：校验子
SP_X, SP_Y, SP_W, SP_H = 852, 300, 956, 372
CH_X0, CH_BASE = 1150, 546
CH_PITCH, CH_BW = 88, 52
# 每轮非零校验方程数（示意）：第 3 轮比第 2 轮高 —— 不单调
SYN = [186, 118, 141, 76, 49, 21, 0]
CH_SCALE = 160.0 / 186.0
ROUND_LEAD = 1.05                              # 第 1 轮柱相对 l2 的偏移
ROUND_DT = 1.05

# ---------------------------------------------------------------- 底部带
BAND_Y0, BAND_Y1 = 700, 930


# ================================================================ 顶部码字条
def codeword(f, t, a, l0, l1):
    if a <= 0:
        return
    split = ramp(t, l1 + 0.4, l1 + 1.3)
    f.text("码字 64,800 bit", CW_X, CW_Y - 34, 22, C.INK2, C.SANS,
           WEIGHT_MEDIUM, alpha=a * 0.95)
    f.text("PL 译码器 · DVB-S2 码率 5/6", CW_X + CW_W, CW_Y - 34, 21, C.LDC,
           C.SANS, WEIGHT_MEDIUM, align="right", alpha=a * 0.95)

    f.rect(CW_X, CW_Y, CW_W, CW_H, C.LDC, alpha=0.16 * a, r=2)
    f.rect_stroke(CW_X, CW_Y, CW_W, CW_H, C.LDC, lw=1.3, r=2, alpha=0.55 * a)

    kinf = ramp(t, l0 + 0.5, l0 + 1.2)
    f.rect(CW_X, CW_Y, INFO_W, CW_H, C.LDC, alpha=0.34 * kinf * a, r=2)
    if split > 0:
        f.rect(PAR_X, CW_Y, CW_W - INFO_W, CW_H, C.LDC,
               alpha=0.16 * (split - 0.55) / 0.45 * a, r=2)
        f.line(PAR_X, CW_Y - 6, PAR_X, CW_Y + CW_H + 6, C.INK,
               2.0, alpha=0.75 * split * a)

    k1 = ramp(t, l0 + 1.4, l0 + 2.0)
    f.text("信息位 k = 54,000 bit", CW_X + 24, CW_Y + 11, 21, C.INK,
           C.SANS, WEIGHT_MEDIUM, alpha=k1 * a)
    k2 = ramp(t, l1 + 1.3, l1 + 1.9)
    f.text("校验位 n−k = 10,800", PAR_X + (CW_W - INFO_W) / 2, CW_Y + 12, 19,
           C.INK, C.SANS, align="center", alpha=k2 * a)


# ================================================================ 比例条
def ratio_strip(f, t, a, l0, l1):
    """5 : 1 的分组示意——只在开头两句话里出现。"""
    if a <= 0:
        return
    f.text("码率 5/6 的分组：每 5 个信息位配 1 个校验位", CW_X, STRIP_Y - 34,
           22, C.INK2, C.SANS, WEIGHT_MEDIUM, alpha=a * 0.95)
    f.text("示意比例，非实际校验矩阵结构", CW_X + CW_W, STRIP_Y - 32, 18,
           C.INK3, align="right", alpha=a * 0.8)

    total = (STRIP_GROUPS * 6 * STRIP_CW
             + (STRIP_GROUPS * 6 - STRIP_GROUPS - 1) * STRIP_GAP
             + (STRIP_GROUPS - 1) * STRIP_GGAP)
    x_start = CW_X + (CW_W - total) / 2.0

    ki = ramp(t, l0 + 0.7, l0 + 1.4)
    kp = ramp(t, l1 + 0.2, l1 + 1.0)
    for g in range(STRIP_GROUPS):
        gx = x_start + g * (6 * STRIP_CW + 5 * STRIP_GAP + STRIP_GGAP)
        for i in range(5):
            x = gx + i * (STRIP_CW + STRIP_GAP)
            f.rect(x, STRIP_Y, STRIP_CW, STRIP_H, C.LDC,
                   alpha=0.30 * ki * a, r=4)
            f.rect_stroke(x, STRIP_Y, STRIP_CW, STRIP_H, C.LDC, lw=1.2, r=4,
                          alpha=0.55 * ki * a)
        x = gx + 5 * (STRIP_CW + STRIP_GAP)
        f.rect(x, STRIP_Y, STRIP_CW, STRIP_H, C.WARNC,
               alpha=0.20 * kp * a, r=4)
        f.rect_stroke(x, STRIP_Y, STRIP_CW, STRIP_H, C.WARNC, lw=1.2, r=4,
                      alpha=0.70 * kp * a)
        # 组内不再标 "5 : 1"：那行字与上方标题同在 STRIP_Y-30 附近会叠印，
        # 比例信息由底部两条图例给出，这里留空更干净。

    f.text("← 5 个信息位 →", CW_X + 20, STRIP_Y + STRIP_H + 16, 19, C.LDC,
           alpha=ki * a * 0.9)
    f.text("← 1 个校验位 →", CW_X + 300, STRIP_Y + STRIP_H + 16, 19,
           C.WARNC, alpha=kp * a * 0.9)


# ================================================================ 左：Tanner
def edge_pt(v, c):
    return VXS[v], VY + VR, CXS[c], CY_ - CS


def tanner(f, t, a, l2):
    if a <= 0:
        return
    f.rect(TG_X, TG_Y, TG_W, TG_H, C.PANEL, alpha=0.97 * a, r=3)
    f.rect_stroke(TG_X, TG_Y, TG_W, TG_H, C.EDGE, lw=1.2, r=3)
    f.text("Tanner 图 · 变量节点 ↔ 校验节点", TG_X + 20, TG_Y + 14, 22,
           C.LDC, C.SANS, WEIGHT_MEDIUM, alpha=a)
    f.text("示意规模", TG_X + TG_W - 20, TG_Y + 17, 18,
           C.INK3, align="right", alpha=a * 0.8)

    ke = ramp(t, l2 + 0.3, l2 + 0.9)
    if ke > 0:
        for (v, c) in EDGES:
            x0, y0, x1, y1 = edge_pt(v, c)
            f.line(x0, y0, x1, y1, C.EDGE, 1.6, alpha=ke * a)

    # 消息脉冲：下行一轮、上行一轮
    if t > l2 + 0.9:
        phase = ((t - (l2 + 0.9)) / ROUND_SEC) % 2.0
        for i, (v, c) in enumerate(PULSE_EDGES):
            p = (phase + 0.17 * i) % 2.0
            u = p if p < 1.0 else 2.0 - p
            x0, y0, x1, y1 = edge_pt(v, c)
            f.circle(lerp(x0, x1, u), lerp(y0, y1, u), 4.2, C.LDC,
                     alpha=0.9 * a)

    kv = ramp(t, l2 + 0.1, l2 + 0.7)
    for i, x in enumerate(VXS):
        f.circle(x, VY, VR, C.PANEL_HI, alpha=0.95 * kv * a)
        f.circle(x, VY, VR, stroke=C.LDC, lw=1.8, alpha=kv * a)
        f.text(V_LAB[i], x, VY - 8, 18, C.LDC, C.MONO, WEIGHT_BOLD,
               align="center", alpha=kv * a)
        # 圆顶在 VY - VR = 369，15 px 字号的实际字高 13，
        # 基线框放在 VY - 40 才留得下 4 px 空隙
        f.text("1 bit", x, VY - 40, 15, C.INK3, align="center",
               alpha=kv * a * 0.75)

    kc = ramp(t, l2 + 0.5, l2 + 1.1)
    for i, x in enumerate(CXS):
        f.rect(x - CS, CY_ - CS, 2 * CS, 2 * CS, C.PANEL_HI,
               alpha=0.95 * kc * a, r=4)
        f.rect_stroke(x - CS, CY_ - CS, 2 * CS, 2 * CS, C.LDC, lw=1.8, r=4,
                      alpha=kc * a)
        f.text(C_LAB[i], x, CY_ - 8, 17, C.LDC, C.MONO, WEIGHT_BOLD,
               align="center", alpha=kc * a)
        f.text("奇偶校验", x, CY_ + CS + 10, 15, C.INK3, align="center",
               alpha=kc * a * 0.7)

    kl = ramp(t, l2 + 1.2, l2 + 1.8)
    if kl > 0:
        f.circle(TG_X + 26, TG_Y + TG_H - 26, 9, stroke=C.LDC, lw=1.6,
                 alpha=kl * a)
        f.text("变量节点", TG_X + 44, TG_Y + TG_H - 34, 18, C.INK3,
               alpha=kl * a * 0.9)
        f.rect_stroke(TG_X + 146, TG_Y + TG_H - 35, 18, 18, C.LDC, lw=1.6,
                      r=3, alpha=kl * a)
        f.text("校验节点", TG_X + 172, TG_Y + TG_H - 34, 18, C.INK3,
               alpha=kl * a * 0.9)
        f.text("每轮全部节点同时更新（Flooding）", TG_X + 320,
               TG_Y + TG_H - 34, 18, C.INK2, alpha=kl * a * 0.9)


# ================================================================ 右：校验子
def syndrome(f, t, a, l2, l4, l5):
    if a <= 0:
        return
    f.rect(SP_X, SP_Y, SP_W, SP_H, C.PANEL, alpha=0.97 * a, r=3)
    f.rect_stroke(SP_X, SP_Y, SP_W, SP_H, C.EDGE, lw=1.2, r=3)
    f.text("迭代与校验子", SP_X + 20, SP_Y + 14, 22, C.LDC, C.SANS,
           WEIGHT_MEDIUM, alpha=a)

    rt0 = l2 + ROUND_LEAD
    # 迭代计数
    n_round = 0
    for i in range(len(SYN)):
        if t >= rt0 + i * ROUND_DT:
            n_round = i + 1
    kc = ramp(t, l2 + 0.8, l2 + 1.5)
    f.text("迭代轮次", SP_X + 24, SP_Y + 58, 19, C.INK3, alpha=kc * a * 0.95)
    f.text("%d" % n_round, SP_X + 24, SP_Y + 82, 58, C.LDC, C.MONO,
           WEIGHT_BOLD, alpha=kc * a)
    f.text("/ 最多 50 轮", SP_X + 24, SP_Y + 158, 18, C.INK3,
           alpha=kc * a * 0.9)

    # 每轮非零校验方程数
    kk = ramp(t, l2 + 0.2, l2 + 0.9)
    f.text("每轮重算，可能波动 · 不是单调下降", CH_X0 - 40, SP_Y + 58, 19,
           C.INK2, alpha=kk * a * 0.95)
    f.line(CH_X0 - 40, CH_BASE, CH_X0 - 40 + CH_PITCH * len(SYN) - 24,
           CH_BASE, C.EDGE, 1.2, alpha=kk * a)
    for i, h in enumerate(SYN):
        bi = ramp(t, rt0 + i * ROUND_DT - 0.25,
                  rt0 + i * ROUND_DT + 0.2)
        if bi <= 0:
            continue
        x = CH_X0 + i * CH_PITCH
        last = (i == len(SYN) - 1)
        col = C.OKC if last else (C.WARNC if (i > 0 and h > SYN[i - 1])
                                  else C.LDC)
        hh = h * CH_SCALE
        if hh <= 0:
            f.rect(x, CH_BASE - 3, CH_BW, 6, C.OKC, alpha=0.9 * bi * a, r=3)
        else:
            f.rect(x, CH_BASE - hh * bi, CH_BW, hh * bi, col,
                   alpha=0.78 * a, r=3)
        f.text(str(i + 1), x + CH_BW / 2, CH_BASE + 12, 16, C.INK3,
               C.MONO, align="center", alpha=bi * a * 0.9)

    kn = ramp(t, l4 + 0.6, l4 + 1.3)
    f.text("示意序列：第 3 轮校验子高于第 2 轮", CH_X0 - 40,
           CH_BASE + 38, 17, C.INK3, alpha=kn * a * 0.85)

    # 收敛门
    kz = ramp(t, l5 - 0.3, l5 + 0.5)
    if kz > 0:
        f.line(SP_X + 20, SP_Y + SP_H - 72, SP_X + SP_W - 20,
               SP_Y + SP_H - 72, C.EDGE, 1.0, alpha=kz * a * 0.6)
        f.text("收敛判据：10,800 位校验子全零", SP_X + 24,
               SP_Y + SP_H - 44, 20, C.INK2, alpha=kz * a)
        hit = ramp(t, l5 + 0.8, l5 + 1.3)
        f.text("0 / 10,800", SP_X + SP_W - 24, SP_Y + SP_H - 52, 26,
               C.INK if hit < 0.4 else C.OKC, C.MONO, WEIGHT_BOLD,
               align="right", alpha=kz * a)


# ================================================================ 底部带
def band_params(f, t, a, l0):
    if a <= 0:
        return
    f.text("参数：DVB-S2 标准，码率 5/6", 150, BAND_Y0 + 2, 22, C.INK2,
           C.SANS, WEIGHT_MEDIUM, alpha=a)
    items = [("64,800", "bit", "码字总长 n", C.LDC, 0.7),
             ("54,000", "bit", "信息位 k", C.INK, 1.2),
             ("10,800", "bit", "校验位 n−k", C.INK, 1.7)]
    for i, (v, u, lab, col, d) in enumerate(items):
        k = ramp(t, l0 + d, l0 + d + 0.5)
        if k <= 0:
            continue
        x = 160 + i * 440
        C.value_label(f, x, BAND_Y0 + 40, v, u, 46, col, alpha=k * a)
        f.text(lab, x, BAND_Y0 + 112, 20, C.INK3, alpha=k * a * 0.95)
    f.text("码字总长 = 信息位 + 校验位", 1808, BAND_Y0 + 112, 18, C.INK3,
           align="right", alpha=a * 0.8)


def band_round(f, t, a, l2):
    if a <= 0:
        return
    f.text("一轮里发生什么：硬判决 Flooding Min-Sum", 150, BAND_Y0 + 2, 22,
           C.INK2, C.SANS, WEIGHT_MEDIUM, alpha=a)
    steps = [("①", "变量节点把当前比特判断传给相邻校验节点"),
             ("②", "校验节点做最小值运算，回传修正量"),
             ("③", "变量节点累加修正量，更新硬判决")]
    for i, (n, s) in enumerate(steps):
        k = ramp(t, l2 + 0.3 + 0.55 * i, l2 + 0.8 + 0.55 * i)
        if k <= 0:
            continue
        x = 150 + i * 570
        f.text(n, x, BAND_Y0 + 44, 28, C.LDC, C.SANS, WEIGHT_BOLD, alpha=k * a)
        f.text(s, x + 40, BAND_Y0 + 52, 20, C.INK2, alpha=k * a * 0.95)
    k = ramp(t, l2 + 2.1, l2 + 2.7)
    f.text("输入本身就是硬比特，所以不做软信息量化", 150, BAND_Y0 + 130, 22,
           C.OKC, alpha=k * a * 0.95)


def band_hard(f, t, a, l3):
    if a <= 0:
        return
    f.text("硬判决：进门的已经是 0/1", 150, BAND_Y0 + 2, 22, C.INK2,
           C.SANS, WEIGHT_MEDIUM, alpha=a)
    k = ramp(t, l3 + 0.3, l3 + 1.0)
    C.bits_row(f, 150, BAND_Y0 + 40, ["1", "0", "1", "1", "0", "0", "1", "0"],
               cw=34, ch=46, gap=8, alpha=k * a, size=26,
               colors={i: C.LDC for i in range(8)})
    f.text("每一位只有 0 或 1，没有可靠度 / 软 LLR", 640, BAND_Y0 + 48, 21,
           C.INK2, alpha=k * a * 0.95)
    k2 = ramp(t, l3 + 1.0, l3 + 1.7)
    f.text("迭代消息只带 0/1 的取向，不带可靠度权重", 640,
           BAND_Y0 + 84, 19, C.INK3, alpha=k2 * a * 0.85)


def band_gate(f, t, a, l5):
    if a <= 0:
        return
    f.text("判据只有一条：校验子全零才算收敛", 150, BAND_Y0 + 2, 22,
           C.INK2, C.SANS, WEIGHT_MEDIUM, alpha=a)
    k = ramp(t, l5 + 0.2, l5 + 0.9)
    f.text("10,800 位校验子", 150, BAND_Y0 + 44, 22, C.INK3, alpha=k * a)
    f.text("=", 420, BAND_Y0 + 44, 22, C.INK3, C.MONO, alpha=k * a)
    C.bits_row(f, 460, BAND_Y0 + 36, ["0"] * 8, cw=26, ch=40, gap=6,
               alpha=k * a, size=22, colors={i: C.OKC for i in range(8)})
    f.text("…", 760, BAND_Y0 + 42, 26, C.INK3, alpha=k * a)
    k2 = ramp(t, l5 + 0.9, l5 + 1.5)
    f.text("→ 接受，进入验收", 830, BAND_Y0 + 46, 22, C.OKC,
           C.SANS, WEIGHT_MEDIUM, alpha=k2 * a)


def band_noconv(f, t, a, l6):
    if a <= 0:
        return
    f.text("不收敛时：照样把 Stage 3 码字交回去，由客户端拒绝", 150, BAND_Y0 + 2,
           22, C.INK2, C.SANS, WEIGHT_MEDIUM, alpha=a)
    steps = [("Stage 3 原码字", C.INK2, 0.10, 0.14),
             ("校验子非零", C.WARNC, 0.16, 0.32),
             ("客户端拒绝", C.WARNC, 0.16, 0.34),
             ("SAFE_NOCONV", C.WARNC, 0.30, 0.44)]
    # 四段等分横贯整幅，右端留出结论位
    xs = [150, 560, 970, 1380]
    for i, (txt, col, fa, d) in enumerate(steps):
        kk = ramp(t, l6 + 0.3 + d, l6 + 0.9 + d)
        if kk <= 0:
            continue
        nx = C.chip(f, xs[i], BAND_Y0 + 44, txt, col, 22, 15, 9,
                    alpha=kk * a, fill_alpha=fa)
        if i < 3:
            ka = ramp(t, l6 + 0.42 + d, l6 + 0.95 + d)
            C.flow_arrow(f, nx + 6, BAND_Y0 + 62, xs[i + 1] - 16,
                         BAND_Y0 + 62, C.INK3, ka, dur=0.5, lw=2.0)
    k3 = ramp(t, l6 + 1.4, l6 + 2.1)
    if k3 > 0:
        f.line(150, BAND_Y0 + 104, 1708, BAND_Y0 + 104, C.EDGE, 1.0,
               alpha=0.55 * k3 * a)
        f.text("非零校验子判为不收敛，如实上报", 150, BAND_Y0 + 120, 21,
               C.INK3, alpha=k3 * a * 0.95)
        f.text("不收敛时保留 Stage 3 原码字，由客户端拒收", 1708,
               BAND_Y0 + 122, 19, C.INK3, align="right",
               alpha=k3 * a * 0.8)




def draw(f, t, S):
    C.background(f, t)
    C.chapter(f, 6, "四级 · 纠错", C.LDC, t)
    C.footer(f, 6, 9, t)
    C.header(f, "硬判决 Flooding Min-Sum，收敛才交结果", t=t)

    l0, l1, l2, l3, l4, l5, l6, l7 = [C.ls(S, i) for i in range(8)]

    a_cw = ramp(t, l0 + 0.1, l0 + 0.9)
    codeword(f, t, a_cw, l0, l1)

    # 比例条要在两块面板起来之前退净：面板淡入到 0.5 时还是半透明，
    # 比例条若仍停在 0.15，条块与图例会从面板底下透出来。
    a_rs = (ramp(t, l0 + 0.5, l0 + 1.3)
            * (1.0 - ramp(t, l2 - 0.85, l2 - 0.50)))
    ratio_strip(f, t, a_rs, l0, l1)
    C.paper_patch(f, t, 0, 356, C.W, 200, ramp(t, l2 - 0.85, l2 - 0.50))

    a_tg = ramp(t, l2 - 0.4, l2 + 0.4) * (1.0 - 0.4 * ramp(t, l4, l4 + 0.8))
    tanner(f, t, a_tg, l2)
    a_sp = ramp(t, l2 + 0.3, l2 + 1.1)
    syndrome(f, t, a_sp, l2, l4, l5)

    # 底部条带：四段都在 BAND_Y0+2 放小标题，换段前先把 692..952 抹回纸。
    # 只做交叉淡出时，退的那一段会在 0.2~0.4 的透明度上与新标题同 y 叠印
    # （「参数：64,800 / 54,000 / 10,800」曾压到「一轮里发生什么」底下）。
    a_p = ramp(t, l0 + 0.3, l0 + 1.0) * (1.0 - ramp(t, l2 - 0.35, l2 - 0.10))
    C.paper_patch(f, t, 0, 692, C.W, 260, ramp(t, l2 - 0.35, l2 - 0.10))
    band_params(f, t, a_p, l0)
    a_r = ramp(t, l2 - 0.10, l2 + 0.5) * (1.0 - ramp(t, l3 - 0.45, l3 - 0.20))
    C.paper_patch(f, t, 0, 692, C.W, 260, ramp(t, l3 - 0.45, l3 - 0.20))
    band_round(f, t, a_r, l2)
    a_h = ramp(t, l3 - 0.20, l3 + 0.5) * (1.0 - ramp(t, l4 - 0.45, l4 - 0.20))
    C.paper_patch(f, t, 0, 692, C.W, 260, ramp(t, l4 - 0.45, l4 - 0.20))
    band_hard(f, t, a_h, l3)
    a_g = ramp(t, l5 - 0.20, l5 + 0.5) * (1.0 - ramp(t, l6 - 0.45, l6 - 0.20))
    C.paper_patch(f, t, 0, 692, C.W, 260, ramp(t, l6 - 0.45, l6 - 0.20))
    band_gate(f, t, a_g, l5)
    a_n = ramp(t, l6 - 0.20, l6 + 0.5)
    band_noconv(f, t, a_n, l6)

    # 收束：未收敛即拒收
    k = ramp(t, l7 + 0.2, l7 + 1.0)
    if k > 0:
        f.rect(0, 0, C.W, C.H, C.BG, alpha=0.72 * k)
        # 面板要接近不透明：只留 0.72 的底噪会把 Tanner 图与校验子条柱透到标题背后
        f.rect(183, 397, C.W - 360, 216, "#8C7A5E", alpha=0.07 * k, r=16)
        f.rect(180, 392, C.W - 360, 216, C.PANEL, alpha=0.97 * k, r=16)
        f.text("无解就判无解", C.W / 2, 452, 54, C.INK,
               C.SANS, WEIGHT_BOLD, align="center", alpha=k)
        f.line(C.W / 2 - 330, 528, C.W / 2 + 330, 528, C.LDC, 2.0,
               alpha=0.6 * k)
        f.text("50 轮内校验子未归零 → 保留原码字，客户端判拒收", C.W / 2, 552,
               26, C.INK2, C.SANS, align="center", alpha=k * 0.95)
