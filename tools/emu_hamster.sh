#!/bin/sh
# SPDX-License-Identifier: GPL-3.0-only
# Hamster Synth's package in fm1-emu: 7 s of the real firmware. A hamster by hand at 4.5 s (E4), PLAY at 5 s, the
# Tromster at 6 s (SEQ), THALLHAMSTERGRINDCORE at 6.2 s (FX). Then, from its report, its sound and its screens:
#   - it sings: silence before the key, sound after it
#   - the audio interrupt's longest render (au_worst, read from RAM by its address) is under half of its time
#   - the screens: the logo's blue, a hamster's cream, the Tromster's page and the black logo of THALL at the end
# Then 12 s of the whole panel (below), each step checked on its screen
#   tools/emu_hamster.sh build/hamstersynth.fwsc     FM1_EMU: the fm1-emu binary (tools/emu_ci.sh builds it)
set -e
PKG="${1:-build/hamstersynth.fwsc}"
EMU="${FM1_EMU:-$HOME/fm1-emu/target/release/fm1-emu}"
OUT=build/emu-ham
rm -rf "$OUT"
mkdir -p "$OUT/work"
cp "$PKG" "$OUT/pkg.fwsc"
ADDR=$(awk '$NF == "au_worst" { print $1 }' build/hamstersynth.syms 2>/dev/null | head -1)
s0=$(date +%s)
(cd "$OUT" && timeout "${EMU_TIMEOUT:-1500}" "$EMU" --fwsc pkg.fwsc --ms 7000 --keys '4500-4700:n11,5000:PLAY,6000:SEQ,6200:FX' \
    --wav out.wav --snap 1000,4600,6900 ${ADDR:+--dump $ADDR 1} >report.txt 2>&1) || true
echo "emu_hamster: 7 s of Hamster Synth took $(( $(date +%s) - s0 )) s to emulate"
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
sys.exit(fail)
PY
fail=$?

# the panel, all of it, on the real package: REC (C4, E4, SEL a rest), the cursor back, EDIT with the knobs and OCT-,
# the tempo, the patterns, PLAY, the Tromster (A3 its hat, KNOB 3 its voices), THALL, GLO held (the song's page), FX
# held (the voice), HOME held (help), stop, the drums by hand
mkdir -p "$OUT/panel/work"
s0=$(date +%s)
(cd "$OUT/panel" && timeout "${EMU_TIMEOUT:-1500}" "$EMU" --fwsc ../pkg.fwsc --ms 12000 --keys \
    '1000:REC,1200-1320:n7,1500-1620:n11,1800:SCL,2300:REC,2400:SELECT:-2,2600:EDIT,2800:K1:+1,3000:K4:+2,3200:OCTDN,3500:EDIT,3700:ALGO:+5,3900:PRESETS:+1,4100:PRESETS:-1,4300:PLAY,5300:SEQ,5600-5700:n4,5800:K3:+3,6200:HOME,6400:FX,7500:FX,7700-8500:GLO,8700:HOME,8900-9600:FX,9900-10600:HOME,10900:HOME,11100:PLAY,11300-11400:n8,11600-11700:n10' \
    --wav out.wav --snap 2100,3400,6000,7400,8600,10700,11900 >report.txt 2>&1) || true
echo "emu_hamster: 12 s of its panel took $(( $(date +%s) - s0 )) s to emulate"
python3 - "$OUT/panel" "$fail" <<'PY'
import sys
from PIL import Image
out, fail = sys.argv[1], int(sys.argv[2])
def check(what, ok, got=""):
    global fail
    print(f"== {what}: {'ok' if ok else 'FAIL'} {got}")
    fail |= not ok
px = lambda t, xy: Image.open(f"{out}/work/lcd_{t}.bmp").convert("RGB").getpixel(xy)
near = lambda a, b: all(abs(p - q) <= 12 for p, q in zip(a, b))
CELL, NOTE, NOTE_BEAT = (0x1D, 0x3A, 0x48), (0x2C, 0x4B, 0x59), (0x34, 0x56, 0x65)   # (ham_draw.h C_STEP0, C_STEP1, C_STEP1B)
PINK2, YELLOW, INK2 = (0xD9, 0x5F, 0x67), (0xFF, 0xD7, 0x4B), (0x17, 0x31, 0x3F)
check("REC: C4 into step 8", near(px(2100, (226, 180)), NOTE), px(2100, (226, 180)))
check("REC: E4 into step 9 (on a beat)", near(px(2100, (24, 196)), NOTE_BEAT), px(2100, (24, 196)))
check("REC: SEL, a rest in step 10", near(px(2100, (52, 196)), CELL), px(2100, (52, 196)))
check("REC: the bar says so (the sign made way)", near(px(2100, (200, 214)), PINK2), px(2100, (200, 214)))
check("EDIT: the bar says so", near(px(3400, (200, 214)), YELLOW), px(3400, (200, 214)))
check("SEQ: the Tromster's page", near(px(6000, (230, 100)), INK2), px(6000, (230, 100)))
check("FX: THALL, the logo on black", sum(px(7400, (3, 3))) < 160, px(7400, (3, 3)))
check("GLO held: the song's page", near(px(8600, (230, 100)), INK2), px(8600, (230, 100)))
check("HOME held: help", near(px(10700, (230, 100)), INK2), px(10700, (230, 100)))
check("PLAY again: stopped, home", near(px(11900, (2, 28)), (0xF7, 0xEC, 0xD7)) or near(px(11900, (2, 28)), (0xFF, 0xF3, 0xDD)), px(11900, (2, 28)))
print("emu_hamster: all passed" if not fail else "emu_hamster: FAILED")
sys.exit(fail)
PY
