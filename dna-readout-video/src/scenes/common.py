# -*- coding: utf-8 -*-
"""Shared palette, chrome (background grid, titles, chapter markers) and the
DNA double-helix renderer used across scenes."""

import math
import os

from engine.gfx import (Frame, rgba, mix, lerp, clamp, ramp, ramp_lin,
                        ease_out, ease_in_out, pulse, WEIGHT_BOLD,
                        WEIGHT_NORMAL, WEIGHT_MEDIUM)

W, H = 1920, 1080
FPS = 30

# ---- palette (warm paper ground, ink typography; colour still carries a label)
# 设计语言：印刷品 / 编辑部。纸是暖白，字是墨，强调色是印刷油墨，只用在
# 真正需要区分的地方。不做发光、不做霓虹，靠留白、字号层级和发丝线建立秩序。
BG = "#EFE8DB"          # 纸面底色（暖白）
BG2 = "#F7F2E8"         # 略亮的一层，用于卡片
PANEL = "#FBF8F1"       # 卡片/表面
PANEL_HI = "#E6DCC9"    # 反相填充（位块、轨道）
EDGE = "#D3C7B0"        # 发丝线
GRID = "#B9AC94"        # 网格，靠 alpha 压到几乎不可见
INK = "#241F19"         # 正文墨色
INK2 = "#574E43"
INK3 = "#8C8070"

ACCENT = "#C0623E"      # 印刷朱砂，全片唯一的“热”色，只做强调
S1C = "#2F5D7C"         # Stage1 滑窗 —— 靛蓝
S2C = "#3D7A5C"         # Stage2 投票 —— 松绿
S3C = "#A9761F"         # Stage3 解稀 —— 赭黄
LDC = "#6B4E82"         # LDPC —— 紫
OKC = "#3F7A55"         # 验收 / 通过
WARNC = "#AE4A2C"       # 拒收 / 提示

BASE_C = {"A": "#2F5D7C", "T": "#A9761F", "C": "#3D7A5C", "G": "#AE4A2C"}
COMP = {"A": "T", "T": "A", "C": "G", "G": "C"}

GRAIN = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                     "assets", "paper.png")

SANS = "Noto Sans CJK SC"
SERIF = "Noto Serif CJK SC"
MONO = "DejaVu Sans Mono"

DEG = math.pi / 180.0


# ------------------------------------------------------------------ chrome
def background(f, t, accent=None, drift=True):
    """Warm paper ground.

    印刷纸面：极浅的顶光渐变、几乎看不见的网格、纸纹与四周极淡的暖色压边。
    没有发光斑、没有扫光——静止的纸才是可信的背景，动的东西应该只有内容。
    """
    f.clear(BG)
    f.grad_v(0, 0, H, [(0.0, "#F6EFE2", 1.0), (0.45, BG, 1.0),
                       (1.0, "#E4DACA", 1.0)])
    f.rect(0, 0, W, H, None)

    # 一点点极淡的暖色偏移，让纸不是纯色块
    acc = accent or ACCENT
    f.glow(520 + 90 * math.sin(t * 0.05), 120, 1100, 520, "#FFFFFF", 0.20)
    f.glow(1500 + 80 * math.sin(t * 0.045 + 2.1), 940, 900, 460, acc, 0.022)

    if drift:
        ox = -((t * 2.2) % 96)
        oy = -((t * 0.8) % 96)
    else:
        ox = oy = 0.0
    x = ox - 96
    while x < W + 96:
        f.rect(x, 0, 1, H, GRID, alpha=0.085)
        x += 96
    y = oy - 96
    while y < H + 96:
        f.rect(0, y, W, 1, GRID, alpha=0.070)
        y += 96

    # 四周压边：暖褐，极淡，只用来把视线收进版面
    f.grad_v(0, 0, 200, [(0.0, "#8C7A5E", 0.10), (1.0, "#8C7A5E", 0.0)])
    f.rect(0, 0, W, 200, None)
    f.grad_v(0, H - 240, 240, [(0.0, "#8C7A5E", 0.0), (1.0, "#8C7A5E", 0.13)])
    f.rect(0, H - 240, W, 240, None)
    f.grad_h(0, 0, 260, [(0.0, "#8C7A5E", 0.09), (1.0, "#8C7A5E", 0.0)])
    f.rect(0, 0, 260, H, None)
    f.grad_h(W - 260, 0, 260, [(0.0, "#8C7A5E", 0.0), (1.0, "#8C7A5E", 0.09)])
    f.rect(W - 260, 0, 260, H, None)

    f.grain(GRAIN, 0.55)


def chapter(f, num, label, accent, t, x=112, y=58):
    """Running head: mono numeral, hairline, sans label."""
    a = clamp(t / 0.45)
    if a <= 0:
        return
    f.save()
    f.translate(0, (1 - ease_out(a)) * -14)
    f.text("%02d" % num, x, y, 19, accent, MONO, WEIGHT_BOLD, alpha=a,
           spacing=1.25)
    f.text(label, x + 54, y - 3, 24, INK2, SANS, alpha=a * 0.95)
    f.line(x, y + 34, x + 232, y + 34, INK3, 1.0, alpha=0.28 * a)
    f.restore()


def header(f, text, sub=None, t=0.0, accent=INK, y=100, rule=None):
    """Scene headline in serif; hairline rule wipes in beneath it."""
    a = ramp(t, 0.0, 0.55)
    if a <= 0:
        return
    dy = (1 - ease_out(a)) * 14
    size = 54
    f.text(text, 112, y + dy, size, accent, SERIF, WEIGHT_BOLD, alpha=a)
    w = f.measure(text, size, SERIF, WEIGHT_BOLD)[0]
    if sub:
        f.text(sub, 112 + w + 30, y + dy + 18, 26, INK2, SANS,
               alpha=a * 0.9)
        w += 30 + f.measure(sub, 26, SANS)[0]
    if rule is not False:
        k = ramp(t, 0.18, 0.95)
        col = rule or INK
        f.line(112, y + 78, 112 + (w + 120) * ease_out(k), y + 78, col, 1.4,
               alpha=0.22 * a)
        f.line(112, y + 78, 112 + 120 * ease_out(k), y + 78, ACCENT, 2.6,
               alpha=0.85 * a)


def footer(f, page, total, t):
    f.line(112, H - 84, W - 112, H - 84, GRID, 1.0, alpha=0.28)
    f.line(112, H - 84, 112 + 160 * clamp(t / 0.8), H - 84, ACCENT, 2.0,
           alpha=0.65)
    f.text("%02d" % page, W - 176, H - 66, 20, INK, MONO, WEIGHT_BOLD,
           align="left", spacing=1.2)
    f.text("/ %02d" % total, W - 148, H - 66, 20, INK3, MONO, align="left")


def caption(f, text, t, y=None, size=26, alpha=1.0, color=None):
    """Caption line with a small ochre tick; no plate — the paper is the plate."""
    a = ramp(t, 0.0, 0.55) * alpha
    if a <= 0:
        return
    yy = H - 172 if y is None else y
    dy = (1 - ease_out(ramp(t, 0.0, 0.7))) * 8
    w = f.measure(text, size, SANS)[0]
    x0 = W / 2 - w / 2
    f.rect(x0 - 26, yy + 6 + dy, 12, 2, ACCENT, alpha=0.85 * a)
    f.text(text, x0, yy + dy, size, color or INK2, SANS, align="left",
           alpha=a)


def panel(f, x, y, w, h, title=None, accent=None, t=1.0, alpha=0.92):
    f.rect(x + 3, y + 5, w, h, "#8C7A5E", alpha=0.055 * alpha, r=3)
    f.rect(x, y, w, h, PANEL, alpha=alpha, r=3)
    f.rect_stroke(x, y, w, h, EDGE, lw=1.1, r=3, alpha=0.95 * alpha)
    if title:
        f.text(title, x + 22, y + 16, 22, accent or INK2, SANS, WEIGHT_MEDIUM)
    return (x, y, w, h)


def chip(f, x, y, text, color, size=22, padx=12, pady=7, alpha=1.0,
         fill_alpha=0.10):
    w, h = f.measure(text, size)[0], size + pady * 2
    f.rect(x, y, w + padx * 2, h + 4, color, alpha=fill_alpha, r=3)
    f.rect_stroke(x, y, w + padx * 2, h + 4, color, lw=1.0, r=3,
                  alpha=0.55 * alpha)
    f.text(text, x + padx, y + pady - 1, size, color, SANS, alpha=alpha)
    return x + w + padx * 2 + 10


def arrow(f, x0, y0, x1, y1, c, lw=2.4, head=11, alpha=1.0, dash=None):
    f.line(x0, y0, x1, y1, c, lw, alpha=alpha, dash=dash)
    ang = math.atan2(y1 - y0, x1 - x0)
    for s in (+1, -1):
        f.line(x1, y1,
               x1 - head * math.cos(ang + s * 0.42),
               y1 - head * math.sin(ang + s * 0.42), c, lw, alpha=alpha)


def flow_arrow(f, x0, y0, x1, y1, c, t, dur=0.5, lw=3.0):
    """Arrow whose shaft grows with t — the standard 'signal moves on' beat."""
    k = ease_out(clamp((t - 0.0) / dur))
    if k <= 0.001:
        return
    xe, ye = lerp(x0, x1, k), lerp(y0, y1, k)
    f.line(x0, y0, xe, ye, c, lw, alpha=0.85)
    if k > 0.75:
        ang = math.atan2(y1 - y0, x1 - x0)
        for s in (+1, -1):
            f.line(xe, ye, xe - 13 * math.cos(ang + s * 0.42),
                   ye - 13 * math.sin(ang + s * 0.42), c, lw, alpha=0.85)


def label_box(f, x, y, text, color, size=24, alpha=1.0):
    w = f.measure(text, size)[0]
    f.rect(x - 8, y - 6, w + 16, size + 12, BG2, alpha=0.85 * alpha, r=5)
    f.text(text, x, y, size, color, alpha=alpha)
    return w


def counter(f, x, y, value, frac, color, label, size=64, alpha=1.0):
    f.rect(x, y, frac, 4, color, alpha=0.85 * alpha)
    f.text(value, x, y + 18, size, color, MONO, WEIGHT_BOLD, alpha=alpha)
    if label:
        f.text(label, x, y + 18 + size + 6, 20, INK3, alpha=alpha)


# ------------------------------------------------------------------ DNA
def helix(f, cx, cy, length, t, phase=0.0, rad=48, pitch=12.0, period=156.0,
          alpha=1.0, rung_alpha=0.5, speed=1.0, bases=None, letters=True,
          letter_dt=None, thickness=1.0):
    """True double helix drawn in perspective, running horizontally.

    Backbones are two sinusoids 180 deg out of phase; base pairs are rungs
    sampled along x, drawn with depth-scaled width/opacity so the strand reads
    as a 3-D coil rather than two flat waves.
    """
    x0 = cx - length / 2.0
    x1 = cx + length / 2.0
    k = 2 * math.pi / period
    w = 2 * math.pi / pitch
    ph = phase + t * speed

    def y_at(x, sgn):
        return cy + rad * math.sin(k * (x - cx) - ph + (0 if sgn > 0 else math.pi))

    # rungs first so the backbones sit on top
    n_rung = int(length / pitch)
    for i in range(n_rung):
        x = x0 + (i + 0.5) * pitch
        if x > x1:
            break
        y_hi, y_lo = y_at(x, 1), y_at(x, -1)
        # depth: 1 when the pair is face-on (y near centre of the coil)
        d_hi = math.cos(k * (x - cx) - ph)
        depth = (d_hi + 1) / 2.0                 # 0..1
        a = rung_alpha * (0.30 + 0.70 * depth) * alpha
        f.line(x, y_hi, x, y_lo, mix("#B8A98F", "#6B5F4C", depth),
               1.2 + 1.8 * depth, alpha=a)
        if bases:
            b = bases[i % len(bases)]
            comp = COMP.get(b, "A")
            gap = abs(y_hi - y_lo)
            if letters and gap > 34:
                z = 0.62 + 0.38 * depth
                sz = int(19 * z * thickness)
                if sz >= 12:
                    f.text(b, x - sz * 0.34, y_hi + (6 if y_hi < y_lo else -sz - 6),
                           sz, BASE_C.get(b, "#7A6E5C"), MONO, WEIGHT_BOLD,
                           alpha=a * 1.5)
                    f.text(comp, x - sz * 0.34,
                           y_lo + (6 if y_lo < y_hi else -sz - 6), sz,
                           BASE_C.get(comp, "#7A6E5C"), MONO, WEIGHT_BOLD,
                           alpha=a * 1.5)

    # backbones: wide soft underlay + crisp core
    for sgn, col in ((1, "#2F5D7C"), (-1, "#5C7F97")):
        pts = []
        x = x0
        while x <= x1:
            pts.append((x, y_at(x, sgn)))
            x += 8
        f.polyline(pts, col, 7.0, alpha=0.10 * alpha)
        f.polyline(pts, col, 2.6, alpha=0.85 * alpha)


def base_seq(n, seed=1, alphabet="ACGT"):
    """Deterministic pseudo-random base string (illustrative, never measured)."""
    x = seed * 2654435761 & 0xFFFFFFFF
    out = []
    for _ in range(n):
        x = (1103515245 * x + 12345) & 0x7FFFFFFF
        out.append(alphabet[(x >> 16) % len(alphabet)])
    return "".join(out)


# ------------------------------------------------------------------ timing
def ls(S, i):
    """Start time of narration line i inside its scene."""
    return S["lines"][i]["start"]


def ld(S, i):
    """Duration of narration line i."""
    return S["lines"][i]["dur"]


def after(S, i, frac=1.0):
    """Fraction of the way through line i (0 = start, 1 = end)."""
    return ls(S, i) + ld(S, i) * frac


def principle_tag(f, x, y, text="原理示意 · 非实测波形", alpha=0.75):
    f.text(text, x, y, 18, INK3, SANS, alpha=alpha)


# ------------------------------------------------------------------ data marks
def bits_row(f, x, y, bits, cw=20, ch=28, gap=4, alpha=1.0, hl=None,
             hl_c=None, colors=None, size=18, dim=None):
    """Draw a run of bits as chips. hl: indices drawn with hl_c ring."""
    hl = hl or set()
    for i, b in enumerate(bits):
        cx = x + i * (cw + gap)
        base = (colors or {}).get(i, INK2)
        a = alpha * (0.35 if (dim and i in dim) else 1.0)
        f.rect(cx, y, cw, ch, PANEL_HI if b == "0" else PANEL, alpha=a, r=3)
        f.rect_stroke(cx, y, cw, ch, EDGE, lw=1.0, r=3, alpha=a)
        f.text(b, cx + cw / 2, y + (ch - size) / 2 - 2, size, base, MONO,
               WEIGHT_BOLD, align="center", alpha=a)
        if i in hl:
            f.rect_stroke(cx - 2, y - 2, cw + 4, ch + 4, hl_c or S1C, lw=2.0,
                          r=4, alpha=a)


def base_row(f, x, y, seq, cw=26, size=20, alpha=1.0, hl=None, hl_c=None):
    hl = hl or set()
    for i, b in enumerate(seq):
        cx = x + i * cw
        f.rect(cx, y, cw - 4, cw - 3, BASE_C.get(b, INK2), alpha=0.10 * alpha, r=3)
        f.text(b, cx + (cw - 4) / 2, y + 3, size, BASE_C.get(b, INK2), MONO,
               WEIGHT_BOLD, align="center", alpha=alpha)
        if i in hl:
            f.rect_stroke(cx - 1, y - 1, cw - 2, cw - 1, hl_c or S1C, lw=2.0,
                          r=3, alpha=alpha)


def bar(f, x, y, w, h, frac, color, track=None, r=2, alpha=1.0):
    f.rect(x, y, w, h, track or PANEL_HI, r=r, alpha=alpha)
    if frac > 0:
        f.rect(x, y, max(2, w * clamp(frac)), h, color, r=r, alpha=alpha)


def value_label(f, x, y, value, unit="", size=34, color=INK, align="left",
                alpha=1.0):
    f.text(value, x, y, size, color, MONO, WEIGHT_BOLD, align=align, alpha=alpha)
    if unit:
        w = f.measure(value, size, MONO, WEIGHT_BOLD)[0]
        f.text(unit, x + (w + 6 if align == "left" else -(w + 6)), y + size * 0.42,
               20, INK3, SANS, align=align, alpha=alpha)


def big_number(f, x, y, value, unit, label, color, t=1.0, size=76):
    a = clamp(t)
    value_label(f, x, y, value, unit, size, color, alpha=a)
    if label:
        f.text(label, x, y + size + 12, 22, INK3, alpha=a)


def callout(f, x0, y0, x1, y1, text, color, t=1.0, size=21):
    """Leader line from an object to a small text label."""
    k = clamp(t)
    if k <= 0:
        return
    xe, ye = lerp(x0, x1, k), lerp(y0, y1, k)
    f.line(x0, y0, xe, ye, color, 1.4, alpha=0.55)
    f.circle(x0, y0, 3.2, color, alpha=0.8 * k)
    if k > 0.6:
        f.text(text, x1 + (12 if x1 >= x0 else -12), y1 - 12, size,
               color, SANS, align="left" if x1 >= x0 else "right",
               alpha=(k - 0.6) / 0.4)


def and_gate(f, x, y, w=64, h=44, color=OKC, alpha=1.0, label=None):
    f.save()
    f.rect(x, y, w * 0.62, h, None, alpha=alpha)
    f.color(color, alpha)
    from engine.gfx import cairo_arc, cairo_fill, cairo_move_to, cairo_line_to, cairo_close_path
    f.restore()
    # simple AND shape: rectangle + semicircle
    f.rect(x, y, w * 0.55, h, None)
    f.arc_stroke(x + w * 0.55, y + h / 2, h / 2, -1.5707963, 1.5707963, color, 2.0, alpha)
    f.rect_stroke(x, y, w * 0.55, h, color, 2.0, alpha=alpha)
    if label:
        f.text(label, x + w / 2, y + h + 8, 18, color, SANS, align="center",
               alpha=alpha)
