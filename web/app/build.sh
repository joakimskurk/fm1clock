#!/bin/sh
# SPDX-License-Identifier: GPL-3.0-only
# FM-1 Clock for the browser: firmware/src/fm1clock.c, unchanged, compiled to WebAssembly on web/app/web_host.c (the
# page's FM-1) instead of the chip: build/web/fm1clock.wasm, no imports, no C library. clang with the wasm32 target
# and wasm-ld (lld): apt install clang lld.
#
#   sh web/app/build.sh [OUT]
set -e
OUT="${1:-build/web/fm1clock.wasm}"
CC="${CC_WASM:-clang}"
mkdir -p "$(dirname "$OUT")"
if ! command -v wasm-ld >/dev/null; then           # (clang runs wasm-ld by that name: a versioned one, linked as it)
    LD=$(command -v wasm-ld-18 || command -v wasm-ld-19 || command -v wasm-ld-20 || true)
    [ -n "$LD" ] || { echo "web/app/build.sh: no wasm-ld (apt install lld)" >&2; exit 1; }
    mkdir -p build/web/bin && ln -sf "$LD" build/web/bin/wasm-ld && PATH="$PWD/build/web/bin:$PATH"
fi
$CC --target=wasm32 -O2 -ffreestanding -nostdlib -mbulk-memory -Wall -Werror -Wno-unused-function \
    -DDINGHY_HOST -DDINGHY_WEB -DAPP_VER="\"${APP_VER:-web}\"" -Ifirmware/hal -Ifirmware/src -Ifirmware/gen \
    -Wl,--no-entry -Wl,--export-memory -Wl,--strip-all -o "$OUT" firmware/src/fm1clock.c
echo "web/app/build.sh: $OUT ($(wc -c < "$OUT") B)"
