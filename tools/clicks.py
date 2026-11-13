#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
# Copyright (C) 2026 Joakim (joakimskurk)
"""The cuckoo clock's clicks (its tick, its train's warning, its door opening, its door shutting): measured, fitted
and checked here; tools/analyze_cuckoo.py measures, tools/fit_cuckoo.py fits, tests/clk/parity.py checks.

A click is not a chord. Side by side, waveform and spectrogram, the recording's tick is a crack and a burst of noise:
held against the next tick, sample by sample, only half of its first 2 ms at 3-8 kHz comes back the same (the
escapement's crack), and after 5 ms next to nothing does, at any frequency. The rest is noise, different every time,
and dies away. An earlier fit gave every twelfth of an octave one sine with its own decay, right in energy band by
band, and it rang: steady tones at 0.6, 1.2, 2.0 and 2.1 kHz for 160 ms, a resonator, a small bell. So a click here
is two things:

  * what comes back every time, played the same every time, phase and all: the tick's crack and its case's
    knock, its modes from the ticks averaged sample by sample, by matrix pencil, frequency, decay, level and phase
    (modes()); the door's wood, struck three times in 20 ms (its tok at 1.2-1.4 kHz and 4-5 kHz), damped sines
    each starting on its own step from nothing, picked by matching pursuit on the one door there is (strikes());
  * the rest, noise: operators that each fill a band of noise instead of a line. Each takes a new frequency in
    its band every P steps of the engine's 16 frames, phase unbroken, P about one over its band's width (its
    sound changes as fast as noise that wide does). Their levels are fitted to the click's power over time
    in two grids at once: in eighths of an octave over 8 windows (its colour), and in octaves over 1 ms
    windows (its time: the crack's rise, how it dies) (fit()).

An operator can start late, on its own step (up to 25 ms in): the door's blows, the tick's rattle after its crack.
The power is measured through smooth bands (cosine squared on a log axis, each half overlapping the next), so a band
does not ring for long the way a brick-wall one does: on the recording and on the engine's own operators,
rendered as it plays them (render()), the same way. The fit's error is squared in dB (too loud as bad as too quiet),
every window and band counting as far as it stands over the floor (the quiet before the click), the floor in both
the recording and the model; how much like noise each is, its spectral flatness, is checked beside it (flatness()).
"""
import numpy as np

FS = 44100
SUB = 16                                        # (the engine's step, CLK_SUB frames: an operator's hop is a number of
                                                # them)


def centres(lo, hi, step):
    k = int(np.floor(np.log2(hi / lo) / step + 1e-9))
    return [lo * 2 ** (i * step) for i in range(k + 1)]


T0_TICK = -0.0008                               # the tick starts this long before its onset (its crack's rise)
T0_CLICK = -0.0003                              # the other clicks
TA = 0.00015                                    # their rise, 1 - exp(-t / TA)
RISE = 0.001                                    # (a window counts once it ends this long after the sound starts)
W_FINE = [(-0.001, 0.002), (0.002, 0.005), (0.005, 0.010), (0.010, 0.018), (0.018, 0.030), (0.030, 0.050),
          (0.050, 0.080), (0.080, 0.130)]
W_TIME = [(-0.002, -0.001), (-0.001, 0.0)] + [(i / 1000, (i + 1) / 1000) for i in range(12)] + \
         [(a / 1000, b / 1000) for a, b in [(12, 15), (15, 19), (19, 24), (24, 30), (30, 38), (38, 48), (48, 60),
                                            (60, 76), (76, 96), (96, 120)]]
FINE = dict(name="fine", centres=centres(300.0, 16000.0, 1 / 8), step=1 / 8, wins=W_FINE)   # its colour
TIME = dict(name="time", centres=centres(350.0, 11200.0, 1.0), step=1.0, wins=W_TIME)        # its time
GRIDS = (FINE, TIME)
TAUS = [0.0007, 0.0014, 0.0028, 0.0056, 0.011, 0.022, 0.040, 0.080]   # a noise operator's decay


def resp(f, c, step):
    """a band's magnitude: cos^2 over log frequency, zero one step either side of its centre c"""
    u = np.log2(np.maximum(f, 1e-6) / c) / step
    return np.where(np.abs(u) < 1, np.cos(np.pi / 2 * u) ** 2, 0.0)


def tf_env(x, fs, ons, grid, quiet=(-0.060, -0.035), span=(0.2, 0.3)):
    """mean power per window per band of grid (windows x bands), over the clicks at ons (s); and the same over the
    quiet stretch before each, its floor (bands)"""
    cs, step, wins = grid["centres"], grid["step"], grid["wins"]
    E, N = 0, 0
    for o in ons:
        i0 = int(round((o - span[0]) * fs))
        seg = np.asarray(x[max(i0, 0):i0 + int(round((span[0] + span[1]) * fs))], dtype=float)
        if i0 < 0:
            seg = np.concatenate([np.zeros(-i0), seg])
        n = len(seg)
        X = np.fft.rfft(seg)
        f = np.fft.rfftfreq(n, 1 / fs)
        e = np.zeros((len(wins), len(cs)))
        nz = np.zeros(len(cs))
        for b, c in enumerate(cs):
            y = np.fft.irfft(X * resp(f, c, step), n) ** 2
            for w, (a, bb) in enumerate(wins):
                e[w, b] = np.mean(y[int(round((span[0] + a) * fs)):int(round((span[0] + bb) * fs))])
            if quiet is not None:
                nz[b] = np.mean(y[int(round((span[0] + quiet[0]) * fs)):int(round((span[0] + quiet[1]) * fs))])
        E, N = E + e, N + nz
    return E / len(ons), N / len(ons)


def measure(x, fs, ons, quiet=(-0.060, -0.035)):
    """a click's power in both grids: {grid: (E, N)}"""
    return {g["name"]: tf_env(x, fs, ons, g, quiet) for g in GRIDS}


def hop_of(f, step=1 / 8):
    """a noise operator at f, an eighth of an octave wide: how far it may stray (Hz) and every how many steps of SUB
    frames it takes another frequency (a power of two, about one over its band's width)"""
    B = f * (2 ** (step / 2) - 2 ** (-step / 2))
    P = 2 ** int(np.clip(np.round(np.log2(FS / B / SUB)), 0, 10))
    return f * (2 ** (step / 2) - 1), P


def render(det, noise, n, ta, rng=None, fs=FS, levrand=True):
    """one click as the engine plays it (firmware/src/clk_engine.h, eng_tick, tick_render): the modes det
    [dict(f, tau, a, phi)] the same every time; the noise operators [dict(f, tau, a, d, P, dly)] each from a random
    phase, a random frequency within +-d of f, another every P steps of SUB frames (staggered by its place k), its
    level 0.88 .. 1.12 of a, from dly steps on; all under the bank's rise 1 - exp(-t/ta)"""
    rng = rng or np.random.default_rng(0)
    t = np.arange(n) / fs
    att = 1 - np.exp(-t / ta)
    y = np.zeros(n)
    for m in det:                               # (from dly steps on, its phase running from the start)
        i0 = int(m.get("dly", 0)) * SUB
        y[i0:] += m["a"] * att[i0:] * np.exp(-t[:n - i0] / m["tau"]) * np.sin(2 * np.pi * m["f"] * t[i0:] + m["phi"])
    nsub = (n + SUB - 1) // SUB
    s = np.arange(nsub)
    for k, m in enumerate(noise):
        P = int(m["P"])
        draws = m["f"] + rng.uniform(-m["d"], m["d"], nsub)
        hop = ((s + k) % P == 0) | (s == 0)
        fr = draws[np.maximum.accumulate(np.where(hop, s, 0))]
        ph = rng.uniform(0, 2 * np.pi) + 2 * np.pi * np.cumsum(np.repeat(fr, SUB)[:n]) / fs
        g = m["a"] * (rng.uniform(0.88, 1.12) if levrand else 1.0)
        i0 = int(m.get("dly", 0)) * SUB
        if 0 < i0 < n:                          # (one that comes later starts from nothing, up or down)
            ph = ph - ph[i0] + (np.pi if rng.uniform() < 0.5 else 0.0)
        if i0 < n:
            y[i0:] += g * att[i0:] * np.exp(-t[:n - i0] / m["tau"]) * np.sin(ph[i0:])
    return y


def align(x, fs, ons, ref=0, lo=1500.0, hi=16000.0, a=-0.005, b=0.03, reach=60):
    """the onsets ons (s) moved, each by up to reach samples, to line up best with ons[ref] above lo Hz; and how well
    each then does (correlation)"""
    def band(i):
        s = np.asarray(x[i + int(a * fs):i + int(b * fs)], dtype=float)
        n = len(s)
        f = np.fft.rfftfreq(n, 1 / fs)
        return np.fft.irfft(np.fft.rfft(s) * ((f >= lo) & (f < hi)), n)
    oi = [int(round(o * fs)) for o in ons]
    r = band(oi[ref])
    out, cor = [], []
    for i in oi:
        best = max((float(np.dot(s, r) / np.sqrt(np.dot(s, s) * np.dot(r, r) + 1e-30)), d)
                   for d in range(-reach, reach + 1) for s in [band(i + d)])
        out.append((i + best[1]) / fs)
        cor.append(best[0])
    return out, cor


def coherent(x, fs, ons, lead=0.02, span=0.13):
    """the clicks at ons averaged sample by sample (what comes back every time), from lead s before each"""
    oi = [int(round(o * fs)) for o in ons]
    return np.mean([np.asarray(x[i - int(lead * fs):i + int(span * fs)], dtype=float) for i in oi], axis=0)


def matrix_pencil(y, order_max, dt):
    """damped complex exponentials in y (complex): [(z, amp)], z = exp((-a + jw) dt)"""
    n = len(y)
    L = n // 3
    Y = np.array([y[i:i + L + 1] for i in range(n - L)])
    _, s, Vh = np.linalg.svd(Y, full_matrices=False)
    M = int(min(order_max, np.sum(s > s[0] * 10 ** (-45 / 20))))
    if M < 1:
        return []
    V = Vh[:M].T
    z = np.linalg.eigvals(np.linalg.pinv(V[:-1]) @ V[1:])
    amp, *_ = np.linalg.lstsq(np.vander(z, n, increasing=True).T, y, rcond=None)
    return list(zip(z, amp))


def modes(ca, fs, lead, lo, hi, t0, t1, order, ta, tau_max=0.025):
    """the modes of the average ca (lead s of it before the onset) in lo..hi Hz, from t0 to t1 s after the onset:
    matrix pencil on the band as an analytic signal, then frequencies and decays refined together (their levels and
    phases by least squares) on the band itself, under the bank's rise from t0 (the sound starts there).
    [dict(f, tau, a, phi)]: a sin(2 pi f t + phi) exp(-t/tau), t from t0"""
    from scipy.optimize import least_squares
    n = len(ca)
    X = np.fft.fft(ca)
    f = np.fft.fftfreq(n, 1 / fs)
    X[(f < lo) | (f > hi)] = 0
    za = np.fft.ifft(X) * 2
    i0, i1 = int(round((lead + t0) * fs)), int(round((lead + t1) * fs))
    init = []
    for z, _ in matrix_pencil(za[i0:i1], order, 1 / fs):
        fr, al = np.angle(z) * fs / (2 * np.pi), -np.log(abs(z)) * fs
        if lo <= fr <= hi and al > 0:
            init.append([fr, min(max(1 / al, 0.0002), tau_max)])
    if not init:
        return []
    y = np.real(za[i0:i1])
    t = np.arange(i1 - i0) / fs
    att = 1 - np.exp(-t / ta)

    def basis(p):
        cols = []
        for k in range(len(p) // 2):
            e = att * np.exp(-t / p[2 * k + 1])
            cols += [e * np.cos(2 * np.pi * p[2 * k] * t), e * np.sin(2 * np.pi * p[2 * k] * t)]
        return np.array(cols).T

    def resid(p):
        A = basis(p)
        c, *_ = np.linalg.lstsq(A, y, rcond=None)
        return A @ c - y
    p0 = np.array(init).ravel()
    lb = np.ravel([[lo, 0.0002]] * len(init))
    ub = np.ravel([[hi, tau_max]] * len(init))
    sol = least_squares(resid, np.clip(p0, lb + 1e-9, ub - 1e-9), bounds=(lb, ub))
    A = basis(sol.x)
    c, *_ = np.linalg.lstsq(A, y, rcond=None)
    out = []
    for k in range(len(sol.x) // 2):
        ac, as_ = c[2 * k], c[2 * k + 1]              # ac cos + as sin = a sin(w t + phi)
        out.append(dict(f=float(sol.x[2 * k]), tau=float(sol.x[2 * k + 1]), a=float(np.hypot(ac, as_)),
                        phi=float(np.arctan2(ac, as_))))
    return sorted(out, key=lambda d: -d["a"] ** 2 * d["tau"])


def strikes(x, fs, on, t0, ta, lo, hi, n=6, taus=(0.002, 0.003, 0.0045, 0.0065, 0.009, 0.013), starts=90,
            span=0.06, df=4.0):
    """a resonance struck again and again in one click (the door's wood, its tok): in lo..hi Hz of the click at on
    (s), damped sines that each start on a step of SUB frames (the first starts with the sound, t0 s before on),
    their phases running from the sound's start, picked one by one as they explain the most of what is left
    (orthogonal matching pursuit), frequencies every df Hz: [dict(f, tau, a, phi, dly)], and what is left of the
    band (its energy, 0..1)"""
    seg = np.asarray(x[int(round((on - 0.1) * fs)):int(round((on + 0.2) * fs))], dtype=float)
    m_ = len(seg)
    f_ = np.fft.rfftfreq(m_, 1 / fs)
    y = np.fft.irfft(np.fft.rfft(seg) * ((f_ >= lo) & (f_ <= hi)), m_)
    i0 = int(round((0.1 + t0) * fs))
    y = y[i0:i0 + int(span * fs)]
    L = len(y)
    t = np.arange(L) / fs
    att = 1 - np.exp(-t / ta)
    st = np.array([int(round(dl * SUB * fs / FS)) for dl in range(starts)])   # (the steps at the recording's rate)

    def atom(fr, tau, dl):                      # (from nothing: a struck resonance starts at rest, moving)
        td = dl * SUB / FS
        u = np.maximum(t - td, 0)
        return (np.where(t >= td, att * np.exp(-u / tau), 0.0) * np.sin(2 * np.pi * fr * u))[:, None]
    picked, r = [], y.copy()
    nfft = 1 << int(np.ceil(np.log2(2 * L)))
    for _ in range(n):
        R = np.fft.fft(r, nfft)
        best = None
        for tau in taus:
            env = np.exp(-t / tau)
            nrm = 0.5 * np.cumsum(env ** 2)[L - 1 - st]     # (an atom's energy, cut where the click's span ends)
            for fr in np.arange(lo, hi, df):
                g = env * np.exp(2j * np.pi * fr * t)
                c = np.fft.ifft(R * np.conj(np.fft.fft(g, nfft)))[:L]   # sum_t r(t) conj(g(t - td)), every td:
                sc = np.imag(c[st]) ** 2 / (nrm + 1e-30)                # its sine part
                j = int(np.argmax(sc))
                if best is None or sc[j] > best[0]:
                    best = (sc[j], fr, tau, j)
        picked.append(best[1:])
        B = np.concatenate([atom(*k) for k in picked], axis=1)
        cf, *_ = np.linalg.lstsq(B, y, rcond=None)
        r = y - B @ cf
    out = []
    for i, (fr, tau, dl) in enumerate(picked):          # a sin(w (t - td)): its phase from the sound's start
        out.append(dict(f=float(fr), tau=float(tau), a=float(abs(cf[i])),
                        phi=float((-2 * np.pi * fr * dl * SUB / FS + (np.pi if cf[i] < 0 else 0.0)) % (2 * np.pi)),
                        dly=int(dl)))
    return out, float(np.sum(r ** 2) / np.sum(y ** 2))


def analyse(y, t0, delay=0.0):
    """a rendered sound in both grids, as the recording is measured: the sound starts t0 s (<= 0) before the
    click's onset, delay s after it"""
    z = np.concatenate([np.zeros(int(round((0.05 + delay) * FS))), y])
    return {g["name"]: tf_env(z, FS, [0.05 - t0], g, None, span=(0.05, 0.25))[0] for g in GRIDS}


DEC = 4                                         # (an operator's power over time, kept every DEC frames)
LEAD = 0.05                                     # (from this long before its start: the bands smear it)


def series(m, ta, seeds):
    """an operator's power through every band of both grids over time, mean over seeds renderings, every DEC frames
    from LEAD s before it starts: {grid: bands x frames}, cumulative (a window's mean is a difference)"""
    n = int(0.40 * FS)
    out = {}
    acc = {g["name"]: 0 for g in GRIDS}
    for s_ in range(seeds):
        y = render([], [dict(m, dly=0)], n, ta, rng=np.random.default_rng(100 + s_), levrand=False)
        z = np.concatenate([np.zeros(int(LEAD * FS)), y])
        X = np.fft.rfft(z)
        f = np.fft.rfftfreq(len(z), 1 / FS)
        for g in GRIDS:
            P = np.array([np.fft.irfft(X * resp(f, c, g["step"]), len(z)) ** 2 for c in g["centres"]])
            acc[g["name"]] = acc[g["name"]] + P[:, :P.shape[1] // DEC * DEC].reshape(len(g["centres"]), -1, DEC).sum(2)
    for g in GRIDS:
        out[g["name"]] = np.concatenate([np.zeros((len(g["centres"]), 1)), np.cumsum(acc[g["name"]] / seeds, axis=1)],
                                        axis=1)
    return out


def windowed(cs, wins, start):
    """an operator's mean power per window and band (windows x bands), from its cumulative series cs, the operator
    starting start s after the click's onset"""
    out = np.zeros((len(wins), cs.shape[0]))
    for w, (a, b) in enumerate(wins):
        ia = int(round((a - start + LEAD) * FS / DEC))
        ib = int(round((b - start + LEAD) * FS / DEC))
        ia, ib = np.clip([ia, ib], 0, cs.shape[1] - 1)
        out[w] = (cs[:, ib] - cs[:, ia]) / max((b - a) * FS, 1)
    return out


def weights(E, N, cs, lo, hi, last=1.0, wins=None):
    """how much each window and band counts: as far as it stands over the floor (none at all under 1.5 x it, fully
    from 4 x), in lo..hi Hz, before last s; each grid in all as much as the other"""
    snr = (E - N[None, :]) / (N[None, :] + 1e-30)
    w = np.clip((snr - 0.5) / 2.5, 0, 1) * ((np.array(cs) >= lo) & (np.array(cs) <= hi))[None, :]
    if wins is not None:
        w *= (np.array([a for a, _ in wins]) < last)[:, None]
    return w / max(w.sum(), 1e-12)


DELAYS = [0, 1, 2, 3, 4, 6, 8, 11, 16, 22, 32, 45]
NARROW_TAU = 0.011                              # (a narrow band of noise that lasts is a whistle: what rings longer is
                                                # half an octave wide)   # a noise operator's start, steps of SUB frames (to 16 ms)


def fit(meas, det, t0, ta, nops=68, lo=400.0, hi=16000.0, last=1.0, taus=TAUS, delays=DELAYS, widths=(1 / 8, 1 / 2),
        seeds=6, iters=600, verbose=True):
    """at most nops noise operators for a click measured as meas ({grid: (E, N)}), over its modes det (played as
    they are), the sound starting t0 s before the click's onset: candidates in every eighth of an octave from lo to
    hi, eighth of an octave or half wide (the long decays only half: a narrow band that lasts is a whistle), each
    decay of taus, each start of delays; all their levels together (squared error in dB, L-BFGS on their logs),
    then the least used dropped a third of the excess at a time (the rest fitted again) down to nops.
    Returns [noise ops], {grid: (rms dB, mean dB)}"""
    names = [g["name"] for g in GRIDS]
    V = {g: np.clip(meas[g][0] - meas[g][1][None, :], 0, None) for g in names}
    Wt = {g["name"]: weights(meas[g["name"]][0], meas[g["name"]][1], g["centres"], lo, hi, last, g["wins"])
          for g in GRIDS}
    for g in GRIDS:                             # (no say for a window over within 1 ms of the sound's start: its
        Wt[g["name"]] *= (np.array([b for _, b in g["wins"]]) >= t0 + RISE)[:, None]   # rise, the modes' alone)
        Wt[g["name"]] /= max(Wt[g["name"]].sum(), 1e-12)
    D = analyse(render(det, [], int(0.35 * FS), ta), t0) if det else {g: 0.0 for g in names}
    for g in names:                             # (the floor is in both: the recording's power against the model's
        D[g] = D[g] + meas[g][1][None, :]       # and its floor, so what the floor explains pulls on no operator)
        V[g] = meas[g][0]
    cands, T = [], {g: [] for g in names}
    for wd in widths:                           # (an eighth of an octave wide, or half: the long tails, broad noise)
        for c in FINE["centres"][::int(round(wd / FINE["step"])) // 2 or 1]:
            if not (lo <= c <= hi and c * 2 ** (-wd / 2) >= lo * 0.85):   # (none reaching under lo: the knock's
                continue                                                  # there)
            d_, P = hop_of(c, wd)
            for tau in [t for t in taus if wd > 0.2 or t <= NARROW_TAU]:
                m = dict(f=float(c), tau=float(tau), a=1.0, d=float(d_), P=int(P))
                cs = series(m, ta, seeds)
                for dl in delays:
                    cands.append(dict(m, dly=int(dl)))
                    for g in GRIDS:
                        T[g["name"]].append(windowed(cs[g["name"]], g["wins"], t0 + dl * SUB / FS))
    T = {g: np.array(T[g]) for g in names}

    from scipy.optimize import minimize

    def model(pw, g):
        return D[g] + np.einsum("k,kwb->wb", pw, T[g]) + 1e-30
    lV = {g: np.log(np.maximum(V[g], 1e-30)) for g in names}

    def loss(x, keep):                          # the squared error in dB (as the ear hears levels, both ways alike),
        pw = np.zeros(len(cands))               # over the levels' logarithms
        pw[keep] = np.exp(x)
        f, grad = 0.0, np.zeros(len(keep))
        for g in names:
            Pm = model(pw, g)
            e = np.log(Pm) - lV[g]
            f += np.sum(Wt[g] * e ** 2)
            grad += np.einsum("kwb,wb->k", T[g][keep], 2 * Wt[g] * e / Pm) * pw[keep]
        return f, grad

    def run(pw, keep, n):
        x0 = np.log(np.maximum(pw[keep], 1e-24))
        r = minimize(loss, x0, args=(keep,), jac=True, method="L-BFGS-B", bounds=[(-55.0, 0.0)] * len(keep),
                     options=dict(maxiter=n, ftol=1e-14, gtol=1e-12))
        pw = np.zeros(len(cands))
        pw[keep] = np.exp(r.x)
        return pw

    def use(pw):                                # how much of the click each explains, the cells weighted
        return sum(np.einsum("k,kwb,wb->k", pw, T[g], Wt[g] / model(pw, g)) for g in names)
    keep = np.arange(len(cands))                # (from all at one level, the best one)
    lv = min((loss(np.full(len(keep), v), keep)[0], v) for v in np.arange(-50.0, 0.0, 1.0))[1]
    pw = run(np.full(len(cands), np.exp(lv)), keep, iters)
    while len(keep) > nops:
        u = use(pw)
        drop = keep[np.argsort(u[keep])[:max(1, (len(keep) - nops) // 3)]]
        keep = np.setdiff1d(keep, drop)
        pw = run(pw, keep, 120)
    pw = run(pw, keep, iters)
    err = {}
    for g in names:                             # (the click itself: the floor off both)
        sel = Wt[g] > 0
        d = 10 * np.log10((model(pw, g) - meas[g][1][None, :])[sel] / np.maximum(V[g] - meas[g][1][None, :], 1e-30)[sel])
        w = Wt[g][sel]
        err[g] = (float(np.sqrt(np.sum(w * d ** 2) / np.sum(w))), float(np.sum(w * d) / np.sum(w)))
    out = [dict(cands[k], a=float(np.sqrt(pw[k]))) for k in keep]
    if verbose:
        print("    " + ", ".join(f"{g}: {e[0]:.2f} dB rms off (mean {e[1]:+.2f})" for g, e in err.items()))
    return sorted(out, key=lambda m: (m["dly"], m["f"])), err


def compare(syn, meas, lo=400.0, hi=16000.0, last=1.0):
    """the synth's power ({grid: E}) against the recording's ({grid: (E, N)}), per grid per window: (rms dB, mean
    dB, bands) over the bands that stand 4 x over the floor, lo..hi Hz"""
    out = {}
    for g in GRIDS:
        E, N = meas[g["name"]]
        cs = np.array(g["centres"])
        rows = []
        for w, (a, _) in enumerate(g["wins"]):
            sel = (E[w] > 4 * N) & (cs >= lo) & (cs <= hi)
            if a >= last or not sel.any():
                rows.append((0.0, 0.0, 0))
                continue
            d = 10 * np.log10((syn[g["name"]][w][sel] + 1e-30) / np.clip(E[w][sel] - N[sel], 1e-30, None))
            rows.append((float(np.sqrt(np.mean(d ** 2))), float(np.mean(d)), int(sel.sum())))
        out[g["name"]] = rows
    return out


def flatness(x, fs, ons, a, b, lo, hi):
    """how much like noise lo..hi Hz is from a to b s after each onset: the periodogram's geometric mean over its
    arithmetic mean, the clicks' mean (white noise about 0.56, a few steady tones near 0)"""
    out = []
    for o in ons:
        s = np.asarray(x[int(round((o + a) * fs)):int(round((o + b) * fs))], dtype=float)
        P = np.abs(np.fft.rfft(s * np.hanning(len(s)), 1 << 14)) ** 2
        f = np.fft.rfftfreq(1 << 14, 1 / fs)
        p = P[(f >= lo) & (f < hi)] + 1e-30
        out.append(np.exp(np.mean(np.log(p))) / np.mean(p))
    return float(np.mean(out))


def over_floor(x, fs, ons, a, b, lo, hi, quiet):
    """how far the clicks stand over their floor in lo..hi Hz from a to b s after each onset (dB, their mean power
    against the quiet stretch's)"""
    e, q = 0.0, 0.0
    for o in ons:
        s = np.asarray(x[int(round((o - 0.2) * fs)):int(round((o + 0.3) * fs))], dtype=float)
        f = np.fft.rfftfreq(len(s), 1 / fs)
        y = np.fft.irfft(np.fft.rfft(s) * ((f >= lo) & (f < hi)), len(s)) ** 2
        e += np.mean(y[int(round((0.2 + a) * fs)):int(round((0.2 + b) * fs))])
        q += np.mean(y[int(round((0.2 + quiet[0]) * fs)):int(round((0.2 + quiet[1]) * fs))])
    return float(10 * np.log10(max(e, 1e-30) / max(q, 1e-30)))
