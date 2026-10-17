"""LCD & light tab: backlight colour, LCD page list (toggle, reorder, drag) with a faithful preview."""
from __future__ import annotations

from collections.abc import Callable

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gdk, GdkPixbuf, GLib, Gtk  # noqa: E402
from PIL import ImageDraw  # noqa: E402

from g13d.config.model import Profile  # noqa: E402
from g13d.lcd.framebuffer import HEIGHT, WIDTH, new_image  # noqa: E402
from g13d.lcd.pages import BUILTIN  # noqa: E402

from .dnd import make_reorderable  # noqa: E402
from .widgets import WidePage  # noqa: E402

_PAGE_TITLES = {"status": "Status", "clock": "Clock", "system": "System", "media": "Media", "text": "Text", "blank": "Blank"}
_PAGE_SUBTITLES = {"status": "Profile, mode and time. LCD keys: M1 M2 M3, next profile",
                   "clock": "Big clock and date",
                   "system": "CPU, temperature, memory, network",
                   "media": "Now playing (MPRIS). LCD keys: previous, play/pause, next, next player",
                   "text": "Free text sent with: g13ctl lcd-text -s 0 \"…\"",
                   "blank": "All pixels off"}


class _Ctx:
    def __init__(self, profile: str, mode: int):
        self.profile_name, self.mode, self.recording, self.connected = profile, mode, False, True

    def set_mode(self, m): ...
    def cycle_profile(self, d): ...


def render_preview(page_name: str, profile_name: str, mode: int, backlight: tuple[int, int, int], scale: int = 2) -> Gdk.Texture | None:
    """Render a page exactly like the daemon does; lit pixels are dark on the backlit panel."""
    cls = BUILTIN.get(page_name)
    if cls is None:
        return None
    page = cls()
    img = new_image()
    try:
        page.render(ImageDraw.Draw(img), img, _Ctx(profile_name, mode))
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
    def __init__(self, on_change: Callable[[], None], on_live_backlight: Callable[[int, int, int], None]):
        super().__init__()
        self._on_change = on_change
        self._on_live = on_live_backlight
        self._profile: Profile | None = None
        self._updating = False
        self._mode = 1

        g = Adw.PreferencesGroup(title="Backlight")
        self.add(g)
        row = Adw.ActionRow(title="Colour", subtitle="Applied when this profile is active")
        self._color = Gtk.ColorDialogButton(dialog=Gtk.ColorDialog(with_alpha=False), valign=Gtk.Align.CENTER)
        self._color.connect("notify::rgba", self._color_changed)
        row.add_suffix(self._color)
        g.add(row)

        self._pages_group = Adw.PreferencesGroup(
            title="LCD pages", description="Pages shown on the panel, in this order; the round button cycles them. Drag to reorder.")
        self.add(self._pages_group)
        self._rows: dict[str, Adw.SwitchRow] = {}
        self._list = Gtk.ListBox(css_classes=["boxed-list"], selection_mode=Gtk.SelectionMode.NONE)
        self._pages_group.add(self._list)

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
    def set_profile(self, profile: Profile | None) -> None:
        self._profile = profile
        if profile is None:
            return
        if hasattr(self, "_order"):
            del self._order
        self._updating = True
        rgba = Gdk.RGBA()
        rgba.red, rgba.green, rgba.blue = (c / 255 for c in profile.backlight)
        rgba.alpha = 1.0
        self._color.set_rgba(rgba)
        self._rebuild_pages()
        self._updating = False
        self._refresh_preview()

    def set_mode(self, mode: int) -> None:
        self._mode = mode
        self._refresh_preview()

    def _full_order(self) -> list[str]:
        """All pages in display order: the enabled ones first (profile order), then the disabled ones."""
        assert self._profile is not None
        if not hasattr(self, "_order") or set(self._order) != set(BUILTIN):
            self._order = list(self._profile.lcd_pages) + [p for p in BUILTIN if p not in self._profile.lcd_pages]
        return self._order

    def _rebuild_pages(self) -> None:
        while (child := self._list.get_first_child()) is not None:
            self._list.remove(child)
        self._rows = {}
        assert self._profile is not None
        order = self._full_order()
        for i, name in enumerate(order):
            row = Adw.SwitchRow(title=_PAGE_TITLES.get(name, name), subtitle=_PAGE_SUBTITLES.get(name, name), use_markup=False)
            row.page_name = name  # type: ignore[attr-defined]
            row.set_active(name in self._profile.lcd_pages)
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
        if self._updating or self._profile is None:
            return
        self._apply()

    def _move(self, src: int, dest: int) -> None:
        order = self._full_order()
        if 0 <= src < len(order) and 0 <= dest < len(order) and src != dest:
            order.insert(dest, order.pop(src))
            self._apply()

    def _apply(self) -> None:
        if self._profile is None:
            return
        enabled = {n for n, r in self._rows.items() if r.get_active()}
        self._profile.lcd_pages = [n for n in self._full_order() if n in enabled] or ["status"]
        self._updating = True
        self._rebuild_pages()
        self._updating = False
        self._on_change()

    def _color_changed(self, *_: object) -> None:
        if self._updating or self._profile is None:
            return
        c = self._color.get_rgba()
        rgb = (round(c.red * 255), round(c.green * 255), round(c.blue * 255))
        self._profile.backlight = rgb
        self._on_live(*rgb)
        self._on_change()
        self._refresh_preview()

    def _refresh_preview(self) -> None:
        name = self._preview_select.get_active_name() or "status"
        tex = render_preview(name, self._profile.name if self._profile else "Profile", self._mode,
                             self._profile.backlight if self._profile else (51, 153, 255))
        if tex is not None:
            self._picture.set_paintable(tex)
