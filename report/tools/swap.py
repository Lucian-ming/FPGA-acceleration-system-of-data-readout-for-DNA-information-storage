# 把新照片直接换进现有 docx / pptx（不重建文档），并清掉海报里两张孤立旧图
import re, sys, zipfile, shutil
OLD_TXT = '图 12 下方四个标注依次对应开发板、以太网、USB（JTAG 与 UART）和电源接口，可据此辨认数据通信、调试观察与供电三类连接。'
NEW_TXT = '图 12 中编号 1～4 依次对应开发板、上位机、以太网和 USB 连接线（JTAG 下载与串口日志），可据此辨认数据通信与调试观察两类连接。'

def rewrite(src, dst, edit):
    zin = zipfile.ZipFile(src)
    tmp = dst + '.tmp'
    with zipfile.ZipFile(tmp, 'w', zipfile.ZIP_DEFLATED) as zout:
        for it in zin.infolist():
            data = edit(it.filename, zin.read(it.filename))
            if data is not None:
                zout.writestr(it, data)
    shutil.move(tmp, dst)

def docx_edit(name, data):
    if name == 'word/media/image13.png':
        return open('/tmp/photo12/fig-photo.png', 'rb').read()
    if name == 'word/document.xml':
        s = data.decode('utf8')
        assert s.count(OLD_TXT) == 1
        s = s.replace(OLD_TXT, NEW_TXT)
        def fix(m):
            b = m.group(0)
            if 'r:embed="rId23"' not in b: return b
            return b.replace('cx="3527490" cy="2700000"', 'cx="3240000" cy="2700000"')
        s2 = re.sub(r'<w:drawing>.*?</w:drawing>', fix, s, flags=re.S)
        assert s2.count('cx="3240000" cy="2700000"') == 2
        return s2.encode('utf8')
    return data

def pptx_edit(name, data):
    if name in ('ppt/media/image2.png', 'ppt/media/image4.png'):
        return None
    if name == 'ppt/media/image3.png':
        return open('/tmp/photo12/poster-photo.png', 'rb').read()
    if name == 'ppt/slides/_rels/slide1.xml.rels':
        s = data.decode('utf8')
        s, n = re.subn(r'<Relationship Id="rId[35]"[^>]*/>', '', s)
        assert n == 2
        return s.encode('utf8')
    return data

rewrite('/tmp/photo12/old/design-report-2026.docx', '/mnt/d/submitwork/report/design-report-2026.docx', docx_edit)
rewrite('/tmp/photo12/old/dna-readout-poster-2026.pptx', '/mnt/d/submitwork/poster/dna-readout-poster-2026.pptx', pptx_edit)
md = '/mnt/d/submitwork/report/design-report-2026.md'
s = open(md, encoding='utf8').read(); assert s.count(OLD_TXT) == 1
open(md, 'w', encoding='utf8').write(s.replace(OLD_TXT, NEW_TXT))
print('ok')
