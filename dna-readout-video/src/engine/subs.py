# -*- coding: utf-8 -*-
"""Generate subtitles.srt + subtitles.ass from build/timeline.json.

Timing comes from the measured TTS line durations, so subtitles follow the
actual speech rather than a character-count estimate. Both files are written
next to the MP4 in the video root.

    python3 src/engine/subs.py
"""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
BUILD = os.path.join(ROOT, "build")
SRT_GAP = 0.10          # leave a small gap between consecutive cues


def srt_ts(t):
    ms = int(round(t * 1000))
    h, ms = divmod(ms, 3600000)
    m, ms = divmod(ms, 60000)
    s, ms = divmod(ms, 1000)
    return "%02d:%02d:%02d,%03d" % (h, m, s, ms)


def ass_ts(t):
    cs = int(round(t * 100))
    h, cs = divmod(cs, 360000)
    m, cs = divmod(cs, 6000)
    s, cs = divmod(cs, 100)
    return "%d:%02d:%02d.%02d" % (h, m, s, cs)


def cues(tl):
    # NOTE: build/timeline.json 里 "start" 已是全局绝对秒；"abs_start" 又被
    # 加了一次场景起点（audio.py 的历史 bug），会造成时间轴翻倍。这里用 "start"。
    out = []
    for sc in tl["scenes"]:
        for ln in sc["lines"]:
            st = ln["start"]
            en = st + ln["dur"]
            out.append((st, en, ln["text"]))
    out.sort()
    # 相邻两条之间留 0.10 s 空隙，避免字幕粘连
    fixed = []
    for i, (st, en, txt) in enumerate(out):
        if i + 1 < len(out):
            en = min(en, out[i + 1][0] - SRT_GAP)
        fixed.append((st, max(st + 0.6, en), txt))
    return fixed


ASS_HEAD = """[Script Info]
Title: DNA 存储读出 FPGA 加速系统 — 原理讲解
ScriptType: v4.00+
WrapStyle: 0
ScaledBorderAndShadow: yes
YCbCr Matrix: TV.709

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Sub,Noto Sans CJK SC,34,&H00F2F4F6,&H00F2F4F6,&H90202020,&H70000000,0,0,0,0,100,100,0.6,0,1,2.2,1.6,2,180,180,54,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""


def main():
    with open(os.path.join(BUILD, "timeline.json")) as fh:
        tl = json.load(fh)
    cs = cues(tl)

    srt = []
    for i, (st, en, txt) in enumerate(cs, 1):
        srt.append("%d\n%s --> %s\n%s\n" % (i, srt_ts(st), srt_ts(en), txt))
    p_srt = os.path.join(ROOT, "subtitles.srt")
    with open(p_srt, "w", encoding="utf-8") as fh:
        fh.write("\n".join(srt))

    lines = [ASS_HEAD]
    for st, en, txt in cs:
        lines.append("Dialogue: 0,%s,%s,Sub,,0,0,0,,%s\n"
                     % (ass_ts(st), ass_ts(en), txt.replace("\n", "\\N")))
    p_ass = os.path.join(ROOT, "subtitles.ass")
    with open(p_ass, "w", encoding="utf-8") as fh:
        fh.write("".join(lines))

    print("subtitles.srt  %d cues" % len(cs))
    print("subtitles.ass  %d cues" % len(cs))
    print("last cue ends at %.2f s (video %.2f s)" % (cs[-1][1], tl["total"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
