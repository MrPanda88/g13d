"""Layout-aware labels for evdev key names, and hardware keycode -> evdev name (GTK events)."""
from __future__ import annotations

import gi

gi.require_version("Gdk", "4.0")
from evdev import ecodes  # noqa: E402
from gi.repository import Gdk  # noqa: E402

from g13d.config.model import Action  # noqa: E402

XKB_OFFSET = 8

NICE = {
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
MODIFIERS = {"KEY_LEFTCTRL", "KEY_RIGHTCTRL", "KEY_LEFTSHIFT", "KEY_RIGHTSHIFT", "KEY_LEFTALT", "KEY_RIGHTALT",
             "KEY_LEFTMETA", "KEY_RIGHTMETA"}


def evdev_name_from_keycode(hardware_keycode: int) -> str | None:
    code = hardware_keycode - XKB_OFFSET
    name = ecodes.KEY.get(code)
    if isinstance(name, list):
        name = name[0]
    return name


def key_label(name: str) -> str:
    """What the key prints with the user's current layout, else a readable evdev name."""
    if name in NICE:
        return NICE[name]
    code = ecodes.ecodes.get(name)
    display = Gdk.Display.get_default()
    if code is not None and display is not None and name.startswith("KEY_"):
        ok, keyval, _group, _level, _consumed = display.translate_key(code + XKB_OFFSET, Gdk.ModifierType(0), 0)
        if ok:
            uni = Gdk.keyval_to_unicode(keyval)
            if uni and not chr(uni).isspace() and uni >= 0x20:
                return chr(uni).upper() if chr(uni).isalpha() else chr(uni)
            kname = Gdk.keyval_name(keyval)
            if kname and not kname.startswith("0x"):
                return kname.replace("KP_", "KP ")
    return name.removeprefix("KEY_").removeprefix("BTN_").replace("_", " ").title()


def action_label(action: Action) -> str:
    match action.type:
        case "none":
            return "—"
        case "key":
            return key_label(action.keys[0])
        case "combo":
            return "+".join(key_label(k) for k in action.keys)
        case "macro":
            return f"⏵ {action.name}"
        case "mouse":
            return key_label(action.name)
        case "mode":
            return f"→ M{action.number}"
        case "profile":
            return f"→ {action.name}"
        case "lcd_page":
            return f"LCD: {action.name}"
    return action.type


def watch_keymap(callback) -> None:
    """Call back when the compositor sends a new keymap (layout switch, first map)."""
    display = Gdk.Display.get_default()
    if display is None:
        return
    seat = display.get_default_seat()
    if seat is None:
        return
    kb = seat.get_keyboard()
    if kb is not None:
        kb.connect("changed", lambda *_: callback())
