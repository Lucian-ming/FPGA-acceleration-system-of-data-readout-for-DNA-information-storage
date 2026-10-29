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

# ---- palette (near-black graphite ground; every colour still carries a label)
BG = "#08090B"          # 近黑石墨底
BG2 = "#0C0E11"
PANEL = "#101317"
PANEL_HI = "#151A1F"
EDGE = "#232A31"
GRID = "#8A97A3"        # 网格线色，靠 alpha 压到几乎不可见
INK = "#F2F4F6"
INK2 = "#A2ACB5"
INK3 = "#6B7680"

S1C = "#5AA9E6"   # Stage1 滑窗
S2C = "#7FC8A9"   # Stage2 投票
S3C = "#E7B65C"   # Stage3 解稀
LDC = "#B08BE8"   # LDPC
OKC = "#6FD3C7"   # 验收 / 通过
WARNC = "#E88B6B" # 拒收 / 提示

BASE_C = {"A": "#4EA3FF", "T": "#FFB454", "C": "#52D1A4", "G": "#FF7A93"}
COMP = {"A": "T", "T": "A", "C": "G", "G": "C"}

GRAIN = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                     "assets", "grain.png")

SANS = "Noto Sans CJK SC"
MONO = "DejaVu Sans Mono"

DEG = math.pi / 180.0


# ------------------------------------------------------------------ chrome
def background(f, t, accent=None, drift=True):
    """Near-black graphite ground.

    分层叠加，让画面有纵深而不抢内容：
      1. 竖向渐变（顶部略亮，模拟顶光）
      2. 两个缓慢漂移的柔光斑，颜色跟随本章主色（低到几乎察觉不到）
      3. 极细网格：120 px 细线 + 480 px 主线，随 t 缓慢横移
      4. 斜向扫光，每 14 s 掠过一次
      5. 四周暗角
    """
    f.clear(BG)
    f.grad_v(0, 0, H, [(0.0, "#12161A", 1.0), (0.42, BG, 1.0),
                       (1.0, "#050607", 1.0)])
    f.rect(0, 0, W, H, None)

    acc = accent or "#8FA6B6"
    brt = 0.030 + 0.006 * math.sin(t * 0.55)
    f.glow(560 + 120 * math.sin(t * 0.085), 180 + 60 * math.cos(t * 0.11),
           980, 620, acc, brt)
    f.glow(1460 + 110 * math.sin(t * 0.07 + 2.1), 880 + 50 * math.cos(t * 0.09),
           900, 560, "#5E7C96", brt * 0.55)

    if drift:
        ox = -((t * 5.0) % 480)
        oy = -((t * 1.6) % 480)
    else:
        ox = oy = 0.0
    x = ox - 480
    while x < W + 480:
        f.rect(x, 0, 1, H, GRID, alpha=0.030)
        x += 120
    y = oy - 480
    while y < H + 480:
        f.rect(0, y, W, 1, GRID, alpha=0.026)
        y += 120
    x = ox - 480
    while x < W + 480:
        f.rect(x, 0, 1, H, GRID, alpha=0.055)
        x += 480
    y = oy - 480
    while y < H + 480:
        f.rect(0, y, W, 1, GRID, alpha=0.050)
        y += 480

    # 斜向扫光：14 s 一轮
    sk = ((t % 14.0) / 14.0)
    sx = -900 + sk * (W + 1800)
    f.save()
    f.translate(sx, H / 2)
    f.rotate(-0.28)
    f.grad_h(-260, -760, 520, [(0.0, "#FFFFFF", 0.0), (0.5, "#FFFFFF", 0.020),
                               (1.0, "#FFFFFF", 0.0)])
    f.rect(-260, -760, 520, 1520, None)
    f.restore()

    f.grad_v(0, 0, 220, [(0.0, "#000000", 0.42), (1.0, "#000000", 0.0)])
    f.rect(0, 0, W, 220, None)
    f.grad_v(0, H - 260, 260, [(0.0, "#000000", 0.0), (1.0, "#000000", 0.50)])
    f.rect(0, H - 260, W, 260, None)
    f.grad_h(0, 0, 300, [(0.0, "#000000", 0.46), (1.0, "#000000", 0.0)])
    f.rect(0, 0, 300, H, None)
    f.grad_h(W - 300, 0, 300, [(0.0, "#000000", 0.0), (1.0, "#000000", 0.46)])
    f.rect(W - 300, 0, 300, H, None)
    # 细颗粒：压住暗部色带，也让大面积黑有质感
    f.grain(GRAIN, 0.50)


def chapter(f, num, label, accent, t, x=112, y=64):
    """Top-left chapter chip: a numbered tab + short title."""
    a = clamp(t / 0.45)
    if a <= 0:
        return
    f.save()
    f.translate(0, (1 - ease_out(a)) * -14)
    f.glow(x + 10, y + 15, 190, 46, accent, 0.10 * a)
    f.rect(x, y, 3, 28, accent, alpha=0.95 * a)
    f.text("%02d" % num, x + 18, y - 4, 22, accent, MONO, WEIGHT_BOLD,
           alpha=a)
    f.text(label, x + 62, y - 3, 26, INK2, alpha=a)
    f.restore()


def header(f, text, sub=None, t=0.0, accent=INK, y=104, rule=None):
    """Big scene headline; optional hairline rule that wipes in beneath it."""
    a = ramp(t, 0.0, 0.55)
    if a <= 0:
        return
    dy = (1 - ease_out(a)) * 12
    f.text(text, 112, y + dy, 44, accent, SANS, WEIGHT_BOLD, alpha=a)
    w = f.measure(text, 44, SANS, WEIGHT_BOLD)[0]
    if sub:
        f.text(sub, 112 + w + 26, y + dy + 12, 26, INK2, SANS,
               alpha=a * 0.9)
        w += 26 + f.measure(sub, 26, SANS)[0]
    if rule is not False:
        k = ramp(t, 0.18, 0.95)
        col = rule or (accent if accent != INK else "#3A444C")
        f.line(112, y + 64, 112 + (w + 90) * ease_out(k), y + 64, col, 1.6,
               alpha=0.55 * a)


def footer(f, page, total, t):
    f.text("%02d / %02d" % (page, total), W - 112, H - 62, 20, INK3, MONO,
           align="right")
    f.line(112, H - 78, W - 112, H - 78, GRID, 1.0, alpha=0.10)
    f.line(112, H - 78, 112 + 180 * clamp(t / 0.8), H - 78, INK3, 1.4,
           alpha=0.45)


def caption(f, text, t, y=None, size=26, alpha=1.0, color=None):
    """Soft caption that fades up `t` seconds after its cue.

    Sits above the subtitle baseline so it never fights the burned-in line.
    """
    a = ramp(t, 0.0, 0.55) * alpha
    if a <= 0:
        return
    yy = H - 168 if y is None else y
    dy = (1 - ease_out(ramp(t, 0.0, 0.7))) * 8
    w = f.measure(text, size, SANS)[0]
    f.rect(W / 2 - w / 2 - 22, yy - 8 + dy, w + 44, size + 20, BG2,
           alpha=0.72 * a, r=8)
    f.text(text, W / 2, yy + dy, size, color or INK2, SANS, align="center",
           alpha=a)


def panel(f, x, y, w, h, title=None, accent=None, t=1.0, alpha=0.92):
    f.rect(x, y, w, h, PANEL, alpha=alpha, r=10)
    f.rect_stroke(x, y, w, h, EDGE, lw=1.2, r=10)
    if title:
        f.text(title, x + 20, y + 14, 22, accent or INK2, SANS, WEIGHT_MEDIUM)
    return (x, y, w, h)


def chip(f, x, y, text, color, size=22, padx=12, pady=7, alpha=1.0,
         fill_alpha=0.14):
    w, h = f.measure(text, size)[0], size + pady * 2
    f.rect(x, y, w + padx * 2, h + 4, color, alpha=fill_alpha, r=6)
    f.rect_stroke(x, y, w + padx * 2, h + 4, color, lw=1.0, r=6, alpha=0.5 * alpha)
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
        f.line(x, y_hi, x, y_lo, mix("#2E3F4B", "#9FB6C6", depth),
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
                           sz, BASE_C.get(b, "#8FA6B6"), MONO, WEIGHT_BOLD,
                           alpha=a * 1.5)
                    f.text(comp, x - sz * 0.34,
                           y_lo + (6 if y_lo < y_hi else -sz - 6), sz,
                           BASE_C.get(comp, "#8FA6B6"), MONO, WEIGHT_BOLD,
                           alpha=a * 1.5)

    # backbones: wide soft underlay + crisp core
    for sgn, col in ((1, "#7FB4D8"), (-1, "#5E8CA6")):
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


def bar(f, x, y, w, h, frac, color, track="#1A242C", r=4, alpha=1.0):
    f.rect(x, y, w, h, track, r=r, alpha=alpha)
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
