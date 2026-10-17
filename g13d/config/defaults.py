"""Built-in default profile: mirrors the left half of a keyboard, stick = arrow keys."""
from __future__ import annotations

from .model import Action, Profile, StickConfig

_ROW1 = ["KEY_1", "KEY_2", "KEY_3", "KEY_4", "KEY_5", "KEY_6", "KEY_7"]            # G1..G7
_ROW2 = ["KEY_TAB", "KEY_Q", "KEY_W", "KEY_E", "KEY_R", "KEY_T", "KEY_Y"]          # G8..G14
_ROW3 = ["KEY_A", "KEY_S", "KEY_D", "KEY_F", "KEY_G"]                               # G15..G19
_ROW4 = ["KEY_LEFTCTRL", "KEY_LEFTALT", "KEY_SPACE"]                               # G20..G22


def default_profile(name: str = "Default") -> Profile:
    keys = _ROW1 + _ROW2 + _ROW3 + _ROW4
    m1 = {f"G{i + 1}": Action.key(k) for i, k in enumerate(keys)}
    m1.update({
        "STICK_UP": Action.key("KEY_UP"),
        "STICK_DOWN": Action.key("KEY_DOWN"),
        "STICK_LEFT": Action.key("KEY_LEFT"),
        "STICK_RIGHT": Action.key("KEY_RIGHT"),
        "STICK_PRESS": Action.key("KEY_ENTER"),
        "STICK_BTN_LEFT": Action.key("KEY_ESC"),
        "STICK_BTN_DOWN": Action.key("KEY_BACKSPACE"),
        "LCD_MENU": Action.lcd_page("next"),
    })
    # M2 / M3 start as copies so switching modes is not a surprise; the user edits them freely.
    return Profile(
        name=name,
        backlight=(51, 153, 255),
        stick=StickConfig(mode="keys"),
        lcd_pages=["status", "clock", "system", "media"],
        modes={1: dict(m1), 2: dict(m1), 3: dict(m1)},
    )
