#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""FM-1 Clock's site (GitHub Pages): its page, its installer in the browser, the firmware.

  index.html                   web/index.html with fm1pkg.js, fm1ota.js (SLOOP's, unchanged) and the metadata
                               inlined: the installer (Web MIDI, Chrome or Edge), the clocks, the links
  firmware/fm1clock-VER.fwsc   the package the page installs (its SHA-256 in the page: a damaged download is
                               never offered)
  screens/                     the pictures and the icon (docs/screens)
  .nojekyll                    (served as it is)

  python3 web/make_site.py build/fm1clock.fwsc VERSION OUT_DIR

The package must be an FM-1 Clock one: its identity FM-1_94N, its Felucca update loader in it (which the installer
talks to). Made after SLOOP's web/make_site.py (Copyright (C) 2026 Leo Kuroshita (@kurogedelic), Hügelton
Instruments; isod89).
"""
import hashlib
import json
import re
import shutil
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
BLOCKS, BLK, KEEP = 20, 0x30, 0x2F
SCREENS = ("clock.png", "cuckoo.png", "icon.png")   # (the icon: the cuckoo clock's house, its dial)


def product_of(raw):
    """the package identity: one marker byte after each of the first 20 blocks (fm1pkg.js productOf)"""
    return "".join(chr((m - i - 1) & 0xFF) for i in range(BLOCKS) if (m := raw[i * BLK + KEEP]) != 0x7D)


def strip_module(src):
    src = re.sub(r"^export\s+", "", src, flags=re.M)
    return re.sub(r"^import .*?;\n", "", src, flags=re.M)


def main(pkg, version, out):
    pkg, out = Path(pkg), Path(out)
    raw = pkg.read_bytes()
    product = product_of(raw)
    if not re.fullmatch(r"FM-1_94\d", product):
        raise SystemExit(f"{pkg}: identity {product!r} is not FM-1 Clock's (FM-1_94N)")
    if b"FELUCCA-LOADER-1" not in raw:
        raise SystemExit(f"{pkg}: no Felucca update loader in it: the installer could not write it")
    name = f"fm1clock-{re.sub(r'[^A-Za-z0-9.-]', '-', version)}.fwsc"
    meta = json.dumps({"version": version, "product": product, "pkg": "firmware/" + name,
                       "sha256": hashlib.sha256(raw).hexdigest(), "size": len(raw)})
    lib = strip_module((HERE / "fm1pkg.js").read_text(encoding="utf-8")) + "\n" + \
        strip_module((HERE / "fm1ota.js").read_text(encoding="utf-8"))
    html = (HERE / "index.html").read_text(encoding="utf-8")
    for mark in ("/*LIB*/", "/*META*/"):
        if html.count(mark) != 1:
            raise SystemExit(f"web/index.html must hold {mark} once")
    html = html.replace("/*LIB*/", lib).replace("/*META*/", meta)
    if out.exists():
        shutil.rmtree(out)
    (out / "firmware").mkdir(parents=True)
    (out / "screens").mkdir()
    shutil.copy(pkg, out / "firmware" / name)
    for f in SCREENS:
        shutil.copy(ROOT / "docs" / "screens" / f, out / "screens" / f)
    (out / "index.html").write_text(html, encoding="utf-8")
    (out / ".nojekyll").write_text("")
    print(f"site: {out}: index.html ({len(html)} B), firmware/{name} ({len(raw)} B, {product}), "
          f"{len(SCREENS)} pictures")


if __name__ == "__main__":
    if len(sys.argv) != 4:
        sys.exit(__doc__)
    main(*sys.argv[1:])
