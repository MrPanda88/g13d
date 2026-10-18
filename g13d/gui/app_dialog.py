"""Dialog linking a profile to an application (auto-switch when it has the focus)."""
from __future__ import annotations

from collections.abc import Callable

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gtk  # noqa: E402

from g13d.config.model import Profile  # noqa: E402

from .client import DaemonClient  # noqa: E402

HELP = ("The rule is matched against the window class, the application id and the process name of the focused "
        "window (case-insensitive, * allowed, e.g. steam_app_*). When that application gets the focus the G13 "
        "switches to this profile, and back to the profile you had chosen when it loses it.")
NO_TRACKING = ("The desktop is not reporting the focused window. Install the g13d GNOME Shell extension "
               "(make install-extension), then log out and back in.")


class AppDialog(Adw.Dialog):
    def __init__(self, profile: Profile, client: DaemonClient, on_save: Callable[[str], None], toast: Callable[[str], None]):
        super().__init__(title=f"Application for “{profile.name}”", content_width=520)
        self._profile = profile
        self._client = client
        self._on_save = on_save
        self._toast = toast

        view = Adw.ToolbarView()
        view.add_top_bar(Adw.HeaderBar())
        page = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=18, margin_top=6, margin_bottom=18, margin_start=18,
                       margin_end=18)
        view.set_content(Gtk.ScrolledWindow(child=page, propagate_natural_height=True, max_content_height=640,
                                            hscrollbar_policy=Gtk.PolicyType.NEVER))
        self.set_child(view)

        self._banner = Adw.Banner(title=NO_TRACKING, revealed=not client.focus_tracking)
        page.append(self._banner)

        g = Adw.PreferencesGroup(title="Rule", description=HELP)
        page.append(g)
        # text field: applied on Enter, the check button or when it loses focus (same as every other text field)
        self._rule = Adw.EntryRow(title="Window class, app id or process", show_apply_button=True, text=profile.app)
        self._rule.connect("apply", lambda *_: self._apply())
        self._rule.connect("entry-activated", lambda *_: self._apply())
        focus = Gtk.EventControllerFocus()
        focus.connect("leave", lambda *_: self._apply())
        self._rule.add_controller(focus)
        g.add(self._rule)
        clear = Adw.ActionRow(title="No application", subtitle="Never switch to this profile automatically", activatable=True)
        clear.add_suffix(Gtk.Image.new_from_icon_name("edit-clear-symbolic"))
        clear.connect("activated", lambda *_: (self._rule.set_text(""), self._apply()))
        g.add(clear)

        capture = Adw.PreferencesGroup(title="Pick it on the G13",
                                       description="Switch to the application, then press LCD 3 under the screen; LCD 4 cancels.")
        page.append(capture)
        row = Adw.ActionRow(title="Capture the focused application", subtitle="The panel shows what it sees", activatable=True)
        row.add_suffix(Gtk.Image.new_from_icon_name("go-next-symbolic"))
        row.connect("activated", lambda *_: self._capture())
        row.set_sensitive(client.available and client.focus_tracking)
        capture.add(row)

        self._apps_group = Adw.PreferencesGroup(title="Running applications", description="Click one to use it.")
        refresh = Gtk.Button(icon_name="view-refresh-symbolic", css_classes=["flat"], tooltip_text="Refresh", valign=Gtk.Align.CENTER)
        refresh.connect("clicked", lambda *_: self._load_apps())
        self._apps_group.set_header_suffix(refresh)
        page.append(self._apps_group)
        self._apps = Gtk.ListBox(css_classes=["boxed-list"], selection_mode=Gtk.SelectionMode.NONE)
        self._apps.connect("row-activated", lambda _l, row: (self._rule.set_text(row.app_key), self._apply()))
        self._apps_group.add(self._apps)
        self._empty = Gtk.Label(label="No window reported.", css_classes=["dim-label"], margin_top=6)
        self._apps_group.add(self._empty)

        auto = Adw.PreferencesGroup(title="All profiles")
        page.append(auto)
        self._auto = Adw.SwitchRow(title="Switch profiles automatically", subtitle="Follow the focused application (all profiles)",
                                   active=client.auto_profiles, sensitive=client.available)
        self._auto.connect("notify::active", lambda r, _p: client.set_auto_profiles(r.get_active()))
        auto.add(self._auto)

        self._load_apps()

    # ---- actions -----------------------------------------------------------------
    def _apply(self) -> None:
        rule = self._rule.get_text().strip()
        if rule != self._profile.app:
            self._on_save(rule)

    def _capture(self) -> None:
        self._client.capture_app(self._profile.name)
        self._toast("Switch to the application, then press LCD 3 on the G13 (LCD 4 cancels)")
        self.close()

    def _load_apps(self) -> None:
        def show(apps: list[dict]) -> None:
            while (row := self._apps.get_row_at_index(0)) is not None:
                self._apps.remove(row)
            apps = sorted(apps, key=lambda a: a.get("label", "").casefold())
            for a in apps:
                row = Adw.ActionRow(title=a.get("label", "?"), subtitle=a.get("key", ""), activatable=True, use_markup=False)
                row.set_subtitle_lines(1)
                row.set_tooltip_text(f"{a.get('title', '')}\n{a.get('ids', '')}")
                row.app_key = a.get("key", "")  # type: ignore[attr-defined]
                if a.get("key") and a["key"].casefold() == self._profile.app.casefold():
                    row.add_suffix(Gtk.Image.new_from_icon_name("object-select-symbolic"))
                row.add_suffix(Gtk.Image.new_from_icon_name("go-next-symbolic"))
                self._apps.append(row)
            self._empty.set_visible(not apps)
            self._apps.set_visible(bool(apps))
        self._client.list_apps(show)

