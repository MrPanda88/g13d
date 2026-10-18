#!/usr/bin/env python3
"""Turn image/g13_template.jpeg (a photo on a fake checkerboard) into g13d/data/g13.png with real alpha.

The checkerboard is removed by flood-filling light, unsaturated pixels that are connected to the
image border, so bright parts of the device itself (bezel, key legends) are kept. The printed
G1..G22 legends are then painted over with the colour of their key cap: the GUI draws its own,
tinted like the backlight.
"""
from __future__ import annotations

import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter

from g13d.gui import device_geometry as geo

SRC = Path("image/g13_template.jpeg")
DST = Path("g13d/data/g13.png")


def erase_legends(im: Image.Image) -> None:
    """Paint the printed legend of every G key with the cap's own (dark) colour, softly blended."""
    W, H = im.size
    px = im.load()
    for x, y, w, h in geo.KEYS.values():
        x0, y0, x1, y1 = int(x * W), int(y * H), int((x + w) * W), int((y + h) * H)
        # cap colour: median of the darker pixels of the cap (legend pixels are the bright ones)
        samples = sorted(px[i, j][:3] for i in range(x0, x1, 2) for j in range(y0, y1, 2) if max(px[i, j][:3]) < 120)
        if not samples:
            continue
        r, g, b = samples[len(samples) // 2]
        # the legend sits in the middle of the cap; cover that area, feather the edge
        cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
        pw, ph = (x1 - x0) * 0.8, (y1 - y0) * 0.6
        patch = Image.new("RGBA", (int(pw) + 8, int(ph) + 8), (r, g, b, 0))
        d = ImageDraw.Draw(patch)
        d.rounded_rectangle((4, 4, pw + 4, ph + 4), radius=6, fill=(r, g, b, 255))
        patch = patch.filter(ImageFilter.GaussianBlur(1.5))
        im.alpha_composite(patch, (int(cx - patch.width / 2), int(cy - patch.height / 2)))


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
    erase_legends(out)
    dst.parent.mkdir(parents=True, exist_ok=True)
    out.save(dst, optimize=True)
    print(f"{dst}: {out.size[0]}x{out.size[1]} (crop box {bbox})")


if __name__ == "__main__":
    main()
