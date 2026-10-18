"""Mapping between kernel evdev codes (hid-lg-g15) and g13d logical control names."""
from __future__ import annotations

from evdev import ecodes as e

VENDOR_ID = 0x046D
PRODUCT_ID = 0xC21C

# Keypad device ("Logitech G13 Gaming Keypad")
KEYPAD_CODE_TO_NAME: dict[int, str] = {}
for _i in range(22):
    KEYPAD_CODE_TO_NAME[e.KEY_MACRO1 + _i] = f"G{_i + 1}"
KEYPAD_CODE_TO_NAME.update({
    e.KEY_KBD_LCD_MENU1: "LCD1",
    e.KEY_KBD_LCD_MENU2: "LCD2",
    e.KEY_KBD_LCD_MENU3: "LCD3",
    e.KEY_KBD_LCD_MENU4: "LCD4",
    e.KEY_KBD_LCD_MENU5: "LCD_MENU",   # the small round button left of LCD1
    e.KEY_MACRO_PRESET1: "M1",
    e.KEY_MACRO_PRESET2: "M2",
    e.KEY_MACRO_PRESET3: "M3",
    e.KEY_MACRO_RECORD_START: "MR",
    e.KEY_LIGHTS_TOGGLE: "LIGHT",      # backlight button; the hardware toggles the light itself
})

# Thumbstick device ("Logitech G13 Thumbstick")
STICK_CODE_TO_NAME: dict[int, str] = {
    e.BTN_THUMB: "STICK_PRESS",     # push the stick down
    e.BTN_BASE: "STICK_BTN_LEFT",   # button on the left side of the stick
    e.BTN_BASE2: "STICK_BTN_DOWN",  # button below the stick
}

NAME_TO_CODE = {v: k for k, v in KEYPAD_CODE_TO_NAME.items()} | {v: k for k, v in STICK_CODE_TO_NAME.items()}

MOUSE_BUTTONS = ("BTN_LEFT", "BTN_RIGHT", "BTN_MIDDLE", "BTN_SIDE", "BTN_EXTRA", "BTN_FORWARD", "BTN_BACK", "BTN_TASK")


def key_code(evdev_name: str) -> int:
    """'KEY_A' -> 30. Raises KeyError for unknown names."""
    code = e.ecodes.get(evdev_name)
    if code is None or not (evdev_name.startswith("KEY_") or evdev_name.startswith("BTN_")):
        raise KeyError(evdev_name)
    return code


def key_name(code: int) -> str:
    n = e.KEY.get(code) or e.BTN.get(code)
    if isinstance(n, list):
        n = n[0]
    return n or f"KEY_{code}"

# Short, layout-independent labels for the keys whose evdev name reads badly
KEY_LABELS = {
    "KEY_LEFTCTRL": "Ctrl", "KEY_RIGHTCTRL": "Ctrl R", "KEY_LEFTSHIFT": "Shift", "KEY_RIGHTSHIFT": "Shift R",
    "KEY_LEFTALT": "Alt", "KEY_RIGHTALT": "AltGr", "KEY_LEFTMETA": "Super", "KEY_RIGHTMETA": "Super R",
    "KEY_ENTER": "Enter", "KEY_KPENTER": "KP Enter", "KEY_SPACE": "Space", "KEY_TAB": "Tab", "KEY_ESC": "Esc",
    "KEY_BACKSPACE": "Bksp", "KEY_DELETE": "Del", "KEY_INSERT": "Ins", "KEY_HOME": "Home", "KEY_END": "End",
    "KEY_PAGEUP": "PgUp", "KEY_PAGEDOWN": "PgDn", "KEY_UP": "↑", "KEY_DOWN": "↓", "KEY_LEFT": "←", "KEY_RIGHT": "→",
    "KEY_CAPSLOCK": "Caps", "KEY_NUMLOCK": "Num", "KEY_SCROLLLOCK": "Scroll", "KEY_PRINT": "PrtSc", "KEY_PAUSE": "Pause",
    "KEY_COMPOSE": "Menu", "KEY_MUTE": "Mute", "KEY_VOLUMEUP": "Vol+", "KEY_VOLUMEDOWN": "Vol−",
    "KEY_PLAYPAUSE": "Play", "KEY_NEXTSONG": "Next", "KEY_PREVIOUSSONG": "Prev", "KEY_STOPCD": "Stop",
    "KEY_KP0": "KP 0", "KEY_KP1": "KP 1", "KEY_KP2": "KP 2", "KEY_KP3": "KP 3", "KEY_KP4": "KP 4", "KEY_KP5": "KP 5",
    "KEY_KP6": "KP 6", "KEY_KP7": "KP 7", "KEY_KP8": "KP 8", "KEY_KP9": "KP 9", "KEY_KPDOT": "KP .", "KEY_KPCOMMA": "KP ,",
    "KEY_KPPLUS": "KP +", "KEY_KPMINUS": "KP −", "KEY_KPASTERISK": "KP *", "KEY_KPSLASH": "KP /", "KEY_KPEQUAL": "KP =",
    "BTN_LEFT": "Mouse L", "BTN_RIGHT": "Mouse R", "BTN_MIDDLE": "Mouse M", "BTN_SIDE": "Mouse 4", "BTN_EXTRA": "Mouse 5",
    "BTN_FORWARD": "Mouse Fwd", "BTN_BACK": "Mouse Back", "BTN_TASK": "Mouse Task",
}
