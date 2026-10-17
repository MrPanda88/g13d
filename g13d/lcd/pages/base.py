"""Base class for LCD pages."""
from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

from PIL import Image

if TYPE_CHECKING:
    from PIL import ImageDraw


class PageContext(Protocol):
    """What pages may ask the daemon about."""
    profile_name: str
    mode: int
    recording: bool
    connected: bool


class Page:
    name = "base"
    refresh_seconds: float = 1.0   # 0 = static, redraw only on events

    def render(self, draw: "ImageDraw.ImageDraw", img: Image.Image, ctx: PageContext) -> None:
        raise NotImplementedError

    def button(self, index: int, ctx: PageContext) -> bool:
        """LCD1..LCD4 pressed while this page is shown. Return True if handled."""
        return False
