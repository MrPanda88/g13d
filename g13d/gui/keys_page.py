"""Keys tab: a clickable picture of the G13 showing the bindings of the selected mode."""
from __future__ import annotations

from collections.abc import Callable

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gtk  # noqa: E402

from g13d.config.model import Action, Profile  # noqa: E402

from .dnd import make_action_target  # noqa: E402
from .keymap import action_label  # noqa: E402
from .widgets import attach_key_menu  # noqa: E402

# (control, column, row, colspan) on a 14-column grid (one key = 2 columns, rows offset by 1 column)
_LAYOUT: list[tuple[str, int, int, int]] = []
for i in range(7):
    _LAYOUT.append((f"G{i + 1}", i * 2, 0, 2))
for i in range(7):
    _LAYOUT.append((f"G{i + 8}", i * 2, 1, 2))
for i in range(5):
    _LAYOUT.append((f"G{i + 15}", i * 2 + 1, 2, 2))
for i in range(3):
    _LAYOUT.append((f"G{i + 20}", i * 2 + 2, 3, 2))

_STICK = [("STICK_UP", 1, 0), ("STICK_LEFT", 0, 1), ("STICK_PRESS", 1, 1), ("STICK_RIGHT", 2, 1),
          ("STICK_DOWN", 1, 2), ("STICK_BTN_LEFT", 0, 3), ("STICK_BTN_DOWN", 1, 3)]
_STICK_TITLES = {"STICK_UP": "Up", "STICK_DOWN": "Down", "STICK_LEFT": "Left", "STICK_RIGHT": "Right",
                 "STICK_PRESS": "Click", "STICK_BTN_LEFT": "Side", "STICK_BTN_DOWN": "Bottom"}
_LCD_TITLES = {"LCD_MENU": "●", "LCD1": "LCD 1", "LCD2": "LCD 2", "LCD3": "LCD 3", "LCD4": "LCD 4"}


class KeyButton(Gtk.Button):
    def __init__(self, control: str, title: str, on_click: Callable[[str], None], chars: int = 5,
                 on_drop: Callable[[str, Action], bool] | None = None,
                 on_unassign: Callable[[str], None] | None = None):
        super().__init__()
        self.control = control
        self._bound = False
        if on_drop is not None:
            make_action_target(self, lambda a: on_drop(control, a))
        if on_unassign is not None:
            attach_key_menu(self, lambda: on_click(control), lambda: on_unassign(control), lambda: self._bound)
        self.add_css_class("g13-key")
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2, valign=Gtk.Align.CENTER)
        self._title = Gtk.Label(label=title, css_classes=["caption", "dim-label"], ellipsize=3,
                                width_chars=chars, max_width_chars=chars)
        # width_chars == max_width_chars pins the natural width: every key keeps the same size
        # whatever its label says; long labels wrap on two lines, then get an ellipsis.
        self._action = Gtk.Label(label="—", ellipsize=3, wrap=True, lines=2, width_chars=chars, max_width_chars=chars,
                                 justify=Gtk.Justification.CENTER, css_classes=["heading"])
        box.append(self._title)
        box.append(self._action)
        self.set_child(box)
        self.connect("clicked", lambda *_: on_click(control))

    def set_action(self, action: Action, label: str | None = None) -> None:
        self._action.set_label(label if label is not None else action_label(action))
        shown, plain = action_label(action), action.describe()
        self._action.set_tooltip_text(shown + (f" ({plain})" if plain != shown else ""))
        self._bound = action.type != "none"
        if action.type == "none":
            self._action.add_css_class("dim-label")
            self.remove_css_class("g13-bound")
        else:
            self._action.remove_css_class("dim-label")
            self.add_css_class("g13-bound")

    def set_pressed(self, pressed: bool) -> None:
        if pressed:
            self.add_css_class("g13-pressed")
        else:
            self.remove_css_class("g13-pressed")


class KeysPage(Gtk.Box):
    def __init__(self, on_edit: Callable[[str], None], on_mode: Callable[[int], None],
                 on_drop: Callable[[str, Action], bool] | None = None,
                 label_for: Callable[[Action], str] = action_label,
                 on_unassign: Callable[[str], None] | None = None):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=12, margin_top=12, margin_bottom=12,
                         margin_start=12, margin_end=12)
        self._on_edit = on_edit
        self._on_drop = on_drop
        self._on_unassign = on_unassign
        self._label_for = label_for
        self._buttons: dict[str, KeyButton] = {}
        self._profile: Profile | None = None
        self._mode = 1

        # Mode selector
        top = Gtk.Box(spacing=12, halign=Gtk.Align.CENTER)
        self._modes = Adw.ToggleGroup(homogeneous=True)
        for m in (1, 2, 3):
            self._modes.add(Adw.Toggle(label=f"M{m}", name=str(m)))
        self._modes.connect("notify::active-name", lambda g, _p: on_mode(int(g.get_active_name() or 1)))
        top.append(self._modes)
        self.append(top)
        self._hint = Gtk.Label(label="Click a key to change what it does. Keys light up when pressed on the device.",
                               css_classes=["dim-label", "caption"], wrap=True, justify=Gtk.Justification.CENTER)
        self.append(self._hint)

        frame = Gtk.Frame()
        frame.add_css_class("g13-body")
        body = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10, margin_top=12, margin_bottom=12,
                       margin_start=12, margin_end=12)
        frame.set_child(body)

        # LCD strip
        lcd = Gtk.Box(spacing=6, halign=Gtk.Align.CENTER)
        screen = Gtk.Label(label="LCD 160×43", css_classes=["g13-lcd"], width_request=240, height_request=52)
        lcd_row = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        lcd_row.append(screen)
        btns = Gtk.Box(spacing=6, halign=Gtk.Align.CENTER)
        for c in ("LCD_MENU", "LCD1", "LCD2", "LCD3", "LCD4"):
            b = self._make(c, _LCD_TITLES[c], chars=5)
            b.add_css_class("g13-small")
            btns.append(b)
        lcd_row.append(btns)
        lcd.append(lcd_row)
        body.append(lcd)

        # Keypad + stick
        main = Gtk.Box(spacing=18, halign=Gtk.Align.CENTER)
        grid = Gtk.Grid(column_spacing=4, row_spacing=4, column_homogeneous=True, hexpand=True)
        for control, col, row, span in _LAYOUT:
            grid.attach(self._make(control, control), col, row, span, 1)
        main.append(grid)
        stick = Gtk.Grid(column_spacing=4, row_spacing=4, valign=Gtk.Align.END)
        for control, col, row in _STICK:
            b = self._make(control, _STICK_TITLES[control], chars=5)
            b.add_css_class("g13-small")
            stick.attach(b, col, row, 1, 1)
        stick_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        stick_box.append(Gtk.Label(label="Thumbstick", css_classes=["caption", "dim-label"]))
        stick_box.append(stick)
        main.append(stick_box)
        body.append(main)
        self.append(Adw.Clamp(maximum_size=1100, tightening_threshold=900, child=frame))

    def _make(self, control: str, title: str, chars: int = 5) -> KeyButton:
        b = KeyButton(control, title, self._on_edit, chars, self._on_drop, self._on_unassign)
        self._buttons[control] = b
        return b

    # ---- state --------------------------------------------------------------
    def set_profile(self, profile: Profile | None) -> None:
        self._profile = profile
        self.refresh()

    def set_mode(self, mode: int) -> None:
        self._mode = mode
        if self._modes.get_active_name() != str(mode):
            self._modes.set_active_name(str(mode))
        self.refresh()

    def refresh(self) -> None:
        for control, b in self._buttons.items():
            action = self._profile.binding(self._mode, control) if self._profile else Action.none()
            b.set_action(action, self._label_for(action))

    def set_pressed(self, control: str, pressed: bool) -> None:
        b = self._buttons.get(control)
        if b is not None:
            b.set_pressed(pressed)
