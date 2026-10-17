"""Blank page: turns every pixel off (useful at night, the backlight stays as configured)."""
from __future__ import annotations

from .base import Page


class BlankPage(Page):
    name = "blank"
    title = "Blank"

    def render(self, draw, img, ctx) -> None:
        return
