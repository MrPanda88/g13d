#!/usr/bin/env python3
"""Find the real drawable area of the G13 LCD.

Stop the daemon first (it redraws every second):  systemctl --user stop g13d
Phase 1: a 1-pixel frame on the 160x43 area we use + corner marks (8 s). All four sides visible?
Phase 2: one full-width line per row, rows 38..47, with the row number printed (3 s each).
         The report has room for 48 rows; the last visible number is the real height.
Phase 3: single-column lines at x = 0 and x = 159 (6 s): both edges visible?
"""
import glob, os, sys, time
from PIL import Image, ImageDraw
from g13d.lcd.fonts import font
from g13d.lcd.framebuffer import HEADER, HEIGHT, REPORT_SIZE, WIDTH, encode, new_image


def hidraw():
    for d in glob.glob("/sys/bus/hid/devices/*046D:C21C*/hidraw/hidraw*"):
        return "/dev/" + os.path.basename(d)
    sys.exit("G13 hidraw not found")


def set_row(buf: bytearray, y: int) -> None:
    for x in range(WIDTH):
        buf[HEADER + x + (y // 8) * WIDTH] |= 1 << (y % 8)


def show(fd, buf: bytes, seconds: float, msg: str) -> None:
    print(msg, flush=True)
    os.write(fd, buf)
    time.sleep(seconds)


fd = os.open(hidraw(), os.O_WRONLY)
f = font(13)

# Phase 1: frame
img = new_image()
d = ImageDraw.Draw(img)
d.rectangle((0, 0, WIDTH - 1, HEIGHT - 1), outline=1)
for x, y in ((0, 0), (WIDTH - 1, 0), (0, HEIGHT - 1), (WIDTH - 1, HEIGHT - 1)):
    d.rectangle((min(max(x - 3, 0), WIDTH - 4), min(max(y - 3, 0), HEIGHT - 4), min(x + 3, WIDTH - 1), min(y + 3, HEIGHT - 1)), fill=1)
d.text((40, 13), "160 x 43 frame", font=f, fill=1)
show(fd, encode(img), 8, "Phase 1: frame on rows 0..42, cols 0..159 (8 s)")

# Phase 2: rows beyond our height
for y in range(38, 48):
    img = new_image()
    ImageDraw.Draw(img).text((4, 2), f"row {y}", font=font(20), fill=1)
    buf = bytearray(encode(img))
    set_row(buf, y)
    show(fd, bytes(buf), 3, f"Phase 2: line on row {y} (3 s)")

# Phase 3: edge columns
img = new_image()
d = ImageDraw.Draw(img)
d.line((0, 0, 0, HEIGHT - 1), fill=1)
d.line((WIDTH - 1, 0, WIDTH - 1, HEIGHT - 1), fill=1)
d.text((30, 13), "x=0 and x=159", font=f, fill=1)
show(fd, encode(img), 6, "Phase 3: columns 0 and 159 (6 s)")
os.close(fd)
print("done — restart the daemon: systemctl --user start g13d")
