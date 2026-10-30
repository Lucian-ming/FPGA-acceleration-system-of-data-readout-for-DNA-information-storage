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
    (12.5, "01-问题-带噪读段"),        # 6 条带噪读段铺满，底部结论已出
    (31.0, "02-流水线总览"),           # 五段框图 + 每段比特数到齐
    (67.5, "03-一级滑窗比对"),         # 读出对位、命中/未命中标记、得分曲线峰值同时可见
    (71.0, "04-一级并行选路"),         # 16 个窗口计分格 + 选路树标注
    (112.0, "05-二级差分投票"),        # 投票表 + 判决行 + vote>0 规则 + 交 PS 异或
    (138.5, "06-三级5比4解稀"),        # 门级图 b0=0/1 双例 + 码本 + 压缩比例
    (163.4, "07-LDPC-Tanner"),         # Tanner 图 + 迭代柱状图 + 硬判决位行
    (181.5, "08-LDPC-判决分支"),       # 不收敛分支：保留原码字，客户端判拒收
    (205.5, "09-客户端双判据"),        # 双判据 PASS + 四级取证 + 通过/拒绝两路
    (232.0, "10-实测性能"),            # 四组时延 + 上传段加速比 + 42 例分布
    (236.5, "11-实测正确性与长稳"),    # 2 小时 / 262 轮 / 0 失败
    (246.0, "12-收束"),                # 五段归位 + 平台署名
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
