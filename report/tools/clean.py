# 遮挡背景私人物品与鼠标垫印字，输出裁剪后的干净照片
import sys
from PIL import Image, ImageDraw, ImageFilter
src, out = sys.argv[1], sys.argv[2]
im = Image.open(src).convert('RGB')
W, H = im.size

def soft(box, radius, feather):
    global im
    m = Image.new('L', (W, H), 0)
    ImageDraw.Draw(m).rectangle(box, fill=255)
    m = m.filter(ImageFilter.GaussianBlur(feather))
    im = Image.composite(im.filter(ImageFilter.GaussianBlur(radius)), im, m)

def pixelate(box, cell):
    x0, y0, x1, y1 = box
    r = im.crop(box)
    r = r.resize((max(1, (x1-x0)//cell), max(1, (y1-y0)//cell)), Image.BILINEAR)
    r = r.resize((x1-x0, y1-y0), Image.NEAREST).filter(ImageFilter.GaussianBlur(cell/3))
    im.paste(r, (x0, y0))

# 合影条与相框：强遮挡
pixelate((900, 195, 1118, 498), 22)
# 鼠标垫印字与圆形徽标：强遮挡
pixelate((878, 500, 1062, 548), 14)
soft((1092, 570, 1190, 642), 9, 6)
# 鼠标垫书法字
soft((870, 540, 940, 800), 7, 6)
soft((1290, 545, 1445, 700), 7, 8)
# 笔记本机身二维码贴纸
pixelate((30, 980, 92, 1070), 8)
# 远处杂物（布料、水杯、耳机盒）整体虚化
soft((880, 0, W, 470), 18, 25)
soft((1440, 470, W, 800), 14, 25)
im = im.crop((0, 5, W, 1195))
im.save(out)
print(im.size)
