#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Hamster Piano's pictures: firmware/gen/ham_art.h.

  the eight hamsters   assets/hamster/hamsters.json: the page's own pixels (54 x 54, 18 colours), as they are
  the drummer          assets/hamster/tromster.png: the page's four frames, at the size the page shows them (112 wide)
  the logo's letters   the page's 7 x 9 pixel font (H A M S T E R P I A N O C)
  the text             a 5 x 7 pixel font of this firmware's own, with what Norwegian needs (the chip's fonts have
                       no AE, OE, AA) and the page's signs: arrows, the middle dot, the cross

  python3 tools/gen_ham_art.py [--check] [--sheet OUT.png]
"""
import json
import sys
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "firmware" / "gen" / "ham_art.h"
SRC = ROOT / "assets" / "hamster"
DRUM_W, DRUM_CROP = 112, (130, 560)     # the drummer: this wide; these rows of the page's 703 hold all of it
DRUM_COLOURS = 47

LOGO = {
    "H": ["1000001", "1000001", "1000001", "1111111", "1000001", "1000001", "1000001", "1000001", "1000001"],
    "A": ["0011100", "0100010", "1000001", "1000001", "1111111", "1000001", "1000001", "1000001", "1000001"],
    "M": ["1000001", "1100011", "1010101", "1001001", "1000001", "1000001", "1000001", "1000001", "1000001"],
    "S": ["0111111", "1000000", "1000000", "0111110", "0000001", "0000001", "0000001", "1000001", "0111110"],
    "T": ["1111111", "0001000", "0001000", "0001000", "0001000", "0001000", "0001000", "0001000", "0001000"],
    "E": ["1111111", "1000000", "1000000", "1111110", "1000000", "1000000", "1000000", "1000000", "1111111"],
    "R": ["1111110", "1000001", "1000001", "1111110", "1010000", "1001000", "1000100", "1000010", "1000001"],
    "P": ["1111110", "1000001", "1000001", "1111110", "1000000", "1000000", "1000000", "1000000", "1000000"],
    "I": ["1111111", "0001000", "0001000", "0001000", "0001000", "0001000", "0001000", "0001000", "1111111"],
    "N": ["1000001", "1100001", "1010001", "1001001", "1000101", "1000011", "1000001", "1000001", "1000001"],
    "O": ["0111110", "1000001", "1000001", "1000001", "1000001", "1000001", "1000001", "1000001", "0111110"],
    "C": ["0111110", "1000001", "1000000", "1000000", "1000000", "1000000", "1000000", "1000001", "0111110"],
}

# the 5 x 7 font: seven rows a glyph, '#' a pixel
F = {}


def g(ch, *rows):
    assert len(rows) == 7 and all(len(r) == 5 for r in rows), ch
    F[ch] = rows


g(" ", ".....", ".....", ".....", ".....", ".....", ".....", ".....")
g("A", ".###.", "#...#", "#...#", "#####", "#...#", "#...#", "#...#")
g("B", "####.", "#...#", "#...#", "####.", "#...#", "#...#", "####.")
g("C", ".###.", "#...#", "#....", "#....", "#....", "#...#", ".###.")
g("D", "####.", "#...#", "#...#", "#...#", "#...#", "#...#", "####.")
g("E", "#####", "#....", "#....", "####.", "#....", "#....", "#####")
g("F", "#####", "#....", "#....", "####.", "#....", "#....", "#....")
g("G", ".###.", "#...#", "#....", "#.###", "#...#", "#...#", ".####")
g("H", "#...#", "#...#", "#...#", "#####", "#...#", "#...#", "#...#")
g("I", ".###.", "..#..", "..#..", "..#..", "..#..", "..#..", ".###.")
g("J", "..###", "...#.", "...#.", "...#.", "...#.", "#..#.", ".##..")
g("K", "#...#", "#..#.", "#.#..", "##...", "#.#..", "#..#.", "#...#")
g("L", "#....", "#....", "#....", "#....", "#....", "#....", "#####")
g("M", "#...#", "##.##", "#.#.#", "#.#.#", "#...#", "#...#", "#...#")
g("N", "#...#", "##..#", "#.#.#", "#..##", "#...#", "#...#", "#...#")
g("O", ".###.", "#...#", "#...#", "#...#", "#...#", "#...#", ".###.")
g("P", "####.", "#...#", "#...#", "####.", "#....", "#....", "#....")
g("Q", ".###.", "#...#", "#...#", "#...#", "#.#.#", "#..#.", ".##.#")
g("R", "####.", "#...#", "#...#", "####.", "#.#..", "#..#.", "#...#")
g("S", ".####", "#....", "#....", ".###.", "....#", "....#", "####.")
g("T", "#####", "..#..", "..#..", "..#..", "..#..", "..#..", "..#..")
g("U", "#...#", "#...#", "#...#", "#...#", "#...#", "#...#", ".###.")
g("V", "#...#", "#...#", "#...#", "#...#", "#...#", ".#.#.", "..#..")
g("W", "#...#", "#...#", "#...#", "#.#.#", "#.#.#", "##.##", "#...#")
g("X", "#...#", "#...#", ".#.#.", "..#..", ".#.#.", "#...#", "#...#")
g("Y", "#...#", "#...#", ".#.#.", "..#..", "..#..", "..#..", "..#..")
g("Z", "#####", "....#", "...#.", "..#..", ".#...", "#....", "#####")
g("Æ", ".####", "#.#..", "#.#..", "####.", "#.#..", "#.#..", "#.###")
g("Ø", ".###.", "#..##", "#.#.#", "#.#.#", "#.#.#", "##..#", ".###.")
g("Å", "..#..", ".#.#.", "..#..", ".###.", "#...#", "#####", "#...#")
g("0", ".###.", "#...#", "#..##", "#.#.#", "##..#", "#...#", ".###.")
g("1", "..#..", ".##..", "..#..", "..#..", "..#..", "..#..", ".###.")
g("2", ".###.", "#...#", "....#", "...#.", "..#..", ".#...", "#####")
g("3", "####.", "....#", "....#", ".###.", "....#", "....#", "####.")
g("4", "...#.", "..##.", ".#.#.", "#..#.", "#####", "...#.", "...#.")
g("5", "#####", "#....", "####.", "....#", "....#", "#...#", ".###.")
g("6", ".###.", "#....", "#....", "####.", "#...#", "#...#", ".###.")
g("7", "#####", "....#", "...#.", "..#..", ".#...", ".#...", ".#...")
g("8", ".###.", "#...#", "#...#", ".###.", "#...#", "#...#", ".###.")
g("9", ".###.", "#...#", "#...#", ".####", "....#", "....#", ".###.")
g(".", ".....", ".....", ".....", ".....", ".....", ".##..", ".##..")
g(",", ".....", ".....", ".....", ".....", ".##..", "..#..", ".#...")
g(":", ".....", ".##..", ".##..", ".....", ".##..", ".##..", ".....")
g("!", "..#..", "..#..", "..#..", "..#..", "..#..", ".....", "..#..")
g("?", ".###.", "#...#", "....#", "...#.", "..#..", ".....", "..#..")
g("-", ".....", ".....", ".....", ".###.", ".....", ".....", ".....")
g("+", ".....", "..#..", "..#..", "#####", "..#..", "..#..", ".....")
g("=", ".....", ".....", "#####", ".....", "#####", ".....", ".....")
g("/", "....#", "....#", "...#.", "..#..", ".#...", "#....", "#....")
g("%", "##..#", "##..#", "...#.", "..#..", ".#...", "#..##", "#..##")
g("(", "...#.", "..#..", ".#...", ".#...", ".#...", "..#..", "...#.")
g(")", ".#...", "..#..", "...#.", "...#.", "...#.", "..#..", ".#...")
g("'", "..#..", "..#..", ".#...", ".....", ".....", ".....", ".....")
g("#", ".#.#.", ".#.#.", "#####", ".#.#.", "#####", ".#.#.", ".#.#.")
g("~", ".....", ".....", ".#...", "#.#.#", "...#.", ".....", ".....")
g("<", "...#.", "..#..", ".#...", "#....", ".#...", "..#..", "...#.")
g(">", ".#...", "..#..", "...#.", "....#", "...#.", "..#..", ".#...")
g("·", ".....", ".....", ".....", "..#..", ".....", ".....", ".....")
g("×", ".....", "#...#", ".#.#.", "..#..", ".#.#.", "#...#", ".....")
g("«", ".....", "..#.#", ".#.#.", "#.#..", ".#.#.", "..#.#", ".....")
g("»", ".....", "#.#..", ".#.#.", "..#.#", ".#.#.", "#.#..", ".....")
g("↑", "..#..", ".###.", "#.#.#", "..#..", "..#..", "..#..", "..#..")
g("↓", "..#..", "..#..", "..#..", "..#..", "#.#.#", ".###.", "..#..")
g("→", ".....", "..#..", "...#.", "#####", "...#.", "..#..", ".....")
g("←", ".....", "..#..", ".#...", "#####", ".#...", "..#..", ".....")
g("↕", "..#..", ".###.", "#.#.#", "..#..", "#.#.#", ".###.", "..#..")
g("▶", "#....", "##...", "###..", "####.", "###..", "##...", "#....")
g("■", ".....", "#####", "#####", "#####", "#####", "#####", ".....")
g("●", ".....", ".###.", "#####", "#####", "#####", ".###.", ".....")
g("○", ".....", ".###.", "#...#", "#...#", "#...#", ".###.", ".....")
g("≈", ".....", ".#..#", "#.##.", ".....", ".#..#", "#.##.", ".....")
g("±", "..#..", "..#..", "#####", "..#..", "..#..", ".....", "#####")
g("♪", "..##.", "..#.#", "..#..", "..#..", ".##..", "###..", ".#...")
ORDER = list(F)


def rgb565(r, g_, b):
    return (r >> 3) << 11 | (g_ >> 2) << 5 | b >> 3


def hexrgb(s):
    return tuple(int(s[i:i + 2], 16) for i in (1, 3, 5))


def drummer():
    im = Image.open(SRC / "tromster.png").convert("RGBA")
    fw = im.width // 4
    h = round((DRUM_CROP[1] - DRUM_CROP[0]) * DRUM_W / fw)
    small = [im.crop((f * fw, DRUM_CROP[0], (f + 1) * fw, DRUM_CROP[1])).resize((DRUM_W, h), Image.BOX) for f in range(4)]
    sheet = Image.new("RGB", (DRUM_W * 4, h))
    for f, s in enumerate(small):
        sheet.paste(s.convert("RGB"), (f * DRUM_W, 0))
    q = sheet.quantize(DRUM_COLOURS, method=Image.Quantize.MEDIANCUT, dither=Image.Dither.NONE)
    pal = q.getpalette()[:DRUM_COLOURS * 3]
    frames = []
    for f, s in enumerate(small):
        px = []
        for y in range(h):
            for x in range(DRUM_W):
                px.append(q.getpixel((f * DRUM_W + x, y)) if s.getpixel((x, y))[3] > 110 else 255)
        frames.append(px)
    return h, [tuple(pal[i:i + 3]) for i in range(0, len(pal), 3)], frames


def carr(name, typ, vals, per=24, fmt="{}"):
    s = [f"static const {typ} {name}[{len(vals)}] = {{"]
    for i in range(0, len(vals), per):
        s.append("    " + ", ".join(fmt.format(v) for v in vals[i:i + per]) + ",")
    s.append("};")
    return "\n".join(s)


def build():
    d = json.loads((SRC / "hamsters.json").read_text())
    ch = ".0123456789ABCDEFGH"
    o = ["/* SPDX-License-Identifier: GPL-3.0-only */",
         "/* Hamster Piano's pictures. Made by tools/gen_ham_art.py: do not edit. */",
         "#pragma once", "#include <stdint.h>", ""]
    o.append("#define HAM_W 55u                               /* a hamster's box (the narrower ones: clear at the right) */")
    o.append("#define HAM_H 54u")
    o.append(carr("HAM_PAL", "uint16_t", [rgb565(*hexrgb(c)) for c in d["palette"]], 9, "0x{:04X}"))
    o.append("static const uint8_t HAM_SPR[8][HAM_W * HAM_H] = {       /* 255: clear */")
    for hmm in d["hamsters"]:
        px = []
        for row in hmm["rows"]:
            row = row + "." * (55 - len(row))
            px += [ch.index(c) - 1 if c != "." else 255 for c in row]
        assert len(px) == 55 * 54
        o.append("    {" + ",".join(str(v) for v in px) + "},")
    o.append("};")
    h, pal, frames = drummer()
    o.append(f"#define DRUM_W {DRUM_W}u")
    o.append(f"#define DRUM_H {h}u")
    o.append(carr("DRUM_PAL", "uint16_t", [rgb565(*c) for c in pal], 8, "0x{:04X}"))
    o.append("static const uint8_t DRUM_SPR[4][DRUM_W * DRUM_H] = {")
    for px in frames:
        o.append("    {" + ",".join(str(v) for v in px) + "},")
    o.append("};")
    o.append("/* the logo's letters, 7 x 9: a row a byte, bit 6 the left pixel */")
    o.append('#define LOGO_CHARS "HAMSTERPINOC"')
    o.append("static const uint8_t LOGO_FONT[12][9] = {")
    for c in "HAMSTERPINOC":
        o.append("    {" + ", ".join(str(int(r, 2)) for r in LOGO[c]) + "},")
    o.append("};")
    o.append("/* the text's font, 5 x 7: a row a byte, bit 4 the left pixel; PF_CODE: each glyph's Unicode code point */")
    o.append(f"#define PF_N {len(ORDER)}u")
    o.append(carr("PF_CODE", "uint16_t", [ord(c) for c in ORDER], 12, "0x{:04X}"))
    o.append("static const uint8_t PF_GLYPH[PF_N][7] = {")
    for c in ORDER:
        o.append("    {" + ", ".join(str(int(r.replace("#", "1").replace(".", "0"), 2)) for r in F[c]) + "},")
    o.append("};")
    return "\n".join(o) + "\n"


def sheet(path):
    """the pictures as one image, to look at"""
    d = json.loads((SRC / "hamsters.json").read_text())
    h, pal, frames = drummer()
    im = Image.new("RGB", (480, 54 + h + 8 * 3 + 12), (247, 236, 215))
    cols = [hexrgb(c) for c in d["palette"]]
    for i, hm in enumerate(d["hamsters"]):
        for y, row in enumerate(hm["rows"]):
            for x, c in enumerate(row):
                if c != ".":
                    im.putpixel((i * 58 + x, y), cols[".0123456789ABCDEFGH".index(c) - 1])
    for f, px in enumerate(frames):
        for i, v in enumerate(px):
            if v != 255:
                im.putpixel((f * (DRUM_W + 4) + i % DRUM_W, 56 + i // DRUM_W), pal[v])
    for i, c in enumerate(ORDER):
        for y, r in enumerate(F[c]):
            for x, b in enumerate(r):
                if b == "#":
                    im.putpixel((2 + (i % 78) * 6 + x, 58 + h + (i // 78) * 9 + y), (9, 26, 37))
    im.resize((im.width * 3, im.height * 3), Image.NEAREST).save(path)


def main():
    if "--sheet" in sys.argv:
        sheet(sys.argv[sys.argv.index("--sheet") + 1])
        return 0
    text = build()
    if "--check" in sys.argv:
        if not OUT.exists() or OUT.read_text() != text:
            print("ham_art.h: differs from what tools/gen_ham_art.py makes (run it)")
            return 1
        print("ham_art.h: up to date")
        return 0
    OUT.write_text(text)
    print(f"{OUT.relative_to(ROOT)}: {len(text)} bytes")
    return 0


if __name__ == "__main__":
    sys.exit(main())
