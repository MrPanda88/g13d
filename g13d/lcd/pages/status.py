"""Status page: profile name, current M mode, time. Buttons: LCD1-3 = M1-M3, LCD4 = next profile."""
from __future__ import annotations

import time

from g13d.lcd.fonts import font
from g13d.lcd.framebuffer import HEIGHT, WIDTH

from .base import Page, fit


class StatusPage(Page):
    name = "status"
    title = "Status"

    def render(self, draw, img, ctx) -> None:
        big = font(15)
        small = font(11, bold=False)
        badge = "MR" if ctx.recording else f"M{ctx.mode}"
        bw = draw.textlength(badge, font=big) + 8
        draw.rectangle((WIDTH - bw, 0, WIDTH - 1, 18), fill=1)
        draw.text((WIDTH - bw + 4, 1), badge, font=big, fill=0)
        draw.text((1, 1), fit(draw, ctx.profile_name, big, WIDTH - bw - 6), font=big, fill=1)
        draw.line((0, 21, WIDTH - 1, 21), fill=1)
        draw.text((1, HEIGHT - 15), time.strftime("%H:%M  %a %d %b"), font=small, fill=1)
        draw.text((WIDTH - 30, HEIGHT - 15), "g13d", font=small, fill=1)

    def button(self, index: int, ctx) -> bool:
        if index in (1, 2, 3):
            ctx.set_mode(index)
        elif index == 4:
            ctx.cycle_profile(1)
        return True
