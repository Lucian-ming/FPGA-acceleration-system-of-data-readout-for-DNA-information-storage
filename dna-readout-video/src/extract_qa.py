# -*- coding: utf-8 -*-
"""从成片按固定步长抽帧，供逐帧版面检查（只读，不改任何交付物）。

    python3 src/extract_qa.py                 # 每 3 秒一帧
    python3 src/extract_qa.py --step 2

写到 build/qa/frames/tXXXXXX.png，并生成 build/qa/index.txt 给出
「帧文件 → 绝对秒 → 所属场景」的对照，方便子 Agent 直接引用。
"""
import argparse
import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)

from engine.video import FFMPEG

# 默认抽最新的渲染产物，避免误抽旧的成片副本
SRC = os.path.join(ROOT, "build", "preview-cut.mp4")
OUT = os.path.join(ROOT, "build", "qa", "frames")
TL = os.path.join(ROOT, "build", "timeline.json")


def scene_at(tl, t):
    cur = tl["scenes"][0]["id"]
    for sc in tl["scenes"]:
        if t >= sc["start"]:
            cur = sc["id"]
    return cur


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--step", type=float, default=3.0)
    ap.add_argument("--src", default=SRC)
    args = ap.parse_args()

    tl = json.load(open(TL))
    total = tl["total"]
    os.makedirs(OUT, exist_ok=True)

    rows = []
    t = 0.5
    while t < total - 0.2:
        name = "t%07.2f.png" % t
        p = os.path.join(OUT, name)
        subprocess.run([FFMPEG, "-v", "error", "-y", "-ss", "%.2f" % t,
                        "-i", args.src, "-frames:v", "1", p], check=True)
        rows.append("%s\t%.2f\t%s" % (name, t, scene_at(tl, t)))
        t += args.step

    idx = os.path.join(ROOT, "build", "qa", "index.txt")
    with open(idx, "w", encoding="utf-8") as fh:
        fh.write("\n".join(rows) + "\n")
    print("%d frames -> %s" % (len(rows), OUT))
    print("index -> %s" % idx)


if __name__ == "__main__":
    main()
