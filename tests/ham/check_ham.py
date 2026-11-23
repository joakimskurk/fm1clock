#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Hamster Piano on the host (tests/host.c), by what it sends over MIDI: every note a hamster sings goes out.

  check_ham.py notes LOG WANT [STEP_MS]   the note-ons on channel 1, in order, are WANT (comma separated); with
                                          STEP_MS: the first sixteen that far apart (+- 12 ms)
  check_ham.py peak WAV MAX               the sound's highest sample is under MAX (of full scale) and it is not silent
"""
import re
import sys

import numpy as np

sys.path.insert(0, __file__.rsplit("/", 3)[0] + "/tools")
from features import read_wav  # noqa: E402


def main():
    if sys.argv[1] == "notes":
        ev = [(int(m[1]), int(m[2])) for m in re.finditer(r"^\s*(\d+) ms  MIDI out 90 (\d+) \d+", open(sys.argv[2]).read(), re.M)]
        want = [int(v) for v in sys.argv[3].split(",")]
        got = [n for _, n in ev][:len(want)]
        ok = got == want
        if ok and len(sys.argv) > 4:
            step = int(sys.argv[4])
            t = [a for a, _ in ev][:16]
            ok = all(abs((b - a) - step) <= 12 for a, b in zip(t, t[1:]))
        print(f"notes {got}: {'ok' if ok else 'FAIL, want ' + str(want)}")
        return 0 if ok else 1
    if sys.argv[1] == "peak":
        _, x = read_wav(sys.argv[2])
        pk = float(np.abs(x).max())
        ok = 0.02 < pk < float(sys.argv[3])
        print(f"peak {pk:.3f}: {'ok' if ok else 'FAIL'}")
        return 0 if ok else 1
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main())
