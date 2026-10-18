"""Profiles page: the profile list; LCD1 = up, LCD2 = down, LCD3 = activate (those keys are reserved)."""
from __future__ import annotations

from g13d.lcd.fonts import font
from g13d.lcd.framebuffer import HEIGHT, WIDTH

from .base import Page, fit

ROWS = 3
ROW_H = 11
# x centres of the four LCD keys, as they sit under the panel
BUTTON_X = (20, 60, 100, 140)


class ProfilesPage(Page):
    name = "profiles"
    title = "Profiles"
    reserved_buttons = (1, 2, 3)

    def __init__(self) -> None:
        self.cursor = 0
        self.top = 0

    def shown(self, ctx) -> None:
        names = sorted(ctx.profile_names)
        self.cursor = names.index(ctx.profile_name) if ctx.profile_name in names else 0
        self._scroll(len(names))

    def _scroll(self, count: int) -> None:
        self.cursor = max(0, min(self.cursor, count - 1))
        if self.cursor < self.top:
            self.top = self.cursor
        elif self.cursor >= self.top + ROWS:
            self.top = self.cursor - ROWS + 1
        self.top = max(0, min(self.top, max(0, count - ROWS)))

    def render(self, draw, img, ctx) -> None:
        names = sorted(ctx.profile_names) or [ctx.profile_name]
        self._scroll(len(names))
        f = font(11, bold=False)
        for row in range(ROWS):
            i = self.top + row
            if i >= len(names):
                break
            y = row * ROW_H
            selected = i == self.cursor
            if selected:
                draw.rectangle((0, y, WIDTH - 1, y + ROW_H - 1), fill=1)
            ink = 0 if selected else 1
            if names[i] == ctx.profile_name:      # active profile: a small triangle in the margin
                draw.polygon([(2, y + 2), (6, y + 5), (2, y + 8)], fill=ink)
            draw.text((10, y - 1), fit(draw, names[i], f, WIDTH - 16), font=f, fill=ink)
        if len(names) > ROWS:
            # scrollbar on the right edge
            h = ROWS * ROW_H
            draw.line((WIDTH - 1, 0, WIDTH - 1, h - 1), fill=1)
            k = max(2, h * ROWS // len(names))
            y0 = (h - k) * self.top // max(1, len(names) - ROWS)
            draw.rectangle((WIDTH - 3, y0, WIDTH - 1, y0 + k - 1), fill=1)
        # button legends aligned with LCD1..3: up, down, select
        y = HEIGHT - 9
        self._arrow(draw, BUTTON_X[0], y, up=True)
        self._arrow(draw, BUTTON_X[1], y, up=False)
        x = BUTTON_X[2]
        draw.line((x - 4, y + 4, x - 1, y + 7, x + 4, y), fill=1, width=2)

    @staticmethod
    def _arrow(draw, x: int, y: int, up: bool) -> None:
        if up:
            draw.polygon([(x, y), (x - 4, y + 4), (x + 4, y + 4)], fill=1)
            draw.rectangle((x - 1, y + 4, x + 1, y + 8), fill=1)
        else:
            draw.polygon([(x, y + 8), (x - 4, y + 4), (x + 4, y + 4)], fill=1)
            draw.rectangle((x - 1, y, x + 1, y + 4), fill=1)

    def button(self, index: int, ctx) -> bool:
        names = sorted(ctx.profile_names)
        if not names:
            return False
        if index == 1:
            self.cursor -= 1
        elif index == 2:
            self.cursor += 1
        elif index == 3:
            self._scroll(len(names))
            ctx.set_profile(names[self.cursor])
            return True
        else:
            return False
        self.cursor %= len(names)
        self._scroll(len(names))
        return True
