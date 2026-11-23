#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Hamster Piano's sound against the original's: the web page renders each case of tests/ham/cases.json to a WAV
itself (tools/ham_ref.js, its own export), and what is kept of those is their energy in third-octave bands over time
(tests/ref/ham_features.json). The firmware's engine plays the same cases on the host (tests/ham/ham_render.c).

  parity.py ref DIR                  DIR/<case>.wav (tools/ham_ref.js) -> tests/ref/ham_features.json
  parity.py casefile NAME OUT.txt    the case as ham_render reads it
  parity.py level NAME OUT.wav TOL    the hamster voice (this firmware's own): as loud as the page's, within TOL dB
  parity.py cmp NAME OUT.wav MEAN MAX [-v]    the engine's WAV against the reference: the mean and the largest
                                     difference (dB) over the windows and bands that sound, and the level over all
"""
import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))
from features import read_wav  # noqa: E402

CASES = ROOT / "tests" / "ham" / "cases.json"
REF = ROOT / "tests" / "ref" / "ham_features.json"
BANDS = [31.25 * 2 ** (k / 3) for k in range(0, 29)]       # 31 Hz .. 20 kHz
WIN = 0.05                                                  # seconds a window
GAIN_DB = 6.02                                              # the firmware plays twice the page's level
LOUD = -45.0                                                # (dB) the largest difference is looked for above this
FLOOR = -62.0                                               # (dB) quieter than this in both: not compared


def features(x, fs):
    n = int(WIN * fs)
    rows = []
    f = np.fft.rfftfreq(n, 1 / fs)
    w = np.hanning(n)
    for i in range(0, len(x) - n + 1, n // 2):
        S = np.abs(np.fft.rfft(x[i:i + n] * w)) ** 2 / (np.sum(w ** 2) * n / 2)
        rows.append([10 * np.log10(S[(f >= lo) & (f < hi)].sum() + 1e-14) for lo, hi in zip(BANDS[:-1], BANDS[1:])])
    return np.array(rows)


def mono(path):
    fs, x = read_wav(path)
    assert fs == 44100, fs
    return x.mean(axis=1)


def casefile(name, out):
    c = json.loads(CASES.read_text())[name]
    L = [f"bpm {c['bpm']}", f"thall {int(bool(c.get('thall')))}", f"drums {int(bool(c.get('drums')))}"]
    for pi, pid in enumerate("ABCD"):
        for i, s in enumerate(c["patterns"][pid]):
            if s:
                L.append(f"step {pi} {i} {s['key']} {s['oct']} {int(s['glide'])} {s['arpInterval'] if s['octArp'] else 0} "
                         f"{int(s['accent'])} {s['ratchet']}")
        if c.get("dp"):
            for di, d in enumerate(("kick", "snare", "hat", "clap")):
                L.append(f"drum {pi} {di} {sum(b << k for k, b in enumerate(c['dp'][pid][d]))}")
                L.append(f"dvoice {pi} {di} {c['dv'][pid][d]}")
    Path(out).write_text("\n".join(L) + "\n")


def main():
    cmd = sys.argv[1]
    if cmd == "ref":
        out = {}
        for name in json.loads(CASES.read_text()):
            x = mono(Path(sys.argv[2]) / f"{name}.wav")
            out[name] = {"n": len(x), "rms": float(np.sqrt((x ** 2).mean())), "peak": float(np.abs(x).max()),
                         "bands": np.round(features(x, 44100), 2).tolist()}
        REF.write_text(json.dumps(out, separators=(",", ":")) + "\n")
        print(f"{REF.relative_to(ROOT)}: {len(out)} cases")
        return 0
    if cmd == "casefile":
        casefile(sys.argv[2], sys.argv[3])
        return 0
    if cmd == "cmp":
        name, tol_mean, tol_max = sys.argv[2], float(sys.argv[4]), float(sys.argv[5])
        ref = json.loads(REF.read_text())[name]
        x = mono(sys.argv[3])
        a, b = np.array(ref["bands"]), features(x, 44100) - GAIN_DB
        n = min(len(a), len(b))
        a, b = a[:n], b[:n]
        sel = (a > FLOOR) | (b > FLOOR)
        d = np.where(sel, np.maximum(b, FLOOR - 12) - np.maximum(a, FLOOR - 12), 0.0)
        # the largest difference: in octaves and tenths of a second (a partial a little off its pitch changes its
        # third of an octave, noise is never twice the same), where it is loud enough to hear one
        def wide(m):
            p = 10 ** (m / 10)
            p = p[:len(p) // 4 * 4].reshape(-1, 4, p.shape[1]).mean(axis=1)
            p = p[:, :p.shape[1] // 3 * 3].reshape(p.shape[0], -1, 3).sum(axis=2)
            return 10 * np.log10(p + 1e-14)
        wa, wb = wide(a), wide(b)
        loud = (wa > LOUD) | (wb > LOUD)
        wd = np.where(loud, wb - wa, 0.0)
        mean, worst = float(np.abs(d[sel]).mean()), float(np.abs(wd).max())
        lvl = 20 * np.log10(np.sqrt((x ** 2).mean()) / ref["rms"]) - GAIN_DB
        pk = float(np.abs(x).max())
        ok = mean <= tol_mean and worst <= tol_max and abs(lvl) <= 1.5 and pk < 0.98
        print(f"{name}: mean {mean:.2f} dB (<= {tol_mean}), worst {worst:.1f} dB (<= {tol_max}), level {lvl:+.2f} dB, "
              f"peak {pk:.2f}: {'ok' if ok else 'FAIL'}")
        if "-v" in sys.argv:
            w, k = np.unravel_index(np.abs(wd).argmax(), wd.shape)
            print(f"  worst at {w * WIN * 2:.3f} s, the octave from {BANDS[3 * k]:.0f} Hz: ref {wa[w, k]:.1f}, engine {wb[w, k]:.1f}")
            print("  per band (mean of engine - ref where it sounds):")
            for k in range(d.shape[1]):
                s = sel[:, k]
                if s.sum() > 2:
                    print(f"    {BANDS[k]:7.0f} Hz {d[s, k].mean():+6.2f} dB  (ref {a[s, k].mean():6.1f})")
        return 0 if ok else 1
    if cmd == "level":                          # the hamster voice: as loud as the page's, within TOL dB; no clip
        name, tol = sys.argv[2], float(sys.argv[4])
        ref = json.loads(REF.read_text())[name]
        x = mono(sys.argv[3])
        lvl = 20 * np.log10(np.sqrt((x ** 2).mean()) / ref["rms"]) - GAIN_DB
        pk = float(np.abs(x).max())
        ok = abs(lvl) <= tol and pk < 0.98
        print(f"{name} (hamster voice): level {lvl:+.2f} dB against the page's (<= {tol}), peak {pk:.2f}: {'ok' if ok else 'FAIL'}")
        return 0 if ok else 1
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main())
