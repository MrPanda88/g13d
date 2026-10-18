"""LCD & light tab: backlight colour, LCD page list (toggle, reorder, drag) with a faithful preview."""
from __future__ import annotations

from collections.abc import Callable

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gdk, GdkPixbuf, GLib, Gtk  # noqa: E402
from PIL import ImageDraw  # noqa: E402

from g13d.config.model import Profile, Settings  # noqa: E402
from g13d.lcd.framebuffer import HEIGHT, WIDTH, new_image  # noqa: E402
from g13d.lcd.pages import BUILTIN, page_options  # noqa: E402

from .color_picker import ColorPicker  # noqa: E402
from .dnd import make_reorderable  # noqa: E402
from .widgets import WidePage  # noqa: E402

_PAGE_TITLES = {"status": "Status", "clock": "Clock", "profiles": "Profiles", "system": "System", "media": "Media",
                "text": "Text", "blank": "Blank"}
_PAGE_SUBTITLES = {"status": "Profile, mode and time. LCD keys: M1 M2 M3, next profile",
                   "clock": "Analog dial (style below), time and date",
                   "profiles": "Pick a profile on the panel. LCD keys 1–3 (up, down, activate) are reserved while it is shown",
                   "system": "CPU, temperature, memory, network",
                   "media": "Now playing (MPRIS). LCD keys: previous, play/pause, next, next player",
                   "text": "Free text sent with: g13ctl lcd-text -s 0 \"…\"",
                   "blank": "All pixels off"}


class _Ctx:
    def __init__(self, profile: str, mode: int, profiles: list[str]):
        self.profile_name, self.mode, self.recording, self.connected = profile, mode, False, True
        self.profile_names = profiles or [profile]
        self.focused_app = ""
        self.locked_profile = ""

    def set_mode(self, m): ...
    def cycle_profile(self, d): ...
    def set_profile(self, n): ...
    def set_locked_profile(self, n): ...


def render_preview(page_name: str, profile_name: str, mode: int, backlight: tuple[int, int, int], scale: int = 2,
                   options: dict[str, str] | None = None, profiles: list[str] | None = None) -> Gdk.Texture | None:
    """Render a page exactly like the daemon does; lit pixels are dark on the backlit panel."""
    cls = BUILTIN.get(page_name)
    if cls is None:
        return None
    page = cls()
    page.configure(options or {})
    img = new_image()
    try:
        ctx = _Ctx(profile_name, mode, profiles or [])
        page.shown(ctx)
        page.render(ImageDraw.Draw(img), img, ctx)
    except Exception:  # noqa: BLE001
        pass
    r, g, b = backlight
    # the backlight shines through the panel: never fully dark so the preview stays readable
    bg = (max(r, 40), max(g, 40), max(b, 40))
    rgb = img.convert("RGB").resize((WIDTH * scale, HEIGHT * scale), resample=0)
    px = rgb.load()
    for y in range(rgb.height):
        for x in range(rgb.width):
            px[x, y] = (18, 18, 22) if px[x, y][0] else bg
    data = GLib.Bytes.new(rgb.tobytes())
    pb = GdkPixbuf.Pixbuf.new_from_bytes(data, GdkPixbuf.Colorspace.RGB, False, 8, rgb.width, rgb.height, rgb.width * 3)
    return Gdk.Texture.new_for_pixbuf(pb)


class LcdPage(WidePage):
    def __init__(self, on_change: Callable[[], None], on_settings_change: Callable[[], None],
                 on_live_backlight: Callable[[int, int, int], None]):
        super().__init__()
        self._on_change = on_change
        self._on_settings_change = on_settings_change
        self._on_live = on_live_backlight
        self._settings = Settings()
        self._profile: Profile | None = None
        self._profiles: list[str] = []
        self._updating = False
        self._mode = 1

        g = Adw.PreferencesGroup(title="Backlight", description="Colour of the keys and the LCD while this profile is active. "
                                 "Brightness is the device's own button.")
        self.add(g)
        self._color = ColorPicker(self._color_changed)
        g.add(self._color)
        self._live_timer = 0

        self._pages_group = Adw.PreferencesGroup(
            title="LCD pages", description="Pages shown on the panel whatever the profile, in this order; the round button "
                                           "cycles them. Drag to reorder.")
        self.add(self._pages_group)
        self._rows: dict[str, Adw.SwitchRow] = {}
        self._list = Gtk.ListBox(css_classes=["boxed-list"], selection_mode=Gtk.SelectionMode.NONE)
        self._pages_group.add(self._list)

        og = Adw.PreferencesGroup(title="Page settings")
        self.add(og)
        self._option_rows: dict[str, tuple[Adw.ComboRow, list[str]]] = {}
        for key, (label, choices) in page_options().items():
            row = Adw.ComboRow(title=label, model=Gtk.StringList.new([c[1] for c in choices]))
            values = [c[0] for c in choices]
            row.connect("notify::selected", lambda r, _p, k=key, v=values: self._option_changed(k, v[r.get_selected()]))
            og.add(row)
            self._option_rows[key] = (row, values)

        pg = Adw.PreferencesGroup(title="Preview")
        self.add(pg)
        self._preview_select = Adw.ToggleGroup(halign=Gtk.Align.CENTER, margin_bottom=8)
        for name in BUILTIN:
            self._preview_select.add(Adw.Toggle(label=_PAGE_TITLES.get(name, name), name=name))
        self._preview_select.connect("notify::active-name", lambda *_: self._refresh_preview())
        pg.add(self._preview_select)
        self._picture = Gtk.Picture(halign=Gtk.Align.CENTER, can_shrink=False, margin_bottom=8)
        self._picture.add_css_class("g13-preview")
        pg.add(self._picture)
        self._preview_note = Gtk.Label(css_classes=["dim-label", "caption"], wrap=True, justify=Gtk.Justification.CENTER,
                                       label="Rendered with the same code as the device. Live data (media, system, text) "
                                             "differs from what the daemon currently shows.")
        pg.add(self._preview_note)

    # ---- state --------------------------------------------------------------
    def set_profile(self, profile: Profile | None, profiles: list[str] | None = None) -> None:
        self._profile = profile
        if profiles is not None:
            self._profiles = profiles
        if profile is None:
            return
        self._updating = True
        self._color.set_rgb(profile.backlight, notify=False)
        self._updating = False
        self._refresh_preview()

    def set_settings(self, settings: Settings) -> None:
        self._settings = settings
        if hasattr(self, "_order"):
            del self._order
        self._updating = True
        for key, (row, values) in self._option_rows.items():
            current = settings.lcd_options.get(key, values[0])
            row.set_selected(values.index(current) if current in values else 0)
        self._rebuild_pages()
        self._updating = False
        self._refresh_preview()

    def _option_changed(self, key: str, value: str) -> None:
        if self._updating:
            return
        self._settings.lcd_options[key] = value
        self._on_settings_change()
        self._refresh_preview()

    def set_mode(self, mode: int) -> None:
        self._mode = mode
        self._refresh_preview()

    def _full_order(self) -> list[str]:
        """All pages in display order: the enabled ones first (configured order), then the disabled ones."""
        if not hasattr(self, "_order") or set(self._order) != set(BUILTIN):
            self._order = list(self._settings.lcd_pages) + [p for p in BUILTIN if p not in self._settings.lcd_pages]
        return self._order

    def _rebuild_pages(self) -> None:
        while (child := self._list.get_first_child()) is not None:
            self._list.remove(child)
        self._rows = {}
        order = self._full_order()
        for i, name in enumerate(order):
            row = Adw.SwitchRow(title=_PAGE_TITLES.get(name, name), subtitle=_PAGE_SUBTITLES.get(name, name), use_markup=False)
            row.page_name = name  # type: ignore[attr-defined]
            row.set_active(name in self._settings.lcd_pages)
            row.connect("notify::active", self._pages_changed)
            handle = Gtk.Image.new_from_icon_name("list-drag-handle-symbolic")
            handle.add_css_class("dim-label")
            row.add_prefix(handle)
            up = Gtk.Button(icon_name="go-up-symbolic", valign=Gtk.Align.CENTER, css_classes=["flat"], tooltip_text="Move up", sensitive=i > 0)
            up.connect("clicked", lambda _b, k=i: self._move(k, k - 1))
            down = Gtk.Button(icon_name="go-down-symbolic", valign=Gtk.Align.CENTER, css_classes=["flat"], tooltip_text="Move down",
                              sensitive=i < len(order) - 1)
            down.connect("clicked", lambda _b, k=i: self._move(k, k + 1))
            row.add_suffix(up)
            row.add_suffix(down)
            self._rows[name] = row
            self._list.append(row)
            make_reorderable(self._list, row, i, self._move)

    def _pages_changed(self, *_: object) -> None:
        if self._updating:
            return
        self._apply()

    def _move(self, src: int, dest: int) -> None:
        order = self._full_order()
        if 0 <= src < len(order) and 0 <= dest < len(order) and src != dest:
            order.insert(dest, order.pop(src))
            self._apply()

    def _apply(self) -> None:
        enabled = {n for n, r in self._rows.items() if r.get_active()}
        self._settings.lcd_pages = [n for n in self._full_order() if n in enabled] or ["status"]
        self._updating = True
        self._rebuild_pages()
        self._updating = False
        self._on_settings_change()

    def _color_changed(self, rgb: tuple[int, int, int]) -> None:
        if self._updating or self._profile is None:
            return
        self._profile.backlight = rgb
        # dragging fires many times a second: send the colour to the device at most every 50 ms,
        # and save / reload once the user pauses
        if not self._live_timer:
            self._live_timer = GLib.timeout_add(50, self._push_live)
        self._on_change()
        self._refresh_preview()

    def _push_live(self) -> bool:
        self._live_timer = 0
        if self._profile is not None:
            self._on_live(*self._profile.backlight)
        return False

    def _refresh_preview(self) -> None:
        name = self._preview_select.get_active_name() or "status"
        tex = render_preview(name, self._profile.name if self._profile else "Profile", self._mode,
                             self._profile.backlight if self._profile else (51, 153, 255),
                             options=self._settings.lcd_options, profiles=self._profiles)
        if tex is not None:
            self._picture.set_paintable(tex)
