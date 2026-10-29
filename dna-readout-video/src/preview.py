# -*- coding: utf-8 -*-
"""跑单帧预览：python3 preview.py s3 30.5 [更多时刻...]"""
import importlib
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from engine import video
from engine.gfx import Frame
from scenes import common as C


def main():
    importlib.invalidate_caches()
    names = sys.argv[1].split(",")
    times = [float(x) for x in sys.argv[2:]] or [1.0]
    tl = video.load_timeline()
    idx = {"s1": 1, "s2": 2, "s3": 3, "s4": 4, "s5": 5, "s6": 6, "s7": 7,
           "s8": 8, "s9": 9}
    out = os.path.join(os.path.dirname(HERE), "build", "preview")
    os.makedirs(out, exist_ok=True)
    for nm in names:
        mod = importlib.import_module("scenes." + nm)
        S = tl["scenes"][idx[nm] - 1]
        for t in times:
            f = Frame(C.W, C.H)
            mod.draw(f, t, S)
            p = os.path.join(out, "%s_%06.2f.png" % (nm, t))
            f.write_png(p)
            print(p)


main()
