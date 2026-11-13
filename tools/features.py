# SPDX-License-Identifier: GPL-3.0-only
# Copyright (C) 2026 Joakim (joakimskurk)
"""What the clock's sound is measured by, in the reference and in the engine alike (numpy only): the energy in
third-octave bands, 100 Hz .. 16 kHz, in windows of time after a hit or a tick (dB, as an RMS level)."""
import numpy as np

BANDS = [100 * 2 ** (k / 3) for k in range(0, 23)]          # 100 .. 16000 Hz, 22 bands
GONG_WIN = [(0.000, 0.020), (0.020, 0.050), (0.050, 0.100), (0.100, 0.200), (0.200, 0.400), (0.400, 0.800),
            (0.800, 1.600), (1.600, 3.200), (3.200, 5.000)]
TICK_WIN = [(-0.002, 0.004), (0.004, 0.010), (0.010, 0.020), (0.020, 0.035), (0.035, 0.060)]


def band_energies(x, fs, t0, wins, gates=()):
    """dB energy per band per window (rows: windows), from an FFT of each window (Hann), as an RMS level.
    gates: (a, b) times after t0 left out (the ticks inside the gong's decay); the rest is scaled up for them"""
    out = []
    for a, b in wins:
        i0 = int(round((t0 + a) * fs))
        s = np.asarray(x[i0:i0 + int(round((b - a) * fs))], dtype=float).copy()
        keep = np.ones(len(s))
        for ga, gb in gates:
            lo, hi = int(round((ga - a) * fs)), int(round((gb - a) * fs))
            if hi > 0 and lo < len(s):
                keep[max(lo, 0):min(hi, len(s))] = 0
        n = 1 << int(np.ceil(np.log2(max(len(s), 256))))
        w = np.hanning(len(s)) * keep
        S = np.abs(np.fft.rfft(s * w, n)) ** 2 / (max(np.sum(w ** 2), 1e-9) * len(s) / 2)
        f = np.fft.rfftfreq(n, 1 / fs)
        row = []
        for lo, hi in zip(BANDS[:-1], BANDS[1:]):
            sel = (f >= lo) & (f < hi)
            row.append(10 * np.log10(S[sel].sum() * len(s) / n + 1e-14))
        out.append(row)
    return np.array(out)


def read_wav(path):
    """16-bit PCM WAV -> (fs, float array frames x channels), without scipy"""
    import struct
    d = open(path, "rb").read()
    assert d[:4] == b"RIFF" and d[8:12] == b"WAVE", path
    i, fs, ch, data = 12, 0, 1, b""
    while i + 8 <= len(d):
        tag, size = d[i:i + 4], struct.unpack("<I", d[i + 4:i + 8])[0]
        body = d[i + 8:i + 8 + size]
        if tag == b"fmt ":
            _, ch, fs = struct.unpack("<HHI", body[:8])
        elif tag == b"data":
            data = body
        i += 8 + size + (size & 1)
    x = np.frombuffer(data, dtype="<i2").astype(float) / 32768
    return fs, x.reshape(-1, ch)
