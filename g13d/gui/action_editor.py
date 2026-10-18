"""Dialog to edit what one control does. Keys are learned by pressing them."""
from __future__ import annotations

from collections.abc import Callable

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gtk  # noqa: E402

from g13d.config.model import Action  # noqa: E402
from g13d.hw.names import MOUSE_BUTTONS  # noqa: E402

from .keymap import MODIFIERS, evdev_name_from_keycode, key_label  # noqa: E402

TYPES = [("none", "Nothing"), ("key", "Keyboard key"), ("combo", "Key combination"), ("macro", "Macro"),
         ("mouse", "Mouse button"), ("mode", "Switch M mode"), ("profile", "Switch profile"), ("lcd_page", "LCD page")]


class ActionEditor(Adw.Dialog):
    def __init__(self, control: str, action: Action, macros: list[str], profiles: list[str], pages: list[str],
                 on_save: Callable[[Action], None], on_unassign: Callable[[], None] | None = None):
        super().__init__(title=control, content_width=480)
        self._on_save = on_save
        self._on_unassign = on_unassign
        self._macros, self._profiles = macros, profiles
        self._pages = ["next", "prev"] + [p for p in pages if p not in ("next", "prev")]
        self._keys: list[str] = list(action.keys)
        self._capturing = False
        self._chord_down: set[str] = set()

        view = Adw.ToolbarView()
        header = Adw.HeaderBar(show_end_title_buttons=False, show_start_title_buttons=False)
        cancel = Gtk.Button(label="Cancel")
        cancel.connect("clicked", lambda *_: self.close())
        save = Gtk.Button(label="Save", css_classes=["suggested-action"])
        save.connect("clicked", self._save)
        header.pack_start(cancel)
        header.pack_end(save)
        if on_unassign is not None:
            unassign = Gtk.Button(label="Unassign", css_classes=["destructive-action"], tooltip_text="Make this key do nothing")
            unassign.connect("clicked", lambda *_: (self.close(), on_unassign()))
            header.pack_end(unassign)
        view.add_top_bar(header)

        page = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=18, margin_top=12, margin_bottom=18,
                       margin_start=18, margin_end=18)
        group = Adw.PreferencesGroup()
        page.append(group)
        self._type = Adw.ComboRow(title="Action", model=Gtk.StringList.new([t[1] for t in TYPES]))
        self._type.set_selected(next(i for i, t in enumerate(TYPES) if t[0] == action.type))
        self._type.connect("notify::selected", lambda *_: self._show_type())
        group.add(self._type)

        self._stack = Gtk.Stack(vhomogeneous=False, hhomogeneous=True)
        page.append(self._stack)

        # key / combo
        kbox = Adw.PreferencesGroup()
        self._key_row = Adw.ActionRow(title="Key", subtitle="—", use_markup=False)
        self._learn = Gtk.ToggleButton(label="Press a key…", valign=Gtk.Align.CENTER)
        self._learn.connect("toggled", lambda b: self._start_capture() if b.get_active() else self._stop_capture())
        clear = Gtk.Button(icon_name="edit-clear-symbolic", valign=Gtk.Align.CENTER, tooltip_text="Clear")
        clear.connect("clicked", lambda *_: self._set_keys([]))
        self._key_row.add_suffix(self._learn)
        self._key_row.add_suffix(clear)
        kbox.add(self._key_row)
        self._key_hint = Gtk.Label(css_classes=["dim-label", "caption"], wrap=True, xalign=0, margin_top=6,
                                   label="Keys are stored by physical position, so what you press is what the G13 "
                                         "will send, whatever your layout. Esc can be assigned too: click the "
                                         "button again to stop listening.")
        kbox.add(self._key_hint)
        self._stack.add_named(kbox, "keys")

        self._macro = Adw.ComboRow(title="Macro", model=Gtk.StringList.new(macros or ["(no macro yet)"]))
        if action.type == "macro" and action.name in macros:
            self._macro.set_selected(macros.index(action.name))
        self._stack.add_named(self._wrap(self._macro), "macro")

        self._mouse = Adw.ComboRow(title="Button", model=Gtk.StringList.new([key_label(b) for b in MOUSE_BUTTONS]))
        if action.type == "mouse" and action.name in MOUSE_BUTTONS:
            self._mouse.set_selected(MOUSE_BUTTONS.index(action.name))
        self._stack.add_named(self._wrap(self._mouse), "mouse")

        self._mode = Adw.ComboRow(title="Mode", model=Gtk.StringList.new(["M1", "M2", "M3"]))
        if action.type == "mode":
            self._mode.set_selected(action.number - 1)
        self._stack.add_named(self._wrap(self._mode), "mode")

        self._profile = Adw.ComboRow(title="Profile", model=Gtk.StringList.new(profiles or ["(none)"]))
        if action.type == "profile" and action.name in profiles:
            self._profile.set_selected(profiles.index(action.name))
        self._stack.add_named(self._wrap(self._profile), "profile")

        self._page = Adw.ComboRow(title="Page", model=Gtk.StringList.new(self._pages))
        if action.type == "lcd_page" and action.name in self._pages:
            self._page.set_selected(self._pages.index(action.name))
        self._stack.add_named(self._wrap(self._page), "lcd_page")
        self._stack.add_named(Gtk.Label(label="This control will do nothing.", css_classes=["dim-label"]), "none")

        view.set_content(page)
        self.set_child(view)

        ctl = Gtk.EventControllerKey()
        ctl.set_propagation_phase(Gtk.PropagationPhase.CAPTURE)
        ctl.connect("key-pressed", self._on_key_pressed)
        ctl.connect("key-released", self._on_key_released)
        self.add_controller(ctl)

        self._set_keys(self._keys)
        self._show_type()

    @staticmethod
    def _wrap(row: Gtk.Widget) -> Gtk.Widget:
        g = Adw.PreferencesGroup()
        g.add(row)
        return g

    # ---- type switching -----------------------------------------------------
    def _current_type(self) -> str:
        return TYPES[self._type.get_selected()][0]

    def _show_type(self) -> None:
        t = self._current_type()
        if t in ("key", "combo"):
            self._stack.set_visible_child_name("keys")
            self._key_row.set_title("Key" if t == "key" else "Combination")
            self._learn.set_label("Press a key…" if t == "key" else "Press keys…")
            if t == "key" and len(self._keys) > 1:
                self._set_keys(self._keys[-1:])
        else:
            self._stack.set_visible_child_name(t)

    # ---- key capture ----------------------------------------------------------
    def _set_keys(self, keys: list[str]) -> None:
        self._keys = keys
        self._key_row.set_subtitle("+".join(key_label(k) for k in keys) if keys else "—")

    def _start_capture(self) -> None:
        self._capturing = True
        self._chord_down = set()
        if self._current_type() == "combo":
            self._set_keys([])   # a new recording replaces the previous combination
        self._learn.set_label("Listening… click to stop")
        self._learn.add_css_class("suggested-action")

    def _stop_capture(self) -> None:
        self._capturing = False
        self._learn.remove_css_class("suggested-action")
        if self._learn.get_active():
            self._learn.set_active(False)
        self._show_type()

    def _on_key_pressed(self, _ctl, keyval, keycode, state) -> bool:
        if not self._capturing:
            return False
        name = evdev_name_from_keycode(keycode)
        if name is None:
            return True
        if self._current_type() == "key":
            self._set_keys([name])
            self._stop_capture()
            return True
        # combo: collect modifiers, finish on the first non-modifier key
        if name not in self._keys:
            self._keys.append(name)
        self._chord_down.add(name)
        self._set_keys(self._keys)
        if name not in MODIFIERS:
            self._stop_capture()
        return True

    def _on_key_released(self, _ctl, keyval, keycode, state) -> None:
        if not self._capturing:
            return
        name = evdev_name_from_keycode(keycode)
        self._chord_down.discard(name)

    # ---- save -------------------------------------------------------------------
    def _save(self, *_: object) -> None:
        t = self._current_type()
        match t:
            case "none":
                action = Action.none()
            case "key":
                action = Action.key(self._keys[-1]) if self._keys else Action.none()
            case "combo":
                action = Action.combo(*self._keys) if self._keys else Action.none()
            case "macro":
                action = Action.macro(self._macros[self._macro.get_selected()]) if self._macros else Action.none()
            case "mouse":
                action = Action.mouse(MOUSE_BUTTONS[self._mouse.get_selected()])
            case "mode":
                action = Action.mode(self._mode.get_selected() + 1)
            case "profile":
                action = Action.profile(self._profiles[self._profile.get_selected()]) if self._profiles else Action.none()
            case _:
                action = Action.lcd_page(self._pages[self._page.get_selected()])
        self._on_save(action)
        self.close()
