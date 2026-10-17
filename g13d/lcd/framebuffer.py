"""G13 LCD framebuffer encoding.

The panel is 160x43 monochrome. The device expects one HID output report:
    byte 0        report id 0x03
    bytes 1..31   zero
    bytes 32..991 pixels: byte = 32 + x + (y // 8) * 160, bit = y % 8 (bit 0 = top row of the band)
"""
from __future__ import annotations

from PIL import Image

WIDTH = 160
HEIGHT = 43
BANDS = 6                      # ceil(43 / 8)
PIXEL_BYTES = WIDTH * BANDS    # 960
HEADER = 32
REPORT_SIZE = HEADER + PIXEL_BYTES  # 992
REPORT_ID = 0x03

_REVERSE = bytes(int(f"{i:08b}"[::-1], 2) for i in range(256))


def new_image() -> Image.Image:
    """Blank 1-bit image; draw with white (1) for lit pixels."""
    return Image.new("1", (WIDTH, HEIGHT), 0)


def encode(img: Image.Image) -> bytes:
    """Encode a 160x43 image (any mode) into the 992-byte report."""
    if img.size != (WIDTH, HEIGHT):
        raise ValueError(f"image must be {WIDTH}x{HEIGHT}, got {img.size}")
    if img.mode != "1":
        img = img.convert("1", dither=Image.Dither.NONE)
    # Transpose so that each source column becomes a packed row of 6 bytes (MSB first),
    # then flip the bit order so bit 0 is the top pixel of each band.
    cols = img.transpose(Image.Transpose.TRANSPOSE).tobytes()  # 160 rows * 6 bytes
    cols = cols.translate(_REVERSE)
    out = bytearray(REPORT_SIZE)
    out[0] = REPORT_ID
    for band in range(BANDS):
        start = HEADER + band * WIDTH
        out[start:start + WIDTH] = cols[band::BANDS]
    return bytes(out)


def encode_slow(img: Image.Image) -> bytes:
    """Reference implementation (pixel by pixel) used by the tests."""
    px = img.convert("1", dither=Image.Dither.NONE).load()
    out = bytearray(REPORT_SIZE)
    out[0] = REPORT_ID
    for y in range(HEIGHT):
        for x in range(WIDTH):
            if px[x, y]:
                out[HEADER + x + (y // 8) * WIDTH] |= 1 << (y % 8)
    return bytes(out)
