"""Modal page shown while linking a profile to an application: LCD3 confirms the focused app, LCD4 cancels."""
from __future__ import annotations

from collections.abc import Callable

from g13d.lcd.fonts import font
from g13d.lcd.framebuffer import HEIGHT, WIDTH

from .base import Page, fit
from .profiles import BUTTON_X


class CapturePage(Page):
    name = "capture"
    title = "Link application"
    reserved_buttons = (1, 2, 3, 4)

    def __init__(self, profile_name: str, on_confirm: Callable[[], None], on_cancel: Callable[[], None]):
        self.profile_name = profile_name
        self._confirm = on_confirm
        self._cancel = on_cancel

    def render(self, draw, img, ctx) -> None:
        small = font(11, bold=False)
        bold = font(13)
        draw.text((1, -1), fit(draw, f"Link {self.profile_name}", bold, WIDTH - 2), font=bold, fill=1)
        app = getattr(ctx, "focused_app", "") or "(no window focused)"
        draw.text((1, 14), fit(draw, "to: " + app, small, WIDTH - 2), font=small, fill=1)
        # legends under LCD3 (confirm) and LCD4 (cancel)
        y = HEIGHT - 9
        x = BUTTON_X[2]
        draw.line((x - 4, y + 4, x - 1, y + 7, x + 4, y), fill=1, width=2)
        x = BUTTON_X[3]
        draw.line((x - 3, y + 1, x + 3, y + 7), fill=1, width=2)
        draw.line((x - 3, y + 7, x + 3, y + 1), fill=1, width=2)

    def button(self, index: int, ctx) -> bool:
        if index == 3:
            self._confirm()
        elif index == 4:
            self._cancel()
        return True
