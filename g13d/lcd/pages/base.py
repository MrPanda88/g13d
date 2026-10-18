"""Base class for LCD pages."""
from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

from PIL import Image

if TYPE_CHECKING:
    from PIL import ImageDraw


class PageContext(Protocol):
    """What pages may ask the daemon about / ask it to do."""
    profile_name: str
    profile_names: list[str]
    mode: int
    recording: bool
    connected: bool
    focused_app: str
    locked_profile: str

    def set_mode(self, mode: int) -> None: ...
    def cycle_profile(self, delta: int) -> None: ...
    def set_profile(self, name: str) -> None: ...
    def set_locked_profile(self, name: str) -> None: ...


class Page:
    """A screen. Subclasses draw with PIL into a 160x43 1-bit image (1 = lit pixel).

    Legibility rules (the panel has no anti-aliasing): text with font(11, bold=False) or bigger, bold only
    from 13 px, rows at least 11 px apart with text drawn at y - 1, symbols drawn with primitives rather
    than non-ASCII glyphs. Render with scripts/render_pages.py before shipping a page.
    """
    name = "base"
    title = "Page"
    # LCD buttons (1..4) this page takes for itself while shown, even if the key is bound
    reserved_buttons: tuple[int, ...] = ()
    # user-settable options: name -> (label, [(value, label), ...]); values live in Profile.lcd_options
    options: dict[str, tuple[str, list[tuple[str, str]]]] = {}

    def configure(self, options: dict[str, str]) -> None:
        """Receive the profile's LCD options (all pages get the whole dict)."""

    def shown(self, ctx: PageContext) -> None:
        """Called when the page becomes the one on screen."""

    def attach(self) -> None:
        """Called when the page becomes part of the active page list (start tasks here)."""

    def detach(self) -> None:
        """Called when the page is removed or the screen is torn down (stop tasks here)."""

    def render(self, draw: "ImageDraw.ImageDraw", img: Image.Image, ctx: PageContext) -> None:
        raise NotImplementedError

    def button(self, index: int, ctx: PageContext) -> bool:
        """LCD1..LCD4 (index 1..4) pressed while this page is shown and the key is unbound."""
        return False


def fit(draw: "ImageDraw.ImageDraw", text: str, font, max_width: float) -> str:
    """Truncate text with an ellipsis so it fits max_width pixels."""
    if draw.textlength(text, font=font) <= max_width:
        return text
    while text and draw.textlength(text + "…", font=font) > max_width:
        text = text[:-1]
    return text + "…"


def marquee(draw: "ImageDraw.ImageDraw", text: str, font, max_width: float, t: float, speed: float = 12.0) -> str:
    """Return the visible slice of text, scrolling horizontally over time when too long."""
    if draw.textlength(text, font=font) <= max_width:
        return text
    padded = text + "   "
    n = len(padded)
    offset = int(t * speed / 8) % n   # ~1.5 characters per second at speed 12
    rolled = padded[offset:] + padded[:offset]
    while rolled and draw.textlength(rolled, font=font) > max_width:
        rolled = rolled[:-1]
    return rolled


def bar(draw: "ImageDraw.ImageDraw", x0: int, y0: int, x1: int, y1: int, ratio: float) -> None:
    """Horizontal progress bar with 1px border."""
    draw.rectangle((x0, y0, x1, y1), outline=1, fill=0)
    inner = x1 - x0 - 3
    w = int(round(max(0.0, min(1.0, ratio)) * inner))
    if w > 0:
        draw.rectangle((x0 + 2, y0 + 2, x0 + 1 + w, y1 - 2), fill=1)
