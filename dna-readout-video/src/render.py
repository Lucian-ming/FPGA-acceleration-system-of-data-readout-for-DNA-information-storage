# -*- coding: utf-8 -*-
"""整片渲染：按全局帧号切块并行出无声 H.264，拼起来再混旁白。

用法:
    python3 src/render.py                        # 渲染全部已完成场景
    python3 src/render.py --scenes s1,s2,s3      # 只渲染指定场景
    python3 src/render.py --keep                 # 保留 build/scenes/*.mp4
    python3 src/render.py --no-audio             # 不混旁白

关键点：成片长度必须等于 timeline.json 的 total，否则画面会逐场领先旁白。
所以这里不切场景头尾帧，而是按全局帧号 f 渲染，时间是 t = f / FPS；
场景边界处的溶接在帧函数内部叠加完成（出画场景打底、入画场景按
smoothstep 透明度盖上去），总帧数 = round(total * FPS)，一帧不多不少。
"""
import argparse
import importlib
import json
import os
import sys
import time
from multiprocessing import Process

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)

from engine import video
from engine.gfx import Frame, clamp
from scenes import common as C

BUILD = os.path.join(ROOT, "build")
SCENE_DIR = os.path.join(BUILD, "scenes")
ORDER = ["s1", "s2", "s3", "s4", "s5", "s6", "s7", "s8", "s9"]
NCHUNK = 16              # 并行块数（本机 16 核）


def available():
    out = []
    for nm in ORDER:
        if os.path.exists(os.path.join(HERE, "scenes", nm + ".py")):
            out.append(nm)
    return out


def load_segs(names, by_id):
    segs = []
    for nm in names:
        S = by_id[nm]
        segs.append((importlib.import_module("scenes." + nm), S))
    return segs


def draw_global(f, t, segs, xf):
    """Draw the film at absolute time t, blending across scene boundaries.

    Scene i owns [start_i, start_i + dur_i). The dissolve is centred on the
    boundary and charges the same 0..xf window to both scenes, so it costs no
    timeline. The outgoing scene may be queried up to xf/2 past its end; it is
    clamped to its last frame rather than extrapolated, and every scene ends on
    a held tail anyway.
    """
    n = len(segs)
    i = 0
    for k in range(n):
        if t >= segs[k][1]["start"]:
            i = k

    half = (xf / 2.0) if xf > 0 else 0.0
    b_in = segs[i][1]["start"] if (i > 0 and half) else None
    b_out = segs[i + 1][1]["start"] if (i + 1 < n and half) else None

    # 入画那一侧的半程：上一场打底，本场盖上去
    if b_in is not None and (t - b_in) < half:
        k = clamp((t - (b_in - half)) / xf, 0.0, 1.0)
        mod_p, S_p = segs[i - 1]
        tp = min(t, S_p["start"] + S_p["dur"] - 1.0 / C.FPS)
        mod_p.draw(f, tp, S_p)
        f.push_group()
        segs[i][0].draw(f, t, segs[i][1])
        f.pop_group(k * k * (3 - 2 * k))
        return
    # 出画那一侧的半程：本场打底，下一场盖上去
    if b_out is not None and (t - b_out) > -half:
        k = clamp((t - (b_out - half)) / xf, 0.0, 1.0)
        if k > 0.0:
            tt = min(t, segs[i][1]["start"] + segs[i][1]["dur"] - 1.0 / C.FPS)
            segs[i][0].draw(f, tt, segs[i][1])
            f.push_group()
            segs[i + 1][0].draw(f, t, segs[i + 1][1])
            f.pop_group(k * k * (3 - 2 * k))
            return

    segs[i][0].draw(f, t, segs[i][1])


def render_range(segs, xf, f0, f1, out, crf=18, tag=""):
    """Render global frames [f0, f1) to a silent MP4."""
    width4 = C.W * 4
    enc = video.Encoder(out, C.W, C.H, C.FPS, crf=crf)
    f = Frame(C.W, C.H)
    t0 = time.time()
    n = f1 - f0
    try:
        for j in range(n):
            draw_global(f, (f0 + j) / float(C.FPS), segs, xf)
            buf = f.rgb_bytes()
            if f.stride != width4:              # 行对齐补齐时逐行裁掉
                buf = b"".join(buf[r * f.stride: r * f.stride + width4]
                               for r in range(C.H))
            enc.write(buf)
            if j and j % 300 == 0:
                el = time.time() - t0
                print("  %s %5d/%d  %.1fs  (%.0f fps)" %
                      (tag or "chunk", j, n, el, j / el), flush=True)
    finally:
        f.close()
        got = enc.close()
    print("  %s done: %d frames in %.1fs -> %s" %
          (tag or "chunk", got, time.time() - t0, out), flush=True)
    return got


def _worker(args):
    try:
        render_range(*args)
    except Exception as e:                        # noqa: BLE001
        print("  chunk FAILED: %r" % (e,), flush=True)
        raise


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--scenes", default="")
    ap.add_argument("--out", default=os.path.join(ROOT, "build", "preview-cut.mp4"))
    ap.add_argument("--crf", type=int, default=18)
    ap.add_argument("--keep", action="store_true")
    ap.add_argument("--no-audio", action="store_true")
    ap.add_argument("--serial", action="store_true")
    ap.add_argument("--chunks", type=int, default=NCHUNK)
    ap.add_argument("--xfade", type=float, default=0.55,
                    help="场景溶接时长，秒；0 = 硬切")
    args = ap.parse_args()

    tl = video.load_timeline()
    by_id = {s["id"]: s for s in tl["scenes"]}
    have = available()
    want = ([x.strip() for x in args.scenes.split(",") if x.strip()]
            if args.scenes else have)
    missing = [x for x in want if x not in have]
    if missing:
        sys.exit("场景还没写：%s（已有：%s）" % (",".join(missing), ",".join(have)))

    os.makedirs(SCENE_DIR, exist_ok=True)
    t_all = time.time()
    segs = load_segs(want, by_id)
    xf = max(0.0, args.xfade)

    # 选段渲染时，只有首尾相接的场景才溶接；否则按硬切处理
    if args.scenes:
        for k in range(len(segs) - 1):
            a, b = segs[k][1], segs[k + 1][1]
            if abs((a["start"] + a["dur"]) - b["start"]) > 1e-6:
                xf = 0.0
                break

    total = segs[-1][1]["start"] + segs[-1][1]["dur"]
    if len(segs) == len(tl["scenes"]):
        total = tl["total"]
    nframes = int(round(total * C.FPS))
    print("时间轴 %.3f s -> %d 帧（溶接 %.2f s）" % (total, nframes, xf), flush=True)

    bounds = [int(round(f * nframes / float(args.chunks)))
              for f in range(args.chunks + 1)]
    parts = []
    jobs = []
    for c in range(args.chunks):
        f0, f1 = bounds[c], bounds[c + 1]
        if f1 <= f0:
            continue
        out = os.path.join(SCENE_DIR, "_part%02d.mp4" % c)
        parts.append(out)
        jobs.append((segs, xf, f0, f1, out, args.crf, "%02d[%d-%d)" % (c, f0, f1)))

    if args.serial or args.chunks == 1:
        for jb in jobs:
            render_range(*jb)
    else:
        procs = [Process(target=_worker, args=(jb,)) for jb in jobs]
        for p in procs:
            p.start()
        for p in procs:
            p.join()
        if any(p.exitcode != 0 for p in procs):
            sys.exit("有分块渲染失败，见上面的日志")

    cut = os.path.join(SCENE_DIR, "_video.mp4")
    video.concat(parts, cut)
    vdur = video.duration(cut)
    print("静画 %.3f s（时间轴 %.3f s，差 %+.3f s）"
          % (vdur, total, vdur - total), flush=True)

    if args.no_audio:
        if os.path.abspath(args.out) != os.path.abspath(cut):
            video.run(["-i", cut, "-c", "copy", "-movflags", "+faststart",
                       args.out])
    else:
        mixed = os.path.join(BUILD, "mix.wav")
        audio = mixed if os.path.exists(mixed) else os.path.join(BUILD, "narration.wav")
        if not os.path.exists(audio):
            sys.exit("缺 narration.wav，先跑 python3 src/engine/audio.py")
        print("音轨：%s" % os.path.basename(audio), flush=True)
        tmp = os.path.join(BUILD, "_mix.m4a")
        video.run(["-i", audio, "-t", "%.3f" % vdur, "-c:a", "aac",
                   "-b:a", "192k", "-ar", "48000", "-ac", "2", tmp])
        video.mux(cut, tmp, args.out)
        os.remove(tmp)

    print("总耗时 %.1f s -> %s (%.2f s)" %
          (time.time() - t_all, args.out, video.duration(args.out)), flush=True)

    if not args.keep:
        for p in parts + [cut]:
            try:
                os.remove(p)
            except OSError:
                pass


if __name__ == "__main__":
    main()
