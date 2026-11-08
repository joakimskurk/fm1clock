#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Clicks measured and fitted at 1/12 of an octave (the cuckoo clock's tick, its warning, its door, its bird):
tools/analyze_cuckoo.py measures, tools/fit_cuckoo.py fits, tests/clk/parity.py checks.

A third of an octave was too coarse for a click: the fit could put a band's energy on one sine anywhere in it and
leave the rest empty, and the cuckoo's tick, whose strongest part is a broad 1.1-1.3 kHz, came out as a few pitched
pings with holes 25-48 dB deep between them. Here every twelfth of an octave from 300 Hz to 16 kHz is measured on
its own: the click's mean power in it over time windows (the recording band-passed by FFT round each click, so a
band is a band), less the same just before the click (the room, the running train, a ringing gong).

The fit gives each fine band one operator at its centre (the engine moves each a little, at random, every time the
click sounds, so it fills its band and no two clicks are alike), its decay chosen from a grid to follow the band's
energy over the windows (in dB), then all the levels together against each operator's own template (rendered, as
the engine plays it), Itakura-Saito: by ratio, so a quiet tail counts as the loud start.
"""
import numpy as np

FS = 44100
WINDOWS = [(-0.002, 0.003), (0.003, 0.008), (0.008, 0.015), (0.015, 0.025), (0.025, 0.040), (0.040, 0.060),
           (0.060, 0.090), (0.090, 0.130)]
TAUS = [0.0008, 0.0012, 0.0018, 0.0027, 0.004, 0.006, 0.009, 0.013, 0.019, 0.028, 0.04, 0.056, 0.08, 0.115, 0.16]
JITTER = 0.03                   # each operator's frequency, every time: +- 3 % (the engine: clk_engine.h)


def edges(lo=300.0, hi=16000.0):
    k = int(np.floor(12 * np.log2(hi / lo)))
    return [lo * 2 ** (i / 12) for i in range(k + 1)]


def band_env(x, fs, ons, wins=WINDOWS, ed=None, quiet=(-0.060, -0.035), span=(0.2, 0.3)):
    """mean power per window per fine band (windows x bands), over the clicks at ons; and the same over the quiet
    stretch before each (its floor: bands)"""
    ed = ed or edges()
    E, N = 0, 0
    for o in ons:
        i0 = int((o - span[0]) * fs)
        seg = np.asarray(x[max(i0, 0):int((o + span[1]) * fs)], dtype=float)
        if i0 < 0:
            seg = np.concatenate([np.zeros(-i0), seg])
        n = len(seg)
        X = np.fft.rfft(seg)
        f = np.fft.rfftfreq(n, 1 / fs)
        e = np.zeros((len(wins), len(ed) - 1))
        nz = np.zeros(len(ed) - 1)
        for b, (lo, hi) in enumerate(zip(ed[:-1], ed[1:])):
            Y = np.where((f >= lo) & (f < hi), X, 0)
            y = np.fft.irfft(Y, n) ** 2
            for w, (a, bb) in enumerate(wins):
                e[w, b] = np.mean(y[int((span[0] + a) * fs):int((span[0] + bb) * fs)])
            nz[b] = np.mean(y[int((span[0] + quiet[0]) * fs):int((span[0] + quiet[1]) * fs)])
        E, N = E + e, N + nz
    return E / len(ons), N / len(ons)


def render(ops, ta, n, fs=FS, rng=None, jitter=JITTER):
    """one click as the engine plays it: each operator a random phase, its frequency +- jitter, its level as given"""
    rng = rng or np.random.default_rng(0)
    t = np.arange(n) / fs
    att = 1 - np.exp(-t / ta)
    y = np.zeros(n)
    for d in ops:
        f = d["f"] * (1 + rng.uniform(-jitter, jitter))
        y += d["a"] * att * np.exp(-t / d["tau"]) * np.sin(2 * np.pi * f * t + rng.uniform(0, 2 * np.pi))
    return y


def fit(E, N, lo=300.0, ta=0.001, wins=WINDOWS, ed=None, nops=64, seeds=6, iters=300, taus=None, hi=16000.0):
    """at most nops operators for a click whose fine-band power over the windows is E (N its floor). One at each
    band's centre from lo on (its decay from the grid); the ones left over to the bands that a second decay helps
    the most (each band's two from the grid, least squares); then all the levels together"""
    ed = ed or edges()
    nb = len(ed) - 1
    centres = np.sqrt(np.array(ed[:-1]) * np.array(ed[1:]))
    n_used = int(np.sum([(lo <= centres[b] <= hi) and ((E[:, b] > 2 * N[b]).sum() >= 1) for b in range(nb)]))
    extra = max(nops - n_used, 0)
    tgt = np.clip(E - N[None, :], 0, None)
    W = (E > 2 * N[None, :]).astype(float) * ((centres >= lo) & (centres <= hi))[None, :]
    nbw = W.sum(axis=1)                              # a window with few bands over the floor (the tail) counts as
    W *= np.sqrt(nbw.max() / np.maximum(nbw, 1))[:, None]   # much as one with many (the start)
    t_ = np.arange(int(0.3 * FS)) / FS
    att = 1 - np.exp(-t_ / ta)

    def shape(tau):                                  # an operator's mean power per window (alone in its band)
        p = (att * np.exp(-t_ / tau)) ** 2 / 2
        return np.array([np.mean(p[max(int(a * FS), 0):int(b * FS)]) if b > 0 else 0.0 for a, b in wins])
    TAUS_ = taus or TAUS
    S = {tau: shape(tau) for tau in TAUS_}
    single, double = {}, {}
    for b in range(nb):
        sel = W[:, b] > 0
        if centres[b] < lo or centres[b] > hi or sel.sum() < 1:
            continue
        best = None
        for tau in TAUS_:                            # one decay: the best fit in dB over the windows that count
            s_ = S[tau]
            k = np.exp(np.mean(np.log(tgt[sel, b] + 1e-30) - np.log(s_[sel] + 1e-30)))
            err = np.sum((np.log(k * s_[sel] + 1e-30) - np.log(tgt[sel, b] + 1e-30)) ** 2)
            if best is None or err < best[0]:
                best = (err, tau, k)
        single[b] = best
        if sel.sum() >= 3:                           # two (it falls fast, then rings on): least squares, weighted
            wt = 1 / (tgt[sel, b] + 1e-30)           # by 1 / target (as in dB), both levels >= 0
            best2 = None
            for i, ts in enumerate(TAUS_):
                for tl in TAUS_[i + 1:]:
                    A = np.stack([S[ts][sel], S[tl][sel]], axis=1) * wt[:, None]
                    x, *_ = np.linalg.lstsq(A, tgt[sel, b] * wt, rcond=None)
                    if np.all(x > 0):
                        pred = S[ts][sel] * x[0] + S[tl][sel] * x[1]
                        err = np.sum((np.log(pred + 1e-30) - np.log(tgt[sel, b] + 1e-30)) ** 2)
                        if best2 is None or err < best2[0]:
                            best2 = (err, ts, tl, x)
            if best2:
                double[b] = best2
    # one operator a band; the spare ones to the bands a second decay helps the most
    gain = sorted(double, key=lambda b: -(single[b][0] - double[b][0]))[:extra]
    ops = []
    for b, (_, tau, k) in single.items():
        if b in gain:
            _, ts, tl, x = double[b]
            ops.append(dict(f=float(centres[b]) * 2 ** (-1 / 48), tau=float(ts), a=float(np.sqrt(x[0])), band=b))
            ops.append(dict(f=float(centres[b]) * 2 ** (1 / 48), tau=float(tl), a=float(np.sqrt(x[1])), band=b))
        else:
            ops.append(dict(f=float(centres[b]), tau=float(tau), a=float(np.sqrt(k)), band=b))
    # the levels all together, each operator's own template (rendered, measured as the recording was)
    T = []
    for d in ops:
        acc = 0
        for s_ in range(seeds):
            y = render([dict(d, a=1.0)], ta, int(0.3 * FS), rng=np.random.default_rng(1000 + s_))
            acc = acc + band_env(np.concatenate([np.zeros(int(0.2 * FS)), y]), FS, [0.2], wins, ed)[0]
        T.append(acc / seeds)
    T = np.array(T)                                  # ops x windows x bands
    pw = np.array([d["a"] ** 2 for d in ops])
    for _ in range(iters):                           # Itakura-Saito multiplicative updates
        P = np.einsum("k,kwb->wb", pw, T) + 1e-30
        num = np.einsum("kwb,wb->k", T, W * tgt / P ** 2)
        den = np.einsum("kwb,wb->k", T, W / P) + 1e-40
        pw *= np.sqrt(num / den)
    for d, p in zip(ops, pw):
        d["a"] = float(np.sqrt(p))
        d.pop("band")
    P = np.einsum("k,kwb->wb", pw, T)
    sel = W > 0
    err = float(np.sqrt(np.mean((10 * np.log10((P[sel] + 1e-30) / (tgt[sel] + 1e-30))) ** 2)))
    return ops, err


def compare(E_syn, E, N, lo=300.0, ed=None, hi=16000.0):
    """the synth's fine-band power against the recording's, per window: rms dB over the bands 6 dB over the floor"""
    ed = ed or edges()
    centres = np.sqrt(np.array(ed[:-1]) * np.array(ed[1:]))
    out = []
    for w in range(E.shape[0]):
        sel = (E[w] > 4 * N) & (centres >= lo) & (centres <= hi)
        tgt = np.clip(E[w] - N, 1e-30, None)
        d = 10 * np.log10((E_syn[w][sel] + 1e-30) / tgt[sel])
        out.append((float(np.sqrt(np.mean(d ** 2))) if sel.any() else 0.0, float(np.mean(d)) if sel.any() else 0.0,
                    int(sel.sum())))
    return out


def refine(parts, E, N, ta=0.001, lo=300.0, wins=WINDOWS, ed=None, seeds=6, iters=400, hi=13500.0):
    """several sounds that make one click together (parts: [(ops, delay s)], e.g. a door's latch and, 13 ms on, the
    door to its stop): all their levels at once against the click's fine-band power E (N its floor), each operator's
    template rendered at its own delay. Changes the ops' levels; returns the rms dB error"""
    ed = ed or edges()
    centres = np.sqrt(np.array(ed[:-1]) * np.array(ed[1:]))
    tgt = np.clip(E - N[None, :], 0, None)
    W = (E > 2 * N[None, :]).astype(float) * ((centres >= lo) & (centres <= hi))[None, :]
    flat, T = [], []
    for ops, delay in parts:
        for d in ops:
            acc = 0
            for s_ in range(seeds):
                y = render([dict(d, a=1.0)], ta, int(0.3 * FS), rng=np.random.default_rng(3000 + s_))
                z = np.concatenate([np.zeros(int((0.2 + delay) * FS)), y])
                acc = acc + band_env(z, FS, [0.2], wins, ed)[0]
            T.append(acc / seeds)
            flat.append(d)
    T = np.array(T)
    pw = np.array([d["a"] ** 2 for d in flat]) + 1e-30
    for _ in range(iters):
        P = np.einsum("k,kwb->wb", pw, T) + 1e-30
        num = np.einsum("kwb,wb->k", T, W * tgt / P ** 2)
        den = np.einsum("kwb,wb->k", T, W / P) + 1e-40
        pw *= np.sqrt(num / den)
    for d, p in zip(flat, pw):
        d["a"] = float(np.sqrt(p))
    P = np.einsum("k,kwb->wb", pw, T)
    sel = W > 0
    return float(np.sqrt(np.mean((10 * np.log10((P[sel] + 1e-30) / (tgt[sel] + 1e-30))) ** 2)))
