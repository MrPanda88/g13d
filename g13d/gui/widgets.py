"""Small reusable widgets."""
from __future__ import annotations

from collections.abc import Callable

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gdk, Gio, GLib, Gtk  # noqa: E402


def focus_entry(entry: Gtk.Widget) -> None:
    """Give a dialog's text field the focus once the dialog is on screen (set_focus before present is lost)."""
    GLib.timeout_add(60, lambda: (entry.grab_focus(), False)[1])


def attach_key_menu(button: Gtk.Widget, on_edit: Callable[[], None], on_unassign: Callable[[], None],
                    has_action: Callable[[], bool]) -> None:
    """Right-click on a key: Edit… / Unassign (the latter only when the key does something)."""
    popover = Gtk.PopoverMenu(has_arrow=False)
    popover.set_parent(button)
    group = Gio.SimpleActionGroup()
    edit = Gio.SimpleAction.new("edit", None)
    edit.connect("activate", lambda *_: on_edit())
    unassign = Gio.SimpleAction.new("unassign", None)
    unassign.connect("activate", lambda *_: on_unassign())
    group.add_action(edit)
    group.add_action(unassign)
    button.insert_action_group("key", group)
    menu = Gio.Menu()
    menu.append("Edit…", "key.edit")
    menu.append("Unassign", "key.unassign")
    popover.set_menu_model(menu)

    def pressed(_g, _n, x, y):
        unassign.set_enabled(has_action())
        rect = Gdk.Rectangle()
        rect.x, rect.y, rect.width, rect.height = int(x), int(y), 1, 1
        popover.set_pointing_to(rect)
        popover.popup()
    click = Gtk.GestureClick(button=Gdk.BUTTON_SECONDARY)
    click.connect("pressed", pressed)
    button.add_controller(click)


class SliderRow(Adw.ActionRow):
    """A row with a slider (min/max marks) and an editable number sharing one adjustment."""

    def __init__(self, title: str, subtitle: str, lo: float, hi: float, step: float,
                 on_change: Callable[[float], None], digits: int = 0, unit: str = ""):
        super().__init__(title=title, subtitle=subtitle)
        self.set_title_lines(1)
        self.set_subtitle_lines(2)
        self._on_change = on_change
        self._adj = Gtk.Adjustment(lower=lo, upper=hi, step_increment=step, page_increment=step * 5, value=lo)
        # fixed length so every slider of a group lines up whatever its subtitle says
        scale = Gtk.Scale(orientation=Gtk.Orientation.HORIZONTAL, adjustment=self._adj, hexpand=False,
                          draw_value=False, width_request=320, valign=Gtk.Align.CENTER)
        fmt = f"{{:.{digits}f}}{unit}"
        scale.add_mark(lo, Gtk.PositionType.BOTTOM, fmt.format(lo))
        scale.add_mark(hi, Gtk.PositionType.BOTTOM, fmt.format(hi))
        spin = Gtk.SpinButton(adjustment=self._adj, digits=digits, valign=Gtk.Align.CENTER, width_chars=6)
        self.add_suffix(scale)
        self.add_suffix(spin)
        self._adj.connect("value-changed", lambda a: self._on_change(a.get_value()))

    @property
    def value(self) -> float:
        return self._adj.get_value()

    @value.setter
    def value(self, v: float) -> None:
        self._adj.set_value(v)


class WidePage(Gtk.ScrolledWindow):
    """Like Adw.PreferencesPage, but the content may grow up to `max_width` pixels."""

    def __init__(self, max_width: int = 1100):
        super().__init__(hscrollbar_policy=Gtk.PolicyType.NEVER, vexpand=True, hexpand=True)
        self._box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=24, margin_top=24, margin_bottom=24,
                            margin_start=18, margin_end=18)
        self.set_child(Adw.Clamp(maximum_size=max_width, tightening_threshold=max_width - 200, child=self._box))

    def add(self, widget: Gtk.Widget) -> None:
        self._box.append(widget)
