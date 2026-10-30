# -*- coding: utf-8 -*-
"""从成片抽关键帧到 stills/，文件名带时间点，便于核对。

    python3 src/stills.py
"""
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)

from engine.video import FFMPEG

# (时间, 文件名)
# 取帧点必须落在该场「内容到齐、还没开始收尾」的窗口里：
# 太早只有标题和半透明的第一行，太晚会吃到收尾叠层。
# 下面每一点都在成片里逐帧看过再定的。
SHOTS = [
    (11.90, "01-问题-带噪读段"),       # 两问 + 结论句到齐，背景读段铺满
    (23.20, "02-流水线总览"),          # 五段框图 + 每段比特数 + PC 侧三格
    (32.50, "03-一级滑窗比对"),        # 参考串、候选起点、读出就位
    (46.60, "04-一级并行选路"),        # 64 条读出编号 + 300/16/10 输出
    (58.50, "05-二级差分投票"),        # 819 标尺 + 峰值 + 差分说明
    (66.50, "06-二级判决与水印"),      # 判决行 + 门限 67 + PS 逐字节异或
    (76.60, "07-三级5比4解稀"),        # 门级图 b0=0/1 双例 + 码本
    (93.50, "08-LDPC-Tanner"),         # Tanner 图 + 逐轮波动 + 硬判决位行
    (99.50, "09-LDPC-判决分支"),       # 不收敛分支：保留原码字，客户端判拒收
    (108.60, "10-客户端双判据"),       # 双判据 PASS + 四级取证 + 通过/拒绝两路
    (124.50, "11-实测性能与正确性"),   # 四组时延 + 上传加速比 + 42 例 + 2 小时 262 轮
    (134.80, "12-收束"),               # 五段归位 + 平台署名
]


def main():
    src = os.path.join(ROOT, "dna-readout-explainer.mp4")
    out = os.path.join(ROOT, "stills")
    os.makedirs(out, exist_ok=True)
    for t, name in SHOTS:
        p = os.path.join(out, name + ".png")
        subprocess.run([FFMPEG, "-v", "error", "-y", "-ss", "%.2f" % t,
                        "-i", src, "-frames:v", "1", p], check=True)
        print("%6.2f s  %s" % (t, name + ".png"), flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
