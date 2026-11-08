#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Fit the clock's sound to the measurements of the reference (tools/ref_model.json, tests/ref/features.json, from
tools/analyze_ref.py) and write tools/clk_model.json, the model the firmware's tables are made from
(tools/gen_tables.py). Deterministic (fixed seeds); run it again when the analysis changes.

  python3 -I tools/fit_model.py            (numpy; ~1 min)

The gong: every mode of the fit is an FM carrier at its frequency, amplitude, decay and phase. The strongest K_FM
get a modulator each: its ratio to the carrier, its index at the hit and how fast the index falls, searched so the
first 100 ms (the hammer's hit) have the reference's band energies; the modulators move the energy of a mode into
its sidebands, the hit's brightness. The modes are ordered by their energy (a^2 tau): the firmware renders as many
of them, from the top, as the chip has time for.

The ticks: two banks of NT sine operators each (the escapement's two sounds, "tick" and "tock"), at the
spectrum's peaks and between them, with the decays measured per octave; their levels are fitted to the reference's
band energies over the first 60 ms. A tick starts each operator at a random phase, so no two ticks are alike.
"""
import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
from features import band_energies, BANDS  # noqa: E402

FS = 44100
K_FM = 32                   # carriers with a modulator
NT = 64                     # operators per tick bank
FM_RATIOS = [0.1, 0.17, 0.25, 1 / 3, 0.5, 0.7071, 1.0, 1.2599, 1.4142, 1.5, 2.0, 2.618, 3.1416]
FM_INDEX = [0.0, 0.3, 0.6, 1.0, 1.5, 2.2, 3.0]
FM_TAU = [0.004, 0.008, 0.015, 0.03, 0.06]
FM_BOOST = [0.0, 0.7, 1.5]                                     # the amplitude at the hit: x (1 + B e^(-t/tauI))


def gong_wave(modes, fm, T, t0=0.0):
    t = np.arange(int(T * FS)) / FS + t0
    y = np.zeros(len(t))
    for k, d in enumerate(modes):
        ph = 2 * np.pi * d["f"] * t + d["ph"]
        env = d["a"] * np.exp(-t / d["tau"])
        if k < len(fm) and (fm[k]["I"] > 0 or fm[k]["B"] > 0):
            e = np.exp(-t / fm[k]["tauI"])
            ph = ph + fm[k]["I"] * e * np.sin(2 * np.pi * fm[k]["r"] * d["f"] * t)
            env = env * (1 + fm[k]["B"] * e)
        y += env * np.cos(ph)
    return y


def fit_tails(modes, feats):
    """the pencil fit leans on the loud start: per third-octave band one stretch of its modes' decays, fitted to the
    reference's band energies from 100 ms to 5 s (each mode's energy in a window, in closed form)"""
    ref = np.array(feats["gong"]); noise = np.array(feats["noise"]); wins = feats["gong_windows"]
    rows = [w for w, (a, b) in enumerate(wins) if a >= 0.1]
    band = np.clip(np.searchsorted(BANDS, [d["f"] for d in modes]) - 1, 0, len(BANDS) - 2)

    def energy(sel, stretch):
        out = []
        for w in rows:
            t1, t2 = wins[w]
            e = 0.0
            for d in sel:
                tau = d["tau"] * stretch
                e += d["a"] ** 2 / 2 * tau / (2 * (t2 - t1)) * (np.exp(-2 * t1 / tau) - np.exp(-2 * t2 / tau))
            out.append(10 * np.log10(e + 1e-20))
        return np.array(out)

    changed = []
    for b in range(len(BANDS) - 1):
        sel = [d for d, bb in zip(modes, band) if bb == b]
        ok = np.array([ref[w, b] > noise[b] + 6 for w in rows])
        if not sel or ok.sum() < 3:
            continue
        best = (1.0, np.inf)
        for st in np.arange(0.85, 1.6, 0.01):
            err = np.sum((energy(sel, st) - ref[rows, b])[ok] ** 2)
            if err < best[1]:
                best = (st, err)
        if abs(best[0] - 1.0) > 0.005:
            for d in sel:
                d["tau"] *= best[0]
            changed.append((int(np.sqrt(BANDS[b] * BANDS[b + 1])), round(float(best[0]), 2)))
    print(f"gong: decays stretched per band (centre Hz, factor): {changed}")
    return modes


def score(feat, ref, noise, rows, w=None):
    err = 0.0
    for r in rows:
        ok = ref[r] > noise + 6
        d = (feat[r] - ref[r])[ok]
        err += np.sum(d ** 2) * (1.0 if w is None else w[r])
    return err


def fit_gong(model, feats, nwin=3, T=0.1, name="gong"):
    """the modulators of the K_FM strongest modes, so the hit's first nwin windows (the wall clock: 0-20, 20-50,
    50-100 ms) have the reference's band energies"""
    modes = sorted(model["modes"], key=lambda d: -d["a"] ** 2 * d["tau"])
    ref = np.array(feats["gong"]); noise = np.array(feats["noise"])
    wins = feats["gong_windows"][:nwin]
    pad = int(0.05 * FS)

    def feat_of(y):
        z = np.concatenate([np.zeros(pad), y, np.zeros(pad)])
        return band_energies(z, FS, pad / FS, wins)

    t = np.arange(int(T * FS)) / FS
    base = gong_wave(modes[K_FM:], [], T)
    parts = [gong_wave([d], [], T) for d in modes[:K_FM]]
    fm = [dict(r=1.0, I=0.0, tauI=0.015, B=0.0) for _ in range(K_FM)]
    total = base + sum(parts)
    best = score(feat_of(total), ref, noise, range(nwin))
    print(f"{name}: the hit's error before FM {np.sqrt(best / (nwin * 20)):.2f} dB rms")
    for sweep in range(3):
        for k in range(K_FM):
            d = modes[k]
            rest = total - parts[k]
            cand_best, cand = best, None
            for r in FM_RATIOS:
                sm = np.sin(2 * np.pi * r * d["f"] * t)
                for tauI in FM_TAU:
                    e = np.exp(-t / tauI)
                    for I in FM_INDEX:
                        ph = 2 * np.pi * d["f"] * t + d["ph"] + I * e * sm
                        c = np.cos(ph) * d["a"] * np.exp(-t / d["tau"])
                        for B in FM_BOOST:
                            y = c * (1 + B * e)
                            s = score(feat_of(rest + y), ref, noise, range(nwin))
                            if s < cand_best - 1e-9:
                                cand_best, cand = s, (dict(r=r, I=I, tauI=tauI, B=B), y)
            if cand:
                fm[k], parts[k] = cand
                total = rest + parts[k]
                best = cand_best
        print(f"{name}: sweep {sweep + 1}, the hit's error {np.sqrt(best / (nwin * 20)):.2f} dB rms")
    return modes, fm


ATTACKS = [0.0006, 0.001, 0.0015, 0.0022, 0.003, 0.004, 0.0055]      # the tick's rise: 1 - e^(-t / ta)


def tick_bank(tk, feats_rows, noise, seed, nwin=4, taus=None, tlen=0.07, loss="kl", lo=300.0, attacks=None):
    best = None
    for ta in attacks or ATTACKS:
        bank, err = tick_bank_at(tk, feats_rows, noise, seed, ta, nwin, taus, tlen, loss, lo)
        if best is None or err < best[1]:
            best = (bank, err, ta)
    return best


def tick_bank_at(tk, feats_rows, noise, seed, ta, nwin=4, taus=None, tlen=0.07, loss="kl", lo=300.0):
    """NT operators for one tick sound: (f, tau, a). The frequencies: the spectrum's strongest peaks, the rest spread
    over 330 Hz .. 14.5 kHz (the case knocks too). Per third-octave band two decays (the tick falls fast, then rings on in the movement and
    the case): the operators of a band take the short and the long one in turn, and the two levels and decays are
    fitted to the reference's band energies in its first nwin windows (4: 35 ms; noise taken off, NNLS over a grid
    of decays, taus; each operator's template tlen s long). The
    tick rises over a fraction of a millisecond (the pallet meets the tooth): that rise is searched too"""
    rng = np.random.default_rng(seed)
    peaks = [p[0] for p in tk["peaks"][:28]]
    fill = list(np.exp(np.linspace(np.log(lo * 1.1), np.log(14500), NT - len(peaks))))   # (lo: 300 Hz, 330 on)
    freqs = np.array(sorted(peaks + [f * np.exp(rng.uniform(-0.03, 0.03)) for f in fill]))
    ref = 10 ** (np.array(feats_rows) / 10)
    nz = 10 ** (np.array(noise) / 10)
    wins = feats["tick_windows"][:nwin]
    pad = int(0.01 * FS)
    t = np.arange(int(tlen * FS)) / FS
    band_of = np.clip(np.searchsorted(BANDS, freqs) - 1, 0, len(BANDS) - 2)
    TAUS = taus or [0.0015, 0.0025, 0.004, 0.006, 0.009, 0.013, 0.019, 0.028, 0.04]

    att = 1 - np.exp(-t / ta)

    def template(f, tau, seeds=6):                              # one operator, amplitude 1: power per window and band
        acc = 0
        for s_ in range(seeds):
            ph = np.random.default_rng(77 + s_).uniform(0, 2 * np.pi)
            y = att * np.exp(-t / tau) * np.sin(2 * np.pi * f * t + ph)
            z = np.concatenate([np.zeros(pad), y, np.zeros(pad)])
            acc = acc + 10 ** (band_energies(z, FS, pad / FS, wins) / 10)
        return acc / seeds                                      # windows x bands

    amps = np.zeros(NT); taus = np.zeros(NT)
    errs = []
    for b in range(len(BANDS) - 1):
        idx = np.where(band_of == b)[0]
        if len(idx) == 0 or np.sqrt(BANDS[b] * BANDS[b + 1]) < lo:
            continue
        target = np.clip(ref[:, b][:nwin] - nz[b], 0, None)
        wt = (ref[:nwin, b] > 2 * nz[b]).astype(float) + 1e-3
        fc = float(np.exp(np.mean(np.log(freqs[idx]))))
        T = {tau: template(fc, tau)[:, b] for tau in TAUS}
        best = None
        for i, ts in enumerate(TAUS):
            for tl in TAUS[i:]:
                A = np.stack([T[ts], T[tl]], axis=1)
                # NNLS on two columns, in a log-ish sense: weight by 1 / target
                W = wt / np.maximum(target, 1e-12)
                sol = None
                for cols in ([0, 1], [0], [1]):
                    Ac = A[:, cols] * W[:, None]
                    x, *_ = np.linalg.lstsq(Ac, target * W, rcond=None)
                    if np.all(x >= 0):
                        xx = np.zeros(2); xx[cols] = x
                        pred = A @ xx
                        e = np.sum(wt * (10 * np.log10(np.maximum(pred, 1e-14) / np.maximum(target, 1e-14))) ** 2)
                        if sol is None or e < sol[0]:
                            sol = (e, xx)
                if sol and (best is None or sol[0] < best[0]):
                    best = (sol[0], ts, tl, sol[1])
        e, ts, tl, x = best
        errs.append(np.sqrt(e / max(np.sum(wt > 0.5), 1)))
        short, long_ = idx[0::2], idx[1::2]
        for group, tau, power in ((short, ts, x[0]), (long_, tl, x[1])):
            if len(group) == 0:                                 # one operator in the band: it takes both powers' sum
                continue
            amps[group] = np.sqrt(power / len(group))
            taus[group] = tau
        if len(long_) == 0:
            amps[short] = np.sqrt((x[0] + x[1]) / len(short))
            taus[short] = ts if x[0] >= x[1] else tl
    # then all levels at once, each operator with its own template at its own frequency: a short window spreads a
    # band's energy into its neighbours, and the low operators have only a few cycles in the first 6 ms
    Tk = np.stack([template(f, max(tt, 0.0015), 4)[:nwin] for f, tt in zip(freqs, taus)])   # ops x windows x bands
    centers = np.sqrt(np.array(BANDS[:-1]) * np.array(BANDS[1:]))
    tgt = np.clip(ref[:nwin] - nz[None, :], 0, None)
    W = ((ref[:nwin] > 2 * nz[None, :]) & (centers[None, :] > lo)).astype(float)
    pw = np.maximum(amps ** 2, 1e-16)
    for _ in range(400):                                       # multiplicative updates (NMF): pw stays >= 0
        P = np.einsum("k,kwb->wb", pw, Tk) + 1e-20
        if loss == "is":                                       # Itakura-Saito: every window and band by its ratio,
            num = np.einsum("kwb,wb->k", Tk, W * tgt / P ** 2)  # as in dB (a quiet tail counts as the loud hit)
            den = np.einsum("kwb,wb->k", Tk, W / P) + 1e-30
            pw *= np.sqrt(num / den)
        else:                                                  # KL: by energy
            num = np.einsum("kwb,wb->k", Tk, W * tgt / P)
            den = np.einsum("kwb,wb->k", Tk, W) + 1e-20
            pw *= num / den
    amps = np.sqrt(pw)
    P = np.einsum("k,kwb->wb", pw, Tk)
    sel = W > 0
    err = float(np.sqrt(np.mean((10 * np.log10(P[sel] / np.maximum(tgt[sel], 1e-20))) ** 2)))
    return [dict(f=float(f), tau=float(tt), a=float(aa)) for f, tt, aa in zip(freqs, taus, amps)], err


if __name__ == "__main__":
    model = json.loads((ROOT / "tools" / "ref_model.json").read_text())
    feats = json.loads((ROOT / "tests" / "ref" / "features.json").read_text())
    modes, fm = fit_gong(model, feats)
    modes = fit_tails(modes, feats)
    out = dict(fs=FS, k_fm=K_FM, nt=NT, modes=modes, fm=fm, train=model["train"], click_before=0.040)
    for name, seed in (("tick", 1), ("tock", 2)):
        bank, err, ta = tick_bank(model["ticks"][name], feats[name], feats["noise"], seed)
        out[name] = bank
        out[name + "_attack"] = ta
        print(f"{name}: {len(bank)} operators, rise {1000 * ta:.1f} ms, band energies over 0-35 ms: {err:.2f} dB rms off")
    (ROOT / "tools" / "clk_model.json").write_text(json.dumps(out, indent=1) + "\n")
