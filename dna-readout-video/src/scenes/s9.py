# -*- coding: utf-8 -*-
"""S9 — 收束：一句话把整条链路收回到可验证的原始数据上。

9.77 s，只有两句旁白，所以整场只有一个主动作：链路从左往右长出来，
最后落到右端的「原始数据」上；螺旋只做背景运动，不抢主轴。
"""
import math

from engine.gfx import (clamp, lerp, ramp, ease_out, pulse,
                        WEIGHT_BOLD, WEIGHT_NORMAL, WEIGHT_MEDIUM)
from scenes import common as C

TITLE = "收束"

NODE_Y = 486
NODE_W, NODE_H = 268, 92
NODE_GAP = 46
NODES = [
    ("定位", "Stage 1", C.S1C),
    ("投票", "Stage 2", C.S2C),
    ("解稀", "Stage 3", C.S3C),
    ("纠错", "LDPC", C.LDC),
    ("验收", "上位机", C.OKC),
]


def chain(f, t, a, l0):
    """四级流水逐节长出，最后接上文件名。"""
    if a <= 0:
        return
    total = len(NODES) * NODE_W + (len(NODES) - 1) * NODE_GAP
    x0 = C.W / 2 - total / 2
    for i, (name, tag, col) in enumerate(NODES):
        t_on = l0 + 0.35 + 0.34 * i
        k = ramp(t, t_on, t_on + 0.55)
        if k <= 0:
            continue
        x = x0 + i * (NODE_W + NODE_GAP)
        y = NODE_Y + (1 - ease_out(k)) * 14
        f.rect(x, y, NODE_W, NODE_H, C.PANEL, alpha=0.92 * k * a, r=10)
        f.rect_stroke(x, y, NODE_W, NODE_H, col, lw=1.6, r=10,
                      alpha=0.55 * k * a)
        f.rect(x, y, NODE_W, 3, col, alpha=0.85 * k * a, r=2)
        f.text(name, x + 22, y + 20, 30, C.INK, C.SANS, WEIGHT_BOLD,
               alpha=k * a)
        f.text(tag, x + 22, y + 62, 18, C.INK3, C.MONO, alpha=k * a * 0.9)

        if i < len(NODES) - 1:
            kk = ramp(t, t_on + 0.30, t_on + 0.62)
            C.flow_arrow(f, x + NODE_W + 6, NODE_Y + NODE_H / 2,
                         x + NODE_W + NODE_GAP - 6, NODE_Y + NODE_H / 2,
                         C.INK3, kk, dur=0.4, lw=2.4)


def platform(f, t, a, l1):
    """平台与工具链：只用一行小字交代，不喧宾夺主。"""
    if a <= 0:
        return
    items = ["Zynq-7000 XC7Z020（BKB220）", "PL 100 MHz", "Vivado / Vitis 2026.1"]
    txt = "   ·   ".join(items)
    f.text(txt, C.W / 2, 812, 22, C.INK3, C.SANS, align="center", alpha=a * 0.9)


def draw(f, t, S):
    C.background(f, t, C.OKC)
    C.chapter(f, 9, "收束", C.OKC, t)
    C.footer(f, 9, 9, t)

    l0, l1 = C.ls(S, 0), C.ls(S, 1)

    # 背景螺旋：只做很慢的横向漂移，作为"DNA"这一层的存在感
    C.helix(f, C.W / 2, 900, 1400, t * 0.55, rad=54, pitch=13.0,
            period=170.0, alpha=0.10, rung_alpha=0.30, thickness=0.8)

    # 主标题
    ka = ramp(t, l0 - 0.6, l0 + 0.4)
    if ka > 0:
        dy = (1 - ease_out(ka)) * 16
        f.text("从带噪碱基，到可验证的原始数据", C.W / 2, 286 + dy, 62, C.INK,
               C.SERIF, WEIGHT_BOLD, align="center", alpha=ka)
        f.text("DNA 存储读出 FPGA 加速系统", C.W / 2, 372, 26, C.INK2,
               C.SANS, align="center", alpha=ka * 0.85, spacing=1.15)

    chain(f, t, 1.0, l0)

    # 第二句：PL 四级 + PS 水印 + PC 验收
    kb = ramp(t, l1 + 0.1, l1 + 0.8)
    if kb > 0:
        f.text("四级在 PL，水印在 PS，验收在 PC", C.W / 2, 640, 40, C.OKC,
               C.SANS, WEIGHT_BOLD, align="center", alpha=kb)
        f.text("每一级都保留中间结果，判定标准全部写死在代码里", C.W / 2, 706,
               24, C.INK2, C.SANS, align="center", alpha=kb * 0.85)

    platform(f, t, ramp(t, l1 + 1.2, l1 + 2.0), l1)

    # 尾部淡出：最后 1.1 s 收拢到纸色，给结束留气口（白场收尾，与纸面语言一致）
    end = S["start"] + S["dur"]
    kout = ramp(t, end - 1.3, end - 0.05)
    if kout > 0:
        f.rect(0, 0, C.W, C.H, "#F2EBDD", alpha=0.88 * kout)
