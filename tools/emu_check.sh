#!/bin/sh
# SPDX-License-Identifier: GPL-3.0-only
# FM1 Clock's package in fm1-emu: 6 s of the real firmware. SEQ at 0.5 s (the operators on the screen), PLAY at
# 4.5 s (the repeat: it strikes ten; the ticks are checked before it, the gong's top end would hide them); then 5 s
# of the cuckoo clock (ALGORITHM, PLAY: it calls ten).
# Then, from its report, its sound and its screens (build/emu/):
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
(cd "$OUT" && timeout "${EMU_TIMEOUT:-1200}" "$EMU" --fwsc pkg.fwsc --ms 6000 --keys '500:SEQ,4500:PLAY' \
    --wav out.wav --snap 1000,1250,4000 ${ADDR:+--dump $ADDR 5} >report.txt 2>&1) || true
echo "emu_check: 6 s of the clock took $(( $(date +%s) - s0 )) s to emulate"
grep -E "in an ISR|^time |^dump| 0x" "$OUT/report.txt" | sed 's/^/  emu: /' || true
fail=0
run() { echo "== $1"; shift; "$@" || fail=1; }
run "the chip: the interrupts take 60 .. 95 % of it" python3 $P isr "$OUT/report.txt" 60 95
run "the engine: the governor's carriers, the worst block under 92 % of its time" python3 $P state "$OUT/report.txt" 92
run "a tick every half second, left and right in turn" python3 $P ticks "$OUT/out.wav" 0.9 4.3
run "PLAY: the first blow ~40 ms after the release click" python3 $P onset "$OUT/out.wav" 4.45 5.2 4.55 6000
run "the pendulum swings" python3 $P moved "$OUT/work/lcd_1000.bmp" "$OUT/work/lcd_1250.bmp"
run "the hands at 10:10" python3 $P hands "$OUT/work/lcd_4000.bmp" 10 10

# the cuckoo clock: ALGORITHM at 0.3 s, SEQ, PLAY at 2.5 s (it calls ten: the gong, the pipes, the door, the bird)
mkdir -p "$OUT/ck/work"
s0=$(date +%s)
(cd "$OUT/ck" && timeout "${EMU_TIMEOUT:-1200}" "$EMU" --fwsc ../pkg.fwsc --ms 5000 --keys '300:ALGO:+1,600:SEQ,2500:PLAY' \
    --wav out.wav --snap 1500,1700,4000 ${ADDR:+--dump $ADDR 6} >report.txt 2>&1) || true
echo "emu_check: 5 s of the cuckoo clock took $(( $(date +%s) - s0 )) s to emulate"
grep -E "in an ISR|^time |^dump| 0x" "$OUT/ck/report.txt" | sed 's/^/  emu: /' || true
run "the cuckoo: the interrupts take 60 .. 95 % of the chip" python3 $P isr "$OUT/ck/report.txt" 60 95
run "the cuckoo: its carriers, the worst block (its calls among them) under 92 %" python3 $P state "$OUT/ck/report.txt" 92 1
# (the sound's times: 0.16 s before the power-on's; the ticks before PLAY's warning click, the blow before its pipe)
run "the cuckoo: a tick every 0.4286 s, left and right in turn" python3 $P ticks "$OUT/ck/out.wav" 0.9 2.2 0.4286
run "the cuckoo: PLAY, its first blow 0.87 s on (the warning, the door)" python3 $P onset "$OUT/ck/out.wav" 3.22 3.52 3.38 5000
run "the cuckoo's pendulum swings" python3 $P moved "$OUT/ck/work/lcd_1500.bmp" "$OUT/ck/work/lcd_1700.bmp" cuckoo
run "the cuckoo's door open, the bird out, calling" python3 $P differ "$OUT/ck/work/lcd_1500.bmp" "$OUT/ck/work/lcd_4000.bmp" 92 28 56 36 150
run "the cuckoo's hands at 10:10" python3 $P hands "$OUT/ck/work/lcd_1500.bmp" 10 10 cuckoo
[ $fail = 0 ] && echo "emu_check: all passed" || { echo "emu_check: FAILED"; exit 1; }
