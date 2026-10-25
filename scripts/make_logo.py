#!/usr/bin/env python3
"""Generate the app icon g13d/data/icons/org.g13d.Gui.svg (128x128, GNOME app icon grid).

The G13 seen as its mode LEDs (M1 lit) over the staggered 7/7/5/3 key rows, with the thumbstick.
usage: scripts/make_logo.py [OUT.svg]
"""
import sys
from pathlib import Path

OUT = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).resolve().parent.parent / "g13d/data/icons/org.g13d.Gui.svg"
INK, STICK, KEY, LED_ON, LED_OFF = "#1b1e24", "#8cc8ff", "#c9d1dc", "#ff453a", "#5a2a2a"
ROWS = [7, 7, 5, 3]          # G1-G7, G8-G14, G15-G19, G20-G22, the lower rows centred like the device

DEFS = ('<linearGradient id="dk" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#363b46"/>'
        '<stop offset="1" stop-color="#16181d"/></linearGradient>'
        '<filter id="glow" x="-50%" y="-50%" width="200%" height="200%"><feGaussianBlur stdDeviation="2.2" result="b"/>'
        '<feMerge><feMergeNode in="b"/><feMergeNode in="SourceGraphic"/></feMerge></filter>')


def keypad(x0: float, y0: float, key: float, gap: float) -> str:
    out = []
    full = 7 * key + 6 * gap
    for r, n in enumerate(ROWS):
        x = x0 + (full - (n * key + (n - 1) * gap)) / 2
        for i in range(n):
            out.append(f'<rect x="{x + i * (key + gap):.1f}" y="{y0 + r * (key + gap):.1f}" width="{key}" '
                       f'height="{key * 0.82:.1f}" rx="2.4" fill="{KEY}"/>')
    return "".join(out)


def icon() -> str:
    tile = ('<rect x="8" y="12" width="112" height="112" rx="22" fill="#000" opacity="0.25"/>'
            '<rect x="8" y="8" width="112" height="112" rx="22" fill="url(#dk)"/>')
    leds = (f'<g filter="url(#glow)"><rect x="26" y="24" width="22" height="8" rx="4" fill="{LED_ON}"/></g>'
            + "".join(f'<rect x="{26 + i * 27}" y="24" width="22" height="8" rx="4" fill="{c}"/>'
                      for i, c in enumerate([LED_ON, LED_OFF, LED_OFF])))
    stick = (f'<circle cx="99" cy="93" r="10" fill="{INK}" stroke="{STICK}" stroke-width="2.5"/>'
             f'<circle cx="99" cy="93" r="4" fill="{STICK}"/>')
    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="128" height="128" viewBox="0 0 128 128">'
            f'<defs>{DEFS}</defs>{tile}{leds}{keypad(22, 44, 10, 2.4)}{stick}</svg>\n')


if __name__ == "__main__":
    OUT.write_text(icon())
    print(OUT)
