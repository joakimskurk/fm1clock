#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""The calibration's MIDI, in host mode (tests/scripts/calib.txt): each time report (CC 29 .. 43 on channel 16) is
whole (read by tools/calibrate.py's own decoding) and carries the crystal as the host counts it (24 per microsecond); the trim set over CC 23, 24 is echoed;
and between the two reports the half seconds are the trimmed ones: half seconds x (12 000 000 + trim) + the ticks
into the half second = the crystal ticks gone by.

  python3 tests/clk/calib_check.py build/host/calib.log
"""
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tools"))
import calibrate                                 # (its own decoding of a reply, as it reads the FM-1)


def reports(log):
    cur, out = None, []
    for ms, st, d1, d2 in re.findall(r"^\s*(\d+) ms  MIDI out (\w\w) (\d+) (\d+)$", log, re.M):
        ms, d1, d2 = int(ms), int(d1), int(d2)
        if st != "BF":
            continue
        if d1 == 29:
            cur = {"ms": ms, "seq": d2, "cc": {}}
        elif cur is not None:
            cur["cc"][d1] = d2
            if d1 == 43:
                c = cur["cc"]
                if all(k in c for k in range(30, 44)):
                    cur["t4"], cur["tod"], cur["sub"], cur["trim"] = calibrate.decode(c)
                    out.append(cur)
                cur = None
    return out


def main():
    r = reports(open(sys.argv[1]).read())
    ok = len(r) == 2
    print(f"time reports: {len(r)} whole (want 2)")
    if not ok:
        return 1
    a, b = r
    for x in r:
        print(f"  {x['ms']} ms: seq {x['seq']}, crystal {x['t4']} (want {x['ms'] * 24000}), time of day "
              f"{x['tod'] // 7200:02d}:{x['tod'] // 120 % 60:02d}:{x['tod'] % 120 / 2:04.1f}, {x['sub']} ticks into the "
              f"half, trim {x['trim']}")
        ok &= x["t4"] == x["ms"] * 24000
    ok &= (a["seq"], a["trim"], b["seq"], b["trim"]) == (1, 0, 2, 6000)
    start = a["t4"] - a["sub"]                    # (the first report: still in the first half second)
    want = b["t4"] - start
    got = (b["tod"] - a["tod"]) * (12000000 + b["trim"]) + b["sub"]
    print(f"  the half seconds trimmed: {got} ticks gone by (want {want}; untrimmed it would read "
          f"{(b['tod'] - a['tod']) * 12000000 + b['sub']})")
    ok &= a["tod"] < b["tod"] and got == want
    print("calib: ok" if ok else "calib: FAILED")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
