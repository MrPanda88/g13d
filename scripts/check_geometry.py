#!/usr/bin/env python3
"""Draw device_geometry over g13d/data/g13.png to check the overlays line up. Usage: check_geometry.py OUT.png"""
import sys

from PIL import Image, ImageDraw

from g13d.gui import device_geometry as g

im = Image.open("g13d/data/g13.png").convert("RGBA")
d = ImageDraw.Draw(im)
W, H = im.size
for name, (x, y, w, h) in {**g.ALL, **g.M_KEYS}.items():
    box = (x * W, y * H, (x + w) * W, (y + h) * H)
    d.rectangle(box, outline=(0, 255, 120, 255), width=2)
    d.text((box[0] + 3, box[1] + 2), name, fill=(255, 80, 80, 255))
cx, cy, r = g.STICK_CENTER[0] * W, g.STICK_CENTER[1] * H, g.STICK_RADIUS * W
d.ellipse((cx - r, cy - r, cx + r, cy + r), outline=(255, 200, 0, 255), width=2)
im.save(sys.argv[1])
