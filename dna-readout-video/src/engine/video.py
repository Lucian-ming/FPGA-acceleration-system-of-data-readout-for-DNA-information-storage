# -*- coding: utf-8 -*-
"""ffmpeg plumbing: raw BGRA frames in, H.264 out; concat; audio mux; subtitles."""

import json
import os
import subprocess
import sys

FFMPEG = ("/home/lucian/venvs/vscode-py38/lib/python3.8/"
          "site-packages/imageio_ffmpeg/binaries/ffmpeg-linux64-v4.2.2")
FFPROBE = FFMPEG  # ffmpeg is enough for the duration queries used here


class Encoder:
    """Pipe BGRA frames (W*H*4 bytes each) into a silent H.264 MP4."""

    def __init__(self, path, w, h, fps=30, crf=18, preset="medium"):
        self.path = path
        self.w, self.h, self.fps = w, h, fps
        self._size = w * h * 4
        self._n = 0
        os.makedirs(os.path.dirname(path), exist_ok=True)
        cmd = [FFMPEG, "-y", "-v", "error",
               "-f", "rawvideo", "-pix_fmt", "bgra", "-s", "%dx%d" % (w, h),
               "-r", str(fps), "-i", "-",
               "-c:v", "libx264", "-preset", preset, "-crf", str(crf),
               "-pix_fmt", "yuv420p", "-g", str(fps * 2),
               "-movflags", "+faststart", path]
        self._p = subprocess.Popen(cmd, stdin=subprocess.PIPE,
                                   stdout=subprocess.DEVNULL,
                                   stderr=subprocess.PIPE)

    def write(self, buf):
        if len(buf) != self._size:
            raise RuntimeError("frame size mismatch: %d != %d"
                               % (len(buf), self._size))
        self._p.stdin.write(buf)
        self._n += 1

    def close(self):
        try:
            self._p.stdin.close()
        except Exception:
            pass
        err = self._p.stderr.read().decode("utf-8", "replace")
        rc = self._p.wait()
        if rc != 0:
            raise RuntimeError("ffmpeg failed (%s):\n%s" % (self.path, err[-2000:]))
        return self._n


def run(args):
    p = subprocess.run([FFMPEG, "-y", "-v", "error"] + args,
                       stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if p.returncode != 0:
        raise RuntimeError("ffmpeg %s\n%s" % (" ".join(args),
                                              p.stderr.decode("utf-8", "replace")[-2000:]))
    return p


def concat(parts, out):
    """Concat scene MP4s (identical codec settings) without re-encoding."""
    listing = out + ".txt"
    with open(listing, "w") as fh:
        for p in parts:
            fh.write("file '%s'\n" % os.path.abspath(p).replace("'", "'\\''"))
    run(["-f", "concat", "-safe", "0", "-i", listing, "-c", "copy", out])
    os.remove(listing)
    return out


def duration(path):
    p = subprocess.run([FFMPEG, "-i", path], stdout=subprocess.PIPE,
                       stderr=subprocess.PIPE)
    txt = p.stderr.decode("utf-8", "replace")
    for line in txt.splitlines():
        line = line.strip()
        if line.startswith("Duration:"):
            hms = line.split("Duration:")[1].split(",")[0].strip()
            h, m, s = hms.split(":")
            return int(h) * 3600 + int(m) * 60 + float(s)
    raise RuntimeError("no duration for %s" % path)


def mux(video, audio, out, subtitles=None, loudnorm=True):
    args = ["-i", video, "-i", audio]
    if subtitles:
        args += ["-i", subtitles, "-c:s", "mov_text",
                 "-metadata:s:s:0", "language=chi"]
    af = "loudnorm=I=-16:TP=-1.5:LRA=11" if loudnorm else "anull"
    args += ["-map", "0:v:0", "-map", "1:a:0"]
    if subtitles:
        args += ["-map", "2:s:0"]
    args += ["-c:v", "copy", "-c:a", "aac", "-b:a", "192k", "-ar", "48000",
             "-ac", "2", "-af", af, "-shortest", "-movflags", "+faststart", out]
    return run(args)


def burn(video, ass, out, crf=18):
    """Hard-subtitled variant: re-encodes video with libass."""
    esc = ass.replace("\\", "\\\\").replace(":", "\\:").replace("'", "\\'")
    return run(["-i", video, "-vf", "ass='%s'" % esc,
                "-c:v", "libx264", "-preset", "medium", "-crf", str(crf),
                "-pix_fmt", "yuv420p", "-c:a", "copy", "-movflags",
                "+faststart", out])


def grab(video, t, out_png, size=None):
    vf = ["-vf", "scale=%s" % size] if size else []
    return run(["-ss", "%.3f" % t, "-i", video] + vf + ["-frames:v", "1", out_png])


def load_timeline():
    here = os.path.dirname(os.path.abspath(__file__))
    root = os.path.dirname(os.path.dirname(here))
    with open(os.path.join(root, "build", "timeline.json")) as fh:
        return json.load(fh)


if __name__ == "__main__":
    print(json.dumps(load_timeline()["total"]))
