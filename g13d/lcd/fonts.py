"""Font lookup for the LCD renderer with distro-agnostic fallbacks."""
from __future__ import annotations

import functools
import os

from PIL import ImageFont

_CANDIDATES = {
    True: (  # bold
        "/usr/share/fonts/liberation-mono-fonts/LiberationMono-Bold.ttf",        # Fedora
        "/usr/share/fonts/truetype/liberation/LiberationMono-Bold.ttf",          # Debian/Ubuntu
        "/usr/share/fonts/TTF/LiberationMono-Bold.ttf",                          # Arch
        "/usr/share/fonts/dejavu-sans-mono-fonts/DejaVuSansMono-Bold.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSansMono-Bold.ttf",
        "/usr/share/fonts/TTF/DejaVuSansMono-Bold.ttf",
    ),
    False: (
        "/usr/share/fonts/liberation-mono-fonts/LiberationMono-Regular.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationMono-Regular.ttf",
        "/usr/share/fonts/TTF/LiberationMono-Regular.ttf",
        "/usr/share/fonts/dejavu-sans-mono-fonts/DejaVuSansMono.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf",
        "/usr/share/fonts/TTF/DejaVuSansMono.ttf",
    ),
}


@functools.lru_cache(maxsize=32)
def font(size: int, bold: bool = True) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    for path in _CANDIDATES[bold]:
        if os.path.exists(path):
            return ImageFont.truetype(path, size)
    try:
        return ImageFont.load_default(size)  # Pillow >= 10.1 ships a scalable fallback
    except TypeError:
        return ImageFont.load_default()
