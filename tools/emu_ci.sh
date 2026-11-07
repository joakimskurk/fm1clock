#!/bin/sh
# SPDX-License-Identifier: GPL-3.0-only
# CI: fm1-emu (joakimeriksson/fm1-emu, pinned) built from source, then FM1 Clock's package run in it
# (tools/emu_check.sh): how much of the chip it takes, that it ticks on the half seconds, strikes, swings.
set -e
REV=a0e9a88cba72a6de7368273c82e26867848e281d
DIR="$HOME/fm1-emu"
if [ ! -x "$DIR/target/release/fm1-emu" ]; then
    rm -rf "$DIR"
    git init -q "$DIR"
    git -C "$DIR" fetch -q --depth 1 https://github.com/joakimeriksson/fm1-emu "$REV"
    git -C "$DIR" checkout -q FETCH_HEAD
    echo "emu_ci: building fm1-emu ($REV)"
    (cd "$DIR" && timeout 900 cargo build -q --release -p fm1-emu)
fi
echo "emu_ci: fm1-emu ready"
timeout 1500 sh tools/emu_check.sh build/fm1clock.fwsc
