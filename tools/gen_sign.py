#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""The site's sign: "FM-1 Clock" on a carved walnut board, hung on the page itself: docs/screens/sign.png.

  python3 tools/gen_sign.py [--check]     (Pillow, numpy)

Drawn as the clocks are (tools/gen_art_cuckoo.py, its own helpers): at the screen's scale, 8 x 8 samples a pixel,
then twice the size, pixel for pixel, as the pictures of the clocks on the page are; on nothing (its background
transparent), so it hangs on the page, its soft shadow on the page. Carved as the cuckoo clock is, in its dark red
walnut (lighter: it hangs on the dark page), and then some: a crest of leaves at the top with the cuckoo on it, leaves along the top edge, a frame of
carved beads round a sunk field, brass rosettes in its corners, scrolls curling out at either end; the letters cut
in and gilded; under it fretwork, two scrolls and a leaf hanging on a stem between, and
two pine cones on their chains; it hangs from two brass nails on two chains.
--check: fail if docs/screens/sign.png is not what this makes.
"""
import argparse
import io
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageFilter, ImageFont

import gen_art_cuckoo as A

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs" / "screens" / "sign.png"
W, H = 364, 156                                  # at the screen's scale (x 2 on the page: its column, 728 px)
CX = W / 2
BX0, BY0, BX1, BY1 = 44, 52, 320, 112            # the board
HOOKS = (98.0, 266.0)                            # the nails, the chains straight down from them
GOLD_L, GOLD_M, GOLD_D = (252, 224, 146), (216, 170, 74), (146, 100, 34)
IRON, IRON_L = (120, 92, 40), (230, 194, 108)    # (the brass of the chains, the nails, the rosettes)
# the cuckoo clock's walnut, lighter: the sign hangs on the dark page, not on the pale wall
SW_L, SW_M, SW_D, SW_X = (A.shade(c, 1.32) for c in (A.WN_L, A.WN_M, A.WN_D, A.WN_X))


def leaf(cv, cx, cy, s, ang):
    A.carved_leaf(cv, cx, cy, s, ang, SW_M, SW_L, SW_X)


def stem(cv, pts, w):
    A.carved_line(cv, pts, w, SW_M, SW_L, SW_X)


def gold(y_top, y_bot):
    """the gilding: light at the letters' tops, darker at their feet, as lit from above"""
    l, m, d = (np.array(c, np.float32) / 255 for c in (GOLD_L, GOLD_M, GOLD_D))

    def fill(x0, y0, x1, y1):
        yy = np.mgrid[y0:y1, x0:x1][0].astype(np.float32) / A.K
        t = np.clip((yy - y_top) / (y_bot - y_top), 0, 1)[..., None]
        return np.where(t < 0.5, l + (m - l) * (t * 2), m + (d - m) * (t * 2 - 1))
    return fill


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
    p0, p1 = np.array(p0, float), np.array(p1, float)
    n = max(1, int(np.linalg.norm(p1 - p0) / 1.6))
    for i in range(n + 1):
        c = p0 + (p1 - p0) * i / n
        if i % 2:
            cv.ellipse(c[0], c[1], 0.5, 0.6, IRON)
        else:
            cv.ellipse(c[0], c[1], 0.9, 0.9, IRON)
            cv.ellipse(c[0] - 0.2, c[1] - 0.2, 0.55, 0.55, IRON_L)


def ring(cv, x, y, r=1.9):
    cv.ellipse(x, y, r, r, IRON)
    cv.ellipse(x - 0.3, y - 0.3, r * 0.65, r * 0.65, IRON_L)
    cv.ellipse(x, y, r * 0.45, r * 0.45, SW_X)


def nail(cv, x, y):
    cv.ellipse(x, y, 2.3, 2.3, IRON)
    cv.ellipse(x - 0.5, y - 0.6, 1.1, 1.1, (250, 226, 150))


def rosette(cv, x, y, r):
    """a brass rosette: a ring of petals round a domed boss"""
    for i in range(8):
        a = np.radians(i * 45 + 22.5)
        cv.ellipse(x + r * 0.62 * np.sin(a), y - r * 0.62 * np.cos(a), r * 0.36, r * 0.36, IRON)
        cv.ellipse(x + r * 0.62 * np.sin(a) - 0.2, y - r * 0.62 * np.cos(a) - 0.2, r * 0.22, r * 0.22, IRON_L)
    cv.ellipse(x, y, r * 0.42, r * 0.42, IRON)
    cv.ellipse(x - 0.3, y - 0.35, r * 0.26, r * 0.26, (250, 226, 150))


def beads(cv, x0, y0, x1, y1, step=3.6, r=0.95):
    """a carved bead moulding round a rectangle"""
    def bead(x, y):
        cv.ellipse(x + 0.25, y + 0.3, r + 0.15, r + 0.15, SW_X)
        cv.ellipse(x, y, r, r, SW_M)
        cv.ellipse(x - 0.3, y - 0.35, r * 0.42, r * 0.42, SW_L, 0.8)
    for x in np.arange(x0, x1 + 0.01, step):
        bead(x, y0)
        bead(x, y1)
    for y in np.arange(y0 + step, y1 - 0.01, step):
        bead(x0, y)
        bead(x1, y)


def cone(scale=0.62):
    """the cuckoo clock's pine-cone weight, smaller (premultiplied RGBA, screen scale)"""
    w = A.weight()
    h, ww = w.shape[:2]
    im = Image.fromarray(np.clip(np.round(w * 255), 0, 255).astype(np.uint8), "RGBA")
    return np.asarray(im.resize((max(1, int(ww * scale)), max(1, int(h * scale))), Image.BOX), np.float32) / 255


def over(img, spr, x0, y0):
    """a premultiplied sprite over a premultiplied image, at whole pixels"""
    h, w = spr.shape[:2]
    reg = img[y0:y0 + h, x0:x0 + w]
    reg[...] = spr + reg * (1 - spr[..., 3:])


def build():
    cv = A.Canvas(W, H)
    for hx in HOOKS:                              # the chains: from the two nails straight down to the board's rings
        chain(cv, (hx, 7.5), (hx, BY0 - 3.6))
        nail(cv, hx, 5.0)
    def on(pts, i, ctr, size):                    # a leaf grown on a scroll, at its i-th point, out from its centre
        x, y = pts[i]
        leaf(cv, x, y, size, np.degrees(np.arctan2(x - ctr[0], -(y - ctr[1]))))
    for s_ in (-1, 1):                            # the end scrolls, curling out from its ends, leaves on them
        ex = BX0 if s_ < 0 else BX1
        ctr = (ex + s_ * 17, (BY0 + BY1) / 2 + 1)
        sc = A.spiral(ctr[0], ctr[1], 14.0, 3.2, s_ * 210, s_ * 560)
        stem(cv, [(ex - s_ * 2, BY0 + 6)] + sc, 2.4)
        for i, size in ((6, 5.6), (15, 5.2), (24, 4.4)):
            on(sc, i, ctr, size)
    for s_ in (-1, 1):                            # the fretwork under it: two scrolls curling in, leaves on them
        ctr = (CX + s_ * 44, BY1 + 9)
        sc = A.spiral(ctr[0], ctr[1], 11.0, 2.8, s_ * -80, s_ * 250)
        stem(cv, [(CX + s_ * 112, BY1 - 0.5), (CX + s_ * 78, BY1 + 2.5)] + sc, 1.8)
        leaf(cv, CX + s_ * 96, BY1 + 2.2, 4.6, s_ * 160)
        for i, size in ((10, 4.6), (22, 3.8)):
            on(sc, i, ctr, size)
        cv.line([(CX + s_ * 60, BY1 + 0.6), (CX + s_ * 3, BY1 + 0.6)], 1.4, SW_D)
    stem(cv, [(CX, BY1 - 1), (CX, BY1 + 12)], 2.6)   # and a leaf in the middle, on a stem with a bead
    cv.ellipse(CX + 0.3, BY1 + 5.8, 2.6, 2.4, SW_X)
    cv.ellipse(CX, BY1 + 5.5, 2.4, 2.2, A.wood(SW_M, SW_D, False, 330))
    cv.ellipse(CX - 0.6, BY1 + 4.8, 0.9, 0.8, SW_L, 0.7)
    leaf(cv, CX, BY1 + 17, 8.0, 180)
    # the board: its edge dark, a bevel lit from the top left, a bead moulding, the field sunk inside it
    cv.rect(BX0, BY0, BX1, BY1, SW_X)
    cv.rect(BX0 + 0.8, BY0 + 0.8, BX1 - 0.8, BY1 - 0.8, A.wood(SW_M, SW_D, False, 301, period=2.6))
    cv.rect(BX0 + 0.8, BY0 + 0.8, BX1 - 0.8, BY0 + 2.0, SW_L, 0.7)
    cv.rect(BX0 + 0.8, BY0 + 0.8, BX0 + 2.0, BY1 - 0.8, SW_L, 0.45)
    cv.rect(BX0 + 0.8, BY1 - 2.0, BX1 - 0.8, BY1 - 0.8, SW_X, 0.8)
    cv.rect(BX1 - 2.0, BY0 + 0.8, BX1 - 0.8, BY1 - 0.8, SW_X, 0.6)
    beads(cv, BX0 + 4.2, BY0 + 4.2, BX1 - 4.2, BY1 - 4.2)
    fx0, fy0, fx1, fy1 = BX0 + 8, BY0 + 8, BX1 - 8, BY1 - 8
    cv.rect(fx0 - 0.8, fy0 - 0.8, fx1 + 0.8, fy1 + 0.8, SW_X, 0.9)
    cv.rect(fx0, fy0, fx1, fy1, A.wood(SW_D, SW_X, False, 302, period=3.0))
    cv.rect(fx0, fy1 - 0.6, fx1, fy1, SW_L, 0.35)
    cv.rect(fx1 - 0.6, fy0, fx1, fy1, SW_L, 0.25)
    for x, y in ((BX0 + 4.2, BY0 + 4.2), (BX1 - 4.2, BY0 + 4.2), (BX0 + 4.2, BY1 - 4.2), (BX1 - 4.2, BY1 - 4.2)):
        rosette(cv, x, y, 4.2)                    # brass rosettes in the corners, over the beads
    for hx in HOOKS:                              # the rings the chains hang from, on its top
        ring(cv, hx, BY0 - 2.2)
    for s_ in (-1, 1):                            # leaves along the top edge, turned out in turn, smaller to the ends
        for i, t in enumerate(np.arange(30.0, 128.0, 13.5)):
            if abs(t - abs(HOOKS[0] - CX)) < 7:
                continue                          # (not over the rings)
            leaf(cv, CX + s_ * t, BY0 - 0.6, 5.6 - 1.6 * t / 128, s_ * (40 if i % 2 else 12))
    for ang in (-66, 66, -33, 33):                # the crest: leaves fanned out from a boss on the board's top, the
        a_ = np.radians(ang)                      # middle one upright, the cuckoo on it
        stem(cv, [(CX, BY0 - 1.0), (CX + np.sin(a_) * 11, BY0 - 1.0 - np.cos(a_) * 9)], 1.6)
        leaf(cv, CX + np.sin(a_) * 15, BY0 - 1.0 - np.cos(a_) * 12, 6.6, ang)
    stem(cv, [(CX, BY0 - 1.0), (CX, BY0 - 14)], 2.2)
    leaf(cv, CX, BY0 - 15, 7.4, 0)
    cv.ellipse(CX + 0.3, BY0 - 1.2, 4.0, 3.2, SW_X)
    cv.ellipse(CX, BY0 - 1.5, 3.7, 3.0, A.wood(SW_M, SW_D, False, 331))
    cv.ellipse(CX - 0.9, BY0 - 2.6, 1.4, 1.1, SW_L, 0.7)
    # the letters, cut in and gilded: the cut's shadow above and left, its lit edge below and right, the gold
    cy = (fy0 + fy1) / 2 + 0.5
    m = letters(cv, "FM-1 Clock", CX, cy, 30)
    cv.paint(shifted(m, -0.5, -0.6), (20, 6, 3), 0.9)
    cv.paint(shifted(m, 0.45, 0.55), SW_L, 0.8)
    cv.paint(m, gold(cy - 12, cy + 12))
    for s_ in (-1, 1):                            # the pine cones' chains, from rings under it
        x = CX + s_ * 64
        chain(cv, (x, BY1 + 2.5), (x, BY1 + 14.5))
        ring(cv, x, BY1 + 1.6, 1.5)
    scr = cv.down()
    # the cuckoo on its crest, the pine cones on their chains (the clock's own sprites)
    b = A.bird(False)
    small = b.reshape(b.shape[0] // 2, 2, b.shape[1] // 2, 2, 4).mean(axis=(1, 3))
    over(scr, small, int(round(CX - 13)), int(round(BY0 - 38)))
    cn = cone()
    for s_ in (-1, 1):
        over(scr, cn, int(round(CX + s_ * 64 - cn.shape[1] / 2)), int(round(BY1 + 14)))
    # its shadow on the page: 3 px right, 4 down, soft, half as dark as black; straight alpha for the PNG
    a = scr[..., 3]
    sh = np.zeros_like(a)
    sh[4:, 3:] = a[:-4, :-3]
    sh = np.asarray(Image.fromarray((sh * 255).astype(np.uint8)).filter(ImageFilter.GaussianBlur(2.2)), np.float32) / 255
    out_a = a + 0.5 * sh * (1 - a)
    rgb = scr[..., :3] / np.maximum(out_a[..., None], 1e-6)
    rgba = np.concatenate([np.clip(rgb, 0, 1), out_a[..., None]], axis=2)
    img = Image.fromarray(np.clip(np.round(rgba * 255), 0, 255).astype(np.uint8), "RGBA")
    big = img.resize((2 * W, 2 * H), Image.NEAREST)
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
