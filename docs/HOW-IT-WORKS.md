# How it works

[Back to the README](../README.md) · [The sound](SOUND.md) · [The cuckoo clock](CUCKOO.md)

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
- **The cuckoo's beat** is its own: 0.4286 s, as measured in its recording, the beat of a pendulum 18 cm long. The
  interrupt counts it from the same crystal, beside the half seconds, from the moment the cuckoo clock is chosen
  (its pendulum starts at one end), and puts each of its ticks on its frame the same way. The time of day, and so
  the hour and its strike, still come from the half seconds.

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
  The brass hub goes over them. Only the round the hands can reach goes to the screen, row by row, not the square
  round it: on the cuckoo clock the square's corners hold the windows' inner shutters, and sent again and again
  (unchanged) they flickered on the panel while the bird was out.
- **The pendulum** is drawn 50 times a second, in its window (78 × 56 pixels):
  - the back panel, darkened by the pendulum's own shadow, 3 px to the right and 2.5 px down (the light falls from
    the top left, as on the bob and on the glass), sampled four times for a soft edge;
  - the rod, a ruler-straight 6 px of brass with its colours across measured from the design;
  - the bob, cut out of the design with its shading as a 35 × 35 sprite with transparency, placed between pixels
    (bilinear) so it glides instead of jumping a pixel at a time;
  - over everything, the glass's reflections and the gold.
- **The cuckoo clock** is drawn the same way, in three regions of its own: the dial's middle each second, the
  door when it or the bird moves, and the space under the house (72 × 94 pixels) 50 times a second, where only the
  columns the pendulum touches now or touched last time are made again, unless a chain has run (see
  [What moves](CUCKOO.md#what-moves)).
- **The screen only takes data from RAM** (its DMA cannot read flash), so every picture is assembled in a RAM
  buffer and sent while the next is made.

| Memory | Used | Of |
|---|---|---|
| Code, tables and pictures of both clocks (flash) | 281 KB | 568 KB |
| RAM | 21 KB | 96 KB |
| Pool (big buffers: the sine table, the operators, the screen buffers, the cuckoo's layers) | 151 KB | 336 KB |

## The tests

**`make test`** (`tests/run_clock.sh`) checks:

- the tables are exactly what the model makes;
- the app compiles without a warning (gcc and clang, `-Werror`);
- the sound against the recordings, as in [the sound](SOUND.md#how-close-it-is) and
  [the cuckoo](CUCKOO.md#how-close-the-cuckoo-is): the wall clock's every window within 2 dB, its ticks within 1.6 dB; the cuckoo's gong within 3.5 dB, its calls within 6 dB over their first 0.5 s (with the 206
  carriers of the chip 5.5 and 6.5 dB), its ticks within 3 dB to 90 ms and its case's knock within 2 dB, its running
  train's drone and rattle within 2 dB; its tick, warning click, door opening and door shutting as measured, in
  eighths of an octave and in octaves over 1 ms, within 5 to 6 dB every window, and each as much like noise as the
  recording (its spectral flatness at least half of the recording's);
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
| `cuckoo.txt` | ALGORITHM, then 2:59:56: three calls, each a blow, the high pipe 0.11 s on (0.22 s the first), the low 0.19 s after it, 0.665 s apart, the first 0.87 s after the hour; a tick every 0.4286 s; the pendulum moves; at the hour the door is open and the bird out, after it the door is shut again; the hands at 3:00. |
| `cuckoo_silent.txt` | The cuckoo, FX and GLO (the keys on the hour): three o'clock without a call or a blow, the door shut, the keys flashing three times; at the half hour nothing. |

**CI** (`.github/workflows/build.yml`, using the shared `zvenson/fm1-build` workflow) builds the package on every
push and attests it, runs these tests and Dinghy's own platform tests, then builds fm1-emu and runs the package in
it for 6 seconds as the wall clock and 5 seconds as the cuckoo clock (`tools/emu_check.sh`):

- the interrupts' share of the chip;
- the governor's carriers (read out of the emulated RAM), and which clock is sounding;
- a tick every half second (every 0.4286 s);
- a blow after PLAY (the cuckoo's first 0.87 s after it, its warning and its door before it);
- the pendulum moving between two screenshots; the cuckoo's door open and the bird out while it calls;
- the hands at 10:10.

The figures in [Using the whole chip](SOUND.md#using-the-whole-chip) come from there. A tag `vX.Y` also publishes a
release.
## Making the tables again

| | |
|---|---|
| `make analyze REF=recording.wav` | Measures the wall clock's recording again (numpy, scipy): `tools/ref_model.json`, `tests/ref/features.json` |
| `make analyze-cuckoo REF=recording.wav` | Measures the cuckoo clock's: `tools/ref_cuckoo.json`, `tests/ref/cuckoo_features.json` |
| `make fit` | Fits both (about a minute each): `tools/clk_model.json`, `tools/clk_cuckoo.json`, then the tables |
| `make tables` | The models as integer tables: `firmware/gen/clk_tables.h` |
| `make art` | The design taken apart (`firmware/gen/clk_art.h`), and the cuckoo clock drawn (`firmware/gen/clk_art_cuckoo.h`) |

## What is where

| | |
|---|---|
| [firmware/src/fm1clock.c](../firmware/src/fm1clock.c) | The app: the time, the two clocks' trains and beats, the weights, the door, the panel, the keys' lights, MIDI, the settings |
| [firmware/src/clk_engine.h](../firmware/src/clk_engine.h) | The sound: the FM gongs, the pipes, the tick banks, the governor |
| [firmware/src/clk_draw.h](../firmware/src/clk_draw.h) | The pictures: the hands; the wall clock's pendulum behind the glass; the cuckoo's pendulum, chains, weights, door and bird |
| [firmware/gen/](../firmware/gen/) | The generated tables (`clk_tables.h`) and pictures (`clk_art.h`, `clk_art_cuckoo.h`) |
| [tools/analyze_ref.py](../tools/analyze_ref.py) | Measures the wall clock's recording: the modes, the strike train, the ticks |
| [tools/analyze_cuckoo.py](../tools/analyze_cuckoo.py) | Measures the cuckoo clock's: its gong, its pipes, its calls, its clicks |
| [tools/features.py](../tools/features.py) | How a sound is measured: band energies over time |
| [tools/fit_model.py](../tools/fit_model.py), [tools/fit_cuckoo.py](../tools/fit_cuckoo.py) | Fit the FM attacks, the pipes and the ticks to the measurements |
| [tools/gen_tables.py](../tools/gen_tables.py) | The models as integer tables |
| [tools/gen_art.py](../tools/gen_art.py) | The design without hands or pendulum, the window's layers, the bob |
| [tools/clicks.py](../tools/clicks.py) | The cuckoo's clicks (its tick, warning, door) measured and fitted: what comes back every time, and noise |
| [tools/gen_art_cuckoo.py](../tools/gen_art_cuckoo.py) | The cuckoo clock, drawn: the house, the door, the bird, the bob, a weight |
| [tools/settime.py](../tools/settime.py) | Sets the clock to the computer's time over MIDI |
| [tools/emu_ci.sh](../tools/emu_ci.sh), [tools/emu_check.sh](../tools/emu_check.sh) | The package in fm1-emu |
| [tests/run_clock.sh](../tests/run_clock.sh), [tests/clk/](../tests/clk/), [tests/scripts/](../tests/scripts/) | The tests |
| [assets/design.png](../assets/design.png) | The design |
| [PLATFORM.md](../PLATFORM.md) | Which Dinghy, and what is changed from it |
| [docs/API.md](API.md), [docs/RULES.md](RULES.md) | Dinghy's API and the chip's rules |
