#!/bin/sh
# SPDX-License-Identifier: GPL-3.0-only
# Hamster Piano's sound demo: the firmware's own code (firmware/src/hamster.c, its engine and its screen) on this
# computer (tests/host.c) plays tests/scripts/ham/demo.txt with a song of four patterns (tests/ham/demo_song.h; the
# firmware itself starts as the page does). Out come, in build/demo/:
#   hamsterpiano-demo.wav   the sound, as the FM-1 sends it over USB (44.1 kHz, 16 bit), brought to -1 dBFS
#   hamsterpiano-demo.mp3   the same, 192 kbit/s                       (ffmpeg)
#   hamsterpiano-demo.mp4   with the screen, 3 x, 30 frames a second   (ffmpeg)
#   hamsterpiano-demo-side.mp3   the same demo in the page's voice, to hold against it
#   tools/ham_demo.sh [--no-video]
set -e
cd "$(dirname "$0")/.."
OUT=build/demo
rm -rf "$OUT"
mkdir -p "$OUT/frames"
cc -O2 -Wall -Wno-unused-function -DDINGHY_HOST -DAPP_VER='"demo"' -DHAM_DEMO='"../../tests/ham/demo_song.h"' \
    -Ifirmware/hal -Ifirmware/src -Ifirmware/gen -o "$OUT/hamsterpiano" firmware/src/hamster.c
if [ "$1" = --no-video ]; then
    "$OUT/hamsterpiano" "$OUT/frames/f" tests/scripts/ham/demo.txt >"$OUT/run.log"
else
    "$OUT/hamsterpiano" "$OUT/frames/f" tests/scripts/ham/demo.txt 30 >"$OUT/run.log"
fi
python3 - "$OUT/frames/f.wav" "$OUT/hamsterpiano-demo.wav" <<'PY'
import struct, sys
import numpy as np
d = open(sys.argv[1], "rb").read()
x = np.frombuffer(d[44:], dtype="<i2").astype(float)
g = 32767 * 10 ** (-1 / 20) / max(np.abs(x).max(), 1)
y = np.clip(np.round(x * g), -32767, 32767).astype("<i2")
open(sys.argv[2], "wb").write(d[:44] + y.tobytes())
print(f"demo: {len(x) / 2 / 44100:.1f} s, peak brought to -1 dBFS (x {g:.2f})")
PY
if command -v ffmpeg >/dev/null 2>&1; then
    ffmpeg -loglevel error -y -i "$OUT/hamsterpiano-demo.wav" -codec:a libmp3lame -b:a 192k \
        -metadata title="Hamster Piano (FM-1)" "$OUT/hamsterpiano-demo.mp3"
    if [ "$1" != --no-video ]; then
        ffmpeg -loglevel error -y -framerate 30 -i "$OUT/frames/f-%05d.ppm" -i "$OUT/hamsterpiano-demo.wav" \
            -vf scale=720:720:flags=neighbor -c:v libx264 -preset slow -crf 16 -pix_fmt yuv420p \
            -c:a aac -b:a 192k -shortest -movflags +faststart "$OUT/hamsterpiano-demo.mp4"
    fi
else
    echo "demo: no ffmpeg, the WAV only"
fi
if command -v ffmpeg >/dev/null 2>&1; then           # the page's voice, the sound only
    mkdir -p "$OUT/side"
    cc -O2 -Wall -Wno-unused-function -DDINGHY_HOST -DAPP_VER='"demo"' -DHAM_DEMO='"../../tests/ham/demo_song.h"' \
        -DHAM_DEMO_PAGE_VOICE -Ifirmware/hal -Ifirmware/src -Ifirmware/gen -o "$OUT/side/hamsterpiano" firmware/src/hamster.c
    "$OUT/side/hamsterpiano" "$OUT/side/f" tests/scripts/ham/demo.txt >/dev/null
    ffmpeg -loglevel error -y -i "$OUT/side/f.wav" -af "volume=$(python3 -c "
import numpy as np; d = open('$OUT/side/f.wav', 'rb').read(); x = np.frombuffer(d[44:], dtype='<i2')
print(f'{32767 * 10 ** (-1 / 20) / max(int(np.abs(x.astype(int)).max()), 1):.3f}')")" \
        -codec:a libmp3lame -b:a 192k -metadata title="Hamster Piano (FM-1), the page's voice" "$OUT/hamsterpiano-demo-side.mp3"
    rm -rf "$OUT/side"
fi
rm -rf "$OUT/frames"
ls -l "$OUT"/hamsterpiano-demo.*
