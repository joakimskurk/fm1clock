#!/bin/sh
# SPDX-License-Identifier: GPL-3.0-only
# Hamster Synth's host tests (no FM-1, no JieLi toolchain; Python with numpy and Pillow): its tables and pictures are
# what their tools make, the app compiles cleanly, its engine sounds like the original web page (band energies over
# time against the page's own renders, tests/ham/parity.py), and the app does what its buttons say (scripts in host
# mode, read back from the notes it sends over MIDI). The chip: tools/emu_hamster.sh.
set -e
cd "$(dirname "$0")/.."
OUT=build/host
mkdir -p "$OUT" build/audio
fail=0
run() { echo "== $1"; shift; "$@" || fail=1; }
CF="-O2 -Wall -Wextra -Werror -Wno-unused-function -Wno-unused-parameter -Wno-sign-compare -Wno-missing-field-initializers -DDINGHY_HOST -DAPP_VER=\"test\" -Ifirmware/hal -Ifirmware/src -Ifirmware/gen"
P=tests/ham/check_ham.py

run "firmware/gen/ham_tables.h is what tools/gen_ham_tables.py makes" python3 tools/gen_ham_tables.py --check
run "firmware/gen/ham_art.h is what tools/gen_ham_art.py makes of tools/ham_sprites.py" python3 tools/gen_ham_art.py --check
run "hamster.c compiles for the host without a warning (-Wextra -Werror)" sh -c "cc $CF -o $OUT/hamstersynth firmware/src/hamster.c"
if command -v clang >/dev/null 2>&1; then
    run "hamster.c with clang (-Werror)" sh -c "clang $CF -o $OUT/hamstersynth-clang firmware/src/hamster.c"
fi
run "hamster.c for the SMK-37 (host)" sh -c "cc $CF -Wno-unused-variable -DBOARD_SMK37=1 -o $OUT/hamstersynth-smk37 firmware/src/hamster.c"
run "the engine alone compiles without a warning" \
    cc -O2 -Wall -Wextra -Werror -Wno-unused-function -Ifirmware/src -Ifirmware/gen -o build/ham_render tests/ham/ham_render.c

# the sound against the page's own (mean over thirds of an octave and 50 ms; the largest over octaves and 0.1 s)
par() {   # case, mean, worst
    python3 tests/ham/parity.py casefile "$1" build/audio/ham_case.txt && build/ham_render build/audio/ham_case.txt "build/audio/h_$1.wav" &&
        python3 tests/ham/parity.py cmp "$1" "build/audio/h_$1.wav" "$2" "$3"
}
run "a hamster, C: within 0.5 dB of the page" par ham_one0 0.5 1.5
run "the last hamster, the high C" par ham_one7 0.8 3.5
run "the pattern the page comes with" par ham_default 0.8 4
run "all eight, one after another" par ham_scale 0.8 4
run "glide, arpeggio, accent, ratchets, five octaves (ratchets of one note beat against each other: 12 dB)" par ham_fx 1.6 12
run "THALLHAMSTERGRINDCORE: a note" par thall_one0 1.0 1.5
run "THALL: the pattern, each note cutting the last off" par thall_default 1.0 5
run "THALL: glide, arpeggio, accent, ratchets" par thall_fx 1.2 3
run "the Tromster's first voices (noise is never twice the same: 2 dB)" par drums_v0 2.0 2.5
run "its second voices" par drums_v1 2.0 2.5
run "its third voices" par drums_v2 2.0 2.5
run "the hamsters and the Tromster together" par full_default 1.0 4

# the hamster voice (this firmware's own, the default): as loud as the page's, nothing clips; the hamster kit too
hv() {   # case, tolerance
    python3 tests/ham/parity.py casefile "$1" build/audio/ham_case.txt && echo "voice 1" >> build/audio/ham_case.txt &&
        build/ham_render build/audio/ham_case.txt "build/audio/hv_$1.wav" && python3 tests/ham/parity.py level "$1" "build/audio/hv_$1.wav" "$2"
}
run "the hamster voice: a note" hv ham_one0 2
run "the hamster voice: the page's pattern" hv ham_default 2
run "the hamster voice: glide, arpeggio, accent, ratchets (its accents squeak louder: 3 dB)" hv ham_fx 3
run "the hamster voice with the Tromster" hv full_default 2
run "the hamster kit (the drums' fourth voices) sounds and does not clip" sh -c \
    "printf 'bpm 120\ndrums 1\ndrum 0 0 17\ndrum 0 1 68\ndrum 0 2 85\ndrum 0 3 170\ndvoice 0 0 3\ndvoice 0 1 3\ndvoice 0 2 3\ndvoice 0 3 3\n' > build/audio/kit.txt &&
     build/ham_render build/audio/kit.txt build/audio/kit.wav && python3 $P peak build/audio/kit.wav 0.9"

# playing over what plays
run "the engine: THALL's two lines, no voice taken as it begins, a step skipped" sh -c \
    "cc -O2 -Wall -Wextra -Werror -Wno-unused-function -Ifirmware/src -Ifirmware/gen -o build/engine_test tests/ham/engine_test.c && build/engine_test"

# the app, by its buttons
A="48,64,67,64,52,67,64,62,53,67,69,72,55,71,67,62"
run "PLAY: the pattern A, a step every 250 ms, and round again" sh -c \
    "$OUT/hamstersynth $OUT/ham_play tests/scripts/ham/play.txt >$OUT/ham_play.log && python3 $P notes $OUT/ham_play.log $A,48 250 && python3 $P peak $OUT/ham_play.wav 0.9"
run "REC writes and moves on, SEL a rest, ENV undoes; the editor changes a step, its arpeggio and ratchet; then PLAY" sh -c \
    "$OUT/hamstersynth $OUT/ham_rec tests/scripts/ham/rec.txt >$OUT/ham_rec.log && python3 $P notes $OUT/ham_rec.log 60,64,79,48,69,69,69,69,69,69,64,67,64,52,67,64,60,64,69,72,55,71,67,62,69"
run "REC while it plays: a note into the step it was heard in (the nearest), not twice; SEL a rest; the next round plays them" sh -c \
    "$OUT/hamstersynth $OUT/ham_od tests/scripts/ham/overdub.txt >$OUT/ham_od.log && python3 $P notes $OUT/ham_od.log 48,64,67,64,52,67,64,62,53,67,69,72,55,71,71,67,79,48,64,67,64,52,67,64,62,53,67,69,72,71,67,79,48"
run "a song written on its page (AB), SONG on, PLAY: A's bar, then B's" sh -c \
    "$OUT/hamstersynth $OUT/ham_song tests/scripts/ham/song.txt >$OUT/ham_song.log && python3 $P notes $OUT/ham_song.log 72,$A,72"
run "a tour of its pages: the screens (build/host/ham_tour-*.png)" sh -c \
    "$OUT/hamstersynth $OUT/ham_tour tests/scripts/ham/tour.txt >$OUT/ham_tour.log && python3 $P peak $OUT/ham_tour.wav 0.98 && python3 - <<'PY'
from pathlib import Path
from PIL import Image
for p in sorted(Path('build/host').glob('ham_tour-*.ppm')):
    Image.open(p).resize((480, 480), Image.NEAREST).save(p.with_suffix('.png'))
    p.unlink()
PY"
[ $fail = 0 ] && echo "run_hamster: all passed" || { echo "run_hamster: FAILED"; exit 1; }
