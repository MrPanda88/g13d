#!/usr/bin/env python3
"""Turn image/g13_naked_template.jpeg (a photo on a fake checkerboard, key legends already removed)
into g13d/data/g13.png with real alpha.

The checkerboard is removed by flood-filling light, unsaturated pixels that are connected to the
image border, so bright parts of the device itself (bezel) are kept. The GUI draws the key legends
itself, tinted like the backlight.
"""
from __future__ import annotations

import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter

SRC = Path("image/g13_naked_template.jpeg")
DST = Path("g13d/data/g13.png")


def main() -> None:
    src = Path(sys.argv[1]) if len(sys.argv) > 1 else SRC
    dst = Path(sys.argv[2]) if len(sys.argv) > 2 else DST
    im = Image.open(src).convert("RGB")
    w, h = im.size
    px = im.load()
    # 255 = looks like checkerboard (light grey / white, no colour), 0 = anything else
    mask = Image.new("L", (w, h), 0)
    mp = mask.load()
    for y in range(h):
        for x in range(w):
            r, g, b = px[x, y]
            lo, hi = min(r, g, b), max(r, g, b)
            if lo > 150 and hi - lo < 28:
                mp[x, y] = 255
    # flood from every border pixel that is "light": only the outside gets 128
    for x in range(w):
        for y in (0, h - 1):
            if mp[x, y] == 255:
                ImageDraw.floodfill(mask, (x, y), 128)
    for y in range(h):
        for x in (0, w - 1):
            if mp[x, y] == 255:
                ImageDraw.floodfill(mask, (x, y), 128)
    alpha = mask.point(lambda v: 0 if v == 128 else 255)
    # soften the cut edge by one pixel so the device does not look paper-cut
    alpha = alpha.filter(ImageFilter.GaussianBlur(0.8))
    out = im.copy()
    out.putalpha(alpha)
    # crop to the opaque content (keeps the PNG small and the geometry simple)
    bbox = alpha.point(lambda v: 255 if v > 8 else 0).getbbox()
    out = out.crop(bbox)
    dst.parent.mkdir(parents=True, exist_ok=True)
    out.save(dst, optimize=True)
    print(f"{dst}: {out.size[0]}x{out.size[1]} (crop box {bbox})")


if __name__ == "__main__":
    main()
