"""Layout-aware labels for evdev key names, and hardware keycode -> evdev name (GTK events)."""
from __future__ import annotations

import gi

gi.require_version("Gdk", "4.0")
from evdev import ecodes  # noqa: E402
from gi.repository import Gdk  # noqa: E402

from g13d.config.model import Action  # noqa: E402
from g13d.hw.names import KEY_LABELS as NICE  # noqa: E402
from g13d.hw.names import MODIFIERS  # noqa: E402,F401  (re-exported)

XKB_OFFSET = 8


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
