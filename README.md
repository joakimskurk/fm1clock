# FM1 Clock for the M-VAVE FM-1

I predict that before we know it, the FM-1 will be an almost forgotten treasure. So I have made something that right
now looks completely useless, but may one day turn out to be its only useful function: a clock! And not just any
clock. The bell of this clock is the sound of a real 31-day BEACON pendulum wall clock striking its coil gong, taken
apart into 742 vibrating modes, each one measured for its pitch, its loudness, its phase and how long it rings, and
built up again as an FM synthesiser of over four hundred operators. That synthesiser keeps the whole chip busy, every
frame, all day long, whether it is striking or not. The tick and the tock are measured the same way and rebuilt from
64 operators each. The pendulum swings, it ticks at each end of its swing, and the clock keeps real time.

<p align="center"><img src="docs/screens/pendulum.gif" width="360" alt="The clock on the FM-1's screen: the hands at ten past ten, the pendulum swinging from side to side behind the glass"></p>

> **Status: 0.1, in progress.** The FM-1 package is built in CI and run there in fm1-emu, the FM-1 emulator. The
> sound is tested against the recording on a computer. It has not yet been tried on a real FM-1.

It is a [Dinghy 0.5](https://github.com/zvenson/dinghy) app, from the same family as
[VaveHero](https://github.com/joakimskurk/fm1vavehero), [RoboSeq](https://github.com/joakimskurk/fm1roboseq) and
[SkurkyMello](https://github.com/joakimskurk/fm1mello).

## Contents

- [What it does](#what-it-does)
- [Using it](#using-it)
- [How it keeps time](#how-it-keeps-time)
- [The sound](#the-sound)
  - [The recording](#the-recording)
  - [The coil gong](#the-coil-gong)
  - [Measuring the modes](#measuring-the-modes)
  - [From modes to FM](#from-modes-to-fm)
  - [The strike train](#the-strike-train)
  - [The tick and the tock](#the-tick-and-the-tock)
  - [How close it is](#how-close-it-is)
- [Using the whole chip](#using-the-whole-chip)
- [The engine, in integers](#the-engine-in-integers)
- [The picture](#the-picture)
- [Build, test, try, install](#build-test-try-install)
- [Making the tables again](#making-the-tables-again)
- [What is where](#what-is-where)
- [Platform, identity, licence and credits](#platform-identity-licence-and-credits)

## What it does

- **It keeps time.** It counts the FM-1's 24 MHz crystal, not the audio clock.
- **The pendulum swings and ticks.** It is a half-second pendulum: one full swing to and fro per second, and one
  click at each end of the swing, so a click every half second. The *tick* comes from the left, the *tock* from the
  right, as the pendulum is there.
- **It strikes the hours** on the gong: one blow at one o'clock, twelve at twelve, 1.19 s apart, every blow as hard
  as the first. **One blow at the half hour.**
- **It behaves like a real striking clock.** Turn the minute hand forward past the hour and it strikes that hour
  when you let go. A repeat button strikes the last hour again. A switch silences the strike.
- **The keys' lights follow the pendulum.** Playing the keys does nothing: this is a clock.
- **The screen** is the clock from the design, with hands and a pendulum that the firmware draws over it: the hands
  smooth-edged, the pendulum behind the glass with the glass's reflections over it and its own shadow on the wood
  behind it.

## Using it

| Control | What it does |
|---|---|
| **SELECT** (encoder) | Turns the minute hand, one minute a detent. Turned forward past the hour or the half hour, the clock strikes it half a second after you stop turning (as a real clock does when you move its hands). Turned back, it does not strike. |
| **ALGORITHM** (encoder) | Turns the hour hand, an hour a detent. |
| **SEL** | Rounds the time to the nearest whole minute. Press it when a clock you trust shows :00 seconds. |
| **PLAY** | Strikes the last full hour again (a *repeater*, as some old clocks have: useful in the dark). It strikes even when the strike is switched off. PLAY is lit while a strike runs. |
| **FX** | The strike on or off. FX is lit, and the screen says SILENT, while it is off. The ticking goes on. |
| **HOME** | The time as digits to the left of the clock, on or off. |
| **SEQ** | How many FM operators the chip is running right now, and how much of the audio's time they take (top right). |
| **KNOB 1** | The ticks' level, 0 to 200 % of the recording's, in steps of 6.25 %. |
| **KNOB 2** | The gong's level, the same way. |
| **MASTER** | The volume of everything (the platform's). |
| **MIDI in** (USB or the TRS jack) | Control change 20 sets the hours (0–23), 21 the minutes (0–59), 22 the seconds (0–59), on any channel. The time is set when the seconds arrive. `tools/settime.py` sends the computer's time, the seconds the moment that second begins. |
| **The keys** | Nothing. The white key under the pendulum's bob is lit and moves with it. (On the M-Vave SMK-37, which has no key lights, the pads do it in brass.) |

<p align="center"><img src="docs/screens/overlays.png" width="360" alt="The clock with its margins in use: 10:10 in digits on the left, TICK 125% on the right while the first knob turns, SILENT at the bottom right"></p>

**At power-on** the clock shows 10:10 (the time watchmakers set their hands to for photographs) and shows it as
digits for three seconds. The FM-1 has no battery-backed clock, so the time is lost when it is switched off, as a
pendulum clock stops when nobody winds it. Set it with SELECT and ALGORITHM, or from a computer:

```sh
pip3 install mido python-rtmidi
python3 tools/settime.py            # finds the MIDI port with "FM-1" in its name; --list shows the ports
```

**The settings are kept**: the two levels, the strike switch, the digits and the operator display are saved in the
FM-1's flash, two seconds after you change one, and only when the gong is still and between two ticks. Writing the
flash stops the sound for about 50 ms, and at that moment there is nothing to stop.

## How it keeps time

- **The time base is the crystal.** The FM-1's TIMER4 counts the 24 MHz crystal. Every 5.8 ms the audio interrupt
  takes what it has counted and turns it into half seconds (12,000,000 crystal ticks each). It does not count audio
  frames, so the clock is exactly as good as the crystal, typically within a couple of seconds a day.
- **Each tick lands on its exact frame.** When a half second falls inside the 256 frames the interrupt is about to
  render, it works out on which frame it falls (44,100 / 24,000,000 = 147 / 80,000 frames per crystal tick) and the
  tick starts there. If a half second ever slips between two blocks, its tick is played at the start of the next
  one: no tick is lost.
- **The pendulum follows the same clock.** Its angle is 8° × cos(π × half seconds since power-on), so it is at one
  end of its swing exactly when a tick sounds. The main loop reads the same counters (through a sequence number, so
  it never sees them half updated) and adds what the crystal has counted since.
- **The time of day** is the half seconds since power-on plus an offset that setting the hands changes. The
  pendulum never jumps when you set the time, because the offset is always whole half seconds; setting it over MIDI
  or with SEL is therefore exact to half a second.
- **Why half a second.** A pendulum that beats half seconds (a full swing to and fro each second) is 24.8 cm long.
  The pendulum in the design hangs about 24 cm from its suspension to the centre of its bob, if the clock is about
  60 cm tall: the design was already a half-second clock.

## The sound

Everything you hear is synthesised. No sample of the recording is in the firmware.

### The recording

*Clock Strike Chime Sound 31x Day BEACON Pendulum Wall Item 1125*, by Adelaide Clocks: 48 kHz, mono, 43 seconds,
low-passed at about 15.5 kHz. It is not in this repository (it is not ours to share). What is here are measurements
of it (`tools/ref_model.json`, `tests/ref/features.json`), made by `tools/analyze_ref.py`.

| Time | What is in it |
|---|---|
| 0–15.5 s | The clock ticking. Its tick and tock come 0.578 s and 0.511 s apart in turn: that clock is a little out of beat. FM1 Clock ticks evenly, every 0.5 s. |
| 15.65 s | **One strike, on its own** (a half hour). This is what the gong's model is measured from. |
| 25.6–37.5 s | **Eleven strikes** (eleven o'clock), 1.192 s apart. This is what the strike train is measured from. |

### The coil gong

A wall clock's "gong" is a coil of hardened steel wire, fixed at one end in a block on the back of the case. Struck
by a hammer, the wire bends and vibrates in many modes at once, each with its own frequency, and each one dies away
at its own rate: that is the gong's sound.

The measurement shows exactly that. The strong partials come in **two nearly equal series**: 267/270 Hz, 328/331,
394/398, 466/472, 543/551, 628/637, 716/727, 810/823 and on up. A wire coiled in a spiral bends a little differently
in its two directions, so each mode comes twice, a few hertz apart, and **the two beat against each other**: the
slow shimmer you hear while the gong rings. Within each series **the square root of the frequency climbs in even
steps** (about 1.76 √Hz a partial). That is how the bending modes of a stiff bar or wire are spaced (their
frequency grows with the square of their number), and not how a string or a pipe is spaced (they grow in
whole-number steps). That is why a gong sounds like a gong and not like a note.

<p align="center"><img src="docs/screens/gong-modes.png" width="820" alt="Left: the 742 measured modes as dots, level against frequency on a log scale, coloured by decay time: the long-ringing ones (seconds) below 2 kHz, the quick ones (tens of milliseconds) at the top. Right: the square root of the strong partials' frequencies against their order: a straight, climbing line of pairs"></p>

### Measuring the modes

A ringing mode is a *damped sinusoid*: a frequency, a level, a phase, and a decay (the level falls by e, about
8.7 dB, every τ seconds). The analysis finds all of them, like this:

1. **The hit.** The strike's exact moment is found in the recording (15.6503 s), and the window 0.06–5.2 s after it
   is taken: after the hammer's first crash, before the room's noise at 22 s.
2. **Bands.** For every 70 Hz from 150 Hz to 15 kHz, the signal is shifted down so that the band's centre sits at
   0 Hz (multiplied by a complex sinusoid), low-passed, and kept at only 400 samples a second. Each band is now a
   short, slow signal holding just the few modes within 35 Hz of its centre.
3. **Matrix pencil.** Each band is analysed with the *matrix pencil* method. A signal that is a sum of damped
   sinusoids has a special structure: shifted by one sample, it is the same sum with each sinusoid multiplied by a
   fixed complex number (its *pole*, which holds its frequency and its decay). The method stacks the signal into a
   matrix of shifted copies, finds the few directions that carry it (a singular value decomposition, keeping what
   is less than 45 dB under the strongest), and solves for the poles directly. Then the levels and phases follow by
   least squares. No guessing, no peak picking.
4. **What is kept.** The bands tile the spectrum, so no mode is found twice. 742 modes are kept, from 128 Hz to
   15 kHz. Many partials turn out to be **two poles at almost the same frequency with different decays**, for
   example the strongest, 551.4 Hz, falls with τ = 0.39 s and with τ = 2.1 s at once: a partial that drops quickly
   after the hit and then rings on. Both are kept.
5. **The tail.** The fit leans on the loud beginning. So afterwards, the decay times in each third of an octave are
   stretched a little (by 0.89–1.34) until the band's energy from 0.1 to 5 s matches the recording too.
6. **The ticks during the decay.** The recording keeps ticking while the gong rings. The analysis finds those ticks
   (above 8 kHz the gong is quiet after 0.2 s) and leaves them out of every measurement of the gong.

### From modes to FM

**FM synthesis** makes sound from *operators*: sine oscillators. A *carrier* is an operator you hear. A
*modulator* is an operator you do not hear: it pushes the carrier's phase back and forth. How far it pushes is the
*index*. With the index at zero the carrier is a pure sine. As the index rises, the carrier's energy spreads out
into *sidebands* above and below it, spaced by the modulator's frequency, and the sound gets brighter and harsher.
A classic FM bell uses a handful of operators at strange ratios and lets the index fall after the attack.

FM1 Clock does the same thing, at a much larger scale:

- **Every measured mode is a carrier**, at its own frequency, level, phase and decay: up to 742 carriers.
- **The 32 strongest have a modulator each.** Their index is high at the moment the hammer hits and falls within
  milliseconds, so that for an instant each of them spreads into sidebands: the crash of the hammer on the steel.
  A carrier's level may also be lifted for that moment. Each of the 32 is, in effect,

  `a · e^(−t/τ) · (1 + B·e^(−t/τI)) · sin(2πft + φ + I·e^(−t/τI) · sin(2π·r·f·t))`

  with its ratio *r* (from 0.1 to π), its index *I* (0 to 3 radians), the index's fall *τI* (4 to 60 ms) and the
  lift *B* chosen by searching (`tools/fit_model.py`: each operator in turn, every combination, three rounds), so
  that the first 100 ms have the recording's energy in every third of an octave. Before the search those first
  100 ms were 2.4 dB off on average; after it, 0.9 dB.

### The strike train

- **Timing.** The hammer strikes 1.192 s from blow to blow, as in the recording, varied by about ±1 % (±12 ms) from
  blow to blow, as a real clock's train is.
- **Strength.** Every blow is as hard as the first, varied by up to ±6 % from blow to blow. The recording's eleven
  strikes do get softer after the first two (0.85, then about 0.53 of the first, measured as the energy just after
  each blow minus the energy just before), but only because the phone recording them was moved further from the
  clock, so here they are balanced.
- **The release click.** About 40 ms before each blow there is a click: the strike train letting the hammer go. It
  is one of the tick sounds, softer.
- **A blow on a ringing gong.** A new blow adds to a gong that is still ringing. Each mode's new level is the sum of
  the old one and the new one with the phase between them unknown (|a + b| ≈ the larger + 3/8 of the smaller). If
  the gong is (almost) still, each mode starts from the phase it had in the recording, so a blow from rest is the
  recorded blow.

### The tick and the tock

The recording's 14 ticks and 14 tocks were lined up and measured separately (above 400 Hz; there is a hum in the
room below that). Each of the two sounds is rebuilt from **64 sine operators**:

- **The frequencies:** the 28 strongest peaks of its spectrum (the escapement's steel ringing, around 1.4, 1.8, 2.3,
  2.5 and 3.7 kHz), and 36 more spread from 330 Hz to 14.5 kHz to fill in between (the wooden case knocks too).
- **Two decays in every third of an octave:** the operators there take a short and a long decay in turn (the
  click falls fast, then the movement and the case ring on). Each band's two decays are picked from a grid by
  non-negative least squares against the recording's energy in that band over its first 35 ms.
- **The levels, all at once:** a window of a few milliseconds smears each operator's energy into the neighbouring
  bands, so all 64 levels are then fitted together, each operator with its own template (non-negative matrix
  factorisation updates).
- **The rise:** a tick is not instant. It rises as 1 − e^(−t/τa): τa = 4.0 ms for the tick, 5.5 ms for the tock.
- **No two alike:** each tick starts every operator at a random phase, a little off in pitch (±0.1 %) and level
  (±12 %), and the whole tick 0.92–1.04 of its level.
- **Where it comes from:** the tick is 4.6 dB louder on the left, the tock on the right.
- **One click on each side.** The recording has a softer second click 115 ms after each tock (the escape wheel
  settling). On the clock it made the tock sound double, so it is gone.

### How close it is

The engine is run on its own on a computer (`tests/clk/clk_render.c`, the firmware's own code), and its output is
measured the way the recording was: the energy in each third of an octave, 100 Hz to 16 kHz, in windows of time
after the hit, with the recording's ticks masked out and only the bands where the recording stands 6 dB over its
noise counted. The numbers are the root mean square of the differences over the bands, in dB
(`tests/clk/parity.py`).

| A strike | 0–20 ms | 20–50 | 50–100 | 0.1–0.2 s | 0.2–0.4 | 0.4–0.8 | 0.8–1.6 | 1.6–3.2 | 3.2–5 |
|---|---|---|---|---|---|---|---|---|---|
| all 742 carriers | 0.66 dB | 1.31 | 0.65 | 0.69 | 0.62 | 1.02 | 1.17 | 0.72 | 1.78 |
| 257 carriers (as on the chip) | 0.53 dB | 1.20 | 0.66 | 0.69 | 0.66 | 1.26 | 1.34 | 0.71 | 1.78 |
| 160 carriers | 0.53 dB | 0.98 | 0.94 | 1.16 | 0.86 | 1.73 | 1.59 | 0.70 | 1.86 |

| The mean of 24 | −2–4 ms | 4–10 | 10–20 | 20–35 |
|---|---|---|---|---|
| ticks | 1.31 dB | 0.93 | 1.15 | 1.23 |
| tocks | 0.95 dB | 0.96 | 1.15 | 1.16 |

A difference of 1 dB in a band is about the smallest change of loudness most people can hear.

<p align="center"><img src="docs/screens/gong-spectrogram.png" width="820" alt="Two spectrograms side by side, the recording and FM1 Clock, the first five seconds after a strike, 0 to 6 kHz: the same series of partials and the same decay; the recording also shows its ticks as vertical lines and the room's noise"></p>

## Using the whole chip

- **Every operator is computed in every frame, sounding or not.** Between the strikes the gong's carriers are
  still there, at a level of zero, and they still cost what they cost. That is the point: the chip is full all of
  the time.
- **A governor keeps it full and no fuller.** It measures each audio block's render against the crystal and
  renders as many of the gong's carriers (the strongest first, by their energy a²τ) as fit in **78 %** of the time
  a block has (256 frames, 5.8 ms). It cuts by up to a quarter at once if a block runs long, and adds back at most 8
  carriers a block.
- **Nothing is lost when it adapts.** The carriers it leaves out keep ringing down and keep their phase going, so a
  carrier taken back in continues where it would have been.
- **It adapts to the real chip.** On a real FM-1 the governor settles wherever the chip really is. SEQ shows the
  number.
- **The updater gets the chip.** When an update starts, the sound stops, so the installer is never slowed down.

**Measured in fm1-emu** (the real package, in CI):

| | |
|---|---|
| Gong carriers the governor renders | 257 of 742 (99.8 % of the gong's energy) |
| FM operators in all | 417: 257 carriers, 32 modulators, 2 × 64 tick operators, at 44.1 kHz |
| The engine's share of each audio block | 76.6 %, 77.7 % in the worst block |
| All interrupts, of the whole chip | 74.9 % (179.7 million instructions a second) |
| What is left | pendulum at 50 frames a second, hands, USB, panel |

On a computer the engine costs about 9.6 x86 instructions per carrier per frame and about 1470 per frame for the
two tick banks.

## The engine, in integers

The chip has no floating point unit, so everything is integers (`firmware/src/clk_engine.h`):

- **The sine** is a table of 16,384 values (Q15: −32,767 to 32,767) in RAM, made at power-on from a quarter wave
  in flash. An operator's phase is 32 bits, a full cycle being 2³², and its top 14 bits index the table.
- **A carrier** is four numbers: its phase, its phase step (frequency × 2³² / 44,100), its level (Q31 of full
  scale) and its decay, a multiplier applied every 16 frames (Q32). Its inner loop is: step the phase, look up the
  sine, multiply by the level, add.
- **A modulator** adds its own phase, step and index envelope. Its output, times the index, is added to the
  carrier's phase before the lookup: `SINT[(p + SINT[mp >> 18] · I) >> 18]`.
- **The tick banks**: two banks of 64 operators, so a tick can ring on while the next sound starts. Their levels
  step down every 4 frames (ticks fall fast) and their rise is applied every frame.
- **The mix** is in Q30 and is scaled by the two level knobs. The gong goes to both channels equally, each tick
  bank with its own left/right pan.
- **The levels:** the output is the recording's level × 2.3. A lone strike peaks at about 0.68 of full scale.
  Twelve blows at twelve o'clock, as the gong rings up and the ticks go on, peak at 0.82, so nothing clips.

## The picture

The screen is 240 × 240 pixels.

- **The background** is the design (`assets/design.png`, 1254 × 1254) scaled to the screen. Only the clock itself
  is stored (126 × 233 pixels, RGB565, 58 KB of flash). What the firmware draws over it is first taken out of the
  design, at the design's own resolution (`tools/gen_art.py`):
  - **The hands and the hub.** On the wood, the grey and dark pixels in a wide area round each hand are replaced
    by wood from the same column higher or lower, with one shift per column so that the vertical grain runs on
    unbroken; the disc's rim is turned round the hub instead. On the cream chapter ring, the tips are covered with
    cream from nearby. XII gets its strokes back by running them on down, and X by mirroring it through its own
    centre of symmetry, which was searched for.
  - **The pendulum.** The window behind it is split into a **back panel** (the wood) and a **front layer** (the
    gold scrollwork and frame, opaque, and the two reflections in the glass, partly transparent), so that the
    pendulum can swing between the two. The design painted the pendulum's shadow onto the wood round it, so there
    the back panel is built again from the wood away from it: each row's colour, each column's grain, the planks
    kept whole.
- **The hands** are drawn each second, at the exact angle (the minute hand moves on every second, not every
  minute). Each is two convex shapes, a shaft and a spear or arrow, filled with 4 × 4 samples per pixel for smooth
  edges, darker on one side and lighter on the other. Each has a soft shadow 1.2 px to the right and 1.6 px down.
  The brass hub goes over them.
- **The pendulum** is drawn 50 times a second, in its window (78 × 56 pixels):
  - the back panel, darkened by the pendulum's own shadow, 3 px to the right and 2.5 px down (the light falls from
    the top left, as on the bob and on the glass), sampled four times for a soft edge;
  - the rod, a ruler-straight 6 px of brass with its colours across measured from the design;
  - the bob, cut out of the design with its shading as a 35 × 35 sprite with transparency, placed between pixels
    (bilinear) so it glides instead of jumping a pixel at a time;
  - over everything, the glass's reflections and the gold.
- **The screen only takes data from RAM** (its DMA cannot read flash), so every picture is assembled in a RAM
  buffer and sent while the next is made.

| Memory | Used | Of |
|---|---|---|
| Code and pictures (flash) | 152 KB | 568 KB |
| RAM | 16 KB | 96 KB |
| Pool (big buffers: the sine table, the operators, the screen buffers) | 98 KB | 336 KB |

## Build, test, try, install

```sh
make test     # the clock's tests on a computer: no FM-1, no toolchain (Python 3 with numpy and Pillow)
make fw       # the FM-1 package, build/fm1clock.fwsc (the JieLi toolchain and the AC79 SDK: docs/DINGHY_README.md)
make emu      # the package in fm1-emu (tools/emu_ci.sh builds the emulator)
make host     # the app on a computer with Dinghy's own script: build/host/fm1clock.wav and screenshots
```

**`make test`** (`tests/run_clock.sh`) checks:

- the tables are exactly what the model makes;
- the app compiles without a warning (gcc and clang, `-Werror`);
- the sound against the recording, as in the tables above: every window within 2 dB, the ticks within 1.6 dB;
- and, running the whole app on a computer from scripts (`tests/scripts/`):

| Script | What must happen |
|---|---|
| `hour.txt` | Set to 2:59:50 over MIDI: three blows, the first 40 ms after three o'clock, 1.19 s apart; the hands at 3:00. |
| `half.txt` | Half past three: one blow. |
| `silent.txt` | FX first, then four o'clock: no blow. |
| `turn.txt` | The minute hand turned forward past 11:00: it strikes eleven when you stop; turned back: nothing more. |
| `repeat.txt` | PLAY: ten blows; the hands at 10:10; the pendulum moves. |
| `twelve.txt` | Twelve o'clock: twelve blows, every one as hard as the first, and nothing clips. |
| (all) | A tick every half second to within 3 ms, left and right in turn, and **nothing between two ticks**. |

**CI** (`.github/workflows/build.yml`, using the shared `zvenson/fm1-build` workflow) builds the package on every
push and attests it, runs these tests and Dinghy's own platform tests, then builds fm1-emu and runs the package in
it for 6 seconds (`tools/emu_check.sh`):

- the interrupts' share of the chip;
- the governor's carriers (read out of the emulated RAM);
- a tick every half second;
- a blow after PLAY;
- the pendulum moving between two screenshots;
- the hands at 10:10.

The figures in [Using the whole chip](#using-the-whole-chip) come from there. A tag `vX.Y` also publishes a
release.

**Try it without an FM-1:** download `packages` from a run under *Actions* on GitHub, unzip `fm1clock.fwsc`, and
open it in [fm1-emu](https://joakimeriksson.github.io/fm1-emu/) in a browser.

**Install it on an FM-1** over USB:

```sh
python3 tools/fm1_install.py build/fm1clock.fwsc     # asks before it writes, then restarts into the clock
```

You can also install it with the [FM-1 Firmware Hub](https://thefirmwarehub.com) in Chrome or Edge, which also takes
you back to any other firmware. If anything goes wrong: hold **OCT−** while switching the FM-1 on, and it starts in
the USB rescue, where an installer always works. Installing firmware is at your own risk.

## Making the tables again

| | |
|---|---|
| `make analyze REF=recording.wav` | Measures the recording again (numpy, scipy): `tools/ref_model.json`, `tests/ref/features.json` |
| `make fit` | Fits the FM attack and the tick banks (about a minute): `tools/clk_model.json`, then the tables |
| `make tables` | The model as integer tables: `firmware/gen/clk_tables.h` |
| `make art` | The design taken apart: `firmware/gen/clk_art.h` |

## What is where

| | |
|---|---|
| [firmware/src/fm1clock.c](firmware/src/fm1clock.c) | The app: the time, the strike train, the panel, MIDI, the settings |
| [firmware/src/clk_engine.h](firmware/src/clk_engine.h) | The sound: the FM gong, the tick banks, the governor |
| [firmware/src/clk_draw.h](firmware/src/clk_draw.h) | The picture: the hands, the pendulum and its shadow behind the glass |
| [firmware/gen/](firmware/gen/) | The generated tables (`clk_tables.h`) and pictures (`clk_art.h`) |
| [tools/analyze_ref.py](tools/analyze_ref.py) | Measures the recording: the modes, the strike train, the ticks |
| [tools/features.py](tools/features.py) | How a sound is measured: band energies over time |
| [tools/fit_model.py](tools/fit_model.py) | Fits the FM attack and the ticks to the measurements |
| [tools/gen_tables.py](tools/gen_tables.py) | The model as integer tables |
| [tools/gen_art.py](tools/gen_art.py) | The design without hands or pendulum, the window's layers, the bob |
| [tools/settime.py](tools/settime.py) | Sets the clock to the computer's time over MIDI |
| [tools/emu_ci.sh](tools/emu_ci.sh), [tools/emu_check.sh](tools/emu_check.sh) | The package in fm1-emu |
| [tests/run_clock.sh](tests/run_clock.sh), [tests/clk/](tests/clk/), [tests/scripts/](tests/scripts/) | The tests |
| [assets/design.png](assets/design.png) | The design |
| [PLATFORM.md](PLATFORM.md) | Which Dinghy, and what is changed from it |
| [docs/API.md](docs/API.md), [docs/RULES.md](docs/RULES.md) | Dinghy's API and the chip's rules |

## Platform, identity, licence and credits

- **Platform.** FM1 Clock runs on Dinghy 0.5 (zvenson), imported as source and left alone but for names (see
  [PLATFORM.md](PLATFORM.md)). Dinghy is built on [Felucca](https://github.com/hugelton/Felucca) by Leo Kuroshita
  (Hügelton Instruments) and its platform as [SLOOP](https://github.com/isod89/sloop-fm1) (isod89) carries it. It
  gives the updater, the USB rescue, MIDI, USB audio, the panel, the screen and the flash storage.
- **Identity.** The package's identity is `FM-1_94N`, where N is the minor version and 0 is a development build.
  94N is not in the list of taken identities that Dinghy keeps.
- **Licence.** The firmware is free software under the GPL-3.0 ([LICENSE](LICENSE); who made what is in
  [LICENSING.md](LICENSING.md)).
- **The design** (`assets/design.png`) is the author's.
- **The recording** belongs to Adelaide Clocks, and only measurements of it are here.
- **Thanks.** The emulator is [fm1-emu](https://github.com/joakimeriksson/fm1-emu) by joakimeriksson.
- **Trademarks.** "M-VAVE" and "FM-1" belong to their owners. This is a fan project, not an official M-VAVE product.
