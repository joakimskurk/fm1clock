#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Checks on what the clock does, from its sound (WAV) and its screen (PNG / BMP), on the host or in fm1-emu.

  check_clock.py hits LOG FROM TO N [T0]   N blows of the hammer between FROM and TO s in the host's log (its "HIT"
                                           lines), the first at T0 +- 0.01 s, 1.192 +- 0.05 s apart
  check_clock.py onset WAV FROM TO T [MS] the loudest jump of the sound between FROM and TO s is at T +- 0.03 s
                                           (the first blow of a train: fm1-emu; MS: the run's length, whose sound
                                           starts after the power-on: the times are the power-on's)
  check_clock.py ticks WAV FROM TO         a tick every 0.5 s (+- 3 ms), left and right in turn, nothing else but
                                           the tocks' second clicks
  check_clock.py moved A B                 the pendulum's window differs between two screens (it swings)
  check_clock.py hands IMG HH MM           the hands point at HH:MM (the darkest ray from the hub, each)
  check_clock.py isr REPORT LO HI          fm1-emu's report: the share of the chip in interrupts within LO..HI %
  check_clock.py state REPORT MAX          fm1-emu's --dump of eng_st: the carriers, the worst block under MAX % of a
                                           block's time
  check_clock.py peak WAV MAX              no sample over MAX of full scale
"""
import re
import sys
from pathlib import Path

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))
from features import read_wav  # noqa: E402


def art_consts():
    h = (ROOT / "firmware" / "gen" / "clk_art.h").read_text()
    return {k: int(v) for k, v in re.findall(r"#define (\w+) (-?\d+)", h)}


def onset(x, fs, t0, t1):
    """the biggest jump of energy between t0 and t1: 5 ms against the 20 ms before (a blow is far louder than a tick)"""
    h2 = x.mean(axis=1) ** 2
    e5 = np.convolve(h2, np.ones(220) / 220, "valid")
    e20 = np.convolve(h2, np.ones(882) / 882, "valid")
    i0, i1 = int(t0 * fs), int(t1 * fs)
    d = e5[i0:i1] - e20[i0 - 882:i1 - 882]
    j = int(np.argmax(d))
    return (i0 + j) / fs, float(e5[i0 + j] / (e20[i0 + j - 882] + 1e-10))


def tick_events(x, fs):
    """the ticks: energy above 3 kHz (FFT filter), its peaks; and which side is louder"""
    out = []
    for ch in (0, 1):
        X = np.fft.rfft(x[:, ch])
        f = np.fft.rfftfreq(len(x), 1 / fs)
        X[f < 3000] = 0
        out.append(np.fft.irfft(X, len(x)))
    hp = (out[0] ** 2 + out[1] ** 2) / 2
    env = np.sqrt(np.convolve(hp, np.ones(44) / 44, "same"))
    ev, i = [], 0
    thr = np.percentile(env, 99.5) * 0.25
    while i < len(env):
        if env[i] > thr:
            seg = slice(i, i + int(0.015 * fs))
            l, r = np.sum(out[0][seg] ** 2), np.sum(out[1][seg] ** 2)
            ev.append((i / fs, 10 * np.log10((l + 1e-12) / (r + 1e-12))))
            i += int(0.08 * fs)
        else:
            i += 1
    return ev


def main():
    what = sys.argv[1]
    if what == "hits":
        log = Path(sys.argv[2]).read_text()
        t0, t1, n = float(sys.argv[3]), float(sys.argv[4]), int(sys.argv[5])
        hits = [float(v) for v in re.findall(r"HIT at ([\d.]+) s", log)]
        hits = [t for t in hits if t0 <= t <= t1]
        print(f"blows between {t0} and {t1} s: {[round(t, 3) for t in hits]} (want {n})")
        ok = len(hits) == n
        if ok and n and len(sys.argv) > 6:
            want = float(sys.argv[6])
            ok = abs(hits[0] - want) < 0.01
            print(f"  the first at {hits[0]:.3f} s, want {want:.3f}")
        if ok and n > 1:
            gaps = np.diff(hits)
            ok = bool(np.all(np.abs(gaps - 1.192) < 0.05))
            print(f"  apart {np.round(gaps, 3).tolist()} (want 1.192 +- 0.05)")
        return 0 if ok else 1
    if what == "onset":
        fs, x = read_wav(sys.argv[2])
        off = float(sys.argv[6]) / 1000 - len(x) / fs if len(sys.argv) > 6 else 0.0   # (fm1-emu: its sound starts late)
        t, r = onset(x, fs, float(sys.argv[3]) - off, float(sys.argv[4]) - off)
        want = float(sys.argv[5])
        print(f"the loudest onset between {sys.argv[3]} and {sys.argv[4]} s: {t + off:.3f} s ({10 * np.log10(r):.0f} dB up), "
              f"want {want}" + (f" (the sound starts {1000 * off:.0f} ms after the power-on)" if off else ""))
        return 0 if abs(t + off - want) < 0.03 and r > 30 else 1
    if what == "ticks":
        fs, x = read_wav(sys.argv[2])
        t0, t1 = float(sys.argv[3]), float(sys.argv[4])
        ev = [(t, lr) for t, lr in tick_events(x, fs) if t0 <= t <= t1]
        # the ticks' place in the half second: where most of them are (fm1-emu's sound starts a little after the
        # power-on, the host's with it); the tock's second click is 115 ms after it, the rest is not a tick
        ph = np.array([t % 0.5 for t, _ in ev])
        circ = lambda a, b: np.abs(((a - b + 0.25) % 0.5) - 0.25)
        cand = [p0 for p0 in ph]
        phase = max(cand, key=lambda p0: np.sum(circ(ph, p0) < 0.004)) if len(ph) else 0.0
        main_ = [e for e, q in zip(ev, ph) if circ(q, phase) < 0.004]
        after = sum(1 for q in ph if circ(q, phase + 0.115) < 0.01)
        others = len(ev) - len(main_) - after
        ts = np.array([e[0] for e in main_])
        ok = len(ts) >= int((t1 - t0) / 0.5) - 1
        err = circ(ts % 0.5, phase) if len(ts) else np.array([1.0])
        gaps = np.diff(ts) if len(ts) > 1 else np.array([0.5])
        sides = [e[1] > 0 for e in main_]
        alt = all(a != b for a, b in zip(sides, sides[1:]))
        print(f"ticks {t0}..{t1} s: {len(ts)} on the half seconds (at +{1000 * phase:.1f} ms; worst {1000 * err.max():.1f} ms "
              f"off), apart {gaps.min():.4f} .. {gaps.max():.4f} s, {after} second clicks of the tocks, {others} else; "
              f"left / right in turn: {alt}")
        return 0 if ok and err.max() < 0.003 and np.all(np.abs(gaps - 0.5) < 0.004) and alt and others == 0 else 1
    if what == "moved":
        c = art_consts()
        a = np.asarray(Image.open(sys.argv[2]).convert("RGB")).astype(int)
        b = np.asarray(Image.open(sys.argv[3]).convert("RGB")).astype(int)
        s = a.shape[0] // 240
        box = (slice(c["WIN_Y"] * s, (c["WIN_Y"] + c["WIN_H"]) * s), slice(c["WIN_X"] * s, (c["WIN_X"] + c["WIN_W"]) * s))
        d = np.abs(a[box] - b[box]).sum(axis=2) > 30
        print(f"the window: {d.sum() // (s * s)} pixels changed")
        return 0 if d.sum() // (s * s) > 40 else 1
    if what == "hands":
        c = art_consts()
        im = np.asarray(Image.open(sys.argv[2]).convert("RGB")).astype(float)
        s = im.shape[0] / 240
        hh, mm = int(sys.argv[3]), int(sys.argv[4])
        hx, hy = c["HUB_X256"] / 256, c["HUB_Y256"] / 256
        lum = im.mean(axis=2)

        def ray(deg, r0, r1):
            v = []
            for r in np.linspace(r0, r1, 24):
                x, y = hx + r * np.sin(np.radians(deg)), hy - r * np.cos(np.radians(deg))
                v.append(lum[int(y * s), int(x * s)])
            return np.mean(v)
        angles = np.arange(0, 360, 3)
        m_d = angles[int(np.argmin([ray(a, 25, 29) for a in angles]))]   # only the minute hand reaches out there
        h_d = angles[int(np.argmin([ray(a, 9, 16) - (0 if abs(((a - m_d + 180) % 360) - 180) > 12 else -999)
                                    for a in angles]))]
        want_m, want_h = mm * 6, (hh % 12) * 30 + mm * 0.5
        dm, dh = abs(((m_d - want_m + 180) % 360) - 180), abs(((h_d - want_h + 180) % 360) - 180)
        print(f"hands: minute at {m_d} deg (want {want_m}), hour at {h_d} deg (want {want_h:.0f})")
        return 0 if dm <= 6 and dh <= 9 else 1
    if what == "isr":
        txt = Path(sys.argv[2]).read_text()
        m = re.search(r"cpu0: ([\d.]+)% in an ISR, ([\d.]+)% nested", txt)
        lo, hi = float(sys.argv[3]), float(sys.argv[4])
        if not m:
            print(txt[-2000:])
            print("no ISR report")
            return 1
        tot = float(m.group(1)) + float(m.group(2))
        print(f"fm1-emu: the interrupts take {tot:.1f} % of the chip (want {lo}..{hi})")
        return 0 if lo <= tot <= hi else 1
    if what == "state":
        txt = Path(sys.argv[2]).read_text()
        m = re.search(r"^\s*0x[0-9a-f]+: ([0-9a-f]{8}) ([0-9a-f]{8}) ([0-9a-f]{8}) ([0-9a-f]{8}) ([0-9a-f]{8})", txt, re.M)
        if not m:
            print("no dump of eng_st (build/fm1clock.syms?)")
            return 1
        ng, load, peak, worst, blocks = (int(v, 16) for v in m.groups())
        block = 139320
        ops = ng + 32 + 128
        print(f"fm1-emu: the governor renders {ng} of the gong's 742 carriers ({ops} FM operators in all, with the "
              f"modulators and the ticks'); the engine takes {100 * load / block:.1f} % of a block, "
              f"{100 * worst / block:.1f} % at its worst, over {blocks} blocks")
        import os
        if os.environ.get("GITHUB_ACTIONS"):
            print(f"::notice title=fm1-emu::{ops} FM operators, the engine {100 * load / block:.0f} % of the chip "
                  f"({100 * worst / block:.0f} % at worst)")
        return 0 if ng > 32 and blocks > 500 and 100 * worst / block <= float(sys.argv[3]) else 1
    if what == "peak":
        fs, x = read_wav(sys.argv[2])
        p = float(np.abs(x).max())
        print(f"peak {p:.3f} of full scale (max {sys.argv[3]})")
        return 0 if p <= float(sys.argv[3]) else 1
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main())
