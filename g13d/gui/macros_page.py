"""Macros tab: list, editor, LGS-style recording (type keys while the window has focus)."""
from __future__ import annotations

import time
from collections.abc import Callable

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, GLib, Gtk  # noqa: E402

from g13d.config.loader import ConfigStore  # noqa: E402
from g13d.config.macro import REPEAT_MODES, Macro, Step  # noqa: E402
from g13d.engine.recorder import MacroRecorder  # noqa: E402
from g13d.hw.names import MOUSE_BUTTONS  # noqa: E402

from .dnd import make_reorderable  # noqa: E402
from .keymap import evdev_name_from_keycode, key_label  # noqa: E402
from .widgets import WidePage  # noqa: E402

_REPEAT_LABELS = {"once": "Once", "while_held": "While held", "toggle": "Toggle"}
_REPEAT_HELP = {"once": "Plays the whole macro each time the key is pressed.",
                "while_held": "Repeats while the key is held; the current pass always completes.",
                "toggle": "One press starts repeating, the next press stops."}
Retarget = Callable[[str, str, str | None], None]   # (kind, old name, new name or None when deleted)


def step_label(step: Step) -> str:
    if step.kind == "delay":
        return f"Wait {step.ms} ms"
    return {"press": "Press", "release": "Release", "tap": "Tap"}[step.kind] + "  " + key_label(step.key)


class MacrosPage(Gtk.Box):
    def __init__(self, store: ConfigStore, client, toast: Callable[[str], None], on_macros_changed: Callable[[], None],
                 retarget: Retarget):
        super().__init__(orientation=Gtk.Orientation.HORIZONTAL)
        self._store = store
        self._client = client
        self._toast = toast
        self._on_macros_changed = on_macros_changed
        self._retarget = retarget
        self._macros: dict[str, Macro] = {}
        self._current: Macro | None = None
        self._updating = False
        self._recorder = MacroRecorder()
        self._before_record: list[Step] = []
        self._save_timer = 0
        self._pending_kind: str | None = None

        # ---- left: list
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

        # ---- right: editor
        self._editor = WidePage()
        self.append(self._editor)
        g = Adw.PreferencesGroup()
        self._editor.add(g)
        # Text fields are applied on Enter, on the check button or when the field loses focus
        # (same behaviour everywhere; renaming live would also rebuild the list under the cursor).
        self._name = self._text_row("Name", self._apply_name)
        g.add(self._name)
        self._desc = self._text_row("Description", self._apply_description)
        g.add(self._desc)
        self._repeat = Adw.ComboRow(title="Playback", model=Gtk.StringList.new([_REPEAT_LABELS[m] for m in REPEAT_MODES]))
        self._repeat.connect("notify::selected", self._field_changed)
        g.add(self._repeat)
        self._repeat_help = Gtk.Label(css_classes=["dim-label", "caption"], wrap=True, xalign=0, margin_top=4)
        g.add(self._repeat_help)
        self._rdelay = Adw.SpinRow.new_with_range(0, 10000, 10)
        self._rdelay.set_title("Pause between repeats")
        self._rdelay.set_subtitle("Milliseconds")
        self._rdelay.connect("notify::value", self._field_changed)
        g.add(self._rdelay)

        sg = Adw.PreferencesGroup(title="Steps", description="Drag to reorder.")
        self._editor.add(sg)
        tools = Gtk.Box(spacing=6, margin_bottom=6)
        self._record = Gtk.ToggleButton(tooltip_text="Record keys typed in this window (replaces the steps)")
        self._record.set_child(self._btn_content("media-record-symbolic", "Record"))
        self._record.add_css_class("destructive-action")
        self._record.connect("toggled", self._toggle_record)
        tools.append(self._record)
        self._delays = Gtk.CheckButton(label="With delays", active=True, valign=Gtk.Align.CENTER)
        tools.append(self._delays)
        tools.append(self._add_step_button())
        clear = Gtk.Button(label="Clear", tooltip_text="Remove all steps")
        clear.connect("clicked", lambda *_: self._clear())
        tools.append(clear)
        play = Gtk.Button(tooltip_text="Play on the device now", hexpand=True, halign=Gtk.Align.END)
        play.set_child(self._btn_content("media-playback-start-symbolic", "Play"))
        play.connect("clicked", lambda *_: self._play())
        tools.append(play)
        sg.add(tools)
        self._steps = Gtk.ListBox(css_classes=["boxed-list"], selection_mode=Gtk.SelectionMode.NONE)
        sg.add(self._steps)
        self._empty = Gtk.Label(label="No steps yet. Press Record and type, or add steps by hand.",
                                css_classes=["dim-label"], margin_top=12)
        sg.add(self._empty)
        hint_box = Gtk.Box(spacing=8, margin_top=6, halign=Gtk.Align.CENTER)
        self._capture_hint = Gtk.Label(css_classes=["accent", "caption"], wrap=True)
        self._capture_cancel = Gtk.Button(label="Cancel", css_classes=["flat"])
        self._capture_cancel.connect("clicked", lambda *_: self._cancel_capture())
        hint_box.append(self._capture_hint)
        hint_box.append(self._capture_cancel)
        self._hint_box = hint_box
        hint_box.set_visible(False)
        sg.add(hint_box)

        ctl = Gtk.EventControllerKey()
        ctl.set_propagation_phase(Gtk.PropagationPhase.CAPTURE)
        ctl.connect("key-pressed", self._on_key)
        ctl.connect("key-released", self._on_key_release)
        self._key_ctl = ctl
        self.reload()

    @staticmethod
    def _text_row(title: str, apply) -> Adw.EntryRow:
        row = Adw.EntryRow(title=title, show_apply_button=True)
        row.connect("apply", lambda *_: apply())
        row.connect("entry-activated", lambda *_: apply())
        focus = Gtk.EventControllerFocus()
        focus.connect("leave", lambda *_: apply())
        row.add_controller(focus)
        return row

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
        wait.connect("clicked", lambda *_: (pop.popdown(), self._append(Step.delay(100))))
        box.append(wait)
        box.append(Gtk.Separator(margin_top=4, margin_bottom=4))
        box.append(Gtk.Label(label="Mouse", css_classes=["caption", "dim-label"], xalign=0))
        self._mouse_btn = Gtk.DropDown.new_from_strings([key_label(b) for b in MOUSE_BUTTONS])
        box.append(self._mouse_btn)
        row = Gtk.Box(spacing=4, homogeneous=True)
        for kind, label in (("tap", "Click"), ("press", "Press"), ("release", "Release")):
            b = Gtk.Button(label=label)
            b.connect("clicked", lambda _b, k=kind: (pop.popdown(), self._append(Step(k, MOUSE_BUTTONS[self._mouse_btn.get_selected()]))))
            row.append(b)
        box.append(row)
        pop.set_child(box)
        menu.set_popover(pop)
        return menu

    def attach_window_controller(self, window: Gtk.Window) -> None:
        window.add_controller(self._key_ctl)

    # ---- list management --------------------------------------------------------
    def reload(self) -> None:
        self._macros = self._store.load_macros()
        selected = self._current.name if self._current else None
        while (row := self._list.get_first_child()) is not None:
            self._list.remove(row)
        for name in sorted(self._macros):
            row = Gtk.ListBoxRow()
            row.set_child(Gtk.Label(label=name, xalign=0, margin_start=6, margin_top=8, margin_bottom=8, ellipsize=3))
            row.macro_name = name  # type: ignore[attr-defined]
            self._list.append(row)
            if name == selected:
                self._list.select_row(row)
        if self._list.get_selected_row() is None:
            first = self._list.get_row_at_index(0)
            if first is not None:
                self._list.select_row(first)
            else:
                self._show(None)

    def _on_select(self, _list, row) -> None:
        self._show(self._macros.get(row.macro_name) if row is not None else None)

    def _show(self, macro: Macro | None) -> None:
        self._stop_record()
        self._cancel_capture()
        self._current = macro
        self._editor.set_sensitive(macro is not None)
        self._updating = True
        self._name.set_text(macro.name if macro else "")
        self._desc.set_text(macro.description if macro else "")
        self._repeat.set_selected(REPEAT_MODES.index(macro.repeat) if macro and macro.repeat in REPEAT_MODES else 0)
        self._repeat_help.set_label(_REPEAT_HELP[macro.repeat] if macro else "")
        self._rdelay.set_value(macro.repeat_delay_ms if macro else 0)
        self._updating = False
        self._render_steps()

    def _new(self) -> None:
        base, name, i = "New macro", "New macro", 2
        while name in self._macros:
            name, i = f"{base} {i}", i + 1
        self._adopt(Macro(name))

    def _duplicate(self) -> None:
        if self._current is None:
            return
        name, i = f"{self._current.name} copy", 2
        while name in self._macros:
            name, i = f"{self._current.name} copy {i}", i + 1
        c = self._current
        self._adopt(Macro(name, list(c.steps), c.repeat, c.repeat_delay_ms, c.description))

    def _adopt(self, m: Macro) -> None:
        self._store.save_macro(m)
        self._current = m
        self.reload()
        self._on_macros_changed()

    def _delete(self) -> None:
        if self._current is None:
            return
        name = self._current.name
        dlg = Adw.AlertDialog(heading=f"Delete “{name}”?", body="Keys bound to this macro will be unbound.")
        dlg.add_response("cancel", "Cancel")
        dlg.add_response("delete", "Delete")
        dlg.set_response_appearance("delete", Adw.ResponseAppearance.DESTRUCTIVE)

        def on_resp(_d, resp):
            if resp == "delete":
                self._store.delete_macro(name)
                self._current = None
                self.reload()
                self._retarget("macro", name, None)
                self._on_macros_changed()
        dlg.connect("response", on_resp)
        dlg.present(self.get_root())

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
        if new_name in self._macros:
            self._name.add_css_class("error")
            self._toast(f"A macro named “{new_name}” already exists")
            return
        self._name.remove_css_class("error")
        old = m.name
        self._store.delete_macro(old)
        del self._macros[old]
        m.name = new_name
        self._macros[new_name] = m
        self._retarget("macro", old, new_name)
        self._do_save(relist=True)

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
        self._repeat_help.set_label(_REPEAT_HELP[m.repeat])
        m.repeat_delay_ms = int(self._rdelay.get_value())
        self._schedule_save()

    def _schedule_save(self, relist: bool = False) -> None:
        if self._save_timer:
            GLib.source_remove(self._save_timer)
        self._save_timer = GLib.timeout_add(400, self._do_save, relist)

    def _do_save(self, relist: bool = False) -> bool:
        self._save_timer = 0
        if self._current is not None:
            self._store.save_macro(self._current)
            if relist:
                self.reload()
            self._on_macros_changed()
        return False

    def refresh_labels(self) -> None:
        self._render_steps()

    def _render_steps(self) -> None:
        while (row := self._steps.get_first_child()) is not None:
            self._steps.remove(row)
        steps = self._current.steps if self._current else []
        self._empty.set_visible(not steps)
        for i, step in enumerate(steps):
            row = Adw.ActionRow(title=step_label(step), use_markup=False)
            row.add_css_class("g13-step-" + step.kind)
            handle = Gtk.Image.new_from_icon_name("list-drag-handle-symbolic")
            handle.add_css_class("dim-label")
            row.add_prefix(handle)
            if step.kind == "delay":
                spin = Gtk.SpinButton.new_with_range(0, 60000, 10)
                spin.set_value(step.ms)
                spin.set_valign(Gtk.Align.CENTER)
                spin.connect("value-changed", lambda s, k=i: self._set_delay(k, int(s.get_value())))
                row.add_suffix(spin)
            up = Gtk.Button(icon_name="go-up-symbolic", css_classes=["flat"], valign=Gtk.Align.CENTER, sensitive=i > 0)
            up.connect("clicked", lambda _b, k=i: self._move(k, k - 1))
            down = Gtk.Button(icon_name="go-down-symbolic", css_classes=["flat"], valign=Gtk.Align.CENTER, sensitive=i < len(steps) - 1)
            down.connect("clicked", lambda _b, k=i: self._move(k, k + 1))
            rm = Gtk.Button(icon_name="edit-delete-symbolic", css_classes=["flat"], valign=Gtk.Align.CENTER, tooltip_text="Remove")
            rm.connect("clicked", lambda _b, k=i: self._remove(k))
            for w in (up, down, rm):
                row.add_suffix(w)
            self._steps.append(row)
            make_reorderable(self._steps, row, i, self._move)

    def _move(self, src: int, dest: int) -> None:
        if self._current is None:
            return
        s = self._current.steps
        if 0 <= src < len(s) and 0 <= dest < len(s) and src != dest:
            s.insert(dest, s.pop(src))
            self._render_steps()
            self._schedule_save()

    def _remove(self, i: int) -> None:
        if self._current is None:
            return
        del self._current.steps[i]
        self._render_steps()
        self._schedule_save()

    def _set_delay(self, i: int, ms: int) -> None:
        if self._current is None:
            return
        self._current.steps[i] = Step.delay(ms)
        self._schedule_save()

    def _append(self, step: Step) -> None:
        if self._current is None:
            return
        self._current.steps.append(step)
        self._render_steps()
        self._schedule_save()

    def _clear(self) -> None:
        if self._current is None or not self._current.steps:
            return
        dlg = Adw.AlertDialog(heading="Remove all steps?", body=f"“{self._current.name}” will be empty.")
        dlg.add_response("cancel", "Cancel")
        dlg.add_response("clear", "Clear")
        dlg.set_response_appearance("clear", Adw.ResponseAppearance.DESTRUCTIVE)

        def on_resp(_d, resp):
            if resp == "clear" and self._current is not None:
                self._current.steps = []
                self._render_steps()
                self._schedule_save()
        dlg.connect("response", on_resp)
        dlg.present(self.get_root())

    def _play(self) -> None:
        if self._current is not None:
            self._do_save()
            self._client.run_macro(self._current.name)

    def _add_key_step(self, kind: str) -> None:
        if self._current is None:
            return
        self._pending_kind = kind
        self._capture_hint.set_label(f"Press the key to {kind} (Esc is allowed)…")
        self._hint_box.set_visible(True)

    def _cancel_capture(self) -> None:
        self._pending_kind = None
        if not self._recorder.recording:
            self._hint_box.set_visible(False)

    # ---- recording ----------------------------------------------------------------
    def _toggle_record(self, btn: Gtk.ToggleButton) -> None:
        if btn.get_active():
            if self._current is None:
                btn.set_active(False)
                return
            self._before_record = list(self._current.steps)
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
        if self._current is not None:
            self._current.steps = steps if steps else self._before_record   # nothing typed: keep the old steps
            self._render_steps()
            self._schedule_save()

    def toggle_record_from_device(self) -> None:
        """MR pressed on the G13 while the GUI is open."""
        if self.get_mapped() and self._current is not None:
            self._record.set_active(not self._record.get_active())

    def _on_key(self, _ctl, keyval, keycode, state) -> bool:
        if not self.get_mapped():
            return False
        name = evdev_name_from_keycode(keycode)
        if self._pending_kind is not None:
            if name is not None and self._current is not None:
                self._append(Step(self._pending_kind, name))
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
