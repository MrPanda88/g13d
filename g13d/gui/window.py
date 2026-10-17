"""Main window: profile sidebar + Keys / Stick / LCD & Light / Macros tabs."""
from __future__ import annotations

import logging

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gdk, GLib, Gtk  # noqa: E402

from g13d import __version__  # noqa: E402
from g13d.config.defaults import default_profile  # noqa: E402
from g13d.config.loader import ConfigStore  # noqa: E402
from g13d.config.model import MODES, Action, Profile, Settings  # noqa: E402

from .action_editor import ActionEditor  # noqa: E402
from .client import DaemonClient  # noqa: E402
from .keymap import watch_keymap  # noqa: E402
from .keys_page import KeysPage  # noqa: E402
from .lcd_page import LcdPage  # noqa: E402
from .macros_page import MacrosPage  # noqa: E402
from .stick_page import StickPage  # noqa: E402

log = logging.getLogger(__name__)

CSS = """
.g13-body { background: alpha(@view_fg_color, 0.06); border-radius: 14px; }
.g13-lcd { background: #141008; color: #ffb000; border-radius: 6px; font-family: monospace; }
.g13-key { min-width: 62px; min-height: 58px; padding: 2px 4px; }
.g13-small { min-width: 44px; min-height: 40px; }
.g13-key.g13-bound { border-color: alpha(@accent_color, 0.5); }
.g13-key.g13-pressed { background: @accent_bg_color; color: @accent_fg_color; }
.g13-key.g13-pressed label { color: @accent_fg_color; }
.g13-preview { border-radius: 6px; }
.g13-step-delay { color: alpha(@view_fg_color, 0.7); }
.g13-dragging { opacity: 0.4; }
.g13-drop { box-shadow: inset 0 2px 0 0 @accent_bg_color; }
"""


class MainWindow(Adw.ApplicationWindow):
    def __init__(self, app: Adw.Application, client: DaemonClient, store: ConfigStore):
        super().__init__(application=app, title="G13 Configuration", default_width=1060, default_height=720)
        self._client = client
        self._store = store
        self._profiles: dict[str, Profile] = {}
        self._profile: Profile | None = None
        self._settings: Settings = store.load_settings()
        self._mode = 1
        self._reload_timer = 0
        self._updating = False
        self._seen_daemon_profile: str | None = None
        self._seen_daemon_mode: int | None = None

        provider = Gtk.CssProvider()
        provider.load_from_string(CSS)
        Gtk.StyleContext.add_provider_for_display(Gdk.Display.get_default(), provider,
                                                  Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)

        self._toasts = Adw.ToastOverlay()
        self.set_content(self._toasts)
        split = Adw.NavigationSplitView(min_sidebar_width=200, max_sidebar_width=260)
        self._toasts.set_child(split)

        # ---- sidebar: profiles
        side = Adw.ToolbarView()
        side_header = Adw.HeaderBar()
        side_header.set_title_widget(Gtk.Label(label="Profiles", css_classes=["heading"]))
        side.add_top_bar(side_header)
        self._list = Gtk.ListBox(css_classes=["navigation-sidebar"])
        self._list.connect("row-activated", self._on_profile_activated)
        side.set_content(Gtk.ScrolledWindow(child=self._list, hscrollbar_policy=Gtk.PolicyType.NEVER))
        bar = Gtk.Box(spacing=4, margin_start=6, margin_end=6, margin_top=4, margin_bottom=4)
        for icon, tip, cb in (("list-add-symbolic", "New profile", self._new_profile),
                              ("edit-copy-symbolic", "Duplicate", self._dup_profile),
                              ("document-edit-symbolic", "Rename", self._rename_profile),
                              ("user-trash-symbolic", "Delete", self._delete_profile)):
            b = Gtk.Button(icon_name=icon, tooltip_text=tip, css_classes=["flat"])
            b.connect("clicked", lambda _b, f=cb: f())
            bar.append(b)
        side.add_bottom_bar(bar)
        self._status = Gtk.Label(css_classes=["caption", "dim-label"], margin_bottom=6, wrap=True)
        side.add_bottom_bar(self._status)
        split.set_sidebar(Adw.NavigationPage(child=side, title="Profiles"))

        # ---- content
        content = Adw.ToolbarView()
        header = Adw.HeaderBar()
        self._stack = Adw.ViewStack()
        switcher = Adw.ViewSwitcher(stack=self._stack, policy=Adw.ViewSwitcherPolicy.WIDE)
        header.set_title_widget(switcher)
        menu_btn = Gtk.MenuButton(icon_name="open-menu-symbolic")
        menu_btn.set_menu_model(self._menu())
        header.pack_end(menu_btn)
        content.add_top_bar(header)
        self._banner = Adw.Banner(title="g13d is not running", button_label="Start", revealed=False)
        self._banner.connect("button-clicked", lambda *_: self._client.start_daemon())
        content.add_top_bar(self._banner)

        self._keys = KeysPage(self._edit_control, self._mode_selected)
        self._stick = StickPage(self._profile_changed)
        self._lcd = LcdPage(self._profile_changed, self._client.set_backlight)
        self._macros = MacrosPage(store, client, self.toast, self._macros_changed, self._retarget)
        self._macros.attach_window_controller(self)
        keys_scroll = Gtk.ScrolledWindow(child=self._keys, hscrollbar_policy=Gtk.PolicyType.AUTOMATIC)
        self._stack.add_titled_with_icon(keys_scroll, "keys", "Keys", "input-keyboard-symbolic")
        self._stack.add_titled_with_icon(self._stick, "stick", "Stick", "input-gaming-symbolic")
        self._stack.add_titled_with_icon(self._lcd, "lcd", "LCD & Light", "video-display-symbolic")
        self._stack.add_titled_with_icon(self._macros, "macros", "Macros", "media-record-symbolic")
        content.set_content(self._stack)
        split.set_content(Adw.NavigationPage(child=content, title="G13"))

        # ---- wiring
        client.connect("changed", lambda *_: self._sync_from_daemon())
        client.connect("key-event", self._on_key_event)
        client.connect("error", lambda _c, msg: self.toast(msg))
        # The compositor hands GTK the real keyboard layout only once the window has had focus:
        # refresh the layout-aware labels whenever we (re)gain it.
        watch_keymap(self.refresh_labels)
        self.connect("notify::is-active", lambda *_: self.refresh_labels())
        self._load_profiles()
        self._sync_from_daemon()

    # ---- helpers ------------------------------------------------------------------
    def toast(self, message: str) -> None:
        self._toasts.add_toast(Adw.Toast(title=message, timeout=4))

    def _menu(self):
        from gi.repository import Gio
        menu = Gio.Menu()
        menu.append("Reload configuration", "app.reload")
        menu.append("Open configuration folder", "app.open-config")
        menu.append("About", "app.about")
        return menu

    # ---- profiles ---------------------------------------------------------------------
    def _load_profiles(self) -> None:
        self._profiles = self._store.load_profiles()
        if not self._profiles:
            self._store.ensure_defaults()
            self._profiles = self._store.load_profiles()
        wanted = self._profile.name if self._profile else self._client.profile
        self._rebuild_list()
        self._select_profile(wanted if wanted in self._profiles else next(iter(self._profiles)), activate=False)

    def _rebuild_list(self) -> None:
        while (row := self._list.get_first_child()) is not None:
            self._list.remove(row)
        for name in sorted(self._profiles):
            row = Adw.ActionRow(title=name, activatable=True, use_markup=False)
            row.profile_name = name  # type: ignore[attr-defined]
            is_default = name == self._settings.default_profile
            star = Gtk.Button(icon_name="starred-symbolic" if is_default else "non-starred-symbolic", css_classes=["flat"],
                              valign=Gtk.Align.CENTER,
                              tooltip_text="Default profile (loaded when g13d starts)" if is_default else "Make this the default profile")
            star.connect("clicked", lambda _b, n=name: self._set_default(n))
            row.add_suffix(star)
            dot = Gtk.Image.new_from_icon_name("emblem-ok-symbolic")
            dot.set_visible(name == self._client.profile)
            dot.set_tooltip_text("Active on the device")
            row.add_suffix(dot)
            row.dot = dot  # type: ignore[attr-defined]
            self._list.append(row)

    def _select_profile(self, name: str, activate: bool) -> None:
        self._profile = self._profiles.get(name)
        i = 0
        while (row := self._list.get_row_at_index(i)) is not None:
            if getattr(row, "profile_name", None) == name:
                self._list.select_row(row)
            i += 1
        self._updating = True
        self._keys.set_profile(self._profile)
        self._stick.set_profile(self._profile)
        self._lcd.set_profile(self._profile)
        self._updating = False
        if activate and self._client.available and name != self._client.profile:
            self._client.set_profile(name)

    def _on_profile_activated(self, _list, row) -> None:
        self._select_profile(row.profile_name, activate=True)

    def _set_default(self, name: str) -> None:
        self._settings.default_profile = "" if self._settings.default_profile == name else name
        self._store.save_settings(self._settings)
        self._rebuild_list()
        self._select_profile(self._profile.name if self._profile else name, activate=False)
        self._schedule_reload()
        self.toast(f"“{name}” is the default profile" if self._settings.default_profile else "No default profile: the last used one is restored")

    def _new_profile(self) -> None:
        self._ask_name("New profile", "Default", lambda n: self._create(default_profile(n)))

    def _dup_profile(self) -> None:
        if self._profile is None:
            return
        self._ask_name("Duplicate profile", f"{self._profile.name} copy", lambda n: self._create(self._profile.copy(n)))

    def _rename_profile(self) -> None:
        if self._profile is None:
            return
        old = self._profile

        def do(n: str) -> None:
            previous = old.name
            self._store.delete_profile(previous)
            old.name = n
            self._store.save_profile(old)
            if self._settings.default_profile == previous:
                self._settings.default_profile = n
                self._store.save_settings(self._settings)
            self._retarget("profile", previous, n)
            self._load_profiles()
            self._activate_fresh(n)
        self._ask_name("Rename profile", old.name, do)

    def _create(self, prof: Profile) -> None:
        self._store.save_profile(prof)
        self._load_profiles()
        self._activate_fresh(prof.name)

    def _activate_fresh(self, name: str) -> None:
        """Make the daemon load the files first, then switch; D-Bus calls on one connection stay ordered."""
        if self._reload_timer:
            GLib.source_remove(self._reload_timer)
            self._reload_timer = 0
        if self._client.available:
            self._client.reload()
        self._select_profile(name, activate=True)

    def _delete_profile(self) -> None:
        if self._profile is None or len(self._profiles) <= 1:
            self.toast("Keep at least one profile")
            return
        name = self._profile.name
        dlg = Adw.AlertDialog(heading=f"Delete “{name}”?", body="This cannot be undone.")
        dlg.add_response("cancel", "Cancel")
        dlg.add_response("delete", "Delete")
        dlg.set_response_appearance("delete", Adw.ResponseAppearance.DESTRUCTIVE)

        def on_resp(_d, resp):
            if resp == "delete":
                self._store.delete_profile(name)
                if self._settings.default_profile == name:
                    self._settings.default_profile = ""
                    self._store.save_settings(self._settings)
                self._profile = None
                self._load_profiles()
                self._retarget("profile", name, None)
                self._schedule_reload()
        dlg.connect("response", on_resp)
        dlg.present(self)

    def _retarget(self, kind: str, old: str, new: str | None) -> None:
        """A profile or macro was renamed/deleted: fix every binding that pointed at it."""
        for prof in self._profiles.values():
            touched = False
            for mode in MODES:
                for control, action in list(prof.modes.get(mode, {}).items()):
                    if action.type == kind and action.name == old:
                        prof.set_binding(mode, control, Action.none() if new is None else
                                         (Action.profile(new) if kind == "profile" else Action.macro(new)))
                        touched = True
            if touched:
                self._store.save_profile(prof)
        self._keys.refresh()

    def _ask_name(self, heading: str, initial: str, cb) -> None:
        dlg = Adw.AlertDialog(heading=heading)
        entry = Gtk.Entry(text=initial, activates_default=True)
        dlg.set_extra_child(entry)
        dlg.add_response("cancel", "Cancel")
        dlg.add_response("ok", "OK")
        dlg.set_default_response("ok")
        dlg.set_response_appearance("ok", Adw.ResponseAppearance.SUGGESTED)

        def on_resp(_d, resp):
            name = entry.get_text().strip()
            if resp != "ok" or not name:
                return
            if name in self._profiles and name != initial:
                self.toast(f"A profile named “{name}” already exists")
                return
            cb(name)
        dlg.connect("response", on_resp)
        dlg.present(self)

    # ---- editing ------------------------------------------------------------------------
    def _mode_selected(self, mode: int) -> None:
        self._mode = mode
        self._keys.set_mode(mode)
        self._lcd.set_mode(mode)
        if self._client.available and self._client.mode != mode and self._profile and self._profile.name == self._client.profile:
            self._client.set_mode(mode)

    def edit_control(self, control: str) -> None:
        self._edit_control(control)

    def _edit_control(self, control: str) -> None:
        if self._profile is None:
            return
        action = self._profile.binding(self._mode, control)
        pages = self._client.available_pages or ["status", "clock", "system", "media", "text", "blank"]
        macros = sorted(self._store.load_macros())

        def on_save(new: Action) -> None:
            assert self._profile is not None
            self._profile.set_binding(self._mode, control, new)
            self._keys.refresh()
            self._profile_changed()
        ActionEditor(control, action, macros, sorted(self._profiles), pages, on_save).present(self)

    def _profile_changed(self) -> None:
        if self._updating or self._profile is None:
            return
        self._store.save_profile(self._profile)
        self._schedule_reload()

    def _macros_changed(self) -> None:
        self._schedule_reload()

    def _schedule_reload(self) -> None:
        if self._reload_timer:
            GLib.source_remove(self._reload_timer)
        self._reload_timer = GLib.timeout_add(300, self._do_reload)

    def _do_reload(self) -> bool:
        self._reload_timer = 0
        if self._client.available:
            self._client.reload()
        return False

    def refresh_labels(self) -> None:
        self._keys.refresh()
        self._macros.refresh_labels()

    def show_mode(self, mode: int) -> None:
        self._seen_daemon_mode = self._client.mode   # do not let the first daemon sync override the request
        self._mode = mode
        self._keys.set_mode(mode)
        self._lcd.set_mode(mode)

    def show_tab(self, name: str) -> None:
        self._stack.set_visible_child_name(name)

    def reload_all(self) -> None:
        self._load_profiles()
        self._macros.reload()
        self._schedule_reload()

    # ---- daemon state -------------------------------------------------------------------
    def _sync_from_daemon(self) -> None:
        c = self._client
        self._banner.set_revealed(not c.available)
        if c.available:
            dev = "G13 connected" if c.device_connected else "G13 not detected"
            self._status.set_label(f"{dev} · active: {c.profile} M{c.mode}" + (" · recording" if c.recording else ""))
        else:
            self._status.set_label("daemon not running")
        i = 0
        while (row := self._list.get_row_at_index(i)) is not None:
            row.dot.set_visible(getattr(row, "profile_name", None) == c.profile)
            i += 1
        if c.available and c.profile and c.profile != self._seen_daemon_profile:
            self._seen_daemon_profile = c.profile
            if c.profile in self._profiles and (self._profile is None or self._profile.name != c.profile):
                self._select_profile(c.profile, activate=False)   # follow what the device switched to
        if c.available and c.mode != self._seen_daemon_mode:
            self._seen_daemon_mode = c.mode
            if self._profile is not None and self._profile.name == c.profile and c.mode != self._mode:
                self._mode = c.mode          # follow M-key presses on the device
                self._keys.set_mode(c.mode)
                self._lcd.set_mode(c.mode)
        if self._profile is None and c.profile in self._profiles:
            self._select_profile(c.profile, activate=False)

    def _on_key_event(self, _c, name: str, pressed: bool) -> None:
        self._keys.set_pressed(name, pressed)
        if name == "MR" and pressed:
            self._macros.toggle_record_from_device()


def about_dialog(parent: Gtk.Window) -> None:
    Adw.AboutDialog(application_name="G13 Configuration", application_icon="input-keyboard", version=__version__,
                    developer_name="g13d contributors", license_type=Gtk.License.MIT_X11,
                    website="https://github.com/MrPanda88/g13d",
                    comments="Native Linux support for the Logitech G13 gameboard.").present(parent)
