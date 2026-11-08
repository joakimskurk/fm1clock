#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Checks on what the clock does, from its sound (WAV) and its screen (PNG / BMP), on the host or in fm1-emu.

  check_clock.py hits LOG FROM TO N [T0 [GAP]]   N blows of the hammer between FROM and TO s in the host's log (its
                                           "HIT" lines), the first at T0 +- 0.01 s ("-": anywhere), GAP (1.192) +- 0.05 s
                                           apart
  check_clock.py events LOG WHAT FROM TO N  N of the host's "WHAT at" lines (HIT, PIPE high, PIPE low, FLASH) there
  check_clock.py calls LOG FROM TO N       N cuckoo calls: a blow, the high pipe 0.11 s on (the train's first 0.22),
                                           the low 0.19 s after it
  check_clock.py even LOG                  every blow in the host's log as hard as the first (+- 7 %: the hammer varies)
  check_clock.py onset WAV FROM TO T [MS] the loudest jump of the sound between FROM and TO s is at T +- 0.03 s
                                           (the first blow of a train: fm1-emu; MS: the run's length, whose sound
                                           starts after the power-on: the times are the power-on's)
  check_clock.py ticks WAV FROM TO [BEAT [MS]]   a tick every BEAT (0.5) s (+- MS, 3 ms), left and right in turn,
                                           one click each, nothing between
  check_clock.py moved A B [cuckoo]        the pendulum's window (the cuckoo's: under its house) differs between two
                                           screens (it swings)
  check_clock.py differ A B X Y W H MIN    at least MIN pixels of that box differ between two screens
  check_clock.py same A B X Y W H MAX      at most MAX of them do
  check_clock.py hands IMG HH MM [cuckoo]  the hands point at HH:MM (the darkest ray from the hub, each)
  check_clock.py isr REPORT LO HI          fm1-emu's report: the share of the chip in interrupts within LO..HI %
  check_clock.py state REPORT MAX [CLOCK]  fm1-emu's --dump of eng_st: the carriers, the worst block under MAX % of
                                           a block's time (and the clock sounding: 0 the wall clock, 1 the cuckoo)
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


def art_consts(name="clk_art.h"):
    h = (ROOT / "firmware" / "gen" / name).read_text()
    return {k: int(v) for k, v in re.findall(r"#define (\w+) (-?\d+)", h)}


def table_consts():
    h = (ROOT / "firmware" / "gen" / "clk_tables.h").read_text()
    c = {k: int(v) for k, v in re.findall(r"#define (\w+) (\d+)u", h)}
    m = re.search(r"PIPE_NBODY\[2\] = \{\s*(\d+)u, (\d+)u", h)
    c["PIPE_OPS"] = 4 + int(m.group(1)) + int(m.group(2)) + c.get("DRONE_N", 0) + 8   # (and the drone's partials,
                                                                                       # the rattle's 8: clk_engine.h)
    return c


def log_events(log, what):
    return [float(v) for v in re.findall(re.escape(what) + r" at ([\d.]+) s", log)]


def onset(x, fs, t0, t1):
    """the biggest jump of energy between t0 and t1: 5 ms against the 20 ms before (a blow is far louder than a tick)"""
    h2 = x.mean(axis=1) ** 2
    e5 = np.convolve(h2, np.ones(220) / 220, "valid")
    e20 = np.convolve(h2, np.ones(882) / 882, "valid")
    i0, i1 = int(t0 * fs), int(t1 * fs)
    d = e5[i0:i1] - e20[i0 - 882:i1 - 882]
    j = int(np.argmax(d))
    return (i0 + j) / fs, float(e5[i0 + j] / (e20[i0 + j - 882] + 1e-10))


def tick_events(x, fs, t0=None, t1=None):
    """the ticks: energy above 3 kHz (FFT filter), its peaks; and which side is louder (the threshold from the
    stretch t0..t1 alone, if given: a louder sound elsewhere, the cuckoo's door, would raise it)"""
    out = []
    for ch in (0, 1):
        X = np.fft.rfft(x[:, ch])
        f = np.fft.rfftfreq(len(x), 1 / fs)
        X[f < 3000] = 0
        out.append(np.fft.irfft(X, len(x)))
    hp = (out[0] ** 2 + out[1] ** 2) / 2
    env = np.sqrt(np.convolve(hp, np.ones(44) / 44, "same"))
    ev, i = [], 0
    part = env[int(t0 * fs):int(t1 * fs)] if t0 is not None else env
    thr = np.percentile(part, 99.5) * 0.12                   # (low enough for a click 9 dB under a tick)
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
        hits = [t for t in log_events(log, "HIT") if t0 <= t <= t1]
        gap = float(sys.argv[7]) if len(sys.argv) > 7 else 1.192
        print(f"blows between {t0} and {t1} s: {[round(t, 3) for t in hits]} (want {n})")
        ok = len(hits) == n
        if ok and n and len(sys.argv) > 6 and sys.argv[6] != "-":
            want = float(sys.argv[6])
            ok = abs(hits[0] - want) < 0.01
            print(f"  the first at {hits[0]:.3f} s, want {want:.3f}")
        if ok and n > 1:
            gaps = np.diff(hits)
            ok = bool(np.all(np.abs(gaps - gap) < 0.05))
            print(f"  apart {np.round(gaps, 3).tolist()} (want {gap} +- 0.05)")
        return 0 if ok else 1
    if what == "events":
        log = Path(sys.argv[2]).read_text()
        name, t0, t1, n = sys.argv[3], float(sys.argv[4]), float(sys.argv[5]), int(sys.argv[6])
        ev = [t for t in log_events(log, name) if t0 <= t <= t1]
        print(f"{name} between {t0} and {t1} s: {[round(t, 3) for t in ev]} (want {n})")
        return 0 if len(ev) == n else 1
    if what == "calls":
        log = Path(sys.argv[2]).read_text()
        t0, t1, n = float(sys.argv[3]), float(sys.argv[4]), int(sys.argv[5])
        sel = lambda v: [t for t in v if t0 <= t <= t1]
        hits, hi, lo = sel(log_events(log, "HIT")), sel(log_events(log, "PIPE high")), sel(log_events(log, "PIPE low"))
        print(f"cuckoo calls between {t0} and {t1} s: {len(hits)} blows, {len(hi)} high pipes, {len(lo)} low (want {n})")
        ok = len(hits) == len(hi) == len(lo) == n
        if ok and n:
            d1 = np.array(hi) - np.array(hits)
            d2 = np.array(lo) - np.array(hi)
            gaps = np.diff(hits)
            print(f"  the blow to the high pipe {np.round(d1, 3).tolist()} s, to the low {np.round(d2, 3).tolist()} s, "
                  f"call to call {np.round(gaps, 3).tolist()} s")
            ok = abs(d1[0] - 0.221) < 0.01 and bool(np.all(np.abs(d1[1:] - 0.110) < 0.01)) and \
                bool(np.all(np.abs(d2 - 0.191) < 0.01)) and bool(np.all(np.abs(gaps - 0.665) < 0.02))
        return 0 if ok else 1
    if what == "even":
        g = [int(v) for v in re.findall(r"HIT at [\d.]+ s, strength (\d+)", Path(sys.argv[2]).read_text())]
        lo, hi = (min(g) / g[0], max(g) / g[0]) if g else (0, 0)
        print(f"{len(g)} blows, from {lo:.3f} to {hi:.3f} of the first")
        return 0 if g and lo > 0.88 and hi < 1.14 else 1
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
        P = float(sys.argv[5]) if len(sys.argv) > 5 else 0.5
        tol = float(sys.argv[6]) / 1000 if len(sys.argv) > 6 else 0.003
        ev = [(t, lr) for t, lr in tick_events(x, fs, t0, t1) if t0 <= t <= t1]
        # the ticks' place in the half second: where most of them are (fm1-emu's sound starts a little after the
        # power-on, the host's with it); one click at each end, nothing between
        ph = np.array([t % P for t, _ in ev])
        circ = lambda a, b: np.abs(((a - b + P / 2) % P) - P / 2)
        cand = [p0 for p0 in ph]
        phase = max(cand, key=lambda p0: np.sum(circ(ph, p0) < 0.004)) if len(ph) else 0.0
        main_ = [e for e, q in zip(ev, ph) if circ(q, phase) < 0.004]
        others = len(ev) - len(main_)
        ts = np.array([e[0] for e in main_])
        ok = len(ts) >= int((t1 - t0) / P) - 1
        err = circ(ts % P, phase) if len(ts) else np.array([1.0])
        gaps = np.diff(ts) if len(ts) > 1 else np.array([P])
        sides = [e[1] > 0 for e in main_]
        alt = all(a != b for a, b in zip(sides, sides[1:]))
        print(f"ticks {t0}..{t1} s: {len(ts)} on the beats of {P} s (at +{1000 * phase:.1f} ms; worst {1000 * err.max():.1f} ms "
              f"off), apart {gaps.min():.4f} .. {gaps.max():.4f} s, {others} clicks between; "
              f"left / right in turn: {alt}")
        return 0 if ok and err.max() < tol and np.all(np.abs(gaps - P) < tol + 0.001) and alt and others == 0 else 1
    if what == "same":
        a = np.asarray(Image.open(sys.argv[2]).convert("RGB")).astype(int)
        b = np.asarray(Image.open(sys.argv[3]).convert("RGB")).astype(int)
        s = a.shape[0] // 240
        x, y, w, h, most = (int(v) for v in sys.argv[4:9])
        d = np.abs(a[y * s:(y + h) * s, x * s:(x + w) * s] - b[y * s:(y + h) * s, x * s:(x + w) * s]).sum(axis=2) > 30
        print(f"{w} x {h} at ({x}, {y}): {d.sum() // (s * s)} pixels changed (at most {most})")
        return 0 if d.sum() // (s * s) <= most else 1
    if what in ("moved", "differ"):
        a = np.asarray(Image.open(sys.argv[2]).convert("RGB")).astype(int)
        b = np.asarray(Image.open(sys.argv[3]).convert("RGB")).astype(int)
        s = a.shape[0] // 240
        if what == "differ":
            x, y, w, h, need = (int(v) for v in sys.argv[4:9])
        elif len(sys.argv) > 4 and sys.argv[4] == "cuckoo":   # (clk_draw.h: LO_X, LO_W; the rows under the house)
            x, w, y = 84, 72, art_consts("clk_art_cuckoo.h")["CK_FRONT_Y"]
            h, need = 240 - y, 40
        else:
            c = art_consts()
            x, y, w, h, need = c["WIN_X"], c["WIN_Y"], c["WIN_W"], c["WIN_H"], 40
        d = np.abs(a[y * s:(y + h) * s, x * s:(x + w) * s] - b[y * s:(y + h) * s, x * s:(x + w) * s]).sum(axis=2) > 30
        print(f"{w} x {h} at ({x}, {y}): {d.sum() // (s * s)} pixels changed (want {need})")
        return 0 if d.sum() // (s * s) >= need else 1
    if what == "hands":
        ck = len(sys.argv) > 5 and sys.argv[5] == "cuckoo"
        c = art_consts("clk_art_cuckoo.h") if ck else art_consts()
        im = np.asarray(Image.open(sys.argv[2]).convert("RGB")).astype(float)
        s = im.shape[0] / 240
        hh, mm = int(sys.argv[3]), int(sys.argv[4])
        hx, hy = (c["CK_HUB_X256"] / 256, c["CK_HUB_Y256"] / 256) if ck else (c["HUB_X256"] / 256, c["HUB_Y256"] / 256)
        rm, rh = ((18, 21), (7, 12)) if ck else ((25, 29), (9, 16))   # out there only the minute hand; the hour's
        lum = im.mean(axis=2)

        def ray(deg, r0, r1):
            v = []
            for r in np.linspace(r0, r1, 24):
                x, y = hx + r * np.sin(np.radians(deg)), hy - r * np.cos(np.radians(deg))
                v.append(lum[int(y * s), int(x * s)])
            return np.mean(v)
        angles = np.arange(0, 360, 3)
        m_d = angles[int(np.argmin([ray(a, *rm) for a in angles]))]
        h_d = angles[int(np.argmin([ray(a, *rh) - (0 if abs(((a - m_d + 180) % 360) - 180) > 12 else -999)
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
        m = re.search(r"^\s*0x[0-9a-f]+: ([0-9a-f]{8}) ([0-9a-f]{8}) ([0-9a-f]{8}) ([0-9a-f]{8}) ([0-9a-f]{8})"
                      r"(?: ([0-9a-f]{8}))?", txt, re.M)
        if not m:
            print("no dump of eng_st (build/fm1clock.syms?)")
            return 1
        ng, load, peak, worst, blocks = (int(v, 16) for v in m.groups()[:5])
        clock = int(m.group(6), 16) if m.group(6) else 0
        t = table_consts()
        block = 139320
        ops = ng + t["K_FM"] + 2 * t["NT"] + t["PIPE_OPS"]
        name = ("the wall clock's coil gong", t["NG"]) if clock == 0 else ("the cuckoo's wire gong", t["NGB"])
        print(f"fm1-emu: the governor renders {ng} of {name[0]}'s {name[1]} carriers ({ops} FM operators in all, with "
              f"the modulators, the ticks', the pipes', the drone's and the rattle's); the engine takes {100 * load / block:.1f} % of a block, "
              f"{100 * worst / block:.1f} % at its worst, over {blocks} blocks")
        if len(sys.argv) > 4 and clock != int(sys.argv[4]):
            print(f"  the clock sounding is {clock}, want {sys.argv[4]}")
            return 1
        import os
        if os.environ.get("GITHUB_ACTIONS"):
            print(f"::notice title=fm1-emu ({'cuckoo' if clock else 'wall clock'})::{ops} FM operators, the engine {100 * load / block:.0f} % of the chip "
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
