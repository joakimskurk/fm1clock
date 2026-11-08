#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""FM1 Clock's own cuckoo clock, drawn from nothing: firmware/gen/clk_art_cuckoo.h.

  python3 tools/gen_art_cuckoo.py [--check] [--preview OUT.png]     (Pillow, numpy)

A painted Black Forest chalet, of this firmware's own: a shingled roof with a carved barge board and a turned
finial, the bird's door in the gable, a big cream dial (Arabic numerals, a carved bezel), two shuttered windows with
geraniums, and a balcony of sawn boards. Everything is drawn 8 times over (polygons, ellipses, wood grain from
smoothed noise) and box-filtered down to the screen, so its edges are soft.

What moves is the firmware's (firmware/src/clk_draw.h), from sprites made here:
  - the door: its leaf, turned about its hinge in perspective; the gable behind it with the doorway open (dark);
  - the bird, in two poses (its beak shut, open), at twice the screen's resolution: the firmware scales it as it
    comes forward out of the dark and turns it as it bows to its call;
  - the pendulum's bob (a wooden disc, a brass rim, an edelweiss), turned with its stick;
  - a pine-cone weight (cast iron), for both chains; the rings and the chains themselves are drawn by the firmware.
The house's lowest rows (the balcony, the carved apron) are a front layer over the chains and the pendulum.
"""
import argparse
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "firmware" / "gen" / "clk_art_cuckoo.h"
FONT = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
K = 8                                       # drawn at 8 x 8 samples a screen pixel

# the layout, in screen pixels
CX = 120.0
DIAL_C, DIAL_R, FACE_R = (120.0, 99.0), 31.0, 26.2
HOLE_C, HOLE_R, HOLE_BOT = (120.0, 43.0), 9.0, 61.0      # the bird's doorway: an arch, its bottom
DOOR_RGN = (92, 28, 56, 36)                 # what the door and the bird can touch: x, y, w, h
FRONT_Y = 146                               # from here down the house is in front of the chains and the pendulum
HOUSE_BOT = 166                             # the apron's lowest point (its scallops, its drop)
PIVOT = (120.0, 99.0)                       # behind the dial
BOB_Y = 206.0
STRANDS = (100.0, 110.0, 130.0, 140.0)      # the chains: the going weight, its ring, the cuckoo's ring, its weight
W_TOP = 169                                 # a weight's hook, wound up
TRAVEL = 66                                 # and how far it goes down in a run (the ring as far up)

WOOD_L, WOOD_M, WOOD_D, WOOD_X = (204, 148, 88), (156, 100, 56), (100, 62, 32), (62, 38, 20)
PLASTER = (238, 228, 204)
GREEN = (66, 112, 70)
ROOF_A, ROOF_B = (92, 58, 40), (70, 44, 32)
BRASS = (206, 166, 76)
RED = (206, 44, 40)


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
def house():
    cv = Canvas(240, 240)
    # the facade behind the roof: the gable's boards above the beam, the plaster below it
    cv.poly([(72, 66), (72, 62), (120, 18), (168, 62), (168, 66)], wood(WOOD_M, WOOD_D, True, 3, period=3.0))
    for x in range(78, 166, 6):                                       # the boards' joints, under the roof
        top = 18 + abs(x - CX) * 44 / 48
        cv.line([(x, top), (x, 66)], 0.35, WOOD_X, 0.6)
    cv.rect(72, 66, 168, 152, lambda *b: np.array(PLASTER, np.float32) / 255 * (0.94 + 0.06 * noise(b[3] - b[1], b[2] - b[0], 2 * K, 9)[..., None]))
    # the timber: a beam under the gable, the corner posts, braces
    cv.rect(70, 63, 170, 68, wood(WOOD_D, WOOD_X, False, 4))
    cv.rect(71, 66, 76, 152, wood(WOOD_D, WOOD_X, True, 5))
    cv.rect(164, 66, 169, 152, wood(WOOD_D, WOOD_X, True, 6))
    for s in (-1, 1):                                                 # the windows, shuttered, with geraniums
        x0 = CX + s * 33 - 8
        cv.rect(x0 + 3.5, 71, x0 + 12.5, 87, WOOD_X)
        cv.rect(x0 + 4.5, 72, x0 + 11.5, 86, (44, 58, 80))
        cv.poly([(x0 + 4.5, 72), (x0 + 7.5, 72), (x0 + 4.5, 77)], (120, 140, 170), 0.6)   # the sky in the glass
        cv.rect(x0 + 7.6, 72, x0 + 8.4, 86, WOOD_L)
        cv.rect(x0 + 4.5, 78.6, x0 + 11.5, 79.4, WOOD_L)
        for sx in (x0, x0 + 12.5):                                    # the shutters, slatted
            cv.rect(sx, 70.5, sx + 3.5, 87.5, GREEN)
            for y in np.arange(72, 87, 1.5):
                cv.line([(sx + 0.4, y), (sx + 3.1, y)], 0.3, shade(GREEN, 0.6))
        cv.rect(x0 + 2.5, 86.5, x0 + 13.5, 90, wood(WOOD_M, WOOD_D, False, 8))   # the flower box
        rng = np.random.default_rng(int(x0))
        for i in range(9):
            fx, fy = x0 + 3.5 + i * 1.2 + rng.random() * 0.4, 85.4 + rng.random() * 1.2
            cv.ellipse(fx, fy + 1.3, 0.9, 0.7, (60, 120, 52))
            cv.ellipse(fx, fy, 0.75, 0.75, RED if i % 3 else (236, 96, 90))
    # the balcony: eighteen sawn boards side by side between the posts, a round hole and a slot cut where every
    # other two meet (nine, the middle one on the clock's middle), rails, posts
    cv.rect(76, 132, 164, 150, (48, 30, 16))
    bw = 88 / 18
    for k in range(18):
        xb = 76 + k * bw
        cv.rect(xb, 135, xb + bw, 146.5, wood(WOOD_L, WOOD_M, True, 60 + k, period=1.6))
        cv.line([(xb + bw - 0.35, 135.4), (xb + bw - 0.35, 146.2)], 0.3, WOOD_D, 0.7)   # its edge, in shadow
    for k in range(1, 18, 2):                                          # the cut-outs, on the joints
        xb = 76 + k * bw
        cv.ellipse(xb, 140.6, 1.35, 1.35, (40, 25, 13))
        cv.rect(xb - 0.45, 136.6, xb + 0.45, 139.4, (40, 25, 13))
        cv.rect(xb - 0.45, 141.8, xb + 0.45, 144.8, (40, 25, 13))
        cv.ellipse(xb - 0.4, 140.2, 0.5, 0.5, WOOD_X, 0.6)
    cv.rect(74, 131, 166, 135.5, wood(WOOD_L, WOOD_M, False, 11))      # the top rail
    cv.rect(74, 146, 166, 150, wood(WOOD_M, WOOD_D, False, 12))       # the floor
    for x in (74, 162):                                               # the end posts, turned
        cv.rect(x, 129, x + 4, 150, wood(WOOD_M, WOOD_D, True, 13))
        cv.ellipse(x + 2, 128.5, 2.4, 2.0, WOOD_L)
    # the apron under it, carved: scallops, and a drop in the middle (a heart)
    cv.rect(73, 150, 167, 158, wood(WOOD_M, WOOD_D, False, 14))
    for j in range(-7, 8):                                            # (fifteen, the middle one under the drop)
        cv.ellipse(CX + j * 6.3, 158, 3.2, 3.0, wood(WOOD_M, WOOD_D, False, 15))
    cv.line([(73, 151), (167, 151)], 0.5, WOOD_L, 0.8)
    cv.ellipse(117.6, 160.5, 3.0, 3.0, WOOD_M)
    cv.ellipse(122.4, 160.5, 3.0, 3.0, WOOD_M)
    cv.poly([(114.8, 161.5), (125.2, 161.5), (120, HOUSE_BOT)], WOOD_M)
    cv.ellipse(117.9, 159.8, 1.0, 0.8, WOOD_L, 0.8)
    # the dial: a carved bezel, a brass bead, the cream face, its numerals and minutes
    cx, cy = DIAL_C
    cv.ellipse(cx + 1.0, cy + 1.4, DIAL_R + 0.4, DIAL_R + 0.4, (0, 0, 0), 0.35)
    cv.ellipse(cx, cy, DIAL_R, DIAL_R, wood(WOOD_D, WOOD_X, False, 16))
    for i in range(48):                                               # the bezel's notches
        a = np.radians(i * 7.5)
        cv.line([(cx + 27.6 * np.sin(a), cy - 27.6 * np.cos(a)), (cx + 30.4 * np.sin(a), cy - 30.4 * np.cos(a))], 0.7,
                WOOD_L if i % 2 else WOOD_X, 0.7)
    cv.ellipse(cx, cy, 27.2, 27.2, BRASS)
    cv.ellipse(cx, cy, FACE_R, FACE_R, lambda x0, y0, x1, y1: face_fill(x0, y0, x1, y1))
    for mnt in range(60):
        a = np.radians(mnt * 6)
        r0 = 22.6 if mnt % 5 else 21.4
        cv.line([(cx + r0 * np.sin(a), cy - r0 * np.cos(a)), (cx + 24.6 * np.sin(a), cy - 24.6 * np.cos(a))],
                0.45 if mnt % 5 else 0.9, (70, 50, 36))
    font = ImageFont.truetype(FONT, int(5.9 * K))
    for h in range(1, 13):
        a = np.radians(h * 30)
        tx, ty = cx + 17.4 * np.sin(a), cy - 17.4 * np.cos(a)
        txt = str(h)

        def num(d, P, k, txt=txt, tx=tx, ty=ty):
            bb = d.textbbox((0, 0), txt, font=font)
            w, hh = bb[2] - bb[0], bb[3] - bb[1]
            d.text((tx * k - w / 2 - bb[0], ty * k - hh / 2 - bb[1]), txt, font=font, fill=255)
        cv.paint(cv.mask(num), (52, 34, 24))
    # the roof: shingles on a thick edge, a scalloped barge board under them, a finial at the peak
    outer = [(52, 62), (120, 7), (188, 62)]
    inner = [(65, 64), (120, 19), (175, 64)]
    cv.poly([(52, 62), (120, 7), (188, 62), (175, 65), (120, 19.5), (65, 65)], shingles)
    for s in (-1, 1):                                                 # the barge board along each slope
        p0, p1 = np.array([120, 19.5]), np.array([120 + s * 55, 65])
        dvec = (p1 - p0) / np.linalg.norm(p1 - p0)
        nrm = np.array([-dvec[1], dvec[0]]) * (1 if s < 0 else -1)
        if nrm[1] < 0:
            nrm = -nrm
        q0, q1 = p0 + nrm * 2.4, p1 + nrm * 2.4
        cv.poly([tuple(p0), tuple(p1), tuple(q1), tuple(q0)], wood(WOOD_L, WOOD_M, False, 20 + s))
        L = np.linalg.norm(p1 - p0)
        for t in np.arange(3.0, L - 1, 4.6):
            c = p0 + dvec * t + nrm * 2.4
            cv.ellipse(c[0], c[1], 1.7, 1.7, wood(WOOD_L, WOOD_M, False, 22))
            cv.ellipse(c[0] + nrm[0] * 0.6, c[1] + nrm[1] * 0.6, 0.6, 0.6, WOOD_X, 0.7)
    cv.line([outer[0], outer[1], outer[2]], 0.7, (40, 24, 16), 0.8)
    cv.rect(118.6, 2.5, 121.4, 9, wood(WOOD_M, WOOD_D, True, 23))     # the finial: a post, a ball, a point
    cv.ellipse(120, 3.6, 2.4, 2.2, WOOD_L)
    cv.poly([(119.2, 1.8), (120.8, 1.8), (120, 0.0)], WOOD_M)
    # the bird's doorway: its frame, a sill, the door shut
    hx, hy = HOLE_C
    cv.ellipse(hx, hy, HOLE_R + 2.0, HOLE_R + 2.0, wood(WOOD_D, WOOD_X, False, 24))
    cv.rect(hx - HOLE_R - 2.0, hy, hx + HOLE_R + 2.0, HOLE_BOT + 0.5, wood(WOOD_D, WOOD_X, True, 25))
    cv.rect(hx - HOLE_R - 3.5, HOLE_BOT, hx + HOLE_R + 3.5, HOLE_BOT + 2.4, wood(WOOD_L, WOOD_M, False, 26))
    return cv


def face_fill(x0, y0, x1, y1):
    yy, xx = np.mgrid[y0:y1, x0:x1].astype(np.float32) / K
    r = np.hypot(xx - DIAL_C[0] + 6, yy - DIAL_C[1] + 8) / 40
    base = np.array((244, 236, 214), np.float32) / 255
    return base * (1.02 - 0.12 * np.clip(r, 0, 1))[..., None]


def shingles(x0, y0, x1, y1):
    """the roof's edge: rows of shingles along the slope, each its own shade"""
    yy, xx = np.mgrid[y0:y1, x0:x1].astype(np.float32) / K
    s = np.sign(xx - CX)
    along = np.abs(xx - CX) * 0.78 + (yy - 7) * 0.62                # down the slope
    across = (yy - 7) * 0.78 - np.abs(xx - CX) * 0.62               # into the roof's edge
    row = np.floor(across / 3.2)
    col = np.floor((along + row * 1.7) / 3.4)
    rng = np.random.default_rng(5)
    tab = rng.random(4096).astype(np.float32)
    v = tab[((row * 61 + col * 17 + (s > 0) * 7).astype(np.int64)) % 4096]
    a, b = np.array(ROOF_A, np.float32) / 255, np.array(ROOF_B, np.float32) / 255
    c = a * v[..., None] + b * (1 - v[..., None])
    edge = ((across % 3.2) < 0.45) | (((along + row * 1.7) % 3.4) < 0.35)
    c[edge] *= 0.55
    return c


def door_leaf():
    """the door, shut, as a sprite of its own (the hinge on its left): an arched board, a carved heart"""
    w, h = int(2 * HOLE_R + 1), int(HOLE_BOT - (HOLE_C[1] - HOLE_R)) + 1
    cv = Canvas(w, h)
    ox, oy = HOLE_C[0] - HOLE_R - 0.5, HOLE_C[1] - HOLE_R - 0.5
    hx, hy = HOLE_C[0] - ox, HOLE_C[1] - oy
    cv.ellipse(hx, hy, HOLE_R + 0.5, HOLE_R + 0.5, wood(WOOD_M, WOOD_D, True, 30))
    cv.rect(hx - HOLE_R - 0.5, hy, hx + HOLE_R + 0.5, h, wood(WOOD_M, WOOD_D, True, 30))
    cv.ellipse(hx, hy, HOLE_R - 1.6, HOLE_R - 1.6, wood(WOOD_L, WOOD_M, True, 31))   # the panel, raised
    cv.rect(hx - HOLE_R + 1.6, hy, hx + HOLE_R - 1.6, h - 1.8, wood(WOOD_L, WOOD_M, True, 31))
    cv.ellipse(hx - 1.3, hy + 4.2, 1.6, 1.6, WOOD_X)                  # the heart, cut through
    cv.ellipse(hx + 1.3, hy + 4.2, 1.6, 1.6, WOOD_X)
    cv.poly([(hx - 2.85, hy + 4.7), (hx + 2.85, hy + 4.7), (hx, hy + 8.2)], WOOD_X)
    cv.ellipse(hx + HOLE_R - 2.6, hy + 9.5, 0.8, 0.8, BRASS)          # the knob
    return cv.down(), (ox, oy)


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


def bob():
    """the pendulum's bob: a wooden disc, a brass rim, an edelweiss"""
    r = 11.0
    n = int(2 * r + 3)
    cv = Canvas(n, n)
    c = n / 2
    cv.ellipse(c, c - r - 0.4, 1.4, 1.6, BRASS)                       # its eye on the stick
    cv.ellipse(c, c, r, r, BRASS)
    cv.ellipse(c, c, r - 1.3, r - 1.3, wood(WOOD_M, WOOD_D, False, 50))
    cv.ellipse(c - 2.5, c - 2.8, r - 6, r - 7, (255, 255, 255), 0.10)  # the light on it
    for i in range(8):                                                # the edelweiss: felted petals, a yellow eye
        a = np.radians(i * 45 + 10)
        cv.ellipse(c + 3.6 * np.sin(a), c - 3.6 * np.cos(a), 1.7, 1.7, (236, 234, 224))
    cv.ellipse(c, c, 1.7, 1.7, (226, 186, 60))
    return cv.down()


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


def build():
    cvh = house()
    scr = cvh.down()
    leaf, (lox, loy) = door_leaf()
    # the house with its door shut: the leaf on the doorway
    shut = scr.copy()
    ix, iy = int(round(lox)), int(round(loy))
    lh, lw = leaf.shape[:2]
    reg = shut[iy:iy + lh, ix:ix + lw]
    reg[..., :3] = leaf[..., :3] + reg[..., :3] * (1 - leaf[..., 3:])
    reg[..., 3:] = leaf[..., 3:] + reg[..., 3:] * (1 - leaf[..., 3:])
    opened = doorway(cvh).down()
    return dict(scr=shut, opened=opened, leaf=leaf, leaf_at=(ix, iy), bird0=bird(False), bird1=bird(True),
                bob=bob(), weight=weight())


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
    scr = a["scr"]
    ys, xs = np.where(scr[..., 3] > 0.02)
    bx0, by0, bx1, by1 = int(xs.min()), int(ys.min()), int(xs.max()) + 1, int(ys.max()) + 1
    over = scr[..., :3] * 255                                          # premultiplied: over black as it is
    dx, dy, dw, dh = DOOR_RGN
    s256 = lambda v: int(round(v * 256))
    out = ["/* SPDX-License-Identifier: GPL-3.0-only */",
           "/* generated by tools/gen_art_cuckoo.py: do not edit */",
           "#pragma once", "#include <stdint.h>",
           f"#define CB_X {bx0}", f"#define CB_Y {by0}", f"#define CB_W {bx1 - bx0}", f"#define CB_H {by1 - by0}",
           f"#define CK_HUB_X256 {s256(DIAL_C[0])}", f"#define CK_HUB_Y256 {s256(DIAL_C[1])}",
           f"#define CK_DIAL_R256 {s256(FACE_R)}",
           f"#define CK_PIVOT_X256 {s256(PIVOT[0])}", f"#define CK_PIVOT_Y256 {s256(PIVOT[1])}",
           f"#define CK_BOB_Y256 {s256(BOB_Y)}",
           f"#define CK_FRONT_Y {FRONT_Y}   /* from this row down the house is a front layer over what hangs below it */",
           f"#define CK_W_TOP {W_TOP}   /* a weight's hook, wound up */",
           f"#define CK_TRAVEL {TRAVEL}   /* its way down in a run; its ring's up */",
           f"#define CK_RING_LOW {W_TOP + 7 + TRAVEL}   /* the ring's centre, wound up */",
           f"#define CK_DR_X {dx}", f"#define CK_DR_Y {dy}", f"#define CK_DR_W {dw}", f"#define CK_DR_H {dh}",
           f"#define CK_HOLE_X256 {s256(HOLE_C[0])}   /* the doorway: an arch round this, down to CK_HOLE_BOT256 */",
           f"#define CK_HOLE_Y256 {s256(HOLE_C[1])}", f"#define CK_HOLE_R256 {s256(HOLE_R)}",
           f"#define CK_HOLE_BOT256 {s256(HOLE_BOT)}",
           f"#define CK_LEAF_X {a['leaf_at'][0]}   /* the door's leaf, its hinge on its left edge */",
           f"#define CK_LEAF_Y {a['leaf_at'][1]}", f"#define CK_LEAF_W {a['leaf'].shape[1]}",
           f"#define CK_LEAF_H {a['leaf'].shape[0]}",
           f"#define CK_BIRD_W {a['bird0'].shape[1]}   /* the bird, at twice the screen's size */",
           f"#define CK_BIRD_H {a['bird0'].shape[0]}",
           "#define CK_BIRD_FX2 26   /* its feet in the sprite (x 2) */", "#define CK_BIRD_FY2 40",
           f"#define CK_BOB_W {a['bob'].shape[1]}", f"#define CK_BOB_H {a['bob'].shape[0]}",
           f"#define CK_WT_W {a['weight'].shape[1]}", f"#define CK_WT_H {a['weight'].shape[0]}"]
    for i, x in enumerate(STRANDS):
        out.append(f"#define CK_STRAND{i}_X256 {s256(x)}")
    out.append("/* the house (the door shut) over black, RGB565 in the screen's byte order */")
    out.append(carray("CB_SW", "uint16_t", swapped(rgb565(over[by0:by1, bx0:bx1])).ravel()))
    out.append("/* the house from CK_FRONT_Y down, premultiplied R G B A: over the pendulum and the chains */")
    out.append(carray("CK_FRONT", "uint8_t", rgba8(scr[FRONT_Y:by1, bx0:bx1]).reshape(-1, 4).ravel(), 32))
    out.append("/* round the door: the gable with the doorway open (and the leaf away), RGB565 in the screen's order */")
    out.append(carray("CK_DRBG_SW", "uint16_t", swapped(rgb565(a["opened"][dy:dy + dh, dx:dx + dw, :3] * 255)).ravel()))
    out.append("/* the door's leaf, the bird (its beak shut, open; x 2), the bob, a weight: premultiplied R G B A */")
    out.append(carray("CK_LEAF_RGBA", "uint8_t", rgba8(a["leaf"]).reshape(-1, 4).ravel(), 32))
    out.append(carray("CK_BIRD0_RGBA", "uint8_t", rgba8(a["bird0"]).reshape(-1, 4).ravel(), 32))
    out.append(carray("CK_BIRD1_RGBA", "uint8_t", rgba8(a["bird1"]).reshape(-1, 4).ravel(), 32))
    out.append(carray("CK_BOB_RGBA", "uint8_t", rgba8(a["bob"]).reshape(-1, 4).ravel(), 32))
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
    """the clock as the firmware shows it at rest, and beside it with the bird out (both 3 x)"""
    def scene(bird_out):
        img = np.zeros((240, 240, 3))
        px, py = PIVOT
        for y in range(int(py), int(BOB_Y)):                         # the stick
            img[y, 119:121] = (130, 76, 36)
        paste(img, a["bob"], int(round(120 - a["bob"].shape[1] / 2)), int(round(BOB_Y - a["bob"].shape[0] / 2)))
        for i, sx in enumerate(STRANDS):
            bot = W_TOP + 20 if i in (0, 3) else W_TOP + TRAVEL - 20
            for y in range(150, bot):
                img[y, int(sx)] = (210, 178, 104) if y % 2 else (120, 96, 48)
            if i in (0, 3):
                paste(img, a["weight"], int(sx - a["weight"].shape[1] / 2), bot)
        scr = a["opened"] if bird_out else a["scr"]
        al = scr[..., 3:]
        img = scr[..., :3] * 255 + img * (1 - al)
        if bird_out:
            b = a["bird1"]
            small = b.reshape(b.shape[0] // 2, 2, b.shape[1] // 2, 2, 4).mean(axis=(1, 3))
            paste(img, small, 120 - 13, int(HOLE_BOT) - 20)
        return img
    both = np.concatenate([scene(False), scene(True)], axis=1)
    Image.fromarray(np.clip(both, 0, 255).astype(np.uint8)).resize((1440, 720), Image.NEAREST).save(path)


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
