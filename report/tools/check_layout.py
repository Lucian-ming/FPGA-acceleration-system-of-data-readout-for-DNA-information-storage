#!/usr/bin/env python3
"""检查 DNA readout poster v2 的页面几何与文本容量。"""
from pathlib import Path
from zipfile import ZipFile
from lxml import etree
import math
import sys

HERE = Path(__file__).resolve().parent
PPTX = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else HERE / 'dna-readout-poster-2026-v2.pptx'
REPORT = HERE / 'layout.md'
EMU_PER_IN = 914400
P_NS = 'http://schemas.openxmlformats.org/presentationml/2006/main'
A_NS = 'http://schemas.openxmlformats.org/drawingml/2006/main'
R_NS = 'http://schemas.openxmlformats.org/officeDocument/2006/relationships'
NS = {'p': P_NS, 'a': A_NS, 'r': R_NS}
P = '{' + P_NS + '}'
A = '{' + A_NS + '}'

def rect_for(el):
    xfrm = el.find('.//' + A + 'xfrm')
    if xfrm is None:
        raise AssertionError(f"形状缺少 xfrm：{el.tag}")
    off = xfrm.find(A + 'off')
    ext = xfrm.find(A + 'ext')
    if off is None or ext is None:
        raise AssertionError(f"形状缺少 off/ext：{el.tag}")
    return tuple(int(v) for v in (off.get('x'), off.get('y'), ext.get('cx'), ext.get('cy')))

def overlap(a, b):
    ax, ay, aw, ah = a
    bx, by, bw, bh = b
    return min(ax + aw, bx + bw) - max(ax, bx) > 0 and min(ay + ah, by + bh) - max(ay, by) > 0

def inch(v):
    return v / EMU_PER_IN

def char_width(ch):
    if ch.isspace(): return 0.29
    if ch.isdigit(): return 0.56
    if ch.isupper(): return 0.64
    if ch.islower(): return 0.53
    if ord(ch) > 0x2E7F: return 1.00
    if ch in '.,:;!|·': return 0.31
    if ch in '-_+/=()[]<>': return 0.43
    return 0.57

def estimate_text(el, rect):
    body = el.find('./' + P + 'txBody')
    if body is None: return None
    bodypr = body.find(A + 'bodyPr')
    ins = [0, 0, 0, 0]
    if bodypr is not None:
        ins = [int(bodypr.get(k, '0')) for k in ('lIns', 'rIns', 'tIns', 'bIns')]
    width = max(0, rect[2] - ins[0] - ins[1]) / EMU_PER_IN * 72
    available_h = max(0, rect[3] - ins[2] - ins[3]) / EMU_PER_IN * 72
    total = 0.0
    paragraphs = []
    for para in body.findall('./' + A + 'p'):
        text = ''.join(para.xpath('.//a:t/text()', namespaces=NS))
        if not text: continue
        sizes = [int(v) / 100 for v in para.xpath('.//a:rPr/@sz | .//a:endParaRPr/@sz', namespaces=NS)]
        size = max(sizes) if sizes else 10.0
        weight = sum(char_width(c) for c in text)
        lines = max(1, math.ceil((weight * size) / max(width, 1)))
        total += lines * size * 1.22
        ppr = para.find(A + 'pPr')
        if ppr is not None:
            after = ppr.find(A + 'spcAft/' + A + 'spcPts')
            if after is not None: total += int(after.get('val', '0')) / 100
        paragraphs.append((text, lines, size))
    return total, available_h, paragraphs

with ZipFile(PPTX) as z:
    presentation = etree.fromstring(z.read('ppt/presentation.xml'))
    size_el = presentation.find('.//' + P + 'sldSz')
    page_w, page_h = int(size_el.get('cx')), int(size_el.get('cy'))
    assert (page_w, page_h) == (12192000, 6858000), f'页面尺寸不符合要求：{page_w} x {page_h}'
    slide = etree.fromstring(z.read('ppt/slides/slide1.xml'))
    rel_root = etree.fromstring(z.read('ppt/slides/_rels/slide1.xml.rels'))
    rel_map = {e.get('Id'): e.get('Target') for e in rel_root}
    shapes = []
    text_shapes = []
    pictures = []
    for el in slide.xpath('.//p:spTree/*[self::p:sp or self::p:pic or self::p:cxnSp]', namespaces=NS):
        name_el = el.find('.//' + P + 'cNvPr')
        name = name_el.get('name', '(unnamed)') if name_el is not None else '(unnamed)'
        kind = etree.QName(el).localname
        rect = rect_for(el)
        shapes.append((name, kind, rect))
        x, y, w, h = rect
        assert x >= 0 and y >= 0 and w >= 0 and h >= 0 and x + w <= page_w and y + h <= page_h, (
            f'形状越界：{name} rect={(x, y, w, h)} page={(page_w, page_h)}')
        if kind == 'pic':
            pictures.append((name, rect))
        if kind == 'sp' and el.xpath('./p:txBody//a:t', namespaces=NS):
            text_shapes.append((name, rect, el))
    for i, (name_a, rect_a, _) in enumerate(text_shapes):
        for name_b, rect_b, _ in text_shapes[i + 1:]:
            assert not overlap(rect_a, rect_b), f'文本框重叠：{name_a} 与 {name_b}'
    for image_name, image_rect in pictures:
        for text_name, text_rect, _ in text_shapes:
            assert not overlap(image_rect, text_rect), f'图片压住文字：{image_name} 与 {text_name}'
    targets = [rel_map.get(pic.xpath('.//a:blip/@r:embed', namespaces=NS)[0])
               for pic in slide.xpath('.//p:pic', namespaces=NS)]
    assert len(pictures) == 2, f'应保留 AMD 标志和实物照两张图片，实际 {len(pictures)} 张'
    assert set(targets) == {'../media/image1.png', '../media/image3.png'}, f'出现旧流程图或丢失素材：{targets}'
    estimates = []
    for name, rect, el in text_shapes:
        result = estimate_text(el, rect)
        if result is None: continue
        used, available, paras = result
        assert used <= available, (f'文本估算高度超框：{name}，估算 {used:.1f} pt / 可用 {available:.1f} pt；'
                                   f'段落={[(p[0], p[1]) for p in paras]}')
        estimates.append((name, used, available))

lines = [
    '# V2 固定网格矩形表',
    '',
    f'- 页面：{inch(page_w):.3f} × {inch(page_h):.3f} in（{page_w} × {page_h} EMU）',
    f'- 形状：{len(shapes)}；文字框：{len(text_shapes)}；图片：{len(pictures)}（AMD 标志 + 实物照）',
    '',
    '| 名称 | 类型 | X (in) | Y (in) | 宽 (in) | 高 (in) |',
    '|---|---:|---:|---:|---:|---:|',
]
for name, kind, (x, y, w, h) in shapes:
    lines.append(f'| {name} | {kind} | {inch(x):.3f} | {inch(y):.3f} | {inch(w):.3f} | {inch(h):.3f} |')
lines += ['', '## 自检判据', '',
          '- 所有直接形状矩形均位于页面范围内。',
          '- 文字框两两不重叠；图片矩形不与任何文字框重叠。',
          '- 按文本宽度、字体字号及段落行距估算的文字高度均未超过文字框可用高度。',
          '- 图片关系仅引用 AMD 标志 `image1.png` 与实物照 `image3.png`；旧流程图图片未被放入页面。', '']
REPORT.write_text('\n'.join(lines), encoding='utf-8')
print(f'PASS: slide size {page_w} x {page_h} EMU ({inch(page_w):.3f} x {inch(page_h):.3f} in)')
print(f'PASS: shapes={len(shapes)}, text_boxes={len(text_shapes)}, pictures={len(pictures)} (AMD logo + board photo)')
print('PASS: all shape rectangles are within the page')
print(f'PASS: text boxes are pairwise non-overlapping ({len(text_shapes)} checked)')
print(f'PASS: pictures do not overlap text ({len(pictures)} x {len(text_shapes)} checked)')
print(f'PASS: estimated text height is within every frame ({len(estimates)} checked)')
print('PASS: only image1.png (AMD logo) and image3.png (board photo) are placed; old diagram images are absent')
print(f'WROTE: {REPORT}')
