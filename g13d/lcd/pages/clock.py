"""Clock page: an analog dial on the left (hour, minute and thin second hands), time and date on the right.

The dial style is a per-profile LCD option (clock_style); "digital" drops the dial for a big time.
"""
from __future__ import annotations

import math
import time

from g13d.lcd.fonts import font
from g13d.lcd.framebuffer import HEIGHT, WIDTH

from .base import Page, fit

STYLES = [("classic", "Classic (12 ticks)"), ("minimal", "Minimal (4 ticks)"), ("numbers", "Numbers"),
          ("plain", "Plain circle"), ("radar", "Radar sweep"), ("orbit", "Orbit"), ("bars", "Bars"),
          ("binary", "Binary"), ("digital", "Digital only")]
HANDS = ("classic", "minimal", "numbers", "plain")
DEFAULT_STYLE = "classic"

CX, CY, R = 21, 21, 20          # dial centre and radius (the panel is 43 px tall)


def _polar(cx: float, cy: float, r: float, angle_deg: float) -> tuple[float, float]:
    a = math.radians(angle_deg - 90)
    return cx + r * math.cos(a), cy + r * math.sin(a)


class ClockPage(Page):
    name = "clock"
    title = "Clock"
    options = {"clock_style": ("Clock dial", STYLES)}

    def __init__(self) -> None:
        self.style = DEFAULT_STYLE

    def configure(self, options: dict[str, str]) -> None:
        style = options.get("clock_style", DEFAULT_STYLE)
        self.style = style if style in dict(STYLES) else DEFAULT_STYLE

    def render(self, draw, img, ctx) -> None:
        lt = time.localtime()
        if self.style == "digital":
            self._digital(draw, lt)
            return
        if self.style in HANDS:
            self._dial(draw, lt)
        else:
            getattr(self, "_" + self.style)(draw, lt)
        x0 = CX + R + 5                     # text column
        w = WIDTH - x0
        big, small = font(15), font(10, bold=False)
        t = time.strftime("%X", lt)         # locale time, e.g. 18:05:09 or 6:05:09 PM
        draw.text((x0 + (w - draw.textlength(t, font=big)) / 2, -1), t, font=big, fill=1)
        day = time.strftime("%A", lt).capitalize()
        date = time.strftime("%d %B %Y", lt).lstrip("0")
        for i, line in enumerate((day, date)):
            line = fit(draw, line, small, w)
            draw.text((x0 + (w - draw.textlength(line, font=small)) / 2, 17 + i * 12), line, font=small, fill=1)

    def _dial(self, draw, lt) -> None:
        draw.ellipse((CX - R, CY - R, CX + R, CY + R), outline=1, fill=0)
        if self.style == "classic":
            for h in range(12):
                length = 3 if h % 3 == 0 else 1
                draw.line((*_polar(CX, CY, R - 1, h * 30), *_polar(CX, CY, R - 1 - length, h * 30)), fill=1)
        elif self.style == "minimal":
            for h in (0, 3, 6, 9):
                draw.line((*_polar(CX, CY, R - 1, h * 30), *_polar(CX, CY, R - 4, h * 30)), fill=1)
        elif self.style == "numbers":
            f = font(8, bold=False)
            for h, label in ((0, "12"), (3, "3"), (6, "6"), (9, "9")):
                x, y = _polar(CX, CY, R - 5, h * 30)
                draw.text((x - draw.textlength(label, font=f) / 2, y - 3), label, font=f, fill=1)
        hour = (lt.tm_hour % 12 + lt.tm_min / 60) * 30
        minute = (lt.tm_min + lt.tm_sec / 60) * 6
        second = lt.tm_sec * 6
        draw.line((CX, CY, *_polar(CX, CY, R * 0.55, hour)), fill=1, width=2)
        draw.line((CX, CY, *_polar(CX, CY, R * 0.85, minute)), fill=1, width=2)
        draw.line((CX, CY, *_polar(CX, CY, R * 0.9, second)), fill=1, width=1)
        draw.rectangle((CX - 1, CY - 1, CX + 1, CY + 1), fill=1)

    # ---- the exotic ones ------------------------------------------------------------
    @staticmethod
    def _radar(draw, lt) -> None:
        """Concentric rings, a sweeping beam for the seconds, blips for the hour and the minute."""
        for k in (1.0, 0.66, 0.33):
            draw.ellipse((CX - R * k, CY - R * k, CX + R * k, CY + R * k), outline=1)
        draw.line((CX - R, CY, CX + R, CY), fill=1)
        draw.line((CX, CY - R, CX, CY + R), fill=1)
        a = lt.tm_sec * 6 - 90
        draw.pieslice((CX - R, CY - R, CX + R, CY + R), a - 40, a, fill=1)
        for angle, radius, size in (((lt.tm_hour % 12 + lt.tm_min / 60) * 30, R * 0.45, 3), (lt.tm_min * 6, R * 0.8, 2)):
            x, y = _polar(CX, CY, radius, angle)
            draw.rectangle((x - size, y - size, x + size, y + size), fill=1)

    @staticmethod
    def _orbit(draw, lt) -> None:
        """A sun, the hour as a planet on the inner orbit, the minute on the outer one, the second as a moon."""
        for radius in (R * 0.5, R * 0.85):
            for k in range(0, 360, 12):
                x, y = _polar(CX, CY, radius, k)
                draw.point((round(x), round(y)), fill=1)
        draw.ellipse((CX - 3, CY - 3, CX + 3, CY + 3), fill=1)
        for k in range(0, 360, 45):
            draw.line((*_polar(CX, CY, 4, k), *_polar(CX, CY, 6, k)), fill=1)
        hx, hy = _polar(CX, CY, R * 0.5, (lt.tm_hour % 12 + lt.tm_min / 60) * 30)
        draw.ellipse((hx - 3, hy - 3, hx + 3, hy + 3), fill=1)
        mx, my = _polar(CX, CY, R * 0.85, lt.tm_min * 6 + lt.tm_sec / 10)
        draw.ellipse((mx - 2, my - 2, mx + 2, my + 2), fill=1)
        sx, sy = _polar(mx, my, 5, lt.tm_sec * 6)
        draw.point((round(sx), round(sy)), fill=1)

    @staticmethod
    def _bars(draw, lt) -> None:
        """Three gauges (day, hour, minute): the percentage in plain digits with a thin level line under it.
        Digits and fill never overlap: inverted or thickened digits turn to mush on the real panel."""
        label_font, pct_font = font(13), font(11, bold=False)
        rows = (("H", (lt.tm_hour + lt.tm_min / 60) / 24), ("M", (lt.tm_min + lt.tm_sec / 60) / 60), ("S", lt.tm_sec / 60))
        x0, x1 = 10, 2 * CX
        for i, (label, ratio) in enumerate(rows):
            y = i * 14
            top, bottom = draw.textbbox((0, 0), label, font=label_font)[1::2]
            draw.text((0, y + (13 - (bottom - top)) / 2 - top), label, font=label_font, fill=1)
            pct = f"{round(ratio * 100)}%"
            draw.text((x1 - draw.textlength(pct, font=pct_font), y - 2), pct, font=pct_font, fill=1)
            # level gauge: 4 px tall, outlined, a 2 px fill growing from the left
            draw.rectangle((x0, y + 9, x1, y + 12), outline=1)
            w = round(ratio * (x1 - x0 - 2))
            if w > 0:
                draw.rectangle((x0 + 1, y + 10, x0 + 1 + w, y + 11), fill=1)

    @staticmethod
    def _binary(draw, lt) -> None:
        """BCD binary clock: six columns (h h m m s s), four bits each, top bit = 8."""
        digits = [int(c) for c in time.strftime("%H%M%S", lt)]
        for col, digit in enumerate(digits):
            x = 3 + col * 7 + (col // 2) * 1
            for bit in range(4):
                y = 4 + bit * 9
                lit = digit & (8 >> bit)
                draw.ellipse((x, y, x + 5, y + 5), outline=1, fill=1 if lit else 0)

    @staticmethod
    def _digital(draw, lt) -> None:
        big = font(26)
        small = font(11, bold=False)
        t = time.strftime("%H:%M:%S", lt)
        draw.text(((WIDTH - draw.textlength(t, font=big)) / 2, -2), t, font=big, fill=1)
        d = time.strftime("%A %d %B %Y", lt)
        draw.text(((WIDTH - draw.textlength(d, font=small)) / 2, HEIGHT - 14), d, font=small, fill=1)
