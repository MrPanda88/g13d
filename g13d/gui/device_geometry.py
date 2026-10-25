"""Where every control sits on the device picture (g13d/data/g13.png), as fractions of its size.

Pure data, no GTK: the GUI scales these with the picture so the overlays never drift when the window
is resized. Rectangles are (x, y, w, h) in 0..1, measured on the photo.
"""
from __future__ import annotations

IMAGE_W, IMAGE_H = 1033, 896
ASPECT = IMAGE_W / IMAGE_H

Rect = tuple[float, float, float, float]


def _r(cx: float, cy: float, w: float, h: float) -> Rect:
    """Rect from a centre and a size, in pixels of the photo."""
    return (round((cx - w / 2) / IMAGE_W, 4), round((cy - h / 2) / IMAGE_H, 4), round(w / IMAGE_W, 4), round(h / IMAGE_H, 4))


KEY_W, KEY_H = 100, 68
_G_ROWS = [  # (first key, y, [centre x of each key])
    (1, 212, [172, 290, 404, 517, 629, 744, 860]),
    (8, 316, [169, 284, 400, 515, 630, 747, 862]),
    (15, 430, [267, 394, 513, 635, 760]),
    (20, 543, [367, 513, 660]),
]

# Key caps (what the user clicks and drops onto)
KEYS: dict[str, Rect] = {}
for _first, _y, _xs in _G_ROWS:
    for _i, _x in enumerate(_xs):
        KEYS[f"G{_first + _i}"] = _r(_x, _y, KEY_W, KEY_H)

# Mode keys on the bezel (not bindable, shown for the active mode)
M_KEYS: dict[str, Rect] = {"M1": _r(292, 95, 118, 26), "M2": _r(437, 95, 128, 26), "M3": _r(595, 95, 128, 26), "MR": _r(745, 95, 100, 26)}

# LCD row at the very top (the light key next to them toggles the backlight by itself: not shown)
LCD_KEYS: dict[str, Rect] = {"LCD_MENU": _r(257, 30, 44, 44), "LCD1": _r(377, 30, 82, 22), "LCD2": _r(472, 30, 82, 22),
                             "LCD3": _r(562, 30, 82, 22), "LCD4": _r(652, 30, 82, 22)}
# Controls whose assignment pill sits on the control itself instead of floating above it
PILL_ON_CONTROL = ("LCD_MENU", "LCD1", "LCD2", "LCD3", "LCD4")

# Thumb module
STICK_CENTER = (round(917 / IMAGE_W, 4), round(660 / IMAGE_H, 4))
STICK_RADIUS = round(52 / IMAGE_W, 4)        # fraction of the width
STICK_BUTTONS: dict[str, Rect] = {"STICK_PRESS": _r(917, 660, 70, 70), "STICK_BTN_LEFT": _r(796, 702, 50, 60),
                                  "STICK_BTN_DOWN": _r(925, 838, 100, 44)}
# The stick's own assignment is shown top-right of it, with a leader line to the cap
STICK_PRESS_PILL: Rect = _r(988, 596, 80, 30)
# Direction labels float around the stick, outside the cap
STICK_DIRS: dict[str, Rect] = {"STICK_UP": _r(917, 585, 90, 30), "STICK_DOWN": _r(917, 768, 90, 30),
                               "STICK_LEFT": _r(850, 715, 80, 30), "STICK_RIGHT": _r(986, 715, 74, 30)}

ALL: dict[str, Rect] = {**KEYS, **LCD_KEYS, **STICK_BUTTONS, **STICK_DIRS}


def fit_widths(items: list[tuple[float, float, float, float, float]], gap: float = 0.0) -> list[float]:
    """Widths for labels centred on their slot, so labels sharing a band never overlap.

    items: (centre x, top, bottom, minimum width, wanted width). A label grows into the room its neighbours
    leave free (a short neighbour gives up its share) and never shrinks below its minimum (the slot itself).
    """
    out = []
    for i, (cx, top, bottom, low, want) in enumerate(items):
        half = want / 2
        for j, (cx2, top2, bottom2, _low2, want2) in enumerate(items):
            d = abs(cx2 - cx)
            if j == i or d == 0 or min(bottom, bottom2) <= max(top, top2):
                continue
            half = min(half, max(d / 2, d - want2 / 2) - gap / 2)
        out.append(max(low, min(want, 2 * half)))
    return out
