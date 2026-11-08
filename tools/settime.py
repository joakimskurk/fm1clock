#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Set FM-1 Clock to this computer's time over USB-MIDI: CC 20 the hours, CC 21 the minutes, CC 22 the seconds (any
channel), the seconds sent the moment that second begins. The clock takes the time when the seconds come (to its
half second: the pendulum keeps its swing).

  python3 tools/settime.py [PORT]        (pip3 install mido python-rtmidi; PORT: a part of the port's name; without
                                          it, the FM-1's: "Felucca" over USB, as the platform names it, or "FM-1")
  python3 tools/settime.py --list
"""
import re
import sys
import time

FM1_PORT = re.compile(r"felucca|fm-1", re.I)     # (the FM-1 says "Felucca" over USB: SLOOP's / Felucca's name)


def main():
    import mido
    names = mido.get_output_names()
    if "--list" in sys.argv:
        print("\n".join(names))
        return 0
    want = sys.argv[1] if len(sys.argv) > 1 else None
    match = [n for n in names if (want.lower() in n.lower() if want else FM1_PORT.search(n))]
    if not match:
        print(f"no MIDI output {'with ' + repr(want) + ' in its name' if want else 'of the FM-1 (Felucca, FM-1)'}; "
              f"there are: {names}")
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
