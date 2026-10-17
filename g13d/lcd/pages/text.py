"""Free text page, filled over D-Bus (g13ctl lcd-text -s 0 "...")."""
from __future__ import annotations

from g13d.lcd.fonts import font
from g13d.lcd.framebuffer import HEIGHT, WIDTH

from .base import Page


def wrap(draw, text: str, f, max_width: float) -> list[str]:
    lines: list[str] = []
    for para in text.split("\n"):
        words = para.split()
        if not words:
            lines.append("")
            continue
        cur = words[0]
        for w in words[1:]:
            if draw.textlength(cur + " " + w, font=f) <= max_width:
                cur += " " + w
            else:
                lines.append(cur)
                cur = w
        lines.append(cur)
    return lines


class TextPage(Page):
    name = "text"
    title = "Text"
    text = ""

    def render(self, draw, img, ctx) -> None:
        if not self.text:
            f = font(11, bold=False)
            msg = "g13ctl lcd-text -s 0 ..."
            draw.text(((WIDTH - draw.textlength(msg, font=f)) / 2, 15), msg, font=f, fill=1)
            return
        for size, step in ((15, 16), (13, 14), (11, 12), (9, 10)):
            f = font(size)
            lines = wrap(draw, self.text, f, WIDTH)
            if len(lines) * step <= HEIGHT + 2:
                break
        y = max(0, (HEIGHT - len(lines) * step) // 2)
        for line in lines[: HEIGHT // step + 1]:
            draw.text((0, y), line, font=f, fill=1)
            y += step
