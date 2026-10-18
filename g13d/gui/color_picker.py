"""Backlight colour picker: hue ring + saturation/value triangle, R G B sliders, preset swatches."""
from __future__ import annotations

import colorsys
import math
from collections.abc import Callable

import cairo
import gi

gi.require_version("Gtk", "4.0")
from gi.repository import Gtk  # noqa: E402

from .widgets import SliderRow  # noqa: E402

RGB = tuple[int, int, int]

PRESETS: list[RGB] = [
    (255, 255, 255), (170, 170, 170), (255, 0, 0), (255, 96, 0), (255, 160, 0), (255, 255, 0), (160, 255, 0),
    (0, 255, 0), (0, 255, 96), (0, 255, 160),
    (96, 96, 96), (48, 48, 48), (255, 0, 160), (255, 0, 255), (160, 0, 255), (96, 0, 255), (0, 0, 255),
    (0, 96, 255), (0, 160, 255), (0, 255, 255),
]


class HueTriangle(Gtk.DrawingArea):
    """A hue ring around a saturation/value triangle that turns with the hue. Values in 0..1."""

    RING = 0.16          # ring thickness as a fraction of the radius

    def __init__(self, on_change: Callable[[], None]):
        super().__init__(content_width=200, content_height=200, halign=Gtk.Align.CENTER)
        self._on_change = on_change
        self.h, self.s, self.v = 0.6, 1.0, 1.0
        self._zone: str | None = None
        self.set_draw_func(self._draw)
        drag = Gtk.GestureDrag()
        drag.connect("drag-begin", self._begin)
        drag.connect("drag-update", self._update)
        drag.connect("drag-end", lambda *_: setattr(self, "_zone", None))
        self.add_controller(drag)
        self._ring_cache: tuple[int, cairo.ImageSurface] | None = None

    # ---- geometry -------------------------------------------------------------------
    def _geom(self) -> tuple[float, float, float, float]:
        w, h = self.get_width(), self.get_height()
        r = min(w, h) / 2 - 2
        return w / 2, h / 2, r, r * (1 - self.RING) - 3      # centre, outer radius, triangle radius

    def _vertices(self, cx: float, cy: float, tr: float) -> list[tuple[float, float]]:
        a = self.h * 2 * math.pi - math.pi / 2                 # pure hue points at the hue on the ring
        return [(cx + tr * math.cos(a + k * 2 * math.pi / 3), cy + tr * math.sin(a + k * 2 * math.pi / 3)) for k in range(3)]

    # ---- drawing ----------------------------------------------------------------------
    def _ring(self, size: int, cx: float, cy: float, r: float) -> cairo.ImageSurface:
        if self._ring_cache and self._ring_cache[0] == size:
            return self._ring_cache[1]
        surf = cairo.ImageSurface(cairo.FORMAT_ARGB32, size, size)
        c = cairo.Context(surf)
        inner = r * (1 - self.RING)
        steps = 180
        for i in range(steps):
            a0, a1 = 2 * math.pi * i / steps - math.pi / 2, 2 * math.pi * (i + 1.3) / steps - math.pi / 2
            c.set_source_rgb(*colorsys.hsv_to_rgb(i / steps, 1, 1))
            c.arc(cx, cy, r, a0, a1)
            c.arc_negative(cx, cy, inner, a1, a0)
            c.close_path()
            c.fill()
        self._ring_cache = (size, surf)
        return surf

    def _draw(self, _area, c: cairo.Context, w: int, h: int) -> None:
        cx, cy, r, tr = self._geom()
        c.set_source_surface(self._ring(min(w, h), cx, cy, r), 0, 0)
        c.paint()
        # triangle: hue vertex, white, black (Gouraud via a mesh pattern)
        (hx, hy), (wx, wy), (bx, by) = self._vertices(cx, cy, tr)
        mesh = cairo.MeshPattern()
        mesh.begin_patch()
        mesh.move_to(hx, hy)
        mesh.line_to(wx, wy)
        mesh.line_to(bx, by)
        mesh.set_corner_color_rgb(0, *colorsys.hsv_to_rgb(self.h, 1, 1))
        mesh.set_corner_color_rgb(1, 1, 1, 1)
        mesh.set_corner_color_rgb(2, 0, 0, 0)
        mesh.end_patch()
        c.set_source(mesh)
        c.move_to(hx, hy)
        c.line_to(wx, wy)
        c.line_to(bx, by)
        c.close_path()
        c.fill()
        # markers
        a = self.h * 2 * math.pi - math.pi / 2
        mr = r * (1 - self.RING / 2)
        self._marker(c, cx + mr * math.cos(a), cy + mr * math.sin(a))
        self._marker(c, *self._sv_to_xy(cx, cy, tr))

    @staticmethod
    def _marker(c: cairo.Context, x: float, y: float) -> None:
        c.set_line_width(2)
        c.arc(x, y, 5, 0, 2 * math.pi)
        c.set_source_rgb(1, 1, 1)
        c.stroke_preserve()
        c.set_source_rgba(0, 0, 0, 0.6)
        c.set_line_width(1)
        c.stroke()

    def _sv_to_xy(self, cx: float, cy: float, tr: float) -> tuple[float, float]:
        (hx, hy), (wx, wy), (bx, by) = self._vertices(cx, cy, tr)
        # point = black + v * ((white + s * (hue - white)) - black)
        px, py = wx + self.s * (hx - wx), wy + self.s * (hy - wy)
        return bx + self.v * (px - bx), by + self.v * (py - by)

    def _xy_to_sv(self, x: float, y: float, cx: float, cy: float, tr: float) -> tuple[float, float]:
        (hx, hy), (wx, wy), (bx, by) = self._vertices(cx, cy, tr)
        # barycentric coordinates (hue, white, black)
        det = (wy - by) * (hx - bx) + (bx - wx) * (hy - by)
        lh = ((wy - by) * (x - bx) + (bx - wx) * (y - by)) / det
        lw = ((by - hy) * (x - bx) + (hx - bx) * (y - by)) / det
        lb = 1 - lh - lw
        lh, lw, lb = (max(0.0, v) for v in (lh, lw, lb))
        total = lh + lw + lb or 1.0
        lh, lw, lb = lh / total, lw / total, lb / total
        v = 1 - lb
        s = lh / v if v > 1e-6 else 0.0
        return min(1.0, max(0.0, s)), min(1.0, max(0.0, v))

    # ---- input ------------------------------------------------------------------------
    def _begin(self, _g, x: float, y: float) -> None:
        cx, cy, r, tr = self._geom()
        d = math.hypot(x - cx, y - cy)
        self._zone = "ring" if d > tr + 2 else "triangle"
        self._start = (x, y)
        self._apply(x, y)

    def _update(self, _g, dx: float, dy: float) -> None:
        if self._zone:
            self._apply(self._start[0] + dx, self._start[1] + dy)

    def _apply(self, x: float, y: float) -> None:
        cx, cy, r, tr = self._geom()
        if self._zone == "ring":
            self.h = (math.atan2(y - cy, x - cx) + math.pi / 2) / (2 * math.pi) % 1.0
        else:
            self.s, self.v = self._xy_to_sv(x, y, cx, cy, tr)
        self.queue_draw()
        self._on_change()

    def set_hsv(self, h: float, s: float, v: float) -> None:
        self.h, self.s, self.v = h, s, v
        self.queue_draw()


class Swatch(Gtk.Button):
    def __init__(self, rgb: RGB, on_pick: Callable[[RGB], None]):
        super().__init__(css_classes=["flat", "g13-swatch"], tooltip_text="#%02x%02x%02x" % rgb)
        area = Gtk.DrawingArea(content_width=22, content_height=22)
        area.set_draw_func(lambda _a, c, w, h: (c.set_source_rgb(*(v / 255 for v in rgb)), c.rectangle(0, 0, w, h), c.fill()))
        self.set_child(area)
        self.connect("clicked", lambda *_: on_pick(rgb))


class ColorPicker(Gtk.Box):
    """Wheel + triangle, R G B sliders and presets, all kept in sync. on_change(rgb) on every change."""

    def __init__(self, on_change: Callable[[RGB], None]):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        self._on_change = on_change
        self._updating = False
        self._rgb: RGB = (51, 153, 255)

        self._wheel = HueTriangle(self._from_wheel)
        self.append(self._wheel)

        sliders = Gtk.ListBox(css_classes=["boxed-list"], selection_mode=Gtk.SelectionMode.NONE)
        self._sliders: list[SliderRow] = []
        for name, colour in (("Red", "#e01b24"), ("Green", "#2ec27e"), ("Blue", "#1c71d8")):
            row = SliderRow(name, "", 0, 255, 1, lambda _v: self._from_sliders())
            dot = Gtk.DrawingArea(content_width=12, content_height=12, valign=Gtk.Align.CENTER)
            r, g, b = (int(colour[i:i + 2], 16) / 255 for i in (1, 3, 5))
            dot.set_draw_func(lambda _a, c, w, h, r=r, g=g, b=b: (c.set_source_rgb(r, g, b), c.arc(w / 2, h / 2, 5, 0, 6.3), c.fill()))
            row.add_prefix(dot)
            self._sliders.append(row)
            sliders.append(row)
        self.append(sliders)

        grid = Gtk.FlowBox(max_children_per_line=10, min_children_per_line=10, selection_mode=Gtk.SelectionMode.NONE,
                           halign=Gtk.Align.CENTER, column_spacing=4, row_spacing=4, homogeneous=True)
        for rgb in PRESETS:
            grid.append(Swatch(rgb, self.set_rgb))
        self.append(grid)

    # ---- state --------------------------------------------------------------------------
    @property
    def rgb(self) -> RGB:
        return self._rgb

    def set_rgb(self, rgb: RGB, notify: bool = True) -> None:
        self._rgb = tuple(max(0, min(255, int(v))) for v in rgb)  # type: ignore[assignment]
        self._updating = True
        for row, v in zip(self._sliders, self._rgb):
            row.value = v
        h, s, v = colorsys.rgb_to_hsv(*(c / 255 for c in self._rgb))
        self._wheel.set_hsv(h, s, v)
        self._updating = False
        if notify:
            self._on_change(self._rgb)

    def _from_wheel(self) -> None:
        if self._updating:
            return
        r, g, b = colorsys.hsv_to_rgb(self._wheel.h, self._wheel.s, self._wheel.v)
        self._rgb = (round(r * 255), round(g * 255), round(b * 255))
        self._updating = True
        for row, v in zip(self._sliders, self._rgb):
            row.value = v
        self._updating = False
        self._on_change(self._rgb)

    def _from_sliders(self) -> None:
        if self._updating:
            return
        self._rgb = tuple(int(row.value) for row in self._sliders)  # type: ignore[assignment]
        h, s, v = colorsys.rgb_to_hsv(*(c / 255 for c in self._rgb))
        self._updating = True
        self._wheel.set_hsv(h, s, v)
        self._updating = False
        self._on_change(self._rgb)

