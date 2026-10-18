"""Main window. Two layouts, switched live from the menu:

- gtk: profile sidebar on the left, Keys / Stick / LCD & Light / Macros tabs, schematic keypad
- lgs: assignment library on the left, the photo of the G13 with drag-and-drop targets, profile tiles
       along the bottom (after Logitech Gaming Software)
"""
from __future__ import annotations

import logging

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gdk, GLib, Gtk  # noqa: E402

from g13d import __version__  # noqa: E402
from g13d.config.defaults import default_profile  # noqa: E402
from g13d.config.library import LibraryEntry  # noqa: E402
from g13d.config.loader import ConfigStore  # noqa: E402
from g13d.config.model import GUI_LAYOUTS, MODES, Action, Profile, Settings  # noqa: E402

from .action_editor import ActionEditor  # noqa: E402
from .client import DaemonClient  # noqa: E402
from .device_view import DevicePage  # noqa: E402
from .keymap import action_label, watch_keymap  # noqa: E402
from .keys_page import KeysPage  # noqa: E402
from .lcd_page import LcdPage  # noqa: E402
from .library_panel import LibraryPanel  # noqa: E402
from .macros_page import MacrosPage  # noqa: E402
from .profiles_ui import ProfilesBar, ProfilesSidebar  # noqa: E402
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
.g13-key.g13-drop { box-shadow: 0 0 0 2px @accent_bg_color; }
.g13-preview { border-radius: 6px; }
.g13-step-delay { color: alpha(@view_fg_color, 0.7); }
.g13-dragging { opacity: 0.4; }
.g13-drop { box-shadow: inset 0 2px 0 0 @accent_bg_color; }

/* device layout: overlays on the photo */
.g13-device-key { padding: 0; min-width: 0; min-height: 0; background: none; border: none; box-shadow: none; }
.g13-device-key .g13-cap { background: alpha(black, 0.55); border-radius: 5px; padding: 0 5px; min-height: 0; }
.g13-device-key:hover .g13-cap { background: alpha(black, 0.85); box-shadow: 0 0 0 2px alpha(white, 0.6); }
.g13-pill { background: alpha(@view_bg_color, 0.94); color: @view_fg_color; border-radius: 4px;
            padding: 0 5px; min-height: 0; border: 1px solid alpha(@view_fg_color, 0.3); }
.g13-device-key.g13-bound .g13-pill { border-color: alpha(@accent_color, 0.7); }
.g13-device-key.g13-inactive .g13-pill { color: alpha(@view_fg_color, 0.5); border-style: dashed; }
.g13-device-key.g13-pressed .g13-cap { background: @accent_bg_color; box-shadow: 0 0 8px 2px @accent_bg_color; }
.g13-device-key.g13-drop .g13-cap { box-shadow: 0 0 0 3px @accent_bg_color; }
.g13-device-key.g13-drop { box-shadow: none; }
.g13-mode-key .g13-cap { background: alpha(black, 0.3); opacity: 0.45; }
.g13-mode-key.g13-mode-active .g13-cap { background: alpha(black, 0.75); opacity: 1; box-shadow: 0 0 6px 1px alpha(white, 0.25); }
.g13-mode-key:disabled .g13-cap { opacity: 0.35; }

/* device layout: profile tiles */
.g13-tile { padding: 4px 6px; min-width: 72px; border-radius: 8px; }
.g13-tile-selected { background: alpha(@accent_bg_color, 0.25); box-shadow: inset 0 0 0 1px @accent_bg_color; }
.g13-tile-add { min-height: 60px; }
.g13-tile-picture { border-radius: 6px; }
.g13-badge { background: alpha(@view_bg_color, 0.9); border-radius: 10px; padding: 2px; margin: 2px;
             box-shadow: 0 0 2px alpha(black, 0.4); }
.g13-pill-detached { padding: 1px 7px; border-color: alpha(@accent_color, 0.7); }
"""


class MainWindow(Adw.ApplicationWindow):
    def __init__(self, app: Adw.Application, client: DaemonClient, store: ConfigStore, layout: str | None = None):
        super().__init__(application=app, title="G13 Configuration", default_width=1120, default_height=760)
        self._client = client
        self._store = store
        self._profiles: dict[str, Profile] = {}
        self._profile: Profile | None = None
        self._settings: Settings = store.load_settings()
        self._library = store.load_library()
        self._layout = layout if layout in GUI_LAYOUTS else self._settings.gui_layout
        self._mode = 1
        self._reload_timer = 0
        self._updating = False
        self._seen_daemon_profile: str | None = None
        self._seen_daemon_mode: int | None = None
        self._macros: MacrosPage | None = None

        provider = Gtk.CssProvider()
        provider.load_from_string(CSS)
        Gtk.StyleContext.add_provider_for_display(Gdk.Display.get_default(), provider,
                                                  Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
        self._toasts = Adw.ToastOverlay()
        self.set_content(self._toasts)
        self._build()

        # The compositor hands GTK the real keyboard layout only once the window has had focus:
        # refresh the layout-aware labels whenever we (re)gain it.
        watch_keymap(self.refresh_labels)
        self.connect("notify::is-active", lambda *_: self.refresh_labels())
        client.connect("changed", lambda *_: self._sync_from_daemon())
        client.connect("key-event", self._on_key_event)
        client.connect("error", lambda _c, msg: self.toast(msg))
        self._load_profiles()
        self._sync_from_daemon()

    # ---- building ------------------------------------------------------------------------
    @property
    def layout(self) -> str:
        return self._layout

    def set_layout(self, name: str) -> None:
        if name not in GUI_LAYOUTS or name == self._layout:
            return
        self._layout = name
        self._settings.gui_layout = name
        self._store.save_settings(self._settings)
        self._build()
        self._rebuild_list()
        if self._profile is not None:
            self._select_profile(self._profile.name, activate=False)
        self._sync_from_daemon()

    def _build(self) -> None:
        """(Re)create everything under the toast overlay for the current layout."""
        if self._macros is not None:
            self._macros.detach_window_controller(self)
        header = Adw.HeaderBar()
        self._stack = Adw.ViewStack()
        switcher = Adw.ViewSwitcher(stack=self._stack, policy=Adw.ViewSwitcherPolicy.WIDE)
        header.set_title_widget(switcher)
        menu_btn = Gtk.MenuButton(icon_name="open-menu-symbolic", menu_model=self._menu())
        header.pack_end(menu_btn)
        content = Adw.ToolbarView()
        content.add_top_bar(header)
        self._banner = Adw.Banner(title="g13d is not running", button_label="Start", revealed=False)
        self._banner.connect("button-clicked", lambda *_: self._client.start_daemon())
        content.add_top_bar(self._banner)

        self._stick = StickPage(self._profile_changed)
        self._lcd = LcdPage(self._profile_changed, self._client.set_backlight)
        self._macros = MacrosPage(self._store, self._client, self.toast, self._macros_changed, self._retarget)
        self._macros.attach_window_controller(self)
        self._library_panel: LibraryPanel | None = None

        if self._layout == "lgs":
            self._keys = DevicePage(self._edit_control, self._mode_selected, self._drop_action,
                                    lambda: self.show_tab("stick"), self._label_for, self._unassign)
            keys_widget: Gtk.Widget = self._keys
            self._profiles_ui = ProfilesBar(self._profile_picked, self._profile_command)
            content.add_bottom_bar(self._profiles_ui)
            self._library_panel = LibraryPanel(self._library_new, self._library_edit, self._library_rename, self._library_remove)
            side = Adw.ToolbarView()
            side_header = Adw.HeaderBar(show_end_title_buttons=False)
            side_header.set_title_widget(Gtk.Label(label="Assignments", css_classes=["heading"]))
            side.add_top_bar(side_header)
            side.set_content(self._library_panel)
            split = Adw.OverlaySplitView(sidebar=side, content=content, min_sidebar_width=220, max_sidebar_width=320,
                                         sidebar_width_fraction=0.24)
            toggle = Gtk.ToggleButton(icon_name="sidebar-show-symbolic", tooltip_text="Show or hide the assignments")
            split.bind_property("show-sidebar", toggle, "active", 3)  # bidirectional | sync-create
            header.pack_start(toggle)
            root: Gtk.Widget = split
        else:
            self._keys = KeysPage(self._edit_control, self._mode_selected, self._drop_action, self._label_for, self._unassign)
            keys_widget = Gtk.ScrolledWindow(child=self._keys, hscrollbar_policy=Gtk.PolicyType.AUTOMATIC)
            self._profiles_ui = ProfilesSidebar(self._profile_picked, self._profile_command)
            nav = Adw.NavigationSplitView(min_sidebar_width=200, max_sidebar_width=260)
            nav.set_sidebar(Adw.NavigationPage(child=self._profiles_ui, title="Profiles"))
            nav.set_content(Adw.NavigationPage(child=content, title="G13"))
            root = nav

        self._stack.add_titled_with_icon(keys_widget, "keys", "Keys", "input-keyboard-symbolic")
        self._stack.add_titled_with_icon(self._stick, "stick", "Stick", "input-gaming-symbolic")
        self._stack.add_titled_with_icon(self._lcd, "lcd", "LCD & Light", "video-display-symbolic")
        self._stack.add_titled_with_icon(self._macros, "macros", "Macros", "media-record-symbolic")
        content.set_content(self._stack)
        self._status = self._profiles_ui.status
        self._toasts.set_child(root)
        self._keys.set_mode(self._mode)
        self._lcd.set_mode(self._mode)
        self._refresh_library()

    # ---- helpers ------------------------------------------------------------------
    def toast(self, message: str) -> None:
        self._toasts.add_toast(Adw.Toast(title=message, timeout=4))

    def _menu(self):
        from gi.repository import Gio
        menu = Gio.Menu()
        layout = Gio.Menu()
        layout.append("GTK", "app.layout::gtk")
        layout.append("LGS", "app.layout::lgs")
        menu.append_submenu("Layout", layout)
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
        if self._library.absorb(self._profiles.values()):
            self._store.save_library(self._library)
            self._refresh_library()
        wanted = self._profile.name if self._profile else self._client.profile
        self._rebuild_list()
        self._select_profile(wanted if wanted in self._profiles else next(iter(self._profiles)), activate=False)

    def _rebuild_list(self) -> None:
        self._profiles_ui.rebuild(self._profiles, self._settings.default_profile, self._client.profile,
                                  self._profile.name if self._profile else "")

    def _select_profile(self, name: str, activate: bool) -> None:
        self._profile = self._profiles.get(name)
        self._profiles_ui.select(name)
        self._updating = True
        self._keys.set_profile(self._profile)
        self._stick.set_profile(self._profile)
        self._lcd.set_profile(self._profile)
        self._updating = False
        if activate and self._client.available and name != self._client.profile:
            self._client.set_profile(name)

    def _profile_picked(self, name: str) -> None:
        self._select_profile(name, activate=True)

    def _profile_command(self, cmd: str, name: str) -> None:
        prof = self._profiles.get(name) or self._profile
        match cmd:
            case "new":
                self._ask_name("New profile", "Default", lambda n: self._create(default_profile(n)))
            case "duplicate" if prof:
                self._ask_name("Duplicate profile", f"{prof.name} copy", lambda n: self._create(prof.copy(n)))
            case "rename" if prof:
                self._rename_profile(prof)
            case "delete" if prof:
                self._delete_profile(prof.name)
            case "default" if prof:
                self._set_default(prof.name)
            case "icon" if prof:
                self._pick_icon(prof)
            case "icon-clear" if prof:
                prof.icon = ""
                self._store.save_profile(prof)
                self._rebuild_list()

    def _set_default(self, name: str) -> None:
        self._settings.default_profile = "" if self._settings.default_profile == name else name
        self._store.save_settings(self._settings)
        self._rebuild_list()
        self._schedule_reload()
        self.toast(f"“{name}” is the default profile" if self._settings.default_profile else "No default profile: the last used one is restored")

    def _rename_profile(self, old: Profile) -> None:
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

    def _pick_icon(self, prof: Profile) -> None:
        dlg = Gtk.FileDialog(title=f"Icon for “{prof.name}”")
        flt = Gtk.FileFilter()
        flt.set_name("Images")
        flt.add_mime_type("image/*")
        dlg.set_default_filter(flt)

        def done(d, res):
            try:
                f = d.open_finish(res)
            except GLib.Error:
                return
            if f is not None and f.get_path():
                prof.icon = f.get_path()
                self._store.save_profile(prof)
                self._rebuild_list()
        dlg.open(self, None, done)

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

    def _delete_profile(self, name: str) -> None:
        if len(self._profiles) <= 1:
            self.toast("Keep at least one profile")
            return
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
                if self._profile is not None and self._profile.name == name:
                    self._profile = None
                self._load_profiles()
                self._retarget("profile", name, None)
                self._schedule_reload()
        dlg.connect("response", on_resp)
        dlg.present(self)

    def _retarget(self, kind: str, old: str, new: str | None) -> None:
        """A profile or macro was renamed/deleted: fix every binding and library entry that pointed at it."""
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
        if self._library.retarget(kind, old, new):
            self._store.save_library(self._library)
        self._keys.refresh()
        self._refresh_library()

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

    def _editor(self, title: str, action: Action, on_save, on_unassign=None) -> ActionEditor:
        pages = self._client.available_pages or ["status", "clock", "system", "media", "text", "blank"]
        macros = sorted(self._store.load_macros())
        return ActionEditor(title, action, macros, sorted(self._profiles), pages, on_save, on_unassign)

    def _edit_control(self, control: str) -> None:
        if self._profile is None:
            return
        action = self._profile.binding(self._mode, control)

        def on_save(new: Action) -> None:
            self._assign(control, new)
        self._editor(control, action, on_save, (lambda: self._unassign(control)) if action.type != "none" else None).present(self)

    def _unassign(self, control: str) -> None:
        if self._profile is None or self._profile.binding(self._mode, control).type == "none":
            return
        self._assign(control, Action.none())
        self.toast(f"{control} unassigned (M{self._mode})")

    def _assign(self, control: str, action: Action) -> None:
        assert self._profile is not None
        self._profile.set_binding(self._mode, control, action)
        self._keys.refresh()
        self._profile_changed()
        self._library_add(action)

    def _drop_action(self, control: str, action: Action) -> bool:
        """An assignment was dropped on a key."""
        if self._profile is None:
            return False
        self._assign(control, action)
        self.toast(f"{control} → {action_label(action)}  (M{self._mode})")
        return True

    def _profile_changed(self) -> None:
        if self._updating or self._profile is None:
            return
        self._store.save_profile(self._profile)
        self._schedule_reload()
        self._keys.refresh()          # backlight colour of the legends, stick mode on the directions

    def _macros_changed(self) -> None:
        self._schedule_reload()
        self._refresh_library()

    def _schedule_reload(self) -> None:
        if self._reload_timer:
            GLib.source_remove(self._reload_timer)
        self._reload_timer = GLib.timeout_add(300, self._do_reload)

    def _do_reload(self) -> bool:
        self._reload_timer = 0
        if self._client.available:
            self._client.reload()
        return False

    # ---- assignment library ----------------------------------------------------------------
    def _label_for(self, action: Action) -> str:
        """What a key shows: the library name of its assignment, else the layout-aware label."""
        entry = self._library.find(action)
        return entry.label if entry is not None else action_label(action)

    def _refresh_library(self) -> None:
        if self._library_panel is not None:
            self._library_panel.set_library(self._library, list(self._store.load_macros()))

    def _library_add(self, action: Action) -> None:
        if self._library.add(action) is not None:
            self._store.save_library(self._library)
            self._refresh_library()

    def _library_new(self) -> None:
        self._editor("New assignment", Action.none(), self._library_add).present(self)

    def _library_edit(self, entry: LibraryEntry) -> None:
        def on_save(new: Action) -> None:
            if new.type == "none":
                self.toast("Choose an action, or remove the entry instead")
            elif self._library.replace(entry.action, new):
                self._store.save_library(self._library)
                self._refresh_library()
            else:
                self.toast("That assignment is already in the library")
        self._editor(entry.label, entry.action, on_save).present(self)

    def _library_rename(self, entry: LibraryEntry, label: str) -> None:
        if self._library.rename(entry.action, label):
            self._store.save_library(self._library)
            self._refresh_library()

    def _library_remove(self, entry: LibraryEntry) -> None:
        if self._library.remove(entry.action):
            self._store.save_library(self._library)
            self._refresh_library()

    # ---- misc -----------------------------------------------------------------------------
    def refresh_labels(self) -> None:
        self._keys.refresh()
        self._macros.refresh_labels()
        if self._library_panel is not None:
            self._library_panel.refresh_labels()

    def show_mode(self, mode: int) -> None:
        self._seen_daemon_mode = self._client.mode   # do not let the first daemon sync override the request
        self._mode = mode
        self._keys.set_mode(mode)
        self._lcd.set_mode(mode)

    def show_tab(self, name: str) -> None:
        self._stack.set_visible_child_name(name)

    def reload_all(self) -> None:
        self._library = self._store.load_library()
        self._load_profiles()
        self._macros.reload()
        self._refresh_library()
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
        self._profiles_ui.set_active(c.profile)
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
