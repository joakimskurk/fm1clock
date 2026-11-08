#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""The site's sign: "FM-1 Clock" on a carved walnut board, hung on the clocks' panel wall: docs/screens/sign.png.

  python3 tools/gen_sign.py [--check]     (Pillow, numpy)

Drawn as the clocks are (tools/gen_art_cuckoo.py, its own helpers): at the screen's scale, 8 x 8 samples a pixel,
then twice the size, pixel for pixel, as the pictures of the clocks on the page are. The wall is their pine wall; the
board the cuckoo clock's dark red walnut, a raised and bevelled frame round a sunk field, a carved leaf on each
corner; the letters carved into it and gilded; two brass chains from a nail; its soft shadow on the wall.
--check: fail if docs/screens/sign.png is not what this makes.
"""
import argparse
import io
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageFont

import gen_art_cuckoo as A

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs" / "screens" / "sign.png"
W, H = 364, 100                                  # at the screen's scale (x 2 on the page: its column, 728 px)
BX0, BY0, BX1, BY1 = 36, 30, 328, 92             # the board
NAIL = (182.0, 5.0)
RINGS = 64.0                                     # the chains' rings, either side of the middle
GOLD_L, GOLD_M, GOLD_D = (252, 222, 140), (214, 168, 72), (150, 104, 36)


def gold(x0, y0, x1, y1):
    """the gilding: light at the letters' tops, darker at their feet, as lit from above"""
    yy = np.mgrid[y0:y1, x0:x1][0].astype(np.float32) / A.K
    t = np.clip((yy - 44.0) / 34.0, 0, 1)[..., None]
    l, m, d = (np.array(c, np.float32) / 255 for c in (GOLD_L, GOLD_M, GOLD_D))
    return np.where(t < 0.5, l + (m - l) * (t * 2), m + (d - m) * (t * 2 - 1))


def letters(cv, txt, cx, cy, size):
    """a mask of the text, centred at (cx, cy), DejaVu Serif Bold"""
    font = ImageFont.truetype(A.SERIF, int(round(size * A.K)))

    def draw(d, P, k):
        bb = d.textbbox((0, 0), txt, font=font)
        w, h = bb[2] - bb[0], bb[3] - bb[1]
        d.text((cx * k - w / 2 - bb[0], cy * k - h / 2 - bb[1]), txt, font=font, fill=255)
    return cv.mask(draw)


def shifted(m, dx, dy, k=A.K):
    a, bb = m
    sx, sy = int(round(dx * k)), int(round(dy * k))
    out = np.zeros_like(a)
    h, w = a.shape
    out[max(sy, 0):h + min(sy, 0), max(sx, 0):w + min(sx, 0)] = a[max(-sy, 0):h - max(sy, 0), max(-sx, 0):w - max(sx, 0)]
    x0, y0, x1, y1 = bb
    return out, (max(x0 + sx, 0), max(y0 + sy, 0), min(x1 + sx, w), min(y1 + sy, h))


def chain(cv, p0, p1):
    """a brass chain, link by link: one face on, the next edge on"""
    p0, p1 = np.array(p0), np.array(p1)
    n = int(np.linalg.norm(p1 - p0) / 1.6)
    for i in range(n + 1):
        c = p0 + (p1 - p0) * i / n
        if i % 2:
            cv.ellipse(c[0], c[1], 0.55, 0.55, (120, 92, 40))
        else:
            cv.ellipse(c[0], c[1], 0.9, 0.9, (120, 92, 40))
            cv.ellipse(c[0] - 0.2, c[1] - 0.2, 0.55, 0.55, (226, 190, 104))


def build():
    cv = A.Canvas(W, H)
    nx, ny = NAIL
    for x in (nx - RINGS, nx + RINGS):           # the chains, from the board's rings to the nail
        chain(cv, (nx, ny + 1.0), (x, BY0 - 2.2))
        cv.ellipse(x, BY0 - 1.4, 1.9, 1.9, (120, 92, 40))
        cv.ellipse(x - 0.3, BY0 - 1.7, 1.2, 1.2, (226, 190, 104))
        cv.ellipse(x, BY0 - 1.4, 0.9, 0.9, A.WN_X)
    cv.ellipse(nx, ny, 2.2, 2.2, (110, 86, 40))   # the nail's head, brass
    cv.ellipse(nx - 0.5, ny - 0.6, 1.0, 1.0, (236, 204, 120))
    # the board: its edge dark, a bevel lit from the top left, the field, a fillet round it
    cv.rect(BX0, BY0, BX1, BY1, A.WN_X)
    cv.rect(BX0 + 0.8, BY0 + 0.8, BX1 - 0.8, BY1 - 0.8, A.wood(A.WN_M, A.WN_D, False, 301, period=2.6))
    cv.rect(BX0 + 0.8, BY0 + 0.8, BX1 - 0.8, BY0 + 2.0, A.WN_L, 0.7)
    cv.rect(BX0 + 0.8, BY0 + 0.8, BX0 + 2.0, BY1 - 0.8, A.WN_L, 0.45)
    cv.rect(BX0 + 0.8, BY1 - 2.0, BX1 - 0.8, BY1 - 0.8, A.WN_X, 0.8)
    cv.rect(BX1 - 2.0, BY0 + 0.8, BX1 - 0.8, BY1 - 0.8, A.WN_X, 0.6)
    fx0, fy0, fx1, fy1 = BX0 + 6, BY0 + 6, BX1 - 6, BY1 - 6
    cv.rect(fx0 - 0.8, fy0 - 0.8, fx1 + 0.8, fy1 + 0.8, A.WN_X, 0.9)   # the field, sunk: its shadowed rim
    cv.rect(fx0, fy0, fx1, fy1, A.wood(A.WN_D, A.WN_X, False, 302, period=3.0))
    cv.rect(fx0, fy1 - 0.6, fx1, fy1, A.WN_L, 0.35)
    cv.rect(fx1 - 0.6, fy0, fx1, fy1, A.WN_L, 0.25)
    for cx, cy, ang in ((BX0 + 3.2, BY0 + 3.2, -45), (BX1 - 3.2, BY0 + 3.2, 45), (BX0 + 3.2, BY1 - 3.2, -135),
                        (BX1 - 3.2, BY1 - 3.2, 135)):       # a carved leaf on each corner, pointing out
        A.carved_leaf(cv, cx, cy, 6.4, ang)
    # the letters, carved in and gilded: the cut's shadow above and left, its lit edge below and right, the gold
    cy = (fy0 + fy1) / 2 + 0.5
    m = letters(cv, "FM-1 Clock", (fx0 + fx1) / 2, cy, 34)
    cv.paint(shifted(m, -0.5, -0.6), (20, 6, 3), 0.9)
    cv.paint(shifted(m, 0.45, 0.55), A.WN_L, 0.8)
    cv.paint(m, gold)
    scr = cv.down()
    tile = A.wall_tile()
    wall = np.concatenate([tile] * (W // A.WALL_TW + 1), axis=1)[:H, :W]
    img = np.clip(A.on_wall(scr, wall), 0, 255).astype(np.uint8)
    big = Image.fromarray(img).resize((2 * W, 2 * H), Image.NEAREST)
    buf = io.BytesIO()
    big.save(buf, "PNG", optimize=True)
    return buf.getvalue()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true")
    a = ap.parse_args()
    png = build()
    if a.check:
        same = OUT.exists() and np.array_equal(np.asarray(Image.open(OUT)), np.asarray(Image.open(io.BytesIO(png))))
        print("sign.png: up to date" if same else "docs/screens/sign.png is not what tools/gen_sign.py makes: run it")
        return 0 if same else 1
    OUT.write_bytes(png)
    print(f"{OUT.relative_to(ROOT)}: {2 * W} x {2 * H}, {len(png)} B")
    return 0


if __name__ == "__main__":
    sys.exit(main())
