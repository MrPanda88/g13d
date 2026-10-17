#!/usr/bin/env python3
"""Draw a test image on the G13 LCD through hidraw (output report 3, 991 bytes)."""
import glob, os, sys, time
from PIL import Image, ImageDraw, ImageFont
W, H = 160, 43
def find_hidraw():
    for d in glob.glob("/sys/bus/hid/devices/*046D:C21C*/hidraw/hidraw*"):
        return "/dev/" + os.path.basename(d)
    sys.exit("G13 hidraw not found")
def encode(img):
    """1-bit PIL image (white = lit) -> 992-byte report: id 0x03, 31 pad bytes, 960 px bytes."""
    px = img.load()
    buf = bytearray(992); buf[0] = 0x03
    for y in range(H):
        for x in range(W):
            if px[x, y]:
                buf[32 + x + (y // 8) * W] |= 1 << (y % 8)
    return bytes(buf)
img = Image.new("1", (W, H), 0)
d = ImageDraw.Draw(img)
d.rectangle((0, 0, W - 1, H - 1), outline=1)
for x in range(0, 40, 2):  # vertical stripes top-left
    d.line((x + 2, 2, x + 2, 12), fill=1)
d.ellipse((W - 30, 4, W - 6, 28), outline=1)
try:
    font = ImageFont.truetype("/usr/share/fonts/liberation-mono-fonts/LiberationMono-Bold.ttf", 13)
except OSError:
    font = ImageFont.load_default()
d.text((44, 10), "g13d OK", font=font, fill=1)
d.text((4, 28), time.strftime("%H:%M:%S"), font=font, fill=1)
path = find_hidraw()
data = encode(img)
with open(path, "wb", buffering=0) as f:
    n = f.write(data)
print(f"wrote {n} bytes to {path}")
