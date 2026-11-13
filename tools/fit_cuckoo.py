#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
# Copyright (C) 2026 Joakim (joakimskurk)
"""Fit the cuckoo clock's sound to the measurements of its recording (tools/ref_cuckoo.json,
tests/ref/cuckoo_features.json, from tools/analyze_cuckoo.py) and write tools/clk_cuckoo.json, the model its tables
are made from (tools/gen_tables.py). The same methods as the wall clock's (tools/fit_model.py):

  - the wire gong: every mode an FM carrier, the K_FM strongest with a modulator searched so the hit's first 140 ms
    (before the first pipe) have the reference's band energies;
  - the two pipes: an FM pair each, carrier and modulator at the pipe's pitch (1:1), the index from the second
    harmonic (J1(I) / J0(I) ~ I / 2), the bellows' envelope as measured, step by step;
  - the clicks (the tick, the warning, the door opening, the door shutting): what comes back every time as
    measured, and noise operators over it (tools/clicks.py).

  python3 -I tools/fit_cuckoo.py [--clicks]   (numpy, scipy; ~8 min; --clicks: only the clicks, ~5)
"""
import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import fit_model as F  # noqa: E402
import clicks as K  # noqa: E402
from features import BANDS, band_energies  # noqa: E402


def pipe_wave(p, n_total, start, fs=44100):
    """a pipe's note as the engine plays it: an FM pair at its pitch (1:1, its index), its body partials, the
    envelope in steps"""
    env = np.repeat(np.array(p["env"]), p["env_step"])
    t = np.arange(len(env)) / fs
    s = np.sin(2 * np.pi * p["f"] * t + p["index"] * np.sin(2 * np.pi * p["f"] * t))
    for b in p.get("body", []):
        s = s + b["rel"] * np.sin(2 * np.pi * b["f"] * t)
    y = np.zeros(n_total)
    i0 = int(round(start * fs))
    n = max(0, min(len(env), n_total - i0))
    y[i0:i0 + n] = (env * s)[:n]
    return y


def fit_tails(modes, pipes, call, feats, fs=44100):
    """the gong's decays per third octave, stretched so a call in the train (the two before it still ringing, the
    pipes sounding) has the reference's band energies from 140 to 600 ms, and the hit alone still its own from 30 to
    140 ms: the pencil saw only 0.17 s round the pipes' pitches, too short for their slow modes"""
    wins = feats["call_windows"]
    ref = np.array(feats["call"]); noise = np.array(feats["noise"])
    gwins = feats["gong_windows"]
    gref = np.array(feats["gong"])
    rows = [w for w, (a, b) in enumerate(wins) if a >= 0.14]
    grows = [w for w, (a, b) in enumerate(gwins) if a >= 0.03]
    P = call["period"]
    n = int((2 * P + 0.7) * fs)
    pw = np.zeros(n)
    for k in range(3):
        hs = k * P + call["hit_to_high"] - 0.010
        pw += pipe_wave(pipes["high"], n, hs) + pipe_wave(pipes["low"], n, hs + call["high_to_low"])
    Ep = 10 ** (band_energies(pw, fs, 2 * P, wins) / 10)          # the pipes' energy, windows x bands
    band = np.clip(np.searchsorted(BANDS, [d["f"] for d in modes]) - 1, 0, len(BANDS) - 2)

    def gong_e(sel, st, t1, t2, backs):
        e = 0.0
        for d in sel:
            tau = d["tau"] * st
            for back in backs:
                e += d["a"] ** 2 / 2 * tau / (2 * (t2 - t1)) * (np.exp(-2 * (t1 + back) / tau) - np.exp(-2 * (t2 + back) / tau))
        return e

    changed = []
    for b in range(len(BANDS) - 1):
        sel = [d for d, bb in zip(modes, band) if bb == b]
        ok = [w for w in rows if ref[w, b] > noise[b] + 6]
        gok = [w for w in grows if gref[w, b] > noise[b] + 6]
        if not sel or len(ok) < 2:
            continue
        g0 = {w: gong_e(sel, 1.0, *gwins[w], (0,)) for w in gok}  # (the hit alone as fitted: its own error kept)
        best = (1.0, np.inf)
        for st in np.exp(np.linspace(np.log(0.8), np.log(4.0), 60)):
            err = sum((10 * np.log10(gong_e(sel, st, *wins[w], (0, P, 2 * P)) + Ep[w, b] + 1e-20) - ref[w, b]) ** 2 for w in ok)
            err += 2 * sum((10 * np.log10((gong_e(sel, st, *gwins[w], (0,)) + 1e-20) / (g0[w] + 1e-20))) ** 2 for w in gok)
            if err < best[1]:
                best = (st, err)
        if abs(best[0] - 1) > 0.01:
            for d in sel:
                d["tau"] *= best[0]
            changed.append((int(np.sqrt(BANDS[b] * BANDS[b + 1])), round(float(best[0]), 2)))
    print(f"cuckoo gong: decays stretched per band (centre Hz, factor): {changed}")
    return modes


def fit_pipe_tails(modes, fm, pipes, call, feats, fs=44100):
    """the pipes' envelopes go on past where they were measured (there the gong was as loud as they are in their
    bands): an exponential from the last step, its time searched so a call in the train (the two before it still
    ringing) has the reference's band energies from 140 to 600 ms in the pipe's bands (its pitch, its octave)"""
    wins = feats["call_windows"]
    ref = np.array(feats["call"]); noise = np.array(feats["noise"])
    rows = [w for w, (a, b) in enumerate(wins) if a >= 0.14]
    P = call["period"]
    n = int((2 * P + 0.7) * fs)
    g1 = F.gong_wave(modes, fm, 2 * P + 0.7)
    gw = np.zeros(n)
    for k in range(3):
        i0 = int(round(k * P * fs))
        gw[i0:] += g1[:n - i0]
    Eg = 10 ** (band_energies(gw, fs, 2 * P, wins) / 10)
    out = {}
    for name, other in (("high", "low"), ("low", "high")):
        p0 = pipes[name]
        f = p0["f"]
        bands = [int(np.searchsorted(BANDS, f) - 1), int(np.searchsorted(BANDS, 2 * f) - 1)]
        best = (None, np.inf, None)
        for tau in np.exp(np.linspace(np.log(0.01), np.log(0.08), 30)):   # (no longer: the bellows are empty)
            nstep = int(np.ceil(tau * np.log(1000) * fs / p0["env_step"]))   # down 60 dB
            tail = p0["env"][-1] * np.exp(-(np.arange(1, nstep + 1) * p0["env_step"] / fs) / tau)
            p1 = dict(p0, env=list(p0["env"]) + tail.tolist())
            pw = np.zeros(n)
            for k in range(3):
                hs = k * P + call["hit_to_high"] - 0.010
                pw += pipe_wave(p1 if name == "high" else pipes["high"], n, hs)
                pw += pipe_wave(p1 if name == "low" else pipes["low"], n, hs + call["high_to_low"])
            Ep = 10 ** (band_energies(pw, fs, 2 * P, wins) / 10)
            err = 0.0
            for b in bands:
                for w in rows:
                    if ref[w, b] > noise[b] + 6:
                        err += (10 * np.log10(Eg[w, b] + Ep[w, b] + 1e-20) - ref[w, b]) ** 2
            if err < best[1]:
                best = (tau, err, tail)
        out[name] = list(p0["env"]) + best[2].tolist()
        print(f"cuckoo {name} pipe: its envelope on past {len(p0['env']) * p0['env_step'] / fs * 1000:.0f} ms, "
              f"down with {best[0] * 1000:.0f} ms to -60 dB")
    for name in out:
        pipes[name]["env"] = out[name]
    return pipes


def low_energy(det, noise, ta, span=0.08, seeds=16):
    """a click's mean power at 80-450 Hz over its first span s, as the engine plays it (tests/clk/parity.py ck_tick)"""
    n = int(0.3 * K.FS)
    f = np.fft.rfftfreq(n, 1 / K.FS)
    sel = (f >= 80) & (f <= 450)
    acc = 0.0
    for s_ in range(seeds):
        y = K.render(det, noise, n, ta, rng=np.random.default_rng(100 + s_))
        acc += np.mean(np.fft.irfft(np.fft.rfft(y) * sel, n)[:int(span * K.FS)] ** 2)
    return acc / seeds


CK_NT = 68                                        # operators a click (the bank: as many as the wall clock's tick, and 4)
RATTLE_RATE, RATTLE_TAU = 250.0, 0.0015           # clicks a second, each its decay (the recording: one every 2-10 ms)


def rattle_model(r, e_db, fs=44100, seconds=2.0):
    """the train's rattle as the engine makes it: clicks at random (RATTLE_RATE a second), each a sine at one of the
    measured frequencies (chosen as often as its share of the power), its level 0.4-1 of the full one, decaying
    in RATTLE_TAU; the full level so that its energy above 800 Hz is the recording's (simulated)"""
    w = np.array([g["w"] for g in r["grains"]])
    prob = w / w.sum()
    rng = np.random.default_rng(7)
    n = int(seconds * fs)
    y = np.zeros(n + fs)
    t = np.arange(int(8 * RATTLE_TAU * fs)) / fs
    k = 0
    pos = 0
    while True:
        pos += int(rng.exponential(fs / RATTLE_RATE))
        if pos >= n:
            break
        f = r["grains"][rng.choice(len(prob), p=prob)]["f"]
        y[pos:pos + len(t)] += rng.uniform(0.4, 1.0) * np.exp(-t / RATTLE_TAU) * np.sin(2 * np.pi * f * t + rng.uniform(0, 6.3))
        k += 1
    y = y[:n]
    fx = np.fft.rfftfreq(n, 1 / fs)
    Y = np.fft.rfft(y)
    Y[fx < 800] = 0
    e = np.mean(np.fft.irfft(Y, n) ** 2)
    a = float(np.sqrt(10 ** (e_db / 10) / e))
    print(f"rattle: {len(prob)} frequencies, {RATTLE_RATE:.0f} clicks a second, each {1000 * RATTLE_TAU:.1f} ms, "
          f"full level {20 * np.log10(a):.1f} dB; runs {r['start']:.2f} .. {r['stop']:.2f} s before the first blow")
    return dict(f=[g["f"] for g in r["grains"]], p=prob.tolist(), a=a, tau=RATTLE_TAU, rate=RATTLE_RATE,
                start=r["start"], stop=r["stop"])

if __name__ == "__main__":
    model = json.loads((ROOT / "tools" / "ref_cuckoo.json").read_text())
    feats = json.loads((ROOT / "tests" / "ref" / "cuckoo_features.json").read_text())
    F.feats = feats
    if "--clicks" in sys.argv:                  # (the clicks only, the rest as it is)
        out = json.loads((ROOT / "tools" / "clk_cuckoo.json").read_text())
    else:
        modes, fm = F.fit_gong(model, feats, nwin=4, T=0.14, name="cuckoo gong")
        out = dict(fs=F.FS, k_fm=F.K_FM, nt=F.NT, modes=modes, fm=fm, call=model["call"], mech=model["mech"],
                   beat=model["beat"])
        out["pipes"] = {k: dict(f=v["f"], env=v["env"], env_step=v["env_step"],
                                index=float(2 * 10 ** (v["h2"] / 20)), body=v["body"]) for k, v in model["pipes"].items()}
        out["pipes"] = fit_pipe_tails(modes, fm, out["pipes"], model["call"], feats)
        out["modes"] = fit_tails(modes, out["pipes"], model["call"], feats)
    # the clicks (tools/clicks.py): what comes back every time (the tick's crack and its case's knock; the door's
    # wood, struck three times) as measured, and over it noise operators, fitted to each click's power over time in
    # eighths of an octave and in octaves over 1 ms windows
    fine = json.loads((ROOT / "tests" / "ref" / "cuckoo_clicks.json").read_text())
    for name, lo, hi, last, delays in [("tick", 400.0, 16000.0, 1.0, K.DELAYS),
                                       ("warning", 300.0, 13500.0, 0.06, K.DELAYS),   # (then its train rattles on)
                                       ("door", 300.0, 13500.0, 1.0, K.DELAYS + [28, 36, 40, 52, 60, 70]),
                                       ("door_shut", 300.0, 13500.0, 1.0, K.DELAYS)]:
        d = fine[name]
        meas = {g: (np.array(d[g]["E"]), np.array(d[g]["N"])) for g in ("fine", "time")}
        t0 = fine["t0"]["tick" if name == "tick" else "other"]
        print(f"{name}: {len(d['det'])} modes the same every time, noise operators over them")
        noise, _ = K.fit(meas, d["det"], t0, fine["ta"], nops=CK_NT - len(d["det"]), lo=lo, hi=hi, last=last,
                         delays=sorted(set(delays)))
        det = d["det"]
        if name == "tick":                      # its case's knock, as loud as the ticks averaged have it over their
            want = 10 ** (feats["knock_db"] / 10)   # floor (80-450 Hz, 80 ms; the average keeps an eighth of the
            kn = [m for m in det if m["f"] < 450]   # room's rumble, and its modes take some of that)
            e_kn, e_all = low_energy(kn, [], fine["ta"]), low_energy(det, noise, fine["ta"])
            g = float(np.sqrt(max(want - (e_all - e_kn), 0.1 * want) / e_kn))
            det = [dict(m, a=m["a"] * g) if m["f"] < 450 else m for m in det]
            print(f"tick: its case's knock, {len(kn)} modes " + ", ".join(f"{m['f']:.0f}" for m in kn) + f" Hz, x {g:.2f}")
        out[name], out[name + "_attack"], out[name + "_t0"] = det + noise, fine["ta"], t0
    if "--clicks" not in sys.argv:
        # the train running: its partials, each third of an octave as loud as the train running is over it still
        out["drone"] = model["drone"]
        out["rattle"] = rattle_model(model["rattle"], feats["rattle_db"])
        print(f"drone: {len(out['drone'])} partials, {min(d['f'] for d in out['drone']):.0f} .. {max(d['f'] for d in out['drone']):.0f} Hz")
    (ROOT / "tools" / "clk_cuckoo.json").write_text(json.dumps(out, indent=1) + "\n")
