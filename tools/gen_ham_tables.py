#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Hamster Piano's sound tables: firmware/gen/ham_tables.h.

The original (a web page, Web Audio) builds every note from a graph of oscillators and biquad filters. All of a
hamster's graph before its amplifier is linear and its source has eight harmonics, so the three formant filters and
the low-pass are worked out here, per note, as what they do to each harmonic: one wavetable a note (and one for the
note a fifth up, for the arpeggio). The chip then plays a wavetable, a sine and an envelope a voice, and no filter.
The heavy mode (THALLHAMSTERGRINDCORE) is not linear (its distortion): its filters run on the chip, their
coefficients are here. Integers only on the chip: levels and pitches are base-2 logarithms in Q16 (a line in the
logarithm is the exponential ramp the page asks Web Audio for), turned into numbers with HAM_EXP2.

  python3 tools/gen_ham_tables.py [--check]
"""
import cmath
import math
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "firmware" / "gen" / "ham_tables.h"
FS = 44100
CB = 16                                 # frames a control block (ham_engine.h)
WT_N = 256                              # a wavetable: one cycle
MIDI = [60, 62, 64, 65, 67, 69, 71, 72]   # the eight hamsters: C D E F G A B C
HARM = [1.0, .54, .31, .19, .12, .075, .045, .025]   # the page's PeriodicWave (sines)
OCT_LO, OCT_HI = -3, 2                  # tables for these octaves (a step: -3..+1; +2 is +1 with the arpeggio's octave)
NOCT = OCT_HI - OCT_LO + 1
RESP_N = 170                            # the formants' response: 16 points an octave, 16 Hz .. 24 kHz
STEP_VELOCITY = [1, .80, .90, .78, .95, .80, .88, .76, 1, .80, .91, .79, .96, .80, .89, .76]


# ---- Web Audio's biquads (the specification's formulas; a low-pass's and a high-pass's Q is in dB)
def bq_lowpass(f, q_db):
    w = 2 * math.pi * f / FS
    a = math.sin(w) / (2 * 10 ** (q_db / 20))
    c = math.cos(w)
    return [(1 - c) / 2, 1 - c, (1 - c) / 2], [1 + a, -2 * c, 1 - a]


def bq_highpass(f, q_db):
    w = 2 * math.pi * f / FS
    a = math.sin(w) / (2 * 10 ** (q_db / 20))
    c = math.cos(w)
    return [(1 + c) / 2, -(1 + c), (1 + c) / 2], [1 + a, -2 * c, 1 - a]


def bq_bandpass(f, q):
    w = 2 * math.pi * f / FS
    a = math.sin(w) / (2 * q)
    c = math.cos(w)
    return [a, 0.0, -a], [1 + a, -2 * c, 1 - a]


def bq_peaking(f, q, gain_db):
    w = 2 * math.pi * f / FS
    a = math.sin(w) / (2 * q)
    c = math.cos(w)
    A = 10 ** (gain_db / 40)
    return [1 + a * A, -2 * c, 1 - a * A], [1 + a / A, -2 * c, 1 - a / A]


def resp(bq, f):
    b, a = bq
    z = cmath.exp(-2j * math.pi * f / FS)
    return (b[0] + b[1] * z + b[2] * z * z) / (a[0] + a[1] * z + a[2] * z * z)


def hz(m):
    return 440 * 2 ** ((m - 69) / 12)


def periodic_norm():
    """Web Audio scales a PeriodicWave so that its highest sample is 1 (a table of 4096 at 44.1 kHz)"""
    t = np.arange(4096) / 4096
    x = sum(h * np.sin(2 * np.pi * (k + 1) * t) for k, h in enumerate(HARM))
    return 1 / np.abs(x).max()


def basic_norm(kind):
    """the built-in waveforms are scaled the same way: a sawtooth and a square lose their overshoot"""
    n = 4096
    spec = np.zeros(n // 2 + 1, dtype=complex)
    for k in range(1, n // 2):
        w = 1 / (k * math.pi)
        b = (2 * w if k & 1 else -2 * w) if kind == "saw" else (4 * w if k & 1 else 0)
        spec[k] = -0.5j * b * n
    return 1 / np.abs(np.fft.irfft(spec, n)).max()


SOFT = bq_lowpass(4300, .55)            # the "soften" low-pass (5000 Hz with an arpeggio: 4300 here for all)


def note_table(key, f):
    """one cycle of a hamster's voice at f, after its formants and the low-pass; its body's sine: level, phase"""
    char = (key - 3.5) / 3.5
    f1, f2, f3 = bq_bandpass(880 + char * 55, 2.8), bq_bandpass(2050 + char * 95, 3.7), bq_bandpass(3150 + char * 120, 4.2)
    norm = periodic_norm()
    t = np.arange(WT_N) / WT_N
    x = np.zeros(WT_N)
    for k, h in enumerate(HARM, 1):
        fk = f * k
        if fk >= FS / 2:
            break
        H = (.72 * resp(f1, fk) + .26 * resp(f2, fk) + .075 * resp(f3, fk)) * resp(SOFT, fk)
        x += h * norm * abs(H) * np.sin(2 * np.pi * k * t + cmath.phase(H))
    hb = .38 * resp(SOFT, f)
    return x, abs(hb), cmath.phase(hb)


def lg(v):                              # a level or a ratio as its base-2 logarithm, Q16
    return int(round(math.log2(v) * 65536))


def q28(bq):
    b, a = bq
    return [int(round(v / a[0] * (1 << 28))) for v in (b[0], b[1], b[2], a[1], a[2])]


def arr(name, typ, vals, per=12, fmt="{}"):
    s = [f"static const {typ} {name}[{len(vals)}] = {{"]
    for i in range(0, len(vals), per):
        s.append("    " + ", ".join(fmt.format(v) for v in vals[i:i + per]) + ",")
    s.append("};")
    return "\n".join(s)


def build():
    o = ["/* SPDX-License-Identifier: GPL-3.0-only */",
         "/* Hamster Piano's sound tables. Made by tools/gen_ham_tables.py: do not edit. */",
         "#pragma once", "#include <stdint.h>", ""]
    o.append(f"#define HAM_WT_N {WT_N}u")
    o.append(f"#define HAM_NOCT {NOCT}u                       /* tables for octaves {OCT_LO}..{OCT_HI} */")
    o.append(f"#define HAM_OCT_LO ({OCT_LO})")
    o.append(f"#define HAM_NWT {8 * NOCT * 2}u                      /* key * {NOCT} + octave, then the same a fifth up */")
    o.append("")
    # the sine, Q15, a cycle of 4096
    o.append(arr("HAM_SIN", "int16_t", [int(round(32767 * math.sin(2 * math.pi * i / 4096))) for i in range(4096)], 16))
    # 2^(i/256), Q30
    o.append(arr("HAM_EXP2", "uint32_t", [int(round(2 ** (i / 256) * (1 << 30))) for i in range(257)], 8, "{}u"))
    # the phase step of each MIDI note as a logarithm (Q16): 2^32 a cycle
    o.append(arr("HAM_LGP", "int32_t", [lg(hz(m) * 2 ** 32 / FS) for m in range(128)], 8))
    # the wavetables (Q14: 16384 is the page's 1.0), the bodies
    wt, bg, bp, peak = [], [], [], 0.0
    for semis in (0, 7):
        for key in range(8):
            for oct_ in range(OCT_LO, OCT_HI + 1):
                x, g, ph = note_table(key, hz(MIDI[key] + 12 * oct_ + semis))
                peak = max(peak, np.abs(x).max())
                wt.append([int(round(v * 16384)) for v in x] + [int(round(x[0] * 16384))])
                bg.append(int(round(g * 32768)))
                bp.append(int(round((ph / (2 * math.pi)) % 1 * 2 ** 32)) & 0xFFFFFFFF)
    assert peak < 1.99, peak
    o.append(f"static const int16_t HAM_WT[{len(wt)}][{WT_N + 1}] = {{")
    for row in wt:
        o.append("    {" + ", ".join(str(v) for v in row) + "},")
    o.append("};")
    # a glide moves a voice's harmonics through its formants: what the filters do at any frequency, per hamster,
    # 16 points an octave from 16 Hz (real and imaginary, Q14); the harmonics' own levels (Q15), log2(k) (Q16)
    re, im = [], []
    for key in range(8):
        char = (key - 3.5) / 3.5
        f1, f2, f3 = bq_bandpass(880 + char * 55, 2.8), bq_bandpass(2050 + char * 95, 3.7), bq_bandpass(3150 + char * 120, 4.2)
        r_, i_ = [], []
        for k in range(RESP_N):
            f = 16 * 2 ** (k / 16)
            H = (.72 * resp(f1, f) + .26 * resp(f2, f) + .075 * resp(f3, f)) * resp(SOFT, f) if f < FS / 2 else 0
            r_.append(int(round(H.real * 16384)) if H else 0)
            i_.append(int(round(H.imag * 16384)) if H else 0)
        re.append(r_)
        im.append(i_)
    for n, t in (("HAM_RESP_RE", re), ("HAM_RESP_IM", im)):
        o.append(f"static const int16_t {n}[8][{RESP_N}] = {{")
        for row in t:
            o.append("    {" + ", ".join(str(v) for v in row) + "},")
        o.append("};")
    o.append(f"#define HAM_RESP_N {RESP_N}u")
    o.append(f"#define LG_RESP0 ({lg(16 * 2 ** 32 / FS)})                      /* 16 Hz as a phase step's logarithm */")
    o.append(arr("HAM_HARM", "int16_t", [int(round(h * periodic_norm() * 32768)) for h in HARM], 8))
    o.append(arr("HAM_LGK", "int32_t", [lg(k) for k in range(1, 9)], 8))
    o.append(arr("HAM_BODY_G", "int16_t", bg))
    o.append(arr("HAM_BODY_PH", "uint32_t", bp, 6, "{}u"))
    # the vibrato of each hamster: 6.4 + key * 0.08 Hz, a phase step a control block
    o.append(arr("HAM_VIB_INC", "uint32_t", [int(round((6.4 + k * .08) * CB / FS * 2 ** 32)) for k in range(8)], 8, "{}u"))
    o.append(arr("HAM_PAN_L", "int16_t", [int(round(32768 * math.cos((((k - 3.5) / 3.5 * .06) + 1) / 2 * math.pi / 2))) for k in range(8)], 8))
    o.append(arr("HAM_PAN_R", "int16_t", [int(round(32768 * math.sin((((k - 3.5) / 3.5 * .06) + 1) / 2 * math.pi / 2))) for k in range(8)], 8))
    o.append(arr("HAM_VEL_LG", "int32_t", [lg(v) for v in STEP_VELOCITY], 8))
    o.append(arr("HAM_MIDI_VEL_LG", "int32_t", [lg(.55 + (1.08 - .55) * max(v, 1) / 127) for v in range(128)], 8))
    # the distortion's curve, as the page's: 2048 points over -1..1
    curve = []
    for i in range(2048):
        x = i * 2 / 2047 - 1
        curve.append(int(round(32767 * (math.tanh(x * 15.5) * .92 + math.tanh(x * 4.2) * .08))))
    o.append(arr("HAM_SHAPE", "int16_t", curve + [curve[-1]], 16))
    # the biquads that run on the chip: b0 b1 b2 a1 a2, Q28
    bqs = {
        "BQ_BREATH": bq_bandpass(3600, .75), "BQ_SOFT": SOFT,
        "BQ_T_BREATH": bq_bandpass(2450, 1.15), "BQ_T_STRING": bq_lowpass(5200, .35), "BQ_T_SOFT5": bq_lowpass(5000, .55),
        "BQ_T_PREHP": bq_highpass(72, .45), "BQ_T_CABHP": bq_highpass(82, .55), "BQ_T_CABMID": bq_peaking(920, .8, 3.4),
        "BQ_T_CABLP": bq_lowpass(4100, .72),
    }
    for n, b in bqs.items():
        o.append(f"static const int32_t {n}[5] = {{{', '.join(str(v) for v in q28(b))}}};")
    drum = [[bq_bandpass(f, q) for f, q in zip([1800, 1180, 2550], [.7, .5, 1.05])],          # snare
            [bq_highpass(f, 1.0) for f in [6200, 4700, 7600]],                               # hat (Q: the default, 1 dB)
            [bq_bandpass(f, q) for f, q in zip([1450, 1050, 2100], [.55, .48, .95])]]        # clap
    o.append("static const int32_t BQ_DRUM[3][3][5] = {                /* snare, hat, clap: a voice each */")
    for row in drum:
        o.append("    {" + ", ".join("{" + ", ".join(str(v) for v in q28(b)) + "}" for b in row) + "},")
    o.append("};")
    # levels and ratios the engine names, as logarithms (Q16)
    names = {
        "LG_FLOOR": .0001, "LG_VMIN": .55, "LG_VMAX": 1.08, "LG_ACCENT": 1.22,
        "LG_H_A1": .22, "LG_H_A2": .15, "LG_H_A3": .055,
        "LG_T_A1": .34, "LG_T_A2": .205, "LG_T_A3": .155, "LG_T_A4": .105,
        "LG_H_BR1": .0065, "LG_H_BR2": .002, "LG_T_BR1": .022, "LG_T_BR2": .004,
        "LG_H_V0": 1.075, "LG_H_B0": 1.025, "LG_T_V0": 1.11, "LG_T_B0": 1.035, "LG_T_E0": 1.04,
        "LG_DRIFT1": 1.008, "LG_DRIFT2": .998, "LG_FIFTH": 2 ** (7 / 12),
        "LG_DRUM": .58, "LG_DVMIN": .25, "LG_DVMAX": 1.25, "LG_CLAP_LOW": .018, "LG_CLICK": .065,
    }
    for n, v in names.items():
        o.append(f"#define {n} ({lg(v)})")
    for n, vals in {"LG_KICK_PK": [.62, .54, .48], "LG_SNARE_PK": [.24, .22, .20], "LG_SNARE_TONE": [.12, .16, .09],
                    "LG_HAT_PK": [.11, .09, .13], "LG_CLAP_PK": [.13, .115, .145]}.items():
        o.append(f"static const int32_t {n}[3] = {{{', '.join(str(lg(v)) for v in vals)}}};")
    for n, vals in {"LGP_KICK0": [150, 185, 125], "LGP_KICK1": [48, 42, 55], "LGP_SNARE": [185, 145, 225],
                    "LGP_CLICK": [820, 190, 190]}.items():
        o.append(f"static const int32_t {n}[3] = {{{', '.join(str(lg(v * 2 ** 32 / FS)) for v in vals)}}};")
    o.append(f"#define LG_T_TRIM ({lg(.155 * math.cos(math.pi / 4))})                    /* the drive's trim and the panner at its middle */")
    o.append(f"#define LG_PAN0 ({lg(math.cos(math.pi / 4))})")
    o.append(f"#define LG_OCT 65536                           /* an octave */")
    o.append(f"#define HAM_CENT_Q16 {int(round(65536 / 1200 * 256))}                         /* a cent, Q16 of an octave, times 256 */")
    o.append(f"#define HAM_SAW_NORM {int(round(basic_norm('saw') * 32768))}                       /* Web Audio's sawtooth against a full one, Q15 */")
    o.append(f"#define HAM_SQR_NORM {int(round(basic_norm('square') * 32768))}                       /* and its square */")
    return "\n".join(o) + "\n"


def main():
    text = build()
    if "--check" in sys.argv:
        if not OUT.exists() or OUT.read_text() != text:
            print("ham_tables.h: differs from what tools/gen_ham_tables.py makes (run it)")
            return 1
        print("ham_tables.h: up to date")
        return 0
    OUT.write_text(text)
    print(f"{OUT.relative_to(ROOT)}: {len(text)} bytes")
    return 0


if __name__ == "__main__":
    sys.exit(main())
