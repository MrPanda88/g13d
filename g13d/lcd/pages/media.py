"""Media page: now playing via MPRIS. Buttons: LCD1 prev, LCD2 play/pause, LCD3 next, LCD4 next player."""
from __future__ import annotations

import time

from g13d.lcd.fonts import font
from g13d.lcd.framebuffer import HEIGHT, WIDTH
from g13d.lcd.mpris import MprisWatcher

from .base import Page, bar, fit, marquee


def _mmss(us: int) -> str:
    s = max(0, us // 1_000_000)
    return f"{s // 60}:{s % 60:02d}"


class MediaPage(Page):
    name = "media"
    title = "Media"

    def __init__(self, watcher: MprisWatcher | None = None) -> None:
        self._w = watcher or MprisWatcher()

    def attach(self) -> None:
        self._w.start()

    def detach(self) -> None:
        self._w.stop()

    def render(self, draw, img, ctx) -> None:
        f_title = font(13)
        f_small = font(11, bold=False)
        p = self._w.active
        if p is None:
            msg = "No media player"
            draw.text(((WIDTH - draw.textlength(msg, font=f_title)) / 2, 14), msg, font=f_title, fill=1)
            return
        t = time.monotonic()
        icon = {"Playing": ">", "Paused": "||", "Stopped": "[]"}.get(p.status, "?")
        draw.text((0, 0), marquee(draw, p.title or "—", f_title, WIDTH - 16, t), font=f_title, fill=1)
        draw.text((WIDTH - 12, 0), icon, font=f_title, fill=1)
        sub = p.artist or p.album or p.identity
        draw.text((0, 15), fit(draw, sub, f_small, WIDTH), font=f_small, fill=1)
        if p.length_us > 0:
            pos = min(p.position_now_us, p.length_us)
            label = f"{_mmss(pos)}/{_mmss(p.length_us)}"
            lw = draw.textlength(label, font=f_small)
            bar(draw, 0, HEIGHT - 10, int(WIDTH - lw - 6), HEIGHT - 2, pos / p.length_us)
            draw.text((WIDTH - lw, HEIGHT - 13), label, font=f_small, fill=1)
        else:
            draw.text((0, HEIGHT - 13), fit(draw, p.identity, f_small, WIDTH), font=f_small, fill=1)

    def button(self, index: int, ctx) -> bool:
        match index:
            case 1:
                self._w.control("Previous")
            case 2:
                self._w.control("PlayPause")
            case 3:
                self._w.control("Next")
            case 4:
                self._w.select_next()
        return True
