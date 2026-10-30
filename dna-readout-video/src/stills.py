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
SHOTS = [
    (11.0, "01-问题-带噪读段"),
    (30.0, "02-流水线总览"),
    (56.0, "03-一级滑窗比对"),
    (72.0, "04-一级并行选路"),
    (95.0, "05-二级差分投票"),
    (130.0, "06-三级5比4解稀"),
    (158.0, "07-LDPC-Tanner"),
    (180.0, "08-LDPC-判决分支"),
    (193.0, "09-客户端双判据"),
    (214.0, "10-实测性能"),
    (235.0, "11-实测正确性与长稳"),
    (245.0, "12-收束"),
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
