"""Main window. Two layouts, switched live from the menu:

- lgs (default): assignment library on the left, the photo of the G13 with drag-and-drop targets, profile tiles
       along the bottom (after Logitech Gaming Software); no Macros tab: a macro is created and edited from
       the library, its editor taking the place of the photo
- gtk: profile sidebar on the left, Keys / Stick / LCD & Light / Macros tabs, schematic keypad
"""
from __future__ import annotations

import logging
import threading
from importlib.resources import files

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gdk, GLib, Gtk  # noqa: E402

from g13d import __version__  # noqa: E402
from g13d.config.appicons import find_icon, is_auto_icon  # noqa: E402
from g13d.config.library import LibraryEntry  # noqa: E402
from g13d.config.loader import ConfigStore  # noqa: E402
from g13d.config.macro import Macro  # noqa: E402
from g13d.config.model import GUI_LAYOUTS, MODES, Action, Profile, Settings, order_profiles  # noqa: E402
from g13d.config.scope import ProfileScope  # noqa: E402

from .action_editor import ActionEditor  # noqa: E402
from .widgets import end_edit_on_click, focus_entry  # noqa: E402
from .app_dialog import AppDialog  # noqa: E402
from .client import DaemonClient  # noqa: E402
from .device_view import DevicePage  # noqa: E402
from .keymap import action_label, watch_keymap  # noqa: E402
from .keys_page import KeysPage  # noqa: E402
from .lcd_page import LcdPage  # noqa: E402
from .library_panel import LibraryPanel  # noqa: E402
from .macros_page import MacroEditor, MacrosPage, confirm_delete_macro, unique_macro_name  # noqa: E402
from .profiles_ui import ProfilesBar, ProfilesSidebar  # noqa: E402
from .profiles_ui import APP_ICON  # noqa: E402
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
.g13-info { min-width: 24px; min-height: 24px; padding: 0; color: @accent_color; }
.g13-drag-icon { background: @accent_bg_color; color: @accent_fg_color; border-radius: 6px; padding: 4px 10px;
                 margin: 6px; box-shadow: 0 1px 4px alpha(black, 0.5); font-weight: bold; }
.g13-drop { box-shadow: inset 0 2px 0 0 @accent_bg_color; }
.g13-drop-before { box-shadow: inset 0 3px 0 0 @accent_bg_color; }
.g13-drop-after { box-shadow: inset 0 -3px 0 0 @accent_bg_color; }
.g13-drop-left { box-shadow: inset 3px 0 0 0 @accent_bg_color; }
.g13-drop-right { box-shadow: inset -3px 0 0 0 @accent_bg_color; }

/* device layout: overlays on the photo */
.g13-device-key { padding: 0; min-width: 0; min-height: 0; background: none; border: none; box-shadow: none; }
.g13-device-key .g13-cap { background: alpha(black, 0.55); border-radius: 5px; padding: 0 5px; min-height: 0; }
.g13-device-key:hover .g13-cap { background: alpha(black, 0.85); box-shadow: 0 0 0 2px alpha(white, 0.6); }
.g13-pill { background: alpha(@view_bg_color, 0.94); color: @view_fg_color; border-radius: 4px;
            padding: 0 5px; min-height: 0; border: 1px solid alpha(@view_fg_color, 0.3); }
.g13-device-key.g13-bound .g13-pill { border-color: alpha(@accent_color, 0.7); }
.g13-device-key.g13-inactive .g13-pill { color: alpha(@view_fg_color, 0.5); border-style: dashed; }
.navigation-sidebar row.g13-current { background: alpha(@accent_bg_color, 0.25); }
.g13-logo.g13-offline { filter: grayscale(1); opacity: 0.45; }
.g13-device-key:hover .g13-pill { box-shadow: 0 2px 6px alpha(black, 0.6); }
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
.g13-tiles-scrollbar { background: none; }
.g13-tiles-scrollbar slider { min-height: 6px; margin: 1px 0; border: none; background: alpha(@view_fg_color, 0.35); }
.g13-tiles-scrollbar slider:hover { background: alpha(@view_fg_color, 0.55); }
.g13-grid-tile { min-width: 104px; }
.g13-tile-picture { border-radius: 6px; }
.g13-badge { background: alpha(@view_bg_color, 0.9); border-radius: 10px; padding: 2px; margin: 2px;
             box-shadow: 0 0 2px alpha(black, 0.4); }
.g13-pill-detached { padding: 1px 7px; border-color: alpha(@accent_color, 0.7); }
.g13-swatch { padding: 2px; min-width: 0; min-height: 0; border-radius: 4px; }
.g13-swatch:hover { box-shadow: 0 0 0 2px @accent_bg_color; }
"""


class MainWindow(Adw.ApplicationWindow):
    def __init__(self, app: Adw.Application, client: DaemonClient, store: ConfigStore, layout: str | None = None):
        super().__init__(application=app, title="G13 Configuration", default_width=1120, default_height=760)
        self._client = client
        self._store = store
        self._profiles: dict[str, Profile] = {}
        self._profile: Profile | None = None
        self._settings: Settings = store.load_settings()
        self._library = store.load_library()        # the global one; each profile has its own too
        self._scope = ProfileScope(store, lambda: self._profile)
        self._layout = layout if layout in GUI_LAYOUTS else self._settings.gui_layout
        self._mode = 1
        self._reload_timer = 0
        self._updating = False
        self._seen_daemon_profile: str | None = None
        self._seen_daemon_mode: int | None = None
        self._macro_editor: MacroEditor | None = None

        provider = Gtk.CssProvider()
        provider.load_from_string(CSS)
        Gtk.StyleContext.add_provider_for_display(Gdk.Display.get_default(), provider,
                                                  Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
        # the app icon ships in the package: found without an installed icon theme (editable install, no make install)
        Gtk.IconTheme.get_for_display(Gdk.Display.get_default()).add_search_path(str(files("g13d") / "data" / "icons"))
        self._toasts = Adw.ToastOverlay()
        self.set_content(self._toasts)
        self._build()

        # The compositor hands GTK the real keyboard layout only once the window has had focus:
        # refresh the layout-aware labels whenever we (re)gain it.
        watch_keymap(self.refresh_labels)
        self.connect("notify::is-active", lambda *_: self.refresh_labels())
        end_edit_on_click(self)
        client.connect("changed", lambda *_: self._sync_from_daemon())
        client.connect("key-event", self._on_key_event)
        client.connect("error", lambda _c, msg: self.toast(msg))
        client.connect("config-changed", lambda *_: self.reload_all(reload_daemon=False))
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
        if self._macro_editor is not None:
            self._macro_editor.detach_window_controller(self)
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
        self._lcd = LcdPage(self._profile_changed, self._settings_changed, self._client.set_backlight)
        self._macros_page: MacrosPage | None = None
        self._library_panel: LibraryPanel | None = None

        if self._layout == "lgs":
            self._keys = DevicePage(self._edit_control, self._mode_selected, self._drop_action,
                                    lambda: self.show_tab("stick"), self._label_for, self._unassign)
            self._macro_editor = MacroEditor(self._scope, self._client, self.toast, lambda _renamed: self._macros_changed(),
                                             self._retarget, self._settings.gui_macro_style, self._macro_style_changed)
            # the Keys tab shows the G13, or the macro being edited in its place
            self._keys_stack = Gtk.Stack(transition_type=Gtk.StackTransitionType.CROSSFADE)
            self._keys_stack.add_named(self._keys, "device")
            self._keys_stack.add_named(self._macro_screen(), "macro")
            keys_widget: Gtk.Widget = self._keys_stack
            self._profiles_ui = ProfilesBar(self._profile_picked, self._profile_command)
            content.add_bottom_bar(self._profiles_ui)
            self._library_panel = LibraryPanel(self._library_new, self._library_edit, self._library_rename, self._library_remove,
                                               self._macro_command, self._settings.gui_library_sort, self._library_sort_changed,
                                               self._library_scope)
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
            # the assignments panel and the profile tiles only make sense on the Keys tab
            self._sidebar_wanted = True
            self._switching_tab = False

            def tab_changed(*_):
                keys = self._stack.get_visible_child_name() == "keys"
                self._switching_tab = True
                split.set_show_sidebar(keys and self._sidebar_wanted)
                toggle.set_visible(keys)
                self._profiles_ui.set_visible(keys)
                self._switching_tab = False

            def sidebar_toggled(*_):
                if not self._switching_tab and self._stack.get_visible_child_name() == "keys":
                    self._sidebar_wanted = split.get_show_sidebar()
            split.connect("notify::show-sidebar", sidebar_toggled)
            self._stack.connect("notify::visible-child-name", tab_changed)
            root: Gtk.Widget = split
        else:
            self._keys = KeysPage(self._edit_control, self._mode_selected, self._drop_action, self._label_for, self._unassign)
            self._macros_page = MacrosPage(self._scope, self._client, self.toast, self._macros_changed, self._retarget,
                                           self._settings.gui_macro_style, self._macro_style_changed)
            self._macro_editor = self._macros_page.editor
            keys_widget = Gtk.ScrolledWindow(child=self._keys, hscrollbar_policy=Gtk.PolicyType.AUTOMATIC)
            self._profiles_ui = ProfilesSidebar(self._profile_picked, self._profile_command)
            nav = Adw.NavigationSplitView(min_sidebar_width=240, max_sidebar_width=280)
            nav.set_sidebar(Adw.NavigationPage(child=self._profiles_ui, title="Profiles"))
            nav.set_content(Adw.NavigationPage(child=content, title="G13"))
            root = nav

        self._stack.add_titled_with_icon(keys_widget, "keys", "Keys", "input-keyboard-symbolic")
        self._stack.add_titled_with_icon(self._stick, "stick", "Stick", "input-gaming-symbolic")
        self._stack.add_titled_with_icon(self._lcd, "lcd", "LCD & Light", "video-display-symbolic")
        if self._macros_page is not None:
            self._stack.add_titled_with_icon(self._macros_page, "macros", "Macros", "media-record-symbolic")
        self._macro_editor.attach_window_controller(self)
        content.set_content(self._stack)
        self._status = self._profiles_ui.status
        self._toasts.set_child(root)
        self._keys.set_mode(self._mode)
        self._lcd.set_settings(self._settings)
        self._lcd.set_mode(self._mode)
        self._refresh_library()

    # ---- helpers ------------------------------------------------------------------
    def toast(self, message: str) -> None:
        self._toasts.add_toast(Adw.Toast(title=message, timeout=4))

    def _macro_screen(self) -> Gtk.Widget:
        """lgs layout: the macro editor with a way back to the G13."""
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        bar = Gtk.Box(spacing=6, margin_start=12, margin_end=12, margin_top=8)
        back = Gtk.Button(tooltip_text="Back to the G13 (Esc)")
        inner = Gtk.Box(spacing=6)
        inner.append(Gtk.Image.new_from_icon_name("go-previous-symbolic"))
        inner.append(Gtk.Label(label="G13"))
        back.set_child(inner)
        back.connect("clicked", lambda *_: self._close_macro())
        bar.append(back)
        bar.append(Gtk.Label(label="Macro", css_classes=["title-4"], hexpand=True))
        for icon, tip, cmd in (("edit-copy-symbolic", "Duplicate", "duplicate"), ("user-trash-symbolic", "Delete…", "delete")):
            b = Gtk.Button(icon_name=icon, tooltip_text=tip, css_classes=["flat"])
            b.connect("clicked", lambda _b, c=cmd: self._macro_editor.current is not None and
                      self._macro_command(c, self._macro_editor.current.name))
            bar.append(b)
        box.append(bar)
        box.append(self._macro_editor)
        esc = Gtk.ShortcutController()
        esc.add_shortcut(Gtk.Shortcut.new(Gtk.ShortcutTrigger.parse_string("Escape"),
                                          Gtk.CallbackAction.new(lambda *_: (self._close_macro(), True)[1])))
        box.add_controller(esc)
        return box

    def _menu(self):
        from gi.repository import Gio
        menu = Gio.Menu()
        layout = Gio.Menu()
        layout.append("LGS", "app.layout::lgs")
        layout.append("GTK", "app.layout::gtk")
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
        for prof in self._profiles.values():
            if prof.library.absorb([prof], skip=self._library):
                self._store.save_profile(prof)
        wanted = self._profile.name if self._profile else self._client.profile
        self._rebuild_list()
        self._select_profile(wanted if wanted in self._profiles else next(iter(self._profiles)), activate=False)

    def _ordered(self) -> list[str]:
        return order_profiles(self._profiles, self._settings.profile_order)

    def _rebuild_list(self) -> None:
        ordered = {n: self._profiles[n] for n in self._ordered()}
        self._profiles_ui.rebuild(ordered, self._settings.default_profile, self._client.profile,
                                  self._profile.name if self._profile else "")

    def _move_profile(self, src: int, dest: int) -> None:
        """Reorder (drag or menu): the full order is saved so the daemon and the LCD follow."""
        names = self._ordered()
        if not (0 <= src < len(names) and 0 <= dest < len(names)) or src == dest:
            return
        names.insert(dest, names.pop(src))
        self._settings.profile_order = names
        self._store.save_settings(self._settings)
        self._rebuild_list()
        self._schedule_reload()

    def _select_profile(self, name: str, activate: bool) -> None:
        if self._profile is not None and self._profile.name != name:
            # the macro being edited belongs to the profile we leave: save it there, then let it go
            leaving = self._macro_editor.current.name if self._macro_editor.current is not None else None
            self._macro_editor.edit(None)
        else:
            leaving = None
        self._profile = self._profiles.get(name)
        self._profiles_ui.select(name)
        self._updating = True
        self._keys.set_profile(self._profile)
        self._stick.set_profile(self._profile)
        self._lcd.set_profile(self._profile, self._ordered())
        self._updating = False
        if self._editing_macro_lgs():
            # stay in the editor: the new profile's macro by the same name, else its first one, else an empty editor
            macros = self._scope.load_macros()
            pick = leaving if leaving in macros else (sorted(macros, key=str.casefold) or [None])[0]
            if pick is not None:
                self._open_macro(macros[pick])
        self._refresh_library()
        if self._macros_page is not None:
            self._macros_page.reload()
        if activate and self._client.available and name != self._client.profile:
            self._client.set_profile(name)

    def _profile_picked(self, name: str) -> None:
        self._select_profile(name, activate=True)

    def _profile_command(self, cmd: str, name: str) -> None:
        prof = self._profiles.get(name) or self._profile
        if cmd.startswith("move:"):
            _, src, dest = cmd.split(":")
            self._move_profile(int(src), int(dest))
            return
        if cmd in ("move-up", "move-down") and prof:
            i = self._ordered().index(prof.name)
            self._move_profile(i, i - 1 if cmd == "move-up" else i + 1)
            return
        match cmd:
            case "new":
                self._new_profile_dialog()
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
            case "icon-find" if prof:
                self._find_icon(prof, manual=True)
            case "icon-clear" if prof:
                prof.icon = ""
                self._store.save_profile(prof)
                self._rebuild_list()
            case "app" if prof:
                self.link_app_dialog(prof.name)
            case "lock" if prof:
                if not self._client.available:
                    self.toast("g13d is not running")
                else:
                    self._client.set_locked_profile("" if self._client.locked_profile == prof.name else prof.name)

    def _new_profile_dialog(self) -> None:
        """Name + the profile to start from: the default profile when there is one, else an empty profile."""
        names = self._ordered()
        choices = ["Empty profile (no assignment)"] + names
        dlg = Adw.AlertDialog(heading="New profile")
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        entry = Gtk.Entry(placeholder_text="Name", activates_default=True)
        box.append(entry)
        based = Adw.ComboRow(title="Based on", model=Gtk.StringList.new(choices))
        default = self._settings.default_profile
        based.set_selected(1 + names.index(default) if default in names else 0)
        group = Gtk.ListBox(css_classes=["boxed-list"], selection_mode=Gtk.SelectionMode.NONE)
        group.append(based)
        box.append(group)
        dlg.set_extra_child(box)
        dlg.add_response("cancel", "Cancel")
        dlg.add_response("ok", "Create")
        dlg.set_default_response("ok")
        dlg.set_response_appearance("ok", Adw.ResponseAppearance.SUGGESTED)

        def on_resp(_d, resp):
            name = entry.get_text().strip()
            if resp != "ok" or not name:
                return
            if name in self._profiles:
                self.toast(f"A profile named “{name}” already exists")
                return
            i = based.get_selected()
            if i == 0:
                prof = Profile(name=name, backlight=(51, 153, 255))
            else:
                prof = self._profiles[names[i - 1]].copy(name)
                prof.app = ""            # one application, one profile
            self._create(prof)
        dlg.connect("response", on_resp)
        dlg.present(self)
        focus_entry(entry)

    def link_app_dialog(self, name: str) -> None:
        prof = self._profiles.get(name)
        if prof is None:
            return

        def save(rule: str, steam_appid: int | None) -> None:
            prof.app = rule
            self._store.save_profile(prof)
            self._rebuild_list()
            self._schedule_reload()
            self.toast(f"“{prof.name}” linked to {rule}" if rule else f"“{prof.name}” no longer linked to an application")
            if rule and is_auto_icon(prof.icon, self._store.icons_dir):
                self._find_icon(prof, steam_appid=steam_appid)
        AppDialog(prof, self._client, save, self.toast).present(self)

    def _find_icon(self, prof: Profile, steam_appid: int | None = None, manual: bool = False) -> None:
        """Look up the linked application's icon in a thread (files + Steam's CDN). Automatic lookups keep an icon
        the user chose; the menu command replaces it."""
        rule, name = prof.app, prof.name
        if not rule:
            self.toast(f"Link “{name}” to an application first (Application…)")
            return

        def done(icon: str) -> bool:
            current = self._profiles.get(name)
            if current is None or current.app != rule or (not manual and not is_auto_icon(current.icon, self._store.icons_dir)):
                return False
            if icon:
                current.icon = icon
                self._store.save_profile(current)
                self._rebuild_list()
                self._schedule_reload()
            elif manual:
                self.toast(f"No icon found for {rule}")
            return False

        def run(appid: int | None) -> None:
            threading.Thread(target=lambda: GLib.idle_add(done, find_icon(rule, self._store.icons_dir, appid)),
                             daemon=True).start()

        if steam_appid is not None or not manual:
            run(steam_appid)
            return

        # a native game's process name says nothing about Steam: ask the running windows for its SteamAppId
        def from_windows(apps: list[dict]) -> None:
            ids = [a.get("steam_appid", "") for a in apps if a.get("key", "").casefold() == rule.casefold()]
            run(next((int(i) for i in ids if i.isdigit()), None))
        self._client.list_apps(from_windows)

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

    def _retarget(self, kind: str, old: str, new: str | None, everywhere: bool = True) -> None:
        """A profile or macro was renamed/deleted: fix every binding and library entry that pointed at it. A macro
        of the selected profile only concerns that profile (everywhere=False); a global one, every profile that
        has no macro of its own by that name."""
        for prof in self._profiles.values():
            if kind == "macro" and (prof is not self._profile if not everywhere else old in prof.macros):
                continue
            touched = prof.library.retarget(kind, old, new)
            for mode in MODES:
                for control, action in list(prof.modes.get(mode, {}).items()):
                    if action.type == kind and action.name == old:
                        prof.set_binding(mode, control, Action.none() if new is None else
                                         (Action.profile(new) if kind == "profile" else Action.macro(new)))
                        touched = True
            if touched:
                self._store.save_profile(prof)
        if (kind != "macro" or everywhere) and self._library.retarget(kind, old, new):
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
        focus_entry(entry)

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
        """The one assignment editor: for a key or a library entry, with the library name of the action."""
        pages = self._client.available_pages or ["status", "clock", "system", "media", "text", "blank"]
        macros = sorted(self._scope.load_macros())
        entry = self._find_entry(action)
        return ActionEditor(title, action, macros, self._ordered(), pages, on_save, on_unassign, entry.label if entry else "")

    def _edit_control(self, control: str) -> None:
        if self._profile is None:
            return
        action = self._profile.binding(self._mode, control)

        def on_save(new: Action, label: str) -> None:
            self._assign(control, new, label)
        self._editor(control, action, on_save, (lambda: self._unassign(control)) if action.type != "none" else None).present(self)

    def _unassign(self, control: str) -> None:
        if self._profile is None or self._profile.binding(self._mode, control).type == "none":
            return
        self._assign(control, Action.none())
        self.toast(f"{control} unassigned (M{self._mode})")

    def _assign(self, control: str, action: Action, label: str = "") -> None:
        assert self._profile is not None
        self._profile.set_binding(self._mode, control, action)
        self._library_add(action, label)
        self._keys.refresh()
        self._profile_changed()

    def _drop_action(self, control: str, action: Action, source: str | None = None) -> bool:
        """An assignment was dropped on a key: from the library, or from the key `source` (a move: that key
        ends up unassigned, whatever `control` had is replaced)."""
        if self._profile is None or source == control:
            return False
        if source is not None:
            self._profile.set_binding(self._mode, source, Action.none())
        self._assign(control, action)
        self.toast(f"{source or action_label(action)} → {control}  (M{self._mode})")
        return True

    def _profile_changed(self) -> None:
        if self._updating or self._profile is None:
            return
        self._store.save_profile(self._profile)
        self._schedule_reload()
        self._keys.refresh()          # backlight colour of the legends, stick mode on the directions

    def _settings_changed(self) -> None:
        """LCD pages / options (global) were edited in the GUI."""
        self._store.save_settings(self._settings)
        self._schedule_reload()

    def _library_sort_changed(self, order: str) -> None:
        self._settings.gui_library_sort = order
        self._store.save_settings(self._settings)

    def _macro_style_changed(self, style: str) -> None:
        self._settings.gui_macro_style = style
        self._store.save_settings(self._settings)

    def _macros_changed(self) -> None:
        self._schedule_reload()
        self._refresh_library()

    # ---- macros (lgs layout: from the library, edited in place of the G13) ---------------------
    def _macro_command(self, cmd: str, name: str) -> None:
        macros = self._scope.load_macros()
        match cmd:
            case "new":
                macro = Macro(unique_macro_name("New macro", macros))
                self._scope.save_macro(macro)
                self._macros_changed()
                self._open_macro(macro)
                self._macro_editor.focus_name()
            case "edit" if name in macros:
                self._open_macro(macros[name])
            case "select" if name in macros and self._editing_macro_lgs():
                self._open_macro(macros[name])
            case "duplicate" if name in macros:
                macro = macros[name].copy(unique_macro_name(f"{name} copy", macros))
                self._scope.save_macro(macro)
                self._macros_changed()
                self._open_macro(macro)
            case "delete" if name in macros:
                def delete() -> None:
                    current = self._macro_editor.current
                    if current is not None and current.name == name:
                        self._close_macro()
                    is_global = self._scope.is_global_macro(name)
                    self._scope.delete_macro(name)
                    self._retarget("macro", name, None, is_global)
                    self._macros_changed()
                confirm_delete_macro(self, name, delete)
            case "make-global" if self._profile is not None and name in self._profile.macros:
                self._macro_make_global(name)
            case "make-local" if self._scope.is_global_macro(name):
                self._macro_make_local(name)

    def _macro_make_global(self, name: str) -> None:
        """Move a macro of the selected profile to the global ones. Identical copies in other profiles (duplicated
        profiles) merge into it; a different macro by the same name elsewhere blocks the move."""
        macro = self._profile.macros[name]
        clash = [p.name for p in self._profiles.values() if name in p.macros and p.macros[name].to_toml() != macro.to_toml()]
        if clash:
            self.toast(f"Other macros are named “{name}” in: {', '.join(clash)}. Rename one first")
            return
        self._close_macro_named(name)
        self._store.save_macro(macro)
        for prof in self._profiles.values():
            if prof.macros.pop(name, None) is not None:
                self._store.save_profile(prof)
        self._macros_changed()
        self.toast(f"“{name}” is global: every profile has it")

    def _macro_make_local(self, name: str) -> None:
        """Give the global macro back to the profiles: the selected one, and every other one whose keys use it."""
        macro = self._store.load_macros()[name]
        self._close_macro_named(name)
        for prof in self._profiles.values():
            uses = any(a == Action.macro(name) for m in MODES for a in prof.modes.get(m, {}).values())
            if (prof is self._profile or uses) and name not in prof.macros:
                prof.macros[name] = macro.copy()
                self._store.save_profile(prof)
        self._store.delete_macro(name)
        self._macros_changed()
        self.toast(f"“{name}” now belongs to “{self._profile.name}”" if self._profile else f"“{name}” is no longer global")

    def _close_macro_named(self, name: str) -> None:
        current = self._macro_editor.current
        if current is not None and current.name == name:
            if self._macros_page is not None:
                self._macro_editor.edit(None)
            else:
                self._close_macro()

    def _open_macro(self, macro: Macro) -> None:
        if self._macros_page is not None:      # gtk layout: the Macros tab
            self._macro_editor.edit(macro)
            self._macros_page.reload()
            self.show_tab("macros")
            return
        self._macro_editor.edit(macro)
        self.show_tab("keys")
        self._keys_stack.set_visible_child_name("macro")
        self._library_panel.set_current_macro(macro.name)

    def _close_macro(self) -> None:
        """Back to the G13 picture (stops a recording, saves pending changes)."""
        self._macro_editor.edit(None)
        if self._macros_page is None:
            self._keys_stack.set_visible_child_name("device")
            self._library_panel.set_current_macro(None)

    def _editing_macro_lgs(self) -> bool:
        """lgs layout with the macro editor in place of the G13 picture."""
        return self._macros_page is None and self._keys_stack.get_visible_child_name() == "macro"

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
    def _find_entry(self, action: Action) -> LibraryEntry | None:
        """The library entry of `action`: the selected profile's own first, then the global one."""
        own = self._profile.library.find(action) if self._profile is not None else None
        return own or self._library.find(action)

    def _owner(self, entry: LibraryEntry):
        """(library holding `entry`, save function)."""
        if any(e is entry for e in self._library.entries) or self._profile is None:
            return self._library, lambda: self._store.save_library(self._library)
        prof = self._profile
        return prof.library, lambda: self._store.save_profile(prof)

    def _label_for(self, action: Action) -> str:
        """What a key shows: the library name of its assignment, else the layout-aware label."""
        entry = self._find_entry(action)
        return entry.label if entry is not None else action_label(action)

    def _refresh_library(self) -> None:
        if self._library_panel is None:
            return
        own = self._profile.library.entries if self._profile is not None else []
        entries = [(e, False) for e in own] + [(e, True) for e in self._library.entries
                                               if self._profile is None or self._profile.library.find(e.action) is None]
        macros = [(n, self._scope.is_global_macro(n)) for n in self._scope.load_macros()]
        current = self._macro_editor.current if self._editing_macro_lgs() else None
        self._library_panel.set_current_macro(current.name if current is not None else None)    # follows a rename
        self._library_panel.set_library(entries, macros)

    def _library_changed(self) -> None:
        self._refresh_library()
        self._keys.refresh()

    def _library_add(self, action: Action, label: str = "") -> None:
        """Make sure `action` is in the library (the selected profile's, unless it is global), named `label` when one
        is given (renames an existing entry)."""
        if action.type in ("none", "macro") or self._profile is None:
            return
        entry = self._find_entry(action)
        if entry is None:
            changed = self._profile.library.add(action, label) is not None
            save = lambda: self._store.save_profile(self._profile)   # noqa: E731
        else:
            lib, save = self._owner(entry)
            changed = bool(label) and lib.rename(action, label)
        if changed:
            save()
            self._library_changed()

    def _library_new(self) -> None:
        def on_save(action: Action, label: str) -> None:
            if action.type == "none":
                self.toast("Choose an action")
            elif self._find_entry(action) is not None:
                self.toast("That assignment is already in the library")
            else:
                self._library_add(action, label)
        self._editor("New assignment", Action.none(), on_save).present(self)

    def _library_edit(self, entry: LibraryEntry) -> None:
        lib, save = self._owner(entry)

        def on_save(new: Action, label: str) -> None:
            if new.type == "none":
                self.toast("Choose an action, or remove the entry instead")
                return
            if new != entry.action and (self._find_entry(new) is not None or not lib.replace(entry.action, new)):
                self.toast("That assignment is already in the library")
                return
            lib.rename(new, label)
            save()
            self._library_changed()
        self._editor(entry.label, entry.action, on_save).present(self)

    def _library_rename(self, entry: LibraryEntry, label: str) -> None:
        lib, save = self._owner(entry)
        if lib.rename(entry.action, label):
            save()
            self._library_changed()

    def _library_remove(self, entry: LibraryEntry) -> None:
        lib, save = self._owner(entry)
        if lib.remove(entry.action):
            save()
            self._library_changed()

    def _library_scope(self, entry: LibraryEntry, to_global: bool) -> None:
        """Global: the entry leaves every profile's library for the global one. Local: it goes back to the selected
        profile and to every profile whose keys use it, under the same name."""
        if to_global:
            for prof in self._profiles.values():
                if prof.library.remove(entry.action):
                    self._store.save_profile(prof)
            self._library.add(entry.action, entry.label)
            self._store.save_library(self._library)
        else:
            self._library.remove(entry.action)
            self._store.save_library(self._library)
            for prof in self._profiles.values():
                uses = any(a == entry.action for m in MODES for a in prof.modes.get(m, {}).values())
                if (prof is self._profile or uses) and prof.library.add(entry.action, entry.label) is not None:
                    self._store.save_profile(prof)
        self._library_changed()
        self._schedule_reload()

    # ---- misc -----------------------------------------------------------------------------
    def refresh_labels(self) -> None:
        self._keys.refresh()
        self._macro_editor.refresh_labels()
        if self._library_panel is not None:
            self._library_panel.refresh_labels()

    def show_mode(self, mode: int) -> None:
        self._seen_daemon_mode = self._client.mode   # do not let the first daemon sync override the request
        self._mode = mode
        self._keys.set_mode(mode)
        self._lcd.set_mode(mode)

    def open_profiles_grid(self) -> None:
        if isinstance(self._profiles_ui, ProfilesBar):
            self._profiles_ui.open_grid()

    def show_tab(self, name: str) -> None:
        if name == "macros" and self._macros_page is None:      # lgs: no tab, the first macro in place of the G13
            if (macros := self._scope.load_macros()):
                self._open_macro(macros[sorted(macros)[0]])
            return
        self._stack.set_visible_child_name(name)

    def reload_all(self, reload_daemon: bool = True) -> None:
        self._library = self._store.load_library()
        self._settings = self._store.load_settings()
        self._lcd.set_settings(self._settings)
        self._load_profiles()
        if self._macros_page is not None:
            self._macros_page.reload()
        elif (current := self._macro_editor.current) is not None:
            macros = self._scope.load_macros()
            if current.name in macros:
                self._macro_editor.edit(macros[current.name])
            else:
                self._close_macro()
        self._refresh_library()
        if reload_daemon:
            self._schedule_reload()

    # ---- daemon state -------------------------------------------------------------------
    def _sync_from_daemon(self) -> None:
        c = self._client
        self._banner.set_revealed(not c.available)
        if c.available:
            dev = "G13 connected" if c.device_connected else "G13 not detected"
            auto = f" (for {c.focused_app})" if c.auto_switched and c.focused_app else (" (automatic)" if c.auto_switched else "")
            lock = " · locked" if c.locked_profile == c.profile else ""
            sep = self._profiles_ui.status_separator
            self._status.set_label(f"{dev}{sep}{c.profile}{auto}{lock} M{c.mode}" + (" · recording" if c.recording else ""))
        else:
            self._status.set_label("daemon not running")
        self._profiles_ui.set_connected(c.available and c.device_connected)
        self._profiles_ui.set_active(c.profile, c.locked_profile)
        if c.available and c.profile and c.profile != self._seen_daemon_profile:
            self._seen_daemon_profile = c.profile
            # follow what the device switched to, but not the automatic per-application switches: the user
            # is probably editing the profile of the application they just left
            if c.profile in self._profiles and not c.auto_switched and (self._profile is None or self._profile.name != c.profile):
                self._select_profile(c.profile, activate=False)
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
            self._macro_editor.toggle_record_from_device()


def about_dialog(parent: Gtk.Window) -> None:
    Adw.AboutDialog(application_name="G13 Configuration", application_icon=APP_ICON, version=__version__,
                    developer_name="g13d contributors", license_type=Gtk.License.MIT_X11,
                    website="https://github.com/MrPanda88/g13d",
                    comments="Native Linux support for the Logitech G13 gameboard.").present(parent)
