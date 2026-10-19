"""Media page: now playing via MPRIS. LCD1 previous, LCD2 play/pause, LCD3 next, LCD4 next player (keys reserved).

The bottom row shows the legends of the four LCD keys, aligned with them as on the profiles page.
"""
from __future__ import annotations

import time

from g13d.lcd.fonts import font
from g13d.lcd.framebuffer import HEIGHT, WIDTH
from g13d.lcd.mpris import MprisWatcher

from .base import Page, fit, marquee
from .profiles import BUTTON_X

LEGEND_Y = HEIGHT - 9       # 9 px high legends, as on the profiles page


def _mmss(us: int) -> str:
    s = max(0, us // 1_000_000)
    return f"{s // 60}:{s % 60:02d}"


class MediaPage(Page):
    name = "media"
    title = "Media"
    reserved_buttons = (1, 2, 3, 4)

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
        draw.text((0, -1), marquee(draw, p.title or p.identity or "—", f_title, WIDTH, t), font=f_title, fill=1)
        sub = p.artist or p.album or (p.identity if p.title else "")
        right = ""
        if p.length_us > 0:
            pos = min(p.position_now_us, p.length_us)
            right = f"{_mmss(pos)}/{_mmss(p.length_us)}"
            # thin progress line between the text and the legends
            draw.line((0, 30, WIDTH - 1, 30), fill=1)
            w = int(round(WIDTH * pos / p.length_us))
            if w > 0:
                draw.rectangle((0, 29, w - 1, 31), fill=1)
        rw = draw.textlength(right, font=f_small) if right else 0
        draw.text((0, 14), fit(draw, sub, f_small, WIDTH - rw - 6), font=f_small, fill=1)
        if right:
            draw.text((WIDTH - rw, 14), right, font=f_small, fill=1)
        n = len(self._w.players)
        players = f"{self._w.index + 1}/{n}" if n > 1 else ""
        self._legends(draw, playing=p.status == "Playing", players=players)

    def _legends(self, draw, playing: bool, players: str) -> None:
        y = LEGEND_Y
        x = BUTTON_X[0]                 # previous: bar + left triangle
        draw.rectangle((x - 5, y, x - 4, y + 8), fill=1)
        draw.polygon([(x - 3, y + 4), (x + 4, y), (x + 4, y + 8)], fill=1)
        x = BUTTON_X[1]                 # play/pause: what pressing does
        if playing:
            draw.rectangle((x - 4, y, x - 2, y + 8), fill=1)
            draw.rectangle((x + 2, y, x + 4, y + 8), fill=1)
        else:
            draw.polygon([(x - 3, y), (x + 4, y + 4), (x - 3, y + 8)], fill=1)
        x = BUTTON_X[2]                 # next: right triangle + bar
        draw.polygon([(x - 4, y), (x + 3, y + 4), (x - 4, y + 8)], fill=1)
        draw.rectangle((x + 4, y, x + 5, y + 8), fill=1)
        if players:                     # next player: index / count, only when there is a choice
            f = font(11, bold=False)
            draw.text((BUTTON_X[3] - draw.textlength(players, font=f) / 2, y - 3), players, font=f, fill=1)

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
