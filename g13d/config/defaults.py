"""Built-in profile created on first run (when no profile exists yet).

A gaming layout: number row on G1-G7, the WASD cluster on the stick, Ctrl / Alt / Shift / Space under
the thumb. M2 and M3 start as copies of M1. Keys are physical positions, so WASD lands where games
expect it whatever the keyboard layout.
"""
from __future__ import annotations

from .model import Action, Profile, StickConfig

_M1 = {
    "G1": "KEY_ESC", "G2": "KEY_1", "G3": "KEY_2", "G4": "KEY_3", "G5": "KEY_4", "G6": "KEY_5", "G7": "KEY_T",
    "G8": "KEY_TAB", "G9": "KEY_6", "G10": "KEY_7", "G11": "KEY_8", "G12": "KEY_E", "G13": "KEY_R", "G14": "KEY_F",
    "G15": "KEY_SPACE", "G16": "KEY_C", "G17": "KEY_Q", "G18": "KEY_V", "G19": "KEY_LEFTSHIFT",
    "G20": "KEY_LEFTCTRL", "G21": "KEY_LEFTALT", "G22": "KEY_L",
    "STICK_UP": "KEY_W", "STICK_DOWN": "KEY_S", "STICK_LEFT": "KEY_A", "STICK_RIGHT": "KEY_D",
    "STICK_PRESS": "KEY_G", "STICK_BTN_LEFT": "KEY_I", "STICK_BTN_DOWN": "KEY_SEMICOLON",
}
def default_profile(name: str = "Default") -> Profile:
    m1 = {c: Action.key(k) for c, k in _M1.items()}
    m1["LCD_MENU"] = Action.lcd_page("next")
    return Profile(name=name, backlight=(9, 135, 5), stick=StickConfig(mode="keys", scroll_speed=20.0),
                   modes={1: dict(m1), 2: dict(m1), 3: dict(m1)})
