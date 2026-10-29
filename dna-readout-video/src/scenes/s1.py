# -*- coding: utf-8 -*-
"""S1 — 问题：一次读回是一堆带噪片段。

一镜到底：双螺旋在中心缓慢旋转；第二句时螺旋被切散成读段碎片，碎片上
标注未知位置与错配碱基；第三句收束为两个问号。全部为原理示意。
"""
import math

from engine.gfx import (Frame, clamp, lerp, ramp, ramp_lin, ease_out, ease_in_out,
                        pulse, WEIGHT_BOLD, WEIGHT_NORMAL, rgba, mix)
from scenes import common as C

TITLE = "问题"

# 碎片布局：(中心 x, 中心 y, 长度, 相位, 错配位下标) —— 全部落在 112..1808 安全区内
FRAGS = [
    (520, 250, 26, 0.0, {7}),
    (1280, 210, 30, 1.1, {22}),
    (760, 420, 34, 2.2, set()),
    (1430, 470, 28, 3.3, {3, 21}),
    (430, 640, 22, 4.4, set()),
    (1080, 700, 32, 5.5, {17}),
]

CW = 22.0


def draw_fragment(f, x, y, n, seed, errs, alpha=1.0, cw=22, size=18,
                  unsure=False):
    seq = C.base_seq(n, seed)
    for i, b in enumerate(seq):
        cx = x + i * cw
        bad = i in errs
        col = C.WARNC if bad else C.BASE_C.get(b, C.INK2)
        ch = "N" if bad else b
        f.rect(cx, y, cw - 3, cw - 2, col, alpha=0.09 * alpha, r=3)
        f.text(ch, cx + (cw - 3) / 2, y + 1, size, col, C.MONO, WEIGHT_BOLD,
               align="center", alpha=alpha * (0.95 if not bad else 1.0))
        if bad and unsure:
            f.rect_stroke(cx - 1, y - 1, cw - 1, cw, C.WARNC, lw=1.6, r=4,
                          alpha=0.9 * alpha)


def draw(f, t, S):
    C.background(f, t)
    C.chapter(f, 1, "问题", C.S1C, t)
    C.footer(f, 1, 9, t)

    l1 = C.ls(S, 1)          # 碎片开始
    l2 = C.ls(S, 2)          # 问号
    scene_end = S["dur"]

    # ---- 第一句：完整双螺旋
    helix_a = ramp(t, 0.15, 1.3) * (1.0 - ramp(t, l1 - 0.15, l1 + 0.85))
    if helix_a > 0.01:
        f.save()
        cx = 960
        cy = 470 + math.sin(t * 0.7) * 6
        # 两端淡出，避免硬边
        rot = (t - 1.0) * 0.22
        C.helix(f, cx, cy, 1500, t, phase=rot, bases=C.base_seq(150, 3),
                alpha=helix_a, rung_alpha=0.55, speed=0.55)
        f.restore()
        if t < l1:
            a = ramp(t, 1.1, 1.9)
            C.chip(f, 812, 760, "A", C.BASE_C["A"], 30, 14, 8, alpha=a)
            f.text("A–T", 870, 766, 24, C.INK2, C.MONO, alpha=a)
            f.text("C–G", 946, 766, 24, C.INK2, C.MONO, alpha=a)
            f.text("互补碱基对", 1030, 766, 24, C.INK3, alpha=a)
            C.caption(f, "数据写进碱基序列，读回来的只是一段段短序列",
                      t - 1.1, y=C.H - 168)

    # ---- 第二句：切成带噪碎片
    q = ramp(t, l2 - 0.1, l2 + 0.8)
    frag_a = ramp(t, l1, l1 + 0.7)
    if frag_a > 0.01:
        drift = clamp((t - l1) / 2.4)
        for i, (dx, dy, n, ph, errs) in enumerate(FRAGS):
            k = ramp(t, l1 + 0.12 * i, l1 + 0.12 * i + 0.75)
            if k <= 0.0:
                continue
            half = n * CW / 2.0
            x = 960 + (dx - 960) * (0.55 + 0.45 * ease_out(drift)) - half
            x = min(max(x, 128), C.W - 128 - n * CW)
            y = dy + 120 + math.sin(t * 0.9 + ph) * 9
            draw_fragment(f, x, y, n, 11 + i * 7, errs, alpha=k * 0.95 * (1.0 - 0.72 * q),
                          cw=CW, unsure=True)
            # 未知位置标签
            if k > 0.5:
                f.text("pos ?", x - 2, y - 26, 18, C.INK3, C.MONO,
                       alpha=(k - 0.5) * 1.8)
        if t > l1 + 0.6:
            a = ramp(t, l1 + 0.6, l1 + 1.2)
            C.caption(f, "每段都带噪声：碱基可能读错，位置也可能对不上",
                      t - (l1 + 0.6), y=C.H - 168)

    # ---- 第三句：两个问号
    if q > 0.01:
        f.rect(0, 0, C.W, C.H, C.BG, alpha=0.72 * q)
        f.text("它原本是哪一段？", 960, 380, 62, C.INK, C.SANS, WEIGHT_BOLD,
               align="center", alpha=q)
        f.text("又该还原成什么？", 960, 500, 62, C.S1C, C.SANS, WEIGHT_BOLD,
               align="center", alpha=ramp(t, l2 + 0.7, l2 + 1.4))
        a2 = ramp(t, l2 + 1.4, l2 + 2.0)
        f.line(760, 640, 1160, 640, C.S1C, 1.6, alpha=0.5 * a2)
        f.text("这就是三级流水线要回答的两件事", 960, 668, 30, C.INK2,
               C.SANS, align="center", alpha=a2)


