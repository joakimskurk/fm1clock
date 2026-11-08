#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""The clock's pictures, from the design (assets/design.png, 1254 x 1254): firmware/gen/clk_art.h.

  python3 tools/gen_art.py [--check] [--preview build/art-preview.png]     (Pillow and numpy)

What the firmware draws over a picture is taken out of it first, at the design's own resolution:
  - the hands and the hub: the wood under them is copied from the same column higher or lower (the grain runs
    up and down), the chapter ring under the tips is cream again, XII and X get their strokes back;
  - the pendulum: the window behind it is built again as a back panel (per column the wood's colour, the grain)
    and a front layer, the gold scrollwork and the frame (opaque) and the two reflections in the glass
    (partly transparent): the pendulum swings between the two.
Then everything is scaled to the screen (240 x 240, the design's square as it is), the clock cut out of the design's
black (what is black and joined to its edge) and hung on the panel wall the cuckoo clocks hang on (tools/
gen_art_cuckoo.py), its soft shadow on it, and written as RGB565 in the byte order the screen takes: the box the clock
and its shadow are in (the firmware draws the wall round it). The bob is cut out of the design with its shading, as a sprite with alpha; the rod
is drawn by the firmware, its colours across are measured here. --check: fail if the header is not what this makes.
"""
import argparse
import sys
from pathlib import Path

import numpy as np
from PIL import Image

from gen_art_cuckoo import WALL_TW, shadowed, wall_tile    # the panel wall, the shadow on it

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "assets" / "design.png"
OUT = ROOT / "firmware" / "gen" / "clk_art.h"
N = 1254                               # the design's size
S = 240 / N                            # to the screen
HUB = (629.7, 503.1)                   # the hands' centre (the brass hub's centroid)
DISC_R = 124.0                         # the wooden centre of the dial
RING_R = 206.0                         # the chapter ring's outer edge
BOB = (627.0, 982.0, 80.0)             # the pendulum's bob: centre, radius
WIN = (424, 788, 836, 1083)            # the window's inside: x0 y0 x1 y1 (the gold frame's inner edge)
KEYHOLES = [(558.0, 563.0, 22.0), (695.0, 563.0, 22.0)]


def poly_mask(pts, shape):
    from PIL import ImageDraw
    m = Image.new("L", (shape[1], shape[0]), 0)
    ImageDraw.Draw(m).polygon([tuple(p) for p in pts], fill=255)
    return np.asarray(m) > 0


def hand_masks(shape):
    hx, hy = HUB
    minute = poly_mask([(630, 338), (651, 384), (644, 402), (644, 522), (616, 522), (616, 402), (609, 384)], shape)
    tip = np.array([494.0, 434.0])                      # the hour hand's tip, by 10
    d = tip - np.array(HUB); d /= np.linalg.norm(d); n = np.array([-d[1], d[0]])
    base = np.array(HUB) - d * 22
    hour = poly_mask([base + n * 17, tip + d * 6 + n * 4, tip + d * 10, tip + d * 6 - n * 4, base - n * 17,
                      ], shape) | poly_mask([np.array(HUB) + d * 95 + n * 25, tip + d * 8, np.array(HUB) + d * 95 - n * 25,
                                              np.array(HUB) + d * 60], shape)
    yy, xx = np.mgrid[0:shape[0], 0:shape[1]]
    hub = np.hypot(xx - hx, yy - hy) < 25
    return minute, hour, hub


def dilate(m, r):
    out = m.copy()
    for dy in range(-r, r + 1):
        for dx in range(-r, r + 1):
            if dx * dx + dy * dy <= r * r:
                out |= np.roll(np.roll(m, dy, axis=0), dx, axis=1)
    return out


def inpaint_dial(im):
    im = im.copy()
    H, W = im.shape[:2]
    minute, hour, hub = hand_masks((H, W))
    yy, xx = np.mgrid[0:H, 0:W]
    hx, hy = HUB
    dist = np.hypot(xx - hx, yy - hy)
    lum = im.mean(axis=2)
    sat = im.max(axis=2) - im.min(axis=2)
    # on the wood the hands are what is grey or dark (the wood is red-brown), with their soft edges: within a wide
    # area around each hand; on the ring only the hands' outlines (the numerals are dark too)
    wide = dilate(minute | hour | hub, 14)
    on_wood = wide & (dist < DISC_R) & ((sat < 45) | (lum < 55))
    mask = dilate(on_wood, 4) & (dist < DISC_R + 2) | dilate(minute | hour | hub, 2)
    keyhole = np.zeros((H, W), bool)
    for kx, ky, kr in KEYHOLES:
        keyhole |= np.hypot(xx - kx, yy - ky) < kr
    src_ok = ~dilate(mask, 4) & ~keyhole & (dist < DISC_R - 4)
    # the wood: per column one shift up or down to clean wood (the grain runs vertically; one shift a column keeps
    # it unbroken), the disc's rim turned round the hub instead (it is round, not striped)
    rim = mask & (dist >= DISC_R - 5) & (dist < DISC_R + 2)
    body = mask & (dist < DISC_R - 5)
    shifts = [k for a in range(30, 260, 5) for k in (a, -a)]
    for x in np.unique(np.where(body)[1]):
        ys = np.where(body[:, x])[0]
        for k in shifts:
            sy = ys + k
            if sy.min() >= 0 and sy.max() < H and src_ok[sy, x].all():
                im[ys, x] = im[sy, x]
                break
        else:                                                  # no one shift: the nearest clean pixel each
            for y in ys:
                for k in shifts:
                    if 0 <= y + k < H and src_ok[y + k, x]:
                        im[y, x] = im[y + k, x]
                        break
    rim_ok = ~dilate(mask, 3)
    for y, x in zip(*np.where(rim)):
        r, t = dist[y, x], np.arctan2(y - hy, x - hx)
        for dt in (0.2, -0.2, 0.3, -0.3, 0.45, -0.45):
            sx, sy = int(round(hx + r * np.cos(t + dt))), int(round(hy + r * np.sin(t + dt)))
            if rim_ok[sy, sx]:
                im[y, x] = im[sy, x * 0 + sx]
                break
    # the chapter ring under the tips: cream from the clean ring at the same radius nearby
    ring = mask & (dist >= DISC_R + 2)
    clean_ring = ~mask & (dist >= DISC_R + 2) & (dist < RING_R - 8) & (lum > 170)
    for y, x in zip(*np.where(ring)):
        y0, y1, x0, x1 = max(y - 14, 0), y + 15, max(x - 14, 0), x + 15
        sel = clean_ring[y0:y1, x0:x1]
        if sel.any():
            im[y, x] = np.median(im[y0:y1, x0:x1][sel], axis=0)
    # XII: its strokes run on down through where the minute hand's tip was (column), its foot bar across (row)
    dark = lambda p: p.mean() < 90
    orig = im.copy()
    for y in range(318, 371):
        for x in range(598, 660):
            if not mask[y, x]:
                continue
            above = [orig[yy_, x] for yy_ in range(y - 1, 318, -1) if not mask[yy_, x]]
            if 361 <= y <= 368:                         # the foot bar: dark where the row is dark either side
                l = [orig[y, xx_] for xx_ in range(x - 1, 596, -1) if not mask[y, xx_]][:1]
                r = [orig[y, xx_] for xx_ in range(x + 1, 662) if not mask[y, xx_]][:1]
                if l and r and dark(l[0]) and dark(r[0]):
                    im[y, x] = (l[0] + r[0]) / 2
                    continue
            if above and dark(above[0]) and y <= 367:
                im[y, x] = above[0]
    # X by ten: it is point-symmetric, its covered leg comes back from the other one
    cx, cy = 486, 424                                        # (its centre of symmetry, searched once)
    for y, x in zip(*np.where(mask[400:452, 466:522])):
        y += 400; x += 466
        sy, sx = 2 * cy - y, 2 * cx - x
        if not mask[sy, sx] and dark(orig[sy, sx]):
            im[y, x] = orig[sy, sx]
    return im


def clock_mask(im):
    """the clock in the design: all but its black background (what is black and joined to the picture's edge; the
    black inside it, its numerals, the hands, the keyholes, is the clock's)"""
    dark = im.max(axis=2) <= 12
    bg = np.zeros_like(dark)
    for sl in (np.s_[0, :], np.s_[-1, :], np.s_[:, 0], np.s_[:, -1]):
        bg[sl] = dark[sl]
    while True:                                                 # grown from the edge through the black
        n = bg.copy()
        n[1:] |= bg[:-1]; n[:-1] |= bg[1:]; n[:, 1:] |= bg[:, :-1]; n[:, :-1] |= bg[:, 1:]
        n &= dark
        if (n == bg).all():
            return ~bg
        bg = n


def resize_f(ch, size):
    return np.asarray(Image.fromarray(ch.astype(np.float32), mode="F").resize(size, Image.LANCZOS), np.float64)


def box_blur(m, r):
    out = m.astype(float)
    for axis in (0, 1):
        acc = np.zeros_like(out)
        for d in range(-r, r + 1):
            acc += np.roll(out, d, axis=axis)
        out = acc / (2 * r + 1)
    return out


def window_layers(im):
    """the window's inside: back panel (wood, no pendulum, no glass), front layer (gold, frame, reflections) RGBA.
    The design paints the pendulum's shadow onto the wood around it: the back panel is built again there from the
    wood away from it (per row its colour, per column its grain), so the firmware's shadow can swing with it"""
    x0, y0, x1, y1 = WIN
    reg = im[y0:y1, x0:x1].astype(float)
    h, w = reg.shape[:2]
    yy, xx = np.mgrid[0:h, 0:w]
    R, G, B = reg[..., 0], reg[..., 1], reg[..., 2]
    gold = (G > 75) & (R > 120) & (R - B > 60)                 # scrollwork, frame lines, and the pendulum
    bx, by, br = BOB
    pend = (np.hypot(xx + x0 - bx, yy + y0 - by) < br + 4) | ((np.abs(xx + x0 - 627) < 19) & (yy + y0 < by))
    zone = dilate(pend, 30)                                    # the pendulum and the shadow painted round it
    lum = reg.mean(axis=2)
    sat = reg.max(axis=2) - reg.min(axis=2)
    glass = (sat < 40) & (lum > 55) & ~pend                     # the reflections: grey, lighter than the wood
    front_gold = gold & ~pend
    clean = ~gold & ~glass & ~zone
    row = np.zeros((h, 3))                                      # per row the wood's colour, both sides of the zone
    for y in range(h):
        sel = clean[y]
        row[y] = np.median(reg[y, sel], axis=0) if sel.sum() > 8 else np.nan
    for y in range(h):
        if np.isnan(row[y, 0]):
            row[y] = row[~np.isnan(row[:, 0])][np.argmin(np.abs(np.where(~np.isnan(row[:, 0]))[0] - y))]
    k = 7
    row = np.array([np.mean(row[max(y - k, 0):y + k + 1], axis=0) for y in range(h)])
    grain = np.ones((w, 3))                                     # per column its grain against the row's colour
    have = np.zeros(w, bool)
    for x in range(w):
        sel = clean[:, x]
        if sel.sum() > 0.3 * h:
            grain[x] = np.median(reg[sel, x] / np.maximum(row[sel], 1), axis=0)
            have[x] = True
    src = np.where(have & (np.arange(w) > 40) & (np.arange(w) < w - 40))[0]   # (not the dark ones by the frame)
    for i, x in enumerate(np.where(~have)[0]):                 # the zone's columns: the clean ones side by side, so
        grain[x] = grain[src[(i + 17) % len(src)]]              # the planks keep their width
    model = row[:, None, :] * grain[None, :, :]
    wz = np.clip(box_blur(dilate(zone, 3), 6) * 1.6, 0, 1)      # the design's own wood outside, feathered
    back = np.where(clean[..., None], reg * (1 - wz[..., None]) + model * wz[..., None], model)
    # the front: gold opaque; the reflections as white-ish over the back, alpha from how much lighter they are
    W_ = np.array([205.0, 205.0, 215.0])
    a = np.zeros((h, w))
    a[front_gold] = 1.0
    lb = back.mean(axis=2)
    ag = np.clip((lum - lb) / (W_.mean() - lb), 0, 0.8)
    a = np.where(glass, ag, a)
    rgb = np.where(front_gold[..., None], reg, W_[None, None, :])
    return back, rgb, a


def bob_sprite(im):
    bx, by, br = BOB
    x0, y0 = int(bx - br - 6), int(by - br - 6)
    size = int(2 * br + 12)
    reg = im[y0:y0 + size, x0:x0 + size].astype(float)
    yy, xx = np.mgrid[0:size, 0:size]
    d = np.hypot(xx + x0 + 0.5 - bx, yy + y0 + 0.5 - by)
    a = np.clip(br + 0.5 - d, 0, 1)
    return reg, a, (bx - x0, by - y0)


def to_screen(rgb, a=None, box=None):
    """scale a full-resolution region (premultiplied when it has alpha) to the screen: box = (x0, y0, x1, y1) in
    screen pixels, the region's full-resolution origin is box / S"""
    x0, y0, x1, y1 = box
    w, h = x1 - x0, y1 - y0
    fx0, fy0, fx1, fy1 = x0 / S, y0 / S, x1 / S, y1 / S
    if a is None:
        img = Image.fromarray(np.clip(rgb, 0, 255).astype(np.uint8))
        return np.asarray(img.resize((w, h), Image.LANCZOS, box=(fx0, fy0, fx1, fy1))).astype(float)
    pre = np.concatenate([rgb * a[..., None], a[..., None] * 255], axis=2)
    out = np.zeros((h, w, 4))
    for c in range(4):
        ch = Image.fromarray(pre[..., c].astype(np.float32), mode="F")
        out[..., c] = np.asarray(ch.resize((w, h), Image.BOX, box=(fx0, fy0, fx1, fy1)))
    return out                                                   # premultiplied RGB (0..255) and alpha (0..255)


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


def build(debug=None):
    im = np.asarray(Image.open(SRC).convert("RGB")).astype(float)
    assert im.shape[:2] == (N, N), "assets/design.png: 1254 x 1254 expected"
    clean = inpaint_dial(im)
    if debug:
        Image.fromarray(np.clip(clean[270:740, 395:865], 0, 255).astype(np.uint8)).save(debug)
    back, frgb, fa = window_layers(clean)
    x0, y0, x1, y1 = WIN
    comp = back * (1 - fa[..., None]) + frgb * fa[..., None]
    clean[y0:y1, x0:x1] = comp
    # the clock on the wall: premultiplied by its outline, colour and coverage scaled alike, its shadow under it
    mask = clock_mask(im).astype(float)
    pre = np.stack([resize_f(np.clip(clean[..., c], 0, 255) * mask, (240, 240)) for c in range(3)], axis=2)
    cover = np.clip(resize_f(mask, (240, 240)), 0, 1)
    tile = wall_tile()
    wall = np.concatenate([tile] * (240 // WALL_TW + 1), axis=1)[:, :240]
    hung = np.concatenate([np.clip(pre, 0, 255) / 255, cover[..., None]], axis=2)
    screen = np.clip(pre + shadowed(hung, wall) * (1 - cover[..., None]), 0, 255)
    ys, xs = np.where(np.abs(screen - wall).max(axis=2) > 0.5)   # the box the clock and its shadow are in
    bx0, by0, bx1, by1 = int(xs.min()), int(ys.min()), int(xs.max()) + 1, int(ys.max()) + 1
    bg = screen[by0:by1, bx0:bx1]
    # the window on the screen: whole pixels inside the frame
    wx0, wy0 = int(np.ceil(x0 * S)), int(np.ceil(y0 * S))
    wx1, wy1 = int(np.floor(x1 * S)), int(np.floor(y1 * S))
    big_back = np.zeros((N, N, 3)); big_back[y0:y1, x0:x1] = back
    big_frgb = np.zeros((N, N, 3)); big_frgb[y0:y1, x0:x1] = frgb
    big_fa = np.zeros((N, N)); big_fa[y0:y1, x0:x1] = fa
    wback = to_screen(big_back, box=(wx0, wy0, wx1, wy1))
    wfront = to_screen(big_frgb, big_fa, box=(wx0, wy0, wx1, wy1))
    # the bob, scaled with one pixel of air around it
    reg, ba, (cx, cy) = bob_sprite(im)
    size = reg.shape[0]
    sw = int(np.ceil(size * S)) + 2
    m = int(np.ceil(1 / S))                                    # one screen pixel of air, at full resolution
    pre = np.pad(np.concatenate([reg * ba[..., None], ba[..., None] * 255], axis=2), ((m, m), (m, m), (0, 0)))
    bob = np.zeros((sw, sw, 4))
    for c in range(4):
        ch = Image.fromarray(pre[..., c].astype(np.float32), mode="F")
        bob[..., c] = np.asarray(ch.resize((sw, sw), Image.BOX, box=(m - 1 / S, m - 1 / S, m + (sw - 1) / S, m + (sw - 1) / S)))
    bob_c = ((cx + 1 / S) * S, (cy + 1 / S) * S)                # the bob's centre in sprite pixels
    # the rod's colours across (left edge to right edge), from the design at y 850, 1 screen px apart
    xs_ = np.arange(612, 643, 1 / S * 0 + 5.2)
    rod = [tuple(np.clip(im[840:860, int(round(x)) - 2:int(round(x)) + 3].reshape(-1, 3).mean(axis=0), 0, 255)) for x in xs_]
    return dict(bg=bg, box=(bx0, by0, bx1, by1), wback=wback, wfront=wfront, wbox=(wx0, wy0, wx1, wy1),
                bob=bob, bob_c=bob_c, rod=rod, screen=screen)


def header(a):
    bx0, by0, bx1, by1 = a["box"]
    wx0, wy0, wx1, wy1 = a["wbox"]
    bob = np.clip(np.round(a["bob"]), 0, 255).astype(int)
    wf = np.clip(np.round(a["wfront"]), 0, 255).astype(int)
    hx, hy = HUB[0] * S, HUB[1] * S
    out = ["/* SPDX-License-Identifier: GPL-3.0-only */",
           "/* generated by tools/gen_art.py from assets/design.png: do not edit */",
           "#pragma once", "#include <stdint.h>",
           f"#define BG_X {bx0}", f"#define BG_Y {by0}", f"#define BG_W {bx1 - bx0}", f"#define BG_H {by1 - by0}",
           f"#define WIN_X {wx0}", f"#define WIN_Y {wy0}", f"#define WIN_W {wx1 - wx0}", f"#define WIN_H {wy1 - wy0}",
           f"#define HUB_X256 {int(round(hx * 256))}   /* the hands' centre on the screen, 1/256 px */",
           f"#define HUB_Y256 {int(round(hy * 256))}",
           f"#define DISC_R256 {int(round(DISC_R * S * 256))}   /* the wooden centre's radius */",
           f"#define RING_R256 {int(round(RING_R * S * 256))}   /* the chapter ring's outer radius */",
           f"#define BOB_W {bob.shape[1]}", f"#define BOB_H {bob.shape[0]}",
           f"#define BOB_CX256 {int(round(a['bob_c'][0] * 256))}   /* the bob's centre in the sprite, 1/256 px */",
           f"#define BOB_CY256 {int(round(a['bob_c'][1] * 256))}",
           f"#define BOB_Y256 {int(round(BOB[1] * S * 256))}   /* the bob's centre on the screen at rest */",
           f"#define BOB_R256 {int(round(BOB[2] * S * 256))}",
           f"#define ROD_N {len(a['rod'])}   /* the rod's colours across, a screen pixel apart */"]
    out.append("/* the clock on the panel wall, its shadow on it (the wall round it is not stored), RGB565 in the screen's byte order */")
    out.append(carray("BG_SW", "uint16_t", swapped(rgb565(a["bg"])).ravel()))
    out.append("/* the window's back panel behind the pendulum, RGB565 (the CPU's order: blended before it is sent) */")
    out.append(carray("WIN_BACK", "uint16_t", rgb565(a["wback"]).ravel()))
    out.append("/* the window's front: the gold and the glass's reflections, premultiplied R G B A (0..255 each) */")
    out.append(carray("WIN_FRONT", "uint8_t", wf.reshape(-1, 4).ravel(), 32))
    out.append("/* the bob, premultiplied R G B A */")
    out.append(carray("BOB_RGBA", "uint8_t", bob.reshape(-1, 4).ravel(), 32))
    out.append(carray("ROD_RGB", "uint8_t", np.clip(np.round(np.array(a["rod"])), 0, 255).astype(int).ravel(), 24))
    return "\n".join(out) + "\n"


def preview(a, path):
    """the background with the window's layers and the bob at rest, as the firmware composes them (roughly)"""
    sc = a["screen"].copy()
    wx0, wy0, wx1, wy1 = a["wbox"]
    back = a["wback"]; fr = a["wfront"]
    win = back.copy()
    bob = a["bob"]; cx, cy = a["bob_c"]
    ox, oy = HUB[0] * S - cx, BOB[1] * S - cy
    for y in range(win.shape[0]):
        for x in range(win.shape[1]):
            sx, sy = int(round(x + wx0 - ox)), int(round(y + wy0 - oy))
            if 0 <= sx < bob.shape[1] and 0 <= sy < bob.shape[0]:
                p = bob[sy, sx]
                win[y, x] = p[:3] + win[y, x] * (1 - p[3] / 255)
    win = fr[..., :3] + win * (1 - fr[..., 3:4] / 255)
    sc[wy0:wy1, wx0:wx1] = win
    Image.fromarray(np.clip(sc, 0, 255).astype(np.uint8)).resize((720, 720), Image.NEAREST).save(path)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--preview", type=Path)
    ap.add_argument("--debug-dial", type=Path)
    a = ap.parse_args()
    art = build(a.debug_dial)
    h = header(art)
    if a.preview:
        preview(art, a.preview)
    if a.check:
        if not OUT.exists() or OUT.read_text() != h:
            print("firmware/gen/clk_art.h is not what tools/gen_art.py makes: run it")
            return 1
        print("clk_art.h: up to date")
        return 0
    OUT.write_text(h)
    print(f"{OUT.relative_to(ROOT)}: clock {art['box']}, window {art['wbox']}, bob {art['bob'].shape[1]} x {art['bob'].shape[0]}, "
          f"{len(h) // 1024} KB of source")
    return 0


if __name__ == "__main__":
    sys.exit(main())
