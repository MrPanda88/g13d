"""The "device" Keys page: the photo of the G13 with clickable, droppable overlays on every control.

DeviceView scales the picture to fit its allocation (aspect ratio kept) and places each overlay from
`device_geometry`, so the overlays never drift when the window is resized.
"""
from __future__ import annotations

from collections.abc import Callable
from importlib.resources import files

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Gdk", "4.0")
gi.require_version("Gsk", "4.0")
gi.require_version("Graphene", "1.0")
from gi.repository import Gdk, Graphene, Gsk, Gtk, Pango  # noqa: E402

from g13d.config.model import STICK_DIRS, Action, Profile  # noqa: E402

from . import device_geometry as geo  # noqa: E402
from .dnd import make_action_target  # noqa: E402
from .keymap import action_label  # noqa: E402

LabelFor = Callable[[Action], str]

TITLES = {"LCD_MENU": "", "LCD1": "", "LCD2": "", "LCD3": "", "LCD4": "",
          "STICK_PRESS": "Click", "STICK_BTN_LEFT": "Side", "STICK_BTN_DOWN": "Bottom",
          "STICK_UP": "Up", "STICK_DOWN": "Down", "STICK_LEFT": "Left", "STICK_RIGHT": "Right"}
STICK_MODE_LABELS = {"mouse": "Mouse", "scroll": "Scroll", "passthrough": "Joystick"}
PILL_PX, CAP_PX = 19, 21          # font sizes at scale 1 (picture shown at its natural size)
PILL_H = 32                       # height reserved above a cap for its assignment pill, at scale 1


def _attrs(px: float, rgb: tuple[int, int, int] | None = None, bold: bool = False) -> Pango.AttrList:
    attrs = Pango.AttrList()
    attrs.insert(Pango.attr_size_new_absolute(int(max(px, 6) * Pango.SCALE)))
    if rgb is not None:
        attrs.insert(Pango.attr_foreground_new(*(c * 257 for c in rgb)))
    if bold:
        attrs.insert(Pango.attr_weight_new(Pango.Weight.BOLD))
    return attrs


class DeviceKey(Gtk.Button):
    """One control: the assignment pill floating above the cap, the cap legend tinted like the backlight."""

    def __init__(self, control: str, on_click: Callable[[str], None], on_drop: Callable[[str, Action], bool]):
        super().__init__(css_classes=["flat", "g13-device-key"], has_frame=False)
        self.control = control
        self.rect = geo.ALL[control]
        self.enabled = True              # False: shown but neither droppable nor editable (stick not in keys mode)
        # where the assignment pill goes: above the cap (default), on the control, or detached (stick press)
        self.pill_above = control not in geo.PILL_ON_CONTROL and control != "STICK_PRESS"
        self.detached_pill: Gtk.Label | None = None
        self._action = Action.none()
        self._rgb = (51, 153, 255)
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0, valign=Gtk.Align.FILL)
        self._pill = Gtk.Label(css_classes=["g13-pill"], ellipsize=Pango.EllipsizeMode.END, halign=Gtk.Align.CENTER,
                               max_width_chars=14, visible=False)
        # the cap legend is never ellipsized: a legend wider than its slot is centred on it by DeviceView
        self._cap = Gtk.Label(label=TITLES.get(control, control), css_classes=["g13-cap"], halign=Gtk.Align.CENTER,
                              valign=Gtk.Align.CENTER, vexpand=True)
        if not self._cap.get_label():
            self._cap.set_visible(False)
        if control == "STICK_PRESS":
            # the pill is a sibling placed by DeviceView, not a child of the button
            self.detached_pill = self._pill
            self._pill.set_valign(Gtk.Align.CENTER)
        else:
            if not self.pill_above:
                self._pill.set_valign(Gtk.Align.CENTER)
                self._pill.set_vexpand(True)
            box.append(self._pill)
        box.append(self._cap)
        self.set_child(box)
        self.connect("clicked", lambda *_: on_click(control))
        make_action_target(self, lambda a: on_drop(control, a), lambda: self.enabled)
        self.set_scale(1.0)

    def set_scale(self, scale: float) -> None:
        self._scale = scale
        self._pill.set_attributes(_attrs(PILL_PX * scale, bold=True))
        self._cap.set_attributes(_attrs(CAP_PX * scale, self._rgb, bold=True))

    def set_backlight(self, rgb: tuple[int, int, int]) -> None:
        self._rgb = rgb
        self.set_scale(self._scale)

    def set_action(self, action: Action, label: str | None = None) -> None:
        self._action = action
        # the pill keeps its place when empty (opacity, not visibility), so the legend never jumps
        self._pill.set_visible(True)
        self._pill.set_opacity(1.0 if action.type != "none" else 0.0)
        self._pill.set_label(label if label is not None else action_label(action))
        self.set_tooltip_text(self._tooltip(action))
        if action.type == "none":
            self.remove_css_class("g13-bound")
        else:
            self.add_css_class("g13-bound")

    def _tooltip(self, action: Action) -> str:
        if action.type == "none":
            return self.control
        shown = action_label(action)
        plain = action.describe()
        return f"{self.control}: {shown}" + (f" ({plain})" if plain != shown else "")

    def set_disabled_label(self, text: str | None) -> None:
        """Stick directions while the stick is not in keys mode: show why instead of a binding."""
        self.enabled = text is None
        if text is None:
            self.remove_css_class("g13-inactive")
            self.set_action(self._action)
        else:
            self.add_css_class("g13-inactive")
            self._pill.set_visible(True)
            self._pill.set_opacity(1.0)
            self._pill.set_label(text)
            self.set_tooltip_text(f"{self.control}: the stick is in {text.lower()} mode (Stick tab)")

    def set_pressed(self, pressed: bool) -> None:
        if pressed:
            self.add_css_class("g13-pressed")
        else:
            self.remove_css_class("g13-pressed")


class ModeKey(Gtk.Button):
    def __init__(self, name: str, on_click: Callable[[int], None]):
        super().__init__(css_classes=["flat", "g13-device-key", "g13-mode-key"], has_frame=False)
        self.name = name
        self.rect = geo.M_KEYS[name]
        self._label = Gtk.Label(label=name, css_classes=["g13-cap"], halign=Gtk.Align.CENTER, valign=Gtk.Align.CENTER)
        self.set_child(self._label)
        self._rgb = (51, 153, 255)
        self.set_scale(1.0)
        if name != "MR":
            self.connect("clicked", lambda *_: on_click(int(name[1])))
        else:
            self.set_sensitive(False)
            self.set_tooltip_text("MR: starts and stops a macro recording (Macros tab)")

    def set_scale(self, scale: float) -> None:
        self._scale = scale
        self._label.set_attributes(_attrs(CAP_PX * scale * 0.85, self._rgb, bold=True))

    def set_backlight(self, rgb: tuple[int, int, int]) -> None:
        self._rgb = rgb
        self.set_scale(self._scale)

    def set_active(self, active: bool) -> None:
        if active:
            self.add_css_class("g13-mode-active")
        else:
            self.remove_css_class("g13-mode-active")


class DeviceView(Gtk.Widget):
    """Picture + overlays. Children are positioned by hand from device_geometry."""

    def __init__(self, on_edit: Callable[[str], None], on_mode: Callable[[int], None], on_drop: Callable[[str, Action], bool]):
        super().__init__(hexpand=True, vexpand=True, overflow=Gtk.Overflow.HIDDEN)
        self._texture = Gdk.Texture.new_from_filename(str(files("g13d") / "data" / "g13.png"))
        self._scale = 1.0
        self.keys: dict[str, DeviceKey] = {}
        self.modes: dict[str, ModeKey] = {}
        for control in geo.ALL:
            k = DeviceKey(control, on_edit, on_drop)
            k.set_parent(self)
            self.keys[control] = k
        self._press_pill = self.keys["STICK_PRESS"].detached_pill
        assert self._press_pill is not None
        self._press_pill.set_parent(self)
        self._press_pill.set_css_classes(["g13-pill", "g13-pill-detached"])
        for name in geo.M_KEYS:
            m = ModeKey(name, on_mode)
            m.set_parent(self)
            self.modes[name] = m

    def do_dispose(self) -> None:
        for child in list(self.keys.values()) + list(self.modes.values()) + [self._press_pill]:
            child.unparent()
        self.keys.clear()
        self.modes.clear()

    def do_get_request_mode(self) -> Gtk.SizeRequestMode:
        return Gtk.SizeRequestMode.CONSTANT_SIZE

    def do_measure(self, orientation: Gtk.Orientation, _for_size: int):
        if orientation == Gtk.Orientation.HORIZONTAL:
            return 360, geo.IMAGE_W, -1, -1
        return int(360 / geo.ASPECT), geo.IMAGE_H, -1, -1

    def do_size_allocate(self, width: int, height: int, _baseline: int) -> None:
        scale = min(width / geo.IMAGE_W, height / geo.IMAGE_H)
        ox, oy = (width - geo.IMAGE_W * scale) / 2, (height - geo.IMAGE_H * scale) / 2
        self._origin = (ox, oy)
        if abs(scale - self._scale) > 1e-3:
            self._scale = scale
            for child in list(self.keys.values()) + list(self.modes.values()):
                child.set_scale(scale)
        for child in list(self.keys.values()) + list(self.modes.values()):
            x, y, w, h = child.rect
            px, py = ox + x * geo.IMAGE_W * scale, oy + y * geo.IMAGE_H * scale
            pw, ph = w * geo.IMAGE_W * scale, h * geo.IMAGE_H * scale
            if isinstance(child, DeviceKey) and child.pill_above:
                pill = PILL_H * scale          # the pill hangs above the cap
                py, ph = py - pill, ph + pill
            # never underallocate, and let a label outgrow a narrow slot (up to 1.8x) rather than ellipsize:
            # the widget is centred on its slot either way
            mw, nw = child.measure(Gtk.Orientation.HORIZONTAL, -1)[:2]
            mh, nh = child.measure(Gtk.Orientation.VERTICAL, -1)[:2]
            grow = 2.6 if isinstance(child, DeviceKey) and not child.pill_above else 1.8
            aw, ah = max(pw, mw, min(nw, pw * grow)), max(ph, mh)
            px -= (aw - pw) / 2
            py -= (ah - ph) / 2
            child.allocate(int(aw), int(ah), -1, Gsk.Transform.new().translate(Graphene.Point().init(px, py)))
        # the stick's own pill, top-right of it
        x, y, w, h = geo.STICK_PRESS_PILL
        px, py = ox + x * geo.IMAGE_W * scale, oy + y * geo.IMAGE_H * scale
        pw, ph = w * geo.IMAGE_W * scale, h * geo.IMAGE_H * scale
        nw = self._press_pill.measure(Gtk.Orientation.HORIZONTAL, -1)[1]
        nh = self._press_pill.measure(Gtk.Orientation.VERTICAL, -1)[1]
        aw, ah = max(pw, min(nw, pw * 1.5)), max(ph, nh)
        self._press_pill.allocate(int(aw), int(ah), -1,
                                  Gsk.Transform.new().translate(Graphene.Point().init(px + pw - aw, py + (ph - ah) / 2)))
        self._press_line = (px + pw * 0.2, py + ah / 2 + 2, ox + geo.STICK_CENTER[0] * geo.IMAGE_W * scale,
                            oy + geo.STICK_CENTER[1] * geo.IMAGE_H * scale)

    def do_snapshot(self, snapshot: Gtk.Snapshot) -> None:
        ox, oy = getattr(self, "_origin", (0.0, 0.0))
        rect = Graphene.Rect().init(ox, oy, geo.IMAGE_W * self._scale, geo.IMAGE_H * self._scale)
        snapshot.append_texture(self._texture, rect)
        if self._press_pill.get_visible() and hasattr(self, "_press_line"):
            # leader line from the detached pill to the edge of the stick cap
            x0, y0, cx, cy = self._press_line
            r = geo.STICK_RADIUS * geo.IMAGE_W * self._scale * 0.55
            dx, dy = cx - x0, cy - y0
            d = (dx * dx + dy * dy) ** 0.5 or 1.0
            x1, y1 = cx - dx / d * r, cy - dy / d * r
            pb = Gsk.PathBuilder()
            pb.move_to(x0, y0)
            pb.line_to(x1, y1)
            color = self.get_color()
            snapshot.append_stroke(pb.to_path(), Gsk.Stroke.new(max(1.5, 2 * self._scale)), color)
        for child in list(self.keys.values()) + list(self.modes.values()) + [self._press_pill]:
            self.snapshot_child(child, snapshot)


class DevicePage(Gtk.Box):
    """Same interface as KeysPage (set_profile / set_mode / refresh / set_pressed), device layout."""

    def __init__(self, on_edit: Callable[[str], None], on_mode: Callable[[int], None],
                 on_drop: Callable[[str, Action], bool], on_stick_tab: Callable[[], None],
                 label_for: LabelFor = action_label):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=6, margin_top=6, margin_bottom=6,
                         margin_start=6, margin_end=6)
        self._on_edit = on_edit
        self._on_stick_tab = on_stick_tab
        self._label_for = label_for
        self._profile: Profile | None = None
        self._mode = 1
        self._rgb: tuple[int, int, int] | None = None
        self.view = DeviceView(self._clicked, on_mode, self._dropped)
        self._on_drop = on_drop
        self.append(self.view)
        self._hint = Gtk.Label(label="Click a key or drop an assignment on it. M1–M3 switch the mode shown.",
                               css_classes=["dim-label", "caption"], wrap=True, justify=Gtk.Justification.CENTER)
        self.append(self._hint)

    # ---- routing ----------------------------------------------------------------------
    def _clicked(self, control: str) -> None:
        if not self.view.keys[control].enabled:
            self._on_stick_tab()
        else:
            self._on_edit(control)

    def _dropped(self, control: str, action: Action) -> bool:
        return self._on_drop(control, action)

    # ---- state ------------------------------------------------------------------------
    def set_profile(self, profile: Profile | None) -> None:
        self._profile = profile
        self.refresh()

    def set_mode(self, mode: int) -> None:
        self._mode = mode
        self.refresh()

    def refresh(self) -> None:
        if self._profile is not None and self._profile.backlight != self._rgb:
            self._rgb = self._profile.backlight
            for k in list(self.view.keys.values()) + list(self.view.modes.values()):
                k.set_backlight(self._rgb)
        for name, m in self.view.modes.items():
            m.set_active(name == f"M{self._mode}")
        stick_mode = self._profile.stick.mode if self._profile else "keys"
        for control, k in self.view.keys.items():
            action = self._profile.binding(self._mode, control) if self._profile else Action.none()
            k.set_action(action, self._label_for(action))
            if control in STICK_DIRS:
                k.set_disabled_label(None if stick_mode == "keys" else STICK_MODE_LABELS.get(stick_mode, stick_mode))

    def set_pressed(self, control: str, pressed: bool) -> None:
        k = self.view.keys.get(control)
        if k is not None:
            k.set_pressed(pressed)
