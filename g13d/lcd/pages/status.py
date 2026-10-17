"""Status page: profile name, current M mode, time."""
from __future__ import annotations

import time

from g13d.lcd.fonts import font
from g13d.lcd.framebuffer import HEIGHT, WIDTH

from .base import Page


class StatusPage(Page):
    name = "status"
    refresh_seconds = 1.0

    def render(self, draw, img, ctx) -> None:
        big = font(15)
        small = font(11, bold=False)
        # Mode badge, top right, inverted.
        badge = f"M{ctx.mode}" if not ctx.recording else "MR"
        bw = draw.textlength(badge, font=big) + 8
        draw.rectangle((WIDTH - bw, 0, WIDTH - 1, 18), fill=1)
        draw.text((WIDTH - bw + 4, 1), badge, font=big, fill=0)
        # Profile name, truncated to fit left of the badge.
        name = ctx.profile_name
        while name and draw.textlength(name, font=big) > WIDTH - bw - 6:
            name = name[:-1]
        draw.text((1, 1), name, font=big, fill=1)
        draw.line((0, 21, WIDTH - 1, 21), fill=1)
        draw.text((1, HEIGHT - 15), time.strftime("%H:%M  %a %d %b"), font=small, fill=1)
        draw.text((WIDTH - 30, HEIGHT - 15), "g13d", font=small, fill=1)
