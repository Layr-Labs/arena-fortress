#!/usr/bin/env python3
"""Pixel diff of two DF legends bitmaps (24-bit BMP, e.g. region7-...-detailed.bmp) from two world gens of one seed.

  python3 embark/bmp_diff.py A.bmp B.bmp [--px-per-tile 16]

Prints the number of differing pixels, the world tiles (pixel // px_per_tile) they fall in, and the colour pairs, so a
difference can be read as terrain (many pixels, terrain colours) vs sites/roads (few pixels, marker colours).
research/seed-portability.md.
"""
import collections, struct, sys


def read(p):
    b = open(p, "rb").read()
    off, w, h, bpp = struct.unpack_from("<I", b, 10)[0], *struct.unpack_from("<ii", b, 18), struct.unpack_from("<H", b, 28)[0]
    assert bpp == 24, bpp
    row = (w * 3 + 3) & ~3
    px = {}
    for y in range(abs(h)):
        yy = (abs(h) - 1 - y) if h > 0 else y        # BMP rows are bottom-up when h > 0
        r = b[off + y * row: off + y * row + w * 3]
        for x in range(w):
            px[(x, yy)] = tuple(r[x * 3: x * 3 + 3][::-1])
    return w, abs(h), px


def main(a, b, ppt=16):
    wa, ha, pa = read(a)
    wb, hb, pb = read(b)
    if (wa, ha) != (wb, hb):
        print(f"size differs: {wa}x{ha} vs {wb}x{hb}")
        return 1
    diff = [k for k in pa if pa[k] != pb[k]]
    tiles = collections.Counter((x // ppt, y // ppt) for x, y in diff)
    colours = collections.Counter((pa[k], pb[k]) for k in diff)
    print(f"{len(diff)} of {wa * ha} pixels differ, in {len(tiles)} world tiles")
    for t, n in sorted(tiles.items()):
        print(f"  tile {t}: {n} px")
    print("colour pairs (A -> B), most common:")
    for (ca, cb), n in colours.most_common(12):
        print(f"  {ca} -> {cb}: {n}")
    return 0 if not diff else 1


if __name__ == "__main__":
    args = [x for x in sys.argv[1:] if not x.startswith("--")]
    ppt = int(sys.argv[sys.argv.index("--px-per-tile") + 1]) if "--px-per-tile" in sys.argv else 16
    if len(args) != 2:
        sys.exit(__doc__)
    sys.exit(main(*args[:2], ppt))
