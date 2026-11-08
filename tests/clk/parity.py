#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""The engine against the reference: the band energies (third octaves, 100 Hz .. 16 kHz) over time after a hit and
after a tick, as tools/analyze_ref.py measured them in the recording (tests/ref/features.json). The engine's output
is the recording's level times GAIN (tools/gen_tables.py); that is taken off. Only bands where the recording stands
6 dB over its noise count.

  parity.py gong STRIKE.wav [MAX_DB]      a strike (clk_render strike): every window's rms error under MAX_DB (2.0)
  parity.py tick|tock TICKS.wav N [MAX]   N ticks 0.2 s apart (clk_render tick): their mean, each window (3.5)
The cuckoo clock's, against its own recording (tests/ref/cuckoo_features.json, tools/analyze_cuckoo.py; GAIN_B):
  parity.py ck_gong STRIKE.wav [MAX]      its wire gong, the 0.14 s before a pipe would sound (clk_render ck_strike)
  parity.py ck_call CALLS.wav N [MAX]     N calls (clk_render ck_call): the gong and both pipes, 0.5 s from the hit
                                          (the last 0.1 s before the next is shown, not held to it: there the
                                          recording's slow tail is under its pipes, longer than the analysis saw)
  parity.py ck_tick WAV N [MAX]           its ticks (clk_render ck_tick), as the wall clock's but to 130 ms: it rings on;
                                          and under 400 Hz its case's knock, its energy within 2 dB of the recording's
  parity.py ck_drone WAV                  the train's drone while it runs (clk_render ck_run): its energy 40-450 Hz
                                          within 2 dB of the recording's (running less still)
  parity.py ck_pre|ck_post WAV N [MAX]    the train's clicks: their peak above 3 kHz within MAX dB (1.5) of the
                                          recording's (under them there the gong and the pipes ring)
"""
import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))
from features import BANDS, band_energies, read_wav  # noqa: E402
from gen_tables import GAIN, GAIN_B  # noqa: E402

F = json.loads((ROOT / "tests" / "ref" / "features.json").read_text())
C = json.loads((ROOT / "tests" / "ref" / "cuckoo_features.json").read_text())
G = 20 * np.log10(GAIN)
G_B = 20 * np.log10(GAIN_B)
HIT = 2208 / 44100                                       # (clk_render: 2205 frames, on the engine's 16-frame step)
CALL_FRAMES = 29332                                      # (clk_tables.h: CK_CALL_FRAMES)


def hp(x, fs, fc=400.0):
    """the analysis' high pass (a 4th-order Butterworth, forwards and back: its magnitude squared), by FFT"""
    n = len(x)
    f = np.fft.rfftfreq(n, 1 / fs)
    return np.fft.irfft(np.fft.rfft(x) / (1 + (fc / np.maximum(f, 1e-9)) ** 8), n)


def onset(x, fs, t, thr=0.3, span=0.01):
    """as tools/analyze_cuckoo.py finds them: the first sample over thr of the local peak above 400 Hz"""
    t0 = max(t - span, 0.003)
    seg = hp(x[int(t0 * fs):int((t + span) * fs)], fs)
    return t0 + int(np.argmax(np.abs(seg) > thr * np.abs(seg).max())) / fs


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
    if what.startswith("ck_"):
        return cuckoo(what, fs, x)
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


def cuckoo(what, fs, x):
    noise = np.array(C["noise"])
    m = x.mean(axis=1)
    if what == "ck_gong":
        limit = float(sys.argv[3]) if len(sys.argv) > 3 else 2.0
        synth = band_energies(m, fs, onset(m, fs, 2205 / fs), C["gong_windows"]) - G_B
        return 0 if report("cuckoo gong", synth, np.array(C["gong"]), noise, C["gong_windows"], limit) else 1
    if what == "ck_drone":                      # (clk_render ck_run: the train runs from 0.1 s to 1.1 s)
        sel = (np.fft.rfftfreq(len(m), 1 / fs) >= 40) & (np.fft.rfftfreq(len(m), 1 / fs) <= 450)
        b = np.fft.irfft(np.fft.rfft(m) * sel, len(m))
        e = 10 * np.log10(np.mean(b[int(0.4 * fs):int(1.0 * fs)] ** 2)) - G_B
        d = e - C["drone_db"]
        print(f"cuckoo drone (40-450 Hz): {e:.1f} dB, the recording's {C['drone_db']:.1f}: {d:+.2f} dB (limit 2)")
        return 0 if abs(d) <= 2 else 1
    n = int(sys.argv[3])
    limit = float(sys.argv[4]) if len(sys.argv) > 4 else 3.0
    if what == "ck_call":
        ons = [onset(m, fs, (2205 + k * CALL_FRAMES) / fs) for k in range(n)]
        E = [10 ** (band_energies(m, fs, t, C["call_windows"]) / 10) for t in ons]
        synth = 10 * np.log10(np.mean(E, axis=0)) - G_B
        ok = report("cuckoo call", synth[:7], np.array(C["call"])[:7], noise, C["call_windows"][:7], limit)
        report("  (and before the next call)", synth[7:], np.array(C["call"])[7:], noise, C["call_windows"][7:], 99)
        return 0 if ok else 1
    ch = x[:, 0]                                           # (the tick from the left; the train's from the middle)
    centers = np.sqrt(np.array(BANDS[:-1]) * np.array(BANDS[1:]))
    if what in ("ck_pre", "ck_post"):
        limit = float(sys.argv[4]) if len(sys.argv) > 4 else 1.5
        ref = json.loads((ROOT / "tools" / "ref_cuckoo.json").read_text())["ticks"][what[3:]]["peak_hf"]
        h3 = hp(ch, fs, 3000.0)
        ons = [onset(ch, fs, (441 + k * 8820) / fs) for k in range(n)]
        pk = float(np.mean([np.abs(h3[int(o * fs):int((o + 0.015) * fs)]).max() for o in ons])) / GAIN_B
        d = 20 * np.log10(pk / ref)
        print(f"cuckoo {what[3:]}: its peak above 3 kHz {20 * np.log10(pk):.1f} dB FS, the recording's "
              f"{20 * np.log10(ref):.1f}: {d:+.2f} dB (limit {limit})")
        return 0 if abs(d) <= limit else 1
    h = hp(ch, fs)
    ons = [onset(ch, fs, (441 + k * 8820) / fs) for k in range(n)]
    E = [10 ** (band_energies(h, fs, t, C["tick_windows"]) / 10) for t in ons]
    synth = 10 * np.log10(np.mean(E, axis=0)) - G_B
    name = what[3:]
    ref = np.where(centers[None, :] < 400, -200, np.array(C[name]))   # (the analysis is high-passed at 400 Hz)
    if name == "tick":                          # under 400 Hz the case's knock: its energy over 80 ms, as the ticks'
        lo_ = (np.fft.rfftfreq(len(ch), 1 / fs) >= 80) & (np.fft.rfftfreq(len(ch), 1 / fs) <= 450)   # average had it
        kb = np.fft.irfft(np.fft.rfft(ch) * lo_, len(ch))
        e = 10 * np.log10(np.mean([np.mean(kb[int(o * fs):int((o + 0.08) * fs)] ** 2) for o in ons])) - G_B
        d = e - C["knock_db"]
        print(f"cuckoo knock (80-450 Hz, 80 ms): {e:.1f} dB, the recording's {C['knock_db']:.1f}: {d:+.2f} dB (limit 2)")
        if abs(d) > 2:
            report(f"cuckoo {name}", synth, ref, np.array(C["tick_noise"]), C["tick_windows"], limit)
            return 1
    return 0 if report(f"cuckoo {name}", synth, ref, np.array(C["tick_noise"]), C["tick_windows"], limit) else 1


if __name__ == "__main__":
    sys.exit(main())
