#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""The engine against the reference: the band energies (third octaves, 100 Hz .. 16 kHz) over time after a hit and
after a tick, as tools/analyze_ref.py measured them in the recording (tests/ref/features.json). The engine's output
is the recording's level times GAIN (tools/gen_tables.py); that is taken off. Only bands where the recording stands
6 dB over its noise count.

  parity.py gong STRIKE.wav [MAX_DB]      a strike (clk_render strike): every window's rms error under MAX_DB (2.0)
  parity.py tick|tock TICKS.wav N [MAX]   N ticks 0.2 s apart (clk_render tick): their mean, each window (3.5)
"""
import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))
from features import BANDS, band_energies, read_wav  # noqa: E402
from gen_tables import GAIN  # noqa: E402

F = json.loads((ROOT / "tests" / "ref" / "features.json").read_text())
G = 20 * np.log10(GAIN)
HIT = 2208 / 44100                                       # (clk_render: 2205 frames, on the engine's 16-frame step)


def report(name, synth, ref, noise, wins, limit):
    ok = True
    worst = 0.0
    print(f"{name}: synth - reference per window (rms over the bands above the noise), limit {limit} dB")
    for w, (a, b) in enumerate(wins):
        sel = ref[w] > noise + 6
        if not sel.any():
            continue
        d = synth[w][sel] - ref[w][sel]
        rms = float(np.sqrt(np.mean(d ** 2)))
        worst = max(worst, rms)
        flag = "" if rms <= limit else "   <-- over"
        ok &= rms <= limit
        print(f"  {1000 * a:6.0f} .. {1000 * b:5.0f} ms  {rms:5.2f} dB   (mean {np.mean(d):+5.2f}, {sel.sum()} bands){flag}")
    print(f"{name}: {'pass' if ok else 'FAIL'} (worst window {worst:.2f} dB)")
    return ok


def main():
    what = sys.argv[1]
    fs, x = read_wav(sys.argv[2])
    noise = np.array(F["noise"])
    if what == "gong":
        limit = float(sys.argv[3]) if len(sys.argv) > 3 else 2.0
        m = x.mean(axis=1)
        synth = band_energies(m, fs, HIT, F["gong_windows"], F["gong_gates"]) - G
        ok = report("gong", synth, np.array(F["gong"]), noise, F["gong_windows"], limit)
    else:
        n = int(sys.argv[3])
        limit = float(sys.argv[4]) if len(sys.argv) > 4 else 3.5
        ch = x[:, 0] if what == "tick" else x[:, 1]         # the near channel (the far one is 4.6 dB down)
        P = 0
        for k in range(n):
            t0 = (448 + k * 8820) / fs
            P = P + 10 ** (band_energies(ch, fs, t0, F["tick_windows"]) / 10)
        synth = 10 * np.log10(P / n) - G
        ref = np.array(F[what])
        centers = np.sqrt(np.array(BANDS[:-1]) * np.array(BANDS[1:]))
        ref = np.where(centers[None, :] < 300, -200, ref)       # (below 300 Hz: the room's hum, not the tick)
        ok = report(what, synth, ref, noise, F["tick_windows"][:4], limit)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
