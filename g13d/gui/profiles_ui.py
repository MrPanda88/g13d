"""The two ways profiles are listed: a sidebar (classic layout) or a strip of tiles (device layout).

Both expose the same interface so the window does not care which one is shown:
  rebuild(profiles, default, active, selected) · select(name) · set_active(name) · status (a Gtk.Label)
and call back on_select(name) when the user picks a profile and on_command(cmd, name) for
new / duplicate / rename / delete / default / icon / icon-clear.
"""
from __future__ import annotations

import os
from collections.abc import Callable

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
gi.require_version("Graphene", "1.0")
gi.require_version("GdkPixbuf", "2.0")
from gi.repository import Adw, Gdk, GdkPixbuf, Gio, GLib, Graphene, Gtk, Pango  # noqa: E402

from g13d.config.model import Profile  # noqa: E402

from .dnd import make_reorderable  # noqa: E402

OnSelect = Callable[[str], None]
OnCommand = Callable[[str, str], None]

_COMMANDS = (("list-add-symbolic", "New profile", "new"), ("edit-copy-symbolic", "Duplicate", "duplicate"),
             ("document-edit-symbolic", "Edit profile…", "menu"), ("user-trash-symbolic", "Delete", "delete"))


def profile_menu(name: str, is_default: bool, is_locked: bool = False, horizontal: bool = False) -> Gio.Menu:
    """The same commands in both layouts (actions live in the "profile" group of the list/strip)."""
    m = Gio.Menu()
    s1 = Gio.Menu()
    s1.append("Activate on the device", "profile.activate")
    s1.append("Unlock" if is_locked else "Lock (activate and ignore applications)", "profile.lock")
    s1.append("Unset as default" if is_default else "Set as default", "profile.default")
    m.append_section(None, s1)
    s2 = Gio.Menu()
    s2.append("Rename…", "profile.rename")
    s2.append("Duplicate", "profile.duplicate")
    s2.append("Choose icon…", "profile.icon")
    s2.append("Remove icon", "profile.icon-clear")
    s2.append("Application…", "profile.app")
    m.append_section(None, s2)
    s_move = Gio.Menu()
    s_move.append("Move up" if not horizontal else "Move left", "profile.move-up")
    s_move.append("Move down" if not horizontal else "Move right", "profile.move-down")
    m.append_section(None, s_move)
    s3 = Gio.Menu()
    s3.append("Delete", "profile.delete")
    m.append_section(None, s3)
    return m


class _ContextMenu:
    """Right-click popover bound to a host widget; `run(cmd, name)` dispatches to the callbacks."""

    def __init__(self, host: Gtk.Widget, on_select: OnSelect, on_command: OnCommand):
        self._host, self._on_select, self._on_command = host, on_select, on_command
        self._target = ""
        self.popover = Gtk.PopoverMenu()
        self.popover.set_parent(host)
        self.popover.set_has_arrow(False)
        group = Gio.SimpleActionGroup()
        for cmd in ("activate", "lock", "default", "rename", "duplicate", "icon", "icon-clear", "app", "delete",
                    "move-up", "move-down"):
            a = Gio.SimpleAction.new(cmd, None)
            a.connect("activate", lambda _a, _p, c=cmd: self._run(c))
            group.add_action(a)
        host.insert_action_group("profile", group)

    locked = ""        # name of the locked profile, set by the owner before opening the menu
    horizontal = False

    def open(self, name: str, is_default: bool, x: float, y: float, origin: Gtk.Widget | None = None) -> None:
        self._target = name
        self.popover.set_menu_model(profile_menu(name, is_default, name == self.locked, self.horizontal))
        if origin is not None and origin is not self._host:
            ok, p = origin.compute_point(self._host, Graphene.Point().init(x, y))
            if ok:
                x, y = p.x, p.y
        rect = Gdk.Rectangle()
        rect.x, rect.y, rect.width, rect.height = int(x), int(y), 1, 1
        self.popover.set_pointing_to(rect)
        self.popover.popup()

    def _run(self, cmd: str) -> None:
        if cmd == "activate":
            self._on_select(self._target)
        else:
            self._on_command(cmd, self._target)


def profile_icon(profile: Profile | None, size: int) -> Gtk.Widget:
    """A picture if the profile points at an image file, else a themed icon."""
    icon = profile.icon if profile else ""
    if icon and os.sep in icon and os.path.exists(icon):
        try:
            # scaled while loading so the tile keeps its size whatever the file's dimensions
            pixbuf = GdkPixbuf.Pixbuf.new_from_file_at_scale(icon, size, size, True)
        except GLib.Error:
            pixbuf = None
        if pixbuf is not None:
            pic = Gtk.Picture.new_for_paintable(Gdk.Texture.new_for_pixbuf(pixbuf))
            pic.set_content_fit(Gtk.ContentFit.COVER)
            pic.set_can_shrink(True)
            pic.set_size_request(size, size)
            pic.set_halign(Gtk.Align.CENTER)
            pic.set_valign(Gtk.Align.CENTER)
            pic.add_css_class("g13-tile-picture")
            frame = Gtk.Box(halign=Gtk.Align.CENTER, valign=Gtk.Align.CENTER, overflow=Gtk.Overflow.HIDDEN)
            frame.set_size_request(size, size)
            frame.append(pic)
            return frame
    img = Gtk.Image.new_from_icon_name(icon if icon and os.sep not in icon else "input-keyboard-symbolic")
    img.set_pixel_size(size)
    return img


class ProfilesSidebar(Gtk.Box):
    def __init__(self, on_select: OnSelect, on_command: OnCommand):
        super().__init__()
        self._on_select, self._on_command = on_select, on_command
        self._selected = ""
        self._default = ""
        self._locked = ""
        self._menu = _ContextMenu(self, on_select, on_command)
        view = Adw.ToolbarView(hexpand=True)
        self.append(view)
        header = Adw.HeaderBar()
        header.set_title_widget(Gtk.Label(label="Profiles", css_classes=["heading"]))
        view.add_top_bar(header)
        self._list = Gtk.ListBox(css_classes=["navigation-sidebar"])
        self._list.connect("row-activated", lambda _l, row: self._on_select(row.profile_name))
        click = Gtk.GestureClick(button=Gdk.BUTTON_SECONDARY)
        click.connect("pressed", self._on_right_click)
        self._list.add_controller(click)
        view.set_content(Gtk.ScrolledWindow(child=self._list, hscrollbar_policy=Gtk.PolicyType.NEVER))
        bar = Gtk.Box(spacing=4, margin_start=6, margin_end=6, margin_top=4, margin_bottom=4)
        for icon, tip, cmd in _COMMANDS:
            b = Gtk.Button(icon_name=icon, tooltip_text=tip, css_classes=["flat"])
            if cmd == "menu":
                b.connect("clicked", lambda btn: self._menu.open(self._selected, self._selected == self._default,
                                                                   btn.get_width() / 2, 0, btn))
            else:
                b.connect("clicked", lambda _b, c=cmd: self._on_command(c, self._selected))
            bar.append(b)
        view.add_bottom_bar(bar)
        self.status = Gtk.Label(css_classes=["caption", "dim-label"], margin_bottom=6, wrap=True)
        view.add_bottom_bar(self.status)

    def _moved(self, src: int, dest: int) -> None:
        self._on_command(f"move:{src}:{dest}", "")

    def _on_right_click(self, _g, _n, x, y) -> None:
        row = self._list.get_row_at_y(int(y))
        if row is not None:
            self._menu.open(row.profile_name, row.profile_name == self._default, x, y, self._list)

    def rebuild(self, profiles: dict[str, Profile], default: str, active: str, selected: str) -> None:
        self._default = default
        while (row := self._list.get_row_at_index(0)) is not None:
            self._list.remove(row)
        for i, name in enumerate(profiles):
            row = Adw.ActionRow(title=name, activatable=True, use_markup=False)
            make_reorderable(self._list, row, i, self._moved)
            row.profile_name = name  # type: ignore[attr-defined]
            row.add_prefix(profile_icon(profiles[name], 16))
            is_default = name == default
            star = Gtk.Button(icon_name="starred-symbolic" if is_default else "non-starred-symbolic", css_classes=["flat"],
                              valign=Gtk.Align.CENTER,
                              tooltip_text="Default profile (loaded when g13d starts)" if is_default else "Make this the default profile")
            star.connect("clicked", lambda _b, n=name: self._on_command("default", n))
            row.add_suffix(star)
            if profiles[name].app:
                link = Gtk.Image.new_from_icon_name("insert-link-symbolic")
                link.set_tooltip_text(f"Switches on automatically for: {profiles[name].app}")
                link.add_css_class("dim-label")
                row.add_suffix(link)
            lock = Gtk.Image.new_from_icon_name("changes-prevent-symbolic")
            lock.set_tooltip_text("Locked: stays active whatever the focused application")
            lock.set_visible(name == self._locked)
            row.add_suffix(lock)
            row.lock = lock  # type: ignore[attr-defined]
            dot = Gtk.Image.new_from_icon_name("object-select-symbolic")
            dot.set_visible(name == active)
            dot.set_tooltip_text("Active on the device")
            row.add_suffix(dot)
            row.dot = dot  # type: ignore[attr-defined]
            self._list.append(row)
        self.select(selected)

    def select(self, name: str) -> None:
        self._selected = name
        i = 0
        while (row := self._list.get_row_at_index(i)) is not None:
            if row.profile_name == name:
                self._list.select_row(row)
            i += 1

    def set_active(self, active: str, locked: str = "") -> None:
        self._locked = self._menu.locked = locked
        i = 0
        while (row := self._list.get_row_at_index(i)) is not None:
            row.dot.set_visible(row.profile_name == active)
            row.lock.set_visible(row.profile_name == locked)
            i += 1


class _Tile(Gtk.Button):
    def __init__(self, profile: Profile, is_default: bool, active: bool, locked: bool = False):
        super().__init__(css_classes=["flat", "g13-tile"])
        self.profile_name = profile.name
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        over = Gtk.Overlay(child=profile_icon(profile, 44))
        badges = Gtk.Box(spacing=2, halign=Gtk.Align.END, valign=Gtk.Align.START)
        if is_default:
            star = Gtk.Image.new_from_icon_name("starred-symbolic")
            star.set_css_classes(["g13-badge", "warning"])
            star.set_tooltip_text("Default profile (loaded when g13d starts)")
            badges.append(star)
        if profile.app:
            link = Gtk.Image.new_from_icon_name("insert-link-symbolic")
            link.set_css_classes(["g13-badge", "dim-label"])
            link.set_tooltip_text(f"Switches on automatically for: {profile.app}")
            badges.append(link)
        self.lock = Gtk.Image.new_from_icon_name("changes-prevent-symbolic")
        self.lock.set_visible(locked)
        self.lock.set_css_classes(["g13-badge", "error"])
        self.lock.set_tooltip_text("Locked: stays active whatever the focused application")
        badges.append(self.lock)
        self.dot = Gtk.Image.new_from_icon_name("object-select-symbolic")
        self.dot.set_visible(active)
        self.dot.set_css_classes(["g13-badge", "accent"])
        badges.append(self.dot)
        over.add_overlay(badges)
        box.append(over)
        box.append(Gtk.Label(label=profile.name, css_classes=["caption"], ellipsize=Pango.EllipsizeMode.END,
                             max_width_chars=12, use_markup=False))
        self.set_child(box)
        self.set_tooltip_text(profile.name + (" · default" if is_default else "") + (" · active on the device" if active else ""))


class ProfilesBar(Gtk.Box):
    """Horizontal strip of profile tiles with a right-click menu, plus a + tile and the status label."""

    def __init__(self, on_select: OnSelect, on_command: OnCommand):
        super().__init__(spacing=6, margin_start=6, margin_end=6, margin_top=4, margin_bottom=4)
        self._on_select, self._on_command = on_select, on_command
        self._tiles: dict[str, _Tile] = {}
        self._default = ""
        self._strip = Gtk.Box(spacing=4)
        scroller = Gtk.ScrolledWindow(child=self._strip, hexpand=True, vscrollbar_policy=Gtk.PolicyType.NEVER,
                                      hscrollbar_policy=Gtk.PolicyType.AUTOMATIC, propagate_natural_height=True)
        self.append(scroller)
        self.status = Gtk.Label(css_classes=["caption", "dim-label"], wrap=True, justify=Gtk.Justification.RIGHT,
                                max_width_chars=48, width_chars=22, xalign=1, valign=Gtk.Align.CENTER)
        self.append(self.status)

        # parented to the bar, not the strip: the strip's children are replaced on every rebuild
        self._menu = _ContextMenu(self, on_select, on_command)

    def rebuild(self, profiles: dict[str, Profile], default: str, active: str, selected: str) -> None:
        self._default = default
        while (w := self._strip.get_first_child()) is not None:
            self._strip.remove(w)
        self._tiles.clear()
        self._menu.horizontal = True
        for i, name in enumerate(profiles):
            tile = _Tile(profiles[name], name == default, name == active, name == self._menu.locked)
            make_reorderable(self._strip, tile, i, lambda s_, d: self._on_command(f"move:{s_}:{d}", ""), horizontal=True)
            tile.connect("clicked", lambda _b, n=name: self._on_select(n))
            click = Gtk.GestureClick(button=Gdk.BUTTON_SECONDARY)
            click.connect("pressed", lambda g, _n, x, y, n=name: self._menu.open(n, n == self._default, x, y, g.get_widget()))
            tile.add_controller(click)
            self._strip.append(tile)
            self._tiles[name] = tile
        plus = Gtk.Button(icon_name="list-add-symbolic", css_classes=["flat", "g13-tile", "g13-tile-add"], tooltip_text="New profile",
                          valign=Gtk.Align.CENTER)
        plus.connect("clicked", lambda *_: self._on_command("new", ""))
        self._strip.append(plus)
        self.select(selected)

    def select(self, name: str) -> None:
        for n, tile in self._tiles.items():
            if n == name:
                tile.add_css_class("g13-tile-selected")
            else:
                tile.remove_css_class("g13-tile-selected")

    def set_active(self, active: str, locked: str = "") -> None:
        self._menu.locked = locked
        for n, tile in self._tiles.items():
            tile.dot.set_visible(n == active)
            tile.lock.set_visible(n == locked)
