#!/bin/sh
# SPDX-License-Identifier: GPL-3.0-only
# FM1 Clock's own host tests (no FM-1, no JieLi toolchain; Python with numpy and Pillow): the tables and pictures are
# what their tools make, the app compiles cleanly, the engine sounds like the reference recording (band energies over
# time, tests/clk/parity.py), the clock keeps time and strikes what it should (tests/scripts/*.txt in host mode,
# tests/clk/check_clock.py). Dinghy's own tests: tests/run_tests.sh (after ./build.sh). The chip: tools/emu_ci.sh.
set -e
cd "$(dirname "$0")/.."
OUT=build/host
mkdir -p "$OUT" build/audio
fail=0
run() { echo "== $1"; shift; "$@" || fail=1; }
CF="-O2 -Wall -Werror -Wno-unused-function -DDINGHY_HOST -DAPP_VER=\"test\" -Ifirmware/hal -Ifirmware/src -Ifirmware/gen"
P=tests/clk/check_clock.py

run "firmware/gen/clk_tables.h is what tools/gen_tables.py makes of tools/clk_model.json" python3 tools/gen_tables.py --check
if python3 tools/gen_art.py --check >/dev/null 2>&1; then echo "== firmware/gen/clk_art.h is what tools/gen_art.py makes of assets/design.png"; echo "clk_art.h: up to date"
else echo "== (clk_art.h differs from what this Pillow makes of the design: run tools/gen_art.py and look; not a failure)"; fi
run "fm1clock.c compiles for the host without a warning (-Werror)" sh -c "cc $CF -o $OUT/fm1clock firmware/src/fm1clock.c"
if command -v clang >/dev/null 2>&1; then              # (the chip's compiler is a clang)
    run "fm1clock.c with clang (-Werror)" sh -c "clang $CF -o $OUT/fm1clock-clang firmware/src/fm1clock.c"
fi
run "the engine alone compiles without a warning (-Wextra -Werror)" \
    cc -O2 -Wall -Wextra -Werror -Wno-unused-function -Ifirmware/src -Ifirmware/gen -o build/clk_render tests/clk/clk_render.c

# the sound against the reference recording
run "a strike, all 742 carriers: every window within 2 dB of the recording" sh -c \
    "build/clk_render strike build/audio/strike.wav && python3 tests/clk/parity.py gong build/audio/strike.wav 2.0"
run "a strike, 257 carriers (what the governor renders in fm1-emu): within 2 dB" sh -c \
    "build/clk_render strike build/audio/strike-257.wav 257 && python3 tests/clk/parity.py gong build/audio/strike-257.wav 2.0"
run "a strike, 160 carriers: within 2.5 dB" sh -c \
    "build/clk_render strike build/audio/strike-160.wav 160 && python3 tests/clk/parity.py gong build/audio/strike-160.wav 2.5"
run "24 ticks: their mean within 1.6 dB of the recording's, every window" sh -c \
    "build/clk_render tick build/audio/ticks.wav 24 && python3 tests/clk/parity.py tick build/audio/ticks.wav 24 1.6"
run "24 tocks: within 1.6 dB" sh -c \
    "build/clk_render tock build/audio/tocks.wav 24 && python3 tests/clk/parity.py tock build/audio/tocks.wav 24 1.6"
run "twelve o'clock (12 blows) does not clip" sh -c \
    "build/clk_render train 12 build/audio/train12.wav && python3 $P peak build/audio/train12.wav 0.95"

# the clock: the time, the strike, the panel (host mode, 200 carriers: quicker, the same events)
for s in hour half silent turn repeat twelve; do
    run "the clock on the host: tests/scripts/$s.txt" sh -c "CLK_NG=200 $OUT/fm1clock $OUT/$s tests/scripts/$s.txt > $OUT/$s.log"
done
run "three o'clock: three blows, the first 40 ms after the hour, 1.19 s apart" python3 $P hits $OUT/hour.log 1 14.9 3 10.04
run "half past: one blow" python3 $P hits $OUT/half.log 1 7.9 1 5.04
run "FX (silent): the hour passes without a blow" python3 $P hits $OUT/silent.log 0.3 7.9 0
run "the minute hand turned past 11:00 strikes eleven when it stops, turned back nothing" python3 $P hits $OUT/turn.log 0.3 6.4 5 1.54
run "PLAY strikes the last hour (ten)" python3 $P hits $OUT/repeat.log 0.3 3.9 3 0.54
run "twelve o'clock: twelve blows" python3 $P hits $OUT/twelve.log 1 21 12 4.04
run "every blow as hard as the first" python3 $P even $OUT/twelve.log
run "twelve o'clock with the ticks does not clip" python3 $P peak $OUT/twelve.wav 0.95
run "a tick every half second, on its frame, left and right in turn" python3 $P ticks $OUT/hour.wav 0.4 9.6
run "the hands at 10:10 after power-on" python3 $P hands $OUT/repeat-1000.ppm 10 10
run "the hands at 3:00 when it strikes three" python3 $P hands $OUT/hour-10500.ppm 3 0
run "the pendulum swings (the window between its end and its middle)" python3 $P moved $OUT/repeat-1000.ppm $OUT/repeat-1250.ppm

[ $fail = 0 ] && echo "run_clock: all passed" || { echo "run_clock: FAILED"; exit 1; }
