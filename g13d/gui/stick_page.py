"""Thumbstick tab."""
from __future__ import annotations

from collections.abc import Callable

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gtk  # noqa: E402

from g13d.config.model import STICK_MODES, Profile  # noqa: E402

from .widgets import SliderRow, WidePage  # noqa: E402

_MODE_LABELS = {"keys": "Keys", "mouse": "Mouse pointer", "scroll": "Scroll wheel", "passthrough": "Passthrough"}
_MODE_HELP = {"keys": "The four directions act as keys: bind them in the Keys tab (Up, Down, Left, Right).",
              "mouse": "Moves the pointer. Speed grows with the deflection.",
              "scroll": "Turns the stick into a scroll wheel (vertical and horizontal).",
              "passthrough": "Leaves the stick alone: games and Steam see it as a joystick."}


class StickPage(WidePage):
    def __init__(self, on_change: Callable[[], None]):
        super().__init__()
        self._on_change = on_change
        self._profile: Profile | None = None
        self._updating = False

        g = Adw.PreferencesGroup(title="Thumbstick", description="How the analog stick behaves in this profile.")
        self.add(g)
        self._mode = Adw.ComboRow(title="Mode", model=Gtk.StringList.new([_MODE_LABELS[m] for m in STICK_MODES]))
        self._mode.connect("notify::selected", self._changed)
        g.add(self._mode)
        self._help = Gtk.Label(css_classes=["dim-label", "caption"], wrap=True, xalign=0, margin_top=6)
        g.add(self._help)

        t = Adw.PreferencesGroup(title="Tuning")
        self.add(t)
        self._dead = SliderRow("Dead zone", "Travel ignored around the centre", 0, 90, 5, self._changed, unit="%")
        self._speed = SliderRow("Pointer speed", "Pixels per second at full deflection (mouse mode)", 50, 4000, 50, self._changed)
        self._scroll = SliderRow("Scroll speed", "Wheel ticks per second at full deflection (scroll mode)", 1, 60, 1, self._changed)
        for r in (self._dead, self._speed, self._scroll):
            t.add(r)
        self._invert = Adw.SwitchRow(title="Invert vertical axis")
        self._invert.connect("notify::active", self._changed)
        t.add(self._invert)

    def set_profile(self, profile: Profile | None) -> None:
        self._profile = profile
        if profile is None:
            return
        self._updating = True
        s = profile.stick
        self._mode.set_selected(STICK_MODES.index(s.mode) if s.mode in STICK_MODES else 0)
        self._dead.value = round(s.deadzone * 100)
        self._speed.value = s.mouse_speed
        self._scroll.value = s.scroll_speed
        self._invert.set_active(s.invert_y)
        self._help.set_label(_MODE_HELP[s.mode])
        self._updating = False

    def _changed(self, *_: object) -> None:
        if self._updating or self._profile is None:
            return
        s = self._profile.stick
        s.mode = STICK_MODES[self._mode.get_selected()]
        s.deadzone = self._dead.value / 100
        s.mouse_speed = float(self._speed.value)
        s.scroll_speed = float(self._scroll.value)
        s.invert_y = self._invert.get_active()
        self._help.set_label(_MODE_HELP[s.mode])
        self._on_change()
