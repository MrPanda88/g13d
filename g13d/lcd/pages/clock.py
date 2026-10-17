"""Big clock page."""
from __future__ import annotations

import time

from g13d.lcd.fonts import font
from g13d.lcd.framebuffer import HEIGHT, WIDTH

from .base import Page


class ClockPage(Page):
    name = "clock"
    title = "Clock"

    def render(self, draw, img, ctx) -> None:
        big = font(26)
        small = font(11, bold=False)
        t = time.strftime("%H:%M:%S")
        w = draw.textlength(t, font=big)
        draw.text(((WIDTH - w) / 2, -2), t, font=big, fill=1)
        d = time.strftime("%A %d %B %Y")
        w = draw.textlength(d, font=small)
        draw.text(((WIDTH - w) / 2, HEIGHT - 14), d, font=small, fill=1)
