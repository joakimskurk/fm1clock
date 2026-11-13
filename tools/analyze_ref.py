#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
# Copyright (C) 2026 Joakim (joakimskurk)
"""Measure the reference recording (a 31-day pendulum wall clock striking on a coil gong) and write what the
firmware's sound is fitted to. The recording itself is not in this repository (it is not ours to share); its
measurements are:

  tools/ref_model.json     the gong's modes (frequency, decay, amplitude at the hit) from a matrix-pencil fit per
                           band, the strike train's timing and gains, the two tick sounds' spectra and decays
  tests/ref/features.json  what the tests compare the engine with: band energies over time after the hit, for the
                           gong and for both ticks

  python3 -I tools/analyze_ref.py RECORDING.wav        (needs numpy and scipy; run once, the outputs are committed)

The recording: 48 kHz, mono in two channels, 43 s. 0-15.5 s ticking; one strike at 15.65 s (alone: the model's
source); 11 strikes from 25.7 s, 1.18 s apart (the train's gains).
"""
import json
import sys
from pathlib import Path

import numpy as np
import scipy.io.wavfile as wavfile
import scipy.signal as sg

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

from features import BANDS, GONG_WIN, TICK_WIN, band_energies  # noqa: E402


def tick_gates(m, fs, hit, t_end):
    """the clock's ticks during the gong's decay (above 8 kHz the gong is quiet after its first 0.2 s): (a, b) after
    the hit, 4 ms before each tick to 45 ms after"""
    b, a = sg.butter(4, 8000 / (fs / 2), "high")
    h = sg.filtfilt(b, a, m[int(hit * fs):int((hit + t_end) * fs)])
    env = np.sqrt(np.convolve(h ** 2, np.ones(96) / 96, "same"))
    pk, _ = sg.find_peaks(env, height=np.median(env) * 6, distance=int(0.3 * fs))
    return [(p / fs - 0.004, p / fs + 0.045) for p in pk if p / fs > 0.15]


def find_hit(m, fs, t_from, t_to, thr=0.05):
    """the gong's hit: the first sample over thr after the small click before it (the hammer's lift)"""
    seg = np.abs(m[int(t_from * fs):int(t_to * fs)])
    i = np.argmax(seg > thr)
    return t_from + i / fs


def matrix_pencil(y, order_max, dt):
    """damped complex exponentials in y (complex): [(z, amp)], z = exp((-a + jw) dt)"""
    n = len(y)
    L = n // 3
    Y = np.array([y[i:i + L + 1] for i in range(n - L)])
    U, s, Vh = np.linalg.svd(Y, full_matrices=False)
    M = int(min(order_max, np.sum(s > s[0] * 10 ** (-45 / 20))))
    if M < 1:
        return []
    V = Vh[:M].T                                              # (the rows of Y lie in the span of conj(V): not V)
    V1, V2 = V[:-1], V[1:]
    z = np.linalg.eigvals(np.linalg.pinv(V1) @ V2)
    Z = np.vander(z, n, increasing=True).T                     # n x M
    amp, *_ = np.linalg.lstsq(Z, y, rcond=None)
    return list(zip(z, amp))


def gong_modes(m, fs, hit):
    """the gong's modes from the lone strike: per band, heterodyned to 0, decimated, matrix pencil"""
    t_a, t_b = 0.06, 5.2                                       # after the hit's transient; before the room noise at 22 s
    x = m[int((hit + t_a) * fs):int((hit + t_b) * fs)]
    t = np.arange(len(x)) / fs + t_a
    dec, step = 120, 70.0                                      # 400 Hz after decimation; bands 70 Hz apart
    fs_d = fs / dec
    lp = sg.firwin(1201, 85.0, fs=fs)
    modes = []
    for fc in np.arange(150.0, 15000.0, step):
        z = x * np.exp(-2j * np.pi * fc * t)
        zb = sg.lfilter(lp, 1.0, z)[600::dec]                 # (the FIR's delay: 600 samples)
        tb = t[600::dec][:len(zb)] - 600 / fs
        for zz, amp in matrix_pencil(zb, 12, 1 / fs_d):
            f = fc + np.angle(zz) * fs_d / (2 * np.pi)
            alpha = -np.log(np.abs(zz)) * fs_d                 # 1/s
            if abs(f - fc) > step / 2 or alpha <= 0.05 or alpha > 40:
                continue
            a0 = 2 * np.abs(amp) * np.exp(alpha * tb[0])       # the amplitude extrapolated to the hit (t = 0)
            ph = np.angle(amp) - 2 * np.pi * (f - fc) * tb[0]   # the phase at the hit: x = a e^(-t/tau) cos(2 pi f t + ph)
            modes.append(dict(f=float(f), tau=float(1 / alpha), a=float(a0), ph=float(np.angle(np.exp(1j * ph)))))
    # (each band keeps only the poles within 35 Hz of its centre: the bands tile, nothing is found twice. Two poles
    # at nearly one frequency are one partial with a two-stage decay, 551.4 Hz the strongest: keep both)
    top = max(d["a"] for d in modes)
    keep = [d for d in modes if d["a"] > top * 10 ** (-55 / 20) and d["a"] ** 2 * d["tau"] > top ** 2 * 1e-7]
    keep.sort(key=lambda d: d["f"])
    return keep


def strike_train(m, fs):
    """the eleven strikes from 25.7 s: their hits (the jump of the gong's own band, 200-2500 Hz: the click before a
    hit has little there), and how much each one adds (the energy just after minus just before: on average what the
    hammer gives, whatever the phases)"""
    b, a = sg.butter(4, [200 / (fs / 2), 2500 / (fs / 2)], "band")
    h = sg.filtfilt(b, a, m)
    env = np.sqrt(np.convolve(h ** 2, np.ones(48) / 48, "same"))
    approx = [25.58, 26.757, 27.94, 29.117, 30.29, 31.50, 32.70, 33.89, 35.09, 36.31, 37.515]   # (by eye, +-40 ms)
    e2 = np.convolve(m ** 2, np.ones(96) / 96, "valid")         # 2 ms energy, from each sample on
    e20 = np.convolve(m ** 2, np.ones(960) / 960, "valid")       # 20 ms energy
    hits = []
    for ap in approx:
        i = np.arange(int((ap - 0.04) * fs), int((ap + 0.04) * fs))
        r = e2[i] / (e20[i - 960] + 1e-9)                        # the next 2 ms against the 20 ms before
        hits.append(float(i[int(np.argmax(r))] / fs))
    gains = []
    for ht in hits:
        before = np.mean(h[int((ht - 0.06) * fs):int((ht - 0.01) * fs)] ** 2)
        after = np.mean(h[int((ht + 0.03) * fs):int((ht + 0.08) * fs)] ** 2)
        gains.append(max(after - before, 1e-12))
    return hits, gains


def tick_features(m, fs):
    b, a = sg.butter(4, 400 / (fs / 2), "high")
    h = sg.filtfilt(b, a, m)
    tock = [0.960, 2.052, 3.138, 4.221, 5.310, 6.399, 7.491, 8.578, 9.667, 10.757, 11.847, 12.937, 14.025, 15.111]
    tick = [0.364, 1.455, 2.546, 3.638, 4.727, 5.817, 6.913, 8.003, 9.090, 10.183, 11.274, 12.358, 13.444, 14.532]
    res = {}
    for name, ts in (("tick", tick), ("tock", tock)):
        onsets, E, P = [], [], 0
        for tc in ts:
            c = int(tc * fs)
            w = h[c - int(0.03 * fs):c + int(0.03 * fs)]
            o = c - int(0.03 * fs) + int(np.argmax(np.abs(w) > 0.3 * np.abs(w).max()))
            onsets.append(o / fs)
            E.append(band_energies(h, fs, o / fs, TICK_WIN))
            s = h[o - int(0.002 * fs):o + int(0.040 * fs)]
            P = P + np.abs(np.fft.rfft(s * np.hanning(len(s)), 8192)) ** 2
        E = 10 * np.log10(np.mean(10 ** (np.array(E) / 10), axis=0))
        f = np.fft.rfftfreq(8192, 1 / fs)
        Pdb = 10 * np.log10(P / len(ts) + 1e-20)
        # its decay per octave band: rms in 1 ms steps, averaged over the ticks, slope from the peak down 20 dB
        dec = []
        for lo in (500, 1000, 2000, 4000, 8000):
            bb, aa = sg.butter(2, [lo / (fs / 2), min(2 * lo, 15000) / (fs / 2)], "band")
            hb = sg.filtfilt(bb, aa, h)
            env = 0
            for o in onsets:
                seg = hb[int(o * fs) - int(0.002 * fs):int(o * fs) + int(0.06 * fs)]
                env = env + seg ** 2
            env = np.sqrt(np.convolve(env / len(onsets), np.ones(48) / 48, "same"))
            edb = 20 * np.log10(env + 1e-9)
            ip = int(np.argmax(edb))
            j = ip + int(np.argmax(edb[ip:] < edb[ip] - 20)) if np.any(edb[ip:] < edb[ip] - 20) else len(edb) - 1
            tau = (j - ip) / fs / np.log(10)                   # 20 dB = ln(10) amplitude time constants
            dec.append(dict(band=lo, tau=float(tau), peak=float(edb[ip])))
        # the spectrum's peaks above 800 Hz (the escapement's ringing): f, level
        sm = np.convolve(Pdb, np.ones(3) / 3, "same")
        pk, _ = sg.find_peaks(sm, prominence=3, distance=8)
        pk = [p for p in pk if 800 < f[p] < 15000]
        peaks = sorted(((float(f[p]), float(sm[p])) for p in pk), key=lambda v: -v[1])[:40]
        # the spectral envelope (third octaves) of the whole tick, for the noise part
        env3 = []
        for lo, hi in zip(BANDS[:-1], BANDS[1:]):
            sel = (f >= lo) & (f < hi)
            env3.append(float(10 * np.log10(np.mean(10 ** (Pdb[sel] / 10)) + 1e-20)))
        res[name] = dict(onsets=onsets, bands=E.tolist(), decay=dec, peaks=peaks, envelope=env3,
                         peak_level=float(np.mean([np.abs(h[int(o * fs):int((o + 0.02) * fs)]).max() for o in onsets])))
    return res


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        return 2
    fs, x = wavfile.read(sys.argv[1])
    m = x.astype(float) / 32768
    if m.ndim > 1:
        m = m.mean(axis=1)
    hit = find_hit(m, fs, 15.64, 15.70)
    click = find_hit(m, fs, 15.60, 15.64, 0.02)
    modes = gong_modes(m, fs, hit)
    hits, gains = strike_train(m, fs)
    ticks = tick_features(m, fs)
    noise = band_energies(m, fs, 15.30, [(0.0, 0.2)])[0]       # between two ticks, before the strike
    gates = tick_gates(m, fs, hit, GONG_WIN[-1][1])
    gong = band_energies(m, fs, hit, GONG_WIN, gates)
    model = dict(fs=fs, hit=hit, click_before=hit - click, clicks_before_train=[0.044, 0.041, 0.048, 0.045, 0.040], modes=modes,
                 train=dict(hits=hits, interval=float(np.mean(np.diff(hits))),
                            gains=[float(np.sqrt(g / gains[0])) for g in gains]),
                 ticks={k: {kk: vv for kk, vv in v.items() if kk != "bands"} for k, v in ticks.items()})
    feats = dict(bands=BANDS, gong_windows=GONG_WIN, gong_gates=gates, tick_windows=TICK_WIN, gong=gong.tolist(),
                 noise=noise.tolist(),
                 tick=ticks["tick"]["bands"], tock=ticks["tock"]["bands"])
    (ROOT / "tools" / "ref_model.json").write_text(json.dumps(model, indent=1) + "\n")
    (ROOT / "tests" / "ref").mkdir(parents=True, exist_ok=True)
    (ROOT / "tests" / "ref" / "features.json").write_text(json.dumps(feats, indent=1) + "\n")
    print(f"ticks inside the decay (left out of the features): {[round(a + 0.004, 3) for a, _ in gates]}")
    print(f"hit {hit:.4f} s (click {1000 * (hit - click):.1f} ms before), {len(modes)} modes, "
          f"train interval {model['train']['interval']:.3f} s, gains {[round(g, 2) for g in model['train']['gains']]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
