# FM1 Clock for the M-VAVE FM-1

Before we know it the FM-1 will be an almost forgotten treasure. So here is something that looks completely
useless now, and may one day turn out to be its only useful function: a clock.

Not just any clock. Its bell is a real 31-day pendulum wall clock striking its coil gong, taken apart into 742
ringing modes and rebuilt as an FM synthesiser of some four hundred operators, which keeps the whole chip busy every
frame, all day long. Turn ALGORITHM and there is a second one: **a cuckoo clock**, a painted chalet whose bird comes
out on the hour and calls on two FM pipes over a wire gong, fitted to a real Black Forest clock.

<p align="center"><img src="docs/screens/pendulum.gif" width="360" alt="The clock on the FM-1's screen: the hands at ten past ten, the pendulum swinging from side to side behind the glass">
<img src="docs/screens/cuckoo.gif" width="240" alt="The cuckoo clock at three o'clock: a painted chalet with a cream dial and a balcony of sawn boards; its door swings open, the bird comes out, bows and calls with its beak open, goes back in and the door shuts, while the pendulum swings behind the chains and their pine-cone weights"></p>

> **Status: 0.1, in progress.** Built and run in CI (in fm1-emu, the FM-1 emulator), the sound tested against the
> recordings on a computer, and now being tried on a real FM-1.

A [Dinghy 0.5](https://github.com/zvenson/dinghy) app, from the family of
[VaveHero](https://github.com/joakimskurk/fm1vavehero), [RoboSeq](https://github.com/joakimskurk/fm1roboseq) and
[SkurkyMello](https://github.com/joakimskurk/fm1mello).

## What it does

- **Two clocks, one time**, kept by the FM-1's crystal. ALGORITHM switches; the FM-1 remembers which.
- **The wall clock** ticks every half second (the tick from the left, the tock from the right), strikes the hours
  on its gong and once at the half hour. Turn the minute hand past the hour and it strikes, as a real clock does.
- **The cuckoo clock** calls the hours: its train warns, the door opens, the bird comes out, bows and calls, and goes
  in again. Its pendulum beats faster, and its pine-cone weights sink on their chains through the day.
- **Everything you hear is synthesised.** No sample of either recording is in the firmware.
- **The keys' lights** follow the pendulum, or flash the hours (also with the strike off: a silent clock you can
  read across the room). Playing the keys does nothing: this is a clock.

## Using it

| Control | What it does |
|---|---|
| **ALGORITHM** | The wall clock or the cuckoo clock. |
| **SELECT** | The minute hand, a minute a detent. Turned forward past the hour, it strikes it when you stop. |
| **PRESETS** | The hour hand, an hour a detent. |
| **SEL** | Rounds the time to the nearest minute (press it at :00 seconds). |
| **PLAY** | Strikes (or calls) the last hour again, even with the strike off. |
| **FX** | The strike on or off (SILENT on the screen). The cuckoo's door stays shut. |
| **GLO** | The keys' lights: SWING, HOURS or OFF. |
| **ENV** | Winds the cuckoo clock (it also winds itself when a weight reaches the bottom). |
| **HOME** | The time as digits beside the clock. |
| **SEQ** | How many FM operators are running, and how much of the chip they take. |
| **KNOB 1 / KNOB 2** | The ticks' and the strike's levels, 0–200 % of the recordings'. |
| **MIDI in** | CC 20, 21, 22 set the hours, minutes and seconds, on any channel. |

<p align="center"><img src="docs/screens/overlays.png" width="360" alt="The clock with its margins in use: 10:10 in digits on the left, TICK 125% on the right while the first knob turns, SILENT at the bottom right"></p>

**Setting the time.** The FM-1 has no battery-backed clock, so it starts at 10:10 and forgets the time when switched
off, as a pendulum clock stops when nobody winds it. Set it with SELECT and PRESETS, or from a computer:

```sh
pip3 install mido python-rtmidi
python3 tools/settime.py            # finds the MIDI port with "FM-1" in its name; --list shows the ports
```

The settings (the clock, the levels, the strike, the lights, the digits) are kept in flash.

## Install and try

**Install it from the browser:** [joakimskurk.github.io/fm1clock](https://joakimskurk.github.io/fm1clock/), in Chrome
or Edge on a computer, the FM-1 on USB. One button; it always offers the latest build that passed its tests.

**Try it without an FM-1:** download `packages` from a run under *Actions* on GitHub, unzip `fm1clock.fwsc`, and
open it in [fm1-emu](https://joakimeriksson.github.io/fm1-emu/) in a browser.

**Or install it** from a computer with Python, or with the [FM-1 Firmware Hub](https://thefirmwarehub.com) in Chrome
or Edge (which also takes you back to any other firmware):

```sh
python3 tools/fm1_install.py build/fm1clock.fwsc     # asks before it writes, then restarts into the clock
```

If anything goes wrong, hold **OCT−** while switching the FM-1 on: it starts in the USB rescue, where an installer
always works. Installing firmware is at your own risk.

**Build and test:**

```sh
make test     # the clock's tests on a computer: no FM-1, no toolchain (Python 3 with numpy and Pillow)
make fw       # the FM-1 package, build/fm1clock.fwsc (the JieLi toolchain and the AC79 SDK: docs/DINGHY_README.md)
make emu      # the package in fm1-emu
make host     # the app on a computer: build/host/fm1clock.wav and screenshots
python3 web/make_site.py build/fm1clock.fwsc VERSION build/site   # the web page with its installer
```

## How it is made

- **[The sound, and the engine](docs/SOUND.md):** the wall clock's recording taken apart into 742 modes and rebuilt
  as FM, its strike train, its tick and tock, the engine in integers and the governor that keeps the chip full.
  Every third of an octave of a strike is within about 1–2 dB of the recording.
- **[The cuckoo clock](docs/CUCKOO.md):** its own design, what moves, why its chains are not a counterweight, and its
  sound: the wire gong, the two pipes, the train's warning and rattle, and clicks made of a crack and noise.
- **[How it works](docs/HOW-IT-WORKS.md):** keeping time from the crystal, drawing the picture, the tests and CI,
  the web page and its installer, making the tables again, and what is where.

<p align="center"><img src="docs/screens/gong-spectrogram.png" width="820" alt="Two spectrograms side by side, the recording and FM1 Clock, the first five seconds after a strike, 0 to 6 kHz: the same series of partials and the same decay; the recording also shows its ticks as vertical lines and the room's noise"></p>

## Platform, licence and credits

- **Platform.** Dinghy 0.5 (zvenson), imported as source and left alone but for names ([PLATFORM.md](PLATFORM.md)),
  built on [Felucca](https://github.com/hugelton/Felucca) by Leo Kuroshita (Hügelton Instruments) and carried by
  [SLOOP](https://github.com/isod89/sloop-fm1) (isod89). The package's identity is `FM-1_94N` (N the minor version).
- **Licence.** GPL-3.0 ([LICENSE](LICENSE); who made what: [LICENSING.md](LICENSING.md)). The design
  (`assets/design.png`) is the author's; the cuckoo clock's is this firmware's own.
- **The recordings.** The wall clock's belongs to Adelaide Clocks; the cuckoo clock's is of a small Black Forest
  clock. Only measurements of them are here.
- **Thanks** to joakimeriksson for [fm1-emu](https://github.com/joakimeriksson/fm1-emu).
- **Trademarks.** "M-VAVE" and "FM-1" belong to their owners. This is a fan project, not an official M-VAVE product.
