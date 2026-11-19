#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Measure FM-1 Clock against this computer's clock, live, and calibrate it: the FM-1 on USB, FM-1 Clock on it.

  python3 tools/calibrate.py                    measure until Ctrl-C, a line a second; then what it found
  python3 tools/calibrate.py --minutes 30       measure for 30 minutes (10 give about 0.2 ppm, an hour ~0.05)
  python3 tools/calibrate.py --set-time         first set the FM-1 to this computer's time (as tools/settime.py)
  python3 tools/calibrate.py --apply [--yes]    and at the end write the trim it found (it asks, without --yes)
  python3 tools/calibrate.py --trim N           set the trim to N crystal ticks a half second, and stop (0: none)
  python3 tools/calibrate.py --status           one report: the FM-1's time, its trim, the computer's time
  python3 tools/calibrate.py --log FILE.csv     every sample, to look at later
  python3 tools/calibrate.py --simulate PPM     against a simulated FM-1 whose crystal is PPM off (no MIDI, quick)
  [--port NAME] (a part of the port's name; without it the FM-1's: "Felucca" over USB, or "FM-1"), [--list]

The same as tools/settime.py needs: pip3 install mido python-rtmidi. The computer's clock is the reference: let it
keep its time from the network (NTP, "set time automatically"), as computers do.

How: the FM-1 counts its 24 MHz crystal (TIMER4) and its time comes from it alone. Every half second this asks it
for the time over MIDI (CC 29 on channel 16) and it answers at once with the crystal's count, its time of day and
its trim (the reply: CC 29 .. 43, firmware/src/fm1clock.c time_report). Each answer is put at the middle of the
round trip, the slow round trips are left out (as NTP does), and a straight line through the crystal's counts
against the computer's time is the crystal's real frequency: how many ppm it is off, and how many seconds a day
the clock gains or loses. The trim that cancels it is 12 crystal ticks a half second for each ppm (12 000 000
ticks a half second as it says on the crystal), +-8191 at most; the FM-1 keeps it with its settings (CC 23, 24).
"""
import argparse
import math
import random
import re
import statistics
import sys
import threading
import time

F_NOM = 24_000_000                               # the crystal, as it says on it
HALF = F_NOM // 2
TRIM_MAX = 8191
CH = 15                                          # MIDI channel 16 (mido counts from 0)
FM1_PORT = re.compile(r"felucca|fm-1", re.I)     # (the FM-1 says "Felucca" over USB: SLOOP's / Felucca's name)


class Estimate:
    """the samples so far and what they say: the crystal's ppm, the clock's offset from the computer's and its rate"""

    def __init__(self):
        self.s = []                              # (host time s, crystal ticks unwrapped, round trip s, offset s, trim)
        self.raw0 = self.raw = None
        self.ticks = 0

    def add(self, t_host, raw_t4, rtt, offset, trim):
        if self.raw is None:
            self.raw0 = self.raw = raw_t4
            self.t0 = t_host
        else:                                    # the crystal's 32 bits wrap every 179 s: unwrapped by the host's time
            want = (t_host - self.s[-1][0]) * F_NOM
            d = (raw_t4 - self.raw) % (1 << 32)
            d += round((want - d) / (1 << 32)) * (1 << 32)
            self.ticks += d
            self.raw = raw_t4
        self.s.append((t_host, self.ticks, rtt, offset, trim))

    def good(self):
        """the samples whose round trip is among the quicker half (the slow ones waited for the FM-1's main loop)"""
        if len(self.s) < 8:
            return self.s
        cut = statistics.median(x[2] for x in self.s)
        return [x for x in self.s if x[2] <= cut]

    @staticmethod
    def fit(xs, ys):
        """least squares: slope, its standard error, intercept"""
        n = len(xs)
        mx, my = sum(xs) / n, sum(ys) / n
        sxx = sum((x - mx) ** 2 for x in xs)
        if n < 3 or sxx <= 0:
            return None
        b = sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / sxx
        a = my - b * mx
        res = [y - (a + b * x) for x, y in zip(xs, ys)]
        se = math.sqrt(sum(r * r for r in res) / (n - 2) / sxx)
        return b, se, a

    def result(self):
        g = self.good()
        if len(g) < 3:
            return None
        t = [x[0] - self.t0 for x in g]
        f = self.fit(t, [x[1] for x in g])
        if f is None:
            return None
        hz, hz_se, _ = f
        ppm = (hz / F_NOM - 1) * 1e6
        o = self.fit(t, [x[3] for x in g])
        trim_now = g[-1][4]
        return {
            "span": t[-1] - t[0], "n": len(self.s), "used": len(g),
            "rtt_min": min(x[2] for x in self.s), "rtt_med": statistics.median(x[2] for x in self.s),
            "ppm": ppm, "ppm_se": hz_se / F_NOM * 1e6,
            "trim": max(-TRIM_MAX, min(TRIM_MAX, round(ppm * HALF / 1e6))), "trim_now": trim_now,
            "offset": g[-1][3], "rate": o[0] * 1e6 if o else float("nan"),
            "left": ppm - trim_now * 1e6 / HALF,     # what the clock is still off by, with the trim it has
        }


def decode(cc):
    """a whole reply (CC 30 .. 43) -> crystal, time of day in half seconds, ticks into the half, trim"""
    t4 = sum(cc[30 + i] << (7 * i) for i in range(5)) & 0xFFFFFFFF
    tod = sum(cc[35 + i] << (7 * i) for i in range(3))
    sub = sum(cc[38 + i] << (7 * i) for i in range(4))
    trim = (cc[42] << 7 | cc[43]) - 8192
    return t4, tod, sub, trim


def fm1_seconds(tod, sub, trim):
    """the FM-1's time of day in seconds, its half seconds and the ticks into the one it is in"""
    return tod / 2 + sub / (2 * (HALF + trim))


def local_seconds(t_wall):
    """this computer's local time of day in seconds, at t_wall (time.time())"""
    lt = time.localtime(t_wall)
    return (lt.tm_hour * 3600 + lt.tm_min * 60 + lt.tm_sec + (t_wall % 1)) % 86400


def wrap(d):
    return (d + 43200) % 86400 - 43200


def line(r):
    if not r:
        return "measuring ..."
    return (f"{r['span'] / 60:6.1f} min  {r['used']:5d}/{r['n']:<5d} round trip {r['rtt_min'] * 1e3:4.1f}/"
            f"{r['rtt_med'] * 1e3:4.1f} ms   crystal {r['ppm']:+8.3f} ppm (+-{r['ppm_se']:.3f}) = {r['ppm'] * 0.0864:+6.2f} s/day"
            f"   clock {r['offset'] * 1e3:+9.1f} ms off, {r['left'] * 0.0864:+6.2f} s/day with trim {r['trim_now']:+d}"
            f"   -> trim {r['trim']:+d}")


def summary(r):
    if not r:
        return "Too few answers to say anything."
    out = [f"After {r['span'] / 60:.1f} minutes, {r['used']} of {r['n']} answers (round trips {r['rtt_min'] * 1e3:.1f} ms "
           f"at the quickest, {r['rtt_med'] * 1e3:.1f} ms typical):",
           f"  the crystal is {r['ppm']:+.3f} ppm off (+-{r['ppm_se']:.3f}): untrimmed the clock "
           f"{'gains' if r['ppm'] > 0 else 'loses'} {abs(r['ppm']) * 0.0864:.2f} s a day",
           f"  with the trim it has now ({r['trim_now']:+d}) it {'gains' if r['left'] > 0 else 'loses'} "
           f"{abs(r['left']) * 0.0864:.2f} s a day; it is {r['offset'] * 1e3:+.1f} ms off the computer's time now",
           f"  the trim for it: {r['trim']:+d} crystal ticks a half second (leaves {abs(r['ppm'] - r['trim'] / 12) * 0.0864:.3f} "
           f"s a day)"]
    if r["ppm_se"] > 0.5:
        out.append("  (measure longer for a trim worth writing: the uncertainty is still over 0.5 ppm)")
    return "\n".join(out)


# ---- the FM-1 over MIDI
class FM1:
    def __init__(self, want):
        import mido
        self.mido = mido
        outs, ins = mido.get_output_names(), mido.get_input_names()
        pick = lambda names: [n for n in names if (want.lower() in n.lower() if want else FM1_PORT.search(n))]
        po, pi = pick(outs), pick(ins)
        if not po or not pi:
            raise SystemExit(f"no MIDI port {'with ' + repr(want) + ' in its name' if want else 'of the FM-1 (Felucca, FM-1)'}; "
                             f"outputs {outs}, inputs {ins}")
        self.name = po[0]
        self.lock = threading.Lock()
        self.cc, self.got, self.seq = {}, {}, -1
        self.out = mido.open_output(po[0])
        self.inp = mido.open_input(pi[0], callback=self.on_msg)

    def on_msg(self, m):
        t = time.time()
        if m.type != "control_change" or m.channel != CH:
            return
        with self.lock:
            if m.control == 29:
                self.cc = {29: m.value}
            elif 30 <= m.control <= 43 and 29 in self.cc:
                self.cc[m.control] = m.value
                if m.control == 43 and all(k in self.cc for k in range(30, 44)):
                    self.got[self.cc[29]] = (t, dict(self.cc))
                    self.cc = {}

    def ask(self, seq, timeout=1.0):
        """one report: (host time at the middle of the round trip, round trip, crystal, tod, sub, trim), or None"""
        with self.lock:
            self.got.pop(seq, None)
        t0 = time.time()
        self.out.send(self.mido.Message("control_change", channel=CH, control=29, value=seq))
        while time.time() - t0 < timeout:
            with self.lock:
                if seq in self.got:
                    t1, cc = self.got.pop(seq)
                    return ((t0 + t1) / 2, t1 - t0, *decode(cc))
            time.sleep(0.0005)
        return None

    def set_trim(self, trim):
        v = max(-TRIM_MAX, min(TRIM_MAX, int(trim))) + 8192
        self.out.send(self.mido.Message("control_change", channel=CH, control=23, value=v >> 7))
        self.out.send(self.mido.Message("control_change", channel=CH, control=24, value=v & 0x7F))

    def set_time(self):
        t = time.time()
        time.sleep(1 - (t % 1) + 0.0005)        # the next whole second (as tools/settime.py)
        lt = time.localtime()
        for c, v in ((20, lt.tm_hour), (21, lt.tm_min), (22, lt.tm_sec)):
            self.out.send(self.mido.Message("control_change", control=c, value=v))
        return lt


class SimFM1:
    """an FM-1 whose crystal is ppm off, on a USB that takes 0.5 to 3 ms each way, now and then 40 ms (its main loop
    drawing): for --simulate, in simulated time"""

    def __init__(self, ppm, trim=0, seed=1):
        self.ppm, self.trim, self.rng = ppm, trim, random.Random(seed)
        self.t = time.time()
        self.start = self.t
        self.tod0 = local_seconds(self.t) * 2      # it was set to the computer's time at the start

    def crystal(self, t):
        return (t - self.start) * F_NOM * (1 + self.ppm * 1e-6)

    def ask(self, seq, timeout=1.0):
        self.t += 0.5
        up = self.rng.uniform(0.0005, 0.003) + (0.04 if self.rng.random() < 0.05 else 0)
        down = self.rng.uniform(0.0005, 0.003)
        ta = self.t + up                            # when the FM-1 answers
        ticks = self.crystal(ta)
        halves = ticks / (HALF + self.trim)
        tod = (self.tod0 + int(halves)) % 172800
        sub = int((halves % 1) * (HALF + self.trim))
        return (self.t + (up + down) / 2, up + down, int(ticks) & 0xFFFFFFFF, int(tod), sub, self.trim)


def measure(dev, minutes, log=None, live=True, interval=0.5):
    est, seq, t_end = Estimate(), 0, (time.time() + minutes * 60 if minutes else None)
    last_print, steps, wall_mono = 0.0, 0.0, None
    simulated = isinstance(dev, SimFM1)
    n_sim = int(minutes * 60 / interval) if simulated else None
    try:
        while True:
            if simulated:
                if len(est.s) >= n_sim:
                    break
            elif t_end and time.time() >= t_end:
                break
            r = dev.ask(seq)
            seq = (seq + 1) % 128
            if r is None:
                continue
            t_mid, rtt, t4, tod, sub, trim = r
            if not simulated:                    # a step of the computer's clock (NTP set it): left out of the line
                wm = time.time() - time.monotonic()
                if wall_mono is not None and abs(wm - wall_mono) > 0.02:
                    steps += wm - wall_mono
                wall_mono = wm
            off = wrap(fm1_seconds(tod, sub, trim) - local_seconds(t_mid))
            est.add(t_mid - steps, t4, rtt, off, trim)
            if log:
                log.write(f"{t_mid:.6f},{rtt * 1e3:.3f},{t4},{tod},{sub},{trim},{off * 1e3:.3f}\n")
            if live and (simulated or time.time() - last_print >= 1.0):
                last_print = time.time()
                if not simulated:
                    print("\r" + line(est.result()), end="", flush=True)
            if not simulated:
                time.sleep(max(0.0, interval - rtt))
    except KeyboardInterrupt:
        pass
    if live and not simulated:
        print()
    return est.result()


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--minutes", type=float, help="measure this long (default: until Ctrl-C)")
    ap.add_argument("--set-time", action="store_true", help="set the FM-1 to this computer's time first")
    ap.add_argument("--apply", action="store_true", help="write the trim found at the end")
    ap.add_argument("--yes", action="store_true", help="(with --apply) without asking")
    ap.add_argument("--trim", type=int, help="set the trim (crystal ticks a half second) and stop")
    ap.add_argument("--status", action="store_true", help="one report and stop")
    ap.add_argument("--log", help="a CSV of every sample")
    ap.add_argument("--port", help="a part of the MIDI port's name")
    ap.add_argument("--list", action="store_true", help="the MIDI ports")
    ap.add_argument("--simulate", type=float, metavar="PPM", help="a simulated FM-1, its crystal PPM off (no MIDI)")
    ap.add_argument("--check", action="store_true", help="(with --simulate) fail unless it finds the PPM to 0.2 (the trim to 2)")
    a = ap.parse_args()

    if a.simulate is not None:
        r = measure(SimFM1(a.simulate), a.minutes or 20, live=False)
        print(summary(r))
        if a.check:
            want = max(-TRIM_MAX, min(TRIM_MAX, round(a.simulate * 12)))
            ok = r and abs(r["ppm"] - a.simulate) < 0.2 and abs(r["trim"] - want) <= 2   # (a trim tick: 0.083 ppm)
            print(f"simulate: {'ok' if ok else 'FAILED'} (found {r['ppm']:+.3f} ppm for {a.simulate:+.3f}, trim {r['trim']:+d})")
            return 0 if ok else 1
        return 0
    if a.list:
        import mido
        print("outputs:", mido.get_output_names())
        print("inputs: ", mido.get_input_names())
        return 0
    dev = FM1(a.port)
    print(f"{dev.name}")
    if a.trim is not None:
        dev.set_trim(a.trim)
        time.sleep(0.2)
        r = dev.ask(1)
        print(f"trim set: {r[5]:+d}" if r else "no answer: is FM-1 Clock (with the calibration) on it?")
        return 0 if r and r[5] == max(-TRIM_MAX, min(TRIM_MAX, a.trim)) else 1
    if a.set_time:
        lt = dev.set_time()
        print(f"the FM-1 set to {lt.tm_hour:02d}:{lt.tm_min:02d}:{lt.tm_sec:02d}")
        time.sleep(0.5)
    r = dev.ask(0)
    if not r:
        print("no answer: is FM-1 Clock on it, a build with the calibration (CC 29 on channel 16)?")
        return 1
    t_mid, rtt, t4, tod, sub, trim = r
    fs = fm1_seconds(tod, sub, trim)
    print(f"the FM-1: {int(fs // 3600):02d}:{int(fs // 60 % 60):02d}:{fs % 60:06.3f}, trim {trim:+d}; the computer "
          f"{time.strftime('%H:%M:%S', time.localtime(t_mid))}; {wrap(fs - local_seconds(t_mid)) * 1e3:+.1f} ms apart; "
          f"round trip {rtt * 1e3:.1f} ms")
    if a.status:
        return 0
    print("measuring (Ctrl-C to stop) ...")
    log = open(a.log, "w") if a.log else None
    if log:
        log.write("host_time,round_trip_ms,crystal,tod_half_seconds,ticks_into_half,trim,offset_ms\n")
    res = measure(dev, a.minutes, log)
    if log:
        log.close()
    print(summary(res))
    if a.apply and res:
        if res["ppm_se"] > 0.5:
            print("not written: measure longer first")
            return 1
        if not a.yes and input(f"Write the trim {res['trim']:+d} to the FM-1? [y/N] ").strip().lower() not in ("y", "yes", "j", "ja"):
            return 0
        dev.set_trim(res["trim"])
        time.sleep(0.2)
        r = dev.ask(2)
        print(f"written: the FM-1's trim is {r[5]:+d} (it keeps it with its settings, 2 s on)" if r else "no answer after it")
    return 0


if __name__ == "__main__":
    sys.exit(main())
