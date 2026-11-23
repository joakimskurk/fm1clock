#!/bin/sh
# SPDX-License-Identifier: GPL-3.0-only
# Hamster Piano's package in fm1-emu: 7 s of the real firmware. A hamster by hand at 4.5 s (E4), PLAY at 5 s, the
# Tromster at 6 s (SEQ), THALLHAMSTERGRINDCORE at 6.2 s (FX). Then, from its report, its sound and its screens:
#   - it sings: silence before the key, sound after it
#   - the audio interrupt's longest render (au_worst, read from RAM by its address) is under half of its time
#   - the screens: the logo's blue, a hamster's cream, the Tromster's page and the black logo of THALL at the end
#   tools/emu_hamster.sh build/hamsterpiano.fwsc     FM1_EMU: the fm1-emu binary (tools/emu_ci.sh builds it)
set -e
PKG="${1:-build/hamsterpiano.fwsc}"
EMU="${FM1_EMU:-$HOME/fm1-emu/target/release/fm1-emu}"
OUT=build/emu-ham
rm -rf "$OUT"
mkdir -p "$OUT/work"
cp "$PKG" "$OUT/pkg.fwsc"
ADDR=$(awk '$NF == "au_worst" { print $1 }' build/hamsterpiano.syms 2>/dev/null | head -1)
s0=$(date +%s)
(cd "$OUT" && timeout "${EMU_TIMEOUT:-1500}" "$EMU" --fwsc pkg.fwsc --ms 7000 --keys '4500-4700:n11,5000:PLAY,6000:SEQ,6200:FX' \
    --wav out.wav --snap 1000,4600,6900 ${ADDR:+--dump $ADDR 1} >report.txt 2>&1) || true
echo "emu_hamster: 7 s of Hamster Piano took $(( $(date +%s) - s0 )) s to emulate"
grep -E "in an ISR|^time " "$OUT/report.txt" | sed 's/^/  emu: /' || true
python3 - "$OUT" <<'PY'
import re, sys
import numpy as np
from PIL import Image
sys.path.insert(0, "tools")
from features import read_wav
out, fail = sys.argv[1], 0
def check(what, ok, got=""):
    global fail
    print(f"== {what}: {'ok' if ok else 'FAIL'} {got}")
    fail |= not ok
rep = open(out + "/report.txt").read()
fs, x = read_wav(out + "/out.wav")
x = x.mean(axis=1)
rms = lambda a, b: float(np.sqrt((x[int(a * fs):int(b * fs)] ** 2).mean()))
check("silent before the key", rms(1.0, 4.0) < 1e-4, f"{rms(1.0, 4.0):.5f}")
check("a hamster sings when its key is pressed", rms(4.3, 4.8) > 2e-3, f"{rms(4.3, 4.8):.4f}")
check("the pattern plays", rms(5.0, 6.0) > 2e-3, f"{rms(5.0, 6.0):.4f}")
check("the Tromster and THALL", rms(6.2, 6.8) > 2e-3, f"{rms(6.2, 6.8):.4f}")
m = re.search(r"dump 0x[0-9a-f]+ \(1 words\):\s+0x[0-9a-f]+: ([0-9a-f]+)", rep)
worst = int(m.group(1), 16) if m else 0
check("the longest render under half a block's time (139320 ticks)", 0 < worst < 69660, f"{worst} ticks, {worst * 100 // 139320} %")
px = lambda t, xy: Image.open(f"{out}/work/lcd_{t}.bmp").convert("RGB").getpixel(xy)
near = lambda a, b: all(abs(p - q) <= 12 for p, q in zip(a, b))
check("the logo's blue", near(px(1000, (3, 3)), (0x42, 0x6B, 0x7C)), px(1000, (3, 3)))
check("a hamster's cell", near(px(1000, (2, 28)), (0xF7, 0xEC, 0xD7)), px(1000, (2, 28)))
check("E sings: its note in pink", near(px(4600, (125, 88)), (0xD9, 0x5F, 0x67)), px(4600, (125, 88)))
check("the Tromster's page", near(px(6900, (230, 100)), (0x17, 0x31, 0x3F)), px(6900, (230, 100)))
check("THALL: the logo on black", sum(px(6900, (3, 3))) < 160, px(6900, (3, 3)))
print("emu_hamster: all passed" if not fail else "emu_hamster: FAILED")
sys.exit(fail)
PY
