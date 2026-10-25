"""Macro editing: MacroEditor (one macro, LGS-style recording: type keys while the window has focus), shown in
place of the G13 picture in the lgs layout, and MacrosPage (list + editor), the Macros tab of the gtk layout."""
from __future__ import annotations

import time
from collections.abc import Callable

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
gi.require_version("Graphene", "1.0")
from gi.repository import Adw, Gdk, Gio, GLib, Graphene, Gtk  # noqa: E402

from g13d.config.scope import ProfileScope  # noqa: E402
from g13d.config.macro import MAX_COUNT, REPEAT_MODES, Macro, Step  # noqa: E402
from g13d.config.macro_edit import History, partner, replace_key  # noqa: E402
from g13d.config.model import MACRO_STYLES  # noqa: E402
from g13d.engine.recorder import MacroRecorder  # noqa: E402
from g13d.hw.names import MOUSE_BUTTONS  # noqa: E402

from . import macro_steps  # noqa: E402
from .keymap import evdev_name_from_keycode, key_label  # noqa: E402
from .widgets import WidePage, info_button, text_row  # noqa: E402

_REPEAT_LABELS = {"once": "Once", "while_held": "While held", "toggle": "Toggle", "count": "A number of times"}
_REPEAT_HELP = {"once": "Plays the whole macro each time the key is pressed.",
                "while_held": "Repeats while the key is held; the current pass always completes.",
                "toggle": "One press starts repeating, the next press stops.",
                "count": "One press plays the macro {n} times in a row. Pressing the key again while it plays "
                         "stops it at once, like Toggle."}
# (kind, old name, new name or None when deleted, macro is global: every profile is concerned, else the selected one)
Retarget = Callable[[str, str, str | None, bool], None]


def unique_macro_name(base: str, taken) -> str:
    name, i = base, 2
    while name in taken:
        name, i = f"{base} {i}", i + 1
    return name


def confirm_delete_macro(parent: Gtk.Widget, name: str, on_delete: Callable[[], None]) -> None:
    dlg = Adw.AlertDialog(heading=f"Delete “{name}”?", body="Keys bound to this macro will be unbound.")
    dlg.add_response("cancel", "Cancel")
    dlg.add_response("delete", "Delete")
    dlg.set_response_appearance("delete", Adw.ResponseAppearance.DESTRUCTIVE)
    dlg.connect("response", lambda _d, resp: resp == "delete" and on_delete())
    dlg.present(parent.get_root())


class MacroEditor(WidePage):
    """Edits one macro (edit()). on_saved(renamed) runs after every save; a rename has already been retargeted.
    `style` is the look of the steps (macro_steps), on_style(style) saves the user's choice. Macros are read and
    saved through `store`, the selected profile's scope (its own macros and the global ones)."""

    def __init__(self, store: ProfileScope, client, toast: Callable[[str], None], on_saved: Callable[[bool], None],
                 retarget: Retarget, style: str = "flow", on_style: Callable[[str], None] | None = None):
        super().__init__()
        self._store = store
        self._client = client
        self._toast = toast
        self._on_saved = on_saved
        self._retarget = retarget
        self._style = style if style in MACRO_STYLES else "flow"
        self._on_style = on_style
        self._current: Macro | None = None
        self._updating = False
        self._recorder = MacroRecorder()
        self._before_record: list[Step] = []
        self._save_timer = 0
        self._pending_kind: str | None = None          # "Add step": waiting for the key to tap / press / release
        self._pending_key: int | None = None           # keycap clicked: waiting for the step's new key
        self._insert_at: int | None = None             # where new steps go (None: at the end); right-click a step
        self._history = History()

        g = Adw.PreferencesGroup()
        self.add(g)
        # Text fields are applied on Enter, on the check button or when the field loses focus
        # (same behaviour everywhere; renaming live would also rebuild the list under the cursor).
        self._name = text_row("Name", self._apply_name)
        g.add(self._name)
        self._desc = text_row("Description", self._apply_description)
        g.add(self._desc)
        self._repeat = Adw.ComboRow(title="Playback", model=Gtk.StringList.new([_REPEAT_LABELS[m] for m in REPEAT_MODES]))
        self._repeat.connect("notify::selected", self._field_changed)
        g.add(self._repeat)
        self._count = Adw.SpinRow.new_with_range(1, MAX_COUNT, 1)
        self._count.set_title("Number of plays")
        self._count.connect("notify::value", self._field_changed)
        g.add(self._count)
        self._rdelay = Adw.SpinRow.new_with_range(0, 10000, 10)
        self._rdelay.set_title("Pause between repeats")
        self._rdelay.set_subtitle("Milliseconds")
        self._rdelay.connect("notify::value", self._field_changed)
        g.add(self._rdelay)
        self._repeat_help = Gtk.Label(css_classes=["dim-label", "caption"], wrap=True, xalign=0, margin_top=4)
        g.add(self._repeat_help)

        sg = Adw.PreferencesGroup(title="Steps")
        self.add(sg)
        # the look of the list, apart from the actions on the steps
        look = Gtk.Box(spacing=6, valign=Gtk.Align.CENTER)
        look.append(Gtk.Label(label="Style", css_classes=["dim-label"]))
        self._style_menu = Gtk.DropDown.new_from_strings(list(macro_steps.STYLE_LABELS.values()))
        self._style_menu.set_selected(MACRO_STYLES.index(self._style))
        self._style_menu.connect("notify::selected", self._style_changed)
        look.append(self._style_menu)
        sg.set_header_suffix(look)
        self._timeline = macro_steps.Timeline()
        sg.add(self._timeline)

        # groups of buttons that wrap as units when the window is narrow (a single row forced the window's width)
        tools = Adw.WrapBox(child_spacing=18, line_spacing=6, margin_bottom=6)
        record = Gtk.Box(spacing=6)
        steps = Gtk.Box(spacing=6)
        history = Gtk.Box(spacing=0)
        self._record = Gtk.ToggleButton()
        self._record.set_child(self._btn_content("media-record-symbolic", "Record"))
        self._record.add_css_class("destructive-action")
        self._record.connect("toggled", self._toggle_record)
        record.append(self._record)
        self._delays = Gtk.CheckButton(label="With delays", active=True, valign=Gtk.Align.CENTER)
        record.append(self._delays)
        self._replace = Gtk.CheckButton(label="Replace steps", active=True, valign=Gtk.Align.CENTER)
        self._replace.connect("toggled", lambda *_: self._update_record_tooltip())
        record.append(self._replace)
        record.append(info_button("On: a recording replaces all the steps.\nOff: it is added to them, at the end, or "
                                 "at the mark when you chose Insert before / after (right-click a step)."))
        self._add_menu = self._add_step_button()
        steps.append(self._add_menu)
        steps.append(macro_steps.simplify_menu(lambda: self._current.steps if self._current else None,
                                            lambda steps: self._change(steps)))
        clear = Gtk.Button(label="Clear", tooltip_text="Remove all steps")
        clear.connect("clicked", lambda *_: self._clear())
        steps.append(clear)
        self._undo = Gtk.Button(icon_name="edit-undo-symbolic", tooltip_text="Undo (Ctrl+Z)", css_classes=["flat"])
        self._undo.connect("clicked", lambda *_: self._undo_redo(redo=False))
        history.append(self._undo)
        self._redo = Gtk.Button(icon_name="edit-redo-symbolic", tooltip_text="Redo (Ctrl+Shift+Z)", css_classes=["flat"])
        self._redo.connect("clicked", lambda *_: self._undo_redo(redo=True))
        history.append(self._redo)
        play = Gtk.Button(tooltip_text="Play on the device now")
        play.set_child(self._btn_content("media-playback-start-symbolic", "Play"))
        play.connect("clicked", lambda *_: self._play())
        for group in (record, steps, history, play):
            tools.append(group)
        sg.add(tools)

        # what a click does, right above the list it is about
        hint = Gtk.Box(spacing=8, margin_top=4, margin_bottom=6)
        self._list_hint = Gtk.Label(css_classes=["dim-label", "caption"], wrap=True, xalign=0, hexpand=True)
        hint.append(self._list_hint)
        self._at_end = Gtk.Button(label="Add at the end instead", css_classes=["flat", "caption"], visible=False)
        self._at_end.connect("clicked", lambda *_: self._set_insert_point(None))
        hint.append(self._at_end)
        self._list_hint_box = hint
        sg.add(hint)
        hint_box = Gtk.Box(spacing=8, margin_bottom=6, halign=Gtk.Align.CENTER)
        self._capture_hint = Gtk.Label(css_classes=["accent", "caption"], wrap=True)
        self._capture_cancel = Gtk.Button(label="Cancel", css_classes=["flat"])
        self._capture_cancel.connect("clicked", lambda *_: self._cancel_capture())
        hint_box.append(self._capture_hint)
        hint_box.append(self._capture_cancel)
        self._hint_box = hint_box
        hint_box.set_visible(False)
        sg.add(hint_box)
        self._steps = Gtk.ListBox(css_classes=["boxed-list"], selection_mode=Gtk.SelectionMode.NONE)
        # the right-click menu lives on a box around the list: the list's rows are replaced on every change
        steps_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        steps_box.append(self._steps)
        sg.add(steps_box)
        self._row_menu_index = 0
        self._row_menu = Gtk.PopoverMenu(has_arrow=False)
        self._row_menu.set_parent(steps_box)
        menu = Gio.Menu()
        menu.append("Insert before…", "step.before")
        menu.append("Insert after…", "step.after")
        section = Gio.Menu()
        section.append("Remove", "step.remove")
        menu.append_section(None, section)
        self._row_menu.set_menu_model(menu)
        group = Gio.SimpleActionGroup()
        for name, cb in (("before", lambda: self._insert_here(self._row_menu_index)),
                         ("after", lambda: self._insert_here(self._row_menu_index + 1)),
                         ("remove", lambda: self._remove(self._row_menu_index))):
            a = Gio.SimpleAction.new(name, None)
            a.connect("activate", lambda _a, _p, f=cb: f())
            group.add_action(a)
        steps_box.insert_action_group("step", group)
        click = Gtk.GestureClick(button=Gdk.BUTTON_SECONDARY)
        click.connect("pressed", self._on_step_right_click)
        self._steps.add_controller(click)
        self._empty = Gtk.Label(label="No steps yet. Press Record and type, or add steps by hand.",
                                css_classes=["dim-label"], margin_top=12)
        sg.add(self._empty)

        ctl = Gtk.EventControllerKey()
        ctl.set_propagation_phase(Gtk.PropagationPhase.CAPTURE)
        ctl.connect("key-pressed", self._on_key)
        ctl.connect("key-released", self._on_key_release)
        self._key_ctl = ctl
        shortcuts = Gtk.ShortcutController()
        for trigger, redo in (("<Control>z", False), ("<Control><Shift>z", True), ("<Control>y", True)):
            shortcuts.add_shortcut(Gtk.Shortcut.new(Gtk.ShortcutTrigger.parse_string(trigger),
                                                    Gtk.CallbackAction.new(lambda *_a, r=redo: (self._undo_redo(r), True)[1])))
        self.add_controller(shortcuts)
        self._update_record_tooltip()
        self.edit(None)

    @staticmethod
    def _btn_content(icon: str, label: str) -> Gtk.Widget:
        box = Gtk.Box(spacing=6)
        box.append(Gtk.Image.new_from_icon_name(icon))
        box.append(Gtk.Label(label=label))
        return box

    def _add_step_button(self) -> Gtk.MenuButton:
        menu = Gtk.MenuButton(label="Add step", tooltip_text="Add a step by hand")
        pop = Gtk.Popover()
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4, margin_top=6, margin_bottom=6, margin_start=6, margin_end=6)
        box.append(Gtk.Label(label="Keyboard", css_classes=["caption", "dim-label"], xalign=0))
        for kind, label in (("tap", "Tap a key…"), ("press", "Press a key…"), ("release", "Release a key…")):
            b = Gtk.Button(label=label, css_classes=["flat"], halign=Gtk.Align.FILL)
            b.get_child().set_xalign(0)
            b.connect("clicked", lambda _b, k=kind: (pop.popdown(), self._add_key_step(k)))
            box.append(b)
        wait = Gtk.Button(label="Wait 100 ms", css_classes=["flat"])
        wait.get_child().set_xalign(0)
        wait.connect("clicked", lambda *_: (pop.popdown(), self._insert([Step.delay(100)])))
        box.append(wait)
        box.append(Gtk.Separator(margin_top=4, margin_bottom=4))
        box.append(Gtk.Label(label="Mouse", css_classes=["caption", "dim-label"], xalign=0))
        self._mouse_btn = Gtk.DropDown.new_from_strings([key_label(b) for b in MOUSE_BUTTONS])
        box.append(self._mouse_btn)
        row = Gtk.Box(spacing=4, homogeneous=True)
        for kind, label in (("tap", "Click"), ("press", "Press"), ("release", "Release")):
            b = Gtk.Button(label=label)
            b.connect("clicked", lambda _b, k=kind: (pop.popdown(), self._insert([Step(k, MOUSE_BUTTONS[self._mouse_btn.get_selected()])])))
            row.append(b)
        box.append(row)
        pop.set_child(box)
        menu.set_popover(pop)
        return menu

    def attach_window_controller(self, window: Gtk.Window) -> None:
        window.add_controller(self._key_ctl)

    def detach_window_controller(self, window: Gtk.Window) -> None:
        window.remove_controller(self._key_ctl)

    def _update_record_tooltip(self) -> None:
        where = "replaces the steps" if self._replace.get_active() else (
            "inserted at the mark" if self._insert_at is not None else "added after the steps")
        self._record.set_tooltip_text(f"Record keys typed in this window ({where})")

    def _style_changed(self, *_: object) -> None:
        self._style = MACRO_STYLES[self._style_menu.get_selected()]
        self._render_steps()
        if self._on_style is not None:
            self._on_style(self._style)

    @property
    def current(self) -> Macro | None:
        return self._current

    def focus_name(self) -> None:
        GLib.timeout_add(60, lambda: (self._name.grab_focus(), False)[1])

    def edit(self, macro: Macro | None) -> None:
        """Edit `macro` (None: nothing, insensitive). A recording in progress stops, pending changes are saved."""
        self._stop_record()
        self._cancel_capture()
        if self._save_timer:
            GLib.source_remove(self._save_timer)
            self._do_save()
        self._current = macro
        self._insert_at = None
        self._history.reset()
        self.set_sensitive(macro is not None)
        self._updating = True
        self._name.remove_css_class("error")
        self._name.set_text(macro.name if macro else "")
        self._desc.set_text(macro.description if macro else "")
        self._repeat.set_selected(REPEAT_MODES.index(macro.repeat) if macro and macro.repeat in REPEAT_MODES else 0)
        self._count.set_value(macro.repeat_count if macro else 2)
        self._rdelay.set_value(macro.repeat_delay_ms if macro else 0)
        self._updating = False
        self._show_repeat()
        self._render_steps()

    # ---- editing ----------------------------------------------------------------
    def _apply_name(self) -> None:
        if self._updating or self._current is None:
            return
        m = self._current
        new_name = self._name.get_text().strip()
        if not new_name or new_name == m.name:
            self._name.remove_css_class("error")
            if not new_name:
                self._name.set_text(m.name)
            return
        if new_name in self._store.load_macros():
            self._name.add_css_class("error")
            self._toast(f"A macro named “{new_name}” already exists")
            return
        self._name.remove_css_class("error")
        old = m.name
        is_global = self._store.is_global_macro(old)
        m.name = new_name
        self._store.rename_macro(old, m)
        self._retarget("macro", old, new_name, is_global)
        self._do_save(renamed=True)

    def _apply_description(self) -> None:
        if self._updating or self._current is None:
            return
        text = self._desc.get_text().strip()
        if text != self._current.description:
            self._current.description = text
            self._do_save()

    def _field_changed(self, *_: object) -> None:
        if self._updating or self._current is None:
            return
        m = self._current
        m.repeat = REPEAT_MODES[self._repeat.get_selected()]
        m.repeat_count = int(self._count.get_value())
        m.repeat_delay_ms = int(self._rdelay.get_value())
        self._show_repeat()
        self._schedule_save()

    def _show_repeat(self) -> None:
        """Only the settings of the chosen playback mode, and what it does."""
        m = self._current
        repeat = m.repeat if m else "once"
        self._count.set_visible(repeat == "count")
        self._rdelay.set_visible(repeat != "once")
        help_ = _REPEAT_HELP[repeat]
        if repeat == "count":
            help_ = help_.format(n=m.repeat_count if m else 2)
        self._repeat_help.set_label(help_ if m else "")

    def _schedule_save(self) -> None:
        if self._save_timer:
            GLib.source_remove(self._save_timer)
        self._save_timer = GLib.timeout_add(400, self._do_save)

    def _do_save(self, renamed: bool = False) -> bool:
        self._save_timer = 0
        if self._current is not None:
            self._store.save_macro(self._current)
            self._on_saved(renamed)
        return False

    def refresh_labels(self) -> None:
        self._render_steps()

    # ---- steps ------------------------------------------------------------------
    def _change(self, steps: list[Step], tag: object = None, render: bool = True) -> None:
        """Every change of the steps goes through here: undo history, redraw, save."""
        if self._current is None or steps == self._current.steps:
            return
        self._history.push(self._current.steps, tag)
        self._current.steps = steps
        if self._insert_at is not None:
            self._insert_at = min(self._insert_at, len(steps))
        if render:
            self._render_steps()
        else:
            self._timeline.set_steps(steps)
            self._update_history_buttons()
        self._schedule_save()

    def _undo_redo(self, redo: bool) -> None:
        if self._current is None or self._recorder.recording:
            return
        steps = (self._history.redo if redo else self._history.undo)(self._current.steps)
        if steps is None:
            return
        self._current.steps = steps
        if self._insert_at is not None:
            self._insert_at = min(self._insert_at, len(steps))
        self._render_steps()
        self._schedule_save()

    def _update_history_buttons(self) -> None:
        self._undo.set_sensitive(self._history.can_undo)
        self._redo.set_sensitive(self._history.can_redo)

    def _render_steps(self) -> None:
        steps = self._current.steps if self._current else []
        self._empty.set_visible(not steps)
        self._timeline.set_visible(self._style == "timeline" and bool(steps))
        self._timeline.set_steps(steps)
        macro_steps.render(self._steps, steps, macro_steps.Callbacks(self._move, self._remove, self._set_delay,
                                                                     self._ask_key), self._style)
        if self._insert_at is not None and steps:
            # the mark: under the step before the insertion point, or over the first step
            p = self._insert_at
            row = self._steps.get_row_at_index(p - 1 if p else 0)
            if row is not None:
                row.add_css_class("g13-insert-after" if p else "g13-insert-before")
        self._update_list_hint()
        self._update_history_buttons()
        self._update_record_tooltip()

    def _update_list_hint(self) -> None:
        steps = self._current.steps if self._current else []
        self._list_hint_box.set_visible(bool(steps))
        p = self._insert_at
        self._at_end.set_visible(p is not None)
        if p is None:
            self._list_hint.set_label("Drag to reorder. Right-click a step to insert before or after it, click a key "
                                      "to change it.")
            self._list_hint.remove_css_class("accent")
            return
        where = ("before the first step" if p == 0 else "after the last step" if p >= len(steps)
                 else f"between steps {p} and {p + 1}")
        self._list_hint.set_label(f"New steps (Add step, Record) go {where}, at the mark.")
        self._list_hint.add_css_class("accent")

    def _on_step_right_click(self, _g, _n, x, y) -> None:
        row = self._steps.get_row_at_y(int(y))
        if row is None or self._recorder.recording:
            return
        self._row_menu_index = row.get_index()
        ok, pt = self._steps.compute_point(self._row_menu.get_parent(), Graphene.Point().init(x, y))
        rect = Gdk.Rectangle()
        rect.x, rect.y, rect.width, rect.height = int(pt.x if ok else x), int(pt.y if ok else y), 1, 1
        self._row_menu.set_pointing_to(rect)
        self._row_menu.popup()

    def _set_insert_point(self, at: int | None) -> None:
        self._insert_at = at
        self._render_steps()

    def _insert_here(self, at: int) -> None:
        """Insert before / after from the menu: mark the place, then offer what to add there."""
        self._set_insert_point(at)
        self._add_menu.popup()

    def _insert(self, new: list[Step]) -> None:
        """Insert at the mark (which then moves after the new steps), or append."""
        if self._current is None or not new:
            return
        steps = list(self._current.steps)
        at = len(steps) if self._insert_at is None else self._insert_at
        steps[at:at] = new
        if self._insert_at is not None:
            self._insert_at = at + len(new)         # the next ones follow
        self._change(steps)

    def _move(self, src: int, dest: int) -> None:
        if self._current is None:
            return
        s = list(self._current.steps)
        if 0 <= src < len(s) and 0 <= dest < len(s) and src != dest:
            s.insert(dest, s.pop(src))
            self._change(s)

    def _remove(self, i: int) -> None:
        if self._current is None:
            return
        s = list(self._current.steps)
        del s[i]
        if self._insert_at is not None and i < self._insert_at:
            self._insert_at -= 1
        self._change(s)

    def _set_delay(self, i: int, ms: int) -> None:
        if self._current is None:
            return
        s = list(self._current.steps)
        s[i] = Step.delay(ms)
        self._change(s, tag=("delay", i), render=False)    # one undo entry for one spin

    def _clear(self) -> None:
        if self._current is None or not self._current.steps:
            return
        dlg = Adw.AlertDialog(heading="Remove all steps?", body=f"“{self._current.name}” will be empty (Undo brings them back).")
        dlg.add_response("cancel", "Cancel")
        dlg.add_response("clear", "Clear")
        dlg.set_response_appearance("clear", Adw.ResponseAppearance.DESTRUCTIVE)

        def on_resp(_d, resp):
            if resp == "clear":
                self._insert_at = None
                self._change([])
        dlg.connect("response", on_resp)
        dlg.present(self.get_root())

    def _play(self) -> None:
        if self._current is not None:
            self._do_save()
            self._client.run_macro(self._current.name)

    def _add_key_step(self, kind: str) -> None:
        if self._current is None:
            return
        self._pending_key = None
        self._pending_kind = kind
        self._capture_hint.set_label(f"Press the key to {kind} (Esc is allowed)…")
        self._hint_box.set_visible(True)

    def _ask_key(self, i: int) -> None:
        """Keycap clicked: the next key typed replaces it (and its press / release partner)."""
        if self._current is None or self._recorder.recording:
            return
        self._pending_kind = None
        self._pending_key = i
        step = self._current.steps[i]
        both = partner(self._current.steps, i) is not None
        self._capture_hint.set_label(f"Press the new key for step {i + 1} ({key_label(step.key)})"
                                     + (", its press and release both change…" if both else "…"))
        self._hint_box.set_visible(True)

    def _cancel_capture(self) -> None:
        self._pending_kind = None
        self._pending_key = None
        if not self._recorder.recording:
            self._hint_box.set_visible(False)

    # ---- recording ----------------------------------------------------------------
    def _toggle_record(self, btn: Gtk.ToggleButton) -> None:
        if btn.get_active():
            if self._current is None:
                btn.set_active(False)
                return
            self._cancel_capture()
            self._before_record = list(self._current.steps)
            if self._replace.get_active():
                self._current.steps = []
                self._render_steps()
            self._recorder.record_delays = self._delays.get_active()
            self._recorder.start()
            self._client.set_recording(True)
            self._capture_hint.set_label("Recording… type the keys, then press Record again or MR on the G13.")
            self._capture_cancel.set_visible(False)
            self._hint_box.set_visible(True)
        else:
            self._stop_record()

    def _stop_record(self) -> None:
        if not self._recorder.recording:
            return
        steps = MacroRecorder.simplify(self._recorder.stop())
        self._client.set_recording(False)
        self._hint_box.set_visible(False)
        self._capture_cancel.set_visible(True)
        if self._record.get_active():
            self._record.set_active(False)
        if self._current is None:
            return
        self._current.steps = self._before_record      # the change below is one undo step from here
        if not steps:
            self._render_steps()                       # nothing typed: keep the old steps
        elif self._replace.get_active():
            self._insert_at = None
            self._change(steps)
        else:
            self._insert(steps)

    def toggle_record_from_device(self) -> None:
        """MR pressed on the G13 while the GUI is open."""
        if self.get_mapped() and self._current is not None:
            self._record.set_active(not self._record.get_active())

    def _on_key(self, _ctl, keyval, keycode, state) -> bool:
        if not self.get_mapped():
            return False
        name = evdev_name_from_keycode(keycode)
        if self._pending_kind is not None or self._pending_key is not None:
            if name is not None and self._current is not None:
                if self._pending_key is not None:
                    self._change(replace_key(self._current.steps, self._pending_key, name))
                else:
                    self._insert([Step(self._pending_kind, name)])
            self._cancel_capture()
            return True
        if self._recorder.recording:
            if name is not None:
                self._recorder.event(name, True, time.monotonic())
                self._live_steps()
            return True
        return False

    def _on_key_release(self, _ctl, keyval, keycode, state) -> None:
        if self._recorder.recording and self.get_mapped():
            name = evdev_name_from_keycode(keycode)
            if name is not None:
                self._recorder.event(name, False, time.monotonic())
                self._live_steps()

    def _live_steps(self) -> None:
        n = len(self._recorder.steps)
        self._capture_hint.set_label(f"Recording… {n} step{'s' if n != 1 else ''}. Press Record again or MR to stop.")


class MacrosPage(Gtk.Box):
    """The gtk layout's Macros tab: the list of macros on the left, the editor on the right."""

    def __init__(self, store: ProfileScope, client, toast: Callable[[str], None], on_macros_changed: Callable[[], None],
                 retarget: Retarget, style: str = "flow", on_style: Callable[[str], None] | None = None):
        super().__init__(orientation=Gtk.Orientation.HORIZONTAL)
        self._store = store
        self._on_macros_changed = on_macros_changed
        self._retarget = retarget
        self._macros: dict[str, Macro] = {}

        side = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, width_request=200)
        self._list = Gtk.ListBox(css_classes=["navigation-sidebar"], vexpand=True)
        self._list.connect("row-selected", self._on_select)
        side.append(Gtk.ScrolledWindow(child=self._list, vexpand=True, hscrollbar_policy=Gtk.PolicyType.NEVER))
        bar = Gtk.Box(spacing=4, margin_start=6, margin_end=6, margin_top=6, margin_bottom=6)
        for icon, tip, cb in (("list-add-symbolic", "New macro", self._new), ("edit-copy-symbolic", "Duplicate", self._duplicate),
                              ("user-trash-symbolic", "Delete", self._delete)):
            b = Gtk.Button(icon_name=icon, tooltip_text=tip, css_classes=["flat"])
            b.connect("clicked", lambda _b, f=cb: f())
            bar.append(b)
        side.append(bar)
        self.append(side)
        self.append(Gtk.Separator(orientation=Gtk.Orientation.VERTICAL))
        self.editor = MacroEditor(store, client, toast, self._saved, retarget, style, on_style)
        self.append(self.editor)
        self.reload()

    def reload(self) -> None:
        self._macros = self._store.load_macros()
        selected = self.editor.current.name if self.editor.current else None
        while (row := self._list.get_first_child()) is not None:
            self._list.remove(row)
        for name in sorted(self._macros):
            row = Gtk.ListBoxRow()
            box = Gtk.Box(spacing=6, margin_start=6, margin_end=6, margin_top=8, margin_bottom=8)
            box.append(Gtk.Label(label=name, xalign=0, hexpand=True, ellipsize=3, use_markup=False))
            if self._store.is_global_macro(name):
                mark = Gtk.Image.new_from_icon_name("web-browser-symbolic")
                mark.set_tooltip_text("Global")
                mark.add_css_class("dim-label")
                box.append(mark)
            row.set_child(box)
            row.macro_name = name  # type: ignore[attr-defined]
            self._list.append(row)
            if name == selected:
                self._list.select_row(row)
        if self._list.get_selected_row() is None:
            first = self._list.get_row_at_index(0)
            if first is not None:
                self._list.select_row(first)
            else:
                self.editor.edit(None)

    def _on_select(self, _list, row) -> None:
        self.editor.edit(self._macros.get(row.macro_name) if row is not None else None)

    def _saved(self, renamed: bool) -> None:
        if renamed:
            self.reload()
        self._on_macros_changed()

    def _new(self) -> None:
        self._adopt(Macro(unique_macro_name("New macro", self._macros)))

    def _duplicate(self) -> None:
        c = self.editor.current
        if c is not None:
            self._adopt(c.copy(unique_macro_name(f"{c.name} copy", self._macros)))

    def _adopt(self, m: Macro) -> None:
        self._store.save_macro(m)
        self.editor.edit(m)
        self.reload()
        self._on_macros_changed()

    def _delete(self) -> None:
        if (c := self.editor.current) is None:
            return
        name = c.name

        def delete() -> None:
            is_global = self._store.is_global_macro(name)
            self._store.delete_macro(name)
            self.editor.edit(None)
            self.reload()
            self._retarget("macro", name, None, is_global)
            self._on_macros_changed()
        confirm_delete_macro(self, name, delete)
