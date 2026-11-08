#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
# Copyright (C) 2026 Joakim (joakimskurk)
"""The site's link preview (Open Graph, web/og.png, 1200 x 630): the two clocks on their wall, the sign, and what
FM-1 Clock is. web/make_site.py puts it in the site; web/index.html names it (og:image).

  python3 web/make_og.py [OUT.png]

The pictures are docs/screens/clock.png, cuckoo.png and sign.png. The text is set in Georgia, as the page is
(/System/Library/Fonts/Supplemental, or GEORGIA_DIR)."""
import os
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent.parent
SCREENS = ROOT / "docs" / "screens"
W, H = 1200, 630
BG0, BG1 = (30, 24, 18), (14, 11, 8)                          # the page's walnut dark, a little lit from above
FG, DIM, BRASS, LINE = (242, 235, 224), (179, 164, 144), (217, 164, 65), (58, 46, 34)


def font(name, size):
    d = Path(os.environ.get("GEORGIA_DIR", "/System/Library/Fonts/Supplemental"))
    return ImageFont.truetype(str(d / name), size)


def wrap(draw, text, f, width):
    lines, line = [], ""
    for w in text.split():
        t = (line + " " + w).strip()
        if draw.textlength(t, font=f) <= width or not line:
            line = t
        else:
            lines.append(line)
            line = w
    return lines + [line]


def main(out):
    img = Image.new("RGB", (W, H))
    px = img.load()
    for y in range(H):
        t = y / (H - 1)
        c = tuple(round(BG0[i] + (BG1[i] - BG0[i]) * t) for i in range(3))
        for x in range(W):
            px[x, y] = c
    d = ImageDraw.Draw(img)

    # the two clocks, side by side, each in a brass-lined frame
    ch, gap, x0 = 462, 16, 56
    y0 = (H - ch) // 2
    x = x0
    for name in ("clock.png", "cuckoo.png"):
        pic = Image.open(SCREENS / name).convert("RGB")
        pic = pic.resize((round(pic.size[0] * ch / pic.size[1]), ch), Image.LANCZOS)
        d.rectangle((x - 3, y0 - 3, x + pic.size[0] + 2, y0 + ch + 2), outline=LINE, width=3)
        img.paste(pic, (x, y0))
        x += pic.size[0] + gap
    tx = x - gap + 52
    tw = W - tx - 52

    sign = Image.open(SCREENS / "sign.png").convert("RGBA")
    sign = sign.resize((tw, round(sign.size[1] * tw / sign.size[0])), Image.LANCZOS)
    big, small = font("Georgia Bold.ttf", 34), font("Georgia.ttf", 22)
    blocks = [(wrap(d, "A pendulum clock and a cuckoo clock for the M-VAVE FM-1", big, tw), big, FG, 44),
              (wrap(d, "Free firmware, installed from the browser", small, tw), small, BRASS, 32)]
    gaps = [22]
    height = sign.size[1] + 18 + sum(len(ls) * lh for ls, _, _, lh in blocks) + sum(gaps)
    y = (H - height) // 2
    img.paste(sign, (tx, y), sign)
    y += sign.size[1] + 18
    for k, (ls, f, col, lh) in enumerate(blocks):
        for ln in ls:
            d.text((tx, y), ln, font=f, fill=col)
            y += lh
        if k < len(gaps):
            y += gaps[k]
    img.save(out, optimize=True)
    print(f"og: {out} ({W} x {H}, {os.path.getsize(out)} B)")


if __name__ == "__main__":
    if len(sys.argv) > 2:
        sys.exit(__doc__)
    main(sys.argv[1] if len(sys.argv) == 2 else ROOT / "web" / "og.png")
