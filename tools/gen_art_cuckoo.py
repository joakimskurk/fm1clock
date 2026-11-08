#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""FM-1 Clock's own cuckoo clock, drawn from nothing, and the panel wall all its clocks hang on:
firmware/gen/clk_art_cuckoo.h.

  python3 tools/gen_art_cuckoo.py [--check] [--preview OUT.png]     (Pillow, numpy)

The classic: carved, in dark red walnut, leaves along its roof boards and a crest of leaves at the peak, vines round
an ivory dial with serif numerals, turned columns on a shelf, fretwork under it with a leaf hanging from it, a leaf
for a bob. It hangs on a wall of pine boards (a tile four boards wide, across the screen), its soft shadow on it;
the wall clock (tools/gen_art.py) hangs on the same wall.
Everything is drawn 8 times over (polygons, ellipses, wood grain from smoothed noise) and box-filtered down to the
screen, so its edges are soft.

What moves is the firmware's (firmware/src/clk_draw.h), from sprites made here:
  - the door: its leaf, turned about its hinge in perspective; the gable behind it with the doorway open (dark);
  - the bird, in two poses (its beak shut, open), at twice the screen's resolution: the firmware scales it as it
    comes forward out of the dark and turns it as it bows to its call;
  - the pendulum's bob, a carved leaf;
  - a pine-cone weight (cast iron), for both chains; the rings and the chains themselves are drawn by the firmware.
The house's lowest rows (the shelf's fretwork) are a front layer over the chains and the pendulum, and the wall
behind those (the house's shadow on it) is kept.
"""
import argparse
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "firmware" / "gen" / "clk_art_cuckoo.h"
K = 8                                       # drawn at 8 x 8 samples a screen pixel

# the layout, in screen pixels
CX = 120.0
DIAL_C, DIAL_R, FACE_R = (120.0, 99.0), 31.0, 26.2
HOLE_C, HOLE_R, HOLE_BOT = (120.0, 43.0), 9.0, 61.0      # the bird's doorway: an arch, its bottom
DOOR_RGN = (92, 28, 56, 36)                 # what the door and the bird can touch: x, y, w, h
FRONT_Y = 146                               # from here down the house is in front of the chains and the pendulum
LO_X, LO_W = 84, 72                         # what hangs below the house is drawn there (clk_draw.h), FRONT_Y down
HOUSE_BOT = 166                             # the apron's lowest point (its scallops, its drop)
PIVOT = (120.0, 99.0)                       # behind the dial
BOB_Y = 206.0
STRANDS = (100.0, 110.0, 130.0, 140.0)      # the chains: the going weight, its ring, the cuckoo's ring, its weight
W_TOP = 169                                 # a weight's hook, wound up
TRAVEL = 66                                 # and how far it goes down in a run (the ring as far up)

WOOD_M, WOOD_D = (156, 100, 56), (100, 62, 32)          # (the bird's perch)
BRASS = (206, 166, 76)


# ---- drawing at K times, premultiplied RGBA floats (0..1)
class Canvas:
    def __init__(self, w, h, k=K):
        self.k, self.w, self.h = k, w, h
        self.c = np.zeros((h * k, w * k, 4), np.float32)

    def mask(self, fn):
        """a mask (0..1) of what fn draws with ImageDraw in screen coordinates, and its bounding box"""
        im = Image.new("L", (self.w * self.k, self.h * self.k), 0)
        d = ImageDraw.Draw(im)
        fn(d, lambda pts: [(x * self.k, y * self.k) for x, y in pts], self.k)
        bb = im.getbbox()
        return (np.asarray(im, np.float32) / 255, bb)

    def paint(self, m, col, alpha=1.0):
        a_, bb = m
        if bb is None:
            return
        x0, y0, x1, y1 = bb
        a = a_[y0:y1, x0:x1, None] * alpha
        if callable(col):
            rgb = col(x0, y0, x1, y1)
        else:
            rgb = np.array(col, np.float32) / 255
        dst = self.c[y0:y1, x0:x1]
        dst[..., :3] = rgb * a + dst[..., :3] * (1 - a)
        dst[..., 3:] = a + dst[..., 3:] * (1 - a)

    def poly(self, pts, col, alpha=1.0):
        self.paint(self.mask(lambda d, P, k: d.polygon(P(pts), fill=255)), col, alpha)

    def ellipse(self, cx, cy, rx, ry, col, alpha=1.0):
        self.paint(self.mask(lambda d, P, k: d.ellipse(P([(cx - rx, cy - ry), (cx + rx, cy + ry)]), fill=255)), col, alpha)

    def rect(self, x0, y0, x1, y1, col, alpha=1.0):
        self.poly([(x0, y0), (x1, y0), (x1, y1), (x0, y1)], col, alpha)

    def line(self, pts, wdt, col, alpha=1.0):
        self.paint(self.mask(lambda d, P, k: d.line(P(pts), fill=255, width=max(1, int(round(wdt * k))), joint="curve")), col, alpha)

    def down(self):
        """to the screen: the mean of each K x K"""
        k = self.k
        return self.c.reshape(self.h, k, self.w, k, 4).mean(axis=(1, 3))


def noise(h, w, cell, seed):
    rng = np.random.default_rng(seed)
    small = rng.random((h // cell + 3, w // cell + 3)).astype(np.float32)
    return np.asarray(Image.fromarray(small, "F").resize((w + 2 * cell, h + 2 * cell), Image.BICUBIC))[cell:cell + h, cell:cell + w]


def wood(base, dark, vertical=True, seed=1, k=K, period=2.2):
    """a fill of wood grain: bands along the board, waving, from base to dark"""
    b = np.array(base, np.float32) / 255
    d = np.array(dark, np.float32) / 255

    def fill(x0, y0, x1, y1):
        h, w = y1 - y0, x1 - x0
        n = noise(h, w, 6 * k, seed)
        yy, xx = np.mgrid[y0:y1, x0:x1].astype(np.float32)
        across = (xx if vertical else yy) / k
        along = (yy if vertical else xx) / k
        g = 0.5 + 0.5 * np.sin(2 * np.pi * (across + 1.6 * n + 0.15 * np.sin(along * 0.4 + seed)) / period)
        g = g ** 3 * 0.55 + 0.3 * noise(h, w, k, seed + 7)
        return b * (1 - g[..., None]) + d * g[..., None]
    return fill


def shade(col, f):
    return tuple(min(255, max(0, int(round(c * f)))) for c in col)


# ---- the house
def numerals(cv, cx, cy, r, font_file, size, col, narrow=1.0):
    """the hours 1 to 12, upright, centred on a circle of radius r round (cx, cy); two-figure ones narrowed by
    narrow (so 10, 11 and 12 keep clear of each other on a small dial)"""
    font = ImageFont.truetype(font_file, int(round(size * K)))
    for h in range(1, 13):
        a = np.radians(h * 30)
        tx, ty = cx + r * np.sin(a), cy - r * np.cos(a)
        txt = str(h)
        f = narrow if h >= 10 else 1.0

        def num(d, P, k, txt=txt, tx=tx, ty=ty, f=f):
            bb = d.textbbox((0, 0), txt, font=font)
            w, hh = bb[2] - bb[0], bb[3] - bb[1]
            if f == 1.0:
                d.text((tx * k - w / 2 - bb[0], ty * k - hh / 2 - bb[1]), txt, font=font, fill=255)
                return
            t = Image.new("L", (w + 4, hh + 4), 0)
            ImageDraw.Draw(t).text((2 - bb[0], 2 - bb[1]), txt, font=font, fill=255)
            t = t.resize((max(1, int(round(t.size[0] * f))), t.size[1]), Image.LANCZOS)
            d.bitmap((int(round(tx * k - t.size[0] / 2)), int(round(ty * k - t.size[1] / 2))), t, fill=255)
        cv.paint(cv.mask(num), col)


def doorway(cv_house):
    """the gable round the door, the doorway open: dark inside, lit a little from the front"""
    cv = Canvas(240, 240)
    cv.c[:] = cv_house.c
    hx, hy = HOLE_C
    inside = lambda x0, y0, x1, y1: interior(x0, y0, x1, y1)
    cv.ellipse(hx, hy, HOLE_R, HOLE_R, inside)
    cv.rect(hx - HOLE_R, hy, hx + HOLE_R, HOLE_BOT, inside)
    return cv


def interior(x0, y0, x1, y1):
    yy, xx = np.mgrid[y0:y1, x0:x1].astype(np.float32) / K
    d = np.clip(np.hypot(xx - HOLE_C[0], (yy - HOLE_C[1] - 6) * 0.8) / 12, 0, 1)
    return np.array((22, 15, 10), np.float32)[None, None, :] / 255 * (1 + 0.9 * d[..., None])


def bird(beak_open):
    """the cuckoo, in profile to the right, on its perch; drawn 16 times over, kept at twice the screen's size"""
    w, h = 28, 22
    cv = Canvas(w, h, 16)
    back, body, breast, bar = (96, 80, 68), (132, 114, 96), (222, 212, 192), (92, 82, 72)
    cv.rect(4, 19.6, 23, 20.8, wood(WOOD_M, WOOD_D, False, 40, 16))   # the perch
    cv.poly([(8.5, 11.5), (0.6, 15.6), (1.4, 17.6), (10, 14.2)], (70, 58, 50))   # the tail
    for t in (0.3, 0.6):
        cv.ellipse(1.2 + 7 * t, 16.4 - 3.4 * t + 0.9, 0.5, 0.4, (230, 226, 216), 0.9)
    cv.ellipse(12.4, 12.6, 7.2, 5.1, body)
    cv.paint(cv.mask(lambda d, P, k: d.chord(P([(6.0, 9.4), (19.6, 18.0)]), 20, 160, fill=255)), breast)
    for i in range(5):                                                # the barred breast
        y = 14.2 + i * 0.9
        cv.line([(9.2 + i * 0.3, y), (16.8 - i * 0.5, y + 0.3)], 0.32, bar, 0.75)
    cv.ellipse(11.0, 11.4, 5.4, 3.0 if not beak_open else 3.4, back)  # the wing (raised a little as it calls)
    for i in range(3):
        cv.line([(7.0 + i * 1.3, 12.6 + i * 0.2), (12.5 + i * 1.0, 11.5)], 0.3, shade(back, 0.7))
    cv.ellipse(18.4, 7.4, 3.8, 3.6, body)                             # the head
    cv.ellipse(19.5, 6.6, 1.05, 1.05, (250, 246, 236))
    cv.ellipse(19.7, 6.6, 0.7, 0.7, (12, 10, 10))
    cv.ellipse(19.9, 6.3, 0.22, 0.22, (255, 255, 255))
    if beak_open:
        cv.poly([(21.4, 7.3), (24.6, 7.9), (21.4, 9.2)], (150, 30, 30))
        cv.poly([(21.3, 6.6), (26.0, 6.4), (21.6, 7.9)], (236, 176, 52))
        cv.poly([(21.3, 8.4), (25.2, 10.1), (21.4, 9.4)], (220, 160, 46))
    else:
        cv.poly([(21.3, 6.9), (26.0, 7.8), (21.3, 8.9)], (236, 176, 52))
        cv.line([(21.6, 7.9), (25.2, 7.8)], 0.2, (140, 96, 30))
    for x in (11.0, 14.0):                                            # its feet round the perch
        cv.line([(x, 17.4), (x + 0.4, 19.8)], 0.5, (190, 140, 60))
    big = Canvas(w, h, 16)
    big.c = cv.c
    pix = cv.c.reshape(h * 2, 8, w * 2, 8, 4).mean(axis=(1, 3))       # twice the screen's resolution
    return pix


def weight():
    """a pine cone in cast iron on its hook: rows of scales, the light from the top left"""
    w, h = 16, 40
    cv = Canvas(w, h)
    cx = w / 2
    cv.ellipse(cx, 1.6, 1.3, 1.3, (60, 56, 52))                       # the hook's eye
    cv.ellipse(cx, 1.6, 0.6, 0.6, (0, 0, 0))
    cv.rect(cx - 1.5, 2.6, cx + 1.5, 5, (70, 62, 56))                 # the cap
    for row in range(14):
        y = 5 + row * 2.45
        t = row / 13
        half = 6.6 * np.sin(np.pi * min(1.0, 0.18 + 0.95 * t)) ** 0.8 + 0.6
        n = 4 if row % 2 else 5
        for j in range(n):
            u = (j + (0.5 if row % 2 else 0.0)) / (n - 0.5) * 2 - 1
            if abs(u) > 1.05:
                continue
            x = cx + u * half * 0.86
            lit = 0.78 + 0.5 * max(0.0, -u) * (1 - t) - 0.25 * t
            cv.ellipse(x, y + 1.2, half / n * 1.35 + 0.6, 1.75, shade((92, 80, 70), lit))
            cv.ellipse(x - 0.3, y + 0.5, half / n * 0.9 + 0.3, 0.7, shade((130, 116, 102), lit), 0.8)
    return cv.down()


# ---- the house: a carved Black Forest house of its own, in dark walnut
WN_L, WN_M, WN_D, WN_X = (164, 82, 52), (112, 48, 30), (72, 28, 18), (40, 14, 9)   # (a dark, red walnut)
IVORY = (238, 226, 198)
SERIF = "/usr/share/fonts/truetype/dejavu/DejaVuSerif-Bold.ttf"


def leaf_pts(cx, cy, s, ang, n=60):
    """a carved leaf, five-lobed (a vine's, a maple's), its tip along ang (degrees, 0 up), its stalk opposite"""
    out = []
    for i in range(n):
        f = 2 * np.pi * i / n
        r = s * (0.42 + 0.58 * abs(np.cos(2.5 * f)) ** 0.7) * (1 + 0.05 * np.sin(15 * f))
        a = f + np.radians(ang)
        out.append((cx + r * np.sin(a), cy - r * np.cos(a)))
    return out


def carved(cv, pts, mid, light, dark, depth=0.55):
    """a carved shape: its shadow below and right, its lit edge above and left, its face between"""
    c = np.mean(np.array(pts), axis=0)
    cv.poly([(x + depth, y + depth * 1.1) for x, y in pts], dark)
    cv.poly([(x - depth * 0.6, y - depth * 0.7) for x, y in pts], light)
    cv.poly([(c[0] + (x - c[0]) * 0.92, c[1] + (y - c[1]) * 0.92) for x, y in pts], mid)


def carved_leaf(cv, cx, cy, s, ang, mid=WN_M, light=WN_L, dark=WN_X):
    carved(cv, leaf_pts(cx, cy, s, ang), mid, light, dark, depth=0.25 + 0.05 * s)
    for k in (0, 72, -72, 144, -144):                                 # its veins
        a = np.radians(ang + k)
        cv.line([(cx, cy), (cx + 0.75 * s * np.sin(a), cy - 0.75 * s * np.cos(a))], max(0.25, 0.05 * s), dark, 0.55)
    a = np.radians(ang + 180)                                         # its stalk
    cv.line([(cx + 0.35 * s * np.sin(a), cy - 0.35 * s * np.cos(a)), (cx + 0.75 * s * np.sin(a), cy - 0.75 * s * np.cos(a))],
            max(0.35, 0.09 * s), mid)


def carved_line(cv, pts, w, mid=WN_M, light=WN_L, dark=WN_X):
    """a carved stem or scroll: a rounded rod, lit above"""
    cv.line([(x + 0.45, y + 0.55) for x, y in pts], w, dark)
    cv.line([(x - 0.25, y - 0.3) for x, y in pts], w * 0.9, light)
    cv.line(pts, w * 0.6, mid)


def spiral(cx, cy, r0, r1, a0, a1, n=40):
    """points of a scroll: from radius r0 at angle a0 to r1 at a1 (degrees, 0 up, clockwise)"""
    out = []
    for i in range(n + 1):
        t = i / n
        a = np.radians(a0 + (a1 - a0) * t)
        r = r0 + (r1 - r0) * t
        out.append((cx + r * np.sin(a), cy - r * np.cos(a)))
    return out


def turned(cv, x0, x1, y0, y1, seed):
    """a turned column, x0..x1 wide, y0..y1: a shaft with rings and a bulge, lit from the left"""
    cx, w = (x0 + x1) / 2, (x1 - x0)
    cv.rect(x0 + w * 0.18, y0, x1 - w * 0.18, y1, wood(WN_M, WN_D, True, seed))
    cv.rect(x0 + w * 0.18, y0, x0 + w * 0.4, y1, WN_L, 0.35)
    for y in np.arange(y0 + 3, y1 - 2, 9.0):
        cv.ellipse(cx, y, w * 0.55, 1.1, WN_D)
        cv.ellipse(cx - w * 0.12, y - 0.3, w * 0.42, 0.7, WN_L, 0.8)
    mid = (y0 + y1) / 2
    cv.ellipse(cx, mid, w * 0.62, 5.5, wood(WN_M, WN_D, True, seed + 1))
    cv.ellipse(cx - w * 0.15, mid - 1.2, w * 0.3, 3.2, WN_L, 0.45)


def house():
    cv = Canvas(240, 240)
    # the body: one carved board, the gable above it, behind everything
    cv.poly([(78, 146), (78, 64), (120, 21), (162, 64), (162, 146)], wood(WN_M, WN_D, True, 101, period=2.6))
    for x in range(84, 158, 7):                                       # its boards' joints, faint
        top = max(64 - (42 - abs(x - CX)) * 43 / 42, 21)
        cv.line([(x, top + 1), (x, 146)], 0.3, WN_X, 0.35)
    # round the dial: vines climbing either side, their leaves, the grapes
    for s_ in (-1, 1):
        stem = [(CX + s_ * 36, 128), (CX + s_ * 39, 116), (CX + s_ * 38.5, 102), (CX + s_ * 36, 88), (CX + s_ * 31, 76),
                (CX + s_ * 24, 70)]
        carved_line(cv, stem, 1.4)
        for (lx, ly, ls, la) in ((38.6, 121, 5.2, 70), (40.4, 106, 5.6, 100), (39.5, 91, 5.0, 60), (32.0, 73.5, 4.4, 30),
                                 (29.0, 128.5, 4.2, 150)):
            carved_leaf(cv, CX + s_ * lx, ly, ls, s_ * la)
        for i, (gx, gy) in enumerate(((35.0, 110.5), (33.6, 112.4), (36.2, 112.6), (34.8, 114.4), (35.4, 116.2))):
            cv.ellipse(CX + s_ * gx + 0.3, gy + 0.4, 1.1, 1.1, WN_X)
            cv.ellipse(CX + s_ * gx, gy, 1.0, 1.0, WN_M)
            cv.ellipse(CX + s_ * gx - 0.3, gy - 0.35, 0.4, 0.4, WN_L)
    # the columns either side, turned, standing on the shelf, their drops below it
    for x0 in (66, 166):
        turned(cv, x0, x0 + 8, 66, 133, 110 + x0)
        cv.rect(x0 - 0.5, 63, x0 + 8.5, 67, wood(WN_D, WN_X, False, 120))   # the capital
        cv.rect(x0 + 0.5, 61, x0 + 7.5, 63.5, WN_M)
        cv.ellipse(x0 + 4, 143, 3.6, 3.2, wood(WN_M, WN_D, False, 121))  # the drop: a ball, a ring, a point
        cv.ellipse(x0 + 3, 142, 1.6, 1.3, WN_L, 0.55)
        cv.ellipse(x0 + 4, 148.5, 2.4, 1.4, WN_D)
        cv.poly([(x0 + 2.0, 149), (x0 + 6.0, 149), (x0 + 4, 157)], wood(WN_M, WN_D, True, 122))
    # the shelf the house stands on: a beam with turned ends, beyond the columns
    cv.rect(60, 132, 180, 139, wood(WN_M, WN_D, False, 130))
    cv.rect(60, 132, 180, 133.4, WN_L, 0.55)
    cv.rect(60, 137.8, 180, 139, WN_X, 0.6)
    for xe in (58.5, 181.5):
        cv.ellipse(xe, 135.5, 3.0, 3.6, wood(WN_M, WN_D, False, 131))
        cv.ellipse(xe - 0.8, 134.4, 1.2, 1.4, WN_L, 0.6)
    # under it, the fretwork: two scrolls curling in from the columns, leaves on them, a leaf hanging in the middle
    # (open between, so the chains and the pendulum show through)
    for s_ in (-1, 1):
        sc = spiral(CX + s_ * 22, 150, 13.0, 3.2, s_ * -80, s_ * 250)
        carved_line(cv, [(CX + s_ * 46, 139.5)] + sc, 1.5)
        carved_leaf(cv, CX + s_ * 38, 147.5, 4.6, s_ * 120)
        carved_leaf(cv, CX + s_ * 9, 143.5, 3.6, s_ * 200)
        cv.line([(CX + s_ * 30, 139.2), (CX + s_ * 1, 139.2)], 1.2, WN_D)
    # the drop: a leaf, its tip down, on a carved stem from under the shelf (a bead on it), the pendulum behind it
    carved_line(cv, [(CX, 138.6), (CX, 153.6)], 2.6)
    cv.ellipse(CX + 0.3, 145.8, 2.5, 2.4, WN_X)
    cv.ellipse(CX, 145.5, 2.3, 2.2, wood(WN_M, WN_D, False, 140))
    cv.ellipse(CX - 0.6, 144.8, 0.9, 0.8, WN_L, 0.7)
    carved_leaf(cv, CX, 156, 7.2, 180)
    # the dial: a carved bezel, a brass bead, the ivory face, its hours and minutes
    cx, cy = DIAL_C
    cv.ellipse(cx + 1.0, cy + 1.4, DIAL_R + 0.6, DIAL_R + 0.6, (0, 0, 0), 0.45)
    cv.ellipse(cx, cy, DIAL_R, DIAL_R, wood(WN_D, WN_X, False, 150))
    for i in range(36):                                               # the bezel, carved: a ring of beads
        a = np.radians(i * 10)
        bx, by = cx + 29.0 * np.sin(a), cy - 29.0 * np.cos(a)
        cv.ellipse(bx + 0.3, by + 0.35, 1.45, 1.45, WN_X)
        cv.ellipse(bx, by, 1.3, 1.3, WN_M)
        cv.ellipse(bx - 0.35, by - 0.4, 0.55, 0.55, WN_L, 0.8)
    cv.ellipse(cx, cy, 27.0, 27.0, BRASS)
    cv.ellipse(cx, cy, FACE_R, FACE_R, lambda x0, y0, x1, y1: ivory_fill(x0, y0, x1, y1))
    for mnt in range(60):
        a = np.radians(mnt * 6)
        r0 = 23.0 if mnt % 5 else 21.6
        cv.line([(cx + r0 * np.sin(a), cy - r0 * np.cos(a)), (cx + 24.8 * np.sin(a), cy - 24.8 * np.cos(a))],
                0.45 if mnt % 5 else 0.9, (62, 40, 28))
    cv.ellipse(cx, cy, 24.8, 24.8, (62, 40, 28), 0.0)
    numerals(cv, cx, cy, 17.6, SERIF, 6.1, (44, 28, 20), 0.86)     # the hours, upright, in a serif
    # the doorway: a carved frame, a sill, and a leaf over it
    hx, hy = HOLE_C
    cv.ellipse(hx + 0.5, hy + 0.6, HOLE_R + 2.4, HOLE_R + 2.4, WN_X)
    cv.ellipse(hx, hy, HOLE_R + 2.2, HOLE_R + 2.2, wood(WN_D, WN_X, False, 160))
    cv.rect(hx - HOLE_R - 2.2, hy, hx + HOLE_R + 2.2, HOLE_BOT + 0.5, wood(WN_D, WN_X, True, 161))
    cv.rect(hx - HOLE_R - 4.0, HOLE_BOT, hx + HOLE_R + 4.0, HOLE_BOT + 2.4, wood(WN_L, WN_M, False, 162))
    carved_leaf(cv, hx, hy - HOLE_R - 3.4, 3.4, 0)
    # the roof: two carved boards, their undersides cut in arches, leaves along their tops, a crest at the peak
    for s_ in (-1, 1):
        p0, p1 = np.array([CX, 14.0]), np.array([CX + s_ * 68, 68.0])
        dv = (p1 - p0) / np.linalg.norm(p1 - p0)
        nr = np.array([-dv[1], dv[0]]) * (-s_)                        # (outwards, up)
        if nr[1] > 0:
            nr = -nr
        L = np.linalg.norm(p1 - p0)
        q0, q1 = p0 - nr * 5.0, p1 - nr * 5.0                         # the board, 5 px deep, below the line
        cv.poly([tuple(p0 + nr * 0.6), tuple(p1 + nr * 0.6), tuple(q1), tuple(q0)], wood(WN_M, WN_D, False, 170 + s_))
        cv.line([tuple(p0 + nr * 0.5), tuple(p1 + nr * 0.5)], 0.8, WN_L, 0.7)
        for t in np.arange(7.0, L - 3, 6.2):                          # the arches cut under it
            c = p0 + dv * t - nr * 5.0
            cv.ellipse(c[0], c[1], 2.4, 2.4, wood(WN_M, WN_D, False, 172))
            cv.ellipse(c[0] - nr[0] * 1.0, c[1] - nr[1] * 1.0, 1.0, 1.0, (0, 0, 0), 0.0)
        for i, t in enumerate(np.arange(15.0, L - 5, 12.0)):          # leaves along it, smaller to the eaves,
            c = p0 + dv * t + nr * 3.2                                # turned out from the roof in turn
            size = 7.0 - 2.0 * t / L
            ang = np.degrees(np.arctan2(nr[0], -nr[1])) + s_ * (34 if i % 2 else 4)
            carved_leaf(cv, c[0], c[1], size, ang)
        e = p1 + dv * 1.5 - nr * 2.0                                  # the eaves' end: a turned knob
        cv.ellipse(e[0], e[1], 2.6, 2.6, wood(WN_M, WN_D, False, 175))
        cv.ellipse(e[0] - 0.7, e[1] - 0.8, 1.0, 1.0, WN_L, 0.7)
    carved_leaf(cv, CX - 10.5, 11.5, 7.0, -48)                        # the crest: three leaves fanned at the peak
    carved_leaf(cv, CX + 10.5, 11.5, 7.0, 48)
    carved_leaf(cv, CX, 8.2, 8.2, 0)
    return cv


def ivory_fill(x0, y0, x1, y1):
    yy, xx = np.mgrid[y0:y1, x0:x1].astype(np.float32) / K
    r = np.hypot(xx - DIAL_C[0] + 6, yy - DIAL_C[1] + 8) / 40
    base = np.array(IVORY, np.float32) / 255
    return base * (1.03 - 0.14 * np.clip(r, 0, 1))[..., None]


def door_leaf():
    """the door, shut: an arched board in walnut, a raised panel, a small carved leaf, a brass knob"""
    w, h = int(2 * HOLE_R + 1), int(HOLE_BOT - (HOLE_C[1] - HOLE_R)) + 1
    cv = Canvas(w, h)
    ox, oy = HOLE_C[0] - HOLE_R - 0.5, HOLE_C[1] - HOLE_R - 0.5
    hx, hy = HOLE_C[0] - ox, HOLE_C[1] - oy
    cv.ellipse(hx, hy, HOLE_R + 0.5, HOLE_R + 0.5, wood(WN_M, WN_D, True, 180))
    cv.rect(hx - HOLE_R - 0.5, hy, hx + HOLE_R + 0.5, h, wood(WN_M, WN_D, True, 180))
    cv.ellipse(hx, hy, HOLE_R - 1.8, HOLE_R - 1.8, wood(WN_L, WN_M, True, 181))
    cv.rect(hx - HOLE_R + 1.8, hy, hx + HOLE_R - 1.8, h - 2.0, wood(WN_L, WN_M, True, 181))
    carved_leaf(cv, hx, hy + 3.6, 3.6, 0, WN_M, WN_L, WN_X)
    cv.ellipse(hx + HOLE_R - 2.6, hy + 9.5, 0.8, 0.8, BRASS)
    return cv.down(), (ox, oy)


def bob():
    """the bob: a carved leaf in walnut, its tip down, a brass eye on the stick"""
    r = 11.0
    n = int(2 * r + 3)
    cv = Canvas(n, n)
    c = n / 2
    cv.ellipse(c, c - r + 0.6, 1.4, 1.6, BRASS)
    carved_leaf(cv, c, c + 0.8, r - 0.6, 180)
    return cv.down()


WALL_TW = 80                                    # the panel wall: four boards a tile, the tile across the screen


def wall_tile():
    """the wall the cuckoos hang on: tongue-and-groove pine boards, stained honey, a V at each joint; lit from above"""
    k = 4
    cv = Canvas(WALL_TW, 240, k)
    for b in range(4):
        x0, x1 = b * 20, b * 20 + 20
        base = shade((176, 132, 90), 0.94 + 0.06 * ((b * 7) % 3))
        cv.rect(x0, 0, x1, 240, wood(base, shade(base, 0.8), True, 200 + b, k, period=2.8))
        cv.rect(x0, 0, x0 + 0.8, 240, shade(base, 0.55))            # the V: its shadowed side, its lit side
        cv.rect(x1 - 0.9, 0, x1, 240, shade(base, 1.12), 0.8)
    for kx, ky in ((13.0, 58.0), (47.0, 171.0)):                     # two knots, faint (the tile repeats)
        cv.ellipse(kx, ky, 2.2, 3.4, (120, 84, 52), 0.35)
        cv.ellipse(kx, ky, 1.0, 1.6, (96, 64, 40), 0.35)
    t = cv.down()[..., :3] * 255
    light = (1.04 - 0.16 * (np.arange(240) / 239.0))[:, None, None]  # lighter at the top
    return np.clip(t * light, 0, 255)


def shadowed(scr, wall):
    """the wall with the house's shadow on it (3 px right, 4 down, soft), the house itself not there"""
    a = scr[..., 3]
    sh = np.zeros_like(a)
    sh[4:, 3:] = a[:-4, :-3]
    sh = np.asarray(Image.fromarray((sh * 255).astype(np.uint8)).filter(ImageFilter.GaussianBlur(2.2)), np.float32) / 255
    return wall * (1 - 0.5 * sh[..., None])


def on_wall(scr, wall):
    """a premultiplied picture over the wall, its shadow on it"""
    return scr[..., :3] * 255 + shadowed(scr, wall) * (1 - scr[..., 3:])


def shut_door(scr, leaf, at):
    """the house with its door shut: the leaf on the doorway"""
    shut = scr.copy()
    ix, iy = at
    lh, lw = leaf.shape[:2]
    reg = shut[iy:iy + lh, ix:ix + lw]
    reg[..., :3] = leaf[..., :3] + reg[..., :3] * (1 - leaf[..., 3:])
    reg[..., 3:] = leaf[..., 3:] + reg[..., 3:] * (1 - leaf[..., 3:])
    return shut


def build():
    tile = wall_tile()
    wall = np.concatenate([tile] * (240 // WALL_TW + 1), axis=1)[:, :240]
    cvh = house()
    leaf, (lox, loy) = door_leaf()
    at = (int(round(lox)), int(round(loy)))
    scr = shut_door(cvh.down(), leaf, at)
    opened = doorway(cvh).down()
    return dict(tile=tile, wall=wall, bird0=bird(False), bird1=bird(True), weight=weight(), scr=scr, opened=opened,
                leaf=leaf, leaf_at=at, bob=bob(), on_wall=on_wall(scr, wall), opened_on_wall=on_wall(opened, wall),
                wall_sh=shadowed(scr, wall))


def rgb565(c):
    c = np.clip(np.round(c), 0, 255).astype(np.int64)
    return (c[..., 0] >> 3) << 11 | (c[..., 1] >> 2) << 5 | (c[..., 2] >> 3)


def swapped(v):
    return ((v & 0xFF) << 8) | (v >> 8)


def carray(name, ctype, vals, per=16):
    vals = list(vals)
    lines = [f"static const {ctype} {name}[{len(vals)}] = {{"]
    for i in range(0, len(vals), per):
        lines.append("    " + ", ".join(str(int(v)) for v in vals[i:i + per]) + ",")
    lines.append("};")
    return "\n".join(lines)


def rgba8(a):
    return np.clip(np.round(a * 255), 0, 255).astype(int)


def header(a):
    wall = a["wall"]
    ys, xs = np.where(np.abs(a["on_wall"] - wall).max(axis=2) > 0.5)   # the box the house and its shadow are in
    bx0, by0, bx1, by1 = int(xs.min()), int(ys.min()), int(xs.max()) + 1, int(ys.max()) + 1
    dx, dy, dw, dh = DOOR_RGN
    s256 = lambda v: int(round(v * 256))
    sw = lambda img: swapped(rgb565(img)).ravel()
    d = a
    out = ["/* SPDX-License-Identifier: GPL-3.0-only */",
           "/* generated by tools/gen_art_cuckoo.py: do not edit */",
           "#pragma once", "#include <stdint.h>",
           "/* the cuckoo clock: the box its house and shadow are in, the layout */",
           f"#define CB_X {bx0}", f"#define CB_Y {by0}", f"#define CB_W {bx1 - bx0}", f"#define CB_H {by1 - by0}",
           f"#define CK_HUB_X256 {s256(DIAL_C[0])}", f"#define CK_HUB_Y256 {s256(DIAL_C[1])}",
           f"#define CK_DIAL_R256 {s256(FACE_R)}",
           f"#define CK_PIVOT_X256 {s256(PIVOT[0])}", f"#define CK_PIVOT_Y256 {s256(PIVOT[1])}",
           f"#define CK_BOB_Y256 {s256(BOB_Y)}",
           f"#define CK_FRONT_Y {FRONT_Y}   /* from this row down the house is a front layer over what hangs below it */",
           f"#define CK_LO_X {LO_X}   /* and what hangs below it is drawn from CK_LO_X, CK_LO_W wide */",
           f"#define CK_LO_W {LO_W}",
           f"#define CK_W_TOP {W_TOP}   /* a weight's hook, wound up */",
           f"#define CK_TRAVEL {TRAVEL}   /* its way down in a run; its ring's up */",
           f"#define CK_RING_LOW {W_TOP + 7 + TRAVEL}   /* the ring's centre, wound up */",
           f"#define CK_DR_X {dx}", f"#define CK_DR_Y {dy}", f"#define CK_DR_W {dw}", f"#define CK_DR_H {dh}",
           f"#define CK_HOLE_X256 {s256(HOLE_C[0])}   /* the doorway: an arch round this, down to CK_HOLE_BOT256 */",
           f"#define CK_HOLE_Y256 {s256(HOLE_C[1])}", f"#define CK_HOLE_R256 {s256(HOLE_R)}",
           f"#define CK_HOLE_BOT256 {s256(HOLE_BOT)}",
           f"#define CK_LEAF_X {d['leaf_at'][0]}   /* the door's leaf, its hinge on its left edge */",
           f"#define CK_LEAF_Y {d['leaf_at'][1]}", f"#define CK_LEAF_W {d['leaf'].shape[1]}",
           f"#define CK_LEAF_H {d['leaf'].shape[0]}",
           f"#define CK_BIRD_W {a['bird0'].shape[1]}   /* the bird, at twice the screen's size */",
           f"#define CK_BIRD_H {a['bird0'].shape[0]}",
           "#define CK_BIRD_FX2 26   /* its feet in the sprite (x 2) */", "#define CK_BIRD_FY2 40",
           f"#define CK_BOB_W {d['bob'].shape[1]}", f"#define CK_BOB_H {d['bob'].shape[0]}",
           f"#define CK_WT_W {a['weight'].shape[1]}", f"#define CK_WT_H {a['weight'].shape[0]}",
           f"#define CK_WALL_TW {WALL_TW}   /* the panel wall they hang on: a tile this wide, the screen's height */"]
    for i, x in enumerate(STRANDS):
        out.append(f"#define CK_STRAND{i}_X256 {s256(x)}")
    out.append("/* the wall: pine boards, RGB565 in the screen's byte order, CK_WALL_TW x 240, across the screen again */")
    out.append(carray("CK_WALL_SW", "uint16_t", sw(a["tile"])))
    out.append("/* the house, its door shut, on the wall (its shadow on it), RGB565 */")
    out.append(carray("CK_HOUSE", "uint16_t", sw(d["on_wall"][by0:by1, bx0:bx1])))
    out.append("/* the house from CK_FRONT_Y down, premultiplied R G B A: over the pendulum and the chains */")
    out.append(carray("CK_FRONT", "uint8_t", rgba8(d["scr"][FRONT_Y:by1, bx0:bx1]).reshape(-1, 4).ravel(), 32))
    out.append("/* the wall behind what hangs below it (the house's shadow on it), RGB565 */")
    out.append(carray("CK_LOWALL", "uint16_t", sw(d["wall_sh"][FRONT_Y:240, LO_X:LO_X + LO_W])))
    out.append("/* round the door: the gable with the doorway open (and the leaf away), on the wall, RGB565 */")
    out.append(carray("CK_DRBG", "uint16_t", sw(d["opened_on_wall"][dy:dy + dh, dx:dx + dw])))
    out.append("/* the door's leaf, the bob: premultiplied R G B A */")
    out.append(carray("CK_LEAF", "uint8_t", rgba8(d["leaf"]).reshape(-1, 4).ravel(), 32))
    out.append(carray("CK_BOB", "uint8_t", rgba8(d["bob"]).reshape(-1, 4).ravel(), 32))
    out.append("/* the bird (its beak shut, open; x 2), a weight: premultiplied R G B A */")
    out.append(carray("CK_BIRD0_RGBA", "uint8_t", rgba8(a["bird0"]).reshape(-1, 4).ravel(), 32))
    out.append(carray("CK_BIRD1_RGBA", "uint8_t", rgba8(a["bird1"]).reshape(-1, 4).ravel(), 32))
    out.append(carray("CK_WT_RGBA", "uint8_t", rgba8(a["weight"]).reshape(-1, 4).ravel(), 32))
    return "\n".join(out) + "\n"


def paste(img, spr, x0, y0):
    h, w = spr.shape[:2]
    for y in range(h):
        for x in range(w):
            X, Y = x0 + x, y0 + y
            if 0 <= X < img.shape[1] and 0 <= Y < img.shape[0]:
                p = spr[y, x]
                img[Y, X] = p[:3] * 255 + img[Y, X] * (1 - p[3])


def preview(a, path):
    """the clock as the firmware shows it, on the wall, at rest and with the bird out (3 x)"""
    def scene(d, bird_out):
        img = d["wall_sh"].copy()
        px, py = PIVOT
        for y in range(int(py), int(BOB_Y)):                         # the stick
            img[y, 119:121] = (130, 76, 36)
        paste(img, d["bob"], int(round(120 - d["bob"].shape[1] / 2)), int(round(BOB_Y - d["bob"].shape[0] / 2)))
        for i, sx in enumerate(STRANDS):
            bot = W_TOP + 20 if i in (0, 3) else W_TOP + TRAVEL - 20
            for y in range(150, bot):
                img[y, int(sx)] = (210, 178, 104) if y % 2 else (120, 96, 48)
            if i in (0, 3):
                paste(img, a["weight"], int(sx - a["weight"].shape[1] / 2), bot)
        scr = d["opened"] if bird_out else d["scr"]
        img = scr[..., :3] * 255 + img * (1 - scr[..., 3:])
        if bird_out:
            b = a["bird1"]
            small = b.reshape(b.shape[0] // 2, 2, b.shape[1] // 2, 2, 4).mean(axis=(1, 3))
            paste(img, small, 120 - 13, int(HOLE_BOT) - 20)
        return img
    both = np.concatenate([scene(a, False), scene(a, True)], axis=1)
    Image.fromarray(np.clip(both, 0, 255).astype(np.uint8)).resize((1440, 720), Image.LANCZOS).save(path)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--preview", type=Path)
    a = ap.parse_args()
    art = build()
    h = header(art)
    if a.preview:
        preview(art, a.preview)
    if a.check:
        if not OUT.exists() or OUT.read_text() != h:
            print("firmware/gen/clk_art_cuckoo.h is not what tools/gen_art_cuckoo.py makes: run it")
            return 1
        print("clk_art_cuckoo.h: up to date")
        return 0
    OUT.write_text(h)
    print(f"{OUT.relative_to(ROOT)}: {len(h) // 1024} KB of source")
    return 0


if __name__ == "__main__":
    sys.exit(main())
