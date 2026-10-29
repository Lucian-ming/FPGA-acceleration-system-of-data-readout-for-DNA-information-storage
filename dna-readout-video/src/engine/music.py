# -*- coding: utf-8 -*-
"""Procedurally synthesised instrumental bed (no external audio assets).

Design notes
------------
* 63 BPM, 4-chord loop of 8 s each — slow enough that it never competes with
  the narration, long enough that the loop point is not audible.
* Layers: warm pad (chorus-modulated additive sines), sub bass, sparse mallet
  arpeggio, high shimmer. Nothing percussive: a demo reel wants a floor, not a
  beat.
* Stereo reverb is an overlap-add convolution with a decorrelated noise impulse
  response, so no libs beyond numpy are needed.
* The bed is ducked by the narration envelope, then written to build/music.wav
  and mixed into build/mix.wav.

    python3 src/engine/music.py            # build music.wav + mix.wav
"""
import os
import sys
import wave

import numpy as np

SR = 48000
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
BUILD = os.path.join(ROOT, "build")


def midi_f(m):
    return 440.0 * (2.0 ** ((m - 69) / 12.0))


# (bass note, pad voicing) — D minor, smooth voice leading
CHORDS = [
    (38, [50, 53, 57, 64]),   # Dm(add9)   D3 F3 A3 E4
    (34, [46, 50, 53, 60]),   # Bbmaj9     Bb2 D3 F3 C4
    (41, [48, 53, 57, 64]),   # Fmaj7      C3 F3 A3 E4
    (36, [43, 48, 52, 59]),   # C(add9)    G2 C3 E3 B3
]
CHORD_LEN = 8.0
ARP_NOTES = [62, 65, 67, 69, 72, 76]       # D F G A C E — D minor pentatonic+2
# 8th-note grid, 0 = rest. Four bars of variety, then it repeats.
ARP_PATTERN = [0, 2, 1, 0, 3, 0, 1, 2, 0, 1, 3, 0, 2, 0, 1, 0]


def pad_track(n, rng, amp=0.5):
    """Slow chorused pad; chords overlap by a 2.4 s release."""
    out = np.zeros(n, dtype=np.float64)
    i = 0
    seg = int(CHORD_LEN * SR)
    while i * seg < n:
        bass, voicing = CHORDS[i % len(CHORDS)]
        a = i * seg
        b = min(n, a + seg + int(2.4 * SR))
        ln = b - a
        tt = np.arange(ln) / SR
        # envelope: 1.4 s cosine attack, cosine release over the last 2.4 s
        env = np.ones(ln)
        at = min(ln, int(1.4 * SR))
        env[:at] = 0.5 - 0.5 * np.cos(np.pi * np.arange(at) / at)
        rl = min(ln, int(2.4 * SR))
        env[-rl:] *= 0.5 + 0.5 * np.cos(np.pi * np.arange(rl) / rl)
        # slow swell across the chord
        env *= 0.86 + 0.14 * np.sin(np.pi * tt / CHORD_LEN)

        for note in voicing:
            f = midi_f(note)
            # three detuned partials per note: chorus without a chorus unit
            for det, ph in ((1.0, 0.0), (1.0016, 1.7), (0.9984, 3.9)):
                lfo = 0.55 * np.sin(2 * np.pi * 0.09 * tt + ph)
                w = np.sin(2 * np.pi * f * det * tt + lfo)
                w += 0.30 * np.sin(2 * np.pi * f * 2 * det * tt + 0.6 * lfo)
                w += 0.10 * np.sin(2 * np.pi * f * 3 * det * tt + ph)
                out[a:b] += amp * env * w / (3.0 * len(voicing))
        i += 1
    return out


def bass_track(n, amp=0.34):
    out = np.zeros(n, dtype=np.float64)
    seg = int(CHORD_LEN * SR)
    i = 0
    while i * seg < n:
        bass, _ = CHORDS[i % len(CHORDS)]
        a = i * seg
        b = min(n, a + seg + int(0.9 * SR))
        ln = b - a
        tt = np.arange(ln) / SR
        f = midi_f(bass)
        env = np.ones(ln) * (0.5 + 0.5 * np.cos(np.pi * tt / CHORD_LEN)) ** 0.5
        at = min(ln, int(0.35 * SR))
        env[:at] *= np.arange(at) / at
        w = np.sin(2 * np.pi * f * tt) + 0.42 * np.sin(2 * np.pi * f * 2 * tt)
        out[a:b] += amp * env * np.tanh(1.6 * w) / 1.6
        i += 1
    return out


def arp_track(n, rng):
    """Sparse mallet arpeggio; one note every 8th note where the pattern says so."""
    out_l = np.zeros(n, dtype=np.float64)
    out_r = np.zeros(n, dtype=np.float64)
    step = 60.0 / 63.0 / 2.0                    # 8th note at 63 BPM
    k = 0
    t = 0.0
    while t < n / SR - 0.2:
        idx = ARP_PATTERN[k % len(ARP_PATTERN)]
        if idx:
            note = ARP_NOTES[(idx + (k // len(ARP_PATTERN)) % 2) % len(ARP_NOTES)]
            f = midi_f(note)
            ln = int(min(1.6 * SR, n - int(t * SR)))
            if ln > 64:
                tt = np.arange(ln) / SR
                env = np.exp(-tt / 0.42) * (1.0 - np.exp(-tt / 0.004))
                w = np.sin(2 * np.pi * f * tt) + 0.22 * np.sin(2 * np.pi * f * 2.01 * tt)
                burst = 0.10 * env * w * (0.6 + 0.4 * np.exp(-tt / 0.8))
                a = int(t * SR)
                pan = 0.5 + 0.5 * np.sin(k * 0.7)     # slow left/right drift
                out_l[a:a + ln] += burst * (1.0 - 0.45 * pan)
                out_r[a:a + ln] += burst * (0.55 + 0.45 * pan)
        k += 1
        t += step
    return out_l, out_r


def shimmer_track(n, amp=0.035):
    """Two very high sines with a 0.1 Hz tremolo — reads as 'air', not melody."""
    tt = np.arange(n) / SR
    trem = 0.5 + 0.5 * np.sin(2 * np.pi * 0.055 * tt)
    w = (np.sin(2 * np.pi * midi_f(84) * tt) +
         0.6 * np.sin(2 * np.pi * midi_f(88) * tt + 1.1))
    return amp * trem * w


def reverb(x, rng, tau=0.62, length=1.4, wet=0.34, dark=0.30):
    """Overlap-add convolution with a decaying, low-passed noise IR."""
    ln = int(length * SR)
    tt = np.arange(ln) / SR
    ir = rng.standard_normal(ln) * np.exp(-tt / tau)
    # one-pole low-pass so the tail is dark instead of hissy
    a = np.exp(-2 * np.pi * 900.0 / SR)
    y = np.empty(ln)
    acc = 0.0
    for i in range(ln):          # 67k taps: fine as a plain loop
        acc = a * acc + (1 - a) * ir[i]
        y[i] = acc
    ir = y / (np.sqrt(np.sum(y ** 2)) + 1e-9)

    nfft = 1 << 18
    block = nfft - ln + 1
    irf = np.fft.rfft(ir, nfft)
    tail = ln - 1
    out = np.zeros(len(x) + tail)
    for s in range(0, len(x), block):
        chunk = x[s:s + block]
        spec = np.fft.irfft(np.fft.rfft(chunk, nfft) * irf, nfft)
        m = min(len(spec), len(out) - s)
        out[s:s + m] += spec[:m]
    out = out[:len(x)]
    return (1.0 - wet) * x + wet * out * 2.2


def envelope_of(narr, hop=0.05):
    """Narration loudness envelope, resampled to every sample — for ducking."""
    h = int(hop * SR)
    k = len(narr) // h
    blk = np.abs(narr[:k * h]).reshape(k, h).max(axis=1)
    sm = np.convolve(blk, np.hanning(9) / np.hanning(9).sum(), mode="same")
    lvl = np.clip(sm / (np.percentile(sm, 92) + 1e-9), 0.0, 1.0)
    rep = np.repeat(lvl, h)
    if len(rep) < len(narr):
        rep = np.concatenate([rep, np.zeros(len(narr) - len(rep))])
    return rep[:len(narr)]


def read_wav(path):
    with wave.open(path) as w:
        assert w.getnchannels() == 1
        raw = w.readframes(w.getnframes())
    return np.frombuffer(raw, dtype="<i2").astype(np.float64) / 32768.0


def write_wav(path, stereo):
    pcm = np.clip(stereo, -1.0, 1.0)
    inter = np.empty(pcm.shape[0] * 2, dtype="<i2")
    inter[0::2] = (pcm[:, 0] * 32767).astype("<i2")
    inter[1::2] = (pcm[:, 1] * 32767).astype("<i2")
    with wave.open(path, "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(inter.tobytes())


def build():
    import json
    tl_path = os.path.join(BUILD, "timeline.json")
    with open(tl_path) as fh:
        total = json.load(fh)["total"]
    n = int(round(total * SR))
    rng = np.random.default_rng(20261029)

    print("  合成铺底（%.1f s）…" % total, flush=True)
    pad = pad_track(n, rng)
    bass = bass_track(n)
    al, ar = arp_track(n, rng)
    sh = shimmer_track(n)

    print("  混响…", flush=True)
    left = reverb(pad + 0.55 * bass + al + sh, rng, wet=0.30)
    right = reverb(pad + 0.55 * bass + ar + sh, np.random.default_rng(77),
                   wet=0.30)

    # 头部淡入 / 尾部淡出，避免和开场黑场对不齐
    fi = int(3.0 * SR)
    fo = int(4.0 * SR)
    ramp = 0.5 - 0.5 * np.cos(np.pi * np.arange(fi) / fi)
    left[:fi] *= ramp
    right[:fi] *= ramp
    ramp = 0.5 + 0.5 * np.cos(np.pi * np.arange(fo) / fo)
    left[-fo:] *= ramp
    right[-fo:] *= ramp

    bed = np.stack([left, right], axis=1)
    # 归一化到很低的电平：这是铺底，不是主声道
    peak = float(np.max(np.abs(bed))) + 1e-9
    bed *= 0.16 / peak
    write_wav(os.path.join(BUILD, "music.wav"), bed)
    print("  -> build/music.wav", flush=True)

    narr_path = os.path.join(BUILD, "narration.wav")
    if os.path.exists(narr_path):
        narr = read_wav(narr_path)
        env = envelope_of(narr)
        duck = 1.0 - 0.45 * env            # 说话时铺底退到 55%
        # 300 ms 平滑，避免抽气感
        h = int(0.30 * SR)
        kern = np.hanning(h)
        kern /= kern.sum()
        duck = np.convolve(duck, kern, mode="same")
        m = min(len(bed), len(narr))
        mix = np.stack([narr[:m] + bed[:m, 0] * duck[:m],
                        narr[:m] + bed[:m, 1] * duck[:m]], axis=1)
        pk = float(np.max(np.abs(mix))) + 1e-9
        if pk > 0.94:
            mix *= 0.94 / pk
        write_wav(os.path.join(BUILD, "mix.wav"), mix)
        print("  -> build/mix.wav (%.1f s)" % (m / SR), flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(build())
