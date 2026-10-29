# -*- coding: utf-8 -*-
"""Narration synthesis and timeline construction.

Each script line is synthesised separately (edge-tts, zh-CN neural), decoded to
48 kHz mono PCM, and measured. The measured durations place every line on the
timeline, so subtitles and animations follow the actual speech rather than a
character-count guess. Output: build/narration.wav + build/timeline.json.
"""
import hashlib
import json
import os
import struct
import subprocess
import time
import sys
import wave

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import script  # noqa: E402  (needs src/ on the path first)

SR = 48000
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))    # dna-readout-video/
BUILD = os.path.join(ROOT, "build")
CACHE = os.path.join(BUILD, "tts")
FFMPEG = "/home/lucian/venvs/vscode-py38/lib/python3.8/site-packages/imageio_ffmpeg/binaries/ffmpeg-linux64-v4.2.2"
EDGE_TTS = "/home/lucian/venvs/vscode-py38/bin/edge-tts"

# Speaking pace inside this range is what the pacing budget assumes.
PACE_LO, PACE_HI = 3.4, 4.6


def _run(cmd, tries=4, **kw):
    """Run a command, retrying: edge-tts drops the odd websocket/network call."""
    last = None
    for k in range(tries):
        try:
            return subprocess.run(cmd, check=True, stdout=subprocess.PIPE,
                                  stderr=subprocess.PIPE, **kw)
        except subprocess.CalledProcessError as e:
            last = e
            time.sleep(1.5 * (k + 1))
    raise last


def synth(text, idx):
    """Synthesise one line to 48k mono WAV, cached by a hash of voice+rate+text."""
    os.makedirs(CACHE, exist_ok=True)
    key = hashlib.sha1(("%s|%s|%s" % (script.VOICE, script.RATE,
                                      text)).encode("utf-8")).hexdigest()[:12]
    stem = os.path.join(CACHE, "l%03d_%s" % (idx, key))
    wav, mp3 = stem + ".wav", stem + ".mp3"
    if os.path.exists(wav) and os.path.getsize(wav) > 1000:
        return wav
    _run([EDGE_TTS, "--voice", script.VOICE, "--rate=" + script.RATE,
          "--text", text, "--write-media", mp3])
    _run([FFMPEG, "-y", "-v", "error", "-i", mp3,
          "-ar", str(SR), "-ac", "1", "-sample_fmt", "s16", wav])
    return wav


def read_wav(path):
    with wave.open(path, "rb") as w:
        assert w.getframerate() == SR and w.getnchannels() == 1, path
        n = w.getnframes()
        data = w.readframes(n)
    return list(struct.unpack("<%dh" % n, data)), n


def trim_silence(samples, thresh=180, pad_ms=40):
    """Drop leading/trailing near-silence edge-tts leaves around a sentence."""
    n = len(samples)
    a, b = 0, n - 1
    while a < n and abs(samples[a]) < thresh:
        a += 1
    while b > a and abs(samples[b]) < thresh:
        b -= 1
    pad = int(SR * pad_ms / 1000.0)
    a = max(0, a - pad)
    b = min(n - 1, b + pad)
    if b <= a:
        return samples
    return samples[a:b + 1]


def build(force=False):
    os.makedirs(BUILD, exist_ok=True)
    timeline = {"sr": SR, "voice": script.VOICE, "scenes": []}
    mix = []
    idx = 0
    for sc in script.SCENES:
        lead = script.LEAD.get(sc["id"], 0.5)
        tail = script.TAIL.get(sc["id"], 0.6)
        cur = len(mix) / float(SR) + lead
        lines = []
        for text in sc["lines"]:
            wav = synth(text, idx)
            idx += 1
            samples, _ = read_wav(wav)
            samples = trim_silence(samples)
            dur = len(samples) / float(SR)
            chars = len(text.replace(" ", ""))
            pace = chars / dur if dur > 0 else 0
            if not (PACE_LO <= pace <= PACE_HI):
                print("  [pace] %-28s %5.2f 字/秒  %r" % (sc["id"], pace, text))
            lines.append({"text": text, "start": round(cur, 3),
                          "dur": round(dur, 3), "chars": chars,
                          "pace": round(pace, 2)})
            start_s = int(round(cur * SR))
            need = start_s + len(samples)
            if len(mix) < need:
                mix.extend([0] * (need - len(mix)))
            for k, s in enumerate(samples):
                mix[start_s + k] += int(s * 0.9)
            cur += dur + script.GAP
        # scene duration = lead + sum(line dur) + gaps + tail
        dur_scene = lead + sum(l["dur"] for l in lines) + script.GAP * (len(lines) - 1) + tail
        timeline["scenes"].append({
            "id": sc["id"], "title": sc["title"],
            "dur": round(dur_scene, 3), "lines": lines,
        })
        print("  %-3s %-18s %6.2f s  (%d 行)" % (sc["id"], sc["title"],
                                                  dur_scene, len(lines)))
        # pad the mix with the gap + tail silence
        pad_to = int(round((cur - script.GAP + tail) * SR))
        if len(mix) < pad_to:
            mix.extend([0] * (pad_to - len(mix)))

    # absolute scene starts + global line numbering
    t = 0.0
    n = 0
    for sc in timeline["scenes"]:
        sc["start"] = round(t, 3)
        t += sc["dur"]
        for l in sc["lines"]:
            l["abs_start"] = round(sc["start"] + l["start"], 3)
            l["index"] = n
            n += 1
    timeline["total"] = round(t, 3)
    timeline["lines"] = n

    # normalise, clip, write
    peak = max(1, max(abs(x) for x in mix))
    scale = min(1.0, 0.89 * 32767.0 / peak)
    pcm = struct.pack("<%dh" % len(mix),
                      *[max(-32768, min(32767, int(x * scale))) for x in mix])
    out = os.path.join(BUILD, "narration.wav")
    with wave.open(out, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(pcm)

    with open(os.path.join(BUILD, "timeline.json"), "w") as fh:
        json.dump(timeline, fh, ensure_ascii=False, indent=1)

    print("\ntotal %.2f s = %d:%05.2f   lines=%d   voice=%s" %
          (t, int(t // 60), t % 60, n, script.VOICE))
    return timeline


if __name__ == "__main__":
    build(force="--force" in sys.argv)
