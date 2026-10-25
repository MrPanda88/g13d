"""Left panel of the device layout: the assignments and macros of the selected profile (its own and the global
ones, marked with a globe), draggable onto the keys. Macros are created (+ on their section) and edited
(right-click) from here."""
from __future__ import annotations

from collections.abc import Callable

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
gi.require_version("Graphene", "1.0")
from gi.repository import Adw, Gdk, Gio, Graphene, Gtk, Pango  # noqa: E402

from g13d.config.library import LibraryEntry  # noqa: E402
from g13d.config.model import LIBRARY_SORTS, Action  # noqa: E402

from .dnd import make_action_source  # noqa: E402
from .widgets import focus_entry  # noqa: E402
from .keymap import action_label  # noqa: E402

ICONS = {"key": "input-keyboard-symbolic", "combo": "preferences-desktop-keyboard-shortcuts-symbolic", "macro": "media-record-symbolic",
         "mouse": "input-mouse-symbolic", "mode": "view-refresh-symbolic", "profile": "user-info-symbolic",
         "lcd_page": "video-display-symbolic"}


TYPE_ORDER = ("key", "combo", "mouse", "macro", "mode", "profile", "lcd_page")
GLOBAL_ICON = "web-browser-symbolic"


class _Row(Gtk.ListBoxRow):
    def __init__(self, action: Action, label: str, is_macro: bool, index: int, is_global: bool = False):
        super().__init__()
        self.action = action
        self.label = label
        self.is_macro = is_macro
        self.index = index
        self.is_global = is_global
        box = Gtk.Box(spacing=8, margin_start=8, margin_end=8, margin_top=6, margin_bottom=6)
        box.append(Gtk.Image.new_from_icon_name(ICONS.get(action.type, "emblem-system-symbolic")))
        text = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self._title = Gtk.Label(label=label, xalign=0, ellipsize=Pango.EllipsizeMode.END, use_markup=False)
        self._sub = Gtk.Label(xalign=0, ellipsize=Pango.EllipsizeMode.END, css_classes=["caption", "dim-label"], use_markup=False)
        text.append(self._title)
        text.append(self._sub)
        box.append(text)
        if is_global:
            mark = Gtk.Image.new_from_icon_name(GLOBAL_ICON)
            mark.set_tooltip_text("Global")
            mark.set_css_classes(["dim-label"])
            mark.set_hexpand(True)
            mark.set_halign(Gtk.Align.END)
            box.append(mark)
        self.set_child(box)
        self.refresh_labels()
        make_action_source(self, lambda: self.action, lambda: self.label, ICONS.get(action.type))

    def refresh_labels(self) -> None:
        """Subtitle: what the key prints with the current layout, when it differs from the entry's name."""
        shown = action_label(self.action)
        self._sub.set_label(shown)
        self._sub.set_visible(not self.is_macro and shown != self.label)


class _NoMacro(Gtk.ListBoxRow):
    """Placeholder of the Macros section while there is none (the section header carries the + button)."""
    is_macro = True
    is_global = False
    label = ""
    index = 0
    action = Action.none()

    def __init__(self):
        super().__init__(activatable=False, selectable=False)
        self.set_child(Gtk.Label(label="No macro yet: + creates one.", xalign=0, wrap=True, margin_start=8,
                                 margin_end=8, margin_top=4, margin_bottom=4, css_classes=["dim-label", "caption"]))

    def refresh_labels(self) -> None:
        pass


class LibraryPanel(Gtk.Box):
    """Callbacks: on_add() opens the action editor for a new entry; on_edit(entry), on_rename(entry, label),
    on_remove(entry) edit the library, on_scope(entry, to_global) moves an entry between the profile and the
    global library; on_macro(cmd, name) with cmd new / edit / duplicate / delete / make-global / make-local, and
    select (left click on a macro: the window opens it when the macro editor is already showing)."""

    def __init__(self, on_add: Callable[[], None], on_edit: Callable[[LibraryEntry], None],
                 on_rename: Callable[[LibraryEntry, str], None], on_remove: Callable[[LibraryEntry], None],
                 on_macro: Callable[[str, str], None], sort: str = "added", on_sort: Callable[[str], None] | None = None,
                 on_scope: Callable[[LibraryEntry, bool], None] | None = None):
        super().__init__(orientation=Gtk.Orientation.VERTICAL)
        self._on_edit, self._on_rename, self._on_remove = on_edit, on_rename, on_remove
        self._on_macro = on_macro
        self._on_sort = on_sort
        self._on_scope = on_scope
        self._entries: list[tuple[LibraryEntry, bool]] = []
        self._macros: list[str] = []
        self._current_macro: str | None = None      # the macro in the editor, highlighted
        self._sort = sort if sort in LIBRARY_SORTS else "added"

        top = Gtk.Box(spacing=4, margin_start=6, margin_end=6, margin_top=6, margin_bottom=6)
        self._search = Gtk.SearchEntry(placeholder_text="Search assignments", hexpand=True)
        self._search.connect("search-changed", lambda *_: self._list.invalidate_filter())
        top.append(self._search)
        self._sort_menu = Gtk.DropDown(model=Gtk.StringList.new(["Added", "Name", "Type"]), tooltip_text="Sort",
                                       valign=Gtk.Align.CENTER)
        self._sort_menu.set_selected(LIBRARY_SORTS.index(self._sort))
        self._sort_menu.connect("notify::selected", self._sort_changed)
        top.append(self._sort_menu)
        self.append(top)
        self._list = Gtk.ListBox(css_classes=["navigation-sidebar"], selection_mode=Gtk.SelectionMode.NONE, vexpand=True)
        self._list.set_filter_func(self._filter)
        self._list.set_sort_func(self._compare)
        self._list.set_header_func(self._header)
        self.append(Gtk.ScrolledWindow(child=self._list, vexpand=True, hscrollbar_policy=Gtk.PolicyType.NEVER))
        hint = Gtk.Label(label="Drag an assignment onto a key of the G13.", css_classes=["dim-label", "caption"], wrap=True,
                         margin_start=8, margin_end=8, margin_bottom=4, justify=Gtk.Justification.CENTER)
        self.append(hint)
        bar = Gtk.Box(spacing=4, margin_start=6, margin_end=6, margin_top=2, margin_bottom=6)
        add = Gtk.Button(icon_name="list-add-symbolic", tooltip_text="New assignment", css_classes=["flat"])
        add.connect("clicked", lambda *_: on_add())
        bar.append(add)
        self.append(bar)

        # right-click menu on entries (one for assignments, one for macros)
        self._menu_row: _Row | None = None
        self._popover = Gtk.PopoverMenu()
        self._popover.set_parent(self)          # not the list: its rows are replaced on every refresh
        self._popover.set_has_arrow(False)
        click = Gtk.GestureClick(button=3)
        click.connect("pressed", self._on_right_click)
        self._list.add_controller(click)
        # left click on a macro: a drag (to a key) cancels it, so only a real click selects
        pick = Gtk.GestureClick(button=1)
        pick.connect("released", self._on_left_click)
        self._list.add_controller(pick)
        group = Gio.SimpleActionGroup()
        for name, cb in (("edit", self._menu_edit), ("rename", self._menu_rename), ("remove", self._menu_remove),
                         ("scope", self._menu_scope)):
            a = Gio.SimpleAction.new(name, None)
            a.connect("activate", lambda _a, _p, f=cb: f())
            group.add_action(a)
        self.insert_action_group("entry", group)
        group = Gio.SimpleActionGroup()
        for name in ("edit", "duplicate", "delete", "scope"):
            a = Gio.SimpleAction.new(name, None)
            a.connect("activate", lambda _a, _p, c=name: self._menu_row is not None and self._macro_cmd(c))
            group.add_action(a)
        self.insert_action_group("macro", group)

    # ---- data ---------------------------------------------------------------------
    def set_library(self, entries: list[tuple[LibraryEntry, bool]], macros: list[tuple[str, bool]]) -> None:
        """entries / macros: (entry or macro name, is global)."""
        self._entries = entries
        self._macros = sorted(n for n, _ in macros)
        while (row := self._list.get_row_at_index(0)) is not None:
            self._list.remove(row)
        for i, (name, is_global) in enumerate(sorted(macros)):
            row = _Row(Action.macro(name), name, True, i, is_global)
            if name == self._current_macro:
                row.add_css_class("g13-current")
            self._list.append(row)
        if not macros:
            self._list.append(_NoMacro())
        for i, (e, is_global) in enumerate(entries):
            self._list.append(_Row(e.action, e.label, False, i, is_global))

    def set_current_macro(self, name: str | None) -> None:
        """Highlight the macro being edited (None: none)."""
        self._current_macro = name
        i = 0
        while (row := self._list.get_row_at_index(i)) is not None:
            if isinstance(row, _Row) and row.is_macro and row.label == name:
                row.add_css_class("g13-current")
            else:
                row.remove_css_class("g13-current")
            i += 1

    def refresh_labels(self) -> None:
        i = 0
        while (row := self._list.get_row_at_index(i)) is not None:
            row.refresh_labels()
            i += 1

    # ---- list cosmetics ------------------------------------------------------------
    def _sort_changed(self, *_: object) -> None:
        self._sort = LIBRARY_SORTS[self._sort_menu.get_selected()]
        self._list.invalidate_sort()
        self._list.invalidate_headers()
        if self._on_sort is not None:
            self._on_sort(self._sort)

    def _key(self, row: _Row):
        """Macros always come first; then the chosen order (type groups keep the library's own order inside)."""
        if self._sort == "name":
            return (row.is_macro is False, row.label.casefold())
        if self._sort == "type":
            t = TYPE_ORDER.index(row.action.type) if row.action.type in TYPE_ORDER else len(TYPE_ORDER)
            return (row.is_macro is False, t, row.label.casefold())
        return (row.is_macro is False, row.index)

    def _compare(self, a: _Row, b: _Row) -> int:
        ka, kb = self._key(a), self._key(b)
        return -1 if ka < kb else (1 if ka > kb else 0)

    def _filter(self, row: _Row) -> bool:
        q = self._search.get_text().strip().lower()
        if isinstance(row, _NoMacro):
            return True
        return not q or q in row.label.lower() or q in action_label(row.action).lower() or q in row.action.describe().lower()

    def _header(self, row: _Row, before: _Row | None) -> None:
        if before is None or before.is_macro != row.is_macro:
            header = Gtk.Box(margin_start=10, margin_end=4, margin_top=6, margin_bottom=2)
            header.append(Gtk.Label(label="Macros" if row.is_macro else "Assignments", xalign=0, hexpand=True,
                                    css_classes=["heading"]))
            if row.is_macro:
                add = Gtk.Button(icon_name="list-add-symbolic", tooltip_text="New macro", css_classes=["flat", "circular"])
                add.connect("clicked", lambda *_: self._on_macro("new", ""))
                header.append(add)
            row.set_header(header)
        else:
            row.set_header(None)

    # ---- context menu ------------------------------------------------------------
    @staticmethod
    def _menu_model(is_global: bool) -> Gio.Menu:
        m = Gio.Menu()
        m.append("Edit…", "entry.edit")
        m.append("Rename…", "entry.rename")
        m.append("Make local (this profile)" if is_global else "Make global (every profile)", "entry.scope")
        m.append("Remove", "entry.remove")
        return m

    @staticmethod
    def _macro_menu_model(is_global: bool) -> Gio.Menu:
        m = Gio.Menu()
        m.append("Edit…", "macro.edit")
        m.append("Duplicate", "macro.duplicate")
        m.append("Make local (this profile)" if is_global else "Make global (every profile)", "macro.scope")
        m.append("Delete…", "macro.delete")
        return m

    def _macro_cmd(self, cmd: str) -> None:
        row = self._menu_row
        if cmd == "scope":
            cmd = "make-local" if row.is_global else "make-global"
        self._on_macro(cmd, row.label)

    def _on_left_click(self, _g, _n, _x, y) -> None:
        row = self._list.get_row_at_y(int(y))
        if isinstance(row, _Row) and row.is_macro:
            self._on_macro("select", row.label)

    def _on_right_click(self, _g, _n, x, y) -> None:
        row = self._list.get_row_at_y(int(y))
        if not isinstance(row, _Row):
            return
        self._menu_row = row
        ok, p = self._list.compute_point(self, Graphene.Point().init(x, y))
        rect = Gdk.Rectangle()
        rect.x, rect.y, rect.width, rect.height = int(p.x if ok else x), int(p.y if ok else y), 1, 1
        self._popover.set_menu_model(self._macro_menu_model(row.is_global) if row.is_macro else self._menu_model(row.is_global))
        self._popover.set_pointing_to(rect)
        self._popover.popup()

    def _entry(self) -> LibraryEntry | None:
        row = self._menu_row
        if row is None:
            return None
        return next((e for e, g in self._entries if e.action == row.action and g == row.is_global), None)

    def _menu_scope(self) -> None:
        if (e := self._entry()) is not None and self._on_scope is not None:
            self._on_scope(e, not self._menu_row.is_global)

    def _menu_edit(self) -> None:
        if (e := self._entry()) is not None:
            self._on_edit(e)

    def _menu_rename(self) -> None:
        if (e := self._entry()) is None:
            return
        dlg = Adw.AlertDialog(heading="Rename assignment")
        entry = Gtk.Entry(text=e.label, activates_default=True)
        dlg.set_extra_child(entry)
        dlg.add_response("cancel", "Cancel")
        dlg.add_response("ok", "OK")
        dlg.set_default_response("ok")
        dlg.set_response_appearance("ok", Adw.ResponseAppearance.SUGGESTED)
        dlg.connect("response", lambda _d, r: r == "ok" and self._on_rename(e, entry.get_text()))
        dlg.present(self.get_root())
        focus_entry(entry)

    def _menu_remove(self) -> None:
        if (e := self._entry()) is None:
            return
        dlg = Adw.AlertDialog(heading=f"Remove “{e.label}” from the library?",
                              body="Keys that use it keep their assignment.")
        dlg.add_response("cancel", "Cancel")
        dlg.add_response("remove", "Remove")
        dlg.set_response_appearance("remove", Adw.ResponseAppearance.DESTRUCTIVE)
        dlg.connect("response", lambda _d, r: r == "remove" and self._on_remove(e))
        dlg.present(self.get_root())

