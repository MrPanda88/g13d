"""How the steps of a macro are drawn, three styles chosen in the editor ([gui] macro_style):

flow     drawn glyphs (arrow into / out of a keycap, stopwatch); waits are slim connector rows between the keys
icons    system icons in coloured badges (go-bottom = press onto a key, go-top = release, alarm = wait)
timeline flow + a piano-roll of the macro (one lane per key, bars from press to release) and its total duration

In every style a key is a keycap in its own colour (a press and its release match at a glance) that can be clicked
to change the key, and a coloured stripe tells press / release / tap apart.
"""
from __future__ import annotations

import math
import zlib
from collections.abc import Callable

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gdk, Gtk  # noqa: E402

from g13d.config.macro import Step  # noqa: E402
from g13d.config.macro_edit import merge_taps  # noqa: E402
from g13d.config.model import MACRO_STYLES  # noqa: E402

from .dnd import make_reorderable  # noqa: E402
from .keymap import key_label  # noqa: E402
from .widgets import info_button  # noqa: E402

STYLE_LABELS = {"flow": "Flow", "icons": "Icons", "timeline": "Timeline"}
assert tuple(STYLE_LABELS) == MACRO_STYLES

KIND_RGB = {"press": (0.21, 0.52, 0.89), "release": (0.90, 0.38, 0.0), "tap": (0.57, 0.25, 0.67),
            "delay": (0.5, 0.5, 0.5)}
KIND_WORD = {"press": "Press", "release": "Release", "tap": "Tap", "delay": "Wait"}

CSS = """
.g13-badge-kind { border-radius: 99px; padding: 6px; min-width: 20px; min-height: 20px; color: white; }
.g13-badge-press { background: #3584e4; }
.g13-badge-release { background: #e66100; }
.g13-badge-tap { background: #9141ac; }
.g13-badge-delay { background: alpha(@view_fg_color, 0.15); color: @view_fg_color; }
.g13-stripe-press { box-shadow: inset 4px 0 0 0 #3584e4; }
.g13-stripe-release { box-shadow: inset 4px 0 0 0 #e66100; }
.g13-stripe-tap { box-shadow: inset 4px 0 0 0 #9141ac; }
button.g13-keycap { border: 1px solid alpha(@view_fg_color, 0.35); border-bottom-width: 3px; border-radius: 6px;
                    padding: 1px 8px; min-height: 0; font-weight: bold; background: alpha(@view_fg_color, 0.04); }
.g13-kind-word { font-weight: bold; min-width: 64px; }
row.g13-wait-row { min-height: 0; background: alpha(@view_fg_color, 0.03); }
row.g13-wait-row > box.header { min-height: 30px; padding-top: 0; padding-bottom: 0; }
row.g13-wait-row spinbutton { min-height: 24px; }
row.g13-wait-row spinbutton > button, row.g13-wait-row > box.header button { min-height: 22px; min-width: 22px; padding: 0; }
.g13-timeline { background: alpha(@view_fg_color, 0.04); border-radius: 10px; margin-bottom: 12px; }
"""
# the insertion mark: an accent line under (after) or over (before) a row, on top of its kind stripe
for _cls, _y in (("after", "-3px"), ("before", "3px")):
    CSS += f"row.g13-insert-{_cls} {{ box-shadow: inset 0 {_y} 0 0 @accent_bg_color; }}\n"
    for _kind, _rgb in (("press", "#3584e4"), ("release", "#e66100"), ("tap", "#9141ac")):
        CSS += (f"row.g13-stripe-{_kind}.g13-insert-{_cls} {{ box-shadow: inset 4px 0 0 0 {_rgb}, "
                f"inset 0 {_y} 0 0 @accent_bg_color; }}\n")
_css_done = False


def install_css() -> None:
    global _css_done
    if _css_done:
        return
    provider = Gtk.CssProvider()
    provider.load_from_string(CSS)
    Gtk.StyleContext.add_provider_for_display(Gdk.Display.get_default(), provider,
                                              Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION + 1)
    _css_done = True


def key_rgb(key: str) -> tuple[float, float, float]:
    """A stable, fairly saturated colour per key (press and release of one key share it)."""
    h = (zlib.crc32(key.encode()) % 360) / 360
    s, v = 0.6, 0.85
    i = int(h * 6)
    f = h * 6 - i
    p, q, t = v * (1 - s), v * (1 - f * s), v * (1 - (1 - f) * s)
    return [(v, t, p), (q, v, p), (p, v, t), (p, q, v), (t, p, v), (v, p, q)][i % 6]


def _hex(rgb) -> str:
    return "#%02x%02x%02x" % tuple(int(c * 255) for c in rgb)


# ---- drawn glyph ------------------------------------------------------------------------------
class StepGlyph(Gtk.DrawingArea):
    """Arrow into a keycap (press), out of it (release), both (tap), or a stopwatch (wait). Mouse buttons get a
    mouse instead of the keycap."""

    def __init__(self, step: Step, size: int = 34):
        super().__init__(content_width=size, content_height=size, valign=Gtk.Align.CENTER)
        self._step = step
        self.set_draw_func(self._draw)

    def _draw(self, _a, cr, w, h) -> None:
        kind = self._step.kind
        fg = self.get_color()
        r, g, b = KIND_RGB[kind]
        if kind == "delay":
            self._stopwatch(cr, w, h, fg)
            return
        mouse = self._step.key.startswith("BTN_")
        # the key (or the mouse) on the bottom half
        cr.set_source_rgba(fg.red, fg.green, fg.blue, 0.85)
        cr.set_line_width(2)
        if mouse:
            _round_rect(cr, w * 0.3, h * 0.5, w * 0.4, h * 0.46, w * 0.2)
            cr.stroke()
            cr.move_to(w * 0.5, h * 0.5)
            cr.line_to(w * 0.5, h * 0.7)
            cr.stroke()
        else:
            _round_rect(cr, w * 0.14, h * 0.62, w * 0.72, h * 0.32, 4)
            cr.stroke()
        # the arrow above it
        cr.set_source_rgb(r, g, b)
        x = w * 0.5
        if kind == "tap":
            _arrow(cr, x - w * 0.15, h * 0.04, h * 0.52, down=True, width=w * 0.26)
            _arrow(cr, x + w * 0.15, h * 0.04, h * 0.52, down=False, width=w * 0.26)
        else:
            _arrow(cr, x, h * 0.02, h * 0.56, down=kind == "press", width=w * 0.5)

    @staticmethod
    def _stopwatch(cr, w, h, fg) -> None:
        cx, cy, rad = w / 2, h * 0.57, min(w, h) * 0.36
        cr.set_source_rgba(fg.red, fg.green, fg.blue, 0.7)
        cr.set_line_width(2)
        cr.arc(cx, cy, rad, 0, 2 * math.pi)
        cr.stroke()
        cr.rectangle(cx - w * 0.08, h * 0.06, w * 0.16, h * 0.09)
        cr.fill()
        cr.move_to(cx, cy)
        cr.line_to(cx + rad * 0.55, cy - rad * 0.55)
        cr.stroke()


def _arrow(cr, x, y0, y1, down: bool, width: float) -> None:
    """A fat arrow between y0 and y1, pointing down or up."""
    shaft = width * 0.38
    head = (y1 - y0) * 0.5
    if down:
        pts = [(x - shaft / 2, y0), (x + shaft / 2, y0), (x + shaft / 2, y1 - head), (x + width / 2, y1 - head),
               (x, y1), (x - width / 2, y1 - head), (x - shaft / 2, y1 - head)]
    else:
        pts = [(x - shaft / 2, y1), (x + shaft / 2, y1), (x + shaft / 2, y0 + head), (x + width / 2, y0 + head),
               (x, y0), (x - width / 2, y0 + head), (x - shaft / 2, y0 + head)]
    cr.move_to(*pts[0])
    for p in pts[1:]:
        cr.line_to(*p)
    cr.close_path()
    cr.fill()


def _round_rect(cr, x, y, w, h, r) -> None:
    cr.new_sub_path()
    cr.arc(x + w - r, y + r, r, -math.pi / 2, 0)
    cr.arc(x + w - r, y + h - r, r, 0, math.pi / 2)
    cr.arc(x + r, y + h - r, r, math.pi / 2, math.pi)
    cr.arc(x + r, y + r, r, math.pi, 3 * math.pi / 2)
    cr.close_path()


# ---- timeline ---------------------------------------------------------------------------------
STEP_PX = 10        # every key event takes a little room even without a wait, so simultaneous events stay readable


def timeline(steps: list[Step]) -> tuple[list[str], list[tuple[str, float, float, bool]], int, list[float]]:
    """(lanes, bars (key, x0, x1, tap), total ms, event positions); x in "ms + STEP_PX per event" units."""
    lanes: list[str] = []
    bars = []
    open_: dict[str, float] = {}
    t = 0.0
    total = 0
    events = []
    for s in steps:
        if s.kind == "delay":
            t += s.ms
            total += s.ms
            continue
        if s.key not in lanes:
            lanes.append(s.key)
        events.append(t)
        if s.kind == "press":
            open_[s.key] = t
        elif s.kind == "release":
            bars.append((s.key, open_.pop(s.key, t), t, False))
        else:
            bars.append((s.key, t, t, True))
        t += STEP_PX
    for k, x0 in open_.items():
        bars.append((k, x0, t, False))
    return lanes, bars, total, events


class Timeline(Gtk.DrawingArea):
    LANE, LEFT, TOP = 22, 90, 8

    def __init__(self):
        super().__init__(css_classes=["g13-timeline"], hexpand=True)
        self._steps: list[Step] = []
        self.set_draw_func(self._draw)

    def set_steps(self, steps: list[Step]) -> None:
        self._steps = list(steps)
        lanes = timeline(self._steps)[0]
        self.set_content_height(self.TOP * 2 + max(1, len(lanes)) * self.LANE + 18)
        self.queue_draw()

    def _draw(self, _a, cr, w, h) -> None:
        lanes, bars, total, _ = timeline(self._steps)
        fg = self.get_color()
        span = max((b[2] for b in bars), default=1) or 1
        scale = (w - self.LEFT - 16) / max(span, 1)
        cr.select_font_face("Sans")
        cr.set_font_size(11)
        for i, key in enumerate(lanes):
            y = self.TOP + i * self.LANE
            cr.set_source_rgba(fg.red, fg.green, fg.blue, 0.06 if i % 2 else 0.0)
            cr.rectangle(0, y, w, self.LANE)
            cr.fill()
            cr.set_source_rgba(fg.red, fg.green, fg.blue, 0.8)
            cr.move_to(10, y + 15)
            cr.show_text(key_label(key)[:12])
        for key, x0, x1, tap in bars:
            i = lanes.index(key)
            y = self.TOP + i * self.LANE + 4
            cr.set_source_rgb(*key_rgb(key))
            px0 = self.LEFT + x0 * scale
            pw = max(6.0, (x1 - x0) * scale)
            _round_rect(cr, px0, y, pw, self.LANE - 8, 3)
            cr.fill()
        # axis: total duration
        cr.set_source_rgba(fg.red, fg.green, fg.blue, 0.6)
        cr.move_to(self.LEFT, h - 6)
        cr.show_text("0")
        txt = f"{total} ms" if total < 2000 else f"{total / 1000:.2f} s"
        ext = cr.text_extents(txt)
        cr.move_to(w - 16 - ext.width, h - 6)
        cr.show_text(txt)


# ---- rows ------------------------------------------------------------------------------------
class Callbacks:
    def __init__(self, move: Callable[[int, int], None], remove: Callable[[int], None],
                 set_delay: Callable[[int, int], None], change_key: Callable[[int], None]):
        self.move, self.remove, self.set_delay, self.change_key = move, remove, set_delay, change_key


def _move_buttons(row: Adw.ActionRow, i: int, n: int, cb: Callbacks, compact: bool = False) -> None:
    up = Gtk.Button(icon_name="go-up-symbolic", css_classes=["flat"], valign=Gtk.Align.CENTER, sensitive=i > 0)
    up.connect("clicked", lambda *_: cb.move(i, i - 1))
    down = Gtk.Button(icon_name="go-down-symbolic", css_classes=["flat"], valign=Gtk.Align.CENTER, sensitive=i < n - 1)
    down.connect("clicked", lambda *_: cb.move(i, i + 1))
    rm = Gtk.Button(icon_name="edit-delete-symbolic", css_classes=["flat"], valign=Gtk.Align.CENTER, tooltip_text="Remove")
    rm.connect("clicked", lambda *_: cb.remove(i))
    for b in (up, down, rm):
        if compact:
            b.add_css_class("circular")
        row.add_suffix(b)


def _spin(step: Step, i: int, cb: Callbacks) -> Gtk.SpinButton:
    spin = Gtk.SpinButton.new_with_range(0, 60000, 10)
    spin.set_value(step.ms)
    spin.set_valign(Gtk.Align.CENTER)
    spin.connect("value-changed", lambda s: cb.set_delay(i, int(s.get_value())))
    return spin


def _keycap(step: Step, i: int, cb: Callbacks) -> Gtk.Button:
    """The key, in its own colour; a click changes it (and its press / release partner)."""
    btn = Gtk.Button(label=key_label(step.key), css_classes=["g13-keycap"], valign=Gtk.Align.CENTER,
                     tooltip_text="Change the key" + ("" if step.kind == "tap" else " (its press and release together)"))
    btn.get_child().set_use_markup(False)
    rgb = _hex(key_rgb(step.key))
    prov = Gtk.CssProvider()
    prov.load_from_string(f"button {{ border-color: {rgb}; background: alpha({rgb}, 0.18); }}")
    btn.get_style_context().add_provider(prov, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION + 2)
    btn.connect("clicked", lambda *_: cb.change_key(i))
    return btn


def _prefix(row: Adw.ActionRow, *widgets: Gtk.Widget, spacing: int = 10) -> None:
    """One box for every prefix: Adw.ActionRow.add_prefix stacks them right to left."""
    box = Gtk.Box(spacing=spacing, valign=Gtk.Align.CENTER)
    for w in widgets:
        box.append(w)
    row.add_prefix(box)


def _handle() -> Gtk.Image:
    img = Gtk.Image.new_from_icon_name("list-drag-handle-symbolic")
    img.add_css_class("dim-label")
    return img


def _word(step: Step) -> Gtk.Label:
    return Gtk.Label(label=KIND_WORD[step.kind], css_classes=["g13-kind-word"], xalign=0)


def row_icons(step: Step, i: int, n: int, cb: Callbacks) -> Adw.ActionRow:
    row = Adw.ActionRow(use_markup=False)
    icon = {"press": "go-bottom-symbolic", "release": "go-top-symbolic", "tap": "media-playlist-repeat-symbolic",
            "delay": "alarm-symbolic"}[step.kind]
    badge = Gtk.Image.new_from_icon_name(icon)
    badge.set_pixel_size(20)
    badge.add_css_class("g13-badge-kind")
    badge.add_css_class("g13-badge-" + step.kind)
    badge.set_valign(Gtk.Align.CENTER)
    if step.kind == "delay":
        _prefix(row, _handle(), badge, _word(step), _spin(step, i, cb), Gtk.Label(label="ms", css_classes=["dim-label"]))
    else:
        row.add_css_class("g13-stripe-" + step.kind)
        _prefix(row, _handle(), badge, _word(step), _keycap(step, i, cb))
    _move_buttons(row, i, n, cb)
    return row


def row_flow(step: Step, i: int, n: int, cb: Callbacks) -> Adw.ActionRow:
    row = Adw.ActionRow(use_markup=False)
    if step.kind == "delay":
        # slim connector: indented, small, subordinate to the key rows around it
        row.add_css_class("g13-wait-row")
        spin = _spin(step, i, cb)
        spin.add_css_class("flat")
        glyph = StepGlyph(step, 22)
        glyph.set_margin_start(30)
        _prefix(row, _handle(), glyph, spin, Gtk.Label(label="ms", css_classes=["dim-label"]), spacing=6)
        _move_buttons(row, i, n, cb, compact=True)
        return row
    row.add_css_class("g13-stripe-" + step.kind)
    _prefix(row, _handle(), StepGlyph(step), _word(step), _keycap(step, i, cb))
    _move_buttons(row, i, n, cb)
    return row


def render(listbox: Gtk.ListBox, steps: list[Step], cb: Callbacks, style: str) -> None:
    install_css()
    while (row := listbox.get_first_child()) is not None:
        listbox.remove(row)
    make = row_icons if style == "icons" else row_flow
    for i, step in enumerate(steps):
        row = make(step, i, len(steps), cb)
        listbox.append(row)
        make_reorderable(listbox, row, i, cb.move)


# ---- simplify menu ------------------------------------------------------------------------------
def simplify_menu(get_steps: Callable[[], list[Step] | None], set_steps: Callable[[list[Step]], None]) -> Gtk.MenuButton:
    """Changes to every step at once: the waits, and press + release pairs into taps."""
    btn = Gtk.MenuButton(label="Simplify", tooltip_text="Change every wait, or turn press + release into taps")
    pop = Gtk.Popover()
    box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4, margin_top=6, margin_bottom=6, margin_start=6, margin_end=6)

    def apply(f):
        steps = get_steps()
        if steps is None:
            return
        pop.popdown()
        set_steps(f(steps))

    def each(f):
        """A function of one step (None drops it) as a function of the list."""
        return lambda steps: [s for s in (f(s) for s in steps) if s is not None]

    def item(label, f, info=None):
        b = Gtk.Button(label=label, css_classes=["flat"], hexpand=True)
        b.get_child().set_xalign(0)
        b.connect("clicked", lambda *_: apply(f))
        if info is None:
            box.append(b)
            return
        line = Gtk.Box(spacing=2)
        line.append(b)
        line.append(info_button(info))
        box.append(line)

    def title(text):
        box.append(Gtk.Label(label=text, css_classes=["caption", "dim-label"], xalign=0))
    title("Keys")
    item("Press + release → Tap", merge_taps,
         "For typing: each key becomes a tap where it was pressed and its release goes, even when fast typing "
         "overlapped two keys. Kept as they are: Shift, Ctrl, Alt and Super (they change the keys pressed "
         "meanwhile), mouse buttons, and keys held 400 ms or more")
    box.append(Gtk.Separator(margin_top=4, margin_bottom=4))
    title("Waits")
    item("Faster (waits ÷ 2)", each(lambda s: Step.delay(s.ms // 2) if s.kind == "delay" else s))
    item("Slower (waits × 2)", each(lambda s: Step.delay(s.ms * 2) if s.kind == "delay" else s))
    item("Remove all waits", each(lambda s: None if s.kind == "delay" else s))
    row = Gtk.Box(spacing=4)
    spin = Gtk.SpinButton.new_with_range(0, 10000, 10)
    spin.set_value(50)
    row.append(Gtk.Label(label="Set all to"))
    row.append(spin)
    ok = Gtk.Button(label="ms", css_classes=["suggested-action"])
    ok.connect("clicked", lambda *_: apply(each(lambda s: Step.delay(int(spin.get_value())) if s.kind == "delay" else s)))
    row.append(ok)
    box.append(row)
    pop.set_child(box)
    btn.set_popover(pop)
    return btn
