# 生成报告图 12：实拍照 + 编号标记 + 下方四个中文图例框（沿用原 fig-photo.svg 样式）
import base64, io, sys
from PIL import Image
clean, out_svg = sys.argv[1], sys.argv[2]
CROP = (0, 5, 1706, 1160)          # clean.png 坐标
im = Image.open(clean).crop(CROP)
buf = io.BytesIO(); im.save(buf, 'JPEG', quality=90)
b64 = base64.b64encode(buf.getvalue()).decode()
pw, ph = im.size
IX, IY, IW = 45, 45, 1110
s = IW / pw; IH = round(ph * s, 3)
FRAME_H = IH + 30
LY = 30 + FRAME_H + 35             # 图例框顶
VB_H = LY + 112 + 13
def P(x, y):                       # clean.png 坐标 → SVG 坐标
    return IX + x * s, IY + (y - CROP[1]) * s
FONT = 'font-family="Noto Sans CJK SC, sans-serif"'
items = [  # 颜色, 标题, 副标题, 标记位置, 指向点
    ('#2D6A9F', 'BKB220 开发板', 'XC7Z020（PS + PL）', (885, 1125), (975, 1060)),
    ('#168C86', '上位机', '笔记本，运行客户端', (215, 930), None),
    ('#7154A3', '以太网', '经 USB 网卡接上位机', (1490, 1110), (1590, 975)),
    ('#D89027', 'USB 线', 'JTAG 下载与串口日志', (1330, 800), (1270, 718)),
]
o = []
o.append(f'<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink" '
         f'width="2400" height="{2400 * VB_H / 1165.306:.3f}" viewBox="17.347 17.347 1165.306 {VB_H:.3f}">')
o.append(f'<rect x="17.347" y="17.347" width="1165.306" height="{VB_H:.3f}" fill="#FFFFFF" />')
o.append(f'<rect x="30" y="30" width="1140" height="{FRAME_H:.3f}" rx="12" fill="#FFFFFF" stroke="#B9C9D6" stroke-width="2" />')
o.append(f'<image x="{IX}" y="{IY}" width="{IW}" height="{IH}" preserveAspectRatio="xMidYMid meet" '
         f'href="data:image/jpeg;base64,{b64}" xlink:href="data:image/jpeg;base64,{b64}" />')
for i, (c, t1, t2, m, tip) in enumerate(items, 1):
    mx, my = P(*m)
    if tip:
        tx, ty = P(*tip)
        o.append(f'<line x1="{mx:.1f}" y1="{my:.1f}" x2="{tx:.1f}" y2="{ty:.1f}" stroke="#FFFFFF" stroke-width="6" stroke-linecap="round" />')
        o.append(f'<line x1="{mx:.1f}" y1="{my:.1f}" x2="{tx:.1f}" y2="{ty:.1f}" stroke="{c}" stroke-width="3" stroke-linecap="round" />')
        o.append(f'<circle cx="{tx:.1f}" cy="{ty:.1f}" r="5" fill="{c}" stroke="#FFFFFF" stroke-width="2" />')
    o.append(f'<circle cx="{mx:.1f}" cy="{my:.1f}" r="17" fill="{c}" stroke="#FFFFFF" stroke-width="3" />')
    o.append(f'<text x="{mx:.1f}" y="{my + 8:.1f}" text-anchor="middle" {FONT} font-size="22" font-weight="700" fill="#FFFFFF">{i}</text>')
    bx = 35 + (i - 1) * 292
    cx = bx + 127.5
    o.append(f'<rect x="{bx}" y="{LY:.3f}" width="255" height="112" rx="12" fill="#F8FBFD" stroke="{c}" stroke-width="2" />')
    o.append(f'<circle cx="{bx + 28}" cy="{LY + 38:.3f}" r="14" fill="{c}" />')
    o.append(f'<text x="{bx + 28}" y="{LY + 45:.3f}" text-anchor="middle" {FONT} font-size="19" font-weight="700" fill="#FFFFFF">{i}</text>')
    o.append(f'<text x="{cx + 12}" y="{LY + 46:.3f}" text-anchor="middle" {FONT} font-size="23" font-weight="700" fill="{c}">{t1}</text>')
    o.append(f'<text x="{cx}" y="{LY + 84:.3f}" text-anchor="middle" {FONT} font-size="21" font-weight="500" fill="#183044">{t2}</text>')
o.append('</svg>')
open(out_svg, 'w', encoding='utf-8').write('\n'.join(o) + '\n')
print('viewBox h', VB_H)
