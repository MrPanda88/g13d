"""LCD screen manager: page list, cycling, transient messages, periodic refresh."""
from __future__ import annotations

import asyncio
import logging
import time

from PIL import ImageDraw

from g13d.hw.lcd_dev import LcdDevice

from .fonts import font
from .framebuffer import HEIGHT, WIDTH, encode, new_image
from .pages import make_pages
from .pages.base import Page, PageContext

log = logging.getLogger(__name__)


class Screen:
    def __init__(self, ctx: PageContext):
        self._ctx = ctx
        self._dev: LcdDevice | None = None
        self._pages: list[Page] = make_pages(["status"])
        self._index = 0
        self._message: tuple[str, float] | None = None   # text, deadline
        self._task: asyncio.Task | None = None
        self._last: bytes | None = None

    # ---- lifecycle --------------------------------------------------------
    def attach(self, dev: LcdDevice) -> None:
        self._dev = dev
        self._last = None
        self.refresh(force=True)
        if self._task is None or self._task.done():
            self._task = asyncio.get_running_loop().create_task(self._loop())

    def detach(self) -> None:
        self._dev = None
        if self._task is not None:
            self._task.cancel()
            self._task = None

    def set_pages(self, names: list[str]) -> None:
        current = self.current.name
        self._pages = make_pages(names)
        self._index = next((i for i, p in enumerate(self._pages) if p.name == current), 0)
        self.refresh(force=True)

    # ---- navigation ---------------------------------------------------------
    @property
    def current(self) -> Page:
        return self._pages[self._index]

    def show(self, name: str) -> None:
        if name == "next":
            self._index = (self._index + 1) % len(self._pages)
        elif name == "prev":
            self._index = (self._index - 1) % len(self._pages)
        else:
            for i, p in enumerate(self._pages):
                if p.name == name:
                    self._index = i
                    break
            else:
                log.warning("unknown LCD page %r", name)
                return
        self._message = None
        self.refresh(force=True)

    def button(self, index: int) -> bool:
        return self.current.button(index, self._ctx)

    def message(self, text: str, seconds: float = 3.0) -> None:
        self._message = (text, time.monotonic() + max(seconds, 0.1))
        self.refresh(force=True)

    # ---- drawing ------------------------------------------------------------
    def refresh(self, force: bool = False) -> None:
        if self._dev is None:
            return
        img = new_image()
        draw = ImageDraw.Draw(img)
        if self._message and time.monotonic() < self._message[1]:
            self._draw_message(draw, self._message[0])
        else:
            self._message = None
            try:
                self.current.render(draw, img, self._ctx)
            except Exception:  # a broken page must never kill the daemon
                log.exception("LCD page %s failed to render", self.current.name)
        data = encode(img)
        if force or data != self._last:
            self._last = data
            self._dev.write(data)

    @staticmethod
    def _draw_message(draw, text: str) -> None:
        f = font(13)
        lines = text.split("\n")[:3]
        y = (HEIGHT - 15 * len(lines)) / 2
        for line in lines:
            w = draw.textlength(line, font=f)
            draw.text(((WIDTH - w) / 2, y), line, font=f, fill=1)
            y += 15

    async def _loop(self) -> None:
        try:
            while True:
                now = time.time()
                await asyncio.sleep(1.0 - (now % 1.0))
                self.refresh()
        except asyncio.CancelledError:
            pass
