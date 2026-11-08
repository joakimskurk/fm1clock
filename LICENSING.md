# Licensing

FM-1 Clock, like Dinghy under it, is free software under the GNU General Public License, version 3 only (`GPL-3.0-only`, full text in
`LICENSE`). You may use, study, change and share it. If you give someone a firmware built from it, give them its
complete source under the same licence too.

## Who made what

| | |
| --- | --- |
| The platform: `firmware/hal/`, `firmware/loader/`, `crt0.S`, `app.ld`, `firmware/src/` (`usb.c`, `ota.c`, `recovery.c`, `lcd.c`, `gfx.c`, `libc.c`, `bootguard.h`, `uac_fir.h`), `tools/` | Copyright (C) 2026 Leo Kuroshita (@kurogedelic), Hügelton Instruments ([Felucca](https://github.com/hugelton/Felucca)), with the changes of [SLOOP](https://github.com/isod89/sloop-fm1) (isod89) |
| The SMK-37 board layer: `firmware/hal/smk_input.h`, `fm1_flash_map.h`, the SMK-37 parts of `fm1_cc.h`, `fm1_flash.h`, `fm1_lcd_hw.h`, `lcd.c`, `ota.c`, `bootguard.h`, `firmware/loader/`, `tools/fm1pkg_make.py`, `tools/fm1_install.py`, `tools/build.py`; `firmware/src/smk_wheel.h`; `tests/ota_test.c`, `ldr_test.c`, `install_test.py`, `smk_wheel_test.c`, `smk_pkg_test.py` | Copyright (C) 2026 M. Geisler (genkigenki/makkuro), from [genkigenki/sloop-fm1](https://github.com/genkigenki/sloop-fm1) branch `smk37` (the reference port of the [fm1-to-smk37](https://github.com/genkigenki/fm1-to-smk37) kit) |
| The TRS MIDI IN `firmware/src/midi_uart.c` | Felucca's, as sloopDX carries it, with the ring read by content from Felucca [Salt] 0.9-salt14 by ChanceTheMaker (found by keremimo) |
| The update loader's screen: `firmware/loader/ldr_screen.c`, `tests/ldr_screen_test.c` | Copyright (C) 2026 zvenson (from OberVave, the Firmware Hub's look); the idea, a loader that draws, its 5 x 7 letters and the order of things from [Skiff](https://github.com/illuminus5/skiff) by illuminus5, GPL-3.0 |
| From OberVave: the storage (blobs, slots), `LCD_IDLE`, the SMK-37 wiring of `platform.c`, `store.h`, the pad event queue in `smk_input.h`, `tests/smk_flash_test.c`, `tests/run_tests.sh`, the CI workflow | Copyright (C) 2026 zvenson |
| The wiring `platform.c`, the host mode `tests/host.c`, Dinghy's docs (`docs/`) | zvenson |
| The browser installer's protocol: `web/fm1pkg.js`, `web/fm1ota.js` (unchanged, from [SLOOP](https://github.com/isod89/sloop-fm1) `bac9c05`); the install flow of `web/index.html` and the shape of `web/make_site.py`, after SLOOP's `web/index_pkg.html` and `web/make_site.py` | Copyright (C) 2026 Leo Kuroshita (@kurogedelic), Hügelton Instruments (Felucca), with the changes of SLOOP (isod89) |
| FM-1 Clock: `firmware/src/fm1clock.c` (from Dinghy's `dinghy.c`), `clk_engine.h`, `clk_draw.h`, `firmware/gen/clk_*.h`, `tools/analyze_ref.py`, `features.py`, `fit_model.py`, `gen_tables.py`, `gen_art.py`, `settime.py`, `emu_ci.sh`, `emu_check.sh`, `tests/run_clock.sh`, `tests/clk/`, `tests/scripts/` (the clock's), `tests/ref/`, `tests/web/`, the page `web/index.html` and `web/make_site.py` (but for what is SLOOP's in them, above), the clock in the browser `web/app/` (its `web_host.c` after Dinghy's `tests/host.c`), `README.md`, `docs/SOUND.md`, `docs/CUCKOO.md`, `docs/HOW-IT-WORKS.md`, `docs/screens/`, `PLATFORM.md` | Copyright (C) 2026 Joakim (joakimskurk) |

## Third-party material

| What | Licence | Where |
| --- | --- | --- |
| Terminus font 8x16 (ter-u16n), rendered into `firmware/gen/felucca_font.h` | SIL OFL 1.1 | `assets/fonts/Terminus-LICENSE.txt` |
| JieLi AC79 SDK: `uboot.boot`, `cfg_tool.bin`, `eq_cfg_hw.bin` are read from your SDK checkout at build time and placed in the package; no SDK files are in this tree | Apache-2.0 | <https://gitee.com/Jieli-Tech/fw-AC79_AIoT_SDK> |

## The design and the recording

`assets/design.png` is FM-1 Clock's design, by its author (joakimskurk); `firmware/gen/clk_art.h` is made from it
(`tools/gen_art.py`) and goes with the firmware under its licence.

The sound is fitted to recordings of a real pendulum wall clock and of a Black Forest cuckoo clock. They are not
ours, they are not in this repository, and it does not point to them; what is here are measurements of them (the
frequencies, decays and levels in `tools/ref_model.json` and `tools/ref_cuckoo.json`, the band energies in
`tests/ref/`) and the models fitted to them (`tools/clk_model.json`, `tools/clk_cuckoo.json`). No sample of them is
in the firmware: every sound is synthesised.

## The logo

`assets/logo.svg` / `logo.png` carry the designburg signet: Copyright (C) designburg, all rights reserved, not under
the GPL. It marks Dinghy itself; FM-1 Clock does not use it as its own.

## Trademarks

"Felucca" and "Hügelton Instruments" are names of Hügelton Instruments; "M-VAVE", "FM-1", "SMK-37" and "MKE-P37"
belong to their owners. Dinghy and FM-1 Clock are not made or endorsed by them.
