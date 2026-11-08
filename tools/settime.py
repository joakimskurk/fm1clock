#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Set FM-1 Clock to this computer's time over USB-MIDI: CC 20 the hours, CC 21 the minutes, CC 22 the seconds (any
channel), the seconds sent the moment that second begins. The clock takes the time when the seconds come (to its
half second: the pendulum keeps its swing).

  python3 tools/settime.py [PORT]        (pip3 install mido python-rtmidi; PORT: a part of the port's name, "FM-1")
  python3 tools/settime.py --list
"""
import sys
import time


def main():
    import mido
    names = mido.get_output_names()
    if "--list" in sys.argv:
        print("\n".join(names))
        return 0
    want = sys.argv[1] if len(sys.argv) > 1 else "FM-1"
    match = [n for n in names if want.lower() in n.lower()]
    if not match:
        print(f"no MIDI output with {want!r} in its name; there are: {names}")
        return 1
    with mido.open_output(match[0]) as out:
        t = time.time()
        time.sleep(1 - (t % 1) + 0.0005)                # the next whole second
        lt = time.localtime()
        out.send(mido.Message("control_change", control=20, value=lt.tm_hour))
        out.send(mido.Message("control_change", control=21, value=lt.tm_min))
        out.send(mido.Message("control_change", control=22, value=lt.tm_sec))
        print(f"{match[0]}: {lt.tm_hour:02d}:{lt.tm_min:02d}:{lt.tm_sec:02d}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
