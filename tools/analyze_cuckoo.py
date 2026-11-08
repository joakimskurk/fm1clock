#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Measure the second reference recording, a small Black Forest cuckoo clock (a one-day "leaf and loon" clock)
calling the half hour and ten o'clock, and write what the cuckoo clock's sound is fitted to. As with the wall clock,
the recording is not in this repository; its measurements are:

  tools/ref_cuckoo.json            its gong's modes (matrix pencil per band), the two pipes (pitch, harmonics, their
                                   envelopes), the timing of a call and of the mechanism around a call, the beat
  tests/ref/cuckoo_features.json   band energies over time: the gong's hit, a whole call, the ticks, the clicks

  python3 -I tools/analyze_cuckoo.py RECORDING.wav      (numpy and scipy)

The recording: 48 kHz, 13.7 s. Ticks 0.428 s apart; at 2.23 s the half hour (one call); 5.39-11.7 s ten o'clock (ten
calls 0.655 s apart). A call: the hammer hits a wire gong, 0.15 s later the bellows blow the high pipe (1224 Hz), 0.17 s
after that the low pipe (998 Hz). Before a strike the train clicks (the warning, the door), after it the door shuts.
"""
import json
import sys
from pathlib import Path

import numpy as np
import scipy.io.wavfile as wavfile
import scipy.signal as sg

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
from analyze_ref import matrix_pencil  # noqa: E402
from features import BANDS, band_energies  # noqa: E402
import clicks as K  # noqa: E402

HALF_HIT = 2.232                                    # (by eye; refined below) the half hour's gong
TRAIN = [5.387, 6.147, 6.772, 7.397, 8.048, 8.718, 9.384, 10.055, 10.719, 11.385]
HIGH = [5.621, 6.284, 6.908, 7.541, 8.197, 8.862, 9.53, 10.199, 10.862, 11.531]
LOW = [5.81, 6.445, 7.057, 7.698, 8.361, 9.031, 9.709, 10.375, 11.037, 11.705]
TICKS = [0.459, 0.886, 1.314, 3.032, 3.458, 3.888, 4.315, 12.475, 12.903, 13.333]   # (all of them: the beat)
TICKS_CLEAN = [0.459, 0.886, 3.458, 3.888, 4.315]   # the ticks with nothing under them for 0.13 s: the sound (at
# 1.314 the warning comes, at 3.032 and after 12 s the gong still rings from a call)
PRE = [1.492, 4.655, 4.729, 4.99]                   # the train's clicks before a strike (warning, door)
POST = [2.825, 11.784, 11.94]                       # and after it (the door shuts)
F_HIGH, F_LOW = 1223.9, 997.6
CALL_WIN = [(0.000, 0.020), (0.020, 0.060), (0.060, 0.140), (0.140, 0.220), (0.220, 0.300), (0.300, 0.400),
            (0.400, 0.500), (0.500, 0.600)]       # a whole call, from the gong's hit (the next one may come at 0.62 s)
GONG_WIN = [(0.000, 0.010), (0.010, 0.030), (0.030, 0.070), (0.070, 0.140)]   # the hit alone (before the pipe)
TICK_WIN = [(-0.002, 0.004), (0.004, 0.010), (0.010, 0.020), (0.020, 0.035), (0.035, 0.060), (0.060, 0.090),
            (0.090, 0.130)]                       # (it rings on: -30 dB above 1.5 kHz at 0.15 s)


def onset(m, fs, t, thr=0.3, span=0.03):
    """the first sample over thr of the local peak (above 400 Hz), within +-span of t"""
    b, a = sg.butter(4, 400 / (fs / 2), "high")
    t0 = max(t - span, 0.003)
    seg = sg.filtfilt(b, a, m[int(t0 * fs):int((t + span) * fs)])
    return t0 + int(np.argmax(np.abs(seg) > thr * np.abs(seg).max())) / fs


def gong_modes(m, fs, hit):
    """the wire gong's modes from the half hour's strike: per 70 Hz band, matrix pencil; the bands that the pipes
    sound in see only the 0.17 s before the first pipe, the others 0.75 s"""
    dec, step = 120, 70.0
    fs_d = fs / dec
    lp = sg.firwin(1201, 85.0, fs=fs)
    near = lambda f: min(abs(f - F_HIGH), abs(f - F_LOW), abs(f - 2 * F_HIGH), abs(f - 2 * F_LOW)) < 80
    modes = []
    for fc in np.arange(80.0, 15000.0, step):                # (from 45 Hz: the case knocks low when the hammer falls)
        t_a, t_b = 0.004, 0.165 if near(fc) else 0.75
        x = m[int((hit + t_a) * fs):int((hit + t_b) * fs)]
        t = np.arange(len(x)) / fs + t_a
        z = sg.lfilter(lp, 1.0, x * np.exp(-2j * np.pi * fc * t))[600::dec]
        if len(z) < 30:
            continue
        for zz, amp in matrix_pencil(z, 10, 1 / fs_d):
            f = fc + np.angle(zz) * fs_d / (2 * np.pi)
            alpha = -np.log(np.abs(zz)) * fs_d
            if abs(f - fc) > step / 2 or alpha <= 0.2 or alpha > 200:
                continue
            a0 = 2 * np.abs(amp) * np.exp(alpha * t_a)
            ph = np.angle(amp) - 2 * np.pi * (f - fc) * t_a
            modes.append(dict(f=float(f), tau=float(1 / alpha), a=float(a0), ph=float(np.angle(np.exp(1j * ph)))))
    top = max(d["a"] for d in modes)
    keep = [d for d in modes if d["a"] > top * 10 ** (-55 / 20) and d["a"] ** 2 * d["tau"] > top ** 2 * 1e-6]
    keep.sort(key=lambda d: d["f"])
    return keep


def pipe(m, fs, onsets, f0, frames_step):
    """a pipe's note: its envelope (the median of the calls, demodulated at f0, 60 Hz wide), from 10 ms before it
    rises over -30 dB of its peak to where it falls under -45 dB or back to what rang there before it (the gong);
    its harmonics against the fundamental"""
    t = np.arange(len(m)) / fs
    z = m * np.exp(-2j * np.pi * f0 * t)
    b, a = sg.butter(2, 60 / (fs / 2))
    env = 2 * np.abs(sg.filtfilt(b, a, z.real) + 1j * sg.filtfilt(b, a, z.imag))
    curves, starts = [], []
    for o in onsets:
        i0, i1 = int((o - 0.03) * fs), int((o + 0.20) * fs)
        e = env[i0:i1]
        pk = e.max()
        k = i0 + int(np.argmax(e > pk * 10 ** (-30 / 20)))         # (-30 dB: the gong rings under it)
        starts.append(k / fs)
        curves.append(env[k - int(0.01 * fs):k - int(0.01 * fs) + int(0.30 * fs)])
    med = np.median(np.array(curves), axis=0)
    floor = np.median(med[:int(0.005 * fs)])                   # (the gong rings at this pitch too: the 5 ms before)
    after = (np.arange(len(med)) > np.argmax(med)) & (med < max(med.max() * 10 ** (-45 / 20), 1.5 * floor))
    end = int(np.argmax(after)) if after.any() else len(med)
    med = np.clip(med[:end] - floor, 0, None)                 # (the note alone: the floor taken off)
    step = frames_step * fs / 44100
    table = [float(med[int(i * step)]) for i in range(int(len(med) / step))]
    H = []
    for o in onsets:
        s = m[int((o + 0.01) * fs):int((o + 0.045) * fs)]
        S = np.abs(np.fft.rfft(s * np.hanning(len(s)), 1 << 15))
        f = np.fft.rfftfreq(1 << 15, 1 / fs)
        H.append([S[(f > k * f0 - 15) & (f < k * f0 + 15)].max() for k in (1, 2, 3)])
    H = np.median(np.array(H), axis=0)
    # the note's body: what rises 10 dB or more when the note starts (the 30 ms before against its first 70 ms),
    # 100 Hz .. 3 kHz, its harmonics aside: the bellows and the pipe's wood (the gong rings on before and after)
    N = 1 << 15
    f = np.fft.rfftfreq(N, 1 / fs)
    Pn, Pb = 0, 0
    for o in starts:
        sn = m[int((o + 0.005) * fs):int((o + 0.075) * fs)]
        sb = m[int((o - 0.035) * fs):int((o - 0.005) * fs)]
        Pn = Pn + np.abs(np.fft.rfft(sn * np.hanning(len(sn)), N)) ** 2 / np.sum(np.hanning(len(sn)) ** 2)
        Pb = Pb + np.abs(np.fft.rfft(sb * np.hanning(len(sb)), N)) ** 2 / np.sum(np.hanning(len(sb)) ** 2)
    fund = Pn[(f > f0 - 15) & (f < f0 + 15)].max()
    dn = 10 * np.log10(Pn / fund + 1e-20)
    sm = np.convolve(dn, np.ones(5) / 5, "same")
    pk, _ = sg.find_peaks(sm, prominence=4, distance=int(20 / (fs / N)))
    body = []
    for q in pk:
        fq = f[q]
        if not 100 < fq < 3000 or min(abs(fq - k * f0) for k in (1, 2, 3)) < 40 or dn[q] < -40:
            continue
        rise = 10 * np.log10(Pn[q] / (Pb[q] + 1e-20))
        if rise >= 10:
            body.append(dict(f=float(fq), rel=float(10 ** (dn[q] / 20))))
    return dict(f=f0, env=table, env_step=frames_step, starts=starts, body=body,
                h2=float(20 * np.log10(H[1] / H[0])), h3=float(20 * np.log10(H[2] / H[0])))


def mean_bands(m, fs, times, wins):
    E = [10 ** (band_energies(m, fs, t, wins) / 10) for t in times]
    return (10 * np.log10(np.mean(E, axis=0))).tolist()


def clicks(m, fs, times, seed_name):
    """a click's spectrum (third octaves) and its decay per octave band, as tools/analyze_ref.py measures ticks"""
    b, a = sg.butter(4, 400 / (fs / 2), "high")
    h = sg.filtfilt(b, a, m)
    ons = [onset(m, fs, t) for t in times]
    P = 0
    for o in ons:
        s = h[int((o - 0.002) * fs):int((o + 0.040) * fs)]
        P = P + np.abs(np.fft.rfft(s * np.hanning(len(s)), 8192)) ** 2
    f = np.fft.rfftfreq(8192, 1 / fs)
    Pdb = 10 * np.log10(P / len(ons) + 1e-20)
    sm = np.convolve(Pdb, np.ones(3) / 3, "same")
    pk, _ = sg.find_peaks(sm, prominence=3, distance=8)
    peaks = sorted(((float(f[p]), float(sm[p])) for p in pk if 800 < f[p] < 15000), key=lambda v: -v[1])[:40]
    env3 = []
    for lo, hi in zip(BANDS[:-1], BANDS[1:]):
        sel = (f >= lo) & (f < hi)
        env3.append(float(10 * np.log10(np.mean(10 ** (Pdb[sel] / 10)) + 1e-20)))
    b3, a3 = sg.butter(4, 3000 / (fs / 2), "high")             # its peak above 3 kHz (the gong's and the pipes'
    h3 = sg.filtfilt(b3, a3, m)                                 # partials under it: a click's level, whatever rings)
    peak = float(np.mean([np.abs(h3[int(o * fs):int((o + 0.015) * fs)]).max() for o in ons]))
    return ons, dict(peaks=peaks, envelope=env3, peak_hf=peak), mean_bands(h, fs, ons, TICK_WIN)



def case_knock(m, fs, ons, lo=80.0, hi=450.0, lead=0.10, span=0.08):
    """the case's knock under the tick: under 400 Hz the room rumbles as loud as it, but the knock comes back the
    same with every tick and the rumble does not, so the ticks before the train, averaged sample by sample, keep it
    and leave the rumble 8.5 dB down. Its modes by matrix pencil (the average's lo..hi Hz, as an analytic signal,
    decimated), and its energy over span s above the average's floor before the tick (dB, for the tests)"""
    L = int(0.25 * fs)
    ca = np.mean([m[int((o - lead) * fs):int((o - lead) * fs) + L] for o in ons], axis=0)
    X = np.fft.fft(ca)
    f = np.fft.fftfreq(L, 1 / fs)
    X[(f < lo) | (f > hi)] = 0                                  # the band, positive frequencies only: analytic
    za = np.fft.ifft(X) * 2
    dec = 24
    seg = za[int(lead * fs):int((lead + span) * fs):dec]
    modes = []
    for z, amp in matrix_pencil(seg, 10, dec / fs):
        fr = float(np.angle(z) / (2 * np.pi) * fs / dec)
        a_ = -np.log(abs(z)) * fs / dec
        if lo <= fr <= hi and a_ > 0 and 1 / a_ > 0.002:
            modes.append(dict(f=fr, tau=float(min(1 / a_, 0.2)), a=float(abs(amp))))
    re = np.real(za)
    e_tick = np.mean(re[int(lead * fs):int((lead + span) * fs)] ** 2)
    e_floor = np.mean(re[int((lead - 0.09) * fs):int((lead - 0.01) * fs)] ** 2)
    return sorted(modes, key=lambda d: -d["a"] ** 2 * d["tau"])[:8], float(10 * np.log10(max(e_tick - e_floor, 1e-20)))


IDLE = [(3.05, 3.45), (3.50, 3.88), (3.92, 4.30)]   # the train still: the ticks only


def train_drone(m, fs, run, n_max=12):
    """the striking train's drone while it runs (run: its stretches; its wheels, its fly: 74 Hz and up, 15-30 dB
    over the train still): the peaks of the running spectrum that stand 6 dB over the still one, each its level
    from a narrow band round it (running less still), and the drone's energy 40-450 Hz over the still (dB)"""
    N = 1 << 16
    def psd(segs):
        acc = 0
        for a, b in segs:
            x = m[int(a * fs):int(b * fs)]
            w = np.hanning(len(x))
            acc = acc + np.abs(np.fft.rfft(x * w, N)) ** 2 / np.sum(w ** 2)
        return acc / len(segs)
    f = np.fft.rfftfreq(N, 1 / fs)
    pr, pi = psd(run), psd(IDLE)
    db, over = 10 * np.log10(pr + 1e-30), 10 * np.log10(pr + 1e-30) - 10 * np.log10(pi + 1e-30)
    sel = (f > 40) & (f < 450)                       # (above it, the rattle: tools/analyze_cuckoo.py train_rattle)
    pk, _ = sg.find_peaks(np.where(sel, db, -300), prominence=6, distance=4)
    pk = sorted([p for p in pk if over[p] > 6], key=lambda p: -db[p])[:n_max]
    n = len(m)
    X = np.fft.rfft(m)
    fx = np.fft.rfftfreq(n, 1 / fs)
    def rms(lo, hi, segs):
        Y = X.copy()
        Y[(fx < lo) | (fx > hi)] = 0
        y = np.fft.irfft(Y, n)
        return np.mean([np.mean(y[int(a * fs):int(b * fs)] ** 2) for a, b in segs])
    parts = []
    for p in sorted(pk):
        e = rms(f[p] - 3, f[p] + 3, run) - rms(f[p] - 3, f[p] + 3, IDLE)
        if e > 0:
            parts.append(dict(f=float(f[p]), a=float(np.sqrt(2 * e))))
    e_db = 10 * np.log10(max(rms(40, 450, run) - rms(40, 450, IDLE), 1e-20))
    return parts, float(e_db)


def train_rattle(m, fs, h0, n_max=10):
    """the train running: its wheels and fly rattle, an irregular click every 2-10 ms (median ~4) above 800 Hz.
    Before the first call it runs twice: from the warning (the train unlocked) until it catches on the warning pin,
    and from the release (the door) on through the calls. Measured: when it starts and stops before the first blow
    h0 (the envelope above 2.5 kHz crossing halfway, in dB, between the train still and running), its spectrum
    (the running less the still, the peaks 800 Hz - 14 kHz), its energy above 800 Hz (dB, for the tests)"""
    n = len(m)
    X = np.fft.rfft(m)
    fx = np.fft.rfftfreq(n, 1 / fs)
    Y = X.copy()
    Y[fx < 2500] = 0
    hf = np.fft.irfft(Y, n)
    k = int(0.01 * fs)
    lv = lambda t: 20 * np.log10(np.sqrt(np.mean(hf[int(t * fs):int(t * fs) + k] ** 2)) + 1e-12)
    still = np.median([lv(t) for t in np.arange(h0 - 0.98, h0 - 0.90, 0.01)])
    run = np.median([lv(t) for t in np.arange(h0 - 0.84, h0 - 0.76, 0.01)])
    mid = (still + run) / 2
    ts = np.arange(h0 - 1.0, h0 - 0.75, 0.005)
    t_run = next(t for t in ts if lv(t) > mid)
    ts = np.arange(h0 - 0.62, h0 - 0.42, 0.005)
    t_stop = next(t for t in ts if lv(t) < mid)
    RUNS = [(t_run + 0.02, h0 - 0.76), (h0 - 0.36, h0 - 0.24), (h0 - 0.17, h0 - 0.02)]   # (no tick, no warning click in them)
    QUIET = [(3.10, 3.40), (3.53, 3.83), (3.96, 4.25)]
    N = 1 << 15
    def psd(segs):
        acc = 0
        for a, b in segs:
            x = m[int(a * fs):int(b * fs)]
            w = np.hanning(len(x))
            acc = acc + np.abs(np.fft.rfft(x * w, N)) ** 2 / np.sum(w ** 2) / len(x)
        return acc / len(segs)
    f = np.fft.rfftfreq(N, 1 / fs)
    pr, pq = psd(RUNS), psd(QUIET)
    net = np.clip(pr - pq, 0, None)
    sel = (f > 800) & (f < 14000)
    sm = np.convolve(net, np.ones(9) / 9, "same")
    pk, _ = sg.find_peaks(np.where(sel, sm, 0), distance=40)
    pk = sorted(pk, key=lambda p: -sm[p])[:n_max]
    grains = [dict(f=float(f[p]), w=float(sm[p])) for p in sorted(pk)]
    Y = X.copy()
    Y[fx < 800] = 0
    hb = np.fft.irfft(Y, n)
    e = lambda segs: np.mean([np.mean(hb[int(a * fs):int(b * fs)] ** 2) for a, b in segs])
    e_db = 10 * np.log10(max(e(RUNS) - e(QUIET), 1e-20))
    return dict(start=float(t_run - h0), stop=float(t_stop - h0), grains=grains), float(e_db)


# the mechanism's clicks, each its own sound (tools/clicks.py): when, and the quiet before each (its floor)
CLICKS = {
    "tick": (TICKS_CLEAN, (-0.060, -0.035)),
    "warning": ([1.492, 4.652, 4.732], (-0.016, -0.004)),   # (the train rattles before them: its floor right before)
    "door": ([5.000], (-0.060, -0.035)),                   # the release: the door opens (the train still before it)
    "door_shut": ([11.940, 2.825], (-0.060, -0.035)),
}
# (the bird going in, 11.784 s, sounds on the low pipe's note, so its own sound cannot be measured: above 3 kHz,
# where the pipe is quiet, it is as loud as the door shutting, within 1.2 dB; the firmware makes it that sound)
TICKS_SAME = [0.459, 0.886, 3.458, 3.888, 4.315, 12.903, 12.475]   # the ticks averaged for what comes back every time
                                                    # (at 13.333 the onset is found 0.8 ms early: it lines up badly)
FLAT_BANDS = [(500, 1500), (1500, 3000), (3000, 7000), (7000, 14000)]
FLAT_WINS = [(0.0, 0.02), (0.02, 0.06), (0.06, 0.12)]
DOOR_WOOD = [(1000.0, 1700.0), (3800.0, 5600.0)]   # the door's wood, its tok: struck three times (0, 10, 19 ms)


def fine_clicks(m, fs):
    """every click: its onsets, its power in both grids (tools/clicks.py), how much like noise it is (its spectral
    flatness, bands x windows); the tick's crack and its case's knock, from the ticks lined up and averaged sample
    by sample; the door's wood struck, from the one door"""
    out = dict(t0=dict(tick=K.T0_TICK, other=K.T0_CLICK), ta=K.TA, flat_bands=FLAT_BANDS, flat_windows=FLAT_WINS)
    for name, (ts, quiet) in CLICKS.items():
        ons = [onset(m, fs, t) for t in ts]
        det = []
        if name == "tick":
            same, cor = K.align(m, fs, [onset(m, fs, t) for t in TICKS_SAME], ref=3)
            print("tick: lined up, " + ", ".join(f"{c:.2f}" for c in cor))
            ons = same[:len(ts)]
            ca = K.coherent(m, fs, same)
            crack = K.modes(ca, fs, 0.02, 1500.0, 16000.0, K.T0_TICK, 0.015, 14, K.TA)
            knock = [d for d in K.modes(ca, fs, 0.02, 80.0, 450.0, K.T0_TICK, 0.08, 8, K.TA, tau_max=0.05)
                     if d["tau"] > 0.002]
            det = crack + knock
            print(f"tick: its crack {len(crack)} modes ({min(d['f'] for d in crack):.0f}-"
                  f"{max(d['f'] for d in crack):.0f} Hz), its case's knock {len(knock)}")
        if name == "door":
            for lo, hi in DOOR_WOOD:
                at, left = K.strikes(m, fs, ons[0], K.T0_CLICK, K.TA, lo, hi, n=6)
                det += at
                print(f"door: its wood {lo:.0f}-{hi:.0f} Hz, {len(at)} strikes, {100 * (1 - left):.0f} % of it")
        meas = K.measure(m, fs, ons, quiet)
        flat = [[K.flatness(m, fs, ons, a, b, lo, hi) for lo, hi in FLAT_BANDS] for a, b in FLAT_WINS]
        snr = [[K.over_floor(m, fs, ons, a, b, lo, hi, quiet) for lo, hi in FLAT_BANDS] for a, b in FLAT_WINS]
        out[name] = dict(ons=ons, quiet=quiet, det=det, flat=flat, flat_snr=snr,
                         **{g: dict(E=meas[g][0].tolist(), N=meas[g][1].tolist()) for g in meas})
    return out

def main():
    if len(sys.argv) < 2:
        print(__doc__)
        return 2
    fs, x = wavfile.read(sys.argv[1])
    m = x.astype(float) / 32768
    if m.ndim > 1:
        m = m.mean(axis=1)
    hit = onset(m, fs, HALF_HIT, 0.2)
    train = [onset(m, fs, t, 0.2) for t in TRAIN]
    modes = gong_modes(m, fs, hit)
    step = 16
    hi_p = pipe(m, fs, HIGH, F_HIGH, step)
    lo_p = pipe(m, fs, LOW, F_LOW, step)
    d_hi = [s - t for s, t in zip(hi_p["starts"], train)]
    d_lo = [s - t for s, t in zip(lo_p["starts"], hi_p["starts"])]
    tick_ons = [onset(m, fs, t) for t in TICKS]
    _, tick, tick_bands = clicks(m, fs, TICKS_CLEAN, "tick")
    pre_ons, pre, pre_bands = clicks(m, fs, PRE, "pre")
    post_ons, post, post_bands = clicks(m, fs, POST, "post")
    beat = float(np.median([b - a for a, b in zip(tick_ons, tick_ons[1:]) if b - a < 0.5]))
    noise = band_energies(m, fs, 3.60, [(0.0, 0.2)])[0]
    # the floor under a tick: just before each clean one (at 3.6 s the half hour's gong and a tick still ring low)
    b4, a4 = sg.butter(4, 400 / (fs / 2), "high")
    h4 = sg.filtfilt(b4, a4, m)
    tick_noise = mean_bands(h4, fs, [onset(m, fs, t) - 0.10 for t in TICKS_CLEAN], [(0.0, 0.09)])[0]
    knock, knock_db = case_knock(m, fs, tick_ons[:7])
    rattle, rattle_db = train_rattle(m, fs, train[0])
    h0 = train[0]                                   # the train running before the first call: no gong, no pipe yet
    drone, drone_db = train_drone(m, fs, [(h0 + rattle["start"] + 0.03, h0 + rattle["stop"] - 0.01), (h0 - 0.36, h0 - 0.02)])
    model = dict(fs=fs, hit=hit, modes=modes, pipes=dict(high=hi_p, low=lo_p),
                 call=dict(period=float(np.median(np.diff(train))), hit_to_high=float(np.median(d_hi[1:])),
                           first_hit_to_high=float(d_hi[0]), high_to_low=float(np.median(d_lo))),
                 mech=dict(pre=[p - train[0] for p in pre_ons[1:]] + [pre_ons[0] - hit],
                           post=[p - lo_p["starts"][-1] for p in post_ons[1:]] + [post_ons[0] - hit]),
                 beat=beat, ticks=dict(tick=tick, pre=pre, post=post, knock=knock), drone=drone,
                 rattle=rattle)
    feats = dict(bands=BANDS, call_windows=CALL_WIN, gong_windows=GONG_WIN, tick_windows=TICK_WIN,
                 gong=band_energies(m, fs, hit, GONG_WIN).tolist(),
                 call=mean_bands(m, fs, train[1:], CALL_WIN), call_times=train[1:],
                 tick=tick_bands, pre=pre_bands, post=post_bands, noise=noise.tolist(), tick_noise=tick_noise,
                 knock_db=knock_db, drone_db=drone_db, rattle_db=rattle_db)
    (ROOT / "tools" / "ref_cuckoo.json").write_text(json.dumps(model, indent=1) + "\n")
    (ROOT / "tests" / "ref" / "cuckoo_clicks.json").write_text(json.dumps(fine_clicks(m, fs)) + "\n")
    (ROOT / "tests" / "ref" / "cuckoo_features.json").write_text(json.dumps(feats, indent=1) + "\n")
    print(f"gong hit {hit:.4f} s, {len(modes)} modes; beat {beat:.4f} s; call every {model['call']['period']:.3f} s, "
          f"hit -> high pipe {model['call']['hit_to_high']:.3f} s (the train's first {d_hi[0]:.3f}), high -> low "
          f"{model['call']['high_to_low']:.3f} s; pipes {F_HIGH} Hz ({len(hi_p['env'])} steps, 2nd {hi_p['h2']:.0f} dB), "
          f"{F_LOW} Hz ({len(lo_p['env'])} steps, 2nd {lo_p['h2']:.0f} dB); clicks before {model['mech']['pre']}, "
          f"after {model['mech']['post']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
