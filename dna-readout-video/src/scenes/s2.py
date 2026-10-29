# -*- coding: utf-8 -*-
"""S2 — 流水线总览：三级硬件 + 一级软件校验，以及每一级的数据量。"""
import math

from engine.gfx import (Frame, clamp, lerp, ramp, ease_out, pulse,
                        WEIGHT_BOLD, WEIGHT_NORMAL, WEIGHT_MEDIUM)
from scenes import common as C

TITLE = "流水线总览"

STAGES = [
    ("Stage 1", "定位", "滑窗比对", C.S1C, "PL"),
    ("Stage 2", "投票", "差分累加", C.S2C, "PL"),
    ("Stage 3", "解稀", "5b → 4b", C.S3C, "PL"),
    ("LDPC", "纠错", "DVB-S2 R=5/6", C.LDC, "PL"),
    ("验收", "双重判据", "校验子 + SHA-256", C.OKC, "上位机"),
]
# 每一级之间的数据量
LINKS = ["103,616 条\n读出记录", "300+16+10 bit\n每条读出", "81,000 bit\n每层 40,500", "64,800 bit\n8,100 B"]

X0, BW, GAP = 118, 300, 44
Y, BH = 372, 158


def draw(f, t, S):
    C.background(f, t)
    C.chapter(f, 2, "流水线总览", C.S1C, t)
    C.footer(f, 2, 9, t)
    C.header(f, "三级硬件 + 一级软件校验", t=t)

    l0, l1, l2 = C.ls(S, 0), C.ls(S, 1), C.ls(S, 2)
    n = len(STAGES)
    total_w = n * BW + (n - 1) * GAP
    xs = [C.W / 2 - total_w / 2 + i * (BW + GAP) for i in range(n)]

    # ---- 五个方框逐个落位
    for i, (tag, name, sub, col, dom) in enumerate(STAGES):
        k = ramp(t, l0 + 0.10 * i, l0 + 0.10 * i + 0.55)
        if k <= 0.0:
            continue
        x = xs[i]
        y = Y + (1 - ease_out(k)) * 26
        f.rect(x, y, BW, BH, C.PANEL, alpha=0.92 * k, r=10)
        f.rect_stroke(x, y, BW, BH, col, lw=1.6, r=10, alpha=0.55 * k)
        f.rect(x, y, BW, 4, col, alpha=0.85 * k, r=2)
        f.text(tag, x + 20, y + 22, 22, col, C.MONO, WEIGHT_BOLD, alpha=k)
        f.text(name, x + 20, y + 56, 40, C.INK, C.SANS, WEIGHT_BOLD, alpha=k)
        f.text(sub, x + 20, y + 112, 21, C.INK2, C.SANS, alpha=k * 0.95)
        # 硬件/软件域标签
        f.text(dom, x + BW - 20, y + 24, 18, C.INK3, C.MONO, align="right",
               alpha=k * 0.9)

    # 虚线框：PL / 上位机 PC 分界（PS 只做 Stage2.5 的水印异或，不在这一排方框里）
    kbox = ramp(t, l0 + 0.55, l0 + 1.1)
    if kbox > 0:
        xl = xs[0] - 18
        xend = xs[3] + BW + 14          # PL 框右边：包住 LDPC
        xp = xs[4] - 14                 # PC 框左边
        f.rect_stroke(xl, Y - 34, xend - xl, BH + 68, C.S1C, lw=1.2, r=14,
                      alpha=0.30 * kbox, dash=[7, 7])
        f.text("PL · 100 MHz 硬件流水", xl + 14, Y - 30, 19, C.S1C, C.SANS,
               alpha=0.85 * kbox)
        f.rect_stroke(xp, Y - 34, xs[4] + BW + 14 - xp, BH + 68, C.OKC, lw=1.2,
                      r=14, alpha=0.30 * kbox, dash=[7, 7])
        f.text("上位机 PC · Python 客户端", xp + 14, Y - 30, 19, C.OKC, C.SANS,
               alpha=0.85 * kbox)
        f.text("PS（板载 ARM）只做 Stage2.5 的逐字节水印异或", xl + 14,
               Y + BH + 74, 18, C.INK3, alpha=0.8 * kbox)

    # ---- 箭头 + 数据量
    for i in range(n - 1):
        k = ramp(t, l0 + 0.55 + 0.10 * i, l0 + 0.9 + 0.10 * i)
        if k <= 0:
            continue
        xa, xb = xs[i] + BW, xs[i + 1]
        C.flow_arrow(f, xa + 3, Y + BH / 2, xb - 3, Y + BH / 2, C.INK3, k,
                     dur=0.4, lw=2.4)
        f.text(LINKS[i], (xa + xb) / 2, Y + BH + 26, 17, C.INK2, C.SANS,
               align="center", alpha=k * 0.95, spacing=1.3)

    # ---- 第二句：输入规模与数据量收窄
    kin = ramp(t, l1 + 0.4, l1 + 1.2)
    if kin > 0:
        f.text("一条任务：", 112, 236, 24, C.INK3, alpha=kin)
        C.value_label(f, 250, 222, "103,616", "", 34, C.INK, alpha=kin)
        f.text("条读出记录", 250, 274, 20, C.INK3, alpha=kin)
        f.text("= 51,781 × 2（正向/反向各一遍）+ 54 条对齐填充",
               500, 236, 20, C.INK3, alpha=kin * 0.9)
    ksz = ramp(t, l1 + 2.2, l1 + 3.4)
    if ksz > 0:
        f.text("数据量沿链路收窄", C.W - 112, 236, 22, C.INK3, align="right",
               alpha=ksz)

    # ---- 第三句：8,100 B → 54,000 bit → 载荷
    kout = ramp(t, l2 + 0.6, l2 + 1.5)
    if kout > 0:
        y = 660
        f.rect(112, y, C.W - 224, 150, C.PANEL, alpha=0.9 * kout, r=10)
        f.rect_stroke(112, y, C.W - 224, 150, C.EDGE, lw=1.2, r=10)
        f.text("上位机（PC）侧", 140, y + 18, 22, C.OKC, C.SANS, WEIGHT_MEDIUM,
               alpha=kout)
        items = [("8,100", "B", "板子返回的结果码字"),
                 ("54,000", "bit", "取前段作为 LDPC 信息位"),
                 ("≤ 6,750", "B", "按 input_bytes 截断后的载荷上限")]
        for i, (v, u, lab) in enumerate(items):
            kk = ramp(t, l2 + 0.8 + 0.35 * i, l2 + 1.2 + 0.35 * i)
            if kk <= 0:
                continue
            x = 200 + i * 580
            C.value_label(f, x, y + 56, v, u, 52, C.INK if i < 2 else C.S3C,
                          alpha=kk)
            f.text(lab, x, y + 118, 20, C.INK3, alpha=kk * 0.95)
            if i:
                f.line(x - 60, y + 48, x - 60, y + 130, C.EDGE, 1.2,
                       alpha=kk * 0.8)

    # ---- 收束：一句话主轴
    kax = ramp(t, l2 + 3.4, l2 + 4.2)
    if kax > 0:
        f.text("定位 → 投票 → 解稀 → 纠错 → 验收", C.W / 2, 852, 30, C.INK2,
               C.SANS, align="center", alpha=kax * 0.9, spacing=1.1)
