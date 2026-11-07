#!/bin/sh
# SPDX-License-Identifier: GPL-3.0-only
# FM1 Clock's package in fm1-emu: 6 s of the real firmware. SEQ at 0.5 s (the operators on the screen), PLAY at
# 2.5 s (the repeat: it strikes ten). Then, from its report, its sound and its screens (build/emu/):
#   - the interrupts' share of the chip (the engine fills it to its governor's target, the platform's on top)
#   - the governor's carriers and the worst block (the engine's state, read from RAM by its address)
#   - a tick on every half second, left and right in turn; the first blow 40 ms after PLAY's click
#   - the pendulum swings (two screens 250 ms apart), the hands at 10:10
#   tools/emu_check.sh build/fm1clock.fwsc        FM1_EMU: the fm1-emu binary (tools/emu_ci.sh builds it)
set -e
PKG="${1:-build/fm1clock.fwsc}"
EMU="${FM1_EMU:-$HOME/fm1-emu/target/release/fm1-emu}"
OUT=build/emu
P=tests/clk/check_clock.py
rm -rf "$OUT"
mkdir -p "$OUT/work"
cp "$PKG" "$OUT/pkg.fwsc"
ADDR=$(awk '$NF == "eng_st" { print $1 }' build/fm1clock.syms 2>/dev/null | head -1)
s0=$(date +%s)
(cd "$OUT" && timeout "${EMU_TIMEOUT:-1200}" "$EMU" --fwsc pkg.fwsc --ms 6000 --keys '500:SEQ,2500:PLAY' \
    --wav out.wav --snap 1000,1250,4000 ${ADDR:+--dump $ADDR 5} >report.txt 2>&1) || true
echo "emu_check: 6 s of the clock took $(( $(date +%s) - s0 )) s to emulate"
grep -E "in an ISR|^time |^dump| 0x" "$OUT/report.txt" | sed 's/^/  emu: /' || true
fail=0
run() { echo "== $1"; shift; "$@" || fail=1; }
run "the chip: the interrupts take 60 .. 95 % of it" python3 $P isr "$OUT/report.txt" 60 95
run "the engine: the governor's carriers, the worst block under 92 % of its time" python3 $P state "$OUT/report.txt" 92
run "a tick every half second, left and right in turn" python3 $P ticks "$OUT/out.wav" 1.4 5.9
run "PLAY: the first blow ~40 ms after the release click" python3 $P onset "$OUT/out.wav" 2.45 3.2 2.55
run "the pendulum swings" python3 $P moved "$OUT/work/lcd_1000.bmp" "$OUT/work/lcd_1250.bmp"
run "the hands at 10:10" python3 $P hands "$OUT/work/lcd_4000.bmp" 10 10
[ $fail = 0 ] && echo "emu_check: all passed" || { echo "emu_check: FAILED"; exit 1; }
