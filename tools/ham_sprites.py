# SPDX-License-Identifier: GPL-3.0-only
"""Hamster Synth's pictures, drawn here pixel by pixel: the eight hamsters and the Tromster's drummer.

Each is drawn on a grid of its own pixels (a hamster 26 x 24, the drummer 56 x 45); the screen shows each of them as
2 x 2 of its own, as the logo's letters and the text. One ink for every outline, the light from the upper left: a
pixel of fur against the outline at its right or below is in shade, at its left or above (on the upper left) in light.

  hamsters()          -> [grid] * 8, a grid: rows of (r, g, b) or None (clear)
  drummer()           -> [grid] * 4, its four frames
tools/gen_ham_art.py makes firmware/gen/ham_art.h of them, and a sheet to look at (--sheet).
"""

INK = (0x2A, 0x1A, 0x14)
EYE = (0x1C, 0x10, 0x0E)
GLINT = (0xFF, 0xFF, 0xFF)
EAR = (0xF2, 0x9A, 0xA0)
NOSE = (0xE0, 0x6A, 0x78)
BLUSH = (0xF6, 0xB0, 0xB0)
PAW = (0xF7, 0xD2, 0xC2)
PAW_S = (0xE6, 0xAE, 0x9C)
MOUTH = (0x6A, 0x24, 0x2A)
TONGUE = (0xF0, 0x7E, 0x8A)

# fur: light, mid, shade; belly: light, shade
FUR = {
    "golden": ((0xF8, 0xCE, 0x8A), (0xE9, 0xAB, 0x62), (0xC2, 0x80, 0x44)),
    "grey": ((0xCF, 0xD3, 0xD9), (0xA3, 0xA9, 0xB2), (0x76, 0x7C, 0x88)),
    "white": ((0xFF, 0xFF, 0xFF), (0xF6, 0xF0, 0xE8), (0xD8, 0xCE, 0xC2)),
    "orange": ((0xFF, 0xC0, 0x62), (0xF2, 0x96, 0x36), (0xC6, 0x6A, 0x26)),
    "brown": ((0xC4, 0x8E, 0x60), (0x9C, 0x66, 0x3C), (0x70, 0x44, 0x26)),
}
BELLY = ((0xFF, 0xF4, 0xE2), (0xEB, 0xD2, 0xB4))
BELLY_W = ((0xFF, 0xFB, 0xF4), (0xE4, 0xD8, 0xCA))

# the hamster's left half, its pixels: O outline, F fur, B belly (cream), P the ear's pink; mirrored for the right.
# A round head with its ears on it, cheeks, a body like a pear, sitting
HALF = [
    "...OOO.......",   # 0
    "..OFFPO......",   # 1
    ".OFPPPFO.OOOO",   # 2
    ".OFPPPFOOFFFF",   # 3
    ".OFFPFFFFFFFF",   # 4
    "..OFFFFFFFFFF",   # 5
    "..OFFFFFFFFFF",   # 6
    ".OFFFFFFFFFFF",   # 7
    ".OFFFFFFFFFFF",   # 8
    ".OFFFFFFFFFFF",   # 9   the eyes, 9..11
    ".OFFFFFFFFFFF",   # 10
    ".OFFFFFFFFFBB",   # 11  the muzzle: round, cream, round the nose and the mouth
    "OFFFFFFFFFBBB",   # 12  the nose
    "OFFFFFFFFBBBB",   # 13  the mouth
    "OFFFFFFFBBBBB",   # 14
    "OFFFFFFBBBBBB",   # 15
    "OFFFFFBBBBBBB",   # 16  the paws
    "OFFFFFBBBBBBB",   # 17
    "OFFFFFBBBBBBB",   # 18
    "OFFFFFBBBBBBB",   # 19
    "OFFFFFBBBBBBB",   # 20
    "OFFFFFFBBBBBB",   # 21
    ".OFFFFFBBBBBB",   # 22
    ".OFFFFFFBBBBB",   # 23
    "..OOFFFFFFBBB",   # 24
    "....OOOOOOOOO",   # 25
    ".............",   # 26  (the feet)
]
W, H = 26, 27

# the eight: C D E F G A B C, as the page has them
KINDS = [
    {"fur": "golden", "patches": True},
    {"fur": "grey", "blaze": True, "seed": True},
    {"fur": "white", "wink": True, "spot": True},
    {"fur": "orange", "cheese": True},
    {"fur": "brown", "blaze": True},
    {"fur": "grey", "blaze": True, "seed": True, "happy": True},
    {"fur": "orange", "blaze": True, "tongue": True},
    {"fur": "white", "shades": True},
]


def stamp(g, art, x0, y0, cmap):
    """art: rows of characters; a character in cmap is a pixel of that (a key), '.' or one not in it: left alone"""
    for y, row in enumerate(art):
        for x, c in enumerate(row):
            if c in cmap and 0 <= y0 + y < len(g) and 0 <= x0 + x < len(g[0]):
                g[y0 + y][x0 + x] = cmap[c]


def body(k, rows=H):
    """the hamster's grid of keys: O F B P (and H S b after the shading), before its face"""
    g = [list(h + h[::-1]) for h in HALF[:rows]]
    if k.get("blaze"):                          # a cream stripe from the forehead down to the muzzle
        for y, (a, b) in {3: (12, 13), 4: (12, 13), 5: (12, 13), 6: (11, 14), 7: (11, 14), 8: (11, 14),
                          9: (11, 14), 10: (11, 14)}.items():
            if y < rows:
                for x in range(a, b + 1):
                    g[y][x] = "B"
    if k.get("patches"):                        # the golden one: a darker cap over its head and down its back
        for y in range(2, 9):
            for x in range(26):
                inside = abs(x - 12.5) < (6.5 if y < 4 else 7.5 + (y - 4) * 1.4) and y < 7 + (abs(x - 12.5) > 6)
                if y < rows and g[y][x] == "F" and inside:
                    g[y][x] = "D"
    if k.get("spot"):                           # the white one's ginger spot on its side
        stamp(g, ["..GG", ".GGGG", "GGGGG", ".GGG"], 20, 15, {"G": "G"})
    return g


def shade(g):
    """light from the upper left: fur against the outline at its right or below in shade, at its left or above
    (upper left) in light; the belly against the outline at its right or below in shade"""
    h, w = len(g), len(g[0])
    out = [r[:] for r in g]
    edge = lambda x, y: x < 0 or y < 0 or x >= w or y >= h or g[y][x] in "O."
    for y in range(h):
        for x in range(w):
            c = g[y][x]
            if c in "FDG":
                if edge(x + 1, y) or edge(x, y + 1):
                    out[y][x] = c.lower() if c != "F" else "S"
                elif (edge(x - 1, y) or edge(x, y - 1)) and x < w // 2 and y < h // 2:
                    out[y][x] = "H" if c == "F" else c
            elif c == "B" and (edge(x + 1, y) or edge(x, y + 1)):
                out[y][x] = "b"
    return out


def face(g, k):
    """the eyes, the nose, the mouth, the cheeks, the paws, the feet; and what it holds or wears"""
    eye = ["WE", "EE", "EE"]
    shut = [".OO.", "O..O"]                     # an eye shut, smiling
    if k.get("happy"):
        stamp(g, shut, 5, 10, {"O": "O"})
        stamp(g, shut, 17, 10, {"O": "O"})
    else:
        stamp(g, eye, 6, 9, {"E": "E", "W": "W"})
        if k.get("wink"):
            stamp(g, shut, 17, 10, {"O": "O"})
        else:
            stamp(g, eye, 18, 9, {"E": "E", "W": "W"})
    stamp(g, ["KK"], 3, 12, {"K": "K"})         # the cheeks
    stamp(g, ["KK"], 21, 12, {"K": "K"})
    stamp(g, ["NN"], 12, 12, {"N": "N"})        # the nose
    if k.get("tongue"):                         # the mouth open, the tongue out
        stamp(g, ["O.OO.O", ".OMMO.", ".OTTO.", "..OO.."], 10, 13, {"O": "O", "M": "M", "T": "T"})
    else:                                       # a mouth like a w
        stamp(g, ["O.OO.O", ".O..O."], 10, 13, {"O": "O"})
    if k.get("shades"):                         # sunglasses over both eyes
        stamp(g, ["OOOOOOOOOOOOOOOOOOOO",
                  ".OZZZZZOOOOOOZZZZZO.",
                  ".OZLZZZO....OZLZZZO.",
                  "..OZZZO......OZZZO..",
                  "...OOO........OOO..."], 3, 8, {"O": "O", "Z": "Z", "L": "L"})
    held = k.get("seed") or k.get("cheese")
    if k.get("seed"):                           # a sunflower seed, held up
        stamp(g, ["..OO..",
                  ".OZZO.",
                  "OZLZZO",
                  "OZLZZO",
                  "OZLZZO",
                  "OZLZZO",
                  ".OZZO.",
                  "..OO.."], 10, 16, {"O": "O", "Z": "Z", "L": "L"})
    if k.get("cheese"):                         # a wedge of cheese
        stamp(g, ["....OO..",
                  "..OOYYO.",
                  "OOYYYYYO",
                  "OYYCYYYO",
                  "OYYYYYCO",
                  "OYCYYYYO",
                  "OyyyyyyO",
                  ".OOOOOO."], 9, 16, {"O": "O", "Y": "Y", "y": "y", "C": "C"})
    if held:                                    # its paws on what it holds
        y = 19
        stamp(g, ["pp", "qq"], 8 if k.get("cheese") else 9, y, {"p": "p", "q": "q"})
        stamp(g, ["pp", "qq"], 16 if k.get("cheese") else 15, y, {"p": "p", "q": "q"})
    else:                                       # its paws in front of it, soft
        stamp(g, ["pp", "qq"], 8, 17, {"p": "p", "q": "q"})
        stamp(g, ["pp", "qq"], 16, 17, {"p": "p", "q": "q"})
    if len(g) > 26:                             # the feet, under it
        for x0 in (5, 18):
            stamp(g, ["OpppO", ".OOO."], x0 - 1, 25, {"O": "O", "p": "p"})
    return g


def colour(g, k):
    f = FUR[k["fur"]]
    belly = BELLY_W if k["fur"] == "white" else BELLY
    dark = {"golden": ((0xD8, 0x92, 0x4E), (0xB0, 0x6C, 0x34)), "white": ((0xF6, 0xF0, 0xE8), (0xD8, 0xCE, 0xC2))}
    d = dark.get(k["fur"], (f[1], f[2]))
    pal = {"O": INK, "H": f[0], "F": f[1], "S": f[2], "B": belly[0], "b": belly[1], "P": EAR, "E": EYE, "W": GLINT,
           "N": NOSE, "K": BLUSH, "p": PAW, "q": PAW_S, "M": MOUTH, "T": TONGUE, "D": d[0], "d": d[1],
           "G": (0xF2, 0xB0, 0x68), "g": (0xD8, 0x8E, 0x4A),
           "Z": (0x3A, 0x3E, 0x48), "L": (0xEE, 0xEE, 0xF2), "Y": (0xFF, 0xD7, 0x4B), "y": (0xE0, 0xA8, 0x2A),
           "C": (0xE8, 0xB0, 0x30)}
    return [[None if c == "." else pal[c] for c in row] for row in g]


def hamster(k):
    return colour(face(shade(body(k)), k), k)


def hamsters():
    return [hamster(k) for k in KINDS]


# ---- the drummer: an orange hamster behind its kit, 56 x 45

DW, DH = 56, 45


def blank(w, h):
    return [[None] * w for _ in range(h)]


def layer(dst, src, x0, y0):
    for y, row in enumerate(src):
        for x, c in enumerate(row):
            if c is not None and 0 <= y0 + y < len(dst) and 0 <= x0 + x < len(dst[0]):
                dst[y0 + y][x0 + x] = c


def outlined(mask_fill, w, h):
    """a shape: fill(x, y) -> colour or None; its own outline round it (inside its edge)"""
    g = blank(w, h)
    m = [[mask_fill(x, y) for x in range(w)] for y in range(h)]
    for y in range(h):
        for x in range(w):
            if m[y][x] is None:
                continue
            edge = any(not (0 <= x + dx < w and 0 <= y + dy < h) or m[y + dy][x + dx] is None
                       for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)))
            g[y][x] = INK if edge else m[y][x]
    return g


def line(g, x0, y0, x1, y1, c, ink=None):
    """a line; with ink, an outline on both of its sides"""
    pts = []
    dx, dy = abs(x1 - x0), -abs(y1 - y0)
    sx, sy = (1 if x0 < x1 else -1), (1 if y0 < y1 else -1)
    err = dx + dy
    while True:
        pts.append((x0, y0))
        if x0 == x1 and y0 == y1:
            break
        e2 = 2 * err
        if e2 >= dy:
            err += dy
            x0 += sx
        if e2 <= dx:
            err += dx
            y0 += sy
    if ink:
        for x, y in pts:
            for ox, oy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                if 0 <= y + oy < len(g) and 0 <= x + ox < len(g[0]) and (x + ox, y + oy) not in pts:
                    g[y + oy][x + ox] = ink
    for x, y in pts:
        if 0 <= y < len(g) and 0 <= x < len(g[0]):
            g[y][x] = c


GREY = ((0xE2, 0xE4, 0xE8), (0xB0, 0xB4, 0xBC), (0x7C, 0x82, 0x8E))
RED = ((0xF4, 0x8A, 0x84), (0xDE, 0x5A, 0x5E), (0xB0, 0x3C, 0x46))
GOLD = ((0xFF, 0xE8, 0x8C), (0xF6, 0xC4, 0x48), (0xC8, 0x90, 0x28))
STICK = (0xF0, 0xD8, 0xA8)
SPARK = (0xFF, 0xE0, 0x50)


def kit_back():
    """the stands and the cymbals, behind the hamster"""
    g = blank(DW, DH)
    for cx, cy in ((8, 21), (47, 19)):         # two cymbals on stands, each on three legs
        line(g, cx, cy + 1, cx, 40, GREY[1], INK)
        line(g, cx, 38, cx - 4, 43, GREY[2], INK)
        line(g, cx, 38, cx + 4, 43, GREY[2], INK)
        cym = outlined(lambda x, y: (GOLD[0] if y < 2 else GOLD[1] if y < 3 else GOLD[2])
                       if (x - 7.5) ** 2 / 56 + (y - 2) ** 2 / 4.5 <= 1 else None, 16, 5)
        layer(g, cym, cx - 7, cy - 2)
        layer(g, [[INK], [INK]], cx, cy - 3)  # its nut
    return g


def kit_front():
    """the toms and the bass drum with its paw, in front of the hamster"""
    g = blank(DW, DH)
    for x0 in (9, 37):                          # two toms
        tom = outlined(lambda x, y: (None if (y == 0 and (x == 0 or x == 9)) else
                                     GREY[0] if y < 2 else RED[0] if x < 3 else RED[2] if x > 7 else RED[1]), 10, 9)
        for y in (2, 7):
            for x in range(1, 9):
                tom[y][x] = GREY[1]
        layer(g, tom, x0, 26)
        line(g, x0 + 4 + (0 if x0 < 20 else 1), 35, x0 + 4 + (0 if x0 < 20 else 1), 41, GREY[2], INK)
    r = 10.5                                    # the bass drum: its rim, its cream head
    drum = outlined(lambda x, y: (None if (x - 10.5) ** 2 + (y - 10.5) ** 2 > r * r else
                                  GREY[1] if (x - 10.5) ** 2 + (y - 10.5) ** 2 > 8.6 ** 2 else
                                  (0xFF, 0xF4, 0xE2) if (x - 9.5) + (y - 9.5) < 8 else (0xF2, 0xE2, 0xCC)), 22, 22)
    for y in range(22):                         # the rim's ring: an ink line inside it
        for x in range(22):
            d = (x - 10.5) ** 2 + (y - 10.5) ** 2
            if 7.9 ** 2 < d <= 8.6 ** 2:
                drum[y][x] = GREY[2]
    stamp(drum, [".P....P.",                # a paw print: four toes over its pad
                 "...PP...",
                 "P......P",
                 "..PPPP..",
                 ".PPPPPP.",
                 ".PPPPPP.",
                 "..PPPP.."], 7, 6, {"P": RED[1]})
    layer(g, drum, 17, 23)
    return g


def arm(g, shoulder, paw, stick_end):
    """an arm from its shoulder to its paw, the paw round its stick: the stick first, the arm over it"""
    (ax, ay), (bx, by) = shoulder, paw
    line(g, bx, by, stick_end[0], stick_end[1], STICK, INK)

    def dist(x, y):                             # from (x, y) to the arm's middle line
        vx, vy, wx, wy = bx - ax, by - ay, x - ax, y - ay
        t = max(0.0, min(1.0, (wx * vx + wy * vy) / float(vx * vx + vy * vy)))
        return ((x - ax - t * vx) ** 2 + (y - ay - t * vy) ** 2) ** .5

    def fill(x, y):
        d2 = (x - bx) ** 2 + (y - by) ** 2
        if d2 <= 1.0:
            return PAW
        if d2 <= 5.0 or dist(x, y) <= 1.9:
            return FUR["orange"][0] if x < (ax + bx) / 2 and dist(x, y) < 1.0 else FUR["orange"][1]
        return None
    layer(g, outlined(fill, DW, DH), 0, 0)


def drummer_hamster():
    k = {"fur": "orange", "tongue": True}
    g = shade(body(k, 24))
    g = face(g, k)
    return colour(g, k)


def sparks(g, x, y, side):
    """three short strokes, out from where the stick meets the cymbal"""
    for dx, dy in ((0, -1), (0, -2), (2, 0), (3, -1), (2, 2), (3, 2)):
        xx, yy = x + dx * side, y + dy
        if 0 <= xx < len(g[0]) and 0 <= yy < len(g):
            g[yy][xx] = SPARK


def drummer():
    frames = []
    ham = drummer_hamster()
    for f in range(4):
        g = blank(DW, DH)
        layer(g, kit_back(), 0, 0)
        layer(g, ham, 15, 6)
        front = kit_front()
        layer(g, front, 0, 0)
        left_up, right_up = f in (1, 3), f in (2, 3)
        # the arms: the sticks down onto the toms, or up in the air
        if left_up:
            arm(g, (17, 19), (11, 10), (6, 2))
        else:
            arm(g, (17, 19), (15, 24), (11, 27))
        if right_up:
            arm(g, (38, 19), (44, 10), (49, 2))
        else:
            arm(g, (38, 19), (40, 24), (44, 27))
        if f == 1:
            sparks(g, 5, 2, -1)
        if f == 2:
            sparks(g, 50, 2, 1)
        frames.append(g)
    return frames
