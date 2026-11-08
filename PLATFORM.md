# PLATFORM

FM-1 Clock runs on **Dinghy 0.5**, imported as source (as VaveHero does).

- upstream: https://github.com/zvenson/dinghy
- commit: `ea1b6bf` (2026-11, after "Dinghy 0.5" `1675934`; the release workflow's file pattern only)
- Dinghy's docs stay in `docs/` (`API.md`, `RULES.md`, `MAKE-IT-YOURS.md`, `SMK37.md`; the clock's own are `SOUND.md`,
  `CUCKOO.md`, `HOW-IT-WORKS.md`). Its README is
  `docs/DINGHY_README.md` (the toolchain, the SDK, the host mode).

## What differs from upstream

Kept small, so a later Dinghy can be merged by diffing these files.

| file | change |
| --- | --- |
| `firmware/src/dinghy.c` | renamed `fm1clock.c`: the app; `APP_NAME "FM1 CLOCK"`, `STORE_MAGIC` "FCLK"; with it `clk_engine.h`, `clk_draw.h` and `firmware/gen/clk_*.h` |
| `tools/build.py` | compiles `fm1clock.c`; outputs `fm1clock.*` and `fm1clock.syms` (the symbol table: `tools/emu_check.sh` reads the engine's state by its address); identity `FM-1_94N` (N = the minor version, 0 = a dev build; 94N is not in Dinghy's list of taken ones); loader screen "FM1 CLOCK" in brass `0xE526`; data family `FMCLOCK` |
| `build.sh` | a comment |
| `tests/run_host.sh` | builds `fm1clock.c` as `build/host/fm1clock` |
| `tests/run_tests.sh` | `fm1clock.*` names; the SMK-37 packages' identities `_94N` |
| `tests/install_test.py` | `fm1clock.*` names |
| `README.md` | moved to `docs/DINGHY_README.md`; FM-1 Clock's README in its place |
| `.github/workflows/release.yml` | replaced by `build.yml` (zvenson/fm1-build, as VaveHero, RoboSeq and SkurkyMello), with a job for the site (GitHub Pages) |
| `web/` (Dinghy has none) | the site: `fm1pkg.js` and `fm1ota.js` from SLOOP (`bac9c05`, unchanged: the update protocol over Web MIDI; Dinghy's `tests/install_test.py` checks `fm1pkg.js` against `tools/fm1pkg_make.py`), FM-1 Clock's own page and `make_site.py` |

Nothing in `firmware/hal/`, `firmware/loader/`, `firmware/app.ld`, `platform.c` or `tests/host.c` is changed.

## Updating Dinghy

1. Diff the new upstream against the commit above for the imported paths.
2. Apply upstream changes; re-apply the table above.
3. `make test`, CI's build, a boot in fm1-emu.
4. Update the commit here.
