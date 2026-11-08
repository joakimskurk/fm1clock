#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Fit the cuckoo clock's sound to the measurements of its recording (tools/ref_cuckoo.json,
tests/ref/cuckoo_features.json, from tools/analyze_cuckoo.py) and write tools/clk_cuckoo.json, the model its tables
are made from (tools/gen_tables.py). The same methods as the wall clock's (tools/fit_model.py):

  - the wire gong: every mode an FM carrier, the K_FM strongest with a modulator searched so the hit's first 140 ms
    (before the first pipe) have the reference's band energies;
  - the two pipes: an FM pair each, carrier and modulator at the pipe's pitch (1:1), the index from the second
    harmonic (J1(I) / J0(I) ~ I / 2), the bellows' envelope as measured, step by step;
  - the tick: 64 operators, two decays per third octave, a rise, all levels fitted together over its first 0.13 s
    (it rings on); the mechanism's clicks
    (the warning and the door before a strike, the door after it) are its sound at their own level (their peaks
    above 3 kHz: under them the pipes and the gong sound in the recording).

  python3 -I tools/fit_cuckoo.py            (numpy; ~1 min)
"""
import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import fit_model as F  # noqa: E402
import clicks as K  # noqa: E402
import os  # noqa: E402
LOSS = os.environ.get("CK_TICK_LOSS", "is")   # (its tick: by ratio, so its quiet tail counts)
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


def low_energy(ops, ta, fs=44100, span=0.08, seeds=16):
    """a tick's mean power at 80-450 Hz over its first span s (random phases, as the engine starts them)"""
    t = np.arange(int(0.3 * fs)) / fs
    att = 1 - np.exp(-t / ta)
    f = np.fft.rfftfreq(len(t), 1 / fs)
    sel = (f >= 80) & (f <= 450)
    acc = 0.0
    for s_ in range(seeds):
        rng = np.random.default_rng(100 + s_)
        y = sum(d["a"] * att * np.exp(-t / d["tau"]) * np.sin(2 * np.pi * d["f"] * t + rng.uniform(0, 2 * np.pi)) for d in ops)
        b = np.fft.irfft(np.fft.rfft(y) * sel, len(t))
        acc += np.mean(b[:int(span * fs)] ** 2)
    return acc / seeds


CLICK_RISE = 0.001                                # the clicks' rise: hard (the pallet strikes the tooth)
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
    modes, fm = F.fit_gong(model, feats, nwin=4, T=0.14, name="cuckoo gong")
    out = dict(fs=F.FS, k_fm=F.K_FM, nt=F.NT, modes=modes, fm=fm, call=model["call"], mech=model["mech"],
               beat=model["beat"])
    out["pipes"] = {k: dict(f=v["f"], env=v["env"], env_step=v["env_step"], index=float(2 * 10 ** (v["h2"] / 20)),
                            body=v["body"]) for k, v in model["pipes"].items()}
    out["pipes"] = fit_pipe_tails(modes, fm, out["pipes"], model["call"], feats)
    out["modes"] = fit_tails(modes, out["pipes"], model["call"], feats)
    # the clicks, each its own sound at 1/12 of an octave (tools/clicks.py): the tick (above 400 Hz; under it the
    # case's knock, its modes from the ticks averaged), the train's warning, the door (its latch, then from 13 ms
    # on the door and its stop, fitted on what the first leaves), the door shutting (and the bird going in)
    fine = json.loads((ROOT / "tests" / "ref" / "cuckoo_clicks.json").read_text())
    ta = CLICK_RISE
    def fit_fine(name, lo, nops, wins=K.WINDOWS, E=None, taus=None, hi=13500.0):
        d = fine[name]                            # (the tick to 16 kHz; the others, mostly in the middle, to 13.5:
        ops, err = K.fit(np.array(d["E"]) if E is None else E, np.array(d["N"]), lo=lo, ta=ta, wins=wins, nops=nops,
                         taus=taus, hi=hi)        # their spare operators for second decays)
        print(f"{name}: {len(ops)} operators at 1/12 octave, {err:.2f} dB rms off")
        return ops
    bank = fit_fine("tick", 400.0, 64, hi=16000.0)
    knock = [dict(f=d["f"], tau=d["tau"], a=d["a"]) for d in model["ticks"]["knock"] if d["tau"] < 0.1][:4]
    e_hi, e_kn = low_energy(bank, ta), low_energy(knock, ta)
    want = 10 ** (feats["knock_db"] / 10)
    g = np.sqrt(max(want - e_hi, 0.1 * want) / e_kn)
    knock = [dict(d, a=d["a"] * g) for d in knock]
    print("knock: " + ", ".join(f"{d['f']:.0f} Hz ({1000 * d['tau']:.0f} ms)" for d in knock) + f", x {g:.2f}")
    out["tick"], out["tick_attack"] = bank + knock, ta
    out["warning"], out["warning_attack"] = fit_fine("warning", 300.0, 68), ta
    door_a = fit_fine("door_a", 300.0, 68, wins=[tuple(w) for w in fine["door_a_windows"]],
                      taus=[t for t in K.TAUS if t <= 0.006])   # (the latch: done when the door hits its stop)
    acc = 0                                       # what the latch leaves from 13 ms on: the door and its stop
    for s_ in range(8):
        y = K.render(door_a, ta, int(0.3 * K.FS), rng=np.random.default_rng(200 + s_))
        acc = acc + K.band_env(np.concatenate([np.zeros(int(0.2 * K.FS)), y]), K.FS, [0.2 + fine["door_split"]])[0]
    Eb = np.clip(np.array(fine["door_b"]["E"]) - acc / 8, 0, None) + np.array(fine["door_b"]["N"])
    door_b = fit_fine("door_b", 300.0, 68, E=Eb)
    err = K.refine([(door_a, 0.0), (door_b, fine["door_split"])], np.array(fine["door"]["E"]), np.array(fine["door"]["N"]),
                   ta=ta)                         # then both their levels together, against the whole door
    print(f"door: the latch and the door to its stop together, {err:.2f} dB rms off")
    out["door"], out["door_attack"] = door_a, ta
    out["door_b"], out["door_b_attack"] = door_b, ta
    out["door_split"] = fine["door_split"]
    out["door_shut"], out["door_shut_attack"] = fit_fine("door_shut", 300.0, 68), ta
    # the train running: its partials as measured, those under 450 Hz together as loud as the recording's drone
    # is there (their narrow bands leave out the whirr between them)
    dr = model["drone"]
    e = sum(d["a"] ** 2 / 2 for d in dr if 40 <= d["f"] <= 450)
    g = np.sqrt(10 ** (feats["drone_db"] / 10) / e)
    out["drone"] = [dict(d, a=d["a"] * (g if d["f"] <= 450 else 1.0)) for d in dr]
    print(f"drone: under 450 Hz x {g:.2f}")
    out["rattle"] = rattle_model(model["rattle"], feats["rattle_db"])
    print(f"drone: {len(out['drone'])} partials, {min(d['f'] for d in out['drone']):.0f} .. {max(d['f'] for d in out['drone']):.0f} Hz")
    (ROOT / "tools" / "clk_cuckoo.json").write_text(json.dumps(out, indent=1) + "\n")
